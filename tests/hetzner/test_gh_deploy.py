"""H4's deploy and its way back, as a person runs them (the H4 plan's S-1 and S-3, and W2): a release whose image/ changed
is a new image RECIPE. Since W2 (the r2 MODEL M-1) it holds nothing: the pool keeps its image until the next runner
release, which the passes switch to on this recipe (test_recipe_follows.py), and each pass prints the recipe line after
its `hz-docker` line (`hz-docker: the image recipe changed (...)`), writing no STOP. (Until W2 the pass held it as
`STOP recipe changed`, every pass, and wrote no STOP either: K1, issue #6.) (Named for its CI part, test_[c-jv-z]*.py:
.github/workflows/release-check.yml.)

- S-1, TO APPLY IT NOW (a person's lines): Install step 3 (this release's ~/build: its image/), RUN_USER's
  `runner-updater build V` (V the runner the pool runs: its build record of THIS recipe), then RS_USER's
  `runner-updater rebuild hz-docker V` at a quiet time: the pool runs the new image, and `status` shows family
  hz-docker's candidate V on it. Control: rebuild before the build refuses, naming the missing record and RUN_USER's
  build line.
- S-3, THE WAY BACK after S-1, two branches, each command's exit status checked: (a) the new image still runs: Install
  step 3 with the release before's files, then RS_USER's `rebuild hz-docker V` (the release before's record of V still
  names its image): the old image runs, and the next pass prints no recipe line. (b) R1 already rolled the new image
  back (V rejected, STOP ROLLED BACK): Install step 3 with the release before's files, then `retry hz-docker` (status
  names it as that STOP's next step); rebuild has nothing to switch: the old image runs, and the next pass prints no
  recipe line. Control: (b)'s lines without the release before's files: the recipe line remains. The way back after the
  passes switched to a newer release on this recipe (`back hz-docker`, N-2) is test_recipe_follows.TheWayBack.
- The README's H4 section names these lines, in this order (Text, runs anywhere).
Install step 3 is modelled by ~/build/image/ alone (the updater reads a recipe by its hash: the release before's
image/ here is its Dockerfile and install-runner.sh, the Dockerfile's bytes another); Install step 4's download stays in
~/build/dl. RUN_USER's `build V` is modelled by the build record it writes (02-d1.sh's record of V for the recipe of
~/build/image/: test_build.py runs the real 02-d1.sh, test_updater_build.py the real `build`): one host user's state
here is both users' (support.Pool), so RUN_USER's own updater cannot run in the same cell. R1's verdict is planted
(test_verdict.plant_r1: the real core with its hz-docker verdict set to rollback). Every other line is the real
updater as RS_USER (support.Pool, a throwaway container, the fake clock).
"""
import json
import os
import re
import shutil
import unittest

from tests.hetzner.support import REPO, digest, needs_container, ref
from tests.hetzner.test_back import one, readme, section
from tests.hetzner.test_pass_switch import IDLE
from tests.hetzner.test_release_due import CUR, FAM, NOT, OLD, STATE, Due
from tests.hetzner.test_verdict import plant_r1

IMAGE = os.path.join(REPO, 'linux-docker', 'image')
H4 = digest(44)            # RUN_USER's build of CUR for this release's recipe (H4's image)
RECIPE = 'runner-updater: pass: hz-docker: the image recipe changed ('
TITLE = "gh from GitHub's apt repository: this release's image, and the way back"


class Deploy(Due):
    """Due's rig with GitHub's latest release CUR (so nothing newer is due), the pool IDLE, no record yet: the release
    before's image/ in ~/build and RUN_USER's record of CUR on OLD for it (what a host before H4 has)."""

    def __init__(self, test):
        super().__init__(test, base=False, built=False, version=CUR)
        self.r1 = None
        self.p.curl['healthz'] = IDLE
        self.release_before()
        self.p.record(CUR, OLD)
        self.lines = readme_lines(test)

    def line(self, n, rc=0):
        """The README section's Nth updater line, run with <runner version> = CUR (its user is checked by the order
        cell: README_ORDER)."""
        _, args = self.lines[n]
        return self.cmd(*args.replace('<runner version>', CUR).split(), rc=rc)

    def image(self, files):
        d = os.path.join(self.p.build, 'image')
        shutil.rmtree(d)
        os.mkdir(d)
        for n, data in files.items():
            with open(os.path.join(d, n), 'wb') as f:
                f.write(data)

    def release_before(self):
        """Install step 3 with the release before's files (its image/)."""
        with open(os.path.join(IMAGE, 'Dockerfile'), 'rb') as f:
            dockerfile = f.read()
        with open(os.path.join(IMAGE, 'install-runner.sh'), 'rb') as f:
            install = f.read()
        self.image({'Dockerfile': dockerfile + b'# the release before (a substitute: another recipe)\n',
                    'install-runner.sh': install})
        if self.r1 is not None:   # step 3 brings that release's core/ too
            self.plant('core/r1.jq', self.r1)

    def this_release(self):
        """Install step 3 with this release's files (its image/)."""
        files = {}
        for n in os.listdir(IMAGE):
            with open(os.path.join(IMAGE, n), 'rb') as f:
                files[n] = f.read()
        self.image(files)
        if self.r1 is not None:
            self.plant('core/r1.jq', self.r1)

    def plant(self, rel, text):
        if rel == 'core/r1.jq' and self.r1 is None:
            self.r1 = self.p.read(os.path.join(self.p.build, rel))
        self.p.write(os.path.join(self.p.build, rel), text)

    def cmd(self, *args, rc=0):
        self.p.clock(plus=600)
        r = self.p.updater(*args)
        self.t.assertEqual(r.returncode, rc, '%s: %s' % (' '.join(args), r.stdout[-4000:] + r.stderr))
        return r

    def due(self, r):
        lines = [l for l in r.stdout.splitlines() if l.startswith(NOT) or ' is due for runner ' in l]
        self.t.assertEqual(len(lines), 1, r.stdout[-3000:])
        return lines[0]

    def fam(self):
        return json.loads(self.p.read(STATE))['families'].get(FAM, {})


# the README section's updater lines, in its order: (user, the updater's arguments)
README_ORDER = [('RUN_USER', 'build <runner version>'), ('RS_USER', 'rebuild hz-docker <runner version>'),
                ('RS_USER', 'status'), ('RS_USER', 'back hz-docker'), ('RS_USER', 'rebuild hz-docker <runner version>'),
                ('RS_USER', 'retry hz-docker')]
BUILD, REBUILD, STATUS, BACK, BACK_REBUILD, BACK_RETRY = range(6)


def readme_lines(test):
    """The updater lines of the README's H4 section, as written: [(user, arguments)], in order (README_ORDER)."""
    s = section(readme(), TITLE)
    got = re.findall(r"(?m)^   ssh <(RUN_USER|RS_USER)>@<host> '~/bin/runner-updater ([^']*)'$", s)
    test.assertEqual(got, README_ORDER)
    return got


def deployed(test):
    """S-1's lines, each checked: the pool runs H4's image and status shows the candidate CUR on it."""
    g = Deploy(test)
    t = test
    r = g.cmd('pass')
    t.assertNotIn(RECIPE, r.stdout, 'the release before runs its own recipe')
    g.this_release()                                         # Install step 3 (both users) and step 4
    r = g.cmd('pass')
    t.assertEqual(g.due(r), NOT + 'release v%s is not newer than its runner %s' % (CUR, CUR))   # W2 M-1: no hold
    line = [l for l in r.stdout.splitlines() if l.startswith(RECIPE)]
    t.assertEqual(len(line), 1, r.stdout[-3000:])
    t.assertIn("'~/bin/runner-updater build %s'`, then `runner-updater rebuild hz-docker %s`" % (CUR, CUR), line[0])
    t.assertEqual(g.fam().get('stops', []), [], 'the pass writes no STOP for it')
    r = g.line(REBUILD, rc=1)                                # the control: no build line yet
    t.assertIn('no usable build record of runner %s for this release\'s image' % CUR, r.stdout)
    t.assertIn("'~/bin/runner-updater build %s'" % CUR, r.stdout)
    t.assertEqual(g.p.images(), [ref(OLD)] * 2)
    g.p.record(CUR, H4)                                      # RUN_USER: g.lines[BUILD] (its build record)
    g.p.curl['served'] = g.p.curl['served'] + [H4]
    r = g.line(REBUILD)                                      # RS_USER, at a quiet time
    t.assertIn('switched hz-docker to %s: it runs %s' % (CUR, ref(H4)), r.stdout)
    t.assertEqual(g.p.images(), [ref(H4)] * 2)
    r = g.line(STATUS)
    t.assertRegex(r.stdout, r'(?m)^runner-updater: family hz-docker: candidate runner %s \(linux-ci-main=%s, '
                  r'linux-ci-small=%s\)' % (re.escape(CUR), re.escape(ref(H4)), re.escape(ref(H4))))
    r = g.cmd('pass')
    t.assertNotIn(RECIPE, r.stdout)
    return g


@needs_container
class TheDeploy(unittest.TestCase):
    def test_build_then_rebuild_puts_the_new_recipe_s_image_in(self):
        deployed(self)


@needs_container
class TheWayBack(unittest.TestCase):
    def test_a_the_new_image_still_runs(self):
        g = deployed(self)
        g.release_before()                                   # Install step 3 from the release before, then step 4
        r = g.line(BACK_REBUILD)
        self.assertIn('switched hz-docker to %s: it runs %s' % (CUR, ref(OLD)), r.stdout)
        self.assertEqual(g.p.images(), [ref(OLD)] * 2)
        r = g.cmd('pass')
        self.assertNotIn(RECIPE, r.stdout)

    def test_b_r1_rolled_the_new_image_back_and_control_without_the_release_before(self):
        for before in (True, False):
            with self.subTest(release_before=before):
                g = deployed(self)
                plant_r1(g)
                r = g.cmd('pass')
                self.assertIn('runner-updater: pass: rolled back hz-docker', r.stdout)
                self.assertEqual(g.p.images(), [ref(OLD)] * 2)
                f = g.fam()
                self.assertEqual(f.get('rejected'), [CUR])
                self.assertEqual([s['stop'] for s in f.get('stops', [])], ['ROLLED BACK'])
                if before:
                    g.release_before()                       # Install step 3 from the release before, then step 4
                else:
                    g.this_release()                         # the control: this release's files stay
                r = g.p.updater('status')
                self.assertIn('runner-updater retry hz-docker', r.stdout)
                g.line(BACK_RETRY)
                self.assertEqual(g.fam().get('rejected', []), [])
                r = g.cmd('pass')
                self.assertEqual(g.p.images(), [ref(OLD)] * 2)
                if before:
                    self.assertNotIn(RECIPE, r.stdout)
                    r = g.cmd('rebuild', FAM, CUR, rc=1)     # no rebuild: nothing to switch
                    self.assertIn('nothing to switch', r.stdout)
                else:                                        # W2 M-1: the recipe line, and no STOP
                    self.assertEqual(len([l for l in r.stdout.splitlines() if l.startswith(RECIPE)]), 1, r.stdout)
                    self.assertEqual(g.fam().get('stops', []), [])


class Text(unittest.TestCase):
    def test_the_readme_s_h4_section_names_the_lines_in_order(self):
        """S-1 and S-3's lines, as the README gives them, in the order the cells above run them, and W2's default (the
        next runner release; the recipe line and status's last pass) and its way back (`back hz-docker`, N-2)."""
        s = section(readme(), TITLE)
        flat = one(s)
        want = ('it holds nothing',
                'the next runner release',
                'hz-docker: the image recipe changed',
                'last pass',
                'Install step 3 for both users, then Install step 4',
                'To apply it now',
                "ssh <RUN_USER>@<host> '~/bin/runner-updater build <runner version>'",
                "ssh <RS_USER>@<host> '~/bin/runner-updater rebuild hz-docker <runner version>'",
                'candidate runner <runner version>',
                "ssh <RS_USER>@<host> '~/bin/runner-updater status'",
                'The way back',
                'The passes switched the pool to a newer runner release',
                'no pass switches to it again',
                "ssh <RS_USER>@<host> '~/bin/runner-updater back hz-docker'",
                "Install step 3 with the release before's files for both users",
                'You ran steps 2 and 3',
                "~/bin/runner-updater rebuild hz-docker <runner version>",
                'R1 has rolled',
                "~/bin/runner-updater retry hz-docker",
                'nothing to switch')
        at = 0
        for w in want:
            i = flat.find(w, at)
            self.assertGreaterEqual(i, 0, 'not found after the one before it: %r' % w)
            at = i + len(w)
        self.assertNotIn('STOP recipe changed', flat)               # W2 M-1: it is no STOP and holds nothing
        self.assertIn('Install step 4 with this release\'s lines', flat)


if __name__ == '__main__':
    unittest.main()
