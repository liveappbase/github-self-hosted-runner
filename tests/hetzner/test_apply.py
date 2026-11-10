"""linux-docker/bin/runner-updater's APPLY STEP and RECOVER FIRST (S2b-3c-1 D-b (b)(c), D-f, the r3 FOLD; B2a items 2
and 3): every RS_USER run that takes the lock (a pass, on, off) runs pool-image.sh's RECOVER as its child when a window
journal is at WINDOW, then applies a CLOSED journal by its own lines (THE CLOSE RULE, THE STOP RULE, THE OWN RESTART: one
state write that also sets `last_window`), then archives it to windows/ID. (Named for its CI part, test_[a-b]*.py:
.github/workflows/release-check.yml.)

- BY ITS LINES ONLY (r2 Opus F1, Codex F9): a change of config.toml after `closed` changes nothing the apply step
  decides; the CLASS is the `installed` line's.
- THE CLOSE RULE by kind and CLASS: a switch's target-* sets the candidate (previous = `old` on the TARGET's sets when
  its backup is config.toml.prev), pre/none change nothing (a backup that replaced the keep: previous and back_until
  gone), other holds HAND CHANGE; a rollback's target-running/target-idle clears candidate, previous and back_until (its
  rejection: B2b's hook), target-old keeps the candidate (CI DISABLED), target-failed keeps it (ROLLBACK FAILED, never
  "rolled back"), pre/none change nothing, other keeps it (HAND CHANGE). No `target` line: only its STOPs. A journal
  with no `kind` (cut right after `window`): its `stop` lines held by THE STOP RULE, no candidate change (B2a review r1,
  Opus F1); with no `stop` line, archived only. A CLASS its kind does not have: STOP, nothing written.
- LEGACY journals (r3 FOLD, Codex r3 F2, Opus r3 F10): no `installed` line: `running` after its `target` is
  target-running, a `stop`/`end` before any `rename-start` is pre, anything else a STOP; a rollback with no `why` is a
  person's back with old-version none (the line says so). A closed journal already in windows/ is never applied.
- THE STOP RULE (the Studio's): each STOP name of the journal held once (its last line), replacing the family's held
  one of that name; DISK, untested jq and NO IDLE never held; a close with CLASS target drops the family's JOBS FAIL ON
  THE NEW IMAGE and NO EVIDENCE.
- THE OWN RESTART (r3 FOLD, Codex r3 F7, r2 Codex F13, Opus F11): `restart` = {from, to: running, stopped} only from a
  journal with no `recover-start`, whose `running` started within 20 s of its `starting`, and while the state holds no
  unconsumed one; any other applied journal removes the member.
- `last_window` (r3 Codex F5's first half): a journal whose ID is the state's `last_window` is only archived.
- RECOVER FIRST: its exits 0 (apply), 4 (WAIT: a line, no STOP), 5 (open: nothing else starts), 6 (STOP: README "An
  unfinished window the updater cannot end", nothing written), 1 (REFUSE), any other (a STOP naming the code); a pass,
  on and off run it before ON/OFF is read; a pass makes at most ONE restart of runscaler (D-g).
Every cell runs the real scripts (support.Pool, a throwaway container): a real window, or a journal planted in its
grammar (the apply step reads lines only), and the updater as RS_USER; no cell asserts a time it waited.
"""
import fcntl
import json
import os
import unittest

from tests.hetzner.support import Pool, needs_container, ref
from tests.hetzner.test_recover import cut
from tests.hetzner.test_unattended import NEW, OLD, V, BackRig, Rig, keys, value

STATEDIR = Pool.STATE
STATE = os.path.join(STATEDIR, 'state.json')
WINDOW = os.path.join(STATEDIR, 'window')
WINDOWS = os.path.join(STATEDIR, 'windows')
README_LINE = 'An unfinished window the updater cannot end'
FAM = 'hz-docker'
MAIN, SMALL = 'linux-ci-main', 'linux-ci-small'
R = os.path.join(Pool.HOME, '.config', 'runner')
WID = '20261106010000-4242'
T0 = 1793900000
TL = {MAIN: ref(NEW), SMALL: ref(NEW)}
OLDL = {MAIN: ref(OLD), SMALL: ref(OLD)}
C = {'version': '2.338.0', 'lines': OLDL, 'closed_at': T0 - 86400}     # an open candidate (a rollback's)
PREV = {MAIN: ref('sha256:' + '37' * 32), SMALL: ref('sha256:' + '37' * 32)}


def h(n):
    return ('%02x' % n) * 32


def tline(lines):
    return ' '.join('%s=%s' % kv for kv in lines.items())


def stopj(name, text='planted', version=None):
    return {'family': FAM, 'stop': name, 'version': version, 'user': None, 'detail': {'text': text}}


def lines_of(kind='switch', cls='target-running', wid=WID, target=True, installed=True, prev=None, stops=(),
             recover=False, run_after=1, legacy=False, why='back', end_before_rename=False, stop_before_rename=False):
    """A closed window journal of KIND in pool-image.sh's grammar (its header), closing with CLASS. target: a `target`
    line (else the shortcut's shape: no target, `running`); installed=False: a LEGACY journal (no closing lines but
    `closed`); prev: the switch's `prev` value(s), in order (default config-sha's sha); stops: (NAME, TEXT) lines before
    the closing lines; recover: RECOVER's `recover-start` and its own start; run_after: `running`'s start - `starting`'s
    epoch; why None: no `why` line (a 3b-3 rollback); end_before_rename: a `stop` before any `rename-start` (right
    after its validate); stop_before_rename: the same after its `target` and `backup` lines (a STOP of the backup's
    check); recover: RECOVER's `recover-start` after the window's own `running` (it only closed it)."""
    sw = kind == 'switch'
    tgt = TL if sw else OLDL
    L = ['window ' + wid, 'kind ' + kind]
    if sw:
        L += ['version ' + V, 'digest ' + NEW]
    else:
        L += (['why ' + why] if why else []) + ['verdict none', 'old-version ' + V, 'target-version 2.338.0']
    L += ['process 100 %d' % (T0 - 1000), 'old ' + (ref(OLD) if sw else ref(NEW)), 'config-sha ' + h(1),
          'start-state %d' % T0, 'staged %s/config.%s.toml' % (R, 'staged' if sw else 'rollback'), 'validate pre 1 PASS']
    if end_before_rename:
        L += ['stop %s: %s' % s for s in stops] + (['prev ' + h(1)] if sw and not legacy else [])
        L += [] if legacy else ['installed %s %s %s' % (h(1), h(5), cls)]
        return L + ['closed %d' % (T0 + 9)]
    if not target:   # a shortcut: `up` already names and runs DIGEST's image, `back` already is the backup
        L += ['running 100 %d' % (T0 - 1000)] + ['stop %s: %s' % s for s in stops]
        if not legacy:
            L += (['prev ' + h(1)] if sw else []) + ['installed %s %s %s' % (h(1), h(5), cls)]
        return L + ['closed %d' % (T0 + 9)]
    L += ['staged-sha ' + h(2), 'target ' + tline(tgt), 'target-content ' + h(3)]
    if sw:
        L += ['idle idle']
    L += ['backup ' + (R + '/config.toml.prev' if sw else '%s/%s.d/config.toml.backup' % (WINDOWS, wid))]
    if stop_before_rename:
        L += ['stop %s: %s' % s for s in stops] + (['prev ' + h(1)] if sw and not legacy else [])
        L += [] if legacy else ['installed %s %s %s' % (h(1), h(5), cls)]
        return L + ['closed %d' % (T0 + 9)]
    L += ['rename-start %d' % (T0 + 1), 'renamed %d' % (T0 + 1)]
    L += ['from 100 %d' % (T0 - 1000), 'stopping %d' % (T0 + 2), 'stopped 1234 567 ' + h(4)]
    L += ['starting %d' % (T0 + 3), 'running 101 %d' % (T0 + 3 + run_after)]
    if recover:
        L += ['recover-start %d' % (T0 + 600)]
    L += ['stop %s: %s' % s for s in stops]
    if not legacy:
        if sw:
            L += ['prev ' + p for p in (prev or [h(1)])]
        L += ['installed %s %s %s' % (h(2), h(3), cls)]
    return L + ['closed %d' % (T0 + 9)]


class A:
    """A Pool with no production (nothing runs; the unit not enabled: no outage reading interferes), the updater's
    state ON or OFF with the family FAM, and a journal planted at WINDOW."""

    def __init__(self, test, on=False, fam=None, extra=None):
        self.t = test
        self.p = Pool(test)
        self.p.files()
        os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
        st = {'format': 1, 'on': on, 'families': {FAM: fam} if fam is not None else {}}
        st.update(extra or {})
        self.put(st)

    def put(self, st):
        self.p.write(STATE, json.dumps(st) + '\n', 0o600)

    def state(self):
        return json.loads(self.p.read(STATE))

    def fam(self):
        return self.state()['families'].get(FAM, {})

    def plant(self, lines):
        self.p.write(WINDOW, ''.join(l + '\n' for l in lines), 0o600)
        return lines

    def run(self, cmd='off', rc=0):
        r = self.p.updater(cmd)
        self.t.assertEqual(r.returncode, rc, r.stdout[-4000:] + r.stderr)
        self.r = r
        return r

    def archived(self, lines, wid=WID):
        """The journal is gone from WINDOW and is windows/WID, line for line."""
        self.t.assertFalse(os.path.lexists(WINDOW), 'the journal is still at WINDOW')
        self.t.assertEqual(self.p.read(os.path.join(WINDOWS, wid)), ''.join(l + '\n' for l in lines))

    def held(self):
        return [s['stop'] for s in self.fam().get('stops', [])]


@needs_container
class ByItsLines(unittest.TestCase):
    """r2 Opus F1, r2 Codex F9: a real switch window closes (target-running); before the next run a person changes
    config.toml (one number; `03 real` after a pool.env change). The apply step decides by the journal's lines:
    candidate runner V on the TARGET's lines, closed_at its `closed`, previous the old image, no HAND CHANGE, and
    `last_window` its ID; the journal archived. The control: a journal whose `installed` line names another content
    (other: a person's file found by the closer): no candidate, HAND CHANGE held."""

    def test_a_change_after_closed_changes_nothing_it_decides(self):
        g = Rig(self)
        self.assertEqual(g.up().returncode, 0)
        lines = g.p.window()
        self.assertEqual(keys(lines)[-1], 'closed')
        cfg = g.p.rpath('config.toml')
        g.p.write(cfg, g.p.config().replace('max-runners = 3\n', 'max-runners = 2\n', 1), 0o600)
        r = g.p.updater('off')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        st = json.loads(g.p.read(STATE))
        f = st['families'][FAM]
        self.assertEqual(f.get('candidate'), {'version': V, 'lines': {MAIN: ref(NEW), SMALL: ref(NEW)},
                                              'closed_at': int(value(lines, 'closed'))})
        self.assertEqual(f.get('previous'), {MAIN: ref(OLD), SMALL: ref(OLD)})
        self.assertIsNone(f.get('back_until'))
        self.assertEqual(f.get('stops', []), [])
        self.assertEqual(st['last_window'], value(lines, 'window'))
        self.assertFalse(os.path.lexists(WINDOW))
        self.assertEqual(g.p.read(os.path.join(WINDOWS, value(lines, 'window'))).splitlines(), lines)

    def test_control_an_installed_line_of_another_file(self):
        a = A(self)
        lines = a.plant(lines_of(cls='other', stops=[('HAND CHANGE', 'config.toml changed during the window')]))
        a.run()
        self.assertIsNone(a.fam().get('candidate'))
        self.assertEqual(a.held(), ['HAND CHANGE'])
        a.archived(lines)


@needs_container
class TheCloseRule(unittest.TestCase):
    """THE CLOSE RULE (D-b (b), the r3 FOLD, B1's CLASS list), one subtest per kind and CLASS, each from a planted
    journal (the apply step reads its lines only): the state's family after it, and the journal archived."""

    def test_a_switch_by_its_class(self):
        cand = {'version': V, 'lines': TL, 'closed_at': T0 + 9}
        for cls, want in (('target-running', 'set'), ('target-idle', 'set'), ('target-old', 'set'),
                          ('pre', 'same'), ('none', 'same'), ('other', 'other')):
            with self.subTest(cls):
                a = A(self, fam={'candidate': None, 'previous': PREV, 'back_until': T0 + 99})
                lines = a.plant(lines_of(cls=cls, prev=[h(9)],
                                         stops=[('HAND CHANGE', 'x')] if cls == 'other' else []))
                a.run()
                f = a.fam()
                if want == 'set':
                    self.assertEqual(f['candidate'], cand)
                    self.assertEqual(f['previous'], OLDL, 'previous is `old` on its sets')
                    self.assertIsNone(f['back_until'])
                else:
                    self.assertIsNone(f.get('candidate'))
                    self.assertEqual((f['previous'], f['back_until']), (PREV, T0 + 99))
                self.assertEqual(a.held(), ['HAND CHANGE'] if want == 'other' else [])
                a.archived(lines)

    def test_a_switch_whose_backup_replaced_the_keep(self):
        """r1 Opus F19: CLASS pre, its LAST `prev` is config-sha (its backup replaced config.toml.prev), no candidate:
        previous and back_until gone, and the line says the keep is gone. The control: a `prev` of another sha (the
        keep is as it was): previous and back_until kept. `prev` twice: the LAST counts. S2b-3c-2 E-10 (B2a's deferral;
        B4a changed this cell, TheCloseRule's class-`other` rule): a close `other` (a person's file the closer found)
        whose backup replaced the keep is the same: previous and back_until gone, and HAND CHANGE held; its control,
        `other` with a `prev` of another sha, keeps them (test_a_switch_by_its_class's other row)."""
        for cls, prevs, gone in (('pre', [h(9), h(1)], True), ('pre', [h(1), h(9)], False),
                                 ('other', [h(9), h(1)], True), ('other', [h(1), h(9)], False)):
            with self.subTest(cls=cls, prevs=prevs):
                a = A(self, fam={'candidate': None, 'previous': PREV, 'back_until': T0 + 99})
                lines = a.plant(lines_of(cls=cls, prev=prevs, end_before_rename=False, target=True,
                                         stops=[('HAND CHANGE', 'x')] if cls == 'other' else []))
                a.run()
                f = a.fam()
                if gone:
                    self.assertEqual((f['previous'], f['back_until']), (None, None))
                    self.assertIn('the keep', a.r.stdout)
                else:
                    self.assertEqual((f['previous'], f['back_until']), (PREV, T0 + 99))
                self.assertIsNone(f.get('candidate'))
                self.assertEqual(a.held(), ['HAND CHANGE'] if cls == 'other' else [])
                a.archived(lines)

    def test_a_rollback_by_its_class(self):
        jf = [stopj('JOBS FAIL ON THE NEW IMAGE'), stopj('NO EVIDENCE')]
        for cls, want, stops in (('target-running', 'back', ()), ('target-idle', 'back', ()),
                                 ('target-old', 'kept', (('CI DISABLED', 'a runscaler that started before'),)),
                                 ('target-failed', 'failed', ()), ('pre', 'same', ()), ('none', 'same', ()),
                                 ('other', 'kept', (('HAND CHANGE', 'x'),))):
            with self.subTest(cls):
                a = A(self, fam={'candidate': C, 'previous': PREV, 'back_until': None, 'stops': jf})
                lines = a.plant(lines_of('rollback', cls, stops=stops))
                a.run()
                f = a.fam()
                if want == 'back':
                    self.assertEqual((f['candidate'], f['previous'], f['back_until']), (None, None, None))
                    self.assertEqual(a.held(), [], 'a target close drops JOBS FAIL and NO EVIDENCE')
                    self.assertIn('rolled back', a.r.stdout)
                    # its rejection (B2b: test_reject.py): `why back`, old-version V newer than target-version 2.338.0
                    self.assertEqual(f.get('rejected', []), [V])
                    continue
                self.assertEqual((f['candidate'], f['previous']), (C, PREV))
                self.assertNotIn('rolled back', a.r.stdout)
                held = a.held()
                for s in ('JOBS FAIL ON THE NEW IMAGE', 'NO EVIDENCE'):   # r2 Codex F14's control: a close that keeps C
                    self.assertIn(s, held)                                 # keeps C's observation STOPs
                if want == 'failed':
                    self.assertIn('ROLLBACK FAILED', held, 'target-failed holds ROLLBACK FAILED')
                elif stops:
                    self.assertIn(stops[0][0], held)
                a.archived(lines)

    def test_a_journal_with_no_target_line_holds_only_its_stops(self):
        """The shortcuts (`up` that already names and runs DIGEST's image; `back` that already is the backup): no
        `target` line: only its STOPs, no candidate change. The control: the same journal with its target: the
        candidate."""
        for target in (False, True):
            with self.subTest(target=target):
                a = A(self, fam={'candidate': None})
                lines = a.plant(lines_of(cls='target-running', target=target,
                                         stops=[] if target else [('CI DISABLED', 'x')]))
                a.run()
                self.assertEqual(a.fam().get('candidate') is not None, target)
                self.assertEqual(a.held(), [] if target else ['CI DISABLED'])
                a.archived(lines)

    def test_a_journal_cut_right_after_window_is_archived_only(self):
        a = A(self, fam={'candidate': C})
        before = a.p.read(STATE)
        lines = a.plant(['window ' + WID, 'recover-start %d' % T0, 'installed none none none', 'closed %d' % T0])
        a.run('on')
        st = a.state()
        self.assertEqual(st['families'], {FAM: {'candidate': C}})
        self.assertNotIn('last_window', st)
        self.assertEqual(json.loads(before)['families'], st['families'])
        a.archived(lines)

    def test_a_journal_with_no_kind_holds_its_stops(self):
        """B2a review r1, Opus F1 (B2a DECISIONS): a window cut right after its first line, `window ID`, the unit not
        enabled: RECOVER closes it with `stop CI DISABLED`. The apply step holds that STOP by THE STOP RULE (version
        null), changes no candidate and keeps the family's other STOPs (no candidate change drops none), sets
        last_window (a cut after this write applies nothing twice), and archives it; so for a planted closed one with a
        `stop` line. The control: the same journal with no `stop` line: archived, and the state as it was."""
        head, tail = ['window ' + WID, 'recover-start %d' % T0], ['installed none none none', 'closed %d' % T0]
        for what, lines, name in (('RECOVER closes it', ['window ' + WID], 'CI DISABLED'),
                                  ('a planted stop line', head + ['stop HAND CHANGE: planted'] + tail, 'HAND CHANGE'),
                                  ('no stop line', head + tail, None)):
            with self.subTest(what):
                a = A(self, fam={'candidate': C, 'stops': [stopj('NO EVIDENCE')]})
                before = a.state()
                a.plant(lines)
                a.run('off')
                self.assertFalse(os.path.lexists(WINDOW), 'the journal is still at WINDOW')
                arch = a.p.read(os.path.join(WINDOWS, WID))
                st = a.state()
                if name is None:
                    self.assertEqual(st, before, 'a journal with no kind and no stop line changed the state')
                    self.assertEqual(arch, ''.join(l + '\n' for l in lines))
                    continue
                self.assertIn('\nstop %s: ' % name, arch, 'the premise: the journal holds the STOP')
                f = st['families'][FAM]
                self.assertEqual(f['candidate'], C)
                self.assertEqual(sorted(s['stop'] for s in f['stops']), sorted(['NO EVIDENCE', name]), self.id())
                s = [x for x in f['stops'] if x['stop'] == name][0]
                self.assertIsNone(s['version'])
                self.assertEqual(s['detail']['text'], arch.split('\nstop %s: ' % name, 1)[1].split('\n', 1)[0])
                self.assertEqual(st.get('last_window'), WID)

    def test_a_class_its_kind_does_not_have_is_a_stop_and_nothing_is_written(self):
        """A switch with target-failed (RECOVER's class of a DECIDED rollback only). The control: a rollback's."""
        for kind in ('switch', 'rollback'):
            with self.subTest(kind):
                a = A(self, fam={'candidate': C})
                before = a.p.read(STATE)
                lines = a.plant(lines_of(kind, 'target-failed'))
                if kind == 'rollback':
                    a.run()
                    a.archived(lines)
                    continue
                r = a.run('off', rc=1)
                self.assertIn(README_LINE, r.stdout)
                self.assertEqual(a.p.read(STATE), before)
                self.assertEqual(a.p.window(), lines)


@needs_container
class Legacy(unittest.TestCase):
    """r3 FOLD LEGACY JOURNALS (Codex r3 F2, Opus r3 F10): a closed journal with no `installed` line (3b-3's, cut
    between its `closed` and its rename): `running` after its `target`: target-running (a switch's candidate C; a
    rollback clears it); a `stop` before any `rename-start`: pre (no change); anything else (a `stop` after the rename):
    a STOP with README's section, nothing written. A rollback with no `why`: a person's back, old-version none, the line
    says so. An old no-target shortcut changes no candidate. A closed journal already in windows/ is never applied."""

    def test_legacy_shapes(self):
        for name, kind, mk, want in (
                ('switch running', 'switch', dict(), 'cand'),
                ('rollback running, no why', 'rollback', dict(why=None), 'back'),
                ('stop before the rename', 'switch', dict(stop_before_rename=True, stops=[('HAND CHANGE', 'x')]),
                 'same'),
                ('stop right after its validate', 'switch', dict(end_before_rename=True, stops=[('DISK', 'x')]),
                 'same'),
                ('no-target shortcut', 'switch', dict(target=False), 'same'),
                ('a stop after the rename', 'switch', dict(stops=[('HAND CHANGE', 'x')], run_after=None), 'stop')):
            with self.subTest(name):
                a = A(self, fam={'candidate': C if kind == 'rollback' else None})
                before = a.p.read(STATE)
                L = lines_of(kind, legacy=True, **{k: v for k, v in mk.items() if k != 'run_after'})
                if 'run_after' in mk:
                    L = [l for l in L if not l.startswith('running ')]
                lines = a.plant(L)
                if want == 'stop':
                    r = a.run('off', rc=1)
                    self.assertIn(README_LINE, r.stdout)
                    self.assertEqual(a.p.read(STATE), before)
                    continue
                a.run()
                f = a.fam()
                if want == 'cand':
                    self.assertEqual(f['candidate']['lines'], TL)
                elif want == 'back':
                    self.assertIsNone(f['candidate'])
                    self.assertIn('no `why`', a.r.stdout)
                    self.assertIn('old-version none', a.r.stdout)
                else:
                    self.assertEqual(f.get('candidate'), None)
                a.archived(lines)

    def test_a_closed_journal_in_windows_is_never_applied(self):
        a = A(self, fam={'candidate': None})
        a.p.write(os.path.join(WINDOWS, WID), ''.join(l + '\n' for l in lines_of()), 0o600)
        a.run('off')
        self.assertIsNone(a.fam().get('candidate'))
        self.assertNotIn('last_window', a.state())


@needs_container
class TheStopRule(unittest.TestCase):
    """THE STOP RULE (the Studio's runner-updater-window :127-139 and kept($W ...); D-b; S2b-3c-2 E-8 and its r2 FOLD):
    each STOP name of the journal held once (its LAST line of that name), replacing the family's held STOP of the same
    name; DISK, untested jq and NO IDLE are never held from a journal (the pass checks them again; NO IDLE: the restart
    came). A close that RAN ITS RESTART (its journal has `stopping`, or it closed CLASS target-running) drops the
    family's held WINDOW STOPs (check failed, HAND CHANGE, NO IDLE, ROLLBACK FAILED, CI DISABLED: the Studio's ru_W but
    DISK and POOL DOWN, which this host's pass computes as levels); a close before `stopping` drops nothing but its own
    names (r2 Opus F2's control). A close with CLASS target (a switched or rolled back candidate) also drops JOBS FAIL ON
    THE NEW IMAGE and NO EVIDENCE; a pre close keeps them. B4a changed this cell: up to 3c-1 "a held CI DISABLED and
    HAND CHANGE survive a target-running close" (the r2 FOLD's E-8 drops them; its control, a close before `stopping`,
    keeps them)."""

    HELD = ('HAND CHANGE', 'CI DISABLED', 'check failed', 'NO IDLE', 'ROLLBACK FAILED', 'DISK', 'POOL DOWN',
            'JOBS FAIL ON THE NEW IMAGE')
    WINDOW_STOPS = {'HAND CHANGE', 'CI DISABLED', 'check failed', 'NO IDLE', 'ROLLBACK FAILED'}

    def test_held_once_replaced_by_name_and_never_three(self):
        journal = [('HAND CHANGE', 'first'), ('DISK', 'd'), ('untested jq', 'j'), ('NO IDLE', 'n'),
                   ('HAND CHANGE', 'second'), ('POOL DOWN', 'p')]
        no_stop = lambda L: [l for l in L if not l.startswith(('stopping ', 'stopped '))]
        for why, mk, stopping, ran, switched in (
                ('pre, after stopping', lambda: lines_of(cls='pre', stops=journal), True, True, False),
                ('target-running', lambda: lines_of(cls='target-running', stops=journal), True, True, True),
                ('target-running with no stopping line (another actor\'s start)',
                 lambda: no_stop(lines_of(cls='target-running', stops=journal)), False, True, True),
                ('target-old, after stopping', lambda: lines_of(cls='target-old', stops=journal), True, True, True),
                ('a close before stopping', lambda: lines_of(cls='pre', stops=journal, stop_before_rename=True),
                 False, False, False)):
            with self.subTest(why):
                a = A(self, fam={'candidate': None, 'stops': [stopj(n, 'old text') for n in self.HELD]})
                lines = a.plant(mk())
                self.assertEqual('stopping' in [l.split(' ')[0] for l in lines], stopping, 'the premise')
                a.run()
                st = a.fam()['stops']
                names = sorted(s['stop'] for s in st)
                want = {'HAND CHANGE', 'POOL DOWN'}                       # the journal's own names
                want |= {n for n in self.HELD if not (ran and n in self.WINDOW_STOPS)}
                if switched:
                    want.discard('JOBS FAIL ON THE NEW IMAGE')
                self.assertEqual(names, sorted(want), st)
                hc = [s for s in st if s['stop'] == 'HAND CHANGE']
                self.assertEqual([s['detail']['text'] for s in hc], ['second'])
                self.assertEqual(hc[0]['version'], V)
                pd = [s for s in st if s['stop'] == 'POOL DOWN']
                self.assertEqual([s['detail']['text'] for s in pd], ['p'], 'the journal\'s POOL DOWN replaces the held')
                a.archived(lines)


@needs_container
class KeepPrevCloses(unittest.TestCase):
    """B3's note and its review's (Codex, Opus: "Notes for B4a"; S2b-3c-2 E-3, E-10): REAL keep-prev switch windows
    (`up --unattended V D --keep-prev`) closed through the apply step, one per CLASS. A keep-prev window's backup is
    its own folder's file (windows/ID.d/config.toml.backup, its `backup` line), so its close keeps the family's
    `previous` and `back_until` as they were, also when its closing `prev` equals config.toml's sha (here
    config.toml.prev IS config.toml's bytes: the plain rule's "the backup replaced the keep" reads that shape), and
    config.toml.prev stays byte for byte. target-*: the candidate is V on the TARGET's lines; pre, none, other: no
    candidate change (other: HAND CHANGE). A switch's target-failed (no real switch closes it: RECOVER's class of a
    DECIDED rollback) is a class its kind has not: a STOP, nothing written (a real keep-prev journal, its class edited).
    The controls: the same windows with no --keep-prev (backup config.toml.prev, prev = config-sha): target-running sets
    previous to `old` and back_until null; pre and other (E-10) drop previous and back_until."""

    KEEP = {MAIN: ref('sha256:' + '36' * 32), SMALL: ref('sha256:' + '36' * 32)}
    CAND = {'version': '2.338.9', 'lines': OLDL, 'closed_at': T0}

    def window(self, how, keep_prev):
        more = ('--keep-prev',) if keep_prev else ()
        if how in ('target-old', 'none'):
            at = 'journal:renamed' if how == 'target-old' else 'journal:keep-prev'
            g = cut(self, 'up', (at, 'kill'), more=more, before=lambda g: g.p.write(g.prev, g.old, 0o600))
            if how == 'target-old':
                g.p.set_unit(enabled=False)                    # a person's `disable` without --now: the old one runs
        else:
            g = Rig(self)
            g.p.write(g.prev, g.old, 0o600)                    # config.toml.prev = config.toml's bytes: prev = config-sha
            g.p.hooks(*{'target-running': (), 'target-idle': (('systemctl:stop-done', 'disable'),),
                        'pre': ((('mv-done:config.toml.backup' if keep_prev else 'mv-done:config.toml.prev'),
                                 'edit-staged'),),
                        'other': (('journal:backup', 'hand-file'),),
                        'target-failed': ()}[how])
            r = g.up(*more)
            self.assertEqual(r.returncode, 0 if how in ('target-running', 'target-failed') else 1,
                             r.stdout[-3000:] + r.stderr)
            if how == 'target-failed':
                lines = g.p.window()
                lines[-2] = ' '.join(lines[-2].split(' ')[:-1] + ['target-failed'])
                g.p.write(WINDOW, ''.join(l + '\n' for l in lines), 0o600)
        return g

    def test_each_class_keeps_previous_and_back_until(self):
        rows = [('target-running', True), ('target-idle', True), ('target-old', True), ('pre', True), ('none', True),
                ('other', True), ('target-failed', True), ('target-running', False), ('pre', False), ('other', False)]
        for how, kp in rows:
            with self.subTest(cls=how, keep_prev=kp):
                g = self.window(how, kp)
                prev_text, prev_st = g.p.read(g.prev), os.stat(g.prev)
                os.makedirs(STATEDIR, mode=0o700, exist_ok=True)
                g.p.write(STATE, json.dumps({'format': 1, 'on': False, 'families': {FAM: {
                    'candidate': self.CAND if kp else None, 'previous': self.KEEP, 'back_until': T0 + 99}}}) + '\n',
                    0o600)   # a keep-prev window is one of an OPEN candidate; a plain one has none (DUE step 1)
                before = g.p.read(STATE)
                lines = g.p.window()
                self.assertEqual('keep-prev' in keys(lines), kp, 'the premise: its keep-prev line')
                r = g.p.updater('off')
                if how == 'target-failed':
                    self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                    self.assertIn(README_LINE, r.stdout)
                    self.assertEqual(g.p.read(STATE), before, 'a class its kind has not: nothing written')
                    continue
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                arch = g.p.closed()[-1][1]
                self.assertEqual(arch[-2].split(' ')[-1], how, arch)
                if kp and 'backup' in keys(arch):
                    self.assertEqual(value(arch, 'backup'), os.path.join(WINDOWS, value(arch, 'window') + '.d',
                                                                         'config.toml.backup'))
                if 'prev' in keys(arch) and 'config-sha' in keys(arch) and how != 'none':
                    self.assertEqual(value(arch, 'prev'), value(arch, 'config-sha'),
                                     'the premise: prev equals config.toml\'s sha')
                f = json.loads(g.p.read(STATE))['families'][FAM]
                if how.startswith('target-'):
                    self.assertEqual(f['candidate']['version'], V)
                    self.assertEqual(f['candidate']['lines'], TL)
                else:
                    self.assertEqual(f.get('candidate'), self.CAND if kp else None)
                if kp:
                    self.assertEqual((f['previous'], f['back_until']), (self.KEEP, T0 + 99))
                    self.assertEqual((g.p.read(g.prev), os.stat(g.prev).st_mtime_ns), (prev_text, prev_st.st_mtime_ns))
                elif how == 'target-running':
                    self.assertEqual((f['previous'], f['back_until']), (OLDL, None))
                else:
                    self.assertEqual((f['previous'], f['back_until']), (None, None), 'E-10: the keep is gone')
                held = [s['stop'] for s in f.get('stops', [])]
                self.assertEqual('HAND CHANGE' in held, how == 'other', held)
                self.assertEqual('CI DISABLED' in held, how in ('target-idle', 'target-old'), held)


@needs_container
class TheOwnRestart(unittest.TestCase):
    """THE OWN RESTART (r3 FOLD; Codex r3 F7, r2 Codex F13, Opus F11): an uninterrupted window's `from`, `stopped` and
    `running` (started within 20 s of its `starting`) -> restart {from, to, stopped}; with a `recover-start`, with its
    `running` 21 s after `starting` (an unseen restart may have come between), or while the state holds an unconsumed
    `restart`: the member removed."""

    def test_the_triple_only_from_one_actor_s_coherent_restart(self):
        old = {'from': {'pid': 7, 'start': 1}, 'to': {'pid': 8, 'start': 2}, 'stopped': {'inode': '1', 'offset': 0,
                                                                                      'sha': h(7)}}
        want = {'from': {'pid': 100, 'start': T0 - 1000}, 'to': {'pid': 101, 'start': T0 + 3 + 20},
                'stopped': {'inode': '1234', 'offset': 567, 'sha': h(4)}}
        for name, mk, held, ok in (('coherent, 20 s', dict(run_after=20), None, True),
                                   ('21 s after starting', dict(run_after=21), None, False),
                                   ('recover-start', dict(recover=True), None, False),
                                   ('an unconsumed restart held', dict(run_after=20), old, False)):
            with self.subTest(name):
                a = A(self, fam={'candidate': None}, extra={'restart': held} if held else None)
                lines = a.plant(lines_of(**mk))
                a.run()
                st = a.state()
                if ok:
                    self.assertEqual(st.get('restart'), want)
                else:
                    self.assertNotIn('restart', st)
                a.archived(lines)


@needs_container
class LastWindow(unittest.TestCase):
    """r3 Codex F5's first half, r2 Codex F9's control: a journal whose ID is the state's `last_window` (a kill after
    the state write, before the archive) is only archived: the state is as it was, byte for byte. The control: another
    ID: applied."""

    def test_an_applied_journal_is_only_archived(self):
        for last, applied in ((WID, False), ('20261106000000-1', True)):
            with self.subTest(applied=applied):
                a = A(self, fam={'candidate': C}, extra={'last_window': last})
                before = a.p.read(STATE)
                lines = a.plant(lines_of(cls='target-running'))
                a.run('on')
                if applied:
                    self.assertEqual(a.fam()['candidate']['version'], V)
                    self.assertEqual(a.state().get('last_window'), WID)
                else:
                    self.assertEqual(json.loads(a.p.read(STATE))['families'], json.loads(before)['families'])
                    self.assertEqual(a.state()['last_window'], WID)
                a.archived(lines)


@needs_container
class RecoverFirst(unittest.TestCase):
    """B2a item 3 (D-b (c), D-f): RECOVER runs at the start of every RS_USER run that takes the lock, as the
    updater's child, before ON/OFF is read, then the apply step: a switch cut after `stopped` (the unit enabled, down):
    a pass while OFF ends it (RECOVER starts runscaler on the TARGET: closed target-running), applies it (the candidate)
    and archives it, then says OFF; no "RECOVER needed". `on` and `off` run it too. A pass makes at most ONE restart
    (D-g): one `systemctl start`, no other start, stop or restart."""

    def test_a_cut_window_is_ended_applied_and_archived_by_each_command(self):
        for cmd, on in (('pass', False), ('on', False), ('off', True)):
            with self.subTest(cmd):
                g = cut(self, 'up', ('journal:stopped', 'kill'))
                os.makedirs(STATEDIR, mode=0o700, exist_ok=True)
                g.p.write(STATE, json.dumps({'format': 1, 'on': on, 'families': {}}) + '\n', 0o600)
                wid = value(g.cut, 'window')
                r = g.p.updater(cmd)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertNotIn('RECOVER needed', r.stdout)
                self.assertIn('POOL IMAGE RECOVER: ', r.stdout)
                st = json.loads(g.p.read(STATE))
                self.assertEqual(st['families'][FAM]['candidate']['version'], V)
                self.assertEqual(st['last_window'], wid)
                self.assertEqual(st['on'], cmd == 'on')
                self.assertIsNone(g.p.window())
                arch = g.p.read(os.path.join(WINDOWS, wid)).splitlines()
                self.assertEqual(arch[-2].split(' ')[-1], 'target-running', arch)
                self.assertEqual((len(g.calls('start')), len(g.calls('stop')), len(g.calls('restart'))), (1, 0, 0))
                if cmd == 'pass':
                    self.assertIn('runner-updater: pass: the updater is OFF', r.stdout)

    def test_an_open_journal_after_recover_starts_nothing_else(self):
        """RECOVER exit 5 (a switch cut after `renamed` on a busy pool: it waits for idle): its line printed, the
        journal open, the updater's STOP line, exit 1, no core program (a pass that is ON), and `off` refuses. The
        control: the pool idle: closed, applied, the core runs."""
        for busy in (True, False):
            with self.subTest(busy=busy):
                g = cut(self, 'up', ('journal:renamed', 'kill'))
                if busy:
                    g.p.curl['healthz'] = g.p.curl['busy']
                os.makedirs(STATEDIR, mode=0o700, exist_ok=True)
                g.p.write(STATE, json.dumps({'format': 1, 'on': True, 'families': {}}) + '\n', 0o600)
                r = g.p.updater('pass')
                pdir = os.path.join(STATEDIR, 'pass')
                if not busy:
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                    self.assertTrue(os.path.exists(os.path.join(pdir, 'r1.json')))
                    continue
                self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
                self.assertIn('the switch waits for idle', r.stdout)
                self.assertIn('runner-updater: STOP the window journal %s stays open' % WINDOW, r.stdout)
                self.assertFalse(os.path.exists(os.path.join(pdir, 'r1.json')), 'a core program ran')
                self.assertIsNotNone(g.p.window())
                r = g.p.updater('off')
                self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
                self.assertIn('runner-updater: REFUSE a window journal stays open', r.stdout)
                self.assertTrue(json.loads(g.p.read(STATE))['on'])

    def test_recover_s_exits(self):
        """4: a person's pool-image.sh run holds its lock: a WAIT line, no STOP; a closed journal is applied all the
        same. 6: a journal RECOVER cannot read: STOP with README's section, nothing written. 1: REFUSE. Another code:
        a STOP that names it."""
        for code in (4, 6, 1, 7):
            with self.subTest(code=code):
                a = A(self, fam={'candidate': None})
                before = a.p.read(STATE)
                if code == 4:
                    lines = a.plant(lines_of())
                    lock = os.path.join(R, 'pool-image.lock')
                    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    self.addCleanup(os.close, fd)
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    a.run('off')
                    self.assertIn('RECOVER waits', a.r.stdout)
                    self.assertNotIn('STOP', a.r.stdout)
                    a.archived(lines)
                    continue
                if code == 6:
                    a.plant(['window ' + WID, 'a line no pattern reads'])
                else:
                    a.plant(lines_of())
                    a.p.write(os.path.join(a.p.build, 'setup', 'pool-image.sh'), '#!/bin/bash\necho planted\nexit %d\n'
                              % code, 0o755)
                r = a.run('off', rc=1)
                self.assertEqual(a.p.read(STATE), before)
                self.assertIsNotNone(a.p.window())
                if code == 6:
                    self.assertIn('runner-updater: STOP RECOVER cannot read or act on the window journal %s' % WINDOW,
                                  r.stdout)
                    self.assertIn(README_LINE, r.stdout.split('runner-updater: STOP RECOVER cannot read', 1)[1])
                elif code == 1:
                    self.assertIn('runner-updater: REFUSE RECOVER', r.stdout)
                else:
                    self.assertIn('RECOVER exited 7', r.stdout)

    def test_the_child_holds_the_lock_on_fd_9(self):
        """RECOVER is the updater's CHILD (D-a): pool-image.sh's rr_held passes (it ran; no REFUSE). The control: run
        as no one's child (support.Pool.unattended with no prefix), it refuses."""
        a = A(self, fam={'candidate': None})
        lines = a.plant(lines_of())
        r = a.p.unattended('recover', '--unattended', prefix=())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("is the updater's only", r.stdout)
        a.run('off')
        self.assertNotIn('REFUSE', a.r.stdout)
        a.archived(lines)


if __name__ == '__main__':
    unittest.main()
