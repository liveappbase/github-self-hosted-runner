"""watchdog/run + watchdog/watchdog.jq — the weekly runner watchdog (PLAN D8), against a substitute gh. Pinned: the rules
STALE (a label's newest job on main runs a version older than a release out for more than 7 days), FAILING (the
newest version differs from 8 days ago, and the last 7 days' failure share is at least twice the 7 days before, with at
least 3 failures) and COULD-NOT-RUN (an untested jq, a gh call that failed twice, a program error: ONE line); one
topic per (rule, newest release), `clear` for the topics of the releases before it; NOT MEASURED only inside another
ask's text; the output is only `open TOPIC TEXT` and `clear TOPIC` lines; gh is only read, every call with
--allow-escape-sequences when `gh api --help` lists it (read once a run: a new gh refuses a log with escape sequences
without it, an old one rejects the flag) and never otherwise, and a failed call is tried once more after `sleep 3`
(issue #3). fixtures/releases.json is the real actions/runner release list (2026-11-01, a prerelease among them);
fixtures/job-log-head.txt the head of a real job log (its runner group renamed); ESCAPED_HEAD is synthetic. Every
trigger has a control that comes out the other way."""
import calendar
import json
import os
import re
import subprocess
import sys
import time
import unittest

from tests.watchdog.wdrun import FLAG, REPO, Sandbox, fixture, jq_version

REPO_ARG = 'example-org/example'
HOSTS = ['--hz', 'ssh scaler@hz.example', '--studio', 'ssh ci@studio.example']
FAMS = ['--family', 'hz-docker=hz:linux-a,linux-b', '--family', 'mac-golden=studio:mac-a']
DAY = 86400
NOW = calendar.timegm((2026, 11, 8, 9, 0, 0))            # 2.338.2 has been out since 2026-10-26 14:45 UTC
TOPIC = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')


def iso(epoch):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(epoch))


class World:
    """Jobs on main: one run per job. job(label, days_ago, ...) adds one; install() answers every gh call."""

    def __init__(self, now=NOW, releases=None):
        """releases: [(version, days_ago)], newest first, all final (default: the real list, newest 2.338.2). head:
        the log head of every job, its version line replaced by the job's (default: fixtures/job-log-head.txt)."""
        self.now, self.jobs, self.next_id, self.releases = now, [], 1000, releases
        self.head = fixture('job-log-head.txt')

    def job(self, label, days_ago, conclusion='success', version='2.338.2'):
        self.next_id += 1
        start = self.now - int(days_ago * DAY)
        self.jobs.append({'id': self.next_id, 'run_id': 50000 + self.next_id, 'head_branch': 'main', 'name': 'build',
                          'status': 'completed', 'conclusion': conclusion, 'started_at': iso(start),
                          'completed_at': iso(start + 300), 'labels': ['self-hosted', label],
                          'runner_name': 'runner-%08x' % self.next_id, 'runner_group_name': 'example-group',
                          '_version': version})
        return self

    def daily(self, label, version='2.338.2'):
        for d in range(0, 14, 2):                                   # a job every second day
            self.job(label, d + 0.5, 'success', version)
        return self

    def install(self, sb):
        if self.releases is None:
            sb.answer('repos/actions/runner/releases/latest', 'v2.338.2\n', jq_expr='.tag_name')
            sb.answer('repos/actions/runner/releases?per_page=30', fixture('releases.json'))
        else:
            sb.answer('repos/actions/runner/releases/latest', 'v%s\n' % self.releases[0][0], jq_expr='.tag_name')
            sb.answer('repos/actions/runner/releases?per_page=30',
                      [{'tag_name': 'v' + v, 'name': 'v' + v, 'draft': False, 'prerelease': False,
                        'published_at': iso(self.now - int(days * DAY))} for v, days in self.releases])
        since = time.strftime('%Y-%m-%d', time.gmtime(self.now - 14 * DAY))
        runs = [{'id': j['run_id'], 'head_branch': 'main'} for j in self.jobs]
        sb.answer('repos/%s/actions/runs?branch=main&created=>=%s&per_page=100' % (REPO_ARG, since),
                  {'total_count': len(runs), 'workflow_runs': runs})
        head = self.head
        assert head.count("Current runner version: '2.338.2'") == 1 and head.count("'2.338.2'") == 1, \
            'a log head names 2.338.2 once, in its version line (each job puts its own version there)'
        for j in self.jobs:
            api = {k: v for k, v in j.items() if not k.startswith('_')}
            sb.answer('repos/%s/actions/runs/%d/jobs?per_page=100' % (REPO_ARG, j['run_id']),
                      {'total_count': 1, 'jobs': [api]})
            if j['_version'] is None:      # a head with no version line, and another version-like text in it
                log = head.replace("Current runner version: '2.338.2'", "Download action repository 'actions/checkout@v4.2.2'")
            else:
                log = head.replace("'2.338.2'", "'%s'" % j['_version'])
            sb.answer('repos/%s/actions/jobs/%d/logs' % (REPO_ARG, j['id']), log)
        return sb


def healthy(now=NOW):
    return World(now).daily('linux-a').daily('linux-b').daily('mac-a')


def watch(test, world, args=None, sb=None):
    sb = sb or Sandbox(test)
    world.install(sb)
    rc, out, err = sb.run(args or (['--repo', REPO_ARG] + HOSTS + FAMS + ['--now', str(world.now)]))
    test.assertEqual(rc, 0, err)
    lines = out.splitlines()
    for l in lines:
        test.assertRegex(l, r'^(open [a-z0-9-]+ \S.*|clear [a-z0-9-]+)$')
        topic = l.split(' ')[1]
        test.assertRegex(topic, TOPIC)
        test.assertLessEqual(len(topic), 48)
    for call in sb.gh_calls():
        test.assertEqual(call[0], 'api', call)
        test.assertFalse({'-X', '--method', '-f', '-F', '--field', '--raw-field', '--input'} & set(call), call)
    return lines


def opened(lines):
    return {l.split(' ', 2)[1]: l.split(' ', 2)[2] for l in lines if l.startswith('open ')}


class Healthy(unittest.TestCase):
    def test_a_healthy_week_opens_nothing_and_clears_every_topic(self):
        lines = watch(self, healthy())
        self.assertEqual(opened(lines), {})
        for t in ('runner-stale-2-338-2', 'runner-failing-2-338-2', 'runner-watchdog-could-not-run-2-338-2',
                  'runner-watchdog-could-not-run'):
            self.assertIn('clear ' + t, lines)

    def test_the_topics_of_every_release_before_the_newest_are_cleared_prereleases_skipped(self):
        lines = watch(self, healthy())
        for v in ('2-338-0', '2-337-0', '2-336-0', '2-335-1', '2-335-0', '2-334-0', '2-333-1', '2-333-0', '2-332-0',
                  '2-331-0'):
            for rule in ('runner-stale-', 'runner-failing-', 'runner-watchdog-could-not-run-'):
                self.assertIn('clear ' + rule + v, lines)
        self.assertFalse(any('2-338-1' in l for l in lines))       # v2.338.1 is a prerelease

    def test_codex_f9_a_topic_four_or_more_releases_back_is_cleared(self):
        # 2.330.0 ... 2.335.0, the newest 2.335.0: an ask of 2.330.0 (missed weekly runs) must not hold a slot
        rels = [('2.335.0', 30), ('2.334.0', 60), ('2.333.0', 90), ('2.332.0', 120), ('2.331.0', 150), ('2.330.0', 180)]
        w = World(releases=rels).daily('linux-a', '2.335.0').daily('linux-b', '2.335.0').daily('mac-a', '2.335.0')
        lines = watch(self, w)
        self.assertEqual(opened(lines), {})
        for v in ('2-330-0', '2-331-0', '2-332-0', '2-333-0', '2-334-0'):
            for rule in ('runner-stale-', 'runner-failing-', 'runner-watchdog-could-not-run-'):
                self.assertIn('clear ' + rule + v, lines)
        # control: the newest release's topics are cleared by their rules, not as superseded; nothing newer exists
        self.assertFalse(any('2-336' in l for l in lines))

    def test_the_jq_under_test_is_a_tested_watchdog_row(self):
        rows = [l.split() for l in open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), 'core', 'TESTED_JQ')) if l.strip() and not l.startswith('#')]
        self.assertIn(jq_version(), [r[0] for r in rows if 'watchdog' in r[1].split(',')])


class Stale(unittest.TestCase):
    def test_a_label_behind_a_release_out_for_more_than_7_days(self):
        w = healthy()
        w.job('linux-a', 0.1, version='2.338.0')                   # its newest job
        o = opened(watch(self, w))
        self.assertEqual(list(o), ['runner-stale-2-338-2'])
        t = o['runner-stale-2-338-2']
        for s in ('linux-a (hz-docker)', 'runner 2.338.0', 'runner 2.338.2', 'since 2026-10-26',
                  '`ssh scaler@hz.example runner-updater status`'):
            self.assertIn(s, t)

    def test_control_a_release_out_for_less_than_7_days_is_not_yet_due(self):
        now = calendar.timegm((2026, 10, 31, 9, 0, 0))             # 2.338.2 out 4.8 days; 2.338.0 out 25 days
        w = World(now).daily('linux-a', version='2.338.0').daily('linux-b', version='2.338.0').daily('mac-a', version='2.338.0')
        self.assertEqual(opened(watch(self, w)), {})

    def test_the_studio_host_line_for_a_studio_family(self):
        w = healthy()
        w.job('mac-a', 0.1, version='2.337.0')
        t = opened(watch(self, w))['runner-stale-2-338-2']
        self.assertIn('`ssh ci@studio.example runner-updater status`', t)
        self.assertNotIn('scaler@hz.example', t)


def failing_world(old_version='2.338.0', fails_now=4, fails_before=1):
    w = World().daily('linux-a').daily('mac-a')
    for d in range(10):                                             # the 7 days before: 8-14 days ago
        w.job('linux-b', 8 + d * 0.6, 'failure' if d < fails_before else 'success', old_version)
    for d in range(10):                                             # the last 7 days
        w.job('linux-b', 0.2 + d * 0.6, 'failure' if d < fails_now else 'success', '2.338.2')
    return w


class Failing(unittest.TestCase):
    def world(self, **kw):
        return failing_world(**kw)

    def test_more_failures_after_a_version_change(self):
        o = opened(watch(self, self.world()))
        self.assertEqual(list(o), ['runner-failing-2-338-2'])
        t = o['runner-failing-2-338-2']
        for s in ('linux-b (hz-docker)', 'runner 2.338.2', '8 days ago: runner 2.338.0', '4 of 10', '1 of 10',
                  '`ssh scaler@hz.example runner-updater back hz-docker`', '`ssh scaler@hz.example runner-updater status`'):
            self.assertIn(s, t)

    def test_control_the_same_version_as_8_days_ago(self):
        self.assertEqual(opened(watch(self, self.world(old_version='2.338.2'))), {})

    def test_control_fewer_than_3_failures(self):
        self.assertEqual(opened(watch(self, self.world(fails_now=2, fails_before=0))), {})

    def test_control_not_twice_the_share_before(self):
        self.assertEqual(opened(watch(self, self.world(fails_now=4, fails_before=3))), {})

    def test_canceled_jobs_are_not_in_the_share(self):
        w = self.world(fails_now=3, fails_before=1)                # 3 of 10 against 1 of 10: twice, so FAILING
        self.assertIn('runner-failing-2-338-2', opened(watch(self, w)))
        for i in range(20):                                         # 3 of 30 would not be twice 1 of 10
            w.job('linux-b', 1 + i * 0.1, 'cancelled', '2.338.2')
        self.assertIn('runner-failing-2-338-2', opened(watch(self, w)))

    def test_canceled_and_skipped_jobs_are_not_counted(self):
        w = self.world(fails_now=2, fails_before=0)
        for i in range(5):
            w.job('linux-b', 1 + i * 0.1, 'cancelled')
        self.assertEqual(opened(watch(self, w)), {})
        w.job('linux-b', 1.9, 'timed_out')                         # a time-out is a failure: now 3
        self.assertIn('runner-failing-2-338-2', opened(watch(self, w)))


class Topics(unittest.TestCase):
    def test_two_rules_two_topics(self):
        w = failing_world()
        w.job('linux-a', 0.05, version='2.338.0')
        o = opened(watch(self, w))
        self.assertEqual(sorted(o), ['runner-failing-2-338-2', 'runner-stale-2-338-2'])

    def test_clears_come_before_opens(self):
        w = healthy()
        w.job('linux-a', 0.1, version='2.338.0')
        lines = watch(self, w)
        kinds = [l.split(' ')[0] for l in lines]
        self.assertEqual(kinds, sorted(kinds))                     # every clear, then every open


CONSUMER = re.compile(r'^#\s+consumer: (.+)$', re.M)
STUB = '#!%(py)s -I\nimport json, sys\nwith open(%(log)r, "a") as f:\n    f.write(json.dumps(sys.argv[1:]) + "\\n")\n'


class Consumer(unittest.TestCase):
    """The consumer line that watchdog/run's header documents — read from the file itself, never a copy — passes each
    printed line's TEXT to `liveapp ask-owner` as data. Run under bash with stub `liveapp` and `ssh` first on PATH,
    the way the duty runs it (the line, with TOPIC and TEXT standing for the printed line's own values where it names
    them, the printed line on its stdin): ssh is never called, and --need gets TEXT byte for byte, backticks and all
    (Opus r1 F7: the asks hold `HOST runner-updater back FAMILY`; pasted into a command, a shell runs it)."""

    def documented(self):
        with open(os.path.join(REPO, 'watchdog', 'run'), encoding='utf-8') as f:
            found = CONSUMER.findall(f.read())
        self.assertEqual(len(found), 1, 'watchdog/run documents ONE line "#   consumer: ..."')
        return found[0]

    def test_the_documented_consumer_passes_the_text_as_data(self):
        w = failing_world()
        w.job('linux-a', 0.05, version='2.338.0')                 # STALE too: both opens carry backticks
        lines = watch(self, w)
        opens = [l for l in lines if l.startswith('open ')]
        self.assertEqual(len(opens), 2, lines)
        self.assertTrue(any('`ssh scaler@hz.example runner-updater back hz-docker`' in l for l in opens), opens)
        doc = self.documented()
        sb = Sandbox(self)
        calls, sshlog = os.path.join(sb.root, 'liveapp.log'), os.path.join(sb.root, 'ssh.log')
        for name, log in (('liveapp', calls), ('ssh', sshlog)):
            p = os.path.join(sb.stubs, name)
            with open(p, 'w') as f:
                f.write(STUB % {'py': sys.executable, 'log': log})
            os.chmod(p, 0o755)
        env = {'PATH': sb.stubs + ':/usr/bin:/bin', 'HOME': sb.root, 'TMPDIR': sb.root, 'LC_ALL': 'C'}
        want = []
        for l in lines:
            verb, topic, text = (l.split(' ', 2) + [''])[:3]
            want.append(['ask-owner', verb, topic] + (['--need', text] if verb == 'open' else []))
            cmd = doc.replace('TOPIC', topic).replace('TEXT', text)
            p = subprocess.run(['bash', '-c', cmd], input=l + '\n', capture_output=True, text=True, env=env, cwd=sb.root)
            self.assertEqual(p.returncode, 0, (cmd, p.stderr))
        self.assertFalse(os.path.exists(sshlog), 'the consumer ran a command of the ask text: %s' % (
            open(sshlog).read() if os.path.exists(sshlog) else ''))
        with open(calls) as f:
            got = [json.loads(x) for x in f]
        self.assertEqual(got, want)


class NotMeasured(unittest.TestCase):
    def test_a_label_with_no_job_opens_nothing_alone(self):
        w = World().daily('linux-a').daily('linux-b')               # mac-a ran nothing on main in 14 days
        self.assertEqual(opened(watch(self, w)), {})

    def test_it_rides_in_another_asks_text(self):
        w = World().daily('linux-b').daily('mac-a')
        w.job('linux-b', 0.1, version='2.338.0')                   # stale
        w.job('linux-a', 0.1, version='2.338.2')
        w.jobs[-1]['_version'] = None                               # its log has no version line
        t = opened(watch(self, w))['runner-stale-2-338-2']
        self.assertIn('Not measured: linux-a (hz-docker): its newest job log names no runner version', t)


class CouldNotRun(unittest.TestCase):
    def one_line(self, lines, topic='runner-watchdog-could-not-run-2-338-2'):
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith('open %s ' % topic), lines)
        return lines[0]

    def test_an_untested_jq(self):
        sb = Sandbox(self)
        sb.use_jq('jq-9.9')
        l = self.one_line(watch(self, healthy(), sb=sb))
        self.assertIn('jq-9.9', l)

    def test_control_a_tested_watchdog_jq_runs(self):
        sb = Sandbox(self)
        sb.use_jq('jq-1.6')                                         # the watchdog-only row
        self.assertIn('clear runner-stale-2-338-2', watch(self, healthy(), sb=sb))

    def test_a_gh_failure(self):
        sb = Sandbox(self)
        w = healthy()
        w.install(sb)
        since = time.strftime('%Y-%m-%d', time.gmtime(NOW - 14 * DAY))
        runs = 'repos/%s/actions/runs?branch=main&created=>=%s&per_page=100' % (REPO_ARG, since)
        sb.answer(runs, rc=1)
        rc, out, err = sb.run(['--repo', REPO_ARG] + HOSTS + FAMS + ['--now', str(NOW)])
        self.assertEqual(rc, 0, err)
        l = self.one_line(out.splitlines())
        self.assertIn('actions/runs', l)
        self.assertEqual(sum(1 for c in sb.gh_calls() if runs in c), 2, sb.timeline())     # tried twice (issue #3)

    def test_the_newest_release_unreadable(self):
        sb = Sandbox(self)
        w = healthy()
        w.install(sb)
        sb.answer('repos/actions/runner/releases/latest', rc=1, jq_expr='.tag_name')
        rc, out, _ = sb.run(['--repo', REPO_ARG] + HOSTS + FAMS + ['--now', str(NOW)])
        self.one_line(out.splitlines(), 'runner-watchdog-could-not-run')
        self.assertEqual(sum(1 for c in sb.gh_calls() if 'repos/actions/runner/releases/latest' in c), 2,
                         sb.timeline())

    def test_a_program_that_does_not_compile(self):
        sb = Sandbox(self)
        p = os.path.join(sb.repo, 'watchdog', 'watchdog.jq')
        with open(p, 'a') as f:
            f.write('\n| if then\n')
        l = self.one_line(watch(self, healthy(), sb=sb))
        self.assertIn('watchdog/watchdog.jq failed at its step pick', l)

    def test_usage_errors(self):
        for args in (HOSTS + FAMS + ['--now', str(NOW)],                                        # no --repo
                     ['--repo', REPO_ARG, '--hz', 'ssh x'] + FAMS + ['--now', str(NOW)],       # studio family, no line
                     ['--repo', REPO_ARG] + HOSTS + ['--family', 'bad'] + ['--now', str(NOW)]):
            self.one_line(watch(self, healthy(), args=args))

    def test_a_generic_or_shared_family_label_cannot_run(self):
        # Opus r1 F9: PLAN §3's label column passed as written puts every self-hosted job (and so the Linux host's) in
        # linux-tart; a label two families name does the same. GitHub compares labels without case
        cases = ((['hz-docker=hz:linux-a', 'linux-tart=studio:self-hosted,gate-x'], 'self-hosted'),
                 (['hz-docker=hz:linux-a', 'linux-tart=studio:Self-Hosted,gate-x'], 'self-hosted'),
                 (['hz-docker=hz:linux-a,linux-b', 'mac-golden=studio:mac-a,linux-b'], 'linux-b'),
                 (['hz-docker=hz:linux-a', 'mac-golden=studio:LINUX-A'], 'linux-a'))
        for fams, label in cases:
            w = healthy()
            w.job('linux-a', 0.1, version='2.338.0')               # the Linux host's newest job is behind
            args = ['--repo', REPO_ARG] + HOSTS + sum((['--family', f] for f in fams), []) + ['--now', str(NOW)]
            l = self.one_line(watch(self, w, args=args))
            self.assertIn('label %s' % label, l, fams)

    def test_control_distinct_labels_run_and_a_label_twice_in_one_family_is_one(self):
        w = healthy()
        w.job('linux-a', 0.1, version='2.338.0')
        args = ['--repo', REPO_ARG] + HOSTS + ['--family', 'hz-docker=hz:linux-a,linux-b,linux-a',
                                               '--family', 'mac-golden=studio:mac-a'] + ['--now', str(NOW)]
        self.assertEqual(list(opened(watch(self, w, args=args))), ['runner-stale-2-338-2'])


E = '\x1b'
# a SYNTHETIC log head (no line of a real job log): terminal escape sequences (colour codes, an erase, a window title)
# on the lines before the version line, around the text on its own line, and on the lines after it; a byte order mark
# first, as in a real log (and fixtures/job-log-head.txt)
ESCAPED_HEAD = '﻿' + ''.join('2026-11-01T09:00:00.%07dZ %s\n' % (i, l) for i, l in enumerate((
    E + '[36;1mRequested labels: self-hosted, example-label' + E + '[0m',
    E + '[1;33mJob defined at: example-org/example/.github/workflows/ci.yml@refs/heads/main' + E + '[0m',
    E + '[32m' + E + "[1mCurrent runner version: '2.338.2'" + E + '[0m' + E + '[K',
    E + "[36;1mRunner name: 'runner-0000abcd'" + E + '[0m',
    E + "[36;1mMachine name: 'example-machine'" + E + '[0m',
    E + '[90m##[group]Operating System' + E + '[0m',
    'Example OS 1.0',
    E + '[90m##[endgroup]' + E + '[0m',
    E + ']0;example title' + E + '\\',
)))


def stale_world(head=None):
    """healthy, and linux-a's newest job runs 2.338.0 (STALE): the lines name the version a log head gives."""
    w = healthy()
    w.job('linux-a', 0.1, version='2.338.0')
    if head is not None:
        w.head = head
    return w


class EscapeSequences(unittest.TestCase):
    """gh 2.98.0 and newer refuse a body that holds a terminal escape sequence (a job log holds colour codes) unless
    given --allow-escape-sequences, and gh 2.66.1 rejects that flag: watchdog/run passes it on every call when this
    gh's `gh api --help` lists it, read once a run."""

    def run_in(self, gh, head):
        sb = Sandbox(self, gh=gh)
        return watch(self, stale_world(head), sb=sb), sb

    def test_a_new_gh_gets_the_flag_on_every_call_and_an_escaped_log_reads_as_a_clean_one(self):
        clean, _ = self.run_in('new', None)
        self.assertIn('linux-a (hz-docker) runs runner 2.338.0', opened(clean)['runner-stale-2-338-2'])
        lines, sb = self.run_in('new', ESCAPED_HEAD)
        self.assertEqual(lines, clean)
        calls = sb.gh_calls()
        self.assertEqual(calls.count(['api', '--help']), 1, calls)                     # read once a run
        reads = [c for c in calls if c != ['api', '--help']]
        self.assertTrue(any(any(a.endswith('/logs') for a in c) for c in reads), reads)
        self.assertTrue(any('repos/actions/runner/releases/latest' in c for c in reads), reads)
        for c in reads:                                             # every call goes through the one helper
            self.assertIn(FLAG, c)

    def test_an_old_gh_never_gets_the_flag_and_an_escaped_log_reads_as_a_clean_one(self):
        clean, _ = self.run_in('old', None)
        self.assertIn('linux-a (hz-docker) runs runner 2.338.0', opened(clean)['runner-stale-2-338-2'])
        lines, sb = self.run_in('old', ESCAPED_HEAD)
        self.assertEqual(lines, clean)
        calls = sb.gh_calls()
        self.assertEqual(calls.count(['api', '--help']), 1, calls)
        self.assertEqual([c for c in calls if FLAG in c], [])

    def test_control_a_new_gh_not_given_the_flag_cannot_read_an_escaped_log(self):
        # the refusal bites: this gh refuses as a new one does, but its help does not list the flag, so it gets none
        lines, _ = self.run_in('new-unlisted', ESCAPED_HEAD)
        self.assertEqual(len(lines), 1, lines)
        self.assertRegex(lines[0], r'^open runner-watchdog-could-not-run-2-338-2 The weekly runner watchdog could not '
                                   r'run: gh api repos/%s/actions/jobs/[0-9]+/logs failed\.' % REPO_ARG)
        clean, _ = self.run_in('new-unlisted', None)                # and it reads a clean log
        self.assertIn('runner-stale-2-338-2', opened(clean))

    def test_a_gh_whose_help_fails_cannot_run(self):
        lines, sb = self.run_in('no-help', None)
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith('open runner-watchdog-could-not-run The weekly runner watchdog could not '
                                            'run: gh api --help failed.'), lines)
        self.assertEqual(sb.gh_calls(), [['api', '--help']])


class VersionRead(unittest.TestCase):
    def test_the_version_is_read_through_escape_sequences_before_after_and_around_its_line(self):
        for gh in ('new', 'old'):
            with self.subTest(gh=gh):
                o = opened(watch(self, stale_world(ESCAPED_HEAD), sb=Sandbox(self, gh=gh)))
                self.assertEqual(list(o), ['runner-stale-2-338-2'])
                t = o['runner-stale-2-338-2']
                self.assertIn('linux-a (hz-docker) runs runner 2.338.0 on its newest job on main', t)
                self.assertNotIn('Not measured', t)

    def test_control_an_escaped_head_with_no_version_line_is_not_measured(self):
        for gh in ('new', 'old'):
            with self.subTest(gh=gh):
                w = stale_world(ESCAPED_HEAD)
                w.job('mac-a', 0.05)
                w.jobs[-1]['_version'] = None
                t = opened(watch(self, w, sb=Sandbox(self, gh=gh)))['runner-stale-2-338-2']
                self.assertIn('Not measured: mac-a (mac-golden): its newest job log names no runner version', t)


class Retry(unittest.TestCase):
    """Issue #3: a run makes about 200 gh calls, and one transient failure ended it as COULD-NOT-RUN. A failed call is
    tried once more after `sleep 3`; a second failure is COULD-NOT-RUN, the line as before."""

    def calls(self, w):
        newest = w.jobs[-1]                                         # stale_world's linux-a job: its log is read
        since = time.strftime('%Y-%m-%d', time.gmtime(w.now - 14 * DAY))
        return (('repos/actions/runner/releases/latest', '.tag_name'),
                ('repos/actions/runner/releases?per_page=30', None),
                ('repos/%s/actions/runs?branch=main&created=>=%s&per_page=100' % (REPO_ARG, since), None),
                ('repos/%s/actions/runs/%d/jobs?per_page=100' % (REPO_ARG, newest['run_id']), None),
                ('repos/%s/actions/jobs/%d/logs' % (REPO_ARG, newest['id']), None))

    def test_a_call_that_fails_once_is_tried_again_after_a_pause_and_the_lines_are_those_of_a_run_that_never_failed(self):
        clean = watch(self, stale_world())
        self.assertIn('runner-stale-2-338-2', opened(clean))
        for path, jq_expr in self.calls(stale_world()):
            with self.subTest(path=path):
                sb = Sandbox(self)
                sb.fail(path, 1, jq_expr)
                self.assertEqual(watch(self, stale_world(), sb=sb), clean)
                t = sb.timeline()
                at = [i for i, c in enumerate(t) if path in c]
                self.assertEqual(len(at), 2, t)                     # exactly two tries
                self.assertEqual(at[1], at[0] + 2, t)
                self.assertEqual(t[at[0] + 1], ['#sleep', '3'])     # a fixed pause between them
                self.assertEqual([c for c in t if c[:1] == ['#sleep']], [['#sleep', '3']], t)   # and no other

    def test_control_a_call_that_fails_every_time_is_tried_twice_and_the_run_cannot_run(self):
        w = stale_world()
        path = self.calls(w)[-1][0]
        sb = Sandbox(self)
        sb.fail(path, 99)
        lines = watch(self, w, sb=sb)
        self.assertEqual(lines, ['open runner-watchdog-could-not-run-2-338-2 The weekly runner watchdog could not run: '
                                 'gh api %s failed. Fix it, then run the duty again.' % path])
        self.assertEqual(sum(1 for c in sb.gh_calls() if path in c), 2, sb.timeline())


if __name__ == '__main__':
    unittest.main()
