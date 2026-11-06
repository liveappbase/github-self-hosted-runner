"""linux-docker/bin/runner-updater's REJECTION (S2b-3c-1 D-e; the r3 FOLD "THE REJECTED FILE"; B2b item 2): the apply
step of a rollback's closed journal that ROLLED BACK (CLASS target-running or target-idle) rejects by the journal's
own `why`, `old-version`, `target-version`, `verdict` and `old` lines (it reads no config.toml, no build record and no
clock).
(Named for its CI part, test_re[!c]*.py: .github/workflows/release-check.yml.)

- `why r1`: old-version V rejected (the state's `rejected`, and the digest of `old` in ~/.local/state/runner-updater/
  rejected, 03-runscaler.sh's reader: one `sha256:<64 hex>` per line), STOP ROLLED BACK of V whose detail is R1's
  verdict for the family {set, failures, connect_only, reason}, read from the window's verdict.json only when its sha is
  the journal's `verdict`; else the detail says R1's failures are not readable, and status prints that line (r2 Codex
  F12). old-version none: nothing rejected, and the line says why.
- `why r1-connect`: the Studio's connect_only {V: {n, at}} (at = the journal's `closed`): n = 1 holds ROLLED BACK with
  connect_only true and rejects nothing (status: the 1-h retry), n = 2 rejects V; per version (r2 Codex F11: V, W, V
  rejects V on the third); a pass removes the n = 1 STOP once now - at >= 3600 (r2 Opus F3). old-version none: not
  counted (r3 Opus F11).
- `why back`: rejected only when old-version is newer than target-version; none on either side: not rejected, and the
  line says why. No ROLLED BACK (a person's).
- THE REJECTED FILE (r3 Opus F9, Codex F5): the digest added only when absent, by a rename of a full copy, BEFORE the
  state write; a file it cannot read is a STOP and nothing is written. A kill at each boundary (after the file's rename;
  after the state write) adds nothing twice and counts no connect-only rollback twice.
- Nothing else rejects: target-old, target-failed, pre, none, other; a legacy rollback with no `why`.
Every cell runs the real scripts (support.Pool, a throwaway container) and the updater as RS_USER; a closed journal in
pool-image.sh's grammar is planted (the apply step reads lines only), or a pass runs on a fake clock; no cell asserts a
time it waited.
"""
import hashlib
import json
import os
import re
import unittest

from tests.hetzner.support import digest, needs_container, ref
from tests.hetzner.test_apply import (FAM, MAIN, OLDL, R, STATE, STATEDIR, T0, TL, WID, WINDOW, WINDOWS, A, lines_of,
                                      stopj)
from tests.hetzner.test_unattended import NEW, V
from tests.hetzner.test_updater import Rig

REJECTED = os.path.join(STATEDIR, 'rejected')
CAND = {'version': V, 'lines': TL, 'closed_at': T0 - 86400}        # the candidate a rollback of V leaves
FAILS = [{'t': T0 - 300 + 10 * i, 'c': False, 'x': 'Failed to start runner %d' % i} for i in (1, 2, 3)]
W2 = '20261106020000-4343'


def r1_out(connect_only=False, fam=FAM):
    """An r1.json (the pass's PASSDIR/r1.json that the window copied as verdict.json): R1's rollback of FAM."""
    return json.dumps({'verdict': 'ok', 'reason': 'planted', 'lines': [], 'families': {fam: {
        'verdict': 'rollback', 'set': MAIN, 'connect_only': connect_only, 'reason': 'R1 on set %s: planted' % MAIN,
        'failures': FAILS, 'stops': [], 'open': True, 'since': T0 - 900, 'gaps': 0, 'pending': None}},
        'state': {'format': 1}}) + '\n'


def rollback(why='r1', old_version=V, target_version='2.338.0', cls='target-running', wid=WID, verdict=None,
             old=None, connect_only=None):
    """A closed rollback journal (test_apply.lines_of), its why / old-version / target-version / old lines as given;
    VERDICT: the text of the window's verdict.json (written into windows/WID.d) and its sha in the `verdict` line
    (None: r1_out for an r1 rollback, `verdict none` for a back; '' : `verdict none`). Returns (lines, verdict text)."""
    if verdict is None:
        verdict = r1_out(why == 'r1-connect' if connect_only is None else connect_only) if why != 'back' else ''
    L = lines_of('rollback', cls, wid=wid, why=why)
    vsha = hashlib.sha256(verdict.encode()).hexdigest() if verdict else 'none'
    L = [('verdict ' + vsha) if l.startswith('verdict ')
         else ('old-version ' + old_version) if l.startswith('old-version ')
         else ('target-version ' + target_version) if l.startswith('target-version ')
         else ('old ' + old) if (old is not None and l.startswith('old ')) else l for l in L]
    return L, verdict


class J(A):
    """test_apply's A (no production; the updater OFF unless on=True; `off` applies): the family's candidate CAND
    (runner V on NEW's lines) and previous OLD's, unless FAM_ is given."""

    def __init__(self, test, fam=None, on=False, extra=None):
        super().__init__(test, on=on, fam=fam if fam is not None else {'candidate': CAND, 'previous': OLDL},
                         extra=extra)

    def journal(self, lines, verdict='', wid=WID):
        if verdict:
            d = os.path.join(WINDOWS, wid + '.d')
            os.makedirs(d, mode=0o700, exist_ok=True)
            self.p.write(os.path.join(d, 'verdict.json'), verdict, 0o600)
        return self.plant(lines)

    def rejected_file(self):
        return self.p.read(REJECTED)

    def rb(self):
        return [s for s in self.fam().get('stops', []) if s['stop'] == 'ROLLED BACK']


def dig(image):
    return image.rsplit('@', 1)[1]


@needs_container
class ByWhy(unittest.TestCase):
    def test_r1_rejects_its_old_version_and_holds_rolled_back_with_r1_s_failures(self):
        """`why r1` of V, target-running and target-idle (a `disable --now`: its TARGET runs at the person's start):
        rolled back, V rejected, the digest of `old` (NEW's) the rejected file's one line, STOP ROLLED BACK of V with
        R1's family verdict as its detail (status: 3 counted failures, the last one's text), connect_only unchanged; 03
        then refuses that digest."""
        for cls in ('target-running', 'target-idle'):
            with self.subTest(cls):
                j = J(self)
                lines, v = rollback(cls=cls)
                j.journal(lines, v)
                j.run('off')
                f = j.fam()
                self.assertEqual((f['candidate'], f['previous'], f['back_until']), (None, None, None))
                self.assertEqual(f.get('rejected'), [V])
                self.assertNotIn('connect_only', f)
                self.assertEqual(j.rejected_file(), dig(ref(NEW)) + '\n')
                rb, = j.rb()
                self.assertEqual(rb['version'], V)
                self.assertEqual(rb['detail'], {'set': MAIN, 'failures': FAILS, 'connect_only': False,
                                                'reason': 'R1 on set %s: planted' % MAIN})
                self.assertIn('rejected runner %s' % V, j.r.stdout)
                j.archived(lines)
                st = j.p.updater('status')
                self.assertIn('hz-docker: STOP ROLLED BACK (runner %s): 3 counted failures, the last: Failed to start '
                              'runner 3' % V, st.stdout)
                self.assertNotIn("R1's failures are not readable", st.stdout)
                r = j.p.s03('render', dig(ref(NEW)), os.path.join(R, 'config.x.toml'))
                self.assertNotEqual(r.returncode, 0, r.stdout[-2000:])
                self.assertIn('is rejected (listed in %s)' % REJECTED, r.stdout + r.stderr)

    def test_a_verdict_copy_that_is_not_the_journal_s_is_not_readable(self):
        """r2 Codex F12: the window's verdict.json changed after its `verdict` line, gone, or `verdict none`: V is
        rejected all the same (by `why` and old-version), and the ROLLED BACK's detail says R1's failures are not
        readable; status prints that line (status.jq alone would print "0 counted failures"). The control: the copy
        that is the journal's (the cell above)."""
        for what in ('changed', 'gone', 'verdict none'):
            with self.subTest(what):
                j = J(self)
                lines, v = rollback(verdict=r1_out() if what != 'verdict none' else '')
                j.journal(lines, v if what != 'gone' else '')
                if what == 'changed':
                    j.p.write(os.path.join(WINDOWS, WID + '.d', 'verdict.json'), v.replace('planted', 'edited'), 0o600)
                j.run('off')
                self.assertEqual(j.fam().get('rejected'), [V])
                rb, = j.rb()
                self.assertNotIn('failures', rb['detail'])
                self.assertIn("R1's failures are not readable", rb['detail'].get('text', ''))
                st = j.p.updater('status')
                self.assertRegex(st.stdout, r"(?m)^runner-updater: status: STOP ROLLED BACK \(runner %s\): R1's "
                                            r"failures are not readable" % re.escape(V))

    def test_old_version_none_rejects_and_counts_nothing(self):
        """`old-version none` (no version known when the window began): `why r1` rolls back and rejects nothing, the
        line says why; `why r1-connect` counts no connect-only rollback (r3 Opus F11). The control: the first cell."""
        for why in ('r1', 'r1-connect'):
            with self.subTest(why):
                j = J(self)
                lines, v = rollback(why=why, old_version='none')
                j.journal(lines, v)
                j.run('off')
                f = j.fam()
                self.assertIsNone(f['candidate'])
                self.assertEqual(f.get('rejected', []), [])
                self.assertNotIn('connect_only', f)
                self.assertIsNone(j.rejected_file())
                self.assertIn('old-version none', j.r.stdout)
                j.archived(lines)

    def test_back_rejects_only_a_newer_version(self):
        """`why back` (a person's): rejected only when old-version is newer than target-version (field by field, as
        numbers); equal or older: not; `none` on either side: not, and the line says why. No ROLLED BACK."""
        for old_v, tgt_v, rej in (('2.339.0', '2.338.0', True), ('2.339.0', '2.339.0', False),
                                  ('2.338.10', '2.338.9', True), ('2.338.0', '2.339.0', False),
                                  ('none', '2.338.0', False), ('2.339.0', 'none', False)):
            with self.subTest(old=old_v, target=tgt_v):
                j = J(self)
                lines, _ = rollback(why='back', old_version=old_v, target_version=tgt_v)
                j.journal(lines)
                j.run('off')
                f = j.fam()
                self.assertIsNone(f['candidate'])
                self.assertEqual(f.get('rejected', []), [old_v] if rej else [])
                self.assertEqual(j.rejected_file(), (dig(ref(NEW)) + '\n') if rej else None)
                self.assertEqual(j.rb(), [])
                if 'none' in (old_v, tgt_v):
                    self.assertIn('none', j.r.stdout.split('apply: ', 2)[-1])
                j.archived(lines)


@needs_container
class ConnectOnly(unittest.TestCase):
    def test_per_version_the_first_rejects_nothing_and_the_second_rejects(self):
        """r2 Opus F3, r2 Codex F11: `why r1-connect` of V (n = 1: ROLLED BACK with connect_only true, not rejected,
        connect_only {V: {n: 1, at: its closed}}; status prints the 1-h retry), then of W (its own count: W not
        rejected, V's count kept), then of V again (n = 2: V rejected, its digest in the file). The control: `why r1`
        rejects at once and leaves connect_only as it is."""
        W = '2.340.0'
        j = J(self)
        seq = ((V, WID, NEW, 1, False), (W, W2, digest(41), 1, False), (V, '20261106030000-4444', NEW, 2, True))
        for n, (ver, wid, d, count, rej) in enumerate(seq):
            st = j.state()
            st['families'][FAM]['candidate'] = {'version': ver, 'lines': TL, 'closed_at': T0 - 86400}
            j.put(st)
            lines, v = rollback(why='r1-connect', old_version=ver, wid=wid, old=ref(d))
            lines[-1] = 'closed %d' % (T0 + 100 * n)
            j.journal(lines, v, wid=wid)
            j.run('off')
            f = j.fam()
            self.assertEqual(f.get('connect_only', {}).get(ver), {'n': count, 'at': T0 + 100 * n}, f)
            self.assertEqual(ver in f.get('rejected', []), rej, f)
            rb = [s for s in f['stops'] if s['stop'] == 'ROLLED BACK']
            self.assertEqual([(s['version'], s['detail']['connect_only']) for s in rb], [(ver, True)])
            j.archived(lines, wid)
        self.assertEqual(f['connect_only'], {V: {'n': 2, 'at': T0 + 200}, W: {'n': 1, 'at': T0 + 100}})
        self.assertEqual(f['rejected'], [V])
        self.assertEqual(j.rejected_file(), dig(ref(NEW)) + '\n')
        # the 1-h line of a first connect-only rollback, as status prints it
        st = j.state()
        st['families'][FAM]['stops'] = [stopj('ROLLED BACK', version=W)]
        st['families'][FAM]['stops'][0]['detail'] = {'connect_only': True, 'failures': FAILS}
        j.put(st)
        self.assertIn('connect-class only: one retry after 1 h comes first', j.p.updater('status').stdout)
        # the control: why r1
        k = J(self, fam={'candidate': CAND, 'connect_only': {V: {'n': 1, 'at': T0}}})
        lines, v = rollback(why='r1')
        k.journal(lines, v)
        k.run('off')
        self.assertEqual(k.fam()['connect_only'], {V: {'n': 1, 'at': T0}})
        self.assertEqual(k.fam()['rejected'], [V])

    def test_a_pass_removes_the_first_one_s_stop_after_1_h(self):
        """r2 Opus F3 (the Studio's pass_connect_retry): a pass that is ON removes STOP ROLLED BACK of V whose detail is
        connect-only when connect_only[V].n = 1 and now - at >= 3600: kept at at + 3599, removed at at + 3600 (V may be
        due again, once). The control: n = 2 (rejected): kept at at + 3600."""
        for n, after, kept in ((1, 3599, True), (1, 3600, False), (2, 3600, True)):
            with self.subTest(n=n, after=after):
                g = Rig(self, on=True)
                at = g.p.clock()
                rb = {'family': FAM, 'stop': 'ROLLED BACK', 'version': V, 'user': None,
                      'detail': {'set': MAIN, 'failures': FAILS, 'connect_only': True, 'reason': 'planted'}}
                g.put({'format': 1, 'on': True, 'families': {FAM: {
                    'stops': [rb], 'connect_only': {V: {'n': n, 'at': at}}, 'rejected': [V] if n == 2 else []}}})
                g.p.clock(now=at + after)
                r = g.ok('pass')
                f = g.state()['families'][FAM]
                self.assertEqual([s['stop'] for s in f.get('stops', [])], ['ROLLED BACK'] if kept else [],
                                 r.stdout[-3000:])
                self.assertEqual(f['connect_only'], {V: {'n': n, 'at': at}}, 'the count changed')
                if not kept:
                    self.assertIn('one retry of %s may start' % V, r.stdout)


@needs_container
class TheFile(unittest.TestCase):
    def test_the_digest_is_added_once_by_a_rename_of_a_full_copy(self):
        """r3 Opus F9, Codex F5: no file: one line; a file that lists other digests: theirs kept, its own added; one
        that lists it already: the same bytes (added only when absent). Each by rename (a new inode). Its mode is 0600
        with no chmod of its own (B2b review r1, the CI red of test_modes OnePlace: rr_lock is the one place that sets
        the modes of the updater's folder, and its files are made under the umask 077 THE MODES names): a new copy,
        also when the file it replaces was 0644 (a file the person made)."""
        other = digest(30)
        for what, before, after, mode in (
                ('no file', None, [dig(ref(NEW))], None), ('others', [other], [other, dig(ref(NEW))], 0o600),
                ('others 0644', [other], [other, dig(ref(NEW))], 0o644),
                ('itself', [other, dig(ref(NEW))], [other, dig(ref(NEW))], 0o600)):
            with self.subTest(what):
                j = J(self)
                if before is not None:
                    j.p.write(REJECTED, ''.join(x + '\n' for x in before), mode)
                ino = os.stat(REJECTED).st_ino if before is not None else None
                lines, v = rollback()
                j.journal(lines, v)
                j.run('off')
                self.assertEqual(j.rejected_file(), ''.join(x + '\n' for x in after))
                if what.startswith('others'):
                    self.assertNotEqual(os.stat(REJECTED).st_ino, ino, 'it was written in place, not renamed')
                if what == 'itself':
                    self.assertEqual(os.stat(REJECTED).st_ino, ino, 'it was written again, though the digest was there')
                self.assertEqual(oct(os.stat(REJECTED).st_mode & 0o777), oct(0o600))

    def test_a_rejected_file_it_cannot_read_is_a_stop_and_nothing_is_written(self):
        """A file 03 cannot read (a line that is not sha256:<64 hex>; a folder): the apply step writes neither it nor
        the state, and the journal stays at WINDOW: a STOP that names the file (03 refuses every mode while it is so).
        The control: the cell above."""
        for what in ('a bad line', 'a folder'):
            with self.subTest(what):
                j = J(self)
                if what == 'a bad line':
                    j.p.write(REJECTED, 'not a digest\n', 0o600)
                else:
                    os.makedirs(REJECTED)
                before = j.p.read(STATE)
                lines, v = rollback()
                j.journal(lines, v)
                r = j.run('off', rc=1)
                self.assertEqual(j.p.read(STATE), before)
                self.assertEqual(j.p.window(), lines)
                self.assertIn('runner-updater: STOP the window journal %s is closed, but its rejection cannot be '
                              'written' % WINDOW, r.stdout)
                if what == 'a bad line':
                    self.assertEqual(j.rejected_file(), 'not a digest\n')


@needs_container
class Kills(unittest.TestCase):
    def test_a_kill_at_each_boundary_adds_nothing_twice_and_counts_nothing_twice(self):
        """r3 Opus F9, Codex F5: a second connect-only rollback of V (n 1 -> 2: it rejects) killed right after the
        rejected file's rename (before the state write), and right after the state write (before the archive); the
        next run ends it: the digest once, n = 2 (counted once), V rejected once, archived. The control: no kill."""
        for at in ('mv-done:rejected', 'mv-done:state.json', None):
            with self.subTest(at=at):
                j = J(self, fam={'candidate': CAND, 'previous': OLDL, 'connect_only': {V: {'n': 1, 'at': T0 - 7200}}})
                lines, v = rollback(why='r1-connect')
                j.journal(lines, v)
                if at:
                    j.p.hooks((at, 'kill-updater'))
                    r = j.p.updater('off')
                    self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
                    self.assertIn('kill-updater', '\n'.join(j.p.events()), 'the premise: the kill came')
                    self.assertEqual(j.p.window(), lines, 'the premise: the journal is still at WINDOW')
                    self.assertEqual(j.rejected_file(), dig(ref(NEW)) + '\n', 'the premise: the file was renamed')
                    j.p.hooks()
                j.run('off')
                f = j.fam()
                self.assertEqual(j.rejected_file(), dig(ref(NEW)) + '\n')
                self.assertEqual(f['connect_only'], {V: {'n': 2, 'at': T0 + 9}})
                self.assertEqual(f['rejected'], [V])
                self.assertEqual(len(j.rb()), 1)
                self.assertEqual(j.state()['last_window'], WID)
                j.archived(lines)


@needs_container
class NothingElseRejects(unittest.TestCase):
    def test_a_close_that_did_not_roll_back_rejects_nothing(self):
        """CLASS target-old (the candidate's image still runs), target-failed (the rollback failed), pre, none, other;
        and a legacy rollback with no `why`: nothing rejected (the state's list, the file), connect_only unchanged,
        no ROLLED BACK; the candidate as each class leaves it (test_apply.py)."""
        for cls, why in (('target-old', 'r1'), ('target-failed', 'r1'), ('pre', 'r1-connect'), ('none', 'r1'),
                         ('other', 'r1'), ('target-running', None)):
            with self.subTest(cls, why=why):
                j = J(self, fam={'candidate': CAND, 'previous': OLDL, 'connect_only': {V: {'n': 1, 'at': T0}}})
                if why is None:
                    lines = [l for l in lines_of('rollback', cls, why=None)
                             if not l.startswith(('old-version ', 'target-version ', 'verdict '))]
                    v = ''
                else:
                    lines, v = rollback(why=why, cls=cls)
                stops = {'target-old': 'CI DISABLED', 'other': 'HAND CHANGE'}
                if cls in stops:
                    lines.insert(len(lines) - 2, 'stop %s: planted' % stops[cls])
                j.journal(lines, v)
                j.run('off')
                f = j.fam()
                self.assertEqual(f.get('rejected', []), [])
                self.assertIsNone(j.rejected_file())
                self.assertEqual(f['connect_only'], {V: {'n': 1, 'at': T0}})
                self.assertEqual(j.rb(), [])
                j.archived(lines)


if __name__ == '__main__':
    unittest.main()
