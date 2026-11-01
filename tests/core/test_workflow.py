"""The CI legs of core/TESTED_JQ: .github/workflows/release-check.yml's jq-linux matrix is exactly TESTED_JQ's ci rows
(version, image, areas), its job name is the one tools/release-check reads on a tag ("jq VERSION (IMAGE)"), each leg
checks that the image's jq prints the row's version, and the hosted macOS job runs the tests with /usr/bin/jq (the
local row). Read as text: the stdlib has no YAML parser, so the rows keep one fixed shape."""
import os
import re
import unittest

from tests.core.corejq import REPO, tested_rows

WF = os.path.join(REPO, '.github', 'workflows', 'release-check.yml')


def workflow():
    with open(WF) as f:
        return f.read()


class Workflow(unittest.TestCase):
    def test_the_jq_linux_matrix_is_the_ci_rows(self):
        rows = re.findall(r'^\s+- \{jq: (\S+), image: "([^"]+)", areas: "([a-z ]+)"\}$', workflow(), re.M)
        want = sorted((v, w[3:], ' '.join(a)) for v, a, w in tested_rows() if w.startswith('ci:'))
        self.assertEqual(sorted(rows), want)

    def test_the_job_name_release_check_reads(self):
        self.assertIn('    name: jq ${{ matrix.jq }} (${{ matrix.image }})\n', workflow())

    def test_each_leg_checks_its_jq_version_and_runs_with_it(self):
        w = workflow()
        self.assertIn('test "$(/usr/bin/jq --version)" = "${{ matrix.jq }}"', w)
        self.assertIn('run: for a in ${{ matrix.areas }}; do python3 -I -m unittest discover -s tests/$a -t . -v || exit 1; done',
                      w)

    def test_the_hosted_mac_runs_the_tests_with_the_local_row(self):
        local = [w[len('local:'):] for v, a, w in tested_rows() if w.startswith('local:')]
        self.assertEqual(local, ['/usr/bin/jq'])
        m = re.search(r'- name: tests\n\s+working-directory: src\n\s+env:\n\s+JQ: (\S+)\n', workflow())
        self.assertTrue(m, 'the tests step of the macOS job names JQ')
        self.assertEqual(m.group(1), '/usr/bin/jq')


if __name__ == '__main__':
    unittest.main()
