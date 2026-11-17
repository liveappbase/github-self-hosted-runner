"""A new image RECIPE (a release whose linux-docker/image/ changed) no longer holds RS_USER's pass (W2, the r2 MODEL
M-1 and the r3 FOLD N-1, N-2, N-4, N-6; issue #6). DUE's step 5 (due_base's recipe compare: the build record of the
image config.toml names is of another recipe than this release's) is no hold any more: DUE goes on through steps 6-12
unchanged, so the NEXT runner release, which RUN_USER's pass builds with this release's recipe, switches in the normal
window (idle, KEEP, R1), and DUE never switches to the version the pool runs (step 10: newer only). When DUE ends with
no switch and the image config.toml names is of another recipe, the pass prints a SECOND line after DUE's own (THE
RECIPE LINE): `hz-docker: the image recipe changed (this release's <rec>…, the pool's image <old>…): it reaches the
pool with the next runner release, or now by ...`, naming RUN_USER's `build CUR` line only when the record of (CUR, this
recipe) is missing, and always `runner-updater rebuild hz-docker CUR`. No STOP is written. `status` shows both lines of
the latest pass (PASSDIR/last-pass, test_last_pass.py), DUE's own outcome first (N-1).

- M-4 (a): a newer release built for this recipe -> the pass switches to it (one window); control: that release
  rejected -> no window, DUE's `rejected` line and the recipe line.
- M-4 (b): no newer release -> `not newer` and the recipe line, every pass, no window, no STOP; control: the recipe
  unchanged -> no recipe line. Its status is the issue #6 cell: the shape seen live (a recipe change after Install step
  3, a pass, then `status`).
- N-1: a newer release built and the pool busy -> the outcome `the switch to runner V waits for idle`, naming V (not
  DUE's `is due` line; build review r1, opus F3), and the recipe line; control: the same, idle -> exactly one window to
  the newer release, status `switched`, no recipe line.
- N-6 (a): the record of (CUR, this recipe) there -> the line names only `rebuild`; missing -> `build` too.
- N-2 / M-4 (c): the way back after such a switch (the new image is the NEWER version's) is `back hz-docker`: the old
  image runs, the newer version is rejected, and the next passes switch nothing (a regression guard for the mutant
  "DUE switches to the running version when the recipe differs": RUN_USER's record of (CUR, this recipe) is planted so
  that mutant has a target). Control: the same-version branch's `rebuild hz-docker CUR` refuses on this path.
- The way back after R1 rolled that switch back (build review r1, opus F4): the old image runs, V rejected, `STOP ROLLED
  BACK`; the README's `retry hz-docker` re-admits V, and the next pass switches to V again on this recipe (the control);
  with the release before's files first (Install step 3: another recipe), the next pass switches nothing: it waits for
  RUN_USER's build of V for that recipe.
Every cell runs the real scripts (support.Pool, a throwaway container, the fake clock) and the updater as RS_USER.
(Named for its CI part, test_re[!nt][!o]*.py: .github/workflows/release-check.yml.)
"""
import os
import unittest

from tests.hetzner.support import digest, needs_container, ref
from tests.hetzner.test_command_rebuild import BUILD_LINE
from tests.hetzner.test_gh_deploy import BACK, BACK_REBUILD, R1_RETRY, readme_lines
from tests.hetzner.test_pass_switch import BUSY, DUE_LINE, IDLE, WAITS, G
from tests.hetzner.test_release_due import CUR, NEW, NOT, OLD, V
from tests.hetzner.test_verdict import plant_r1

OLDREC = 'e' * 64          # the release before's image recipe: the recipe of the record of the image the pool runs
H = digest(44)             # RUN_USER's build of CUR for this release's recipe (a person's `build CUR`)
RECIPE = 'runner-updater: pass: hz-docker: the image recipe changed ('
LAST = 'runner-updater: last pass '
LAST_RECIPE = 'runner-updater: last pass: hz-docker: the image recipe changed ('


class R(G):
    """test_pass_switch's G (production OLD, the fake clock, ON, IDLE unless hz says), with the image config.toml names
    built from the release before's recipe: RUN_USER's record of (CUR, OLDREC) on OLD. LATEST: GitHub's latest release
    (V, newer, with RUN_USER's record of (V, this recipe) on NEW when built; or CUR)."""

    def __init__(self, test, latest=V, built=True, hz=IDLE, family=None):
        super().__init__(test, hz=hz, base=False, built=built and latest != CUR, version=latest, family=family)
        self.p.record(CUR, OLD, recipe=OLDREC)

    def pass_(self, rc=0):
        self.p.clock(plus=600)
        return self.go(rc=rc)

    def recipe_lines(self, r):
        return [l for l in r.stdout.splitlines() if l.startswith(RECIPE)]

    def due_line(self, r):
        lines = [l for l in r.stdout.splitlines() if l.startswith(NOT) or l.startswith(
            'runner-updater: pass: hz-docker is due for runner ')]
        self.t.assertEqual(len(lines), 1, r.stdout[-3000:])
        return lines[0]

    def status(self):
        r = self.p.updater('status')
        self.t.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        return r.stdout.splitlines()

    def last(self, lines):
        """status's last-pass lines: (the outcome line, [the recipe lines])."""
        out = [l for l in lines if l.startswith(LAST) and not l.startswith('runner-updater: last pass:')]
        self.t.assertEqual(len(out), 1, lines)
        return out[0], [l for l in lines if l.startswith(LAST_RECIPE)]

    def no_stop(self):
        self.t.assertEqual(self.held(), [], 'a recipe change writes no STOP')

    def plant(self, rel, text):
        """A file of the cell's own ~/build copy replaced by TEXT (plant_r1's planted R1)."""
        self.p.write(os.path.join(self.p.build, rel), text)


def recipe_text(rec, line):
    return ("hz-docker: the image recipe changed (this release's %s…, the pool's image %s…): it reaches the pool with "
            "the next runner release, or now by a person's %s" % (rec[:12], OLDREC[:12], line))


@needs_container
class NoHold(unittest.TestCase):
    def test_a_newer_release_built_for_this_recipe_is_switched_and_control_rejected(self):
        """M-4 (a): red under the mutant "step 5 kept as a hold" (the pass prints `STOP recipe changed` and switches
        nothing). The control: V rejected -> step 9's line, no window, and the recipe line (the record of (CUR, this
        recipe) is missing: both lines)."""
        for row in ('switch', 'control: rejected'):
            with self.subTest(row):
                g = R(self, family={'rejected': [V]} if row.startswith('control') else None)
                r = g.pass_()
                if row == 'switch':
                    self.assertIn(DUE_LINE, r.stdout)
                    self.assertIn('runner-updater: pass: switched hz-docker to %s: it runs %s (the window journal '
                                  % (V, ref(NEW)), r.stdout)
                    self.assertEqual(len(g.ups()), 1, r.stdout[-3000:])
                    self.assertEqual(g.fam()['candidate']['version'], V)
                    self.assertEqual(g.p.images(), [ref(NEW)] * 2)
                    self.assertEqual(g.recipe_lines(r), [], 'a pass that switched prints no recipe line')
                    continue
                self.assertEqual(g.due_line(r), NOT + 'release v%s is rejected for hz-docker' % V)
                self.assertEqual(len(g.recipe_lines(r)), 1, r.stdout[-3000:])
                self.assertEqual(g.ups(), [])
                self.assertEqual(g.p.images(), [ref(OLD)] * 2)
                g.no_stop()

    def test_no_newer_release_holds_nothing_and_says_so_every_pass_and_status_shows_it(self):
        """M-4 (b) and N-1 (i), the issue #6 cell: the latest release is the version the pool runs. Three passes:
        each prints step 10's `not newer` line, then the recipe line (with RUN_USER's `build CUR` line and `rebuild
        hz-docker CUR`); no window, no STOP. status: the last pass's outcome, then its recipe line (red under the
        mutant "the recipe line replaces the outcome"). The control: the recipe unchanged (the record of the image
        config.toml names is of this recipe) -> no recipe line in the pass or in status."""
        for row in ('recipe changed', 'control: recipe unchanged'):
            with self.subTest(row):
                g = R(self, latest=CUR)
                if row.startswith('control'):                  # the image's record is of this recipe again
                    os.remove(g.p.record(CUR, OLD, recipe=OLDREC))
                    g.p.record(CUR, OLD)
                for _ in range(3):
                    r = g.pass_()
                    self.assertEqual(g.due_line(r), NOT + 'release v%s is not newer than its runner %s' % (CUR, CUR))
                    lines = g.recipe_lines(r)
                    if row.startswith('control'):
                        self.assertEqual(lines, [], r.stdout[-3000:])
                    else:
                        self.assertEqual(lines, ['runner-updater: pass: ' + recipe_text(
                            g.p.recipe(), 'two lines: %s, then `runner-updater rebuild hz-docker %s`'
                            % (BUILD_LINE % CUR, CUR))], r.stdout[-3000:])
                        self.assertNotIn('STOP recipe changed', r.stdout)
                    self.assertEqual(g.ups(), [])
                    self.assertEqual(g.p.images(), [ref(OLD)] * 2)
                    g.no_stop()
                s = g.status()
                out, rl = g.last(s)
                self.assertRegex(out, r'^runner-updater: last pass \d+ (s|min) ago \(\d{4}-\d\d-\d\d \d\d:\d\d UTC\): '
                                 r'hz-docker is not due: release v%s is not newer than its runner %s$'
                                 % (CUR.replace('.', r'\.'), CUR.replace('.', r'\.')))
                if row.startswith('control'):
                    self.assertEqual(rl, [], s)
                    continue
                self.assertEqual(rl, ['runner-updater: last pass: ' + recipe_text(
                    g.p.recipe(), 'two lines: %s, then `runner-updater rebuild hz-docker %s`' % (BUILD_LINE % CUR, CUR))],
                    s)
                self.assertLess(s.index(out), s.index(rl[0]), 'the outcome comes first')

    def test_the_line_names_run_user_s_build_only_when_its_record_is_missing(self):
        """N-6 (a): RUN_USER's record of (CUR, this recipe) there -> the line names only `rebuild hz-docker CUR` (a
        `build` would replace that record with a new digest); missing -> RUN_USER's `build CUR` line first."""
        for row in ('missing', 'there'):
            with self.subTest(row):
                g = R(self, latest=CUR)
                if row == 'there':
                    rec = g.p.record(CUR, H)
                r = g.pass_()
                lines = g.recipe_lines(r)
                self.assertEqual(len(lines), 1, r.stdout[-3000:])
                if row == 'there':
                    self.assertEqual(lines[0], 'runner-updater: pass: ' + recipe_text(
                        g.p.recipe(), "line: `runner-updater rebuild hz-docker %s` (root's build of runner %s for this "
                                      "release's image is there: %s)" % (CUR, CUR, rec)))
                    self.assertNotIn('~/bin/runner-updater build', lines[0])
                else:
                    self.assertIn(BUILD_LINE % CUR, lines[0])

    def test_a_busy_pool_waits_for_idle_with_the_recipe_line_and_control_idle_switches(self):
        """N-1 (iii): a newer release built for this recipe, the pool busy: the pass's outcome is `waits for idle`
        (status shows it, never DUE's `is due` line: red under the mutant "store DUE's first line"), then the recipe
        line. The control: the next pass, idle -> exactly one window to V, status `switched`, no recipe line."""
        g = R(self, hz=BUSY)
        r = g.pass_()
        self.assertIn(DUE_LINE, r.stdout)
        self.assertIn(WAITS, r.stdout)
        self.assertEqual(len(g.recipe_lines(r)), 1, r.stdout[-3000:])
        self.assertEqual(g.ups(), [])
        out, rl = g.last(g.status())
        self.assertIn(': hz-docker: the switch to runner %s waits for idle (since ' % V, out)   # it names V
        self.assertNotIn('is due for runner', out)
        self.assertEqual(len(rl), 1)
        g.p.curl['healthz'] = IDLE                           # the control
        r = g.pass_()
        self.assertEqual(len(g.ups()), 1, r.stdout[-3000:])
        self.assertEqual(g.fam()['candidate']['version'], V)
        self.assertEqual(g.recipe_lines(r), [])
        out, rl = g.last(g.status())
        self.assertIn(': switched hz-docker to %s: it runs %s' % (V, ref(NEW)), out)
        self.assertEqual(rl, [])


@needs_container
class TheWayBack(unittest.TestCase):
    def test_back_after_the_pass_switched_to_the_newer_release_and_no_pass_switches_again(self):
        """N-2, M-4 (c): the pass switches to V on this recipe's image (RUN_USER's record of (CUR, this recipe) is there
        too: a target for the mutant "DUE switches to CUR"). The control: the same-version branch's `rebuild
        hz-docker CUR` refuses here (one open release per family), and the new image stays. `back hz-docker`: the old
        image runs, V rejected; three passes switch nothing (step 9's line, the recipe line naming only `rebuild`)."""
        g = R(self)
        g.p.record(CUR, H)
        r = g.pass_()
        self.assertIn('runner-updater: pass: switched hz-docker to %s: it runs %s' % (V, ref(NEW)), r.stdout)
        self.assertEqual(g.p.images(), [ref(NEW)] * 2)
        lines = readme_lines(self)                           # the README's H4 section, its lines in order
        self.assertEqual(lines[BACK], ('RS_USER', 'back hz-docker'))
        g.p.clock(plus=600)
        r = g.p.updater(*lines[BACK_REBUILD][1].replace('<runner version>', CUR).split())   # the control
        self.assertEqual(r.returncode, 1, r.stdout[-3000:])
        self.assertIn("REFUSE rebuild hz-docker: one open release per family: hz-docker's open candidate is runner %s"
                      % V, r.stdout)
        self.assertEqual(g.p.images(), [ref(NEW)] * 2)
        g.p.clock(plus=600)
        r = g.p.updater(*lines[BACK][1].split())
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('runner-updater: back hz-docker: rolled back: it runs %s again' % ref(OLD), r.stdout)
        self.assertEqual(g.p.images(), [ref(OLD)] * 2)
        self.assertEqual(g.fam().get('rejected'), [V])
        for _ in range(3):
            r = g.pass_()
            self.assertEqual(g.due_line(r), NOT + 'release v%s is rejected for hz-docker' % V)
            lines = g.recipe_lines(r)
            self.assertEqual(len(lines), 1, r.stdout[-3000:])
            self.assertIn('`runner-updater rebuild hz-docker %s`' % CUR, lines[0])
            self.assertEqual(len(g.ups()), 1, 'a pass switched again: ' + r.stdout[-3000:])
            self.assertEqual(g.p.images(), [ref(OLD)] * 2)
            g.no_stop()

    def test_r1_rolls_the_passes_switch_back_then_retry_with_and_without_the_release_before(self):
        """opus F4: the pass switches to V on this recipe's image; R1 says rollback (planted) and the next pass rolls
        it back: the old image runs, V rejected, `STOP ROLLED BACK`, and status names `runner-updater retry
        hz-docker`. Then Install step 3 brings the release before's core/ back (the real R1), and the README's line
        R1_RETRY runs: V is re-admitted. Without the release before's files (the control) the next pass switches to V
        again, on this recipe's image; with them (~/build/image/ of another recipe) it switches nothing and waits for
        RUN_USER's build of V for that recipe."""
        for row in ('control: this release\'s files', "the release before's files"):
            with self.subTest(row):
                g = R(self)
                r = g.pass_()
                self.assertIn('runner-updater: pass: switched hz-docker to %s: it runs %s' % (V, ref(NEW)), r.stdout)
                with open(os.path.join(g.p.build, 'core', 'r1.jq')) as f:
                    real = f.read()
                plant_r1(g)
                r = g.pass_()
                self.assertIn('runner-updater: pass: rolled back hz-docker', r.stdout)
                self.assertEqual(g.p.images(), [ref(OLD)] * 2)
                self.assertEqual(g.fam().get('rejected'), [V])
                self.assertEqual([s['stop'] for s in g.held()], ['ROLLED BACK'])
                self.assertIn('runner-updater retry hz-docker', g.p.updater('status').stdout)
                g.plant('core/r1.jq', real)                  # Install step 3 brings its core/ (the real R1)
                if not row.startswith('control'):            # the release before's image/: another recipe
                    rec = g.p.recipe()
                    with open(os.path.join(g.p.build, 'image', 'Dockerfile'), 'a') as f:
                        f.write('# the release before (a substitute: another recipe)\n')
                    self.assertNotEqual(g.p.recipe(), rec, 'the premise: another recipe')
                lines = readme_lines(self)
                self.assertEqual(lines[R1_RETRY], ('RS_USER', 'retry hz-docker'))
                g.p.clock(plus=600)
                r = g.p.updater(*lines[R1_RETRY][1].split())
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.fam().get('rejected', []), [])
                self.assertEqual(g.held(), [], 'retry ends the STOP')
                r = g.pass_()
                if row.startswith('control'):
                    self.assertIn('runner-updater: pass: switched hz-docker to %s: it runs %s' % (V, ref(NEW)),
                                  r.stdout)
                    self.assertEqual(g.p.images(), [ref(NEW)] * 2)
                    self.assertEqual(len(g.ups()), 2)
                    continue
                self.assertTrue(g.due_line(r).startswith(NOT + "it waits for root's build of runner %s (" % V), r.stdout)
                self.assertEqual(g.p.images(), [ref(OLD)] * 2)
                self.assertEqual(len(g.ups()), 1, 'a pass switched again: ' + r.stdout[-3000:])


if __name__ == '__main__':
    unittest.main()
