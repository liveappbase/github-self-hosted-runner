"""core/keep.jq — KEEP (PLAN D6): 72 h after the evidence window opened (the switch, or the last gap), at least one job
completed `result=succeeded` with provenance and no verdict -> accept; completions but none succeeded -> jobs-fail
(JOBS FAIL ON THE NEW IMAGE); none -> no-evidence, which heals itself when a job succeeds; a standing R1 verdict or
STOP -> held, r1's own or one the glue holds in facts.stops (any but NO EVIDENCE). The end-to-end cells feed r1.jq's
own state into keep.jq. Every trigger has a control."""
import unittest

from tests.core.corejq import ok, run
from tests.core.test_r1 import NOW, OTHER, P, Run, failed, fam, facts, removed, scaling

H = 3600
KEEP = 72 * H


def ev(since=NOW, open_=True, succeeded=0, failed=0, canceled=0, other=0, verdict=None, stops=(), version='2.339.0'):
    return {'version': version, 'lines': {'mac-a': 'img-new'}, 'open': open_, 'since': since if open_ else None,
            'gaps': 0, 'succeeded': succeeded, 'failed': failed, 'canceled': canceled, 'other': other, 'sets': {},
            'verdict': verdict, 'stops': list(stops)}


def keep(test, e, now, families=None, stops=None):
    st = {'format': 1, 'families': {'fx': e} if e is not None else {}}
    f = facts(families or {'fx': fam()})
    if stops is not None:
        f['stops'] = stops
    return ok(test, 'keep', state=st, facts=f, now=now)['families']['fx']


def held(name, family='fx'):
    return {'family': family, 'stop': name, 'version': '2.339.0', 'user': 'ci', 'detail': {}}


# PLAN D7's STOPs that a person must answer: every STOP but NO EVIDENCE, which heals itself
PERSON_STOPS = ('check failed', 'ROLLED BACK', 'PINNED RUNNER RETIRED', 'JOBS FAIL ON THE NEW IMAGE', 'ROLLBACK FAILED',
                'CI DISABLED', 'POOL DOWN', 'HAND CHANGE', 'recipe changed', 'NO BASELINE', 'NO IDLE', 'untested jq',
                'SHIM REFUSED', 'A STOP THIS CORE DOES NOT KNOW')


class HeldStops(unittest.TestCase):
    """A STOP the glue holds for the family (facts.stops) means no ACCEPT; only NO EVIDENCE heals itself (PLAN D6, D7:
    JOBS FAIL's lines are `back` or `retry` to keep it; Codex r1 F6, Opus r1 F1)."""

    def test_opus_f1_a_held_jobs_fail_and_a_later_success_is_not_accept(self):
        # 73 h, 1 success, 3 failed, JOBS FAIL ON THE NEW IMAGE held by the glue
        r = keep(self, ev(since=NOW - 73 * H, succeeded=1, failed=3), NOW, stops=[held('JOBS FAIL ON THE NEW IMAGE')])
        self.assertEqual(r['verdict'], 'held', r)
        self.assertIn('JOBS FAIL ON THE NEW IMAGE', r['reason'])

    def test_every_stop_but_no_evidence_holds(self):
        for name in PERSON_STOPS:
            r = keep(self, ev(succeeded=2), NOW + KEEP, stops=[held('NO EVIDENCE'), held(name)])
            self.assertNotEqual(r['verdict'], 'accept', name)
            self.assertEqual(r['verdict'], 'held', name)

    def test_control_a_held_no_evidence_heals_with_a_success(self):
        r = keep(self, ev(succeeded=1), NOW + KEEP, stops=[held('NO EVIDENCE')])
        self.assertEqual(r['verdict'], 'accept', r)

    def test_control_another_familys_stop_does_not_hold_this_one(self):
        r = keep(self, ev(succeeded=1), NOW + KEEP, stops=[held('JOBS FAIL ON THE NEW IMAGE', family='fy')])
        self.assertEqual(r['verdict'], 'accept', r)

    def test_stops_that_are_not_a_list_cannot_decide(self):
        for bad in ({'family': 'fx', 'stop': 'HAND CHANGE'}, 'HAND CHANGE', 7):
            f = facts({'fx': fam()})
            f['stops'] = bad
            rc, _, err = run(self, 'keep', state={'format': 1, 'families': {'fx': ev(succeeded=1)}}, facts=f, now=NOW + KEEP)
            self.assertNotEqual(rc, 0, bad)
            self.assertIn('keep: facts.stops', err)


class Keep(unittest.TestCase):
    def test_72h_with_a_success_accepts(self):
        r = keep(self, ev(succeeded=1, failed=3), NOW + KEEP)
        self.assertEqual(r['verdict'], 'accept', r)
        self.assertEqual(r['keep_at'], NOW + KEEP)

    def test_control_a_second_before_72h_observes(self):
        r = keep(self, ev(succeeded=5), NOW + KEEP - 1)
        self.assertEqual(r['verdict'], 'observe')

    def test_completions_none_succeeded_is_jobs_fail(self):
        r = keep(self, ev(failed=4), NOW + KEEP)
        self.assertEqual(r['verdict'], 'jobs-fail', r)
        self.assertEqual((r['completions'], r['succeeded'], r['failed']), (4, 0, 4))

    def test_canceled_jobs_are_not_completions(self):
        self.assertEqual(keep(self, ev(canceled=3), NOW + KEEP)['verdict'], 'no-evidence')
        # control: one failed among them is a completion
        self.assertEqual(keep(self, ev(canceled=3, failed=1), NOW + KEEP)['verdict'], 'jobs-fail')

    def test_another_result_is_a_completion_that_did_not_succeed(self):
        self.assertEqual(keep(self, ev(other=1), NOW + KEEP)['verdict'], 'jobs-fail')

    def test_no_evidence_heals_with_a_later_success(self):
        self.assertEqual(keep(self, ev(), NOW + KEEP + 5 * H)['verdict'], 'no-evidence')
        self.assertEqual(keep(self, ev(succeeded=1), NOW + KEEP + 6 * H)['verdict'], 'accept')

    def test_a_standing_verdict_or_stop_holds(self):
        rb = {'verdict': 'rollback', 'set': 'mac-a', 'failures': [], 'connect_only': True}
        self.assertEqual(keep(self, ev(succeeded=3, verdict=rb), NOW + KEEP)['verdict'], 'held')
        st = [{'stop': 'SHIM REFUSED', 'reason': 'set mac-a: free disk below the floor'}]
        self.assertEqual(keep(self, ev(succeeded=3, stops=st), NOW + KEEP)['verdict'], 'held')

    def test_no_window_counts_from_the_switch_close(self):
        closed = P['start']                                  # fam()'s candidate closed_at
        self.assertEqual(keep(self, ev(open_=False), closed + KEEP)['verdict'], 'no-evidence')
        self.assertEqual(keep(self, ev(open_=False), closed + KEEP - 1)['verdict'], 'observe')
        self.assertEqual(keep(self, None, closed + KEEP)['verdict'], 'no-evidence')

    def test_evidence_of_another_candidate_is_not_used(self):
        r = keep(self, ev(succeeded=3, since=P['start'], version='2.338.0'), P['start'] + KEEP)
        self.assertEqual(r['verdict'], 'no-evidence')

    def test_a_family_with_no_candidate_is_none(self):
        r = keep(self, ev(succeeded=3), NOW + KEEP, families={'fx': dict(fam(), candidate=None)})
        self.assertEqual(r['verdict'], 'none')

    def test_an_unknown_state_format_waits(self):
        out = ok(self, 'keep', state={'format': 7}, facts=facts({'fx': fam()}), now=NOW)
        self.assertEqual(out['verdict'], 'wait')


class EndToEnd(unittest.TestCase):
    """r1.jq's state, pass after pass, then keep.jq on it."""

    def keep_after(self, r, now):
        return ok(self, 'keep', state=r.state, facts=facts(r.families), now=now)['families']['fx']

    def test_a_success_counted_by_r1_accepts_72h_after_the_window_opened(self):
        r = Run(self)                                                    # the window opens at r.now
        opened = r.now
        r.go(removed(10, 'runner-0000beef', 'job-completed') + scaling(20))
        self.assertEqual(self.keep_after(r, opened + KEEP - 1)['verdict'], 'observe')
        self.assertEqual(self.keep_after(r, opened + KEEP)['verdict'], 'accept')

    def test_a_gap_restarts_the_clock_and_the_counts(self):
        r = Run(self)
        opened = r.now
        r.go(removed(10, 'runner-0000beef', 'job-completed') + scaling(20))
        r.go(scaling(30), continuous=False)                              # a gap: the window opens again now
        reopened = r.now
        self.assertEqual(self.keep_after(r, opened + KEEP)['verdict'], 'observe')
        out = self.keep_after(r, reopened + KEEP)
        self.assertEqual((out['verdict'], out['succeeded']), ('no-evidence', 0))

    def test_codex_f3_no_accept_while_an_unsettled_run_can_still_reach_r1(self):
        # a proven success, then three counted failures and no later record: KEEP must not accept; after the settle: R1
        r = Run(self)
        opened = r.now
        r.go(removed(5, 'runner-0000beef', 'job-completed') + failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER))
        k = self.keep_after(r, opened + KEEP)
        self.assertNotEqual(k['verdict'], 'accept', k)
        self.assertIn('R1 may still come', k['reason'])
        out = r.go('', now=r.now + 600)                                 # quiet: the failures settle
        self.assertEqual(out['families']['fx']['verdict'], 'rollback')
        self.assertEqual(self.keep_after(r, opened + KEEP)['verdict'], 'held')

    def test_control_a_same_second_completion_in_the_next_pass_is_no_rollback_and_accepts(self):
        r = Run(self)
        opened = r.now
        r.go(removed(5, 'runner-0000beef', 'job-completed') + failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER))
        self.assertEqual(r.go(removed(30, 'runner-0000cafe', 'job-completed'))['families']['fx']['verdict'], 'none')
        self.assertEqual(r.go('', now=r.now + 600)['families']['fx']['verdict'], 'none')
        k = self.keep_after(r, opened + KEEP)
        self.assertEqual((k['verdict'], k['succeeded']), ('accept', 2))

    def test_control_two_unsettled_failures_cannot_reach_r1_alone(self):
        r = Run(self)
        opened = r.now
        r.go(removed(5, 'runner-0000beef', 'job-completed') + failed(10, OTHER) + failed(20, OTHER) + scaling(25))
        self.assertEqual(self.keep_after(r, opened + KEEP)['verdict'], 'accept')

    def test_a_partial_line_held_after_two_failures_may_be_the_third(self):
        r = Run(self)
        opened = r.now
        third = failed(30, OTHER)
        r.go(removed(5, 'runner-0000beef', 'job-completed') + failed(10, OTHER) + failed(20, OTHER) + third[:12])
        k = self.keep_after(r, opened + KEEP)
        self.assertEqual(k['verdict'], 'observe', k)
        self.assertIn('R1 may still come', k['reason'])

    def test_a_success_without_provenance_is_not_counted(self):
        r = Run(self, opened=False)
        lines = {'mac-a': 'img-old'}
        r.go(lines=lines)
        r.go(removed(10, 'runner-0000beef', 'job-completed') + scaling(20), lines=lines)
        self.assertEqual(self.keep_after(r, P['start'] + KEEP)['verdict'], 'no-evidence')

    def test_a_failed_job_counted_by_r1_is_jobs_fail(self):
        r = Run(self)
        opened = r.now
        r.go(removed(10, 'runner-0000beef', 'job-completed', result='failed') + scaling(20))
        self.assertEqual(self.keep_after(r, opened + KEEP)['verdict'], 'jobs-fail')


if __name__ == '__main__':
    unittest.main()
