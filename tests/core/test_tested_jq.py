"""core/TESTED_JQ, the ONE list of the jq builds the core and the watchdog are tested with: its rows parse, and the jq
these tests run under is one of its rows for the area `core` (so a run under an untested jq is RED, never green)."""
import os
import re
import unittest

from tests.core.corejq import REPO, jq_version, tested_rows


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

    def test_every_documented_test_line_names_the_local_rows_jq(self):
        # a maintainer's line that runs the unit tests runs them under the first jq on PATH unless it names JQ, and a
        # Homebrew jq first on PATH is no row: the line is RED there (Opus r1 F11, r2 F6). Every *.md line outside
        # tests/ that runs the tests (`unittest discover`, or the parallel runner `python3 -I tools/run-tests`) names
        # `JQ=` with a local row's path (the CI lines run in containers and live in the workflow file, not in a doc)
        local = ['JQ=' + r[2][len('local:'):] for r in tested_rows() if r[2].startswith('local:')]
        self.assertTrue(local)
        run = r'unittest discover|python3 [^`]*tools/run-tests'
        found = []
        for d, dirs, files in os.walk(REPO):
            dirs[:] = [x for x in dirs if x not in ('.git', 'tests')]
            for fn in files:
                if fn.endswith('.md'):
                    p = os.path.join(d, fn)
                    with open(p, encoding='utf-8') as f:
                        for n, line in enumerate(f, 1):
                            where = '%s:%d' % (os.path.relpath(p, REPO), n)
                            spans = [m.group(0) for m in re.finditer(r'`[^`]*(?:%s)[^`]*`' % run, line)]
                            found += [(where, s) for s in spans]
                            if len(re.findall(run, line)) > sum(len(re.findall(run, s)) for s in spans):
                                found.append((where, 'not in a `command`: ' + line.strip()[:120]))
        self.assertTrue(found, 'no documented test line found: the sweep reads nothing')
        bad = [(w, cmd) for w, cmd in found if not any(cmd.startswith('`' + j + ' ') for j in local)]
        self.assertEqual(bad, [], 'a documented test line does not name %s' % ' or '.join(local))

    def test_the_watchdog_rows_include_every_core_row(self):
        rows = tested_rows()
        for version, areas, _ in rows:
            if 'core' in areas:
                self.assertIn('watchdog', areas, version)


if __name__ == '__main__':
    unittest.main()
