"""`runner-updater rebuild hz-docker [VERSION]`, a person's command (S2b-3c-2 B4b; the slice plan's E-6, its r2 FOLD and
the r3 FOLD's THE VERSION OF rebuild AND switch-now): the SWITCH half (this host's build is RUN_USER's): ONE switch
window, `pool-image.sh up --unattended V D [--keep-prev]` with the idle pair, to RUN_USER's build record of (V, this
release's recipe) whose digest is not the one config.toml runs. RECOVER first; OFF: REFUSE; DISK: a REFUSE with its
text, nothing held; never NO IDLE; not idle: exit 5, nothing stopped. (Named for its CI part, test_[c-jv-z]*.py:
.github/workflows/release-check.yml.) Its (c) twin, switch-now with no NO IDLE, shares its version rule: some rows here
run it (test_switch_now.py has switch-now's own).

- THE VERSION: the open candidate's when its lines run (then --keep-prev: config.toml.prev, the `back` config, stays
  byte for byte, and `previous` is kept; a VERSION of another version: REFUSE, no journal); else the version of
  RUN_USER's record of the running image (another VERSION: REFUSE: a newer one is DUE's); else (NO BASELINE) the
  person's VERSION, required, not rejected, with a record. No record of (V, this recipe), or one whose digest
  config.toml runs: REFUSE with RUN_USER's `build V` line (from host.conf's RUN_USER, HOST_IP and SSH_PORT: `ssh -p`,
  B4b fix 1) and the whole next
  command; DUE's NO BASELINE and recipe changed lines name the whole command too.
- E-14 (r3 Opus F3 (b)): rebuild writes the state's `core` to THE CORE STATE COPY before its `up`: a set the passes read
  not ready for 25 h is excused (`idle idle`, the switch); 23 h: exit 5.
- THE OUTAGE RULE as its last step after its window (the r2 FOLD; Opus r1 F1).
Every cell runs the real scripts (support.Pool, a throwaway container, the fake clock) and the updater as RS_USER.
"""
import json
import os
import unittest

from tests.hetzner.support import Pool, digest, healthz, needs_container, ref, sha256_file
from tests.hetzner.test_pass_switch import BIG, BUSY, IDLE, G
from tests.hetzner.test_release_due import CUR, DAY, FAM, MAIN, NEW, NOT, OLD, SMALL, STATE, V, stop
from tests.hetzner.test_unattended import keys, value

D2 = digest(41)          # RUN_USER's new build of V (`build V` again: the (V, recipe) record replaced)
D3 = digest(43)          # RUN_USER's new build of CUR (it replaces the (CUR, recipe) record: NO BASELINE then)
BUILD_LINE = "as root: `ssh -p 22 root@203.0.113.10 '~/bin/runner-updater build %s'`"
KEEPP = os.path.join(Pool.HOME, '.config', 'runner', 'config.toml.prev')


class C(G):
    """test_pass_switch's G (production OLD, RUN_USER's records of CUR on OLD and of V on NEW, the release V due, ON,
    the fake clock), with a person's command and the windows since mark()."""

    def mark(self):
        self.p.write(self.p.path('logs', 'systemctl.log'), '')
        self.n_win = len(self.p.closed())

    def cmd(self, *args, rc=0):
        r = self.p.updater(*args)
        self.t.assertEqual(r.returncode, rc, r.stdout[-5000:] + r.stderr)
        return r

    def windows(self):
        return [l for _, l in self.p.closed()[self.n_win:]]

    def none(self, r):
        """No window: none closed since mark(), none at WINDOW, no stop, start or restart."""
        self.t.assertEqual(self.windows(), [], r.stdout[-3000:])
        self.t.assertIsNone(self.p.window())
        self.t.assertEqual(self.calls('stop') + self.calls('start') + self.calls('restart'), [])

    def prev(self):
        return sha256_file(KEEPP), os.stat(KEEPP).st_mtime_ns

    def one(self, r):
        """ONE window since mark(), closed and archived, one stop and one start: its lines."""
        ws = self.windows()
        self.t.assertEqual(len(ws), 1, r.stdout[-3000:])
        self.t.assertEqual((len(self.calls('stop')), len(self.calls('start')), len(self.calls('restart'))), (1, 1, 0))
        return ws[0]


def opened(test, hz=IDLE):
    """An OPEN candidate whose lines run: a real pass switched the pool to V (NEW), then RUN_USER built V again (D2:
    02-d1.sh's record of (V, this recipe) replaced, so no record names the running image any more)."""
    g = C(test)
    g.go()
    test.assertEqual(g.fam()['candidate']['version'], V)
    g.p.record(V, D2)
    g.p.curl['served'] = g.p.curl['served'] + [D2]
    g.p.curl['healthz'] = hz
    g.p.clock(plus=600)
    g.mark()
    g.prev0 = g.prev()
    g.cand0 = g.fam()['candidate']
    return g


def new_cur(g):
    """RUN_USER builds CUR again: D3 replaces the (CUR, this recipe) record, so the running image (OLD) has none (NO
    BASELINE: the person names CUR)."""
    g.p.record(CUR, D3)
    g.p.curl['served'] = g.p.curl['served'] + [D3]


@needs_container
class TheOpenCandidate(unittest.TestCase):
    def test_a_rebuild_of_the_open_candidate_keeps_the_back_config(self):
        """r2 Codex F2's input (the r3 FOLD's cell): an open candidate V whose lines run, rebuilt by RUN_USER (D2), the
        pool BUSY: `rebuild hz-docker` exits 5 "not now", nothing stopped, no journal; `switch-now hz-docker` -> ONE
        window `--now --keep-prev`: `keep-prev` and `idle skipped` journaled, config.toml.prev byte-equal, the candidate
        {V, D2's lines, a new closed_at}, `previous` kept. The control: the pool IDLE -> `rebuild hz-docker` switches
        with `idle idle` (and --keep-prev: config.toml.prev byte-equal, previous kept)."""
        for busy in (True, False):
            with self.subTest(busy=busy):
                g = opened(self, BUSY if busy else IDLE)
                if busy:
                    r = g.cmd('rebuild', FAM, rc=5)
                    self.assertIn('runner-updater: rebuild hz-docker: not now: ', r.stdout)
                    self.assertIn('`runner-updater switch-now hz-docker %s` now' % V, r.stdout)
                    g.none(r)
                    r = g.cmd('switch-now', FAM)
                else:
                    r = g.cmd('rebuild', FAM)
                lines = g.one(r)
                self.assertEqual((value(lines, 'version'), value(lines, 'digest')), (V, D2))
                self.assertIn('keep-prev', keys(lines))
                self.assertEqual(value(lines, 'idle'), 'skipped' if busy else 'idle')
                self.assertEqual(g.prev(), g.prev0, 'config.toml.prev changed')
                f = g.fam()
                self.assertEqual((f['candidate']['version'], f['candidate']['lines']), (V, {MAIN: ref(D2), SMALL: ref(D2)}))
                self.assertGreater(f['candidate']['closed_at'], g.cand0['closed_at'])
                self.assertEqual(f['previous'], {MAIN: ref(OLD), SMALL: ref(OLD)})
                self.assertIn('switched hz-docker to %s: it runs %s (the window journal ' % (V, ref(D2)), r.stdout)

    def test_a_version_that_is_not_the_one_it_switches_is_refused(self):
        """THE VERSION (r3 Opus F4 (2)): an open candidate V whose lines run: `rebuild hz-docker W` and `switch-now
        hz-docker W` (W != V) -> REFUSE, no journal, config.toml.prev byte-equal. With no candidate and the pool on
        CUR's record: `rebuild hz-docker V` -> REFUSE (a newer release is DUE's). The control: `rebuild hz-docker V`
        of the open candidate runs (busy: exit 5, a wait, not a REFUSE)."""
        g = opened(self, BUSY)
        for c in ('rebuild', 'switch-now'):
            r = g.cmd(c, FAM, '2.340.0', rc=1)
            self.assertIn('runner-updater: REFUSE %s hz-docker: ' % c, r.stdout)
            self.assertIn("one open release per family: hz-docker's open candidate is runner %s, and %s switches only "
                          'it (`runner-updater %s hz-docker %s`), never runner 2.340.0' % (V, c, c, V), r.stdout)
            g.none(r)
            self.assertEqual(g.prev(), g.prev0)
        g.cmd('rebuild', FAM, V, rc=5)
        n = C(self)
        n.mark()
        r = n.cmd('rebuild', FAM, V, rc=1)
        self.assertIn('rebuild switches the version config.toml names, runner %s (' % CUR, r.stdout)
        self.assertIn('never runner %s: a newer release is the pass\'s to switch (DUE)' % V, r.stdout)
        n.none(r)


@needs_container
class NoBaseline(unittest.TestCase):
    def test_after_run_user_built_the_accepted_version_again_the_version_is_the_person_s(self):
        """r3 Opus F4 (1): no candidate, the accepted image NEW of V (back until 7 days); RUN_USER builds V again (D2):
        DUE says NO BASELINE and names `runner-updater rebuild hz-docker <runner version>`; `rebuild hz-docker` -> REFUSE,
        no journal, naming the same; `rebuild hz-docker V`, the pool busy -> exit 5; `switch-now hz-docker` (no
        VERSION) -> REFUSE "nothing waits for idle", no journal; `switch-now hz-docker V` -> ONE window `--now`, no
        `keep-prev`, its backup config.toml.prev; the close: candidate {V, D2}, previous NEW's, back_until null."""
        g = C(self)
        g.go()
        st = json.loads(g.p.read(STATE))
        f = st['families'][FAM]
        f['candidate'], f['back_until'] = None, g.p.clock() + 7 * DAY
        g.put(st)
        g.p.record(V, D2)
        g.p.curl['served'] = g.p.curl['served'] + [D2]
        g.p.curl['healthz'] = BUSY
        g.p.clock(plus=600)
        g.mark()
        nb = '`runner-updater rebuild hz-docker <runner version>` switches it to root\'s build of runner <runner version>'
        r = g.go()
        self.assertIn(NOT + 'STOP NO BASELINE: ', r.stdout)
        self.assertIn(nb, r.stdout)
        r = g.cmd('rebuild', FAM, rc=1)
        self.assertIn('runner-updater: REFUSE rebuild hz-docker: STOP NO BASELINE: ', r.stdout)
        self.assertIn(nb, r.stdout)
        self.assertIn(BUILD_LINE % '<runner version>', r.stdout)
        g.none(r)
        g.cmd('rebuild', FAM, V, rc=5)
        g.none(r)
        r = g.cmd('switch-now', FAM, rc=1)
        self.assertIn('runner-updater: REFUSE switch-now hz-docker: nothing waits for idle: STOP NO BASELINE: ', r.stdout)
        g.none(r)
        r = g.cmd('switch-now', FAM, V)
        lines = g.one(r)
        self.assertNotIn('keep-prev', keys(lines))
        self.assertEqual((value(lines, 'idle'), value(lines, 'backup')), ('skipped', KEEPP))
        f = g.fam()
        self.assertEqual(f['candidate']['lines'], {MAIN: ref(D2), SMALL: ref(D2)})
        self.assertEqual(f['previous'], {MAIN: ref(NEW), SMALL: ref(NEW)})
        self.assertIsNone(f.get('back_until'))

    def test_the_person_s_version_must_not_be_rejected(self):
        """Opus r1 F5: NO BASELINE (no record of the running image) and V rejected: `rebuild hz-docker V` -> REFUSE, no
        journal. The control: V not rejected -> the window runs (idle: switched to V)."""
        for rejected in (True, False):
            with self.subTest(rejected=rejected):
                g = C(self, base=False, family={'rejected': [V]} if rejected else None)
                g.mark()
                if rejected:
                    r = g.cmd('rebuild', FAM, V, rc=1)
                    self.assertIn('runner-updater: REFUSE rebuild hz-docker: runner %s is rejected for hz-docker' % V,
                                  r.stdout)
                    g.none(r)
                    continue
                r = g.cmd('rebuild', FAM, V)
                g.one(r)
                self.assertEqual(g.fam()['candidate']['version'], V)


@needs_container
class TheTarget(unittest.TestCase):
    def test_no_record_for_this_recipe_or_the_running_one_refuses_with_the_build_line(self):
        """Opus r1 F5, F11; r3 Opus F4 (4): the target is RUN_USER's record of (V, this release's recipe). (i) that
        record is the one config.toml runs -> REFUSE, naming RUN_USER's `build CUR` line (host.conf's RUN_USER and
        HOST_IP) and `runner-updater rebuild hz-docker CUR`; (ii) recipe changed: the running image's record and a newer
        one of CUR are of another recipe -> REFUSE "no usable build record", the same lines (DUE's recipe changed line
        names the command with CUR too). The control: RUN_USER builds CUR again (D3: the running image then has no
        record, NO BASELINE) -> `rebuild hz-docker CUR` switches to D3."""
        for row in ('the running record', 'recipe changed', 'control: a new build'):
            with self.subTest(row):
                g = C(self, base=row != 'recipe changed')
                if row == 'recipe changed':
                    g.p.record(CUR, OLD, recipe='ab' * 32)
                    g.p.record(CUR, digest(42), recipe='cd' * 32)
                    self.assertIn('`runner-updater rebuild hz-docker %s` switches it' % CUR, g.go().stdout)
                if row.startswith('control'):
                    new_cur(g)
                g.mark()
                if row.startswith('control'):
                    r = g.cmd('rebuild', FAM, CUR)
                    lines = g.one(r)
                    self.assertEqual((value(lines, 'version'), value(lines, 'digest')), (CUR, D3))
                    continue
                r = g.cmd('rebuild', FAM, rc=1)
                g.none(r)
                self.assertIn(BUILD_LINE % CUR, r.stdout)
                self.assertIn(', then `runner-updater rebuild hz-docker %s`' % CUR, r.stdout)
                self.assertIn('config.toml names RUN_USER\'s build of runner %s for this release\'s image already' % CUR
                              if row == 'the running record' else
                              'no usable build record of runner %s for this release\'s image' % CUR, r.stdout)


@needs_container
class ItsIdlePair(unittest.TestCase):
    def test_rebuild_s_idle_pair_reads_the_core_state_the_passes_grew(self):
        """E-14, r3 Opus F3 (b): an open candidate rebuilt by RUN_USER (D2); the small set not ready (all its counts 0),
        the main set idle; real passes from T0 read it so (the core keeps T0); a copy at the pass's path that names no
        age (left there: rebuild must write its own). At T0 + 25 h `rebuild hz-docker` -> `idle idle`, the switch. The
        control: at T0 + 23 h -> exit 5, not ready, nothing stopped."""
        for hours, ok in ((25, True), (23, False)):
            with self.subTest(hours=hours):
                g = opened(self, healthz(**{SMALL: {'ready': False}}))
                t0 = g.p.clock()
                g.go()
                g.p.clock(now=t0 + 12 * 3600)
                g.go()
                g.p.clock(now=t0 + hours * 3600)
                g.p.write(os.path.join(g.p.STATE, 'pass', 'state.json'), '{"format":1}\n', 0o600)
                g.mark()
                if not ok:
                    r = g.cmd('rebuild', FAM, rc=5)
                    self.assertIn('not ready', r.stdout)
                    g.none(r)
                    continue
                r = g.cmd('rebuild', FAM)
                lines = g.one(r)
                self.assertEqual(value(lines, 'idle'), 'idle')
                self.assertIn('excused from readiness only', r.stdout)


@needs_container
class DiskOffAndOutage(unittest.TestCase):
    def test_disk_and_off_are_a_refuse_and_hold_nothing(self):
        """E-9 + r2 FOLD: df 10 % less 1 KiB -> `rebuild` and `switch-now` REFUSE with DISK's text, no DISK held, no
        journal; the updater OFF -> REFUSE. The control: exactly 10 % -> rebuild switches."""
        for row in ('disk', 'off', 'control'):
            with self.subTest(row):
                g = C(self, family={'stops': []})
                new_cur(g)
                g.p.disk(BIG, BIG // 10 - (1 if row == 'disk' else 0))
                if row == 'off':
                    st = json.loads(g.p.read(STATE))
                    st['on'] = False
                    g.put(st)
                g.mark()
                if row == 'control':
                    g.one(g.cmd('rebuild', FAM, CUR))
                    continue
                for c in ('rebuild', 'switch-now'):
                    r = g.cmd(c, FAM, CUR, rc=1)
                    g.none(r)
                    self.assertEqual(g.held(), [])
                    self.assertIn('runner-updater: REFUSE %s hz-docker: ' % c, r.stdout)
                    self.assertIn('no window: STOP DISK: ' if row == 'disk' else 'the updater is OFF: %s runs only while '
                                  'it is ON' % c, r.stdout)

    def test_the_outage_rule_is_its_last_step(self):
        """Opus r1 F1, the r2 FOLD: the new runscaler never serves (it hangs after the stop): the window journals
        `pre-close-failure` and stays open after its own stop and start: the STOP line, exit 1, one stop and one start,
        and THE OUTAGE RULE holds POOL DOWN naming the journal's last line. The control: the window runs to its end:
        a POOL DOWN held before is cleared."""
        for hang in (True, False):
            with self.subTest(hang=hang):
                g = C(self, family={'stops': [] if hang else [stop('POOL DOWN', text='planted')]})
                new_cur(g)
                if hang:
                    g.p.hooks(('systemctl:stop-done', 'hang'))
                g.mark()
                r = g.cmd('rebuild', FAM, CUR, rc=1 if hang else 0)
                self.assertEqual((len(g.calls('stop')), len(g.calls('start'))), (1, 1))
                pd = g.held('POOL DOWN')
                if hang:
                    self.assertEqual(len(pd), 1, r.stdout[-3000:])
                    self.assertIn('pre-close-failure', pd[0]['detail']['text'])
                    self.assertIn("the next run's RECOVER ends it", r.stdout)
                else:
                    self.assertEqual(pd, [], r.stdout[-3000:])
                    self.assertIn('runner-updater: rebuild hz-docker: STOP POOL DOWN is cleared', r.stdout)


if __name__ == '__main__':
    unittest.main()
