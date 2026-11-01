"""The release's wiring for golden-gate: install links it (TOOLS), and release-check holds its REALRUN constant to one
value across the scripts (CONSTANT_NAMES). release-check runs on a temporary git repository with only the files
the constants rule reads; it downloads nothing there (no manifest, no 02-wall.sh).
"""
import os
import re
import unittest

from tests.studio.support_emudhra import REPO, ZSH, read, run, tmpdir, write

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


class ReleaseCheckRealrun(unittest.TestCase):
    def check(self, realrun_in_gate):
        d = tmpdir(self)
        env = dict(GIT_ENV, HOME=d)
        write(os.path.join(d, 'tools', 'release-check'), read(os.path.join(REPO, 'tools', 'release-check')), 0o755)
        for f in ('golden-build', 'golden-gate'):
            write(os.path.join(d, 'bin', f), read(os.path.join(REPO, 'bin', f)), 0o755)
        gate = os.path.join(d, 'bin', 'golden-gate')
        text = read(gate)
        self.assertEqual(text.count('\nREALRUN=/Users/ci/bin/real-run\n'), 1)
        write(gate, text.replace('\nREALRUN=/Users/ci/bin/real-run\n', '\nREALRUN=%s\n' % realrun_in_gate), 0o755)
        for argv in (['init', '-q'], ['add', '-A'], ['commit', '-q', '-m', 'wiring test']):
            r = run(['/usr/bin/git'] + argv, env=env, cwd=d)
            self.assertEqual(r.returncode, 0, r.stderr)
        return run([ZSH, '-f', os.path.join(d, 'tools', 'release-check')], env=env, cwd=d)

    def test_two_values_of_realrun_are_red(self):
        r = self.check('/Users/ci/bin/real-run-other')
        self.assertTrue(any(l.startswith('RED constants: REALRUN has 2 values') for l in r.stdout.splitlines()), r.stdout)
        # control: the same value in both scripts gives no REALRUN finding
        r = self.check('/Users/ci/bin/real-run')
        self.assertFalse(any('REALRUN' in l for l in r.stdout.splitlines()), r.stdout)
        self.assertIn('release-check: checking HEAD', r.stdout)   # it ran


if __name__ == '__main__':
    unittest.main()
