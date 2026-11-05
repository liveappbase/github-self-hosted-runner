"""The unattended modes' fix round 1 (S2b-3c-1 B1; build review r1, codex F1-F8 and opus F1-F7): what RECOVER and the
window must do at the edges the first build got wrong. Each class names its finding; each cell has the control that
must come out the other way. RECOVER's main routes are test_recover.py's; a SIGKILL after each journal line,
test_kills.py; the window's main cells, test_unattended.py.

- A ROLLBACK IS DECIDED ONLY BY LINES ABOUT ITS TARGET (B1 DECISIONS): a `validate recover N NON-API|UNKNOWN` (RECOVER's
  validate of the TARGET; another file's is `validate hand N`), `restore`, `stop ROLLBACK FAILED`, or a
  `pre-close-failure` of a start OF THE TARGET (the window's own `starting E`, or RECOVER's `starting E target`).
  RECOVER's starts of the pre-window file (`starting E pre`) or of another file (`starting E other`) decide nothing.
  An open start of the TARGET is waited for to its 10 min and never made again; expired: ONE `pre-close-failure`, then
  THE RESTORE in the same pass. A decided rollback whose close finds the TARGET installed: class `target-failed`.
- ONE READ PER CLOSE: a close's SHA, CONTENT and CLASS are one read of config.toml; a file another actor installed
  meanwhile is `other`, with STOP HAND CHANGE.
- THE INSTALL BOUNDARY: a start proves a file only when it came after max(the journaled install, the file's mtime now).
- A START NEEDS A VALIDATED SHA: `config-sha` is trusted only after the window's `start-state` line (START STATE
  passed); else a copy validates first, and NON-API/UNKNOWN: no start, a STOP that says CI is down, the journal open.
- RUNS EVERYWHERE: a runscaler that is active but serves nothing is no runscaler that runs.
- NO SILENT END WITH CI DOWN: a rollback that found the enabled unit down and ends before its rename leaves its journal
  open, and RECOVER starts runscaler.
- A ONCE-LINE IS KEYED ON ITSELF: a cut between `hand-change` and its STOP: the next pass writes the STOP, once.
- THE LOCKS: no systemctl call of the unattended modes holds fd 8 or fd 9; a killed window's validate try holds the
  updater lock until it ends (the named residual).
- RECOVER journals only a `recover-target` its own reader reads; back goes on through an auto-restart wait.
- The systemctl substitute's job merge (a start during a drain cancels the stop job): the window's "stop failed" and
  RECOVER's "did not stop" / "start failed" branches.
Every cell cuts or ends a REAL window of the real scripts (support.Pool, a throwaway container, a fake clock unless it
says so) and runs RECOVER as the updater's child; no cell asserts a time it waited.
"""
import fcntl
import os
import re
import signal
import subprocess
import time
import unittest

from tests.hetzner.support import needs_container, sha256_file
from tests.hetzner.test_recover import Rec, cut, own
from tests.hetzner.test_unattended import (NEW, NONAPI, PASS, PIMG, UNKNOWN, V, BackRig, Rig, alive, installed, keys,
                                           value)


def ended(test, g):
    """A window of rig G that ran to its end with its journal OPEN, as cut() leaves a cut one: the hooks
    cleared, the logs emptied (so the calls counted are RECOVER's), g.cut its lines."""
    lines = g.p.window()
    test.assertIsNotNone(lines, 'no journal')
    test.assertNotEqual(keys(lines)[-1], 'closed', lines)
    g.p.hooks()
    for n in ('systemctl', 'curl', 'runner'):
        g.p.write(g.p.path('logs', n + '.log'), '')
    g.cut = lines
    return g


def stops(lines, name):
    """The `stop NAME: ...` lines' texts."""
    return [l.split(': ', 1)[1] for l in lines if l.startswith('stop %s: ' % name)]


def starts(lines):
    """The `starting` lines' values."""
    return [l.split(' ', 1)[1] for l in lines if l.startswith('starting ')]


def hold(path):
    """Is the lock file PATH held now (another open file description's view)?"""
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


def until(test, cond, what, bound=120):
    """Wait for a STATE (cond() true), polling; BOUND seconds of the real clock only fail a cell that hangs."""
    t0 = time.time()
    while not cond():
        if time.time() - t0 > bound:
            test.fail('%s did not happen' % what)
        time.sleep(0.1)


@needs_container
class DecidedByItsTarget(unittest.TestCase):
    """B1 DECISIONS, opus F1, F2, F7, codex F1, F5: a rollback is decided only by lines about its TARGET."""

    def test_a_cut_start_of_the_pre_window_file_decides_nothing(self):
        """opus F1 (a): a rollback window cut at its `backup` line (no backup file yet), a person's plain stop; RECOVER
        starts the pre-window file and is cut right after that `starting`. The next RECOVER: that start is no TARGET's:
        it is waited for, it runs: closed pre, no `pre-close-failure`, no ROLLBACK FAILED, CI up. The control: the
        window's own TARGET start that does not run (the cell below) decides."""
        g = cut(self, 'back', ('journal:backup', 'stop', 'kill'))
        g.p.hooks(('journal:starting', 'kill'))
        x = Rec(self, g)
        x.run(-9)
        self.assertEqual(own(x.lines())[-1:], ['starting'])
        g.p.hooks()
        x.run(0)
        lines = x.closed('pre')
        self.assertNotIn('pre-close-failure', keys(lines))
        self.assertEqual(stops(lines, 'ROLLBACK FAILED'), [], lines)
        self.assertIn('running', own(lines))
        self.assertTrue(g.p.unit_now()['active'], 'CI left down')
        self.assertEqual(g.p.config(), g.candidate)

    def test_a_failed_start_of_the_pre_window_file_decides_nothing(self):
        """opus F1 (b): a rollback cut after THE BACKUP's rename (before rename-start), a person's stop; RECOVER's start
        of the pre-window file does not run in 10 min (a crash loop): `pre-close-failure`, open. The next RECOVER (it
        serves now): no ROLLBACK FAILED, no restore: closed pre. The control: the window's own TARGET start (below)."""
        g = cut(self, 'back', ('mv-done:config.toml.backup', 'stop', 'kill'))
        g.p.set_unit(runner='crash')
        x = Rec(self, g)
        x.run(5)
        self.assertEqual(own(x.open()), ['recover-target', 'starting', 'pre-close-failure'])
        g.p.set_unit(runner='serves')
        x.run(0)
        lines = x.closed('pre')
        self.assertEqual(stops(lines, 'ROLLBACK FAILED'), [], lines)
        self.assertNotIn('restore', keys(lines))

    def test_control_the_window_s_own_start_of_the_target_that_did_not_run_decides(self):
        """The window's own start of the TARGET did not run in its 10 min (`pre-close-failure`, the journal open): the
        rollback is decided: THE RESTORE, ROLLBACK FAILED once, the backup installed and started: closed pre."""
        g = BackRig(self)
        g.p.set_unit(runner='serves')
        g.p.hooks(('journal:starting', 'crash'))
        r = g.back()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        ended(self, g)
        self.assertEqual(keys(g.cut)[-1], 'pre-close-failure')
        g.p.hooks(('journal:restore', 'serve'))
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('pre')
        self.assertEqual(g.p.config(), g.candidate)
        self.assertEqual(len(stops(lines, 'ROLLBACK FAILED')), 1, lines)
        self.assertEqual(keys(lines).count('pre-close-failure'), 1)
        self.assertIn('restore', own(lines))

    def test_an_open_start_of_the_target_that_runs_is_no_failed_rollback(self):
        """B1 DECISIONS, opus F2 (c); with the cell below it replaces test_recover's Decided.test_a_rollback_whose_
        start_did_not_run_is_restored_not_started_again (it pinned "a `starting` with no `running` decides"). A rollback
        cut right after its `starting` (before the start ran): its TARGET start is in progress: RECOVER starts the
        stopped unit again with no new line, and it runs: closed target-running, no restore. The control: the cell
        below (it never runs)."""
        g = cut(self, 'back', ('journal:starting', 'kill'))
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('target-running')
        self.assertNotIn('restore', keys(lines))
        self.assertEqual(len(starts(lines)), 1, 'a second `starting`')
        self.assertEqual(len(x.calls('start')), 1)
        self.assertEqual(g.validates(), [], 'the start in progress is of a validated sha: no validate')

    def test_a_target_start_that_never_runs_is_one_failure_then_the_restore(self):
        """B1 DECISIONS, codex F1, opus F2 (a): a rollback cut right after its `starting`, its TARGET never runs (a
        crash loop): waited for to the start's 10 min, ONE `pre-close-failure`, THE RESTORE in the same pass, no second
        start of the TARGET (the one start RECOVER journals is the backup's, `starting E pre`); also when the 10 min ran
        out before RECOVER (then RECOVER never starts the TARGET at all). The control (test_recover TheStart): a switch
        cut the same way gets its second start, then POOL DOWN."""
        for expired in (False, True):
            with self.subTest(expired=expired):
                g = BackRig(self)
                g.p.set_unit(runner='serves')
                g.p.hooks(('journal:starting', 'crash', 'kill'))
                self.assertEqual(g.back().returncode, -9)
                ended(self, g)
                if expired:
                    g.p.clock(plus=601)
                g.p.hooks(('journal:restore', 'serve'))
                x = Rec(self, g)
                x.run(0)
                lines = x.closed('pre')
                self.assertEqual(keys(lines).count('pre-close-failure'), 1, lines)
                self.assertEqual(own(lines)[:3], ['pre-close-failure', 'stop', 'restore'], lines)
                self.assertEqual(len(stops(lines, 'ROLLBACK FAILED')), 1)
                self.assertEqual([s.split(' ')[1:] for s in starts(lines)], [[], ['pre']],
                                 'RECOVER started the TARGET again')
                self.assertEqual(len(x.calls('start')), 1 if expired else 2)
                self.assertEqual(g.p.config(), g.candidate)
                self.assertEqual(g.validates(), [], 'the TARGET was validated again')

    def test_a_person_s_file_recover_started_is_never_restored_over(self):
        """opus F1 (its unmeasured variant): a DECIDED rollback (its TARGET's validate NON-API) meets a person's file H
        with runscaler down: THE ONE RULE: H validates, `recover-target H`, RECOVER starts it, and is cut right after
        that `starting` (of another file: it decides nothing). The next pass: H is RECOVER's own validated file for a
        person, never the TARGET: the start in progress is waited for, H runs, closed other, the backup NOT put back
        over it. The control: the TARGET still installed: THE RESTORE (Decided in test_recover)."""
        g = cut(self, 'back', ('journal:renamed', 'kill'))
        g.p.runner = {'seq': [NONAPI]}
        g.p.hooks(('journal:validate', 'stop', 'kill'))
        x = Rec(self, g)
        x.run(-9)
        h = g.p.config().replace('max-runners = 3\n', 'max-runners = 2\n', 1)
        g.p.write(g.p.rpath('config.toml'), h, 0o600)
        g.p.runner = PASS                                  # H validates
        g.p.hooks(('journal:starting', 'kill'))
        x.run(-9)
        self.assertEqual(keys(x.lines())[-1], 'starting')
        g.p.hooks()
        x.run(0)
        lines = x.closed('other')
        self.assertEqual(g.p.config(), h, 'the backup was put back over the person\'s file')
        self.assertNotIn('restore', keys(lines))
        self.assertEqual([v.split(' ')[1:] for v in starts(lines)], [['other']])

    def test_unknown_restores_with_no_failure_line_and_non_api_holds_rollback_failed(self):
        """B1 DECISIONS: a rollback cut after `stopped`; RECOVER's validate of its TARGET is UNKNOWN: THE RESTORE with
        no `pre-close-failure` and no ROLLBACK FAILED. The control: NON-API: ROLLBACK FAILED."""
        for seq, rbf in (([UNKNOWN], 0), ([NONAPI], 1)):
            with self.subTest(rbf=rbf):
                g = cut(self, 'back', ('journal:stopped', 'kill'))
                g.p.runner = {'seq': seq}
                x = Rec(self, g)
                x.run(0)
                lines = x.closed('pre')
                self.assertNotIn('pre-close-failure', keys(lines))
                self.assertEqual(len(stops(lines, 'ROLLBACK FAILED')), rbf, lines)
                self.assertIn('restore', own(lines))

    def test_a_decided_rollback_that_leaves_the_target_installed_is_target_failed(self):
        """codex F5, opus F7: a decided rollback (its TARGET's validate NON-API) whose close finds the TARGET installed
        never closes target-running or target-idle (the apply step would read "rolled back"): the backup fails its
        config-sha check (the STOP says CI is down: nothing runs), or the unit not enabled with a TARGET process that
        runs and does not RUN (nothing is stopped under it): `target-failed`. The control: an UNDECIDED rollback, the
        TARGET installed, the unit disabled with no process: target-idle (rolled back)."""
        with self.subTest('the backup is not config-sha'):
            g = cut(self, 'back', ('journal:stopped', 'kill'))
            g.p.runner = {'seq': [NONAPI]}
            bk = value(g.cut, 'backup')
            g.p.write(bk, g.p.read(bk) + '# changed\n', 0o600)
            x = Rec(self, g)
            x.run(0)
            lines = x.closed('target-failed')
            rbf = stops(lines, 'ROLLBACK FAILED')
            self.assertEqual(len(rbf), 1, lines)
            self.assertIn('not the config', rbf[0])
            self.assertIn('CI is down', rbf[0])
            self.assertEqual(x.calls('stop') + x.calls('start'), [])
        with self.subTest('not enabled, a TARGET process runs'):
            g = cut(self, 'back', ('journal:stopped', 'kill'))
            g.p.runner = {'seq': [NONAPI]}
            g.p.hooks(('journal:validate', 'kill'))
            x = Rec(self, g)
            x.run(-9)
            g.p.hooks()
            g.p.set_unit(active=True, start=g.p.clock(plus=2), pid=900, enabled=False, runner='hang')
            x.run(0)
            lines = x.closed('target-failed')
            self.assertTrue(stops(lines, 'CI DISABLED'), lines)
            self.assertEqual(x.calls('stop') + x.calls('start'), [])
            self.assertEqual(g.p.unit_now()['pid'], 900)
        with self.subTest('control: undecided, disabled, none runs'):
            g = cut(self, 'back', ('journal:stopped', 'disable', 'kill'))
            x = Rec(self, g)
            x.run(0)
            x.closed('target-idle')


@needs_container
class OneReadPerClose(unittest.TestCase):
    """codex F4: every close's SHA, CONTENT and CLASS come from ONE read of config.toml, the class from that read's
    content, never from a class decided before it. A switch whose window's start did not run (`pre-close-failure`);
    RECOVER's second start does not run either, and a person replaces the TARGET meanwhile (another file, or
    config.toml.prev put back): POOL DOWN, class other, STOP HAND CHANGE. The control: the TARGET unchanged: POOL DOWN,
    target-idle or target-old."""

    def test_a_file_changed_during_the_second_start_closes_other(self):
        for act in ('hand-file', 'put-prev', None):
            with self.subTest(act):
                g = Rig(self)
                g.p.set_unit(runner='serves')
                g.p.hooks(('journal:starting', 'crash'))
                r = g.up()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                ended(self, g)
                if act:
                    g.p.hooks(('systemctl:start-done', act))
                x = Rec(self, g)
                x.run(0)
                lines = x.lines()
                self.assertTrue(stops(lines, 'POOL DOWN'), lines)
                if act:
                    self.assertIn('hand install ' + act, g.p.events())
                    x.closed('other')
                    self.assertEqual(len(stops(lines, 'HAND CHANGE')), 1, lines)
                    self.assertEqual(value(lines, 'hand-change'), sha256_file(g.p.rpath('config.toml')))
                else:
                    self.assertIn(installed(lines)[2], ('target-idle', 'target-old'))
                    x.closed(installed(lines)[2])
                    self.assertEqual(stops(lines, 'HAND CHANGE'), [])

    def test_a_window_close_that_finds_another_file_says_hand_change(self):
        """codex F4, the window's own closes: a person's file installed once `staged` is synced: the window's STOP
        (check failed: D3, the render differs from config.toml in more than its image lines) closes it with the class
        of its one read, other, and a STOP HAND CHANGE. The control: config.toml unchanged: pre, no HAND CHANGE (test_
        unattended's Switch cells)."""
        g = Rig(self)
        g.p.hooks(('journal:staged', 'hand-file'))
        r = g.up()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        lines = g.done()[1]
        self.assertTrue(stops(lines, 'check failed'), lines)
        self.assertEqual(installed(lines)[2], 'other')
        self.assertEqual(installed(lines)[0], sha256_file(g.p.rpath('config.toml')))
        self.assertEqual(len(stops(lines, 'HAND CHANGE')), 1, lines)


@needs_container
class InstallBoundary(unittest.TestCase):
    """codex F3: a start proves a file only when its process started after max(the journaled install second, the
    file's mtime now): for the TARGET (the window's `renamed`) and for the backup THE RESTORE put back (its `renamed`)
    alike. A person installs H and starts it, then puts the file back WITHOUT a restart (a later mtime): the running
    process ran H, so it proves nothing: the restart. The control: a process started after both: closed, no restart."""

    def test_a_process_older_than_the_file_s_mtime_proves_nothing(self):
        for what in ('target', 'restored backup'):
            for after in (False, True):
                with self.subTest(what, started_after_both=after):
                    g = cut(self, 'back', ('journal:renamed', 'kill'))
                    cls = 'target-running'
                    if what == 'restored backup':
                        g.p.runner = {'seq': [NONAPI]}
                        g.p.hooks(('journal:renamed', 'kill'))   # THE RESTORE cut right after its own rename
                        x = Rec(self, g)
                        x.run(-9)
                        g.p.hooks()
                        cls = 'pre'
                    cfg = g.p.rpath('config.toml')
                    keep = g.p.config()
                    g.p.write(cfg, keep.replace('max-runners = 3\n', 'max-runners = 2\n', 1), 0o600)
                    if not after:
                        g.p.set_unit(active=True, start=g.p.clock(plus=2), pid=900)   # H starts
                    m = g.p.clock(plus=5)
                    g.p.write(cfg, keep, 0o600)
                    os.utime(cfg, (m, m))                                            # the file back, no restart
                    if after:
                        g.p.set_unit(active=True, start=g.p.clock(plus=2), pid=900)
                    for n in ('systemctl', 'curl', 'runner'):
                        g.p.write(g.p.path('logs', n + '.log'), '')
                    x = Rec(self, g)
                    x.run(0)
                    lines = x.closed(cls)
                    if after:
                        self.assertEqual(x.calls('stop') + x.calls('start'), [])
                        continue
                    self.assertEqual((len(x.calls('stop')), len(x.calls('start'))), (1, 1), lines)
                    self.assertGreater(int(value(lines, 'running').split()[1]), m)


@needs_container
class ValidatedStart(unittest.TestCase):
    """codex F2: RECOVER starts config.toml only on a sha a line proves: `staged-sha`, a `recover-target`, or
    `config-sha` after the window's `start-state` (START STATE passed: up; back's unit active and started after the
    install). A pending hand edit (installed after runscaler started, never run) that an up window journaled as
    `config-sha` and was cut at, the unit then stopped: a copy validates first (`validate hand`); NON-API or UNKNOWN: no
    start, STOP POOL DOWN that says CI is down, once, the journal open; PASS: the start. A back that found the unit down
    (no START STATE): validated first too. The control: a window cut after START STATE: no validate."""

    def pending(self, at):
        g = Rig(self)
        g.p.write(g.p.rpath('config.toml'), g.old.replace('max-runners = 3\n', 'max-runners = 2\n', 1), 0o600)
        g.p.hooks((at, 'stop', 'kill'))
        self.assertEqual(g.up().returncode, -9)
        return ended(self, g)

    def test_an_unproven_config_sha_is_validated_before_its_start(self):
        for seq, ok in (([NONAPI], False), ([UNKNOWN], False), ([PASS], True)):
            with self.subTest(seq[0]['out'][:20], ok=ok):
                g = self.pending('journal:config-sha')
                g.p.runner = {'seq': seq}
                x = Rec(self, g)
                if ok:
                    x.run(0)
                    lines = x.closed('pre')
                    self.assertEqual(own(lines)[:4], ['validate', 'recover-target', 'starting', 'running'], lines)
                    self.assertEqual(value(lines, 'validate'), 'hand 1 PASS')
                    self.assertEqual(len(x.calls('start')), 1)
                    continue
                r = x.run(5)
                lines = x.open()
                self.assertEqual(x.calls('start'), [])
                self.assertNotIn('recover-target', keys(lines))
                down = stops(lines, 'POOL DOWN')
                self.assertEqual(len(down), 1, lines)
                self.assertIn('CI is down', down[0])
                x.run(5)
                lines = x.open()
                self.assertEqual(len(stops(lines, 'POOL DOWN')), 1, 'the STOP twice')
                self.assertEqual(keys(lines).count('validate'), 2, 'the next pass validates again')
                self.assertEqual(x.calls('start'), [])

    def test_a_back_that_found_the_unit_down_proved_nothing(self):
        g = BackRig(self)
        g.p.set_unit(active=False, pid=0)
        g.p.hooks(('journal:staged', 'kill'))
        self.assertEqual(g.back().returncode, -9)
        ended(self, g)
        self.assertNotIn('start-state', keys(g.cut))
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('pre')
        self.assertEqual(own(lines)[:3], ['validate', 'recover-target', 'starting'], lines)
        self.assertEqual(value(lines, 'validate'), 'hand 1 PASS')

    def test_control_a_window_past_start_state_needs_no_validate(self):
        g = cut(self, 'up', ('journal:staged', 'stop', 'kill'))
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('pre')
        self.assertEqual(g.validates(), [])
        self.assertEqual(own(lines)[:3], ['recover-target', 'starting', 'running'], lines)


@needs_container
class RunsEverywhere(unittest.TestCase):
    """codex F7 (its first input): every "runscaler runs" of RECOVER is RUNS (/healthz lists every set on two reads 3 s
    apart, the same process), never one `proc_now`: a process that is active and hangs before it serves /healthz is no
    runscaler that runs. Step 1 and step 4 (the pre-window file), step 5 (another file): THE START (it does not run:
    `pre-close-failure`, the journal open); the unit disabled: STOP CI DISABLED. The control: a runscaler that serves:
    closed, nothing started, no STOP."""

    def test_a_hung_process_is_no_runscaler_that_runs(self):
        for why, at, more, hand in (('step 1', 'journal:staged', (), False), ('step 4', 'journal:backup', (), False),
                                    ('step 5', 'journal:renamed', (), True),
                                    ('step 1, disabled', 'journal:staged', ('disable-only',), False)):
            for hang in (True, False):
                with self.subTest(why, hang=hang):
                    g = cut(self, 'up', (at,) + (('hang',) if hang else ()) + more + ('kill',))
                    if hand:
                        g.p.write(g.p.rpath('config.toml'), g.p.config().replace('max-runners = 3\n',
                                                                                 'max-runners = 2\n', 1), 0o600)
                    x = Rec(self, g)
                    cls = 'other' if hand else 'pre'
                    if more:
                        x.run(0)
                        lines = x.closed(cls)
                        self.assertEqual(bool(stops(lines, 'CI DISABLED')), hang, lines)
                        self.assertEqual(x.calls('start'), [])
                        continue
                    if not hang:
                        x.run(0)
                        lines = x.closed(cls)
                        self.assertEqual(x.calls('start'), [])
                        self.assertEqual(stops(lines, 'POOL DOWN'), [])
                        continue
                    x.run(5)
                    lines = x.open()
                    self.assertEqual(keys(lines)[-1], 'pre-close-failure', lines)
                    self.assertEqual(len(x.calls('start')), 1)


@needs_container
class CiDownIsNeverSilent(unittest.TestCase):
    """codex F7 (its second input): a rollback that found the enabled unit DOWN (operator (1): it is to be started) and
    ends before its rename (its validate UNKNOWN: `end`; NON-API: STOP ROLLBACK FAILED) leaves its journal OPEN (its
    last word kept), exit 1; RECOVER then validates the pre-window file (no START STATE proved it) and starts it: closed
    pre, the window's last word kept for the apply step. The control: the unit active: the journal closed, `end`."""

    def test_a_down_rollback_that_ends_early_leaves_its_journal_to_recover(self):
        for out, last in ((UNKNOWN, 'end'), (NONAPI, 'stop')):
            with self.subTest(last):
                g = BackRig(self)
                g.p.set_unit(active=False, pid=0)
                g.p.runner = out
                r = g.back()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                lines = g.p.window()
                self.assertEqual(keys(lines)[-1], last, lines)
                self.assertNotIn('installed', keys(lines))
                self.assertIn('RECOVER', r.stdout)
                ended(self, g)
                g.p.runner = PASS
                x = Rec(self, g)
                x.run(0)
                lines = x.closed('pre')
                self.assertEqual(own(lines)[:4], ['validate', 'recover-target', 'starting', 'running'], lines)
                self.assertTrue(g.p.unit_now()['active'])
        with self.subTest('control: active'):
            g = BackRig(self)
            g.p.runner = UNKNOWN
            r = g.back()
            self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
            lines = g.done()[1]
            self.assertIsNotNone(value(lines, 'end'))


@needs_container
class OnceLines(unittest.TestCase):
    """codex F6: a STOP written "once" is checked against the STOP line itself, never against the marker before it: a
    cut between each `hand-change` and its `stop HAND CHANGE` (the window's, and each of RECOVER's), then RECOVER: the
    STOP is written, once, and a file that failed validate is not started. The control: a journal that has the STOP:
    no second one (the pass after)."""

    def test_a_cut_between_hand_change_and_its_stop(self):
        h = lambda t: t.replace('max-runners = 3\n', 'max-runners = 2\n', 1)
        for site in ('the window', 'step 5', 'step 1', 'step 2 disabled', 'the restore', 'a switch\'s validate'):
            with self.subTest(site):
                if site == 'the window':
                    g = Rig(self)
                    g.p.hooks(('journal:renamed', 'edit-config'), ('journal:hand-change', 'kill'))
                    self.assertEqual(g.up().returncode, -9)
                    ended(self, g)
                    self.assertEqual(keys(g.cut)[-1], 'hand-change')
                    x = Rec(self, g)
                    x.run(0)
                    self.assertEqual(len(stops(x.lines(), 'HAND CHANGE')), 1, x.lines())
                    continue
                if site == 'step 5':
                    g = cut(self, 'up', ('journal:stopped', 'kill'))
                    g.p.write(g.p.rpath('config.toml'), h(g.p.config()), 0o600)
                    g.p.runner = {'seq': [NONAPI]}
                elif site == 'step 1':
                    g = cut(self, 'up', ('journal:staged', 'kill'))
                    g.p.write(g.p.rpath('config.toml'), h(g.p.config()), 0o600)
                elif site == 'step 2 disabled':
                    g = cut(self, 'up', ('journal:renamed', 'disable-only', 'kill'))
                    g.p.write(g.p.rpath('config.toml'), h(g.p.config()), 0o600)
                elif site == 'the restore':
                    g = cut(self, 'back', ('journal:renamed', 'kill'))
                    g.p.runner = {'seq': [NONAPI]}
                    g.p.hooks(('journal:validate', 'kill'))
                    Rec(self, g).run(-9)
                    g.p.write(g.p.rpath('config.toml'), h(g.p.config()), 0o600)
                else:
                    g = cut(self, 'up', ('journal:stopped', 'kill'))
                    g.p.write(g.p.rpath('config.toml'), g.p.config() + '# a comment\n', 0o600)
                    g.p.runner = {'seq': [NONAPI]}
                g.p.hooks(('journal:hand-change', 'kill'))
                x = Rec(self, g)
                x.run(-9)
                self.assertEqual(keys(x.lines())[-1], 'hand-change')
                g.p.hooks()
                r = g.p.recover()
                lines = x.lines()
                self.assertEqual(len(stops(lines, 'HAND CHANGE')), 1, lines)
                self.assertGreater(keys(lines)[::-1].index('hand-change'), keys(lines)[::-1].index('stop'))
                self.assertEqual(x.calls('start'), [], 'a file that failed its validate was started')
                if r.returncode == 5:
                    g.p.recover()
                    self.assertEqual(len(stops(x.lines(), 'HAND CHANGE')), 1, 'a second STOP')
                    self.assertEqual(x.calls('start'), [])


@needs_container
class Locks(unittest.TestCase):
    """opus F3, codex F8: no systemctl call of the unattended modes holds fd 8 (pool-image.sh's own lock) or fd 9 (the
    updater lock): a stop client that outlives a killed window would hold both. And 03's render try must hold fd 9 to
    pass it on (03's THE UPDATER'S CHILD check), so a killed window's try holds the updater lock until the try ends (at
    most 130 s, the named residual): it is free once the try has ended. The control: a window that is not killed holds
    the lock during its try."""

    def test_no_systemctl_call_holds_a_lock(self):
        g = cut(self, 'back', ('journal:renamed', 'kill'))   # a switch and a rollback window ran
        g.p.runner = {'seq': [NONAPI]}
        Rec(self, g).run(0)                                  # THE RESTORE: its stop, its start
        calls = g.p.systemctl_fds()
        g = cut(self, 'up', ('journal:starting', 'kill'))
        Rec(self, g).run(0)                                  # RECOVER's start of a start in progress
        calls += g.p.systemctl_fds()
        seen = {c['argv'][1] for c in calls if len(c['argv']) > 1}
        self.assertTrue({'show', 'is-active', 'is-enabled', 'stop', 'start'} <= seen, seen)
        held = [c for c in calls if c['fd8'] or c['fd9']]
        self.assertEqual(held, [], 'a systemctl call held a lock')

    def test_a_killed_window_s_try_holds_the_updater_lock_until_it_ends(self):
        with open(PIMG) as f:
            header = f.read().split('\nset -uo pipefail\n', 1)[0]
        self.assertRegex(header, r'RESIDUAL[^.]*killed window[^.]*130 s', 'the header names the residual and its bound')
        for kill in (True, False):
            with self.subTest(kill=kill):
                g = Rig(self)
                g.p.short_timeout()
                g.p.runner = {'hang': True, 'rc': 1, 'out': 'never\n'}
                g.p.files()
                lock, own_lock = os.path.join(g.p.STATE, 'lock'), g.p.rpath('pool-image.lock')
                p = subprocess.Popen(g.p.holder() + ['bash', os.path.join(g.p.build, 'setup', 'pool-image.sh'), 'up',
                                                     '--unattended', V, NEW],
                                     env=g.p.env(), cwd=g.p.HOME, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, start_new_session=True)

                def stop(p=p):
                    if p.poll() is None:
                        try:
                            os.killpg(p.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        p.wait()
                self.addCleanup(stop)
                until(self, lambda: os.path.exists(g.p.path('logs', 'hang.pid')), 'the validate try')
                self.assertTrue(hold(lock), 'the window holds the updater lock during its try')
                if not kill:
                    out = p.communicate()[0]
                    self.assertEqual(p.returncode, 1, out)
                    self.assertFalse(hold(lock))
                    continue
                os.killpg(p.pid, signal.SIGKILL)
                p.communicate()
                self.assertFalse(hold(own_lock), "the try holds pool-image.sh's own lock")
                pids = g.p.timeout_pids()
                self.assertEqual(len(pids), 1, pids)
                until(self, lambda: not alive(pids[0]), 'the end of the try')
                self.assertFalse(hold(lock), 'the updater lock is held after the try ended')


@needs_container
class OwnLines(unittest.TestCase):
    """opus F4: RECOVER journals a `recover-target` only when its value matches its own reader's pattern (strict
    digest images): a person's file naming `localhost:27500/linux-runner:pinned` that validates: no start, STOP HAND
    CHANGE that says why, the journal open and readable (exit 5 at the next pass too). The control: digest images:
    `recover-target`, the start, closed other."""

    def test_recover_target_is_a_line_its_reader_reads(self):
        for pinned in (True, False):
            with self.subTest(pinned=pinned):
                g = cut(self, 'up', ('journal:stopped', 'kill'))
                cfg = g.p.config()
                if pinned:
                    h = re.sub(r'(?m)^runner-image = ".*"$', 'runner-image = "localhost:27500/linux-runner:pinned"',
                               cfg)
                else:
                    h = cfg.replace('max-runners = 3\n', 'max-runners = 2\n', 1)
                g.p.write(g.p.rpath('config.toml'), h, 0o600)
                g.p.runner = PASS
                x = Rec(self, g)
                if not pinned:
                    x.run(0)
                    lines = x.closed('other')
                    self.assertIn('recover-target', own(lines))
                    self.assertEqual(len(x.calls('start')), 1)
                    continue
                r = x.run(5)
                lines = x.open()
                self.assertNotIn('recover-target', keys(lines))
                self.assertEqual(x.calls('start'), [])
                self.assertTrue(any('digest' in s for s in stops(lines, 'HAND CHANGE')), lines)
                x.run(5)


@needs_container
class BackThroughAnAutoRestartWait(unittest.TestCase):
    """opus F5: a rollback on an enabled unit in a crash loop, read between two tries (activating, MainPID 0: the
    auto-restart wait, no process) goes on as on a stopped unit: its restart starts the TARGET. The control: a drain
    (deactivating, the old process): `end`, nothing restarted."""

    def test_activating_with_no_process_goes_on(self):
        for state in ('activating', 'deactivating'):
            with self.subTest(state):
                g = BackRig(self)
                if state == 'activating':
                    g.p.set_unit(runner='crash', start=g.p.clock() - 10)
                    g.p.hooks(('journal:starting', 'serve'))
                    r = g.back()
                    self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                    self.assertEqual(g.p.config(), g.old)
                    self.assertEqual(installed(g.done()[1])[2], 'target-running')
                    continue
                g.p.set_unit(drain_until=g.p.clock() + 600)
                r = g.back()
                lines = g.kept(r)
                self.assertIn('deactivating', value(lines, 'end'))


@needs_container
class JobMerge(unittest.TestCase):
    """opus F6: the systemctl substitute models the real manager's job merge: a start or restart that comes while a
    stop job drains cancels that stop job (its client exits 1), the old process drains on, and the new one starts after
    it; a person's stop while a start job is queued cancels it. The branches it reaches: the window's "systemctl --user
    stop runscaler failed" (the journal open after `stopping`), then RECOVER waits out the drain and the new process,
    started after `renamed`, RUNS: closed target-running, nothing stopped or started by RECOVER; RECOVER's "did not
    stop" (THE RESTORE's stop canceled: open, then the next pass restores); RECOVER's "start failed" (open, then the next
    pass's start). The control: no merge: the window's own stop and start, exit 0."""

    def test_a_start_during_the_window_s_drain_cancels_its_stop(self):
        for merge in (True, False):
            with self.subTest(merge=merge):
                g = Rig(self)
                g.p.set_unit(drain=60)
                if merge:
                    g.p.hooks(('systemctl:stop-begin', 'restart'))
                r = g.up()
                if not merge:
                    self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                    continue
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertIn('systemctl --user stop runscaler failed', r.stdout)
                ended(self, g)
                self.assertEqual(keys(g.cut)[-1], 'stopping')
                x = Rec(self, g)
                r = x.run(0)
                self.assertIn('deactivating', r.stdout)
                lines = x.closed('target-running')
                self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])
                self.assertGreater(int(value(lines, 'running').split()[1]), int(value(lines, 'renamed')))

    def test_recover_s_stop_and_start_that_the_manager_cancels(self):
        with self.subTest('did not stop'):
            g = cut(self, 'back', ('journal:renamed', 'kill'))
            g.p.runner = {'seq': [NONAPI]}
            g.p.set_unit(drain=60)
            g.p.hooks(('systemctl:stop-begin', 'start'))
            x = Rec(self, g)
            r = x.run(5)
            self.assertIn('did not stop for the restore', r.stdout)
            self.assertEqual(g.p.config(), g.old, 'the backup was put back under a process')
            g.p.hooks()
            x.run(0)
            x.closed('pre')
            self.assertEqual(g.p.config(), g.candidate)
        with self.subTest('start failed'):
            g = cut(self, 'up', ('journal:stopped', 'kill'))
            g.p.hooks(('systemctl:start-begin', 'stop'))
            x = Rec(self, g)
            r = x.run(5)
            self.assertIn('systemctl --user start runscaler failed', r.stdout)
            self.assertEqual(keys(x.open())[-1], 'starting')
            g.p.hooks()
            x.run(0)
            lines = x.closed('target-running')
            self.assertEqual(len(starts(lines)), 1, 'a second `starting`')


if __name__ == '__main__':
    unittest.main()
