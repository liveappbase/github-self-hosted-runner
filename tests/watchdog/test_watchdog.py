"""watchdog/run + watchdog/watchdog.jq — the weekly runner watchdog (PLAN D8), against a substitute gh. Pinned: the rules
STALE (a label's newest job on main runs a version older than a release out for more than 7 days), FAILING (the
newest version differs from 8 days ago, and the last 7 days' failure share is at least twice the 7 days before, with at
least 3 failures) and COULD-NOT-RUN (an untested jq, a gh failure, a program error: ONE line); one topic per (rule,
newest release), `clear` for the topics of the releases before it; NOT MEASURED only inside another ask's text; the
output is only `open TOPIC TEXT` and `clear TOPIC` lines; gh is only read. fixtures/releases.json is the real
actions/runner release list (2026-11-01, a prerelease among them); fixtures/job-log-head.txt the head of a real job
log (its runner group renamed). Every trigger has a control that comes out the other way."""
import calendar
import os
import re
import time
import unittest

from tests.watchdog.wdrun import Sandbox, fixture, jq_version

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

    def __init__(self, now=NOW):
        self.now, self.jobs, self.next_id = now, [], 1000

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
        sb.answer('repos/actions/runner/releases/latest', 'v2.338.2\n', jq_expr='.tag_name')
        sb.answer('repos/actions/runner/releases?per_page=30', fixture('releases.json'))
        since = time.strftime('%Y-%m-%d', time.gmtime(self.now - 14 * DAY))
        runs = [{'id': j['run_id'], 'head_branch': 'main'} for j in self.jobs]
        sb.answer('repos/%s/actions/runs?branch=main&created=>=%s&per_page=100' % (REPO_ARG, since),
                  {'total_count': len(runs), 'workflow_runs': runs})
        head = fixture('job-log-head.txt')
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

    def test_the_topics_of_the_releases_before_the_newest_are_cleared_prereleases_skipped(self):
        lines = watch(self, healthy())
        for v in ('2-338-0', '2-337-0', '2-336-0'):
            for rule in ('runner-stale-', 'runner-failing-', 'runner-watchdog-could-not-run-'):
                self.assertIn('clear ' + rule + v, lines)
        self.assertFalse(any('2-338-1' in l for l in lines))       # v2.338.1 is a prerelease
        self.assertFalse(any('2-335-1' in l for l in lines))       # only the three before the newest

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
        sb.answer('repos/%s/actions/runs?branch=main&created=>=%s&per_page=100' % (REPO_ARG, since), rc=1)
        rc, out, err = sb.run(['--repo', REPO_ARG] + HOSTS + FAMS + ['--now', str(NOW)])
        self.assertEqual(rc, 0, err)
        l = self.one_line(out.splitlines())
        self.assertIn('actions/runs', l)

    def test_the_newest_release_unreadable(self):
        sb = Sandbox(self)
        w = healthy()
        w.install(sb)
        sb.answer('repos/actions/runner/releases/latest', rc=1, jq_expr='.tag_name')
        rc, out, _ = sb.run(['--repo', REPO_ARG] + HOSTS + FAMS + ['--now', str(NOW)])
        self.one_line(out.splitlines(), 'runner-watchdog-could-not-run')

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


if __name__ == '__main__':
    unittest.main()
