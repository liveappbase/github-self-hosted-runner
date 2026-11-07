"""bin/runner-updater-window's RECOVER (PLAN D5, RECOVER 1-5; D1's at-most-once and TARGET rules): a pass and each
command that holds the updater lock end an open window journal first. RECOVER reads only the journal (by the window
header's patterns) and the facts (FLAG, ps, the config, the real lsof, tart, the real runner-lock-free).

The rig is test_runner_updater_window's (Win): a window is killed at a step boundary (RU_KILL_AT=KEY, or KEY:N for the
Nth KEY line), and then a pass (or a command) runs RECOVER. runner-lock-free is the REAL one on the rig's lock (real
lsof, real lockf); the fake tart lists a VM as running when scn/running-NAME exists.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest

from tests.studio.test_runner_updater import IMG2, P, proc_line, read_text, the_jq
from tests.studio.test_runner_updater_state import fam, lines_of, state, stop
from tests.studio.test_runner_updater_window import (FAM, KILLED, OLD, REFUSE_TEXT, SHA0, V0, Win, sha,
                                                     switched_config, today)

# a builder's VM that is NOT the record's own (another day's work VM): it holds RECOVER's wait, and RECOVER never stops
# it (the record's own VMs, which RECOVER stops: test_runner_updater_recover_vms)
OTHER_VM = 'gold-20290101'
RESTART_OLD = {'from': {'pid': 1, 'start': 2}, 'to': {'pid': 3, 'start': 4},
               'stopped': {'inode': '5', 'offset': 0, 'sha': '6' * 64}}


def tmp(test):
    d = os.path.realpath(tempfile.mkdtemp(prefix='studio-jq-'))
    test.addCleanup(shutil.rmtree, d, True)
    return d


def write_exec(path, text):
    with open(path, 'w') as f:
        f.write(text)
    os.chmod(path, 0o755)
    return path


def out_name():
    return 'liveapp-mac-golden-' + today()


def killed(test, key, w=None, cmd='rebuild', env=None):
    """a window of W (a new Win) killed right after its journal line KEY"""
    w = w or Win(test)
    res = w.run(cmd, env=dict(env or {}, RU_KILL_AT=key))
    test.assertEqual(res.returncode, KILLED, res.stdout + res.stderr)
    test.assertTrue(os.path.exists(w.u.window), res.stdout)
    return w


def cut(w):
    """the journal's last line is lost (runner-journal's named residual: a power loss after the fsync)"""
    with open(w.u.window) as f:
        lines = f.read().splitlines(True)
    with open(w.u.window, 'w') as f:
        f.write(''.join(lines[:-1]))
    return lines[-1].split(' ', 1)[0]


def n_disable(w):
    return len(w.calls('runner-disable'))


def recover(w, cmd='pass', env=None, ok=None):
    args = [cmd] if cmd in ('pass', 'on', 'off') else [cmd, FAM]
    res = w.r.cmd(*args, ok=False, env=env)
    if ok is not None:
        w.test.assertEqual(res.returncode, ok, res.stdout + res.stderr)
    return res


def stops(w):
    f = w.family()
    return [s['stop'] for s in f['stops']] if f else []


def assert_closed(test, w):
    test.assertFalse(os.path.exists(w.u.window), w.r.cmd('status', ok=False).stdout)


def assert_runs(test, w, config):
    """CI runs CONFIG (its log-file pin on the rig's runner.log: Rig.pin): FLAG present, and the last runner-enable
    was on it"""
    config = w.r.pin(config)
    test.assertTrue(os.path.exists(w.r.flag))
    test.assertEqual(w.config_now(), config)
    test.assertEqual(w.enables()[-1][2], sha(config))


def three_passes(test, w):
    """the next three passes run no runner-disable and find no open journal"""
    n = n_disable(w)
    for _ in range(3):
        res = w.r.cmd('pass', ok=False)
        test.assertNotIn('recover:', res.stdout)
        test.assertFalse(os.path.exists(w.u.window))
    test.assertEqual(n_disable(w), n)


class TestStep1FlagPresent(unittest.TestCase):
    """RECOVER step 1, FLAG first: present and no disable-done (nothing was disabled) = close, no STOP; present after
    `enable-start` = the updater's: the window closes when its LAST target runs, else after 10 min a pre-close
    failure; present after `disable-done` with no `enable-start` = a person enabled CI: STOP HAND CHANGE."""

    def test_nothing_was_disabled_closes_with_no_stop(self):
        w = killed(self, 'disable-start')
        res = recover(w, ok=0)
        self.assertIn('runner-updater: recover: nothing was disabled', res.stdout)
        assert_closed(self, w)
        self.assertEqual((n_disable(w), w.enables(), w.family()), (0, [], None))
        self.assertTrue(os.path.exists(w.r.flag))

    def test_flag_present_after_enable_start_closes_when_the_target_runs(self):
        w = killed(self, 'enable-done')
        res = recover(w, ok=0)
        self.assertIn('runner-updater: recover: the target runs', res.stdout)
        assert_closed(self, w)
        self.assertEqual((n_disable(w), len(w.enables())), (1, 1))      # the window's only: RECOVER ran neither
        f = w.family()
        self.assertEqual((f['candidate']['lines'], f['stops']), ({'mac-a': out_name()}, []))   # it switched
        self.assertEqual(w.keys()[-4:], ['running', 'pin-rule', 'state-write', 'closed'])
        self.assertEqual(w.value('state-write'), 'switched')

    def test_flag_present_target_not_running_in_10_min_is_a_pre_close_failure(self):
        w = killed(self, 'enable-done')
        w.r.set_ps([])                       # runscaler is not running (launchd gave up)
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP check failed: the target did not run within 3 s', res.stdout)
        self.assertEqual(n_disable(w), 2)                        # RECOVER's one runner-disable
        assert_runs(self, w, w.pre)                              # the backup is back, CI on it
        assert_closed(self, w)
        self.assertEqual(stops(w), ['check failed'])
        self.assertEqual(w.keys().count('pre-close-failure'), 1)

    def test_a_person_enabled_ci_after_runner_disable_is_hand_change(self):
        w = killed(self, 'build-start')
        w.sb.write(w.r.flag, '')                                 # a person's runner-enable
        w.r.set_ps([proc_line(4343, 'Mon Nov  2 10:00:00 2026')])
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP HAND CHANGE: CI was enabled while the window had it disabled', res.stdout)
        assert_closed(self, w)
        self.assertEqual((n_disable(w), w.enables()), (1, []))
        self.assertEqual(w.config_now(), w.pre)
        self.assertEqual(stops(w), ['HAND CHANGE'])

    def test_the_last_target_is_compared_not_the_first(self):
        # the post-edit validate refuses: the backup back, a second TARGET (the old lines), enable; killed after it
        w = Win(self)
        w.validate('refuse', call=3)
        killed(self, 'enable-done', w)
        self.assertEqual([l for l in w.journal() if l.startswith('target ')],
                         ['target mac-a=' + out_name(), 'target mac-a=' + OLD])
        res = recover(w, ok=1)
        self.assertNotIn('HAND CHANGE', res.stdout)
        self.assertEqual((n_disable(w), len(w.enables())), (1, 1))
        assert_closed(self, w)
        self.assertEqual(stops(w), ['check failed'])             # the window's own, from its journal
        self.assertEqual(w.config_now(), w.pre)

    def test_a_cut_journal_after_enable_start_on_the_edited_config_keeps_the_switch(self):
        # PLAN D1: a journal that ends after `enable-start` with FLAG present and the running config = the edited sha:
        # the switch happened (R1 stays armed: the candidate is set)
        w = killed(self, 'enable-done')
        self.assertEqual(cut(w), 'enable-done')
        recover(w, ok=0)
        self.assertEqual(w.family()['candidate']['lines'], {'mac-a': out_name()})
        self.assertEqual(n_disable(w), 1)

    def test_control_the_same_cut_journal_with_another_config_is_hand_change(self):
        w = killed(self, 'enable-done')
        cut(w)
        text = w.config_now().replace(out_name().encode(), IMG2.encode())
        w.r.write_config(text.decode())
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP HAND CHANGE: ', res.stdout)
        self.assertIsNone(w.family()['candidate'])
        self.assertEqual((n_disable(w), len(w.enables())), (1, 1))   # it leaves the person's config running
        assert_closed(self, w)


class TestPoolDown(unittest.TestCase):
    """D1: a pre-close failure happens AT MOST ONCE per journal; the second time, STOP POOL DOWN and no runner-disable."""

    def test_a_window_that_fails_at_the_build_then_recover_then_three_passes(self):
        w = Win(self)
        w.put('build-fail')
        killed(self, 'enable-start', w)                          # its own enable on the backup never ran
        self.assertFalse(os.path.exists(w.r.flag))
        recover(w, ok=1)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)
        self.assertEqual(stops(w), ['check failed'])
        three_passes(self, w)

    def test_a_sigkill_of_recover_after_runner_enable_wrote_flag(self):
        w = killed(self, 'build-start')
        res = recover(w, env={'RU_KILL_AT': 'enable-done'})
        self.assertEqual(res.returncode, KILLED, res.stdout)
        self.assertTrue(os.path.exists(w.r.flag))
        n = n_disable(w)
        recover(w, ok=1)                                         # FLAG present after enable-start: it closes
        self.assertEqual(n_disable(w), n)
        assert_closed(self, w)
        self.assertEqual(len(w.enables()), 1)
        three_passes(self, w)

    def test_runner_enable_refuses_in_recover_is_pool_down_after_one_runner_disable(self):
        w = killed(self, 'build-start')
        for n in (1, 2, 3):
            w.put('enable-refuse.%d' % n)                        # a planted stamp mismatch
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP POOL DOWN: runner-enable refused', res.stdout)
        self.assertEqual(n_disable(w), 2)                        # the window's, and RECOVER's one
        self.assertEqual(len(w.enables()), 2)
        self.assertFalse(os.path.exists(w.r.flag))
        assert_closed(self, w)
        self.assertIn('POOL DOWN', stops(w))
        three_passes(self, w)

    def test_a_journal_with_its_first_pre_close_failure_then_a_refusal_in_recover_has_no_runner_disable(self):
        w = Win(self)
        w.put('enable-refuse.1')                                 # the window's first enable refuses
        killed(self, 'enable-start:2', w)                         # its second enable never ran
        self.assertEqual(n_disable(w), 2)
        w.put('enable-refuse.2')                                 # RECOVER's refuses: the journal's second failure
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP POOL DOWN: ', res.stdout)
        self.assertEqual(n_disable(w), 2)                        # no runner-disable in RECOVER
        assert_closed(self, w)
        three_passes(self, w)

    def test_flag_present_target_not_running_after_a_pre_close_failure_is_pool_down(self):
        # step 1's own 10-min wait: the journal had its pre-close failure, so this second one is POOL DOWN
        w = Win(self)
        w.put('enable-refuse.1')
        killed(self, 'enable-done', w)                           # the second enable ran (FLAG, a runscaler)
        w.r.set_ps([])                                           # its runscaler is gone
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP POOL DOWN: the target did not run within 3 s', res.stdout)
        self.assertEqual((n_disable(w), len(w.enables())), (2, 2))  # no runner-disable, no runner-enable in RECOVER
        assert_closed(self, w)
        self.assertIn('POOL DOWN', stops(w))

    def test_a_journal_that_ended_in_pool_down_gets_no_more_runner_enable(self):
        w = Win(self)
        for n in (1, 2):
            w.put('enable-refuse.%d' % n)
        killed(self, 'pin-rule', w)                              # its POOL DOWN is journaled; the close was cut short
        self.assertIn('stop POOL DOWN: ', '\n'.join(w.journal()))
        res = recover(w, ok=1)
        self.assertIn('runner-updater: recover: the window ended in POOL DOWN', res.stdout)
        self.assertEqual((n_disable(w), len(w.enables())), (2, 2))
        self.assertFalse(os.path.exists(w.r.flag))
        assert_closed(self, w)
        self.assertEqual(stops(w), ['check failed', 'POOL DOWN'])

    def test_control_one_refusal_in_recover_then_the_backup_runs(self):
        w = killed(self, 'build-start')
        w.put('enable-refuse.1')
        recover(w, ok=1)
        self.assertEqual(n_disable(w), 2)
        assert_runs(self, w, w.pre)
        self.assertEqual(stops(w), ['check failed'])


class TestStep2Quiet(unittest.TestCase):
    """RECOVER step 2, FLAG absent: it waits until no process of this user has a journaled tool open (by dev+inode,
    EVERY open file: the real lsof), no gold-*, n1-* or s1-* VM runs (the record's own VMs it stops first:
    test_runner_updater_recover_vms; these cells run another one, OTHER_VM), and the runner lock is free (the real
    runner-lock-free). One bound (RECOVER_WAIT, 20 s in the rig): then STOP CI DISABLED, and the journal stays open."""

    def builder_under_lockf(self, w):
        """a REAL zsh running the window's golden-build copy (the journaled tool) under the REAL lockf on the rig's
        lock, blocked in its build until scn/go exists -> (the lockf process, the pid of its zsh)"""
        w.hook('build-hook', 'until [[ -f %s/go ]]; do /bin/sleep 0.05; done\n' % w.scn)
        pidf = w.sb.path('builder.pid')
        p = w.sb.hold_lock(w.r.lock, name='builder', argv=[
            '/bin/zsh', '-f', '-c',
            'print -r -- $$ > %s; exec /bin/zsh -f %s --date %s' % (pidf, os.path.join(w.tools, 'golden-build'),
                                                                   today())])
        w.sb.wait_for(lambda: os.path.exists(pidf) and read_text(pidf).strip(), 'the builder to start')
        zpid = int(read_text(pidf))
        w.sb.wait_for(lambda: self.lock_reads(w) == 'held', 'lockf to hold the lock')
        return p, zpid

    def lock_reads(self, w):
        return subprocess.run(['/bin/zsh', '-f', os.path.join(w.tools, 'runner-lock-free')], capture_output=True,
                              text=True).stdout.strip()

    def test_real_lsof_lockf_killed_alone_the_lock_reads_free_and_recover_waits(self):
        w = killed(self, 'build-start')
        p, zpid = self.builder_under_lockf(w)
        os.kill(p.pid, 9)                                        # lockf alone: its zsh child runs on
        p.wait()
        self.assertEqual(self.lock_reads(w), 'free')
        os.kill(zpid, 0)                                         # the builder's zsh still runs
        rec = w.sb.start(['/bin/zsh', '-f', w.r.script, 'pass'], name='recover')
        w.sb.wait_for(lambda: 'recover: waits' in read_text(w.sb.path('logs', 'recover.out')), 'RECOVER to wait')
        time.sleep(1.0)
        self.assertIsNone(rec.poll(), w.sb.output('recover'))   # it waits: the tool is open
        self.assertEqual((len(w.enables()), os.path.exists(w.u.window)), (0, True))
        self.assertIn('pid %d' % zpid, read_text(w.sb.path('logs', 'recover.out')))
        w.put('go')                                              # the builder ends
        self.assertEqual(rec.wait(timeout=60), 1, w.sb.output('recover'))
        assert_closed(self, w)
        assert_runs(self, w, w.pre)

    def test_control_the_builder_ended_recover_goes_on_at_once(self):
        w = killed(self, 'build-start')
        p, zpid = self.builder_under_lockf(w)
        w.put('go')
        self.assertEqual(p.wait(timeout=30), 0, w.sb.output('builder'))
        t0 = time.monotonic()
        res = recover(w, ok=1)
        self.assertLess(time.monotonic() - t0, 15)
        self.assertNotIn('recover: waits', res.stdout)
        assert_runs(self, w, w.pre)
        # the builder's output (made after the kill, its gate never ran) is deleted, journaled first
        self.assertEqual(w.value('delete'), out_name())
        self.assertFalse(os.path.exists(os.path.join(w.vms, out_name())))

    def test_a_running_builder_vm_holds_recover_until_ci_disabled(self):
        w = killed(self, 'build-start', Win(self, extra_rewrites=[('RECOVER_WAIT=20', 'RECOVER_WAIT=1')]))
        w.sb.write(os.path.join(w.vms, OTHER_VM), '')
        w.put('running-' + OTHER_VM)
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP CI DISABLED: ', res.stdout)
        self.assertIn(OTHER_VM, res.stdout)
        self.assertTrue(os.path.exists(w.u.window))              # the journal stays open: the next pass tries again
        self.assertEqual((w.enables(), stops(w)), ([], ['CI DISABLED']))
        self.assertIn('\n%s: STOP CI DISABLED' % FAM, w.status())
        os.remove(os.path.join(w.scn, 'running-' + OTHER_VM))   # the VM ends
        res = recover(w, ok=1)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)
        self.assertEqual(stops(w), ['check failed'])             # CI DISABLED is gone
        self.assertEqual(w.keys().count('recover-wait'), 1)      # ONE bound: the first wait's

    def test_past_the_bound_a_later_run_checks_once(self):
        # ONE bound, from the first `recover-wait`: a run after it does not wait again
        w = killed(self, 'build-start')
        with open(w.u.window, 'a') as f:
            f.write('recover-wait %d\n' % (int(time.time()) - 4600))
        w.sb.write(os.path.join(w.vms, OTHER_VM), '')
        w.put('running-' + OTHER_VM)
        t0 = time.monotonic()
        res = recover(w, ok=1)
        self.assertLess(time.monotonic() - t0, 10)                # RECOVER_WAIT is 20 s in the rig
        self.assertIn('runner-updater: STOP CI DISABLED: ', res.stdout)
        self.assertEqual(w.keys().count('recover-wait'), 1)

    def test_control_within_the_bound_it_waits(self):
        w = killed(self, 'build-start')
        w.sb.write(os.path.join(w.vms, OTHER_VM), '')
        w.put('running-' + OTHER_VM)
        t0 = time.monotonic()
        recover(w, ok=1)
        self.assertGreaterEqual(time.monotonic() - t0, 19)

    def test_a_held_runner_lock_holds_recover(self):
        w = killed(self, 'build-start', Win(self, extra_rewrites=[('RECOVER_WAIT=20', 'RECOVER_WAIT=1')]))
        hold = w.sb.hold_lock(w.r.lock, name='holder')
        w.sb.wait_for(lambda: self.lock_reads(w) == 'held', 'the lock to be held')
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP CI DISABLED: ', res.stdout)
        self.assertIn('the runner lock', res.stdout)
        os.kill(hold.pid, 9)
        hold.wait()
        recover(w, ok=1)
        assert_closed(self, w)


class TestStep3Delete(unittest.TestCase):
    """RECOVER step 3: the journaled VMs and outputs are deleted unless the gate passed, only when no non-comment line
    of the config names them, each journaled first (`delete NAME`)."""

    def test_a_gate_red_window_killed_after_the_gate_its_output_is_deleted(self):
        w = Win(self)
        w.put('gate', 1)
        killed(self, 'gate', w)
        self.assertTrue(os.path.exists(os.path.join(w.vms, out_name())))
        recover(w, ok=1)
        self.assertFalse(os.path.exists(os.path.join(w.vms, out_name())))
        self.assertEqual(w.value('delete'), out_name())
        k = w.keys()
        self.assertLess(k.index('delete'), k.index('enable-start', k.index('recover-wait')))
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))

    def test_control_a_gate_green_window_keeps_its_output(self):
        w = killed(self, 'enable-check')
        recover(w, ok=1)
        self.assertTrue(os.path.exists(os.path.join(w.vms, out_name())))
        self.assertNotIn('delete', w.keys())

    def test_a_name_a_config_line_names_is_kept(self):
        w = Win(self)
        w.put('gate', 1)
        killed(self, 'gate', w)
        with open(w.r.config, 'a') as f:      # a person's line names it (the config is then a HAND CHANGE too)
            f.write('# a note\n')
        text = w.config_now().decode().replace('# a note\n', '[[scaleset]]\nname = "mac-z"\nrunner-image = "%s"\n'
                                               % out_name())
        w.r.write_config(text)
        recover(w, ok=1)
        self.assertTrue(os.path.exists(os.path.join(w.vms, out_name())))
        self.assertNotIn('delete', w.keys())


class TestStep4Config(unittest.TestCase):
    """RECOVER step 4: the edited sha -> the backup goes back; the pre-window sha -> left; another sha -> left as found,
    and (AFTER THE INSTALL) CI is enabled on it only when it validates first."""

    def test_the_edited_config_goes_back_to_the_backup(self):
        w = killed(self, 'enable-start')
        self.assertEqual(w.config_now(), switched_config(w.pre, out_name()))
        recover(w, ok=1)
        assert_runs(self, w, w.pre)
        k = w.keys()
        self.assertEqual(w.value('restore'), w.value('backup'))
        self.assertLess(k.index('restore'), k.index('recover-target'))
        self.assertEqual(stops(w), ['check failed'])
        self.assertIn('interrupted', w.family()['stops'][0]['detail']['text'])
        self.assertIsNone(w.family()['candidate'])

    def test_the_pre_window_config_is_left(self):
        w = killed(self, 'build-start')
        recover(w, ok=1)
        assert_runs(self, w, w.pre)
        self.assertNotIn('restore', w.keys())
        self.assertNotIn('validate hand 1 PASS', w.journal())   # the pre-window config was validated before

    def test_another_config_that_validates_is_left_and_enabled(self):
        w = killed(self, 'build-start')
        found = w.pre + b'# a hand edit\n'
        w.r.write_config(found.decode())
        res = recover(w, ok=1)
        assert_runs(self, w, found)
        self.assertIn('validate hand 1 PASS', w.journal())
        self.assertEqual(w.validates()[-1][2], sha(found))
        self.assertEqual(stops(w), ['HAND CHANGE'])
        self.assertIn('runner-updater: STOP HAND CHANGE: ', res.stdout)

    def test_another_config_that_fails_validate_gets_no_ci(self):
        w = killed(self, 'build-start')
        found = w.pre + b'# a hand edit\n'
        w.r.write_config(found.decode())
        n = int(read_text(os.path.join(w.scn, 'validate.n')))
        w.validate('refuse', call=n + 1)
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP HAND CHANGE: ', res.stdout)
        self.assertEqual((w.enables(), os.path.exists(w.r.flag)), ([], False))
        self.assertEqual(w.config_now(), found)
        self.assertTrue(os.path.exists(w.u.window))              # it stays open: CI down until the file validates
        self.assertEqual(stops(w), ['HAND CHANGE'])

    def test_a_hand_change_after_the_install_validates_then_gets_ci(self):
        # S3b-3's window left its journal open: a person's file after the install, never validated (carried (a))
        w = Win(self)
        w.hook('validate-prehook.3', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)
        w.validate('refuse', call=3)
        res = w.run()
        self.assertIn('runner-updater: STOP HAND CHANGE: %s changed after the window installed its edit' % w.r.config,
                      res.stdout)
        self.assertTrue(os.path.exists(w.u.window))
        found = w.config_now()
        recover(w, ok=1)                                         # call 4 validates the person's file: PASS
        assert_runs(self, w, found)
        self.assertEqual(w.validates()[-1][2], sha(found))
        assert_closed(self, w)
        self.assertEqual(stops(w), ['HAND CHANGE'])

    def test_control_a_hand_change_after_the_install_that_fails_validate_stays_down(self):
        w = Win(self)
        w.hook('validate-prehook.3', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)
        w.validate('refuse', call=3)
        w.run()
        w.validate('refuse', call=4)
        recover(w, ok=1)
        self.assertEqual((w.enables(), os.path.exists(w.r.flag)), ([], False))
        self.assertTrue(os.path.exists(w.u.window))

    def test_recover_appends_its_own_target_before_enable_start(self):
        w = killed(self, 'enable-start')
        recover(w, ok=1)
        j = w.journal()
        i = j.index('recover-target %s mac-a=%s' % (sha(w.pre), OLD))
        self.assertEqual(j[i + 1:i + 3], ['installed %s %s %s' % (j[i + 1].split()[1], sha(w.pre), content_sha(w.pre)),
                                          'enable-start '])
        self.assertEqual([l.split(' ', 1)[0] for l in j[i + 1:]][:3], ['installed', 'enable-start', 'enable-done'])


class TestCarriedPreCloseEnable(unittest.TestCase):
    """S3b-3 review r2 carry (1): every enable of the window passes the sha it chose. The pre-close path (runner-enable
    refused, runner-disable) enables CI only on the backup or the file it had chosen, never on a person's file."""

    def test_a_person_s_file_found_at_the_pre_close_failure_gets_no_ci(self):
        w = Win(self)
        w.put('enable-refuse.1')
        w.hook('disable-hook.2', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)   # during the second disable
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP HAND CHANGE: %s changed after the window installed its edit' % w.r.config,
                      res.stdout)
        self.assertEqual(len(w.enables()), 1)                     # only the refused one
        self.assertFalse(os.path.exists(w.r.flag))
        self.assertTrue(os.path.exists(w.u.window))

    def test_control_no_hand_edit_the_backup_runs(self):
        w = Win(self)
        w.put('enable-refuse.1')
        w.hook('disable-hook.2', ': nothing\n')
        w.run()
        assert_runs(self, w, w.pre)


class TestRestartMember(unittest.TestCase):
    """S3b-3 fix r1 carry (b): an open journal beside an older `restart` state member. RECOVER keeps it when the
    journal disabled nothing (its runscaler, the member's `to`, still runs); else it clears it, and records its own
    {from, to, stopped} only from the journal's own `from` and `stopped` lines, with no pre-close failure."""

    def test_nothing_disabled_keeps_the_older_member(self):
        w = Win(self, s=state(on=True, images={OLD: V0}, restart=RESTART_OLD))
        killed(self, 'disable-start', w)
        recover(w, 'on', ok=0)                                   # `on`: a pass would pass the member on and clear it
        self.assertEqual(w.u.get()['restart'], RESTART_OLD)

    def test_a_journal_that_disabled_ci_clears_the_older_member(self):
        w = Win(self, s=state(on=True, images={OLD: V0}, restart=RESTART_OLD))
        killed(self, 'build-start', w)
        self.assertEqual(w.value('from'), 'none')
        recover(w, 'on', ok=0)
        self.assertNotIn('restart', w.u.get())

    def test_the_journal_s_own_from_and_stopped_give_recover_s_own_restart(self):
        w = Win(self)
        w.r.write_log('')
        w.r.cmd('pass')                                          # the boundary: P
        killed(self, 'build-start', w)
        self.assertEqual(w.value('from'), '%d %d' % (P[0], P[2]))
        recover(w, 'on', ok=0)
        rs = w.u.get()['restart']
        pid, start = (int(x) for x in [l for l in w.journal() if l.startswith('running ')][-1].split()[1:])
        self.assertEqual((rs['from'], rs['to']), ({'pid': P[0], 'start': P[2]}, {'pid': pid, 'start': start}))
        st = w.value('stopped').split()
        self.assertEqual(rs['stopped'], {'inode': st[0], 'offset': int(st[1]), 'sha': st[2]})

    def test_control_a_pre_close_failure_in_recover_records_none(self):
        w = Win(self)
        w.r.write_log('')
        w.r.cmd('pass')
        killed(self, 'build-start', w)
        w.put('enable-refuse.1')
        recover(w, 'on', ok=0)
        self.assertNotIn('restart', w.u.get())


class TestCutJournal(unittest.TestCase):
    """fit6 O4: a kill at each step boundary, and the same with the journal's last line lost: RECOVER stays safe. CI
    runs a validated config (the window's edit only when the window switched), the journal closes, the family's state
    says which, and nothing runs runner-disable twice for one pre-close failure."""

    KEYS = ['disable-start', 'disable-done', 'stopped', 'pin-write', 'build-start', 'build-done', 'gate-start', 'gate',
            'enable-check', 'edited-sha', 'installed', 'enable-start', 'enable-done', 'running', 'pin-rule',
            'state-write', 'closed']

    def safe(self, w, key, lost):
        res = recover(w)
        self.assertIn(res.returncode, (0, 1), (key, lost, res.stdout))
        assert_closed(self, w)
        f = w.family() or {'candidate': None, 'stops': []}
        new = switched_config(w.pre, out_name())
        if f['candidate'] is not None:
            assert_runs(self, w, new)
            self.assertEqual(f['candidate']['lines'], {'mac-a': out_name()})
        else:
            self.assertTrue(os.path.exists(w.r.flag), (key, lost))
            self.assertEqual(w.config_now(), w.pre, (key, lost))
        for e in w.enables():
            self.assertIn(e[2], (sha(w.pre), sha(new)), (key, lost))
        self.assertLessEqual(n_disable(w), 2)
        if f['candidate'] is None and 'gate green 0' not in w.journal():   # an output no gate passed is deleted
            self.assertFalse(os.path.exists(os.path.join(w.vms, out_name())), (key, lost))
        n = n_disable(w)
        res = w.r.cmd('pass', ok=False)
        self.assertNotIn('recover:', res.stdout)
        self.assertEqual(n_disable(w), n)

    def test_a_kill_at_each_step(self):
        for key in self.KEYS:
            with self.subTest(key=key):
                w = killed(self, key)
                self.safe(w, key, False)

    def test_a_kill_at_each_step_with_its_line_lost(self):
        for key in self.KEYS:
            with self.subTest(key=key):
                w = killed(self, key)
                self.assertEqual(cut(w), key)
                self.safe(w, key, True)


class TestCutJournalStepRan(unittest.TestCase):
    """S3b-4a r1 F5: the journal's last line is lost, but the step it names RAN (its side effect is on the host).
    RECOVER is FLAG first: no journal ends with CI down and no STOP, and a switch whose target runs keeps its
    candidate. The controls are TestCutJournal's cells (the step did not run)."""

    def test_disable_start_lost_after_runner_disable_ran(self):
        w = killed(self, 'disable-start')
        os.remove(w.r.flag)                                      # runner-disable's first act
        self.assertEqual(cut(w), 'disable-start')
        res = recover(w)
        self.assertNotIn('nothing was disabled', res.stdout)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)                              # CI back, on the pre-window config
        self.assertEqual(stops(w), ['check failed'])
        self.assertEqual(n_disable(w), 0)

    def test_enable_start_lost_after_runner_enable_ran(self):
        w = killed(self, 'enable-start')
        new = switched_config(w.pre, out_name())
        r = w.sb.run(['/bin/zsh', '-f', os.path.join(w.tools, 'runner-enable')])   # runner-enable ran
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(cut(w), 'enable-start')
        res = recover(w, ok=0)
        self.assertNotIn('HAND CHANGE', res.stdout)
        assert_closed(self, w)
        assert_runs(self, w, new)
        self.assertEqual((n_disable(w), len(w.enables())), (1, 1))   # RECOVER ran neither
        f = w.family()
        self.assertEqual((f['candidate']['lines'], f['stops']), ({'mac-a': out_name()}, []))   # R1 stays armed

    def test_restore_lost_after_the_backup_went_back(self):
        w = Win(self)
        w.validate('refuse', call=3)                             # after the edit: the backup goes back
        killed(self, 'restore', w)
        w.r.write_config(w.pre.decode())                   # the backup went back
        self.assertEqual(cut(w), 'restore')
        recover(w, ok=1)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)
        self.assertEqual(stops(w), ['check failed'])

    def test_delete_lost_after_the_image_was_deleted(self):
        w = Win(self)
        w.put('gate', 1)                                         # gate RED: the held close deletes the output
        killed(self, 'delete', w)
        os.remove(os.path.join(w.vms, out_name()))               # tart deleted it
        self.assertEqual(cut(w), 'delete')
        recover(w, ok=1)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)
        self.assertEqual(stops(w), ['check failed'])
        self.assertNotIn('delete', w.keys())

    def test_around_runner_disable_in_both_windows(self):
        # the cut at each line around runner-disable, with runner-disable already run (FLAG gone), in a switch and in a
        # rollback window: CI comes back on the pre-window config, the journal closes
        from tests.studio.test_runner_updater_rollback import rb_win, rollback
        for kind in ('switch', 'rollback'):
            for key in ('disable-start', 'disable-done'):
                with self.subTest(kind=kind, key=key):
                    if kind == 'switch':
                        w = killed(self, key)
                    else:
                        w = rb_win(self)
                        self.assertEqual(rollback(w, env={'RU_KILL_AT': key}).returncode, KILLED)
                    if os.path.exists(w.r.flag):
                        os.remove(w.r.flag)                      # runner-disable's first act
                    self.assertEqual(cut(w), key)
                    res = recover(w)
                    self.assertIn(res.returncode, (0, 1), res.stdout)
                    self.assertNotIn('nothing was disabled', res.stdout)
                    assert_closed(self, w)
                    assert_runs(self, w, w.pre)

    def test_enable_start_lost_in_a_rollback_after_runner_enable_ran(self):
        from tests.studio.test_runner_updater_rollback import rb_win, rollback
        w = rb_win(self)
        self.assertEqual(rollback(w, env={'RU_KILL_AT': 'enable-start'}).returncode, KILLED)
        r = w.sb.run(['/bin/zsh', '-f', os.path.join(w.tools, 'runner-enable')])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(cut(w), 'enable-start')
        res = recover(w, ok=0)
        self.assertNotIn('HAND CHANGE', res.stdout)
        assert_closed(self, w)
        self.assertIsNone(w.family()['candidate'])               # it rolled back
        self.assertEqual(len(w.enables()), 1)

    def test_control_a_journal_that_ends_before_its_backup_disabled_nothing(self):
        # D1 loses only the LAST line: a journal that ends before the line that comes just before disable-start
        # (`backup`; a rollback's `edited-sha`) never wrote disable-start. FLAG absent there is a person's: no action.
        # S3b-4a r2 P3-b: RECOVER cannot tell it from two lost lines (`backup` and `disable-start`, after runner-disable
        # ran: the same journal and the same host), which is beyond D1. So CI down is never silent: a no-action STOP
        # CI DISABLED, held, names runner-enable. The control (FLAG present: no STOP) is TestStep1FlagPresent's first
        for kind, key in (('switch', 'config-sha'), ('rollback', 'backup')):
            with self.subTest(kind=kind):
                if kind == 'switch':
                    w = killed(self, key)
                else:
                    from tests.studio.test_runner_updater_rollback import rb_win, rollback
                    w = rb_win(self)
                    self.assertEqual(rollback(w, env={'RU_KILL_AT': key}).returncode, KILLED)
                os.remove(w.r.flag)                              # a person's runner-disable, or two lost lines
                res = recover(w, ok=1)
                self.assertIn('nothing was disabled (no disable-start)', res.stdout)
                self.assertIn('runner-updater: STOP CI DISABLED: ', res.stdout)
                assert_closed(self, w)
                self.assertEqual((w.enables(), os.path.exists(w.r.flag), n_disable(w)), ([], False, 0))
                f = w.family() or {'stops': []}
                self.assertEqual([(s['stop'], s['detail']['hand']) for s in f['stops']],
                                 [('CI DISABLED', w.sb.path('cibin', 'runner-enable'))])
                self.assertIn('%s: STOP CI DISABLED' % FAM, w.status())


class TestRecoverDecidesOnce(unittest.TestCase):
    """S3b-4a r2 N1: the F5 rules (a lost `disable-start` whose runner-disable ran; a lost `enable-start` whose
    runner-enable ran) are decided from the WINDOW's own lines, never from a line an earlier RECOVER appended. RECOVER
    journals `recover-start` first whenever it acts; a later RECOVER reads the lines before it as the window's, and a
    journal with that line is never "nothing was disabled" again. Each cell: RECOVER #1 is killed after one of its own
    lines (or leaves the journal open on purpose), then RECOVER #2 must bring CI back or hold its STOP. The controls:
    TestCutJournalStepRan's "ends before its backup" cell and TestStep1FlagPresent's "nothing was disabled" cell."""

    def lost_disable_start(self, kind, w=None):
        """a window of KIND killed at disable-start whose runner-disable ran (FLAG gone) and whose line is lost; the
        state holds an older `restart` member"""
        if kind == 'switch':
            w = killed(self, 'disable-start', w)
        else:
            from tests.studio.test_runner_updater_rollback import rb_win, rollback
            w = rb_win(self)
            self.assertEqual(rollback(w, env={'RU_KILL_AT': 'disable-start'}).returncode, KILLED)
        os.remove(w.r.flag)
        self.assertEqual(cut(w), 'disable-start')
        s = w.u.get()
        s['restart'] = RESTART_OLD
        w.u.put(s)
        return w

    def back_up(self, w, kind, res):
        """RECOVER #2 brought CI back on the pre-window config and closed the journal: a switch holds check failed, a
        rollback that did not reach its target nothing; the older `restart` member is gone (runner-disable stopped its
        `to`)"""
        self.assertNotIn('nothing was disabled', res.stdout)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)
        self.assertEqual(stops(w), ['check failed'] if kind == 'switch' else [])
        self.assertNotIn('restart', w.u.get())

    def test_recover_killed_after_each_of_its_lines(self):
        for kind, keys in (('switch', ('recover-start', 'recover-wait', 'recover-target', 'installed', 'enable-done')),
                           ('rollback', ('recover-wait', 'recover-target', 'installed', 'enable-done'))):
            for key in keys:
                with self.subTest(kind=kind, key=key):
                    w = self.lost_disable_start(kind)
                    res = recover(w, env={'RU_KILL_AT': key})
                    self.assertEqual(res.returncode, KILLED, res.stdout)
                    self.back_up(w, kind, recover(w))

    def test_recover_s_own_lost_enable_start(self):
        # RECOVER #1's own last line is lost: its `enable-start`, whose runner-enable ran. The journal's last line is then
        # RECOVER's `installed`: the lost line may be enable-start (F5), whoever wrote the line before it
        w = self.lost_disable_start('switch')
        res = recover(w, env={'RU_KILL_AT': 'enable-start'})
        self.assertEqual(res.returncode, KILLED, res.stdout)
        r = w.sb.run(['/bin/zsh', '-f', os.path.join(w.tools, 'runner-enable')])   # runner-enable ran
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(cut(w), 'enable-start')
        res = recover(w)
        self.assertNotIn('HAND CHANGE', res.stdout)
        self.back_up(w, 'switch', res)
        self.assertEqual(len(w.enables()), 1)                    # RECOVER #2 ran no runner-enable

    def test_a_person_s_file_left_open_then_fixed(self):
        # RECOVER #1 leaves the journal open on purpose: a person's file that does not validate. Its STOP says the next
        # pass validates the file again; it does, and CI goes on the file once it validates
        w = self.lost_disable_start('switch')
        found = w.pre + b'# a hand edit\n'
        w.r.write_config(found.decode())
        n = int(read_text(os.path.join(w.scn, 'validate.n')))
        w.validate('refuse', call=n + 1)
        res = recover(w, ok=1)
        self.assertIn('the next pass validates the file again', res.stdout)
        self.assertTrue(os.path.exists(w.u.window))
        res = recover(w, ok=1)                                   # call n + 2: PASS
        self.assertNotIn('nothing was disabled', res.stdout)
        assert_closed(self, w)
        assert_runs(self, w, found)
        self.assertEqual(stops(w), ['HAND CHANGE'])

    def test_ci_disabled_left_open_then_quiet(self):
        # RECOVER #1 leaves the journal open on purpose: CI DISABLED after its bound ("the next pass checks again")
        w = self.lost_disable_start('switch', Win(self, extra_rewrites=[('RECOVER_WAIT=20', 'RECOVER_WAIT=1')]))
        w.sb.write(os.path.join(w.vms, OTHER_VM), '')
        w.put('running-' + OTHER_VM)
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP CI DISABLED: ', res.stdout)
        self.assertIn('the next pass checks again', res.stdout)
        self.assertTrue(os.path.exists(w.u.window))
        os.remove(os.path.join(w.scn, 'running-' + OTHER_VM))   # the VM ends
        self.back_up(w, 'switch', recover(w, ok=1))

    def test_a_lost_enable_start_then_recover_killed_after_running(self):
        # F5's other rule: the window's last line is `installed` (its lost enable-start ran runner-enable). RECOVER #1
        # sees the target run and is killed after `running`: RECOVER #2 reads the WINDOW's last line, and the window
        # switched (rolled back), with no HAND CHANGE
        from tests.studio.test_runner_updater_rollback import rb_win, rollback
        for kind in ('switch', 'rollback'):
            with self.subTest(kind=kind):
                if kind == 'switch':
                    w = killed(self, 'enable-start')
                else:
                    w = rb_win(self)
                    self.assertEqual(rollback(w, env={'RU_KILL_AT': 'enable-start'}).returncode, KILLED)
                r = w.sb.run(['/bin/zsh', '-f', os.path.join(w.tools, 'runner-enable')])   # runner-enable ran
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(cut(w), 'enable-start')
                res = recover(w, env={'RU_KILL_AT': 'running'})
                self.assertEqual(res.returncode, KILLED, res.stdout)
                res = recover(w, ok=0)
                self.assertNotIn('HAND CHANGE', res.stdout)
                assert_closed(self, w)
                self.assertEqual((n_disable(w), len(w.enables())), (1, 1))   # neither RECOVER ran either
                f = w.family()
                if kind == 'switch':
                    self.assertEqual((f['candidate']['lines'], f['stops']), ({'mac-a': out_name()}, []))
                else:
                    self.assertIsNone(f['candidate'])


def content_sha(data):
    """PLAN D1's CONTENT (as amended 2026-11-03, S3b-4a r2 P3-c): the sha256 of the file's lines with whole-line comments
    (first non-blank character `#`) and blank lines removed, each kept line byte for byte with its newline"""
    return sha(b''.join(l + b'\n' for l in data.split(b'\n') if not re.match(rb'[ \t]*(#|$)', l)))


class TestStep1ComparesTheContent(unittest.TestCase):
    """RECOVER step 1 (PLAN D1 as amended 2026-11-03, S3b-4a r2 P3-c; before it, S3b-4a r1 P3-3's sha compare): a cut
    journal that ends after `enable-start` with FLAG present keeps its switch (R1 stays armed) when the running config's
    CONTENT (whole-line comments and blank lines removed) is the content sha the window journaled on its last `installed`
    line, beside the file's sha, before `enable-start`. A comment cannot change what runs; any other change (a number, a
    line outside the family's, an inline comment, a space inside a line) is HAND CHANGE, so an R1 rollback never puts
    the backup over it unseen. An older `installed` line with no content sha falls back to the file's sha."""

    REAL = (('a number', b'concurrent = 2', b'concurrent = 1'),
            ('a line outside the family', b'disable-update = false\n',
             b'disable-update = false\n[[scaleset]]\nname = "mac-z"\nrunner-image = "%s"\n' % IMG2.encode()),
            ('an inline comment', b'drain-timeout = "60m"', b'drain-timeout = "60m" # a note'),
            ('a space inside a line', b'log-level = "info"', b'log-level =  "info"'))

    def test_the_window_journals_the_content_sha_before_enable_start(self):
        w = killed(self, 'enable-start')
        j = w.journal()
        now = w.config_now()
        self.assertEqual(j[-2].split()[0::2], ['installed', sha(now)])
        self.assertEqual(j[-2].split()[3:], [content_sha(now)])

    def test_a_comment_only_edit_after_enable_keeps_the_switch(self):
        w = killed(self, 'enable-done')
        new = b'# a note\n\n   # an indented note\n' + w.config_now() + b'\n\t\n# the last line, with no newline'
        self.assertEqual(content_sha(new), content_sha(w.config_now()))
        w.r.write_config(new.decode())
        res = recover(w, ok=0)
        self.assertNotIn('HAND CHANGE', res.stdout)
        assert_closed(self, w)
        f = w.family()
        self.assertEqual((f['candidate']['lines'], f['stops']), ({'mac-a': out_name()}, []))   # R1 stays armed
        self.assertEqual((n_disable(w), len(w.enables())), (1, 1))
        self.assertEqual(w.config_now(), new)                    # the person's file stays

    def test_a_real_change_is_hand_change(self):
        for what, old, new in self.REAL:
            with self.subTest(what=what):
                w = killed(self, 'enable-done')
                text = w.config_now()
                self.assertEqual(text.count(old), 1, what)
                w.r.write_config(text.replace(old, new).decode())
                res = recover(w, ok=1)
                self.assertIn('runner-updater: STOP HAND CHANGE: ', res.stdout)
                assert_closed(self, w)
                self.assertIsNone(w.family()['candidate'])
                self.assertEqual((n_disable(w), len(w.enables())), (1, 1))   # CI and the file as they are

    def test_an_old_journal_without_the_content_sha_compares_the_file_s_sha(self):
        # a comment is a change there (the file's sha); the control writes the same bytes again (a new mtime, after the
        # start): the switch stays, as the start is compared with the journaled install time, not the mtime now
        for edit, rc in ((b'', 0), (b'# a note\n', 1)):
            with self.subTest(edit=edit):
                w = killed(self, 'enable-done')
                lines = w.journal()
                i = max(k for k, l in enumerate(lines) if l.startswith('installed '))
                lines[i] = ' '.join(lines[i].split()[:3])        # `installed EPOCH SHA`: an older window's line
                with open(w.u.window, 'w') as f:
                    f.write(''.join(l + '\n' for l in lines))
                w.r.write_config((w.config_now() + edit).decode())
                res = recover(w, ok=rc)
                assert_closed(self, w)
                if edit:
                    self.assertIn('runner-updater: STOP HAND CHANGE: ', res.stdout)
                    self.assertIsNone(w.family()['candidate'])
                else:
                    self.assertEqual(w.family()['candidate']['lines'], {'mac-a': out_name()})


class TestEveryCommandRecoversFirst(unittest.TestCase):
    """A pass and every command that takes the updater lock (rebuild, switch-now, on, off) run RECOVER first when a
    journal is open; report (no action) and status (no lock) do not."""

    def test_each_command_recovers(self):
        for cmd in ('pass', 'rebuild', 'switch-now', 'on', 'off'):
            with self.subTest(cmd=cmd):
                w = killed(self, 'build-start')
                res = recover(w, cmd)
                self.assertIn('runner-updater: recover: ', res.stdout)
                assert_closed(self, w)
                self.assertTrue(os.path.exists(w.r.flag))

    def test_control_report_and_status_do_not(self):
        w = killed(self, 'build-start')
        for args in (('report',), ('status',)):
            res = w.r.cmd(*args, ok=False)
            self.assertNotIn('recover:', res.stdout)
        self.assertTrue(os.path.exists(w.u.window))
        self.assertEqual(w.enables(), [])

    def test_a_pass_while_off_recovers(self):
        w = killed(self, 'build-start')
        s = w.u.get()
        s['on'] = False
        w.u.put(s)
        res = recover(w, ok=1)                                  # RECOVER held a STOP (check failed): exit 1
        self.assertIn('runner-updater: recover: ', res.stdout)
        self.assertIn('the updater is OFF', res.stdout)
        assert_closed(self, w)

    def test_ru_window_still_refuses_an_open_journal(self):
        # 4b's pass calls ru_window: it must have run RECOVER first
        w = killed(self, 'build-start')
        body = ('source %s || exit 8\nru_window mac-golden %s %s idle 0 pass\nprint -r -- "rc $?"\n'
                % (os.path.join(w.tools, 'runner-updater-window'), V0, SHA0))
        from tests.studio.test_runner_updater_state import lib_run
        res = lib_run(w.r, 'WINDOW=%s WINDOWS=%s\n' % (w.u.window, os.path.join(w.r.statedir, 'windows')) + body)
        self.assertIn('runner-updater: STOP RECOVER needed: the window journal %s is open' % w.u.window, res.stdout)
        self.assertEqual(res.stdout.splitlines()[-1], 'rc 1')


class TestNoJq(unittest.TestCase):
    """PLAN :60, RECOVER is glue and needs no jq: its steps on CI (the journal, FLAG, the config, lsof, tart, the lock,
    validate, runner-disable and -enable) run with no jq; jq only reads and writes the state."""

    def test_an_untested_jq_does_not_stop_recover(self):
        d = tmp(self)
        v = os.path.join(d, 'untested')
        wrap = write_exec(os.path.join(d, 'jq'), '#!/bin/zsh -f\nif [[ $1 == --version && -f %s ]]; then print -r -- '
                          'jq-0.0; exit 0; fi\nexec %s "$@"\n' % (v, the_jq()))
        w = Win(self, jq=wrap)
        killed(self, 'build-start', w)
        open(v, 'w').close()                                     # from now on, `jq --version` is not a tested one
        res = recover(w, ok=3)
        self.assertIn('runner-updater: recover: ', res.stdout)
        self.assertIn('runner-updater: STOP untested jq', res.stdout)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)

    def test_jq_failing_from_recover_s_first_line_on_ci_still_comes_back(self):
        d = tmp(self)
        off = os.path.join(d, 'off')
        wrap = write_exec(os.path.join(d, 'jq'), '#!/bin/zsh -f\n[[ -f %s ]] && { print -u2 -r -- "jq: injected failure"; '
                          'exit 5 }\nexec %s "$@"\n' % (off, the_jq()))
        w = Win(self, jq=wrap)
        killed(self, 'enable-start', w)                          # the edited config is installed
        res = recover(w, env={'RU_JQ_OFF_AT': 'recover-wait', 'RU_JQ_OFF': off})
        self.assertTrue(os.path.exists(off), res.stdout)
        assert_runs(self, w, w.pre)                              # the backup back and CI on it, with no jq
        self.assertTrue(os.path.exists(w.u.window), res.stdout)   # the state could not be written: it stays open
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V0, SHA0))   # a jq that fails is not "no record": pin kept
        os.remove(off)
        recover(w, ok=1)                                         # the next pass closes it (FLAG after enable-start)
        assert_closed(self, w)
        self.assertEqual(len(w.enables()), 1)
        self.assertEqual(stops(w), ['check failed'])


class TestJournalPatterns(unittest.TestCase):
    """RECOVER reads the journal ONLY by the window header's patterns: a line no pattern reads is a STOP, and RECOVER
    changes nothing (CI stays as it is, the journal stays open)."""

    def test_a_line_no_pattern_reads(self):
        w = killed(self, 'build-start')
        with open(w.u.window, 'a') as f:
            f.write('backup relative/path\n')
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP RECOVER cannot read the window journal', res.stdout)
        self.assertTrue(os.path.exists(w.u.window))
        self.assertEqual((w.enables(), n_disable(w)), ([], 1))

    def test_an_unknown_key(self):
        w = killed(self, 'build-start')
        with open(w.u.window, 'a') as f:
            f.write('surprise yes\n')
        res = recover(w, ok=1)
        self.assertIn('RECOVER does not read the key', res.stdout)
        self.assertEqual(w.enables(), [])

    def test_control_a_cut_last_fragment_is_dropped(self):
        w = killed(self, 'build-start')
        with open(w.u.window, 'a') as f:
            f.write('build-don')                                 # no newline: the last line was cut mid-write
        recover(w, ok=1)
        assert_closed(self, w)
        assert_runs(self, w, w.pre)


if __name__ == '__main__':
    unittest.main()
