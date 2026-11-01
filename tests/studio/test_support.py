"""support.py's own guards: a rewrite that does not match, a host path left in a copy, the stub's argv log, and
the clean environment. Each guard has a control that must pass."""
import os
import unittest

from tests.studio.support import Sandbox


class TestCopy(unittest.TestCase):
    def script(self, sb):
        return sb.write(sb.path('src', 'tool'), '#!/bin/zsh -f\n# run /Users/ci/bin/tool\nX=/Users/ci/x\n')

    def test_a_rewrite_that_does_not_match_fails(self):
        sb = Sandbox(self)
        with self.assertRaisesRegex(AssertionError, 'rewrite target is not in the script'):
            sb.copy_script(self.script(sb), [('Y=/Users/ci/x', 'Y=/elsewhere')])

    def test_a_host_path_left_fails(self):
        sb = Sandbox(self)
        with self.assertRaisesRegex(AssertionError, 'still names /Users/ci'):
            sb.copy_script(self.script(sb), [('X=/Users/ci/x', 'X=/elsewhere')])

    def test_an_allowed_string_that_is_not_there_fails(self):
        sb = Sandbox(self)
        with self.assertRaisesRegex(AssertionError, 'allowed string is not in the copy'):
            sb.copy_script(self.script(sb), [('X=/Users/ci/x', 'X=/elsewhere')], allow=['/Users/ci/nothing'])

    def test_control_rewritten_and_allowed(self):
        sb = Sandbox(self)
        dest = sb.copy_script(self.script(sb), [('X=/Users/ci/x', 'X=/elsewhere')], allow=['run /Users/ci/bin/tool'])
        with open(dest) as f:
            self.assertEqual(f.read(), '#!/bin/zsh -f\n# run /Users/ci/bin/tool\nX=/elsewhere\n')
        self.assertTrue(os.access(dest, os.X_OK))


class TestCleanup(unittest.TestCase):
    def test_sandbox_is_removed_even_with_mode_000_inside(self):
        inner = unittest.TestCase()
        sb = Sandbox(inner)
        locked = sb.mkdir('locked', 'deeper')
        sb.write(os.path.join(locked, 'f'), 'x', 0)
        os.chmod(locked, 0)
        os.chmod(os.path.dirname(locked), 0)
        self.assertTrue(os.path.isdir(sb.root))
        inner.doCleanups()
        self.assertFalse(os.path.exists(sb.root))


class TestStubAndEnv(unittest.TestCase):
    def test_stub_logs_each_argv(self):
        sb = Sandbox(self)
        sb.stub('thing', 'exit 3')
        for argv in (['a b', "it's", ''], []):
            res = sb.run(['thing'] + argv)
            self.assertEqual(res.returncode, 3)
        self.assertEqual(sb.calls('thing'), [['a b', "it's", ''], []])

    def test_env_is_clean(self):
        sb = Sandbox(self)
        probe = 'print -r -- "$HOME|$TMPDIR|$PATH|$LC_ALL|${+STUDIO_PROBE}"'
        os.environ['STUDIO_PROBE'] = '1'
        self.addCleanup(os.environ.pop, 'STUDIO_PROBE', None)
        res = sb.run(['/bin/zsh', '-f', '-c', probe])
        self.assertEqual(res.stdout, '%s|%s/|%s:/usr/bin:/bin:/usr/sbin:/sbin|C|0\n' % (sb.home, sb.tmp, sb.stubs))
        res = sb.run(['/bin/zsh', '-f', '-c', probe], extra_env={'STUDIO_PROBE': '1'})   # the control
        self.assertTrue(res.stdout.endswith('|1\n'), res.stdout)


if __name__ == '__main__':
    unittest.main()
