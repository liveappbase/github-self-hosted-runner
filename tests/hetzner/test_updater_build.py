"""linux-docker/bin/runner-updater as RUN_USER (S2b-3b-2; PLAN D1 "Hetzner's two users", D2 HETZNER BUILD, D7, D11):
the same program as RS_USER's, and the user decides the role (RS_USER's, else RUN_USER's; any other user: REFUSE).
RUN_USER's own state STATEDIR/state.json (format 1: `on`, `stops` [{stop, version, user, detail}]; missing: OFF, nothing
held; a member it does not read: WAIT, exit 4), and its commands:

- `status` (no lock, writes nothing), `on`, `off` (they wait for the updater lock);
- `pass`, THE BUILD PASS (a timer's entry later): the lock only tried; OFF ends it with no network; the latest release
  (rr_eligible): WAIT or not eligible is its line, exit 0; this release's recipe of ~/build/image (rr_recipe); a build
  record of (V, recipe) is "built", exit 0, and it clears a `check failed` STOP of V (by rename); a STOP that holds V
  (stops.jq: a `check failed` of V; a newer release proceeds alone past an older one) is its line, exit 0, and no
  build; else `~/build/setup/02-d1.sh build V` runs as its CHILD on the lock it holds (fd 9). 02-d1.sh exit 0:
  "built"; 75: WAIT, exit 0, no STOP; 129, 141, 143 (SIGHUP, SIGPIPE, SIGTERM): CUT, exit 0, no STOP; else STOP `check
  failed` of V with the cause 02-d1.sh printed (the REFUSE line right before its last FAIL line, else that FAIL line),
  written by rename, exit 1;
- `build V`, a person's path: it waits for the lock, runs 02-d1.sh build V while OFF too; exit 0 clears the `check
  failed` STOP of V; a failure prints the cause, exit 1, and writes no STOP (one that is there stays).

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
import signal
import time
import unittest

from tests.hetzner.support import HANG, REPO, RS_USER, Pool, digest, needs_container, run_pool

V = '2.339.0'
OLDER, NEWER = '2.338.2', '2.340.0'
STATEDIR = Pool.STATE
STATE = os.path.join(STATEDIR, 'state.json')
LOCK = os.path.join(STATEDIR, 'lock')
DAY = 86400
FAIL = 'FAIL docker build failed: no record, image.ref NOT changed\n'
USAGE = 'usage: runner-updater status | on | off | pass | back hz-docker | build VERSION'   # its one usage line


# rm, for the TERM-window cell: an rm whose arguments name BUILDOUT (build.out: build_child's first step, right before
# the fork of 02-d1.sh) writes barrier.json {pid: its own, ppid: the updater's}, ignores SIGTERM (the updater gets it),
# and waits until the cell writes barrier.go (at most 600 s; then barrier.timeout, exit 124). Then, and for any other
# arguments, it is the real rm.
RM_BARRIER = r'''#!/usr/bin/python3 -I
import json, os, signal, sys, time
SB = @SB@
a = sys.argv[1:]
if any(x.endswith('/build.out') for x in a):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with open(SB + '/barrier.json.new', 'w') as f:
        json.dump({'pid': os.getpid(), 'ppid': os.getppid()}, f)
    os.replace(SB + '/barrier.json.new', SB + '/barrier.json')
    for _ in range(12000):
        if os.path.exists(SB + '/barrier.go'):
            break
        time.sleep(0.05)
    else:
        open(SB + '/barrier.timeout', 'w').close()
        sys.exit(124)
os.execv('/bin/rm', ['rm'] + a)
'''

# 02-d1.sh, for the cell of a TERM that reaches the updater alone (fix round 2): it logs its call as support.D1_STUB
# does (logs/d1.log), writes d1late.json {pid: its own, ppid: its parent's, the updater's}, waits until the cell writes
# d1late.go (at most 600 s; then d1late.timeout, exit 124), then prints d1late.cfg's out and exits with its rc.
D1_LATE = r'''#!/usr/bin/python3 -I
import json, os, sys, time
SB = @SB@
with open(SB + '/logs/d1.log', 'a') as f:
    f.write(json.dumps({'argv': sys.argv[1:]}) + '\n')
with open(SB + '/d1late.json.new', 'w') as f:
    json.dump({'pid': os.getpid(), 'ppid': os.getppid()}, f)
os.replace(SB + '/d1late.json.new', SB + '/d1late.json')
for _ in range(12000):
    if os.path.exists(SB + '/d1late.go'):
        break
    time.sleep(0.05)
else:
    open(SB + '/d1late.timeout', 'w').close()
    sys.exit(124)
c = json.load(open(SB + '/d1late.cfg'))
sys.stdout.write(c['out'])
sys.stdout.flush()
sys.exit(c['rc'])
'''
NINE = '9' * 9                    # the most digits of one part of a version (the updater's VERSION_RE)
TEN = '1' + '0' * 9               # one more


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
                self.assertIn(USAGE, r.stderr)
        self.assertEqual(p.d1_calls(), [])

    def test_build_takes_a_version_of_1_to_9_digits_in_each_part(self):
        """Fix round 2 (Opus r2 F3): `build VERSION`'s usage is the ONE version pattern RS_USER's status shows a
        version by (VERSION_RE: each part 1 to 9 digits), so a version a person retries is one RS_USER's status can
        show: 10 digits in any part is usage (exit 2), and no 02-d1.sh runs. Control: 9 digits in each part runs
        02-d1.sh build with it."""
        p, _ = run_pool(self, V, on=False)
        for v in (TEN + '.0.0', '2.' + TEN + '.0', '2.339.' + TEN):
            with self.subTest(v):
                r = p.updater('build', v)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(USAGE, r.stderr)
        self.assertEqual(p.d1_calls(), [])
        big = '.'.join([NINE] * 3)                                   # the control
        ok(self, p.updater('build', big))
        self.assertEqual([c['argv'] for c in p.d1_calls()], [['build', big]])


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
        """RUN_USER's state is 0640 (fix round 1, PLAN D1 11-05: RS_USER reads it through RUN_USER's group; until then
        0600): test_modes.py runs it as two real users."""
        p, _ = run_pool(self, V, on=None)
        self.assertIn('runner-updater: on: the updater is ON', ok(self, p.updater('on')).stdout)
        self.assertEqual(state(p), {'format': 1, 'on': True, 'stops': []})
        self.assertEqual(os.stat(STATE).st_mode & 0o777, 0o640)
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

    def test_a_build_cut_by_a_signal_holds_no_stop_and_the_next_pass_builds_again(self):
        """Opus r1 F2: 02-d1.sh ended by SIGHUP, SIGPIPE or SIGTERM (exit 129, 141, 143: an ssh drop, a reboot, a timer
        stop) was CUT, and no check failed: a line, no STOP, exit 0, and the next pass builds V again. Control:
        SIGKILL's 137 (an OOM kill too: a build that fails each time must not loop) and 1 are `check failed`, and the
        next pass builds nothing."""
        for rc, cut in ((129, 'SIGHUP'), (141, 'SIGPIPE'), (143, 'SIGTERM'), (137, None), (1, None)):
            with self.subTest(rc=rc):
                p, _ = run_pool(self, V, rc=rc, out='== 5. the runner image of release v%s\n' % V)
                r = p.updater('pass')
                if cut:
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertIn('runner-updater: pass: CUT 02-d1.sh build %s ended by %s (exit %d): no STOP; the '
                                  'next pass builds it again' % (V, cut, rc), r.stdout)
                    self.assertEqual(state(p)['stops'], [])
                else:
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertEqual([(s['stop'], s['version']) for s in state(p)['stops']], [('check failed', V)])
                ok(self, p.updater('pass'))
                self.assertEqual(len(p.d1_calls()), 2 if cut else 1)

    def test_systemd_s_stop_of_the_unit_during_a_build_is_a_cut(self):
        """S2b-3b-3: the timer's unit bounds a pass (config/runner-updater.service, TimeoutStartSec), and systemd's stop
        (that bound, a shutdown, `systemctl --user stop`) is SIGTERM to EVERY process of the unit's cgroup: the
        updater's own, not only 02-d1.sh's. The pass lives to see 02-d1.sh's 143: its CUT line, exit 0, no STOP, the
        lock free, and the next pass builds V again. Control: SIGKILL to the same group (systemd's last word, after
        TimeoutStopSec) leaves no line at all; still no STOP (the updater wrote nothing)."""
        for sig, cut in ((signal.SIGTERM, True), (signal.SIGKILL, False)):
            with self.subTest(signal=sig.name):
                p, _ = run_pool(self, V)
                p.d1_stub(out='== 5. the runner image of release v%s\n' % V, hang=True)
                before = p.read(STATE)
                pr = p.updater_start('pass')                     # a session of its own: its group is the unit's
                for _ in range(2400):                            # the state "02-d1.sh runs", never a time; a bound
                    if p.d1_calls():
                        break
                    time.sleep(0.05)
                self.assertEqual(len(p.d1_calls()), 1, 'the build never started')
                os.killpg(pr.pid, sig)
                out, _ = pr.communicate(timeout=120)
                if cut:
                    self.assertEqual(pr.returncode, 0, out)
                    self.assertIn('runner-updater: pass: CUT 02-d1.sh build %s ended by SIGTERM (exit 143): no STOP; '
                                  'the next pass builds it again' % V, out)
                else:
                    self.assertEqual(pr.returncode, -signal.SIGKILL, out)
                    self.assertNotIn('CUT', out)
                self.assertEqual(p.read(STATE), before)
                # the lock: free at once after a CUT (the pass waited for 02-d1.sh, which shares it); after the
                # control's SIGKILL, free once the killed child has exited too (that state is waited for, never a time)
                fd = os.open(LOCK, os.O_RDONLY)
                try:
                    for _ in range(1 if cut else 2400):
                        try:
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            time.sleep(0.05)
                    else:
                        self.fail('the updater lock is still held')
                finally:
                    os.close(fd)
                p.d1_stub(out='BUILD DONE (D1): a substitute\n', digest=digest(39))
                r = ok(self, p.updater('pass'))
                self.assertIn('runner-updater: pass: built runner %s' % V, r.stdout)
                self.assertEqual(len(p.d1_calls()), 2)

    def test_a_term_before_the_fork_starts_no_build(self):
        """Codex F1 (fix round 1): the build pass's TERM trap is set before build_child's `rm` of BUILDOUT and the fork
        of 02-d1.sh. A TERM there (systemd's stop of the unit: every process of it) is recorded, and the pass checks it
        right before the fork: "CUT ... (no build started)", exit 0, no 02-d1.sh start, no STOP, the state byte for byte
        the same. The barrier is that `rm` (RM_BARRIER, the cell's own substitute): it waits until the cell lets it
        go, so the TERM comes at a known point; every wait is bounded (timeout's 124: HUNG). Controls: no TERM, and the
        same pass starts 02-d1.sh; a TERM while 02-d1.sh runs is the CUT after it ends
        (test_systemd_s_stop_of_the_unit_during_a_build_is_a_cut)."""
        for why, term in (('a TERM at the barrier', True), ('no TERM (the control): the build starts', False)):
            with self.subTest(why):
                p, _ = run_pool(self, V)
                p.write(p.path('stubs', 'rm'), RM_BARRIER.replace('@SB@', repr(p.root)), 0o755)
                before = p.read(STATE)
                pr = p.start(['timeout', '-k', '10', str(HANG), os.path.join(p.build, 'bin', 'runner-updater'), 'pass'])
                b = None
                for _ in range(2400):                  # the state "rm waits at the barrier", never a time; a bound
                    t = p.read(p.path('barrier.json'))
                    if t:
                        b = json.loads(t)
                        break
                    time.sleep(0.05)
                self.assertIsNotNone(b, 'the pass never reached the barrier')
                self.assertEqual(p.d1_calls(), [], 'a build started before the barrier')
                if term:
                    os.kill(b['ppid'], signal.SIGTERM)     # the updater, and its rm: what systemd's stop reaches
                    os.kill(b['pid'], signal.SIGTERM)
                p.write(p.path('barrier.go'), '')
                out, _ = pr.communicate(timeout=HANG + 30)
                self.assertNotEqual(pr.returncode, 124, 'HUNG: ' + out)
                self.assertFalse(os.path.exists(p.path('barrier.timeout')), 'the barrier was never let go')
                if term:
                    self.assertEqual(pr.returncode, 0, out)
                    self.assertEqual(p.d1_calls(), [], 'a build started after the TERM: ' + out)
                    self.assertIn('runner-updater: pass: CUT 02-d1.sh build %s by SIGTERM before it started (no build '
                                  'started): no STOP; the next pass builds it again' % V, out)
                    self.assertEqual(p.read(STATE), before)
                else:
                    self.assertEqual(pr.returncode, 0, out)
                    self.assertEqual(len(p.d1_calls()), 1, out)
                    self.assertIn('runner-updater: pass: built runner %s' % V, out)

    def test_a_term_that_reaches_only_the_updater_during_the_build_is_a_cut(self):
        """Opus r2 F2, Codex r2 F4 (fix round 2): a TERM that reaches the updater while 02-d1.sh runs and not 02-d1.sh
        (THE TERM WINDOW's residual: a 02-d1.sh forked after systemd's TERM runs on), then a 02-d1.sh that fails (exit
        1: in a shutdown its `docker info` fails): CUT, exit 0, no STOP (the state byte for byte), and the next pass
        builds V again (until fix round 2 it held `check failed`). The TERM goes to the updater's pid alone while
        02-d1.sh waits for the cell (D1_LATE); every wait is bounded (timeout's 124: HUNG). Controls, the other way:
        no TERM and the same exit 1 writes the STOP, exit 1; a TERM and exit 0 is still `built runner V`."""
        for why, term, rc in (('a TERM, then exit 1', True, 1), ('no TERM, exit 1 (the control)', False, 1),
                              ('a TERM, then exit 0 (the control)', True, 0)):
            with self.subTest(why):
                p, _ = run_pool(self, V)
                p.write(p.path('stubs', 'd1late.py'), D1_LATE.replace('@SB@', repr(p.root)), 0o755)
                p.write(os.path.join(p.build, 'setup', '02-d1.sh'),
                        '#!/bin/bash\nexec /usr/bin/python3 -I %s "$@"\n' % p.path('stubs', 'd1late.py'), 0o755)
                p.write(p.path('d1late.cfg'), json.dumps({'rc': rc, 'out': '== 5. the runner image\n' + FAIL}))
                before = p.read(STATE)
                pr = p.start(['timeout', '-k', '10', str(HANG), os.path.join(p.build, 'bin', 'runner-updater'), 'pass'])
                b = None
                for _ in range(2400):                  # the state "02-d1.sh waits for the cell", never a time; a bound
                    t = p.read(p.path('d1late.json'))
                    if t:
                        b = json.loads(t)
                        break
                    time.sleep(0.05)
                self.assertIsNotNone(b, 'the pass never started 02-d1.sh')
                with open('/proc/%d/cmdline' % b['ppid'], 'rb') as f:
                    self.assertIn(b'runner-updater', f.read(), "02-d1.sh's parent is not the updater")
                if term:
                    os.kill(b['ppid'], signal.SIGTERM)     # the updater alone: 02-d1.sh gets no TERM
                p.write(p.path('d1late.go'), '')
                out, _ = pr.communicate(timeout=HANG + 30)
                self.assertNotEqual(pr.returncode, 124, 'HUNG: ' + out)
                self.assertFalse(os.path.exists(p.path('d1late.timeout')), 'the cell never let 02-d1.sh go')
                self.assertEqual(len(p.d1_calls()), 1, out)
                if term and rc == 1:
                    self.assertEqual(pr.returncode, 0, out)
                    self.assertIn('runner-updater: pass: CUT 02-d1.sh build %s exited 1 after a SIGTERM reached this '
                                  'run (a stop of its unit): no STOP; the next pass builds it again' % V, out)
                    self.assertNotIn('STOP check failed', out)
                    self.assertEqual(p.read(STATE), before)
                    p.d1_stub(out='BUILD DONE (D1): a substitute\n', digest=digest(39))
                    r = ok(self, p.updater('pass'))
                    self.assertIn('runner-updater: pass: built runner %s' % V, r.stdout)
                    self.assertEqual(len(p.d1_calls()), 2)
                elif term:
                    self.assertEqual(pr.returncode, 0, out)
                    self.assertIn('runner-updater: pass: built runner %s' % V, out)
                    self.assertNotIn('CUT', out)
                    self.assertEqual(p.read(STATE), before)
                else:
                    self.assertEqual(pr.returncode, 1, out)
                    self.assertIn('runner-updater: STOP check failed (runner %s): %s' % (V, FAIL.strip()), out)
                    self.assertEqual([(s['stop'], s['version']) for s in state(p)['stops']], [('check failed', V)])

    def test_a_pass_builds_no_version_the_reader_cannot_show(self):
        """Fix round 2 (the writer half of Opus r2 F3: ONE version pattern, VERSION_RE): GitHub's latest release whose
        version has a part of 10 digits is not built by a pass: one line, exit 0, no 02-d1.sh, no STOP (a STOP of it
        would be one RS_USER's status cannot show and `build VERSION` cannot retry), and the line holds no such
        version. Control: 9 digits in a part is built, and its failure holds the STOP of that version."""
        for why, version, built in (('10 digits in a part', '2.' + TEN + '.0', False),
                                    ('9 digits in a part (the control)', '2.' + NINE + '.0', True)):
            with self.subTest(why):
                p, _ = run_pool(self, version, rc=1, out=FAIL)
                before = p.read(STATE)
                r = p.updater('pass')
                if built:
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertEqual(len(p.d1_calls()), 1, r.stdout)
                    self.assertEqual([(s['stop'], s['version']) for s in state(p)['stops']], [('check failed', version)])
                    continue
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(p.d1_calls(), [], r.stdout)
                self.assertEqual(p.read(STATE), before)
                self.assertIn("runner-updater: pass: no build: the latest release's version is not N.N.N of 1 to 9 "
                              "digits each", r.stdout)
                self.assertNotIn(TEN, r.stdout)

    def test_a_pass_that_finds_the_record_of_v_clears_its_check_failed_stop(self):
        """Opus r1 F3 (a): a person built V by README "A new runner release" step 1 (02-d1.sh build V), after a pass's
        build of V failed: the next pass finds the record of (V, this recipe), builds nothing, and removes the `check
        failed` STOP of V (by rename). A STOP of another version, and another STOP of V, stay. Control: the same pass
        with no STOP of V to clear writes nothing (the state byte-equal)."""
        held = stop('check failed', V, text='FAIL x', step='build', build_user='root')
        others = [stop('check failed', OLDER, text='FAIL y', step='build', build_user='root'), stop('DISK', V)]
        for why, stops in (('a check failed of V', [held] + others), ('control: none of V', others)):
            with self.subTest(why):
                p, _ = run_pool(self, V, stops=stops)
                p.record(V, digest(39))
                p.hooks()
                before, ino = p.read(STATE), os.stat(STATE).st_ino
                r = ok(self, p.updater('pass'))
                self.assertIn('runner-updater: pass: runner %s is built for this release\'s image' % V, r.stdout)
                self.assertEqual(p.d1_calls(), [])
                if held in stops:
                    self.assertIn('runner-updater: pass: the STOP check failed of runner %s is cleared' % V, r.stdout)
                    self.assertEqual(state(p)['stops'], others)
                    self.assertNotEqual(os.stat(STATE).st_ino, ino, 'not written by rename')
                    self.assertIn('mv state.json', p.events())
                else:
                    self.assertNotIn('is cleared', r.stdout)
                    self.assertEqual(p.read(STATE), before)

    def test_the_stop_names_the_cause_02_d1_sh_printed(self):
        """Opus r1 F4: the STOP's text (and status's line) is the cause 02-d1.sh printed: the REFUSE line right before
        its last FAIL line (that FAIL line then says only "the REFUSE line above says why"), else that FAIL line; with
        no FAIL line, its last REFUSE line. Controls: a FAIL line alone is that line; a REFUSE line earlier than the
        line before the FAIL line is no cause of it."""
        why = ("http://gh/actions-runner-linux-x64-%s.tar.gz: its sha256 is %s, not the release asset's digest "
               "sha256:%s" % (V, 'a' * 64, 'b' * 64))
        refuse = 'runner-release: REFUSE ' + why
        fail = 'FAIL release v%s: nothing was built (the REFUSE line above says why)' % V
        host = '02-d1.sh: REFUSE no host config /etc/liveapp-ci/host.conf (linux-docker/README.md)'
        for case, out, text in (
                ('a REFUSE line right before the FAIL line', 'OK   the recipe\n%s\n%s\n' % (refuse, fail), refuse),
                ('a REFUSE line and no FAIL line', host + '\n', host),
                ('control: a FAIL line alone', 'OK   x\n' + FAIL, FAIL.strip()),
                ('control: an earlier REFUSE line', 'runner-release: REFUSE early\nOK   y\n' + FAIL, FAIL.strip())):
            with self.subTest(case):
                p, _ = run_pool(self, V, rc=1, out=out)
                r = p.updater('pass')
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertEqual([s['detail']['text'] for s in state(p)['stops']], [text])
                self.assertIn('runner-updater: STOP check failed (runner %s): %s;' % (V, text), r.stdout)
                self.assertIn('hz-docker: STOP check failed (runner %s): %s. Next: as root: `runner-updater build %s`'
                              % (V, text, V), ok(self, p.updater('status')).stdout)
        p, _ = run_pool(self, V, rc=1, out='no line of either kind\n')
        p.updater('pass')
        self.assertEqual([s['detail']['text'] for s in state(p)['stops']],
                         ['02-d1.sh build %s exited 1 and printed no FAIL or REFUSE line (its output: %s)'
                          % (V, os.path.join(STATEDIR, 'build.out'))])

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

    def test_a_failed_build_v_writes_no_stop_and_keeps_the_one_there(self):
        """Opus r1 F3 (b): a person's `build V` that fails prints why and exits 1, and the state stays byte for byte: no
        new STOP (a typo such as 2.399.0, which GitHub answers 404, would otherwise hold a STOP nothing clears), and a
        STOP that is there stays. Only a pass writes `check failed`. Control: a pass whose build fails the same way
        holds the STOP."""
        typo = '2.399.0'
        refuse = ('runner-release: REFUSE GitHub answered 404 for http://gh/repos/actions/runner/releases/tags/v%s'
                  % typo)
        out = ('OK   the recipe\n%s\nFAIL release v%s: nothing was built (the REFUSE line above says why)\n'
               % (refuse, typo))
        held = stop('check failed', typo, text='FAIL x', step='build', build_user='root')
        for why, stops in (('no STOP', []), ('a STOP of that version', [held])):
            with self.subTest(why):
                p, _ = run_pool(self, V, on=False, rc=1, out=out, stops=stops)
                before = p.read(STATE)
                r = p.updater('build', typo)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('runner-updater: build: runner %s is not built: %s; the state is as it was'
                              % (typo, refuse), r.stdout)
                self.assertEqual(p.read(STATE), before)
                self.assertEqual(p.d1_calls()[0]['argv'], ['build', typo])
        p, _ = run_pool(self, typo, rc=1, out=out)                     # the control: a pass's failure
        r = p.updater('pass')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(state(p)['stops'], [stop('check failed', typo, text=refuse, step='build', build_user='root')])

    def test_a_build_v_that_waits_keeps_the_state(self):
        held = stop('check failed', V, text='FAIL x', step='build', build_user='root')
        p, _ = run_pool(self, V, stops=[held], rc=75, out='WAIT a rate limit\n')
        before = p.read(STATE)
        r = p.updater('build', V)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn('runner-updater: WAIT 02-d1.sh build %s waits (exit 75)' % V, r.stdout)
        self.assertEqual(p.read(STATE), before)

    def test_an_inherited_termed_never_skips_a_build(self):
        """Codex r2 F4 (fix round 2): TERMED (the build pass's record of a TERM) is set empty at the program's start,
        for every command, so a TERMED in the caller's environment never skips a build: `TERMED=1 runner-updater
        build V` with a `check failed` STOP of V and a 02-d1.sh that fails starts 02-d1.sh, prints why, exits 1, and
        the STOP stays (until fix round 2 it started none, said `built runner V` and cleared the STOP). A pass the
        same (it set TERMED itself before, so it was never red). The control that comes out the other way: a TERM at
        the pass's pre-fork barrier starts no 02-d1.sh (BuildPass.test_a_term_before_the_fork_starts_no_build)."""
        held = stop('check failed', V, text='FAIL x', step='build', build_user='root')
        for args in (('build', V), ('pass',)):
            with self.subTest(args):
                p, _ = run_pool(self, V, stops=[held] if args[0] == 'build' else [], rc=1, out=FAIL)
                before = p.read(STATE)
                r = p.updater(*args, env=dict(p.env(), TERMED='1'))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertEqual(len(p.d1_calls()), 1, 'no 02-d1.sh started: ' + r.stdout)
                if args[0] == 'build':
                    self.assertIn('runner-updater: build: runner %s is not built: %s;' % (V, FAIL.strip()), r.stdout)
                    self.assertNotIn('built runner', r.stdout)
                    self.assertEqual(p.read(STATE), before)
                else:
                    self.assertEqual(state(p)['stops'], [stop('check failed', V, text=FAIL.strip(), step='build',
                                                              build_user='root')])

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
                  'the build record', 'DUE', 'CUT', 'SIGPIPE', 'writes no STOP'):
            self.assertIn(s, h)

    def test_the_readme_names_run_user_s_commands(self):
        with open(os.path.join(REPO, 'linux-docker', 'README.md')) as f:
            text = f.read()
        self.assertIn('| `bin/runner-updater` | RS_USER, RUN_USER |', text)
        sec = text.split('\n## The updater: status, on, off, pass, build\n', 1)[1].split('\n## ', 1)[0]
        for s in ("ssh <RUN_USER>@<host> '~/bin/runner-updater build <runner version>'", 'runner-updater pass',
                  'check failed', 'hz-docker is due for runner', 'cut by a signal', 'holds no STOP',
                  'clears that STOP when it finds'):
            self.assertIn(s, sec)
        self.assertRegex(text, r'(?s)\n10\. \*\*The updater \(RS_USER and RUN_USER\)\.\*\*.*Then the same line with '
                               r'`<RUN_USER>`')

    def test_the_header_the_unit_and_the_readme_say_a_term_during_the_build_is_a_cut(self):
        """Fix round 2 (Opus r2 F2, Codex r2 F4): the header's THE TERM WINDOW, the unit's comment and the README's
        build pass say that a TERM that reached the updater while 02-d1.sh ran is a CUT with no STOP whatever 02-d1.sh
        then exits with (so the residual's "no STOP" is true), and the header that an inherited TERMED never skips a
        build. Control: each still names the CUT of a 02-d1.sh ended by SIGTERM."""
        with open(os.path.join(REPO, 'linux-docker', 'bin', 'runner-updater')) as f:
            h = ' '.join(l.lstrip('#').strip() for l in f.read().split('\nset -uo pipefail\n', 1)[0].splitlines())
        with open(os.path.join(REPO, 'linux-docker', 'config', 'runner-updater.service')) as f:
            svc = ' '.join(f.read().replace('#', ' ').split())
        with open(os.path.join(REPO, 'linux-docker', 'README.md')) as f:
            sec = f.read().split('\n## The updater: status, on, off, pass, build\n', 1)[1].split('\n## ', 1)[0]
        for name, part, says in (
                ('the header', h, ('an inherited TERMED never skips a build',
                                   'prints a CUT and writes no STOP, whatever it exited with')),
                ('the unit', svc, ('when that 02-d1.sh ends first, the updater prints a CUT and writes no STOP',)),
                ('the README', sec, ('is a `CUT` too, whatever 02-d1.sh then exits with',))):
            with self.subTest(name):
                for s in says:
                    self.assertIn(s, part)
                self.assertIn('SIGTERM', part)                                       # the control
                self.assertIn('CUT', part)


if __name__ == '__main__':
    unittest.main()
