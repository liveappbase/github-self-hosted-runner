"""RS_USER's pass SWITCHES (S2b-3c-2 B4a; the slice plan's E-1, E-2, E-9, E-11, E-13, E-14's pass side, E-15, THE TWO
LEVELS and THE OUTAGE RULE after every window, with its r2 and r3 FOLDs): DUE's step 12, a due release V with RUN_USER's
build record of digest D, is no longer a "would switch" line but the switch window itself.

- THE SWITCH CALLER (E-1 + r2 FOLD): with the updater ON, no window journal, no window in this pass and no restart by
  this pass's RECOVER, the pass runs `pool-image.sh up --unattended V D` as its child (fd 9), then: a closed journal ->
  THE APPLY STEP (the candidate, `due` removed in the same write: E-15); an open one with no `stopping` or `starting`
  line -> RECOVER at once (the pass's one restart); an open one after the child's own stop or start -> the STOP line,
  no RECOVER in this pass, exit 1 (E-13: one restart per pass); exit 3 (not idle, START STATE) -> THE NO IDLE CLOCK.
  THE OUTAGE RULE is the pass's LAST step after any child (also one that kept no journal).
- THE NO IDLE CLOCK (E-2): `due` {version, since}, the first pass that found the family due for V; OFF days count; a
  newer release starts it again. An `up` that exits 3 with now - since >= 3 days holds STOP NO IDLE of V (detail
  `digest`, hand `runner-updater switch-now hz-docker`), and that pass exits 0; before, "waits for idle (since ...)",
  exit 0, no journal (E-11). A cut switch's RECOVER wait keeps the journal: exit 1 (E-11).
- THE TWO LEVELS (r3 FOLD), before the facts: a held DISK is cleared when disk_ok passes; a held NO IDLE of V is
  dropped when the family has a candidate or runs V or newer: config.toml on that image AND the runscaler that runs
  started after its install (an install with no restart after it counts nothing: B4a fix 1). DISK is RAISED only when
  DUE finds a release due (E-9), by runner-facts.sh's disk_ok (ONE copy): exactly 10 % free goes on, 10 % less 1 KiB
  holds it.
- E-14, the pass's side: the copy `up` reads (pass/state.json) holds THIS pass's core state: a copy an older pass, an
  OFF time or a set this host does not have left excuses nothing; a copy the pass cannot write starts no `up`. The
  ages grown by real passes: test_recurring_passes.py (24 h of passes) and test_age_reset.py (the reset).
Every cell runs the real scripts (support.Pool, a throwaway container, the fake clock) and the updater as RS_USER.
(Named for its CI part, test_[n-q]*.py: .github/workflows/release-check.yml.)
"""
import json
import os
import unittest

from tests.hetzner.support import REPO, Pool, digest, healthz, iso, needs_container, ref, tarball
from tests.hetzner.test_back import one, readme, section
from tests.hetzner.test_recover import cut
from tests.hetzner.test_release_due import CUR, DAY, FAM, MAIN, NEW, NOT, OLD, SMALL, STATE, V, Due, stop

WINDOW = os.path.join(Pool.STATE, 'window')
WINDOWS = os.path.join(Pool.STATE, 'windows')
CORE_COPY = os.path.join(Pool.STATE, 'pass', 'state.json')
BUSY = healthz(**{MAIN: {'busy': 1}})
IDLE = healthz()
DUE_LINE = ('runner-updater: pass: hz-docker is due for runner %s: the switch window, pool-image.sh up --unattended %s '
            '%s (its lines follow)' % (V, V, NEW))
WAITS = 'runner-updater: pass: hz-docker waits for idle (since '
NO_IDLE_S = 3 * DAY
BIG = 1000000          # KiB: df's size in the DISK cells (10 % of it: 100000)


class G(Due):
    """Due's rig (production on OLD, RUN_USER's records of CUR on OLD and of V on NEW, the release V 3 days old, ON),
    the pool IDLE (Due's own cells make it busy), and a pass that may write the state."""

    def __init__(self, test, hz=IDLE, **kw):
        super().__init__(test, **kw)
        self.p.curl['healthz'] = hz
        self.p.write(self.p.path('logs', 'systemctl.log'), '')   # the production's calls are not the updater's

    def go(self, rc=0):
        r = self.p.updater('pass')
        self.t.assertEqual(r.returncode, rc, r.stdout[-5000:] + r.stderr)
        return r

    def fam(self):
        return self.families().get(FAM, {})

    def held(self, name=None):
        return [s for s in self.fam().get('stops', []) if name is None or s['stop'] == name]

    def calls(self, verb):
        return [l for l in self.p.lines('systemctl') if l.split(' ')[1:2] == [verb]]

    def ups(self):
        """The switch windows the passes started: each a journal (open, or archived) of kind switch."""
        out = [l for _, l in self.p.closed() if 'kind switch' in l]
        w = self.p.window()
        return out + ([w] if w and 'kind switch' in w else [])


@needs_container
class TheSwitchCaller(unittest.TestCase):
    def test_a_due_release_on_an_idle_pool_is_switched_by_the_pass(self):
        """E-1: one window `up --unattended V D`, one stop and one start; THE APPLY STEP: the candidate V on D's image,
        previous the old image, `due` gone in that write (E-15); DUE's line says what was done; exit 0. No "would"."""
        g = G(self)
        r = g.go()
        self.assertIn(DUE_LINE, r.stdout)
        self.assertNotIn('would switch', r.stdout)
        self.assertIn('runner-updater: pass: switched hz-docker to %s: it runs %s (the window journal ' % (V, ref(NEW)),
                      r.stdout)
        ups = g.ups()
        self.assertEqual(len(ups), 1, r.stdout[-3000:])
        self.assertIn('digest ' + NEW, ups[0])
        self.assertEqual((len(g.calls('stop')), len(g.calls('start')), len(g.calls('restart'))), (1, 1, 0))
        f = g.fam()
        self.assertEqual(f['candidate']['version'], V)
        self.assertEqual(f['candidate']['lines'], {MAIN: ref(NEW), SMALL: ref(NEW)})
        self.assertEqual(f['previous'], {MAIN: ref(OLD), SMALL: ref(OLD)})
        self.assertNotIn('due', f, 'E-15: the close that sets the candidate removes `due`')
        self.assertIsNone(g.p.window())
        self.assertEqual(g.p.images(), [ref(NEW)] * 2)
        r2 = g.go()
        self.assertIn(NOT + 'an open candidate (runner %s)' % V, r2.stdout)

    def test_controls_no_window_starts(self):
        """OFF; an open candidate (DUE step 1); a STOP that holds it (step 2); this pass's RECOVER started runscaler
        (D-g: a pass makes at most one restart; a window cut before its first effect, with the unit down: RECOVER's
        start is the pass's one): no switch window, and DUE's line says why."""
        for why in ('off', 'a candidate', 'a stop', "recover's start"):
            with self.subTest(why):
                fam = {'candidate': {'version': '2.338.9', 'lines': {MAIN: ref(OLD), SMALL: ref(OLD)},
                                     'closed_at': 1761955200}} if why == 'a candidate' else \
                      {'stops': [stop('HAND CHANGE', text='x')]} if why == 'a stop' else None
                g = G(self, family=fam)
                if why == 'off':
                    st = json.loads(g.p.read(STATE))
                    st['on'] = False
                    g.put(st)
                if why == "recover's start":
                    os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
                    g.p.write(WINDOW, 'window 20261106010000-4242\n', 0o600)
                    g.p.act('stop')                                # the unit enabled and down: RECOVER starts it
                r = g.go()
                self.assertEqual(g.ups(), [], r.stdout[-3000:])
                self.assertNotIn('pool-image.sh up --unattended', r.stdout)
                if why == "recover's start":
                    self.assertIn("this pass's RECOVER started runscaler", r.stdout)
                    self.assertEqual(len(g.calls('start')), 1)

    def test_a_child_that_restarted_and_left_its_journal_open_is_a_stop_with_no_recover(self):
        """E-1 + r2 FOLD (Codex r1 F1, Opus r1 F4), E-13: the new runscaler never serves (it hangs after the stop):
        `up` journals `pre-close-failure` and exits 1 with its journal open after its own stop and start: no RECOVER in
        this pass, exactly one stop and one start, the STOP line, exit 1, and THE OUTAGE RULE (the last step) holds POOL
        DOWN naming the journal's last line (Codex r1 F2). The control: an open journal with neither line (a hand change
        found right after `rename-start`): RECOVER runs in the same pass."""
        g = G(self)
        g.p.hooks(('systemctl:stop-done', 'hang'))
        r = g.go(rc=1)
        w = g.p.window()
        self.assertIsNotNone(w, r.stdout[-3000:])
        self.assertIn('pre-close-failure', [l.split(' ')[0] for l in w])
        self.assertNotIn('recover-start', [l.split(' ')[0] for l in w], 'RECOVER ran in the same pass')
        self.assertEqual((len(g.calls('stop')), len(g.calls('start')), len(g.calls('restart'))), (1, 1, 0))
        self.assertIn('the next run\'s RECOVER ends it (a pass makes at most one restart of runscaler)', r.stdout)
        pd = g.held('POOL DOWN')
        self.assertEqual(len(pd), 1, r.stdout[-3000:])
        self.assertIn('pre-close-failure', pd[0]['detail']['text'])
        c = G(self)
        c.p.hooks(('journal:rename-start', 'hand-file'))
        r = c.go()
        w = c.ups()[-1]
        self.assertIn('recover-start', [l.split(' ')[0] for l in w], r.stdout[-3000:])
        self.assertIn('POOL IMAGE RECOVER: ', r.stdout)

    def test_a_child_that_closed_with_a_stop_is_applied_and_the_pass_exits_0(self):
        """`up` exits 1 with its journal CLOSED (STAGED changed after THE BACKUP: STOP check failed, closed pre): THE
        APPLY STEP holds check failed of V; no candidate; a STOP held anew: the pass exits 0 (E-15), and the next
        pass's DUE says step 8 (a STOP of the eligible release)."""
        g = G(self)
        g.p.hooks(('mv-done:config.toml.prev', 'edit-staged'))
        r = g.go()
        cf = g.held('check failed')
        self.assertEqual(len(cf), 1, r.stdout[-3000:])
        self.assertEqual(cf[0]['version'], V)
        self.assertIsNone(g.fam().get('candidate'))
        self.assertIsNone(g.p.window())
        g.p.hooks()
        self.assertIn(NOT + 'STOP check failed (runner %s): it is of the eligible release' % V, g.go().stdout)

    def test_the_switched_line_says_it_runs_only_after_a_start_into_its_target(self):
        """B4a fix 1 (Opus r1 F1): a person's `systemctl --user disable` during the switch's drain: the window closes
        target-idle (its TARGET installed, nothing started, STOP CI DISABLED held), the candidate is set, and the pass's
        line says the TARGET is installed and runscaler has not started into it, never "it runs". The control: the
        uninterrupted switch (target-running) says "it runs IMAGE"."""
        for disable in (True, False):
            with self.subTest(disable=disable):
                g = G(self)
                if disable:
                    g.p.hooks(('systemctl:stop-done', 'disable'))
                r = g.go()
                self.assertEqual(g.fam()['candidate']['version'], V, r.stdout[-3000:])
                line = [l for l in r.stdout.splitlines() if l.startswith('runner-updater: pass: switched hz-docker to ')]
                self.assertEqual(len(line), 1, r.stdout[-3000:])
                if disable:
                    self.assertEqual(len(g.calls('start')), 0)
                    self.assertEqual([s['stop'] for s in g.held()], ['CI DISABLED'])
                    self.assertNotIn('it runs', line[0])
                    self.assertIn('runner-updater: pass: switched hz-docker to %s: %s is installed, and runscaler has '
                                  'not started into it (the close: target-idle; the window journal ' % (V, ref(NEW)),
                                  line[0])
                else:
                    self.assertTrue(line[0].startswith('runner-updater: pass: switched hz-docker to %s: it runs %s (the '
                                                       'window journal ' % (V, ref(NEW))), line[0])

    def test_a_child_that_kept_no_journal_is_followed_by_the_outage_rule(self):
        """Codex r1 F2: runscaler is down when the switch starts (the unit enabled: CI down): `up` exits 3 (START
        STATE) with no journal; THE OUTAGE RULE as the pass's last step holds POOL DOWN. The control: the same exit 3
        with a healthy busy pool holds none."""
        for down in (True, False):
            with self.subTest(down=down):
                g = G(self, hz=BUSY)
                if down:
                    g.p.hooks(('journal:window', 'stop'))       # it stops right after the window's first line
                r = g.go()
                self.assertEqual(g.p.window(), None)
                self.assertIn(WAITS, r.stdout)
                self.assertEqual(len(g.held('POOL DOWN')), 1 if down else 0, r.stdout[-3000:])


@needs_container
class TheNoIdleClock(unittest.TestCase):
    def test_three_days_of_a_busy_pool_hold_no_idle(self):
        """E-2, E-11: each pass's `up` finds the pool busy and exits 3 (no journal): the pass exits 0 with "waits for
        idle (since T0)", `due` {V, T0}; at T0 + 3 days - 1 s it still waits; at T0 + 3 days: STOP NO IDLE of V, held,
        detail.digest D and the hand line `runner-updater switch-now hz-docker` (status prints it), exit 0; the next
        pass is held by it (DUE step 2: a newer release does not proceed alone past it)."""
        g = G(self, hz=BUSY)
        t0 = g.p.clock()
        r = g.go()
        self.assertIn(WAITS, r.stdout)
        self.assertEqual(g.fam()['due'], {'version': V, 'since': t0})
        self.assertEqual(g.ups(), [])
        for plus, held in ((NO_IDLE_S - 1, False), (NO_IDLE_S, True)):
            g.p.clock(now=t0 + plus)
            r = g.go()
            self.assertEqual(g.fam()['due'], {'version': V, 'since': t0})
            ni = g.held('NO IDLE')
            if not held:
                self.assertEqual(ni, [], r.stdout[-3000:])
                self.assertIn(WAITS, r.stdout)
                continue
            self.assertEqual(len(ni), 1, r.stdout[-3000:])
            self.assertEqual((ni[0]['version'], ni[0]['detail']['digest'], ni[0]['detail']['hand']),
                             (V, NEW, 'runner-updater switch-now hz-docker'))
            self.assertIn('runner-updater: pass: hz-docker holds STOP NO IDLE (runner %s): ' % V, r.stdout)
        self.assertIn('Next: `runner-updater switch-now hz-docker`', g.p.updater('status').stdout)
        g.p.clock(plus=600)
        r = g.go()
        self.assertIn(NOT + 'STOP NO IDLE (runner %s): a newer release does not proceed alone past it' % V, r.stdout)
        self.assertEqual(g.ups(), [])

    def test_off_days_count_and_a_newer_release_starts_the_clock_again(self):
        """E-2: `due` stays while the updater is OFF (those days count): a busy pass, `off`, 3 days, `on`, a busy pass:
        NO IDLE at once. The control: a newer release (eligible, built) at that pass: `due` {that version, now}, it
        waits, no NO IDLE."""
        for newer in (False, True):
            with self.subTest(newer=newer):
                g = G(self, hz=BUSY)
                t0 = g.p.clock()
                g.go()
                for cmd in ('off',):
                    self.assertEqual(g.p.updater(cmd).returncode, 0)
                g.p.clock(now=t0 + NO_IDLE_S)
                self.assertEqual(g.p.updater('on').returncode, 0)
                if newer:
                    g.p.gh.release('2.340.0', tarball('2.340.0'), latest=True, published=iso(t0 - 3 * DAY))
                    g.p.record('2.340.0', digest(40))
                    g.p.curl['served'] = g.p.curl['served'] + [digest(40)]
                now = g.p.clock()
                r = g.go()
                if newer:
                    self.assertEqual(g.fam()['due'], {'version': '2.340.0', 'since': now})
                    self.assertEqual(g.held('NO IDLE'), [], r.stdout[-3000:])
                    self.assertIn(WAITS, r.stdout)
                else:
                    self.assertEqual(g.fam()['due'], {'version': V, 'since': t0})
                    self.assertEqual(len(g.held('NO IDLE')), 1, r.stdout[-3000:])

    def test_a_pass_while_a_cut_switch_waits_exits_1_and_one_with_no_journal_exits_0(self):
        """E-11: a due release on a busy pool keeps no journal: exit 0 "waits for idle". A CUT switch (killed right
        after its rename) whose RECOVER waits for idle keeps its journal: exit 1, and no second window."""
        g = G(self, hz=BUSY)
        self.assertIn(WAITS, g.go().stdout)
        c = cut(self, 'up', ('journal:renamed', 'kill'))      # a switch cut right after its rename
        c.p.curl['healthz'] = BUSY
        os.makedirs(Pool.STATE, mode=0o700, exist_ok=True)
        c.p.write(STATE, json.dumps({'format': 1, 'on': True, 'families': {}}) + '\n', 0o600)
        r = c.p.updater('pass')
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertIn('the switch waits for idle', r.stdout)
        self.assertEqual(c.p.window()[:len(c.cut)], c.cut, 'the journal stays open')
        self.assertEqual(c.p.closed(), [], 'no second window')


@needs_container
class TheTwoLevels(unittest.TestCase):
    def test_a_held_disk_is_cleared_at_10_percent_free_and_due_goes_on(self):
        """THE TWO LEVELS (i), before the facts: DISK held, df exactly 10 % free -> cleared in that pass, and DUE goes
        on to the switch (busy here: it waits for idle). The control: 10 % less 1 KiB -> DISK stays, DUE held at step
        2, no window."""
        for avail, cleared in ((BIG // 10, True), (BIG // 10 - 1, False)):
            with self.subTest(avail=avail):
                g = G(self, hz=BUSY, family={'stops': [stop('DISK', text='low')]})
                g.p.disk(BIG, avail)
                r = g.go()
                self.assertEqual(g.held('DISK') == [], cleared, r.stdout[-3000:])
                if cleared:
                    self.assertIn('runner-updater: pass: STOP DISK is cleared', r.stdout)
                    self.assertIn(WAITS, r.stdout)
                else:
                    self.assertIn(NOT + 'STOP DISK (no runner version)', r.stdout)
                    self.assertNotIn('pool-image.sh up --unattended', r.stdout)

    def test_disk_is_raised_only_when_a_release_is_due(self):
        """E-9 + r2 FOLD: df 10 % less 1 KiB and a due release: STOP DISK held (its text the free and the size, its
        hand line names /home/RUN_USER), no window, exit 0; exactly 10 %: the switch goes on (up's own check passes:
        one disk_ok). The control: the same disk with no release due (it is younger than 2 days): no DISK."""
        for avail, age, held in ((BIG // 10 - 1, 3 * DAY, True), (BIG // 10, 3 * DAY, False),
                                 (BIG // 10 - 1, DAY, False)):
            with self.subTest(avail=avail, age=age):
                g = G(self, age=age)
                g.p.disk(BIG, avail)
                r = g.go()
                d = g.held('DISK')
                self.assertEqual(len(d), 1 if held else 0, r.stdout[-3000:])
                if held:
                    self.assertIn('%d KiB free of %d' % (avail, BIG), d[0]['detail']['text'])
                    self.assertIn('free disk on /home/root', d[0]['detail']['hand'])
                    self.assertEqual(g.ups(), [])
                    self.assertIn('runner-updater: pass: hz-docker holds STOP DISK: ', r.stdout)
                elif age == 3 * DAY:
                    self.assertEqual(g.fam()['candidate']['version'], V, r.stdout[-3000:])

    def test_a_held_no_idle_ends_when_the_pool_runs_its_version_or_has_a_candidate(self):
        """THE TWO LEVELS (ii), before the facts: NO IDLE of V held; config.toml on V's image and runscaler restarted
        after that install (a hand switch: RUN_USER's record of the running image names V) -> gone in that pass, and DUE
        says "not newer". A candidate -> gone too. The control: the pool still on the older image -> it stays, and DUE
        holds at step 2. (An install with no restart after it: the next cell.)"""
        ni = stop('NO IDLE', V, text='3 days', digest=NEW, hand='runner-updater switch-now hz-docker')
        for why in ('the pool runs V', 'a candidate', 'an older image'):
            with self.subTest(why):
                fam = {'stops': [ni]}
                if why == 'a candidate':
                    fam['candidate'] = {'version': '2.338.9', 'lines': {MAIN: ref(OLD), SMALL: ref(OLD)},
                                        'closed_at': 1761955200}
                g = G(self, hz=BUSY, family=fam)
                if why == 'the pool runs V':
                    cfg = g.p.rpath('config.toml')
                    g.p.write(cfg, g.p.config().replace(ref(OLD), ref(NEW)), 0o600)
                    g.p.clock(plus=600)
                    g.p.act('restart')                      # the fake clock: a start after the install's second
                r = g.go()
                self.assertEqual(g.held('NO IDLE') == [], why != 'an older image', r.stdout[-3000:])
                if why == 'the pool runs V':
                    self.assertIn(NOT + 'release v%s is not newer than its runner %s' % (V, V), r.stdout)
                if why == 'an older image':
                    self.assertIn(NOT + 'STOP NO IDLE (runner %s)' % V, r.stdout)

    def test_a_held_no_idle_stays_until_runscaler_restarts_into_v(self):
        """B4a fix 1 (Codex r1 F1): NO IDLE of V held by real busy passes, no candidate; then a person's attended
        `pool-image.sh up V` (README "A new runner release", step 2, NO IDLE's hand path) cut between its install of
        config.toml (V's image) and its restart: the runscaler that runs started before that install, so the pool still
        runs the image before (config.toml's install counts nothing until a restart). The next pass keeps NO IDLE (its
        line says why), `due` {V, since} as it was, and it stops and starts nothing; DUE holds at step 2. So does a
        runscaler stopped after that install (no process: the safe side). The control: the same, then runscaler
        restarted after the install: that pass drops NO IDLE (DUE: not newer)."""
        for after in ('the install alone', 'runscaler stopped', 'control: restarted'):
            with self.subTest(after):
                restart = after.startswith('control')
                g = G(self, hz=BUSY)
                g.p.docker['versions'] = {ref(OLD): CUR + '\n', ref(NEW): V + '\n'}
                t0 = g.p.clock()
                g.go()
                g.p.clock(now=t0 + NO_IDLE_S)
                r = g.go()
                self.assertEqual(len(g.held('NO IDLE')), 1, r.stdout[-3000:])
                self.assertIsNone(g.fam().get('candidate'))
                g.p.hooks(('mv-done:config.toml', 'kill'))          # cut right after its install, before its restart
                r = g.p.unattended('up', V, prefix=())
                self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
                g.p.hooks()
                self.assertIn('== 03-runscaler.sh real %s --image-only' % NEW, r.stdout)
                self.assertEqual(g.p.images(), [ref(NEW)] * 2)
                self.assertGreaterEqual(int(os.stat(g.p.rpath('config.toml')).st_mtime), g.p.unit_now()['start'],
                                        'the install came after the start of the runscaler that runs')
                if restart:
                    g.p.clock(plus=600)
                    g.p.act('restart')                      # the fake clock: a start after the install's second
                if after == 'runscaler stopped':
                    g.p.act('stop')                         # a person's plain stop: systemd shows no process
                g.p.clock(plus=600)
                g.p.write(g.p.path('logs', 'systemctl.log'), '')
                r = g.go()
                self.assertEqual((len(g.calls('stop')), len(g.calls('start')), len(g.calls('restart'))), (0, 0, 0))
                if restart:
                    self.assertEqual(g.held('NO IDLE'), [], r.stdout[-3000:])
                    self.assertIn('runner-updater: pass: STOP NO IDLE (runner %s) is gone: ' % V, r.stdout)
                    self.assertIn(NOT + 'release v%s is not newer than its runner %s' % (V, V), r.stdout)
                    continue
                self.assertEqual(len(g.held('NO IDLE')), 1, r.stdout[-3000:])
                self.assertEqual(g.fam()['due'], {'version': V, 'since': t0})
                self.assertIn('runner-updater: pass: STOP NO IDLE (runner %s) stays: config.toml names runner %s\'s '
                              'image, but runscaler has not started since its install (%s' % (
                                  V, V, 'no runscaler process' if after == 'runscaler stopped' else 'runscaler pid '),
                              r.stdout)
                self.assertIn(NOT + 'STOP NO IDLE (runner %s)' % V, r.stdout)
                self.assertEqual(g.ups(), [])

    def test_a_start_in_the_install_s_own_second_keeps_no_idle(self):
        """B4b item 9 (B4a review r2, Opus F1): the level's start-versus-install compare at its boundary. NO IDLE of V
        held by real busy passes; a person's attended `pool-image.sh up V` cut right after its install; runscaler's start
        planted at config.toml's install second: equal proves nothing (core.jq's "equal is NOT proven"): NO IDLE stays,
        and the line says why. The control: the start one second later drops it (DUE: not newer)."""
        for plus in (0, 1):
            with self.subTest(plus=plus):
                g = G(self, hz=BUSY)
                g.p.docker['versions'] = {ref(OLD): CUR + '\n', ref(NEW): V + '\n'}
                t0 = g.p.clock()
                g.go()
                g.p.clock(now=t0 + NO_IDLE_S)
                g.go()
                self.assertEqual(len(g.held('NO IDLE')), 1)
                g.p.curl['healthz'] = IDLE
                g.p.hooks(('mv-done:config.toml', 'kill'))
                r = g.p.unattended('up', V, prefix=())
                self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
                g.p.hooks()
                m = int(os.stat(g.p.rpath('config.toml')).st_mtime)
                g.p.set_unit(start=m + plus)
                g.p.clock(plus=600)
                r = g.go()
                if plus:
                    self.assertEqual(g.held('NO IDLE'), [], r.stdout[-3000:])
                    self.assertIn(NOT + 'release v%s is not newer than its runner %s' % (V, V), r.stdout)
                else:
                    self.assertEqual(len(g.held('NO IDLE')), 1, r.stdout[-3000:])
                    self.assertIn('runner-updater: pass: STOP NO IDLE (runner %s) stays: ' % V, r.stdout)
                    self.assertIn('started at %d; config.toml installed at %d)' % (m, m), r.stdout)


@needs_container
class TheCoreStateCopy(unittest.TestCase):
    """E-14, the pass's side (B3 review r1: the copy has no freshness mark): `up` runs only after a successful run_core
    of the same locked pass, on its result. The small set reads not ready (all counts 0), the main set idle, so only an
    excuse could switch. A copy an older pass left (planted aged), one left while OFF (an OFF pass after it), and an
    aged entry of a set this host does not have each excuse nothing: the pass's own core state names no age, so `up`
    waits for idle. A pass that cannot write the copy (a folder in its place) starts no `up`. The control: the pass's
    own core state (the state's `core`, as earlier passes keep it) names the small set 25 h: excused, switched."""

    def test_only_this_pass_s_core_state_excuses(self):
        for why in ('an older pass', 'an off pass', 'another set', 'the copy cannot be written', 'control: its own'):
            with self.subTest(why):
                g = G(self, hz=healthz(**{SMALL: {'ready': False}}))
                now = g.p.clock()
                aged = {'format': 1, 'not_ready_since': {SMALL: now - 25 * 3600}}
                st = json.loads(g.p.read(STATE))
                if why in ('an older pass', 'an off pass'):
                    g.p.write(CORE_COPY, json.dumps(aged) + '\n', 0o600)
                if why == 'an off pass':
                    st['on'] = False
                    g.put(st)
                    self.assertEqual(g.p.updater('pass').returncode, 0)
                    st['on'] = True
                if why == 'another set':
                    st['core'] = {'format': 1, 'not_ready_since': {'linux-ci-other': now - 25 * 3600}}
                if why == 'control: its own':
                    st['core'] = aged
                g.put(st)
                if why == 'the copy cannot be written':
                    os.makedirs(CORE_COPY, mode=0o700)
                    r = g.go(rc=1)
                    self.assertIn('cannot copy the core', r.stdout)
                    self.assertEqual(g.ups(), [])
                    continue
                r = g.go()
                if why.startswith('control'):
                    self.assertEqual(g.fam()['candidate']['version'], V, r.stdout[-3000:])
                    self.assertIn('excused from readiness only', r.stdout)
                else:
                    self.assertIn(WAITS, r.stdout)
                    self.assertIn('not ready', r.stdout)
                    self.assertEqual(g.ups(), [])



class Text(unittest.TestCase):
    """The README's switch, as a person reads it (B4a item 12; every sentence a cell can read has a cell here, or in
    the cells named), the service's bound (E-13), and B3 review r1 Opus F1 (B4a item 13 (a)). Runs anywhere."""

    def test_the_readme_s_switch_section_and_its_stops(self):
        text = readme()
        upd = one(section(text, 'The updater: status, on, off, pass, build'))
        for s in ('`hz-docker is due for runner <version>`', '`hz-docker waits for idle (since <date>)`, exit 0',
                  'not ready for 24 hours is excused from readiness only', 'a pass that reads it ready starts it again',
                  'After 3 days of that (from the first pass that found it due, also while the updater was OFF or a '
                  'STOP held the family)', '`STOP NO IDLE` instead, with `runner-updater switch-now hz-docker`',
                  'it holds every later release too', '`STOP DISK`', 'free disk on `/home/<RUN_USER>`',
                  'never in a pass whose RECOVER started runscaler', '`switched hz-docker to <version>`',
                  '`accepted hz-docker`', '`STOP JOBS FAIL ON THE NEW IMAGE`', '`STOP NO EVIDENCE`',
                  'it first clears a `STOP DISK` once 10% of RUN_USER\'s filesystem is free',
                  'a `STOP NO IDLE` once the family has a candidate, or runscaler runs that release (or a newer one): '
                  'config.toml names its image and runscaler started after that file was installed (a hand switch ends '
                  'it too, once its restart is done; an install alone does not)',
                  'After an accept: the candidate is gone and `back` still restores the previous image until 7 days '
                  'after the accept', '`config.toml.prev` stays the rollback\'s config',
                  'the runner release it first found due and when (`due`)',
                  'The pass then holds or clears `STOP POOL DOWN` again, as its last step'):
            self.assertIn(s, upd)
        for s in ('would switch', 'would accept', 'would hold', 'switches nothing', 'takes no action'):
            self.assertNotIn(s, one(text))
        sw = one(section(text, "The updater's switch and rollback"))
        for s in ('`~/.local/state/runner-updater/pass/state.json`', 'RECOVER excuses none', '`--now`',
                  '`idle skipped`', '`--keep-prev`', '`windows/<id>.d/config.toml.backup`',
                  "the registry serves `config.toml.prev`'s image"):
            self.assertIn(s, sw)
        rb = one(section(text, 'The rollback, and what status shows of it'))
        for s in ('`STOP NO IDLE` names `runner-updater switch-now hz-docker`, which switches that release now',
                  'A `STOP NO IDLE` ends when runscaler runs that release: `switch-now`\'s window drops it, and so does a '
                  'release put in by hand at a quiet time', 'the first pass after that restart drops it',
                  'a config.toml installed without that restart (the step cut while it waits) keeps it',
                  '`systemctl --user enable runscaler`, then `systemctl --user restart runscaler` at idle',
                  '`systemctl --user enable --now runscaler`', 'its validate first'):
            self.assertIn(s, rb)
        up = one(section(text, 'Upgrading from a release before this one'))
        self.assertIn('An updater of an earlier release does not read that entry: on such a state every command of it '
                      'prints `WAIT` (exit 4) and changes nothing', up)

    def test_the_unfinished_window_s_backup_is_the_one_its_journal_names(self):
        """13 (a): step 3 names the file the journal's `backup` line names: config.toml.prev of a plain switch, the
        window folder's file of a switch whose journal has `keep-prev` (config.toml.prev is the earlier keep then), and
        of a rollback (the controls: a plain switch and a rollback keep their words)."""
        sec = one(section(readme(), 'An unfinished window the updater cannot end'))
        step3 = sec.split(' 3. ', 1)[1].split(' 4. ', 1)[0]
        for s in ('the file its `backup` line names', '`config.toml.prev` of a switch',
                  '`windows/<id>.d/config.toml.backup` of a switch whose journal has a `keep-prev` line',
                  '`config.toml.prev` is then the earlier keep: leave it as it is',
                  '`windows/<id>.d/config.toml.backup` of a rollback'):
            self.assertIn(s, step3)

    def test_the_install_line_drops_macos_s_extended_attributes(self):
        line = [l for l in readme().splitlines() if 'tar -C linux-docker' in l]
        self.assertEqual(len(line), 1)
        self.assertTrue(line[0].strip().startswith('COPYFILE_DISABLE=1 tar -C linux-docker --no-xattrs -cf - . '), line)

    def test_the_service_names_both_restart_sums(self):
        """E-13: a pass makes at most one restart, RECOVER's or one window's; the service's comment names both."""
        with open(os.path.join(REPO, 'linux-docker', 'config', 'runner-updater.service')) as f:
            svc = one(' '.join(l[2:] if l.startswith('# ') else l for l in f.read().splitlines()))
        for s in ('at most ONE restart of runscaler', "RECOVER's", "OR one window's: R1's rollback or DUE's switch",
                  'about 5310 s', 'TimeoutStartSec=2h'):
            self.assertIn(s, svc)


if __name__ == '__main__':
    unittest.main()
