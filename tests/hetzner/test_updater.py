"""linux-docker/bin/runner-updater, the runner-image updater on the Linux host as RS_USER (S2b-3a: status, on, off and
a pass that measures, asks the decision core and prints what it WOULD do), and setup/runner-facts.sh, the ONE copy of
the measuring helpers it shares with pool-image.sh (PLAN D1, D6, D7, D11; core/README.md, "The call" and "facts"):

- THE STATE (STATEDIR/state.json, format 1): fresh = OFF; another format WAITs (exit 4) with every command; a format 1
  state of another shape is REFUSED (exit 1); a member this release does not read WAITs; every write is a rename after
  a sync, and a sync that fails is a STOP with the state as it was.
- status: no lock, no write anywhere, ONE read; status.jq's answer checked as a pass checks it: a `wait` is its lines,
  then WAIT (exit 4), another answer is a STOP; on and off wait for the updater lock; off refuses while a window
  journal is open.
- pass: it only TRIES the lock; OFF ends it at once; an open window journal is "STOP RECOVER needed (S2b-3c)"; an
  untested jq is exit 3; the facts (host "hz"), in the Studio's order: proc before, the log position (one open of
  runner.log, and the text since the core state's boundary through it), proc after, the config (installed: the
  `renamed` epoch of the newest closed window journal that installed config.toml's sha, else its mtime), the family
  hz-docker of the host config's sets, the state's candidate, back_until, STOPs and restart, the /healthz pair; idle,
  r1, keep, status; the core state written back only when all four decided; then what it WOULD do, and DUE's one line
  for hz-docker (S2b-3b-2: its steps are test_release_due.py's; RUN_USER's role is test_updater_build.py's).
- It acts on nothing: no systemctl start, stop or restart, no pool-image.sh or 02-d1.sh, no change to config.toml or
  to pool-image.sh's files.

Every cell runs the real scripts (pin lines rewritten: support.Pool) in a throwaway container, most with the fake
clock (support.Pool.fake_clock): no cell asserts a time it waited, only the clock reads the substitutes gave and the
order of their events. The log text is runscaler's own text format (core/README.md, "The log").
"""
import fcntl
import hashlib
import json
import os
import re
import select
import subprocess
import time
import unittest

from tests.hetzner.support import REPO, Pool, digest, healthz, needs_container, ref, sha256_file

UPD = os.path.join(REPO, 'linux-docker', 'bin', 'runner-updater')
LIB = os.path.join(REPO, 'linux-docker', 'setup', 'runner-facts.sh')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
README = os.path.join(REPO, 'linux-docker', 'README.md')
V = '2.339.0'
NEW, OLD = digest(39), digest(38)
MAIN, SMALL = 'linux-ci-main', 'linux-ci-small'
FAM = 'hz-docker'
LINES = {MAIN: ref(OLD), SMALL: ref(OLD)}
STATEDIR = Pool.STATE
STATE = os.path.join(STATEDIR, 'state.json')
PASS = os.path.join(STATEDIR, 'pass')
LOCK = os.path.join(STATEDIR, 'lock')
WINDOW = os.path.join(STATEDIR, 'window')
WINDOWS = os.path.join(STATEDIR, 'windows')
H = 'ab' * 32
DUE = r'(?m)^runner-updater: pass: (hz-docker is not due: |would switch hz-docker to )'   # DUE's one line
# runscaler's own records (the real log's text format; the set names are host.conf.example's)
REAL = ('2026-10-25 20:04:01 INFO linux-ci-main: Scaling up runner currentCount=0 desiredCount=1\n'
        '2026-10-25 20:04:01 INFO linux-ci-main: refreshing token githubConfigUrl=https://github.com/example-org\n'
        '2026-10-25 20:04:02 INFO linux-ci-main: Runner started name=runner-2f4af1f2 instanceID=2820738787a80b6cc91e4b5f'
        'e96095bacb4889385f433895835afa9336a40b6f startupTime=1.309319425s\n'
        '2026-10-26 01:10:12 WARN linux-ci-small: Runner exited before job completion; removing stale capacity '
        'name=runner-58c119b8\n')


def rec(t, lvl, msg):
    """One record of runscaler's log at log time t (epoch seconds, written as the UTC runscaler runs in)."""
    return '%s %s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(t)), lvl, msg)


def failed(t):
    return rec(t, 'ERRO', MAIN + ': Failed to start runner, will retry error="failed to create runner container: Error '
                                 'response from daemon: No such image: example-runner"')


def scaling(t):
    return rec(t, 'INFO', MAIN + ': Scaling up runner currentCount=0 desiredCount=1')


def completed(t, result):
    return rec(t, 'INFO', MAIN + ': Runner removed name=runner-8b9b64ca instanceID=83dafc48 reason=job-completed '
                                 'jobId=2ce18645-b726-290f-1564-ea0902058718 repo=example-org/example '
                                 'workflowRunId=15885850636 job="build (9150)" result=' + result)


def tree(root):
    """{path: what a write would change}: every file (mtime, size, mode) and folder (mtime) under root, but the
    substitutes' own: their answers, which Pool.run writes before each command (docker.json, curl.json, runner.json),
    their logs (logs/: the fake clock logs each read of it) and their folder (stubs/: python caches their module)."""
    out = {}
    for d, dirs, names in os.walk(root):
        if d == root:
            dirs[:] = [x for x in dirs if x not in ('logs', 'stubs')]
        out[d] = ('folder', os.stat(d).st_mtime_ns)
        for n in names:
            if d == root and n in ('docker.json', 'curl.json', 'runner.json'):
                continue
            s = os.lstat(os.path.join(d, n))
            out[os.path.join(d, n)] = (s.st_mtime_ns, s.st_size, s.st_mode)
    return out


def candidate(closed_at, version=V, lines=None):
    return {'version': version, 'lines': dict(lines or LINES), 'closed_at': closed_at}


def stop(name, version=None, **detail):
    return {'family': FAM, 'stop': name, 'version': version, 'user': None, 'detail': detail}


def wait_past(t):
    """Until the REAL clock's second is past t: a state of the clock, never a set time."""
    while int(time.time()) <= t:
        time.sleep(0.05)


class Rig:
    """A Pool whose production runs OLD (the registry serves OLD and NEW), with the fake clock; the updater's state ON
    (on=True), OFF (on=False) or none at all (on=None). production=False: no runscaler and no config at all (a cell
    whose commands end before the facts: it saves 03's run)."""

    def __init__(self, test, on=True, clock=True, families=None, production=True):
        self.t = test
        self.p = p = Pool(test)
        p.curl['served'] = [OLD, NEW]
        if production:
            p.production(OLD)
        if clock:
            p.fake_clock()
        for n in ('systemctl', 'curl'):              # the production's calls are not the updater's
            if os.path.exists(p.path('logs', n + '.log')):
                os.remove(p.path('logs', n + '.log'))
        self.log = p.rpath('runner.log')
        p.files()                                    # the substitutes' answer files exist before any command
        if on is not None:
            self.put({'format': 1, 'on': on, 'families': families or {}})

    def put(self, state=None, raw=None):
        os.makedirs(STATEDIR, mode=0o700, exist_ok=True)
        self.p.write(STATE, raw if raw is not None else json.dumps(state) + '\n', 0o600)

    def state(self):
        t = self.p.read(STATE)
        return None if t is None else json.loads(t)

    def raw(self):
        return self.p.read(STATE)

    def run(self, *args, **kw):
        return self.p.updater(*args, **kw)

    def ok(self, *args, **kw):
        r = self.run(*args, **kw)
        self.t.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        return r

    def out(self, name):
        return json.loads(self.p.read(os.path.join(PASS, name + '.json')))

    def facts(self):
        return self.out('facts')

    def text(self):
        with open(os.path.join(PASS, 'log.txt'), 'rb') as f:
            return f.read()

    def append(self, text, path=None):
        with open(path or self.log, 'ab') as f:
            f.write(text.encode() if isinstance(text, str) else text)

    def calls(self, verb):
        return [l for l in self.p.lines('systemctl') if l.split(' ')[1:2] == [verb]]

    def healthz_reads(self):
        return [c for c in self.p.calls('curl') if any(x.endswith('/healthz') for x in c['argv'])]

    def hold_lock(self):
        """The updater lock, held by THIS process (another open of the file: another holder) until release()."""
        os.makedirs(STATEDIR, mode=0o700, exist_ok=True)
        fd = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.t.addCleanup(os.close, fd)
        return fd

    def plant(self, rel, text):
        """A file of the cell's own ~/build copy replaced by TEXT (a planted fault; the shipped file is not touched)."""
        self.p.write(os.path.join(self.p.build, rel), text, 0o755 if rel.startswith('bin/') else 0o644)

    def program(self):
        with open(os.path.join(self.p.build, 'bin', 'runner-updater')) as f:
            return f.read()


def nothing_ran(t, g, r):
    """A pass that ended before the facts: no pass file, no systemctl and no /healthz read."""
    t.assertFalse(os.path.exists(os.path.join(PASS, 'facts.json')), r.stdout)
    t.assertEqual(g.p.lines('systemctl'), [])
    t.assertEqual(g.healthz_reads(), [])


# ---- the state

@needs_container
class State(unittest.TestCase):
    def test_a_fresh_install_is_off_and_status_writes_nothing_anywhere(self):
        g = Rig(self, on=None, production=False)
        before = tree(g.p.root)
        r = g.ok('status')
        self.assertIn('runner-updater: status: the updater is OFF', r.stdout)
        self.assertIn('family hz-docker: no candidate; back: none; rejected: none', r.stdout)
        self.assertIn('status: ok (0 STOPs)', r.stdout)
        after = tree(g.p.root)
        self.assertEqual(sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)), [],
                         'status wrote something')
        self.assertFalse(os.path.lexists(STATEDIR))
        # the control: the same snapshot sees a command that writes
        g.ok('on')
        self.assertNotEqual(tree(g.p.root), before)

    def test_on_and_off_and_status_says_which(self):
        g = Rig(self, on=None, production=False)
        self.assertIn('runner-updater: on: the updater is ON', g.ok('on').stdout)
        self.assertEqual(g.state(), {'format': 1, 'on': True, 'families': {}})
        self.assertEqual(os.stat(STATE).st_mode & 0o777, 0o600)
        self.assertIn('the updater is ON', g.ok('status').stdout)
        self.assertIn('runner-updater: off: the updater is OFF', g.ok('off').stdout)
        self.assertEqual(g.state(), {'format': 1, 'on': False, 'families': {}})
        self.assertIn('the updater is OFF', g.ok('status').stdout)

    def test_the_state_is_written_by_rename_after_a_sync_to_disk(self):
        g = Rig(self, on=False, production=False)
        g.p.hooks()                                     # no hook: the dd and mv substitutes log the order
        g.ok('on')
        ev = g.p.events()
        self.assertIn('dd state.json.new', ev)
        self.assertIn('mv state.json', ev)
        self.assertLess(ev.index('dd state.json.new'), ev.index('mv state.json'))
        self.assertTrue(g.state()['on'])
        self.assertFalse(os.path.lexists(STATE + '.new'))

    def test_a_sync_that_fails_is_a_stop_and_the_state_stays(self):
        g = Rig(self, on=False, production=False)
        g.p.hooks(('ddfail-file:state.json.new',))
        before = g.raw()
        r = g.run('on')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('runner-updater: STOP the state cannot be synced to disk', r.stdout)
        self.assertEqual(g.raw(), before)
        self.assertFalse(os.path.lexists(STATE + '.new'))

    def test_another_format_waits_with_every_command_and_nothing_is_written(self):
        for fmt in (2, None, '1'):
            with self.subTest(format=fmt):
                g = Rig(self, on=None, production=False)
                st = {'on': True, 'families': {}}
                if fmt is not None:
                    st['format'] = fmt
                g.put(st)
                before, mtime = g.raw(), os.stat(STATE).st_mtime_ns
                for cmd in ('status', 'on', 'off', 'pass'):
                    r = g.run(cmd)
                    self.assertEqual(r.returncode, 4, '%s: %s' % (cmd, r.stdout + r.stderr))
                    self.assertIn('runner-updater: WAIT the state %s has format %s' % (STATE, json.dumps(fmt)),
                                  r.stdout)
                self.assertEqual((g.raw(), os.stat(STATE).st_mtime_ns), (before, mtime))
                self.assertFalse(os.path.lexists(PASS))
        g = Rig(self, on=False, production=False)      # the control: format 1
        self.assertIn('the updater is OFF', g.ok('status').stdout)

    def test_a_member_this_release_does_not_read_waits(self):
        full = {'format': 1, 'on': True, 'core': {'format': 1},
                'restart': {'from': {'pid': 100, 'start': 1761955200}, 'to': {'pid': 101, 'start': 1761955300},
                            'stopped': {'inode': '42', 'offset': 0, 'sha': H}},
                'families': {FAM: {'candidate': candidate(1761955000), 'previous': dict(LINES), 'back_until': None,
                                   'rejected': ['2.338.0'], 'stops': [stop('DISK', text='free disk')]}}}
        cases = (
            ('images', lambda s: s.update(images={})),
            ('families.linux-tart', lambda s: s['families'].update({'linux-tart': {}})),
            ('families.hz-docker.recipe', lambda s: s['families'][FAM].update(recipe=H)),
            ('families.hz-docker.candidate.digest', lambda s: s['families'][FAM]['candidate'].update(digest=NEW)),
            ('families.hz-docker.stops[0].since', lambda s: s['families'][FAM]['stops'][0].update(since=1)),
            ('restart.why', lambda s: s['restart'].update(why='x')),
            ('restart.from.uid', lambda s: s['restart']['from'].update(uid=0)),
            ('restart.stopped.path', lambda s: s['restart']['stopped'].update(path='x')),
        )
        for member, change in cases:
            with self.subTest(member):
                g = Rig(self, on=None, production=False)
                st = json.loads(json.dumps(full))
                change(st)
                g.put(st)
                before = g.raw()
                for cmd in ('status', 'on', 'pass'):
                    r = g.run(cmd)
                    self.assertEqual(r.returncode, 4, '%s: %s' % (cmd, r.stdout + r.stderr))
                    self.assertIn('runner-updater: WAIT the state %s holds members this release does not read (%s)'
                                  % (STATE, member), r.stdout)
                self.assertEqual(g.raw(), before)

    def test_control_every_member_it_reads_is_read_and_kept(self):
        g = Rig(self, on=None, production=False)
        st = {'format': 1, 'on': False, 'core': {'format': 1},
              'restart': {'from': {'pid': 100, 'start': 1761955200}, 'to': {'pid': 101, 'start': 1761955300},
                          'stopped': {'inode': '42', 'offset': 0, 'sha': H}},
              'families': {FAM: {'candidate': candidate(1761955000), 'previous': dict(LINES),
                                 'back_until': 1762000000, 'rejected': ['2.338.0'],
                                 'stops': [stop('DISK', text='free disk')]}}}
        g.put(st)
        g.ok('status')
        g.ok('on')
        self.assertEqual(g.state(), dict(st, on=True))

    def test_a_format_1_state_of_another_shape_is_refused_and_left_as_it_is(self):
        cases = (
            ('not JSON', '{"format": 1,'),
            ('two objects', '{"format": 1, "on": false, "families": {}}\n{"format": 1}\n'),
            ('on is no boolean', {'format': 1, 'on': 'yes', 'families': {}}),
            ('families is no object', {'format': 1, 'on': False, 'families': []}),
            ('a version that is not N.N.N', {'format': 1, 'on': False, 'families': {FAM: {
                'candidate': candidate(1, version='2.339')}}}),
            ('an image that is no digest reference', {'format': 1, 'on': False, 'families': {FAM: {
                'previous': {MAIN: 'localhost:27500/linux-runner:latest'}}}}),
            ('a STOP of another family', {'format': 1, 'on': False, 'families': {FAM: {
                'stops': [dict(stop('DISK'), family='linux-tart')]}}}),
            ('a restart whose pid is 0', {'format': 1, 'on': False, 'families': {}, 'restart': {
                'from': {'pid': 0, 'start': 1}, 'to': {'pid': 101, 'start': 2},
                'stopped': {'inode': '42', 'offset': 0, 'sha': H}}}),
        )
        for why, st in cases:
            with self.subTest(why):
                g = Rig(self, on=None, production=False)
                g.put(raw=st if isinstance(st, str) else json.dumps(st) + '\n')
                before = g.raw()
                for cmd in ('status', 'on'):
                    r = g.run(cmd)
                    self.assertEqual(r.returncode, 1, '%s: %s' % (cmd, r.stdout + r.stderr))
                    self.assertRegex(r.stdout, r'runner-updater: REFUSE %s is not (one JSON object|a state of format 1 '
                                     r'this reads)' % re.escape(STATE))
                self.assertEqual(g.raw(), before)


# ---- status

@needs_container
class Status(unittest.TestCase):
    def test_each_line_of_the_family_and_the_core_s_stop_lines(self):
        switched, until = 1793692800, 1794297600      # 2026-11-03 and 2026-11-10, 08:00 UTC
        g = Rig(self, on=True, production=False, families={FAM: {
            'candidate': candidate(switched), 'back_until': until, 'rejected': ['2.338.0', '2.338.1'],
            'stops': [stop('check failed', V, text='03-runscaler.sh render, try 1: VALIDATE NON-API')]}})
        r = g.ok('status')
        self.assertIn('runner-updater: status: the updater is ON', r.stdout)
        self.assertIn('runner-updater: family hz-docker: candidate runner 2.339.0 (linux-ci-main=%s, linux-ci-small=%s), '
                      'switched 2026-11-03 08:00 UTC; back until 2026-11-10 08:00 UTC; rejected: 2.338.0, 2.338.1'
                      % (ref(OLD), ref(OLD)), r.stdout)
        self.assertIn('status: ok (1 STOPs)', r.stdout)
        self.assertIn('hz-docker: STOP check failed (runner 2.339.0): 03-runscaler.sh render, try 1: VALIDATE NON-API. '
                      'Next: `runner-updater retry hz-docker`', r.stdout)
        self.assertIn('hz-docker: `runner-updater back hz-docker` restores the previous image until 2026-11-10 08:00 UTC',
                      r.stdout)
        self.assertIn('runner-updater: STOP hz-docker check failed: known true; candidate closed: yes; version '
                      'rejected: no; a newer release proceeds alone: yes', r.stdout)
        self.assertNotIn('window journal', r.stdout)

    def test_an_unknown_stop_is_known_false_never_guessed(self):
        g = Rig(self, on=False, production=False, families={FAM: {'stops': [stop('A NEW STOP')]}})
        r = g.ok('status')
        self.assertIn('runner-updater: STOP hz-docker A NEW STOP: known false; candidate closed: unknown; version '
                      'rejected: unknown; a newer release proceeds alone: no', r.stdout)

    def test_an_open_window_journal_is_named(self):
        g = Rig(self, on=True, production=False)
        g.p.write(WINDOW, 'window 20261103080000-42\nkind switch\n', 0o600)
        r = g.ok('status')
        self.assertIn('runner-updater: status: a window journal is open: %s' % WINDOW, r.stdout)
        self.assertIn('RECOVER (S2b-3c)', r.stdout)

    def test_status_takes_no_lock(self):
        g = Rig(self, on=True, production=False)
        g.hold_lock()
        r = g.run('status', timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('the updater is ON', r.stdout)

    def test_untested_jq_stops_status_before_any_core_call(self):
        g = Rig(self, on=True, production=False)
        g.p.jq_version('jq-9.9')
        r = g.run('status')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('runner-updater: STOP untested jq: jq here prints [jq-9.9]', r.stdout)
        self.assertNotIn('status: ok', r.stdout)
        g.p.jq_version('jq-1.7.1' if 'jq-1.7.1' in self.jq_rows() else self.jq_rows()[0])   # the control
        self.assertIn('status: ok', g.ok('status').stdout)

    def jq_rows(self):
        """core/TESTED_JQ's versions for the area core (a helper: its name is no test_ name)"""
        with open(os.path.join(REPO, 'core', 'TESTED_JQ')) as f:
            return [l.split()[0] for l in f if l.strip() and not l.startswith('#') and ',core' in ',' + l.split()[1]]

    def test_a_core_that_cannot_decide_is_a_stop(self):
        g = Rig(self, on=True, production=False)
        g.plant('core/status.jq', 'error("planted")\n')
        r = g.run('status')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('runner-updater: STOP core could not decide (status)', r.stdout)

    def test_a_core_that_waits_prints_its_lines_then_waits_and_writes_nothing(self):
        """Opus r2 F1 (S2b-3a): status.jq answers `wait` when the core's own state is of a format it does not read: it
        decided nothing, so status prints its lines, then WAIT, exit 4, as a pass does, and writes nothing. Control:
        the core's own format, 1: exit 0, `ok`, no WAIT."""
        g = Rig(self, on=True, production=False)
        g.put({'format': 1, 'on': True, 'families': {}, 'core': {'format': 2}})
        before = tree(g.p.root)
        r = g.run('status')
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        out = r.stdout.splitlines()
        for l in ('runner-updater: status: the updater is ON', 'runner-updater: family hz-docker: no candidate; back: '
                  'none; rejected: none', 'status: wait (unknown state format)',
                  'status: the state has format 2; this core reads format 1: waiting'):
            self.assertIn(l, out[:-1])
        self.assertEqual(out[-1], 'runner-updater: WAIT the decision core waits (status: the state has format 2; this '
                                  'core reads format 1: waiting): status decides nothing, and it writes nothing')
        self.assertEqual(sorted(k for k, v in tree(g.p.root).items() if before.get(k) != v), [], 'status wrote')
        g.put({'format': 1, 'on': True, 'families': {}, 'core': {'format': 1}})      # the control
        r = g.ok('status')
        self.assertIn('status: ok (0 STOPs)', r.stdout.splitlines())
        self.assertNotIn('WAIT', r.stdout)

    def test_a_verdict_core_readme_does_not_name_for_status_jq_is_a_stop(self):
        """Opus r2 F1 (S2b-3a): status takes the verdicts core/README.md names for status.jq (ok, or wait), the
        pass's own set for it (ONE copy: decided); any other, also another program's (`not-idle`), is "core could not
        decide", exit 1. Control: a planted `ok` is printed, exit 0."""
        for verdict, rc in (('maybe', 1), ('not-idle', 1), ('ok', 0)):
            with self.subTest(verdict):
                g = Rig(self, on=True, production=False)
                g.plant('core/status.jq', '{verdict: %s, reason: "planted", lines: ["a planted line"]}\n'
                        % json.dumps(verdict))
                r = g.run('status')
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                if rc:
                    self.assertIn('runner-updater: STOP core could not decide (status)', r.stdout)
                    self.assertNotIn('a planted line', r.stdout)
                else:
                    self.assertIn('status: ok (planted)', r.stdout.splitlines())
                    self.assertIn('a planted line', r.stdout.splitlines())


# ---- on, off

@needs_container
class OnOff(unittest.TestCase):
    def test_off_refuses_while_a_window_journal_is_open_and_changes_nothing(self):
        g = Rig(self, on=True, production=False)
        g.p.write(WINDOW, 'window 20261103080000-42\n', 0o600)
        before = g.raw()
        r = g.run('off')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('runner-updater: REFUSE a window is open (%s): off never strands a window' % WINDOW, r.stdout)
        self.assertEqual(g.raw(), before)
        os.remove(WINDOW)                               # the control: no window, and off turns it off
        g.ok('off')
        self.assertFalse(g.state()['on'])

    def test_on_and_off_wait_for_the_updater_lock(self):
        for cmd, was in (('on', False), ('off', True)):
            with self.subTest(cmd):
                g = Rig(self, on=was)
                fd = g.hold_lock()
                p = g.p.updater_start(cmd)
                ready, _, _ = select.select([p.stdout], [], [], 120)   # a bound on a hang, not a time it asserts
                self.assertTrue(ready, '%s printed nothing while it waited (or before it hung)' % cmd)
                first = p.stdout.readline()
                self.assertIn('WAIT another run holds the updater lock %s' % LOCK, first)
                self.assertEqual(g.state()['on'], was, 'it changed the state before it held the lock')
                fcntl.flock(fd, fcntl.LOCK_UN)
                out, _ = p.communicate(timeout=120)
                self.assertEqual(p.returncode, 0, first + out)
                self.assertEqual(g.state()['on'], not was)

    def test_control_with_the_lock_free_on_says_no_wait(self):
        g = Rig(self, on=False, production=False)
        r = g.ok('on')
        self.assertNotIn('WAIT', r.stdout)


# ---- the pass

@needs_container
class Pass(unittest.TestCase):
    def test_a_held_lock_ends_a_pass_at_once(self):
        g = Rig(self, on=True, production=False)
        g.hold_lock()
        before = g.raw()
        r = g.run('pass', timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('runner-updater: pass: another run holds the updater lock %s; this pass ends' % LOCK, r.stdout)
        nothing_ran(self, g, r)
        self.assertEqual(g.raw(), before)

    def test_off_ends_a_pass_at_once_with_no_core_call(self):
        g = Rig(self, on=False, production=False)
        r = g.ok('pass')
        self.assertIn('runner-updater: pass: the updater is OFF: nothing to do', r.stdout)
        nothing_ran(self, g, r)
        self.assertNotIn('idle:', r.stdout)

    def test_an_open_window_journal_is_recover_needed_and_nothing_else(self):
        g = Rig(self, on=True, production=False)
        g.p.write(WINDOW, 'window 20261103080000-42\n', 0o600)
        before = g.raw()
        r = g.run('pass')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('runner-updater: STOP RECOVER needed (S2b-3c): the window journal %s is open' % WINDOW, r.stdout)
        nothing_ran(self, g, r)
        self.assertEqual(g.raw(), before)

    def test_untested_jq_stops_a_pass_that_is_on(self):
        g = Rig(self, on=True, production=False)
        g.p.jq_version('jq-9.9')
        before = g.raw()
        r = g.run('pass')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('runner-updater: STOP untested jq: jq here prints [jq-9.9]', r.stdout)
        nothing_ran(self, g, r)
        self.assertEqual(g.raw(), before)

    def test_control_untested_jq_and_off_ends_at_once(self):
        g = Rig(self, on=False, production=False)
        g.p.jq_version('jq-9.9')
        r = g.ok('pass')
        self.assertIn('the updater is OFF', r.stdout)

    def test_a_pass_writes_its_facts_and_the_core_state_back(self):
        g = Rig(self, on=True)
        r = g.ok('pass')
        for n in ('facts.json', 'log.txt', 'healthz.json', 'state.json', 'idle.json', 'r1.json', 'keep.json',
                  'status.json'):
            self.assertTrue(os.path.isfile(os.path.join(PASS, n)), n)
        self.assertEqual(g.state()['core'], g.out('state'))
        self.assertEqual(g.state()['core']['boundary']['position'], g.facts()['position'])
        for line in ('runner-updater: pass: one pass at ', 'idle: idle (', 'r1: ok (', 'keep: ok (', 'status: ok ('):
            self.assertIn(line, r.stdout)

    def test_the_core_state_is_written_only_when_all_four_decided(self):
        for prog in ('idle', 'r1', 'keep', 'status'):
            with self.subTest(prog):
                g = Rig(self, on=True)
                g.ok('pass')                            # a first pass: the state has a core
                g.append(scaling(int(time.time())))
                before = g.raw()
                g.plant('core/%s.jq' % prog, 'error("planted")\n')
                r = g.run('pass')
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('runner-updater: core could not decide (%s)' % prog, r.stdout)
                self.assertIn('runner-updater: the pass did nothing: %s is as it was' % STATE, r.stdout)
                self.assertEqual(g.raw(), before)
                self.assertNotIn('would', r.stdout)

    def test_a_pass_passes_the_restart_member_once_and_removes_it(self):
        rs = {'from': {'pid': 100, 'start': 1761955200}, 'to': {'pid': 101, 'start': 1761955300},
              'stopped': {'inode': '42', 'offset': 0, 'sha': H}}
        g = Rig(self, on=True)
        st = g.state()
        st['restart'] = rs
        g.put(st)
        g.ok('pass')
        self.assertEqual(g.facts()['restart'], rs)
        self.assertNotIn('restart', g.state())
        g.ok('pass')
        self.assertIsNone(g.facts()['restart'])

    def test_control_a_pass_whose_core_cannot_decide_keeps_the_restart_member(self):
        rs = {'from': {'pid': 100, 'start': 1761955200}, 'to': {'pid': 101, 'start': 1761955300},
              'stopped': {'inode': '42', 'offset': 0, 'sha': H}}
        g = Rig(self, on=True)
        st = g.state()
        st['restart'] = rs
        g.put(st)
        g.plant('core/keep.jq', 'error("planted")\n')
        self.assertEqual(g.run('pass').returncode, 1)
        self.assertEqual(g.state()['restart'], rs)

    def with_core(self, core):
        """ON, the decision core's own state CORE, and a restart member to hand over."""
        rs = {'from': {'pid': 100, 'start': 1761955200}, 'to': {'pid': 101, 'start': 1761955300},
              'stopped': {'inode': '42', 'offset': 0, 'sha': H}}
        g = Rig(self, on=True)
        st = g.state()
        st.update(core=core, restart=rs)
        g.put(st)
        return g, rs

    def test_a_core_that_waits_decides_nothing_and_the_state_stays_byte_for_byte(self):
        """Codex r1 F2: the core answers `wait` (its own state is of another format: core/README.md); that is no
        decision, so the pass WAITs and the restart member is not handed over."""
        g, rs = self.with_core({'format': 2})
        before = g.raw()
        r = g.run('pass')
        self.assertEqual(r.returncode, 4, r.stdout[-3000:] + r.stderr)
        self.assertIn('runner-updater: WAIT the decision core waits (idle: the state has format 2; this core reads '
                      'format 1: waiting): this pass decides nothing, and %s is as it was' % STATE, r.stdout)
        self.assertEqual(g.raw(), before)
        self.assertEqual(g.state()['restart'], rs)
        self.assertNotIn('would', r.stdout)

    def test_control_a_core_of_format_1_decides_and_hands_the_restart_over_once(self):
        g, rs = self.with_core({'format': 1})
        r = g.ok('pass')
        self.assertNotIn('WAIT', r.stdout)
        self.assertEqual(g.facts()['restart'], rs)
        self.assertNotIn('restart', g.state())
        self.assertEqual(g.state()['core'], g.out('state'))
        self.assertRegex(r.stdout, DUE)
        g.ok('pass')
        self.assertIsNone(g.facts()['restart'])

    def test_a_verdict_the_program_does_not_name_is_no_decision(self):
        """The class of Codex r1 F2: a decision is one of the verdicts core/README.md names for that program (idle:
        idle or not-idle; r1, keep and status: ok); anything else is "could not decide"."""
        for prog in ('idle', 'r1', 'keep', 'status'):
            with self.subTest(prog):
                g = Rig(self, on=True)
                before = g.raw()
                g.plant('core/%s.jq' % prog, '{verdict: "maybe", reason: "planted", lines: [], families: {}, '
                                             'state: {format: 1}}\n')
                r = g.run('pass')
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertIn('runner-updater: core could not decide (%s)' % prog, r.stdout)
                self.assertEqual(g.raw(), before)
                self.assertNotIn('would', r.stdout)

    def test_control_a_planted_program_that_answers_a_verdict_it_names_decides(self):
        g = Rig(self, on=True)
        g.plant('core/idle.jq', '{verdict: "not-idle", reason: "planted", lines: [], state: {format: 1}}\n')
        r = g.ok('pass')
        self.assertIn('idle: not-idle (planted)', r.stdout)
        self.assertRegex(r.stdout, DUE)

    def test_the_boundary_is_carried_to_the_next_pass(self):
        g = Rig(self, on=True)
        g.ok('pass')
        first = g.facts()
        self.assertFalse(first['continuous'])
        self.assertEqual(g.text(), b'')
        add = scaling(int(time.time())) + scaling(int(time.time()) + 1)
        g.append(add)
        g.ok('pass')
        f = g.facts()
        self.assertTrue(f['continuous'])
        self.assertEqual(g.text(), add.encode())
        self.assertEqual(f['position']['offset'], first['position']['offset'] + len(add.encode()))
        self.assertEqual(g.state()['core']['boundary']['position'], f['position'])


# ---- the facts

@needs_container
class Facts(unittest.TestCase):
    def test_the_facts_are_format_1_of_host_hz(self):
        g = Rig(self, on=True)
        g.ok('pass')
        unit = g.p.unit_now()
        st = os.stat(g.log)
        with open(g.log, 'rb') as f:
            data = f.read()
        p = {'pid': 100, 'start': unit['start']}
        self.assertEqual(g.facts(), {
            'format': 1, 'host': 'hz', 'sets': [MAIN, SMALL], 'proc': {'before': p, 'after': p},
            'position': {'inode': str(st.st_ino), 'offset': len(data), 'sha': hashlib.sha256(data[-64:]).hexdigest()},
            'continuous': False, 'restart': None,
            'config': {'installed': int(os.stat(g.p.rpath('config.toml')).st_mtime), 'lines': LINES},
            'families': {FAM: {'provider': 'docker', 'sets': [MAIN, SMALL], 'candidate': None, 'back_until': None}},
            'stops': []})

    def test_the_family_s_candidate_back_until_and_stops_are_the_state_s(self):
        c, s = candidate(1762156800), [stop('NO IDLE', V, text='3 days')]
        g = Rig(self, on=True, families={FAM: {'candidate': c, 'back_until': 1762761600, 'stops': s}})
        g.ok('pass')
        f = g.facts()
        self.assertEqual(f['families'][FAM], {'provider': 'docker', 'sets': [MAIN, SMALL], 'candidate': c,
                                              'back_until': 1762761600})
        self.assertEqual(f['stops'], s)

    def test_the_family_s_sets_are_the_host_config_s(self):
        g = Rig(self, on=True)
        conf = g.p.read(g.p.path('host.conf'))
        g.p.write(g.p.path('host.conf'), conf.replace('\nSMALL_SET=linux-ci-small\n', '\nSMALL_SET=linux-ci-lane\n'),
                  0o644)
        g.ok('pass')
        f = g.facts()
        self.assertEqual(f['families'][FAM]['sets'], [MAIN, 'linux-ci-lane'])
        self.assertEqual(f['sets'], [MAIN, SMALL], 'the config runscaler runs still names its own sets')

    def test_proc_before_then_the_position_then_proc_after(self):
        for at, moved in (('systemctl:show-1', True), ('systemctl:show-2', False)):
            with self.subTest(at):
                g = Rig(self, on=True)
                g.p.count_shows()
                g.p.hooks((at, 'restart'))              # an independent restart right after that read
                g.ok('pass')
                f, unit = g.facts(), g.p.unit_now()
                self.assertIn('hook %s: restart' % at, g.p.events())
                with open(g.log, 'rb') as fh:
                    data = fh.read()
                restart = data.rindex(b'\n', 0, data.index(b'runscaler stopped pid=100')) + 1   # its line's start
                if moved:   # after proc before: the restart's lines are before the position, proc after is the new one
                    self.assertEqual(f['proc']['before']['pid'], 100)
                    self.assertEqual(f['proc']['after'], {'pid': unit['pid'], 'start': unit['start']})
                    self.assertEqual(f['position']['offset'], len(data))
                else:       # after proc after: the position and both reads are the old process's
                    self.assertEqual(f['proc']['before'], f['proc']['after'])
                    self.assertEqual(f['proc']['after']['pid'], 100)
                    self.assertEqual(f['position']['offset'], restart)

    def test_a_systemd_answer_it_cannot_read_is_no_facts(self):
        cases = (('the read fails', 1, ''),
                 ('no ActiveState', 0, 'MainPID=100\nActiveEnterTimestamp=@1761955200\n'),
                 ('active with no MainPID', 0, 'ActiveState=active\nMainPID=0\nActiveEnterTimestamp=@1761955200\n'),
                 ('active with no start', 0, 'ActiveState=active\nMainPID=100\nActiveEnterTimestamp=\n'))
        for why, rc, out in cases:
            with self.subTest(why):
                g = Rig(self, on=True)
                g.p.show_answer(rc, out)
                before = g.raw()
                r = g.run('pass')
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('runner-updater: REFUSE no facts: systemd', r.stdout)
                self.assertFalse(os.path.exists(os.path.join(PASS, 'idle.json')))
                self.assertEqual(g.raw(), before)

    def test_control_an_inactive_unit_is_no_process(self):
        g = Rig(self, on=True)
        g.p.set_unit(active=False)
        g.ok('pass')
        self.assertEqual(g.facts()['proc'], {'before': None, 'after': None})

    def test_no_runscaler_log_is_no_facts(self):
        g = Rig(self, on=True)
        os.remove(g.log)
        r = g.run('pass')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('runner-updater: REFUSE no facts: cannot read runscaler\'s log %s' % g.log, r.stdout)
        self.assertFalse(os.path.exists(os.path.join(PASS, 'idle.json')))

    def test_the_healthz_pair_two_reads_3_s_apart(self):
        g = Rig(self, on=True)
        g.p.hooks()
        g.ok('pass')
        ev = g.p.events()
        reads = [i for i, e in enumerate(ev) if e == 'healthz read']
        self.assertEqual(len(reads), 2, ev)
        self.assertEqual([e for e in ev[reads[0] + 1:reads[1]] if e.startswith('sleep ')], ['sleep 3'])
        with open(os.path.join(PASS, 'healthz.json')) as f:
            self.assertEqual([json.loads(l) for l in f.read().splitlines()], [healthz(), healthz()])
        self.assertEqual(g.out('idle')['verdict'], 'idle')

    def test_control_no_answer_adds_no_read_and_idle_says_so(self):
        g = Rig(self, on=True)
        g.p.curl['healthz'] = None
        g.ok('pass')
        self.assertEqual(g.p.read(os.path.join(PASS, 'healthz.json')), '')
        self.assertEqual(g.out('idle')['verdict'], 'not-idle')


@needs_container
class Continuity(unittest.TestCase):
    """The log text of the second of two passes, against the boundary the first one left (Studio: TestContinuity)."""

    def two_passes(self, between):
        g = Rig(self, on=True)
        g.ok('pass')
        first = g.facts()['position']
        want = between(g)
        g.ok('pass')
        return g, first, want

    def check(self, between, continuous):
        g, first, want = self.two_passes(between)
        f = g.facts()
        self.assertIs(f['continuous'], continuous)
        self.assertEqual(g.text(), want)
        st = os.stat(g.log)
        self.assertEqual(f['position']['inode'], str(st.st_ino))
        self.assertEqual(f['position']['offset'], st.st_size)
        return g, first, f

    def test_a_quiet_log(self):
        self.check(lambda g: b'', True)

    def test_real_runscaler_lines(self):
        def between(g):
            g.append(REAL)
            return REAL.encode()
        self.check(between, True)

    def test_one_rotation(self):
        def between(g):
            g.append(REAL[:120])
            os.rename(g.log, g.log + '.1')
            g.p.write(g.log, REAL[120:], 0o600)
            return REAL.encode()
        g, first, f = self.check(between, True)
        self.assertNotEqual(f['position']['inode'], first['inode'])

    def test_a_rotation_right_at_the_boundary(self):
        def between(g):
            os.rename(g.log, g.log + '.1')
            g.p.write(g.log, REAL, 0o600)
            return REAL.encode()
        self.check(between, True)

    @staticmethod
    def rotate_twice(g, second):
        """runner.log -> runner.log.1, a new runner.log of SECOND's bytes, -> runner.log.1 again, a new runner.log of
        REAL. Each new file is made while the boundary's file still exists: a file made after it is gone may get its
        inode number back (overlayfs does), and would read as that file cut or rewritten, not as one gone."""
        os.rename(g.log, g.log + '.1')
        g.p.write(g.log, second(g), 0o600)
        g.p.write(g.log + '.new', REAL, 0o600)
        os.rename(g.log, g.log + '.1')                # the boundary's file is gone only now
        os.rename(g.log + '.new', g.log)
        return REAL.encode()                          # only what can be read: runner.log to the position

    def test_two_rotations_are_not_continuous(self):
        self.check(lambda g: self.rotate_twice(g, lambda g: 'two\n'), False)

    def test_two_rotations_through_a_file_with_the_same_bytes_are_not_continuous(self):
        """The boundary's sha matches a copy that holds the same bytes: only the inode tells the files apart."""
        def same(g):
            with open(g.log + '.1') as f:
                return f.read()
        self.check(lambda g: self.rotate_twice(g, same), False)

    def test_a_cut_file_is_not_continuous(self):
        def between(g):
            with open(g.log, 'rb') as f:
                data = f.read()
            with open(g.log, 'r+b') as f:            # the same file (inode), cut below the boundary
                f.truncate(len(data) - 5)
            return data[:-5]
        self.check(between, False)

    def test_a_file_rewritten_before_the_boundary_is_not_continuous(self):
        def between(g):
            with open(g.log, 'rb') as f:
                data = f.read()
            with open(g.log, 'r+b') as f:            # the same file and size, one byte before the boundary changed
                f.seek(len(data) - 2)
                f.write(b'X')
            g.append(REAL)
            return data[:-2] + b'X' + data[-1:] + REAL.encode()
        self.check(between, False)

    def test_a_removed_backup_is_not_continuous(self):
        def between(g):
            os.rename(g.log, g.log + '.1')
            g.p.write(g.log, REAL, 0o600)
            os.remove(g.log + '.1')
            return REAL.encode()
        self.check(between, False)


@needs_container
class InstallTime(unittest.TestCase):
    def journal(self, g, wid, staged, renamed):
        """A closed window journal windows/WID of pool-image.sh's form: its TARGET sha, and `rename-start` one second
        before `renamed` unless renamed is None."""
        lines = ['window ' + wid, 'kind switch', 'staged-sha ' + staged]
        if renamed is not None:
            lines += ['rename-start %d' % (renamed - 1), 'renamed %d' % renamed]
        os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
        g.p.write(os.path.join(WINDOWS, wid), '\n'.join(lines + ['closed %d' % ((renamed or 0) + 9)]) + '\n', 0o600)

    def touched(self, g, t):
        """config.toml's mtime set to t (the second a window's touch, or a later write, leaves it at)."""
        os.utime(g.p.rpath('config.toml'), (t, t))

    def test_installed_is_the_renamed_epoch_of_the_window_that_installed_config_toml(self):
        g = Rig(self, on=True)
        up = g.p.unattended('up', '--unattended', V, NEW)
        self.assertEqual(up.returncode, 0, up.stdout[-3000:] + up.stderr)
        (wid, lines), = g.p.closed()
        renamed = int([l for l in lines if l.startswith('renamed ')][0].split()[1])
        mtime = int(os.stat(g.p.rpath('config.toml')).st_mtime)
        self.assertNotEqual(renamed, mtime, 'the fake clock gives the journal its own time: the cell tells them apart')
        g.ok('pass')
        self.assertEqual(g.facts()['config']['installed'], renamed)
        self.assertEqual(g.facts()['config']['lines'], {MAIN: ref(NEW), SMALL: ref(NEW)})
        # the control: a hand change of config.toml after that window is no file it installed: its mtime
        g.append('# a hand change\n', g.p.rpath('config.toml'))
        g.ok('pass')
        self.assertEqual(g.facts()['config']['installed'], int(os.stat(g.p.rpath('config.toml')).st_mtime))

    def test_the_newest_journal_that_renamed_config_toml_s_sha_wins(self):
        """config.toml's mtime is the newest window's touch (its `rename-start` second, a second before `renamed`), as
        that window's own install leaves it."""
        g = Rig(self, on=True)
        s = sha256_file(g.p.rpath('config.toml'))
        t = int(os.stat(g.p.rpath('config.toml')).st_mtime)
        self.journal(g, '20261101000000-7', s, t - 90)              # an older install of the same file
        self.journal(g, '20261101000001-8', s, t - 50)              # the newest (its name sorts neither first nor last)
        self.journal(g, '20261101000002-9', s, t - 70)              # another older one
        self.journal(g, '20261101000003-5', 'cd' * 32, t - 10)      # another file's, newer still
        self.journal(g, '20261101000004-6', s, None)                # a window that stopped before its rename
        os.makedirs(os.path.join(WINDOWS, '20261101000005-4.d'))
        self.touched(g, t - 51)
        g.ok('pass')
        self.assertEqual(g.facts()['config']['installed'], t - 50)

    def test_a_later_install_of_the_same_bytes_is_its_mtime(self):
        """Opus r1 F1 / Codex r1 F1, planted: a window renamed these bytes into place 100 s before runscaler started,
        and config.toml's own mtime is 100 s after it (the same bytes written again: `03-runscaler.sh real DIGEST`
        restarts nothing). The install time is that mtime, never earlier than the file itself."""
        g = Rig(self, on=True)
        start = g.p.unit_now()['start']
        self.journal(g, '20261101000000-7', sha256_file(g.p.rpath('config.toml')), start - 100)
        self.touched(g, start + 100)
        g.p.clock(now=start + 200)
        r = g.ok('pass')
        self.assertEqual(g.facts()['config']['installed'], start + 100)
        self.assertIn('runner-updater: config: installed at %d (its mtime: it was written again after the window '
                      'journal that renamed these bytes into place at %d)' % (start + 100, start - 100), r.stdout)

    def test_control_the_window_s_own_touch_keeps_its_renamed(self):
        """The same journal, config.toml's mtime the window's `rename-start` second (its touch): the install time is
        `renamed`, not that earlier mtime."""
        g = Rig(self, on=True)
        start = g.p.unit_now()['start']
        self.journal(g, '20261101000000-7', sha256_file(g.p.rpath('config.toml')), start - 100)
        self.touched(g, start - 101)
        g.p.clock(now=start + 200)
        r = g.ok('pass')
        self.assertEqual(g.facts()['config']['installed'], start - 100)
        self.assertIn('runner-updater: config: installed at %d (the window journal that renamed it into place)'
                      % (start - 100), r.stdout)

    def documented(self, restart):
        """Opus r1 F1 / Codex r1 F1 on the documented path, with the real scripts and the REAL clock: the updater's
        switch to NEW (W1, `up --unattended`); a person's `back --unattended` (W2: config.toml back on OLD, process P);
        in a later second a person's `03-runscaler.sh real NEW`, which writes W1's TARGET bytes again and restarts
        nothing, so P still runs OLD; restart=True: then, in a later second, a person's restart (process Q runs NEW).
        Then a pass whose state holds NEW as hz-docker's candidate, three start failures, and the next pass. Returns
        the rig, whether r1's evidence window was open after the first pass, and the second pass."""
        new = {MAIN: ref(NEW), SMALL: ref(NEW)}
        g = Rig(self, on=True, clock=False)
        up = g.p.unattended('up', '--unattended', V, NEW)
        self.assertEqual(up.returncode, 0, up.stdout[-3000:] + up.stderr)
        (w1, l1), = g.p.closed()
        target = [l.split()[1] for l in l1 if l.startswith('staged-sha ')][-1]
        renamed1 = int([l.split()[1] for l in l1 if l.startswith('renamed ')][-1])
        back = g.p.unattended('back', '--unattended')
        self.assertEqual(back.returncode, 0, back.stdout[-3000:] + back.stderr)
        self.assertEqual(g.p.images(), [ref(OLD)] * 2)
        p = g.p.unit_now()
        wait_past(p['start'])
        r = g.p.s03('real', NEW)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        cfg = g.p.rpath('config.toml')
        self.assertEqual(sha256_file(cfg), target, "03 wrote W1's TARGET bytes again (the shape is reached)")
        mtime = int(os.stat(cfg).st_mtime)
        self.assertGreater(mtime, p['start'])
        self.assertEqual(g.p.unit_now()['start'], p['start'], '03 restarted nothing: P still runs OLD')
        if restart:
            wait_past(mtime)
            r = g.p.run(['systemctl', '--user', 'restart', 'runscaler'])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            p = g.p.unit_now()
            self.assertGreater(p['start'], mtime)
        st = g.state()
        st['families'] = {FAM: {'candidate': candidate(renamed1 + 30, lines=new)}}
        g.put(st)
        g.ok('pass')
        f = g.facts()
        self.assertEqual(f['config']['lines'], new)
        self.assertEqual(f['proc']['before'], {'pid': p['pid'], 'start': p['start']})
        self.assertEqual(f['config']['installed'], mtime, "the install time is 03's write, not W1's rename")
        opened = g.out('r1')['families'][FAM]['open']
        t = int(time.time()) + 100
        g.append(failed(t) + failed(t + 10) + failed(t + 20) + scaling(t + 160) + scaling(t + 161))
        return g, opened, g.ok('pass')

    def test_a_reinstall_of_the_candidate_s_bytes_opens_no_window_on_the_process_that_runs_the_old_image(self):
        g, opened, r = self.documented(restart=False)
        self.assertFalse(opened, 'the evidence window of candidate NEW opened on a process that runs OLD')
        self.assertNotEqual(g.out('r1')['families'][FAM]['verdict'], 'rollback')
        self.assertNotIn('would roll back', r.stdout)

    def test_control_a_restart_after_that_reinstall_runs_the_candidate_and_its_failures_count(self):
        g, opened, r = self.documented(restart=True)
        self.assertTrue(opened, g.out('r1'))
        self.assertIn('runner-updater: pass: would roll back hz-docker (this release takes no action)', r.stdout)

    def test_control_a_journal_with_no_renamed_line_is_no_install(self):
        g = Rig(self, on=True)
        s = sha256_file(g.p.rpath('config.toml'))
        self.journal(g, '20261101000003-6', s, None)
        g.ok('pass')
        self.assertEqual(g.facts()['config']['installed'], int(os.stat(g.p.rpath('config.toml')).st_mtime))


@needs_container
class ConfigRead(unittest.TestCase):
    """config_read (setup/runner-facts.sh): the Studio's "no facts" rules for config.toml that apply on this host
    (bin/runner-updater-lib, ru_config): every one would leave R1 or provenance reading the wrong lines."""

    def read(self, g, text):
        p = g.p.write(g.p.path('tmp', 'config.toml'), text, 0o600)
        return g.p.lib('config_read "$1"', p, source='runner-facts.sh')

    def test_the_rules(self):
        g = Rig(self, on=None, clock=False)
        real = g.p.config()
        main, rest = real.split('\n[[scaleset]]\n', 2)[1:]
        self.assertIn('[scaleset.docker]', rest)
        self.assertEqual(real.count('\nlog-level = "info"\n'), 1)

        def level(v):
            return real.replace('\nlog-level = "info"\n', '\nlog-level = "%s"\n' % v)
        cases = (
            ('two names in a block', real.replace('name = "linux-ci-main"\n', 'name = "linux-ci-main"\nname = "x"\n'),
             'line [0-9]+: a \\[\\[scaleset\\]\\] block has two names'),
            ('two images in a block', real.replace('runner-image = "%s"\n' % ref(OLD), 'runner-image = "%s"\n'
                                                   'runner-image = "%s"\n' % (ref(OLD), ref(NEW)), 1),
             'a \\[\\[scaleset\\]\\] block has two runner-image lines'),
            ('an image line at the top', 'runner-image = "%s"\n' % ref(OLD) + real,
             'line 1: a runner-image line outside a \\[\\[scaleset\\]\\] block'),
            ('an image line in another table', real + 'runner-image = "%s"\n' % ref(NEW),
             'a runner-image line outside a \\[\\[scaleset\\]\\] block'),
            ('a block with no name', real.replace('name = "linux-ci-small"\n', ''),
             'a \\[\\[scaleset\\]\\] block has no name'),
            ('two blocks with one name', real.replace('name = "linux-ci-small"\n', 'name = "linux-ci-main"\n'),
             "two \\[\\[scaleset\\]\\] blocks are named 'linux-ci-main'"),
            ('an image line it cannot read', real.replace('runner-image = "%s"\n' % ref(OLD), "runner-image = '%s'\n"
                                                          % ref(OLD), 1), 'a runner-image line this does not read'),
            ('a name it cannot read', real.replace('name = "linux-ci-main"\n', 'name = "linux ci"\n'),
             'a scale set name this does not read'),
            ('a top-level log-file', 'log-file = "/tmp/x.log"\n' + real, 'a top-level log-file key'),
            ('a log-format other than text', 'log-format = "json"\n' + real, 'log-format is not "text"'),
            # Opus r1 F2: runscaler then writes no INFO record (no job-completed: the proof of life R1 and KEEP read)
            ('log-level warn', level('warn'), 'line [0-9]+: log-level is not "info" or "debug"'),
            ('log-level error', level('error'), 'line [0-9]+: log-level is not "info" or "debug"'),
        )
        for why, text, says in cases:
            with self.subTest(why):
                r = self.read(g, text)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertRegex(r.stdout, says)
        # the controls: 03's own render; log-format text and a log-file key inside a table; a comment
        for why, text, sets, lines in (
                ("03's render", real, [MAIN, SMALL], LINES),
                ('log-format "text" and a log-file in a table', 'log-format = "text"\n' + real.replace(
                    '[docker]\n', '[docker]\nlog-file = "x"\n'), [MAIN, SMALL], LINES),
                ('a comment that names an image', real.replace('runner-image = "%s"\n' % ref(OLD), '# runner-image = '
                                                               '"%s"\n' % ref(NEW), 1), [MAIN, SMALL], {SMALL: ref(OLD)}),
                ('log-level debug', level('debug'), [MAIN, SMALL], LINES),
                ('no log-level line', real.replace('\nlog-level = "info"\n', '\n'), [MAIN, SMALL], LINES),
                ('a log-level line in a table', real.replace('[docker]\n', '[docker]\nlog-level = "error"\n'),
                 [MAIN, SMALL], LINES)):
            with self.subTest(why):
                r = self.read(g, text)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                head, js = r.stdout.splitlines()
                p = g.p.path('tmp', 'config.toml')
                self.assertEqual(head, '%d %s' % (int(os.stat(p).st_mtime), sha256_file(p)))
                self.assertEqual(json.loads(js), {'sets': sets, 'lines': lines})

    def test_a_config_it_cannot_read_is_no_facts_in_a_pass(self):
        g = Rig(self, on=True)
        g.p.write(g.p.rpath('config.toml'), 'log-format = "json"\n' + g.p.config(), 0o600)
        before = g.raw()
        r = g.run('pass')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('runner-updater: REFUSE no facts: %s line 1: log-format is not "text"' % g.p.rpath('config.toml'),
                      r.stdout)
        self.assertFalse(os.path.exists(os.path.join(PASS, 'idle.json')))
        self.assertEqual(g.raw(), before)

    def test_a_log_level_that_drops_info_records_is_no_facts_in_a_pass(self):
        """Opus r1 F2: runner-start runs runscaler with log-level "warn" (03 renders "info"), and then runner.log has
        no `Runner removed reason=job-completed`: R1 and KEEP would read a quiet log as a normal one."""
        g = Rig(self, on=True)
        cfg = g.p.rpath('config.toml')
        text = g.p.config()
        n = text.split('\n').index('log-level = "info"') + 1
        g.p.write(cfg, text.replace('\nlog-level = "info"\n', '\nlog-level = "warn"\n'), 0o600)
        before = g.raw()
        r = g.run('pass')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('runner-updater: REFUSE no facts: %s line %d: log-level is not "info" or "debug"' % (cfg, n),
                      r.stdout)
        self.assertFalse(os.path.exists(os.path.join(PASS, 'idle.json')))
        self.assertEqual(g.raw(), before)


# ---- what a pass would do

@needs_container
class Would(unittest.TestCase):
    def armed(self, **fam):
        """ON, hz-docker's candidate = the lines production runs (so the running process runs it), and a first pass:
        the evidence window opens at its boundary. Returns the rig and the log time to write from."""
        g = Rig(self, on=True)
        g.put({'format': 1, 'on': True, 'families': {FAM: dict({'candidate': candidate(g.p.clock() - 60)}, **fam)}})
        g.ok('pass')
        self.assertTrue(g.out('r1')['families'][FAM]['open'], g.out('r1'))
        return g, int(time.time()) + 100

    def test_three_counted_failures_on_a_set_would_roll_back(self):
        g, t = self.armed()
        g.append(failed(t) + failed(t + 10) + failed(t + 20) + scaling(t + 160) + scaling(t + 161))
        r = g.ok('pass')
        self.assertEqual(g.out('r1')['families'][FAM]['verdict'], 'rollback')
        self.assertIn('runner-updater: pass: would roll back hz-docker (this release takes no action)', r.stdout)

    def test_control_a_proof_of_life_between_them_is_no_rollback(self):
        g, t = self.armed()
        g.append(failed(t) + failed(t + 10) + completed(t + 15, 'succeeded') + failed(t + 20) + scaling(t + 160)
                 + scaling(t + 161))
        r = g.ok('pass')
        self.assertEqual(g.out('r1')['families'][FAM]['verdict'], 'none')
        self.assertNotIn('would roll back', r.stdout)

    def keep(self, records, after):
        g, t = self.armed()
        since = g.out('r1')['families'][FAM]['since']
        g.append(records(t))
        g.p.clock(now=since + after)
        r = g.ok('pass')
        return g, r

    def test_72_h_after_the_window_opened_with_a_success_it_would_accept(self):
        g, r = self.keep(lambda t: completed(t, 'succeeded') + scaling(t + 1), 72 * 3600)
        self.assertEqual(g.out('keep')['families'][FAM]['verdict'], 'accept')
        self.assertIn('runner-updater: pass: would accept hz-docker (this release takes no action)', r.stdout)

    def test_control_a_second_before_72_h_it_observes(self):
        g, r = self.keep(lambda t: completed(t, 'succeeded') + scaling(t + 1), 72 * 3600 - 1)
        self.assertEqual(g.out('keep')['families'][FAM]['verdict'], 'observe')
        self.assertNotIn('would accept', r.stdout)

    def test_72_h_with_completions_none_succeeded_would_hold_jobs_fail(self):
        g, r = self.keep(lambda t: completed(t, 'failed') + scaling(t + 1), 72 * 3600)
        self.assertIn('runner-updater: pass: would hold hz-docker: STOP JOBS FAIL ON THE NEW IMAGE (this release takes '
                      'no action)', r.stdout)

    def test_72_h_with_no_completion_would_hold_no_evidence(self):
        g, r = self.keep(lambda t: scaling(t), 72 * 3600)
        self.assertIn('runner-updater: pass: would hold hz-docker: STOP NO EVIDENCE (this release takes no action)',
                      r.stdout)

    def test_the_switch_line_is_due_s_one_line(self):
        """S2b-3b-2: S2b-3a's switch line ("would switch hz-docker: the pool is idle ...", which read no release) is
        gone; DUE prints ONE line for hz-docker (test_release_due.py: its 12 steps; an open candidate is step 1, a
        STOP that holds it step 2, and the idle pair is the switch window's own: pool-image.sh up --unattended).
        Control: a busy pool changes the idle line, not DUE's."""
        for why, hz in (('idle', None), ('a busy set', healthz(**{MAIN: {'busy': 1}}))):
            with self.subTest(why):
                g = Rig(self, on=True)
                if hz is not None:
                    g.p.curl['healthz'] = hz
                r = g.ok('pass')
                switch = [l for l in r.stdout.splitlines() if l.startswith('runner-updater: pass: ')
                          and ('switch' in l or ' is not due: ' in l)]
                self.assertEqual(len(switch), 1, r.stdout[-3000:])
                self.assertRegex(switch[0], DUE)
                self.assertIn('idle: %s (' % ('idle' if hz is None else 'not-idle'), r.stdout)


# ---- it acts on nothing

@needs_container
class NoAction(unittest.TestCase):
    def mark(self, g):
        """What the home holds (Pool.snapshot, less what a pass may write: STATEDIR's state.json, lock and pass/), and
        how many systemctl, docker and runscaler validate calls the substitutes have seen."""
        sd = os.path.join(g.p.home, '.local', 'state', 'runner-updater')
        home = {k: v for k, v in g.p.snapshot().items()
                if k not in (os.path.join(sd, 'state.json'), os.path.join(sd, 'lock'))
                and not k.startswith(os.path.join(sd, 'pass') + '/')}
        return (home, len(g.p.lines('systemctl')), len(g.p.calls('docker')),
                len([c for c in g.p.calls('runner') if c['argv'][:1] == ['validate']]))

    def acted_on_nothing(self, g, mark):
        """Since MARK: no systemctl call but `show` (no start, stop or restart), no docker call (no 02-d1.sh), no
        runscaler validate (no 03, no pool-image.sh window), and no file of the home changed (config.toml, its
        rollback, pool-image.sh's journals and lock, runscaler's log)."""
        home, n_sys, n_docker, n_val = mark
        now = self.mark(g)
        calls = g.p.lines('systemctl')[n_sys:]
        self.assertTrue(calls, 'the pass read runscaler')
        self.assertEqual([c for c in calls if c.split(' ')[1:2] != ['show']], [])
        self.assertEqual(now[2:], (n_docker, n_val))
        self.assertEqual(now[0], home)

    def rig(self):
        g = Rig(self, on=True)
        up = g.p.unattended('up', '--unattended', V, NEW)     # pool-image.sh's files: config.toml.prev, windows/
        self.assertEqual(up.returncode, 0, up.stdout[-3000:] + up.stderr)
        self.assertTrue(os.path.isfile(g.p.rpath('config.toml.prev')))
        st = g.state()
        st['families'] = {FAM: {'candidate': candidate(g.p.clock() - 60, lines={MAIN: ref(NEW), SMALL: ref(NEW)})}}
        g.put(st)
        return g

    def test_a_pass_that_would_roll_back_acts_on_nothing(self):
        g = self.rig()
        m = self.mark(g)
        self.assertIn('runner-updater: pass: hz-docker is not due: an open candidate', g.ok('pass').stdout)
        self.acted_on_nothing(g, m)
        t = int(time.time()) + 100
        g.append(failed(t) + failed(t + 10) + failed(t + 20) + scaling(t + 160) + scaling(t + 161))
        m = self.mark(g)
        self.assertIn('would roll back hz-docker', g.ok('pass').stdout)
        self.acted_on_nothing(g, m)

    def test_control_a_planted_restart_is_seen(self):
        g = self.rig()
        text = g.program()
        self.assertEqual(text.count('\n  would_do\n'), 1)
        g.plant('bin/runner-updater', text.replace('\n  would_do\n', '\n  would_do\n  systemctl --user restart '
                                                                     'runscaler\n'))
        m = self.mark(g)
        g.ok('pass')
        with self.assertRaises(AssertionError):
            self.acted_on_nothing(g, m)


# ---- its own PATH, its install line, its usage

@needs_container
class OwnPath(unittest.TestCase):
    def nopath(self, g):
        return dict(g.p.env(), PATH='/nonexistent')

    def test_status_and_pass_run_with_a_caller_path_that_holds_nothing(self):
        g = Rig(self, on=True)
        for cmd in ('status', 'pass'):
            with self.subTest(cmd):
                r = g.run(cmd, env=self.nopath(g))
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertTrue(g.facts()['proc']['before'])

    def test_control_a_copy_that_sets_no_path_or_finds_bash_on_it_fails(self):
        for why, old, new in (('no PATH line', '\nPATH=', '\nNOPATH='),
                              ('#!/usr/bin/env bash', '#!/bin/bash\n', '#!/usr/bin/env bash\n')):
            with self.subTest(why):
                g = Rig(self, on=True)
                text = g.program()
                self.assertEqual(text.count(old), 1)
                g.plant('bin/runner-updater', text.replace(old, new))
                r = g.run('status', env=self.nopath(g))
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)


@needs_container
class Install(unittest.TestCase):
    def test_the_readme_s_line_links_bin_runner_updater_into_build(self):
        g = Rig(self, on=None, clock=False, production=False)
        with open(README) as f:
            lines = [l.strip() for l in f.read().splitlines() if 'runner-updater ~/bin/runner-updater' in l]
        self.assertEqual(len(lines), 1, lines)
        here = re.sub(r"^ssh <RS_USER>@<host> '", "bash -c '", lines[0])
        self.assertNotRegex(here, r'<[A-Za-z_ ]+>')
        r = subprocess.run(['bash', '-c', here], env=g.p.env(), cwd=Pool.HOME, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        link = os.path.join(Pool.HOME, 'bin', 'runner-updater')
        self.assertEqual(os.readlink(link), os.path.join(Pool.HOME, 'build', 'bin', 'runner-updater'))
        r = g.p.updater('status', argv0=link)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('the updater is OFF', r.stdout)

    def test_the_watchdog_s_ask_finds_runner_updater_by_its_bare_name(self):
        """Codex r1 F3: the watchdog's asks say `LINE runner-updater status` (watchdog/run, --hz), the bare name, run
        by RS_USER's shell over ssh with a PATH of the system folders. The README's --hz line puts ~/bin first; the
        cell runs what it sends after step 10's link (`ssh <RS_USER>@<host>` is the shell's own `bash -c`). Control:
        the same PATH without ~/bin finds no runner-updater (127)."""
        g = Rig(self, on=None, clock=False, production=False)
        with open(README) as f:
            text = f.read()
        link = [l.strip() for l in text.splitlines() if 'runner-updater ~/bin/runner-updater' in l][0]
        r = subprocess.run(['bash', '-c', re.sub(r"^ssh <RS_USER>@<host> '", "bash -c '", link)], env=g.p.env(),
                           cwd=Pool.HOME, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        hz = re.findall(r"^\s*--hz 'ssh <RS_USER>@<host> (PATH=\S+)'$", text, re.M)
        self.assertEqual(len(hz), 1, 'the README names one --hz line of that shape')
        path = hz[0].replace('<RS_USER>', 'root')                     # Pool's RS_USER: its home is /home/root
        bare = 'PATH=' + ':'.join(d for d in path[len('PATH='):].split(':') if d != Pool.HOME + '/bin')
        system = dict(g.p.env(), PATH='/usr/bin:/bin:/usr/sbin:/sbin')
        for why, line, rc in (("the README's --hz line", path, 0), ('the same without ~/bin', bare, 127)):
            with self.subTest(why):
                r = subprocess.run(['bash', '-c', line + ' runner-updater status'], env=system, cwd=Pool.HOME,
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                if rc == 0:
                    self.assertIn('runner-updater: status: the updater is OFF', r.stdout)
                else:
                    self.assertIn('runner-updater: command not found', r.stderr)


@needs_container
class Usage(unittest.TestCase):
    def test_another_user_than_rs_user_or_run_user_is_refused(self):
        """The user decides the role (S2b-3b-2): RS_USER's or RUN_USER's (test_updater_build.py, Role); any other user
        is refused, and nothing is written."""
        g = Rig(self, on=None, clock=False, production=False)
        conf = g.p.read(g.p.path('host.conf'))
        g.p.write(g.p.path('host.conf'), conf.replace('\nRS_USER=root\n', '\nRS_USER=ci-rs\n')
                  .replace('\nRUN_USER=root\n', '\nRUN_USER=ci-run\n'), 0o644)
        for cmd in ('status', 'on', 'pass'):
            r = g.run(cmd)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn('runner-updater: REFUSE run me as ci-rs or ci-run', r.stdout)
        self.assertFalse(os.path.lexists(STATEDIR))

    def test_usage(self):
        g = Rig(self, on=None, clock=False, production=False)
        for args in ((), ('report',), ('status', 'x'), ('pass', '--now')):
            with self.subTest(args):
                r = g.run(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn('usage: runner-updater status | on | off | pass | build VERSION', r.stderr)


# ---- the text (runs anywhere)

def defs(path, name):
    with open(path) as f:
        return len(re.findall(r'^%s\(\) \{' % re.escape(name), f.read(), re.M))


class Text(unittest.TestCase):
    def test_one_copy_of_each_measuring_helper(self):
        """The brief: ONE copy of each measuring helper, shared with pool-image.sh by a sourced file."""
        for name in ('proc_now', 'log_pos', 'tested_jq', 'healthz_pair'):
            with self.subTest(name):
                self.assertEqual((defs(LIB, name), defs(PIMG, name), defs(UPD, name)), (1, 0, 0))
        with open(PIMG) as f:
            p = f.read()
        self.assertIn('. "$B/setup/runner-facts.sh"', p)
        uidle = p.split('\nuidle() {', 1)[1].split('\n}\n', 1)[0]
        self.assertNotIn('curl', uidle, "the idle pair's reads are healthz_pair's")
        self.assertIn('healthz_pair', uidle)
        with open(UPD) as f:
            self.assertIn('. "$B/setup/runner-facts.sh"', f.read())

    def test_the_header_names_the_state_the_commands_the_exit_codes_and_what_differs(self):
        with open(UPD) as f:
            h = f.read().split('\nset -uo pipefail\n', 1)[0]
        for s in ('state.json', 'format', 'hz-docker', 'status', ' on ', ' off ', ' pass ', 'WAIT', 'REFUSE',
                  'DIFFERS', 'STATEDIR', 'PASSDIR', 'proc before', 'proc after', '`renamed`'):
            self.assertIn(s, h)
        for code in ('0', '1', '2', '3', '4'):
            self.assertRegex(h, r'#\s+%s\s' % code, 'the header names no exit code %s' % code)

    def test_the_differs_list_names_the_core_wait_and_the_verdicts_it_takes(self):
        """Opus r2 F3 (S2b-3a): the header's "DIFFERS from the Studio's pass" (complete, as the header's first lines
        promise) names that a core `wait` is a WAIT here, in a pass and in status, and that only the verdicts
        core/README.md names for each program are taken (the Studio's takes any). Control: the paragraph is found,
        and it still names what it named."""
        with open(UPD) as f:
            h = f.read().split('\nset -uo pipefail\n', 1)[0]
        d = ' '.join(l.lstrip('#').strip() for l in h.split("# DIFFERS from the Studio's pass", 1)[1]
                     .split('\n# Exit codes:', 1)[0].splitlines())
        self.assertIn('no protected list to rewrite', d)
        self.assertIn('a decision core that answers `wait` is a WAIT (exit 4), in a pass and in status', d)
        self.assertIn('takes only the verdicts core/README.md names for each program (idle: idle or not-idle; r1, '
                      'keep and status: ok; or wait)', d)

    def test_the_header_and_the_readme_say_status_waits_when_the_core_waits(self):
        """Opus r2 F1 (S2b-3a): the header's `status` and the README's updater section say that status WAITs (exit 4)
        after its lines when the decision core waits, and STOPs on an answer the core does not give. Control: they
        still say it for a pass."""
        with open(UPD) as f:
            h = ' '.join(l.lstrip('#').strip() for l in f.read().split('\nset -uo pipefail\n', 1)[0].splitlines())
        st = h.split('status   no lock,', 1)[1].split(' on       on = true.', 1)[0]
        self.assertIn('status.jq\'s answer is checked as a pass checks it (`decided`): a `wait` is its lines, then '
                      '"runner-updater: WAIT the decision core waits ...", exit 4; another answer is "runner-updater: '
                      'STOP core could not decide (status)", exit 1', st)
        self.assertIn('a pass, or status, whose decision core waits', h.split('Exit codes:', 1)[1])
        with open(README) as f:
            sec = f.read().split('\n## The updater: status, on, off, pass, build\n', 1)[1].split('\n## ', 1)[0]
        self.assertIn('A pass or `status` whose decision core waits (the core\'s own state, kept in the state file, is '
                      'of a format it does not read) prints `WAIT` (exit 4) too, `status` after its lines, and changes '
                      'nothing. An answer of the core that is not one of its own is `STOP core could not decide` (exit '
                      '1).', sec)

    def test_one_copy_of_the_verdicts_the_updater_takes(self):
        """Opus r2 F1 (S2b-3a): a pass and status take ONE set of verdicts per program, decided()'s."""
        with open(UPD) as f:
            text = f.read()
        self.assertEqual(defs(UPD, 'decided'), 1)
        self.assertEqual(len(re.findall(r'"idle not-idle wait"', text)), 1)
        self.assertEqual(len(re.findall(r'"ok wait"', text)), 1)
        status = text.split('\ndo_status() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('decided status', status)
        self.assertNotIn('.verdict | type', status, 'status has a verdict check of its own')

    def test_the_readme_names_the_files_the_install_line_and_the_commands(self):
        with open(README) as f:
            text = f.read()
        for row in ('| `bin/runner-updater` | RS_USER, RUN_USER |', '| `setup/runner-facts.sh` | RS_USER, RUN_USER |',
                    '| `setup/03-runscaler.sh` | RS_USER |'):            # 03: the control, RS_USER's alone
            self.assertIn(row, text)
        self.assertNotIn('| `setup/runner-facts.sh` | RS_USER |', text)   # Opus r1 F6: both users' updater reads it
        sec = text.split('\n## The updater: status, on, off, pass, build\n', 1)[1].split('\n## ', 1)[0]
        for s in ('runner-updater status', 'runner-updater on', 'runner-updater off', 'runner-updater pass',
                  'STOP RECOVER needed', '~/.local/state/runner-updater/state.json'):
            self.assertIn(s, sec)

    def test_every_path_to_this_release_sends_a_host_to_install_step_10(self):
        """Opus r1 F3: a host that gets this release by the upgrade notes, or moves from a hand copy, gets the updater's
        link too (Install step 10), so `runner-updater status` exists there. Control: step 10 is the Install
        section's, and the README holds its link line once (Install runs that line)."""
        with open(README) as f:
            text = f.read()

        def section(title):
            return text.split('\n## %s\n' % title, 1)[1].split('\n## ', 1)[0]
        release = section('A new runner release')
        for why, part in (('A new runner release, its first paragraph', release.strip().split('\n\n', 1)[0]),
                          ('the upgrade notes', section('Upgrading from a release before this one')),
                          ('a hand copy', section('A host that already runs these scripts from a hand copy'))):
            with self.subTest(why):
                self.assertIn('Install step 10', part)
        links = [l for l in text.splitlines() if 'runner-updater ~/bin/runner-updater' in l]
        self.assertEqual(len(links), 1, links)
        self.assertIn(links[0], section('Install').split('\n10. **The updater (RS_USER and RUN_USER).**', 1)[1])


if __name__ == '__main__':
    unittest.main()
