"""`runner-updater switch-now hz-docker [VERSION]`, a person's override of operator rule (2) for ONE window (S2b-3c-2
B4b; the slice plan's E-7, its r2 FOLD and the r3 FOLD): no idle pair (the restart's drain lets running jobs finish),
never from a pass. RECOVER first; OFF: REFUSE. (Named for its CI part, test_s*.py:
.github/workflows/release-check.yml.)

- (a) a SWITCH journal RECOVER keeps open (a cut switch's idle restart waits): `pool-image.sh recover --unattended --now`
  (`idle skipped`, then the restart): "the switch is done" only on a close of CLASS target-running. RECOVER's open for
  another reason (HAND CHANGE): its line, exit 1, nothing restarted. RECOVER FIRST that ended the switch: "done" (or its
  close, when it is not target-running), and no `up` (r2 Opus F4), also when another record could be switched to. A
  RECOVER FIRST that restarted runscaler and left the journal open: no `recover --now` (one restart per run, r3 Opus
  F1), the STOP line, POOL DOWN by THE OUTAGE RULE, exit 1.
- (b) a held NO IDLE of V: `up --unattended V D --now` with the STOP's digest; the close drops NO IDLE (E-8); a VERSION of
  another version: REFUSE (r3 Opus F4 (3)). The window's shortcut (config.toml already runs V's image after a hand
  switch: Opus r1 F3): exit 0, nothing restarted, and the next pass's level drops NO IDLE.
- (c) else rebuild's target with --now (and --keep-prev when an open candidate's lines run): test_command_rebuild.py.
- B4b fix 1 (review r1): (a) with a VERSION that is not the open switch's: REFUSE, nothing restarted, the journal open
  (opus F2; controls: its own VERSION, and none, run `recover --now`). THE SHORTCUT'S RESTART (opus F1, the ruling's
  (i)): NO IDLE of V held, then config.toml put on V's image by hand and never started into (installed after
  runscaler's start), the pool busy: `rebuild` refuses with no "nothing to switch", names switch-now and restarts
  nothing; switch-now's window restarts runscaler ONCE (`idle skipped`), closed target-running, no candidate (a hand
  release is none), NO IDLE dropped, exit 0. The same state with no NO IDLE: (c) restarts it the same way. That
  restart cut after its stop began, the pool busy: the next RECOVER waits for idle, and switch-now's (a) ends it.
- B4b fix 2 (review r2, opus F1 = codex F1): that restart's gate is the process's start alone (at or before the install,
  the updater's rule, ONE copy: runner-facts.sh's unstarted): a person's hand restart after the install, with /healthz
  not answering or listing one set, gets no stop and no start from switch-now, and its `end` line says what is true.
Every cell runs the real scripts (support.Pool, a throwaway container, the fake clock) and the updater as RS_USER.
"""
import json
import os
import unittest

from tests.hetzner.support import Pool, digest, needs_container, ref
from tests.hetzner.test_pass_switch import BUSY, IDLE, NO_IDLE_S, G
from tests.hetzner.test_command_rebuild import C, KEEPP
from tests.hetzner.test_recover import cut, own
from tests.hetzner.test_release_due import FAM, NEW, NOT, OLD, STATE, V, stop
from tests.hetzner.test_switch_flags import installed_unstarted
from tests.hetzner.test_unattended import NONAPI, installed, keys, value
from tests.hetzner.test_unattended import V as UV, NEW as UNEW


def cut_switch(test, hz):
    """A switch cut right after its rename (the TARGET installed, the older runscaler runs the file before), the updater
    ON, no candidate yet; the pool HZ. The logs emptied (the calls counted are the command's)."""
    c = cut(test, 'up', ('journal:renamed', 'kill'))
    c.p.curl['healthz'] = hz
    os.makedirs(Pool.STATE, mode=0o700, exist_ok=True)
    c.p.write(STATE, json.dumps({'format': 1, 'on': True, 'families': {}}) + '\n', 0o600)
    return c


def calls(c, verb):
    return [l for l in c.p.lines('systemctl') if l.split(' ')[1:2] == [verb]]


def fam(c):
    return json.loads(c.p.read(STATE))['families'].get(FAM, {})


@needs_container
class ACutSwitch(unittest.TestCase):
    def test_a_cut_switch_that_waits_for_idle_restarts_now(self):
        """(a): the pool busy: RECOVER FIRST waits (no restart); switch-now runs `recover --unattended --now`: `idle
        skipped`, one stop, one start, closed target-running, applied: "the switch is done", exit 0, the candidate set,
        and no `up`."""
        c = cut_switch(self, BUSY)
        r = c.p.updater('switch-now', FAM)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        (wid, lines), = c.p.closed()
        self.assertEqual(lines[keys(lines).index('idle', keys(lines).index('recover-start'))], 'idle skipped', lines)
        self.assertEqual((len(calls(c, 'stop')), len(calls(c, 'start')), len(calls(c, 'restart'))), (1, 1, 0))
        self.assertIn('pool-image.sh recover --unattended --now', r.stdout)
        self.assertIn('runner-updater: switch-now hz-docker: the switch is done: RECOVER ended its window, and runscaler '
                      'runs %s (the window journal %s)' % (ref(UNEW), wid), r.stdout)
        self.assertNotIn('pool-image.sh up --unattended', r.stdout)
        self.assertEqual(fam(c)['candidate']['version'], UV)

    def test_one_restart_per_run_and_done_only_when_its_target_runs(self):
        """r3 Opus F1 and r2 Opus F4. Rows: (1) the pool IDLE at RECOVER FIRST, whose idle restart starts a runscaler
        that never serves (it hangs): the journal stays open (`pre-close-failure`): exactly one stop and one start in the
        run, no `recover --now` (no `idle skipped`), the STOP line, POOL DOWN raised by THE OUTAGE RULE, exit 1. (2) the
        pool IDLE: RECOVER FIRST closes the switch target-running: "the switch is done", exit 0, no `up` (though RUN_USER
        holds a record (c) could switch to), and THE OUTAGE RULE clears a POOL DOWN held before. (3) a person's
        `disable --now` during RECOVER FIRST's restart: it closes target-idle (CI DISABLED): its close is named, never
        "done", exit 1, no `up`."""
        for row in ('hang', 'done', 'disabled'):
            with self.subTest(row):
                c = cut_switch(self, IDLE)
                if row == 'done':
                    st = json.loads(c.p.read(STATE))
                    st['families'] = {FAM: {'stops': [stop('POOL DOWN', text='planted')]}}
                    c.p.write(STATE, json.dumps(st) + '\n', 0o600)
                c.p.record(UV, digest(43))
                c.p.curl['served'] = c.p.curl['served'] + [digest(43)]
                if row != 'done':
                    c.p.hooks(('systemctl:stop-done', 'hang' if row == 'hang' else 'disable'))
                r = c.p.updater('switch-now', FAM)
                self.assertEqual(r.returncode, 0 if row == 'done' else 1, r.stdout[-4000:] + r.stderr)
                self.assertEqual(len(calls(c, 'stop')), 1, r.stdout[-3000:])
                self.assertEqual(len(calls(c, 'start')), 0 if row == 'disabled' else 1)
                self.assertNotIn('pool-image.sh up --unattended', r.stdout)
                self.assertNotIn('recover --unattended --now', r.stdout)
                if row != 'done':
                    self.assertNotIn('the switch is done', r.stdout)
                pd = [s for s in fam(c).get('stops', []) if s['stop'] == 'POOL DOWN']
                if row == 'hang':
                    lines = c.p.window()
                    self.assertIn('pre-close-failure', keys(lines))
                    self.assertNotIn('skipped', [l.split(' ', 1)[1] for l in lines if l.startswith('idle ')])
                    self.assertEqual(len(pd), 1)
                    self.assertIn("the next run's RECOVER tries again", r.stdout)
                    continue
                (wid, lines), = c.p.closed()
                if row == 'done':
                    self.assertEqual(pd, [], r.stdout[-3000:])
                    self.assertIn('runner-updater: switch-now hz-docker: the switch is done: RECOVER ended its window, '
                                  'and runscaler runs %s (the window journal %s)' % (ref(UNEW), wid), r.stdout)
                else:
                    self.assertIn('runner-updater: switch-now hz-docker: RECOVER ended the window (the window journal %s, '
                                  'switch, closed target-idle; it holds STOP CI DISABLED): runscaler does not run a '
                                  "switch's TARGET" % wid, r.stdout)

    def test_a_version_that_is_not_the_open_switch_s_is_refused(self):
        """B4b fix 1 (review r1, opus F2): the cut switch of UV waits for idle, the pool BUSY: `switch-now hz-docker
        9.9.9` is a REFUSE, exit 1, no `recover --now`, nothing stopped or started, the journal still open, and its line
        names `runner-updater switch-now hz-docker UV`. The controls: UV itself runs `recover --now` (`idle skipped`, one
        stop, one start, exit 0), as no VERSION does (test_a_cut_switch_that_waits_for_idle_restarts_now)."""
        for arg in ('9.9.9', UV):
            with self.subTest(arg):
                c = cut_switch(self, BUSY)
                r = c.p.updater('switch-now', FAM, arg)
                if arg == UV:
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                    self.assertIn('pool-image.sh recover --unattended --now', r.stdout)
                    (wid, lines), = c.p.closed()
                    self.assertEqual(lines[keys(lines).index('idle', keys(lines).index('recover-start'))], 'idle skipped')
                    self.assertEqual((len(calls(c, 'stop')), len(calls(c, 'start'))), (1, 1))
                    continue
                self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
                self.assertIn('runner-updater: REFUSE switch-now hz-docker: ', r.stdout)
                self.assertIn('`runner-updater switch-now hz-docker %s`' % UV, r.stdout)
                self.assertIn('never runner 9.9.9', r.stdout)
                self.assertNotIn('recover --unattended --now', r.stdout)
                self.assertEqual(calls(c, 'stop') + calls(c, 'start') + calls(c, 'restart'), [])
                self.assertEqual(c.p.closed(), [])
                self.assertNotEqual(keys(c.p.window())[-1], 'closed')

    def test_a_cut_shortcut_restart_waits_for_idle_and_switch_now_ends_it(self):
        """B4b fix 1 (opus F1): THE SHORTCUT'S RESTART (a --now window on config.toml that names its digest and never
        ran) cut right after its `stopping` line, the older runscaler still running, the pool BUSY: switch-now's
        RECOVER FIRST keeps it open (it waits for idle: a cut --now switch waits as any other), then (a) `recover --now`
        restarts it once: closed target-running, "the switch is done", exit 0, no candidate (it names no TARGET line:
        no candidate change)."""
        def before(g):
            installed_unstarted(g)
            g.p.curl['healthz'] = BUSY
        c = cut(self, 'up', ('journal:stopping', 'kill'), more=('--now',), before=before)
        os.makedirs(Pool.STATE, mode=0o700, exist_ok=True)
        c.p.write(STATE, json.dumps({'format': 1, 'on': True, 'families': {}}) + '\n', 0o600)
        r = c.p.updater('switch-now', FAM)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertIn('pool-image.sh recover --unattended --now', r.stdout)
        (wid, lines), = c.p.closed()
        self.assertEqual(installed(lines)[2], 'target-running', lines)
        self.assertEqual((len(calls(c, 'stop')), len(calls(c, 'start')), len(calls(c, 'restart'))), (1, 1, 0))
        self.assertIn('runner-updater: switch-now hz-docker: the switch is done: RECOVER ended its window, and runscaler '
                      'runs %s (the window journal %s)' % (ref(UNEW), wid), r.stdout)
        self.assertIsNone(fam(c).get('candidate'))

    def test_a_journal_kept_open_for_another_reason_restarts_nothing(self):
        """E-7 (a), r2 FOLD (Opus r1 F7; B3 review: `recover --now`'s exit 5 never means a wait for idle): the cut
        switch's TARGET with a comment added, its copy's validate NON-API: RECOVER keeps the journal open for HAND
        CHANGE, with --now too: switch-now says the journal stays open, and not for idle, exit 1, nothing stopped or
        started. (The control, a wait for idle: the first cell.)"""
        c = cut_switch(self, BUSY)
        c.p.write(c.p.rpath('config.toml'), c.p.config() + '# a comment\n', 0o600)
        c.p.runner = {'seq': [NONAPI, NONAPI, NONAPI, NONAPI]}
        r = c.p.updater('switch-now', FAM)
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        self.assertIn('pool-image.sh recover --unattended --now', r.stdout)
        self.assertIn('runner-updater: switch-now hz-docker: the window journal stays open, and not for idle', r.stdout)
        self.assertEqual(calls(c, 'stop') + calls(c, 'start') + calls(c, 'restart'), [])
        self.assertIn('hand-change', own(c.p.window()))


@needs_container
class ANoIdle(unittest.TestCase):
    def test_a_held_no_idle_is_switched_now_and_dropped(self):
        """(b): NO IDLE of V by real busy passes (3 days): `switch-now hz-docker W` (W != V) -> REFUSE, no journal; then
        `switch-now hz-docker V` -> ONE window `up --unattended V D --now` with the STOP's digest: `idle skipped`, no
        `keep-prev`, one stop and one start, the candidate V, and the close drops NO IDLE (E-8), exit 0."""
        g = C(self, hz=BUSY)
        t0 = g.p.clock()
        g.go()
        g.p.clock(now=t0 + NO_IDLE_S)
        g.go()
        self.assertEqual(len(g.held('NO IDLE')), 1)
        g.mark()
        r = g.cmd('switch-now', FAM, '2.340.0', rc=1)
        self.assertIn('runner-updater: REFUSE switch-now hz-docker: STOP NO IDLE holds runner %s: switch-now switches '
                      'that release (`runner-updater switch-now hz-docker %s`), never runner 2.340.0' % (V, V), r.stdout)
        g.none(r)
        r = g.cmd('switch-now', FAM, V)
        lines = g.one(r)
        self.assertEqual((value(lines, 'version'), value(lines, 'digest'), value(lines, 'idle')), (V, NEW, 'skipped'))
        self.assertNotIn('keep-prev', keys(lines))
        self.assertEqual(g.held('NO IDLE'), [], r.stdout[-3000:])
        self.assertEqual(g.fam()['candidate']['version'], V)
        self.assertIn('the release of its STOP NO IDLE', r.stdout)

    def test_an_install_with_no_restart_is_restarted_once_and_no_idle_dropped(self):
        """B4b fix 1 (review r1, opus F1: THE INSTALLED-NOT-STARTED DEAD END; the ruling's (i)). NO IDLE of V by real busy
        passes; then config.toml put on V's image (NEW) with no restart (installed after runscaler's start); the pool
        BUSY. The sibling row first: `rebuild hz-docker` REFUSEs with no "nothing to switch" and no "the pool runs",
        names `runner-updater switch-now hz-docker`, and restarts nothing (rebuild never skips idle). Then `switch-now
        hz-docker`: ONE window (`idle skipped`, no backup), exactly one stop and one start, closed target-running, exit
        0, NO IDLE dropped, no candidate (a hand release is none), config.toml.prev as it was; the next pass keeps NO IDLE
        dropped. The control: test_the_window_s_shortcut_after_a_hand_switch (runscaler restarted after the install)."""
        g = C(self, hz=BUSY)
        t0 = g.p.clock()
        g.go()
        g.p.clock(now=t0 + NO_IDLE_S)
        g.go()
        self.assertEqual(len(g.held('NO IDLE')), 1)
        g.p.write(g.p.rpath('config.toml'), g.p.config().replace(ref(OLD), ref(NEW)), 0o600)
        t = g.p.unit_now()['start'] + 1
        os.utime(g.p.rpath('config.toml'), (t, t))
        keep = g.p.read(KEEPP)
        g.p.clock(plus=600)
        g.mark()
        r = g.cmd('rebuild', FAM, rc=1)
        self.assertIn('runner-updater: REFUSE rebuild hz-docker: ', r.stdout)
        self.assertNotIn('nothing to switch', r.stdout)
        self.assertNotIn('the pool runs', r.stdout)
        self.assertIn('`runner-updater switch-now hz-docker`', r.stdout)
        g.none(r)
        r = g.cmd('switch-now', FAM)
        lines = g.one(r)
        self.assertEqual((value(lines, 'version'), value(lines, 'digest'), value(lines, 'idle')), (V, NEW, 'skipped'))
        self.assertNotIn('backup', keys(lines))
        self.assertEqual(installed(lines)[2], 'target-running', lines)
        self.assertEqual(g.held('NO IDLE'), [], r.stdout[-3000:])
        self.assertIsNone(g.fam().get('candidate'))
        self.assertEqual(g.p.read(KEEPP), keep)
        self.assertIn('runner-updater: switch-now hz-docker: switched hz-docker to %s: runscaler restarted into %s, '
                      'which config.toml named already' % (V, ref(NEW)), r.stdout)
        g.p.clock(plus=600)
        r = g.go()
        self.assertEqual(g.held('NO IDLE'), [], r.stdout[-3000:])
        self.assertIn(NOT + 'release v%s is not newer than its runner %s' % (V, V), r.stdout)

    def test_with_no_no_idle_switch_now_c_restarts_an_install_with_no_restart(self):
        """B4b fix 1 (opus F1's state with no STOP NO IDLE: rebuild's line names switch-now there too): config.toml on
        V's image (NEW, RUN_USER's record of V) with no restart, the pool BUSY: switch-now's (c) runs THE SHORTCUT'S
        RESTART: one window, one stop and one start, closed target-running, exit 0."""
        g = C(self, hz=BUSY)
        g.p.write(g.p.rpath('config.toml'), g.p.config().replace(ref(OLD), ref(NEW)), 0o600)
        t = g.p.unit_now()['start'] + 1
        os.utime(g.p.rpath('config.toml'), (t, t))
        g.mark()
        r = g.cmd('switch-now', FAM)
        lines = g.one(r)
        self.assertEqual((value(lines, 'version'), value(lines, 'digest'), value(lines, 'idle')), (V, NEW, 'skipped'))
        self.assertEqual(installed(lines)[2], 'target-running', lines)

    def test_a_hand_restart_after_the_install_is_not_restarted_while_its_health_is_not_proven(self):
        """B4b fix 2 (review r2, opus F1 = codex F1; opus's probe p1.txt, its input): NO IDLE of V by real busy passes;
        config.toml put on V's image (NEW), then a person's hand restart of runscaler (the STOP's own hand line), so a
        runscaler that started AFTER the install runs config.toml; when switch-now runs, its /healthz does not answer (a
        fresh start, not yet serving), or lists one set only. THE SHORTCUT'S RESTART's gate is the process's start alone
        (at or before the install: runner-facts.sh's unstarted, the updater's own rule), so `switch-now hz-docker`
        stops and starts nothing: no `idle skipped`, closed with `end` (its line: runscaler started after the install
        and is not proven to serve yet), no "installed with no restart since" line, NO IDLE still held (the next pass
        decides), exit 1. (The hook makes /healthz answer after a stop, so a restart, were it made, would run.) The
        controls: test_an_install_with_no_restart_is_restarted_once_and_no_idle_dropped (started before the install:
        one stop, one start) and test_the_window_s_shortcut_after_a_hand_switch (/healthz answers: exit 0, 0/0)."""
        for row in ('no answer', 'one set'):
            with self.subTest(row):
                g = C(self, hz=BUSY)
                t0 = g.p.clock()
                g.go()
                g.p.clock(now=t0 + NO_IDLE_S)
                g.go()
                self.assertEqual(len(g.held('NO IDLE')), 1)
                g.p.write(g.p.rpath('config.toml'), g.p.config().replace(ref(OLD), ref(NEW)), 0o600)
                g.p.clock(plus=600)
                g.p.act('restart')
                pid, start = g.p.unit_now()['pid'], g.p.unit_now()['start']
                self.assertGreater(start, int(os.stat(g.p.rpath('config.toml')).st_mtime), 'a start after the install')
                if row == 'no answer':
                    g.p.curl['healthz'] = None
                else:
                    h = json.loads(json.dumps(BUSY))
                    h['scale_sets'] = h['scale_sets'][:1]
                    g.p.curl['healthz'] = h
                g.p.hooks(('systemctl:stop-done', 'busy'))
                g.mark()
                r = g.p.updater('switch-now', FAM)
                self.assertEqual(calls(g, 'stop') + calls(g, 'start') + calls(g, 'restart'), [], r.stdout[-3000:])
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                ws = g.windows()
                self.assertEqual(len(ws), 1, r.stdout[-3000:])
                lines = ws[0]
                self.assertNotIn('idle', keys(lines))
                self.assertNotIn('stopping', keys(lines))
                end = value(lines, 'end') or ''
                self.assertIn('runscaler (%d %d) started after its install' % (pid, start), end, lines)
                self.assertIn('not proven to serve it yet', end)
                self.assertNotIn('installed with no restart since', r.stdout)
                self.assertIn('runner-updater: switch-now hz-docker: the switch window to runner %s closed with no '
                              'switch' % V, r.stdout)
                self.assertEqual(len(g.held('NO IDLE')), 1, r.stdout[-3000:])

    def test_the_window_s_shortcut_after_a_hand_switch(self):
        """Opus r1 F3: NO IDLE of V held, then a person switched by hand (config.toml on V's image, runscaler restarted
        after it): switch-now -> `up`'s shortcut: exit 0, "nothing to switch", no stop or start; the next pass's level
        drops NO IDLE and DUE says not newer."""
        g = C(self, hz=BUSY)
        t0 = g.p.clock()
        g.go()
        g.p.clock(now=t0 + NO_IDLE_S)
        g.go()
        g.p.write(g.p.rpath('config.toml'), g.p.config().replace(ref(OLD), ref(NEW)), 0o600)
        g.p.clock(plus=600)
        g.p.act('restart')
        g.mark()
        r = g.cmd('switch-now', FAM)
        self.assertIn('runner-updater: switch-now hz-docker: nothing to switch: config.toml names runner %s\'s image '
                      'already' % V, r.stdout)
        self.assertEqual(calls(g, 'stop') + calls(g, 'start') + calls(g, 'restart'), [])
        g.p.clock(plus=600)
        r = g.go()
        self.assertEqual(g.held('NO IDLE'), [], r.stdout[-3000:])
        self.assertIn(NOT + 'release v%s is not newer than its runner %s' % (V, V), r.stdout)


if __name__ == '__main__':
    unittest.main()
