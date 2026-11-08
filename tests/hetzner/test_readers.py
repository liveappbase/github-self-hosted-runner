"""The Linux host's readers of runscaler's output, on runscaler v0.12.0's shapes that change nothing (runscaler 0.12
bump, slice H1; the census's A2, A6 and A8). Each cell gives a reader a v0.12.0-form input and its v0.9.5 twin, and
pins that the reader answers both alike: each is a GUARD, green before the bump too (no reader changed for it).

- /healthz (A2): v0.12.0 adds a `runtime` object per set, and a set whose runners fail to start while jobs wait reads
  `ready: false` with `last_error: "runner startup failed: <reason>"` (internal/health/health.go). bin/pool-ready says
  NOT READY of such a set, and core/idle.jq (as pool-image.sh's idle pair calls it) says not idle and why; the control,
  the same read with the set ready and every count 0, is READY and idle.
- The log's WARN line (A6): v0.12.0's level column is five wide (`WARN  linux-a: Job started for unknown runner
  (already removed?) runnerName=…`, two spaces). pool-image.sh's restart-cut scan (A JOB A RESTART CUT) finds the
  runner name in it as in its v0.9.5 twin (`WARN linux-a: …`), and neither finds a line older than the install.
- runner validate's output (A8): the same check lines (`  ✗ scaleset[0] "…" GitHub API: …`, `All checks passed.`), and
  the client's records now start `INFO  ` and `ERROR `: bin/validate-class gives each output the class of its v0.9.5
  twin (`INFO `, `ERRO `).
- THE UPDATER'S PASS (runscaler 0.12 bump, slice H2c: the Hetzner half of the Studio's C2, core/lib/logfmt.jq reading
  both level columns): RS_USER's `runner-updater pass` (linux-docker/bin/runner-updater, the core as it ships) reads
  runner.log through runner-facts.sh's log_pos and the core state's carry, on a v0.12.0-form log and on its v0.9.5
  twin (the same records in the four-letter column), and gives the same R1 and KEEP verdicts, at the same times, from
  the same records read: the five-wide level column of a set's record (`INFO  linux-ci-main: Runner removed …`), an
  ERROR record (a counted start failure), a global record (no set: the disk guard's WARN, the one record that settles
  the failures), and a record cut where a pass's position falls (held as the carry, then read whole once the rest is
  written). Unlike the cells above, this one is red before C2: on b2eb739's logfmt.jq (the pre-C2 reader) the v0.12.0
  log gives no R1 and no KEEP accept, while its v0.9.5 twin gives both (the control). The two rigs run on ONE fake
  clock, so the compare does not depend on when each is made (review r1 of H2c; CI run 42511818282 was red when a
  minute of the real clock fell between them): a third cell makes the second rig a minute later.
The /healthz cell runs pool-ready in a container (support.Sandbox: the host config and the curl substitute), the pass
cell the real scripts in one (support.Pool, a fake clock); the others run anywhere with bash 5, awk and jq.
"""
import calendar
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from tests.hetzner.support import REPO, Sandbox, bash5, needs_container
from tests.hetzner.test_updater import FAM, Rig, candidate

PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
VCLASS = os.path.join(REPO, 'linux-docker', 'bin', 'validate-class')
CORE = os.path.join(REPO, 'core')
MAIN, SMALL = 'linux-ci-main', 'linux-ci-small'      # host.conf.example's set names
REASON = 'provider_start_failed'


def a_set(name, **over):
    """One set of a v0.12.0 /healthz: ready, no runner, no job, and its `runtime` object (start counts, no failure)."""
    s = {'name': name, 'ready': True, 'last_connected': '2026-11-06T19:58:02Z', 'idle': 0, 'busy': 0,
         'metrics': {'jobs_started': 12, 'jobs_completed': 12, 'desired_runners': 0},
         'runtime': {'start_attempts': 12, 'start_failures': 3, 'consecutive_start_failures': 0,
                     'last_start_attempt': '2026-11-06T19:58:02Z', 'last_successful_start': '2026-11-06T19:58:02Z',
                     'waiting_for_capacity': False, 'draining': False, 'degraded': False}}
    s.update(over)
    return s


def healthz(main):
    """A v0.12.0 /healthz of host.conf.example's two sets, MAIN's fields replaced by main."""
    sets = [a_set(MAIN, **main), a_set(SMALL)]
    return {'status': 'ok' if all(s['ready'] for s in sets) else 'degraded', 'version': '0.12.0', 'uptime': '2h1m4s',
            'scale_sets': sets, 'disk': [{'filesystem': '/home/ci-run/.local/share/docker', 'free_percent': 81.5,
                                          'free_bytes': 131000000000, 'total_bytes': 160700000000}],
            'capacity': {'limit': 4, 'in_use': 0}}


# MAIN's runners fail to start while a job waits: runtime.go's Degraded (consecutive failures, idle+busy < target),
# so ready is false and last_error names the reason (health.go)
DEGRADED = healthz(dict(ready=False, last_error='runner startup failed: ' + REASON,
                        metrics={'jobs_started': 12, 'jobs_completed': 12, 'desired_runners': 1, 'assigned_jobs': 1},
                        runtime=dict(a_set(MAIN)['runtime'], start_attempts=15, start_failures=6,
                                     consecutive_start_failures=3, last_start_attempt='2026-11-06T20:04:01Z',
                                     failure_reason=REASON, degraded=True)))
QUIET = healthz({})         # the control: the same shape, MAIN ready and every count 0


@needs_container
class PoolReady(unittest.TestCase):
    def ready(self, read):
        sb = Sandbox(self)
        sb.curl['healthz'] = read
        sb.files()
        return subprocess.run(['bash', os.path.join(sb.build, 'bin', 'pool-ready'), MAIN, SMALL], env=sb.env(),
                              cwd=sb.home, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)

    def test_a_degraded_set_is_not_ready(self):
        r = self.ready(DEGRADED)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            "%s: ready=False idle=0 busy=0 last_error='runner startup failed: %s'" % (MAIN, REASON),
            "%s: ready=True idle=0 busy=0 last_error=''" % SMALL,
            'NOT READY'])

    def test_control_the_same_read_with_the_set_ready_is_ready(self):
        r = self.ready(QUIET)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines()[-1], 'READY')


class Idle(unittest.TestCase):
    """core/idle.jq as pool-image.sh's uidle calls it: no state (an empty file), the config's two sets, two reads."""

    def idle(self, read):
        jq = os.environ.get('JQ') or shutil.which('jq')
        if not jq:
            self.fail('no jq: these cells need the jq the host runs (core/TESTED_JQ)')
        d = tempfile.mkdtemp(prefix='readers-')
        self.addCleanup(shutil.rmtree, d, True)
        h, f, s = (os.path.join(d, n) for n in ('healthz.json', 'facts.json', 'state.json'))
        with open(h, 'w') as o:
            o.write(json.dumps(read) + '\n' + json.dumps(read) + '\n')
        with open(f, 'w') as o:
            o.write(json.dumps({'format': 1, 'sets': [MAIN, SMALL]}))
        open(s, 'w').close()
        r = subprocess.run([jq, '-n', '-L', os.path.join(CORE, 'lib'), '-f', os.path.join(CORE, 'idle.jq'),
                            '--slurpfile', 'state', s, '--slurpfile', 'facts', f, '--slurpfile', 'healthz', h,
                            '--arg', 'now', str(int(time.time()))], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_a_degraded_set_is_not_idle_and_names_why(self):
        out = self.idle(DEGRADED)
        self.assertEqual(out['verdict'], 'not-idle', out)
        self.assertEqual(out['lines'], ['%s: assigned 1, desired 1, not ready' % MAIN], out)

    def test_control_the_same_read_with_the_set_ready_and_every_count_0_is_idle(self):
        out = self.idle(QUIET)
        self.assertEqual(out['verdict'], 'idle', out)


def records(text, width):
    """text's record headers in a release's level column: {INFO} {WARN} {ERROR} -> v0.12.0's five-wide column (width
    5: `INFO `, `WARN `, `ERROR`) or v0.9.5's four (width 4: `INFO`, `WARN`, `ERRO`); one space follows either."""
    cols = {5: {'INFO': 'INFO ', 'WARN': 'WARN ', 'ERROR': 'ERROR'}, 4: {'INFO': 'INFO', 'WARN': 'WARN', 'ERROR': 'ERRO'}}
    return re.sub(r'\{(INFO|WARN|ERROR)\}', lambda m: cols[width][m.group(1)], text)


class RestartCut(unittest.TestCase):
    """pool-image.sh's A JOB A RESTART CUT: its `cut=$(awk …)` line, as it ships, run on a runner.log with the
    install's time `inst`. The runner GitHub had given a job before the restart cut it is named once, with its log
    time; a line from before the install is not."""
    LOG = ('2026-11-06 20:00:00 {INFO} Starting scale sets count=2\n'
           '2026-11-06 20:03:59 {WARN} %(m)s: Job started for unknown runner (already removed?) runnerName=%(m)s-old11\n'
           '2026-11-06 20:04:01 {INFO} %(m)s: Runner removed name=%(m)s-x7k2p reason=drain jobId= result=\n'
           '2026-11-06 20:05:12 {WARN} %(m)s: Job started for unknown runner (already removed?) runnerName=%(m)s-ab12c\n'
           '2026-11-06 20:05:13 {ERROR} %(m)s: Failed to start runner, will retry error="no such image"\n') % {'m': MAIN}

    def cut(self, log):
        with open(PIMG) as f:
            lines = [l for l in f.read().splitlines() if l.startswith('cut=$(awk ')]
        self.assertEqual(len(lines), 1, 'pool-image.sh has one restart-cut scan line')
        d = tempfile.mkdtemp(prefix='readers-')
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'runner.log'), 'w') as f:
            f.write(log)
        r = subprocess.run(['bash', '-c', 'R=$1 inst=$2\n' + lines[0] + '\nprintf "%s\\n" "$cut"', 'cut', d,
                            '2026-11-06 20:04:00'], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_the_v0_12_0_warn_line_names_the_runner_as_its_v0_9_5_twin(self):
        want = '2026-11-06 20:05:12 %s-ab12c\n' % MAIN
        self.assertEqual(self.cut(records(self.LOG, 4)), want)     # the v0.9.5 twin: the premise
        self.assertEqual(self.cut(records(self.LOG, 5)), want)


class Validate(unittest.TestCase):
    """bin/validate-class (the Linux copy) on v0.12.0 outputs of `runner validate` and on each one's v0.9.5 twin (the
    same output, the client's records in the four-wide level column)."""
    CHECKS = ('  ✓ scaleset[0] "%s" — provider=docker url=https://github.com/example-org max=3 min=0\n'
              '  ✓ scaleset[1] "%s" — provider=docker url=https://github.com/example-org max=1 min=0\n'
              '  ✓ Docker is reachable at /home/ci-run/run/docker.sock\n') % (MAIN, SMALL)
    TOKEN = ('2026-11-06 20:11:39 {INFO} refreshing token githubConfigUrl=https://github.com/example-org\n'
             '2026-11-06 20:11:39 {INFO} getting runner registration token registrationTokenURL='
             'https://api.github.com/orgs/example-org/actions/runners/registration-token\n')
    FAILED = ('2026-11-06 20:11:40 {ERROR} request failed error="Post \\"https://api.github.com/orgs/example-org/actions/'
              'runners/registration-token\\": dial tcp: lookup api.github.com: no such host" method=POST '
              'url=https://api.github.com/orgs/example-org/actions/runners/registration-token\n')
    API = ('  ✗ scaleset[0] "%s" GitHub API: failed to create new actions service request: failed to issue update '
           'token if needed: failed to get runner registration token on refresh: context deadline exceeded\n'
           '    Check that your token has the correct scopes (admin:org or repo)\n') % MAIN
    COBRA = ('Error: validation failed\nUsage:\n  runner validate [flags]\n\nExamples:\n  runner validate --config '
             'config.toml\n\nFlags:\n  -h, --help   help for validate\n\nGlobal Flags:\n      --config string   Path to '
             'config file (TOML)\n\nvalidation failed\n')
    OUTPUTS = (
        ('a GitHub API failure', 1, CHECKS + TOKEN + FAILED * 3 + API + COBRA, 'API-ONLY'),
        ('a record that quotes a check line', 1,
         CHECKS + TOKEN + '2026-11-06 20:11:40 {ERROR} request failed error="  ✗ global config: x"\n' + API + COBRA,
         'API-ONLY'),
        ('all checks passed', 0, CHECKS + TOKEN + ''.join('  ✓ scaleset[%d] "%s" GitHub API is reachable\n' % (i, n)
                                                          for i, n in enumerate((MAIN, SMALL))) + '\nAll checks passed.\n',
         'PASS'),
    )

    def classify(self, rc, text):
        b = bash5()
        if not b:
            self.fail('no bash 5 on PATH: linux-docker/ runs under the host\'s bash 5')
        d = tempfile.mkdtemp(prefix='readers-')
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, 'out.txt')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        r = subprocess.run([b, VCLASS, str(rc), p], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           env={'PATH': '/usr/bin:/bin'}, timeout=60)
        self.assertEqual((r.returncode, r.stderr), (0, ''), r.stdout)
        return r.stdout.strip()

    def test_each_v0_12_0_output_classes_as_its_v0_9_5_twin(self):
        for why, rc, text, want in self.OUTPUTS:
            with self.subTest(why):
                self.assertNotRegex(records(text, 5), r'\{(INFO|WARN|ERROR)\}')
                self.assertEqual(self.classify(rc, records(text, 4)), want, 'the v0.9.5 twin: the premise')
                self.assertEqual(self.classify(rc, records(text, 5)), want)


# THE UPDATER'S PASS: runscaler's records, each one both releases write, field for field; only the level column
# differs (charm log v2.0.0's four letters in v0.9.5, v2.0.1's five-wide column in v0.12.0: records()). Their source,
# runscaler v0.12.0's (v0.9.5's):
# - a start failure: internal/controller/controller.go:254 (:248) `Failed to start runner, will retry` error=, the docker
#   provider's internal/provider/docker.go:162 (both) around Docker's own text (test_updater.failed's);
# - a job's removal: logRemoved, controller.go:717-734 (:656-673): name instanceID reason jobId repo workflowRunId job
#   result (tests/core/fixtures/hz-cut.log's line 42, its set renamed);
# - the disk guard's WARN: internal/diskguard/guard.go:215 (both), warnShortfall: path free_bytes target_bytes
#   shortfall_bytes, by the process logger, so with no set prefix (cmd/runner/main.go's runManager);
# - a scale-up: controller.go:236 (:230) currentCount desiredCount.
ERR = 'failed to create runner container: Error response from daemon: No such image: example-runner'
CUT_AT = 'error="failed to create runner con'   # where a pass's position cuts the third failure (the rest: later)


def stamp(t):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(t))


def start_failed(t):
    return '%s {ERROR} %s: Failed to start runner, will retry error="%s"\n' % (stamp(t), MAIN, ERR)


def job_done(t, s):
    return ('%s {INFO} %s: Runner removed name=runner-1d1af85d instanceID=5869c40ebfde32e17ad9799d5b287c5170d517260be9'
            '646c39fb3ffa06c3d300 reason=job-completed jobId=3247e383-0f16-cfaf-b270-199a67527096 repo=example-org/example'
            ' workflowRunId=82593050714 job="build (9150)" result=succeeded\n' % (stamp(t), s))


def guard_warn(t):
    return ('%s {WARN} Disk guard: reached max-tier without meeting target-free path=/home/ci-run/.local/share/docker '
            'free_bytes=30000000000 target_bytes=32140000000 shortfall_bytes=2140000000\n' % stamp(t))


def scale_up(t):
    return '%s {INFO} %s: Scaling up runner currentCount=0 desiredCount=1\n' % (stamp(t), MAIN)


def read_as(x, t0):
    """X (r1's family evidence, KEEP's answer) with every log time and every time of the passes' clock made relative
    to t0 (a second: x - t0; a log time text: ('log', its second - t0)): what the pass READ and when, comparable between
    two rigs that run on one clock (twins)."""
    if isinstance(x, dict):
        return {k: read_as(v, t0) for k, v in x.items()}
    if isinstance(x, list):
        return [read_as(v, t0) for v in x]
    if isinstance(x, str) and re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d', x):
        return ('log', calendar.timegm(time.strptime(x, '%Y-%m-%d %H:%M:%S')) - t0)
    if isinstance(x, int) and not isinstance(x, bool) and abs(x - t0) < 10 ** 6:
        return x - t0
    return x


@needs_container
class UpdaterPass(unittest.TestCase):
    """RS_USER's pass over runner.log in one release's level column (WIDTH 5: v0.12.0; 4: its v0.9.5 twin), on
    test_updater's Rig (production on the old image, a fake clock, ON) with a candidate on config.toml's own lines set
    by hand (test_updater.Would's: the first pass opens its evidence window; no switch kept a config.toml.prev, so R1's
    rollback holds STOP ROLLBACK FAILED and starts no window). After that pass: two start failures (ERROR, the main
    set), a job that succeeded (INFO, on SET), and the first part of a third failure, up to CUT_AT (pass B: its
    position cuts that record); then the rest of it, the disk guard's WARN (global) 160 s after the first failure, and
    a scale-up a second later (the record a pass always holds) (pass C, at the clock C_AT sets). Returns, per pass: R1's
    and KEEP's family answers and r1's state of the family (read_as), and the carry. The two rigs of a cell run on ONE
    clock (twins: review r1 of H2c, opus F5 and opus2 F1), so no value depends on when each rig is made."""

    def passes(self, g, t, width, s, c_at=None):
        """The three passes on rig G (its fake clock at the cell's one epoch), the log's records from T."""
        g.put({'format': 1, 'on': True, 'families': {FAM: {'candidate': candidate(g.p.clock() - 60)}}})
        out = []

        def one():
            r = g.ok('pass')
            r1, keep = g.out('r1'), g.out('keep')
            out.append({'r1': read_as(r1['families'][FAM], t), 'keep': read_as(keep['families'][FAM], t),
                        'state': read_as(r1['state']['families'][FAM], t), 'carry': r1['state']['carry'],
                        'stdout': r.stdout})
        one()
        third = records(start_failed(t + 20), width)
        head = third[:third.index(CUT_AT) + len(CUT_AT)]
        g.append(records(start_failed(t) + start_failed(t + 10) + job_done(t + 15, s), width) + head)
        one()
        g.append(third[len(head):] + records(guard_warn(t + 160) + scale_up(t + 161), width))
        if c_at:
            g.p.clock(now=c_at(g))
        one()
        return out, head, records(scale_up(t + 161), width)

    def twins(self, s, check, c_at=None):
        """passes() in v0.9.5's column (the control), then in v0.12.0's, each a subtest on a rig of its own: CHECK(its
        passes) asserts its own verdicts and reading, and the v0.12.0 one is read as its twin was, pass for pass, the
        passes' clock too. Both rigs run on ONE fake-clock epoch, set when the cell starts: ten minutes past the real
        clock, so past every real install of either rig (as fake_clock's own ahead; no pass here starts a process), and
        the log's records from 90 s after it (as each rig's own clock had them). Each rig's clock had started at the
        real clock when it was made, and the core prints the clock to the minute in its reason texts, so the compare
        was red whenever a minute of the real clock fell between the two rigs (CI run 42511818282: review r1 of H2c,
        opus F5, opus2 F1). (The rigs are made one after the other: a Pool's home is the one HOME of the container.)"""
        epoch = int(time.time()) + 600
        seen = {}
        for width, name in ((4, 'v0.9.5'), (5, 'v0.12.0')):
            with self.subTest(column=name):
                g = Rig(self, on=True)
                g.p.clock(now=epoch)
                out, head, held = self.passes(g, epoch + 90, width, s, c_at)
                seen[width] = out
                check(*out)
                self.assertEqual([p['carry'] for p in out[1:]], [head, held],
                                 'pass B holds the cut record from its header, pass C the last record')
                if width == 5 and 4 in seen:
                    self.assertEqual([{k: p[k] for k in ('r1', 'keep', 'state')} for p in out],
                                     [{k: p[k] for k in ('r1', 'keep', 'state')} for p in seen[4]],
                                     'the v0.12.0 log is read as its v0.9.5 twin')

    def failures(self, p):
        return [(f['s'], f['c'], f['x'], f['settled']) for f in p['state']['sets'].get(MAIN, {}).get('fails', [])]

    def test_r1_s_rollback_from_both_columns(self):
        """Three counted failures on the main set, no proof of life on it between them (the job ran on the small
        set): pass B reads two (the third is held; R1 may still come: pending), pass C the third WHOLE (its error text
        whole: the cut fell inside it) and the global WARN, 140 s past the third, which settles all three: R1's
        rollback on the main set, KEEP held, the pass's rollback line; the success counted, a proof of the small set."""
        def check(a, b, c):
            self.assertEqual([(p['r1']['verdict'], p['keep']['verdict']) for p in (a, b, c)],
                             [('none', 'observe'), ('none', 'observe'), ('rollback', 'held')])
            self.assertEqual(self.failures(b), [(0, False, ERR, False), (10, False, ERR, False)])
            self.assertEqual((b['state']['succeeded'], b['state']['sets'][SMALL]['proofs']), (1, [15]))
            self.assertEqual(b['r1']['pending']['set'], MAIN)
            self.assertEqual(self.failures(c), [(0, False, ERR, True), (10, False, ERR, True), (20, False, ERR, True)])
            self.assertEqual((c['r1']['set'], len(c['r1']['failures']), c['state']['newest']), (MAIN, 3, 160),
                             'the global WARN was read: it is the newest record read')
            self.assertIn("runner-updater: pass: R1's rollback is due for hz-docker", c['stdout'])
        self.twins(SMALL, check)

    def test_keep_s_accept_from_both_columns(self):
        """The job that succeeded ran on the main set, between the second and the third failure (a proof of life:
        no run of three, no R1); pass C, 72 h after the window opened: KEEP accepts (one success), and the main set
        keeps the proof and the third failure (read whole, settled by the global WARN); the two before the proof are
        judged and pruned."""
        def c_at(g):
            return g.out('r1')['families'][FAM]['since'] + 72 * 3600

        def check(a, b, c):
            self.assertEqual([(p['r1']['verdict'], p['keep']['verdict']) for p in (a, b, c)],
                             [('none', 'observe'), ('none', 'observe'), ('none', 'accept')])
            self.assertEqual((self.failures(b), b['state']['sets'][MAIN]['proofs']),
                             ([(0, False, ERR, False), (10, False, ERR, False)], [15]))
            self.assertEqual((self.failures(c), c['state']['sets'][MAIN]['proofs']), ([(20, False, ERR, True)], [15]))
            self.assertEqual((c['keep']['succeeded'], c['state']['newest']), (1, 160))
            self.assertIn('runner-updater: pass: would accept hz-docker', c['stdout'])
        self.twins(MAIN, check, c_at)

    def test_the_compare_holds_when_the_second_rig_is_made_a_minute_later(self):
        """Review r1 of H2c (opus F5, opus2 F1; CI run 42511818282): the twins' compare does not depend on when each
        rig is made. The v0.12.0 twin's rig made a minute later: its fake clock moved on by 60 s right after it is made
        (what a later minute of the real clock did to a clock that started at it); the R1 cell's passes (no verdict
        asserted here: the compare is the claim) read the v0.12.0 log as its twin, reason texts and clock alike. Red on
        8b917c7, whose rigs each ran on their own clock."""
        made, real = [], Rig

        def later(test, **kw):
            g = real(test, **kw)
            made.append(g)
            if len(made) == 2:
                g.p.clock(plus=60)
            return g
        with mock.patch.object(sys.modules[__name__], 'Rig', later):
            self.twins(SMALL, lambda *a: None)
        self.assertEqual(len(made), 2)

if __name__ == '__main__':
    unittest.main()
