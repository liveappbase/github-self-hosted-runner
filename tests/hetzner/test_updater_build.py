"""linux-docker/bin/runner-updater as RUN_USER (S2b-3b-2; PLAN D1 "Hetzner's two users", D2 HETZNER BUILD, D7, D11):
the same program as RS_USER's, and the user decides the role (RS_USER's, else RUN_USER's; any other user: REFUSE).
RUN_USER's own state STATEDIR/state.json (format 1: `on`, `stops` [{stop, version, user, detail}]; missing: OFF, nothing
held; a member it does not read: WAIT, exit 4), and its commands:

- `status` (no lock, writes nothing), `on`, `off` (they wait for the updater lock);
- `pass`, THE BUILD PASS (a timer's entry later): the lock only tried; OFF ends it with no network; the latest release
  (rr_eligible): WAIT or not eligible is its line, exit 0; this release's recipe of ~/build/image (rr_recipe); a build
  record of (V, recipe) is "built", exit 0; a STOP that holds V (stops.jq: a `check failed` of V; a newer release
  proceeds alone past an older one) is its line, exit 0, and no build; else `~/build/setup/02-d1.sh build V` runs as its
  CHILD on the lock it holds (fd 9). 02-d1.sh exit 0: "built"; 75: WAIT, exit 0, no STOP; else STOP `check failed` of V
  with 02-d1.sh's FAIL line, written by rename, exit 1;
- `build V`, a person's path: it waits for the lock, runs 02-d1.sh build V while OFF too; exit 0 clears the `check
  failed` STOP of V, a failure writes it (or keeps it, with the new line).

02-d1.sh is ALWAYS its substitute here (support.Pool.d1_stub, in the cell's copy of ~/build): it logs its argv, whether
its fd 9 is the updater lock, whether a new open finds the lock held, and whether fd 9 takes it. The real build runs
only in test_build.py. The fake clock (support.Pool.fake_clock) is the pass's NOW, and the release's published_at is set
relative to it: no cell reads or asserts a wall-clock time.
"""
import fcntl
import json
import os
import re
import select
import time
import unittest

from tests.hetzner.support import REPO, RS_USER, Pool, digest, needs_container, run_pool

V = '2.339.0'
OLDER, NEWER = '2.338.2', '2.340.0'
STATEDIR = Pool.STATE
STATE = os.path.join(STATEDIR, 'state.json')
LOCK = os.path.join(STATEDIR, 'lock')
DAY = 86400
FAIL = 'FAIL docker build failed: no record, image.ref NOT changed\n'


def stop(name, version=None, **detail):
    return {'stop': name, 'version': version, 'user': 'root', 'detail': detail}


def state(p):
    t = p.read(STATE)
    return None if t is None else json.loads(t)


def put(p, st=None, raw=None):
    os.makedirs(STATEDIR, mode=0o700, exist_ok=True)
    p.write(STATE, raw if raw is not None else json.dumps(st) + '\n', 0o600)


def hold_lock(test):
    """The updater lock, held by THIS process (another open of the file: another holder)."""
    os.makedirs(STATEDIR, mode=0o700, exist_ok=True)
    fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    test.addCleanup(os.close, fd)
    return fd


def ok(test, r):
    test.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
    return r


# ---- the role

@needs_container
class Role(unittest.TestCase):
    def test_the_user_decides_the_role(self):
        """As RUN_USER (root alone, RS_USER another user) status is RUN_USER's: no family line, no window. As RS_USER
        (the Pool's root is both: RS_USER's role comes first) status is RS_USER's, and `build` is not its command."""
        p, _ = run_pool(self, V, on=False)
        r = ok(self, p.updater('status'))
        self.assertIn('runner-updater: status: the updater is OFF', r.stdout)
        self.assertNotIn('family hz-docker', r.stdout)
        q = Pool(self)                                   # the control: RS_USER = RUN_USER = root
        q.files()
        r = ok(self, q.updater('status'))
        self.assertIn('runner-updater: family hz-docker: no candidate', r.stdout)
        r = q.updater('build', V)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('runner-updater: REFUSE build is a command of RUN_USER (root)', r.stdout)

    def test_another_user_than_rs_user_or_run_user_is_refused(self):
        p, _ = run_pool(self, V, on=None)
        conf = p.read(p.path('host.conf'))
        p.write(p.path('host.conf'), conf.replace('\nRUN_USER=root\n', '\nRUN_USER=ci-run\n'), 0o644)
        for args in (('status',), ('on',), ('pass',), ('build', V)):
            with self.subTest(args):
                r = p.updater(*args)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('runner-updater: REFUSE run me as %s or ci-run' % RS_USER, r.stdout)
        self.assertFalse(os.path.lexists(STATEDIR))
        self.assertEqual(p.d1_calls(), [])

    def test_usage(self):
        p, _ = run_pool(self, V, on=None)
        for args in (('build',), ('build', '2.339'), ('build', V, 'x'), ('build', 'v' + V)):
            with self.subTest(args):
                r = p.updater(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn('usage: runner-updater status | on | off | pass | build VERSION', r.stderr)
        self.assertEqual(p.d1_calls(), [])


# ---- RUN_USER's state

@needs_container
class RunState(unittest.TestCase):
    def test_a_fresh_install_is_off_and_status_writes_nothing(self):
        p, _ = run_pool(self, V, on=None)
        r = ok(self, p.updater('status'))
        self.assertIn('runner-updater: status: the updater is OFF', r.stdout)
        self.assertIn('status: ok (0 STOPs)', r.stdout)
        self.assertFalse(os.path.lexists(STATEDIR), 'status wrote')
        r = ok(self, p.updater('pass'))
        self.assertIn('runner-updater: pass: the updater is OFF: nothing to do', r.stdout)

    def test_on_and_off(self):
        p, _ = run_pool(self, V, on=None)
        self.assertIn('runner-updater: on: the updater is ON', ok(self, p.updater('on')).stdout)
        self.assertEqual(state(p), {'format': 1, 'on': True, 'stops': []})
        self.assertEqual(os.stat(STATE).st_mode & 0o777, 0o600)
        self.assertIn('the updater is ON', ok(self, p.updater('status')).stdout)
        self.assertIn('runner-updater: off: the updater is OFF', ok(self, p.updater('off')).stdout)
        self.assertEqual(state(p), {'format': 1, 'on': False, 'stops': []})

    def test_on_waits_for_the_updater_lock(self):
        p, _ = run_pool(self, V, on=False)
        fd = hold_lock(self)
        pr = p.start([os.path.join(p.build, 'bin', 'runner-updater'), 'on'])
        ready, _, _ = select.select([pr.stdout], [], [], 120)    # a bound on a hang, not a time it asserts
        self.assertTrue(ready)
        first = pr.stdout.readline()
        self.assertIn('WAIT another run holds the updater lock %s' % LOCK, first)
        self.assertFalse(state(p)['on'])
        fcntl.flock(fd, fcntl.LOCK_UN)
        out, _ = pr.communicate(timeout=120)
        self.assertEqual(pr.returncode, 0, first + out)
        self.assertTrue(state(p)['on'])

    def test_another_format_waits_with_every_command(self):
        for fmt in (2, None):
            with self.subTest(format=fmt):
                p, _ = run_pool(self, V, on=None)
                st = {'on': True, 'stops': []}
                if fmt is not None:
                    st['format'] = fmt
                put(p, st)
                before = p.read(STATE)
                for args in (('status',), ('on',), ('off',), ('pass',), ('build', V)):
                    r = p.updater(*args)
                    self.assertEqual(r.returncode, 4, '%s: %s' % (args, r.stdout + r.stderr))
                    self.assertIn('runner-updater: WAIT the state %s has format %s' % (STATE, json.dumps(fmt)),
                                  r.stdout)
                self.assertEqual(p.read(STATE), before)
                self.assertEqual(p.d1_calls(), [])
                self.assertEqual(p.gh.seen, [])

    def test_a_member_it_does_not_read_waits(self):
        full = {'format': 1, 'on': True, 'stops': [stop('check failed', V, text='FAIL x', step='build',
                                                        build_user='root')]}
        cases = (
            ('families', lambda s: s.update(families={})),            # RS_USER's member: not RUN_USER's
            ('core', lambda s: s.update(core={'format': 1})),
            ('stops[0].family', lambda s: s['stops'][0].update(family='hz-docker')),
            ('stops[0].since', lambda s: s['stops'][0].update(since=1)),
        )
        for member, change in cases:
            with self.subTest(member):
                p, _ = run_pool(self, V, on=None)
                st = json.loads(json.dumps(full))
                change(st)
                put(p, st)
                before = p.read(STATE)
                for args in (('status',), ('on',), ('pass',), ('build', V)):
                    r = p.updater(*args)
                    self.assertEqual(r.returncode, 4, '%s: %s' % (args, r.stdout + r.stderr))
                    self.assertIn('runner-updater: WAIT the state %s holds members this release does not read (%s)'
                                  % (STATE, member), r.stdout)
                self.assertEqual(p.read(STATE), before)
                self.assertEqual(p.d1_calls(), [])
        p, _ = run_pool(self, V, on=None)                             # the control: every member it reads, kept
        put(p, dict(full, on=False))
        ok(self, p.updater('on'))
        self.assertEqual(state(p), full)

    def test_a_state_of_another_shape_is_refused(self):
        cases = (
            ('on is no boolean', {'format': 1, 'on': 'yes', 'stops': []}),
            ('stops is no list', {'format': 1, 'on': False, 'stops': {}}),
            ('a STOP with no name', {'format': 1, 'on': False, 'stops': [stop('', V)]}),
            ('a STOP whose detail is text', {'format': 1, 'on': False, 'stops': [dict(stop('check failed', V),
                                                                                       detail='FAIL x')]}),
        )
        for why, st in cases:
            with self.subTest(why):
                p, _ = run_pool(self, V, on=None)
                put(p, st)
                before = p.read(STATE)
                for args in (('status',), ('on',), ('pass',)):
                    r = p.updater(*args)
                    self.assertEqual(r.returncode, 1, '%s: %s' % (args, r.stdout + r.stderr))
                    self.assertIn('runner-updater: REFUSE %s is not a state of format 1 this reads' % STATE, r.stdout)
                self.assertEqual(p.read(STATE), before)

    def test_status_prints_each_stop_with_its_next_step_and_takes_no_lock(self):
        p, _ = run_pool(self, V, on=True, stops=[stop('check failed', V, text=FAIL.strip(), step='build',
                                                      build_user='root')])
        hold_lock(self)
        before = p.read(STATE)
        r = ok(self, p.updater('status'))
        self.assertIn('runner-updater: status: the updater is ON', r.stdout)
        self.assertIn('status: ok (1 STOPs)', r.stdout)
        self.assertIn('hz-docker: STOP check failed (runner %s): %s. Next: as root: `runner-updater build %s`'
                      % (V, FAIL.strip(), V), r.stdout)
        self.assertIn('runner-updater: STOP hz-docker check failed: known true', r.stdout)
        self.assertEqual(p.read(STATE), before)

    def test_untested_jq_stops_status_and_a_pass_that_is_on(self):
        p, _ = run_pool(self, V, on=True)
        p.jq_version('jq-9.9')
        for cmd in ('status', 'pass'):
            with self.subTest(cmd):
                r = p.updater(cmd)
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertIn('runner-updater: STOP untested jq: jq here prints [jq-9.9]', r.stdout)
        self.assertEqual(p.gh.seen, [])
        self.assertEqual(p.d1_calls(), [])
        q, _ = run_pool(self, V, on=False)                    # the control: OFF ends a pass before the jq check
        q.jq_version('jq-9.9')
        self.assertIn('the updater is OFF', ok(self, q.updater('pass')).stdout)


# ---- the build pass

@needs_container
class BuildPass(unittest.TestCase):
    def test_a_held_lock_ends_a_pass_at_once(self):
        p, _ = run_pool(self, V)
        hold_lock(self)
        r = ok(self, p.updater('pass'))
        self.assertIn('runner-updater: pass: another run holds the updater lock %s; this pass ends' % LOCK, r.stdout)
        self.assertEqual((p.gh.seen, p.d1_calls()), ([], []))

    def test_off_ends_a_pass_with_no_network(self):
        p, _ = run_pool(self, V, on=False)
        r = ok(self, p.updater('pass'))
        self.assertIn('runner-updater: pass: the updater is OFF: nothing to do', r.stdout)
        self.assertEqual((p.gh.seen, p.d1_calls()), ([], []))

    def test_a_release_younger_than_two_days_is_not_built(self):
        for why, age, built in (('2 days - 1 s', 2 * DAY - 1, False), ('2 days + 1 s', 2 * DAY + 1, True)):
            with self.subTest(why):
                p, now = run_pool(self, V, age=age)
                r = ok(self, p.updater('pass'))
                self.assertEqual(len(p.d1_calls()), 1 if built else 0, r.stdout)
                if not built:
                    self.assertIn('runner-updater: pass: no build: release v%s is younger than 2 days: published %s, '
                                  'eligible from %s' % (V, time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(now - age)),
                                                        time.strftime('%Y-%m-%d %H:%M:%S UTC',
                                                                      time.gmtime(now - age + 2 * DAY))), r.stdout)

    def test_a_rate_limit_waits_and_builds_nothing(self):
        p, _ = run_pool(self, V, status=429)
        r = ok(self, p.updater('pass'))
        self.assertIn('runner-updater: pass: WAIT GitHub answered 429 (a rate limit)', r.stdout)
        self.assertEqual(p.d1_calls(), [])
        self.assertEqual(state(p)['stops'], [])

    def test_a_record_of_v_and_this_recipe_is_built_and_nothing_runs(self):
        for why, recipe, runs in (("this release's recipe", None, False), ('another recipe', 'e' * 64, True)):
            with self.subTest(why):
                p, _ = run_pool(self, V)
                rec = p.record(V, digest(39), recipe=recipe)
                r = ok(self, p.updater('pass'))
                self.assertEqual(len(p.d1_calls()), 1 if runs else 0, r.stdout)
                if not runs:
                    self.assertIn("runner-updater: pass: runner %s is built for this release's image (its build "
                                  "record: %s): nothing to build" % (V, rec), r.stdout)

    def test_the_build_is_02_d1_build_v_as_the_child_on_the_held_lock(self):
        p, _ = run_pool(self, V, digest=digest(39))
        r = ok(self, p.updater('pass'))
        self.assertEqual(p.d1_calls(), [{'argv': ['build', V], 'fd9': True, 'held': True, 'shares': True}])
        self.assertIn("runner-updater: pass: building runner %s for this release's image (recipe %s): 02-d1.sh build %s"
                      % (V, p.recipe(), V), r.stdout)
        self.assertIn('BUILD DONE (D1): a substitute', r.stdout)
        self.assertIn('runner-updater: pass: built runner %s' % V, r.stdout)
        self.assertEqual(state(p), {'format': 1, 'on': True, 'stops': []})
        r = ok(self, p.updater('pass'))                       # its record now: the next pass builds nothing
        self.assertEqual(len(p.d1_calls()), 1)
        self.assertIn('is built for this release', r.stdout)

    def test_a_build_that_waits_writes_no_stop(self):
        p, _ = run_pool(self, V, rc=75, out='WAIT GitHub\'s rate limit: nothing was built; run it again later\n')
        r = ok(self, p.updater('pass'))
        self.assertIn('runner-updater: pass: WAIT 02-d1.sh build %s waits (exit 75)' % V, r.stdout)
        self.assertEqual(state(p), {'format': 1, 'on': True, 'stops': []})
        self.assertEqual(len(p.d1_calls()), 1)

    def test_a_build_that_fails_writes_its_check_failed_stop_by_rename(self):
        p, _ = run_pool(self, V, rc=1, out='== 5. the runner image\n' + FAIL + 'trailing text\n')
        p.hooks()                                              # no hook: the dd and mv substitutes log the order
        ino = os.stat(STATE).st_ino
        r = p.updater('pass')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('runner-updater: STOP check failed (runner %s): %s' % (V, FAIL.strip()), r.stdout)
        self.assertEqual(state(p)['stops'], [stop('check failed', V, text=FAIL.strip(), step='build',
                                                  build_user='root')])
        self.assertNotEqual(os.stat(STATE).st_ino, ino, 'not written by rename')
        ev = p.events()
        self.assertLess(ev.index('dd state.json.new'), ev.index('mv state.json'))
        r = ok(self, p.updater('pass'))                       # its version is never built again by a pass
        self.assertEqual(len(p.d1_calls()), 1)
        self.assertIn('runner-updater: pass: no build of runner %s: STOP check failed (runner %s)' % (V, V), r.stdout)

    def test_a_stop_holds_its_build_and_a_newer_release_proceeds_alone(self):
        held = stop('check failed', V, text='FAIL x', step='build', build_user='root')
        for why, version, stops, runs in (
                ('check failed of V', V, [held], False),
                ('a STOP that names no version', V, [stop('check failed', None, text='FAIL x')], False),
                ('a STOP a newer release does not proceed past', NEWER, [stop('DISK', V)], False),
                ('a STOP this release does not know', NEWER, [stop('A NEW STOP', V)], False),
                ('a newer release, the old STOP held', NEWER, [held], True),
                ('check failed of an older version', V, [stop('check failed', OLDER)], True)):
            with self.subTest(why):
                p, _ = run_pool(self, version, stops=stops)
                before = p.read(STATE)
                r = ok(self, p.updater('pass'))
                self.assertEqual(len(p.d1_calls()), 1 if runs else 0, r.stdout)
                if not runs:
                    self.assertIn('runner-updater: pass: no build of runner %s: STOP ' % version, r.stdout)
                    self.assertEqual(p.read(STATE), before)
                else:
                    self.assertEqual(state(p)['stops'], stops, 'the older STOP stays')

    def test_a_recipe_it_cannot_compute_refuses_and_builds_nothing(self):
        p, _ = run_pool(self, V)
        os.symlink('Dockerfile', os.path.join(p.build, 'image', 'link'))
        r = p.updater('pass')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("runner-updater: REFUSE this release's image recipe cannot be computed: image/link", r.stdout)
        self.assertEqual(p.d1_calls(), [])


# ---- build V, a person's path

@needs_container
class BuildCommand(unittest.TestCase):
    def test_build_v_works_while_off_and_clears_the_stop_of_v(self):
        other = stop('check failed', OLDER, text='FAIL y', step='build', build_user='root')
        p, _ = run_pool(self, V, on=False, stops=[stop('check failed', V, text='FAIL x', step='build',
                                                       build_user='root'), other])
        p.hooks()
        r = ok(self, p.updater('build', V))
        self.assertEqual(p.d1_calls(), [{'argv': ['build', V], 'fd9': True, 'held': True, 'shares': True}])
        self.assertIn('runner-updater: build: built runner %s' % V, r.stdout)
        self.assertIn('runner-updater: build: the STOP check failed of runner %s is cleared' % V, r.stdout)
        self.assertEqual(state(p), {'format': 1, 'on': False, 'stops': [other]})
        self.assertIn('mv state.json', p.events())
        self.assertEqual(p.gh.seen, [], 'build V asks GitHub nothing itself (02-d1.sh does)')

    def test_a_failed_build_v_writes_its_stop_and_keeps_it_with_the_new_line(self):
        p, _ = run_pool(self, V, on=False, rc=1, out=FAIL)
        r = p.updater('build', V)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(state(p)['stops'], [stop('check failed', V, text=FAIL.strip(), step='build',
                                                  build_user='root')])
        p.d1_stub(rc=1, out='FAIL another line\n')
        r = p.updater('build', V)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(state(p)['stops'], [stop('check failed', V, text='FAIL another line', step='build',
                                                  build_user='root')])

    def test_a_build_v_that_waits_keeps_the_state(self):
        held = stop('check failed', V, text='FAIL x', step='build', build_user='root')
        p, _ = run_pool(self, V, stops=[held], rc=75, out='WAIT a rate limit\n')
        before = p.read(STATE)
        r = p.updater('build', V)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn('runner-updater: WAIT 02-d1.sh build %s waits (exit 75)' % V, r.stdout)
        self.assertEqual(p.read(STATE), before)

    def test_build_v_waits_for_the_updater_lock(self):
        p, _ = run_pool(self, V)
        fd = hold_lock(self)
        pr = p.start([os.path.join(p.build, 'bin', 'runner-updater'), 'build', V])
        ready, _, _ = select.select([pr.stdout], [], [], 120)
        self.assertTrue(ready)
        first = pr.stdout.readline()
        self.assertIn('WAIT another run holds the updater lock %s' % LOCK, first)
        self.assertEqual(p.d1_calls(), [])
        fcntl.flock(fd, fcntl.LOCK_UN)
        out, _ = pr.communicate(timeout=120)
        self.assertEqual(pr.returncode, 0, first + out)
        self.assertEqual(len(p.d1_calls()), 1)


# ---- the text (runs anywhere)

class Text(unittest.TestCase):
    def test_the_header_names_run_user_s_role_its_state_and_commands(self):
        with open(os.path.join(REPO, 'linux-docker', 'bin', 'runner-updater')) as f:
            h = ' '.join(l.lstrip('#').strip() for l in f.read().split('\nset -uo pipefail\n', 1)[0].splitlines())
        for s in ('RUN_USER', 'build VERSION', 'THE BUILD PASS', '02-d1.sh build', 'check failed', 'fd 9',
                  'the build record', 'DUE'):
            self.assertIn(s, h)

    def test_the_readme_names_run_user_s_commands(self):
        with open(os.path.join(REPO, 'linux-docker', 'README.md')) as f:
            text = f.read()
        self.assertIn('| `bin/runner-updater` | RS_USER, RUN_USER |', text)
        sec = text.split('\n## The updater: status, on, off, pass, build\n', 1)[1].split('\n## ', 1)[0]
        for s in ("ssh <RUN_USER>@<host> '~/bin/runner-updater build <runner version>'", 'runner-updater pass',
                  'check failed', 'would switch hz-docker to'):
            self.assertIn(s, sec)
        self.assertRegex(text, r'(?s)\n10\. \*\*The updater \(RS_USER and RUN_USER\)\.\*\*.*Then the same line with '
                               r'`<RUN_USER>`')


if __name__ == '__main__':
    unittest.main()
