"""support.py's own guards: a rewrite that does not match, a host path left in a copy, the stub's argv log, the
clean environment, the lock holder (hold_lock), which waits for its lock, the wait for a process group's end
(group_gone) and the cleanup that kills what is left of a group (kill_group). Each guard has a control that must
pass."""
import fcntl
import os
import signal
import subprocess
import unittest
from unittest import mock

from tests.studio.support import Sandbox, group_alive, group_gone, members


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


def ended(p):
    """the started process has ended (a lockf -t 0 ends at its one try)"""
    return p.poll() is not None


def waits(p):
    """the started lockf waits for the lock, or it has ended. A lockf that waits sleeps in its open of the lock (ps:
    S or I), so it has made its try. ps cannot tell that sleep from another: this relies on a lockf not sleeping
    before its try (it reads no input and starts no child before it)."""
    if ended(p):
        return True
    st = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(p.pid)], capture_output=True, text=True,
                        stdin=subprocess.DEVNULL).stdout.strip()
    return st.startswith(('S', 'I'))


def held_at_start(sb, lock, until):
    """From now on sb.start runs with lock held by THIS process (an flock, as lockf takes it) at the instant the
    started process begins, and lets it go once until(p) holds for the started process p: a state, never a time
    (wait_for's bound fails the test when it never holds). start returns only after that, so the caller's own wait
    begins with the lock free: a probe that held the lock for a moment just when the holder tried it (the red on
    main, run 42035056492), made certain."""
    start = sb.start

    def injected(argv, extra_env=None, name='proc'):
        fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            p = start(argv, extra_env, name)
            sb.wait_for(lambda: until(p), 'the injected hold to end: %s' % until.__name__)
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
        held_at_start(sb, lock, waits)
        p = sb.hold_lock(lock)
        self.assertIsNone(p.poll())
        self.assertEqual(probe(lock), 75)

    def test_control_the_same_hold_ends_a_lockf_that_does_not_wait(self):
        # the injection is live: a lockf -t 0 started at the same instant gives up, and the lock is free after. The
        # hold lasts until that lockf has ended, so a lockf that reaches its try late (a busy host: 1 s) gives up too.
        for late in (False, True):
            with self.subTest(late=late):
                sb = Sandbox(self)
                lock = sb.path('lock')
                held_at_start(sb, lock, ended)
                no_wait = ['/usr/bin/lockf', '-k', '-t', '0', lock, '/bin/sleep', '600']
                late_argv = ['/bin/zsh', '-f', '-c', '/bin/sleep 1; exec "$@"', 'late'] + no_wait
                p = sb.start(late_argv if late else no_wait, name='no-wait')
                self.assertEqual(p.poll(), 75, sb.output('no-wait'))
                self.assertEqual(probe(lock), 0)

    def test_control_no_hold_the_holder_holds_it_at_once(self):
        sb = Sandbox(self)
        lock = sb.path('lock')
        p = sb.hold_lock(lock, argv=['/bin/zsh', '-f', '-c', 'print -r -- ran; exec /bin/sleep 600'], name='h')
        self.assertIsNone(p.poll())
        self.assertEqual(probe(lock), 75)
        sb.wait_for(lambda: sb.output('h')[0] == 'held\nran\n', 'its command to run')

    def test_a_holder_that_holds_nothing_fails_the_test(self):
        # hold_lock's own probe: its holder runs without its lockf, so it prints `held` and holds no lock. The control:
        # test_control_no_hold_the_holder_holds_it_at_once (the real lockf: the probe reads the lock held)
        sb = Sandbox(self)
        lock = sb.path('lock')
        start = sb.start

        def no_lockf(argv, extra_env=None, name='proc'):
            self.assertEqual(argv[0], '/usr/bin/lockf')
            return start(argv[argv.index(lock) + 1:], extra_env, name)   # the holder's command alone
        sb.start = no_lockf
        with self.assertRaisesRegex(AssertionError, 'a probe reads .* free under its holder'):
            sb.hold_lock(lock)
        self.assertTrue(sb.output('lock-holder')[0].startswith('held\n'))   # it did print held: only the probe saw it

    def test_a_holder_that_ends_before_it_holds_the_lock_fails_the_test(self):
        sb = Sandbox(self)
        lock = sb.path('no-folder', 'lock')              # lockf cannot create it, and ends at once
        with self.assertRaisesRegex(AssertionError, 'the holder could not take'):
            sb.hold_lock(lock)


class TestGroupGone(unittest.TestCase):
    """The helper the TERM cells wait with (FLAKE, 11-04): os.killpg(pgid, 0) can raise PermissionError (EPERM) at high
    load while the group's last members exit. group_gone ends when no member of the group is alive, also on EPERM, and
    keeps waiting while a member lives. EPERM is injected; the controls are the real killpg."""

    def group(self, member):
        """a process group whose leader has exited; MEMBER: a sleep of it still runs (the test's cleanup kills it)"""
        self.sb = Sandbox(self)
        p = self.sb.start(['/bin/sh', '-c', '/bin/sleep 600 & exit 0' if member else 'exit 0'], name='group')
        p.wait(timeout=30)
        return p

    @staticmethod
    def eperm(pgid, sig):
        raise PermissionError(1, 'Operation not permitted')

    def test_eperm_with_a_member_alive_keeps_waiting(self):
        p = self.group(True)
        with mock.patch.object(os, 'killpg', self.eperm):
            self.assertFalse(group_gone(p))
            with self.assertRaisesRegex(AssertionError, 'timed out waiting for the group'):
                self.sb.wait_for(lambda: group_gone(p), 'the group', timeout=0.2)
        self.assertFalse(group_gone(p))                          # the control: the real killpg finds the member

    def test_eperm_with_no_member_alive_ends(self):
        p = self.group(False)
        with mock.patch.object(os, 'killpg', self.eperm):
            self.assertTrue(group_gone(p))
            self.sb.wait_for(lambda: group_gone(p), 'the group')  # the wait ends, it does not raise
        self.assertTrue(group_gone(p))                           # the control: the real killpg finds no group


class TestKillGroup(unittest.TestCase):
    """Sandbox.start's cleanup kills what is left of the group with kill_group (test_golden_gate's reap uses the same
    helper). At the end of a cell the group can hold only zombies for a moment, and macOS answers EPERM to killpg then:
    the cleanup must end with no error and reap the process. Real processes and the host's own killpg answers; the
    control: a live group, whose members the cleanup kills."""

    def cleanup_of(self, script, ready, what, eperm):
        """/bin/sh -c SCRIPT started by sb.start in a test of its own, which ends once ready(the states of the group's
        members) holds (EPERM: and killpg answers EPERM for the group then); unittest then runs that test's cleanups
        -> (the process, the errors and failures of that run)"""
        started = []

        class Inner(unittest.TestCase):
            def runTest(inner):
                sb = Sandbox(inner)
                p = sb.start(['/bin/sh', '-c', script], name='group')
                started.append(p)
                sb.wait_for(lambda: ready(members(p.pid)), 'the group to be ' + what, timeout=30)
                if eperm:   # the injection is live: the host's real answer for this group
                    with inner.assertRaises(PermissionError):
                        os.killpg(p.pid, signal.SIGKILL)
        r = unittest.TestResult()
        Inner().run(r)
        return started[0], [text for _, text in r.errors + r.failures]

    def test_a_group_of_zombies_ends_with_no_error_and_is_reaped(self):
        p, errors = self.cleanup_of('exit 0', lambda m: len(m) == 1 and m[0].startswith('Z'), 'one zombie', True)
        self.assertEqual(errors, [])
        self.assertEqual(p.returncode, 0)                        # reaped: its exit status is read

    def test_control_a_live_group_is_killed(self):
        p, errors = self.cleanup_of('/bin/sleep 600 & exec /bin/sleep 600',
                                    lambda m: len(m) == 2 and not any(s.startswith('Z') for s in m), 'two live', False)
        self.assertEqual(errors, [])
        self.assertEqual(p.returncode, -signal.SIGKILL)
        Sandbox(self).wait_for(lambda: not group_alive(p.pid), 'the member to be killed too', timeout=30)


if __name__ == '__main__':
    unittest.main()
