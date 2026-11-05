"""bin/runner-updater `pass --log FILE` (S3b-5 A3): the timer's pass (config/sh.liveapp.runner-updater.plist) writes its
output to FILE. Only `pass` takes the option (another command: usage, exit 2). FILE over 1 MiB is renamed to FILE.1
first. Each pass writes `=== pass <UTC> pid N` first and `=== end rc N <UTC>` last, also a pass that finds the lock
held. A FILE it cannot open or rename never stops the pass (RECOVER must run): its output stays where it was (the
plist's .err).

The rig is test_runner_updater's (Rig); RECOVER's cell uses test_runner_updater_window's (Win), killed at a step.
"""
import os
import re
import unittest

from tests.studio.test_runner_updater import Rig, read_text
from tests.studio.test_runner_updater_recover import assert_closed, killed
from tests.studio.test_runner_updater_state import hold_lock, release

MIB = 1048576
START = re.compile(r'^=== pass \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC pid (\d+)$')
END = re.compile(r'^=== end rc (\d+) \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC$')


def logged_pass(r, log, script=None):
    return r.sb.run(['/bin/zsh', '-f', script or r.script, 'pass', '--log', log])


class TestPassLog(unittest.TestCase):
    def test_a_pass_writes_its_start_and_end_lines_and_its_output(self):
        r = Rig(self)
        log = r.sb.path('logs', 'runner-updater.log')
        res = logged_pass(r, log)
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, '', ''))
        lines = read_text(log).splitlines()
        self.assertRegex(lines[0], START)
        self.assertEqual(lines[1], 'runner-updater: pass: the updater is OFF: nothing to do')
        self.assertEqual(END.match(lines[2]).group(1), '0')
        self.assertEqual(len(lines), 3)
        # a second pass appends
        logged_pass(r, log)
        lines = read_text(log).splitlines()
        self.assertEqual(len(lines), 6)
        self.assertRegex(lines[3], START)

    def test_the_end_line_has_the_exit_code(self):
        r = Rig(self)
        r.sb.write(os.path.join(r.statedir, 'state.json'), 'not json\n')
        log = r.sb.path('logs', 'runner-updater.log')
        res = logged_pass(r, log)
        self.assertEqual(res.returncode, 1, read_text(log))
        lines = read_text(log).splitlines()
        self.assertTrue(lines[1].startswith('runner-updater: REFUSE '), lines)
        self.assertEqual(END.match(lines[-1]).group(1), '1')

    def test_a_held_lock_writes_both_lines(self):
        r = Rig(self)
        holder = hold_lock(r)
        log = r.sb.path('logs', 'runner-updater.log')
        res = logged_pass(r, log)
        release(r, holder)
        self.assertEqual(res.returncode, 0, read_text(log))
        lines = read_text(log).splitlines()
        self.assertRegex(lines[0], START)
        self.assertEqual(lines[1], 'runner-updater: pass: another run holds the updater lock; this pass ends')
        self.assertEqual(END.match(lines[2]).group(1), '0')

    def big(self, r, size):
        log = r.sb.path('logs', 'runner-updater.log')
        with open(log, 'wb') as f:
            f.write(b'x' * (size - 1) + b'\n')
        return log

    def test_a_file_over_1_mib_is_renamed_first(self):
        r = Rig(self)
        log = self.big(r, MIB + 1)
        old = r.log_bytes(log)
        logged_pass(r, log)
        self.assertEqual(r.log_bytes(log + '.1'), old)
        self.assertRegex(read_text(log).splitlines()[0], START)
        self.assertEqual(len(read_text(log).splitlines()), 3)

    def test_control_a_file_of_exactly_1_mib_is_kept(self):
        r = Rig(self)
        log = self.big(r, MIB)
        logged_pass(r, log)
        self.assertFalse(os.path.exists(log + '.1'))
        text = r.log_bytes(log)
        self.assertEqual(text[:MIB], b'x' * (MIB - 1) + b'\n')
        self.assertRegex(text[MIB:].decode().splitlines()[0], START)

    def test_a_rename_it_cannot_do_never_stops_the_pass(self):
        r = Rig(self)
        d = r.sb.mkdir('ro')
        log = os.path.join(d, 'runner-updater.log')
        with open(log, 'wb') as f:
            f.write(b'x' * MIB + b'\n')
        os.chmod(d, 0o500)                    # the file can be appended to, the folder takes no rename
        self.addCleanup(os.chmod, d, 0o700)
        res = logged_pass(r, log)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('runner-updater: pass: cannot rename %s to %s.1' % (log, log), res.stderr)
        self.assertFalse(os.path.exists(log + '.1'))
        tail = r.log_bytes(log)[MIB + 1:].decode().splitlines()
        self.assertRegex(tail[0], START)
        self.assertEqual(tail[1], 'runner-updater: pass: the updater is OFF: nothing to do')

    def test_a_file_it_cannot_open_never_stops_the_pass_recover_runs(self):
        w = killed(self, 'build-start')       # a window journal is open, CI disabled by the window
        d = w.sb.mkdir('closed')
        os.chmod(d, 0o500)
        self.addCleanup(os.chmod, d, 0o700)
        log = os.path.join(d, 'runner-updater.log')
        res = logged_pass(w.r, log)
        self.assertFalse(os.path.exists(log))
        self.assertIn('runner-updater: recover: the window journal ', res.stdout)   # on the caller's output
        assert_closed(self, w)
        self.assertTrue(os.path.exists(w.r.flag))                                   # CI is back

    def test_control_the_same_journal_with_a_file_it_can_open(self):
        w = killed(self, 'build-start')
        log = w.sb.path('logs', 'runner-updater.log')
        res = logged_pass(w.r, log)
        self.assertEqual(res.stdout, '')
        self.assertIn('runner-updater: recover: the window journal ', read_text(log))
        assert_closed(self, w)


class TestLogUsage(unittest.TestCase):
    def test_only_pass_takes_log_and_it_needs_an_absolute_file(self):
        for args in (['status', '--log', '/x.log'], ['on', '--log', '/x.log'], ['protect', '--log', '/x.log'],
                     ['report', '--log', '/x.log'], ['pass', '--log'], ['pass', '--log', 'relative.log'],
                     ['pass', '--log', '/x.log', 'more'], ['pass', '/x.log']):
            with self.subTest(args=args):
                r = Rig(self)
                res = r.sb.run(['/bin/zsh', '-f', r.script] + args)
                self.assertEqual((res.returncode, res.stdout), (2, ''), res.stderr)
                self.assertTrue(res.stderr.startswith('runner-updater: usage: '), res.stderr)
                self.assertEqual(sorted(os.listdir(r.statedir)), ['protected'])
                self.assertFalse(os.path.exists('/x.log'))

    def test_control_the_usage_names_pass_log(self):
        r = Rig(self)
        res = r.sb.run(['/bin/zsh', '-f', r.script])
        self.assertIn(' pass [--log FILE] ', res.stderr)


if __name__ == '__main__':
    unittest.main()
