"""core/idle.jq — IDLE (PLAN D5): may the host's runscaler be stopped now. Two /healthz reads, over EVERY set the host
serves (facts.sets and every set a read lists), not only the family's: each set present with `metrics` on both reads,
`ready` on both (a set read not ready for 24 h is excused from READINESS only), and the eight counts 0 on both
(an absent key reads 0). Each trigger has a control that comes out the other way. fixtures/hz-healthz-busy.json is a
real read of the Linux host's /healthz (names replaced): one set busy, so not idle; its quiet copy is the control."""
import copy
import json
import unittest

from tests.core.corejq import fixture, ok, run

NOW = 1793530800          # 2026-11-01 11:00:00 UTC
DAY = 86400


def real():
    return json.loads(fixture('hz-healthz-busy.json'))


def quiet():
    r = real()
    for s in r['scale_sets']:
        s['idle'] = s['busy'] = 0
        s['metrics'] = {'jobs_started': 98, 'jobs_completed': 98, 'desired_runners': 0}
    return r


def facts(sets=('linux-a', 'linux-b')):
    return {'format': 1, 'host': 'hz', 'sets': list(sets)}


def with_set(read, name, **kw):
    read = copy.deepcopy(read)
    for s in read['scale_sets']:
        if s['name'] == name:
            for k, v in kw.items():
                if k in ('available_jobs', 'assigned_jobs', 'running_jobs', 'desired_runners'):
                    s['metrics'][k] = v
                elif v is None:
                    s.pop(k, None)
                else:
                    s[k] = v
    return read


def idle(test, reads, state=None, f=None, now=NOW):
    return ok(test, 'idle', healthz=reads, facts=f or facts(), state=state if state is not None else [], now=now)


class Idle(unittest.TestCase):
    def test_control_all_sets_ready_and_zero_on_both_reads_is_idle(self):
        out = idle(self, [quiet(), quiet()])
        self.assertEqual(out['verdict'], 'idle', out)

    def test_the_real_read_with_a_busy_set_is_not_idle(self):
        out = idle(self, [real(), real()])
        self.assertEqual(out['verdict'], 'not-idle')
        self.assertTrue(any('linux-a' in l and 'busy 2' in l for l in out['lines']), out['lines'])

    def test_each_count_on_either_read_blocks(self):
        for key in ('idle', 'busy', 'provisioning', 'removing', 'available_jobs', 'assigned_jobs', 'running_jobs',
                    'desired_runners'):
            for which in (0, 1):
                reads = [quiet(), quiet()]
                reads[which] = with_set(reads[which], 'linux-b', **{key: 1})
                out = idle(self, reads)
                self.assertEqual(out['verdict'], 'not-idle', (key, which))
                self.assertTrue(any(l.startswith('linux-b:') for l in out['lines']), (key, out['lines']))

    def test_another_familys_set_blocks_the_window(self):
        # linux-b is not the family being switched: IDLE still covers it (a stop drains every set)
        out = idle(self, [quiet(), with_set(quiet(), 'linux-b', busy=1)])
        self.assertEqual(out['verdict'], 'not-idle')

    def test_a_configured_set_absent_from_a_read_is_not_idle(self):
        r = quiet()
        r['scale_sets'] = [s for s in r['scale_sets'] if s['name'] != 'linux-b']
        self.assertEqual(idle(self, [quiet(), r])['verdict'], 'not-idle')
        # control: the same read when linux-b is not configured and no read lists it
        self.assertEqual(idle(self, [r, r], f=facts(['linux-a']))['verdict'], 'idle')

    def test_a_set_a_read_lists_but_the_config_does_not_still_counts(self):
        out = idle(self, [quiet(), with_set(quiet(), 'linux-b', busy=1)], f=facts(['linux-a']))
        self.assertEqual(out['verdict'], 'not-idle')

    def test_a_set_without_metrics_is_not_idle(self):
        self.assertEqual(idle(self, [quiet(), with_set(quiet(), 'linux-b', metrics=None)])['verdict'], 'not-idle')

    def test_not_ready_on_one_read_is_not_idle(self):
        out = idle(self, [quiet(), with_set(quiet(), 'linux-b', ready=False)])
        self.assertEqual(out['verdict'], 'not-idle')

    def test_one_read_is_never_idle(self):
        out = idle(self, [quiet()])
        self.assertEqual(out['verdict'], 'not-idle')
        self.assertIn('two reads', out['reason'])

    def test_the_last_two_reads_decide(self):
        self.assertEqual(idle(self, [real(), quiet(), quiet()])['verdict'], 'idle')
        self.assertEqual(idle(self, [quiet(), quiet(), real()])['verdict'], 'not-idle')


class Readiness24h(unittest.TestCase):
    def not_ready(self, read):
        return with_set(read, 'linux-b', ready=False)

    def test_a_set_not_ready_for_24h_is_excused_from_readiness(self):
        st = {'format': 1, 'not_ready_since': {'linux-b': NOW - DAY}}
        out = idle(self, [self.not_ready(quiet()), self.not_ready(quiet())], state=st)
        self.assertEqual(out['verdict'], 'idle', out)
        self.assertTrue(any('linux-b' in l and 'not ready since' in l for l in out['lines']), out['lines'])

    def test_control_not_ready_for_less_than_24h_is_not_excused(self):
        st = {'format': 1, 'not_ready_since': {'linux-b': NOW - DAY + 1}}
        out = idle(self, [self.not_ready(quiet()), self.not_ready(quiet())], state=st)
        self.assertEqual(out['verdict'], 'not-idle')

    def test_an_excused_set_keeps_its_counts(self):
        # REV 11: the exception waives readiness only; its runner and job counts still count
        st = {'format': 1, 'not_ready_since': {'linux-b': NOW - 2 * DAY}}
        for kw in ({'idle': 1}, {'assigned_jobs': 1}):
            reads = [with_set(self.not_ready(quiet()), 'linux-b', **kw)] * 2
            self.assertEqual(idle(self, reads, state=st)['verdict'], 'not-idle', kw)

    def test_an_excused_set_without_metrics_is_not_idle(self):
        st = {'format': 1, 'not_ready_since': {'linux-b': NOW - 2 * DAY}}
        reads = [with_set(self.not_ready(quiet()), 'linux-b', metrics=None)] * 2
        self.assertEqual(idle(self, reads, state=st)['verdict'], 'not-idle')

    def test_the_state_records_when_a_set_was_first_read_not_ready_and_forgets_it_when_ready(self):
        out = idle(self, [self.not_ready(quiet())])
        self.assertEqual(out['state']['not_ready_since'], {'linux-b': NOW})
        out2 = idle(self, [self.not_ready(quiet())], state=out['state'], now=NOW + 600)
        self.assertEqual(out2['state']['not_ready_since'], {'linux-b': NOW})
        out3 = idle(self, [quiet()], state=out2['state'], now=NOW + 1200)
        self.assertEqual(out3['state']['not_ready_since'], {})

    def test_a_set_absent_from_the_read_is_not_tracked(self):
        r = quiet()
        r['scale_sets'] = [s for s in r['scale_sets'] if s['name'] != 'linux-b']
        st = {'format': 1, 'not_ready_since': {'linux-b': NOW - DAY}}
        self.assertEqual(idle(self, [r], state=st)['state']['not_ready_since'], {'linux-b': NOW - DAY})


class Formats(unittest.TestCase):
    def test_an_unknown_state_format_waits_and_keeps_the_state(self):
        st = {'format': 2, 'whatever': 1}
        out = idle(self, [quiet(), quiet()], state=st)
        self.assertEqual(out['verdict'], 'wait')
        self.assertEqual(out['state'], st)
        self.assertTrue(out['lines'])

    def test_an_unknown_facts_format_cannot_decide(self):
        rc, out, err = run(self, 'idle', healthz=[quiet(), quiet()], facts={'format': 9, 'sets': []}, state=[], now=NOW)
        self.assertNotEqual(rc, 0)
        self.assertIn('idle: facts', err)
        # control: format 1 decides
        self.assertEqual(run(self, 'idle', healthz=[quiet(), quiet()], facts=facts(), state=[], now=NOW)[0], 0)

    def test_no_healthz_input_cannot_decide(self):
        rc, _, err = run(self, 'idle', facts=facts(), state=[], now=NOW)
        self.assertNotEqual(rc, 0)
        self.assertIn('idle: --slurpfile healthz is required', err)


if __name__ == '__main__':
    unittest.main()
