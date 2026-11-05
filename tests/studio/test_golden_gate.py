"""bin/golden-gate IMAGE [--journal FILE]: clone IMAGE to s1-gate-<UTC time>, boot it with real-run, run golden-emudhra
--gate on it, and delete the clone before the runner lock is let go, on every path (green, red, a failed step, INT,
TERM, HUP).

A copy runs with FLAG, LOCK, LOGDIR, REAL and REALRUN rewritten into the test's folder, a stub tart (its `delete`
records whether the runner lock is still held at that moment: lockf -t 0 answers 75), a stub real-run that runs until
the stub `tart stop` marks its VM stopped, the real runner-journal, and a stub golden-emudhra beside the copy.
GateVerdicts puts a copy of the REAL golden-emudhra there instead: its tart is the same stub, whose exec answers each
guest step from scenario files, so golden-gate's verdict is read from what golden-emudhra really prints.
"""
import os
import re
import signal
import subprocess
import time
import unittest

from tests.studio.support import group_alive, kill_group, members
from tests.studio.support_emudhra import (BASE_ENV, REPO, ZSH, copy_script, excluded_copy, lines, read, run, stub, tmpdir,
                                          write)

IMAGE = 'liveapp-mac-golden-20261101'
OTHERS = ['liveapp-mac-golden-20261031', 'gold-20261101', 'runner-abc123']
NAME_RE = r'^s1-gate-[0-9]{14}$'

TART = r'''D=@D@
if [[ $1 == exec ]]; then print -r -- "$1 $2 $3" >> $D/tart-calls   # one line per call (a guest script is long)
else print -r -- "$*" >> $D/tart-calls; fi
case $1 in
  (list) [[ $2 == --source && $3 == local && $4 == -q ]] || exit 3
    [[ -f $D/flag-on-list ]] && : > @FLAG@   # the agent enabled between golden-gate's first check and its lock
    /bin/cat $D/vms; exit 0 ;;
  (clone)
    if [[ -f @J@ ]] && (( ${${(f)"$(<@J@)"}[(Ie)gate-clone $3]} )); then print -r -- yes >> $D/clone-journal
    else print -r -- no >> $D/clone-journal; fi
    (( ${${(f)"$(<$D/vms)"}[(Ie)$2]} )) || exit 1
    print -r -- $3 >> $D/vms
    [[ -f $D/clone-block ]] && { : > $D/clone-started; /bin/sleep 30 }   # a clone still being made
    exit 0 ;;
  (exec) (( ${${(f)"$(<$D/vms)"}[(Ie)$2]} )) || exit 1
    case $3 in   # the real golden-emudhra's guest calls (GateVerdicts); golden-gate's own is `exec NAME true`
      (/usr/bin/mktemp) print -r -- /private/tmp/golden-emudhra.T3st ;;
      (/bin/test) exit 1 ;;   # `test -e W` after the rm: the guest work folder is gone
      (/bin/zsh) [[ $7 == golden-emudhra-guest ]] || exit 9
        print -r -- $8 >> $D/guest-steps
        [[ -f $D/scenario/$8.out ]] && /bin/cat $D/scenario/$8.out
        [[ -f $D/scenario/$8.rc ]] && exit $(<$D/scenario/$8.rc) ;;
    esac
    exit 0 ;;
  (stop) : > $D/stopped.$2; exit 0 ;;
  (delete)
    /usr/bin/lockf -k -t 0 @LOCK@ /usr/bin/true 2>/dev/null; rc=$?
    if (( rc == 75 )); then print -r -- "$2 held" >> $D/deletes; else print -r -- "$2 free($rc)" >> $D/deletes; fi
    [[ -f $D/keep-on-delete ]] && exit 0
    v=(${(f)"$(<$D/vms)"}); (( ${v[(Ie)$2]} )) || exit 1
    print -rl -- ${v:#$2} > $D/vms; exit 0 ;;
  (*) print -r -- "unexpected: $*" >> $D/unexpected; exit 1 ;;
esac
'''
REALRUN = r'''D=@D@
print -r -- "$*" >> $D/realrun-args
while [[ ! -e $D/stopped.$1 ]]; do /bin/sleep 0.1; done
exit 0
'''
EMUDHRA = r'''D=@D@
print -r -- "$*" >> $D/emudhra-args
s=$(<$D/gatescen)
case $s in
  (green) print -r -- "golden-emudhra: gate: no FAIL"; print -r -- "golden-emudhra: GATE GREEN"; exit 0 ;;
  (green-no-line) print -r -- "golden-emudhra: gate: no FAIL"; exit 0 ;;   # exit 0, but no GATE GREEN line
  (red) print -r -- "golden-emudhra: FAIL census: AAA Certificate Services: no deny"; print -r -- "golden-emudhra: GATE RED"; exit 1 ;;
  (stop) print -r -- "golden-emudhra: STOP $2 does not answer tart exec"; exit 1 ;;
  (sleep*) : > $D/gate-started; /bin/sleep ${s#sleep }; print -r -- "golden-emudhra: GATE GREEN"; exit 0 ;;
esac
exit 9
'''


class GateRig:
    """The copy, its stubs and the helpers; a TestCase class mixes this in."""

    def setUp(self):
        d = self.d = tmpdir(self)
        self.lock = os.path.join(d, 'runner.lock')
        self.flag = os.path.join(d, 'enabled')
        self.logs = os.path.join(d, 'logs')
        os.makedirs(self.logs)
        self.journal = os.path.join(d, 'journal', 'updater.journal')
        os.makedirs(os.path.dirname(self.journal))
        sub = lambda t: (t.replace('@D@', d).replace('@J@', self.journal).replace('@LOCK@', self.lock)
                         .replace('@FLAG@', self.flag))
        self.tart = stub(os.path.join(d, 'stub', 'tart'), sub(TART))
        realrun = stub(os.path.join(d, 'stub', 'real-run'), sub(REALRUN))
        self.tool = os.path.join(d, 'bin', 'golden-gate')
        text = copy_script(self, 'bin/golden-gate', self.tool, rewrites=[
            ('REAL=/Users/ci/Applications/tart.app/Contents/MacOS/tart', 'REAL=' + self.tart),
            ('REALRUN=/Users/ci/bin/real-run', 'REALRUN=' + realrun),
            ('LOCK=/tmp/runner.lock', 'LOCK=' + self.lock),
            ('FLAG=/Users/ci/.config/runner/enabled', 'FLAG=' + self.flag),
            ('LOGDIR=/Users/ci/Library/Logs/mac-runner', 'LOGDIR=' + self.logs),
        ], allow_ci=('HOME=/Users/ci ', '#   /Users/ci/bin/golden-gate '))   # tart's HOME; the usage line
        self.assertNotIn('/tmp/runner.lock', text)
        copy_script(self, 'bin/runner-journal', os.path.join(d, 'bin', 'runner-journal'))
        stub(os.path.join(d, 'bin', 'golden-emudhra'), sub(EMUDHRA))
        self.vms0 = [IMAGE] + OTHERS
        write(os.path.join(d, 'vms'), '\n'.join(self.vms0) + '\n')
        self.scen('green')

    def scen(self, s):
        write(os.path.join(self.d, 'gatescen'), s + '\n')

    def argv(self, image=IMAGE, journal=True):
        return [ZSH, '-f', self.tool, image] + (['--journal', self.journal] if journal else [])

    def gate(self, image=IMAGE, journal=True):
        r = run(self.argv(image, journal), env={'HOME': self.d}, cwd=self.d)
        self.assertFalse(os.path.exists(os.path.join(self.d, 'unexpected')))
        return r, r.stdout.splitlines()

    def f(self, name):
        return lines(os.path.join(self.d, name))

    def vms(self):
        return [v for v in self.f('vms') if v]

    def the_clone(self):
        clones = [c.split()[2] for c in self.f('tart-calls') if c.startswith('clone ')]
        self.assertEqual(len(clones), 1, self.f('tart-calls'))
        self.assertRegex(clones[0], NAME_RE)
        return clones[0]

    def assert_clone_deleted_under_the_lock(self):
        name = self.the_clone()
        self.assertEqual(self.f('deletes'), [name + ' held'])   # only NAME, and the lock still held
        self.assertEqual(self.vms(), self.vms0)                  # no other image deleted
        return name

    def assert_no_tart_call(self):
        self.assertEqual(self.f('tart-calls'), [])

    def assert_no_clone(self):
        self.assertEqual([c for c in self.f('tart-calls') if c.startswith(('clone ', 'delete '))], [])

    def started(self, flag):
        """Start golden-gate in a process group of its own; return it once the stub wrote D/FLAG."""
        p = subprocess.Popen(self.argv(), env=dict(BASE_ENV, HOME=self.d), cwd=self.d, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(self.reap, p)
        t0 = time.time()
        while not os.path.exists(os.path.join(self.d, flag)):
            self.assertIsNone(p.poll(), 'golden-gate ended before the stub wrote ' + flag)
            self.assertLess(time.time() - t0, 30, 'the stub did not write ' + flag)
            time.sleep(0.05)
        return p

    def reap(self, p):
        # the group the test started (its own session): kill what is left of it, the leader gone or not. support.py's
        # kill_group is the one copy of this cleanup (Sandbox.start's too), so EPERM for a group of zombies ends it.
        kill_group(p)


class GoldenGate(GateRig, unittest.TestCase):
    # ---- the paths through the gate

    def test_green_deletes_its_clone_under_the_lock(self):
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out[-1], 'golden-gate: GREEN ' + IMAGE)
        name = self.assert_clone_deleted_under_the_lock()
        self.assertEqual(self.f('clone-journal'), ['yes'])   # gate-clone NAME was journaled before tart clone
        self.assertEqual(self.f('realrun-args'), [name])
        self.assertEqual(self.f('emudhra-args'), ['--gate ' + name])
        self.assertIn('golden-emudhra: GATE GREEN', out)    # the gate's own lines pass through
        self.assertTrue(os.path.exists(os.path.join(self.logs, name + '-vm.log')))
        self.assertEqual(lines(self.journal), ['gate-clone ' + name])
        calls = [c.split()[0] for c in self.f('tart-calls')]
        self.assertLess(calls.index('clone'), calls.index('stop'))
        self.assertLess(calls.index('stop'), calls.index('delete'))

    def test_red_deletes_its_clone_under_the_lock(self):
        self.scen('red')
        r, out = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(out[-1], 'golden-gate: RED ' + IMAGE)
        self.assert_clone_deleted_under_the_lock()

    def test_a_gate_that_did_not_run_to_its_end_is_stop(self):
        self.scen('stop')   # exit 1 with no GATE line: could not run, not RED
        r, out = self.gate()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertTrue(any(l.startswith('golden-gate: STOP') for l in out), r.stdout)
        self.assertFalse(any(l.startswith(('golden-gate: RED', 'golden-gate: GREEN')) for l in out), r.stdout)
        self.assert_clone_deleted_under_the_lock()

    def test_exit_0_without_the_gate_green_line_is_stop(self):
        self.scen('green-no-line')
        r, out = self.gate()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertTrue(out[-1].startswith('golden-gate: STOP the gate did not run to its end'), r.stdout)
        self.assertFalse(any(l.startswith(('golden-gate: RED', 'golden-gate: GREEN')) for l in out), r.stdout)
        self.assert_clone_deleted_under_the_lock()
        # control: test_green_deletes_its_clone_under_the_lock (exit 0 with the GATE GREEN line)

    def test_a_clone_still_there_after_the_delete_is_stop(self):
        write(os.path.join(self.d, 'keep-on-delete'), '')
        r, out = self.gate()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        name = self.the_clone()
        self.assertIn('%s delete %s' % (self.tart, name), r.stdout)   # the exact delete line
        self.assertFalse(any(l.startswith('golden-gate: GREEN') for l in out), r.stdout)
        # control: the green test above (the clone gone) ends GREEN

    # ---- signals: the clone is deleted before the lock is let go

    def signalled(self, sig):
        self.scen('sleep 30')
        p = self.started('gate-started')
        os.killpg(p.pid, sig)
        out, err = p.communicate(timeout=60)
        t0 = time.time()   # with a wrapper process, the cleanup may outlive the process the test started
        while not self.f('deletes') and time.time() - t0 < 30:
            time.sleep(0.1)
        self.assert_clone_deleted_under_the_lock()
        self.assertEqual(p.returncode, 2, out + err)
        self.assertIn('golden-gate: STOP interrupted', out)

    def test_term_to_the_group(self):
        self.signalled(signal.SIGTERM)

    def test_int_to_the_group(self):
        self.signalled(signal.SIGINT)

    def test_hup_to_the_group(self):
        self.signalled(signal.SIGHUP)

    def test_term_while_tart_clone_runs_deletes_only_its_name(self):
        write(os.path.join(self.d, 'clone-block'), '')   # the stub's clone has made NAME and is still running
        p = self.started('clone-started')
        os.killpg(p.pid, signal.SIGTERM)
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 2, out + err)
        self.assertIn('golden-gate: STOP interrupted (TERM)', out)
        self.assert_clone_deleted_under_the_lock()   # NAME deleted, the lock held; no other image deleted
        self.assertEqual(self.f('realrun-args'), [])   # nothing booted
        # control: test_green_deletes_its_clone_under_the_lock (no signal)

    def test_term_with_the_clone_left_after_the_delete_is_stop(self):
        write(os.path.join(self.d, 'keep-on-delete'), '')
        self.scen('sleep 30')
        p = self.started('gate-started')
        os.killpg(p.pid, signal.SIGTERM)
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 2, out + err)
        name = self.the_clone()
        self.assertIn('golden-gate: STOP the gate clone %s may still be there: delete it with: %s delete %s'
                      % (name, self.tart, name), out)
        self.assertNotIn('golden-gate: deleted the gate clone', out)

    def test_control_no_signal(self):
        self.scen('sleep 0.2')
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_clone_deleted_under_the_lock()

    # ---- the cleanup of a started group (reap)

    def group(self, script, ready, what):
        """/bin/sh -c SCRIPT in a process group of its own, once ready(the states of its members) holds"""
        p = subprocess.Popen(['/bin/sh', '-c', script], start_new_session=True, stdin=subprocess.DEVNULL)
        self.addCleanup(lambda: p.returncode is None and self.reap(p))   # not reaped yet: its group still exists
        t0 = time.time()
        while not ready(members(p.pid)):
            self.assertLess(time.time() - t0, 30, 'the group is not ' + what + ': ' + repr(members(p.pid)))
            time.sleep(0.05)
        return p

    def test_reap_of_a_group_of_zombies_ends_with_no_error_and_reaps_it(self):
        # the end of a signal cell: golden-gate has ended, and its group holds only zombies for a moment (the leader,
        # members launchd has not reaped yet). macOS answers EPERM, not ESRCH, to killpg then.
        p = self.group('exit 0', lambda m: len(m) == 1 and m[0].startswith('Z'), 'one zombie')
        with self.assertRaises(PermissionError):   # the injection is live: the host's real answer for this group
            os.killpg(p.pid, signal.SIGKILL)
        self.reap(p)
        self.assertEqual(p.returncode, 0)          # reaped: its exit status is read

    def test_control_reap_of_a_live_group_kills_its_members(self):
        p = self.group('/bin/sleep 600 & exec /bin/sleep 600',
                       lambda m: len(m) == 2 and not any(s.startswith('Z') for s in m), 'two live members')
        self.reap(p)
        self.assertEqual(p.returncode, -signal.SIGKILL)
        t0 = time.time()
        while group_alive(p.pid):                  # the member, too, is killed
            self.assertLess(time.time() - t0, 30, 'a member lives on: ' + repr(members(p.pid)))
            time.sleep(0.05)

    # ---- refusals and stops before any clone

    def test_flag_present_refuses_with_no_tart_call(self):
        write(self.flag, '')
        r, out = self.gate()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertTrue(out[-1].startswith('golden-gate: REFUSE'), r.stdout)
        self.assert_no_tart_call()
        os.remove(self.flag)   # control
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_flag_appearing_after_the_first_check_refuses(self):
        # black-box this proves a second FLAG check after the first `tart list`; that it is under the lock is
        # test_the_flag_recheck_comes_after_the_lock (no external call runs between the lock and the check)
        write(os.path.join(self.d, 'flag-on-list'), '')
        r, out = self.gate()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertTrue(out[-1].startswith('golden-gate: REFUSE the agent is enabled'), r.stdout)
        self.assertTrue(os.path.exists(self.flag))
        self.assertEqual(self.f('tart-calls'), ['list --source local -q'])   # the first check passed; no clone
        os.remove(os.path.join(self.d, 'flag-on-list'))   # control
        os.remove(self.flag)
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_the_flag_recheck_comes_after_the_lock(self):
        src = read(os.path.join(REPO, 'bin', 'golden-gate')).splitlines()
        at = lambda pred: [i for i, l in enumerate(src) if pred(l)]
        lock = at(lambda l: l.startswith('zsystem flock '))
        checks = at(lambda l: l.startswith('[[ ! -e $FLAG ]] || refuse '))
        clone = at(lambda l: l.startswith('tart clone '))
        self.assertEqual((len(lock), len(checks), len(clone)), (1, 2, 1), (lock, checks, clone))
        self.assertLess(checks[0], lock[0])              # the first check, before the lock
        self.assertLess(lock[0], checks[1])              # the recheck: under the lock
        self.assertLess(checks[1], clone[0])             # and before any clone

    def test_lock_held_stops_with_no_clone(self):
        holder = subprocess.Popen(['/usr/bin/lockf', '-k', self.lock, '/bin/sleep', '60'], start_new_session=True,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.reap, holder)
        t0 = time.time()
        while subprocess.run(['/usr/bin/lockf', '-k', '-t', '0', self.lock, '/usr/bin/true'],
                             stderr=subprocess.DEVNULL).returncode != 75:
            self.assertLess(time.time() - t0, 10, 'the test lockf did not take the lock')
            time.sleep(0.05)
        r, out = self.gate()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertTrue(any(l.startswith('golden-gate: STOP the runner lock is held') for l in out), r.stdout)
        self.assert_no_clone()
        os.killpg(holder.pid, signal.SIGTERM)   # control: the lock free again
        holder.wait()
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_leftover_gate_clone_stops_with_no_delete(self):
        write(os.path.join(self.d, 'vms'), '\n'.join(self.vms0 + ['s1-gate-x']) + '\n')
        r, out = self.gate()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn('%s delete s1-gate-x' % self.tart, r.stdout)   # the exact delete line, for a person
        # its VM may still run (a gate killed with SIGKILL leaves real-run running): stop it, then delete it
        self.assertIn('%s stop s1-gate-x; %s delete s1-gate-x' % (self.tart, self.tart), r.stdout)
        self.assertTrue(out[-1].startswith('golden-gate: STOP'), r.stdout)
        self.assert_no_clone()
        self.assertIn('s1-gate-x', self.vms())
        write(os.path.join(self.d, 'vms'), '\n'.join(self.vms0) + '\n')   # control
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_journal_folder_missing_stops_with_no_clone(self):
        os.rmdir(os.path.dirname(self.journal))
        r, out = self.gate()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertTrue(any(l.startswith('runner-journal: STOP') for l in out), r.stdout)
        self.assertTrue(out[-1].startswith('golden-gate: STOP'), r.stdout)
        self.assert_no_clone()
        os.makedirs(os.path.dirname(self.journal))   # control
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.f('clone-journal'), ['yes'])

    def test_without_a_journal_it_prints_the_clone_name(self):
        r, out = self.gate(journal=False)
        self.assertEqual(r.returncode, 0, r.stdout)
        name = self.the_clone()
        self.assertIn('golden-gate: clone ' + name, out)
        self.assertFalse(os.path.exists(self.journal))

    def test_image_kinds_refused(self):
        for bad in ('gold-x', 's1-x', 'n1-x', 'runner-x', '-x', 'a b', ''):
            r, out = self.gate(image=bad)
            self.assertEqual(r.returncode, 2, bad)
            self.assertTrue(out and out[-1].startswith('golden-gate: REFUSE'), bad + r.stdout)
            self.assert_no_tart_call()
        r, out = self.gate(image='liveapp-mac-golden-20990101')   # not a local image
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertTrue(out[-1].startswith('golden-gate: REFUSE'), r.stdout)
        self.assert_no_clone()
        r, out = self.gate()   # control
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_usage(self):
        for argv in ([], [IMAGE, '--journal'], [IMAGE, '--log', self.journal], [IMAGE, IMAGE]):
            r = run([ZSH, '-f', self.tool] + argv, env={'HOME': self.d}, cwd=self.d)
            self.assertEqual(r.returncode, 2, argv)
            self.assert_no_tart_call()



class GateVerdicts(GateRig, unittest.TestCase):
    """golden-gate behind the REAL golden-emudhra (a copy whose tart is the same stub; the stub's exec answers each guest
    step from D/scenario/<step>.out and .rc): RED only when the gate step ran to its end with a FAIL; a step that did not
    complete is STOP, so the RED of the owed live proof can only come from the deny check."""

    def setUp(self):
        super().setUp()
        copy_script(self, 'bin/golden-emudhra', os.path.join(self.d, 'bin', 'golden-emudhra'),
                    rewrites=[('REAL=/Users/ci/Applications/tart.app/Contents/MacOS/tart', 'REAL=' + self.tart)],
                    allow_ci=('HOME=/Users/ci ',))
        excluded_copy(self, self.d)   # golden-emudhra reads its keys through tls-excluded-lib
        self.guest('save', '1. save\n')
        self.guest('gate', 'census: control USERTrust RSA: verify-cert exits 0 (pass)\ngate: no FAIL\n')

    def guest(self, step, out, rc=0):
        write(os.path.join(self.d, 'scenario', step + '.out'), out)
        write(os.path.join(self.d, 'scenario', step + '.rc'), '%d\n' % rc)

    def test_a_save_that_did_not_complete_is_stop_not_red(self):
        self.guest('save', 'STOP missing in the guest: /opt/homebrew/bin/gtimeout\n', rc=2)
        r, out = self.gate()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('golden-emudhra: GATE STOP the save step did not complete: the gate did not run', out)
        self.assertTrue(out[-1].startswith('golden-gate: STOP'), r.stdout)
        self.assertFalse(any(l.startswith(('golden-gate: RED', 'golden-gate: GREEN')) for l in out), r.stdout)
        self.assertEqual(self.f('guest-steps'), ['save'])   # the deny check never ran
        self.assert_clone_deleted_under_the_lock()

    def test_control_a_gate_fail_is_red(self):
        self.guest('gate', 'FAIL census: AAA Certificate Services (SHA-1 X): no deny in the admin trust settings (none)\n',
                   rc=1)
        r, out = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(out[-1], 'golden-gate: RED ' + IMAGE)
        self.assertEqual(self.f('guest-steps'), ['save', 'gate'])
        self.assert_clone_deleted_under_the_lock()

    def test_control_green(self):
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(out[-1], 'golden-gate: GREEN ' + IMAGE)
        self.assertEqual(self.f('guest-steps'), ['save', 'gate'])
        self.assert_clone_deleted_under_the_lock()


if __name__ == '__main__':
    unittest.main()
