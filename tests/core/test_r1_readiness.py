"""core/r1.jq on runscaler v0.22.0's Docker readiness removal (H3 M-B, PLAN D6's class): `Runner removed
reason=readiness-failed` with NO jobId, on a family whose provider is not "tart", is read EXACTLY as `Runner removed
reason=exited` with no jobId — kind `exited`: a counted failure (non-connect), taken back by a `Job started|completed
for unknown runner (already removed?)` line naming its runner within SETTLE - ORDER before or after it. Controls:
`readiness-failed` WITH a jobId, and `exited` with no jobId, keep today's result; a Tart family ($p == "tart", the
classify gate, r1.jq:82) keeps today's result for the same records (runscaler logs readiness only for Docker:
controller/readiness.go via WaitReady, which only DockerProvider implements, docker_readiness.go:26).

The records are v0.22.0's own shapes, in its 5-wide level column (charm log v2.0.1, as v0.12.0; corejq.to_v012):
- `Runner removed` (internal/controller/controller.go:750-767 at v0.22.0, tag 7245c058a): name, instanceID, reason,
  and jobId, repo, workflowRunId, job (and result) only when the runner held a job. reason `readiness-failed` is
  state.go:29 (reasonReadiness), set by readinessResult (state.go:130-145); `exited` is state.go:27, set by
  markExited (state.go:184-200).
- `Runner started` (controller.go:471-475, INFO, logged BEFORE readiness on Docker), the WARN `Runner exited before job
  completion; scheduling cleanup` (controller.go:604): the readiness-takeover shape (readiness_test.go:174-195).
- `Job started|completed for unknown runner (already removed?) runnerName=` (controller.go:169, :187)."""
import unittest

from tests.core.corejq import charm
from tests.core.test_r1 import Run, fam, t

SET = 'linux-a'
JOB = [('jobId', '2ce18645-b726-290f-1564-ea0902058718'), ('repo', 'example-org/example'),
       ('workflowRunId', '15885850636'), ('job', 'build (9150)')]


def name(i):
    return 'runner-0000b%03d' % i


def removed22(sec, n, reason, job=False, set_=SET):
    """controller.go:750-767: the job's four attributes only when the runner held one (job.id != "")."""
    a = [('name', n), ('instanceID', 'c0ffee%02d' % (sec % 100)), ('reason', reason)] + (JOB if job else [])
    return charm(t(sec), 'INFO ', set_, 'Runner removed', a)


def started22(sec, n, set_=SET):
    return charm(t(sec), 'INFO ', set_, 'Runner started', [('name', n), ('instanceID', 'c0ffee%02d' % (sec % 100)),
                                                           ('startupTime', '1.2s')])


def exited_warn22(sec, n, set_=SET):
    return charm(t(sec), 'WARN ', set_, 'Runner exited before job completion; scheduling cleanup', [('name', n)])


def unknown22(sec, n, what='completed', set_=SET):
    return charm(t(sec), 'WARN ', set_, 'Job %s for unknown runner (already removed?)' % what, [('runnerName', n)])


def tail22(sec, set_=SET):
    """two records SETTLE + ORDER past the events (the last record of a pass is held): every failure before is settled
    and every exit final."""
    rec = lambda s: charm(t(s), 'INFO ', set_, 'Scaling up runner', [('currentCount', 0), ('desiredCount', 1)])  # noqa
    return rec(sec) + rec(sec + 1)


def three(reason, job=False, takeover=False):
    """three removals of REASON, 10 s apart, on one set, no proof of life between them. takeover: each with its runner's
    `Runner started` 300 s before it and the scheduling-cleanup WARN 1 s before it (readiness_test.go:174-195)."""
    log = ''
    for i in range(3):
        s = 400 + 10 * i
        if takeover:
            log += started22(s - 300, name(i))
    for i in range(3):
        s = 400 + 10 * i
        if takeover:
            log += exited_warn22(s - 1, name(i))
        log += removed22(s, name(i), reason, job=job)
    return log + tail22(700)


def fx(test, log, provider='docker'):
    return Run(test, {'fx': fam(provider, (SET,))}).fx(log)


def shape(r):
    """the verdict as a person reads it, without the failures' texts (they name the reason)."""
    return (r['verdict'], r['set'], r['connect_only'], [f['t'] for f in r['failures']], [f['c'] for f in r['failures']])


class ReadinessFailedIsExited(unittest.TestCase):
    def test_three_readiness_failed_removals_with_no_job_roll_back(self):
        r = fx(self, three('readiness-failed'))
        self.assertEqual((r['verdict'], r['set'], r['connect_only'], len(r['failures'])), ('rollback', SET, False, 3), r)
        # the failure's text names the reason runscaler logged
        self.assertTrue(all('reason=readiness-failed' in f['x'] for f in r['failures']), r['failures'])

    def test_the_same_verdict_and_class_as_three_exited_removals(self):
        for takeover in (False, True):
            with self.subTest(takeover=takeover):
                a = fx(self, three('readiness-failed', takeover=takeover))
                b = fx(self, three('exited', takeover=takeover))
                self.assertEqual(shape(a), shape(b))
                self.assertEqual(b['verdict'], 'rollback', b)

    def test_control_exited_with_no_job_keeps_todays_result(self):
        r = fx(self, three('exited'))
        self.assertEqual((r['verdict'], r['connect_only'], len(r['failures'])), ('rollback', False, 3), r)
        self.assertTrue(all(f['x'].startswith('Runner removed reason=exited, no job: ') for f in r['failures']))

    def test_control_readiness_failed_with_a_job_keeps_todays_result(self):
        r = fx(self, three('readiness-failed', job=True))
        self.assertEqual((r['verdict'], r['failures']), ('none', []), r)

    def test_control_on_tart_the_same_records_keep_todays_result(self):
        # the gate is classify's $p (r1.jq:82): a Tart family reads `readiness-failed` as any other removal
        for takeover in (False, True):
            with self.subTest(takeover=takeover):
                r = fx(self, three('readiness-failed', takeover=takeover), provider='tart')
                self.assertEqual((r['verdict'], r['failures']), ('none', []), r)
        # control of the control: the Tart family does roll back on three exited removals
        self.assertEqual(fx(self, three('exited'), provider='tart')['verdict'], 'rollback')


class ThePairing(unittest.TestCase):
    """A `readiness-failed` removal with no jobId and an unknown-runner line naming its runner within SETTLE - ORDER
    (110 s), in either order, is no counted failure (the D6 AMENDMENT, as for `exited`)."""

    def log(self, line_first, other=None):
        log = ''
        for i in range(3):
            s = 400 + 30 * i
            line = unknown22(s + (-5 if line_first else 5), other or name(i))
            rem = removed22(s, name(i), 'readiness-failed')
            log += line + rem if line_first else rem + line
        return log + tail22(800)

    def test_the_line_after_the_removal_takes_it_back(self):
        r = fx(self, self.log(line_first=False))
        self.assertEqual((r['verdict'], r['pending']), ('none', None), r)

    def test_the_line_before_the_removal_takes_it_back(self):
        r = fx(self, self.log(line_first=True))
        self.assertEqual((r['verdict'], r['pending']), ('none', None), r)

    def test_control_a_line_naming_another_runner_takes_nothing_back(self):
        for line_first in (False, True):
            with self.subTest(line_first=line_first):
                r = fx(self, self.log(line_first, other='runner-0000feed'))
                self.assertEqual((r['verdict'], len(r['failures'])), ('rollback', 3), r)


if __name__ == '__main__':
    unittest.main()
