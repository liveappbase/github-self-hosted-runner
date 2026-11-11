"""linux-docker/bin/runner-updater's ROLLBACK CALLER (S2b-3c-1 D-e; the r3 FOLD "THE ROLLBACK'S PRECONDITIONS"; B2b
item 1): R1's rollback verdict for hz-docker's candidate, in a pass that is ON, starts ONE rollback window as the pass's
CHILD, `pool-image.sh back --unattended --why r1|r1-connect --verdict PASSDIR/r1.json --old-version V` (no idle wait),
then the apply step. (Named for its CI part, test_[c-jv-z]*.py: .github/workflows/release-check.yml.)

- A REAL ONE (r3 Codex F2): an inherited switch journal (a 3b-3 one: no closing lines but `closed`) applied, then the
  real core's R1 verdict: one window, rolled back, the candidate's version rejected; the next pass starts none.
- THE STUDIO'S PRECONDITIONS (r3 Opus F3): a candidate; no ROLLBACK FAILED held; config.toml's family lines = the
  candidate's (else STOP HAND CHANGE, no window: a person's hand switch, config.toml.prev put back); config.toml.prev's
  lines = the state's `previous` (else STOP ROLLBACK FAILED, no window); a pass whose RECOVER started runscaler starts
  none (D-g: one restart per pass).
- THE UNIT (operator (1), r3 Opus F4): not enabled: no window, "rollback pending: CI disabled by a person"; enabled
  and down (a plain stop, a failed unit): the window goes on, and its restart starts runscaler on the rollback.
- r1_since (r3 Opus F13; the Studio's): the first pass whose R1 said rollback; counted only while a try could start (a
  disabled unit, a pending hand edit, D-g's wait and `off` remove it); 2 h of tries: STOP ROLLBACK FAILED.
- THE CHILD'S JOURNAL: open with no restart of its own (it found the enabled unit down and ended before its rename):
  RECOVER in the same pass, then the apply step; open after its own restart: the next pass's RECOVER (D-g).
Every cell runs the real scripts (support.Pool, a throwaway container, a fake clock) and the updater as RS_USER. R1's
verdict is the real core's in the first class; elsewhere a planted core/r1.jq (the cell's ~/build copy) is the real
program with its answer's hz-docker verdict set to rollback, so the preconditions meet a verdict no log has to build.
"""
import json
import os
import time
import unittest

from tests.hetzner.support import digest, needs_container, ref, sha256_file
from tests.hetzner.test_unattended import PASS, UNKNOWN, keys, value
from tests.hetzner.test_recover import cut
from tests.hetzner.test_updater import (FAM, MAIN, NEW, OLD, PASS as PASSDIR, SMALL, STATEDIR, V, WINDOW, WINDOWS, Rig,
                                        candidate, failed, scaling)

PREV = digest(37)                 # the image the planted rigs' config.toml.prev names (their `previous`)
REJECTED = os.path.join(STATEDIR, 'rejected')
DUE_LINE = 'runner-updater: pass: hz-docker is not due: a window ran in this pass'
VERDICT = {'verdict': 'rollback', 'set': MAIN, 'connect_only': False, 'reason': 'a planted R1 verdict',
           'failures': [{'t': 1793900000 + 10 * i, 'c': False, 'x': 'planted failure %d' % i} for i in (1, 2, 3)]}


def plant_r1(g, connect_only=False):
    """core/r1.jq of the cell's ~/build: the real program, its answer's hz-docker verdict set to R1's rollback."""
    with open(os.path.join(g.p.build, 'core', 'r1.jq')) as f:
        real = f.read()
    v = dict(VERDICT, connect_only=connect_only)
    g.plant('core/r1.jq', real + '\n| if .verdict == "ok" then .families[%s] = ((.families[%s] // {}) + %s) else . end'
            '\n' % (json.dumps(FAM), json.dumps(FAM), json.dumps(v)))


class Armed(Rig):
    """test_updater's Rig (production OLD, fake clock, ON), the registry serving OLD, NEW and PREV; config.toml.prev =
    config.toml with PREV's image (a switch's backup: the rollback's target); hz-docker's candidate runner V on OLD's
    lines (config.toml's) and previous PREV's; R1 planted to say rollback (plant=False: the real core)."""

    def __init__(self, test, fam=None, plant=True, connect_only=False):
        super().__init__(test, on=True)
        self.p.curl['served'] = [OLD, NEW, PREV]
        self.p.write(self.p.rpath('config.toml.prev'), self.p.config().replace(ref(OLD), ref(PREV)), 0o600)
        f = {'candidate': candidate(self.p.clock() - 60), 'previous': {MAIN: ref(PREV), SMALL: ref(PREV)}}
        f.update(fam or {})
        self.put({'format': 1, 'on': True, 'families': {FAM: f}})
        if plant:
            plant_r1(self, connect_only)
        self.mark()

    def mark(self):
        """From here on: the systemctl calls counted, and the windows closed before (none or the switch's)."""
        self.n_sys = len(self.p.lines('systemctl'))
        self.n_win = len(self.p.closed())

    def since(self, verb):
        return [l for l in self.p.lines('systemctl')[self.n_sys:] if l.split(' ')[1:2] == [verb]]

    def fam(self):
        return self.state()['families'][FAM]

    def held(self):
        return [s['stop'] for s in self.fam().get('stops', [])]

    def windows(self):
        """The rollback windows since mark(): their (ID, lines)."""
        return self.p.closed()[self.n_win:]

    def no_window(self, r):
        """No rollback window: none closed, none at WINDOW, no stop, start or restart, config.toml as it was."""
        self.t.assertEqual(self.windows(), [], r.stdout[-3000:])
        self.t.assertIsNone(self.p.window())
        self.t.assertEqual(self.since('stop') + self.since('start') + self.since('restart'), [])
        self.t.assertEqual(self.p.images(), [ref(OLD)] * 2)
        self.t.assertIsNone(self.p.read(REJECTED))

    def rolled_back(self, r, why='r1'):
        """ONE rollback window, closed and archived: rolled back to PREV, the candidate V rejected (OLD's digest, the
        image it left, in the rejected file), the window's one stop and one start. Its (ID, lines)."""
        t = self.t
        ws = self.windows()
        t.assertEqual(len(ws), 1, 'not ONE rollback window: %r\n%s' % ([w for w, _ in ws], r.stdout[-3000:]))
        (wid, lines), = ws
        t.assertEqual((value(lines, 'kind'), value(lines, 'why'), value(lines, 'old-version')), ('rollback', why, V))
        t.assertEqual(lines[-2].split(' ')[-1], 'target-running', lines)
        t.assertEqual(self.p.images(), [ref(PREV)] * 2)
        f = self.fam()
        t.assertEqual((f.get('candidate'), f.get('previous')), (None, None))
        t.assertNotIn('r1_since', f)
        t.assertEqual(f.get('rejected'), [V])
        t.assertEqual(self.p.read(REJECTED), OLD + '\n')
        t.assertEqual((len(self.since('stop')), len(self.since('start')), self.since('restart')), (1, 1, []))
        t.assertIn("runner-updater: pass: R1's rollback is due for hz-docker (runner %s)" % V, r.stdout)
        t.assertIn('runner-updater: pass: rolled back hz-docker', r.stdout)
        t.assertIn(DUE_LINE, r.stdout)
        return wid, lines


@needs_container
class Real(unittest.TestCase):
    def test_r1_s_verdict_on_an_inherited_switch_rolls_back_once(self):
        """r3 Codex F2: 3b-3's switch to NEW (a real `up --unattended` window whose closing lines are cut to 3b-3's
        shape: `running`, then `closed`) is applied by the next pass (candidate V, previous OLD) and its evidence
        window opens; three counted failures: the next pass's real R1 says rollback, and the pass starts ONE window as
        its child: rolled back to OLD, V rejected (NEW's digest in the rejected file), STOP ROLLED BACK of V with R1's
        own failures, the verdict (PASSDIR/r1.json) copied into the window's folder by its sha; no "would roll back";
        every systemctl call of that pass that is not a read (show, is-active, is-enabled) is the window's one stop and
        one start (B2b review r1, Codex F6: no disable, enable or other unit change). The next pass starts none (the
        candidate is gone)."""
        g = Rig(self, on=True)
        g.p.curl['served'] = [OLD, NEW]
        up = g.p.unattended('up', '--unattended', V, NEW)
        self.assertEqual(up.returncode, 0, up.stdout[-3000:] + up.stderr)
        legacy = [l for l in g.p.window() if not l.startswith(('prev ', 'installed '))]
        g.p.write(WINDOW, ''.join(l + '\n' for l in legacy), 0o600)
        g.ok('pass')
        f = g.state()['families'][FAM]
        self.assertEqual((f['candidate']['version'], f['candidate']['lines'], f['previous']),
                         (V, {MAIN: ref(NEW), SMALL: ref(NEW)}, {MAIN: ref(OLD), SMALL: ref(OLD)}))
        self.assertEqual(g.state()['last_window'], value(legacy, 'window'))
        self.assertTrue(g.out('r1')['families'][FAM]['open'], g.out('r1'))
        t = int(time.time()) + 100
        g.append(failed(t) + failed(t + 10) + failed(t + 20) + scaling(t + 160) + scaling(t + 161))
        n_sys, n_win = len(g.p.lines('systemctl')), len(g.p.closed())
        r = g.ok('pass')
        self.assertEqual(g.out('r1')['families'][FAM]['verdict'], 'rollback')
        self.assertNotIn('would roll back', r.stdout)
        ws = g.p.closed()[n_win:]
        self.assertEqual(len(ws), 1, r.stdout[-3000:])
        (wid, lines), = ws
        self.assertEqual((value(lines, 'kind'), value(lines, 'why'), value(lines, 'old-version')),
                         ('rollback', 'r1', V))
        copy = os.path.join(WINDOWS, wid + '.d', 'verdict.json')
        self.assertEqual(value(lines, 'verdict'), sha256_file(copy))
        self.assertEqual(sha256_file(copy), sha256_file(os.path.join(PASSDIR, 'r1.json')))
        self.assertEqual(g.p.images(), [ref(OLD)] * 2)
        f = g.state()['families'][FAM]
        self.assertEqual((f.get('candidate'), f.get('rejected')), (None, [V]))
        self.assertEqual(g.p.read(REJECTED), NEW + '\n')
        rb, = [s for s in f['stops'] if s['stop'] == 'ROLLED BACK']
        self.assertEqual(rb['version'], V)
        self.assertEqual(len(rb['detail']['failures']), 3)
        self.assertEqual(rb['detail']['set'], MAIN)
        sys_ = [l for l in g.p.lines('systemctl')[n_sys:]
                if l.split(' ')[1] not in ('show', 'is-active', 'is-enabled')]
        self.assertEqual(sys_, ['--user stop runscaler', '--user start runscaler'],
                         'the window restarts runscaler once, and nothing else changes the unit')
        self.assertIn(DUE_LINE, r.stdout)
        n_sys = len(g.p.lines('systemctl'))
        r = g.ok('pass')
        self.assertEqual(len(g.p.closed()), n_win + 1, 'a second window started')
        self.assertNotIn("R1's rollback is due", r.stdout)
        self.assertEqual([l for l in g.p.lines('systemctl')[n_sys:] if l.split(' ')[1] != 'show'], [])

    def test_r1_s_verdict_on_a_cut_switch_that_recover_ended_rolls_back(self):
        """r2 Codex F2's input: a switch cut after `stopped` (its journal OPEN at install: here this release's own
        window, cut by a SIGKILL); the next pass's RECOVER starts runscaler on its TARGET, the apply step sets the
        candidate (V on NEW's lines, previous OLD) and archives it. Three counted failures: the next pass's real R1 says
        rollback, and the rollback runs (that pass's RECOVER started nothing): rolled back to OLD, V rejected."""
        g = cut(self, 'up', ('journal:stopped', 'kill'))
        u = Rig.__new__(Rig)                  # test_updater's Rig methods on the cut rig's Pool
        u.t, u.p, u.log = self, g.p, g.p.rpath('runner.log')
        u.put({'format': 1, 'on': True, 'families': {}})
        r = u.ok('pass')
        self.assertIn('POOL IMAGE RECOVER: ', r.stdout)
        f = u.state()['families'][FAM]
        self.assertEqual((f['candidate']['version'], f['previous']), (V, {MAIN: ref(OLD), SMALL: ref(OLD)}))
        self.assertIsNone(g.p.window())
        u.ok('pass')
        self.assertTrue(u.out('r1')['families'][FAM]['open'], u.out('r1'))
        t = int(time.time()) + 100
        u.append(failed(t) + failed(t + 10) + failed(t + 20) + scaling(t + 160) + scaling(t + 161))
        n_win = len(g.p.closed())
        r = u.ok('pass')
        self.assertEqual(u.out('r1')['families'][FAM]['verdict'], 'rollback')
        ws = g.p.closed()[n_win:]
        self.assertEqual(len(ws), 1, r.stdout[-3000:])
        self.assertEqual(value(ws[0][1], 'why'), 'r1')
        self.assertEqual(g.p.images(), [ref(OLD)] * 2)
        f = u.state()['families'][FAM]
        self.assertEqual((f.get('candidate'), f.get('rejected')), (None, [V]))


@needs_container
class Preconditions(unittest.TestCase):
    def test_the_control_one_window_rolls_back(self):
        """The control of the cells below: one window, rolled back to PREV, V rejected. r3 Opus F11: old-version is the
        candidate's version (its lines name `old`), never RUN_USER's build record of that image, which here names
        another version (2.338.7)."""
        a = Armed(self)
        a.p.record('2.338.7', OLD)
        r = a.ok('pass')
        wid, lines = a.rolled_back(r)
        rb, = [s for s in a.fam()['stops'] if s['stop'] == 'ROLLED BACK']
        self.assertEqual(rb['detail'], {k: VERDICT[k] for k in ('set', 'failures', 'connect_only', 'reason')})

    def test_a_connect_only_verdict_rolls_back_with_why_r1_connect(self):
        """R1's verdict connect-class only: the window's `why` is r1-connect; the apply step counts it (connect_only {V:
        {n: 1, at: its closed}}) and rejects nothing (one retry after 1 h); the rollback itself is the same. The
        control: the cell above (`why r1`: rejected)."""
        a = Armed(self, connect_only=True)
        r = a.ok('pass')
        ws = a.windows()
        self.assertEqual(len(ws), 1, r.stdout[-3000:])
        (wid, lines), = ws
        self.assertEqual(value(lines, 'why'), 'r1-connect')
        self.assertEqual(a.p.images(), [ref(PREV)] * 2)
        f = a.fam()
        self.assertEqual(f.get('candidate'), None)
        self.assertEqual(f.get('rejected', []), [])
        self.assertIsNone(a.p.read(REJECTED))
        self.assertEqual(f['connect_only'], {V: {'n': 1, 'at': int(value(lines, 'closed'))}})
        rb, = [s for s in f['stops'] if s['stop'] == 'ROLLED BACK']
        self.assertTrue(rb['detail']['connect_only'])

    def test_the_studio_s_preconditions_start_no_window(self):
        """r3 Opus F3 (a) a person's hand switch to H, restarted (config.toml names H for hz-docker, not its
        candidate's lines): no window, STOP HAND CHANGE (a pending hand edit), nothing rejected, config.toml H;
        (b) config.toml.prev put back by hand as config.toml, three passes: no window in any, HAND CHANGE each pass;
        config.toml.prev changed (its lines are not the state's `previous`): STOP ROLLBACK FAILED, no window; a held
        ROLLBACK FAILED: no window, its line; no candidate: no window, its line. Each: r1_since as the Studio's (a
        pending hand edit removes it). The control: the cell above."""
        H = digest(36)
        for what in ('a hand switch', 'prev put back', 'prev changed', 'ROLLBACK FAILED held', 'no candidate'):
            with self.subTest(what):
                fam = {}
                if what == 'ROLLBACK FAILED held':
                    fam = {'stops': [{'family': FAM, 'stop': 'ROLLBACK FAILED', 'version': V, 'user': None,
                                      'detail': {'text': 'planted'}}]}
                if what == 'no candidate':
                    fam = {'candidate': None}
                a = Armed(self, fam=fam)
                a.p.curl['served'] = [OLD, NEW, PREV, H]
                if what in ('a hand switch', 'prev put back'):
                    text = (a.p.config().replace(ref(OLD), ref(H)) if what == 'a hand switch'
                            else a.p.config('config.toml.prev'))
                    a.p.write(a.p.rpath('config.toml'), text, 0o600)
                    m = int(os.stat(a.p.rpath('config.toml')).st_mtime)
                    a.p.set_unit(start=max(m, a.p.clock()) + 1, pid=200)     # a person restarted it on that file
                    a.mark()
                if what == 'prev changed':
                    a.p.write(a.p.rpath('config.toml.prev'), a.p.config().replace(ref(OLD), ref(H)), 0o600)
                for n in range(3 if what == 'prev put back' else 1):
                    r = a.ok('pass')
                    self.assertEqual(a.windows(), [], (n, r.stdout[-3000:]))
                    self.assertIsNone(a.p.window())
                    self.assertEqual(a.since('stop') + a.since('start') + a.since('restart'), [])
                    self.assertIsNone(a.p.read(REJECTED))
                    f = a.fam()
                    self.assertEqual(f.get('rejected', []), [])
                    if what in ('a hand switch', 'prev put back'):
                        self.assertEqual(a.held(), ['HAND CHANGE'], r.stdout[-3000:])
                        self.assertIn('runner-updater: pass: STOP HAND CHANGE: a pending hand edit', r.stdout)
                        self.assertNotIn('r1_since', f)
                        self.assertEqual(f['candidate']['version'], V)
                    elif what == 'prev changed':
                        self.assertEqual(a.held(), ['ROLLBACK FAILED'], r.stdout[-3000:])
                        self.assertIn('runner-updater: pass: STOP ROLLBACK FAILED: ', r.stdout)
                    elif what == 'ROLLBACK FAILED held':
                        self.assertEqual(a.held(), ['ROLLBACK FAILED'])
                        self.assertIn('but ROLLBACK FAILED holds it', r.stdout)
                    else:
                        self.assertIn('but it has no candidate', r.stdout)
                if what == 'a hand switch':
                    self.assertEqual(a.p.images(), [ref(H)] * 2)

    def test_a_pass_whose_recover_started_runscaler_starts_no_rollback(self):
        """D-g (a pass makes at most ONE restart of runscaler): a window journal cut right after its first line, the
        enabled unit down: this pass's RECOVER starts runscaler and closes it; R1 says rollback: no rollback window in
        this pass (its line says why; r1_since removed: no try could start), one start and no stop. The next pass
        starts it. The control: the cell above (no journal)."""
        a = Armed(self)
        os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
        a.p.write(WINDOW, 'window 20261106010000-4242\n', 0o600)
        a.p.set_unit(active=False)
        a.mark()
        r = a.ok('pass')
        self.assertIn("this pass's RECOVER started runscaler", r.stdout)
        self.assertEqual((len(a.since('start')), a.since('stop'), a.since('restart')), (1, [], []))
        self.assertEqual([w for w, _ in a.windows()], ['20261106010000-4242'], 'a rollback window started')
        self.assertNotIn('r1_since', a.fam())
        a.mark()
        r = a.ok('pass')
        a.rolled_back(r)


@needs_container
class TheUnit(unittest.TestCase):
    def test_not_enabled_is_rollback_pending_and_enabled_and_down_rolls_back(self):
        """Operator (1) on every route (r3 Opus F4 (a)): a person's `disable` (with or without --now): no window, the
        line "rollback pending: CI disabled by a person", r1_since removed (no try could start). The unit enabled and
        down (a plain `systemctl --user stop`; a failed unit): the window goes on, its restart starts runscaler on the
        rollback: rolled back, no `end`, no HAND CHANGE."""
        for what, kw in (('disabled', {'enabled': False}), ('disabled --now', {'enabled': False, 'active': False}),
                         ('stopped', {'active': False}), ('failed', {'active': False, 'failed': True})):
            with self.subTest(what):
                a = Armed(self)
                a.p.set_unit(**kw)
                r = a.ok('pass')
                if not kw.get('enabled', True) is False:
                    wid, lines = a.rolled_back(r)
                    self.assertNotIn('end', keys(lines))
                    self.assertNotIn('HAND CHANGE', a.held())
                    self.assertTrue(a.p.unit_now()['active'])
                    continue
                a.no_window(r)
                self.assertIn('runner-updater: pass: rollback pending: CI disabled by a person', r.stdout)
                self.assertNotIn('r1_since', a.fam())
                self.assertEqual(a.fam()['candidate']['version'], V)


@needs_container
class Since(unittest.TestCase):
    def test_a_disabled_unit_never_counts_against_the_2_h(self):
        """r3 Opus F13: the unit disabled for 3 h (R1's verdict standing: two passes, 3 h apart), then enabled: the
        next pass tries the rollback (one window, rolled back), no ROLLBACK FAILED. The control: the cell below."""
        a = Armed(self)
        a.p.set_unit(enabled=False)
        for n in (0, 1):
            if n:
                a.p.clock(plus=3 * 3600)
            r = a.ok('pass')
            self.assertIn('rollback pending: CI disabled by a person', r.stdout)
            self.assertNotIn('r1_since', a.fam())
        a.p.set_unit(enabled=True)
        r = a.ok('pass')
        a.rolled_back(r)
        self.assertNotIn('ROLLBACK FAILED', a.held())

    def test_control_2_h_of_unknown_tries_hold_rollback_failed(self):
        """Each try's validate is UNKNOWN (`end`: no STOP, R1 stays armed): tries at r1_since (the first pass's own
        clock), 1 h later and at 2 h - 1 s; at exactly 2 h (the pass's one clock, set to r1_since + 7200), STOP ROLLBACK
        FAILED and no try; then a pass starts none (ROLLBACK FAILED holds it)."""
        a = Armed(self)
        a.p.runner = UNKNOWN
        since = None
        for n, after in enumerate((None, 3600, 7199, 7200, 7300)):
            if after is not None:
                a.p.clock(now=since + after)
            a.mark()
            r = a.ok('pass')
            f = a.fam()
            if n < 3:
                self.assertEqual(len(a.windows()), 1, r.stdout[-3000:])
                (wid, lines), = a.windows()
                self.assertIn('UNKNOWN', value(lines, 'end'), lines)
                self.assertIn('rollback pending: ', r.stdout)
                since = f['r1_since'] if since is None else since
                self.assertEqual(f['r1_since'], since, 'r1_since moved')
                self.assertNotIn('ROLLBACK FAILED', a.held())
                continue
            self.assertEqual(a.windows(), [], r.stdout[-3000:])
            self.assertEqual(a.held(), ['ROLLBACK FAILED'], r.stdout[-3000:])
            self.assertEqual(f['candidate']['version'], V)
            if n == 3:
                self.assertIn('runner-updater: pass: STOP ROLLBACK FAILED: ', r.stdout)
            else:
                self.assertIn('but ROLLBACK FAILED holds it', r.stdout)

    def test_r1_since_goes_when_r1_says_other(self):
        """The Studio's do_pass: a pass whose R1 says anything but rollback removes r1_since (a pending try set it); the
        next rollback verdict starts its 2 h anew."""
        a = Armed(self)
        a.p.runner = UNKNOWN
        with open(os.path.join(a.p.build, 'core', 'r1.jq')) as f:
            planted = f.read()
        a.ok('pass')
        self.assertIn('r1_since', a.fam())
        real = planted.rsplit('\n| if .verdict == "ok" then .families[', 1)[0] + '\n'
        a.plant('core/r1.jq', real)
        r = a.ok('pass')
        self.assertNotEqual(a.out('r1')['families'][FAM]['verdict'], 'rollback', r.stdout[-3000:])
        self.assertNotIn('r1_since', a.fam())

    def test_off_removes_r1_since(self):
        """The Studio's `off`: time while OFF never counts against the 2 h: a try (UNKNOWN: pending) sets r1_since;
        `off` removes it; `on`, 3 h later: the next pass tries again (no ROLLBACK FAILED)."""
        a = Armed(self)
        a.p.runner = UNKNOWN
        a.ok('pass')
        self.assertIn('r1_since', a.fam())
        a.ok('off')
        self.assertNotIn('r1_since', a.fam())
        a.p.clock(plus=3 * 3600)
        a.ok('on')
        a.mark()
        r = a.ok('pass')
        self.assertEqual(len(a.windows()), 1, r.stdout[-3000:])
        self.assertNotIn('ROLLBACK FAILED', a.held())


@needs_container
class TheChildsJournal(unittest.TestCase):
    def test_open_with_no_restart_of_its_own_is_recovered_in_the_same_pass(self):
        """The child found the enabled unit down (a plain stop) and ended before its rename (its validate UNKNOWN): its
        journal stays OPEN (exit 1). The pass runs RECOVER right after it (which validates config.toml and starts
        runscaler on it: the pass's one start), then the apply step: the journal closed and archived in this pass, the
        candidate kept, nothing rejected, rollback pending. The control: the unit active: the child's `end` closes its
        journal itself (no RECOVER start), the same apply."""
        for down in (True, False):
            with self.subTest(down=down):
                a = Armed(self)
                a.p.runner = {'seq': [UNKNOWN, PASS]}
                if down:
                    a.p.set_unit(active=False)
                r = a.ok('pass')
                self.assertEqual(len(a.windows()), 1, r.stdout[-3000:])
                (wid, lines), = a.windows()
                self.assertIsNone(a.p.window())
                self.assertEqual('recover-start' in keys(lines), down, lines)
                self.assertEqual(len(a.since('start')), 1 if down else 0)
                self.assertEqual(a.since('stop'), [])
                self.assertTrue(a.p.unit_now()['active'])
                f = a.fam()
                self.assertEqual((f['candidate']['version'], f.get('rejected', [])), (V, []))
                self.assertIn('rollback pending: ', r.stdout)

    def test_open_after_its_own_restart_waits_for_the_next_pass(self):
        """D-g: the child's restart (its `starting`) runs a runscaler that crash-loops: no RUNS in 10 min,
        `pre-close-failure`, the journal open (exit 1). The pass runs no RECOVER on it (that would restart runscaler a
        second time): its STOP line, exit 1, the window's one stop and one start. The next pass's RECOVER ends it (B2b
        review r1, Opus F4: runner-start serves again by then): its `pre-close-failure` DECIDED the rollback as failed,
        so THE RESTORE puts the backup (OLD's config) back and starts runscaler on it; the apply step keeps the
        candidate V, rejects nothing and holds ROLLBACK FAILED; the journal archived, and no new window in that pass."""
        a = Armed(self)
        a.p.hooks(('journal:starting', 'crash'))
        r = a.run('pass')
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        lines = a.p.window()
        self.assertIsNotNone(lines)
        self.assertEqual(keys(lines)[-1], 'pre-close-failure', lines)
        self.assertNotIn('recover-start', keys(lines))
        self.assertEqual((len(a.since('stop')), len(a.since('start')), a.since('restart')), (1, 1, []))
        self.assertIn('runner-updater: STOP the window journal %s stays open' % WINDOW, r.stdout)
        self.assertNotIn(DUE_LINE, r.stdout)
        wid = value(lines, 'window')
        a.p.hooks()
        a.p.set_unit(runner='serves')
        a.mark()
        r = a.ok('pass')
        self.assertIsNone(a.p.window(), r.stdout[-3000:])
        ws = a.p.closed()
        self.assertEqual([w for w, _ in ws], [wid], 'a new window started: ' + r.stdout[-3000:])
        self.assertIn('restore', keys(ws[0][1]))
        self.assertEqual(a.p.images(), [ref(OLD)] * 2)
        self.assertTrue(a.p.unit_now()['active'])
        f = a.fam()
        self.assertEqual(((f.get('candidate') or {}).get('version'), f.get('rejected', [])), (V, []))
        self.assertIn('ROLLBACK FAILED', a.held())
        self.assertIsNone(a.p.read(REJECTED))


if __name__ == '__main__':
    unittest.main()
