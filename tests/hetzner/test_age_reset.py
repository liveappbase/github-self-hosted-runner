"""E-14 BY RECURRING PASSES, the reset (S2b-3c-2 B4a item 10; r3 Opus F3 (c)): the small set is read not ready by the
passes (one each 10 min of the fake clock) for 20 h, ready at one pass, then not ready again; the release eligible 23 h
after the first not-ready read. At 25 h after that first read the pass's `up` still waits for idle ("not ready"): the
age restarted at the ready read, and no window starts. Its control, a set never read ready, is excused at 24 h:
test_recurring_passes.py (the same rig, Passes). (Named for its CI part, test_[a-b]*.py:
.github/workflows/release-check.yml.)
"""
import unittest

from tests.hetzner.support import needs_container
from tests.hetzner.test_pass_switch import WAITS
from tests.hetzner.test_recurring_passes import HOUR, STEP, Passes
from tests.hetzner.test_release_due import SMALL


@needs_container
class ReadyReadRestartsTheAge(unittest.TestCase):
    def test_a_ready_read_restarts_the_age(self):
        x = Passes(self)
        for k in range(25 * HOUR // STEP + 1):
            r = x.run(k, {'ready': k == 20 * HOUR // STEP})
        self.assertIn(WAITS, r.stdout)
        self.assertIn('%s: not ready' % SMALL, r.stdout)
        self.assertNotIn('excused from readiness only', r.stdout)
        self.assertEqual(x.g.ups(), [])


if __name__ == '__main__':
    unittest.main()
