"""core/keep.jq — KEEP (PLAN D6): 72 h after the evidence window opened (the switch, or the last gap), at least one job
completed `result=succeeded` with provenance and no verdict -> accept; completions but none succeeded -> jobs-fail
(JOBS FAIL ON THE NEW IMAGE); none -> no-evidence, which heals itself when a job succeeds; a standing R1 verdict or
STOP -> held. The end-to-end cells feed r1.jq's own state into keep.jq. Every trigger has a control."""
import unittest

from tests.core.corejq import ok
from tests.core.test_r1 import NOW, P, Run, fam, facts, removed, scaling

H = 3600
KEEP = 72 * H


def ev(since=NOW, open_=True, succeeded=0, failed=0, canceled=0, other=0, verdict=None, stops=(), version='2.339.0'):
    return {'version': version, 'lines': {'mac-a': 'img-new'}, 'open': open_, 'since': since if open_ else None,
            'gaps': 0, 'succeeded': succeeded, 'failed': failed, 'canceled': canceled, 'other': other, 'sets': {},
            'verdict': verdict, 'stops': list(stops)}


def keep(test, e, now, families=None):
    st = {'format': 1, 'families': {'fx': e} if e is not None else {}}
    return ok(test, 'keep', state=st, facts=facts(families or {'fx': fam()}), now=now)['families']['fx']


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
