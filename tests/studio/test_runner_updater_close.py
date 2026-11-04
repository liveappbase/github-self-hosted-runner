"""How a candidate and the keep after its ACCEPT end, when a pass or a person ends them (S3b-4b fix r1):

- `retry FAMILY` on a held JOBS FAIL ON THE NEW IMAGE of the candidate IS the person's ACCEPT (PLAN D7, 11-04): the same
  writes as KEEP's ACCEPT (the recipe baseline, `previous` kept until now + 7 days, the candidate closed), so the next
  pass holds no STOP. `retry` on another STOP accepts nothing (NO EVIDENCE: the candidate stays under observation).
- R1's verdict `stop` with PINNED RUNNER RETIRED (PLAN D6, D7): the pass holds the STOP, closes the candidate with no
  restart and rejects the version, so a newer release is due alone. SHIM REFUSED keeps the candidate.
- ONE OPEN RELEASE, AFTER ACCEPT (PLAN D6, 11-04): the 7 days after an ACCEPT do not hold the next switch. The next
  switch window SUPERSEDES the keep: its old image (the accepted one) becomes `previous`, and the image the keep held
  leaves the protected list once that window has closed, and is deleted then by its recorded name (DELETION, written to
  the actions journal first). A window that does not switch supersedes nothing.

The rigs are test_runner_updater_pass's (the pass's clock from RU_TEST_NOW; every other command keeps the real clock
unless it reads the same `now` line).
"""
import os
import time
import unittest

from tests.studio.test_runner_updater import config
from tests.studio.test_runner_updater_pass import (CLOCK, DAY, HOUR, MIN, armed, family, gh_rig, job, latest, pass_,
                                                   switched_and_open, utc)
from tests.studio.test_runner_updater_recover import assert_runs, n_disable, stops
from tests.studio.test_runner_updater_rollback import NEW, V2, switched
from tests.studio.test_runner_updater_state import KEEP, fam, lines_of, state, stop
from tests.studio.test_runner_updater_window import FAM, OLD, V0, Win, today

WEEK = 7 * DAY


def retry(w, at):
    return w.r.cmd('retry', FAM, ok=False, env={'RU_TEST_NOW': str(at)})


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
