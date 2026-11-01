"""golden-build: --date, the clock read once, an existing output, cleanup on TERM, the host pin, --print-runner.

A REAL golden-build copy runs with its host paths rewritten into a sandbox. Stub tart keeps its VMs as files in
the sandbox and answers the guest commands; stub real-run waits until `tart stop` kills it; a stub golden-emudhra
beside the copy exits 0; stub `date` and `sw_vers` are on PATH. The stub `date` answers `+%Y%m%d` with CLOCK[0]
on its first call and CLOCK[1] after, so a build that reads the clock twice shows two dates.
"""
import os
import re
import shlex
import signal
import unittest

from tests.studio.support import REPO, Sandbox

SCRIPT = 'bin/golden-build'
D = '20261102'
CLOCK = ('20261103', '20261104')
OLD = 'liveapp-mac-golden-20261001'   # an earlier image on the host: no call may name it
PIN_V = '2.399.1'
PIN_SHA = '0123456789abcdef' * 4
URL = 'https://github.com/actions/runner/releases/download/v{0}/actions-runner-osx-arm64-{0}.tar.gz'
NAME = re.compile(r'^(gold-[0-9]+|liveapp-mac-golden-[0-9]+)$')


def literal(name):
    with open(os.path.join(REPO, SCRIPT)) as f:
        return re.search(r'^%s=(\S+)' % name, f.read(), re.M).group(1)


LIT_V = literal('RUNNER_VERSION')
LIT_SHA = literal('RUNNER_SHA')
MAJOR = literal('BASE_MACOS_MAJOR')

TART = r'''
VMS=%(vms)s SCN=%(scn)s PIDF=%(pidf)s
cmd=$1; shift
case $cmd in
  (list) /bin/ls -1 $VMS ;;
  (pull) ;;
  (clone)
    [[ ! -e $VMS/$2 ]] || { print -u2 -r -- "tart stub: $2 exists"; exit 1 }
    : > $VMS/$2
    if [[ -e $SCN/block-clone-$2 ]]; then : > $SCN/blocked-clone-$2; exec /bin/sleep 600; fi ;;
  (set) ;;
  (stop)
    n=0; until [[ -s $PIDF ]]; do (( n++ < 200 )) || exit 1; /bin/sleep 0.05; done
    kill $(<$PIDF) 2>/dev/null; : ;;
  (delete) [[ -e $VMS/$1 ]] || exit 1; /bin/rm -f -- $VMS/$1 ;;
  (exec)
    shift
    case "$*" in
      (true) ;;
      ('diskutil list disk0') print -r -- '   2:   Apple_APFS Container disk3   100.0 GB   disk0s2' ;;
      ('sw_vers -productVersion') print -r -- %(major)s.0 ;;
      ('networksetup -listallnetworkservices') print -rl -- 'An asterisk (*) denotes a disabled service.' Ethernet ;;
      ('networksetup -getdnsservers Ethernet') print -rl -- 1.1.1.1 8.8.8.8 ;;
      ('/Users/admin/actions-runner/config.sh --version') print -r -- "$(<$SCN/guest-runner-version)" ;;
      ('sudo launchctl print-disabled system')
        print -rl -- '"com.openssh.sshd" => disabled' '"com.apple.screensharing" => disabled' ;;
      ('df -k /') print -rl -- 'Filesystem 1024-blocks Used Available Capacity Mounted' '/dev/disk3s1 1 1 31457280 1%% /' ;;
    esac ;;
  (*) exit 2 ;;
esac
'''

DATE = r'''
if [[ $1 == +%%Y%%m%%d ]]; then
  n=$(( $(/bin/cat %(cnt)s 2>/dev/null || print 0) + 1 ))
  print -r -- $n > %(cnt)s
  (( n == 1 )) && print -r -- %(d1)s || print -r -- %(d2)s
else
  exec /bin/date "$@"
fi
'''


def q(p):
    return shlex.quote(p)


class Rig:
    def __init__(self, test, cat_body=None):
        self.test = test
        sb = self.sb = Sandbox(test)
        self.vms = sb.mkdir('vms')
        self.scn = sb.mkdir('scenario')
        self.logdir = sb.mkdir('logdir')
        self.flag = sb.path('enabled')
        self.lock = sb.path('runner.lock')
        self.pin = sb.path('state', 'pin', 'mac-golden')
        fake = sb.mkdir('fake')
        sb.stub('tart', TART % {'vms': q(self.vms), 'scn': q(self.scn), 'pidf': q(sb.path('realrun.pid')),
                                'major': MAJOR}, folder=fake)
        sb.stub('real-run', 'print -r -- $$ > %s\nexec /bin/sleep 600' % q(sb.path('realrun.pid')), folder=fake)
        self.script = sb.copy_script(SCRIPT, [
            ('REAL=/Users/ci/Applications/tart.app/Contents/MacOS/tart', 'REAL=' + os.path.join(fake, 'tart')),
            ('REALRUN=/Users/ci/bin/real-run', 'REALRUN=' + os.path.join(fake, 'real-run')),
            ('LOCK=/tmp/runner.lock', 'LOCK=' + self.lock),
            ('FLAG=/Users/ci/.config/runner/enabled', 'FLAG=' + self.flag),
            ('LOGDIR=/Users/ci/Library/Logs/mac-runner', 'LOGDIR=' + self.logdir),
            ('STATEDIR=/Users/ci/.local/state/runner-updater', 'STATEDIR=' + sb.path('state')),
            ('HOME=/Users/ci ', 'HOME=%s ' % sb.home),
            ('vol=/Users/ci/.tart; [[ -d $vol ]] || vol=/Users/ci', 'vol=%s' % sb.home),
            ('FLOOR_GIB=200', 'FLOOR_GIB=0'),
        ] + ([] if cat_body is None else [('/bin/cat -- $f', sb.stub('cat', cat_body, folder=fake) + ' -- $f')]),
            allow=['Run as ci on the host: /Users/ci/bin/golden-build'])
        sb.stub('golden-emudhra', 'exit 0', folder=os.path.dirname(self.script))
        sb.stub('date', DATE % {'cnt': q(sb.path('date.count')), 'd1': CLOCK[0], 'd2': CLOCK[1]})
        sb.stub('sw_vers', 'print -r -- %s.0' % MAJOR)
        self.guest_version(LIT_V)
        sb.write(os.path.join(self.vms, OLD), '')

    def guest_version(self, v):
        self.sb.write(os.path.join(self.scn, 'guest-runner-version'), v + '\n')

    def write_pin(self, text):
        self.sb.write(self.pin, text, 0o600)

    def run(self, *args):
        return self.sb.run(['/bin/zsh', '-f', self.script] + list(args))

    def tart(self):
        return self.sb.calls('tart')

    def names(self):
        return {a for c in self.tart() for a in c if NAME.match(a)}

    def clock_reads(self):
        return [c for c in self.sb.calls('date') if c == ['+%Y%m%d']]

    def log(self, date):
        with open(os.path.join(self.logdir, 'golden-%s.log' % date)) as f:
            return f.read()

    def download(self):
        cmds = [c[4] for c in self.tart() if c[:1] == ['exec'] and c[2:4] == ['sh', '-c'] and 'curl' in c[4]]
        self.test.assertEqual(len(cmds), 1, self.tart())
        return cmds[0]

    def hold_lock(self):
        p = self.sb.start(['/usr/bin/lockf', '-k', '-t', '0', self.lock, '/bin/zsh', '-f', '-c',
                           'print -r -- held; exec /bin/sleep 600'], name='holder')
        self.sb.wait_for(lambda: self.sb.output('holder')[0] == 'held\n' or p.poll() is not None, 'the lock holder')
        self.test.assertIsNone(p.poll(), 'the test could not take the lock: %r' % (self.sb.output('holder'),))


class TestDate(unittest.TestCase):
    def test_a_date_names_every_artefact(self):
        r = Rig(self)
        res = r.run('--date', D)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('DONE: liveapp-mac-golden-%s' % D, res.stdout)
        self.assertIn('DONE: liveapp-mac-golden-%s' % D, r.log(D))
        self.assertTrue(os.path.exists(os.path.join(r.logdir, 'golden-%s-vm.log' % D)))
        self.assertEqual(sorted(os.listdir(r.logdir)), ['golden-%s-vm.log' % D, 'golden-%s.log' % D])
        self.assertEqual(r.names(), {'gold-' + D, 'liveapp-mac-golden-' + D})
        self.assertEqual(r.sb.calls('real-run'), [['gold-' + D]])
        self.assertEqual(sorted(os.listdir(r.vms)), sorted([OLD, 'liveapp-mac-golden-' + D]))
        self.assertEqual(r.clock_reads(), [], 'with --date the clock is not read for the date')

    def test_b_clock_read_once(self):
        r = Rig(self)
        res = r.run()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        d = CLOCK[0]
        self.assertIn('DONE: liveapp-mac-golden-%s' % d, res.stdout)
        self.assertEqual(sorted(os.listdir(r.logdir)), ['golden-%s-vm.log' % d, 'golden-%s.log' % d])
        self.assertEqual(r.names(), {'gold-' + d, 'liveapp-mac-golden-' + d})
        self.assertEqual(r.sb.calls('real-run'), [['gold-' + d]])
        self.assertEqual(len(r.clock_reads()), 1)

    def test_c_existing_output_is_never_touched(self):
        r = Rig(self)
        out = os.path.join(r.vms, 'liveapp-mac-golden-' + D)
        r.sb.write(out, 'the image')
        res = r.run('--date', D)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn('golden-build: STOP liveapp-mac-golden-%s already exists' % D, res.stdout)
        touched = [c for c in r.tart() if c[:1] in (['clone'], ['delete'], ['stop']) and
                   'liveapp-mac-golden-' + D in c]
        self.assertEqual(touched, [])
        with open(out) as f:
            self.assertEqual(f.read(), 'the image')

    def term_while_blocked(self, dst):
        r = Rig(self)
        r.sb.write(os.path.join(r.scn, 'block-clone-' + dst), '')
        p = r.sb.start(['/bin/zsh', '-f', r.script, '--date', D], name='build')
        blocked = os.path.join(r.scn, 'blocked-clone-' + dst)
        r.sb.wait_for(lambda: os.path.exists(blocked) or p.poll() is not None, 'the clone to block')
        self.assertTrue(os.path.exists(blocked), r.sb.output('build'))
        os.killpg(p.pid, signal.SIGTERM)

        def group_gone():
            if p.poll() is None:
                return False
            try:
                os.killpg(p.pid, 0)
            except ProcessLookupError:
                return True
            return False
        r.sb.wait_for(group_gone, 'every process of the build to end')
        return r

    def assert_cleaned(self, r):
        deletes = [c for c in r.tart() if c[:1] == ['delete']]
        self.assertIn(['delete', 'gold-' + D], deletes, r.tart())
        self.assertFalse(os.path.exists(os.path.join(r.vms, 'gold-' + D)))
        self.assertEqual([c for c in deletes if any(a.startswith('liveapp-mac-golden-') for a in c)], [])
        self.assertTrue(os.path.exists(os.path.join(r.vms, OLD)))

    def test_d_term_during_first_clone(self):
        r = self.term_while_blocked('gold-' + D)
        self.assert_cleaned(r)

    def test_d_term_during_final_clone(self):
        r = self.term_while_blocked('liveapp-mac-golden-' + D)
        self.assertIn(['stop', 'gold-' + D], r.tart())   # it got as far as the final clone
        self.assert_cleaned(r)


GOOD_PIN = '%s %s\n' % (PIN_V, PIN_SHA)


def _symlink_pin(r):
    target = r.sb.write(r.sb.path('elsewhere', 'pin'), GOOD_PIN)
    os.makedirs(os.path.dirname(r.pin), exist_ok=True)
    os.symlink(target, r.pin)


def _unreadable_pin(r):
    r.write_pin(GOOD_PIN)
    os.chmod(r.pin, 0)


def _pin_text(t):
    return lambda r: r.write_pin(t)


BAD_PINS = [
    ('two lines', _pin_text(GOOD_PIN + GOOD_PIN)),
    ('a second, empty line', _pin_text(GOOD_PIN + '\n')),
    ('a bad sha', _pin_text('%s %s\n' % (PIN_V, PIN_SHA[:-1] + 'g'))),
    ('an upper-case sha', _pin_text('%s %s\n' % (PIN_V, PIN_SHA.upper()))),
    ('a short sha', _pin_text('%s %s\n' % (PIN_V, PIN_SHA[:-1]))),
    ('a bad version', _pin_text('2.399 %s\n' % PIN_SHA)),
    ('two spaces', _pin_text('%s  %s\n' % (PIN_V, PIN_SHA))),
    ('a NUL byte', _pin_text('%s %s\0x\n' % (PIN_V, PIN_SHA))),
    ('an empty file', _pin_text('')),
    ('a symlink to a valid file', _symlink_pin),
    ('unreadable', _unreadable_pin),
    ('a directory', lambda r: os.makedirs(r.pin)),
]


class TestPin(unittest.TestCase):
    def assert_built_with(self, r, res, v, sha, source):
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        cmd = r.download()
        self.assertIn(' -o /tmp/runner.tgz %s && ' % URL.format(v), cmd)
        self.assertIn("echo '%s  /tmp/runner.tgz'" % sha, cmd)
        self.assertEqual(r.sb.calls('golden-emudhra'), [['gold-' + D, '/tmp/runner.tgz', sha]])
        log = r.log(D)
        self.assertRegex(log, r'golden-build: \S+ runner %s\n' % re.escape(v))
        start = [l for l in log.splitlines() if ' start: liveapp-mac-golden-%s from ' % D in l]
        self.assertEqual(len(start), 1, log)
        self.assertTrue(start[0].endswith(', runner %s (%s)' % (v, source)), start[0])

    def test_e_pin_wins(self):
        r = Rig(self)
        r.write_pin(GOOD_PIN)
        r.guest_version(PIN_V)
        res = r.run('--date', D)
        self.assert_built_with(r, res, PIN_V, PIN_SHA, 'host pin')
        self.assertNotIn(URL.format(LIT_V), r.download())

    def test_e_control_no_pin_uses_the_literals(self):
        r = Rig(self)
        res = r.run('--date', D)
        self.assert_built_with(r, res, LIT_V, LIT_SHA, 'release literal')

    def test_e_pin_version_is_the_one_checked(self):
        r = Rig(self)
        r.write_pin(GOOD_PIN)
        r.guest_version(LIT_V)
        res = r.run('--date', D)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn('golden-build: STOP runner version %s, want %s' % (LIT_V, PIN_V), res.stdout)
        self.assertNotIn('DONE:', res.stdout)

    def test_e_bad_pin_stops_before_the_flag_and_the_lock(self):
        for label, make in BAD_PINS:
            with self.subTest(label):
                r = Rig(self)
                make(r)
                r.sb.write(r.flag, '')
                r.hold_lock()
                res = r.run('--date', D)
                self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
                self.assertEqual(res.stdout, "golden-build: STOP host pin %s is not one line 'VERSION SHA256'\n"
                                 % r.pin)
                self.assertEqual(r.tart(), [])
                self.assertEqual(os.listdir(r.logdir), [], 'nothing reached the locked step')

    def test_e_pin_read_failure_stops(self):
        # cat prints a good pin, then fails: the pin is not trusted
        r = Rig(self, cat_body='/bin/cat $2; exit 1')
        r.write_pin(GOOD_PIN)
        res = r.run('--print-runner')
        self.assertEqual((res.returncode, res.stdout),
                         (1, "golden-build: STOP host pin %s is not one line 'VERSION SHA256'\n" % r.pin))
        r = Rig(self, cat_body='/bin/cat $2; exit 0')   # the control: the same read, no failure
        r.write_pin(GOOD_PIN)
        res = r.run('--print-runner')
        self.assertEqual((res.returncode, res.stdout), (0, 'host pin %s (release literal %s)\n' % (PIN_V, LIT_V)))

    def test_e_pin_in_a_folder_that_cannot_be_searched_stops(self):
        # stat cannot tell "absent" from "behind a closed folder": a closed folder must not read as "no pin"
        for folder in ('pin', ''):
            with self.subTest(folder=folder or 'state'):
                r = Rig(self)
                r.write_pin(GOOD_PIN)
                os.chmod(r.sb.path('state', folder) if folder else r.sb.path('state'), 0o600)
                res = r.run('--print-runner')
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertTrue(res.stdout.startswith("golden-build: STOP host pin %s is not one line 'VERSION SHA256'"
                                                      % r.pin), res.stdout)
        r = Rig(self)   # the control: the same folders, searchable
        r.write_pin(GOOD_PIN)
        os.chmod(r.sb.path('state', 'pin'), 0o700)
        os.chmod(r.sb.path('state'), 0o700)
        res = r.run('--print-runner')
        self.assertEqual((res.returncode, res.stdout), (0, 'host pin %s (release literal %s)\n' % (PIN_V, LIT_V)))

    def test_e_control_flag_and_lock_are_live(self):
        r = Rig(self)
        r.write_pin(GOOD_PIN)
        r.sb.write(r.flag, '')
        res = r.run('--date', D)
        self.assertIn('golden-build: STOP the agent is enabled', res.stdout)
        os.unlink(r.flag)
        r.hold_lock()
        res = r.run('--date', D)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn('golden-build: STOP the runner lock is held', res.stdout)
        self.assertEqual(r.tart(), [])


class TestPrintRunner(unittest.TestCase):
    def print_runner(self, setup):
        r = Rig(self)
        setup(r)
        r.sb.write(r.flag, '')
        r.hold_lock()
        res = r.run('--print-runner')
        self.assertEqual(r.tart(), [])
        self.assertEqual(r.sb.calls('real-run'), [])
        self.assertEqual(os.listdir(r.logdir), [])
        return r, res

    def test_f_no_pin(self):
        _, res = self.print_runner(lambda r: None)
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, 'release literal %s (no host pin)\n' % LIT_V, ''))

    def test_f_pin(self):
        for text in (GOOD_PIN, GOOD_PIN.rstrip('\n')):
            with self.subTest(text=text):
                _, res = self.print_runner(_pin_text(text))
                self.assertEqual((res.returncode, res.stdout, res.stderr),
                                 (0, 'host pin %s (release literal %s)\n' % (PIN_V, LIT_V), ''))

    def test_f_bad_pin(self):
        r, res = self.print_runner(_pin_text(GOOD_PIN + GOOD_PIN))
        self.assertEqual((res.returncode, res.stdout),
                         (1, "golden-build: STOP host pin %s is not one line 'VERSION SHA256'\n" % r.pin))


class TestUsage(unittest.TestCase):
    def test_usage_refused(self):
        for args in (['--bogus'], ['--date'], ['--date', '20261332'], ['--date', '20260230'], ['--date', '2026110'],
                     ['--date', 'x20261102'], ['--date', D, 'extra'], ['--print-runner', 'extra'], [D]):
            with self.subTest(args=args):
                r = Rig(self)
                res = r.run(*args)
                self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
                self.assertTrue(res.stdout.startswith('golden-build: STOP usage: '), res.stdout)
                self.assertEqual(r.tart(), [])
                self.assertEqual(os.listdir(r.logdir), [])

    def test_locked_child_rechecks_its_arguments(self):
        good = [D, LIT_V, LIT_SHA, 'release-literal']
        for i, bad in ((0, '20261332'), (1, '2.338'), (2, LIT_SHA.upper()), (3, 'anything')):
            with self.subTest(arg=i):
                r = Rig(self)
                args = list(good)
                args[i] = bad
                res = r.run('--locked', *args)
                self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
                self.assertTrue(res.stdout.startswith('golden-build: STOP '), res.stdout)
                self.assertEqual(r.tart(), [])
                self.assertEqual(r.clock_reads(), [])

    def test_locked_child_control(self):
        r = Rig(self)
        res = r.run('--locked', D, LIT_V, LIT_SHA, 'release-literal')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('DONE: liveapp-mac-golden-%s' % D, res.stdout)
        self.assertEqual(r.clock_reads(), [])


if __name__ == '__main__':
    unittest.main()
