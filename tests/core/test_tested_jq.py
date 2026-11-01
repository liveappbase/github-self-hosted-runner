"""core/TESTED_JQ, the ONE list of the jq builds the core and the watchdog are tested with: its rows parse, and the jq
these tests run under is one of its rows for the area `core` (so a run under an untested jq is RED, never green)."""
import re
import unittest

from tests.core.corejq import jq_version, tested_rows


class TestedJq(unittest.TestCase):
    def test_rows_parse(self):
        rows = tested_rows()
        self.assertTrue(rows)
        for version, areas, where in rows:
            self.assertRegex(version, r'^jq-[0-9]+\.[0-9]+(\.[0-9]+)?(-[a-z]+)?$')
            self.assertTrue(set(areas) <= {'core', 'watchdog'} and areas, areas)
            self.assertRegex(where, r'^(local:/[^\s]+|ci:[a-z0-9.-]+:[a-z0-9.-]+)$')
        versions = [r[0] for r in rows]
        self.assertEqual(len(versions), len(set(versions)), 'one row per version')

    def test_the_jq_under_test_is_a_tested_core_row(self):
        v = jq_version()
        core = [r[0] for r in tested_rows() if 'core' in r[1]]
        self.assertIn(v, core, 'the jq under test prints %r: not a core row of core/TESTED_JQ %r' % (v, core))

    def test_the_watchdog_rows_include_every_core_row(self):
        rows = tested_rows()
        for version, areas, _ in rows:
            if 'core' in areas:
                self.assertIn('watchdog', areas, version)


if __name__ == '__main__':
    unittest.main()
