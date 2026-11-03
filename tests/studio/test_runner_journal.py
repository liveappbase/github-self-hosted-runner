"""bin/runner-journal FILE KEY VALUE: one line appended and fsynced (dd conv=notrunc,fsync), or STOP with FILE unchanged.

Each injected failure has a control that must come out the other way.
"""
import os
import unittest

from tests.studio.support_emudhra import ZSH, copy_script, read, run, stub, tmpdir, write


class RunnerJournal(unittest.TestCase):
    def setUp(self):
        self.d = tmpdir(self)
        self.tool = os.path.join(self.d, 'bin', 'runner-journal')
        copy_script(self, 'bin/runner-journal', self.tool)
        self.j = os.path.join(self.d, 'journal')

    def journal(self, *args, tool=None):
        return run([ZSH, '-f', tool or self.tool, *args], cwd=self.d)

    def assert_stop(self, r):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r'^runner-journal: STOP ')

    def test_one_line_per_call(self):
        r = self.journal(self.j, 'gate-clone', 's1-gate-20261101120000')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(self.j), 'gate-clone s1-gate-20261101120000\n')
        r = self.journal(self.j, 'enable-start', 'a b c')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(self.j), 'gate-clone s1-gate-20261101120000\nenable-start a b c\n')

    def test_newline_in_value_stops_file_unchanged(self):
        write(self.j, 'target abc\n')
        self.assert_stop(self.journal(self.j, 'gate-clone', 's1-gate-x\nforged-key y'))
        self.assertEqual(read(self.j), 'target abc\n')
        # control: the same value without the newline is appended
        r = self.journal(self.j, 'gate-clone', 's1-gate-x forged-key y')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(self.j), 'target abc\ngate-clone s1-gate-x forged-key y\n')

    def test_other_control_characters_stop(self):
        write(self.j, 'target abc\n')
        for bad in ('a\tb', 'a\rb', 'a\x7fb', 'a\x1bb'):
            self.assert_stop(self.journal(self.j, 'k', bad))
        self.assertEqual(read(self.j), 'target abc\n')
        r = self.journal(self.j, 'k', 'a b')   # control
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_value_at_most_1000_bytes(self):
        write(self.j, '')
        self.assert_stop(self.journal(self.j, 'k', 'x' * 1001))
        # bytes, not characters: 501 two-byte characters are 1002 bytes
        self.assert_stop(self.journal(self.j, 'k', 'é' * 501))
        self.assertEqual(read(self.j), '')
        r = self.journal(self.j, 'k', 'x' * 1000)   # control
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.journal(self.j, 'k', 'é' * 500)   # control: 1000 bytes
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(read(self.j).splitlines()), 2)

    def test_key_pattern(self):
        write(self.j, '')
        for bad in ('Gate', '-x', '1x', 'a_b', 'a b', 'a' + 'b' * 41, ''):
            self.assert_stop(self.journal(self.j, bad, 'v'))
        self.assertEqual(read(self.j), '')
        for good in ('a', 'a' + 'b' * 40, 'gate-clone', 'enable-done'):   # control
            r = self.journal(self.j, good, 'v')
            self.assertEqual(r.returncode, 0, good + r.stdout + r.stderr)

    def test_file_rules(self):
        self.assert_stop(self.journal('journal', 'k', 'v'))   # relative
        missing = os.path.join(self.d, 'no-such-folder', 'journal')
        r = self.journal(missing, 'k', 'v')
        self.assert_stop(r)
        self.assertIn('the folder of FILE does not exist', r.stdout)
        self.assertFalse(os.path.exists(os.path.dirname(missing)))
        os.mkdir(os.path.join(self.d, 'adir'))
        r = self.journal(os.path.join(self.d, 'adir'), 'k', 'v')
        self.assert_stop(r)
        self.assertIn('is not a regular file', r.stdout)
        self.assert_stop(self.journal(self.j, 'k'))   # usage
        self.assertFalse(os.path.exists(self.j))
        r = self.journal(self.j, 'k', 'v')   # control: an absolute path in a folder that exists
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(self.j), 'k v\n')

    def dd_copy(self, body):
        tool = os.path.join(self.d, 'bin2', 'runner-journal')
        dd = stub(os.path.join(self.d, 'stub', 'dd'), body)
        copy_script(self, 'bin/runner-journal', tool, rewrites=[('DD=/bin/dd', 'DD=' + dd)])
        return tool

    def test_dd_failing_exits_1(self):
        tool = self.dd_copy('print -u2 -r -- "dd: injected failure"; exit 1\n')
        r = self.journal(self.j, 'k', 'v', tool=tool)
        self.assert_stop(r)
        self.assertIn('fsync', r.stdout)
        # dd's one line reaches the STOP line whole (a one-line value is not an array: [1] would be its first letter)
        self.assertTrue(r.stdout.endswith('(the line is written, not known to be on disk): dd: injected failure\n'),
                        r.stdout)
        # control: the real dd
        r = self.journal(self.j, 'k', 'v')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_dd_is_asked_for_fsync_on_the_file(self):
        rec = os.path.join(self.d, 'dd-args')
        tool = self.dd_copy('print -r -- "$*" >> %s\nexit 0\n' % rec)
        r = self.journal(self.j, 'k', 'v', tool=tool)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(rec), 'if=/dev/null of=%s conv=notrunc,fsync\n' % self.j)
        self.assertEqual(read(self.j), 'k v\n')


if __name__ == '__main__':
    unittest.main()
