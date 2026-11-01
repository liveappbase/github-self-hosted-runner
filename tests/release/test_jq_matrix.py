"""tools/release-check's jq-matrix rule, red on planted inputs: core/TESTED_JQ's rows are the jq builds the core and the
watchdog are tested with. A `local:PATH` row runs the tests of its areas with JQ=PATH when PATH prints the row's
version; a `ci:IMAGE` row is the workflow job "jq VERSION (IMAGE)", whose newest check run on the tagged commit
--build reads with gh. With --build a row that cannot run or be read is RED; without --build it is named "absent: not
tested here". release-check runs on a temporary repository holding only what the rule reads, a planted test that
passes or fails, a stub `jq` (a version, nothing else) and a stub `gh`; it downloads nothing there. This area is not
one the rule runs, so the rule never runs these cells."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ZSH = '/bin/zsh'
GIT_ENV = {'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}

PASS = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        pass\n'
FAIL = 'import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail("planted")\n'
GH = r'''#!%(py)s -I
import json, sys
with open(%(log)r, 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\n')
a = json.load(open(%(ans)r))
if a.get('rc'):
    sys.stderr.write('gh: HTTP 502\n')
    sys.exit(a['rc'])
for r in a['runs']:
    print('%%s\t%%s\t%%s\t%%s' %% (r['id'], r['status'], r['conclusion'] or '', r['name']))
'''
FAKEJQ = '#!/bin/sh\n[ "$1" = --version ] && echo %s && exit 0\nexit 9\n'


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)
    os.chmod(path, mode)


class JqMatrix(unittest.TestCase):
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp(prefix='jqmatrix-'))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.repo = os.path.join(self.d, 'repo')
        self.stubs = os.path.join(self.d, 'stubs')
        os.makedirs(self.stubs)
        os.symlink(sys.executable, os.path.join(self.stubs, 'python3'))
        self.jq = os.path.join(self.d, 'bin', 'jq')
        write(self.jq, FAKEJQ % 'jq-9.9-test', 0o755)
        self.gh_log = os.path.join(self.d, 'gh.log')
        self.gh({'runs': []})

    def gh(self, answer):
        write(os.path.join(self.d, 'gh.json'), json.dumps(answer))
        write(os.path.join(self.stubs, 'gh'), GH % {'py': sys.executable, 'log': self.gh_log,
                                                     'ans': os.path.join(self.d, 'gh.json')}, 0o755)

    def check(self, rows, tests=PASS, build=False, extra=None):
        with open(os.path.join(REPO, 'tools', 'release-check')) as f:
            write(os.path.join(self.repo, 'tools', 'release-check'), f.read(), 0o755)
        if rows is not None:
            write(os.path.join(self.repo, 'core', 'TESTED_JQ'), '# planted\n' + ''.join(r + '\n' for r in rows))
        write(os.path.join(self.repo, 'tests', '__init__.py'), '')
        for area in ('core', 'watchdog'):
            write(os.path.join(self.repo, 'tests', area, '__init__.py'), '')
            write(os.path.join(self.repo, 'tests', area, 'test_planted.py'), tests)
        for path, text in (extra or {}).items():
            write(os.path.join(self.repo, path), text)
        env = dict(GIT_ENV, HOME=self.d, PATH=self.stubs + ':/usr/bin:/bin', LC_ALL='C')
        for argv in (['init', '-q'], ['add', '-A'], ['commit', '-q', '-m', 'jq matrix test'],
                     ['tag', '-a', 'v0.0.0', '-m', 'test']):
            r = subprocess.run(['/usr/bin/git'] + argv, env=env, cwd=self.repo, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        argv = [ZSH, '-f', os.path.join(self.repo, 'tools', 'release-check')]
        if build:
            plist = os.path.join(self.d, 'private.txt')
            write(plist, 'zzz-no-such-value\n')
            argv += ['--build', 'v0.0.0', '--private-list', plist, '--out', os.path.join(self.d, 'out')]
        r = subprocess.run(argv, env=env, cwd=self.repo, capture_output=True, text=True, timeout=300)
        self.assertIn('release-check: checking ', r.stdout, r.stderr)    # it ran
        return r.stdout.splitlines()

    def red(self, out):
        return [l for l in out if l.startswith('RED jq-matrix')]

    def local(self):
        return 'jq-9.9-test core,watchdog local:%s' % self.jq

    # local rows
    def test_a_local_row_runs_the_tests_of_its_areas(self):
        out = self.check([self.local()])
        self.assertEqual(self.red(out), [])
        self.assertIn('release-check: jq jq-9.9-test (%s): tests/core pass' % self.jq, out)
        self.assertIn('release-check: jq jq-9.9-test (%s): tests/watchdog pass' % self.jq, out)

    def test_a_failing_test_is_red(self):
        self.assertTrue(self.red(self.check([self.local()], tests=FAIL)))

    def test_only_its_own_areas(self):
        out = self.check(['jq-9.9-test watchdog local:%s' % self.jq])
        self.assertNotIn('release-check: jq jq-9.9-test (%s): tests/core pass' % self.jq, out)
        self.assertIn('release-check: jq jq-9.9-test (%s): tests/watchdog pass' % self.jq, out)

    def test_an_absent_local_row_is_named_without_build(self):
        out = self.check(['jq-1.0 core,watchdog local:%s/none/jq' % self.d])
        self.assertEqual(self.red(out), [])
        self.assertIn('release-check: jq jq-1.0 (local:%s/none/jq) absent: not tested here' % self.d, out)

    def test_a_local_binary_with_another_version_is_absent(self):
        out = self.check(['jq-1.0 core local:%s' % self.jq])
        self.assertIn('release-check: jq jq-1.0 (local:%s) absent: not tested here' % self.jq, out)

    def test_an_absent_local_row_is_red_with_build(self):
        out = self.check(['jq-1.0 core,watchdog local:%s/none/jq' % self.d], build=True)
        self.assertTrue(self.red(out))
        # control: a local row that runs is not red with --build
        self.setUp()
        self.assertEqual(self.red(self.check([self.local()], build=True)), [])

    # ci rows
    def ci(self, *runs):
        self.gh({'runs': [{'id': i, 'status': s, 'conclusion': c, 'name': n} for i, s, c, n in runs]})

    CI = 'jq-1.7 core,watchdog ci:ubuntu:24.04'
    JOB = 'jq jq-1.7 (ubuntu:24.04)'

    def test_a_ci_row_is_named_without_build_and_gh_is_not_called(self):
        out = self.check([self.CI])
        self.assertEqual(self.red(out), [])
        self.assertTrue(any(l.startswith('release-check: jq jq-1.7 (ci:ubuntu:24.04) absent: not tested here') for l in out))
        self.assertFalse(os.path.exists(self.gh_log))

    def test_a_ci_row_with_build_needs_its_newest_check_run_green(self):
        self.ci((5, 'completed', 'success', self.JOB))
        out = self.check([self.CI], build=True)
        self.assertEqual(self.red(out), [])
        self.assertIn('release-check: jq jq-1.7 (ci:ubuntu:24.04): its CI job "%s" passed on this commit' % self.JOB, out)
        with open(self.gh_log) as f:
            calls = [json.loads(l) for l in f]
        self.assertTrue(all(c[0] == 'api' and '-X' not in c and '--method' not in c for c in calls), calls)

    def test_a_failed_check_run_is_red(self):
        self.ci((5, 'completed', 'failure', self.JOB))
        self.assertTrue(self.red(self.check([self.CI], build=True)))

    def test_no_check_run_is_red(self):
        self.ci((5, 'completed', 'success', 'jq jq-1.8.1 (ubuntu:26.04)'))
        self.assertTrue(self.red(self.check([self.CI], build=True)))

    def test_the_newest_check_run_decides(self):
        self.ci((5, 'completed', 'failure', self.JOB), (9, 'completed', 'success', self.JOB))
        self.assertEqual(self.red(self.check([self.CI], build=True)), [])
        self.setUp()
        self.ci((5, 'completed', 'success', self.JOB), (9, 'in_progress', None, self.JOB))
        self.assertTrue(self.red(self.check([self.CI], build=True)))

    def test_check_runs_that_cannot_be_read_are_red(self):
        self.gh({'rc': 1, 'runs': []})
        red = self.red(self.check([self.CI], build=True))
        self.assertEqual(len(red), 1)
        self.assertIn('cannot be read with gh', red[0])     # not "no check run": the operator learns why

    # the file
    def test_a_row_not_of_the_shape_is_red(self):
        self.assertTrue(self.red(self.check(['jq-1.7 core'])))
        self.setUp()
        self.assertTrue(self.red(self.check(['jq-1.7 everything ci:ubuntu:24.04'])))

    def test_no_tested_jq_beside_the_core_is_red(self):
        self.assertTrue(self.red(self.check(None, extra={'core/idle.jq': '.\n'})))
        # control: a tree with no core/ has nothing to test
        self.setUp()
        self.assertEqual(self.red(self.check(None)), [])

    def test_an_empty_list_is_red(self):
        self.assertTrue(self.red(self.check([])))


if __name__ == '__main__':
    unittest.main()
