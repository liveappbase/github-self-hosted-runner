"""THE CHECK THE NEXT DAY, `pool-image.sh runscaler-check` (runscaler 0.12 bump, Hetzner slice H2b-2; the H2 plan's M-5
with its r3 FOLD R-7 and its r4 AMENDMENT, ACCEPTANCE (c)): the README line a person runs as RS_USER the day after
`pool-image.sh runscaler` (the section "runscaler: the release this one pins, and the way back", step 3), extracted and
run as written (`bash -s -- ARGS`, pool-image.sh on its stdin) on fixture homes, one per answer. It only READS: every
file and folder of the home (sha256, mtime, mode) is the same after it, and it takes no lock (no pool-image.lock).

What it reads: the unit, the binary runscaler's process runs (THE RUNNING BINARY, running_sha: v0.12.0, v0.9.5 or
another), runner.log (and runner.log.1, the one older file runscaler keeps at a rotation) since that process started
(systemd's ActiveEnterTimestamp: log time at or after the start's second), THE RUNS RULE (runner-facts.sh's `runs`: two
/healthz reads 3 s apart that list both sets, the same process before and after, no file), then the unit again. It
prints the last three records with their level column as written, v0.12.0's start WARN and its `runner update` note
marked (never run), and, from the second after the start's (that second may hold the old process's last records, its
drain's), the removals, the `keeping it` records, the deregister errors, the runner starts and start failures (and the
open ones), and each record of a job that may have been cut. A RESTART AFTER THE STEP (review r1 of H2c, the H2 plan's
r5 AMENDMENT): with ~/bin/runner the pinned runscaler, the records of an earlier v0.12.0 process (five wide) from its
mtime (the step's install) to the start are named as not counted, and read for a removal that names a job.

THE ANSWERS, one per run, the first that holds in this order (the build log, fix round 1, and the README name it): no
process; changed during the check; starting (a binary that is no runscaler yet, its unit started under a minute ago);
v0.12.0 is not running; does not serve (THE RUNS RULE); no log; the way back (the open deregister errors of one runner
over an hour; or, with no open error, deregister errors over an hour with no accepted removal after the first of them;
or OPEN start failures over an hour); a job may have been cut; look again in an hour (any other open error, or open
start failures under an hour); the fix works (a removal at a scale-down or a drain); not measured yet. An ACCEPTED
removal: a `Runner removed` of reason scaled-down or drain (logged only after GitHub accepted the DELETE) or a `keeping
it` record (GitHub's answer to the DELETE); a job-completed removal is none. A deregister error is OPEN while its runner
has no later removal (any reason) and no later `keeping it`; a start failure is OPEN while no `Runner started` follows
it (r5).

THE RECORDS: every fixture line is one runscaler really writes, field for field (each helper names its source line):
v0.12.0's (charm log v2.0.1: a level column five wide, then one space; a value with a newline on lines of its own) and,
for the old process before the start, v0.9.5's (charm log v2.0.0: four wide). The cells are a Pool (support.py) with no
03 run: the unit (systemd.json), the process table (proc/PID/exe: the pinned substitute is 03's BIN_SHA,
test_render.way_back's the way-back one), runner.log, /healthz (curl.json) and the fake clock (Pool.fake_clock: the
check's `date +%s`, and the RUNS RULE's `sleep 3`, which then returns at once and is logged). (Named for its CI part,
test_[k-q]*.py: .github/workflows/release-check.yml.)
"""
import calendar
import json
import os
import re
import shlex
import subprocess
import tarfile
import time
import unittest

from tests.hetzner.support import REPO, Pool, healthz, needs_container, sha256_file
from tests.hetzner.test_render import WAYBACK_MARK, way_back

README = os.path.join(REPO, 'linux-docker', 'README.md')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
SECTION = '\n## runscaler: the release this one pins, and the way back\n'
LINE = r"ssh <RS_USER>@<host> '(bash -s -- [^']*)' < linux-docker/(setup/pool-image\.sh)"
PINNED, WAYBACK = '0.12.0', '0.9.5'
MAIN, SMALL = 'linux-ci-main', 'linux-ci-small'          # host.conf.example's set names
RB = "'/home/ci-rs/bin/runner'"                           # host.conf.example's RS_USER's ~/bin/runner, shell-quoted
START = calendar.timegm((2026, 11, 7, 10, 0, 0, 0, 0, 0))  # runscaler's ActiveEnterTimestamp: the step's restart
DAY = 86400                                               # the check's clock: the next day (home's AGE)
PID = 101
WBDL = 'runner-v%s-linux-amd64.tar.gz' % WAYBACK
URL = 'https://github.com/ysya/runscaler/releases/download/v%s/runner-linux-amd64.tar.gz'
SVC = "Service definition predates this runner's template (log directory, lock access, stop timeout)"
PROTECTED = 'protected a job GitHub had assigned (the fix at work)'
ACTIONS = 'https://pipelinesghubeus6.actions.githubusercontent.com/Xf3kQ9vLm2nRt7wYc4bJ8hZ1sD6pG0aEu5iKoN/'
JIT = ACTIONS + '_apis/runtime/runnerscalesets/7/generatejitconfig?api-version=6.0-preview'   # MAIN's scale set: 7
IID = ('0d1e2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a', '1e2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e'
       '8f9a0b1c2d3e4f5a6b', '2f3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c',
       '3a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d')
JOBID = '7c1e9a52-0b3d-4f6e-9a8b-2d4c6e8f0a1b'
A, B, C = 'runner-4d5e6f7a', 'runner-5e6f7a8b', 'runner-2b3c4d5e'
BODY = 'upstream connect error or disconnect/reset before headers.\nreset reason: connection timeout'   # two lines


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


def lines_value(head, key, value):
    """A record whose LAST attribute's value holds a newline, as charm log v2.0.1 writes it (text.go:18-48, :236-240):
    the record's first line, then `  KEY=` on a line of its own, then each line of the value after `  │ `, its quotes
    as they are (no escaping), and the record's own newline."""
    return '%s\n  %s=\n%s\n' % (head.rstrip('\n'), key, '\n'.join('  │ ' + l for l in value.split('\n')))


def warn_svc(sec):   # cmd/runner/service_env.go:94 and :179-186 (fix: :165, shellQuotePath)
    return v12(sec, 'WARN', '%s fix="%s migrate --user"' % (SVC, RB))


def newer(sec):
    """cmd/runner/main.go:539-551: at a start, when GitHub's latest runscaler release is another (internal/versioncheck
    IsNewer); current = main.version, goreleaser's {{.Version}} (no v), latest = the release's tag."""
    return v12(sec, 'WARN', "A newer version of runner is available — run 'runner update' to upgrade current=0.12.0 "
               "latest=v0.13.0")


def monitor(sec, name):
    """internal/controller/controller.go:537 (watchInstance): the docker wait for a runner's container failed
    (provider/docker.go WaitInstance: "wait for runner container: %w", the docker client's own text); it retries in
    5 s."""
    return v12(sec, 'WARN', 'Runner monitor failed; retrying name=%s error="wait for runner container: Cannot connect '
               'to the Docker daemon at unix:///home/ci-run/run/docker.sock. Is the docker daemon running?"' % name,
               MAIN)


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


def removed(sec, name, iid, reason, form=v12, set_=MAIN, job=None):
    """internal/controller/controller.go:717-734 (v0.9.5: :656-673): the job's fields when the runner had one: a
    job-completed removal always, with its result (state.go:244-255); a scaled-down or drain removal with JOB=True, a
    job GitHub gave the runner while its removal ran (markBusy, state.go:186-197), with no result
    (markIdleAboveTarget and idleForRemoval set none)."""
    if job is None:
        job = reason == 'job-completed'
    j = (' jobId=%s repo=your-org/app workflowRunId=19234567890 job=build' % JOBID
         + (' result=succeeded' if reason == 'job-completed' else '')) if job else ''
    return form(sec, 'INFO', 'Runner removed name=%s instanceID=%s reason=%s%s' % (name, iid, reason, j), set_)


def keeping(sec, name):   # internal/controller/controller.go:329-330
    return v12(sec, 'INFO', 'Runner holds a job GitHub assigned before JobStarted arrived; keeping it name=%s' % name,
               MAIN)


def unknown_job(sec, name):
    """internal/controller/controller.go:152-163 (HandleJobStarted): GitHub's JobStarted names a runner this process no
    longer tracks (markBusy false): the record pool-image.sh's restart-cut scan reads as a cut job."""
    return v12(sec, 'WARN', 'Job started for unknown runner (already removed?) runnerName=%s' % name, MAIN)


def dereg(sec, name, retry, status='403 Forbidden', agent=57, lines=False):
    """internal/controller/controller.go:300-304 (the record) and :333 (its error); the error of scaleset v0.4.0's
    RemoveRunner (client.go:708-727, its URL :241-268; errors.go:42-62: an answer with no body), quoted with each `"`
    escaped (charm log text.go:254-259); retryIn state.go:326-341. LINES: GitHub answered a 503 with a text/plain body
    of two lines (BODY; errors.go:79-80 puts it into the error as it is): the error on lines of its own."""
    if lines:
        err = ('deregister runner %s: request DELETE %s_apis/distributedtask/pools/0/agents/%d?api-version=6.0-preview '
               'failed(status="503 Service Unavailable"): unexpected status code: 503: %s'
               % (name, ACTIONS, agent, BODY))
        return lines_value(v12(sec, 'ERROR', 'Failed to remove runner, will retry name=%s retryIn=%s' % (name, retry),
                               MAIN), 'error', err)
    err = ('deregister runner %s: request DELETE %s_apis/distributedtask/pools/0/agents/%d?api-version=6.0-preview '
           'failed(status=\\"%s\\"): unexpected status code: %s: unknown error' % (name, ACTIONS, agent, status,
                                                                                  status.split()[0]))
    return v12(sec, 'ERROR', 'Failed to remove runner, will retry name=%s retryIn=%s error="%s"' % (name, retry, err),
               MAIN)


def docker_err(sec, name, retry, iid=IID[2]):
    """internal/controller/controller.go:300-304 when the container's removal fails, not the deregister (GitHub accepted
    it, or none was needed): provider/docker.go:179-187 ("failed to remove runner container: %w") around the docker
    daemon's answer. No deregister error."""
    return v12(sec, 'ERROR', 'Failed to remove runner, will retry name=%s retryIn=%s error="failed to remove runner '
               'container: Error response from daemon: removal of container %s is already in progress"'
               % (name, retry, iid), MAIN)


def start_failed(sec, lines=False):
    """internal/controller/controller.go:254-257 (reconcileOne; retried 5 s later while the demand lasts): the error of
    startInstanceWithLease (:419, "failed to generate JIT config: %w") around scaleset v0.4.0's GenerateJitRunnerConfig
    (client.go:606-630, errors.go:42-62): a 500 with no body; LINES: a 503 whose text/plain body has two lines."""
    if lines:
        return lines_value(v12(sec, 'ERROR', 'Failed to start runner, will retry', MAIN), 'error',
                           'failed to generate JIT config: request POST %s failed(status="503 Service Unavailable"): '
                           'unexpected status code: 503: %s' % (JIT, BODY))
    return v12(sec, 'ERROR', 'Failed to start runner, will retry error="failed to generate JIT config: request POST %s '
               'failed(status=\\"500 Internal Server Error\\"): unexpected status code: 500: unknown error"' % JIT,
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


def a_process(t0, form=v12, job=True, drain=None):
    """A runscaler process that started at START + t0, before the start the check reads, in FORM (v12: an earlier
    v0.12.0 process, five wide; v095: the v0.9.5 process before the step, four wide): its start records
    (main.go:534-537, :673-676), runner C started (controller.go:445-449) and removed at a scale-down (controller.go
    :717-734), while GitHub had given it a job (JOB: removed(job=True), the cut record) or not. DRAIN: the second (from
    START) of its drain at its stop, the removal of runner A with a job (reason drain, jobId=); none by default."""
    out = (form(t0, 'INFO', 'Starting scale sets count=2 concurrent=4')
           + form(t0 + 1, 'INFO', 'Listening for jobs maxRunners=3 minRunners=0', MAIN)
           + form(t0 + 600, 'INFO', 'Scaling up runner currentCount=0 desiredCount=1', MAIN)
           + form(t0 + 603, 'INFO', 'Runner started name=%s instanceID=%s startupTime=2.104318871s' % (C, IID[3]), MAIN)
           + removed(t0 + 900, C, IID[3], 'scaled-down', form, job=job))
    if drain is not None:
        out += removed(drain, A, IID[2], 'drain', form, job=True)
    return out


def a_job(t0, name, iid):
    """A job on a runner the new process starts: scaled up, started, the job done (reason job-completed)."""
    return scaling_up(t0) + started(t0 + 3, name, iid) + removed(t0 + 480, name, iid, 'job-completed')


def scaled_down(t0, name, iid):
    """A runner the new process starts, then removes at a scale-down (its DELETE accepted)."""
    return scaling_up(t0) + started(t0 + 3, name, iid) + removed(t0 + 290, name, iid, 'scaled-down')


def retries(t0, name, until, make=dereg):
    """THE RETRY of a removal that fails (state.go:326-341): 5 s, 10 s, 20 s, 40 s, then every 80 s, from t0 while the
    time is before UNTIL: (the records, the time of the next). MAKE(sec, name, retryIn): the record."""
    out, t, n = [], t0, 0
    while t < until:
        d = 5 * 2 ** min(n, 4)
        out.append(make(t, name, '%ds' % d if d < 60 else '1m20s'))
        t, n = t + d, n + 1
    return ''.join(out), t


def start_failures(t0, until, lines=False):
    """A job waits and no runner starts: `Scaling up runner`, then the start's failure, again 6 s later (the 5 s retry),
    from t0 while the time is before UNTIL."""
    return ''.join(scaling_up(t) + start_failed(t + 1, lines) for t in range(t0, until, 6))


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


def home(test, log, exe='pinned', age=DAY, rotated=None, installed=None, **unit):
    """A fixture home: runscaler's unit active and enabled, its process PID (started START) running EXE (pinned: 03's
    BIN_SHA; wayback: test_render.way_back's, 03's WAYBACK_BIN_SHA; other: bytes 03 does not name; none: no exe to
    read), runner.log LOG (None: none) and runner.log.1 ROTATED (None: none), /healthz listing both sets (support's
    healthz()), and the fake clock at START + AGE (the next day). INSTALLED: ~/bin/runner is the pinned runscaler, its
    mtime START + INSTALLED (the step's install of v0.12.0); None: no ~/bin/runner (the check reads no install time)."""
    p = Pool(test)
    b = substitute(p)
    if installed is not None:
        rb = os.path.join(p.HOME, 'bin', 'runner')
        os.makedirs(os.path.dirname(rb), exist_ok=True)
        with open(rb, 'wb') as f:
            f.write(b)
        os.chmod(rb, 0o755)
        os.utime(rb, (START + installed, START + installed))
    if exe == 'wayback':
        way_back(test, p, install=False)
        b += WAYBACK_MARK
    elif exe == 'other':
        b += b'# a runscaler this release does not know\n'
    d = p.path('proc', str(PID))
    os.makedirs(d, exist_ok=True)
    if exe != 'none':
        with open(os.path.join(d, 'exe'), 'wb') as f:
            f.write(b)
    p.set_unit(**dict(dict(active=True, enabled=True, start=START, pid=PID, next_pid=PID), **unit))
    if log is not None:
        p.write(p.rpath('runner.log'), log, 0o600)
    if rotated is not None:
        p.write(p.rpath('runner.log.1'), rotated, 0o600)
    p.fake_clock()
    p.clock(now=START + age)
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


def after_answer(test, r):
    """The two lines right after the ANSWER line."""
    out = r.stdout.splitlines()
    i = out.index(answer(test, r))
    return out[i + 1:i + 3]


def reads(p):
    """The /healthz reads and the sleeps between them, in order (the substitutes' events)."""
    return [e for e in p.events() if e == 'healthz read' or e.startswith('sleep ')]


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

    def test_step_3_names_the_rules_of_fix_round_1(self):
        """Fix round 1 (review r1: the H2 plan's r4 AMENDMENT): the answers it adds, with what to do; what an accepted
        removal is and when an error is open; the `runner update` note marked; runner.log.1 read; and the ORDER of the
        answers, each named once in that order."""
        s = step3()
        for w in ('`starting`', '`does not serve`', '`a job may have been cut`', '`keeping it`', '`job-completed`',
                  'accepted', 'open', '`Failed to start runner`', '`Runner started`', '`runner.log.1`',
                  '`Job started for unknown runner`', '`jobId=`', 'lost communication', 'in a minute',
                  'in a few minutes', "`A newer version of runner is available …`"):
            self.assertIn(w, s)
        order = re.search(r'(?m)^   The answers, in this order[^\n]*\n((?:   - [^\n]*\n?)+)', s)
        self.assertIsNotNone(order, s)
        got = re.findall(r'(?m)^   - `([^`]+)`', order.group(1))
        self.assertEqual(got, ['no process', 'changed during the check', 'starting', 'v0.12.0 is not running',
                               'does not serve', 'no log', 'the way back', 'a job may have been cut',
                               'look again in an hour', 'the fix works', 'not measured yet'])

    def test_step_3_names_the_rules_of_fix_round_2(self):
        """Fix round 2 (review r1 of H2c: the H2 plan's r5 AMENDMENT): a start failure is open while no `Runner
        started` follows it, and the way back and look again read the open ones (8b917c7's text: "with no runner
        started", since the start); a restart after the step: the check says so, does not count the records from the
        install of v0.12.0 to that restart, and still reads a removal among them that names a `jobId=`."""
        s = step3()
        for w in ('A start failure is open while no `Runner started` follows it', 'open start failures over an hour',
                  'open start failures, not over an hour yet', 'If runscaler restarted after the step',
                  'not counted', 'the mtime of `~/bin/runner`'):
            self.assertIn(w, s)
        self.assertNotIn('with no runner started', s)


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
        binary; after each of THE RUNS RULE's two reads of the process, around its /healthz reads): "changed during
        the check" (exit 1), never an answer from the facts of two processes, and never "does not serve". The control,
        the same home with no restart: the fix works."""
        log = new_start() + scaling_up(610) + started(613, 'runner-2b3c4d5e', IID[3]) \
            + removed(900, 'runner-2b3c4d5e', IID[3], 'scaled-down')
        for n in (1, 2, 3, 4):
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

    # ---- fix round 1 (review r1: opus.md, opus2.md; the H2 plan's r4 AMENDMENT)

    def test_the_update_note_is_marked_never_run(self):
        """opus F5: v0.12.0's start note `A newer version of runner is available — run 'runner update' to upgrade`
        (main.go:546) among the last three records is marked as the service WARN is: never run `runner update`. The
        control: another WARN (`Runner monitor failed; retrying`) among them is not marked."""
        log = new_start() + newer(2) + monitor(700, A) + scaling_up(705)
        r = check(self, home(self, log))
        upd = [l for l in r.stdout.splitlines() if l.startswith('  ' + newer(2).rstrip('\n'))]
        self.assertEqual(len(upd), 1, r.stdout)
        self.assertRegex(upd[0][len(newer(2)) + 1:], r'^ +<- expected.*never run runner update')
        mon = [l for l in r.stdout.splitlines() if l.startswith('  ' + monitor(700, A).rstrip('\n'))]
        self.assertEqual(mon, ['  ' + monitor(700, A).rstrip('\n')], 'the monitor WARN is printed with no mark')
        self.assertRegex(answer(self, r), r'^ANSWER not measured yet: ')

    def test_a_job_completed_removal_is_no_accepted_deregister(self):
        """opus F1 (input A): every DELETE refused (403), each stuck runner leaving only when GitHub's job on it ends
        (reason job-completed: no DELETE accepted, state.go:211-219, :244-255): runner A's 20 min of retries, then three
        hours later runner B's. No error is open, but the errors span over an hour with no accepted removal after the
        first: the way back (exit 1), never "not measured yet"; also after runner C's scale-down removal BEFORE the
        first error (only an accepted removal after it counts). Control 1: each episode ended by a scale-down removal
        (the DELETE accepted at last): the fix works, with N retries (exit 0). Control 2: a `keeping it` (GitHub's
        answer to a DELETE) after the first error: not measured yet. Control 3: A's episode alone (20 min, under an
        hour): not measured yet. With B's episode still open (under an hour): look again in an hour (the rule reads
        only a log with no open error)."""
        ea, ta = retries(900, A, 900 + 1200)
        eb, tb = retries(900 + 10800, B, 900 + 10800 + 1200)
        n = (ea + eb).count('\n')
        head = new_start() + scaling_up(610) + started(613, A, IID[2]) + ea
        mid = scaling_up(11400) + started(11403, B, IID[3]) + eb
        done = head + removed(ta, A, IID[2], 'job-completed') + mid + removed(tb, B, IID[3], 'job-completed')
        after = done[len(new_start()):]   # the same records, after the start's
        kc = new_start() + scaling_up(300) + started(303, C, IID[0]) + dereg(400, C, '5s', '502 Bad Gateway') \
            + keeping(405, C)
        for name, log, want, rc in (
                ('job-completed', done, r'^ANSWER the way back: ', 1),
                ('a scale-down before the first error', new_start() + scaled_down(200, C, IID[0]) + after,
                 r'^ANSWER the way back: ', 1),
                ('control: scaled-down', head + removed(ta, A, IID[2], 'scaled-down') + mid
                 + removed(tb, B, IID[3], 'scaled-down'), r'^ANSWER the fix works, with %d retries: ' % n, 0),
                ('control 2: keeping it after the first error', kc + after,
                 r'^ANSWER not measured yet: ', 0),
                ('control 3: one episode, under an hour', head + removed(ta, A, IID[2], 'job-completed'),
                 r'^ANSWER not measured yet: ', 0),
                ('B open, under an hour', head + removed(ta, A, IID[2], 'job-completed') + mid,
                 r'^ANSWER look again in an hour: ', 1)):
            with self.subTest(name):
                r = check(self, home(self, log))
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                self.assertRegex(answer(self, r), want)
                if rc == 1 and 'way back' in want:
                    self.assertEqual(after_answer(self, r), way_back_lines())
                else:
                    self.assertNotIn(way_back_lines()[1], r.stdout.splitlines())

    def test_keeping_it_closes_an_error(self):
        """opus F1 (input B) and opus2 F3 (P3, P3b): a `keeping it` record of A after A's error closes it (GitHub
        answered the DELETE: A holds a job, runscaler retries it no more). A alone, its job still running: not measured
        yet (exit 0), and with a later scale-down removal: the fix works, with one retry. With runner B's one fresh
        error 61 min after A's: look again in an hour, never the way back. The way back is read per runner: A's and B's
        single open errors an hour apart (a synthetic order: each line is real) read look again too."""
        ka = new_start() + scaling_up(610) + started(613, A, IID[2]) + dereg(900, A, '5s', '502 Bad Gateway') \
            + keeping(905, A)
        for name, log, want, rc in (
                ('A kept, no removal (P3b)', ka, r'^ANSWER not measured yet: ', 0),
                ('A kept, then a removal', ka + scaled_down(1000, C, IID[3]),
                 r'^ANSWER the fix works, with one retry: ', 0),
                ('B errs 61 min later (P3, input B)', ka + scaling_up(4000) + started(4003, B, IID[3])
                 + dereg(4560, B, '5s', '502 Bad Gateway'), r'^ANSWER look again in an hour: ', 1),
                ('one open error each, an hour apart', new_start() + scaling_up(610) + started(613, A, IID[2])
                 + started(614, B, IID[3]) + dereg(900, A, '5s') + dereg(4560, B, '5s'),
                 r'^ANSWER look again in an hour: ', 1)):
            with self.subTest(name):
                r = check(self, home(self, log))
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                self.assertRegex(answer(self, r), want)
                self.assertNotIn(way_back_lines()[1], r.stdout.splitlines())

    def test_a_removal_of_that_runner(self):
        """opus F6, opus2 F4 (tree-ma): runner A's error, then runner B's removal at a scale-down: A's error stays open:
        look again in an hour (exit 1). The control, the same log with B = A: the fix works, with one retry."""
        base = new_start() + scaling_up(610) + started(613, A, IID[2]) + started(614, B, IID[3]) + dereg(900, A, '5s')
        for name, log, want, rc in (
                ('B removed', base + removed(950, B, IID[3], 'scaled-down'), r'^ANSWER look again in an hour: ', 1),
                ('control: A removed', base + removed(950, A, IID[2], 'scaled-down'),
                 r'^ANSWER the fix works, with one retry: ', 0)):
            with self.subTest(name):
                r = check(self, home(self, log))
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                self.assertRegex(answer(self, r), want)

    def test_a_docker_removal_error_is_no_deregister_error(self):
        """opus2 F4 (tree-mb): `Failed to remove runner, will retry … error="failed to remove runner container: …"`
        (docker's removal, not GitHub's) over an hour, no deregister error: not measured yet (exit 0), and the count
        line names 0 deregister errors."""
        errs, _ = retries(900, A, 900 + 3700, make=docker_err)
        r = check(self, home(self, new_start() + scaling_up(610) + started(613, A, IID[2]) + errs))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(answer(self, r), r'^ANSWER not measured yet: ')
        self.assertRegex(r.stdout, r'\n  deregister errors: 0[^0-9]')

    def test_an_error_on_lines_of_its_own_is_one_error(self):
        """opus F4: a deregister error whose text holds a newline (GitHub's text/plain answer), which charm log writes
        on lines of its own, is ONE deregister error: runner A refused for over an hour in that form, after runner C's
        scale-down removal: the way back (exit 1), as the one-line form gives (control 1). Control 2: a `Failed to start
        runner` whose error is on lines of its own is no deregister error (the fix works, 0 deregister errors)."""
        ml, _ = retries(900, A, 900 + 3700, make=lambda t, x, d: dereg(t, x, d, lines=True))
        one, _ = retries(900, A, 900 + 3700)
        base = new_start() + scaled_down(200, C, IID[3]) + scaling_up(610) + started(613, A, IID[2])
        for name, log in (('on lines of its own', base + ml), ('control 1: one line', base + one)):
            with self.subTest(name):
                r = check(self, home(self, log))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertRegex(answer(self, r), r'^ANSWER the way back: ')
                self.assertRegex(r.stdout, r'\n  deregister errors: %d[^0-9]' % one.count(' ERROR '))
        with self.subTest('control 2: a start failure on lines of its own'):
            log = new_start() + scaling_up(610) + start_failed(611, lines=True) + scaling_up(616) \
                + started(619, A, IID[2]) + removed(900, A, IID[2], 'scaled-down')
            r = check(self, home(self, log))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(answer(self, r), r'^ANSWER the fix works: ')
            self.assertRegex(r.stdout, r'\n  deregister errors: 0[^0-9]')

    def test_a_job_may_have_been_cut(self):
        """opus F2, opus2 F1: since the start, v0.12.0 removed runner C at a scale-down (or a drain), and then GitHub's
        JobStarted named it (`Job started for unknown runner (already removed?) runnerName=C`); or a removal of reason
        scaled-down or drain names a `jobId=` (GitHub gave C a job while its removal ran): "a job may have been cut",
        its own answer (exit 1), never "the fix works": it names the runner, the job id when the record has one, and
        the log time, says to find that job on GitHub (lost communication: v0.12.0 cut it, take the way back;
        completed: nothing to do) and prints the way back's two lines."""
        down = new_start() + scaling_up(610) + started(613, C, IID[3])
        for name, log, sec, job in (
                ('Job started for a runner removed at a scale-down', down + removed(900, C, IID[3], 'scaled-down')
                 + unknown_job(930, C), 930, None),
                ('a scale-down removal that names a job', down + removed(900, C, IID[3], 'scaled-down', job=True), 900,
                 JOBID),
                ('a drain removal that names a job', down + removed(900, C, IID[3], 'drain', job=True), 900, JOBID)):
            with self.subTest(name):
                r = check(self, home(self, log))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, r'^ANSWER a job may have been cut: ')
                self.assertIn(C, a)
                self.assertIn(at(sec), a)
                if job:
                    self.assertIn(job, a)
                self.assertIn('lost communication', a)
                self.assertIn('completed, nothing to do', a)
                self.assertEqual(after_answer(self, r), way_back_lines())
                self.assertNotIn('the fix works', r.stdout)

    def test_a_job_started_for_another_runner_is_not_held_against_it(self):
        """The controls of opus F2 / opus2 F1: the same WARN for a runner removed with reason exited (its container
        ended) or job-completed, for a runner not removed since the start, or for one the OLD process drained (before
        the start): not held against v0.12.0; nor a `reason=job-completed jobId=` removal. Each log also has runner A's
        scale-down removal: the fix works (exit 0)."""
        works = scaled_down(2000, A, IID[2])
        down = new_start() + scaling_up(610) + started(613, C, IID[3])
        for name, log in (
                ('removed: exited', down + removed(900, C, IID[3], 'exited') + unknown_job(930, C)),
                ('removed: job-completed', down + removed(900, C, IID[3], 'job-completed') + unknown_job(930, C)),
                ('not removed', down + unknown_job(930, C)),
                ('drained by the old process', old_drain() + new_start() + unknown_job(30, 'runner-0a1b2c3d')),
                ('a job-completed removal that names a job', new_start() + a_job(120, C, IID[3]))):
            with self.subTest(name):
                r = check(self, home(self, log + works))
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertRegex(answer(self, r), r'^ANSWER the fix works: ')

    def test_does_not_serve(self):
        """opus F3: v0.12.0 removed a runner at a scale-down, but /healthz gives no answer, or the second of THE RUNS
        RULE's two reads (3 s apart) lists one set only: "does not serve", its own answer (exit 1): run the check again
        in a few minutes, and if it stays so the way back (its two lines). The control: /healthz lists both sets on
        both reads: the answer is the log's (the fix works). Each: two /healthz reads with the pause between them."""
        log = new_start() + scaled_down(610, C, IID[3])
        one = healthz()
        one['scale_sets'] = one['scale_sets'][:1]
        for name, curl, want, rc in (('no answer', dict(healthz=None), r'^ANSWER does not serve: ', 1),
                                     ('one set on the second read', dict(healthz_seq=[healthz(), one]),
                                      r'^ANSWER does not serve: ', 1),
                                     ('control: both sets on both reads', {}, r'^ANSWER the fix works: ', 0)):
            with self.subTest(name):
                p = home(self, log)
                p.curl.update(curl)
                r = check(self, p)
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, want)
                self.assertEqual(reads(p), ['healthz read', 'sleep 3', 'healthz read'])
                if rc:
                    self.assertIn('in a few minutes', a)
                    self.assertEqual(after_answer(self, r), way_back_lines())

    def test_no_runner_starts(self):
        """opus2 F2: `Failed to start runner, will retry` since the start and no `Runner started` since the start: under
        an hour, look again in an hour (exit 1); an hour or more, the way back (exit 1, its two lines). The controls: a
        quiet day (no Scaling up, no start failure): not measured yet (exit 0); start failures, then a runner started
        and removed at a scale-down: the fix works (exit 0)."""
        for name, log, want, rc in (
                ('under an hour', new_start() + start_failures(610, 610 + 1800), r'^ANSWER look again in an hour: ', 1),
                ('over an hour', new_start() + start_failures(610, 610 + 3700), r'^ANSWER the way back: ', 1),
                ('control: a quiet day', new_start(), r'^ANSWER not measured yet: ', 0),
                ('control: then a runner starts', new_start() + start_failures(610, 640) + scaled_down(700, A, IID[2]),
                 r'^ANSWER the fix works: ', 0)):
            with self.subTest(name):
                r = check(self, home(self, log))
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, want)
                if 'way back' in want:
                    self.assertIn('start', a)
                    self.assertEqual(after_answer(self, r), way_back_lines())

    def test_a_rotated_log(self):
        """opus2 F5: runner.log rotated since the start (runscaler keeps one older file, runner.log.1): the check reads
        runner.log.1's records since the start too (its scale-down removal: the fix works, and the record count names
        runner.log.1). Rotated twice (runner.log.1 itself begins after the start): it says from when its records and
        counts run (the first record it has) and that runner.log rotated. The control: an unrotated log: no such
        line."""
        one = old_drain() + new_start() + scaled_down(610, C, IID[3])
        later = a_job(3000, A, IID[2])
        for name, log, rot, want, rc, note in (
                ('rotated once', later, one, r'^ANSWER the fix works: ', 0, False),
                ('rotated twice', a_job(9000, B, IID[3]), later, r'^ANSWER not measured yet: ', 0, True),
                ('control: not rotated', one + later, None, r'^ANSWER the fix works: ', 0, False)):
            with self.subTest(name):
                r = check(self, home(self, log, rotated=rot))
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                self.assertRegex(answer(self, r), want)
                if rot is not None and not note:
                    self.assertRegex(r.stdout, r'\n  removed at a scale-down or a drain: 1 runner\(s\)')
                    self.assertRegex(r.stdout, r'records since that start \([0-9]+ of them in runner\.log\.1')
                lines = [l for l in r.stdout.splitlines() if l.startswith('the log begins at ')]
                if note:
                    self.assertEqual(len(lines), 1, r.stdout)
                    self.assertIn(at(3000), lines[0])
                    self.assertIn('rotated', lines[0])
                else:
                    self.assertEqual(lines, [])

    def test_starting(self):
        """opus2 F6: the unit started seconds ago and its process does not run a runscaler yet (runner-start, bash, runs
        its checks before its exec): a binary 03 does not name, or one the check cannot read: "starting", run the check
        again in a minute (exit 1). The controls: the same unknown binary after a day, and the way-back runscaler
        seconds after its start: v0.12.0 is not running."""
        log = new_start()
        for name, exe, age, want in (('an unknown binary, 5 s', 'other', 5, r'^ANSWER starting: '),
                                     ('no binary to read, 5 s', 'none', 5, r'^ANSWER starting: '),
                                     ('control: an unknown binary, a day', 'other', DAY,
                                      r'^ANSWER v0\.12\.0 is not running: '),
                                     ('control: v0.9.5, 5 s', 'wayback', 5, r'^ANSWER v0\.12\.0 is not running: ')):
            with self.subTest(name):
                r = check(self, home(self, log, exe, age=age))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, want)
                if 'starting' in want:
                    self.assertIn('in a minute', a)

    def test_the_order_of_the_answers(self):
        """One ANSWER per run, the first that holds (the README's order): v0.12.0 is not running before does not serve;
        does not serve before no log; the way back before a job may have been cut (whose records still print); a job may
        have been cut before look again in an hour."""
        cut = removed(900, C, IID[3], 'scaled-down') + unknown_job(930, C)
        down = new_start() + scaling_up(610) + started(613, C, IID[3]) + started(614, A, IID[2])
        stuck, _ = retries(1000, A, 1000 + 3700)
        for name, log, exe, curl, want in (
                ('not running, not serving', new_start(), 'other', dict(healthz=None),
                 r'^ANSWER v0\.12\.0 is not running: '),
                ('not serving, no log', None, 'pinned', dict(healthz=None), r'^ANSWER does not serve: '),
                ('the way back, a cut', down + cut + stuck, 'pinned', {}, r'^ANSWER the way back: '),
                ('a cut, an open error', down + cut + dereg(1000, A, '5s'), 'pinned', {},
                 r'^ANSWER a job may have been cut: ')):
            with self.subTest(name):
                p = home(self, log, exe)
                p.curl.update(curl)
                r = check(self, p)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertRegex(answer(self, r), want)
                if cut in (log or ''):
                    self.assertIn('\n  a job may have been cut: %s UTC, runner %s' % (at(930), C), r.stdout)

    # ---- fix round 2 (review r1 of H2c: opus F1, opus2 F2; the H2 plan's r5 AMENDMENT)

    def test_start_failures_with_no_runner_started_after_them(self):
        """opus F1 (r5, NO RUNNER STARTS): a start failure is OPEN while no `Runner started` follows it, and a runner
        started BEFORE the failures does not close them. Runner C started and removed at a scale-down in the first
        hour, then every start fails (each 6 s while a job waits) from 4001 s: over an hour of open ones, the way back
        (exit 1, its two lines), from the first open one; under an hour, look again in an hour (exit 1). With failures
        before a start too (closed by it), the span is the open ones': under an hour, look again. Control 1: a runner
        started after the last of them: the fix works (exit 0). (test_no_runner_starts keeps its controls: no earlier
        start, the way back; then a runner starts, the fix works.) 8b917c7 counted every `Runner started` since the
        start, so one before the failures turned the rule off: "the fix works … Nothing to do" (exit 0)."""
        first = new_start() + scaled_down(610, C, IID[3])
        closed = new_start() + start_failures(610, 640) + scaled_down(700, C, IID[3])
        for name, log, want, rc in (
                ('a runner started before them, over an hour', first + start_failures(4000, 7700),
                 r'^ANSWER the way back: ', 1),
                ('a runner started before them, under an hour', first + start_failures(4000, 5800),
                 r'^ANSWER look again in an hour: ', 1),
                ('closed ones before a start, open ones under an hour', closed + start_failures(4000, 5800),
                 r'^ANSWER look again in an hour: ', 1),
                ('control 1: a runner started after the last of them', first + start_failures(4000, 7700)
                 + scaled_down(7720, A, IID[2]), r'^ANSWER the fix works: ', 0)):
            with self.subTest(name):
                r = check(self, home(self, log, age=7800))
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, want)
                if rc:
                    self.assertIn('start failure', a)
                    self.assertIn(at(4001), a, 'from the first OPEN one')
                    self.assertNotIn(at(611), a)
                if 'way back' in want:
                    self.assertEqual(after_answer(self, r), way_back_lines())
                else:
                    self.assertNotIn(way_back_lines()[1], r.stdout.splitlines())

    def test_a_restart_after_the_step(self):
        """opus2 F2 (r5, A RESTART AFTER THE STEP): the step installed v0.12.0 (~/bin/runner's mtime M, 6 h 10 min
        before the start S) and its process ran from 6 h before S; then runscaler restarted at S (a person's up of a
        runner release, a reboot), and the process since removed runner A at a scale-down. The check counts from S and
        says that runscaler restarted at S after the step installed v0.12.0 at M, and that the records from M to S are
        not counted; it reads that span for a removal at a scale-down or a drain that names a `jobId=`: the earlier
        process's removal of runner C while it held a job reads "a job may have been cut" (exit 1, the way back's
        lines), naming C, the job and its time, as one after S does; so does its drain's in S's own second (the new
        process removes no runner in its first second). With no such removal: the restart line, the fix works. The
        controls: the same records before M in v0.9.5's form (the process before the step), and v0.9.5's records
        between M and S (the step's own restart): the fix works (exit 0), no restart line; v0.12.0's records before M
        (an earlier v0.12.0, before a way back and the step again): the same; the cut after S, nothing between M and S:
        still named, no restart line; ~/bin/runner not v0.12.0 (its mtime is no install of v0.12.0: a way back cut
        after its rename of the binary, before its restart), the first input: the fix works, no restart line. 8b917c7
        read nothing before S: "the fix works" (exit 0)."""
        t0 = -6 * 3600
        after = new_start() + scaled_down(120, B, IID[0])
        cut_after = new_start() + scaling_up(600) + started(603, C, IID[3]) \
            + removed(900, C, IID[3], 'scaled-down', job=True)
        for name, log, installed, want, rc, cut, note in (
                ('restarted after the step, a cut before the restart', a_process(t0) + after, t0 - 600,
                 r'^ANSWER a job may have been cut: ', 1, (t0 + 900, C), True),
                ('restarted after the step, its drain in the start\'s second names a job',
                 a_process(t0, job=False, drain=0) + after, t0 - 600, r'^ANSWER a job may have been cut: ', 1, (0, A),
                 True),
                ('restarted after the step, no cut', a_process(t0, job=False) + after, t0 - 600,
                 r'^ANSWER the fix works: ', 0, None, True),
                ('control: v0.9.5\'s records before M', a_process(t0, v095) + after, -600, r'^ANSWER the fix works: ',
                 0, None, False),
                ('control: v0.9.5\'s records between M and S', a_process(t0, v095, drain=0) + after, t0 - 600,
                 r'^ANSWER the fix works: ', 0, None, False),
                ('control: v0.12.0\'s records before M', a_process(t0) + after, -600, r'^ANSWER the fix works: ', 0,
                 None, False),
                ('control: the cut after S', cut_after, -600, r'^ANSWER a job may have been cut: ', 1, (900, C),
                 False),
                ('control: ~/bin/runner is not v0.12.0', a_process(t0) + after, t0 - 600, r'^ANSWER the fix works: ', 0,
                 None, False)):
            with self.subTest(name):
                p = home(self, log, installed=installed)
                if 'not v0.12.0' in name:   # other bytes, the same mtime
                    rb = os.path.join(p.HOME, 'bin', 'runner')
                    with open(rb, 'ab') as f:
                        f.write(b'# not v0.12.0\n')
                    os.utime(rb, (START + installed, START + installed))
                r = check(self, p)
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                a = answer(self, r)
                self.assertRegex(a, want)
                lines = [l for l in r.stdout.splitlines() if l.startswith('runscaler restarted at ')]
                if note:
                    self.assertEqual(len(lines), 1, r.stdout)
                    self.assertTrue(lines[0].startswith('runscaler restarted at %s UTC' % at(0)), lines[0])
                    self.assertIn('installed v0.12.0 at %s UTC' % at(installed), lines[0])
                    self.assertIn('not counted', lines[0])
                else:
                    self.assertEqual(lines, [], r.stdout)
                if cut:
                    self.assertIn(cut[1], a)
                    self.assertIn(at(cut[0]), a)
                    self.assertIn(JOBID, a)
                    self.assertIn('lost communication', a)
                    self.assertEqual(after_answer(self, r), way_back_lines())
                    if note:
                        self.assertIn('\n  a job may have been cut before that restart: %s UTC, runner %s, job %s: '
                                      % (at(cut[0]), cut[1], JOBID), r.stdout)
                else:
                    self.assertNotIn(way_back_lines()[1], r.stdout.splitlines())


if __name__ == '__main__':
    unittest.main()
