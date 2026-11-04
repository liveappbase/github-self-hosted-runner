"""The CI legs of core/TESTED_JQ: .github/workflows/release-check.yml's jq-linux matrix is exactly TESTED_JQ's ci rows
(version, image, areas), its job name is the one tools/release-check reads on a tag ("jq VERSION (IMAGE)"), each leg
checks that the image's jq prints the row's version, and the hosted macOS job runs the tests with /usr/bin/jq (the
local row), all of tests/ through tools/run-tests. tests/hetzner (linux-docker/'s scripts: no jq, so not a TESTED_JQ
area) runs in the hetzner job, in the images of the ubuntu rows and only those, split into parts by module name: the
parts run every module of tests/hetzner exactly once, in a container (its cells fail rather than skip without one),
and its setup step installs what those cells need. Every jq-linux leg waits for that job and fails unless all of it
passed, so the job tools/release-check reads on a tag passes only when the hetzner cells did. Read as text: the stdlib
has no YAML parser, so the rows keep one fixed shape."""
import os
import re
import unittest

from tests.core.corejq import REPO, tested_rows

WF = os.path.join(REPO, '.github', 'workflows', 'release-check.yml')


def workflow():
    with open(WF) as f:
        return f.read()


def job(name):
    """The text of one job of the workflow: from its `  NAME:` line to the next job's (or the end)."""
    m = re.search(r'^  %s:\n(.*?)(?=^  \S|\Z)' % re.escape(name), workflow(), re.M | re.S)
    return m.group(1) if m else ''


def matrix():
    return re.findall(r'^\s+- \{jq: (\S+), image: "([^"]+)", areas: "([a-z ]+)"\}$', job('jq-linux'), re.M)


def hetzner_matrix(key):
    """The hetzner job's matrix list KEY (image or part): its quoted items, in order."""
    m = re.search(r'^        %s: \[(.*)\]$' % key, job('hetzner'), re.M)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def flat(s):
    if isinstance(s, unittest.TestSuite):
        for t in s:
            yield from flat(t)
    else:
        yield s


def modules(pattern):
    """The modules of tests/hetzner that unittest's discovery loads for PATTERN (-p), as the hetzner job runs it."""
    suite = unittest.TestLoader().discover(os.path.join(REPO, 'tests', 'hetzner'), pattern=pattern, top_level_dir=REPO)
    return sorted(set(type(t).__module__ for t in flat(suite)))


def split(parts):
    """[] when the parts run every module the plain line runs (unittest's default pattern) exactly once, else what
    is wrong: a module no part runs, one that two parts run, a part that runs none."""
    every, seen, why = modules('test*.py'), {}, []
    for p in parts:
        got = modules(p)
        if not got:
            why.append('the part %s runs no module' % p)
        for m in got:
            seen.setdefault(m, []).append(p)
    why += ['%s: no part runs it' % m for m in every if m not in seen]
    why += ['%s: run by %s' % (m, ' and '.join(ps)) for m, ps in sorted(seen.items()) if len(ps) > 1]
    why += ['%s: a part runs it, the plain line does not' % m for m in sorted(seen) if m not in every]
    return why


class Workflow(unittest.TestCase):
    def test_the_jq_linux_matrix_is_the_ci_rows(self):
        want = sorted((v, w[3:], ' '.join(a)) for v, a, w in tested_rows() if w.startswith('ci:'))
        self.assertEqual(sorted(matrix()), want)

    def test_the_hetzner_job_runs_in_the_ubuntu_rows_images_and_only_those(self):
        ubuntu = sorted(i for _, i, _ in matrix() if i.startswith('ubuntu:'))
        self.assertTrue(ubuntu, 'no ubuntu row')
        self.assertEqual(sorted(hetzner_matrix('image')), ubuntu)
        j = job('hetzner')
        self.assertIn('    name: hetzner ${{ matrix.part }} (${{ matrix.image }})\n', j)
        # in the image's container: the cells fail rather than skip on a Linux root without /.dockerenv (support.py)
        self.assertIn('    container: ${{ matrix.image }}\n', j)
        self.assertIn("        run: python3 -I -m unittest discover -s tests/hetzner -t . -p '${{ matrix.part }}' -v\n",
                      j)
        # what those cells need beyond the tests' own: jq, curl, openssl and the system's CA bundle (support.py)
        self.assertIn('DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends ca-certificates curl git '
                      'jq openssl python3\n', j)

    def test_the_parts_run_every_module_of_tests_hetzner_exactly_once(self):
        parts = hetzner_matrix('part')
        self.assertGreaterEqual(len(parts), 2, parts)
        self.assertEqual(split(parts), [])
        # the controls: the check finds a module no part runs, one run twice, and a part that runs none
        self.assertTrue([w for w in split(parts[1:]) if w.endswith('no part runs it')])
        self.assertTrue([w for w in split(parts + parts[:1]) if ' and ' in w])
        self.assertIn('the part nothing*.py runs no module', split(parts + ['nothing*.py']))

    def test_every_jq_row_waits_for_the_hetzner_job_and_fails_unless_all_of_it_passed(self):
        """A tag's release-check reads the jq rows' results by name, not the hetzner job's: so each jq row passes only
        when every hetzner leg did. It runs its own tests even when one did not (!cancelled()), then fails."""
        j = job('jq-linux')
        self.assertIn('    needs: hetzner\n', j)
        self.assertIn('    if: ${{ !cancelled() }}\n', j)
        steps = j.split('\n    steps:\n', 1)[1]
        self.assertTrue(steps.rstrip('\n').endswith('\n        run: test "${{ needs.hetzner.result }}" = success'),
                        'the last step of each jq row is the hetzner check')
        self.assertNotIn('hetzner', ' '.join(a for _, _, a in matrix()), 'a jq row runs tests/hetzner itself')

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
