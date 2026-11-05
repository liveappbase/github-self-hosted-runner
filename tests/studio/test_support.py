"""support.py's own guards: a rewrite that does not match, a host path left in a copy, the stub's argv log, the
clean environment, and the lock holder (hold_lock), which waits for its lock. Each guard has a control that must
pass."""
import fcntl
import os
import subprocess
import time
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


def probe(lock):
    """lockf -t 0 on lock now, as wait_for polls it: 0 free, 75 held"""
    return subprocess.run(['/usr/bin/lockf', '-k', '-s', '-t', '0', lock, '/usr/bin/true']).returncode


def held_at_start(sb, lock):
    """From now on sb.start runs with lock held by THIS process (an flock, as lockf takes it) at the instant the
    started process begins, and lets it go when that process has ended or 0.5 s have passed. start returns only
    after that, so the caller's own wait begins with the lock free: a probe that held the lock for a moment just when
    the holder tried it (the red on main, run 42035056492), made certain."""
    start = sb.start

    def injected(argv, extra_env=None, name='proc'):
        fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            p = start(argv, extra_env, name)
            end = time.monotonic() + 0.5
            while p.poll() is None and time.monotonic() < end:
                time.sleep(0.01)
        finally:
            os.close(fd)
        return p
    sb.start = injected


class TestHoldLock(unittest.TestCase):
    """hold_lock: a REAL lockf holds the lock and runs its command until the test ends; hold_lock returns only once
    it holds the lock, and a holder that ends first fails the test. The holder WAITS for the lock: another process
    that holds it for a moment when the holder starts delays the holder and never ends it."""

    def test_a_hold_at_its_start_delays_the_holder_and_never_ends_it(self):
        sb = Sandbox(self)
        lock = sb.path('lock')
        held_at_start(sb, lock)
        p = sb.hold_lock(lock)
        self.assertIsNone(p.poll())
        self.assertEqual(probe(lock), 75)

    def test_control_the_same_hold_ends_a_lockf_that_does_not_wait(self):
        # the injection is live: a lockf -t 0 started at the same instant gives up, and the lock is free after
        sb = Sandbox(self)
        lock = sb.path('lock')
        held_at_start(sb, lock)
        p = sb.start(['/usr/bin/lockf', '-k', '-t', '0', lock, '/bin/sleep', '600'], name='no-wait')
        self.assertEqual(p.poll(), 75, sb.output('no-wait'))
        self.assertEqual(probe(lock), 0)

    def test_control_no_hold_the_holder_holds_it_at_once(self):
        sb = Sandbox(self)
        lock = sb.path('lock')
        p = sb.hold_lock(lock, argv=['/bin/zsh', '-f', '-c', 'print -r -- ran; exec /bin/sleep 600'], name='h')
        self.assertIsNone(p.poll())
        self.assertEqual(probe(lock), 75)
        sb.wait_for(lambda: sb.output('h')[0] == 'held\nran\n', 'its command to run')

    def test_a_holder_that_ends_before_it_holds_the_lock_fails_the_test(self):
        sb = Sandbox(self)
        lock = sb.path('no-folder', 'lock')              # lockf cannot create it, and ends at once
        with self.assertRaisesRegex(AssertionError, 'the holder could not take'):
            sb.hold_lock(lock)


if __name__ == '__main__':
    unittest.main()
