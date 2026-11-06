"""linux-docker/bin/runner-updater's ROLLBACK CALLER, its bounds (S2b-3c-1 D-g and D-e; the r3 FOLD "THE ROLLBACK'S
PRECONDITIONS"; B2b review r1: Codex F1, F2, F3 and Opus F1). (Named for its CI part, test_[a-j]*.py:
.github/workflows/release-check.yml.)

- ONE RESTART PER PASS, BY THE PROCESS (Codex F1): a pass whose RECOVER started or restarted runscaler starts no
  rollback window, decided by runscaler's MainPID and its start before and after RECOVER, so a RECOVER that resumes a
  start it journaled before a cut (`starting E pre`, no new line) counts too; r1_since removed (no try could start).
  The control: RECOVER finds runscaler running on its file and starts nothing: the rollback goes on in that pass.
- THE 2-H CLOCK (Codex F2, Opus F1): the core's ONE state write sets r1_since only when a try can start, so a kill right
  after it never leaves time counted while the unit is not enabled; a pending hand edit (config.toml written after the
  running runscaler started, no restart since: un_back's own HAND CHANGE test) is no try: no window, STOP HAND CHANGE,
  no r1_since, and once a person restarts runscaler the rollback runs; a window that meets such an edit itself (a hand
  edit as it begins) counts no time either. The controls: a restart before the first pass rolls back at once; a try
  whose validate is UNKNOWN keeps r1_since (and 2 h of them hold ROLLBACK FAILED: test_verdict Since).
- THE OUTAGE RULE AFTER THE WINDOW (Codex F3): a rollback whose start fails holds POOL DOWN once, naming the open
  journal, with no second restart; a POOL DOWN held when the pass began, which the window's RECOVER made untrue, is
  cleared, and the pass's "rollback pending" line no longer says CI is down. The control: a person's `disable --now`
  during the window holds none.
Every cell runs the real scripts (support.Pool, a throwaway container, a fake clock) and the updater as RS_USER; R1's
verdict is test_verdict's planted one (the real core program, its answer's hz-docker verdict set to rollback).
"""
import json
import os
import unittest

from tests.hetzner.support import needs_container, ref
from tests.hetzner.test_unattended import PASS, UNKNOWN, keys, value
from tests.hetzner.test_updater import FAM, OLD, STATE, V, WINDOW
from tests.hetzner.test_verdict import PREV, Armed

# mv, for the kill cell of THE 2-H CLOCK: support.py's mv substitute fires "mv-done:state.json" on the first rename onto
# any state.json, and a pass renames its core copy PASSDIR/state.json twice before it writes STATE; this one fires
# "mv-done:STATE" only after a rename onto the updater's STATE (~/.local/state/runner-updater/state.json)
MV_STATE = r'''#!/usr/bin/python3 -I
import os, subprocess, sys
SB = @SB@
sys.path.insert(0, SB + '/stubs')
import hzlib
a = sys.argv[1:]
dest = [x for x in a if not x.startswith('-')][-1]
r = subprocess.run(['/usr/bin/mv'] + a)
want = os.path.join(os.environ['HOME'], '.local', 'state', 'runner-updater', 'state.json')
if r.returncode == 0 and os.path.realpath(dest) == os.path.realpath(want):
    hzlib.event('mv STATE')
    hzlib.fire('mv-done:STATE')
sys.exit(r.returncode)
'''


def held(a, name='POOL DOWN'):
    """The detail texts of the family's held STOPs of NAME."""
    return [(s.get('detail') or {}).get('text', '') for s in a.fam().get('stops', []) if s['stop'] == name]


def hand_edit(a):
    """A person's hand `03-runscaler.sh real` with pool.env as it is (Opus F1's input): config.toml written again with
    the same bytes, so it is installed after runscaler started; no restart. Its mtime."""
    cfg = a.p.rpath('config.toml')
    a.p.write(cfg, a.p.config(), 0o600)
    m = a.p.unit_now()['start'] + 1
    os.utime(cfg, (m, m))
    return m


def last_line(r):
    return [l for l in r.stdout.splitlines() if l.startswith('runner-updater: ')][-1]


@needs_container
class OneRestart(unittest.TestCase):
    def cut_recover_start(self, a):
        """Codex F1's journal: a real child, `back --unattended --why r1 --old-version V` (the updater's child: the
        holder), finds the enabled unit down and its validate UNKNOWN, so its journal stays OPEN; then RECOVER (the
        holder's child too) validates config.toml (PRE: PASS) and is cut by a SIGKILL right after its `starting E pre`,
        before its start. The journal's lines."""
        a.p.set_unit(active=False)
        a.p.runner = UNKNOWN
        r = a.p.unattended('back', '--unattended', '--why', 'r1', '--old-version', V)
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertEqual(keys(a.p.window())[-1], 'end', 'the premise: the child left its journal open')
        a.p.runner = PASS
        a.p.hooks(('journal:starting', 'kill'))
        r = a.p.recover()
        self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
        lines = a.p.window()
        self.assertEqual((keys(lines)[-1], value(lines, 'starting').split(' ')[1]), ('starting', 'pre'), lines)
        self.assertFalse(a.p.unit_now()['active'], 'the premise: the cut came before its start')
        a.p.hooks()
        a.p.runner = PASS
        a.mark()
        return lines

    def test_a_resumed_start_is_the_pass_s_one_restart(self):
        """The next pass (within 600 s of that `starting`): RECOVER resumes the start with no new line and closes the
        journal on PRE; R1 says rollback: no rollback window in this pass (its line says why), r1_since removed, ONE
        start and no stop. The next pass rolls back."""
        a = Armed(self)
        cut = self.cut_recover_start(a)
        r = a.ok('pass')
        ws = a.windows()
        self.assertEqual([w for w, _ in ws], [value(cut, 'window')], 'a rollback window started: ' + r.stdout[-3000:])
        self.assertEqual([k for k in keys(ws[0][1])[len(cut):] if k in ('starting', 'stopping')], [],
                         'the premise: RECOVER resumed its start with no new line')
        self.assertEqual((len(a.since('start')), a.since('stop'), a.since('restart')), (1, [], []))
        self.assertIn("this pass's RECOVER started runscaler", r.stdout)
        self.assertNotIn('r1_since', a.fam())
        self.assertEqual((a.fam()['candidate']['version'], a.p.images()), (V, [ref(OLD)] * 2))
        a.mark()
        a.rolled_back(a.ok('pass'))

    def test_control_recover_that_finds_runscaler_running_starts_nothing_and_the_rollback_goes_on(self):
        """The same journal; runscaler started before the pass (systemd, or a person), after config.toml's install:
        RECOVER's resumed start finds it RUNNING and starts nothing; the rollback goes on in this pass: one window,
        rolled back to PREV, its one stop and one start."""
        a = Armed(self)
        cut = self.cut_recover_start(a)
        a.p.set_unit(active=True, start=a.p.clock() + 1, pid=300)
        a.p.clock(plus=2)
        r = a.ok('pass')
        ws = a.windows()
        self.assertEqual(len(ws), 2, r.stdout[-3000:])
        self.assertEqual(ws[0][0], value(cut, 'window'))
        self.assertEqual((value(ws[1][1], 'kind'), value(ws[1][1], 'why')), ('rollback', 'r1'))
        self.assertEqual(a.p.images(), [ref(PREV)] * 2)
        self.assertEqual((a.fam().get('candidate'), a.fam().get('rejected')), (None, [V]))
        self.assertEqual((len(a.since('stop')), len(a.since('start')), a.since('restart')), (1, 1, []))


@needs_container
class TheClock(unittest.TestCase):
    def test_a_kill_after_the_core_s_write_counts_no_time_while_the_unit_is_disabled(self):
        """Codex F2: R1 says rollback while a person's `disable` (without --now) leaves runscaler serving; the pass is
        killed right after its first rename onto STATE (the core's write, which persists R1's verdict): no r1_since in
        it. Then 2 h with the unit disabled and no pass (the timer stopped), then enabled: the next pass tries afresh:
        one window, rolled back, no ROLLBACK FAILED."""
        a = Armed(self)
        a.p.set_unit(enabled=False)
        a.p.hooks(('mv-done:STATE', 'kill-updater'))
        a.p.write(a.p.path('stubs', 'mv'), MV_STATE.replace('@SB@', repr(a.p.root)), 0o755)
        r = a.run('pass')
        self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
        self.assertIn('kill-updater', '\n'.join(a.p.events()), 'the premise: the kill came')
        st = a.state()
        self.assertIsNotNone(st.get('core'), "the premise: the core's write came before the kill")
        self.assertNotIn('r1_since', st['families'][FAM], 'time with the unit not enabled counts')
        a.p.hooks()
        a.p.clock(plus=7201)
        a.p.set_unit(enabled=True)
        a.mark()
        r = a.ok('pass')
        self.assertNotIn('ROLLBACK FAILED', a.held(), r.stdout[-3000:])
        a.rolled_back(r)

    def test_a_pending_hand_edit_never_counts_against_the_2_h(self):
        """Opus F1: R1 says rollback; a hand `03-runscaler.sh real` with the same bytes (config.toml installed after
        runscaler started), no restart. Passes at t, t + 1 h and t + 2 h: no r1_since, no ROLLBACK FAILED, STOP HAND
        CHANGE (a pending hand edit) held, and no window (the Studio's shape: the precondition before the child). Then
        the person restarts runscaler (the STOP's advice), and the next pass rolls back."""
        a = Armed(self)
        hand_edit(a)
        t = a.p.clock()
        for after in (0, 3600, 7200):
            a.p.clock(now=t + after)
            a.mark()
            r = a.ok('pass')
            f = a.fam()
            self.assertNotIn('r1_since', f, (after, r.stdout[-3000:]))
            self.assertNotIn('ROLLBACK FAILED', a.held(), (after, r.stdout[-3000:]))
            self.assertEqual(a.held(), ['HAND CHANGE'], r.stdout[-3000:])
            self.assertIn('runner-updater: pass: STOP HAND CHANGE: a pending hand edit', r.stdout)
            self.assertEqual(a.windows(), [], r.stdout[-3000:])
            self.assertIsNone(a.p.window())
            self.assertEqual(a.since('stop') + a.since('start') + a.since('restart'), [])
            self.assertEqual(f['candidate']['version'], V)
        a.p.clock(now=t + 7250)
        a.p.set_unit(start=a.p.clock(), pid=300)
        a.p.clock(now=t + 7300)
        a.mark()
        a.rolled_back(a.ok('pass'))

    def test_control_the_restart_before_the_first_pass_rolls_back_at_once(self):
        """The control of the cell above: the same hand install, then the person's restart before R1's first pass: one
        window, rolled back."""
        a = Armed(self)
        m = hand_edit(a)
        a.p.set_unit(start=max(m, a.p.clock()) + 1, pid=300)
        a.p.clock(plus=5)
        a.mark()
        a.rolled_back(a.ok('pass'))

    def test_a_window_that_meets_a_pending_hand_edit_itself_counts_no_time(self):
        """The brief's 3(b) as worded: a try that ends by the window's own STOP HAND CHANGE (un_back: config.toml
        written after runscaler started; here a person's edit right as the window begins, after the pass's own check)
        is no try: its apply step's ONE write holds HAND CHANGE and removes r1_since. The control: a try that ends by
        its validate UNKNOWN (`end`, no STOP) keeps r1_since."""
        for what in ('hand edit', 'UNKNOWN'):
            with self.subTest(what):
                a = Armed(self)
                if what == 'hand edit':
                    a.p.hooks(('journal:why', 'edit-config'))
                else:
                    a.p.runner = UNKNOWN
                r = a.ok('pass')
                ws = a.windows()
                self.assertEqual(len(ws), 1, r.stdout[-3000:])
                (wid, lines), = ws
                self.assertNotIn('rename-start', keys(lines))
                if what == 'UNKNOWN':
                    self.assertIn('UNKNOWN', value(lines, 'end'), lines)
                    self.assertIn('r1_since', a.fam())
                    continue
                self.assertIn('HAND CHANGE: config.toml was installed after runscaler started', value(lines, 'stop'))
                self.assertIn('HAND CHANGE', a.held())
                self.assertNotIn('r1_since', a.fam(), r.stdout[-3000:])


@needs_container
class OutageLast(unittest.TestCase):
    def test_a_rollback_whose_start_fails_holds_pool_down_naming_its_journal(self):
        """Codex F3: the rollback window stops runscaler, and its start crash-loops (no RUNS in 10 min:
        `pre-close-failure`, the journal open, exit 1). THE OUTAGE RULE runs after it: STOP POOL DOWN held, once,
        naming the open journal and its last line; no second restart (the window's one stop and one start)."""
        a = Armed(self)
        a.p.hooks(('journal:starting', 'crash'))
        r = a.run('pass')
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertEqual(keys(a.p.window())[-1], 'pre-close-failure', a.p.window())
        down = held(a)
        self.assertEqual(len(down), 1, r.stdout[-3000:])
        for s in ('CI is down', WINDOW, 'pre-close-failure'):
            self.assertIn(s, down[0])
        self.assertEqual((len(a.since('stop')), len(a.since('start')), a.since('restart')), (1, 1, []))
        self.assertTrue(last_line(r).startswith('runner-updater: STOP the window journal %s stays open' % WINDOW))

    def test_a_pool_down_the_window_s_recover_made_untrue_is_cleared(self):
        """The reverse (Codex F3): the unit enabled and down when the pass begins (POOL DOWN held by its first outage
        read); the window finds it down and its validate UNKNOWN (its journal open), and RECOVER right after it
        validates config.toml and starts runscaler: THE OUTAGE RULE after the window clears POOL DOWN, and the pass's
        "rollback pending" line says nothing of CI down (the window's own `end` said so before RECOVER started it)."""
        a = Armed(self)
        a.p.set_unit(active=False)
        a.p.runner = {'seq': [UNKNOWN, PASS]}
        r = a.ok('pass')
        self.assertIn('runner-updater: pass: STOP POOL DOWN: ', r.stdout, 'the premise: the pass began with CI down')
        (wid, lines), = a.windows()
        self.assertIn('recover-start', keys(lines), 'the premise: RECOVER ended the window journal')
        self.assertTrue(a.p.unit_now()['active'])
        self.assertEqual(held(a), [], r.stdout[-3000:])
        self.assertIn('runner-updater: pass: STOP POOL DOWN is cleared', r.stdout)
        pending = [l for l in r.stdout.splitlines() if l.startswith('runner-updater: pass: rollback pending')]
        self.assertEqual(len(pending), 1, r.stdout[-3000:])
        self.assertNotIn('CI is down', pending[0])

    def test_control_a_person_s_disable_during_the_window_holds_no_pool_down(self):
        """The control: a person's `disable --now` right after the window stopped runscaler: the window closes with CI
        DISABLED and no start; THE OUTAGE RULE after it holds no POOL DOWN (CI off by a person)."""
        a = Armed(self)
        a.p.hooks(('journal:stopped', 'disable'))
        r = a.ok('pass')
        (wid, lines), = a.windows()
        self.assertFalse(a.p.unit_now()['active'])
        self.assertIn('CI DISABLED', a.held(), r.stdout[-3000:])
        self.assertEqual(held(a), [], r.stdout[-3000:])
        self.assertEqual(json.loads(a.p.read(STATE))['families'][FAM].get('candidate'), None, lines)


if __name__ == '__main__':
    unittest.main()
