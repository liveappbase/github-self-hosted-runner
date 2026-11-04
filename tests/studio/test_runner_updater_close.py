"""How a candidate and the keep after its ACCEPT end, when a pass or a person ends them (S3b-4b fix r1):

- `retry FAMILY` on a held JOBS FAIL ON THE NEW IMAGE of the candidate IS the person's ACCEPT (PLAN D7, 11-04): the same
  writes as KEEP's ACCEPT (the recipe baseline, `previous` kept until now + 7 days, the candidate closed, the pin by D2's
  ONE RULE: a right pin stays byte-equal, a removed one is written, journaled first), so the next pass holds no STOP.
  `retry` on another STOP accepts nothing (NO EVIDENCE: the candidate stays under observation), and neither does it
  while R1's rollback verdict stands for the candidate's window (the core state's: S3b-4b r2 P1-1): it clears the
  STOPs it names, says why it accepts nothing, and the next pass with CI up rolls back.
- R1's verdict `stop` with PINNED RUNNER RETIRED (PLAN D6, D7): the pass holds the STOP, closes the candidate with no
  restart and rejects the version, so a newer release is due alone. SHIM REFUSED keeps the candidate. The STOP clears
  itself when a newer version's switch window closes on the family with the newer image running (PLAN D7, 11-04); a
  window that goes back to its backup leaves it.
- ONE OPEN RELEASE, AFTER ACCEPT (PLAN D6, 11-04): the 7 days after an ACCEPT do not hold the next switch. The next
  switch window SUPERSEDES the keep: its old image (the accepted one) becomes `previous`, and the image the keep held
  leaves the protected list once that window has closed, and is deleted then by its recorded name (DELETION, written to
  the actions journal first). A window that does not switch supersedes nothing, and a switched close supersedes ONLY a
  keep (no candidate, a back_until before the window): a rebuild of an open candidate keeps `previous`, the image
  before the candidate's version, and deletes nothing (S3b-4b r2 P2-2).

The rigs are test_runner_updater_pass's (the pass's clock from RU_TEST_NOW; every other command keeps the real clock
unless it reads the same `now` line).
"""
import os
import time
import unittest

from tests.studio.test_runner_updater import config
from tests.studio.test_runner_updater_pass import (CLOCK, DAY, HOUR, MIN, armed, failures, family, gh_rig, job, latest,
                                                   pass_, switched_and_open, utc)
from tests.studio.test_runner_updater_recover import assert_runs, n_disable, stops
from tests.studio.test_runner_updater_rollback import NEW, V2, actions, switched
from tests.studio.test_runner_updater_state import KEEP, fam, lines_of, state, stop
from tests.studio.test_runner_updater_window import FAM, KILLED, OLD, V0, Win, today

WEEK = 7 * DAY


def retry(w, at):
    return w.r.cmd('retry', FAM, ok=False, env={'RU_TEST_NOW': str(at)})


def raw(path):
    with open(path, 'rb') as f:
        return f.read()


def jobs_fail(test):
    """switched_and_open, then a failed job: the pass at t1 + 72 h holds JOBS FAIL ON THE NEW IMAGE. -> w, that time"""
    w, t1 = switched_and_open(test)
    w.r.append_log(job('failed'))
    res = pass_(w, t1 + KEEP)
    test.assertEqual(stops(w), ['JOBS FAIL ON THE NEW IMAGE'], res.stdout)
    return w, t1 + KEEP


class TestRetryOnJobsFailAccepts(unittest.TestCase):
    """PLAN D7 (11-04): on JOBS FAIL ON THE NEW IMAGE, `retry FAMILY` IS the person's ACCEPT."""

    def test_jobs_fail_then_retry_then_the_next_pass_holds_no_stop(self):
        w, t1 = switched_and_open(self)
        out = family(w)['candidate']['lines']['mac-a']
        w.r.append_log(job('failed'))
        res = pass_(w, t1 + KEEP)
        self.assertEqual(stops(w), ['JOBS FAIL ON THE NEW IMAGE'], res.stdout)
        at = t1 + KEEP + 10 * MIN
        res = retry(w, at)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('runner-updater: retry %s: accepted runner %s: JOBS FAIL ON THE NEW IMAGE is your call, and retry '
                      'keeps the image; `runner-updater back %s` restores %s until %s\n'
                      % (FAM, V2, FAM, OLD, utc(at + WEEK)), res.stdout)
        f = family(w)
        self.assertEqual((f['candidate'], f['previous'], f['back_until'], f['recipe'], f['stops']),
                         (None, {'mac-a': OLD}, at + WEEK, w.recipe, []))
        self.assertEqual(lines_of(w.u.protected), [OLD])   # previous, kept for `back`; out runs (the config names it)
        res = pass_(w, at + HOUR)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn('holds STOP', res.stdout)
        self.assertIn('\nstatus: ok (0 STOPs)\n', res.stdout)
        self.assertIn('\nkeep %s: none (no candidate under observation)' % FAM, res.stdout)
        self.assertEqual((stops(w), family(w)['candidate']), ([], None))
        self.assertTrue(os.path.exists(os.path.join(w.vms, out)))

    def test_control_retry_on_no_evidence_accepts_nothing(self):
        w, t1 = switched_and_open(self)
        pass_(w, t1 + KEEP)
        self.assertEqual(stops(w), ['NO EVIDENCE'])
        res = retry(w, t1 + KEEP + 10 * MIN)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn('accepted', res.stdout)
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['back_until'], f['stops']), (V2, None, []))

    def test_control_a_jobs_fail_of_another_version_accepts_nothing(self):
        held = [stop(FAM, 'JOBS FAIL ON THE NEW IMAGE', version='2.338.9', detail={'text': 'x'})]
        w = Win(self, cfg=config((('mac-a', NEW),)), extra_rewrites=[CLOCK],
                s=state(on=True, families={FAM: switched(stops=held)}, images={OLD: V0, NEW: V2}))
        res = retry(w, int(time.time()))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn('accepted', res.stdout)
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['back_until'], f['stops']), (V2, None, []))


class TestRetryWhileR1RollbackIsDue(unittest.TestCase):
    """S3b-4b r2 P1-1. PLAN D6: no STOP disarms R1 while a candidate is live, and KEEP never accepts while R1's verdict
    holds. So while R1's rollback verdict stands for the candidate's window (the core state's verdict, r1.jq's own,
    never `r1_since`), `retry` on JOBS FAIL ON THE NEW IMAGE accepts nothing: it clears the STOPs it names (ROLLBACK
    FAILED too), the candidate stays, it says why, and the next pass with CI up rolls back (runner-disable once, ROLLED
    BACK). The control, JOBS FAIL with no R1 verdict, accepts: TestRetryOnJobsFailAccepts."""

    def r1_due(self):
        """jobs_fail, then three counted failures: the next pass's R1 says rollback. -> w, the time of that pass"""
        w, t = jobs_fail(self)
        w.r.append_log(failures(hour=11))
        return w, t + HOUR

    def no_accept_then_rolls_back(self, w, at, cleared, then=None):
        res = retry(w, at)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn('accepted runner', res.stdout)
        self.assertIn('runner-updater: retry %s: runner %s is not accepted: R1\'s rollback is due for it (set mac-a, 3 '
                      'counted failures), and no STOP cancels it: the next pass with CI up rolls it back\n'
                      % (FAM, V2), res.stdout)
        self.assertIn('runner-updater: retry %s: cleared %s;' % (FAM, cleared), res.stdout)
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['back_until'], f['stops'], 'r1_since' in f),
                         (V2, None, [], False))
        if then:
            then()
        n = n_disable(w)
        res = pass_(w, at + HOUR)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('runner-updater: pass: rolled back %s: it runs %s again\n' % (FAM, OLD), res.stdout)
        self.assertNotIn('ROLLBACK FAILED', res.stdout)
        self.assertEqual((n_disable(w) - n, stops(w), family(w)['candidate']), (1, ['ROLLED BACK'], None))
        assert_runs(self, w, config((('mac-a', OLD),)).encode())

    def test_jobs_fail_then_r1_then_rollback_failed_then_retry_accepts_nothing_and_the_next_pass_rolls_back(self):
        w, t = self.r1_due()
        w.validate('unknown')                     # every try pending: after 2 h, ROLLBACK FAILED
        res = pass_(w, t)
        self.assertIn('runner-updater: rollback pending: pre-window validate (pre) is UNKNOWN', res.stdout)
        res = pass_(w, t + 2 * HOUR)
        self.assertEqual(sorted(stops(w)), ['JOBS FAIL ON THE NEW IMAGE', 'ROLLBACK FAILED'], res.stdout)
        w.validate('pass')
        self.no_accept_then_rolls_back(w, t + 2 * HOUR + 10 * MIN, 'JOBS FAIL ON THE NEW IMAGE, ROLLBACK FAILED')

    def test_jobs_fail_then_r1_while_a_person_disabled_ci_then_retry_accepts_nothing_and_the_next_pass_rolls_back(self):
        w, t = self.r1_due()
        os.remove(w.r.flag)                       # a person ran runner-disable: the rollback is pending
        res = pass_(w, t)
        self.assertIn('runner-updater: rollback pending: CI disabled by a person', res.stdout)
        self.assertEqual(stops(w), ['JOBS FAIL ON THE NEW IMAGE'])
        self.no_accept_then_rolls_back(w, t + 10 * MIN, 'JOBS FAIL ON THE NEW IMAGE',
                                       then=lambda: w.sb.write(w.r.flag, ''))   # the person runs runner-enable

    def test_only_a_verdict_of_the_candidates_own_window_holds_retry(self):
        # the core state's evidence is the candidate's window only when its version, lines and switch (closed_at) are
        # the candidate's (core/lib/core.jq, same_window): a verdict of another switch of the same lines holds nothing
        closed = int(time.time()) - DAY
        fails = [{'t': '2026-11-01 11:0%d:00' % i, 'c': False, 'x': 'tart clone failed'} for i in (1, 2, 3)]
        for at, accepted in ((closed, False), (closed - HOUR, True)):
            with self.subTest(verdict_of_the_switch_at=at):
                held = [stop(FAM, 'JOBS FAIL ON THE NEW IMAGE', detail={'text': 'x'})]
                ev = {'version': V2, 'lines': {'mac-a': NEW}, 'closed_at': at, 'open': False, 'stops': [],
                      'verdict': {'verdict': 'rollback', 'set': 'mac-a', 'failures': fails, 'connect_only': False}}
                w = Win(self, cfg=config((('mac-a', NEW),)), extra_rewrites=[CLOCK],
                        s=state(on=False, families={FAM: fam(candidate={'version': V2, 'lines': {'mac-a': NEW},
                                                                         'closed_at': closed},
                                                             previous={'mac-a': OLD}, stops=held)},
                                images={OLD: V0, NEW: V2}, core={'format': 1, 'families': {FAM: ev}}))
                res = retry(w, int(time.time()))
                self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
                self.assertEqual('accepted runner %s' % V2 in res.stdout, accepted, res.stdout)
                self.assertEqual('is not accepted: R1\'s rollback is due' in res.stdout, not accepted, res.stdout)
                self.assertEqual(family(w)['candidate'] is None, accepted)


class TestRetryAcceptKeepsThePinRule(unittest.TestCase):
    """S3b-4b r2 P2-1. retry's ACCEPT applies D2's ONE RULE as KEEP's does (its cells: TestAccept, the controls): it
    reads the family's sets (the families file) first, so a pin that follows the rule stays byte-equal with no journal
    line, and a pin removed before (off, then on) is written, `pin-write` in the actions journal first."""

    def test_a_pin_that_follows_the_rule_stays_byte_equal(self):
        w, t = jobs_fail(self)
        before = raw(w.pin)
        self.assertEqual(before, ('%s %s\n' % (V2, w.tsha)).encode())
        res = retry(w, t + 10 * MIN)
        self.assertIn('runner-updater: retry %s: accepted runner %s: ' % (FAM, V2), res.stdout)
        self.assertNotIn('the pin', res.stdout)
        self.assertEqual(raw(w.pin), before)
        self.assertEqual(actions(w), [])

    def test_a_pin_removed_before_is_written_and_journaled_first(self):
        w, t = jobs_fail(self)
        self.assertEqual(w.r.cmd('off').returncode, 0)
        self.assertEqual(w.r.cmd('on').returncode, 0)
        self.assertFalse(os.path.exists(w.pin))
        self.assertEqual(actions(w), ['pin-remove %s %s %s' % (FAM, V2, w.tsha)])   # off's
        out = family(w)['candidate']['lines']['mac-a']
        res = retry(w, t + 10 * MIN)
        self.assertIn('runner-updater: retry %s: accepted runner %s: ' % (FAM, V2), res.stdout)
        self.assertIn('runner-updater: retry: the pin %s: %s (the version of %s, which the config runs)\n'
                      % (w.pin, V2, out), res.stdout)
        self.assertEqual(raw(w.pin), ('%s %s\n' % (V2, w.tsha)).encode())
        self.assertEqual(actions(w), ['pin-remove %s %s %s' % (FAM, V2, w.tsha), 'pin-write %s %s %s' % (FAM, V2, w.tsha)])

    def test_a_kill_right_after_the_pin_write_line_leaves_no_pin(self):
        # the journal line comes first: a kill right after it has not written the pin yet
        w, t = jobs_fail(self)
        self.assertEqual(w.r.cmd('off').returncode, 0)
        self.assertEqual(w.r.cmd('on').returncode, 0)
        res = w.r.cmd('retry', FAM, ok=False, env={'RU_TEST_NOW': str(t + 10 * MIN), 'RU_KILL_AT': 'pin-write'})
        self.assertEqual(res.returncode, KILLED, res.stdout + res.stderr)
        self.assertEqual(actions(w)[-1], 'pin-write %s %s %s' % (FAM, V2, w.tsha))
        self.assertFalse(os.path.exists(w.pin))


RETIRED_LOG = ('2026-11-01 05:00:10 ERRO mac-a: Failed to start runner, will retry\n'
               '  error=\n'
               '  │ failed to start runner: runner process exited on runner-00000001 right after connecting to GitHub; '
               'runner log:\n'
               '  │ √ Connected to GitHub\n'
               '  │ \n'
               "  │ Current runner version: '2.339.0'\n"
               '  │ 2026-11-01 05:00:00Z: Listening for Jobs\n'
               '  │ Runner version v2.339.0 is deprecated and cannot receive messages.\n'
               '  │ Exiting runner...\n'
               '2026-11-01 05:02:30 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n'
               '2026-11-01 05:02:31 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n')
SHIM_LOG = ('2026-11-01 05:00:10 ERRO mac-a: Failed to start runner, will retry error="failed to start runner: '
            'liveapp-ci-shim: REFUSE free disk below the floor: 93 GiB < 100 GiB"\n'
            '2026-11-01 05:02:30 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n'
            '2026-11-01 05:02:31 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n')
V3 = '2.340.0'


class TestPinnedRunnerRetired(unittest.TestCase):
    """PLAN D6, D7: PINNED RUNNER RETIRED closes the candidate (no restart), rejects its version, and a newer release
    proceeds alone. The control: SHIM REFUSED keeps the candidate (D7: not closed, nothing rejected, a newer release
    does not proceed)."""

    def test_retired_closes_the_candidate_and_a_newer_release_is_due(self):
        w = armed(self, log=RETIRED_LOG, gh=True)
        before, n = w.config_now(), n_disable(w)
        t = int(time.time())
        res = pass_(w, t)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn('\nr1 %s: stop (PINNED RUNNER RETIRED: ' % FAM, res.stdout)
        self.assertIn('runner-updater: pass: %s holds STOP PINNED RUNNER RETIRED (runner %s): the candidate is closed '
                      'with no restart, and runner %s is rejected: a newer release is due alone\n' % (FAM, V2, V2),
                      res.stdout)
        f = family(w)
        (s,) = f['stops']
        self.assertEqual((f['candidate'], f['rejected'], s['stop'], s['version']),
                         (None, [V2], 'PINNED RUNNER RETIRED', V2))
        self.assertTrue(s['detail']['reason'].startswith('set mac-a: failed to start runner: '), s)   # r1's reason
        self.assertEqual((n_disable(w), w.config_now()), (n, before))   # no restart, no edit
        st = w.status()
        self.assertIn('runner-updater: family %s: no candidate' % FAM, st)
        self.assertIn('runner-updater: STOP %s PINNED RUNNER RETIRED: known true; candidate closed: yes; version '
                      'rejected: yes; a newer release proceeds alone: yes' % FAM, st)
        res = pass_(w, t + HOUR)                          # held once
        self.assertEqual((res.returncode, stops(w)), (0, ['PINNED RUNNER RETIRED']), res.stdout)
        latest(w, v=V3, published=t - 3 * DAY)
        res = pass_(w, t + 2 * HOUR)
        self.assertIn('runner-updater: pass: %s is due: runner %s\n' % (FAM, V3), res.stdout)
        self.assertIn('runner-updater: pass: switched %s to ' % FAM, res.stdout)
        self.assertEqual(family(w)['candidate']['version'], V3)

    def retired_then_newer_due(self):
        """the pass holds PINNED RUNNER RETIRED of V2; GitHub's latest release is then V3 (3 days old). -> w, t"""
        w = armed(self, log=RETIRED_LOG, gh=True)
        t = int(time.time())
        pass_(w, t)
        self.assertEqual(stops(w), ['PINNED RUNNER RETIRED'])
        latest(w, v=V3, published=t - 3 * DAY)
        return w, t

    def test_a_newer_window_that_closes_switched_clears_the_stop(self):
        # PLAN D7 (11-04): it clears itself when a newer version's switch window closes on the family with the newer
        # image running
        w, t = self.retired_then_newer_due()
        res = pass_(w, t + HOUR)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('runner-updater: pass: switched %s to ' % FAM, res.stdout)
        self.assertIn('runner-updater: window: STOP PINNED RUNNER RETIRED (runner %s) is cleared: the family runs '
                      'runner %s\n' % (V2, V3), res.stdout)
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['stops'], f['rejected']), (V3, [], [V2]))
        st = w.status()
        self.assertNotIn('PINNED RUNNER RETIRED', st)
        self.assertIn('\nstatus: ok (0 STOPs)\n', st)

    def test_control_a_newer_window_that_goes_back_to_its_backup_keeps_the_stop(self):
        w, t = self.retired_then_newer_due()
        w.validate('refuse', call=3)              # the window's validate after its edit: the backup goes back
        res = pass_(w, t + HOUR)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn('runner-updater: STOP check failed: after the edit: validate (post) is NON-API', res.stdout)
        self.assertNotIn('is cleared', res.stdout)
        f = family(w)
        self.assertEqual((f['candidate'], sorted(stops(w))), (None, ['PINNED RUNNER RETIRED', 'check failed']))
        self.assertIn('runner-updater: STOP %s PINNED RUNNER RETIRED: known true' % FAM, w.status())

    def test_control_a_switched_close_of_the_retired_version_itself_keeps_the_stop(self):
        # only a NEWER version clears it: a rebuild of the image the family runs (the retired version) switches, and
        # the STOP stays
        w = armed(self, log=RETIRED_LOG, gh=True)
        pass_(w, int(time.time()))
        self.assertEqual(stops(w), ['PINNED RUNNER RETIRED'])
        w.sb.write(w.pin, '%s %s\n' % (V2, 'b' * 64))
        res = w.run('rebuild')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn('is cleared', res.stdout)
        self.assertEqual((family(w)['candidate']['version'], stops(w)), (V2, ['PINNED RUNNER RETIRED']))

    def test_control_shim_refused_keeps_the_candidate(self):
        w = armed(self, log=SHIM_LOG, gh=True)
        t = int(time.time())
        res = pass_(w, t)
        self.assertIn('\nr1 %s: stop (SHIM REFUSED: ' % FAM, res.stdout)
        self.assertNotIn('PINNED RUNNER RETIRED', res.stdout)
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['rejected']), (V2, []))
        latest(w, v=V3, published=t - 3 * DAY)
        res = pass_(w, t + HOUR)
        self.assertIn('runner-updater: pass: %s is not due: an open candidate (runner %s)' % (FAM, V2), res.stdout)
        self.assertEqual(n_disable(w), 0)


def accepted_win(test, images=None):
    """mac-golden ACCEPTED a day ago: it runs NEW (runner V0), its previous image OLD is kept for `back` until 6 days
    from now; its recipe baseline is its files' recipe; GitHub's latest release V2 is 3 days old: the family is due"""
    w = Win(test, cfg=config((('mac-a', NEW),)), extra_rewrites=[CLOCK])
    w.recipe = gh_rig(w)
    w.until = int(time.time()) + 6 * DAY
    w.u.put(state(on=True, families={FAM: fam(recipe=w.recipe, previous={'mac-a': OLD}, back_until=w.until)},
                  images=images if images is not None else {OLD: '2.338.1', NEW: V0}))
    w.sb.write(os.path.join(w.vms, NEW), '')
    w.tsha = latest(w)
    # the protected list, as runner-disable runs (the window is open then)
    w.hook('disable-hook.1', '/bin/cp %s %s\n' % (w.u.protected, os.path.join(w.scn, 'protected-in-window')))
    return w


class TestSupersede(unittest.TestCase):
    """PLAN D6 AFTER ACCEPT and ONE OPEN RELEASE (11-04): an accepted family inside its 7 days and a DUE release: the
    switch starts. Its window keeps both images in the protected list while it is open; when it closes switched, its
    old image (the accepted one) is `previous` (the `back` target until the new ACCEPT + 7 days), and the image the
    keep held is no longer protected and is deleted by its recorded name, written to the actions journal first."""

    def test_an_accepted_family_inside_its_7_days_switches_and_supersedes_the_keep(self):
        w = accepted_win(self)
        res = pass_(w)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        out = 'liveapp-mac-golden-' + today()
        self.assertIn('runner-updater: pass: %s is due: runner %s\n' % (FAM, V2), res.stdout)
        self.assertIn('runner-updater: pass: switched %s to %s (runner %s)\n' % (FAM, out, V2), res.stdout)
        # while the window was open, the list held the keep's image and the window's old image
        inside = lines_of(os.path.join(w.scn, 'protected-in-window'))
        self.assertIn(OLD, inside)
        self.assertIn(NEW, inside)
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['candidate']['lines'], f['previous'], f['back_until']),
                         (V2, {'mac-a': out}, {'mac-a': NEW}, None))
        # after its close: OLD is not protected, and is deleted by its recorded name (journaled first)
        self.assertEqual(lines_of(w.u.protected), sorted([NEW, out]))
        self.assertIn('runner-updater: window: deleted %s (the previous image of %s, which this window superseded)\n'
                      % (OLD, FAM), res.stdout)
        self.assertFalse(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertEqual(lines_of(w.u.actions), ['delete ' + OLD])
        # `back` now restores the newer accepted image
        res = w.run('back')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        assert_runs(self, w, config((('mac-a', NEW),)).encode())

    def test_control_a_window_that_does_not_switch_supersedes_nothing(self):
        w = accepted_win(self)
        w.put('build-fail')
        res = pass_(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP check failed: build: ', res.stdout)
        f = family(w)
        self.assertEqual((f['candidate'], f['previous'], f['back_until']), (None, {'mac-a': OLD}, w.until))
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertFalse(os.path.exists(w.u.actions))
        self.assertIn(OLD, lines_of(w.u.protected))

    def test_a_rebuild_of_an_open_candidate_supersedes_nothing(self):
        # S3b-4b r2 P2-2: HAND CHANGE's line is `rebuild FAMILY`. A switched close supersedes ONLY a keep (no candidate,
        # a back_until before the window): here `previous` stays OLD, the image before the candidate's version (the
        # rollback target and `back`'s), and nothing is deleted
        w = Win(self, cfg=config((('mac-a', NEW),)), extra_rewrites=[CLOCK],
                s=state(on=True, families={FAM: switched()}, images={OLD: V0, NEW: V2}))
        w.sb.write(os.path.join(w.vms, NEW), '')
        w.sb.write(w.pin, '%s %s\n' % (V2, 'b' * 64))
        res = w.run('rebuild')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        out = 'liveapp-mac-golden-' + today()
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['candidate']['lines'], f['previous'], f['back_until']),
                         (V2, {'mac-a': out}, {'mac-a': OLD}, None))
        self.assertNotIn('superseded', res.stdout)
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertTrue(os.path.exists(os.path.join(w.vms, NEW)))
        self.assertEqual([l for l in actions(w) if l.startswith('delete ')], [])
        self.assertIn(OLD, lines_of(w.u.protected))
        # `back` restores the image before the candidate's version
        res = w.run('back')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        assert_runs(self, w, config((('mac-a', OLD),)).encode())

    def test_control_a_superseded_image_the_updater_did_not_record_stays(self):
        w = accepted_win(self, images={NEW: V0})
        res = pass_(w)
        self.assertIn('runner-updater: pass: switched %s to ' % FAM, res.stdout)
        self.assertIn('runner-updater: window: %s stays: the state does not record it as an image of %s' % (OLD, FAM),
                      res.stdout)
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertNotIn(OLD, lines_of(w.u.protected))


if __name__ == '__main__':
    unittest.main()
