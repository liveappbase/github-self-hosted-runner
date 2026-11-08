"""THE CHECK THE NEXT DAY, `pool-image.sh runscaler-check` (runscaler 0.12 bump, Hetzner slice H2b-2; the H2 plan's M-5
with its r3 FOLD R-7, ACCEPTANCE (c)): the README line a person runs as RS_USER the day after `pool-image.sh runscaler`
(the section "runscaler: the release this one pins, and the way back", step 3), extracted and run as written (`bash -s
-- ARGS`, pool-image.sh on its stdin) on fixture homes, one per answer. It only READS: every file and folder of the home
(sha256, mtime, mode) is the same after it, and it takes no lock (no pool-image.lock).

What it prints: the binary runscaler's process runs (THE RUNNING BINARY, running_sha: v0.12.0, v0.9.5 or another); the
last three records of the readers' runner.log since that process started (systemd's ActiveEnterTimestamp: log time at
or after the start's second), with their level column as written, the start's WARN marked expected; and since that
start (from the second after the start's: that second may hold the old process's last records, its drain's) the runners
removed at a scale-down or a drain, the `keeping it` records (each printed as "protected a job GitHub had assigned (the
fix at work)") and the deregister errors (`Failed to remove runner, will retry` with `error="deregister runner NAME: …`).
Its ANSWER, one per run: an error is UNRESOLVED while its runner has no LATER `Runner removed`; unresolved errors over an
hour or more (two or more) -> the way back (with its two lines, as the step's NEXT prints them); any other unresolved
error -> look again in an hour; removals and no unresolved error -> the fix works (with one retry, or N, when an error
was resolved); no removal -> not measured yet. Each of: no process, a process that changed during the read, a binary
that is not v0.12.0, and a log that is missing, unreadable or holds no record since the start, is an answer of its own,
never a count of zero.

THE RECORDS: every fixture line is one runscaler really writes, field for field (the build log, rs012-H2b2, names the
source line of each): v0.12.0's (charm log v2.0.1: a level column five wide, then one space) and, for the old process
before the start, v0.9.5's (charm log v2.0.0: four wide). The cells are a Pool (support.py) with no 03 run: the unit
(systemd.json), the process table (proc/PID/exe: the pinned substitute is 03's BIN_SHA, test_render.way_back's the
way-back one), and runner.log. (Named for its CI part, test_[k-q]*.py: .github/workflows/release-check.yml.)
"""
import calendar
import os
import re
import shlex
import subprocess
import tarfile
import time
import unittest

from tests.hetzner.support import REPO, Pool, needs_container, sha256_file
from tests.hetzner.test_render import WAYBACK_MARK, way_back

README = os.path.join(REPO, 'linux-docker', 'README.md')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
SECTION = '\n## runscaler: the release this one pins, and the way back\n'
LINE = r"ssh <RS_USER>@<host> '(bash -s -- [^']*)' < linux-docker/(setup/pool-image\.sh)"
PINNED, WAYBACK = '0.12.0', '0.9.5'
MAIN, SMALL = 'linux-ci-main', 'linux-ci-small'          # host.conf.example's set names
RB = "'/home/ci-rs/bin/runner'"                           # host.conf.example's RS_USER's ~/bin/runner, shell-quoted
START = calendar.timegm((2026, 11, 7, 10, 0, 0, 0, 0, 0))  # runscaler's ActiveEnterTimestamp: the step's restart
PID = 101
WBDL = 'runner-v%s-linux-amd64.tar.gz' % WAYBACK
URL = 'https://github.com/ysya/runscaler/releases/download/v%s/runner-linux-amd64.tar.gz'
SVC = "Service definition predates this runner's template (log directory, lock access, stop timeout)"
PROTECTED = 'protected a job GitHub had assigned (the fix at work)'
ACTIONS = 'https://pipelinesghubeus6.actions.githubusercontent.com/Xf3kQ9vLm2nRt7wYc4bJ8hZ1sD6pG0aEu5iKoN/'
IID = ('0d1e2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a', '1e2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e'
       '8f9a0b1c2d3e4f5a6b', '2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c',
       '3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d')


def at(sec):
    """The log time of START + sec (time.DateTime, UTC: the host's zone)."""
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(START + sec))


def v12(sec, level, msg, set_=None):
    """One record as runscaler v0.12.0 writes it: the time, the level column five wide and one space (charm log v2.0.1,
    styles.go Width(5)), `SET: ` for a scale set's logger (its Prefix), the message and its key=value attributes."""
    return '%s %-5s %s%s\n' % (at(sec), level, set_ + ': ' if set_ else '', msg)


def v095(sec, level, msg, set_=None):
    """The same as runscaler v0.9.5 writes it: the level column four wide (charm log v2.0.0: INFO, WARN, ERRO)."""
    return '%s %s %s%s\n' % (at(sec), level[:4], set_ + ': ' if set_ else '', msg)


def warn_svc(sec):   # cmd/runner/service_env.go:94 and :179-186 (fix: :165, shellQuotePath)
    return v12(sec, 'WARN', '%s fix="%s migrate --user"' % (SVC, RB))


def starting(sec):   # cmd/runner/main.go:534-537
    return v12(sec, 'INFO', 'Starting scale sets count=2 concurrent=4')


def reused(sec, set_, n):   # cmd/runner/scaleset.go:82-85
    return v12(sec, 'INFO', 'Scale set reused scaleSetID=%d name=%s' % (n, set_), set_)


def listening(sec, set_, mx):   # cmd/runner/main.go:673-676
    return v12(sec, 'INFO', 'Listening for jobs maxRunners=%d minRunners=0' % mx, set_)


def scaling_up(sec):   # internal/controller/controller.go:236-239
    return v12(sec, 'INFO', 'Scaling up runner currentCount=0 desiredCount=1', MAIN)


def started(sec, name, iid):   # internal/controller/controller.go:445-449
    return v12(sec, 'INFO', 'Runner started name=%s instanceID=%s startupTime=2.104318871s' % (name, iid), MAIN)


def removed(sec, name, iid, reason, form=v12, set_=MAIN):   # internal/controller/controller.go:717-734 (v0.9.5: :656-673)
    job = (' jobId=7c1e9a52-0b3d-4f6e-9a8b-2d4c6e8f0a1b repo=your-org/app workflowRunId=19234567890 job=build '
           'result=succeeded') if reason == 'job-completed' else ''
    return form(sec, 'INFO', 'Runner removed name=%s instanceID=%s reason=%s%s' % (name, iid, reason, job), set_)


def keeping(sec, name):   # internal/controller/controller.go:329-330
    return v12(sec, 'INFO', 'Runner holds a job GitHub assigned before JobStarted arrived; keeping it name=%s' % name,
               MAIN)


def dereg(sec, name, retry, status='403 Forbidden', agent=57):
    """internal/controller/controller.go:300-304 (the record) and :333 (its error); the error of scaleset v0.4.0's
    RemoveRunner (client.go:708-727, its URL :241-268; errors.go:42-62: an answer with no body), quoted with each `"`
    escaped (charm log text.go:254-259); retryIn state.go:326-341."""
    err = ('deregister runner %s: request DELETE %s_apis/distributedtask/pools/0/agents/%d?api-version=6.0-preview '
           'failed(status=\\"%s\\"): unexpected status code: %s: unknown error' % (name, ACTIONS, agent, status,
                                                                                  status.split()[0]))
    return v12(sec, 'ERROR', 'Failed to remove runner, will retry name=%s retryIn=%s error="%s"' % (name, retry, err),
               MAIN)


def old_drain():
    """The old process (runscaler v0.9.5, before the step's restart) drains: its idle runners removed with reason drain
    (v0.9.5 controller.go:533-541), `Draining runners busy=0` (:544), then `Shutting down runners` (:588), the small
    set's last in the start's own second."""
    return (removed(-2, 'runner-0a1b2c3d', IID[0], 'drain', v095) + v095(-2, 'INFO', 'Draining runners busy=0', MAIN)
            + v095(-2, 'INFO', 'Shutting down runners', MAIN)
            + removed(0, 'runner-9f8e7d6c', IID[1], 'drain', v095, SMALL)
            + v095(0, 'INFO', 'Draining runners busy=0', SMALL) + v095(0, 'INFO', 'Shutting down runners', SMALL))


def new_start():
    """runscaler v0.12.0 starts (the step's restart): its WARN, then each set's scale set and listener."""
    return (warn_svc(0) + starting(0) + reused(1, MAIN, 7) + reused(1, SMALL, 8) + listening(1, MAIN, 3)
            + listening(1, SMALL, 1))


def a_job(t0, name, iid):
    """A job on a runner the new process starts: scaled up, started, the job done (reason job-completed)."""
    return scaling_up(t0) + started(t0 + 3, name, iid) + removed(t0 + 480, name, iid, 'job-completed')


def retries(t0, name, until):
    """THE RETRY of a removal whose deregister fails (state.go:326-341): 5 s, 10 s, 20 s, 40 s, then every 80 s, from
    t0 while the time is before UNTIL: [(sec, the record)]."""
    out, t, n = [], t0, 0
    while t < until:
        d = 5 * 2 ** min(n, 4)
        out.append(dereg(t, name, '%ds' % d if d < 60 else '1m20s'))
        t, n = t + d, n + 1
    return ''.join(out), t


def section():
    with open(README) as f:
        text = f.read()
    assert text.count(SECTION) == 1, 'one section "runscaler: the release this one pins, and the way back"'
    return text.split(SECTION, 1)[1].split('\n## ', 1)[0]


def step3():
    """Step 3 of the section: its line `3. …` and the lines indented under it."""
    lines = section().split('\n')
    i = [n for n, l in enumerate(lines) if l.startswith('3. ')]
    assert len(i) == 1, 'one step 3'
    out = [lines[i[0]]]
    for l in lines[i[0] + 1:]:
        if not l.startswith('   '):
            break
        out.append(l)
    return '\n'.join(out)


def check_line():
    """Step 3's one fenced line."""
    blocks = re.findall(r'(?m)^   ```\n   (.*)\n   ```$', step3())
    assert len(blocks) == 1, 'step 3 has one fenced line: %r' % blocks
    return blocks[0]


def every(p):
    """{path: (kind, sha256, mtime_ns, mode)} of every file and folder in the home, ~/build too."""
    out = {}
    for d, dirs, names in os.walk(p.home):
        s = os.stat(d)
        out[d] = ('dir', None, s.st_mtime_ns, s.st_mode)
        for n in names:
            f = os.path.join(d, n)
            s = os.lstat(f)
            out[f] = ('file', sha256_file(f) if os.path.isfile(f) and not os.path.islink(f) else None, s.st_mtime_ns,
                      s.st_mode)
    return out


def substitute(p):
    """The pinned runscaler of the cell (03's BIN_SHA): the `runner` of ~/build/dl's tarball (support.Pool)."""
    with tarfile.open(os.path.join(p.build, 'dl', 'runner-linux-amd64.tar.gz')) as t:
        return t.extractfile('runner').read()


def home(test, log, exe='pinned', **unit):
    """A fixture home: runscaler's unit active and enabled, its process PID (started START) running EXE (pinned: 03's
    BIN_SHA; wayback: test_render.way_back's, 03's WAYBACK_BIN_SHA; other: bytes 03 does not name), and runner.log LOG
    (None: none)."""
    p = Pool(test)
    b = substitute(p)
    if exe == 'wayback':
        way_back(test, p, install=False)
        b += WAYBACK_MARK
    elif exe == 'other':
        b += b'# a runscaler this release does not know\n'
    d = p.path('proc', str(PID))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'exe'), 'wb') as f:
        f.write(b)
    p.set_unit(**dict(dict(active=True, enabled=True, start=START, pid=PID, next_pid=PID), **unit))
    if log is not None:
        p.write(p.rpath('runner.log'), log, 0o600)
    return p


def check(test, p, grows=False):
    """THE README LINE, as written: `bash -s -- ARGS` with pool-image.sh (the home's ~/build copy) on its stdin, as
    RS_USER; it changes nothing (every(): the home before and after) and takes no lock. GROWS: runner.log may have
    grown by what a restart during the check appended to it (the systemctl substitute's process logs its start)."""
    m = re.fullmatch(LINE, check_line())
    test.assertIsNotNone(m, check_line())
    before = every(p)
    log = os.path.realpath(p.rpath('runner.log'))   # every() names the sandbox's paths
    old = open(log, 'rb').read() if grows else None
    p.files()
    with open(os.path.join(p.build, m.group(2)), 'rb') as f:
        r = subprocess.run(shlex.split(m.group(1)), stdin=f, env=p.env(), cwd=p.HOME, capture_output=True, text=True,
                           timeout=300)
    after = every(p)
    if grows:
        test.assertTrue(open(log, 'rb').read().startswith(old), 'runner.log only grew')
        test.assertIn(log, before)
        after[log] = before[log]
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    test.assertEqual(changed, [], 'the check changed the home: ' + r.stdout[-2000:] + r.stderr)
    test.assertFalse(os.path.lexists(p.rpath('pool-image.lock')), 'the check took the lock')
    return r


def answer(test, r):
    """The run's one ANSWER line."""
    a = [l for l in r.stdout.splitlines() if l.startswith('ANSWER ')]
    test.assertEqual(len(a), 1, r.stdout[-3000:] + r.stderr)
    return a[0]


def records_shown(r):
    """The records the check printed: its lines that start with two spaces and a log time."""
    return [l[2:] for l in r.stdout.splitlines() if re.match(r'  [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} ', l)]


def way_back_lines():
    """The way back's two lines, as the step's NEXT prints them (test_the_runscaler_step's Forward)."""
    return ['  mkdir -p ~/build/dl && curl -fsSL -o ~/build/dl/%s %s' % (WBDL, URL % WAYBACK),
            '  pool-image.sh runscaler %s' % WAYBACK]


class Readme(unittest.TestCase):
    def test_step_3_is_the_check_s_one_line(self):
        """Step 3 runs the check: one runnable line as RS_USER, pool-image.sh's mode `runscaler-check` (the mode its
        usage names and its case reads), the same `bash -s` form as the step's own line."""
        line = check_line()
        m = re.fullmatch(LINE, line)
        self.assertIsNotNone(m, line)
        self.assertEqual(shlex.split(m.group(1)), ['bash', '-s', '--', 'runscaler-check'])
        with open(PIMG) as f:
            text = f.read()
        self.assertEqual(text.count('\n  runscaler-check:1) '), 1, "pool-image.sh's case reads the mode")
        self.assertIn('| runscaler-check', text.split('\nusage() {', 1)[1].split('\n', 1)[0])

    def test_step_3_names_each_answer_and_what_to_do(self):
        """Each answer by its words, with what to do; the WARN expected, its fix and `runner update` never run."""
        s = step3()
        for w in ('`the fix works`', '`with one retry`', '`not measured yet`', '`look again in an hour`',
                  '`the way back`', '`v0.12.0 is not running`', '`no process`', '`no log`',
                  '`changed during the check`', '`%s`' % PROTECTED, 'Nothing to do', 'the next day', 'in an hour',
                  'over an hour', "the way back's two lines", 'only reads', 'no lock'):
            self.assertIn(w, s)
        self.assertIn("`Service definition predates this runner's template …`", s)
        self.assertRegex(s, r'expected')
        self.assertRegex(s, r'(?i)never run its `fix=… migrate --user`')
        self.assertRegex(s, r'(?i)never `runner update`')


@needs_container
class Answers(unittest.TestCase):
    def test_works(self):
        """A runner removed at a scale-down since the start, no deregister error: the fix works (exit 0). The process
        line names v0.12.0; the last three records are the process's, each with its level column as written."""
        log = old_drain() + new_start() + a_job(120, 'runner-1a2b3c4d', IID[2]) + scaling_up(610) \
            + started(613, 'runner-2b3c4d5e', IID[3]) + removed(900, 'runner-2b3c4d5e', IID[3], 'scaled-down')
        p = home(self, log)
        r = check(self, p)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(answer(self, r), r'^ANSWER the fix works: ')
        self.assertIn('runscaler v%s' % PINNED, r.stdout)
        self.assertEqual(records_shown(r), log.splitlines()[-3:])
        self.assertIn('%s INFO  %s: Runner removed name=runner-2b3c4d5e' % (at(900), MAIN), r.stdout)
        self.assertIn('  removed at a scale-down or a drain: 1 runner(s), the last at %s (runner-2b3c4d5e, '
                      'reason=scaled-down)\n' % at(900), r.stdout)

    def test_works_with_one_retry(self):
        """A deregister error (a 502) followed by that runner's removal 5 s later: resolved: "the fix works, with one
        retry"."""
        log = old_drain() + new_start() + scaling_up(610) + started(613, 'runner-2b3c4d5e', IID[3]) \
            + dereg(900, 'runner-2b3c4d5e', '5s', '502 Bad Gateway') \
            + removed(905, 'runner-2b3c4d5e', IID[3], 'scaled-down')
        r = check(self, home(self, log))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(answer(self, r), r'^ANSWER the fix works, with one retry: ')

    def test_protected_a_job(self):
        """R-7: a `keeping it` record prints as "protected a job GitHub had assigned (the fix at work)", with its time
        and runner; with a removal the fix works; with none (that runner's job done later: job-completed) it is not
        measured yet, and the record still prints."""
        kept = scaling_up(610) + started(613, 'runner-3c4d5e6f', IID[2]) + keeping(700, 'runner-3c4d5e6f') \
            + removed(1500, 'runner-3c4d5e6f', IID[2], 'job-completed')
        down = scaling_up(1600) + started(1603, 'runner-2b3c4d5e', IID[3]) \
            + removed(1900, 'runner-2b3c4d5e', IID[3], 'scaled-down')
        for name, log, want, rc in (('with a removal', new_start() + kept + down, 'the fix works: ', 0),
                                    ('no removal', new_start() + kept, 'not measured yet: ', 0)):
            with self.subTest(name):
                r = check(self, home(self, log))
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                self.assertRegex(answer(self, r), '^ANSWER ' + want)
                self.assertIn('  %s runner-3c4d5e6f: %s\n' % (at(700), PROTECTED), r.stdout)

    def test_not_yet(self):
        """No runner removed at a scale-down or a drain since the start (a job done is no such removal): not measured
        yet, nothing to do, look again the next day (exit 0). The OLD process's drain removals (v0.9.5's, before the
        start and in its own second) are not counted."""
        log = old_drain() + new_start() + a_job(120, 'runner-1a2b3c4d', IID[2])
        r = check(self, home(self, log))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        a = answer(self, r)
        self.assertRegex(a, r'^ANSWER not measured yet: ')
        self.assertIn('the next day', a)

    def test_look_again_in_an_hour(self):
        """Unresolved deregister errors (a 403) not yet over an hour: one; three of one runner 5 s and 10 s apart (the
        retry's first steps); and one whose runner was removed BEFORE it (a removal resolves only a LATER one)."""
        base = new_start() + scaling_up(610) + started(613, 'runner-4d5e6f7a', IID[2])
        for name, log in (
                ('one error', base + dereg(900, 'runner-4d5e6f7a', '5s')),
                ('a retry run of 15 s', base + retries(900, 'runner-4d5e6f7a', 916)[0]),
                ('the removal before it', base + removed(800, 'runner-4d5e6f7a', IID[2], 'scaled-down')
                 + dereg(900, 'runner-4d5e6f7a', '5s'))):
            with self.subTest(name):
                r = check(self, home(self, log))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, r'^ANSWER look again in an hour: ')
                self.assertNotIn('pool-image.sh runscaler %s' % WAYBACK, r.stdout)

    def test_the_way_back(self):
        """Unresolved deregister errors (403s, runscaler's retry: 5, 10, 20, 40 s, then every 80 s) from 900 s to more
        than an hour later: the way back, with its two lines as the step's NEXT prints them (exit 1). The control: the
        same errors, then that runner's removal: resolved, "the fix works, with N retries" (exit 0), no way back."""
        errs, end = retries(900, 'runner-5e6f7a8b', 900 + 3700)
        n = errs.count('\n')
        base = new_start() + scaling_up(610) + started(613, 'runner-5e6f7a8b', IID[2]) + errs
        r = check(self, home(self, base))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(answer(self, r), r'^ANSWER the way back: ')
        out = r.stdout.splitlines()
        i = out.index(answer(self, r))
        self.assertEqual(out[i + 1:i + 3], way_back_lines())
        r = check(self, home(self, base + removed(end, 'runner-5e6f7a8b', IID[2], 'scaled-down')))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(answer(self, r), r'^ANSWER the fix works, with %d retries: ' % n)
        self.assertNotIn(way_back_lines()[1], r.stdout.splitlines())

    def test_v0_12_0_not_running(self):
        """The process runs v0.9.5 (the way back: its log in v0.9.5's form), or a runscaler this release does not know:
        v0.12.0 is not running (exit 1), never a count."""
        old = v095(0, 'INFO', 'Starting scale sets count=2 concurrent=4') \
            + v095(1, 'INFO', 'Listening for jobs maxRunners=3 minRunners=0', MAIN) \
            + removed(900, 'runner-2b3c4d5e', IID[3], 'scaled-down', v095)
        new = new_start() + scaling_up(610) + started(613, 'runner-2b3c4d5e', IID[3]) \
            + removed(900, 'runner-2b3c4d5e', IID[3], 'scaled-down')
        for exe, log, name in (('wayback', old, 'runscaler v%s' % WAYBACK),
                               ('other', new, 'a runscaler this release does not know')):
            with self.subTest(exe):
                r = check(self, home(self, log, exe))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, r'^ANSWER v0\.12\.0 is not running: ')
                self.assertIn(name, a)
                self.assertNotIn('the fix works', r.stdout)

    def test_no_process(self):
        """runscaler's unit runs no process (failed; inactive): its own answer (exit 1), naming the unit's state. A unit
        whose read fails: a FAIL line, no answer."""
        log = new_start()
        for name, unit, state in (('failed', dict(active=False, failed=True, pid=0), 'failed'),
                                  ('inactive', dict(active=False, pid=0), 'inactive')):
            with self.subTest(name):
                r = check(self, home(self, log, **unit))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, r'^ANSWER no process: ')
                self.assertIn(state, a)
        with self.subTest('the unit cannot be read'):
            p = home(self, log)
            p.show_answer(1, '')
            r = check(self, p)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertNotIn('ANSWER ', r.stdout)
            self.assertIn('FAIL ', r.stdout)

    def test_missing_log(self):
        """No runner.log; a folder in its place; a runner.log with no record since the start (only the old process's,
        before it): each "no log" (exit 1), never "not measured yet"."""
        for name, log, why in (('no file', None, 'missing'), ('a folder', 'folder', 'not a file'),
                               ('no record since the start', removed(-90, 'runner-0a1b2c3d', IID[0], 'drain', v095)
                                + v095(-90, 'INFO', 'Draining runners busy=0', MAIN), 'no record since')):
            with self.subTest(name):
                p = home(self, None if log == 'folder' else log)
                if log == 'folder':
                    os.makedirs(p.rpath('runner.log'))
                r = check(self, p)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, r'^ANSWER no log: ')
                self.assertIn(why, a)

    def test_changed_during_the_read(self):
        """runscaler restarts while the check reads (after its first unit read; after its read of the process's
        binary): "changed during the check" (exit 1), never an answer from the facts of two processes. The control,
        the same home with no restart: the fix works."""
        log = new_start() + scaling_up(610) + started(613, 'runner-2b3c4d5e', IID[3]) \
            + removed(900, 'runner-2b3c4d5e', IID[3], 'scaled-down')
        for n in (1, 2):
            with self.subTest(after='systemctl show %d' % n):
                p = home(self, log)
                p.count_shows()
                p.hooks(('systemctl:show-%d' % n, 'restart'))
                r = check(self, p, grows=True)
                self.assertTrue([e for e in p.events() if re.fullmatch(r'process [0-9]+ started [0-9]+', e)],
                                'the restart ran')
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertRegex(answer(self, r), r'^ANSWER changed during the check: ')
        with self.subTest('control: no restart'):
            r = check(self, home(self, log))
            self.assertRegex(answer(self, r), r'^ANSWER the fix works: ')

    def test_the_warn_is_marked_expected(self):
        """v0.12.0's start WARN among the last three records: printed as written, marked expected, its fix and
        `runner update` never run; a record of another text is not marked."""
        log = old_drain() + warn_svc(0) + starting(0) + reused(1, MAIN, 7)
        r = check(self, home(self, log))
        shown = [l for l in r.stdout.splitlines() if l.startswith('  ' + warn_svc(0).rstrip('\n'))]
        self.assertEqual(len(shown), 1, r.stdout)
        self.assertRegex(shown[0], r'expected.*never run its fix=… migrate --user.*never runner update')
        marked = [l for l in r.stdout.splitlines() if 'expected' in l and l.startswith('  20')]
        self.assertEqual(marked, shown)
        self.assertRegex(answer(self, r), r'^ANSWER not measured yet: ')


if __name__ == '__main__':
    unittest.main()
