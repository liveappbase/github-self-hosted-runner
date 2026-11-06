"""linux-docker/bin/runner-updater's OUTAGE RULE (S2b-3c-1 B1 DECISIONS r4; B2a item 4; operator (1): the unit enabled
means CI on, "else a STOP that says CI is down"): on EVERY pass of RS_USER, ON or OFF, after RECOVER and the apply step,
ONE read of the unit and ONE runner-facts.sh `runs` (never one `active` read): the unit enabled and no runscaler RUNS
-> STOP POOL DOWN in the state, held once (no new STOP each pass), its text naming the open window journal's last line
when there is one, else what the pass saw; a pass that sees RUNS since config.toml's install clears it, and a held CI
DISABLED too when the unit is enabled. It is level-triggered: what a journal line said is text for the person, never
the guarantee. (Named for its CI part, test_[k-q]*.py: .github/workflows/release-check.yml.)

- Every way CI is down: an open journal with the enabled unit down (RECOVER exit 5: Codex r4 F1's input, a switch's
  comment-edited TARGET that does not validate, with its RECOVER cut between `hand-change` and its STOP; Codex r4 F3's
  input, the older runscaler crashing during RECOVER's idle pair); `up --unattended` exiting 3 on an enabled unit that
  is down; a crash after RECOVER closed.
- The controls: runscaler RUNS -> no POOL DOWN, and a held one cleared; the unit not enabled -> no POOL DOWN (CI
  DISABLED's rule: a person's); a crash loop (active for 1 s of each 31) never clears it, a pass at every phase
  (Opus r3 F1); a CI DISABLED is cleared only with the unit enabled; a runscaler older than a hand-installed config.toml
  that serves is CI up: no POOL DOWN is raised (and a held one stays: it is not RUNS since the install).
Every cell runs the real scripts (support.Pool, a throwaway container, a fake clock) and the updater as RS_USER; no
cell asserts a time it waited.
"""
import json
import os
import unittest

from tests.hetzner.support import Pool, needs_container
from tests.hetzner.test_recover import Rec, cut
from tests.hetzner.test_unattended import NONAPI, Rig, keys

STATEDIR = Pool.STATE
STATE = os.path.join(STATEDIR, 'state.json')
WINDOW = os.path.join(STATEDIR, 'window')
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

    def test_an_older_runscaler_that_serves_a_hand_installed_config_is_ci_up(self):
        """A person's `03-runscaler.sh real` after a pool.env change installs config.toml under the running process
        (it restarts nothing: PLAN D2): that process serves, so CI is up: no POOL DOWN is raised. A held one stays (it
        is cleared only by a runscaler that started after config.toml's install). The control: the same with no
        runscaler: POOL DOWN."""
        for runs in (True, False):
            with self.subTest(runs=runs):
                g = Rig(self)
                cfg = g.p.rpath('config.toml')
                g.p.write(cfg, g.p.config().replace('max-runners = 3\n', 'max-runners = 2\n', 1), 0o600)
                os.utime(cfg, (g.p.clock() + 5, g.p.clock() + 5))
                if not runs:
                    g.p.set_unit(active=False)
                put(g)
                pass_(self, g)
                self.assertEqual(len(held(g)), 0 if runs else 1)
                if runs:
                    put(g, stops=[stopj('POOL DOWN', 'held')])
                    pass_(self, g)
                    self.assertEqual(held(g), ['held'])


if __name__ == '__main__':
    unittest.main()
