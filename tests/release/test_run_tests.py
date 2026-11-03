"""tools/run-tests, the parallel test runner: it runs the tests that `python3 -I -m unittest discover -s tests -t .`
runs, one unittest process per module, N at a time. Each cell builds a small tree of planted test modules in a
temporary folder and runs the runner there (and, where a cell compares, the plain discover line too): the same test
count as plain discover (a module's and a package's load_tests included); a failing module is rc 1 and named; a module
killed by SIGKILL, one that does not report, one whose report is not a pass, one that fails to import, and one that
loads more or fewer tests than discovery found each count as failed and are named; a discovery that fails or finds
nothing is red; -j 1 and -j 4 give the same
results (and -j 4 runs modules at once, -j 1 never); the module with the most tests starts first; each module runs
with the caller's env and -I; a SIGTERM ends the run red and ends the module it was running; the mutant that ignores a
module's rc goes red."""
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNNER = os.path.join(REPO, 'tools', 'run-tests')

T_OK = '''import unittest


class T(unittest.TestCase):
    def test_a(self):
        pass

    def test_b(self):
        pass

    @unittest.skip('planted skip')
    def test_c(self):
        pass
'''
T_TWO = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n\n' \
        '    def test_b(self):\n        pass\n'
T_ONE = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n'
T_IN_INIT = 'import unittest\n\n\nclass InInit(unittest.TestCase):\n    def test_in_init(self):\n        pass\n'
T_BAD = '''import unittest


class T(unittest.TestCase):
    def test_fails(self):
        self.fail('planted failure')

    def test_passes(self):
        pass
'''
T_MIXED = '''import unittest


class T(unittest.TestCase):
    def test_fails(self):
        self.fail('planted failure')

    def test_errs(self):
        raise RuntimeError('planted error')

    def test_passes(self):
        pass

    @unittest.skip('planted skip')
    def test_skipped(self):
        pass
'''
# the module's one test ends its process in a way the planted line names (LINE replaces `pass`)
T_END = '''import atexit
import os
import signal
import unittest


class T(unittest.TestCase):
    def test_ends(self):
        LINE

    def test_other(self):
        pass
'''
KILL_NOW = 'os.kill(os.getpid(), signal.SIGKILL)'                      # killed mid-run: no report
KILL_AT_EXIT = 'atexit.register(os.kill, os.getpid(), signal.SIGKILL)'  # killed after the report: only the rc says so
EXIT0_NOW = 'os._exit(0)'                                                # rc 0, but no report
FAIL_EXIT0 = 'atexit.register(os._exit, 0); self.fail("planted failure")'   # a failing report, but rc 0
# discovery passes its pattern to a module's load_tests (a run by module name passes none: then it loads 0 tests)
T_LOAD_TESTS = T_ONE + '\n\ndef load_tests(loader, tests, pattern):\n    return tests if pattern else unittest.TestSuite()\n'
# a package's load_tests that picks one test of one of its modules: discovery runs that test and no other of tests/a
T_PKG_LOAD_TESTS = '''import unittest


def load_tests(loader, tests, pattern):
    from tests.a import test_one
    return unittest.TestSuite([test_one.T('test_a')])
'''
# a module whose tests depend on what ran before it in the one process: in discovery tests.a.test_one is imported
# first and it has 1 test; alone in its own process it has 2
T_ORDER = '''import sys
import unittest


class T(unittest.TestCase):
    def test_a(self):
        pass


if 'tests.a.test_one' not in sys.modules:
    T.test_b = lambda self: None
'''
# its twin in the other direction: in discovery it has 2 tests, and the second fails; alone it has 1, so a run that let
# it pass would drop that failing test without a sign
T_FEWER = '''import sys
import unittest


class T(unittest.TestCase):
    def test_a(self):
        pass


if 'tests.a.test_one' in sys.modules:
    T.test_b = lambda self: self.fail('planted failure')
'''
# a module that imports IMPORT: discovery cannot load a module whose import raises, so it makes one failing test that
# names the module (and loads no module); that test counts for the module it names
T_IMPORT = 'import unittest\nimport IMPORT\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n'

# the base tree: 7 tests in 4 modules (a package's own __init__ is one), 1 skipped; a helper that does not match
# test*.py, a module with no test and a folder with no __init__.py hold tests that discovery does not run
BASE = {
    'tests/__init__.py': '',
    'tests/a/__init__.py': '',
    'tests/a/test_one.py': T_OK,
    'tests/a/test_two.py': T_TWO,
    'tests/a/helper.py': T_ONE,
    'tests/b/__init__.py': T_IN_INIT,
    'tests/b/test_three.py': T_ONE,
    'tests/b/test_empty.py': '"""no test here"""\n',
    'tests/noinit/test_unseen.py': T_ONE,
}
BASE_MODULES = ['tests.a.test_one', 'tests.a.test_two', 'tests.b', 'tests.b.test_three']

MOD = re.compile(r'^run-tests: (tests[.\w]*): (OK|FAILED \(([^)]*)\))'
                 r'(?:: ran (\d+), failures (\d+), errors (\d+), skipped (\d+))? in [0-9.]+ s$', re.M)
SUM = re.compile(r'^run-tests: ran (\d+) tests in (\d+) modules, (\d+) at a time, in [0-9.]+ s: '
                 r'failures (\d+), errors (\d+), skipped (\d+)$', re.M)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


class Tree:
    """A temporary repository root holding tests/ (BASE unless base=False, then FILES over it)."""

    def __init__(self, test, files=None, base=True):
        self.test = test
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='runtests-'))
        test.addCleanup(shutil.rmtree, self.root, True)
        for p, t in list((BASE if base else {}).items()) + list((files or {}).items()):
            write(os.path.join(self.root, p), t)

    def path(self, *p):
        return os.path.join(self.root, *p)

    def plain(self, start='tests'):
        """the reference line: (rc, its 'Ran N tests' number or None, its stderr)"""
        r = subprocess.run([sys.executable, '-I', '-m', 'unittest', 'discover', '-s', start, '-t', '.'],
                           cwd=self.root, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
        ran = re.findall(r'^Ran (\d+) tests? in ', r.stderr, re.M)
        return r.returncode, int(ran[-1]) if ran else None, r.stderr

    def run(self, *args, runner=RUNNER, env=None):
        r = subprocess.run([sys.executable, '-I', runner] + list(args), cwd=self.root, capture_output=True,
                           text=True, timeout=120, env=env, stdin=subprocess.DEVNULL)
        r.modules = {m[0]: m for m in MOD.findall(r.stdout)}
        r.summary = SUM.findall(r.stdout)
        lines = r.stdout.splitlines()
        r.last = lines[-1] if lines else ''
        return r


def why(r, module):
    return r.modules[module][2]


class TestSameTests(unittest.TestCase):
    def test_the_same_count_as_plain_discover(self):
        t = Tree(self)
        rc, ran, err = t.plain()
        self.assertEqual((rc, ran), (0, 7), err)          # control: the fixture is the tree it says it is
        r = t.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.summary, [(str(ran), '4', str(os.cpu_count() or 1), '0', '0', '1')], r.stdout)
        self.assertEqual(sorted(r.modules), BASE_MODULES, r.stdout)
        self.assertTrue(all(m[1] == 'OK' for m in r.modules.values()), r.stdout)
        self.assertIn('run-tests: tests: 7 tests in 4 modules, %d at a time\n' % (os.cpu_count() or 1), r.stdout)
        self.assertEqual(r.last, 'run-tests: OK')
        # the summary names the slowest modules
        slow = r.stdout.split('run-tests: the slowest modules:\n', 1)[1]
        for m in BASE_MODULES:
            self.assertRegex(slow, r'run-tests: +[0-9.]+ s  %s\n' % re.escape(m))

    def test_an_area_is_a_folder_under_tests(self):
        t = Tree(self)
        rc, ran, err = t.plain('tests/a')
        self.assertEqual((rc, ran), (0, 5), err)
        r = t.run('-j', '2', 'a')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.summary, [(str(ran), '2', '2', '0', '0', '1')], r.stdout)
        self.assertEqual(sorted(r.modules), ['tests.a.test_one', 'tests.a.test_two'])
        # two areas: the tests of both
        r = t.run('a', 'b')
        self.assertEqual([s[:2] for s in r.summary], [('7', '4')], r.stdout)

    def test_the_module_with_the_most_tests_starts_first(self):
        # the slow modules are the long ones: started last, one of them alone would set the wall time
        t = Tree(self, {'tests/__init__.py': '', 'tests/a/__init__.py': '', 'tests/a/test_small.py': T_ONE,
                        'tests/b/__init__.py': '', 'tests/b/test_big.py': T_OK, 'tests/b/test_mid.py': T_TWO,
                        'tests/c/__init__.py': '', 'tests/c/test_small.py': T_ONE}, base=False)
        r = t.run('-j', '1')
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(re.findall(r'^run-tests: start (\S+)$', r.stdout, re.M),
                         ['tests.b.test_big', 'tests.b.test_mid', 'tests.a.test_small', 'tests.c.test_small'])

    def test_v_lists_each_test(self):
        t = Tree(self)
        self.assertRegex(t.run('-v').stdout, r'test_b \(tests\.a\.test_one\.T[.\w]*\) \.\.\. ok\n')
        self.assertNotIn('test_b (tests.a.test_one.T', t.run().stdout)     # control: without -v, dots only

    def test_a_module_load_tests_gets_the_pattern_discovery_passes(self):
        t = Tree(self, {'tests/a/test_lt.py': T_LOAD_TESTS})
        self.assertEqual(t.plain()[:2], (0, 8))
        r = t.run()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(r.modules['tests.a.test_lt'][1:4], ('OK', '', '1'))
        self.assertEqual([s[0] for s in r.summary], ['8'])

    def test_a_package_load_tests_is_honoured(self):
        t = Tree(self, {'tests/a/__init__.py': T_PKG_LOAD_TESTS})
        self.assertEqual(t.plain()[:2], (0, 3))
        r = t.run()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(sorted(r.modules), ['tests.a', 'tests.b', 'tests.b.test_three'])
        self.assertEqual([s[:2] for s in r.summary], [('3', '3')])

    def test_a_module_that_loads_other_tests_than_discovery_found_fails(self):
        t = Tree(self, {'tests/a/test_order.py': T_ORDER})
        self.assertEqual(t.plain()[:2], (0, 8))
        r = t.run()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(why(r, 'tests.a.test_order'), 'loaded 2 tests, discovery found 1')
        self.assertEqual(r.last, 'run-tests: FAILED: 1 of 5 modules: tests.a.test_order (loaded 2 tests, discovery '
                                 'found 1)')
        # control: the same module without the test that depends on the order passes
        t = Tree(self, {'tests/a/test_order.py': T_ONE})
        self.assertEqual(t.run().returncode, 0)

    def test_a_module_that_loads_fewer_tests_than_discovery_found_fails(self):
        t = Tree(self, {'tests/a/test_order.py': T_FEWER})
        rc, ran, err = t.plain()
        self.assertEqual((rc, ran), (1, 9), err)                  # the plain line runs the second test, and it fails
        self.assertIn('AssertionError: planted failure', err)
        r = t.run()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(r.modules['tests.a.test_order'][1:], ('FAILED (loaded 1 tests, discovery found 2)',
                                                               'loaded 1 tests, discovery found 2', '1', '0', '0', '0'))
        self.assertEqual(r.last, 'run-tests: FAILED: 1 of 5 modules: tests.a.test_order (loaded 1 tests, discovery '
                                 'found 2)')
        # control: the same module without the test that depends on the order passes
        t = Tree(self, {'tests/a/test_order.py': T_ONE})
        self.assertEqual(t.plain()[:2], (0, 8))
        r = t.run()
        self.assertEqual((r.returncode, r.last), (0, 'run-tests: OK'), r.stdout)


class TestFailures(unittest.TestCase):
    def test_a_failing_module_gives_rc_1_and_names_it(self):
        t = Tree(self, {'tests/a/test_bad.py': T_BAD})
        self.assertEqual(t.plain()[0], 1)
        r = t.run()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(r.modules['tests.a.test_bad'][1:], ('FAILED (tests failed, rc 1)', 'tests failed, rc 1', '2',
                                                             '1', '0', '0'))
        self.assertEqual([m for m, v in r.modules.items() if v[1] != 'OK'], ['tests.a.test_bad'])
        self.assertEqual(r.summary, [('9', '5', str(os.cpu_count() or 1), '1', '0', '1')], r.stdout)
        self.assertEqual(r.last, 'run-tests: FAILED: 1 of 5 modules: tests.a.test_bad (tests failed, rc 1)')
        self.assertIn('AssertionError: planted failure', r.stdout)     # the module's own block is in the output

    def test_a_module_that_fails_to_import_gives_rc_1_and_names_it(self):
        t = Tree(self, {'tests/a/test_import.py': T_IMPORT.replace('IMPORT', 'tests.a.no_such_module')})
        rc, ran, err = t.plain()
        self.assertEqual((rc, ran), (1, 8), err)
        self.assertIn("ModuleNotFoundError: No module named 'tests.a.no_such_module'", err)
        r = t.run()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('run-tests: tests: 8 tests in 5 modules, ', r.stdout)
        self.assertEqual(why(r, 'tests.a.test_import'), 'no report, rc 1')
        self.assertEqual(r.last, 'run-tests: FAILED: 1 of 5 modules: tests.a.test_import (no report, rc 1)')
        self.assertIn("ModuleNotFoundError: No module named 'tests.a.no_such_module'", r.stdout)   # its own block
        # control: the same module, importable, passes
        t = Tree(self, {'tests/a/test_import.py': T_IMPORT.replace('IMPORT', 'tests.a.helper')})
        self.assertEqual(t.plain()[:2], (0, 8))
        r = t.run()
        self.assertEqual((r.returncode, r.last), (0, 'run-tests: OK'), r.stdout)
        self.assertEqual(r.modules['tests.a.test_import'][1:4], ('OK', '', '1'))

    def end(self, line):
        return Tree(self, {'tests/a/test_end.py': T_END.replace('LINE', line)}).run()

    def test_a_module_killed_by_sigkill_fails(self):
        r = self.end(KILL_NOW)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(why(r, 'tests.a.test_end'), 'no report, killed by signal 9')
        self.assertEqual(r.last, 'run-tests: FAILED: 1 of 5 modules: tests.a.test_end (no report, killed by signal 9)')

    def test_a_module_killed_after_its_report_fails(self):
        r = self.end(KILL_AT_EXIT)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(r.modules['tests.a.test_end'][1:], ('FAILED (killed by signal 9)', 'killed by signal 9', '2',
                                                             '0', '0', '0'))

    def test_a_module_that_exits_0_with_no_report_fails(self):
        r = self.end(EXIT0_NOW)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(why(r, 'tests.a.test_end'), 'no report')

    def test_a_module_whose_report_fails_with_rc_0_fails(self):
        r = self.end(FAIL_EXIT0)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(r.modules['tests.a.test_end'][1:], ('FAILED (tests failed)', 'tests failed', '2', '1', '0',
                                                             '0'))

    def test_control_the_same_module_that_ends_normally_passes(self):
        r = self.end('pass')
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(r.modules['tests.a.test_end'][1], 'OK')
        self.assertEqual(r.last, 'run-tests: OK')

    def test_mutant_that_ignores_a_module_rc_is_seen(self):
        with open(RUNNER) as f:
            text = f.read()
        old = 'if rc != 0:'
        self.assertEqual(text.count(old), 1)
        t = Tree(self, {'tests/a/test_end.py': T_END.replace('LINE', KILL_AT_EXIT)})
        write(t.path('mutant'), text.replace(old, 'if False:'))
        r = t.run(runner=t.path('mutant'))
        self.assertEqual((r.returncode, r.last), (0, 'run-tests: OK'), r.stdout)   # what the cells above would see

    def test_discovery_that_fails_is_red(self):
        t = Tree(self)
        self.assertEqual(t.plain('tests/noinit')[0], 1)
        r = t.run('noinit')
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(r.last, 'run-tests: FAILED: discovery (no report, rc 1)')
        self.assertIn('ImportError', r.stdout)

    def test_a_discovery_that_reports_then_exits_non_zero_is_red(self):
        # a module that ends its process at exit when it is imported: the plain line, which imports it, ends that way
        t = Tree(self, {'tests/a/test_atexit.py': 'import atexit\nimport os\n\natexit.register(os._exit, 3)\n' + T_ONE})
        self.assertEqual(t.plain()[0], 3)
        r = t.run()
        self.assertEqual((r.returncode, r.last), (1, 'run-tests: FAILED: discovery (rc 3)'), r.stdout)

    def test_no_test_found_is_red(self):
        t = Tree(self, {'tests/none/__init__.py': '', 'tests/none/test_empty.py': '"""no test"""\n'})
        r = t.run('none')
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(r.last, 'run-tests: FAILED: discovery found no test')

    def test_usage_errors_are_rc_2(self):
        t = Tree(self)
        for args in (['-j', '0'], ['-j', 'x'], ['nosuch'], ['a', 'a'], ['../tests'], ['a/'], ['.']):
            r = t.run(*args)
            self.assertEqual(r.returncode, 2, (args, r.stdout, r.stderr))
            self.assertEqual(r.stdout, '', args)
        shutil.rmtree(t.path('tests'))
        r = t.run()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn('no tests/ folder here', r.stderr)


# two modules that each wait (up to WAIT s) for the other to run at the same time, and write whom they met
T_MEET = '''import os
import time
import unittest

D = %(d)r


class T(unittest.TestCase):
    def test_meet(self):
        me = os.path.join(D, 'running-%(name)s')
        open(me, 'w').close()
        try:
            end, met = time.monotonic() + %(wait)s, []
            while time.monotonic() < end and not met:
                met = [n[8:] for n in os.listdir(D) if n.startswith('running-') and n != 'running-%(name)s']
                time.sleep(0.02)
            with open(os.path.join(D, 'met-%(name)s'), 'w') as f:
                f.write(' '.join(met))
        finally:
            os.remove(me)
'''


class TestParallel(unittest.TestCase):
    def meet(self, j):
        d = os.path.realpath(tempfile.mkdtemp(prefix='runtests-meet-'))
        self.addCleanup(shutil.rmtree, d, True)
        t = Tree(self, {'tests/__init__.py': '', 'tests/a/__init__.py': '', 'tests/a/test_mixed.py': T_MIXED,
                        'tests/r/__init__.py': '',
                        'tests/r/test_meet_a.py': T_MEET % {'d': d, 'name': 'a', 'wait': 4},
                        'tests/r/test_meet_b.py': T_MEET % {'d': d, 'name': 'b', 'wait': 4}}, base=False)
        r = t.run('-j', str(j))
        with open(os.path.join(d, 'met-a')) as fa, open(os.path.join(d, 'met-b')) as fb:
            met = (fa.read(), fb.read())
        mods = sorted(v[:2] + v[3:] for v in r.modules.values())
        return r, mods, [s[:2] + s[3:] for s in r.summary], met

    def test_j1_matches_j4(self):
        r1, mods1, sum1, met1 = self.meet(1)
        r4, mods4, sum4, met4 = self.meet(4)
        self.assertEqual((r1.returncode, r4.returncode), (1, 1), r1.stdout + r4.stdout)
        self.assertEqual(mods1, mods4)
        self.assertEqual(mods1, [('tests.a.test_mixed', 'FAILED (tests failed, rc 1)', '4', '1', '1', '1'),
                                 ('tests.r.test_meet_a', 'OK', '1', '0', '0', '0'),
                                 ('tests.r.test_meet_b', 'OK', '1', '0', '0', '0')])
        self.assertEqual(sum1, sum4)
        self.assertEqual(sum1, [('6', '3', '1', '1', '1')])
        self.assertEqual(r1.last, r4.last)
        # control: -j 4 ran the two modules at the same time, -j 1 never did
        self.assertEqual(met4, ('b', 'a'))
        self.assertEqual(met1, ('', ''))
        self.assertIn(', 4 at a time, ', r4.stdout)
        self.assertIn(', 1 at a time, ', r1.stdout)


T_ENV = '''import json
import os
import sys
import unittest


class T(unittest.TestCase):
    def test_env(self):
        with open(%(out)r, 'w') as f:
            json.dump({'JQ': os.environ.get('JQ'), 'isolated': sys.flags.isolated}, f)
'''

T_HANG = '''import os
import time
import unittest


class T(unittest.TestCase):
    def test_wait(self):
        with open(%(pid)r + '.tmp', 'w') as f:
            f.write(str(os.getpid()))
        os.rename(%(pid)r + '.tmp', %(pid)r)
        end = time.monotonic() + 30
        while not os.path.exists(%(go)r) and time.monotonic() < end:
            time.sleep(0.05)
        open(%(pid)r + '.done', 'w').close()       # it ended on its own, not by a signal
'''


class TestProcess(unittest.TestCase):
    def test_each_module_runs_with_the_callers_env_and_isolated(self):
        out = os.path.realpath(tempfile.mkdtemp(prefix='runtests-env-'))
        self.addCleanup(shutil.rmtree, out, True)
        t = Tree(self, {'tests/e/__init__.py': '', 'tests/e/test_env.py': T_ENV % {'out': os.path.join(out, 'env')}})
        env = dict(os.environ, JQ='/planted/jq')
        self.assertEqual(t.run('e', env=env).returncode, 0)
        with open(os.path.join(out, 'env')) as f:
            self.assertEqual(f.read(), '{"JQ": "/planted/jq", "isolated": 1}')
        # control: a caller with no JQ gives none
        env.pop('JQ')
        self.assertEqual(t.run('e', env=env).returncode, 0)
        with open(os.path.join(out, 'env')) as f:
            self.assertEqual(f.read(), '{"JQ": null, "isolated": 1}')

    def hang(self, go):
        t = Tree(self, {'tests/h/__init__.py': '', 'tests/h/test_hang.py': T_HANG % {'pid': t_path(self, 'pid'),
                                                                                       'go': t_path(self, 'go')}})
        if go:
            write(t_path(self, 'go'), '')
        self.addCleanup(write, t_path(self, 'go'), '')          # a cell that fails still lets the module end
        p = subprocess.Popen([sys.executable, '-I', RUNNER, 'h'], cwd=t.root, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        end = time.monotonic() + 60
        while not os.path.exists(t_path(self, 'pid')) and p.poll() is None and time.monotonic() < end:
            time.sleep(0.02)
        self.assertTrue(go or os.path.exists(t_path(self, 'pid')), 'the module did not start')
        with open(t_path(self, 'pid')) as f:
            child = int(f.read())
        if not go:
            p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=120)
        return p.returncode, out, child

    def test_sigterm_ends_the_run_red_and_ends_its_modules(self):
        rc, out, child = self.hang(go=False)
        self.assertEqual(rc, 1, out)
        self.assertIn('run-tests: tests.h.test_hang: FAILED (interrupted) in ', out)
        self.assertEqual(out.splitlines()[-1], 'run-tests: FAILED: interrupted by signal 15, 1 of 1 modules not done: '
                                               'tests.h.test_hang')
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)
        self.assertFalse(os.path.exists(t_path(self, 'pid.done')), 'the module ended on its own: the run did not end it')

    def test_control_the_same_module_that_is_let_go_passes(self):
        rc, out, _ = self.hang(go=True)
        self.assertEqual((rc, out.splitlines()[-1]), (0, 'run-tests: OK'), out)
        self.assertTrue(os.path.exists(t_path(self, 'pid.done')))


def t_path(test, name):
    """a file of the cell's own folder, outside the tree"""
    if not hasattr(test, '_files'):
        test._files = os.path.realpath(tempfile.mkdtemp(prefix='runtests-files-'))
        test.addCleanup(shutil.rmtree, test._files, True)
    return os.path.join(test._files, name)


if __name__ == '__main__':
    unittest.main()
