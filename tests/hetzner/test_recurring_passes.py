"""E-14 BY RECURRING PASSES (S2b-3c-2 B4a item 10; the slice plan's E-14 with its r3 FOLD, r3 Opus F3 (c); B3's note):
the pass's own `up` excuses a set that is not ready for 24 h, and the age is the one the PASSES grow: each pass (one
each 10 min of the fake clock) runs core/idle.jq on its own /healthz pair and keeps `not_ready_since` in the core state,
and the switch's idle pair reads that pass's copy. The release becomes eligible 23 h after the small set was first read
not ready (the passes before it end at DUE's step 7, which keeps them cheap); the main set idle.

- 23 h to 24 h: each pass's `up` waits for idle ("not ready"); at the first pass 24 h after the first not-ready read the
  set is excused, but `busy 1` on it still keeps the pool from idle (its counts count); the next pass switches.
- r3 Opus F3 (c), the reset (the ready read that starts the age again): test_age_reset.py (its own CI part: each cell
  is about 150 passes).
Every cell runs the real scripts (support.Pool, a throwaway container) and the updater as RS_USER on the fake clock.
(Named for its CI part, test_rec*.py: .github/workflows/release-check.yml.)
"""
import unittest

from tests.hetzner.support import healthz, iso, needs_container, tarball
from tests.hetzner.test_pass_switch import WAITS, G
from tests.hetzner.test_release_due import DAY, NOT, SMALL, V

STEP = 600
HOUR = 3600


class Passes:
    """G's rig, but the release V published so that it is eligible 23 h after T0, the first pass; NOT_READY(k): the
    small set's readiness at pass k (T0 + k * 10 min)."""

    def __init__(self, test):
        self.t = test
        self.g = G(test, age=3 * DAY)
        self.t0 = self.g.p.clock()
        self.g.p.gh.release(V, tarball(V), latest=True, published=iso(self.t0 + 23 * HOUR - 2 * DAY))

    def run(self, k, small):
        g = self.g
        g.p.curl['healthz'] = healthz(**{SMALL: small})
        g.p.clock(now=self.t0 + k * STEP)
        return g.go()


@needs_container
class ReadinessAge(unittest.TestCase):
    def test_a_set_not_ready_24_h_by_the_passes_is_excused_and_busy_still_counts(self):
        x = Passes(self)
        first = 24 * HOUR // STEP                        # the first pass 24 h after the first not-ready read
        for k in range(first + 2):
            busy = k == first
            r = x.run(k, {'ready': False, 'busy': 1 if busy else 0})
            if k * STEP < 23 * HOUR:
                self.assertIn(NOT + 'release v%s is younger than 2 days' % V, r.stdout)
                continue
            if k < first:
                self.assertIn(WAITS, r.stdout, k)
                self.assertIn('%s: not ready' % SMALL, r.stdout)
                self.assertEqual(x.g.ups(), [], k)
                continue
            if busy:
                self.assertIn(WAITS, r.stdout, k)
                self.assertIn('%s: not ready since' % SMALL, r.stdout, 'excused from readiness only')
                self.assertIn('busy 1', r.stdout)
                self.assertEqual(x.g.ups(), [])
                continue
            self.assertEqual(x.g.fam()['candidate']['version'], V, r.stdout[-3000:])
            self.assertIn('excused from readiness only', r.stdout)
            self.assertEqual(len(x.g.ups()), 1)


if __name__ == '__main__':
    unittest.main()
