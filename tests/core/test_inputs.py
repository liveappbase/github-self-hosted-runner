"""The core's inputs fail closed, on EVERY entry point (idle, r1, keep, status): rc != 0 (the glue does nothing this pass
and says so) when `now` is not an integer epoch in [1700000000, 4102444800) — 1e999, a clock in milliseconds and the
1e9 of a stopped clock included — and when a process observation of facts.proc (either read) has a pid that is not a
positive integer or a start that is not a number: such a read must never prove ownership or provenance. Controls: the
range's own ends, and valid numeric observations that keep provenance."""
import unittest

from tests.core.corejq import ok, run
from tests.core.test_r1 import NOW, P, facts, fam

PROGRAMS = ('idle', 'r1', 'keep', 'status')


def call(test, prog, now=NOW, f=None):
    f = f if f is not None else facts({'fx': fam()})
    return run(test, prog, state=[], log='', healthz=[], facts=f, now=now)


class Now(unittest.TestCase):
    def test_a_now_out_of_range_or_not_whole_is_refused_by_every_program(self):
        for now in ('1e999', '1e9', str(NOW * 1000), str(NOW) + '.5', '1699999999', '4102444800', 'nan', '-1'):
            for prog in PROGRAMS:
                rc, _, err = call(self, prog, now=now)
                self.assertNotEqual(rc, 0, (prog, now))
                self.assertIn('%s: now' % prog, err, (prog, now))

    def test_control_the_ends_of_the_range_and_an_ordinary_epoch_decide(self):
        for now in ('1700000000', '4102444799', str(NOW)):
            for prog in PROGRAMS:
                rc, _, err = call(self, prog, now=now)
                self.assertEqual(rc, 0, (prog, now, err))


class Proc(unittest.TestCase):
    BAD = ({'start': 'bad'}, {'pid': 0, 'start': P['start']}, {'pid': -4, 'start': P['start']},
           {'pid': 4.5, 'start': P['start']}, {'pid': '4242', 'start': P['start']}, {'pid': None, 'start': P['start']},
           {'pid': 4242}, {'pid': 4242, 'start': 'bad'}, {'pid': 4242, 'start': None}, {}, 'P', 7)

    def test_a_malformed_observation_in_either_read_is_refused_by_every_program(self):
        for bad in self.BAD:
            for which in ('before', 'after'):
                f = facts({'fx': fam()})
                f['proc'][which] = bad
                for prog in PROGRAMS:
                    rc, _, err = call(self, prog, f=f)
                    self.assertNotEqual(rc, 0, (prog, which, bad))
                    self.assertIn('%s: facts' % prog, err, (prog, which, bad))

    def test_codex_f4_start_bad_in_both_reads_proves_nothing(self):
        # Codex r1 F4: {"start": "bad"} in both reads, the config naming the candidate: two passes and a success must
        # not give an evidence window (and so no ACCEPT); the core refuses the facts instead
        f = facts({'fx': fam()}, before={'start': 'bad'})
        rc, _, _ = run(self, 'r1', state=[], log='', healthz=[], facts=f, now=NOW)
        self.assertNotEqual(rc, 0)

    def test_control_valid_numeric_observations_keep_provenance(self):
        out = ok(self, 'r1', state=[], log='', healthz=[], facts=facts({'fx': fam()}), now=NOW)
        self.assertTrue(out['families']['fx']['open'], out)
        # and no process at all (null reads) is a valid observation that proves nothing
        out = ok(self, 'r1', state=[], log='', healthz=[], facts=facts({'fx': fam()}, before=None, after=None), now=NOW)
        self.assertFalse(out['families']['fx']['open'], out)


if __name__ == '__main__':
    unittest.main()
