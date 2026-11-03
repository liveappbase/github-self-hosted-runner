"""The release's wiring for golden-gate: install links it (TOOLS); release-check holds the constants that two scripts set
to one value across the scripts (CONSTANT_NAMES): REALRUN (golden-build, golden-gate), STATEDIR (golden-build,
golden-prune), PINDIR (runner-updater, golden-build), PROTECTED (runner-updater, golden-prune) and DD (runner-updater,
runner-journal). release-check runs on a temporary git repository with only the files the constants rule reads; it
downloads nothing there (no manifest, no 02-wall.sh). And every lock-holder message of a script names golden-gate.
"""
import os
import re
import unittest

from tests.studio.support_emudhra import REPO, ZSH, assert_no_ci, read, run, tmpdir, write

GIT_ENV = {'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}


def tools():
    m = re.search(r'^TOOLS=\(([^)]*)\)$', read(os.path.join(REPO, 'install')), re.M)
    return m.group(1).split()


class InstallTools(unittest.TestCase):
    def test_install_links_golden_gate(self):
        self.assertIn('golden-gate', tools())

    def test_every_tool_install_links_is_in_the_release(self):
        for t in tools():   # install STOPs on "the release has no bin/<tool>"
            self.assertTrue(os.path.isfile(os.path.join(REPO, 'bin', t)), t)


class ReleaseCheckConstants(unittest.TestCase):
    # NAME: (its line in each script, the script whose value the test changes, the other script that sets it)
    WIRING = {'REALRUN': ('/Users/ci/bin/real-run', 'golden-gate', 'golden-build'),
              'STATEDIR': ('/Users/ci/.local/state/runner-updater', 'golden-prune', 'golden-build'),
              'PINDIR': ('$STATEDIR/pin', 'runner-updater', 'golden-build'),
              'PROTECTED': ('$STATEDIR/protected', 'runner-updater', 'golden-prune'),
              'DD': ('/bin/dd', 'runner-updater', 'runner-journal')}

    def check(self, name, value):
        line, changed, other = self.WIRING[name]
        d = tmpdir(self)
        env = dict(GIT_ENV, HOME=d)
        rc_text = read(os.path.join(REPO, 'tools', 'release-check'))
        # the script under test: its /Users/ci strings are compared, never opened (and --build is not used here)
        assert_no_ci(self, rc_text, ('/Users/ci/mac-runner', '/Users/ci and /Users/admin', '/Users/ci or /Users/admin'),
                     'tools/release-check')
        write(os.path.join(d, 'tools', 'release-check'), rc_text, 0o755)
        for f in (changed, other):   # data for release-check: read, never run
            text = read(os.path.join(REPO, 'bin', f))
            # the line NAME=VALUE, alone or before a comment
            self.assertEqual(len(re.findall(r'^%s=%s(?=[ \n])' % (re.escape(name), re.escape(line)), text, re.M)), 1, f)
            if f == changed:
                self.assertEqual(text.count('\n%s=%s\n' % (name, line)), 1, f)
                text = text.replace('\n%s=%s\n' % (name, line), '\n%s=%s\n' % (name, value))
            write(os.path.join(d, 'bin', f), text, 0o755)
        for argv in (['init', '-q'], ['add', '-A'], ['commit', '-q', '-m', 'wiring test']):
            r = run(['/usr/bin/git'] + argv, env=env, cwd=d)
            self.assertEqual(r.returncode, 0, r.stderr)
        return run([ZSH, '-f', os.path.join(d, 'tools', 'release-check')], env=env, cwd=d)

    def two_values_are_red(self, name):
        line = self.WIRING[name][0]
        r = self.check(name, line + '-other')
        self.assertTrue(any(l.startswith('RED constants: %s has 2 values' % name) for l in r.stdout.splitlines()), r.stdout)
        # control: the same value in both scripts gives no finding for NAME
        r = self.check(name, line)
        self.assertFalse(any(name in l for l in r.stdout.splitlines()), r.stdout)
        self.assertIn('release-check: checking HEAD', r.stdout)   # it ran

    def test_two_values_of_realrun_are_red(self):
        self.two_values_are_red('REALRUN')

    def test_two_values_of_statedir_are_red(self):
        self.two_values_are_red('STATEDIR')

    def test_two_values_of_pindir_are_red(self):
        self.two_values_are_red('PINDIR')

    def test_two_values_of_protected_are_red(self):
        self.two_values_are_red('PROTECTED')

    def test_two_values_of_dd_are_red(self):
        self.two_values_are_red('DD')


class LockHolderMessages(unittest.TestCase):
    """A message that lists who may hold the runner lock names golden-gate too (it holds the lock for its whole run).
    wall-check and real-run are left out: they are wall-proof tools, and a changed byte in them needs a new wall-check
    on every host (runner-enable compares their sha256 with the wall proof)."""

    PROOF_TOOLS = ('wall-check', 'real-run')

    def test_every_lock_holder_list_names_golden_gate(self):
        files = [os.path.join('bin', f) for f in sorted(os.listdir(os.path.join(REPO, 'bin')))] + ['install']
        found = []
        for rel in files:
            if os.path.basename(rel) in self.PROOF_TOOLS:
                continue
            for n, l in enumerate(read(os.path.join(REPO, rel)).splitlines(), 1):
                if 'golden-build' in l and 'runscaler' in l and 'is running' in l:   # a list of lock holders
                    found.append((rel, n, l))
        self.assertGreaterEqual(len(found), 6, found)   # golden-build, runner-enable (2), install (2), golden-gate
        self.assertEqual([(rel, n) for rel, n, l in found if 'golden-gate' not in l], [])


if __name__ == '__main__':
    unittest.main()
