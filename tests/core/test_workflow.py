"""The CI legs of core/TESTED_JQ: .github/workflows/release-check.yml's jq-linux matrix is exactly TESTED_JQ's ci rows
(version, image, areas), its job name is the one tools/release-check reads on a tag ("jq VERSION (IMAGE)"), each leg
checks that the image's jq prints the row's version, and the hosted macOS job runs the tests with /usr/bin/jq (the
local row), all of tests/ through tools/run-tests. The ubuntu rows, and only they, also run tests/hetzner
(linux-docker/'s scripts: no jq, so not a TESTED_JQ area), and the setup step installs what those cells need. Read as
text: the stdlib has no YAML parser, so the rows keep one fixed shape."""
import os
import re
import unittest

from tests.core.corejq import REPO, tested_rows

WF = os.path.join(REPO, '.github', 'workflows', 'release-check.yml')


JQ_FREE = ('hetzner',)   # areas a row also runs that use no jq, so they are no TESTED_JQ area


def workflow():
    with open(WF) as f:
        return f.read()


def matrix():
    return re.findall(r'^\s+- \{jq: (\S+), image: "([^"]+)", areas: "([a-z ]+)"\}$', workflow(), re.M)


class Workflow(unittest.TestCase):
    def test_the_jq_linux_matrix_is_the_ci_rows(self):
        rows = [(v, i, ' '.join(x for x in a.split() if x not in JQ_FREE)) for v, i, a in matrix()]
        want = sorted((v, w[3:], ' '.join(a)) for v, a, w in tested_rows() if w.startswith('ci:'))
        self.assertEqual(sorted(rows), want)

    def test_the_ubuntu_rows_and_only_they_run_the_linux_docker_cells(self):
        rows = matrix()
        self.assertTrue([i for _, i, _ in rows if i.startswith('ubuntu:')], 'no ubuntu row')
        for v, i, a in rows:
            self.assertEqual('hetzner' in a.split(), i.startswith('ubuntu:'), (v, i, a))
        # what those cells need beyond the tests' own: curl, openssl and the system's CA bundle (tests/hetzner/support.py)
        self.assertIn('DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends ca-certificates curl git '
                      'jq openssl python3\n', workflow())

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
        m = re.search(r'- name: tests\n\s+working-directory: src\n\s+env:\n\s+JQ: (\S+)\n\s+run: (.*)\n', workflow())
        self.assertTrue(m, 'the tests step of the macOS job names JQ')
        self.assertEqual(m.group(1), '/usr/bin/jq')
        # every area of tests/, through the parallel runner (the same tests as the plain discover line), at its default
        # -j: the Mac's CPU count
        self.assertEqual(m.group(2), 'python3 -I tools/run-tests -v')


if __name__ == '__main__':
    unittest.main()
