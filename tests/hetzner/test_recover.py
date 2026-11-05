"""RECOVER, `pool-image.sh recover --unattended` (S2b-3c-1 D-c, D-d and the r3 FOLD; PLAN D1, D5 RECOVER): it ends a
window journal that a cut left OPEN, as the updater's child (D-a), and leaves it CLOSED at WINDOW with the closing
lines (`prev`, `installed SHA CONTENT CLASS`, `closed`) for the updater's apply step. It reads the journal only by the
header's patterns (an unterminated last line dropped and kept aside; any other line no pattern reads: STOP, exit 6,
nothing written) and decides by THE INSTALLED FILE (config.toml's CONTENT against the TARGET's, its sha against
`config-sha`) and by the UNIT (one `systemctl --user show`), never by which lines survived. In order:
  0 closed: nothing (exit 0); 1 NO EFFECT YET (no `config-sha` or no `backup`): closed, STAGED removed;
  DECIDED LINES (lines about a rollback's TARGET only: its failed `validate recover`, `restore`, `stop ROLLBACK
  FAILED`, a `pre-close-failure` of a TARGET start; test_urecover.py's DecidedByItsTarget): THE RESTORE; 2 THE UNIT: a drain waited for, NOT enabled: CI DISABLED,
  nothing stopped or started; 3 the TARGET installed: it RUNS (closed), none runs it (THE START), an older runscaler
  runs (a switch's IDLE RESTART: never while busy, STOP NO IDLE after 3 days; a rollback's restart at once); 4 the
  pre-window file and no rename: closed; 5 OTHER: PLAN D5's ONE RULE, HAND CHANGE.
  OPERATOR (1) on every route: an ENABLED unit that is down is started (on `config-sha` with no validate, on another
  file only once a copy validates). THE START: at most one start per pass, its 10-min deadline the journal's own epoch;
  a `starting` with no `running` past it is ONE pre-close failure, the second STOP POOL DOWN. RUNS, never one `active`.
Exit: 0 closed at WINDOW; 3 no journal; 4 WAIT (a person's pool-image.sh run holds its own lock); 5 open (the line says
why); 6 a record RECOVER cannot read. Every cell cuts a REAL window of the real scripts (support.Pool, a throwaway
container, a fake clock) with a SIGKILL of the updater and its window, then runs RECOVER as the updater's child; no
cell asserts a time it waited. A SIGKILL after EACH journal line of both modes: test_kills.py.
"""
import fcntl
import json
import os
import unittest

from tests.hetzner.support import needs_container, sha256_file
from tests.hetzner.test_unattended import (NONAPI, PASS, UNKNOWN, BackRig, Rig, alive, content, installed, keys,
                                           sha, value)

README_LINE = 'An unfinished window the updater cannot end'


def own(lines):
    """RECOVER's own keys: those after its first `recover-start`."""
    k = keys(lines)
    return k[k.index('recover-start') + 1:] if 'recover-start' in k else []


def cut(test, mode, *hooks, rc=-9, clock=True):
    """A window of MODE (up on a Rig, back --why back on a BackRig) cut by its HOOKS (a `kill` is a SIGKILL of the
    updater and its window); the hooks cleared, the logs emptied (so the calls counted are RECOVER's). The rig."""
    g = Rig(test, clock) if mode == 'up' else BackRig(test, clock)
    g.p.hooks(*hooks)
    r = g.up() if mode == 'up' else g.back()
    test.assertEqual(r.returncode, rc, r.stdout[-3000:] + r.stderr)
    test.assertIsNotNone(g.p.window(), 'the cut window left no journal')
    test.assertNotEqual(keys(g.p.window())[-1], 'closed')
    g.p.hooks()
    g.p.curl = json.loads(g.p.read(g.p.path('curl.json')))    # a hook's `busy` stays: the next run writes this file
    for n in ('systemctl', 'curl', 'runner'):
        g.p.write(g.p.path('logs', n + '.log'), '')
    g.cut = g.p.window()
    return g


class Rec:
    """Assertions on a RECOVER run."""

    def __init__(self, t, g):
        self.t, self.g = t, g

    def run(self, rc=0, **kw):
        r = self.g.p.recover(**kw)
        self.t.assertEqual(r.returncode, rc, r.stdout[-4000:] + r.stderr)
        self.r = r
        return r

    def lines(self):
        return self.g.p.window()

    def closed(self, cls, sha_=None):
        """The journal closed at WINDOW (not archived), the window's own lines kept as they were, `installed SHA
        CONTENT CLS` naming config.toml as it is."""
        t, g = self.t, self.g
        lines = self.lines()
        t.assertEqual(keys(lines)[-1], 'closed', lines)
        t.assertEqual(lines[:len(g.cut)], g.cut, 'RECOVER changed a line of the window')
        t.assertEqual(installed(lines), (sha256_file(g.p.rpath('config.toml')), content(g.p.config()), cls), lines)
        if sha_ is not None:
            t.assertEqual(installed(lines)[0], sha_)
        t.assertEqual(len(g.p.closed()), g.archived)
        return lines

    def open(self):
        lines = self.lines()
        self.t.assertNotEqual(keys(lines)[-1], 'closed', lines)
        self.t.assertNotIn('installed', own(lines))
        return lines

    def calls(self, what):
        return self.g.calls(what)

    def stops(self, lines):
        return [v for k, v in (l.split(' ', 1) for l in lines) if k == 'stop']


@needs_container
class Reading(unittest.TestCase):
    """Step 0, the reading, the exit codes."""

    def test_no_journal_is_3_and_a_closed_one_is_the_apply_step_s(self):
        g = Rig(self)
        r = g.p.recover()
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIsNone(g.p.window())
        self.assertEqual(g.up().returncode, 0)
        before = g.p.read(os.path.join(g.p.STATE, 'window'))
        n = len(g.p.lines('systemctl'))
        r = g.p.recover()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(g.p.read(os.path.join(g.p.STATE, 'window')), before, 'RECOVER wrote to a closed journal')
        self.assertEqual([l for l in g.p.lines('systemctl')[n:] if 'show' not in l], [])

    def test_a_cut_after_installed_gets_only_its_closed(self):
        """The closing lines are the closer's decision: a cut between `installed` and `closed` is ended by `closed`
        alone (no new read, no `recover-start`)."""
        g = cut(self, 'up', ('journal:installed', 'kill'))
        x = Rec(self, g)
        x.run(0)
        lines = x.lines()
        self.assertEqual(lines[:-1], g.cut)
        self.assertEqual(keys(lines)[-1], 'closed')
        self.assertEqual(installed(lines)[2], 'target-running')

    def test_an_unterminated_last_line_is_dropped_and_kept_aside(self):
        """Opus r2 F12 (a): a last line with no newline is D1's lost line: dropped (kept aside as the window's
        journal.cut), and RECOVER goes on as without it (here `renamed` lost: the TARGET is installed, its install time
        config.toml's mtime). The control: the same line whole, but of a key RECOVER does not read: STOP, exit 6, nothing
        written."""
        g = cut(self, 'up', ('journal:renamed', 'kill'))
        j = os.path.join(g.p.STATE, 'window')
        text = g.p.read(j)
        last = text[:-1].rsplit('\n', 1)[1]
        self.assertTrue(last.startswith('renamed '))
        g.p.write(j, text[:len(text) - 1 - len(last) // 2], 0o600)
        g.cut = g.cut[:-1]
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('target-running')
        self.assertEqual(sum(1 for l in lines if l.startswith('renamed ')), 0)
        wd = os.path.join(g.p.STATE, 'windows', value(lines, 'window') + '.d')
        self.assertEqual(g.p.read(os.path.join(wd, 'journal.cut')), last[:len(last) - len(last) // 2])
        # the control
        g = cut(self, 'up', ('journal:renamed', 'kill'))
        text = g.p.read(j) + 'renamd 12\n'
        g.p.write(j, text, 0o600)
        r = g.p.recover()
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        self.assertIn(README_LINE, r.stdout)
        self.assertEqual(g.p.read(j), text)
        self.assertEqual([l for l in g.p.lines('systemctl') if 'show' not in l], [])

    def test_a_line_no_pattern_reads_is_a_stop_and_nothing_is_written(self):
        """D-c / D-g: every line by its key's pattern; another is a STOP that names README "An unfinished window the
        updater cannot end", exit 6, the journal unchanged, nothing stopped or started. Each: an unknown key, a value of
        another shape, a backup that is not its kind's, no `window` first line."""
        for why, edit in (('an unknown key', lambda t: t + 'flag x\n'),
                          ('a value of another shape', lambda t: t + 'renamed soon\n'),
                          ('a stop of another name', lambda t: t + 'stop MAYBE: x\n'),
                          ('a backup that is not the switch\'s', lambda t: t + 'backup /tmp/x\n'),
                          ('no window line first', lambda t: t.split('\n', 1)[1])):
            with self.subTest(why):
                g = cut(self, 'up', ('journal:renamed', 'kill'))
                j = os.path.join(g.p.STATE, 'window')
                text = edit(g.p.read(j))
                g.p.write(j, text, 0o600)
                r = g.p.recover()
                self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
                self.assertIn('STOP RECOVER cannot end', r.stdout)
                self.assertIn(README_LINE, r.stdout)
                self.assertEqual(g.p.read(j), text)
                self.assertEqual([l for l in g.p.lines('systemctl') if 'show' not in l], [])

    def test_a_unit_it_cannot_read_leaves_the_journal_open(self):
        """No answer from `systemctl --user show` is no fact about the unit: nothing stopped or started, nothing renamed,
        the journal open with a line that says so (exit 5). The control: every cell below reads the unit."""
        g = cut(self, 'up', ('journal:renamed', 'kill'))
        g.p.show_answer(1, '')
        x = Rec(self, g)
        r = x.run(5)
        self.assertIn("runscaler's unit cannot be read", r.stdout)
        self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])
        self.assertEqual(own(x.open()), [])

    def test_an_inherited_open_journal_is_read_by_its_sha(self):
        """THE CUT (S2b-3c-1): a release must undo every switch it can meet: a journal an earlier release left open has
        no `target-content` line: T is then its `staged-sha`, by bytes. Cut after `renamed`, that line taken out: the
        idle restart, closed target-running. The control: a comment added (the bytes differ, no content to compare): a
        file the window did not write: HAND CHANGE, closed other."""
        for comment in (False, True):
            with self.subTest(comment=comment):
                g = cut(self, 'up', ('journal:renamed', 'kill'))
                g.cut = [l for l in g.cut if not l.startswith('target-content ')]
                g.p.write(os.path.join(g.p.STATE, 'window'), '\n'.join(g.cut) + '\n', 0o600)
                if comment:
                    g.p.write(g.p.rpath('config.toml'), g.p.config() + '# a comment\n', 0o600)
                x = Rec(self, g)
                x.run(0)
                lines = x.closed('other' if comment else 'target-running')
                self.assertEqual('hand-change' in own(lines), comment)
                self.assertEqual(len(x.calls('stop')), 0 if comment else 1)

    def test_a_person_s_attended_run_is_a_wait(self):
        """D-h (Opus r2 F13 (c)): pool-image.sh's own lock (fd 8) held by a person's attended run: RECOVER is a WAIT
        (exit 4), reads and changes nothing. The control: the lock free, RECOVER ends the journal."""
        g = cut(self, 'up', ('journal:renamed', 'kill'))
        j = os.path.join(g.p.STATE, 'window')
        text = g.p.read(j)
        with open(g.p.rpath('pool-image.lock'), 'a') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = g.p.recover()
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn('WAIT', r.stdout)
        self.assertNotIn('STOP', r.stdout)
        self.assertEqual(g.p.read(j), text)
        Rec(self, g).run(0)


@needs_container
class NoEffectYet(unittest.TestCase):
    """Step 1 (r2 Codex F6, Opus F12 (b)): no `config-sha` or no `backup`: the window changed no config and stopped
    nothing: STAGED removed, `installed ... pre|none`, closed, nothing stopped or started; its journaled STOP kept.
    OPERATOR (1): an enabled unit that is down is started, on `config-sha` with no validate; a disabled one: CI DISABLED,
    no start."""

    def test_a_cut_before_the_backup_closes_with_nothing_changed(self):
        for at, cls in (('journal:process', 'none'), ('journal:config-sha', 'pre'), ('journal:validate', 'pre'),
                        ('journal:target-content', 'pre'), ('journal:idle', 'pre')):
            with self.subTest(at):
                g = cut(self, 'up', (at, 'kill'))
                before = g.p.unit_now()
                x = Rec(self, g)
                x.run(0)
                lines = x.closed(cls)
                self.assertEqual(g.p.config(), g.old)
                self.assertFalse(os.path.lexists(g.staged), 'STAGED left')
                self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])
                self.assertEqual(g.p.unit_now()['pid'], before['pid'])
                self.assertEqual(own(lines), ['prev', 'installed', 'closed'])

    def test_a_cut_between_an_early_stop_and_closed_keeps_the_stop(self):
        """r2 Codex F6: a STOP of the window before any effect (DISK), cut before its closing lines: the next pass closes
        the journal with the STOP kept, nothing restarted, nothing changed."""
        g = Rig(self)
        g.p.disk(1000, 99)
        g.p.hooks(('journal:stop', 'kill'))
        r = g.up()
        self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
        g.cut = g.p.window()
        g.p.hooks()
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('pre')
        self.assertEqual(len(x.stops(lines)), 1)
        self.assertTrue((value(lines, 'stop') or '').startswith('DISK: '))
        self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])

    def test_an_enabled_unit_that_is_down_is_started_on_config_sha(self):
        """OPERATOR (1) ON EVERY ROUTE (Opus r3 F4): a person's plain `systemctl --user stop runscaler` (the unit stays
        enabled) once the window journaled `validate`: RECOVER starts it on the pre-window file with no validate:
        `recover-target`, `starting`, `running`, closed pre. The control: the unit disabled (`disable --now`): STOP CI
        DISABLED, no start."""
        for act, started in (('stop', True), ('disable', False)):
            with self.subTest(act):
                g = cut(self, 'up', ('journal:validate', act, 'kill'))
                x = Rec(self, g)
                x.run(0)
                lines = x.closed('pre')
                self.assertEqual(g.validates(), [], 'RECOVER validated the pre-window file')
                if started:
                    self.assertEqual(own(lines)[:3], ['recover-target', 'starting', 'running'], lines)
                    self.assertEqual(value(lines, 'recover-target').split(' ', 1)[0], sha(g.old))
                    self.assertEqual(len(x.calls('start')), 1)
                    self.assertIsNone(value(lines, 'stop'))
                else:
                    self.assertEqual(x.calls('start'), [])
                    self.assertTrue((value(lines, 'stop') or '').startswith('CI DISABLED: '), lines)


@needs_container
class PreWindowFile(unittest.TestCase):
    """Step 4: the pre-window file installed and no window rename: nothing was installed: closed pre, STAGED removed, no
    restart (its journaled STOP kept); an enabled unit that is down is started on it (Opus r3 F4 (b))."""

    def test_a_cut_after_the_backup_and_before_the_rename_closes_pre(self):
        for at in ('journal:backup', 'journal:rename-start'):
            with self.subTest(at):
                g = cut(self, 'up', (at, 'kill'))
                x = Rec(self, g)
                x.run(0)
                x.closed('pre')
                self.assertEqual(g.p.config(), g.old)
                self.assertFalse(os.path.lexists(g.staged))
                self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])

    def test_an_enabled_stopped_unit_is_started_and_a_disabled_one_is_ci_disabled(self):
        for act, started in (('stop', True), ('disable', False)):
            with self.subTest(act):
                g = cut(self, 'up', ('journal:backup', act, 'kill'))
                x = Rec(self, g)
                x.run(0)
                lines = x.closed('pre')
                self.assertEqual(len(x.calls('start')), 1 if started else 0)
                self.assertEqual((value(lines, 'stop') or '').startswith('CI DISABLED'),
                                 not started)


@needs_container
class TargetInstalled(unittest.TestCase):
    """Step 3, the TARGET installed, the unit enabled: 3a it RUNS since the install (also a start by another actor after
    `renamed`: P for PLAN D5 :222): closed target-running, nothing restarted; 3b none runs it: THE START (a rollback's
    TARGET validated first); 3c an older runscaler runs: a switch's IDLE RESTART (validate if needed, then ONE idle pair,
    then at once), a rollback's restart at once (its TARGET validated first)."""

    def test_3a_it_runs_closed_with_no_restart(self):
        for mode, at in (('up', 'journal:running'), ('back', 'journal:running')):
            with self.subTest(mode):
                g = cut(self, mode, (at, 'kill'))
                x = Rec(self, g)
                x.run(0)
                x.closed('target-running')
                self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])

    def test_3a_a_start_by_another_actor_after_the_rename_proves_the_target(self):
        """P (Opus r3 F17): the rename done, `renamed` lost, an independent restart then (busy pool): the install time
        is config.toml's mtime, the restarted process started after it and RUNS: closed target-running, nothing
        restarted while busy."""
        g = cut(self, 'up', ('mv-done:config.toml', 'restart', 'busy', 'kill'))
        x = Rec(self, g)
        x.run(0)
        x.closed('target-running')
        self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])

    def test_3b_none_runs_it_the_start(self):
        """A cut after `stopped` (the unit down): THE START on the TARGET: a switch's sha is validated (staged-sha), so
        no validate; a rollback's TARGET is validated again first (`validate recover 1 PASS`, `recover-target`)."""
        for mode in ('up', 'back'):
            with self.subTest(mode):
                g = cut(self, mode, ('journal:stopped', 'kill'))
                x = Rec(self, g)
                x.run(0)
                lines = x.closed('target-running')
                self.assertEqual(len(x.calls('start')), 1)
                self.assertEqual(x.calls('stop'), [])
                if mode == 'up':
                    self.assertEqual(own(lines)[:2], ['starting', 'running'], lines)
                    self.assertEqual(g.validates(), [])
                else:
                    self.assertEqual(own(lines)[:4], ['validate', 'recover-target', 'starting', 'running'], lines)
                    self.assertEqual(value(lines, 'validate'), 'recover 1 PASS')

    def test_3b_a_start_in_progress_is_waited_for_with_no_new_line(self):
        """A cut right after `starting` (before the start ran): that attempt is still inside its 10 min: the unit,
        down, is started again with no new `starting` line, and it RUNS: closed. (A rollback's: test_urecover.py,
        DecidedByItsTarget.)"""
        g = cut(self, 'up', ('journal:starting', 'kill'))
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('target-running')
        self.assertEqual(keys(lines).count('starting'), 1)
        self.assertEqual(own(lines)[:1], ['running'])

    def test_3c_a_switch_restarts_only_at_idle(self):
        """Operator (2): an older runscaler runs the pre-window file: idle: ONE idle pair, then at once the stop and the
        start (`from`, `stopping`, `stopped`, `starting`, `running`): closed. Busy: nothing restarts, the journal stays
        open (exit 5) and the line says the switch waits for idle; 3 days after `recover-start`: STOP NO IDLE with the
        hand line, journaled once, printed at each pass; never an automatic restart."""
        g = cut(self, 'up', ('journal:renamed', 'kill'))
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('target-running')
        self.assertEqual(own(lines)[:5], ['from', 'stopping', 'stopped', 'starting', 'running'], lines)
        self.assertEqual((len(x.calls('stop')), len(x.calls('start'))), (1, 1))
        g = cut(self, 'up', ('journal:renamed', 'busy', 'kill'))
        x = Rec(self, g)
        r = x.run(5)
        self.assertIn('waits for idle', r.stdout)
        self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])
        x.run(5)
        g.p.clock(plus=3 * 86400)
        r = x.run(5)
        self.assertIn('STOP NO IDLE: ', r.stdout)
        self.assertIn('systemctl --user restart runscaler', r.stdout)
        r = x.run(5)
        self.assertIn('STOP NO IDLE: ', r.stdout)
        lines = x.open()
        self.assertEqual(len([s for s in x.stops(lines) if s.startswith('NO IDLE')]), 1)
        self.assertEqual(keys(lines).count('recover-start'), 1)
        self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])

    def test_3c_the_validate_comes_before_the_idle_pair(self):
        """r2 Codex F7: the TARGET with a comment added (its sha needs a validate), an older runscaler: jobs arrive during
        the validate: the idle pair, after it, reads busy: no stop. The control: no job: the restart, past the validate."""
        for busy in (True, False):
            with self.subTest(busy=busy):
                g = cut(self, 'up', ('journal:renamed', 'kill'))
                g.p.write(g.p.rpath('config.toml'), g.p.config() + '# a comment\n', 0o600)
                if busy:
                    g.p.hooks(('journal:validate', 'busy'))
                x = Rec(self, g)
                x.run(5 if busy else 0)
                self.assertEqual(len(x.calls('stop')), 0 if busy else 1)
                if not busy:
                    self.assertEqual(own(x.closed('target-running'))[:3], ['validate', 'recover-target', 'from'])

    def test_3c_an_untested_jq_reads_as_not_idle(self):
        """Opus r3 F12: RECOVER needs no jq but for a switch's idle pair; an untested jq reads as not idle, and a line
        says so: no stop. The control: the idle restart above (a tested jq)."""
        g = cut(self, 'up', ('journal:renamed', 'kill'))
        g.p.jq_version('jq-9.9')
        x = Rec(self, g)
        r = x.run(5)
        self.assertIn('untested jq', r.stdout)
        self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])

    def test_3c_a_rollback_restarts_at_once(self):
        """PLAN D5 :282: a rollback does not wait for idle: an older runscaler and a busy pool: its TARGET validated, then
        the stop and the start at once: closed target-running."""
        g = cut(self, 'back', ('journal:renamed', 'kill'))
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('target-running')
        self.assertEqual(own(lines)[:7], ['validate', 'recover-target', 'from', 'stopping', 'stopped', 'starting',
                                          'running'], lines)

    def test_a_switch_s_failed_validate_is_the_one_rule(self):
        """Opus r3 F6: the TARGET installed with a comment added (CONTENT the TARGET's, the sha not validated), none runs
        it: a copy validates first; NON-API: `hand-change`, STOP HAND CHANGE, no start, the journal open; a second pass
        validates again and adds no second hand-change. The control: PASS: `recover-target`, the start, closed
        target-running."""
        for seq, ok in (([NONAPI], False), ([PASS], True)):
            with self.subTest(ok=ok):
                g = cut(self, 'up', ('journal:stopped', 'kill'))
                g.p.write(g.p.rpath('config.toml'), g.p.config() + '# a comment\n', 0o600)
                g.p.runner = {'seq': seq}
                x = Rec(self, g)
                if ok:
                    x.run(0)
                    lines = x.closed('target-running')
                    self.assertEqual(own(lines)[:3], ['validate', 'recover-target', 'starting'])
                    continue
                r = x.run(5)
                self.assertIn('STOP HAND CHANGE: ', r.stdout)
                lines = x.open()
                self.assertEqual(own(lines), ['validate', 'hand-change', 'stop'])
                self.assertEqual(x.calls('start'), [])
                x.run(5)
                lines = x.open()
                self.assertEqual(keys(lines).count('hand-change'), 1)
                self.assertEqual(keys(lines).count('validate'), 1 + 2)


@needs_container
class TheStart(unittest.TestCase):
    """THE START'S DEADLINE and RUNS (Opus r3 F1, Codex r3 F3): Type=simple with Restart=always: a runner-start that
    REFUSEs is `active` for a second of each 31, one that hangs is `active` throughout, and neither serves /healthz.
    A window cut at `starting` (the start in progress): no `running`, one `pre-close-failure` once 10 min pass, the
    second START (a new `starting`), no `running` again: STOP POOL DOWN, closed. The control: a runner-start that serves:
    `running` at once."""

    def start(self, runner):
        g = Rig(self)
        g.p.set_unit(runner='serves')
        g.p.hooks(('journal:starting', runner, 'kill'))
        r = g.up()
        self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
        g.cut = g.p.window()
        g.p.hooks()
        for n in ('systemctl', 'curl', 'runner'):
            g.p.write(g.p.path('logs', n + '.log'), '')
        return g

    def test_a_crash_loop_or_a_hang_is_pool_down_after_the_second_start(self):
        for runner in ('crash', 'hang'):
            with self.subTest(runner):
                g = self.start(runner)
                x = Rec(self, g)
                x.run(0)
                lines = x.closed(installed(x.lines())[2])
                self.assertNotIn('running', keys(lines))
                self.assertEqual(own(lines)[:3], ['pre-close-failure', 'starting', 'stop'], lines)
                self.assertTrue((value(lines, 'stop') or '').startswith('POOL DOWN: '), lines)
                self.assertIn(installed(lines)[2], ('target-idle', 'target-old'))
                self.assertEqual(keys(lines).count('starting'), 2)

    def test_a_start_of_recover_s_own_that_fails_twice_takes_two_passes(self):
        """r2 Opus F5: a crash loop, the window cut after `stopped` (no `starting` yet). Pass 1: its own start, no RUNS in
        10 min: `pre-close-failure`, the journal open (exit 5): at most one start per pass. Pass 2: a second start, no
        RUNS: STOP POOL DOWN, closed; never CI DISABLED."""
        g = cut(self, 'up', ('journal:stopped', 'crash', 'kill'))
        x = Rec(self, g)
        x.run(5)
        lines = x.open()
        self.assertEqual(own(lines), ['starting', 'pre-close-failure'], lines)
        self.assertEqual(len(x.calls('start')), 1)
        x.run(0)
        lines = x.lines()
        self.assertEqual(own(lines)[:4], ['starting', 'pre-close-failure', 'starting', 'stop'], lines)
        self.assertTrue((value(lines, 'stop') or '').startswith('POOL DOWN: '), lines)
        self.assertEqual(len(x.calls('start')), 2)
        self.assertNotIn('CI DISABLED', '\n'.join(lines))

    def test_a_change_right_before_the_start_gets_no_start(self):
        """Opus r3 F15: THE START checks config.toml against the validated sha right before `systemctl start`: a change
        once its `starting` is synced: `hand-change`, STOP HAND CHANGE, no start, the journal open. The control: no
        change: TargetInstalled's START."""
        g = cut(self, 'up', ('journal:stopped', 'kill'))
        g.p.hooks(('journal:starting', 'edit-config'))
        x = Rec(self, g)
        x.run(5)
        lines = x.open()
        self.assertEqual(own(lines), ['starting', 'hand-change', 'stop'], lines)
        self.assertEqual(x.calls('start'), [])

    def test_control_a_runner_start_that_serves_runs(self):
        g = self.start('serve')
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('target-running')
        self.assertNotIn('pre-close-failure', keys(lines))

    def test_a_window_s_own_failure_then_one_more_start(self):
        """The window's own 10 min ran out (`pre-close-failure` by the window, the journal open): RECOVER's START is the
        second try: a crash loop again: POOL DOWN; a runner-start that serves: closed target-running."""
        for runner, cls in (('crash', None), ('serve', 'target-running')):
            with self.subTest(runner):
                g = Rig(self)
                g.p.set_unit(runner='serves')
                g.p.hooks(('journal:starting', 'crash'))
                r = g.up()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                g.cut = g.p.window()
                self.assertEqual(keys(g.cut)[-1], 'pre-close-failure')
                g.p.hooks()
                g.p.set_unit(runner='serves' if runner == 'serve' else 'crash', active=False)   # the next start's
                x = Rec(self, g)
                x.run(0)
                lines = x.lines()
                self.assertEqual(keys(lines).count('starting'), 2)
                if cls:
                    x.closed(cls)
                else:
                    self.assertTrue((value(lines, 'stop') or '').startswith('POOL DOWN: '), lines)


@needs_container
class UnitNotEnabled(unittest.TestCase):
    """Step 2: the unit NOT enabled: nothing is stopped or started; `stop CI DISABLED`, closed, the class saying what is
    installed and what runs (A ROLLBACK IS DONE ONLY WHEN ITS TARGET RUNS: Opus r3 F7, Codex r3 F1): the TARGET installed
    under an older runscaler that a person's `disable` (no --now) left running: target-old, and the STOP names the image
    that runs; `disable --now`: target-idle. A drain that outlives its client is waited for first."""

    def test_disabled_with_an_older_runscaler_running_is_target_old(self):
        for mode in ('up', 'back'):
            for act, cls in (('disable-only', 'target-old'), ('disable', 'target-idle')):
                with self.subTest(mode, act=act):
                    g = cut(self, mode, ('journal:renamed', act, 'kill'))
                    before = g.p.unit_now()
                    x = Rec(self, g)
                    x.run(0)
                    lines = x.closed(cls)
                    self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])
                    stop = value(lines, 'stop')
                    self.assertTrue(stop.startswith('CI DISABLED: '), lines)
                    if cls == 'target-old':
                        self.assertIn(value(lines, 'old'), stop, 'the STOP names the image that runs')
                        self.assertEqual(g.p.unit_now()['pid'], before['pid'])
                    else:
                        self.assertIn('systemctl --user enable --now runscaler', stop)

    def test_disabled_while_the_target_runs_says_so(self):
        """Step 2 comes before the RUNS test (a mutant: after it): a window cut after `running`, then a person's `disable`
        with no --now: the TARGET RUNS, the class target-running, and CI DISABLED still tells that a reboot leaves CI
        down. The control: the enabled unit's 3a (TargetInstalled): no STOP."""
        g = cut(self, 'up', ('journal:running', 'disable-only', 'kill'))
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('target-running')
        self.assertTrue((value(lines, 'stop') or '').startswith('CI DISABLED: '), lines)
        self.assertIn('reboot', value(lines, 'stop'))
        self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])

    def test_a_drain_that_outlives_its_client_is_waited_for(self):
        """Codex r2 F3: the window's stop drains (60 s of the clock) and the updater is killed meanwhile: the stop job
        goes on. RECOVER reads `deactivating`, waits until it ends, then (none runs) THE START: closed target-running."""
        g = Rig(self)
        g.p.set_unit(drain=60)
        g.p.hooks(('systemctl:stop-begin', 'kill'))
        r = g.up()
        self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
        g.cut = g.p.window()
        self.assertEqual(keys(g.cut)[-1], 'stopping')
        g.p.hooks()
        x = Rec(self, g)
        r = x.run(0)
        self.assertIn('deactivating', r.stdout)
        x.closed('target-running')


@needs_container
class Decided(unittest.TestCase):
    """DECIDED LINES FIRST (Opus r3 F2, Codex r3 F4; B1 DECISIONS): right after steps 0 and 1, a ROLLBACK journal with
    a failed validate of its TARGET, a `restore`, a `stop ROLLBACK FAILED` or a `pre-close-failure` of a TARGET start
    goes to THE RESTORE, with no new validate of the TARGET; its close is a failed rollback (class pre: the backup;
    target-failed when the TARGET stays: test_urecover.py).
    THE RESTORE's order (Opus r3 F5): the copy of the backup checked, config.toml checked (the TARGET, or already the
    backup: a replay), `restore`, the stop, `rename-start`, the copy's mtime set, no process, config.toml still the
    TARGET, the rename, `renamed`, `recover-target`, THE START."""

    def nonapi(self, *hooks, clock=True):
        """A rollback cut after `renamed` (an older runscaler runs), then RECOVER whose validate of the TARGET is
        NON-API, with HOOKS."""
        g = cut(self, 'back', ('journal:renamed', 'kill'), clock=clock)
        g.p.runner = {'seq': [NONAPI]}
        g.p.hooks(*hooks)
        return g

    def test_a_failed_validate_restores_the_backup(self):
        """On the REAL clock (the restore's copy gets its mtime from it): the copy's mtime is set at or after the
        restore's `rename-start`, and the start comes past `renamed`."""
        g = self.nonapi(clock=False)
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('pre', sha(g.candidate))
        self.assertEqual(g.p.config(), g.candidate)
        self.assertEqual(own(lines)[:6], ['validate', 'stop', 'restore', 'rename-start', 'renamed', 'recover-target'])
        self.assertTrue((value(lines, 'stop') or '').startswith('ROLLBACK FAILED: '))
        self.assertEqual(len(g.validates()), 1, 'one validate: no new validate of the TARGET')
        self.assertGreaterEqual(int(os.stat(g.p.rpath('config.toml')).st_mtime), int(value(lines, 'rename-start')))
        self.assertGreater(int(value(lines, 'running').split()[1]), int(value(lines, 'renamed')))

    def test_unknown_restores_with_no_stop(self):
        g = cut(self, 'back', ('journal:renamed', 'kill'))
        g.p.runner = {'seq': [UNKNOWN]}
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('pre')
        self.assertIsNone(value(lines, 'stop'), lines)
        self.assertIn('restore', own(lines))

    def test_a_replay_after_the_restore_s_rename_needs_no_validate_and_no_hand_change(self):
        """Opus r3 F2 (a): RECOVER cut right after the restore's rename (its `renamed` lost): config.toml is the
        backup; the next pass: no validate, no HAND CHANGE, ROLLBACK FAILED once, the start on the backup: closed pre."""
        g = self.nonapi(('mv-done:config.toml', 'kill'))
        x = Rec(self, g)
        x.run(-9)
        self.assertEqual(g.p.config(), g.candidate)
        g.p.hooks()
        n = len(g.validates())
        x.run(0)
        lines = x.closed('pre')
        self.assertEqual(len(g.validates()), n)
        self.assertNotIn('hand-change', keys(lines))
        self.assertEqual(len([s for s in x.stops(lines) if s.startswith('ROLLBACK FAILED')]), 1)

    def test_a_person_s_file_is_never_restored_over(self):
        """Opus r3 F5 (a), Codex r2 F5: the NON-API decided, the run cut; a person installs H and starts it: the next
        pass stops nothing and renames nothing: `hand-change`, STOP HAND CHANGE, the same pid runs; closed other. The
        control: config.toml still the TARGET: the stop, then the rename (the cell above)."""
        g = self.nonapi(('journal:validate', 'kill'))
        x = Rec(self, g)
        x.run(-9)
        g.p.hooks()
        h = g.old.replace('max-runners = 3', 'max-runners = 2')
        g.p.write(g.p.rpath('config.toml'), h, 0o600)
        g.p.set_unit(start=g.p.clock(plus=2), pid=900)
        x.run(0)
        lines = x.closed('other')
        self.assertEqual(g.p.config(), h)
        self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])
        self.assertEqual(g.p.unit_now()['pid'], 900)
        self.assertIn('hand-change', own(lines))

    def test_a_person_s_file_with_none_running_is_the_one_rule(self):
        """The same decided rollback, H installed and no runscaler: nothing is put back; a copy of H validates: the start
        on H, closed other, its HAND CHANGE once. The control: H with a runscaler running (the cell above)."""
        g = self.nonapi(('journal:validate', 'stop', 'kill'))
        x = Rec(self, g)
        x.run(-9)
        g.p.hooks()
        h = g.old.replace('max-runners = 3', 'max-runners = 2')
        g.p.write(g.p.rpath('config.toml'), h, 0o600)
        g.p.runner = PASS
        x.run(0)
        lines = x.closed('other')
        self.assertEqual(g.p.config(), h)
        self.assertEqual(keys(lines).count('hand-change'), 1)
        self.assertEqual(len(x.calls('start')), 1)
        self.assertNotIn('restore', own(lines))

    def test_a_disabled_unit_still_gets_the_backup_and_its_text_names_it(self):
        """Opus r3 F2 (b): the NON-API decided, the run cut before the restore's rename, then a person's `disable --now`:
        the backup is put back (no process), CI DISABLED names the backup, the class pre (a failed rollback: the
        candidate stays). The control: a rollback with no decided line, the TARGET installed, the unit disabled: the
        class target-idle (rolled back)."""
        g = self.nonapi(('journal:restore', 'disable', 'kill'))
        x = Rec(self, g)
        x.run(-9)
        g.p.hooks()
        x.run(0)
        lines = x.closed('pre')
        self.assertEqual(g.p.config(), g.candidate)
        self.assertIn('config.toml.backup', value(lines, 'stop'))
        self.assertEqual(x.calls('start'), [])
        g = cut(self, 'back', ('journal:stopped', 'disable', 'kill'))
        x = Rec(self, g)
        x.run(0)
        x.closed('target-idle')

    def test_a_start_after_the_drain_and_before_the_rename_stops_the_restore(self):
        """Opus r3 F5 (b): a 60-s drain, then a start injected right after the restore's `rename-start`: no rename, the
        journal open. The control: no injected start: the rename (config.toml's mtime at or after `rename-start`), then
        THE START past `renamed`."""
        g = self.nonapi(('journal:rename-start', 'start'))
        g.p.set_unit(drain=60)
        x = Rec(self, g)
        r = x.run(5)
        self.assertIn('before the restore', r.stdout)
        lines = x.open()
        self.assertNotIn('renamed', own(lines))
        self.assertEqual(g.p.config(), g.old, 'the backup was put back under a process')

    def test_a_restore_never_renames_under_a_surviving_drain(self):
        """Codex r2 F3: the restore's stop drains 60 s of the clock, the updater and its client are killed meanwhile, and
        the stop job goes on (deactivating, the old pid). The next RECOVER waits until it ended: the old process stops
        BEFORE the backup's rename. The control: a stop that completes (the cells above)."""
        g = self.nonapi(('systemctl:stop-begin', 'kill'))
        g.p.set_unit(drain=60)
        x = Rec(self, g)
        x.run(-9)
        self.assertEqual(g.p.config(), g.old, 'the backup was put back during the drain')
        g.p.hooks()
        x.run(0)
        x.closed('pre')
        ev = g.p.events()
        at = len(ev) - 1 - ev[::-1].index('mv config.toml')
        stopped = [i for i, e in enumerate(ev) if e.startswith('process ') and e.endswith(' stopped')]
        self.assertTrue(stopped, ev)
        self.assertLess(stopped[-1], at, 'the rename came before the drain ended')

    def test_a_backup_that_is_not_config_sha_stops_nothing(self):
        """Opus r2 F4 (c): the backup's copy is checked FIRST: a backup with another sha: STOP ROLLBACK FAILED, nothing
        stopped, the old process still runs. The control: a good backup (the cells above)."""
        g = self.nonapi()
        bk = value(g.cut, 'backup')
        g.p.write(bk, g.p.read(bk) + '# changed\n', 0o600)
        before = g.p.unit_now()
        x = Rec(self, g)
        x.run(0)
        lines = x.lines()
        self.assertTrue(any(s.startswith('ROLLBACK FAILED') and 'not the config' in s for s in x.stops(lines)), lines)
        self.assertEqual(x.calls('stop') + x.calls('start'), [])
        self.assertEqual(g.p.unit_now()['pid'], before['pid'])
        self.assertNotIn('restore', own(lines))


@needs_container
class OtherFile(unittest.TestCase):
    """Step 5, OTHER (PLAN D5's ONE RULE): a file the window did not write: STOP HAND CHANGE; a runscaler runs: nothing
    restarts, closed other; none runs: a copy validates (PASS) -> the start past the file's mtime, closed other; NON-API
    or UNKNOWN: no start, `hand-change`, the journal open, and the next pass validates again."""

    def test_a_person_s_file_with_a_runscaler_running_restarts_nothing(self):
        g = cut(self, 'up', ('journal:renamed', 'kill'))
        g.p.write(g.p.rpath('config.toml'), g.old.replace('max-runners = 3', 'max-runners = 2'), 0o600)
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('other')
        self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])
        self.assertTrue((value(lines, 'stop') or '').startswith('HAND CHANGE: '))

    def test_a_person_s_file_with_none_running_is_started_only_once_it_validates(self):
        for seq, ok in (([PASS], True), ([NONAPI], False)):
            with self.subTest(ok=ok):
                g = cut(self, 'up', ('journal:stopped', 'kill'))
                h = g.old.replace('max-runners = 3', 'max-runners = 2')
                g.p.write(g.p.rpath('config.toml'), h, 0o600)
                g.p.runner = {'seq': seq}
                x = Rec(self, g)
                if ok:
                    x.run(0)
                    lines = x.closed('other')
                    self.assertEqual(len(x.calls('start')), 1)
                    self.assertGreater(int(value(lines, 'running').split()[1]),
                                       int(os.stat(g.p.rpath('config.toml')).st_mtime))
                    continue
                x.run(5)
                lines = x.open()
                self.assertEqual(x.calls('start'), [])
                x.run(5)
                self.assertEqual(keys(x.lines()).count('hand-change'), 1)
                self.assertEqual(len(g.validates()), 2)


@needs_container
class IndependentRestarts(unittest.TestCase):
    """PLAN D5 :225-227: an independent restart (Restart=always after a crash, a person's restart, a runner-start slow
    across the rename) around the rename, the run killed, a busy /healthz; then RECOVER: no old file is ever put back,
    and no switch restarts while busy (a process that started in `renamed`'s own second is no proof: it waits for idle)."""

    def test_no_old_file_back_and_no_restart_while_busy(self):
        for why, at, rc, cfg in (('before rename-start', 'journal:backup', 0, 'old'),
                                 ('between rename-start and the rename', 'journal:rename-start', 0, 'old'),
                                 ('the rename done, renamed missing', 'mv-done:config.toml', 0, 'new'),
                                 ('after renamed', 'journal:renamed', 5, 'new'),
                                 ('delayed across the rename', 'mv:config.toml', 0, 'old')):
            with self.subTest(why):
                g = cut(self, 'up', (at, 'restart', 'busy', 'kill'))
                cand = g.p.config()
                x = Rec(self, g)
                x.run(rc)
                self.assertEqual(x.calls('stop') + x.calls('start') + x.calls('restart'), [])
                self.assertEqual(g.p.config(), cand, 'RECOVER changed config.toml')
                self.assertEqual(g.p.config() == g.old, cfg == 'old')


@needs_container
class Bound(unittest.TestCase):
    """r2 Codex F15, Opus F13 (b): RECOVER's validate tries run as the window's do: `timeout -k 10 120`, its own process
    group swept after, fd 9 closed; a cut try is UNKNOWN (a rollback: THE RESTORE, no STOP). The control: a validate that
    ends is classified (TargetInstalled's rollback cells)."""

    def test_a_validate_that_hangs_is_cut_unknown(self):
        g = cut(self, 'back', ('journal:stopped', 'kill'))
        g.p.short_timeout()
        g.p.runner = {'hang': True, 'rc': 1, 'out': 'never\n'}
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('pre')
        self.assertEqual(value(lines, 'validate'), 'recover 1 UNKNOWN')
        self.assertIsNone(value(lines, 'stop'))
        self.assertEqual([a[:3] for a in g.p.timeouts()], [['-k', '10', '120']])
        self.assertEqual([c['fd9'] for c in g.validates()], [False])
        with open(g.p.path('logs', 'hang.pid')) as f:
            pid = int(f.read().split()[0])
        self.assertFalse(alive(pid), 'the cut validate still runs')


if __name__ == '__main__':
    unittest.main()
