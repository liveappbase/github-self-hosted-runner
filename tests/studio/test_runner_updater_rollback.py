"""bin/runner-updater-window's ROLLBACK WINDOW (PLAN D5 ROLLBACK precondition, CONFIG EDIT's rollback rule, RECOVER of
a rollback; D6 ROLLBACK, DELETION, CONNECT-ONLY), `back FAMILY` (D6 AFTER ACCEPT, D7, the D10 rehearsal) and `retry
FAMILY` (D2 REJECTED, D7).

The rig is test_runner_updater_window's (Win) with the family switched: the config names NEW for mac-a, the state's
candidate is NEW (runner V2) and its previous OLD (runner V0). ru_rollback FAMILY REASON SINCE, the function 4b's pass
calls on an R1 verdict, is called by a copy of runner-updater whose `pass` calls it first (RU_ROLLBACK = REASON, r1's
verdict of the family; RU_SINCE), after the lock, the state and RECOVER, as a pass would.
"""
import json
import os
import time
import unittest

from tests.studio.test_runner_updater import config, read_text
from tests.studio.test_runner_updater_recover import (assert_closed, assert_runs, cut, killed, n_disable, stops,
                                                      three_passes)
from tests.studio.test_runner_updater_state import cand, fam, lines_of, state, stop
from tests.studio.test_runner_updater_window import FAM, KILLED, OLD, SHA0, V0, Win, sha

NEW = 'liveapp-mac-golden-20261020'
V2 = '2.339.0'
SHA2 = '2' * 64
FAILS = [{'t': '2026-11-01 05:0%d:00' % i, 'c': False, 'x': 'Failed to start runner on runner-000%d' % i}
         for i in (1, 2, 3)]
VERDICT = {'set': 'mac-a', 'failures': FAILS, 'connect_only': False,
           'reason': 'R1 on set mac-a: 3 counted failures with no proof of life between them'}
CONNECT = dict(VERDICT, connect_only=True, failures=[dict(f, c=True) for f in FAILS],
               reason='R1 on set mac-a: 3 counted failures with no proof of life between them (connect-class only)')
CELL = '''rollback_cell() {
  local rc
  load_state
  run_recover
  jq_tested
  source $RELBIN/runner-updater-window || exit 9
  ru_rollback ${RU_FAMILY:-mac-golden} "$RU_ROLLBACK" ${RU_SINCE:-$EPOCHSECONDS}
  rc=$?
  print -r -- "rollback rc $rc"
  exit $rc
}
'''


def switched(**kw):
    """the family after its switch to NEW: candidate NEW (V2), previous OLD"""
    f = dict(candidate=cand(V2, {'mac-a': NEW}, int(time.time()) - 3600), previous={'mac-a': OLD})
    f.update(kw)
    return fam(**f)


def rb_win(test, families=None, images=None, cfg=None, **kw):
    w = Win(test, cfg=cfg if cfg is not None else config((('mac-a', NEW),)),
            s=state(on=True, families=families or {FAM: switched()}, images=images or {OLD: V0, NEW: V2}), **kw)
    w.sb.write(os.path.join(w.vms, NEW), '')
    w.driver = w.r.copy('rb-driver', [
        ('  (pass) do_pass ;;', '  (pass) [[ -n ${RU_ROLLBACK-} ]] && rollback_cell; do_pass ;;'),
        ('# ---- protect: the protected list, written from the state', CELL + '# ---- protect: the protected list, '
                                                                      'written from the state')])
    return w


def rollback(w, reason=VERDICT, since=None, env=None):
    e = {'RU_ROLLBACK': json.dumps(reason) if not isinstance(reason, str) else reason}
    if since is not None:
        e['RU_SINCE'] = str(since)
    e.update(env or {})
    return w.r.cmd('pass', ok=False, env=e, script=w.driver)


def actions(w):
    p = w.u.actions
    return lines_of(p) if os.path.exists(p) else []


class TestRollback(unittest.TestCase):
    """ONE rollback window: no idle wait, PRE-VALIDATE of its TARGET (the candidate's previous image), runner-disable
    (the drain), the config edit under the runner lock, enable, the target runs; the close."""

    def test_an_automatic_rollback(self):
        w = rb_win(self)
        res = rollback(w)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('rollback rc 0', res.stdout)
        old = config((('mac-a', OLD),)).encode()
        assert_runs(self, w, old)
        self.assertEqual((n_disable(w), len(w.enables())), (1, 1))
        self.assertEqual(w.r.curl_calls(), [])                   # no idle wait: no /healthz read
        k = w.keys()
        self.assertEqual(k[:5], ['window', 'family', 'kind', 'command', 'version'])
        self.assertEqual((w.value('kind'), w.value('version'), w.value('reject')), ('rollback', V2, V2))
        self.assertEqual(w.value('target'), 'mac-a=' + OLD)
        self.assertEqual(k[-5:], ['running', 'stop', 'pin-rule', 'state-write', 'closed'])
        self.assertEqual(w.value('state-write'), 'rolled')
        self.assertEqual(w.validates()[0][2], sha(old))          # PRE-VALIDATE read the TARGET
        f = w.family()
        self.assertEqual((f['candidate'], f['previous'], f['back_until'], f['rejected']), (None, None, None, [V2]))
        (s,) = f['stops']
        self.assertEqual((s['stop'], s['version']), ('ROLLED BACK', V2))
        self.assertEqual((len(s['detail']['failures']), s['detail']['connect_only']), (3, False))
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V0, SHA0))
        # the image it left: deleted by its recorded name, journaled first in ACTIONS
        self.assertFalse(os.path.exists(os.path.join(w.vms, NEW)))
        self.assertEqual(actions(w), ['delete ' + NEW])
        self.assertNotIn(NEW, lines_of(w.u.protected))
        st = w.status()
        self.assertIn('\n%s: STOP ROLLED BACK (runner %s): 3 counted failures, the last: Failed to start runner on '
                      'runner-0003. Next: `runner-updater retry %s`' % (FAM, V2, FAM), st)
        three_passes(self, w)

    def test_pre_validate_non_api_is_rollback_failed_with_no_drain(self):
        w = rb_win(self)
        w.validate('refuse', call=1)                             # the target image is not on this host
        res = rollback(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP ROLLBACK FAILED: pre-window validate (pre) is NON-API', res.stdout)
        self.assertEqual((n_disable(w), w.enables(), os.path.exists(w.u.window)), (0, [], False))
        self.assertEqual(w.config_now(), w.pre)
        self.assertTrue(os.path.exists(w.r.flag))
        f = w.family()
        self.assertEqual(([s['stop'] for s in f['stops']], f['candidate']['version']), (['ROLLBACK FAILED'], V2))
        self.assertIn('Next, by hand: `runner-updater retry %s`' % FAM, w.status())

    def test_control_pre_validate_api_only_three_times_counts_as_pass(self):
        w = rb_win(self)
        for n in (1, 2, 3):
            w.validate('api', call=n)
        self.assertEqual(rollback(w).returncode, 0)

    def test_pre_validate_unknown_is_pending_then_rollback_failed_after_2_h(self):
        w = rb_win(self)
        w.validate('unknown')
        res = rollback(w, since=int(time.time()) - 600)
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn('runner-updater: rollback pending: pre-window validate (pre) is UNKNOWN', res.stdout)
        self.assertEqual((n_disable(w), stops(w)), (0, []))
        res = rollback(w, since=int(time.time()) - 7200)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP ROLLBACK FAILED: pre-window validate (pre) is UNKNOWN', res.stdout)
        self.assertEqual((n_disable(w), stops(w)), (0, ['ROLLBACK FAILED']))

    def test_ci_disabled_by_a_person_nothing_restarts(self):
        w = rb_win(self)
        os.remove(w.r.flag)
        res = rollback(w)
        self.assertEqual(res.returncode, 2, res.stdout)
        self.assertIn('runner-updater: rollback pending: CI disabled by a person', res.stdout)
        self.assertEqual((n_disable(w), w.enables(), w.validates(), stops(w)), (0, [], [], []))
        self.assertEqual(w.config_now(), w.pre)

    def test_a_pending_hand_edit_is_a_stop(self):
        w = rb_win(self, cfg=config((('mac-a', 'liveapp-mac-golden-20261025'),)))
        res = rollback(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP HAND CHANGE: a pending hand edit: ', res.stdout)
        self.assertEqual((n_disable(w), w.validates()), (0, []))

    def test_a_held_rollback_failed_starts_no_rollback(self):
        w = rb_win(self, families={FAM: switched(stops=[stop(FAM, 'ROLLBACK FAILED', version=V2)])})
        res = rollback(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE %s holds ROLLBACK FAILED' % FAM, res.stdout)
        self.assertEqual((n_disable(w), w.validates()), (0, []))

    def test_a_reason_that_is_not_r1_s_verdict_is_refused(self):
        w = rb_win(self)
        res = rollback(w, reason='{"set": "mac-a"}')
        self.assertIn('runner-updater: REFUSE the rollback\'s REASON is not r1\'s verdict', res.stdout)
        self.assertEqual(n_disable(w), 0)


class TestRollbackFailsAfterTheDisable(unittest.TestCase):
    """CONFIG EDIT's rollback rule: after the install, a validate STOP class puts the BACKUP (the config that ran before
    the window) back and enables CI on it; it never enables CI on lines that just failed validate. NON-API: STOP
    ROLLBACK FAILED; UNKNOWN: no STOP (tried again). A runner-disable time-out: a rollback that cannot start."""

    def test_post_validate_non_api_puts_the_backup_back(self):
        w = rb_win(self)
        w.validate('refuse', call=2)
        res = rollback(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP ROLLBACK FAILED: after the edit: validate (post) is NON-API', res.stdout)
        assert_runs(self, w, w.pre)
        self.assertEqual([e[2] for e in w.enables()], [sha(w.pre)])  # never on the rollback's lines
        f = w.family()
        self.assertEqual((f['candidate']['version'], [s['stop'] for s in f['stops']]), (V2, ['ROLLBACK FAILED']))
        self.assertTrue(os.path.exists(os.path.join(w.vms, NEW)))
        assert_closed(self, w)
        three_passes(self, w)

    def test_post_validate_unknown_puts_the_backup_back_with_no_stop(self):
        w = rb_win(self)
        w.validate('unknown', call=2)
        res = rollback(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        assert_runs(self, w, w.pre)
        self.assertEqual((w.family()['candidate']['version'], stops(w)), (V2, []))

    def test_a_runner_disable_time_out_then_recover_then_the_rollback_again(self):
        w = rb_win(self)
        w.put('disable-fail')
        res = rollback(w)
        self.assertEqual(res.returncode, 3, res.stdout)       # the window journal stays open
        self.assertIn('the rollback could not start', res.stdout)
        os.remove(os.path.join(w.scn, 'disable-fail'))
        recover = w.r.cmd('pass', ok=False)                   # RECOVER: CI back on the candidate, no STOP
        self.assertIn('runner-updater: recover: ', recover.stdout)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)
        self.assertEqual((w.family()['candidate']['version'], stops(w)), (V2, []))
        self.assertEqual(rollback(w).returncode, 0)           # the next try rolls back
        self.assertIsNone(w.family()['candidate'])


class TestConnectOnly(unittest.TestCase):
    """CONNECT-ONLY: a rollback whose counted failures are all connect-class does not reject the version the first time
    (one retry after 1 h); the second rollback of it rejects it."""

    def test_the_first_does_not_reject_the_second_does(self):
        w = rb_win(self)
        self.assertEqual(rollback(w, reason=CONNECT).returncode, 0)
        f = w.family()
        self.assertEqual((f['rejected'], w.value('reject')), ([], 'none'))
        (s,) = f['stops']
        self.assertEqual((s['stop'], s['detail']['connect_only']), ('ROLLED BACK', True))
        self.assertIn('version rejected: after-retry', w.status())
        # the retry after 1 h switched it again (here: the state and the config say so), and R1 rolls it back again
        s0 = w.u.get()
        s0['families'][FAM].update(candidate=cand(V2, {'mac-a': NEW}, int(time.time()) - 60), previous={'mac-a': OLD})
        w.u.put(s0)
        w.sb.write(w.r.config, config((('mac-a', NEW),)))
        w.sb.write(os.path.join(w.vms, NEW), '')
        self.assertEqual(rollback(w, reason=CONNECT).returncode, 0)
        self.assertEqual(w.family()['rejected'], [V2])

    def test_control_an_automatic_rollback_that_is_not_connect_only_rejects_at_once(self):
        w = rb_win(self)
        rollback(w)
        self.assertEqual(w.family()['rejected'], [V2])


class TestDeletion(unittest.TestCase):
    """DELETION: the rolled-back image is deleted by its recorded name in the same pass, only when no non-comment line
    of the config names it."""

    def test_a_config_line_that_names_it_keeps_it(self):
        w = rb_win(self, cfg=config((('mac-a', NEW), ('mac-c', NEW))))
        self.assertEqual(rollback(w).returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(w.vms, NEW)))
        self.assertEqual(actions(w), [])

    def test_a_kill_at_the_delete_line_leaves_the_image(self):
        w = rb_win(self)
        res = rollback(w, env={'RU_KILL_AT': 'delete'})
        self.assertEqual(res.returncode, KILLED, res.stdout)
        self.assertTrue(os.path.exists(os.path.join(w.vms, NEW)))
        self.assertFalse(os.path.exists(w.u.window))          # the journal had closed first


class TestRollbackRestart(unittest.TestCase):
    """It records its own restart (from / stopped / to) like the switch window."""

    def test_the_own_restart(self):
        w = rb_win(self)
        w.r.write_log('')
        w.r.cmd('pass')                                       # the boundary process P
        rollback(w)
        rs = w.u.get().get('restart')
        self.assertIsNotNone(rs)
        pid, start = (int(x) for x in w.value('running').split())
        self.assertEqual(rs['to'], {'pid': pid, 'start': start})
        self.assertNotEqual(w.value('from'), 'none')


class TestRollbackKilled(unittest.TestCase):
    """A kill at each step of a rollback window, and the same with the last line lost: RECOVER (CONFIG EDIT's rule)
    leaves CI on the rollback's lines only when they validate, else on the backup; the journal closes."""

    KEYS = ['disable-start', 'disable-done', 'stopped', 'installed', 'enable-start', 'enable-done', 'running', 'stop',
            'pin-rule', 'state-write', 'closed']

    def killed_rb(self, key, w=None):
        w = w or rb_win(self)
        res = rollback(w, env={'RU_KILL_AT': key})
        self.assertEqual(res.returncode, KILLED, (key, res.stdout))
        self.assertTrue(os.path.exists(w.u.window))
        return w

    def safe(self, w, key):
        res = w.r.cmd('pass', ok=False)
        self.assertIn(res.returncode, (0, 1), (key, res.stdout))
        assert_closed(self, w)
        old = config((('mac-a', OLD),)).encode()
        f = w.family()
        want = old if f['candidate'] is None else w.pre
        self.assertTrue(os.path.exists(w.r.flag), key)
        self.assertEqual(w.config_now(), want, key)
        for e in w.enables():                                 # CI only on the backup or on lines that validated
            self.assertIn(e[2], (sha(w.pre), sha(old)), key)
        if w.enables():
            self.assertEqual(w.enables()[-1][2], sha(want), key)
        self.assertLessEqual(n_disable(w), 2)

    def test_a_kill_at_each_step(self):
        for key in self.KEYS:
            for lost in (False, True):
                with self.subTest(key=key, lost=lost):
                    w = self.killed_rb(key)
                    if lost:
                        self.assertEqual(cut(w), key)
                    self.safe(w, key)

    def test_killed_after_the_install_with_the_target_image_removed(self):
        # PLAN D5 RECOVER 4: the rollback's lines no longer validate: the pre-window config runs, the STOP, and the next
        # three passes run no runner-disable
        w = self.killed_rb('enable-start')
        n = int(read_text(os.path.join(w.scn, 'validate.n')))
        w.validate('refuse', call=n + 1)
        res = w.r.cmd('pass', ok=False)
        self.assertIn('runner-updater: STOP ROLLBACK FAILED: RECOVER: the rollback\'s lines do not validate now', res.stdout)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)
        self.assertEqual([e[2] for e in w.enables()], [sha(w.pre)])
        self.assertIn('ROLLBACK FAILED', stops(w))
        self.assertEqual(w.family()['candidate']['version'], V2)
        three_passes(self, w)

    def test_control_killed_after_the_install_the_lines_validate_it_rolls_back(self):
        w = self.killed_rb('enable-start')
        w.r.cmd('pass', ok=False)
        assert_closed(self, w)
        assert_runs(self, w, config((('mac-a', OLD),)).encode())
        self.assertIsNone(w.family()['candidate'])
        self.assertEqual(w.family()['rejected'], [V2])


class TestBack(unittest.TestCase):
    """`back FAMILY`: a rollback window started by a person. Before ACCEPT (the D10 rehearsal) or after it while
    back_until holds; outside it: REFUSE. It rejects the version it leaves only when that is newer than the restored
    image's, and holds no ROLLED BACK."""

    def test_before_accept_the_rehearsal_no_rejection(self):
        w = rb_win(self, families={FAM: switched(candidate=cand(V0, {'mac-a': NEW}, int(time.time()) - 60))},
                   images={OLD: V0, NEW: V0})
        res = w.run('back')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('runner-updater: back %s: the family runs %s again; the window closed' % (FAM, OLD), res.stdout)
        assert_runs(self, w, config((('mac-a', OLD),)).encode())
        f = w.family()
        self.assertEqual((f['candidate'], f['rejected'], f['stops']), (None, [], []))
        self.assertEqual((w.value('command'), w.value('reject')), ('back', 'none'))

    def test_back_from_a_newer_version_rejects_it(self):
        w = rb_win(self)
        self.assertEqual(w.run('back').returncode, 0)
        self.assertEqual((w.family()['rejected'], w.family()['stops']), ([V2], []))

    def test_after_accept_within_back_until(self):
        w = rb_win(self, families={FAM: fam(previous={'mac-a': OLD}, back_until=int(time.time()) + 86400)})
        res = w.run('back')
        self.assertEqual(res.returncode, 0, res.stdout)
        assert_runs(self, w, config((('mac-a', OLD),)).encode())
        self.assertEqual((w.family()['rejected'], w.family()['back_until'], w.family()['previous']), ([V2], None, None))

    def test_outside_back_until_refuses(self):
        w = rb_win(self, families={FAM: fam(previous={'mac-a': OLD}, back_until=int(time.time()) - 60)})
        res = w.run('back')
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE back %s: the family has no candidate, and its previous image is kept for '
                      '`back` only until 7 days after the accept' % FAM, res.stdout)
        self.assertEqual((n_disable(w), w.validates(), os.path.exists(w.u.window)), (0, [], False))
        self.assertEqual(w.config_now(), w.pre)

    def test_back_while_a_rollback_failed_is_held(self):
        w = rb_win(self, families={FAM: switched(stops=[stop(FAM, 'ROLLBACK FAILED', version=V2)])})
        self.assertEqual(w.run('back').returncode, 0)
        self.assertEqual(stops(w), [])

    def test_back_clears_the_candidate_s_observation_stops(self):
        # JOBS FAIL ON THE NEW IMAGE names `back` as its next step; NO EVIDENCE is about the candidate too: both go
        held = [stop(FAM, 'JOBS FAIL ON THE NEW IMAGE', version=V2), stop(FAM, 'NO EVIDENCE', version=V2),
                stop(FAM, 'PINNED RUNNER RETIRED', version='2.0.1')]
        w = rb_win(self, families={FAM: switched(stops=held)})
        self.assertEqual(w.run('back').returncode, 0)
        self.assertEqual(stops(w), ['PINNED RUNNER RETIRED'])

    def test_back_while_off_refuses(self):
        w = rb_win(self)
        s = w.u.get()
        s['on'] = False
        w.u.put(s)
        res = w.run('back')
        self.assertIn('runner-updater: REFUSE the updater is OFF: back runs only while it is ON', res.stdout)
        self.assertEqual(n_disable(w), 0)

    def test_the_pin_after_back_names_the_restored_version(self):
        w = rb_win(self)
        w.u.pins(mac_golden='%s %s\n' % (V2, SHA2))
        w.run('back')
        out = w.sb.run(['/bin/zsh', '-f', os.path.join(w.tools, 'golden-build'), '--print-runner']).stdout
        self.assertEqual(out.strip(), 'host pin %s (release literal %s)' % (V0, V0))


class TestRetry(unittest.TestCase):
    """`retry FAMILY`: clears the family's rejection and every STOP it holds whose line (status.jq's) names `retry
    FAMILY`; a STOP whose line does not, and another family's, stay. The next pass may proceed."""

    HELD = ['check failed', 'ROLLED BACK', 'NO EVIDENCE', 'JOBS FAIL ON THE NEW IMAGE', 'ROLLBACK FAILED',
            'HAND CHANGE', 'POOL DOWN', 'NO IDLE', 'DISK', 'PINNED RUNNER RETIRED']

    def held(self, family=FAM):
        out = []
        for n in self.HELD:
            d = {'text': 'x'}
            if n == 'ROLLBACK FAILED':
                d['hand'] = 'runner-updater retry %s' % family
            if n == 'POOL DOWN':
                d['hand'] = '/x/runner-enable'
            out.append(stop(family, n, version=('2.0.1' if n == 'PINNED RUNNER RETIRED' else V2), detail=d))
        return out

    def test_retry_clears_what_names_retry(self):
        w = Win(self, s=state(on=True, families={FAM: fam(rejected=[V2, '2.0.1'], stops=self.held())},
                              images={OLD: V0}))
        res = w.r.cmd('retry', FAM, ok=False)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        f = w.family()
        self.assertEqual([s['stop'] for s in f['stops']],
                         ['HAND CHANGE', 'POOL DOWN', 'NO IDLE', 'DISK', 'PINNED RUNNER RETIRED'])
        self.assertEqual(f['rejected'], ['2.0.1'])            # a retired version stays rejected
        self.assertIn('runner-updater: retry %s: cleared check failed, ROLLED BACK, NO EVIDENCE, JOBS FAIL ON THE NEW '
                      'IMAGE, ROLLBACK FAILED; rejected now: 2.0.1; the next pass may proceed' % FAM, res.stdout)

    def test_another_family_s_stops_stay(self):
        other = 'linux-tart'
        w = Win(self, families='mac-golden tart mac-a\nlinux-tart tart mac-b\n',
                s=state(on=True, families={FAM: fam(rejected=[V2]), other: fam(rejected=[V2], stops=self.held(other))},
                        images={OLD: V0}))
        w.r.cmd('retry', FAM)
        s = w.u.get()['families']
        self.assertEqual((s[FAM]['rejected'], len(s[other]['stops']), s[other]['rejected']), ([], len(self.HELD), [V2]))

    def test_a_cleared_rollback_failed_lets_r1_roll_back_again(self):
        w = rb_win(self, families={FAM: switched(stops=[stop(FAM, 'ROLLBACK FAILED', version=V2,
                                                            detail={'text': 'x', 'hand': 'runner-updater retry %s' % FAM})])})
        self.assertEqual(rollback(w).returncode, 1)
        w.r.cmd('retry', FAM)
        self.assertEqual(rollback(w).returncode, 0)

    def test_nothing_held(self):
        w = Win(self)
        res = w.r.cmd('retry', FAM)
        self.assertIn('nothing to clear', res.stdout)

    def test_the_check_failed_status_line_names_retry(self):
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[stop(FAM, 'check failed', detail={'text': 'x'})])},
                              images={OLD: V0}))
        self.assertIn('Next: `runner-updater retry %s`' % FAM, w.status())


V1 = '2.338.9'                 # a runner version that is neither the release literal (V0) nor the candidate's (V2)
SHA1 = '3' * 64
RETRY = 'runner-updater retry %s' % FAM


def hands(w):
    """{STOP: its hand line} of the family's held STOPs"""
    f = w.family()
    return {s['stop']: (s.get('detail') or {}).get('hand') for s in f['stops']} if f else {}


def retry_then_rollback(test, w):
    """every ROLLBACK FAILED line of status names `runner-updater retry FAMILY`; retry clears it; the next ru_rollback
    starts (no REFUSE) and rolls back"""
    lines = [l for l in w.status().splitlines() if l.startswith('%s: STOP ROLLBACK FAILED' % FAM)]
    test.assertTrue(lines)
    for l in lines:
        test.assertTrue(l.endswith('Next, by hand: `%s`' % RETRY), l)
    res = w.r.cmd('retry', FAM, ok=False)
    test.assertIn('cleared ROLLBACK FAILED', res.stdout)
    test.assertNotIn('ROLLBACK FAILED', stops(w))
    res = rollback(w)
    test.assertNotIn('REFUSE', res.stdout)
    test.assertEqual(res.returncode, 0, res.stdout)
    test.assertIsNone(w.family()['candidate'])


class TestRollbackFailedNamesRetry(unittest.TestCase):
    """S3b-4a r1 F1: EVERY ROLLBACK FAILED the family holds names `runner-updater retry FAMILY` as its hand line, from
    every raiser (the pre-close path, RECOVER step 1's pre-close failure, and a STOP RECOVER holds again from a journal
    line), so `retry` clears it and R1 can roll back again."""

    def test_runner_enable_refuses_on_the_target(self):
        w = rb_win(self)
        w.put('enable-refuse.1')
        self.assertEqual(rollback(w).returncode, 1)
        self.assertEqual(hands(w), {'ROLLBACK FAILED': RETRY})
        assert_runs(self, w, w.pre)
        retry_then_rollback(self, w)

    def test_the_target_does_not_run_in_close_wait(self):
        w = rb_win(self)
        w.put('no-start.1')
        self.assertEqual(rollback(w).returncode, 1)
        self.assertEqual(hands(w), {'ROLLBACK FAILED': RETRY})
        retry_then_rollback(self, w)

    def test_recover_holds_the_journaled_rollback_failed_again(self):
        w = rb_win(self)
        w.validate('refuse', call=2)                 # the post-edit validate is NON-API
        self.assertEqual(rollback(w, env={'RU_KILL_AT': 'restore'}).returncode, KILLED)
        self.assertIn('stop ROLLBACK FAILED: after the edit: ', '\n'.join(w.journal()))
        w.r.cmd('pass', ok=False)                    # RECOVER
        assert_closed(self, w)
        self.assertEqual(hands(w), {'ROLLBACK FAILED': RETRY})
        retry_then_rollback(self, w)

    def test_recover_step_1_pre_close_failure_on_a_rollback_journal(self):
        w = rb_win(self)
        self.assertEqual(rollback(w, env={'RU_KILL_AT': 'enable-done'}).returncode, KILLED)
        w.r.set_ps([])                               # the target's runscaler is gone: step 1's wait fails
        res = w.r.cmd('pass', ok=False)
        self.assertIn('runner-updater: STOP ROLLBACK FAILED: the target did not run within 3 s', res.stdout)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)                   # the backup back (CONFIG EDIT's rule), CI on it
        self.assertEqual(w.family()['candidate']['version'], V2)
        self.assertEqual(hands(w), {'ROLLBACK FAILED': RETRY})
        retry_then_rollback(self, w)


class TestRecoverAfterAFailedPostValidate(unittest.TestCase):
    """S3b-4a r1 F2: a rollback journal that records a STOP class at the post-edit validate is finished as the window
    decided (CONFIG EDIT's rule): the BACKUP back with no new validate of the target, CI on the pre-window config only;
    NON-API holds ROLLBACK FAILED, UNKNOWN none; the candidate and its image stay."""

    def recovered(self, cls, kill):
        w = rb_win(self)
        w.validate(cls, call=2)                      # call 1: PRE-VALIDATE (PASS); call 2: after the edit
        self.assertEqual(rollback(w, env={'RU_KILL_AT': kill}).returncode, KILLED)
        self.assertEqual(w.enables(), [])
        res = w.r.cmd('pass', ok=False)              # RECOVER; any validate it ran would PASS
        assert_closed(self, w)
        self.assertEqual(len(w.validates()), 2, res.stdout)   # no new validate of the target
        self.assertEqual([e[2] for e in w.enables()], [sha(w.pre)])
        assert_runs(self, w, w.pre)
        f = w.family()
        self.assertEqual((f['candidate']['version'], f['rejected']), (V2, []))
        self.assertTrue(os.path.exists(os.path.join(w.vms, NEW)))
        return w

    def test_non_api_killed_at_each_line_after_it(self):
        for kill in ('validate:2', 'stop', 'restore'):
            with self.subTest(kill=kill):
                w = self.recovered('refuse', kill)
                self.assertEqual(hands(w), {'ROLLBACK FAILED': RETRY})

    def test_unknown_killed_at_each_line_after_it(self):
        for kill in ('validate:2', 'restore'):
            with self.subTest(kill=kill):
                w = self.recovered('unknown', kill)
                self.assertEqual(stops(w), [])

    def test_control_killed_at_installed_after_a_post_pass_rolls_back(self):
        w = rb_win(self)
        self.assertEqual(rollback(w, env={'RU_KILL_AT': 'installed'}).returncode, KILLED)
        w.r.cmd('pass', ok=False)
        self.assertIn('validate recover 1 PASS', w.journal())
        assert_closed(self, w)
        assert_runs(self, w, config((('mac-a', OLD),)).encode())
        self.assertIsNone(w.family()['candidate'])


# runner-enable's hook: a target that never runs (launchd's runscaler exits at once whenever the config is SHA T)
TARGET_NEVER_RUNS = '''T=%s PSD=%s
if [[ $(/usr/bin/shasum -a 256 < $C | /usr/bin/cut -c1-64) == $T ]]; then /bin/cp $PSD/background $PSD/out; fi
'''


class TestRecoverAfterAPreCloseFailure(unittest.TestCase):
    """S3b-4a r2 N2: a journaled `pre-close-failure` (the window's, or an earlier RECOVER's) whose config is still the
    target's edit is DECIDED, as the window decided it (CONFIG EDIT's rule): the backup goes back with no new validate
    and no runner-enable on the target that just failed to run, ROLLBACK FAILED holds with its retry line, CI goes on the
    pre-window config, and the candidate and its image stay. RECOVER finishes a journaled pre-close failure whose
    runner-disable did not finish (FLAG still present): it is not a second one, so no POOL DOWN. A switch in the same
    spot ends the same way (check failed). Controls: the window not killed ends the same;
    TestRecoverAfterAFailedPostValidate's cell killed at `installed` still rolls back."""

    def target_never_runs(self, w, target):
        tsha = sha(target)
        for n in (1, 2, 3):
            w.hook('enable-hook.%d' % n, TARGET_NEVER_RUNS % (tsha, w.r.psd))
        return tsha

    def decided(self, w, tsha, name='ROLLBACK FAILED'):
        assert_closed(self, w)
        self.assertEqual([e[2] for e in w.enables()], [tsha, sha(w.pre)])   # never the target again
        assert_runs(self, w, w.pre)
        self.assertEqual(n_disable(w), 2)                   # the window's, and the one its pre-close failure decided
        if name == 'ROLLBACK FAILED':
            self.assertEqual(hands(w), {'ROLLBACK FAILED': RETRY})
            f = w.family()
            self.assertEqual((f['candidate']['version'], f['rejected']), (V2, []))
            self.assertTrue(os.path.exists(os.path.join(w.vms, NEW)))
            self.assertEqual(len(w.validates()), 2)         # PRE-VALIDATE and post: no new validate of the target
        else:
            self.assertEqual(stops(w), [name])

    def test_control_not_killed(self):
        w = rb_win(self)
        tsha = self.target_never_runs(w, config((('mac-a', OLD),)).encode())
        self.assertEqual(rollback(w).returncode, 1)
        self.decided(w, tsha)

    def test_killed_at_each_line_of_the_pre_close_path(self):
        for kill in ('pre-close-failure', 'disable-start:2', 'disable-done:2', 'restore'):
            with self.subTest(kill=kill):
                w = rb_win(self)
                tsha = self.target_never_runs(w, config((('mac-a', OLD),)).encode())
                self.assertEqual(rollback(w, env={'RU_KILL_AT': kill}).returncode, KILLED)
                res = w.r.cmd('pass', ok=False)
                self.assertNotIn('POOL DOWN', res.stdout)
                self.decided(w, tsha)

    def test_recover_s_own_pre_close_failure_killed_before_its_runner_disable(self):
        w = rb_win(self)
        self.assertEqual(rollback(w, env={'RU_KILL_AT': 'enable-done'}).returncode, KILLED)
        w.r.set_ps([])                               # the target's runscaler is gone: step 1's wait fails
        res = w.r.cmd('pass', ok=False, env={'RU_KILL_AT': 'pre-close-failure'})
        self.assertEqual(res.returncode, KILLED, res.stdout)
        res = w.r.cmd('pass', ok=False)
        self.assertNotIn('POOL DOWN', res.stdout)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)
        self.assertEqual(n_disable(w), 2)
        self.assertEqual(hands(w), {'ROLLBACK FAILED': RETRY})
        self.assertEqual(w.family()['candidate']['version'], V2)

    def test_a_switch_the_same(self):
        from tests.studio.test_runner_updater_recover import out_name
        from tests.studio.test_runner_updater_window import switched_config
        for kill in ('pre-close-failure', 'disable-start:2'):
            with self.subTest(kill=kill):
                w = Win(self)
                tsha = self.target_never_runs(w, switched_config(w.pre, out_name()))
                self.assertEqual(w.run(env={'RU_KILL_AT': kill}).returncode, KILLED)
                res = w.r.cmd('pass', ok=False)
                self.assertNotIn('POOL DOWN', res.stdout)
                self.decided(w, tsha, 'check failed')


class TestTwoHourBound(unittest.TestCase):
    """S3b-4a r1 F3: the 2-h bound (ROLLBACK_BOUND from SINCE) covers every retried rollback failure: a runner-disable
    time-out, an UNKNOWN validate before and after the edit. Past it the next call holds STOP ROLLBACK FAILED and runs
    no runner-disable; within it (the control) the rollback is tried again."""

    H = 3600

    def first(self, kind):
        w = rb_win(self)
        if kind == 'disable':
            w.put('disable-fail')
            self.assertEqual(rollback(w, since=int(time.time()) - self.H).returncode, 3)
            os.remove(os.path.join(w.scn, 'disable-fail'))
        elif kind == 'post':
            w.validate('unknown', call=2)
            self.assertEqual(rollback(w, since=int(time.time()) - self.H).returncode, 1)
            self.assertEqual(stops(w), [])
        else:
            w.validate('unknown', call=1)
            self.assertEqual(rollback(w, since=int(time.time()) - self.H).returncode, 2)
            w.validate('unknown', call=2)
        return w

    def test_past_the_bound_no_runner_disable(self):
        for kind in ('disable', 'post', 'pre'):
            with self.subTest(kind=kind):
                w = self.first(kind)
                n = n_disable(w)
                res = rollback(w, since=int(time.time()) - 3 * self.H)
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn('runner-updater: STOP ROLLBACK FAILED: ', res.stdout)
                self.assertEqual(n_disable(w), n)
                self.assertEqual(hands(w), {'ROLLBACK FAILED': RETRY})
                self.assertFalse(os.path.exists(w.u.window))
                self.assertEqual((w.config_now(), os.path.exists(w.r.flag)), (w.pre, True))
                self.assertEqual([e[2] for e in w.enables()][-1:], [] if kind == 'pre' else [sha(w.pre)])

    def test_control_within_the_bound_it_is_tried_again(self):
        for kind in ('disable', 'post', 'pre'):
            with self.subTest(kind=kind):
                w = self.first(kind)
                n, v = n_disable(w), len(w.validates())
                res = rollback(w, since=int(time.time()) - self.H)
                self.assertNotIn('ROLLBACK FAILED', res.stdout)
                self.assertGreater(len(w.validates()), v)
                if kind == 'pre':
                    self.assertEqual((res.returncode, n_disable(w)), (2, n))
                else:
                    self.assertEqual((res.returncode, n_disable(w)), (0, n + 1), res.stdout)


def archived(w, name, family, *lines):
    """a closed journal in WINDOWS (an earlier window's), FAMILY's, with LINES"""
    w.sb.write(os.path.join(w.r.statedir, 'windows', name),
               ''.join(l + '\n' for l in ['window ' + name, 'family ' + family, 'kind switch'] + list(lines)
                       + ['closed 1']))


class TestPinAfterARollback(unittest.TestCase):
    """S3b-4a r1 F4: D2's ONE RULE at a rollback's close: the pin names the restored image's version V1 (the state's
    record) with a sha the updater once had as the family's pin (a closed journal of the family: pin-write, pin-rule
    or pin-before), also when V1 is not the release literal; at each rollback boundary (config edited, enable, pin
    written) through RECOVER too."""

    def win(self, journal=True):
        self.assertNotIn(V1, (V0, V2))
        w = rb_win(self, images={OLD: V1, NEW: V2})
        w.u.pins(mac_golden='%s %s\n' % (V2, SHA2))
        if journal:   # the candidate's switch window: it started on the pin of V1
            archived(w, '20261020100000-11', FAM, 'version ' + V2, 'pin-before %s %s' % (V1, SHA1),
                     'pin-write %s %s' % (V2, SHA2), 'pin-rule %s %s' % (V2, SHA2))
        # a decoy: a later journal of ANOTHER family that names another sha for V1
        archived(w, '20261021100000-12', 'linux-tart', 'pin-before %s %s' % (V1, '4' * 64))
        return w

    def assert_pin(self, w, key=None):
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V1, SHA1), key)
        out = w.sb.run(['/bin/zsh', '-f', os.path.join(w.tools, 'golden-build'), '--print-runner']).stdout
        self.assertEqual(out.strip(), 'host pin %s (release literal %s)' % (V1, V0), key)

    def test_an_automatic_rollback(self):
        w = self.win()
        self.assertEqual(rollback(w).returncode, 0)
        self.assertIsNone(w.family()['candidate'])
        self.assert_pin(w)

    def test_back(self):
        w = self.win()
        self.assertEqual(w.run('back').returncode, 0)
        self.assert_pin(w)

    def test_recover_at_each_boundary(self):
        for key in ('installed', 'enable-start', 'enable-done', 'running', 'pin-rule'):
            with self.subTest(key=key):
                w = self.win()
                self.assertEqual(rollback(w, env={'RU_KILL_AT': key}).returncode, KILLED)
                w.r.cmd('pass', ok=False)
                self.assertFalse(os.path.exists(w.u.window), key)
                self.assertIsNone(w.family()['candidate'], key)
                self.assert_pin(w, key)

    def test_control_no_journal_of_the_family_names_its_sha(self):
        w = self.win(journal=False)
        res = rollback(w)
        self.assertIn('the pin %s is removed: no sha256 of runner %s is known' % (w.pin, V1), res.stdout)
        self.assertFalse(os.path.exists(w.pin))


class TestDeleteOnlyARecordedImage(unittest.TestCase):
    """S3b-4a r1 P3-1: the image a rollback (or `back`) leaves is deleted only when the state records it as the
    family's (the candidate's lines, or an image the updater built or adopted: its image record). A person's hand image
    stays."""

    H = 'liveapp-mac-golden-20261025'

    def test_back_after_accept_keeps_a_hand_image(self):
        w = rb_win(self, cfg=config((('mac-a', self.H),)),
                   families={FAM: fam(previous={'mac-a': OLD}, back_until=int(time.time()) + 86400)})
        w.sb.write(os.path.join(w.vms, self.H), '')
        res = w.run('back')
        self.assertEqual(res.returncode, 0, res.stdout)
        assert_runs(self, w, config((('mac-a', OLD),)).encode())
        self.assertTrue(os.path.exists(os.path.join(w.vms, self.H)))
        self.assertIn('%s stays: the state does not record it' % self.H, res.stdout)
        self.assertEqual(actions(w), [])

    def test_control_back_after_accept_deletes_the_recorded_image(self):
        w = rb_win(self, families={FAM: fam(previous={'mac-a': OLD}, back_until=int(time.time()) + 86400)})
        self.assertEqual(w.run('back').returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(w.vms, NEW)))
        self.assertEqual(actions(w), ['delete ' + NEW])


class TestRecoverKeepsTheVerdict(unittest.TestCase):
    """S3b-4a r1 P3-2: the ROLLED BACK that RECOVER holds keeps R1's failures and text (the verdict the window kept in
    its folder, by the sha its journal names)."""

    def test_killed_at_state_write(self):
        w = rb_win(self)
        self.assertEqual(rollback(w, env={'RU_KILL_AT': 'state-write'}).returncode, KILLED)
        w.r.cmd('pass', ok=False)
        assert_closed(self, w)
        (s,) = w.family()['stops']
        self.assertEqual((s['stop'], len(s['detail']['failures']), s['detail']['text']),
                         ('ROLLED BACK', 3, VERDICT['reason']))
        self.assertIn('%s: STOP ROLLED BACK (runner %s): 3 counted failures, the last: Failed to start runner on '
                      'runner-0003' % (FAM, V2), w.status())

    def test_control_a_verdict_file_that_changed_is_not_read(self):
        w = rb_win(self)
        self.assertEqual(rollback(w, env={'RU_KILL_AT': 'state-write'}).returncode, KILLED)
        (vf,) = [os.path.join(d, 'verdict.json') for d in
                 (os.path.join(w.r.statedir, 'windows', n) for n in os.listdir(os.path.join(w.r.statedir, 'windows')))
                 if os.path.isdir(d)]
        w.sb.write(vf, json.dumps(dict(VERDICT, failures=FAILS[:1])) + '\n')
        w.r.cmd('pass', ok=False)
        (s,) = w.family()['stops']
        self.assertEqual((s['stop'], s['detail'].get('failures'), s['detail']['text']),
                         ('ROLLED BACK', None, VERDICT['reason']))


class TestFutureMtimeInARollback(unittest.TestCase):
    """S3b-4a r1 P3-4: A FUTURE MTIME in a rollback window is the rollback's failure, ROLLBACK FAILED (with its retry
    line), not a switch's `check failed`."""

    def test_a_target_dated_in_the_future(self):
        w = rb_win(self)
        w.hook('validate-hook.2', '/usr/bin/touch -t 203001010000 %s\n' % w.r.config)
        res = rollback(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("runner-updater: STOP ROLLBACK FAILED: the config's mtime ", res.stdout)
        assert_runs(self, w, w.pre)
        self.assertEqual(hands(w), {'ROLLBACK FAILED': RETRY})


class TestHandChangeUnderTheLock(unittest.TestCase):
    """S3b-4a r1 F6 (PLAN :236-243 as amended): a person's file found under the runner lock is not edited (STOP HAND
    CHANGE) and gets CI only when a copy of it validates (the ONE VALIDATE RULE); else no runner-enable, FLAG absent,
    the journal stays open with its `hand-change` line, and the next RECOVER validates it again."""

    def win(self):
        w = rb_win(self)
        w.hook('disable-hook.1', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)
        return w, w.pre + b'# a hand edit\n'

    def test_a_file_that_does_not_validate_gets_no_ci(self):
        w, found = self.win()
        w.validate('refuse', call=2)                 # call 1: PRE-VALIDATE; call 2: the copy of the person's file
        res = rollback(w)
        self.assertEqual(res.returncode, 3, res.stdout)
        self.assertIn('runner-updater: STOP HAND CHANGE: ', res.stdout)
        self.assertIn('runner-enable` by hand', res.stdout)
        self.assertEqual(w.validates()[-1][2], sha(found))
        self.assertEqual((w.enables(), os.path.exists(w.r.flag)), ([], False))
        self.assertEqual(w.config_now(), found)
        self.assertTrue(os.path.exists(w.u.window))
        self.assertEqual(w.value('hand-change'), sha(found))
        w.r.cmd('pass', ok=False)                    # RECOVER validates it again (PASS now): CI on it
        assert_closed(self, w)
        assert_runs(self, w, found)

    def test_control_a_file_that_validates_gets_ci(self):
        w, found = self.win()
        res = rollback(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertEqual(w.validates()[-1][2], sha(found))
        assert_runs(self, w, found)
        assert_closed(self, w)
        self.assertEqual(stops(w), ['HAND CHANGE'])


if __name__ == '__main__':
    unittest.main()
