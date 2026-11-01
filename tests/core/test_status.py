"""core/status.jq — the STOP table (PLAN D7) as ONE copy: each STOP's properties (candidate closed? version rejected?
does a newer release proceed alone?) and its line with the next step, for the STOPs the glue holds (facts.stops) and
the ones the core's own state holds (r1.jq's SHIM REFUSED, PINNED RUNNER RETIRED); then the evidence lines (an R1
rollback due, observing since, counted failures per set) and the date until which `back` restores the old image."""
import unittest

from tests.core.corejq import ok
from tests.core.test_r1 import NOW, fam, facts

# PLAN REV 11 D7: STOP -> (candidate closed?, version rejected?, a newer release proceeds alone?); None = the table's "—"
TABLE = {
    'check failed': (True, False, True),
    'ROLLED BACK': (True, True, True),
    'PINNED RUNNER RETIRED': (True, True, True),
    'JOBS FAIL ON THE NEW IMAGE': (False, False, False),
    'ROLLBACK FAILED': (False, None, False),
    'CI DISABLED': (False, None, False),
    'POOL DOWN': (False, None, False),
    'HAND CHANGE': (None, False, False),
    'recipe changed': (None, False, False),
    'NO BASELINE': (None, False, False),
    'NO EVIDENCE': (False, False, False),
    'NO IDLE': (False, False, False),
    'untested jq': (None, False, False),
    'SHIM REFUSED': (False, False, False),      # D6 names it ("STOP with the shim's reason"); D7 has no row: see README
}


def status(test, stops=(), state=None, families=None, host='studio'):
    f = facts(families or {'fx': fam()})
    f['host'] = host
    f['stops'] = list(stops)
    return ok(test, 'status', state=state if state is not None else [], facts=f, now=NOW)


def stop(name, **detail):
    return {'family': 'fx', 'stop': name, 'version': '2.339.0', 'user': 'ci', 'detail': detail}


class Table(unittest.TestCase):
    def test_every_stop_of_the_table_has_its_properties(self):
        for name, (closes, rejects, newer) in TABLE.items():
            s = status(self, [stop(name)])['stops'][0]
            self.assertEqual((s['closes_candidate'], s['rejects'], s['newer_proceeds']), (closes, rejects, newer), name)
            self.assertTrue(s['known'], name)
            self.assertTrue(s['line'].startswith('fx: STOP %s (runner 2.339.0)' % name), s['line'])

    def test_a_connect_only_rollback_rejects_only_after_its_retry(self):
        s = status(self, [stop('ROLLED BACK', connect_only=True, failures=[])])['stops'][0]
        self.assertEqual(s['rejects'], 'after-retry')
        self.assertIn('one retry after 1 h', s['line'])

    def test_control_an_unknown_stop_is_named_not_guessed(self):
        s = status(self, [stop('SOMETHING NEW')])['stops'][0]
        self.assertFalse(s['known'])
        self.assertEqual((s['closes_candidate'], s['rejects'], s['newer_proceeds']), (None, None, False))
        self.assertIn('this core does not know this STOP', s['line'])


class Lines(unittest.TestCase):
    def line(self, *a, **kw):
        return status(self, [stop(*a, **kw)])['stops'][0]['line']

    def test_rolled_back_names_the_counted_failures_and_retry(self):
        l = self.line('ROLLED BACK', failures=[{'t': '2026-11-01 05:00:10', 'c': True, 'x': 'runner process exited'}] * 3)
        self.assertIn('3 counted failures', l)
        self.assertIn('runner process exited', l)
        self.assertIn('`runner-updater retry fx`', l)

    def test_check_failed_names_the_failing_line_and_retry(self):
        l = self.line('check failed', text='golden-gate: RED liveapp-mac-golden-20261101')
        self.assertIn('golden-gate: RED', l)
        self.assertIn('as ci: `runner-updater retry fx`', l)

    def test_check_failed_at_the_linux_build_names_the_build_line_and_its_user(self):
        l = status(self, [dict(stop('check failed', text='02-d1.sh build: step 5 failed', step='build',
                                    build_user='builder'), user='scaler')], host='hz')['stops'][0]['line']
        self.assertIn('as builder: `runner-updater build 2.339.0`', l)
        # control: the same STOP at another step is a retry by the stop's own user
        l2 = status(self, [dict(stop('check failed', text='validate: NON-API'), user='scaler')], host='hz')['stops'][0]['line']
        self.assertIn('as scaler: `runner-updater retry fx`', l2)

    def test_jobs_fail_names_the_counts_back_and_retry(self):
        l = self.line('JOBS FAIL ON THE NEW IMAGE', counts={'succeeded': 0, 'completions': 7, 'failed': 7, 'canceled': 2})
        self.assertIn('7 completed, 0 succeeded, 7 failed, 2 canceled', l)
        self.assertIn('`runner-updater back fx`', l)
        self.assertIn('`runner-updater retry fx` to keep it', l)

    def test_hand_stops_name_the_failing_step_and_the_hand_line(self):
        for name in ('ROLLBACK FAILED', 'CI DISABLED', 'POOL DOWN'):
            l = self.line(name, text='runner-enable: REFUSE stamp mismatch', hand='/Users/ci/bin/runner-enable')
            self.assertIn('runner-enable: REFUSE stamp mismatch', l, name)
            self.assertIn('`/Users/ci/bin/runner-enable`', l, name)

    def test_rebuild_rows(self):
        for name in ('HAND CHANGE', 'recipe changed', 'NO BASELINE'):
            self.assertIn('`runner-updater rebuild fx`', self.line(name), name)

    def test_no_evidence_no_idle_untested_jq(self):
        self.assertIn('`runner-updater retry fx`', self.line('NO EVIDENCE'))
        self.assertIn('`runner-updater switch-now fx`', self.line('NO IDLE', text='set mac-b: busy 1'))
        l = self.line('untested jq', jq={'version': 'jq-1.9', 'path': '/opt/x/jq'})
        self.assertIn('JQ=/opt/x/jq python3 -I -m unittest discover -s tests/core -t .', l)
        self.assertIn('jq-1.9', l)

    def test_retired_says_a_newer_release_is_needed(self):
        self.assertIn('a newer runner release', self.line('PINNED RUNNER RETIRED'))

    def test_shim_refused_names_the_reason_and_the_runbook(self):
        l = self.line('SHIM REFUSED', reason='set mac-a: free disk below the floor: 93 GiB < 100 GiB')
        self.assertIn('free disk below the floor', l)
        self.assertIn('docs/operations.md, "When the shim refuses"', l)


def core_state(**ev):
    e = {'version': '2.339.0', 'lines': {'mac-a': 'img-new'}, 'open': True, 'since': NOW - 3600, 'gaps': 1,
         'succeeded': 2, 'failed': 1, 'canceled': 0, 'other': 0,
         'sets': {'mac-a': {'fails': [{'t': '2026-11-01 05:00:10', 'c': True, 'x': 'x'}], 'starts': [], 'proof': None,
                            'ns': None, 'completed': False}},
         'verdict': None, 'stops': []}
    e.update(ev)
    return {'format': 1, 'families': {'fx': e}}


class CoreState(unittest.TestCase):
    def test_the_cores_own_stops_are_listed_once(self):
        st = core_state(stops=[{'stop': 'SHIM REFUSED', 'reason': 'set mac-a: free disk below the floor'}])
        out = status(self, [], state=st)
        self.assertEqual([s['stop'] for s in out['stops']], ['SHIM REFUSED'])
        out2 = status(self, [stop('SHIM REFUSED', reason='set mac-a: free disk below the floor')], state=st)
        self.assertEqual([s['stop'] for s in out2['stops']], ['SHIM REFUSED'])

    def test_an_r1_rollback_due_is_a_line(self):
        st = core_state(verdict={'verdict': 'rollback', 'set': 'mac-a', 'connect_only': True,
                                 'failures': [{'t': 't', 'c': True, 'x': 'x'}] * 3})
        self.assertTrue(any(l.startswith('fx: R1: a rollback is due (set mac-a, 3 counted failures, connect-class only)')
                            for l in status(self, [], state=st)['lines']))

    def test_the_evidence_line(self):
        lines = status(self, [], state=core_state())['lines']
        self.assertIn('fx: runner 2.339.0: observing since 2026-11-01 10:00 UTC, 1 gap; 2 succeeded of 3 completed; '
                      'set mac-a: 1 counted failure since its last proof of life', lines)

    def test_back_until(self):
        fams = {'fx': dict(fam(), candidate=None, back_until=NOW + 7 * 86400)}
        lines = status(self, [], families=fams)['lines']
        self.assertIn('fx: `runner-updater back fx` restores the previous image until 2026-11-08 11:00 UTC', lines)

    def test_stops_come_first_then_evidence(self):
        out = status(self, [stop('NO IDLE', text='set mac-b: busy 1')], state=core_state())
        self.assertTrue(out['lines'][0].startswith('fx: STOP NO IDLE'))
        self.assertTrue(out['lines'][1].startswith('fx: runner 2.339.0: observing'))

    def test_an_unknown_state_format_waits(self):
        self.assertEqual(status(self, [], state={'format': 0})['verdict'], 'wait')


if __name__ == '__main__':
    unittest.main()
