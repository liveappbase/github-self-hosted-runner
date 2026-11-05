"""RECOVER stops the record's own leftover VMs (S3b-5 A6; PLAN D1: "RECOVER's busy wait stops the record's own journaled
gate clone ..., as it stops a journaled builder's VM").

In RECOVER's busy read (ru_rc_busy), FIRST, before its lsof tool check: when tart lists running one of the record's
own VMs, `tart stop NAME` by the journaled name, matched exactly: the `gate-clone` name (s1-gate-<14 digits>); for a
`kind switch` record, its work VM (the second `image` line, gold-<8 digits>). At each busy read (a failed stop is tried
again). Never a rollback record's `image` lines; never by a prefix. Then step 3 deletes them by the existing rules.

The rig is test_runner_updater_window's (Win). Its fake tart here: `stop NAME` removes scn/running-NAME and ends the
real-run that runs it (scn/vmpid-NAME), and fails on call N when scn/stop-fail.N exists. A window is SIGKILLed with its
tool (the pass and golden-gate, or the pass and golden-build) while real-run and the VM run on.
"""
import os
import signal
import unittest

from tests.studio.test_runner_updater import read_text
from tests.studio.test_runner_updater_recover import assert_closed, assert_runs, killed, recover, stops
from tests.studio.test_runner_updater_rollback import NEW, rb_win
from tests.studio.test_runner_updater_window import FAM, KILLED, OLD, TART_LIST, Win, today
from tests.studio import test_golden_build as gb

CLONE = 's1-gate-20300101000000'
STOP = '''  (stop)
    n=$(( $(/bin/cat $SCN/stop.n 2>/dev/null || print 0) + 1 )); print -r -- $n > $SCN/stop.n
    [[ -f $SCN/stop-fail.$n ]] && { print -u2 -r -- "tart stub: stop failed"; exit 1 }
    /bin/rm -f -- $SCN/running-$1
    [[ -s $SCN/vmpid-$1 ]] && kill $(<$SCN/vmpid-$1) 2>/dev/null
    : ;;
'''
OLD_STOP = '''  (stop)
    n=0; until [[ -s $PIDF ]]; do (( n++ < 200 )) || exit 1; /bin/sleep 0.05; done
    kill $(<$PIDF) 2>/dev/null; : ;;
'''
# the VM NAME starts and its real-run runs on (a process that holds no tool of the window: real-run execs tart)
VM_UP = ''': > %(vms)s/$vm; : > %(scn)s/running-$vm
/bin/sleep 600 &!
print -r -- $! > %(scn)s/vmpid-$vm
'''
# golden-gate: it journals its clone, the clone runs, then the pass and golden-gate are SIGKILLed (scn/emudhra: a
# golden-emudhra that drives the clone runs on beside it, holding its tool open until the clone stops)
GATE = '''S=%(scn)s
img=$1 j=$3
/bin/zsh -f ${0:A:h}/runner-journal $j gate-clone %(clone)s || exit 2
vm=%(clone)s
''' + VM_UP + '''
if [[ -f $S/emudhra ]]; then
  /bin/zsh -f ${0:A:h}/golden-emudhra --gate %(clone)s &!
  n=0; until [[ -f $S/emudhra-up ]]; do (( n++ < 400 )) || exit 3; /bin/sleep 0.05; done
fi
kill -KILL $PPID; kill -KILL $$
'''
EMUDHRA = '''S=%(scn)s
[[ $1 == --gate ]] || exit 0
: > $S/emudhra-up
until [[ ! -e $S/running-$2 ]]; do /bin/sleep 0.05; done
'''
# golden-build's hook: its work VM gold-DATE runs, then the pass and golden-build are SIGKILLed
BUILD_HOOK = 'vm=gold-$2\n' + VM_UP + 'kill -KILL $PPID; kill -KILL $$\n'


def stop_calls(w):
    return [c for c in w.calls('tart') if c[:1] == ['stop']]


def vm_win(test, wait=10, **kw):
    """a Win whose fake tart stops a VM (and its real-run), RECOVER_WAIT = WAIT s"""
    w = Win(test, extra_rewrites=[('RECOVER_WAIT=20', 'RECOVER_WAIT=%d' % wait)], **kw)
    test.assertIn(OLD_STOP, gb.TART)
    w.sb.stub('tart', gb.TART.replace(*TART_LIST).replace(OLD_STOP, STOP) % {
        'vms': gb.q(w.vms), 'scn': gb.q(w.scn), 'pidf': gb.q(w.sb.path('realrun.pid')), 'major': gb.MAJOR},
        folder=w.sb.path('fake'))
    test.addCleanup(end_vms, w)
    return w


def end_vms(w):
    for n in os.listdir(w.scn):
        if n.startswith('vmpid-'):
            try:
                os.kill(int(read_text(os.path.join(w.scn, n))), signal.SIGKILL)
            except (ValueError, ProcessLookupError):
                pass


def killed_in_the_gate(test, emudhra=False, **kw):
    w = vm_win(test, **kw)
    v = {'scn': w.scn, 'vms': w.vms, 'clone': CLONE}
    w.sb.stub('golden-gate', GATE % v, folder=w.tools)
    w.sb.stub('golden-emudhra', EMUDHRA % v, folder=w.tools)
    if emudhra:
        w.put('emudhra')
    res = w.run('rebuild')
    test.assertEqual(res.returncode, KILLED, res.stdout + res.stderr)
    test.assertEqual(w.keys()[-1], 'gate-clone')
    test.assertTrue(os.path.exists(os.path.join(w.scn, 'running-' + CLONE)))
    return w


def killed_in_the_build(test, **kw):
    w = vm_win(test, **kw)
    w.hook('build-hook', BUILD_HOOK % {'scn': w.scn, 'vms': w.vms})
    res = w.run('rebuild')
    test.assertEqual(res.returncode, KILLED, res.stdout + res.stderr)
    test.assertEqual(w.keys()[-1], 'build-start')
    test.assertTrue(os.path.exists(os.path.join(w.scn, 'running-gold-' + today())))
    return w


class TestRecoverStopsTheRecordsOwnVms(unittest.TestCase):
    def assert_back_at_once(self, w, res, name):
        """RECOVER stopped NAME, step 3 deleted it, and CI came back within the wait (no CI DISABLED)"""
        self.assertIn('runner-updater: recover: tart stop %s (the window\'s own VM, still running): exit 0\n' % name,
                      res.stdout)
        self.assertNotIn('CI DISABLED', res.stdout)
        self.assertIn(['stop', name], stop_calls(w))
        self.assertIn('delete ' + name, w.journal())
        self.assertFalse(os.path.exists(os.path.join(w.vms, name)))
        assert_closed(self, w)
        assert_runs(self, w, w.pre)
        self.assertEqual(stops(w), ['check failed'])

    def test_a_window_killed_in_the_gate_its_clone_is_stopped_and_deleted(self):
        w = killed_in_the_gate(self)
        res = recover(w, ok=1)
        self.assert_back_at_once(w, res, CLONE)
        self.assertEqual(stop_calls(w), [['stop', CLONE]])

    def test_a_window_killed_in_the_build_its_work_vm_is_stopped_and_deleted(self):
        w = killed_in_the_build(self)
        res = recover(w, ok=1)
        self.assert_back_at_once(w, res, 'gold-' + today())
        self.assertEqual(stop_calls(w), [['stop', 'gold-' + today()]])

    def test_the_stop_comes_before_the_tool_check(self):
        # a golden-emudhra still drives the clone (its tool open: lsof sees it) and ends only when the clone stops
        w = killed_in_the_gate(self, emudhra=True)
        res = recover(w, ok=1)
        self.assert_back_at_once(w, res, CLONE)

    def test_a_stop_that_fails_is_tried_again_at_the_next_read(self):
        w = killed_in_the_gate(self)
        w.put('stop-fail.1')
        res = recover(w, ok=1)
        self.assertIn('runner-updater: recover: tart stop %s (the window\'s own VM, still running): exit 1\n' % CLONE,
                      res.stdout)
        self.assert_back_at_once(w, res, CLONE)
        self.assertEqual(stop_calls(w), [['stop', CLONE], ['stop', CLONE]])


class TestControlsNoStop(unittest.TestCase):
    def test_control_a_gate_and_a_build_that_ended_stop_nothing(self):
        # each one's VM is still in tart's list, STOPPED (its tool stopped it and was cut before its delete)
        for key, vm in (('gate', CLONE), ('build-done', 'gold-' + today())):
            with self.subTest(killed_after=key):
                w = killed(self, key, vm_win(self))
                w.sb.write(os.path.join(w.vms, vm), '')
                recover(w, ok=1)
                self.assertEqual(stop_calls(w), [])
                assert_closed(self, w)

    def test_control_a_running_vm_that_is_not_the_record_s_is_not_stopped(self):
        w = killed(self, 'gate-start', vm_win(self, wait=1))
        for name in ('gold-20290101', 's1-gate-20290101000000', 'gold-' + today() + '0', CLONE[:-1]):
            w.sb.write(os.path.join(w.vms, name), '')
            w.put('running-' + name)
        res = recover(w, ok=1)
        self.assertEqual(stop_calls(w), [])
        self.assertIn('runner-updater: STOP CI DISABLED: ', res.stdout)   # they hold RECOVER, as before
        self.assertTrue(os.path.exists(w.u.window))

    def rollback_killed(self, second=None):
        """a rollback window killed after its runner-disable; SECOND: its second `image` line planted as that name"""
        w = rb_win(self, extra_rewrites=[('RECOVER_WAIT=20', 'RECOVER_WAIT=1')])
        w.sb.stub('tart', gb.TART.replace(*TART_LIST).replace(OLD_STOP, STOP) % {
            'vms': gb.q(w.vms), 'scn': gb.q(w.scn), 'pidf': gb.q(w.sb.path('realrun.pid')), 'major': gb.MAJOR},
            folder=w.sb.path('fake'))
        res = w.run('back', env={'RU_KILL_AT': 'disable-done'})
        self.assertEqual(res.returncode, KILLED, res.stdout + res.stderr)
        self.assertEqual(w.value('kind'), 'rollback')
        images = [l for l in w.journal() if l.startswith('image ')]
        self.assertEqual(images, ['image ' + NEW, 'image ' + OLD])
        if second:
            with open(w.u.window) as f:
                text = f.read()
            with open(w.u.window, 'w') as f:
                f.write(text.replace('image %s\n' % OLD, 'image %s\n' % second, 1))
        return w

    def test_control_a_rollback_record_s_running_target_is_not_stopped(self):
        w = self.rollback_killed()
        w.put('running-' + OLD)
        recover(w)
        self.assertEqual(stop_calls(w), [])
        assert_closed(self, w)

    def test_control_a_rollback_record_s_second_image_of_a_work_vm_s_shape_is_not_stopped(self):
        # planted: a rollback's second `image` line never names a work VM; this one does, so only the record's KIND
        # keeps RECOVER from stopping it
        name = 'gold-' + today()
        w = self.rollback_killed(second=name)
        w.sb.write(os.path.join(w.vms, name), '')
        w.put('running-' + name)
        recover(w, ok=1)
        self.assertEqual(stop_calls(w), [])


if __name__ == '__main__':
    unittest.main()
