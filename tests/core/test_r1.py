"""core/r1.jq — the log pass (PLAN D6): ownership by position, provenance, the classification table with its D6
AMENDMENT (an exited removal taken back by a later unknown-runner line), SETTLE (a failure is judged only when no proof
of life can still arrive for it), R1 (three settled counted failures on one set with no proof of life between them ->
ROLLBACK; `pending` while they may still come), CONNECT-ONLY, NOT SERVING, evidence gaps.
Records are built by corejq.charm(), which test_records.py pins byte for byte to the real logs; the error texts are
runscaler's own (internal/provider/tart.go, docker.go, internal/controller/controller.go at ae405a5), the benign
"no longer exists" record is the Studio's real one. Every trigger has a control that comes out the other way."""
import datetime
import re
import unittest

from tests.core.corejq import charm, fixture, ok, run

NOW = 1793530800                                   # 2026-11-01 11:00:00 UTC (the glue's clock)
P = {'pid': 4242, 'start': 1793520000}             # runscaler, started 08:00:00 UTC
Q = {'pid': 5151, 'start': 1793525000}             # a later runscaler (09:23:20 UTC)
INSTALLED = P['start'] - 60                        # the config was installed a minute before P started
BASE = datetime.datetime(2026, 11, 1, 5, 0, 0)     # log times (no zone; never compared with NOW)


def t(sec):
    return (BASE + datetime.timedelta(seconds=sec)).strftime('%Y-%m-%d %H:%M:%S')


def failed(sec, err, set_='mac-a'):
    return charm(t(sec), 'ERRO', set_, 'Failed to start runner, will retry', [('error', err)])


def scaling(sec, set_='mac-a'):
    return charm(t(sec), 'INFO', set_, 'Scaling up runner', [('currentCount', 0), ('desiredCount', 1)])


def tail(sec=160, set_='mac-a'):
    """The log moves on: two records at least SETTLE (120 s of log time) after a cell's events, so every failure before
    them is settled. Two, because the last record of a pass is held (it may yet grow): the first one is read."""
    return scaling(sec, set_) + scaling(sec + 1, set_)


def started(sec, name, set_='mac-a'):
    return charm(t(sec), 'INFO', set_, 'Runner started', [('name', name), ('instanceID', name), ('startupTime', '22.4s')])


def removed(sec, name, reason, job=True, result='succeeded', set_='mac-a'):
    a = [('name', name), ('instanceID', name), ('reason', reason)]
    if job:
        a += [('jobId', '2ce18645-b726-290f-1564-ea0902058718'), ('repo', 'example-org/example'),
              ('workflowRunId', '15885850636'), ('job', 'build (9150)')]
        if result:
            a += [('result', result)]
    return charm(t(sec), 'INFO', set_, 'Runner removed', a)


def exited_warn(sec, name, set_='mac-a'):
    return charm(t(sec), 'WARN', set_, 'Runner exited before job completion; removing stale capacity', [('name', name)])


def unknown(sec, name, set_='mac-a', what='completed'):
    return charm(t(sec), 'WARN', set_, 'Job %s for unknown runner (already removed?)' % what, [('runnerName', name)])


TAIL_OK = "√ Connected to GitHub\n\nCurrent runner version: '2.339.0'\n2026-11-01 05:00:00Z: Listening for Jobs\n"


def before_connecting(vm):
    return ('failed to start runner: runner process exited on %s before connecting to GitHub; runner log:\n'
            'Starting Runner listener with startup type: service\nAn error occurred: Not configured.' % vm)


def right_after(vm, line):
    return ('failed to start runner: runner process exited on %s right after connecting to GitHub; runner log:\n%s%s\n'
            'Exiting runner...' % (vm, TAIL_OK, line))


BENIGN = 'The runner no longer exists on the server. Cleaning up local configuration.'
RETIRED = 'Runner version v2.339.0 is deprecated and cannot receive messages.'


def did_not_connect(vm):
    return ('failed to start runner: runner on %s did not connect to GitHub within 5m0s; newest runner diagnostics:\n'
            '[2026-11-01 05:00:00Z INFO RunnerServer] Establish connection' % vm)


JIT = 'failed to generate JIT config: POST https://api.github.com/actions/runner-registration: 422 Unprocessable Entity'
DOCKER_CREATE = 'failed to create runner container: Error response from daemon: No such image: example-runner'
DOCKER_START = 'failed to start runner container: Error response from daemon: OCI runtime create failed'
OTHER = 'failed to start runner on runner-0000aaaa: tart exec: exit status 1'
SHIM = 'liveapp-ci-shim: REFUSE free disk below the floor: 93 GiB < 100 GiB'


def three(err_of, set_='mac-a', start=10):
    return ''.join(failed(start + 10 * i, err_of(i), set_) for i in range(3)) + tail(start + 140, set_)


def fam(provider='tart', sets=('mac-a',), version='2.339.0', image='img-new', closed_at=None):
    return {'provider': provider, 'sets': list(sets),
            'candidate': {'version': version, 'lines': {s: image for s in sets},
                          'closed_at': P['start'] if closed_at is None else closed_at}}


def facts(families, before=P, after=None, continuous=True, installed=INSTALLED, lines=None, offset=0, restart=None):
    """restart: (FROM, TO), the glue's fact that it restarted runscaler from process FROM to TO in this interval."""
    after = before if after is None else after
    if lines is None:
        lines = {}
        for f in families.values():
            if f['candidate']:
                lines.update(f['candidate']['lines'])
    out = {'format': 1, 'host': 'studio', 'sets': sorted(lines), 'proc': {'before': before, 'after': after},
           'position': {'inode': '7', 'offset': offset, 'sha': 'x'}, 'continuous': continuous,
           'config': {'installed': installed, 'lines': lines}, 'families': families}
    if restart is not None:
        out['restart'] = {'from': restart[0], 'to': restart[1]}
    return out


class Run:
    """Passes of the glue: each pass gives the text since the last one; the state goes from pass to pass."""

    def __init__(self, test, families=None, opened=True):
        self.test, self.families, self.state, self.now = test, families or {'fx': fam()}, [], NOW
        if opened:
            self.go()

    def go(self, log='', healthz=(), now=None, families=None, **kw):
        self.now = now or (self.now + 600)
        fams = families or self.families
        out = ok(self.test, 'r1', state=self.state, log=log, healthz=list(healthz), facts=facts(fams, **kw), now=self.now)
        self.state = out['state']
        return out

    def fx(self, log='', **kw):
        return self.go(log, **kw)['families']['fx']


class R1(unittest.TestCase):
    def test_three_connect_failures_roll_back_connect_only(self):
        r = Run(self).fx(three(lambda i: before_connecting('runner-0000000%d' % i)))
        self.assertEqual(r['verdict'], 'rollback', r)
        self.assertEqual(r['set'], 'mac-a')
        self.assertTrue(r['connect_only'])
        self.assertEqual(len(r['failures']), 3)

    def test_control_a_job_completed_between_them_is_proof_of_life(self):
        log = (failed(10, before_connecting('runner-00000001')) + failed(20, before_connecting('runner-00000002'))
               + removed(25, 'runner-0000beef', 'job-completed') + failed(30, before_connecting('runner-00000003'))
               + tail())
        self.assertEqual(Run(self).fx(log)['verdict'], 'none')

    def test_two_failures_are_not_r1(self):
        log = failed(10, before_connecting('runner-00000001')) + failed(20, OTHER) + tail()
        self.assertEqual(Run(self).fx(log)['verdict'], 'none')

    def test_did_not_connect_is_connect_class(self):
        r = Run(self).fx(three(lambda i: did_not_connect('runner-0000000%d' % i)))
        self.assertEqual((r['verdict'], r['connect_only']), ('rollback', True))

    def test_any_other_start_failure_counts_and_is_not_connect_class(self):
        r = Run(self).fx(three(lambda i: OTHER))
        self.assertEqual((r['verdict'], r['connect_only']), ('rollback', False))

    def test_one_non_connect_failure_makes_the_run_not_connect_only(self):
        errs = [before_connecting('runner-00000001'), OTHER, did_not_connect('runner-00000003')]
        r = Run(self).fx(three(lambda i: errs[i]))
        self.assertEqual((r['verdict'], r['connect_only']), ('rollback', False))

    def test_jit_failures_are_not_counted(self):
        self.assertEqual(Run(self).fx(three(lambda i: JIT))['verdict'], 'none')

    def test_docker_container_failures_count(self):
        for err in (DOCKER_CREATE, DOCKER_START):
            r = Run(self, {'fx': fam('docker', ('linux-a',))}).fx(three(lambda i: err, 'linux-a'))
            self.assertEqual((r['verdict'], r['connect_only']), ('rollback', False), err)

    def test_records_of_another_set_do_not_count_for_the_family(self):
        self.assertEqual(Run(self).fx(three(lambda i: OTHER, 'mac-b'))['verdict'], 'none')

    def test_failures_on_three_different_sets_are_not_r1(self):
        run_ = Run(self, {'fx': fam(sets=('mac-a', 'mac-b', 'mac-c'))})
        log = failed(10, OTHER, 'mac-a') + failed(20, OTHER, 'mac-b') + failed(30, OTHER, 'mac-c') + tail()
        self.assertEqual(run_.fx(log)['verdict'], 'none')
        # control: the same three on one of them
        self.assertEqual(Run(self, {'fx': fam(sets=('mac-a', 'mac-b'))}).fx(three(lambda i: OTHER, 'mac-b'))['verdict'],
                         'rollback')


class ConnectClassTexts(unittest.TestCase):
    def test_no_longer_exists_on_the_server_is_benign(self):
        self.assertEqual(Run(self).fx(three(lambda i: right_after('runner-0000000%d' % i, BENIGN)))['verdict'], 'none')

    def test_control_right_after_connecting_without_it_counts(self):
        r = Run(self).fx(three(lambda i: right_after('runner-0000000%d' % i, 'An error occurred: Access denied.')))
        self.assertEqual((r['verdict'], r['connect_only']), ('rollback', True))


class ProofOfLife(unittest.TestCase):
    def test_tart_runner_started_is_proof_of_life(self):
        log = (failed(10, OTHER) + failed(20, OTHER) + started(25, 'runner-0000beef') + failed(30, OTHER) + tail())
        self.assertEqual(Run(self).fx(log)['verdict'], 'none')

    def test_a_start_taken_back_by_exited_without_a_job(self):
        log = (failed(10, OTHER) + failed(20, OTHER) + started(25, 'runner-0000beef') + failed(30, OTHER)
               + removed(35, 'runner-0000beef', 'exited', job=False) + tail())
        r = Run(self).fx(log)
        self.assertEqual(r['verdict'], 'rollback', r)
        self.assertEqual(len(r['failures']), 4)

    def test_control_a_start_confirmed_by_another_removal_stays_proof(self):
        log = (failed(10, OTHER) + failed(20, OTHER) + started(25, 'runner-0000beef') + failed(30, OTHER)
               + removed(35, 'runner-0000beef', 'scaled-down', job=False) + tail())
        self.assertEqual(Run(self).fx(log)['verdict'], 'none')

    def test_a_confirmed_start_leaves_the_state(self):
        r = Run(self)
        out = r.go(started(10, 'runner-0000beef') + removed(20, 'runner-0000beef', 'scaled-down', job=False) + scaling(30))
        self.assertEqual(out['state']['families']['fx']['sets']['mac-a']['starts'], [])
        # control: an unconfirmed start stays (it may yet be taken back)
        out = Run(self).go(started(10, 'runner-0000beef') + scaling(30))
        self.assertEqual(len(out['state']['families']['fx']['sets']['mac-a']['starts']), 1)

    def test_docker_runner_started_is_not_proof_of_life(self):
        log = (failed(10, DOCKER_CREATE, 'linux-a') + failed(20, DOCKER_CREATE, 'linux-a')
               + started(25, 'runner-0000beef', 'linux-a') + failed(30, DOCKER_CREATE, 'linux-a') + tail(160, 'linux-a'))
        self.assertEqual(Run(self, {'fx': fam('docker', ('linux-a',))}).fx(log)['verdict'], 'rollback')

    def test_exited_without_a_job_counts_and_with_a_job_does_not(self):
        nojob = ''.join(removed(10 * i + 10, 'runner-0000000%d' % i, 'exited', job=False) for i in range(3))
        self.assertEqual(Run(self).fx(nojob + tail())['verdict'], 'rollback')
        withjob = ''.join(removed(10 * i + 10, 'runner-0000000%d' % i, 'exited', result=None) for i in range(3))
        self.assertEqual(Run(self).fx(withjob + tail())['verdict'], 'none')

    def test_the_exited_warning_alone_is_unknown(self):
        warns = ''.join(exited_warn(10 * i + 10, 'runner-0000000%d' % i) for i in range(3))
        self.assertEqual(Run(self).fx(warns + tail())['verdict'], 'none')


class SameSecond(unittest.TestCase):
    def test_a_proof_in_the_same_second_as_the_third_failure_is_between_in_both_orders(self):
        for proof_first in (True, False):
            third, proof = failed(30, OTHER), removed(30, 'runner-0000beef', 'job-completed')
            log = failed(10, OTHER) + failed(20, OTHER) + (proof + third if proof_first else third + proof) + tail()
            self.assertEqual(Run(self).fx(log)['verdict'], 'none', proof_first)

    def test_a_proof_in_the_same_second_as_the_first_failure_is_between_in_both_orders(self):
        proofs = {'job': removed(30, 'runner-0000beef', 'job-completed'), 'start': started(30, 'runner-0000beef')}
        for kind, proof in proofs.items():
            for proof_first in (True, False):
                first = failed(30, OTHER)
                log = (proof + first if proof_first else first + proof) + failed(40, OTHER) + failed(50, OTHER) + tail(180)
                self.assertEqual(Run(self).fx(log)['verdict'], 'none', (kind, proof_first))

    def test_control_the_proof_a_second_before_the_first_failure(self):
        log = removed(9, 'runner-0000beef', 'job-completed') + three(lambda i: OTHER)
        self.assertEqual(Run(self).fx(log)['verdict'], 'rollback')

    def test_a_failure_is_judged_only_once_the_log_is_settle_past_it(self):
        r = Run(self)
        log = failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + scaling(149) + scaling(150)
        self.assertEqual(r.fx(log)['verdict'], 'none')                     # 149 is read: 119 s past the third
        self.assertEqual(r.fx(scaling(151), now=r.now + 10)['verdict'], 'rollback')   # 150 is read: 120 s past it

    def test_control_the_proof_arrives_in_the_next_pass_in_the_same_second(self):
        r = Run(self)
        self.assertEqual(r.fx(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER))['verdict'], 'none')
        self.assertEqual(r.fx(removed(30, 'runner-0000beef', 'job-completed') + tail())['verdict'], 'none')


def real_seq():
    """hz-cut.log:55-59, the Linux host's real text: a runner started, its exited WARN, `Runner removed reason=exited`
    with no jobId, then `Job started|completed for unknown runner (already removed?) runnerName=` it, 13 s later: the
    runner ran a job (PLAN D6 AMENDMENT, S2-CHECKLIST)."""
    seq = fixture('hz-cut.log').split('\n')[54:59]
    assert 'Runner started name=runner-58c119b8' in seq[0] and 'reason=exited' in seq[2], seq
    assert 'Job started for unknown runner' in seq[3] and 'Job completed for unknown runner' in seq[4], seq
    return seq


def shifted(lines, k, unknown_delay=0, rename=None):
    """lines moved k x 5 min later, the runner named ...b<k> (the unknown-runner lines another name with rename), the
    unknown-runner lines unknown_delay s later still."""
    out = []
    for l in lines:
        m = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(.*)$', l)
        late = 'for unknown runner' in l
        when = (datetime.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
                + datetime.timedelta(minutes=5 * k, seconds=unknown_delay if late else 0))
        name = rename if (late and rename) else 'runner-58c119b%d' % k
        out.append(when.strftime('%Y-%m-%d %H:%M:%S') + m.group(2).replace('runner-58c119b8', name))
    return out


REAL_TAIL = '2026-10-26 02:00:00 INFO linux-b: Scaling up runner currentCount=0 desiredCount=1\n' \
            '2026-10-26 02:00:01 INFO linux-b: Scaling up runner currentCount=0 desiredCount=1\n'


class Settle(unittest.TestCase):
    """SETTLE (PLAN D6): a counted failure is settled only when no proof of life can still arrive for it — the log has
    moved SETTLE (120 s) of log time past it, or the log is quiet (nothing held) and a later pass's `now` is 120 s or
    more past the `now` of the pass that read it. R1 judges only settled failures; a proof of life is between the
    failures it falls among (same second = between), never one that comes after a run."""

    def test_codex_f2_a_late_same_second_proof_after_another_sets_later_second(self):
        log = (failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + scaling(31, 'mac-b')
               + removed(30, 'runner-0000beef', 'job-completed') + tail())
        self.assertEqual(Run(self).fx(log)['verdict'], 'none')

    def test_control_an_unknown_record_in_its_place_rolls_back(self):
        log = (failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + scaling(31, 'mac-b')
               + charm(t(30), 'INFO', 'mac-a', 'Pool status', [('name', 'runner-0000beef')]) + tail())
        self.assertEqual(Run(self).fx(log)['verdict'], 'rollback')

    def test_out_of_order_across_a_pass_boundary(self):
        # the builder's named edge: the proof of second 30 is read in the next pass, after a record of second 40
        r = Run(self)
        self.assertEqual(r.fx(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + scaling(40) + scaling(41))
                         ['verdict'], 'none')
        self.assertEqual(r.fx(removed(30, 'runner-0000beef', 'job-completed') + tail())['verdict'], 'none')

    def test_control_a_proof_after_the_run_does_not_take_it_back(self):
        log = failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + removed(100, 'runner-0000beef', 'job-completed')
        self.assertEqual(Run(self).fx(log + tail(200))['verdict'], 'rollback')
        # also when the run settles in a later pass than the proof was read in
        r = Run(self)
        self.assertEqual(r.fx(log + scaling(101))['verdict'], 'none')     # 100 is read: 70 s past the third
        self.assertEqual(r.fx(tail(200))['verdict'], 'rollback')

    def test_a_quiet_log_settles_by_the_glue_clock(self):
        r = Run(self)
        self.assertEqual(r.fx(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER))['verdict'], 'none')
        self.assertEqual(r.fx('', now=r.now + 119)['verdict'], 'none')     # the third is held, then quiet 119 s
        self.assertEqual(r.fx('', now=r.now + 1)['verdict'], 'rollback')   # read after 120 s quiet: settled

    def docker(self):
        return {'fx': fam('docker', ('linux-b',))}

    def test_opus_f3_the_real_sequence_three_times_is_no_r1(self):
        seq = real_seq()
        log = '\n'.join(sum((shifted(seq, k) for k in range(3)), [])) + '\n' + REAL_TAIL
        out = Run(self, self.docker()).go(log)
        self.assertEqual(out['families']['fx']['verdict'], 'none', out['families']['fx'])
        self.assertEqual(counted(out, 'linux-b'), 0)

    def test_opus_f3_with_a_record_of_a_later_second_before_the_unknown_runner_lines(self):
        seq = real_seq()
        between = '2026-10-26 01:10:18 INFO linux-a: Scaling up runner currentCount=0 desiredCount=1'
        log = '\n'.join(sum((shifted(seq[:3] + [between] + seq[3:], k) for k in range(3)), [])) + '\n' + REAL_TAIL
        self.assertEqual(Run(self, self.docker()).fx(log)['verdict'], 'none')

    def test_control_without_the_unknown_runner_lines_it_rolls_back(self):
        seq = real_seq()[:3]
        log = '\n'.join(sum((shifted(seq, k) for k in range(3)), [])) + '\n' + REAL_TAIL
        r = Run(self, self.docker()).fx(log)
        self.assertEqual((r['verdict'], len(r['failures'])), ('rollback', 3))

    def test_control_an_unknown_runner_line_that_names_another_runner_is_no_proof(self):
        log = '\n'.join(sum((shifted(real_seq(), k, rename='runner-0000feed') for k in range(3)), [])) + '\n' + REAL_TAIL
        self.assertEqual(Run(self, self.docker()).fx(log)['verdict'], 'rollback')

    def test_control_an_unknown_runner_line_settle_or_later_is_no_proof(self):
        log = '\n'.join(sum((shifted(real_seq(), k, unknown_delay=120) for k in range(3)), [])) + '\n' + REAL_TAIL
        self.assertEqual(Run(self, self.docker()).fx(log)['verdict'], 'rollback')

    def test_on_tart_too(self):
        tart = {'fx': fam('tart', ('linux-b',))}
        log = '\n'.join(sum((shifted(real_seq(), k) for k in range(3)), [])) + '\n' + REAL_TAIL
        self.assertEqual(Run(self, tart).fx(log)['verdict'], 'none')
        log = '\n'.join(sum((shifted(real_seq()[:3], k) for k in range(3)), [])) + '\n' + REAL_TAIL
        self.assertEqual(Run(self, tart).fx(log)['verdict'], 'rollback')

    def test_an_exited_failure_taken_back_is_not_the_third(self):
        # the line is after the run, so as a proof alone it would not be between: the exited failure itself goes
        d = {'fx': fam('docker', ('linux-a',))}
        run_ = (failed(10, DOCKER_CREATE, 'linux-a') + failed(20, DOCKER_CREATE, 'linux-a')
                + removed(25, 'runner-0000beef', 'exited', job=False, set_='linux-a'))
        out = Run(self, d).go(run_ + unknown(38, 'runner-0000beef', 'linux-a') + tail(200, 'linux-a'))
        self.assertEqual((out['families']['fx']['verdict'], out['families']['fx']['pending']), ('none', None))
        # control: no unknown-runner line
        self.assertEqual(Run(self, d).fx(run_ + tail(200, 'linux-a'))['verdict'], 'rollback')

    def test_the_unknown_runner_line_is_proof_of_life_for_the_set(self):
        d = {'fx': fam('docker', ('linux-a',))}
        log = (failed(10, DOCKER_CREATE, 'linux-a') + failed(20, DOCKER_CREATE, 'linux-a')
               + removed(25, 'runner-0000beef', 'exited', job=False, set_='linux-a'))
        after = failed(40, DOCKER_CREATE, 'linux-a') + tail(200, 'linux-a')
        self.assertEqual(Run(self, d).fx(log + unknown(30, 'runner-0000beef', 'linux-a', 'started') + after)['verdict'],
                         'none')                         # 30 lies between 20 and 40
        self.assertEqual(Run(self, d).fx(log + after)['verdict'], 'rollback')

    def test_the_start_of_a_runner_taken_back_is_proof_again(self):
        # Tart: the start at 25 is proof between 20 and 30 once the unknown-runner line shows that runner ran a job
        log = (failed(10, OTHER) + failed(20, OTHER) + started(25, 'runner-0000beef') + failed(30, OTHER)
               + removed(40, 'runner-0000beef', 'exited', job=False))
        self.assertEqual(Run(self).fx(log + unknown(50, 'runner-0000beef') + tail(200))['verdict'], 'none')
        self.assertEqual(Run(self).fx(log + tail(200))['verdict'], 'rollback')

    def test_a_held_record_may_be_the_proof_so_the_clock_waits_for_it(self):
        d = {'fx': fam('docker', ('linux-a',))}
        r = Run(self, d)
        r.go(failed(10, DOCKER_CREATE, 'linux-a') + failed(20, DOCKER_CREATE, 'linux-a')
             + removed(25, 'runner-0000beef', 'exited', job=False, set_='linux-a') + scaling(30, 'linux-a'))
        # 600 s later the log has moved only to 30 and holds the unknown-runner line: nothing is settled
        self.assertEqual(r.fx(unknown(38, 'runner-0000beef', 'linux-a'))['verdict'], 'none')
        out = r.go('')                                   # quiet: the held line is read, the exited failure taken back
        self.assertEqual((out['families']['fx']['verdict'], out['families']['fx']['pending']), ('none', None))


class Retired(unittest.TestCase):
    def test_deprecated_on_tart_stops_and_is_not_counted(self):
        r = Run(self).fx(three(lambda i: right_after('runner-0000000%d' % i, RETIRED)))
        self.assertEqual(r['verdict'], 'stop', r)
        self.assertEqual(r['stops'][0]['stop'], 'PINNED RUNNER RETIRED')

    def test_one_deprecated_record_is_enough(self):
        r = Run(self).fx(failed(10, right_after('runner-00000001', RETIRED)) + tail())
        self.assertEqual(r['verdict'], 'stop')

    def test_control_on_docker_it_is_any_other_text(self):
        r = Run(self, {'fx': fam('docker', ('linux-a',))}).fx(three(lambda i: 'failed to start runner: ' + RETIRED,
                                                                     'linux-a'))
        self.assertEqual(r['verdict'], 'rollback')


class Shim(unittest.TestCase):
    def test_a_refusal_in_the_start_failure_stops_and_is_not_counted(self):
        err = lambda i: 'failed to clone VM: tart clone base runner-0000000%d: exit status 1: %s' % (i, SHIM)
        r = Run(self).fx(three(err))
        self.assertEqual(r['verdict'], 'stop', r)
        self.assertEqual(r['stops'][0]['stop'], 'SHIM REFUSED')
        self.assertIn('free disk below the floor: 93 GiB < 100 GiB', r['stops'][0]['reason'])

    def vm_refused(self, sec, vm):
        return charm(t(sec), 'ERRO', 'mac-a', 'VM exited unexpectedly',
                     [('name', vm), ('error', 'tart run %s --no-graphics: exit status 1: %s' % (vm, SHIM))])

    def agent(self, vm):
        return 'guest agent not ready on %s: context deadline exceeded' % vm

    def test_a_refused_vm_and_its_start_failure_pair_by_name_across_passes(self):
        r = Run(self)
        r.fx(self.vm_refused(10, 'runner-00000001') + self.vm_refused(11, 'runner-00000002')
             + self.vm_refused(12, 'runner-00000003'))
        out = r.fx(''.join(failed(20 + i, self.agent('runner-0000000%d' % (i + 1))) for i in range(3)) + tail())
        self.assertEqual(out['verdict'], 'stop', out)
        self.assertEqual(out['stops'][0]['stop'], 'SHIM REFUSED')

    def test_control_start_failures_of_other_vms_count(self):
        r = Run(self)
        r.fx(self.vm_refused(10, 'runner-00000001'))
        out = r.fx(''.join(failed(20 + i, self.agent('runner-0000000%d' % (i + 5))) for i in range(3)) + tail())
        self.assertEqual(out['verdict'], 'rollback', out)

    def test_no_stop_takes_r1_back(self):
        r = Run(self)
        r.fx(self.vm_refused(10, 'runner-00000001'))
        out = r.fx(three(lambda i: OTHER, start=20))
        self.assertEqual(out['verdict'], 'rollback')
        self.assertEqual(out['stops'][0]['stop'], 'SHIM REFUSED')


class Ownership(unittest.TestCase):
    def test_a_stable_process_keeps_its_evidence_across_passes(self):
        r = Run(self)
        r.fx(failed(10, OTHER) + failed(20, OTHER) + scaling(25))
        self.assertEqual(r.fx(failed(30, OTHER) + tail())['verdict'], 'rollback')

    def test_text_of_an_unseen_process_counts_neither_way(self):
        # P seen -> P dies -> an unseen U runs and logs -> V (=Q) seen: U's text counts neither way, and it is a gap
        r = Run(self)
        r.fx(failed(10, OTHER) + failed(20, OTHER) + scaling(25))
        self.assertEqual(r.fx(failed(30, OTHER) + failed(31, OTHER) + failed(32, OTHER) + scaling(40), before=Q)['verdict'],
                         'none')
        # counting resumes with Q: two more failures do not join the ones before the gap
        self.assertEqual(r.fx(failed(50, OTHER) + failed(60, OTHER) + scaling(70), before=Q)['verdict'], 'none')
        self.assertEqual(r.fx(failed(80, OTHER) + tail(200), before=Q)['verdict'], 'rollback')

    def test_a_restart_between_the_first_read_and_the_capture_makes_the_boundary_ambiguous(self):
        r = Run(self)
        r.fx('', before=P, after=Q)                     # the capture is no boundary of P nor of Q
        self.assertEqual(r.fx(three(lambda i: OTHER), before=Q)['verdict'], 'none')   # Q's first text is UNKNOWN
        self.assertEqual(r.fx(three(lambda i: OTHER, start=100), before=Q)['verdict'], 'rollback')

    def test_a_cursor_that_does_not_match_is_a_gap(self):
        r = Run(self)
        r.fx(failed(10, OTHER) + failed(20, OTHER) + scaling(25))
        self.assertEqual(r.fx(failed(30, OTHER) + scaling(40), continuous=False)['verdict'], 'none')
        out = r.go(failed(50, OTHER) + tail(200))
        self.assertEqual(out['families']['fx']['verdict'], 'none')
        self.assertEqual(out['state']['families']['fx']['gaps'], 1)

    def test_the_first_pass_counts_nothing(self):
        r = Run(self, opened=False)
        self.assertEqual(r.fx(three(lambda i: OTHER))['verdict'], 'none')
        self.assertEqual(r.fx(three(lambda i: OTHER, start=100))['verdict'], 'rollback')


R = {'pid': 6161, 'start': 1793526000}             # a third runscaler


class OwnRestart(unittest.TestCase):
    """The updater's own restart is no gap (PLAN D6: its own switches leave no gap; another family's window does not end
    X's evidence; Codex r1 F10, Opus r1 F10, G1): with facts.restart = {from: P, to: Q} matching the state's boundary
    process and this pass's process, every family the restart did not switch keeps its counts, its NOT SERVING and its
    KEEP clock while Q's config still names its candidate; the interval's own text counts neither way. A foreign
    restart still makes a gap."""

    def setUp(self):
        self.fams = {'fx': fam(sets=('mac-a',)), 'fy': fam(sets=('mac-b',), image='img-y')}
        # fy's switch: a new candidate, its line in the config Q runs
        self.fy2 = {'fx': self.fams['fx'], 'fy': fam(sets=('mac-b',), image='img-y2', version='2.340.0',
                                                       closed_at=NOW + 1800)}
        # the interval: P's tail and Q's head, with a failure and a success on fx's set that count neither way
        self.interval = (failed(50, OTHER) + removed(55, 'runner-0000cafe', 'job-completed')
                         + charm(t(60), 'INFO', None, 'Starting scale sets', [('count', 2)]) + tail(300))

    def before(self):
        r = Run(self, self.fams)                        # both windows open at P
        r.go(failed(10, OTHER) + failed(20, OTHER) + removed(25, 'runner-0000beef', 'job-completed')
             + failed(30, OTHER) + failed(35, OTHER) + scaling(40))
        return r, dict(r.state['families']['fx'])

    def restart(self, r, restart=(P, Q), lines=None):
        return r.go(self.interval, families=self.fy2, before=Q, installed=Q['start'] - 60, restart=restart,
                    lines=lines or {'mac-a': 'img-new', 'mac-b': 'img-y2'})

    def test_g1_fx_keeps_since_counts_and_failures_across_fys_restart(self):
        r, fx0 = self.before()
        self.assertEqual((fx0['succeeded'], len(fx0['sets']['mac-a']['fails'])), (1, 4))
        out = self.restart(r)
        fx1 = out['state']['families']['fx']
        for k in ('open', 'since', 'gaps', 'succeeded', 'failed', 'sets'):
            self.assertEqual(fx1[k], fx0[k], k)
        # fy's new window opens at this boundary
        fy1 = out['state']['families']['fy']
        self.assertEqual((fy1['open'], fy1['since'], fy1['version']), (True, r.now, '2.340.0'))
        # Q's own text counts from here: one more failure on mac-a makes the third since the proof at 25
        out = r.go(failed(400, OTHER) + tail(600), families=self.fy2, before=Q, installed=Q['start'] - 60,
                   lines={'mac-a': 'img-new', 'mac-b': 'img-y2'})
        self.assertEqual(out['families']['fx']['verdict'], 'rollback')

    def test_g1_the_keep_clock_stays(self):
        r, fx0 = self.before()
        self.restart(r)
        k = ok(self, 'keep', state=r.state, facts=facts(self.fy2, before=Q, installed=Q['start'] - 60,
                                                         lines={'mac-a': 'img-new', 'mac-b': 'img-y2'}),
               now=fx0['since'] + 72 * 3600)['families']['fx']
        self.assertEqual(k['verdict'], 'accept', k)

    def test_control_the_same_text_with_no_restart_fact_is_a_gap(self):
        r, fx0 = self.before()
        out = self.restart(r, restart=None)
        fx1 = out['state']['families']['fx']
        self.assertEqual((fx1['gaps'], fx1['since'], fx1['succeeded'], counted(out)), (1, r.now, 0, 0))

    def test_a_foreign_restart_is_a_gap(self):
        for rs in ((P, R), (R, Q), (Q, P)):
            r, fx0 = self.before()
            fx1 = self.restart(r, restart=rs)['state']['families']['fx']
            self.assertEqual((fx1['gaps'], fx1['since']), (1, r.now), rs)

    def test_no_carry_when_qs_config_does_not_name_the_candidate(self):
        r, fx0 = self.before()
        fx1 = self.restart(r, lines={'mac-a': 'img-hand', 'mac-b': 'img-y2'})['state']['families']['fx']
        self.assertEqual((fx1['gaps'], fx1['open']), (1, False))

    def test_a_malformed_restart_fact_cannot_decide(self):
        for bad in ({'from': P}, {'from': P, 'to': None}, {'from': {'start': 'x'}, 'to': Q}, 'P->Q', 7):
            f = facts(self.fams, before=Q)
            f['restart'] = bad
            for prog in ('idle', 'r1', 'keep', 'status'):
                rc, _, err = run(self, prog, state=[], log='', healthz=[], facts=f, now=NOW)
                self.assertNotEqual(rc, 0, (prog, bad))
                self.assertIn('%s: facts' % prog, err, (prog, bad))


class Provenance(unittest.TestCase):
    def test_installed_in_the_start_second_is_not_proven(self):
        r = Run(self, opened=False)
        r.go(installed=P['start'])
        self.assertEqual(r.fx(three(lambda i: OTHER), installed=P['start'])['verdict'], 'none')
        # control: a second earlier is proven
        r2 = Run(self, opened=False)
        r2.go(installed=P['start'] - 1)
        self.assertEqual(r2.fx(three(lambda i: OTHER), installed=P['start'] - 1)['verdict'], 'rollback')

    def test_a_config_that_does_not_name_the_candidate_counts_nothing(self):
        r = Run(self, opened=False)
        r.go(lines={'mac-a': 'img-old'})
        self.assertEqual(r.fx(three(lambda i: OTHER), lines={'mac-a': 'img-old'})['verdict'], 'none')

    def test_another_familys_lines_do_not_matter(self):
        fams = {'fx': fam(sets=('mac-a',)), 'fy': fam(sets=('mac-b',), image='img-y')}
        lines = {'mac-a': 'img-new', 'mac-b': 'img-hand'}      # fy's set runs another image: fy has no provenance
        r = Run(self, fams, opened=False)
        r.go(lines=lines)
        out = r.go(three(lambda i: OTHER) + three(lambda i: OTHER, 'mac-b', start=100), lines=lines)
        self.assertEqual(out['families']['fx']['verdict'], 'rollback')
        self.assertEqual(out['families']['fy']['verdict'], 'none')

    def test_a_new_candidate_starts_fresh_evidence(self):
        r = Run(self)
        r.fx(failed(10, OTHER) + failed(20, OTHER) + scaling(25))
        newer = {'fx': fam(version='2.340.0', image='img-newer')}
        r.go('', families=newer)
        self.assertEqual(r.go(failed(30, OTHER) + tail(), families=newer)['families']['fx']['verdict'], 'none')

    def test_a_family_with_no_candidate_leaves_the_state(self):
        r = Run(self)
        r.fx(failed(10, OTHER) + scaling(15))
        out = r.go('', families={'fx': dict(fam(), candidate=None)})
        self.assertNotIn('fx', out['state'].get('families', {}))
        self.assertEqual(out['families']['fx']['verdict'], 'none')


def counted(out, set_='mac-a'):
    """The counted failures r1's state holds for family fx's set."""
    return len(out['state']['families']['fx']['sets'].get(set_, {}).get('fails', []))


class Carry(unittest.TestCase):
    """A record cut at the pass boundary is not complete until a following record header is read: the last record of
    a pass is held to the next one, also when the text ends with a newline (Codex r1 F1). A held record is read when
    the log has been quiet for SETTLE (120 s of the glue's clock, the text unchanged) and ends with a newline."""

    def test_a_record_split_across_passes_counts_once_whole(self):
        r = Run(self)
        rec = failed(30, right_after('runner-00000003', BENIGN))
        cut = rec.index('The runner no longer')
        r.fx(failed(10, OTHER) + failed(20, OTHER) + rec[:cut])
        # the whole record is benign: not the third failure
        self.assertEqual(r.fx(rec[cut:] + tail())['verdict'], 'none')

    def test_control_the_same_split_of_a_counted_record(self):
        r = Run(self)
        rec = failed(30, right_after('runner-00000003', 'An error occurred: Access denied.'))
        cut = rec.index('An error occurred')
        r.fx(failed(10, OTHER) + failed(20, OTHER) + rec[:cut])
        self.assertEqual(r.fx(rec[cut:] + tail())['verdict'], 'rollback')

    def cuts(self, rec):
        # before the record, and after every newline of it (the last one: the record whole in the first pass)
        return [0] + [i + 1 for i, c in enumerate(rec) if c == '\n']

    def test_the_benign_record_split_at_every_newline_is_the_unsplit_verdict(self):
        rec = failed(30, right_after('runner-00000003', BENIGN))
        unsplit = Run(self)
        out = unsplit.go(failed(10, OTHER) + failed(20, OTHER) + rec + tail())
        self.assertEqual((out['families']['fx']['verdict'], counted(out)), ('none', 2))
        self.assertGreaterEqual(len(self.cuts(rec)), 9)        # the header, the key line, seven value lines
        for cut in self.cuts(rec):
            r = Run(self)
            r.go(failed(10, OTHER) + failed(20, OTHER) + rec[:cut])
            out = r.go(rec[cut:] + tail())
            self.assertEqual((out['families']['fx']['verdict'], counted(out)), ('none', 2), (cut, rec[:cut][-60:]))

    def test_control_the_counted_record_split_at_every_newline_rolls_back(self):
        rec = failed(30, right_after('runner-00000003', 'An error occurred: Access denied.'))
        for cut in self.cuts(rec):
            r = Run(self)
            r.go(failed(10, OTHER) + failed(20, OTHER) + rec[:cut])
            out = r.go(rec[cut:] + tail())
            self.assertEqual(out['families']['fx']['verdict'], 'rollback', cut)
            self.assertEqual(len(out['families']['fx']['failures']), 3, cut)

    def test_the_last_record_waits_for_a_following_header(self):
        r = Run(self)
        out = r.go(removed(10, 'runner-0000beef', 'job-completed'))
        self.assertEqual(out['state']['families']['fx']['succeeded'], 0)      # held: it may yet grow
        out = r.go(scaling(20), now=r.now + 30)
        self.assertEqual(out['state']['families']['fx']['succeeded'], 1)      # a header followed it: read

    def test_a_held_record_is_read_when_the_log_is_quiet_for_settle(self):
        r = Run(self)
        r.go(removed(10, 'runner-0000beef', 'job-completed'))
        out = r.go('', now=r.now + 119)
        self.assertEqual(out['state']['families']['fx']['succeeded'], 0)      # quiet for 119 s: still held
        out = r.go('', now=r.now + 1)
        self.assertEqual(out['state']['families']['fx']['succeeded'], 1)      # quiet for 120 s: read
        self.assertEqual(out['state']['carry'], '')

    def test_control_a_record_that_grows_is_not_quiet(self):
        r = Run(self)
        rec = failed(30, right_after('runner-00000003', BENIGN))
        cut = rec.index('  │ The runner no longer')
        r.go(failed(10, OTHER) + failed(20, OTHER) + rec[:cut])
        out = r.go(rec[cut:], now=r.now + 600)          # it grew in this pass: the 120 s start again
        self.assertNotEqual(out['state']['carry'], '')
        out = r.go('', now=r.now + 60)                  # quiet for 60 s since it grew (660 s since it was first held)
        self.assertNotEqual(out['state']['carry'], '')
        out = r.go('', now=r.now + 60)                  # quiet for 120 s: read whole, benign
        self.assertEqual(out['state']['carry'], '')
        self.assertEqual((out['families']['fx']['verdict'], counted(out)), ('none', 2))

    def test_a_partial_last_line_is_held_until_the_log_is_quiet_for_settle(self):
        r = Run(self)
        rec = removed(10, 'runner-0000beef', 'job-completed')
        r.go(rec[:-20])
        out = r.go('', now=r.now + 119)
        self.assertEqual((out['state']['carry'], out['state']['families']['fx']['succeeded']), (rec[:-20], 0))
        out = r.go('', now=r.now + 1)                   # quiet for 120 s: released, read as what it is
        self.assertEqual(out['state']['carry'], '')
        self.assertEqual(out['state']['families']['fx']['sets']['mac-a']['proofs'][-1:], [sec(10)])


def sec(s):
    """A log time of t(s) in r1's seconds (strptime | mktime: the log's time read as UTC)."""
    return int((BASE - datetime.datetime(1970, 1, 1)).total_seconds()) + s


class PartialLine(unittest.TestCase):
    """A text that ends in a partial line holds it (it may yet grow). runscaler writes each record with one write
    (internal/config/logfile.go), so a partial line still partial after the log has been quiet for SETTLE is a short
    write (a full disk): it is released and read as what it is — a proof of life when its text is one; any other
    truncated record is unknown text, never a counted failure — so the failures before it settle and R1 can come
    (Codex r2 F2, Opus r2 F4; PLAN D6: no STOP disarms R1 while a candidate is live)."""

    def quiet(self, r, n=3, dt=10000):
        return [r.fx('', now=r.now + dt)['verdict'] for _ in range(n)]

    def test_codex_r2_f2_three_failures_then_a_partial_scaling_record_reach_r1(self):
        r = Run(self)
        out = r.go(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + scaling(31)[:-1])
        self.assertEqual(out['families']['fx']['verdict'], 'none')
        out = r.go('', now=r.now + 10000)
        self.assertEqual((out['families']['fx']['verdict'], len(out['families']['fx']['failures'])), ('rollback', 3))

    def test_opus_r2_f4_a_partial_header_or_a_line_of_another_program_reach_r1(self):
        d = {'fx': fam('docker', ('linux-b',))}
        run3 = (failed(10, DOCKER_CREATE, 'linux-b') + failed(20, DOCKER_CREATE, 'linux-b')
                + failed(30, DOCKER_CREATE, 'linux-b') + scaling(31, 'linux-a'))
        for partial in ('2026-11-01 05:00:3', 'localhost:5000/example-runner@sha256:00: Pulling from example-runner'):
            r = Run(self, d)
            self.assertEqual(r.fx(run3 + partial)['verdict'], 'none', partial)
            self.assertEqual(self.quiet(r, 1, 4 * 3600), ['rollback'], partial)

    def test_control_a_partial_line_that_is_a_complete_proof_is_one(self):
        # the job completed in the third failure's second, its newline missing: proof of life between them
        r = Run(self)
        r.go(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + removed(30, 'runner-0000beef', 'job-completed')[:-1])
        self.assertEqual(self.quiet(r), ['none'] * 3)
        self.assertEqual((r.state['families']['fx']['succeeded'], r.state['families']['fx']['pending']), (1, None))
        # cut inside its attributes, after reason=job-completed: still a job completed
        r = Run(self)
        rec = removed(30, 'runner-0000beef', 'job-completed')
        r.go(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + rec[:rec.index(' repo=')])
        self.assertEqual(self.quiet(r), ['none'] * 3)

    def test_a_partial_tart_start_and_a_partial_unknown_runner_line_are_proofs_of_life(self):
        # Tart: a runner started in the third failure's second, its newline missing
        r = Run(self)
        r.go(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + started(30, 'runner-0000beef')[:-1])
        self.assertEqual(self.quiet(r), ['none'] * 3)
        # Docker: the unknown-runner line naming the runner removed reason=exited takes its failure back
        d = {'fx': fam('docker', ('linux-a',))}
        run_ = (failed(10, DOCKER_CREATE, 'linux-a') + failed(20, DOCKER_CREATE, 'linux-a')
                + removed(25, 'runner-0000beef', 'exited', job=False, set_='linux-a'))
        line = unknown(38, 'runner-0000beef', 'linux-a')
        r = Run(self, d)
        r.go(run_ + line[:-1])
        self.assertEqual(self.quiet(r), ['none'] * 3)
        # control: cut inside the runner's name, it names no runner removed so: the exited failure is the third
        r = Run(self, d)
        r.go(run_ + line[:line.index('beef')])
        self.assertEqual(self.quiet(r, 1), ['rollback'])

    def test_a_truncated_record_that_is_no_proof_of_life_is_unknown_text(self):
        # cut inside `reason=job-completed`: a removal of no known reason, no proof; the run of three reaches R1
        r = Run(self)
        rec = removed(30, 'runner-0000beef', 'job-completed')
        r.go(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + rec[:rec.index('-completed')])
        self.assertEqual(self.quiet(r, 1), ['rollback'])
        # nor does it confirm that runner's Tart start: the start stays a start
        r = Run(self)
        r.go(started(5, 'runner-0000beef') + scaling(6) + rec[:rec.index('-completed')])
        self.quiet(r, 1)
        self.assertEqual([s['n'] for s in r.state['families']['fx']['sets']['mac-a']['starts']], ['runner-0000beef'])
        # a truncated start failure is not counted: two failures and it are no R1, and nothing is pending
        r = Run(self)
        r.go(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER)[:-1])
        self.assertEqual(self.quiet(r), ['none'] * 3)
        self.assertEqual((counted(r.go('', now=r.now + 600)), r.state['families']['fx']['pending']), (2, None))

    def test_control_the_same_start_failure_with_its_newline_is_counted(self):
        r = Run(self)
        r.go(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER))
        self.assertEqual(self.quiet(r, 1), ['rollback'])

    def test_control_a_partial_line_that_completes_within_settle_is_read_whole(self):
        # Opus r2 F4's control: it completes into a job completed in the third failure's second -> no R1
        r = Run(self)
        rec = removed(30, 'runner-0000beef', 'job-completed')
        r.go(failed(10, OTHER) + failed(20, OTHER) + failed(30, OTHER) + rec[:40])
        out = r.go(rec[40:] + tail(), now=r.now + 60)
        self.assertEqual((out['families']['fx']['verdict'], out['state']['families']['fx']['succeeded']), ('none', 1))
        self.assertEqual(self.quiet(r), ['none'] * 3)


def hz(ready=True, idle=1, busy=0, assigned=1, set_='linux-a'):
    m = {'jobs_started': 5, 'jobs_completed': 4, 'desired_runners': 1}
    if assigned:
        m['assigned_jobs'] = assigned
    return {'status': 'ok', 'scale_sets': [{'name': set_, 'ready': ready, 'idle': idle, 'busy': busy, 'metrics': m}]}


class NotServing(unittest.TestCase):
    def setUp(self):
        self.fams = {'fx': fam('docker', ('linux-a',))}

    def reads(self, r, n, **kw):
        out = None
        for _ in range(n):
            out = r.go('', healthz=[hz(**kw)])
        return out['families']['fx']

    def test_thirty_minutes_of_not_serving_is_the_third_failure_connect_class(self):
        r = Run(self, self.fams)
        self.assertEqual(self.reads(r, 3)['verdict'], 'none')          # 0, 10, 20 min
        out = self.reads(r, 1)                                          # 30 min, 4 reads
        self.assertEqual((out['verdict'], out['connect_only']), ('rollback', True), out)

    def test_it_needs_three_reads_as_well_as_30_minutes(self):
        r = Run(self, self.fams)
        r.go('', healthz=[hz()], now=r.now + 600)
        self.assertEqual(r.go('', healthz=[hz()], now=r.now + 2400)['families']['fx']['verdict'], 'none')   # 2 reads, 40 min
        self.assertEqual(r.go('', healthz=[hz()], now=r.now + 600)['families']['fx']['verdict'], 'rollback')

    def test_control_a_not_ready_read_starts_the_30_minutes_again(self):
        r = Run(self, self.fams)
        self.reads(r, 2)
        self.reads(r, 1, ready=False)
        self.assertEqual(self.reads(r, 3)['verdict'], 'none')
        self.assertEqual(self.reads(r, 1)['verdict'], 'rollback')

    def test_control_a_job_completed_on_the_set_starts_it_again(self):
        r = Run(self, self.fams)
        self.reads(r, 2)
        r.go(removed(10, 'runner-0000beef', 'job-completed', set_='linux-a') + scaling(11, 'linux-a'), healthz=[hz()])
        self.assertEqual(self.reads(r, 2)['verdict'], 'none')

    def test_control_busy_or_nothing_assigned_is_serving(self):
        for kw in ({'busy': 1}, {'assigned': 0}, {'idle': 0}):
            r = Run(self, self.fams)
            self.assertEqual(self.reads(r, 5, **kw)['verdict'], 'none', kw)

    def test_a_gap_starts_it_again(self):
        r = Run(self, self.fams)
        self.reads(r, 3)
        r.go('', healthz=[hz()], continuous=False)
        self.assertEqual(self.reads(r, 2)['verdict'], 'none')

    def test_with_two_counted_failures_the_run_is_not_connect_only(self):
        r = Run(self, self.fams)
        r.go(failed(10, DOCKER_CREATE, 'linux-a') + failed(20, DOCKER_CREATE, 'linux-a') + scaling(30, 'linux-a'))
        out = self.reads(r, 4)
        self.assertEqual((out['verdict'], out['connect_only']), ('rollback', False))

    # the 30 min are measured by the reads (the first and the last NOT SERVING read 30 min or more apart), not by the
    # clock: a pass with no /healthz read adds nothing (Opus r1 F2)
    def test_opus_f2_n1_passes_with_no_read_add_nothing(self):
        r = Run(self, self.fams)
        r.go('', healthz=[hz(), hz()])                  # +0 min: two NOT SERVING reads
        r.go('', healthz=[hz(), hz()])                  # +10 min: two more
        r.go('', healthz=[])                            # +20 min: the read failed
        self.assertEqual(r.go('', healthz=[])['families']['fx']['verdict'], 'none')   # +30 min: no read

    def test_opus_f2_n2_three_reads_in_one_pass_then_a_pass_with_none_30_min_later(self):
        r = Run(self, self.fams)
        r.go('', healthz=[hz(), hz(), hz()])
        self.assertEqual(r.go('', healthz=[], now=r.now + 1800)['families']['fx']['verdict'], 'none')

    def test_control_reads_at_0_15_and_30_minutes_are_the_third_failure(self):
        r = Run(self, self.fams)
        r.go('', healthz=[hz()])
        self.assertEqual(r.go('', healthz=[hz()], now=r.now + 900)['families']['fx']['verdict'], 'none')
        out = r.go('', healthz=[hz()], now=r.now + 900)['families']['fx']
        self.assertEqual((out['verdict'], out['connect_only']), ('rollback', True))
        self.assertEqual(out['failures'][-1]['t'], 'NOT SERVING')


class Sticky(unittest.TestCase):
    def test_a_rollback_verdict_holds_for_the_candidate(self):
        r = Run(self)
        r.fx(three(lambda i: OTHER))
        self.assertEqual(r.fx(removed(100, 'runner-0000beef', 'job-completed') + scaling(110))['verdict'], 'rollback')

    # a verdict belongs to its window (the candidate's closed_at), not only to the candidate's lines (Opus r1 F6): the
    # Linux host's CONNECT-ONLY retry and `retry FAMILY` switch to the SAME lines, in a new window
    def test_opus_f6_a_retry_with_the_same_lines_and_a_new_closed_at_is_a_new_verdict(self):
        r = Run(self)
        self.assertEqual(r.fx(three(lambda i: OTHER))['verdict'], 'rollback')
        retry = {'fx': fam(closed_at=NOW + 7200)}
        out = r.go('', families=retry, now=r.now + 7200, before=Q, installed=Q['start'] - 60)
        self.assertEqual(out['families']['fx']['verdict'], 'none')
        out = r.go(scaling(1000) + tail(1100), families=retry, before=Q, installed=Q['start'] - 60)
        self.assertEqual((out['families']['fx']['verdict'], out['families']['fx']['open']), ('none', True))
        self.assertEqual(out['state']['families']['fx']['closed_at'], NOW + 7200)

    def test_control_the_same_closed_at_keeps_the_verdict_across_a_new_process(self):
        r = Run(self)
        r.fx(three(lambda i: OTHER))
        out = r.go('', now=r.now + 7200, before=Q, installed=Q['start'] - 60)
        self.assertEqual(out['families']['fx']['verdict'], 'rollback')
        self.assertEqual(r.fx(tail(1100), before=Q, installed=Q['start'] - 60)['verdict'], 'rollback')


class Formats(unittest.TestCase):
    def test_an_unknown_state_format_waits(self):
        st = {'format': 3}
        out = ok(self, 'r1', state=st, log='', healthz=[], facts=facts({'fx': fam()}), now=NOW)
        self.assertEqual((out['verdict'], out['state']), ('wait', st))

    def test_no_log_input_cannot_decide(self):
        rc, _, err = run(self, 'r1', state=[], healthz=[], facts=facts({'fx': fam()}), now=NOW)
        self.assertNotEqual(rc, 0)
        self.assertIn('r1: --rawfile log is required', err)


if __name__ == '__main__':
    unittest.main()
