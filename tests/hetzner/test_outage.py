"""linux-docker/bin/runner-updater's OUTAGE RULE (S2b-3c-1 B1 DECISIONS r4; B2a item 4; operator (1): the unit enabled
means CI on, "else a STOP that says CI is down"): on EVERY pass of RS_USER, ON or OFF, after RECOVER and the apply step,
a PURE LEVEL computed anew by each pass (B2a DECISIONS, review r1: Opus F2, Codex F1) from ONE runner-facts.sh `runs`
(never one `active` read) and the read of the unit AFTER it: the unit enabled and no runscaler RUNS (whenever it
started) -> STOP POOL DOWN in the state, held once (no new STOP each pass), its text naming the open window journal's
last line when there is one, else what the pass saw; else (a runscaler RUNS, whenever it started, or the unit not
enabled) -> POOL DOWN cleared; the unit enabled and a runscaler that RUNS and started after config.toml's install
clear a held CI DISABLED too (the plan's CORRECTION: it is a rollback's only line that its TARGET does not run yet).
What a journal line said is text for the person, never the guarantee. (Named for its CI part, test_[o-q][!n]*.py:
.github/workflows/release-check.yml.)

- Every way CI is down: an open journal with the enabled unit down (RECOVER exit 5: Codex r4 F1's input, a switch's
  comment-edited TARGET that does not validate, with its RECOVER cut between `hand-change` and its STOP; Codex r4 F3's
  input, the older runscaler crashing during RECOVER's idle pair); `up --unattended` exiting 3 on an enabled unit that
  is down; a crash after RECOVER closed.
- The controls: runscaler RUNS -> no POOL DOWN, and a held one cleared; the unit not enabled -> no POOL DOWN (CI
  DISABLED's rule: a person's); a crash loop (active for 1 s of each 31) never clears it, a pass at every phase
  (Opus r3 F1); a CI DISABLED is cleared only with the unit enabled; a runscaler older than a hand-installed config.toml
  that serves is CI up: no POOL DOWN is raised, and a held one is cleared (B2a DECISIONS: the install boundary proves
  which file a process runs, never whether CI is up).
- The pure level (B2a review r1): a person's `disable --now` during the RUNS pair raises nothing (the unit read after
  it decides); a held POOL DOWN is cleared once the unit is not enabled, ON and OFF; CI DISABLED is NOT cleared by a
  runscaler that started at or before config.toml's install (a target-old rollback, then a person's `enable` without
  --now). POOL DOWN's text says a run ends the journal only when one can: a journal no run of the updater ends names
  README's section (Opus F4).
Every cell runs the real scripts (support.Pool, a throwaway container, a fake clock) and the updater as RS_USER; no
cell asserts a time it waited.
"""
import json
import os
import unittest

from tests.hetzner.support import Pool, needs_container
from tests.hetzner.test_apply import README_LINE, C, lines_of
from tests.hetzner.test_recover import Rec, cut
from tests.hetzner.test_unattended import NONAPI, Rig, keys

STATEDIR = Pool.STATE
STATE = os.path.join(STATEDIR, 'state.json')
WINDOW = os.path.join(STATEDIR, 'window')
WINDOWS = os.path.join(STATEDIR, 'windows')
FAM = 'hz-docker'


def put(g, on=False, stops=()):
    os.makedirs(STATEDIR, mode=0o700, exist_ok=True)
    g.p.write(STATE, json.dumps({'format': 1, 'on': on, 'families': {FAM: {'stops': list(stops)}}}) + '\n', 0o600)


def held(g, name='POOL DOWN'):
    """The state's held STOPs of NAME (their detail texts)."""
    st = json.loads(g.p.read(STATE))
    return [(s.get('detail') or {}).get('text', '') for s in st['families'].get(FAM, {}).get('stops', [])
            if s['stop'] == name]


def stopj(name, text='planted'):
    return {'family': FAM, 'stop': name, 'version': None, 'user': None, 'detail': {'text': text}}


def pass_(t, g, rc=0):
    r = g.p.updater('pass')
    t.assertEqual(r.returncode, rc, r.stdout[-4000:] + r.stderr)
    return r


@needs_container
class EveryWayCiIsDown(unittest.TestCase):
    """The rule's inputs (B1 DECISIONS r4): each leaves the enabled unit down; each pass that follows holds ONE STOP
    POOL DOWN that says CI is down (the second pass writes no second one)."""

    def test_an_open_journal_with_the_enabled_unit_down(self):
        """Codex r4 F1's input, from B1's real cuts: a switch cut after `stopped`; a person adds a comment to the
        TARGET; its validate is NON-API; RECOVER is cut right after its `hand-change`, before its STOP (rc_dangling then
        gives a HAND CHANGE that says nothing of CI). Each pass: RECOVER exit 5, the journal open, and POOL DOWN, its
        text naming the journal's last line."""
        g = cut(self, 'up', ('journal:stopped', 'kill'))
        g.p.write(g.p.rpath('config.toml'), g.p.config() + '# a comment\n', 0o600)
        g.p.runner = NONAPI
        g.p.hooks(('journal:hand-change', 'kill'))
        Rec(self, g).run(-9)
        g.p.hooks()
        put(g)
        for n in (1, 2):
            r = pass_(self, g, rc=1)
            last = g.p.window()[-1]
            self.assertNotEqual(keys(g.p.window())[-1], 'closed')
            down = held(g)
            self.assertEqual(len(down), 1, (n, down))
            self.assertIn('CI is down', down[0])
            if n == 1:
                self.assertIn(last[:60], down[0], 'the POOL DOWN does not name the open journal\'s last line')
            self.assertIn('STOP POOL DOWN', r.stdout)
            self.assertFalse(g.p.unit_now()['active'])

    def test_the_older_runscaler_crashes_during_recover_s_idle_pair(self):
        """Codex r4 F3's input: a switch cut after `renamed` (the older runscaler runs the file before); during
        RECOVER's idle pair it crashes after the first /healthz answer: not idle, RECOVER exit 5 ("the switch waits for
        idle"), the unit enabled and down: POOL DOWN. The control: it keeps running and busy: no POOL DOWN."""
        for crash in (True, False):
            with self.subTest(crash=crash):
                g = cut(self, 'up', ('journal:renamed', 'kill'))
                g.p.curl['healthz'] = g.p.curl['busy']
                if crash:
                    g.p.hooks(('healthz-read', 'crash'))
                put(g)
                r = pass_(self, g, rc=1)
                self.assertIn('the switch waits for idle', r.stdout)
                down = held(g)
                if not crash:
                    self.assertEqual(down, [], r.stdout[-3000:])
                    continue
                self.assertEqual(len(down), 1, r.stdout[-3000:])
                self.assertIn('CI is down', down[0])
                # B2a review r1, Opus F4's control: a journal RECOVER keeps open (it waits for idle) is one the next
                # run's RECOVER tries again: no README section
                self.assertIn("the next run's RECOVER tries again", down[0])
                self.assertNotIn(README_LINE, down[0])

    def test_up_exiting_3_on_an_enabled_unit_that_is_down(self):
        """START STATE not met (the unit enabled, stopped by a person's plain `systemctl --user stop`): `up
        --unattended` exits 3 and keeps no journal. The pass: POOL DOWN, its text what the pass saw (the unit's state).
        The control: the unit active: exit 3 is not now (not idle), no POOL DOWN."""
        for down in (True, False):
            with self.subTest(down=down):
                g = Rig(self)
                if down:
                    g.p.set_unit(active=False)
                else:
                    g.p.curl['healthz'] = g.p.curl['busy']
                self.assertEqual(g.up().returncode, 3)
                self.assertIsNone(g.p.window())
                put(g)
                pass_(self, g)
                d = held(g)
                if not down:
                    self.assertEqual(d, [])
                    continue
                self.assertEqual(len(d), 1)
                self.assertIn('CI is down', d[0])
                self.assertIn('inactive', d[0])

    def test_a_crash_after_recover_closed(self):
        """RECOVER ends a cut switch (it starts runscaler on the TARGET: closed target-running): no POOL DOWN; then
        runner-start crash-loops: the next pass holds POOL DOWN."""
        g = cut(self, 'up', ('journal:stopped', 'kill'))
        put(g)
        pass_(self, g)
        self.assertIsNone(g.p.window())
        self.assertEqual(held(g), [])
        g.p.set_unit(runner='crash')
        pass_(self, g)
        self.assertEqual(len(held(g)), 1)


@needs_container
class Controls(unittest.TestCase):
    def test_runs_clears_and_a_crash_loop_never_does(self):
        """A held POOL DOWN; runner-start crash-loops (active 1 s of each 31, a fresh ActiveEnterTimestamp each
        time, no /healthz): a pass at each phase, the active second too, keeps it (Opus r3 F1: never one active read).
        Then it serves: the next pass clears it (r2 Opus F2). And a pass ON clears and raises too."""
        g = Rig(self)
        put(g, stops=[stopj('POOL DOWN', 'held')])
        g.p.set_unit(runner='crash', start=g.p.clock())
        for phase in (0, 10, 20, 31):
            g.p.clock(now=g.p.unit_now()['start'] + phase)
            pass_(self, g)
            self.assertEqual(held(g), ['held'], 'phase %d cleared POOL DOWN' % phase)
        g.p.set_unit(runner='serves')
        r = pass_(self, g)
        self.assertEqual(held(g), [], r.stdout[-2000:])
        self.assertIn('STOP POOL DOWN is cleared', r.stdout)

    def test_runs_raises_nothing_and_on_too(self):
        for on in (False, True):
            with self.subTest(on=on):
                g = Rig(self)
                put(g, on=on)
                pass_(self, g)
                self.assertEqual(held(g), [])

    def test_the_unit_not_enabled_is_no_pool_down(self):
        """A person's `systemctl --user disable --now runscaler`: CI is off by hand: no POOL DOWN; a held CI DISABLED
        stays (its clear needs the unit enabled). The control: enabled and down: POOL DOWN."""
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                g = Rig(self)
                put(g, stops=[stopj('CI DISABLED', 'held')])
                g.p.set_unit(active=False, enabled=enabled)
                pass_(self, g)
                self.assertEqual(len(held(g)), 1 if enabled else 0)
                self.assertEqual(held(g, 'CI DISABLED'), ['held'])

    def test_ci_disabled_is_cleared_by_runs_with_the_unit_enabled(self):
        """r3 Opus F1: CI DISABLED's clear also needs UnitFileState enabled: RUNS and enabled -> cleared; RUNS and
        not enabled (a `disable` without --now) -> kept."""
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                g = Rig(self)
                put(g, stops=[stopj('CI DISABLED', 'held')])
                g.p.set_unit(enabled=enabled)
                pass_(self, g)
                self.assertEqual(held(g, 'CI DISABLED'), [] if enabled else ['held'])

    def test_ci_disabled_s_clear_needs_the_unit_enabled_past_its_install_boundary(self):
        """B2a review r2, Codex F2 (B2a CLOSED): the cell that ISOLATES the `enabled` check of CI DISABLED's clear.
        Both STOPs held (so the rule reads past its first-read shortcut), a runscaler that RUNS and started AFTER
        config.toml's install (the install boundary passes), and a person's `disable` without --now: POOL DOWN is
        cleared (CI is off by hand, not down) and CI DISABLED is KEPT. The control: the same unit enabled (no change of
        process or config): both cleared."""
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                g = Rig(self)
                self.assertGreater(g.p.unit_now()['start'], int(os.stat(g.p.rpath('config.toml')).st_mtime),
                                   'the premise: the process started after the install')
                put(g, stops=[stopj('CI DISABLED', 'held'), stopj('POOL DOWN', 'held')])
                g.p.set_unit(enabled=enabled)
                r = pass_(self, g)
                self.assertEqual(held(g), [], r.stdout[-2500:])
                self.assertEqual(held(g, 'CI DISABLED'), [] if enabled else ['held'], r.stdout[-2500:])
                self.assertTrue(g.p.unit_now()['active'], 'the premise: the process still runs')

    def test_an_older_runscaler_that_serves_a_hand_installed_config_is_ci_up(self):
        """A person's `03-runscaler.sh real` after a pool.env change installs config.toml under the running process
        (it restarts nothing: PLAN D2): that process serves, so CI is up: no POOL DOWN is raised, and a held one is
        cleared (B2a DECISIONS, review r1: a runscaler that RUNS clears it whenever it started; the build's "a held one
        stays" was the known gap). The control: the same with no runscaler: POOL DOWN."""
        for runs in (True, False):
            with self.subTest(runs=runs):
                g = Rig(self)
                hand_install(g)
                if not runs:
                    g.p.set_unit(active=False)
                put(g)
                pass_(self, g)
                self.assertEqual(len(held(g)), 0 if runs else 1)
                if runs:
                    put(g, stops=[stopj('POOL DOWN', 'held')])
                    r = pass_(self, g)
                    self.assertEqual(held(g), [], r.stdout[-2000:])
                    self.assertIn('STOP POOL DOWN is cleared', r.stdout)


def hand_install(g):
    """config.toml installed by hand (one number changed) 5 s after the process that runs started: that process is
    older than the install."""
    cfg = g.p.rpath('config.toml')
    g.p.write(cfg, g.p.config().replace('max-runners = 3\n', 'max-runners = 2\n', 1), 0o600)
    os.utime(cfg, (g.p.clock() + 5, g.p.clock() + 5))
    g.t.assertGreater(int(os.stat(cfg).st_mtime), g.p.unit_now()['start'], 'the premise: the process is older')


def events(g):
    return g.p.read(g.p.path('logs', 'events.log')) or ''


@needs_container
class PureLevel(unittest.TestCase):
    """B2a DECISIONS (review r1: Opus F2, Codex F1): each pass computes THE OUTAGE RULE anew, from the unit read AFTER
    the RUNS check: enabled and no runscaler RUNS (any start) -> POOL DOWN held, once; else (a runscaler RUNS, any
    start, or the unit not enabled) -> POOL DOWN cleared. The unit enabled and a runscaler that RUNS and started after
    config.toml's install clear CI DISABLED (the plan's CORRECTION)."""

    def test_a_person_s_disable_now_during_the_runs_pair_is_no_pool_down(self):
        """Codex F1: the unit enabled and serving, no STOP; a person's `systemctl --user disable --now runscaler`
        right after the pair's first /healthz answer: RUNS fails, but CI is off by hand: no POOL DOWN, ON and OFF, on
        that pass and the next. The control: a crash there with the unit enabled: ONE POOL DOWN, over two passes."""
        for on in (False, True):
            for act, n in (('disable', 0), ('crash', 1)):
                with self.subTest(on=on, act=act):
                    g = Rig(self)
                    put(g, on=on)
                    g.p.hooks(('healthz-read', act))
                    for k in (1, 2):
                        r = pass_(self, g)
                        self.assertEqual(len(held(g)), n, (k, r.stdout[-2500:]))
                    self.assertIn('hook healthz-read: ' + act, events(g), 'the premise: the hook fired')
                    self.assertEqual(g.p.unit_now()['enabled'], act != 'disable')

    def test_a_person_s_plain_stop_after_the_runs_pair_is_pool_down(self):
        """B2a review r2, Codex F1 (B2a CLOSED): the DECIDING unit read agrees with RUNS (active, the same MainPID as
        RUNS's process; else no runscaler RUNS). A person's plain `systemctl --user stop runscaler` right after RUNS's
        last process read (the hook at the rule's third `systemctl show`: runs' second proc_now) and before the deciding
        read: that read shows the unit enabled, inactive, pid 0. The pass holds exactly ONE POOL DOWN (a held one stays,
        none held: one raised), and a held CI DISABLED is not cleared by the process that is gone, ON and OFF; so for an
        independent restart there (another MainPID: a process RUNS did not prove). The controls: no stop (the same
        process serves): a held POOL DOWN is cleared; a `disable --now` there instead: no POOL DOWN (off by hand)."""
        for on, act, start in ((False, 'stop', 'both'), (True, 'stop', 'both'), (False, 'stop', 'ci'),
                               (True, 'stop', 'ci'), (False, 'restart', 'both'), (False, None, 'both'),
                               (False, 'disable', 'both')):
            with self.subTest(on=on, act=act, start=start):
                g = Rig(self)
                put(g, on=on, stops=[stopj('CI DISABLED', 'held')] + ([stopj('POOL DOWN', 'held')]
                                                                       if start == 'both' else []))
                if act:
                    g.p.count_shows()
                    g.p.hooks(('systemctl:show-3', act))
                r = pass_(self, g)
                if act:
                    self.assertIn('hook systemctl:show-3: ' + act, events(g), 'the premise: the hook fired')
                down = held(g)
                if act in ('stop', 'restart'):
                    self.assertEqual(len(down), 1, r.stdout[-2500:])
                    self.assertEqual(held(g, 'CI DISABLED'), ['held'], r.stdout[-2500:])
                    self.assertEqual(g.p.unit_now()['active'], act == 'restart')
                    if start == 'ci':
                        self.assertIn('CI is down', down[0])
                    continue
                self.assertEqual(down, [], r.stdout[-2500:])
                self.assertEqual(held(g, 'CI DISABLED'), [] if act is None else ['held'], r.stdout[-2500:])

    def test_a_held_pool_down_is_cleared_once_the_unit_is_not_enabled(self):
        """Opus F2: the enabled unit down: a pass holds POOL DOWN; then a person keeps CI off on purpose (`disable
        --now`, operator (1)): the next pass clears it, ON and OFF. The control: the unit still enabled and down: the
        one POOL DOWN stays."""
        for on in (False, True):
            for disable in (True, False):
                with self.subTest(on=on, disable=disable):
                    g = Rig(self)
                    put(g, on=on)
                    g.p.set_unit(active=False)
                    pass_(self, g)
                    self.assertEqual(len(held(g)), 1, 'the premise: a POOL DOWN held')
                    if disable:
                        g.p.set_unit(enabled=False)
                    r = pass_(self, g)
                    self.assertEqual(len(held(g)), 0 if disable else 1, r.stdout[-2500:])
                    if disable:
                        self.assertIn('STOP POOL DOWN is cleared', r.stdout)

    def test_ci_disabled_is_cleared_only_by_a_runscaler_that_started_after_the_install(self):
        """The plan's CORRECTION (after B2a fix round 1; Opus r1 F6): CI DISABLED is cleared only by the unit enabled
        AND a runscaler that RUNS and started after config.toml's install (its install time read after the RUNS check:
        the safe direction). A rollback closed `target-old` (a person's `disable` without --now: the older runscaler
        serves the candidate's image) holds CI DISABLED as the only line that says its TARGET does not run yet; a
        person's `enable` without --now must not clear it. So for an older runscaler with POOL DOWN held too (POOL DOWN,
        a level of any start, is cleared), and for a hand install of config.toml during the RUNS pair. The controls:
        enabled and a runscaler that started after the install: both cleared; not enabled: CI DISABLED stays."""
        for what in ('target-old, then enable', 'an older runscaler', 'a hand install during the pair',
                     'a runscaler after the install', 'not enabled'):
            with self.subTest(what):
                g = Rig(self)
                if what == 'target-old, then enable':
                    hand_install(g)
                    put(g)
                    g.p.write(STATE, json.dumps({'format': 1, 'on': False, 'families': {FAM: {'candidate': C}}}) + '\n',
                              0o600)
                    os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
                    g.p.write(WINDOW, ''.join(l + '\n' for l in lines_of('rollback', 'target-old', stops=(
                        ('CI DISABLED', 'a runscaler that started before its install runs the image before'),))), 0o600)
                    g.p.set_unit(enabled=False)                       # `disable` without --now: the old one runs
                    pass_(self, g)
                    self.assertIsNone(g.p.window(), 'the premise: the journal is applied and archived')
                    self.assertEqual(len(held(g, 'CI DISABLED')), 1, 'the premise: target-old holds CI DISABLED')
                    self.assertEqual(json.loads(g.p.read(STATE))['families'][FAM]['candidate'], C)
                    g.p.set_unit(enabled=True)                        # a person's `enable` without --now
                    before = held(g, 'CI DISABLED')
                    r = pass_(self, g)
                    self.assertEqual(held(g, 'CI DISABLED'), before, r.stdout[-2500:])
                    continue
                if what in ('an older runscaler', 'not enabled'):
                    hand_install(g)
                if what == 'a hand install during the pair':
                    g.p.hooks(('healthz-read', 'hand-file'))
                put(g, stops=[stopj('CI DISABLED', 'held'), stopj('POOL DOWN', 'held')])
                g.p.set_unit(enabled=what != 'not enabled')
                r = pass_(self, g)
                if what == 'a hand install during the pair':
                    self.assertIn('hand install hand-file', events(g), 'the premise: the hook fired')
                self.assertEqual(held(g, 'CI DISABLED'), [] if what == 'a runscaler after the install' else ['held'],
                                 r.stdout[-2500:])
                self.assertEqual(held(g), [], r.stdout[-2500:])

    def test_ci_disabled_s_hand_line_is_its_close_s_class_s(self):
        """S2b-3c-2 E-12 (the r2 FOLD; r1 Codex F5, Opus F9): CI DISABLED's hand line (what status prints after "Next, by
        hand:") is the CLASS's own, runner-facts.sh's ci_hand, the ONE copy pool-image.sh's RECOVER texts read too: a
        rollback closed target-old (an older runscaler still runs the file before its TARGET) names `enable`, then a
        restart at idle; `enable` alone keeps CI DISABLED (the install boundary), and the restart clears it. The
        control: a switch closed target-idle (a person's `disable --now` after its stop) names `enable --now` alone,
        which clears it (the unit enabled, a runscaler started after the install)."""
        hand = {'target-old': 'systemctl --user enable runscaler, then at idle systemctl --user restart runscaler',
                'target-idle': 'systemctl --user enable --now runscaler'}
        for kind, cls in (('rollback', 'target-old'), ('switch', 'target-idle')):
            with self.subTest(cls):
                g = Rig(self)
                hand_install(g)
                put(g)
                g.p.write(STATE, json.dumps({'format': 1, 'on': False, 'families': {FAM: {'candidate': C}}}) + '\n',
                          0o600)
                os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
                g.p.write(WINDOW, ''.join(l + '\n' for l in lines_of(kind, cls, stops=(
                    ('CI DISABLED', 'runscaler is not enabled'),))), 0o600)
                if cls == 'target-old':
                    g.p.set_unit(enabled=False)                  # `disable` without --now: the old one runs
                else:
                    g.p.act('disable')                           # `disable --now`: nothing runs
                pass_(self, g)
                st = json.loads(g.p.read(STATE))['families'][FAM]['stops']
                cd = [s for s in st if s['stop'] == 'CI DISABLED']
                self.assertEqual(len(cd), 1, st)
                self.assertEqual(cd[0]['detail'].get('hand'), hand[cls])
                s = g.p.updater('status')
                self.assertIn('STOP CI DISABLED', s.stdout)
                self.assertIn('Next, by hand: `%s`' % hand[cls], s.stdout)
                if cls == 'target-old':
                    g.p.act('enable')                            # `enable` alone: the older runscaler runs on
                    r = pass_(self, g)
                    self.assertEqual(len(held(g, 'CI DISABLED')), 1, r.stdout[-2500:])
                    g.p.clock(plus=10)
                    g.p.act('restart')                           # the restart at idle: a start after the install
                else:
                    g.p.act('enable')
                    g.p.clock(plus=10)
                    g.p.act('start')                             # `enable --now`
                r = pass_(self, g)
                self.assertEqual(held(g, 'CI DISABLED'), [], r.stdout[-2500:])

    def test_pool_down_s_text_names_readme_when_no_run_ends_the_journal(self):
        """Opus F4 (B2a review r1): POOL DOWN's text promises that a run ends the window journal only when one can: a
        journal RECOVER cannot read (exit 6), and a closed one the apply step cannot read (a switch closed
        target-failed, a class only a rollback has), name README's section "An unfinished window the updater cannot
        end", never "RECOVER ends it". The control: a journal RECOVER keeps open (EveryWayCiIsDown, the older
        runscaler's crash): the next run's RECOVER tries again, no README section."""
        wid = '20261106010000-4242'
        for what, text in (('RECOVER cannot read it', 'window %s\na line no pattern reads\n' % wid),
                           ('the apply step cannot read it', ''.join(l + '\n' for l in lines_of('switch',
                                                                                              'target-failed')))):
            with self.subTest(what):
                g = Rig(self)
                put(g)
                os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
                g.p.write(WINDOW, text, 0o600)
                g.p.set_unit(active=False)
                r = pass_(self, g, rc=1)
                self.assertIn(README_LINE, r.stdout)       # the premise: the pass's own STOP names it
                down = held(g)
                self.assertEqual(len(down), 1, r.stdout[-2500:])
                self.assertIn(README_LINE, down[0])
                self.assertNotIn('ends it', down[0])
                self.assertEqual(g.p.read(WINDOW), text, 'the journal changed')


if __name__ == '__main__':
    unittest.main()
