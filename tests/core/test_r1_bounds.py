"""core/r1.jq's state stays bounded on a long-running busy host (Codex r2 F4, Opus r2 F3, F5): each set keeps only
what can still matter — the failures and proofs of life of the last SETTLE (120 s) of log time and the newest proof
before the oldest failure that is not settled yet, the settled failures since that proof (a third is R1), the Tart
starts of runners not yet removed (a later `reason=exited` with no jobId still takes one back), and the settled
failures such a start alone keeps apart (they are R1 if it is taken back). Everything older than that proof is settled
and judged. So the entries per set are bounded by what the set logs in SETTLE and by its runners alive at once, never
by the hours, and a pass's time does not grow with them. Controls: a same-second proof at the pruned edge, a genuine
run of three after hours of pruned history, a Tart start taken back many passes later, the D6 AMENDMENT's late
unknown-runner line (test_r1.py's Settle cells).

A pass's time does not grow either: r1's time is a function of its inputs, the state and a pass's text (the same size
every pass here), so the deterministic form of that invariant is the whole state's size, every field, under a stated
bound for the 72 h (no clock is read: a machine that slows between two timings is no defect; Codex r3 F2, Opus r3 F4)."""
import json
import unittest

from tests.core.test_r1 import (DOCKER_CREATE, OTHER, Run, exited_warn, failed, fam, removed, scaling, started, tail,
                                 unknown)

LISTS = ('fails', 'proofs', 'starts', 'exits', 'unknowns')
# the whole state's size for the 72 h of the flaky Tart and Docker sets, every field (compact JSON, sorted keys):
# measured 1812-1820 bytes on every pass; with no prune (r2's code on this workload) 4726 at the first, +3670 a pass
STATE_BYTES = 2048
# a set keeps at most this many Tart starts of runners not yet removed (core/README.md, "The state stays bounded")
STARTS_MAX = 16


def flaky(base, set_):
    """Opus r2 F3: every 60 s a counted start failure, and 30 s after each the retry's job completed (R1 is right to
    stay silent), 600 s of log. -> [(log second, record)]"""
    err = OTHER if set_.startswith('mac') else DOCKER_CREATE
    out = []
    for i in range(0, 600, 60):
        out += [(base + i, failed(base + i, err, set_)),
                (base + i + 30, removed(base + i + 30, 'runner-%08x' % (base + i), 'job-completed', set_=set_))]
    return out


def healthy(base, set_):
    """Tart: a runner starts and completes a job every 30 s, 600 s of log."""
    out = []
    for i in range(0, 600, 30):
        n = 'runner-%08x' % (base + i)
        out += [(base + i, started(base + i, n, set_)), (base + i + 20, removed(base + i + 20, n, 'job-completed', set_=set_))]
    return out


def amendment(base, set_):
    """Docker: every 60 s the real exited / unknown-runner pair (hz-cut.log:55-59's shape), and a job completed."""
    out = []
    for i in range(0, 600, 60):
        n = 'runner-%08x' % (base + i)
        out += [(base + i, removed(base + i, n, 'exited', job=False, set_=set_)),
                (base + i + 13, unknown(base + i + 13, n, set_, 'started')),
                (base + i + 13, unknown(base + i + 13, n, set_, 'completed')),
                (base + i + 40, removed(base + i + 40, 'runner-%08x' % (base + i + 1), 'job-completed', set_=set_))]
    return out


def text(*events):
    """The sets' records as one log writes them: in log-time order (a stable sort keeps each set's own order)."""
    return ''.join(r for _, r in sorted(sum(events, []), key=lambda e: e[0]))


def sizes(out, fam_, set_):
    s = out['state']['families'][fam_]['sets'].get(set_, {})
    return {k: len(s.get(k, [])) for k in LISTS}


def state_bytes(state):
    """The whole state's size, every field: compact JSON with sorted keys (one spelling whatever jq printed)."""
    return len(json.dumps(state, sort_keys=True, separators=(',', ':')).encode('utf-8'))


class Bounded(unittest.TestCase):
    def test_opus_r2_f3_the_flaky_sets_stay_bounded_for_72_h_and_the_whole_state_stays_under_its_bound(self):
        # Tart and Docker, one pass per 600 s of the glue's clock and of log time, 432 passes. The bound: what a set logs
        # in SETTLE (two failures and two proofs here) plus the held record's second, the newest proof before them and
        # the settled failures since it: at most 4 failures and 4 proofs (r2's code: 10 more of each per pass). And the
        # whole state, every field, under STATE_BYTES on every pass: a pass's time does not grow (the module's header)
        fams = {'fx': fam('tart', ('mac-a',)), 'fy': fam('docker', ('linux-b',), image='img-y')}
        r = Run(self, fams)
        for k in range(432):
            out = r.go(text(flaky(1000 + 600 * k, 'mac-a'), flaky(1000 + 600 * k, 'linux-b')))
            self.assertLessEqual(state_bytes(out['state']), STATE_BYTES, k)
            for f, s in (('fx', 'mac-a'), ('fy', 'linux-b')):
                n = sizes(out, f, s)
                self.assertLessEqual(n['fails'], 4, (k, f, n))
                self.assertLessEqual(n['proofs'], 4, (k, f, n))
                self.assertEqual((n['starts'], n['exits']), (0, 0), (k, f, n))
                self.assertEqual(out['families'][f]['verdict'], 'none', (k, f))

    def test_codex_r2_f4_a_busy_set_stays_bounded(self):
        # every 10 s a counted failure and, 1 s later, a job completed; 30 pairs and a scaling record per pass. The
        # bound: SETTLE / 10 s + 1 entries of each (the unsettled failures of the last 120 s of log, and their proofs
        # with the newest one before them): 13 (today's code: 30, 60, 90)
        r = Run(self)
        seen = []
        for b in range(10):
            log = ''.join(failed((b * 30 + i) * 10, OTHER) + removed((b * 30 + i) * 10 + 1, 'runner-%08x' % (b * 30 + i),
                                                                     'job-completed') for i in range(30))
            out = r.go(log + scaling((b + 1) * 300))
            n = sizes(out, 'fx', 'mac-a')
            self.assertLessEqual(n['fails'], 13, (b, n))
            self.assertLessEqual(n['proofs'], 13, (b, n))
            self.assertEqual((out['families']['fx']['verdict'], out['families']['fx']['pending']), ('none', None), b)
            seen.append(n)
        self.assertEqual(seen[2], seen[9])
        # control: a genuine run of three after the pruned hours is R1
        out = r.go(failed(3100, OTHER) + failed(3110, OTHER) + failed(3120, OTHER) + tail(3300))
        self.assertEqual((out['families']['fx']['verdict'], len(out['families']['fx']['failures'])), ('rollback', 3))

    def test_every_pattern_stays_bounded_and_stops_growing(self):
        # 40 passes of the healthy Tart set (starts), the D6 AMENDMENT pairs (exits) and the flaky sets
        fams = {'fa': fam('tart', ('mac-a',)), 'fb': fam('tart', ('mac-b',), image='img-b'),
                'fc': fam('docker', ('linux-c',), image='img-c'), 'fd': fam('docker', ('linux-d',), image='img-d')}
        gens = (('fa', 'mac-a', healthy), ('fb', 'mac-b', flaky), ('fc', 'linux-c', amendment), ('fd', 'linux-d', flaky))
        r = Run(self, fams)
        at = {}
        for k in range(40):
            out = r.go(text(*[g(1000 + 600 * k, s) for _, s, g in gens]))
            for f, s, _ in gens:
                n = sizes(out, f, s)
                self.assertLessEqual(max(n.values()), 8, (k, f, n))
                self.assertEqual(out['families'][f]['verdict'], 'none', (k, f, out['families'][f]))
                if k in (19, 39):
                    at[(f, k)] = n
        for f, _, _ in gens:
            self.assertEqual(at[(f, 19)], at[(f, 39)], f)

    def test_opus_r4_f6_starts_whose_runner_is_never_removed_stay_under_the_cap(self):
        # Opus r4 F6: when RemoveInstance fails runscaler writes no `Runner removed` line, so a Tart start is never
        # removed. Tart, 40 passes: each pass a runner starts, another completes a job, and the first one exits (its
        # WARN) with its cleanup failed (no removal line). The starts kept grow to STARTS_MAX and stop there, the
        # oldest going first
        r = Run(self)
        names = []
        for k in range(40):
            base = 1000 + 600 * k
            names.append('runner-%08x' % (0xb000 + k))
            out = r.go(started(base, names[-1]) + removed(base + 20, 'runner-%08x' % (0xc000 + k), 'job-completed')
                       + exited_warn(base + 300, names[-1]) + scaling(base + 500))
            self.assertEqual(len(out['state']['families']['fx']['sets']['mac-a']['starts']), min(k + 1, STARTS_MAX), k)
            self.assertEqual(out['families']['fx']['verdict'], 'none', k)
        self.assertEqual(sorted(s['n'] for s in out['state']['families']['fx']['sets']['mac-a']['starts']),
                         names[-STARTS_MAX:])
        # control: the cleanup works (each runner is removed `reason=exited`): no start is kept
        r = Run(self)
        for k in range(20):
            base, nm = 1000 + 600 * k, 'runner-%08x' % (0xb000 + k)
            out = r.go(started(base, nm) + removed(base + 20, 'runner-%08x' % (0xc000 + k), 'job-completed')
                       + exited_warn(base + 300, nm) + removed(base + 301, nm, 'exited', job=False) + scaling(base + 500))
            self.assertEqual((len(out['state']['families']['fx']['sets']['mac-a']['starts']),
                              out['families']['fx']['verdict']), (0, 'none'), k)


class StillDecides(unittest.TestCase):
    def test_a_start_beyond_the_cap_is_read_as_confirmed_the_oldest_first(self):
        # Tart: failures 10, 20; runner R0 started 25; a failure 30; then N more starts (40, 41, ...), none removed; the
        # log moves on; then R0 is removed `reason=exited` with no jobId (that takes its start back) and the exit is
        # final. With STARTS_MAX more starts R0's is the oldest beyond the cap: it is read as confirmed, a proof of life
        # between 20 and 30 -> no R1 (only a take-back is lost, which delays R1). With one fewer it is still a start:
        # the exit takes it back -> R1 on 10, 20, 30. The oldest by log time: also when R0's start is written late (less
        # than SETTLE out of order) and read after the others
        def last(n, late):
            r0, more = started(25, 'runner-00000000'), ''.join(started(40 + i, 'runner-%08x' % (i + 1)) for i in range(n))
            r = Run(self)
            r.go(failed(10, OTHER) + failed(20, OTHER) + (failed(30, OTHER) + more + r0 if late else r0 + failed(30, OTHER) + more)
                 + tail(300))
            return r.fx(removed(400, 'runner-00000000', 'exited', job=False) + tail(600))
        for late in (False, True):
            with self.subTest(late=late):
                self.assertEqual(last(STARTS_MAX, late)['verdict'], 'none')
                self.assertEqual([f['t'][-2:] for f in last(STARTS_MAX - 1, late)['failures']][:3], ['10', '20', '30'])

    def test_a_same_second_proof_at_the_pruned_edge_is_between(self):
        r = Run(self)
        r.go(failed(10, OTHER) + removed(100, 'runner-0000beef', 'job-completed') + failed(100, OTHER) + tail(300))
        out = r.go(failed(400, OTHER) + failed(410, OTHER) + tail(600))
        self.assertEqual(out['families']['fx']['verdict'], 'none')
        # control: the proof a second earlier is not between the failure of second 100 and the next two
        r = Run(self)
        r.go(failed(10, OTHER) + removed(99, 'runner-0000beef', 'job-completed') + failed(100, OTHER) + tail(300))
        out = r.go(failed(400, OTHER) + failed(410, OTHER) + tail(600))
        self.assertEqual(out['families']['fx']['verdict'], 'rollback')

    def test_unsettled_failures_before_a_newer_proof_stay(self):
        # failures 10 and 20 are read with a job completed at 25 after them, not yet settled; a failure of second 24
        # written late (inside SETTLE) joins them: no proof between 10, 20 and 24 -> R1
        r = Run(self)
        r.go(failed(10, OTHER) + failed(20, OTHER) + removed(25, 'runner-0000beef', 'job-completed') + scaling(40)
             + scaling(41))
        out = r.go(failed(24, OTHER) + tail(300))
        self.assertEqual([f['t'][-2:] for f in out['families']['fx']['failures']], ['10', '20', '24'])
        # control: the late failure is of second 25, the proof's own: between
        r = Run(self)
        r.go(failed(10, OTHER) + failed(20, OTHER) + removed(25, 'runner-0000beef', 'job-completed') + scaling(40)
             + scaling(41))
        self.assertEqual(r.fx(failed(25, OTHER) + tail(300))['verdict'], 'none')

    def docker_f3(self):
        d = {'fx': fam('docker', ('linux-b',))}
        return (d, lambda s: failed(s, DOCKER_CREATE, 'linux-b'),
                lambda s: removed(s, 'runner-0000cafe', 'job-completed', set_='linux-b'), lambda s: scaling(s, 'linux-b'))

    def test_opus_r3_f3_a_failure_written_out_of_order_joins_its_run(self):
        # Docker fx on linux-b: failures 10, 20; the log moves on (150 settles them); a job completed at 160; a record of
        # 160. The failure of 159 is written less than SETTLE out of order, after the job completed of 160, and read in
        # the next pass: a record a pass reads may be up to SETTLE older than the newest one read, so nothing that a
        # failure still to come could join goes. The same R1 as the records in order, or in one pass
        d, F, J, S = self.docker_f3()
        for name, p1, p2 in (('in order', F(10) + F(20) + S(150) + F(159) + J(160) + S(160) + S(161), tail(400, 'linux-b')),
                             ('out of order', F(10) + F(20) + S(150) + J(160) + S(160), F(159) + tail(400, 'linux-b')),
                             ('out of order, a record later', F(10) + F(20) + S(150) + J(160) + S(160) + S(161),
                              F(159) + tail(400, 'linux-b')),
                             ('one pass', F(10) + F(20) + S(150) + J(160) + S(160) + F(159) + S(161), tail(400, 'linux-b'))):
            with self.subTest(name):
                r = Run(self, d)
                self.assertEqual(r.fx(p1)['verdict'], 'none')
                self.assertEqual([f['t'][-5:] for f in r.fx(p2)['failures']], ['00:10', '00:20', '02:39'])

    def test_the_prune_point_is_settle_behind_the_newest_record_read(self):
        # the edge: the newest record read is of 278, so a failure of 159 may still come (119 s out of order) -> R1
        d, F, J, S = self.docker_f3()
        r = Run(self, d)
        self.assertEqual(r.fx(F(10) + F(20) + S(150) + J(160) + S(278) + S(279))['verdict'], 'none')
        self.assertEqual([f['t'][-5:] for f in r.fx(F(159) + tail(400, 'linux-b'))['failures']], ['00:10', '00:20', '02:39'])
        # control: once a record of 280 is read (SETTLE past the proof of 160), what is before that proof goes: a
        # failure of 159 read now would be more than SETTLE out of order, which SETTLE rests on never happening (read so,
        # it is a log clock that stepped back: an evidence gap, test_r1.py ClockStepBack)
        r = Run(self, d)
        r.fx(F(10) + F(20) + S(150) + J(160) + S(280) + S(281))
        self.assertEqual(len(r.state['families']['fx']['sets']['linux-b']['fails']), 0)
        self.assertEqual(r.fx(F(159) + tail(400, 'linux-b'))['verdict'], 'none')

    def test_two_runs_a_tart_start_keeps_apart_stay_apart_from_each_other(self):
        # Tart: failures 10, 15, runner A started 20, a failure 22, a job completed 25; failures 30, 35, runner B started
        # 40, a failure 42, a job completed 45. Both runs stay (a start may yet be taken back), and so does the proof
        # between them: 22, 30 and 35 are no run of three
        r = Run(self)
        r.go(failed(10, OTHER) + failed(15, OTHER) + started(20, 'runner-000000aa') + failed(22, OTHER)
             + removed(25, 'runner-0000cafe', 'job-completed') + failed(30, OTHER) + failed(35, OTHER)
             + started(40, 'runner-000000bb') + failed(42, OTHER) + removed(45, 'runner-0000d00d', 'job-completed')
             + tail(200))
        for k in range(3):
            self.assertEqual(r.fx(text(flaky(1000 + 600 * k, 'mac-a')))['verdict'], 'none', k)
        # control: B taken back, its run of three is R1
        out = r.fx(removed(3000, 'runner-000000bb', 'exited', job=False) + tail(3200))
        self.assertEqual([f['t'][-2:] for f in out['failures']], ['30', '35', '42'])

    def opus_f5(self, removal):
        """Opus r2 F5: Tart, failures 10, 15, runner X started 20, a failure 22, a job completed 25 (runner Y), all
        settled; then 20 passes of the flaky pattern on the set; then X is removed."""
        r = Run(self)
        out = r.go(failed(10, OTHER) + failed(15, OTHER) + started(20, 'runner-0000beef') + failed(22, OTHER)
                   + removed(25, 'runner-0000cafe', 'job-completed') + tail(200))
        self.assertEqual(out['families']['fx']['verdict'], 'none')
        for k in range(20):
            self.assertEqual(r.fx(text(flaky(1000 + 600 * k, 'mac-a')))['verdict'], 'none', k)
        return r.fx(removal + tail(13400))

    def test_opus_r2_f5_a_tart_start_taken_back_many_passes_later_is_r1(self):
        out = self.opus_f5(removed(13200, 'runner-0000beef', 'exited', job=False))
        self.assertEqual(out['verdict'], 'rollback', out)
        self.assertEqual([f['t'][-2:] for f in out['failures']], ['10', '15', '22'])

    def test_control_the_start_confirmed_by_a_job_completed_is_no_r1(self):
        self.assertEqual(self.opus_f5(removed(13200, 'runner-0000beef', 'job-completed'))['verdict'], 'none')


if __name__ == '__main__':
    unittest.main()
