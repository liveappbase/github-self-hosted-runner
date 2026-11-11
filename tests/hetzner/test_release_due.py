"""DUE: which runner release hz-docker would switch to, or why not (S2b-3b-2; PLAN D2 HETZNER, D6 ONE OPEN RELEASE and
AFTER ACCEPT, D7): RS_USER's pass, after its core calls, prints ONE line for hz-docker, in the Studio's order
(bin/runner-updater-release, rl_pass), adapted:

  1. an open candidate (a `previous` that back_until keeps is none: the 11-04 decision);
  2. a STOP that holds whatever the release is (stops.jq: no version, or a newer release does not proceed alone past
     it; STOPs jq cannot read: fail closed);
  3. this release's image recipe cannot be computed (runner-release.sh's rr_recipe);
  4. STOP NO BASELINE: config.toml's two family lines do not name one image, or not exactly one build record of
     RUN_USER has its digest (rr_record_of);
  5. STOP recipe changed: that record's recipe is not this release's;
  6. (the current version is that record's version);
  7. the latest release (rr_eligible): WAIT, or not eligible;
  8. a STOP of that version; 9. it is rejected for hz-docker; 10. it is not newer than the current version;
  11. no build record of (V, recipe): it waits for RUN_USER's build of V (rr_record);
  12. the switch window (S2b-3c-2 B4a: "would switch hz-docker to V" is gone): "hz-docker is due for runner V: the
      switch window, pool-image.sh up --unattended V D (its lines follow)"; its cells are test_pass_switch.py's. Here
      the pool is BUSY (Due), so that window ends not idle with no journal, and the pass writes only `due`.

Steps 1-6 ask GitHub nothing; no step downloads a tarball (RUN_USER's build checked the digest). DUE never fails the pass
and writes nothing into the state but step 12's `due` (NO BASELINE and recipe changed are printed, not stored). Step 10 compares versions
field by field, as numbers. RUN_USER's records are HOSTILE (PLAN D1, class Hostile): a FIFO or a symlink renamed over a
record's name while the pass reads it is no record, at once (runner-release.sh's rr_read: one open, no symlink, never
blocks), and the pass ends as always.

Every cell runs the real scripts (pin lines rewritten: support.Pool) in a throwaway container, with the fake clock
(support.Pool.fake_clock): the release's published_at is set relative to it, and no cell reads a wall-clock time.
"""
import json
import os
import re
import unittest

from tests.hetzner.support import Pool, digest, healthz, iso, needs_container, ref, tarball

V = '2.339.0'                 # GitHub's latest release
CUR = '2.338.2'               # the runner of the image the pool runs: its build record's version
OLDER = '2.338.0'
NEW, OLD = digest(39), digest(38)
FAM = 'hz-docker'
MAIN, SMALL = 'linux-ci-main', 'linux-ci-small'
STATE = os.path.join(Pool.STATE, 'state.json')
BUILDS = os.path.join(Pool.HOME, 'run', 'builds')
DAY = 86400
API = '/repos/actions/runner/releases/latest'
SWITCH = ('runner-updater: pass: hz-docker is due for runner %s: the switch window, pool-image.sh up --unattended %s %s '
          '(its lines follow)' % (V, V, NEW))   # step 12 (B4a: the switch itself; it was "would switch ...")
NOT = 'runner-updater: pass: hz-docker is not due: '


def stop(name, version=None, **detail):
    return {'family': FAM, 'stop': name, 'version': version, 'user': None, 'detail': detail}


class Due:
    """A Pool whose production runs OLD; the updater ON, the fake clock. The BASELINE (base=True): RUN_USER's build record
    of OLD's digest, runner CUR (or cur), this release's recipe. GitHub's latest release VERSION, published AGE before
    the fake now (STATUS: the API's answer), and its build record of NEW's digest (built=True). The pool BUSY (B4a: step
    12 runs the switch window, which then ends not idle, with no journal: these cells are DUE's order)."""

    def __init__(self, test, family=None, base=True, built=True, age=3 * DAY, status=200, version=V, cur=CUR):
        self.t = test
        self.p = p = Pool(test)
        p.curl['served'] = [OLD, NEW]
        p.production(OLD)
        p.curl['healthz'] = healthz(**{MAIN: {'busy': 1}})
        p.fake_clock()
        self.now = p.clock()
        p.gh.release(version, tarball(version), latest=True, published=iso(self.now - age), status=status)
        if base:
            p.record(cur, OLD)
        if built:
            p.record(version, NEW)
        self.put({'format': 1, 'on': True, 'families': {FAM: family} if family is not None else {}})

    def put(self, st):
        os.makedirs(Pool.STATE, mode=0o700, exist_ok=True)
        self.p.write(STATE, json.dumps(st) + '\n', 0o600)

    def families(self):
        return json.loads(self.p.read(STATE))['families']

    def run(self):
        """A pass: exit 0 always (DUE never fails it), and the state's families as they were, but step 12's `due` (DUE
        writes nothing else; the busy pool: no window)."""
        def nodue(fs):
            return {k: {m: x for m, x in v.items() if m != 'due'} if isinstance(v, dict) else v for k, v in fs.items()}
        before = self.families()
        r = self.p.updater('pass')
        self.t.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        after = self.families()
        if FAM in after and after[FAM] == {'due': after[FAM].get('due')} and FAM not in before:
            after = {k: v for k, v in after.items() if k != FAM}
        self.t.assertEqual(nodue(after), nodue(before), 'the pass wrote into the families')
        return r

    def due(self, r):
        """DUE's lines: exactly one."""
        lines = [l for l in r.stdout.splitlines() if l.startswith(NOT) or l.startswith('runner-updater: pass: hz-docker '
                                                                                       'is due for runner ')]
        self.t.assertEqual(len(lines), 1, r.stdout[-3000:])
        return lines[0]

    def asked(self):
        """What the pass asked GitHub (the stub's request paths): never a download."""
        self.t.assertEqual([s for s in self.p.gh.seen if '/download/' in s or '/objects/' in s], [])
        return self.p.gh.seen


@needs_container
class Switch(unittest.TestCase):
    def test_every_step_passed_starts_the_switch_and_asks_github_once(self):
        g = Due(self)
        r = g.run()
        self.assertEqual(g.due(r), SWITCH)
        self.assertEqual(g.asked(), [API])
        self.assertNotIn('would switch', r.stdout)


@needs_container
class Steps(unittest.TestCase):
    def held(self, g, start, network=False):
        line = g.due(g.run())
        self.assertTrue(line.startswith(NOT + start), line)
        self.assertEqual(g.asked(), [API] if network else [], 'steps 1-6 ask GitHub nothing')
        return line

    def test_1_an_open_candidate(self):
        """Its switch closed a minute before the pass (B4a: KEEP now ACTS, so a candidate 72 h old with no evidence
        window would hold NO EVIDENCE in this pass: a write of the families this cell does not test)."""
        g = Due(self)
        g.put({'format': 1, 'on': True, 'families': {FAM: {'candidate': {
            'version': '2.338.9', 'lines': {MAIN: ref(NEW), SMALL: ref(NEW)}, 'closed_at': g.now - 60}}}})
        self.held(g, 'an open candidate (runner 2.338.9): one open release per family')

    def test_1_control_the_7_days_after_accept_are_no_open_release(self):
        g = Due(self, family={'candidate': None, 'previous': {MAIN: ref(digest(37)), SMALL: ref(digest(37))},
                              'back_until': 1893456000})
        self.assertEqual(g.due(g.run()), SWITCH)

    def test_2_a_stop_that_holds_whatever_the_release_is(self):
        for why, st, start in (
                ('no version, though its name proceeds', stop('check failed', text='FAIL x'),
                 'STOP check failed (no runner version): a STOP that names no version holds every release'),
                ('a newer release does not proceed alone', stop('JOBS FAIL ON THE NEW IMAGE', OLDER),
                 'STOP JOBS FAIL ON THE NEW IMAGE (runner %s): a newer release does not proceed alone past it' % OLDER),
                ('one this release does not know', stop('A NEW STOP', OLDER),
                 'STOP A NEW STOP (runner %s): a STOP this release does not know holds every release' % OLDER)):
            with self.subTest(why):
                g = Due(self, family={'stops': [st]})
                line = self.held(g, start)
                self.assertTrue(line.endswith('; `runner-updater status` names its next step'), line)

    def test_2_control_a_newer_release_proceeds_alone_past_an_older_check_failed(self):
        g = Due(self, family={'stops': [stop('check failed', OLDER, text='FAIL x')]})
        self.assertEqual(g.due(g.run()), SWITCH)

    def test_2_stops_jq_cannot_read_hold_the_family(self):
        """A jq that fails on DUE's reading of the STOPs (its program asks stops.jq's newer_proceeds inline; the core's
        programs, run with -f, are the real jq's) holds the family: fail closed."""
        g = Due(self)
        g.p.write(g.p.path('stubs', 'jq'), '#!/bin/sh\nfor a in "$@"; do case $a in -f) exec /usr/bin/jq "$@" ;; '
                  '*newer_proceeds*) exit 5 ;; esac; done\nexec /usr/bin/jq "$@"\n', 0o755)
        self.held(g, 'jq could not read the STOPs of the state; a family is never due while they cannot be read')

    def test_3_a_recipe_it_cannot_compute(self):
        g = Due(self)
        os.symlink('Dockerfile', os.path.join(g.p.build, 'image', 'link'))
        self.held(g, "this release's image recipe cannot be computed: image/link")

    def test_4_no_baseline(self):
        def two_images(g):
            c = g.p.rpath('config.toml')
            text = g.p.read(c)
            i = text.rindex('runner-image = "%s"' % ref(OLD))
            g.p.write(c, text[:i] + 'runner-image = "%s"' % ref(NEW) + text[i + len(ref(OLD)) + 17:], 0o600)

        def none(g):
            os.remove(os.path.join(BUILDS, '%s-%s' % (CUR, g.p.recipe())))

        def two(g):
            g.p.record('2.338.1', OLD)

        def misnamed(g):
            none(g)
            g.p.record(CUR, OLD, name='%s-%s' % ('2.338.1', g.p.recipe()))

        def malformed(g):
            none(g)
            g.p.record(CUR, OLD, text='format 1\nversion %s\ndigest %s\nrecipe %s\nnote x\n' % (CUR, OLD, g.p.recipe()))

        def a_link(g):
            none(g)
            g.p.record(CUR, OLD, name='good')
            os.symlink('good', os.path.join(BUILDS, '%s-%s' % (CUR, g.p.recipe())))

        for why, change, says in (
                ('two images', two_images, 'its sets (%s, %s) do not name one image in config.toml' % (MAIN, SMALL)),
                ('no record names its digest', none, 'no build record of RUN_USER (%s) names its image\'s digest %s'
                 % (BUILDS, OLD)),
                ('two records name it', two, '2 build records of RUN_USER (%s) name its image\'s digest %s'
                 % (BUILDS, OLD)),
                ('a record whose name is not its version and recipe', misnamed, 'no build record'),
                ('a record of another form', malformed, 'no build record'),
                ('a symlink to a record', a_link, 'no build record')):
            with self.subTest(why):
                g = Due(self)
                change(g)
                line = self.held(g, 'STOP NO BASELINE: ')
                self.assertIn(says, line)

    def test_4_control_one_good_record_beside_a_malformed_one_is_the_baseline(self):
        g = Due(self)
        g.p.record('2.338.1', OLD, text='format 1\nversion 2.338.1\ndigest %s\nrecipe %s\n\n' % (OLD, g.p.recipe()))
        self.assertEqual(g.due(g.run()), SWITCH)

    def test_5_recipe_changed(self):
        g = Due(self, base=False)
        rec = g.p.record(CUR, OLD, recipe='e' * 64)
        line = self.held(g, 'STOP recipe changed: ')
        self.assertIn("this release's image recipe is %s, and the build record of config.toml's image (%s) names %s"
                      % (g.p.recipe(), rec, 'e' * 64), line)

    def test_7_the_latest_release_waits_or_is_not_eligible(self):
        for why, kw, start in (('429', {'status': 429}, 'WAIT GitHub answered 429 (a rate limit)'),
                               ('403', {'status': 403}, 'WAIT GitHub answered 403 (a rate limit)'),
                               ('2 days - 1 s', {'age': 2 * DAY - 1}, 'release v%s is younger than 2 days' % V)):
            with self.subTest(why):
                g = Due(self, **kw)
                self.held(g, start, network=True)

    def test_7_control_2_days_old_is_eligible(self):
        g = Due(self, age=2 * DAY)
        self.assertEqual(g.due(g.run()), SWITCH)

    def test_7_its_age_is_read_at_the_pass_s_start_before_recover(self):
        """B2a review r2, Opus F1 (B2a CLOSED; its mutant M-R, the clock read after RECOVER FIRST): DUE's boundary with
        a window journal that RECOVER ends while the fake clock moves (`window ID`, the enabled unit serving: RECOVER's
        own RUNS pair moves it 3 s; it closes the journal with no STOP, and the apply step only archives it). The
        pass's ONE clock is its start, so a release 2 days - 1 s old is still younger than 2 days. The control: the
        same journal at 2 days: step 12."""
        wid = '20261106010000-4242'
        for age, want in ((2 * DAY - 1, 'young'), (2 * DAY, 'switch')):
            with self.subTest(age=age):
                g = Due(self, age=age)
                os.makedirs(os.path.join(Pool.STATE, 'windows'), mode=0o700, exist_ok=True)
                g.p.write(os.path.join(Pool.STATE, 'window'), 'window %s\n' % wid, 0o600)
                start = g.p.clock()
                r = g.run()
                arch = g.p.read(os.path.join(Pool.STATE, 'windows', wid))
                self.assertIsNotNone(arch, 'the premise: RECOVER closed the journal and it is archived: '
                                     + r.stdout[-3000:])
                self.assertIn('\nrecover-start ', arch, 'the premise: RECOVER ran on it')
                self.assertGreaterEqual(g.p.clock(), start + 9,
                                        'the premise: RECOVER, THE OUTAGE RULE and the facts slept')
                line = g.due(r)
                if want == 'switch':
                    self.assertEqual(line, SWITCH)
                else:
                    self.assertTrue(line.startswith(NOT + 'release v%s is younger than 2 days' % V), line)

    def test_8_a_stop_of_the_eligible_version(self):
        g = Due(self, family={'stops': [stop('check failed', V, text='FAIL x')]})
        self.held(g, 'STOP check failed (runner %s): it is of the eligible release' % V, network=True)

    def test_9_rejected_for_hz_docker(self):
        for rejected, held in (([V], True), (['2.338.9'], False)):
            with self.subTest(rejected=rejected):
                g = Due(self, family={'rejected': rejected})
                if held:
                    self.held(g, 'release v%s is rejected for hz-docker' % V, network=True)
                else:
                    self.assertEqual(g.due(g.run()), SWITCH)

    def test_10_not_newer_than_the_current_version(self):
        for latest in (CUR, OLDER):
            with self.subTest(latest=latest):
                g = Due(self, version=latest, built=False)    # its record would be the baseline's name
                self.held(g, 'release v%s is not newer than its runner %s' % (latest, CUR), network=True)

    def test_10_the_version_compare_is_numeric_field_by_field(self):
        """Opus r1 F5: the patch number decides when major and minor are equal (2.338.3 over 2.338.2), and each field is
        a number, not text (2.1000.0 over 2.999.0); each reverse is not newer. Red on a string compare and on a compare
        that ignores the patch number (the review's mutants m1 and m2)."""
        for latest, cur, due in (('2.338.3', '2.338.2', True), ('2.1000.0', '2.999.0', True),
                                 ('2.338.2', '2.338.3', False), ('2.999.0', '2.1000.0', False)):
            with self.subTest(latest=latest, cur=cur):
                g = Due(self, version=latest, cur=cur)
                line = g.due(g.run())
                if due:
                    self.assertEqual(line, 'runner-updater: pass: hz-docker is due for runner %s: the switch window, '
                                           'pool-image.sh up --unattended %s %s (its lines follow)' % (latest, latest, NEW))
                else:
                    self.assertEqual(line, NOT + 'release v%s is not newer than its runner %s' % (latest, cur))

    def test_11_no_build_record_of_the_release_waits_for_run_user_s_build(self):
        g = Due(self, built=False)
        line = self.held(g, "it waits for root's build of runner %s (no usable build record of runner %s for this "
                            "release's image" % (V, V), network=True)
        self.assertIn(g.p.recipe()[:12], line)
        g.p.record(V, NEW)                                        # the control: its record, then step 12
        g.p.gh.seen.clear()
        self.assertEqual(g.due(g.run()), SWITCH)


@needs_container
class Hostile(unittest.TestCase):
    """PLAN D1: RUN_USER's files are HOSTILE to RS_USER (Opus r1 F1). RUN_USER renames a FIFO, or a symlink to a good
    record, over a record's name at the moment the pass's reader makes its private copy (support.Pool.swap: the
    deterministic form of the race between the old reader's type check and its open). The reader (runner-release.sh's
    rr_read) opens the name ONCE, never follows a symlink and never blocks: the name is no record, AT ONCE. At step 4
    (the baseline): STOP NO BASELINE; at step 11 (the release's own record): it waits for RUN_USER's build. The pass
    exits 0 as always, under `timeout` (support.Pool.bounded: a bound on a hang, never a time a cell asserts: exit 124
    is a hang), and the next pass finds the updater lock free. Control: the same swap of a PLAIN record is a record."""

    def swapped(self, kind, at, version):
        g = Due(self)
        rec = os.path.join(BUILDS, '%s-%s' % (version, g.p.recipe()))
        target = g.p.write(g.p.path('good-record'), g.p.read(rec), 0o640)
        g.p.swap(rec, kind, at=at, target=target)
        before = g.families()
        updater = os.path.join(g.p.build, 'bin', 'runner-updater')
        r = g.p.bounded([updater, 'pass'])
        self.assertNotEqual(r.returncode, 124, 'the pass hung on a %s renamed over %s' % (kind, rec))
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertTrue(g.p.swapped(), 'the swap did not happen: the cell proves nothing')
        after = g.families()
        if kind == 'plain':        # the control reaches step 12, whose only write is `due` (B4a: the busy pool)
            self.assertEqual(after.pop(FAM, {}).pop('due', None)['version'], V)
            after = {k: v for k, v in after.items() if v}
        self.assertEqual(after, before, 'the pass wrote into the families')
        again = g.p.bounded([updater, 'pass'])
        self.assertEqual(again.returncode, 0, again.stdout[-4000:] + again.stderr)
        self.assertNotIn('another run holds the updater lock', again.stdout)
        return g.due(r)

    def test_4_a_fifo_or_a_symlink_renamed_over_the_baseline_record_is_no_record(self):
        for kind in ('fifo', 'link', 'plain'):
            with self.subTest(kind):
                line = self.swapped(kind, 1, CUR)
                if kind == 'plain':                               # the control
                    self.assertEqual(line, SWITCH)
                else:
                    self.assertTrue(line.startswith(NOT + "STOP NO BASELINE: no build record of RUN_USER (%s) names "
                                                          "its image's digest %s" % (BUILDS, OLD)), line)

    def test_11_a_fifo_or_a_symlink_renamed_over_the_release_s_record_is_no_record(self):
        """Step 4 made two private copies (the baseline's record and the release's): step 11's is the third."""
        for kind in ('fifo', 'link', 'plain'):
            with self.subTest(kind):
                line = self.swapped(kind, 3, V)
                if kind == 'plain':                               # the control
                    self.assertEqual(line, SWITCH)
                else:
                    self.assertTrue(line.startswith(NOT + "it waits for root's build of runner %s" % V), line)
                    self.assertTrue(line.endswith(': it is not a plain file)'), line)


@needs_container
class Order(unittest.TestCase):
    def test_a_family_held_before_step_7_asks_github_nothing(self):
        """The order: a family held at step 2 (a STOP of no version) asks the stub API nothing, though every later step
        would hold it too (a younger release, no record, rejected). Control: the same family without the STOP asks
        GitHub once, and step 7 holds it."""
        for held in (True, False):
            with self.subTest(held_at_step_2=held):
                g = Due(self, built=False, age=DAY,
                        family=dict({'rejected': [V]}, **({'stops': [stop('DISK', text='free disk')]} if held else {})))
                if held:      # B4a: a pass clears a held DISK when disk_ok passes (THE TWO LEVELS): the disk stays low
                    g.p.disk(1000, 50)
                line = g.due(g.run())
                if held:
                    self.assertTrue(line.startswith(NOT + 'STOP DISK'), line)
                    self.assertEqual(len(g.asked()), 0)
                else:
                    self.assertTrue(line.startswith(NOT + 'release v%s is younger' % V), line)
                    self.assertEqual(g.asked(), [API])


if __name__ == '__main__':
    unittest.main()
