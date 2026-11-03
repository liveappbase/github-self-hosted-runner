"""bin/runner-updater's SWITCH slice: `rebuild FAMILY` and `switch-now FAMILY`, ONE switch window (PLAN D5, "STUDIO
WINDOW") of bin/runner-updater-window, for the family mac-golden (its builder: golden-build).

The rig is test_runner_updater's (every path constant rewritten into a sandbox; ps and curl stubs; the real core), plus
a fake host. FLAG is a file. runner-disable (a stub in the release's bin/) removes it and takes runscaler out of the ps
output (scn/keep-proc.N: its call N leaves it there), and its call N appends scn/drain.N to runner.log (the stopped
runscaler's last records); runner-enable writes it (scn/no-flag.N: not) and puts a runscaler started NOW into the ps
output (launchd's start), sources scn/enable-hook.N, refuses with scn/enable-refuse.N's text (empty: the stamp's), and
records the config's mtime and sha as it is called; its --check passes. runner-start validate answers from a scenario
(scn/validate-prehook.N runs before it reads the config, scn/validate-hook.N after). golden-build
is a stub that makes the image in the fake tart's list (or the REAL golden-build copy with stub tart, for the --date
identity and an interrupt at clone and at publication); golden-gate is a stub that journals its clone and says GREEN;
df and du are stubs. runner-journal and validate-class are the real ones; a copy of runner-journal can SIGKILL its
caller right after it wrote one KEY (RU_KILL_AT), so a cell sees what a kill at that step boundary leaves.
"""
import hashlib
import json
import os
import pwd
import signal
import subprocess
import time
import unittest

from tests.studio.test_runner_updater import BACKGROUND, FIX, HEALTHZ, IMG, IMG2, P, Rig, config, proc_line, read_text
from tests.studio.test_runner_updater_state import Paths, fam, lib_run, lines_of, state, stop
from tests.studio import test_golden_build as gb

FAM = 'mac-golden'
OLD = IMG                      # liveapp-mac-golden-20261001: the image the family runs
V0, SHA0 = gb.LIT_V, gb.LIT_SHA  # the release literal: the old image's version
V2, SHA2 = '2.339.0', '2' * 64
GIB = 1048576                  # KiB
KILLED = -signal.SIGKILL
VALID = os.path.join(FIX, '..', 'validate')
PASS_TEXT = '  ✓ scaleset[0] "mac-a" — provider=tart\nAll checks passed.\n'
REFUSE_TEXT = 'runner-start: REFUSE configured runner-image is not on this host: liveapp-mac-golden-20300101\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def today():
    return time.strftime('%Y%m%d', time.gmtime())


DISABLE = '''F=%(flag)s PSD=%(psd)s S=%(scn)s LOG=%(log)s
n=$(( $(/bin/cat $S/disable.n 2>/dev/null || print 0) + 1 )); print -r -- $n > $S/disable.n
/bin/rm -f $F
[[ -f $S/disable-hook.$n ]] && source $S/disable-hook.$n
[[ -f $S/disable-fail ]] && { print -r -- "runner-disable: still held after 3700s"; exit 1 }
[[ -f $S/drain.$n ]] && /bin/cat $S/drain.$n >> $LOG          # the stopped runscaler's last records, as it drains
[[ -f $S/keep-proc.$n ]] || /bin/cp $PSD/background $PSD/out   # keep-proc: it did not stop the old runscaler
print -r -- "runner-disable: disabled; the lock is free"
'''

ENABLE = '''F=%(flag)s PSD=%(psd)s S=%(scn)s C=%(config)s RUN=%(runner)s
zmodload zsh/datetime
zmodload -F zsh/stat b:zstat
count() { local n=$(( $(/bin/cat $S/$1.n 2>/dev/null || print 0) + 1 )); print -r -- $n > $S/$1.n; REPLY=$n }
if [[ ${1-} == --check ]]; then
  count check; n=$REPLY
  [[ -f $S/check-hook.$n ]] && source $S/check-hook.$n
  [[ -f $S/check-refuse.$n ]] && { print -u2 -r -- "runner-enable: REFUSE the wall stamp's macos line is not this Mac's"; exit 1 }
  print -r -- "runner-enable: check passed (shim ok)"; exit 0
fi
count enable; n=$REPLY
typeset -A st; zstat -H st $C
print -r -- "$EPOCHREALTIME $st[mtime] $(/usr/bin/shasum -a 256 < $C | /usr/bin/cut -c1-64)" >> $S/enable.calls
if [[ -f $S/enable-refuse.$n ]]; then   # the file's text is the refusal (empty: the stamp's)
  t=$(<$S/enable-refuse.$n); print -u2 -r -- "${t:-runner-enable: REFUSE the wall stamp does not match Tart}"; exit 1
fi
[[ -f $S/no-flag.$n ]] || : > $F
if [[ ! -f $S/no-start.$n ]]; then
  export TZ=UTC
  print -r -- "$(printf '%%5d %%5d' $(( 6000 + n )) $UID) $(strftime '%%a %%b %%e %%H:%%M:%%S %%Y' $EPOCHSECONDS)     $RUN run --config $C" > $PSD/out.new
  /bin/cat $PSD/background >> $PSD/out.new; /bin/mv -f $PSD/out.new $PSD/out
fi
[[ -f $S/enable-hook.$n ]] && source $S/enable-hook.$n
print -r -- "runner-enable: enabled (shim ok)"
'''

START = '''S=%(scn)s C=%(config)s
[[ $1 == validate ]] || exit 2
n=$(( $(/bin/cat $S/validate.n 2>/dev/null || print 0) + 1 )); print -r -- $n > $S/validate.n
cfg=${2:-$C}
[[ -f $S/validate-prehook.$n ]] && source $S/validate-prehook.$n   # before it reads the config
print -r -- "$n ${2:-configured} $(/usr/bin/shasum -a 256 < $cfg | /usr/bin/cut -c1-64)" >> $S/validate.calls
[[ -f $S/validate-hook.$n ]] && source $S/validate-hook.$n
spec=$S/validate; [[ -f $S/validate.$n ]] && spec=$S/validate.$n
read rc fix < $spec
/bin/cat $fix
exit $rc
'''

GATE = '''S=%(scn)s
img=$1 j=$3
/bin/zsh -f ${0:A:h}/runner-journal $j gate-clone s1-gate-20300101000000 || exit 2
rc=0; [[ -f $S/gate ]] && rc=$(<$S/gate)
case $rc in
  (0) print -r -- "golden-gate: GREEN $img" ;;
  (1) print -r -- "golden-gate: RED $img" ;;
  (*) print -r -- "golden-gate: STOP the gate did not run to its end (golden-emudhra exit 1): $img is not checked" ;;
esac
exit $rc
'''

BUILD = '''RUNNER_SHA=%(sha)s
RUNNER_VERSION=%(v)s   # the release literal (the window reads both lines)
S=%(scn)s PIN=%(pin)s VMS=%(vms)s F=%(flag)s
if [[ ${1-} == --print-runner ]]; then
  if [[ -f $PIN ]]; then c=$(<$PIN); print -r -- "host pin ${c%%%% *} (release literal $RUNNER_VERSION)"
  else print -r -- "release literal $RUNNER_VERSION (no host pin)"; fi
  exit 0
fi
[[ ${1-} == --date && $# == 2 ]] || exit 2
[[ ! -e $F ]] || { print -r -- "golden-build: STOP the agent is enabled"; exit 1 }
out=liveapp-mac-golden-$2 v=$RUNNER_VERSION
[[ -f $PIN ]] && { c=$(<$PIN); v=${c%%%% *} }
print -r -- "golden-build: 10:00:00 start: $out from BASE, runner $v (host pin)"
[[ -f $S/build-hook ]] && source $S/build-hook
[[ -f $S/build-fail ]] && { print -r -- "golden-build: STOP tart clone failed"; exit 1 }
print -r -- "golden-build: 10:00:01 runner ${$(/bin/cat $S/guest-version 2>/dev/null):-$v}"
: > $VMS/$out
print -r -- "golden-build: 10:00:02 DONE: ${$(/bin/cat $S/done-name 2>/dev/null):-$out}"
'''

# the clock as golden-build would read it: far from today, so a build that read it for a name would show it
CLOCK = r'''
if [[ $1 == +%%Y%%m%%d ]]; then print -r -- %(d)s; else exec /bin/date "$@"; fi
'''

# RU_KILL_AT=KEY: SIGKILL the caller right after the first KEY line; KEY:N, right after the Nth KEY line of the file.
# RU_JQ_OFF_AT=KEY: after a KEY line, the file RU_JQ_OFF exists (a jq wrapper then fails every call)
KILL_AT = ('\nexit 0\n', '''
if [[ -n ${RU_JQ_OFF_AT-} && $key == "$RU_JQ_OFF_AT" ]]; then : > $RU_JQ_OFF; fi
if [[ -n ${RU_KILL_AT-} ]]; then
  kk=${RU_KILL_AT%%:*} kn=1
  [[ $RU_KILL_AT == *:* ]] && kn=${RU_KILL_AT##*:}
  if [[ $key == "$kk" ]]; then
    seen=(${(M)${(f)"$(<$file)"}:#$key *})
    (( ${#seen} == kn )) && kill -KILL $PPID
  fi
fi
exit 0
''')
# the fake tart's list: `-q`, the names (as before); without it, tart's table (State last: scn/running-NAME = running)
TART_LIST = ('  (list) /bin/ls -1 $VMS ;;\n', '''  (list)
    if [[ " $* " == *" -q "* ]]; then /bin/ls -1 $VMS
    else
      print -r -- "Source Name Disk Size SizeOnDisk Accessed State"
      for v in $VMS/*(N); do
        st=stopped; [[ -e $SCN/running-${v:t} ]] && st=running
        print -r -- "local ${v:t} 90 50 50 2 days ago $st"
      done
    fi ;;
''')


class Win:
    """the fake host and the release's bin/ beside the updater (the rig's tools/)"""

    def __init__(self, test, real_build=False, cfg=None, families='mac-golden tart mac-a\n', s=None, extra_rewrites=(),
                 win_rewrites=(), jq=None):
        self.test = test
        r = self.r = Rig(test, cfg=cfg, families=families, extra_rewrites=extra_rewrites, jq=jq)
        sb = self.sb = r.sb
        self.u = Paths(r)
        self.tools = os.path.dirname(r.script)
        self.scn = sb.mkdir('scn')
        self.vms = sb.mkdir('vms')
        self.pin = os.path.join(r.statedir, 'pin', FAM)
        os.makedirs(os.path.join(r.tartdir, 'vms'), exist_ok=True)
        sb.copy_script('bin/runner-updater-window', list(win_rewrites))
        sb.copy_script('bin/validate-class', [])
        sb.copy_script('bin/runner-journal', [KILL_AT])           # the real one, with the kill hook (RU_KILL_AT)
        v = {'flag': r.flag, 'psd': r.psd, 'scn': self.scn, 'config': r.config, 'runner': r.runner, 'sha': SHA0, 'v': V0,
             'pin': self.pin, 'vms': self.vms, 'log': r.runlog}
        sb.stub('runner-disable', DISABLE % v, folder=self.tools)
        sb.stub('runner-enable', ENABLE % v, folder=self.tools)
        sb.stub('runner-start', START % v, folder=self.tools)
        sb.stub('golden-gate', GATE % v, folder=self.tools)
        sb.stub('golden-emudhra', 'exit 0', folder=self.tools)
        # RECOVER's lock read: the REAL runner-lock-free (the real lsof and lockf) on the rig's lock, as this user
        sb.copy_script('bin/runner-lock-free', [
            ('LOCK=/tmp/runner.lock', 'LOCK=' + r.lock), ('RUNNER=/Users/ci/bin/runner', 'RUNNER=' + r.runner),
            ('CI_USER=ci', 'CI_USER=' + pwd.getpwuid(os.getuid()).pw_name)],
            allow=['Installed as /Users/ci/bin/runner-lock-free', 'can unlink /tmp/runner.lock under'],
            dest=os.path.join(self.tools, 'runner-lock-free'))
        fake = sb.mkdir('fake')
        self.test.assertIn(TART_LIST[0], gb.TART)
        sb.stub('tart', gb.TART.replace(*TART_LIST) % {'vms': gb.q(self.vms), 'scn': gb.q(self.scn),
                                                       'pidf': gb.q(sb.path('realrun.pid')), 'major': gb.MAJOR},
                folder=fake)
        sb.stub('real-run', 'print -r -- $$ > %s\nexec /bin/sleep 600' % gb.q(sb.path('realrun.pid')), folder=fake)
        disk = sb.mkdir('tools-disk')
        sb.stub('df', 'print -r -- "Filesystem 1024-blocks Used Available Capacity Mounted on"\n'
                      'print -r -- "/dev/disk3s5 999999999 1 $(<%s/free-kib) 1%% /System/Volumes/Data"' % self.scn,
                folder=disk)
        sb.stub('du', 'print -r -- "$(<%s/img-kib)\t${@[-1]}"' % self.scn, folder=disk)
        if real_build:
            self.real_build()
        else:
            sb.stub('golden-build', BUILD % v, folder=self.tools)
        sb.write(os.path.join(r.psd, 'background'), ''.join(l + '\n' for l in BACKGROUND))
        sb.write(r.flag, '')
        sb.write(os.path.join(self.vms, OLD), '')
        self.put('free-kib', 300 * GIB)
        self.put('img-kib', 50 * GIB)
        self.fix = {'pass': sb.write(sb.path('fix', 'pass.txt'), PASS_TEXT),
                    'refuse': sb.write(sb.path('fix', 'refuse.txt'), REFUSE_TEXT),
                    'api': os.path.join(VALID, 'api-only-real.txt'),
                    'nonapi': os.path.join(VALID, 'non-api-real.txt'),
                    'unknown': sb.write(sb.path('fix', 'unknown.txt'), 'something else\n')}
        self.validate('pass')
        self.u.put(s if s is not None else state(on=True, images={OLD: V0}))
        self.pre = r.log_bytes(r.config)

    def real_build(self):
        sb, r = self.sb, self.r
        sb.copy_script('bin/golden-build', [
            ('REAL=/Users/ci/Applications/tart.app/Contents/MacOS/tart', 'REAL=' + sb.path('fake', 'tart')),
            ('REALRUN=/Users/ci/bin/real-run', 'REALRUN=' + sb.path('fake', 'real-run')),
            ('LOCK=/tmp/runner.lock', 'LOCK=' + r.lock),
            ('FLAG=/Users/ci/.config/runner/enabled', 'FLAG=' + r.flag),
            ('LOGDIR=/Users/ci/Library/Logs/mac-runner', 'LOGDIR=' + r.logdir),
            ('STATEDIR=/Users/ci/.local/state/runner-updater', 'STATEDIR=' + r.statedir),
            ('HOME=/Users/ci ', 'HOME=%s ' % sb.home),
            ('vol=/Users/ci/.tart; [[ -d $vol ]] || vol=/Users/ci', 'vol=%s' % sb.home),
            ('FLOOR_GIB=200', 'FLOOR_GIB=0'),
        ], allow=['Run as ci on the host: /Users/ci/bin/golden-build'])
        sb.stub('date', CLOCK % {'d': '20300101'})
        sb.stub('sw_vers', 'print -r -- %s.0' % gb.MAJOR)
        sb.write(os.path.join(self.scn, 'guest-runner-version'), V0 + '\n')

    # scenario
    def put(self, name, value=''):
        self.sb.write(os.path.join(self.scn, name), '%s\n' % value if value != '' else '')

    def validate(self, kind, call=None):
        """runner-start validate answers KIND (pass, refuse, api, nonapi, unknown), for every call or call CALL"""
        rc = 0 if kind == 'pass' else 1
        self.put('validate' if call is None else 'validate.%d' % call, '%d %s' % (rc, self.fix[kind]))

    def hook(self, name, body):
        self.sb.write(os.path.join(self.scn, name), body)

    # runs
    def run(self, cmd='rebuild', family=FAM, env=None):
        return self.r.cmd(cmd, family, ok=False, env=env)

    def ok(self, cmd='rebuild', family=FAM):
        res = self.run(cmd, family)
        self.test.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return res

    # what it left
    def windows(self):
        d = os.path.join(self.r.statedir, 'windows')
        return sorted(n for n in os.listdir(d) if not n.endswith('.d')) if os.path.isdir(d) else []

    def journal(self):
        """the window's journal: the open one, else the one archived journal"""
        if os.path.exists(self.u.window):
            return lines_of(self.u.window)
        w = self.windows()
        self.test.assertEqual(len(w), 1, w)
        return lines_of(os.path.join(self.r.statedir, 'windows', w[0]))

    def keys(self):
        return [l.split(' ', 1)[0] for l in self.journal()]

    def value(self, key):
        vals = [l.split(' ', 1)[1] if ' ' in l else '' for l in self.journal() if l.split(' ', 1)[0] == key]
        self.test.assertEqual(len(vals), 1, (key, self.journal()))
        return vals[0]

    def calls(self, name):
        return self.sb.calls(name)

    def enables(self):
        """runner-enable's calls (not --check): (time, the config's mtime, its sha) each"""
        p = os.path.join(self.scn, 'enable.calls')
        if not os.path.exists(p):
            return []
        return [(float(a), int(b), c) for a, b, c in (l.split() for l in lines_of(p))]

    def validates(self):
        p = os.path.join(self.scn, 'validate.calls')
        return [l.split() for l in lines_of(p)] if os.path.exists(p) else []

    def builds(self):
        return [c for c in self.calls('golden-build') if c[:1] == ['--date']]

    def family(self):
        return self.u.get()['families'].get(FAM)

    def config_now(self):
        return self.r.log_bytes(self.r.config)

    def status(self):
        return self.r.cmd('status').stdout


def healthz(*names):
    """one /healthz read: every set NAMES ready and idle"""
    h = json.loads(json.dumps(HEALTHZ))
    h['scale_sets'] = [dict(h['scale_sets'][0], name=n) for n in names]
    return h


def switched_config(pre, new):
    return pre.replace(('runner-image = "%s"' % OLD).encode(), ('runner-image = "%s"' % new).encode())


HAPPY_KEYS = ['window', 'family', 'kind', 'command', 'version', 'runner-sha', 'date', 'image', 'image', 'image', 'tool',
              'tool', 'tool', 'tool', 'pin-before', 'target', 'validate', 'idle', 'from', 'config-sha', 'backup',
              'disable-start', 'disable-done', 'stopped', 'pin-write', 'build-start', 'build-done', 'gate-start',
              'gate-clone', 'gate', 'enable-check', 'validate', 'edited-sha', 'validate', 'installed', 'enable-start',
              'enable-done', 'running', 'pin-rule', 'state-write', 'closed']


class TestRebuild(unittest.TestCase):
    """`rebuild mac-golden`: ONE window that builds the family's CURRENT runner version anew (the old image's version:
    the state's record, else golden-build's log), with the idle pair, and closes on the new image."""

    def test_rebuild_switches_the_family_to_a_new_image_of_its_current_version(self):
        w = Win(self, real_build=True)
        t0 = int(time.time())
        res = w.ok()
        d = today()
        out = 'liveapp-mac-golden-' + d
        self.assertIn('runner-updater: rebuild %s: switched to %s (runner %s); the window closed\n' % (FAM, out, V0),
                      res.stdout)
        self.assertEqual(w.keys(), HAPPY_KEYS)
        j = w.journal()
        self.assertEqual(j[:10], ['window ' + w.windows()[0], 'family ' + FAM, 'kind switch', 'command rebuild',
                                  'version ' + V0, 'runner-sha ' + SHA0, 'date ' + d, 'image ' + OLD, 'image gold-' + d,
                                  'image ' + out])
        self.assertRegex(w.windows()[0], r'^[0-9]{14}-[0-9]+$')
        self.assertEqual(w.value('pin-before'), 'none')
        self.assertEqual(w.value('target'), 'mac-a=' + out)
        self.assertEqual(w.value('idle'), 'idle')
        self.assertEqual(w.value('config-sha'), sha(w.pre))
        self.assertEqual(w.value('pin-write'), '%s %s' % (V0, SHA0))
        self.assertEqual(w.value('build-done'), out)
        self.assertEqual(w.value('gate'), 'green 0')
        self.assertEqual(w.value('pin-rule'), '%s %s' % (V0, SHA0))
        for l in [l for l in j if l.startswith('tool ')]:
            self.assertRegex(l, r'^tool (golden-build|golden-emudhra|golden-gate|real-run) [0-9]+ [0-9]+ /\S+$')
        # the --date identity: every name of the build is the journaled date, never the clock golden-build would read
        self.assertEqual(w.r.log_bytes(w.r.config), switched_config(w.pre, out))
        self.assertEqual(sorted(os.listdir(w.vms)), sorted([OLD, out]))
        self.assertTrue(os.path.exists(os.path.join(w.r.logdir, 'golden-%s.log' % d)))
        self.assertNotIn('20300101', read_text(os.path.join(w.r.statedir, 'windows', w.windows()[0] + '.d', 'build.out')))
        # the state, the pin, the list
        f = w.family()
        self.assertEqual(f['candidate']['version'], V0)
        self.assertEqual(f['candidate']['lines'], {'mac-a': out})
        self.assertTrue(t0 <= f['candidate']['closed_at'] <= int(time.time()) + 1, f)
        self.assertEqual((f['previous'], f['back_until'], f['stops']), ({'mac-a': OLD}, None, []))
        self.assertEqual(w.u.get()['images'], {OLD: V0, out: V0})
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V0, SHA0))
        self.assertEqual(lines_of(w.u.protected), sorted([OLD, out]))
        self.assertFalse(os.path.exists(w.u.window))
        # the backup is the pre-window config; CI runs again on the new config, started after its install
        self.assertEqual(w.r.log_bytes(w.value('backup')), w.pre)
        self.assertTrue(os.path.exists(w.r.flag))
        self.assertEqual(len(w.calls('runner-disable')), 1)
        (at, mtime, csha), = w.enables()
        self.assertEqual(csha, sha(switched_config(w.pre, out)))
        self.assertGreater(int(at), mtime)
        self.assertEqual(w.calls('golden-gate'), [[out, '--journal', w.u.window]])
        self.assertEqual([v[1] for v in w.validates()], [w.value('backup'), w.r.sb.path(
            'state', 'runner-updater', 'windows', w.windows()[0] + '.d', 'config.toml.target'), 'configured'])
        self.assertIn('\nrunner-updater: family %s: host pin %s\n' % (FAM, V0), w.status())

    def test_rebuild_adopts_the_version_golden_build_logged_for_a_hand_built_image(self):
        w = Win(self, s=state(on=True))
        w.sb.write(os.path.join(w.r.logdir, 'golden-20261001.log'),
                   'golden-build: 09:00:00 start: %s from BASE, runner %s (release literal)\n'
                   'golden-build: 09:20:00 runner %s\ngolden-build: 09:30:00 DONE: %s\n' % (OLD, V0, V0, OLD))
        w.ok()
        out = 'liveapp-mac-golden-' + today()
        self.assertEqual(w.u.get()['images'], {OLD: V0, out: V0})

    def test_control_a_hand_built_image_with_no_record_and_no_log_is_refused(self):
        w = Win(self, s=state(on=True))
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE the runner version of %s, the image %s runs, is not known' % (OLD, FAM),
                      res.stdout)
        self.assertEqual(w.calls('runner-disable'), [])

    def test_no_builder_wired_for_a_studio_linux_family(self):
        w = Win(self, families='mac-golden tart mac-b\nlinux-tart tart mac-a\n')
        res = w.run('rebuild', 'linux-tart')
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE no builder wired for linux-tart', res.stdout)
        self.assertEqual((w.calls('runner-disable'), w.calls('runner-enable'), w.r.ps_calls()), ([], [], 0))
        res = w.run('switch-now', 'linux-tart')
        self.assertIn('runner-updater: REFUSE no builder wired for linux-tart', res.stdout)

    def test_off_refuses(self):
        w = Win(self, s=state(on=False, images={OLD: V0}))
        for cmd in ('rebuild', 'switch-now'):
            res = w.run(cmd)
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn('runner-updater: REFUSE the updater is OFF', res.stdout)
        self.assertEqual(w.r.ps_calls(), 0)

    def test_usage(self):
        w = Win(self)
        for args in (('rebuild',), ('rebuild', FAM, 'x'), ('switch-now', 'Bad'), ('rebuild', '')):
            res = w.r.cmd(*args, ok=False)
            self.assertEqual(res.returncode, 2, (args, res.stdout, res.stderr))


class TestSwitchNow(unittest.TestCase):
    """`switch-now mac-golden`: D5 NO IDLE's override: the window with no idle pair, and it says so. Its release: the
    one the family's NO IDLE STOP holds (version and sha), else the family's current version."""

    def test_switch_now_has_no_idle_pair_and_says_so(self):
        w = Win(self)
        res = w.ok('switch-now')
        self.assertIn('runner-updater: switch-now %s: no idle pair: runner-disable drains every set now' % FAM, res.stdout)
        self.assertEqual(w.value('idle'), 'skipped')
        self.assertEqual(w.value('command'), 'switch-now')
        self.assertEqual(len(w.r.curl_calls()), 1)      # START STATE's one read; no idle pair

    def test_control_rebuild_reads_the_idle_pair(self):
        w = Win(self)
        w.ok('rebuild')
        self.assertEqual(len(w.r.curl_calls()), 3)      # START STATE's read and the idle pair

    def test_switch_now_takes_the_release_of_the_no_idle_stop_and_clears_it(self):
        held = stop(FAM, 'NO IDLE', version=V2, detail={'text': 'IDLE: mac-a: busy 1', 'sha': SHA2})
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[held])}, images={OLD: V0}))
        w.ok('switch-now')
        out = 'liveapp-mac-golden-' + today()
        self.assertEqual((w.value('version'), w.value('runner-sha'), w.value('pin-write')), (V2, SHA2, V2 + ' ' + SHA2))
        f = w.family()
        self.assertEqual((f['candidate']['version'], f['stops']), (V2, []))
        self.assertEqual(w.u.get()['images'], {OLD: V0, out: V2})
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V2, SHA2))


class TestNotNow(unittest.TestCase):
    """START STATE and IDLE: not met = not now (exit 5): no journal, no runner-disable, nothing held. 3 days from the
    release's eligibility it is STOP NO IDLE (a pass gives that date; the commands' release is due from now, so a
    cell plants an older one in the copy)."""

    SINCE = '  since=$now   # the commands\' release is due from now: never NO IDLE (a pass gives its eligibility)'

    def not_now(self, w, why):
        res = w.run()
        self.assertEqual(res.returncode, 5, res.stdout + res.stderr)
        self.assertIn('runner-updater: rebuild %s: not now: %s; nothing changed\n' % (FAM, why), res.stdout)
        self.assertEqual((w.calls('runner-disable'), w.windows(), os.path.exists(w.u.window)), ([], [], False))
        self.assertEqual(w.family(), None)
        return res

    def test_not_idle(self):
        w = Win(self)
        busy = json.loads(json.dumps(HEALTHZ))
        busy['scale_sets'][0]['busy'] = 1
        w.r.set_curl(json.dumps(busy), call=3)
        self.not_now(w, 'IDLE: mac-a: busy 1')

    def test_ci_disabled(self):
        w = Win(self)
        os.remove(w.r.flag)
        self.not_now(w, 'START STATE: CI is disabled (%s is absent)' % w.r.flag)

    def test_runscaler_not_running(self):
        w = Win(self)
        w.r.set_ps([])
        self.not_now(w, 'START STATE: runscaler is not running')

    def test_a_config_installed_after_runscaler_started(self):
        w = Win(self)
        os.utime(w.r.config, (P[2], P[2]))      # the same second: not proven
        self.not_now(w, 'START STATE: %s was installed at %d, not before runscaler started (%d): it has not read it yet'
                     % (w.r.config, P[2], P[2]))

    def test_a_family_set_not_ready(self):
        w = Win(self)
        h = json.loads(json.dumps(HEALTHZ))
        h['scale_sets'][0]['ready'] = False
        w.r.set_curl(json.dumps(h), call=1)
        self.not_now(w, 'START STATE: not ready on /healthz: mac-a')

    def no_idle(self, back):
        w = Win(self, extra_rewrites=[(self.SINCE, '  since=$(( now - %d ))' % back)])
        busy = json.loads(json.dumps(HEALTHZ))
        busy['scale_sets'][0]['busy'] = 1
        w.r.set_curl(json.dumps(busy), call=3)
        return w

    def test_3_days_from_eligibility_it_is_no_idle(self):
        w = self.no_idle(3 * 86400)
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP NO IDLE: IDLE: mac-a: busy 1 (due since ', res.stdout)
        (s,) = w.family()['stops']
        self.assertEqual((s['stop'], s['version'], s['detail']['sha']), ('NO IDLE', V0, SHA0))
        self.assertEqual((w.calls('runner-disable'), w.windows()), ([], []))
        self.assertIn('\n%s: STOP NO IDLE (runner %s): IDLE: mac-a: busy 1 (due since ' % (FAM, V0), w.status())
        self.assertIn('. Next: `runner-updater switch-now %s`\n' % FAM, w.status())

    def test_control_a_minute_short_of_3_days_is_not_now(self):
        w = self.no_idle(3 * 86400 - 60)
        res = w.run()
        self.assertEqual(res.returncode, 5, res.stdout)
        self.assertEqual(w.family(), None)


class TestPreWindowStops(unittest.TestCase):
    """A failure before runner-disable: a STOP held in the state, no runner-disable, NO drain, no journal."""

    def stopped(self, w, name, text):
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn('runner-updater: STOP %s: %s' % (name, text), res.stdout)
        self.assertEqual((w.calls('runner-disable'), w.builds(), os.path.exists(w.u.window)), ([], [], False))
        self.assertTrue(os.path.exists(w.r.flag))
        self.assertEqual(w.config_now(), w.pre)
        (s,) = w.family()['stops']
        self.assertEqual(s['stop'], name)
        self.assertIn('\n%s: STOP %s' % (FAM, name), w.status())
        return res, s

    def test_family_lines_that_disagree(self):
        w = Win(self, cfg=config((('mac-a', OLD), ('mac-b', IMG2))), families='mac-golden tart mac-a mac-b\n')
        res, s = self.stopped(w, 'check failed', 'pre-window: the sets of %s name more than one image' % FAM)
        self.assertIsNone(s['version'])
        self.assertIn('. Next: `runner-updater retry %s`' % FAM, w.status())

    def test_control_family_lines_that_agree(self):
        w = Win(self, cfg=config((('mac-a', OLD), ('mac-b', OLD), ('mac-c', IMG2))),
                families='mac-golden tart mac-a mac-b\n')
        w.r.set_curl(json.dumps(healthz('mac-a', 'mac-b', 'mac-c')))
        w.ok()
        out = 'liveapp-mac-golden-' + today()
        self.assertEqual(w.value('target'), 'mac-a=%s mac-b=%s' % (out, out))
        self.assertEqual(w.u.get()['families'][FAM]['candidate']['lines'], {'mac-a': out, 'mac-b': out})
        self.assertIn(b'runner-image = "%s"' % IMG2.encode(), w.config_now())     # mac-c is another family's

    def test_the_old_image_is_not_on_the_host(self):
        w = Win(self)
        os.remove(os.path.join(w.vms, OLD))
        self.stopped(w, 'check failed', 'pre-window: the old image %s is not on this host' % OLD)

    def test_an_existing_output_not_journaled_as_ours(self):
        w = Win(self)
        out = os.path.join(w.vms, 'liveapp-mac-golden-' + today())
        w.sb.write(out, 'a hand build')
        self.stopped(w, 'check failed', 'pre-window: liveapp-mac-golden-%s already exists and no open window journals '
                     'it as ours: no window' % today())
        self.assertEqual(read_text(out), 'a hand build')

    def test_a_host_pin_that_is_not_one_line(self):
        w = Win(self)
        w.sb.write(w.pin, '%s %s\n%s %s\n' % (V0, SHA0, V0, SHA0))
        self.stopped(w, 'check failed', "pre-window: the host pin %s is not one line 'VERSION SHA256'" % w.pin)

    def test_disk(self):
        w = Win(self)
        w.put('free-kib', 250 * GIB - 1)        # 249 GiB < the floor 200 + the image 50
        res, s = self.stopped(w, 'DISK', 'free disk 249 GiB < 250 GiB (the builder\'s floor 200 GiB + the image %s 50 '
                              'GiB)' % OLD)
        self.assertEqual(s['version'], V0)
        self.assertIn('Next, by hand: free disk on the host (docs/operations.md, "Disk"); the next window of %s checks '
                      'it again' % FAM, w.status())
        self.assertIn('\nrunner-updater: STOP %s DISK: known true; candidate closed: no; version rejected: no; a newer '
                      'release proceeds alone: no\n' % FAM, w.status())

    def test_control_disk_at_the_floor_plus_the_image(self):
        w = Win(self)
        w.put('free-kib', 250 * GIB)
        w.put('img-kib', 49 * GIB + 1)           # rounds up to 50
        res = w.ok()
        self.assertIn('runner-updater: window: DISK: free 250 GiB >= 250 GiB', res.stdout)

    def test_a_check_that_fails(self):
        w = Win(self)
        w.put('check-refuse.1')
        self.stopped(w, 'check failed', "pre-window: runner-enable --check (exit 1): runner-enable: REFUSE the wall "
                     "stamp's macos line is not this Mac's")

    def test_pre_validate_refuse(self):
        w = Win(self)
        w.validate('refuse', call=1)
        self.stopped(w, 'check failed', 'pre-window validate (pre) is NON-API (exit 1): ' + REFUSE_TEXT.strip())

    def test_pre_validate_unknown(self):
        w = Win(self)
        w.validate('unknown', call=1)
        self.stopped(w, 'check failed', 'pre-window validate (pre) is UNKNOWN (exit 1)')

    def test_control_three_api_only_at_pre_validate_count_as_pass(self):
        w = Win(self)
        for n in (1, 2, 3):
            w.validate('api', call=n)
        w.ok()
        self.assertEqual([l for l in w.journal() if l.startswith('validate pre')],
                         ['validate pre 1 API-ONLY', 'validate pre 2 API-ONLY', 'validate pre 3 API-ONLY'])

    def test_a_later_good_window_clears_the_held_window_stops_and_keeps_the_others(self):
        held = [stop(FAM, 'DISK', version=V0, detail={'text': 'x'}), stop(FAM, 'HAND CHANGE', version=V0),
                stop(FAM, 'JOBS FAIL ON THE NEW IMAGE', version=V0)]
        w = Win(self, s=state(on=True, families={FAM: fam(stops=held)}, images={OLD: V0}))
        w.ok()
        self.assertEqual([s['stop'] for s in w.family()['stops']], ['JOBS FAIL ON THE NEW IMAGE'])

    def test_a_config_changed_during_the_checks_is_no_window(self):
        w = Win(self)
        w.hook('validate-hook.1', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE %s changed while the window checked it (its sha is not the backup\'s): no '
                      'window; run rebuild again\n' % w.r.config, res.stdout)
        self.assertEqual((w.calls('runner-disable'), os.path.exists(w.u.window)), ([], False))
        self.assertEqual(w.keys()[-1], 'closed')


class TestAfterDisable(unittest.TestCase):
    """A failure after runner-disable: STOP check failed, the backup back when the config is the window's edit, CI
    enabled on the pre-window config, the window closes; the pin follows D2's ONE RULE (the old image's version)."""

    def back(self, w, text, edited=False):
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn('runner-updater: STOP check failed: ' + text, res.stdout)
        self.assertEqual(w.config_now(), w.pre)
        self.assertTrue(os.path.exists(w.r.flag))
        self.assertEqual(len(w.calls('runner-disable')), 1)
        (at, mtime, csha), = w.enables()
        self.assertEqual(csha, sha(w.pre))                       # CI enabled on the pre-window config
        self.assertEqual(w.keys()[-3:], ['pin-rule', 'state-write', 'closed'])
        self.assertEqual(w.value('state-write'), 'held')
        self.assertEqual(w.value('pin-rule'), '%s %s' % (V0, SHA0))
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V0, SHA0))
        self.assertEqual(('restore' in w.keys()), edited)
        f = w.family()
        self.assertEqual((f['candidate'], [s['stop'] for s in f['stops']]), (None, ['check failed']))
        self.assertEqual(lines_of(w.u.protected), [])
        self.assertIn('\n%s: STOP check failed (runner %s): %s' % (FAM, V0, text), w.status())
        return res

    def test_the_build_fails(self):
        w = Win(self)
        w.put('build-fail')
        self.back(w, 'build: golden-build exit 1: golden-build: STOP tart clone failed')
        self.assertEqual(w.value('build-failed'), 'exit 1')
        self.assertEqual(w.calls('golden-gate'), [])

    def test_a_stop_text_with_a_control_character_is_journaled_with_it_replaced(self):
        w = Win(self)
        w.hook('build-hook', "print -r -- $'golden-build: STOP a\\tb'; exit 1\n")
        self.back(w, 'build: golden-build exit 1: golden-build: STOP a\tb')
        self.assertIn('stop check failed: build: golden-build exit 1: golden-build: STOP a?b', w.journal())

    def test_a_done_name_that_is_not_the_journaled_date(self):
        w = Win(self)
        w.put('done-name', 'liveapp-mac-golden-20300101')
        self.back(w, "build: golden-build's DONE line names 'liveapp-mac-golden-20300101', not liveapp-mac-golden-"
                  + today())

    def test_a_runner_version_that_is_not_the_candidates(self):
        w = Win(self)
        w.put('guest-version', '2.0.0')
        self.back(w, "build: golden-build's runner line names '2.0.0', not %s" % V0)

    def test_the_gate_is_red_or_cannot_run(self):
        for rc, word in ((1, 'red'), (2, 'stop')):
            with self.subTest(rc=rc):
                w = Win(self)
                w.put('gate', rc)
                self.back(w, 'gate: golden-gate %s (exit %d): golden-gate: ' % (word, rc))
                self.assertEqual(w.value('gate'), '%s %d' % (word, rc))
                self.assertIn('gate-clone s1-gate-20300101000000', w.journal())

    def test_the_second_check_fails(self):
        w = Win(self)
        w.put('check-refuse.2')
        self.back(w, "runner-enable --check (exit 1): runner-enable: REFUSE the wall stamp's macos line")
        self.assertEqual(w.value('enable-check'), 'fail')

    def test_the_targets_validate_is_non_api(self):
        w = Win(self)
        w.validate('nonapi', call=2)
        self.back(w, 'validate (target) is NON-API (exit 1):   ✗ scaleset[0] "mac-ci-example": runner-image is required')
        self.assertNotIn('edited-sha', w.keys())

    def test_validate_after_the_edit_refuses_the_backup_goes_back_before_enable(self):
        w = Win(self)
        w.validate('refuse', call=3)
        self.back(w, 'after the edit: validate (post) is NON-API (exit 1): ' + REFUSE_TEXT.strip(), edited=True)
        k = w.keys()
        self.assertLess(k.index('restore'), k.index('enable-start'))
        self.assertEqual(w.value('restore'), w.value('backup'))
        # the target was installed once: the validate saw it
        self.assertEqual(w.validates()[2][2], w.value('edited-sha'))

    def test_three_api_only_after_the_build_and_after_the_edit_reach_enable_done(self):
        for calls in ((2, 3, 4), (3, 4, 5)):
            with self.subTest(calls=calls):
                w = Win(self)
                for n in calls:
                    w.validate('api', call=n)
                w.ok()
                self.assertIn('enable-done', w.keys())
                out = 'liveapp-mac-golden-' + today()
                self.assertEqual(w.config_now(), switched_config(w.pre, out))
                self.assertEqual(w.family()['stops'], [])


class TestHandChange(unittest.TestCase):
    """CONFIG EDIT: the config's sha is compared under the runner lock before the edit. Another sha: no edit, CI is
    enabled on the file as found, STOP HAND CHANGE."""

    def test_a_hand_change_during_the_window(self):
        w = Win(self)
        w.hook('check-hook.2', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)
        found = w.pre + b'# a hand edit\n'
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP HAND CHANGE: %s changed inside the window' % w.r.config, res.stdout)
        self.assertEqual(w.config_now(), found)
        self.assertEqual(w.value('hand-change'), sha(found))
        (at, mtime, csha), = w.enables()
        self.assertEqual(csha, sha(found))
        self.assertTrue(os.path.exists(w.r.flag))
        self.assertEqual([s['stop'] for s in w.family()['stops']], ['HAND CHANGE'])
        self.assertIn('\n%s: STOP HAND CHANGE (runner %s): %s changed inside the window' % (FAM, V0, w.r.config),
                      w.status())
        self.assertIn('Next: `runner-updater rebuild %s`' % FAM, w.status())

    def test_control_no_hand_change_the_edit_is_made(self):
        w = Win(self)
        w.hook('check-hook.2', ': nothing\n')
        w.ok()
        self.assertEqual(w.config_now(), switched_config(w.pre, 'liveapp-mac-golden-' + today()))

    def test_a_hand_change_that_does_not_validate_gets_no_ci(self):
        # S3b-4a r1 F6 (PLAN :236-243 as amended): CI on the file as found ONLY when a copy of it validates
        w = Win(self)
        w.hook('check-hook.2', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)
        found = w.pre + b'# a hand edit\n'
        w.validate('refuse', call=3)            # 1: PRE-VALIDATE, 2: the target, 3: the copy of the person's file
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP HAND CHANGE: %s changed inside the window' % w.r.config, res.stdout)
        self.assertIn('runner-enable` by hand', res.stdout)
        self.assertEqual(w.validates()[-1][2], sha(found))
        self.assertEqual((w.enables(), os.path.exists(w.r.flag)), ([], False))
        self.assertEqual(w.config_now(), found)
        self.assertTrue(os.path.exists(w.u.window))      # open, with its hand-change line: RECOVER validates again
        self.assertEqual(w.value('hand-change'), sha(found))
        self.assertIn('validate hand 1 NON-API', w.journal())
        w.validate('refuse', call=4)
        w.r.cmd('pass', ok=False)                         # RECOVER: it still does not validate: CI stays down
        self.assertEqual((w.enables(), os.path.exists(w.r.flag)), ([], False))
        self.assertTrue(os.path.exists(w.u.window))
        w.r.cmd('pass', ok=False)                         # it validates now: CI on it
        assert_closed_runs = (os.path.exists(w.u.window), w.enables()[-1][2], os.path.exists(w.r.flag))
        self.assertEqual(assert_closed_runs, (False, sha(found), True))

    def test_control_a_hand_change_that_validates_is_validated_first(self):
        w = Win(self)
        w.hook('check-hook.2', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)
        found = w.pre + b'# a hand edit\n'
        w.run()
        self.assertEqual(len(w.validates()), 3)
        self.assertEqual(w.validates()[-1][2], sha(found))
        self.assertIn('validate hand 1 PASS', w.journal())
        self.assertEqual([e[2] for e in w.enables()], [sha(found)])


class TestPoolDown(unittest.TestCase):
    """A pre-close failure (runner-enable refuses, or the target does not run in time) happens at most ONCE per journal:
    the first time runner-disable, the backup back, CI enabled again; the second time STOP POOL DOWN, no
    runner-disable."""

    def test_runner_enable_refuses_twice(self):
        w = Win(self)
        for n in (1, 2, 3, 4):
            w.put('enable-refuse.%d' % n)
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP POOL DOWN: runner-enable refused (exit 1): runner-enable: REFUSE the wall '
                      'stamp does not match Tart; a second pre-close failure in this window', res.stdout)
        self.assertEqual(len(w.calls('runner-disable')), 2)
        self.assertEqual([l for l in w.keys() if l == 'pre-close-failure'], ['pre-close-failure'] * 2)
        self.assertEqual(len(w.enables()), 2)
        self.assertEqual(w.enables()[1][2], sha(w.pre))   # the second on the backup
        self.assertEqual(w.config_now(), w.pre)
        self.assertFalse(os.path.exists(w.r.flag))
        self.assertEqual(w.keys()[-1], 'closed')
        self.assertEqual([s['stop'] for s in w.family()['stops']], ['check failed', 'POOL DOWN'])
        st = w.status()
        self.assertIn('\n%s: STOP POOL DOWN (runner %s): runner-enable refused' % (FAM, V0), st)
        self.assertIn('Next, by hand: `%s/runner-enable`' % w.sb.path('cibin'), st)

    def test_control_runner_enable_refuses_once_then_the_old_config_runs(self):
        w = Win(self)
        w.put('enable-refuse.1')
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertEqual(len(w.calls('runner-disable')), 2)
        self.assertEqual([s['stop'] for s in w.family()['stops']], ['check failed'])
        self.assertTrue(os.path.exists(w.r.flag))
        self.assertEqual(w.config_now(), w.pre)
        self.assertEqual([l for l in w.journal() if l.startswith('target ')],
                         ['target mac-a=liveapp-mac-golden-' + today(), 'target mac-a=' + OLD])
        self.assertEqual(w.keys()[-4:], ['running', 'pin-rule', 'state-write', 'closed'])

    def test_the_target_does_not_run_in_time(self):
        w = Win(self)
        w.put('no-start.1')
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP check failed: the target did not run within 3 s', res.stdout)
        self.assertEqual(len(w.calls('runner-disable')), 2)
        self.assertEqual(w.config_now(), w.pre)
        self.assertEqual(w.keys()[-4:], ['running', 'pin-rule', 'state-write', 'closed'])


class TestMtimeSecond(unittest.TestCase):
    """runner-enable runs only when the clock's second is past the config's install time (its mtime): a start in the
    same second is not proven. A validate hook sets the edited config's mtime 2 s ahead."""

    def test_enable_waits_past_the_mtime_second(self):
        w = Win(self)
        w.hook('validate-hook.3', 'zmodload zsh/datetime; export TZ=UTC\n'
                                  '/usr/bin/touch -t $(strftime %%Y%%m%%d%%H%%M.%%S $(( EPOCHSECONDS + 2 ))) %s\n'
                                  % w.r.config)
        w.ok()
        (at, mtime, csha), = w.enables()
        self.assertGreater(int(at), mtime)
        # the install time, the file's sha, and its CONTENT sha (S3b-4a r2 P3-c: RECOVER step 1 compares it)
        from tests.studio.test_runner_updater_recover import content_sha
        self.assertEqual(w.value('installed'), '%d %s %s' % (mtime, csha, content_sha(w.config_now())))


class TestKillAtEachStep(unittest.TestCase):
    """A kill at a step boundary: the journal's last line names that step, no side effect after it, and the next pass
    runs RECOVER first (test_runner_updater_recover.py has its rules): it ends the journal and CI runs."""

    def killed(self, key, w=None):
        w = w or Win(self)
        res = w.run(env={'RU_KILL_AT': key})
        self.assertEqual(res.returncode, KILLED, res.stdout + res.stderr)
        self.assertTrue(os.path.exists(w.u.window))
        self.assertEqual(w.keys()[-1], key)
        return w

    def assert_recover_needed(self, w):
        """the next pass runs RECOVER first: the journal closes and CI runs (FLAG present); no build starts"""
        n = len(w.calls('golden-build'))
        res = w.r.cmd('pass', ok=False)
        self.assertIn('runner-updater: recover: the window journal %s is open' % w.u.window, res.stdout)
        self.assertFalse(os.path.exists(w.u.window), res.stdout)
        self.assertTrue(os.path.exists(w.r.flag))
        self.assertEqual(len(w.calls('golden-build')), n)

    def test_disable_start(self):
        w = self.killed('disable-start')
        self.assertEqual(w.calls('runner-disable'), [])
        self.assertTrue(os.path.exists(w.r.flag))
        self.assert_recover_needed(w)

    def test_pin_write(self):
        w = self.killed('pin-write')
        self.assertFalse(os.path.exists(w.pin))
        self.assert_recover_needed(w)

    def test_build_start(self):
        w = self.killed('build-start')
        self.assertEqual(w.builds(), [])
        self.assert_recover_needed(w)

    def test_gate_start(self):
        w = self.killed('gate-start')
        self.assertEqual(w.calls('golden-gate'), [])

    def test_edited_sha(self):
        w = self.killed('edited-sha')
        self.assertEqual(w.config_now(), w.pre)

    def test_enable_start(self):
        w = self.killed('enable-start')
        self.assertEqual((w.enables(), os.path.exists(w.r.flag)), ([], False))
        self.assertEqual(w.config_now(), switched_config(w.pre, 'liveapp-mac-golden-' + today()))
        self.assert_recover_needed(w)

    def test_restore(self):
        w = Win(self)
        w.validate('refuse', call=3)
        self.killed('restore', w)
        self.assertEqual(w.config_now(), switched_config(w.pre, 'liveapp-mac-golden-' + today()))
        self.assertEqual(w.enables(), [])

    def test_pre_close_failure(self):
        w = Win(self)
        w.put('enable-refuse.1')
        self.killed('pre-close-failure', w)
        self.assertEqual(len(w.calls('runner-disable')), 1)

    def test_pin_rule(self):
        held = stop(FAM, 'NO IDLE', version=V2, detail={'text': 'x', 'sha': SHA2})
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[held])}, images={OLD: V0}))
        w.put('build-fail')
        res = w.run('switch-now', env={'RU_KILL_AT': 'pin-rule'})
        self.assertEqual(res.returncode, KILLED, res.stdout)
        self.assertEqual(w.keys()[-1], 'pin-rule')
        self.assertEqual(w.value('pin-rule'), '%s %s' % (V0, SHA0))
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V2, SHA2))   # still the window's

    def test_state_write(self):
        w = self.killed('state-write')
        self.assertEqual(w.value('state-write'), 'switched')
        self.assertIsNone(w.family())                                # the state is not written yet
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V0, SHA0))
        self.assert_recover_needed(w)

    def test_closed(self):
        w = self.killed('closed')
        self.assertEqual(w.windows(), [])
        self.assertEqual(w.family()['candidate']['version'], V0)     # the state was written before `closed`

    def test_control_no_kill_closes(self):
        w = Win(self)
        w.ok()
        self.assertFalse(os.path.exists(w.u.window))
        self.assertEqual(len(w.windows()), 1)
        res = w.r.cmd('pass')
        self.assertNotIn('RECOVER needed', res.stdout)


class TestRealBuildInterrupted(unittest.TestCase):
    """The REAL golden-build copy (stub tart) interrupted at its first clone and at publication (the clone to the
    output's name): a TERM to the window's process group. The journal ends at `build-start`; its names (the work VM,
    the output) stay protected; nothing after the build ran; a pre-existing image is never touched."""

    def interrupted(self, dst):
        w = Win(self, real_build=True)
        d = today()
        w.put('block-clone-' + dst.replace('D', d))
        p = w.sb.start(['/bin/zsh', '-f', w.r.script, 'rebuild', FAM], name='win')
        blocked = os.path.join(w.scn, 'blocked-clone-' + dst.replace('D', d))
        w.sb.wait_for(lambda: os.path.exists(blocked) or p.poll() is not None, 'the clone to block', timeout=120)
        self.assertTrue(os.path.exists(blocked), w.sb.output('win'))
        os.killpg(p.pid, signal.SIGTERM)

        def gone():
            if p.poll() is None:
                return False
            try:
                os.killpg(p.pid, 0)
            except ProcessLookupError:
                return True
            return False
        w.sb.wait_for(gone, 'every process of the window to end', timeout=60)
        self.assertEqual(w.keys()[-1], 'build-start')
        self.assertEqual(w.calls('golden-gate'), [])
        self.assertEqual(w.enables(), [])
        self.assertFalse(os.path.exists(w.r.flag))
        self.assertEqual(w.config_now(), w.pre)
        self.assertEqual(lines_of(w.u.protected), sorted([OLD, 'gold-' + d, 'liveapp-mac-golden-' + d]))
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertNotIn(OLD, [a for c in w.calls('tart') if c[:1] in (['delete'], ['stop']) for a in c])
        res = w.r.cmd('pass', ok=False)                 # RECOVER: the builder's names go (its gate never ran)
        self.assertIn('runner-updater: recover: ', res.stdout)
        self.assertFalse(os.path.exists(w.u.window), res.stdout)
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertFalse(os.path.exists(os.path.join(w.vms, 'liveapp-mac-golden-' + d)))
        return w, d

    def test_at_the_first_clone(self):
        w, d = self.interrupted('gold-D')
        self.assertFalse(os.path.exists(os.path.join(w.vms, 'gold-' + d)))   # golden-build's own cleanup

    def test_at_publication(self):
        w, d = self.interrupted('liveapp-mac-golden-D')
        self.assertIn(['stop', 'gold-' + d], w.calls('tart'))


class TestPinRule(unittest.TestCase):
    """D2's ONE RULE when the window closes: the pin names the version of the image the family's lines name in the
    config that runs; none found = the pin is removed, and status says so."""

    def test_a_failed_window_pins_the_old_images_version(self):
        held = stop(FAM, 'NO IDLE', version=V2, detail={'text': 'x', 'sha': SHA2})
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[held])}, images={OLD: V0}))
        w.put('build-fail')
        w.run('switch-now')
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V0, SHA0))
        self.assertEqual([s['stop'] for s in w.family()['stops']], ['check failed'])

    def test_an_old_image_of_no_known_version_removes_the_pin_and_status_says_so(self):
        held = stop(FAM, 'NO IDLE', version=V2, detail={'text': 'x', 'sha': SHA2})
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[held])}))
        w.put('build-fail')
        res = w.run('switch-now')
        self.assertIn('the pin %s is removed: the runner version of %s is not known' % (w.pin, OLD), res.stdout)
        self.assertEqual(w.value('pin-rule'), 'removed')
        self.assertFalse(os.path.exists(w.pin))
        self.assertIn('\nrunner-updater: family %s: host pin: none (a hand golden-build uses the release literal)\n'
                      % FAM, w.status())


class TestRecoverNeeded(unittest.TestCase):
    """An open window journal that no run of this release started: a pass or a command runs RECOVER first (a journal
    that disabled nothing closes with no STOP and no runner-disable); status names it and runs no RECOVER."""

    def test_pass_and_the_commands_with_an_open_journal(self):
        for args in (('pass',), ('rebuild', FAM), ('switch-now', FAM)):
            with self.subTest(args=args):
                w = Win(self)
                w.sb.write(w.u.window, 'window 20261101080000-1\nfamily %s\nkind switch\nimage %s\n' % (FAM, OLD),
                           0o600)
                self.assertIn('runner-updater: status: a window journal is open: %s' % w.u.window, w.status())
                res = w.r.cmd(*args, ok=False)
                self.assertIn('runner-updater: recover: nothing was disabled (no disable-start): the journal closes, '
                              'no STOP\n', res.stdout)
                self.assertFalse(os.path.exists(w.u.window))
                self.assertEqual(w.windows()[0], '20261101080000-1')

    def test_an_open_journal_comes_before_every_other_refusal(self):
        # RECOVER first: a config the window would refuse is read only after it
        w = Win(self, cfg=config(top='log-file = "/elsewhere.log"\n'))
        w.sb.write(w.u.window, 'window 20261101080000-1\nfamily %s\n' % FAM, 0o600)
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertLess(res.stdout.index('runner-updater: recover: '), res.stdout.index('a top-level log-file key'))

    WINDOW_CALL = ('WINDOW=%(w)s WINDOWS=%(ws)s CONFIG=%(c)s\nsource %(win)s || exit 8\n'
                   'ru_window mac-golden %(v)s %(sha)s idle 0 pass\nprint -r -- "rc $?"\n'
                   '[[ -d $WINDOWS ]] && print -r -- "windows made"\n')

    def window_call(self, open_journal):
        w = Win(self)
        if open_journal:
            w.sb.write(w.u.window, 'window 20261101080000-1\n', 0o600)
        body = self.WINDOW_CALL % {'w': w.u.window, 'ws': os.path.join(w.r.statedir, 'windows'),
                                   'c': w.sb.path('no-config'), 'win': os.path.join(w.tools, 'runner-updater-window'),
                                   'v': V0, 'sha': SHA0}
        return lib_run(w.r, body)

    def test_ru_window_itself_refuses_an_open_journal(self):
        # the function a later pass calls: its own check, before it makes or reads anything
        res = self.window_call(True)
        self.assertEqual(res.stdout.splitlines()[-1], 'rc 1', res.stdout + res.stderr)
        self.assertIn('runner-updater: STOP RECOVER needed: the window journal ', res.stdout)
        self.assertNotIn('windows made', res.stdout)

    def test_control_ru_window_with_no_open_journal_goes_on(self):
        res = self.window_call(False)
        self.assertNotIn('RECOVER needed', res.stdout)
        self.assertIn('windows made', res.stdout)

    def test_control_no_open_journal_the_pass_runs(self):
        w = Win(self)
        res = w.r.cmd('pass')
        self.assertNotIn('RECOVER needed', res.stdout)
        self.assertGreater(w.r.ps_calls(), 0)
        self.assertNotIn('a window journal is open', w.status())



class TestPreWindowStopsKeepWhatStillHolds(unittest.TestCase):
    """A STOP raised before runner-disable replaces only a held STOP of its own name. It never removes a held POOL DOWN
    (CI is down on the host: only a window that sees its target run, `running`, clears it) or a held NO IDLE (its
    release, which switch-now runs)."""

    def test_a_pre_window_stop_keeps_a_held_pool_down(self):
        w = Win(self)
        for n in (1, 2, 3, 4):
            w.put('enable-refuse.%d' % n)
        w.run()                                   # the first window: POOL DOWN, CI down, today's output kept (gate green)
        self.assertEqual([s['stop'] for s in w.family()['stops']], ['check failed', 'POOL DOWN'])
        self.assertFalse(os.path.exists(w.r.flag))
        res = w.run()                             # the same day: step 1 finds today's output, before START STATE
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP check failed: pre-window: liveapp-mac-golden-%s already exists' % today(),
                      res.stdout)
        self.assertEqual(sorted(s['stop'] for s in w.family()['stops']), ['POOL DOWN', 'check failed'])
        self.assertIn('pre-window', [s for s in w.family()['stops'] if s['stop'] == 'check failed'][0]['detail']['text'])
        st = w.status()
        self.assertIn('\n%s: STOP POOL DOWN (runner %s): runner-enable refused' % (FAM, V0), st)
        self.assertIn('Next, by hand: `%s/runner-enable`' % w.sb.path('cibin'), st)

    def test_a_pre_window_stop_keeps_a_held_no_idle_and_its_release(self):
        held = stop(FAM, 'NO IDLE', version=V2, detail={'text': 'IDLE: mac-a: busy 1', 'sha': SHA2})
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[held])}, images={OLD: V0}))
        w.put('free-kib', 10 * GIB)               # DISK: a STOP before runner-disable
        res = w.run('switch-now')
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP DISK: ', res.stdout)
        self.assertEqual(sorted(s['stop'] for s in w.family()['stops']), ['DISK', 'NO IDLE'])
        w.put('free-kib', 300 * GIB)
        w.ok('switch-now')                        # switch-now still runs the NO IDLE's release
        self.assertEqual((w.value('version'), w.value('runner-sha')), (V2, SHA2))
        self.assertEqual(w.family()['stops'], [])

    def test_a_pre_window_stop_replaces_a_held_stop_of_its_own_name(self):
        held = stop(FAM, 'DISK', version=V0, detail={'text': 'an old reading'})
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[held])}, images={OLD: V0}))
        w.put('free-kib', 10 * GIB)
        w.run()
        (s,) = w.family()['stops']
        self.assertEqual(s['stop'], 'DISK')
        self.assertIn('free disk 10 GiB', s['detail']['text'])

    def test_control_a_window_that_switches_clears_a_held_pool_down(self):
        held = stop(FAM, 'POOL DOWN', version=V0, detail={'text': 'x', 'hand': '/x/runner-enable'})
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[held])}, images={OLD: V0}))   # a person enabled CI
        w.ok()
        self.assertEqual(w.family()['stops'], [])

    def test_control_a_failed_window_that_sees_ci_run_clears_it(self):
        held = stop(FAM, 'POOL DOWN', version=V0, detail={'text': 'x', 'hand': '/x/runner-enable'})
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[held])}, images={OLD: V0}))
        w.put('build-fail')
        w.run()
        self.assertIn('running', w.keys())
        self.assertEqual([s['stop'] for s in w.family()['stops']], ['check failed'])


# the old runscaler's last record, written while runner-disable drains it; then the new one's: a CANNOT START of the
# new image, and a record after it (the last record of a pass is held to the next one)
P_LINE = ('2026-11-01 05:00:10 ERRO mac-a: Failed to start runner, will retry error="failed to start runner on '
          'runner-0000aaaa: tart exec: exit status 1"\n')
Q_LINES = ('2026-11-01 05:01:00 ERRO mac-a: Failed to start runner, will retry error="failed to start runner on '
           'runner-0000bbbb: tart exec: exit status 1"\n'
           '2026-11-01 05:01:10 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n')
RESTART = {'from': {'pid': 1, 'start': 2}, 'to': {'pid': 3, 'start': 4}, 'stopped': {'inode': '5', 'offset': 0,
                                                                                    'sha': '6' * 64}}


class TestOwnRestart(unittest.TestCase):
    """THE OWN RESTART (PLAN D6, core/README.md "Ownership by position"): the window reads the runscaler it will stop
    (`from`, which must be the state's boundary process), captures the log position once runner-disable has returned
    and no runscaler runs (`stopped`), and reads the new one running (`to`). The state's `restart` member keeps them
    until the next pass, which passes them as facts.restart once and clears them: that pass reads no gap, and the
    switched family's evidence opens at `stopped`."""

    def window(self, *scenario):
        """a pass (the boundary: P, at the log's end), then rebuild; SCENARIO: empty scenario files (e.g. no-start.1)"""
        w = Win(self)
        w.r.write_log('')
        w.r.cmd('pass')
        w.hook('drain.1', P_LINE)
        for name in scenario:
            w.put(name)
        res = w.run()
        return w, res

    def second_pass(self, w):
        w.r.append_log(Q_LINES)
        w.r.cmd('pass')
        with open(os.path.join(w.r.statedir, 'pass', 'r1.json')) as f:
            r1 = json.load(f)
        with open(os.path.join(w.r.statedir, 'pass', 'facts.json')) as f:
            facts = json.load(f)
        return r1, facts, w.u.get()['core']['families'][FAM]

    def test_the_pass_after_a_window_has_no_gap_and_counts_q_from_stopped(self):
        w, res = self.window()
        self.assertEqual(res.returncode, 0, res.stdout)
        after = w.r.log_bytes()
        self.assertEqual(after, P_LINE.encode())
        pid, start = (int(x) for x in w.value('running').split())
        rs = {'from': {'pid': P[0], 'start': P[2]}, 'to': {'pid': pid, 'start': start},
              'stopped': {'inode': str(os.stat(w.r.runlog).st_ino), 'offset': len(after),
                          'sha': hashlib.sha256(after[-64:]).hexdigest()}}
        self.assertEqual(w.u.get()['restart'], rs)
        self.assertEqual(w.value('from'), '%d %d' % (P[0], P[2]))
        self.assertEqual(w.value('stopped'), '%s %d %s' % (rs['stopped']['inode'], len(after), rs['stopped']['sha']))
        r1, facts, ev = self.second_pass(w)
        self.assertEqual(facts['restart'], rs)
        self.assertNotIn('restart', w.u.get())    # passed once, then cleared
        self.assertIn("(the updater's own restart: P's text to `stopped`, then Q's)", r1['reason'])
        self.assertEqual((ev['open'], ev['gaps']), (True, 0))
        self.assertEqual([x['t'] for x in ev['sets']['mac-a']['fails']], ['2026-11-01 05:01:00'])   # Q's, not P's

    def test_control_the_same_with_no_restart_member_is_a_gap(self):
        w, res = self.window()
        self.assertEqual(res.returncode, 0, res.stdout)
        s = w.u.get()
        del s['restart']
        w.u.put(s)
        r1, facts, ev = self.second_pass(w)
        self.assertIsNone(facts['restart'])
        self.assertIn('(the text before this boundary is UNKNOWN: it counts neither way)', r1['reason'])
        self.assertEqual(ev['sets'].get('mac-a', {}).get('fails', []), [])

    def test_from_is_not_the_boundary_process_no_restart_is_recorded(self):
        # no pass before the window: the state has no boundary process; a stale record is removed
        w = Win(self, s=state(on=True, images={OLD: V0}, restart=RESTART))
        w.ok()
        self.assertEqual(w.value('from'), 'none')
        self.assertNotIn('restart', w.u.get())

    def test_a_pre_close_failure_records_no_restart(self):
        # the text between the two runner-disables may be a third runscaler's: neither P's nor Q's
        w, res = self.window('enable-refuse.1')
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertEqual(w.keys().count('running'), 1)
        self.assertNotIn('restart', w.u.get())

    def test_a_runscaler_still_running_after_runner_disable_is_no_stopped(self):
        w, res = self.window('keep-proc.1', 'no-start.1')
        self.assertEqual(w.value('stopped'), 'none')
        self.assertNotIn('restart', w.u.get())

    def test_a_runscaler_seen_right_after_the_capture_is_no_stopped(self):
        # ps reads: the pass's two, START STATE, `from`, then `stopped`'s: none before the capture, one after it
        w = Win(self)
        w.r.write_log('')
        w.r.cmd('pass')
        w.r.set_ps([proc_line(*P)], call=6)
        w.ok()
        self.assertEqual(w.value('stopped'), 'none')
        self.assertNotIn('restart', w.u.get())

    def test_control_no_runscaler_before_or_after_the_capture(self):
        w, res = self.window()
        self.assertRegex(w.value('stopped'), r'^[0-9]+ [0-9]+ [0-9a-f]{64}$')


class TestTheTargetRuns(unittest.TestCase):
    """D1's close proof, each part on its own: FLAG present, ONE runscaler started after the config's install time
    (whole seconds), and the config's family lines = the last TARGET. In each cell the first runner-enable does not
    prove it: no `running` for it, a pre-close failure follows, and the second runner-enable's runscaler (6002) runs.
    A config changed to other lines is a person's file: the pre-close path enables no CI on it (carried (1))."""

    def proven_only_after_the_pre_close_failure(self, w):
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        k = w.keys()
        self.assertEqual((k.count('pre-close-failure'), k.count('running')), (1, 1), k)
        self.assertLess(k.index('pre-close-failure'), k.index('running'))
        self.assertEqual(w.value('running').split()[0], '6002')
        self.assertEqual(len(w.calls('runner-disable')), 2)

    def test_the_old_runscaler_that_still_runs_is_not_the_target(self):
        w = Win(self)
        w.put('keep-proc.1')                      # runner-disable did not stop it, and runner-enable starts none
        w.put('no-start.1')
        self.proven_only_after_the_pre_close_failure(w)

    def test_a_new_runscaler_with_no_flag_is_not_the_target(self):
        w = Win(self)
        w.put('no-flag.1')
        self.proven_only_after_the_pre_close_failure(w)

    def test_a_new_runscaler_on_other_family_lines_is_not_the_target(self):
        # the lines changed under it (a person's file): no `running`, and the pre-close path does not enable CI on a
        # file it never chose: STOP HAND CHANGE, CI down, the journal open for RECOVER
        w = Win(self)
        w.hook('enable-hook.1', "/usr/bin/sed -i '' 's/runner-image = \"liveapp-mac-golden-[0-9]*\"/runner-image = "
                                '"%s"/\' %s\n' % (IMG2, w.r.config))
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        k = w.keys()
        self.assertEqual((k.count('pre-close-failure'), k.count('running')), (1, 0), k)
        self.assertEqual(len(w.enables()), 1)
        self.assertIn('runner-updater: STOP HAND CHANGE: %s changed after the window installed its edit' % w.r.config,
                      res.stdout)
        self.assertTrue(os.path.exists(w.u.window))

    def test_control_the_first_runscaler_is_the_target(self):
        w = Win(self)
        w.ok()
        self.assertEqual(w.value('running').split()[0], '6001')
        self.assertNotIn('pre-close-failure', w.keys())


SEQ_TOOLS = (('tools-ps', 'ps'), ('tools-curl', 'curl'), ('tools-disk', 'df'), ('tools-disk', 'du'), ('fake', 'tart'),
             ('tools', 'runner-start'), ('tools', 'runner-enable'), ('tools', 'runner-disable'), ('tools', 'golden-build'),
             ('tools', 'golden-gate'))


def seq_log(w):
    """every host tool the window runs writes its name and first argument into ONE log, in call order"""
    seq = w.sb.path('logs', 'seq.log')
    for folder, name in SEQ_TOOLS:
        p = w.sb.path(folder, name)
        head, rest = read_text(p).split('\n', 1)
        w.sb.write(p, '%s\nprint -r -- "%s ${1-}" >> %s\n%s' % (head, name, seq, rest), 0o755)
    return seq


class TestIdlePairLast(unittest.TestCase):
    """PLAN D5: the idle pair's last read is followed only by runner-disable. Every check (START STATE, DISK,
    runner-enable --check, PRE-VALIDATE, the runscaler read `from`) runs before the pair; after its second read only
    local writes (runner-journal, jq, shasum, dd) come before runner-disable."""

    def test_after_the_second_idle_read_the_next_tool_is_runner_disable(self):
        w = Win(self)
        seq = seq_log(w)
        w.ok()
        names = [l.split()[0] for l in lines_of(seq)]
        curls = [i for i, n in enumerate(names) if n == 'curl']
        self.assertEqual(len(curls), 3, names)    # START STATE's read, then the pair
        self.assertEqual(names[curls[2] + 1], 'runner-disable', names)
        for t in ('ps', 'tart', 'df', 'du', 'runner-enable', 'runner-start'):
            self.assertIn(t, names[:curls[1]], (t, names))


class TestHandChangeAfterTheInstall(unittest.TestCase):
    """A person's edit after the window installed its edit (during the post-edit validate, between its tries, or while
    enable waits past the install second): the window restores nothing over the person's file and never enables CI on
    it. STOP HAND CHANGE, CI stays down, and the window journal stays open: the next pass's RECOVER validates the file
    before any runner-enable on it (test_runner_updater_recover.py, TestStep4Config)."""

    def hook_file(self, w, name, body):
        return w.sb.write(w.sb.path('hooks', name), '#!/bin/zsh -f\n' + body, 0o755)

    def handed(self, w, found, env=None):
        res = w.run(env=env)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP HAND CHANGE: %s changed after the window installed its edit' % w.r.config,
                      res.stdout)
        self.assertEqual(w.enables(), [])
        self.assertFalse(os.path.exists(w.r.flag))
        self.assertEqual(w.config_now(), found)
        self.assertTrue(os.path.exists(w.u.window))
        self.assertEqual(w.keys()[-2:], ['hand-change', 'stop'])
        self.assertEqual(w.value('hand-change'), sha(found))
        self.assertNotIn('restore', w.keys())
        w.window_validates = list(w.validates())                  # the window's own, before RECOVER's
        n = len(w.validates())
        res2 = w.r.cmd('pass', ok=False)
        self.assertIn('runner-updater: recover: ', res2.stdout)
        self.assertEqual(w.validates()[n][2], sha(found))         # RECOVER validated the person's file first
        for e in w.enables():
            self.assertEqual(e[2], sha(found))
        return res

    def test_an_edit_during_a_post_edit_validate_try(self):
        w = Win(self)
        w.validate('api', call=3)                 # post-edit try 1: API-ONLY, try again
        w.hook('validate-hook.3', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)   # after try 1 read the config
        w.validate('refuse', call=4)              # a try 2 would read the person's file (RECOVER's: NON-API, no CI)
        self.handed(w, switched_config(w.pre, 'liveapp-mac-golden-' + today()) + b'# a hand edit\n')

    def test_an_edit_before_a_try_reads_the_config(self):
        w = Win(self)
        w.hook('validate-prehook.3', 'print -r -- "# a hand edit" >> %s\n' % w.r.config)
        w.validate('refuse', call=3)              # try 1 reads the person's file: NON-API
        self.handed(w, switched_config(w.pre, 'liveapp-mac-golden-' + today()) + b'# a hand edit\n')

    # the window copy runs RU_TEST_HOOK where it would sleep: between two validate tries, or in the mtime-second wait
    ONCE = '[[ -f ${0:h}/done ]] || { print -r -- "# a hand edit" >> %s; : > ${0:h}/done }\n'

    def test_an_edit_between_two_tries_is_never_validated(self):
        w = Win(self, win_rewrites=[('/bin/sleep $VALIDATE_GAP', '/bin/zsh -f $RU_TEST_HOOK')])
        hook = self.hook_file(w, 'gap', self.ONCE % w.r.config)
        w.validate('api', call=3)                 # post-edit try 1: API-ONLY; the edit lands before try 2
        found = switched_config(w.pre, 'liveapp-mac-golden-' + today()) + b'# a hand edit\n'
        self.handed(w, found, env={'RU_TEST_HOOK': hook})
        self.assertNotIn(sha(found), [v[2] for v in w.window_validates])

    def test_an_edit_while_enable_waits_past_the_install_second(self):
        w = Win(self, win_rewrites=[('/bin/sleep 0.2', '/bin/zsh -f $RU_TEST_HOOK')])
        hook = self.hook_file(w, 'wait', (self.ONCE % w.r.config) + '/bin/sleep 0.2\n')
        w.hook('validate-hook.3', 'zmodload zsh/datetime; export TZ=UTC\n'   # the installed edit's mtime 2 s ahead
                                  '/usr/bin/touch -t $(strftime %%Y%%m%%d%%H%%M.%%S $(( EPOCHSECONDS + 2 ))) %s\n'
                                  % w.r.config)
        self.handed(w, switched_config(w.pre, 'liveapp-mac-golden-' + today()) + b'# a hand edit\n',
                    env={'RU_TEST_HOOK': hook})
        self.assertEqual(w.window_validates[-1][2], sha(switched_config(w.pre, 'liveapp-mac-golden-' + today())))

    def test_control_a_non_api_post_validate_on_the_windows_own_edit_enables_the_backup(self):
        w = Win(self)
        w.validate('refuse', call=3)
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertEqual([e[2] for e in w.enables()], [sha(w.pre)])
        self.assertEqual(w.config_now(), w.pre)
        self.assertFalse(os.path.exists(w.u.window))


class TestToolTextInTheJournal(unittest.TestCase):
    """Every journal value made from a tool's text (pre-close-failure, build-failed, stop) is one line of at most 900
    bytes, each control character a `?` (runner-journal refuses a control character or more than 1000 bytes): a long or
    tabbed refusal still takes the window's one pre-close recovery."""

    def refused_once(self, text):
        w = Win(self)
        w.hook('enable-refuse.1', text)
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertEqual(len(w.calls('runner-disable')), 2)
        self.assertEqual(w.config_now(), w.pre)
        self.assertTrue(os.path.exists(w.r.flag))
        self.assertEqual(w.enables()[-1][2], sha(w.pre))
        self.assertEqual([s['stop'] for s in w.family()['stops']], ['check failed'])
        self.assertFalse(os.path.exists(w.u.window))
        v = w.value('pre-close-failure')
        self.assertNotRegex(v, '[\x00-\x1f\x7f]')
        self.assertLessEqual(len(v.encode()), 900)
        return w, v

    def test_a_1200_byte_refusal(self):
        w, v = self.refused_once('runner-enable: REFUSE FILES is not green: ' + 'x' * 1200)
        self.assertTrue(v.startswith('runner-enable refused (exit 1): runner-enable: REFUSE FILES is not green: xxx'), v)
        self.assertIn('x' * 1200, [s for s in w.family()['stops']][0]['detail']['text'])   # the state keeps it whole

    def test_a_tab_in_the_refusal(self):
        w, v = self.refused_once('runner-enable: REFUSE a\tb')
        self.assertEqual(v, 'runner-enable refused (exit 1): runner-enable: REFUSE a?b')

    def test_control_a_short_refusal(self):
        w, v = self.refused_once('')
        self.assertEqual(v, 'runner-enable refused (exit 1): runner-enable: REFUSE the wall stamp does not match Tart')

    def test_a_tab_in_the_done_name(self):
        w = Win(self)
        w.put('done-name', 'x\ty')
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertEqual(w.value('build-failed'), 'DONE x?y')
        self.assertFalse(os.path.exists(w.u.window))
        self.assertTrue(os.path.exists(w.r.flag))


class TestFailedWindowDeletesItsOutput(unittest.TestCase):
    """PLAN D5 :209, RECOVER step 3: a window that ends held, whose gate did not pass, deletes its builder's names (the
    output, the work VM) that tart lists, each journaled first (`delete NAME`), and only when no non-comment line of
    the config names it. The old image is never one of them. golden-prune (the REAL copy) then prints nothing new."""

    OLDER = 'liveapp-mac-golden-20260901'

    def prune(self, w):
        prune = w.sb.copy_script('bin/golden-prune', [
            ('STATEDIR=/Users/ci/.local/state/runner-updater', 'STATEDIR=' + w.r.statedir)],
            dest=w.sb.path('prune', 'golden-prune'))
        return subprocess.run(['/bin/zsh', '-f', prune, OLD] + sorted(os.listdir(w.vms)), capture_output=True, text=True)

    def red(self, cfg=None, sets=('mac-a',)):
        out = 'liveapp-mac-golden-' + today()
        w = Win(self, cfg=cfg)
        w.r.set_curl(json.dumps(healthz(*sets)))
        w.sb.write(os.path.join(w.vms, self.OLDER), '')
        w.put('gate', 1)
        res = w.run()
        self.assertEqual(res.returncode, 1, res.stdout)
        return w, out

    def test_a_gate_red_window_deletes_its_output(self):
        w, out = self.red(cfg=config(top='# today: liveapp-mac-golden-%s\n' % today()))   # a comment names it
        self.assertFalse(os.path.exists(os.path.join(w.vms, out)))
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))
        k = w.keys()
        self.assertEqual(w.value('delete'), out)
        self.assertLess(k.index('delete'), k.index('pin-rule'))
        self.assertIn(['delete', out], w.calls('tart'))
        self.assertNotIn(out, lines_of(w.u.protected))
        p = self.prune(w)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, '', ''))

    def test_a_name_a_config_line_names_is_kept(self):
        out = 'liveapp-mac-golden-' + today()
        w, _ = self.red(cfg=config((('mac-a', OLD), ('mac-c', out))), sets=('mac-a', 'mac-c'))   # another set names it
        self.assertTrue(os.path.exists(os.path.join(w.vms, out)))
        self.assertNotIn('delete', w.keys())

    def test_control_a_gate_green_window_keeps_its_output(self):
        w = Win(self)
        w.validate('refuse', call=3)              # a failure after the gate passed
        w.run()
        self.assertTrue(os.path.exists(os.path.join(w.vms, 'liveapp-mac-golden-' + today())))
        self.assertNotIn('delete', w.keys())

    def test_a_kill_at_delete_leaves_the_output(self):
        w = Win(self)
        w.put('gate', 1)
        res = w.run(env={'RU_KILL_AT': 'delete'})
        self.assertEqual(res.returncode, KILLED, res.stdout + res.stderr)
        self.assertEqual(w.keys()[-1], 'delete')
        self.assertTrue(os.path.exists(os.path.join(w.vms, 'liveapp-mac-golden-' + today())))


class TestFutureMtime(unittest.TestCase):
    """The wait past the config's install second is bounded (MTIME_WAIT): a config whose mtime is further ahead of the
    clock (clock skew, a hand `touch`) is STOP check failed, the file as found is kept in the window's folder, the
    backup goes back and CI is enabled on it, and the window ends (the lock is free). TestMtimeSecond is the control:
    2 s ahead, it waits and enables."""

    def test_a_config_dated_in_the_future_does_not_hold_ci_down(self):
        w = Win(self)
        w.hook('check-hook.2', 'print -r -- "# a hand edit" >> %s\n/usr/bin/touch -t 203001010000 %s\n'
               % (w.r.config, w.r.config))
        found = w.pre + b'# a hand edit\n'
        res = w.sb.run(['/bin/zsh', '-f', w.r.script, 'rebuild', FAM], timeout=60)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("runner-updater: STOP check failed: the config's mtime ", res.stdout)
        self.assertEqual(w.config_now(), w.pre)
        self.assertTrue(os.path.exists(w.r.flag))
        self.assertEqual([e[2] for e in w.enables()], [sha(w.pre)])
        self.assertEqual(w.r.log_bytes(w.value('found')), found)
        self.assertEqual(sorted(s['stop'] for s in w.family()['stops']), ['HAND CHANGE', 'check failed'])
        self.assertFalse(os.path.exists(w.u.window))
        self.assertNotIn('another run holds', w.r.cmd('pass').stdout)


class TestPinRuleNoSha(unittest.TestCase):
    """D2's ONE RULE: the old image's version is known (the state's record) but no sha256 of it is (not this window's,
    not the pre-window pin's, not the release literal's): the pin is removed, never written with another version's
    sha."""

    V1 = '2.338.9'

    def test_a_version_known_with_no_sha_removes_the_pin(self):
        self.assertNotIn(self.V1, (V0, V2))
        held = stop(FAM, 'NO IDLE', version=V2, detail={'text': 'x', 'sha': SHA2})
        w = Win(self, s=state(on=True, families={FAM: fam(stops=[held])}, images={OLD: self.V1}))
        w.put('build-fail')
        res = w.run('switch-now')
        self.assertIn('the pin %s is removed: no sha256 of runner %s is known' % (w.pin, self.V1), res.stdout)
        self.assertEqual(w.value('pin-rule'), 'removed')
        self.assertFalse(os.path.exists(w.pin))


if __name__ == '__main__':
    unittest.main()
