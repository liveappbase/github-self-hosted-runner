"""core/r1.jq's state stays bounded on a long-running busy host (Codex r2 F4, Opus r2 F3, F5): each set keeps only
what can still matter — the failures and proofs of life of the last SETTLE (120 s) of log time and the newest proof
before the oldest failure that is not settled yet, the settled failures since that proof (a third is R1), the Tart
starts of runners not yet removed (a later `reason=exited` with no jobId still takes one back), and the settled
failures such a start alone keeps apart (they are R1 if it is taken back). Everything older than that proof is settled
and judged. So the entries per set are bounded by what the set logs in SETTLE and by its runners alive at once, never
by the hours, and a pass's time does not grow with them. Controls: a same-second proof at the pruned edge, a genuine
run of three after hours of pruned history, a Tart start taken back many passes later, the D6 AMENDMENT's late
unknown-runner line (test_r1.py's Settle cells)."""
import json
import os
import subprocess
import time
import unittest

from tests.core.corejq import CORE, jq, tmpdir
from tests.core.test_r1 import (DOCKER_CREATE, OTHER, Run, facts, failed, fam, removed, scaling, started, tail,
                                unknown)

LISTS = ('fails', 'proofs', 'starts', 'exits')


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


def timed(test, r, log, fams):
    """The best of three r1 calls on the same inputs (a pure function of them): its seconds."""
    d = tmpdir(test)
    paths = {}
    for name, text in (('state', json.dumps(r.state)), ('log', log), ('healthz', ''),
                       ('facts', json.dumps(facts(fams)))):
        paths[name] = os.path.join(d, name)
        with open(paths[name], 'w', encoding='utf-8') as f:
            f.write(text)
    argv = [jq(), '-n', '-L', os.path.join(CORE, 'lib'), '-f', os.path.join(CORE, 'r1.jq'),
            '--slurpfile', 'state', paths['state'], '--rawfile', 'log', paths['log'],
            '--slurpfile', 'healthz', paths['healthz'], '--slurpfile', 'facts', paths['facts'], '--arg', 'now', str(r.now + 600)]
    best = None
    for _ in range(3):
        t0 = time.monotonic()
        p = subprocess.run(argv, capture_output=True, text=True)
        dt = time.monotonic() - t0
        test.assertEqual(p.returncode, 0, p.stderr)
        best = dt if best is None else min(best, dt)
    return best


class Bounded(unittest.TestCase):
    def test_opus_r2_f3_the_flaky_sets_stay_bounded_for_72_h_and_a_pass_does_not_slow(self):
        # Tart and Docker, one pass per 600 s of the glue's clock and of log time, 432 passes. The bound: what a set logs
        # in SETTLE (two failures and two proofs here) plus the held record's second, the newest proof before them and
        # the settled failures since it: at most 4 failures and 4 proofs (today's code: 10 more of each per pass)
        fams = {'fx': fam('tart', ('mac-a',)), 'fy': fam('docker', ('linux-b',), image='img-y')}
        r = Run(self, fams)
        t1 = None
        for k in range(432):
            log = text(flaky(1000 + 600 * k, 'mac-a'), flaky(1000 + 600 * k, 'linux-b'))
            if k == 6:
                t1 = timed(self, r, log, fams)                  # the pass of the first hour
            out = r.go(log)
            for f, s in (('fx', 'mac-a'), ('fy', 'linux-b')):
                n = sizes(out, f, s)
                self.assertLessEqual(n['fails'], 4, (k, f, n))
                self.assertLessEqual(n['proofs'], 4, (k, f, n))
                self.assertEqual((n['starts'], n['exits']), (0, 0), (k, f, n))
                self.assertEqual(out['families'][f]['verdict'], 'none', (k, f))
        t72 = timed(self, r, text(flaky(1000 + 600 * 432, 'mac-a'), flaky(1000 + 600 * 432, 'linux-b')), fams)
        self.assertLessEqual(t72, 2 * t1 + 0.25, 'a pass at 72 h takes %.3f s, at 1 h %.3f s' % (t72, t1))

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


class StillDecides(unittest.TestCase):
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
