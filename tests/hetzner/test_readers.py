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
The /healthz cell runs pool-ready in a container (support.Sandbox: the host config and the curl substitute); the others
run anywhere with bash 5, awk and jq.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest

from tests.hetzner.support import REPO, Sandbox, bash5, needs_container

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


if __name__ == '__main__':
    unittest.main()
