"""runner-enable --check: the enable checks, the stray-VM check before the lock check, and no lock, no
runner-lock-free and no FLAG in --check. Any other argument is the usage REFUSE, with nothing run or written.

A copy runs with every host path rewritten to stubs or sandbox paths: wall-files-check, the shim, Tart, launchctl,
runner-lock-free, sw_vers, and lockf (a stub that logs its call and runs the real lockf).
"""
import hashlib
import os
import unittest

from tests.studio.support import Sandbox

SCRIPT = 'bin/runner-enable'
BUILD = '27A123'
GREEN_LIST = 'Source Name Disk Size Accessed State\nlocal liveapp-mac-golden-20261001 50 30 now stopped\n' \
             'local runner-0123abcd 50 30 now running\n'
USAGE = 'runner-enable: REFUSE usage: runner-enable [--check]\n'


class Rig:
    def __init__(self, test):
        sb = self.sb = Sandbox(test)
        fake = sb.mkdir('fake')
        self.bin = sb.mkdir('bin')
        self.scn = sb.mkdir('scenario')
        self.flag = sb.path('enabled')
        self.lock = sb.path('runner.lock')
        self.stamp = sb.path('wall-stamp')
        self.proof = sb.path('wall-proof')
        sb.stub('wall-files-check', "print -rl -- 'FILES green' 'STAMP current'", folder=self.bin)
        for t in ('wall-check', 'real-run'):
            sb.stub(t, 'exit 0', folder=self.bin)
        sb.stub('shim', "[[ $1 == --liveapp-check ]] && print -r -- 'shim check ok'", folder=fake)
        sb.stub('tart', '[[ $* == "list --source local" ]] && /bin/cat %s' % sb.path('scenario', 'tart-list'),
                folder=fake)
        sb.stub('launchctl', 'exit 0', folder=fake)
        sb.stub('runner-lock-free', 'print -r -- free', folder=fake)
        sb.stub('sw_vers', '[[ $1 == -buildVersion ]] && print -r -- ' + BUILD, folder=fake)
        sb.stub('lockf', 'exec /usr/bin/lockf "$@"', folder=fake)
        self.script = sb.copy_script(SCRIPT, [
            ('FLAG=/Users/ci/.config/runner/enabled', 'FLAG=' + self.flag),
            ('SHIM=/usr/local/libexec/liveapp-ci/tart', 'SHIM=' + os.path.join(fake, 'shim')),
            ('REAL=/Users/ci/Applications/tart.app/Contents/MacOS/tart', 'REAL=' + os.path.join(fake, 'tart')),
            ('LOCK=/tmp/runner.lock', 'LOCK=' + self.lock),
            ('WALLPROOF=/Users/ci/.config/runner/wall-proof', 'WALLPROOF=' + self.proof),
            ('STAMP=/Users/ci/.config/runner/wall-stamp', 'STAMP=' + self.stamp),
            ('BIN=/Users/ci/bin\n', 'BIN=%s\n' % self.bin),
            ('WFC=/Users/ci/bin/wall-files-check', 'WFC=' + os.path.join(self.bin, 'wall-files-check')),
            ('LOCKFREE=/Users/ci/bin/runner-lock-free', 'LOCKFREE=' + os.path.join(fake, 'runner-lock-free')),
            ('HOME=/Users/ci ', 'HOME=%s ' % sb.home),
            ('/bin/launchctl print', os.path.join(fake, 'launchctl') + ' print'),
            ('/usr/bin/sw_vers', os.path.join(fake, 'sw_vers')),
            ('/usr/bin/lockf', os.path.join(fake, 'lockf')),
        ])
        sb.write(self.stamp, 'tart 2.41.1\nmacos %s\n' % BUILD)
        lines = []
        for t in ('wall-check', 'real-run', 'wall-files-check'):
            with open(os.path.join(self.bin, t), 'rb') as f:
                lines.append('%s %s' % (t, hashlib.sha256(f.read()).hexdigest()))
        sb.write(self.proof, '\n'.join(lines) + '\n')
        self.tart_list(GREEN_LIST)

    def tart_list(self, text):
        self.sb.write(os.path.join(self.scn, 'tart-list'), text)

    def run(self, *args):
        return self.sb.run(['/bin/zsh', '-f', self.script] + list(args))

    def calls(self, name):
        return self.sb.calls(name)


class TestCheck(unittest.TestCase):
    def test_check_passes_and_writes_nothing(self):
        r = Rig(self)
        res = r.run('--check')
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, 'runner-enable: check passed (shim check ok)\n', ''))
        self.assertFalse(os.path.exists(r.flag))
        self.assertEqual(r.calls('runner-lock-free'), [])
        self.assertEqual(r.calls('lockf'), [])
        self.assertEqual(r.calls('shim'), [['--liveapp-check']])        # the checks did run
        self.assertEqual(r.calls('tart'), [['list', '--source', 'local']])

    def test_check_passes_while_the_lock_is_held(self):
        r = Rig(self)
        r.sb.stub('runner-lock-free', 'print -r -- held; exit 1', folder=r.sb.path('fake'))
        res = r.run('--check')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(os.path.exists(r.flag))

    def test_control_enable_writes_the_flag(self):
        r = Rig(self)
        res = r.run()
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, 'runner-enable: enabled (shim check ok)\n', ''))
        self.assertTrue(os.path.isfile(r.flag))
        self.assertEqual(len(r.calls('runner-lock-free')), 1)
        self.assertEqual([c[:4] for c in r.calls('lockf')], [['-k', '-t', '0', r.lock]])

    def test_check_refuses_a_stamp_mismatch(self):
        r = Rig(self)
        r.sb.write(r.stamp, 'tart 2.41.1\nmacos 26Z999\n')
        res = r.run('--check')
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn('runner-enable: REFUSE the wall was proven on macOS build 26Z999', res.stderr)
        self.assertFalse(os.path.exists(r.flag))

    def test_check_refuses_a_stray_vm(self):
        r = Rig(self)
        r.tart_list(GREEN_LIST + 'local gold-20261001 50 30 now running\n')
        res = r.run('--check')
        self.assertEqual((res.returncode, res.stderr),
                         (1, 'runner-enable: REFUSE a VM outside runscaler is running: gold-20261001\n'))
        self.assertFalse(os.path.exists(r.flag))

    def test_stray_vm_is_checked_before_the_lock(self):
        r = Rig(self)
        r.tart_list(GREEN_LIST + 'local gold-20261001 50 30 now running\n')
        r.sb.stub('runner-lock-free', 'print -r -- held; exit 1', folder=r.sb.path('fake'))
        res = r.run()
        self.assertEqual((res.returncode, res.stderr),
                         (1, 'runner-enable: REFUSE a VM outside runscaler is running: gold-20261001\n'))
        self.assertEqual(r.calls('runner-lock-free'), [])
        self.assertFalse(os.path.exists(r.flag))


class TestUsage(unittest.TestCase):
    def test_any_other_argument_is_refused(self):
        for args in (['--bogus'], ['--check', 'x'], ['check'], [''], ['--check', '--check']):
            with self.subTest(args=args):
                r = Rig(self)
                res = r.run(*args)
                self.assertEqual((res.returncode, res.stdout, res.stderr), (1, '', USAGE))
                self.assertFalse(os.path.exists(r.flag))
                for stub in ('wall-files-check', 'shim', 'tart', 'launchctl', 'runner-lock-free', 'lockf'):
                    self.assertEqual(r.calls(stub), [], stub)


if __name__ == '__main__':
    unittest.main()
