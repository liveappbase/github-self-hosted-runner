"""bin/runner-updater report and its facts collector, bin/runner-updater-lib (the updater's OBSERVE slice: no action).

A Rig copies both files into a sandbox with every path constant rewritten (RUNNER, CONFIG and with it runner.log beside
it, STATEDIR, FAMILIES, PS, CURL, CORE; JQ is the jq under test, $JQ or /usr/bin/jq). Stubs stand in for ps (it prints
a scenario, and may append to the log as it is called, which places a write before or after the capture) and curl (the
/healthz reads). The core programs are the real ones. The log text is runscaler's own format: fixtures/updater/
studio-cut.log is cut from a real Studio log with every host value replaced, and the failure records are runscaler's
error texts in charm's text format (the core's fixtures pin that format byte for byte).
"""
import calendar
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import unittest

from tests.studio.support import REPO, Sandbox

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'updater')
IMG = 'liveapp-mac-golden-20261001'
IMG2 = 'liveapp-mac-golden-20261015'
UID = os.getuid()
P = (4242, 'Sun Nov  1 08:00:00 2026', calendar.timegm((2026, 11, 1, 8, 0, 0, 0, 0, 0)))
Q = (5151, 'Sun Nov  1 09:23:20 2026', calendar.timegm((2026, 11, 1, 9, 23, 20, 0, 0, 0)))
INSTALLED = P[2] - 60
HEALTHZ = {'status': 'ok', 'version': '0.9.5', 'uptime': '1h0m0s',
           'scale_sets': [{'name': 'mac-a', 'ready': True, 'idle': 0, 'busy': 0,
                           'metrics': {'jobs_started': 0, 'jobs_completed': 0, 'desired_runners': 0}}]}
ACTIONS = ('runner-disable', 'runner-enable', 'golden-build', 'golden-gate', 'tart', 'launchctl', 'kill')


def the_jq():
    j = os.environ.get('JQ', '/usr/bin/jq')
    return j if os.sep in j else shutil.which(j)


def read_text(path):
    with open(path) as f:
        return f.read()


def fixture(name):
    with open(os.path.join(FIX, name), encoding='utf-8') as f:
        return f.read()


def example():
    with open(os.path.join(REPO, 'config', 'config.toml.example')) as f:
        return f.read()


def config(blocks=(('mac-a', IMG),), top=''):
    """config.toml.example with its [[scaleset]] block once per (NAME, IMAGE); IMAGE None drops the runner-image line.
    top: lines put among the top-level keys."""
    head, block = example().split('[[scaleset]]\n', 1)
    head = head.replace('log-level = "info"\n', 'log-level = "info"\n' + top)
    out = head
    for name, image in blocks:
        b = block.replace('name = "mac-ci-REPO"', 'name = "%s"' % name)
        b = b.replace('runner-image = "liveapp-mac-golden-YYYYMMDD"\n', '' if image is None else 'runner-image = "%s"\n' % image)
        out += '[[scaleset]]\n' + b
    return out


def sha64(data):
    return hashlib.sha256(data[-64:]).hexdigest()


class Rig:
    def __init__(self, test, statedir=True, gap='0', jq=None, families='fx tart mac-a\n', cfg=None, extra_rewrites=(),
                 jq_wrap=False, protected=True):
        self.test = test
        sb = self.sb = Sandbox(test)
        self.cfgdir = sb.mkdir('config')
        self.config = os.path.join(self.cfgdir, 'config.toml')
        self.runlog = os.path.join(self.cfgdir, 'runner.log')
        self.statedir = sb.path('state', 'runner-updater')
        if statedir:
            os.makedirs(self.statedir)
            if protected:
                sb.write(os.path.join(self.statedir, 'protected'), '')
        self.report_dir = os.path.join(self.statedir, 'report')
        self.pass_dir = os.path.join(self.report_dir, 'pass')
        self.families = sb.path('families')
        self.runner = sb.path('fake', 'runner')
        self.psd = sb.mkdir('ps')
        self.curld = sb.mkdir('curl')
        sb.stub('ps', PS_STUB % {'d': self.psd, 'log': self.runlog, 'config': self.config}, folder=sb.mkdir('tools-ps'))
        sb.stub('curl', CURL_STUB % {'d': self.curld}, folder=sb.mkdir('tools-curl'))
        for a in ACTIONS:   # each logs its name and arguments to logs/actions.log
            sb.stub(a, 'print -r -- "${0:t} $*" >> %s' % sb.path('logs', 'actions.log'))
        self.jq = jq or the_jq()
        self.jqd = sb.mkdir('jqwrap')
        if jq_wrap:   # logs each call; --version from jqwrap/version when it exists; jqwrap/fail names a program to fail
            self.jq = sb.stub('jq', JQ_WRAP % {'d': self.jqd, 'jq': self.jq}, folder=self.jqd)
        rewrites = [
            ('RUNNER=/Users/ci/bin/runner', 'RUNNER=' + self.runner),
            ('CONFIG=/Users/ci/.config/runner/config.toml', 'CONFIG=' + self.config),
            ('STATEDIR=/Users/ci/.local/state/runner-updater', 'STATEDIR=' + self.statedir),
            ('FAMILIES=/Users/ci/.config/runner-updater/families', 'FAMILIES=' + self.families),
            ('JQ=/usr/bin/jq', 'JQ=' + self.jq),
            ('PS=/bin/ps', 'PS=' + sb.path('tools-ps', 'ps')),
            ('CURL=/usr/bin/curl', 'CURL=' + sb.path('tools-curl', 'curl')),
            ('HEALTHZ_GAP=3', 'HEALTHZ_GAP=' + gap),
            ('CORE=${0:A:h:h}/core', 'CORE=' + os.path.join(REPO, 'core')),
        ] + list(extra_rewrites)
        self.script = sb.copy_script('bin/runner-updater', rewrites)
        self.lib = sb.copy_script('bin/runner-updater-lib', [])
        sb.write(self.config, cfg if cfg is not None else config())
        os.utime(self.config, (INSTALLED, INSTALLED))
        if families is not None:
            sb.write(self.families, families)
        self.set_ps([proc_line(*P)])
        self.set_curl(json.dumps(HEALTHZ))
        self.write_log(fixture('studio-cut.log'))

    # scenario
    def set_ps(self, lines, call=None):
        """the ps output (with BACKGROUND), for every call or for call number CALL only"""
        name = 'out' if call is None else 'out.%d' % call
        text = ''.join(l + '\n' for l in lines + BACKGROUND)
        self.sb.write(os.path.join(self.psd, name), text.replace('{runner}', self.runner).replace('{config}', self.config))

    def ps_append(self, call, text):
        """the ps stub's call number CALL appends TEXT to runner.log after it prints (1: before the capture, 2: after)"""
        self.sb.write(os.path.join(self.psd, 'append.%d' % call), text)

    def set_curl(self, body, call=None):
        self.sb.write(os.path.join(self.curld, 'out' if call is None else 'out.%d' % call), body)

    def write_log(self, text, path=None):
        with open(path or self.runlog, 'w', encoding='utf-8') as f:
            f.write(text)

    def append_log(self, text):
        with open(self.runlog, 'a', encoding='utf-8') as f:
            f.write(text)

    def rotate(self):
        """runscaler's rotation (internal/config/logfile.go): remove runner.log.1, rename runner.log to it, a new file"""
        if os.path.exists(self.runlog + '.1'):
            os.remove(self.runlog + '.1')
        os.rename(self.runlog, self.runlog + '.1')
        self.write_log('')

    # runs
    def report(self, *args, env=None, ok=True):
        r = self.sb.run(['/bin/zsh', '-f', self.script, 'report'] + list(args), extra_env=env)
        if ok:
            self.test.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def facts(self):
        with open(os.path.join(self.pass_dir, 'facts.json')) as f:
            return json.load(f)

    def text(self):
        with open(os.path.join(self.pass_dir, 'log.txt'), 'rb') as f:
            return f.read()

    def healthz(self):
        with open(os.path.join(self.pass_dir, 'healthz.json')) as f:
            return [json.loads(l) for l in f.read().splitlines()]

    def state_bytes(self):
        p = os.path.join(self.report_dir, 'state.json')
        if not os.path.exists(p):
            return None
        with open(p, 'rb') as f:
            return f.read()

    def log_bytes(self, path=None):
        with open(path or self.runlog, 'rb') as f:
            return f.read()

    def ps_calls(self):
        return len(self.sb.calls('ps'))

    def curl_calls(self):
        return self.sb.calls('curl')


def proc_line(pid, lstart, start=None, args=None, uid=None):
    return '%5d %5d %s     %s' % (pid, UID if uid is None else uid, lstart, args or '{runner} run --config {config}')


# lines of other processes, always in the ps output
BACKGROUND = ['    1     0 Mon Nov  2 09:47:57 2026     /sbin/launchd',
              '  345   %d Mon Nov  2 10:22:56 2026     /bin/zsh -f' % UID]

PS_STUB = '''d=%(d)s
n=0; [[ -f $d/count ]] && n=$(<$d/count); (( n++ )); print -r -- $n > $d/count
f=$d/out; [[ -f $d/out.$n ]] && f=$d/out.$n
[[ -f $f ]] || exit 1
/bin/cat $f
[[ -f $d/append.$n ]] && /bin/cat $d/append.$n >> %(log)s
[[ -f $d/mtime.$n ]] && /usr/bin/touch -t $(<$d/mtime.$n) %(config)s
exit 0
'''

CURL_STUB = '''d=%(d)s
zmodload zsh/datetime
n=0; [[ -f $d/count ]] && n=$(<$d/count); (( n++ )); print -r -- $n > $d/count
print -r -- $EPOCHREALTIME >> $d/times
if [[ -f $d/block ]]; then i=0; until [[ -f $d/go ]]; do (( i++ < 1200 )) || exit 28; /bin/sleep 0.05; done; fi
f=$d/out; [[ -f $d/out.$n ]] && f=$d/out.$n
[[ -f $f && $(<$f) != FAIL ]] || exit 22
/bin/cat $f
'''


class TestFacts(unittest.TestCase):
    """facts.json: format 1, exactly core/README.md's members, from what the pass measured."""

    def test_facts_are_format_1(self):
        r = Rig(self, cfg=config((('mac-a', IMG), ('mac-b', None), ('mac-c', IMG2))),
                families='# the Mac families\n\nfx tart mac-a\nfy tart mac-c\n')
        r.report()
        data = r.log_bytes()
        st = os.stat(r.runlog)
        proc = {'pid': P[0], 'start': P[2]}
        self.assertEqual(r.facts(), {
            'format': 1, 'host': 'studio', 'sets': ['mac-a', 'mac-b', 'mac-c'],
            'proc': {'before': proc, 'after': proc},
            'position': {'inode': str(st.st_ino), 'offset': len(data), 'sha': sha64(data)},
            'continuous': False, 'restart': None,
            'config': {'installed': INSTALLED, 'lines': {'mac-a': IMG, 'mac-c': IMG2}},
            'families': {'fx': {'provider': 'tart', 'sets': ['mac-a'], 'candidate': None, 'back_until': None},
                         'fy': {'provider': 'tart', 'sets': ['mac-c'], 'candidate': None, 'back_until': None}},
            'stops': []})

    def test_the_sha_of_a_log_shorter_than_64_bytes(self):
        r = Rig(self)
        r.write_log('2026-11-01 05:00:00 INFO a\n')
        r.report()
        self.assertEqual(r.facts()['position']['sha'], hashlib.sha256(b'2026-11-01 05:00:00 INFO a\n').hexdigest())
        r.write_log('')
        r.report()
        self.assertEqual(r.facts()['position'], {'inode': str(os.stat(r.runlog).st_ino), 'offset': 0,
                                                 'sha': hashlib.sha256(b'').hexdigest()})

    def test_no_runscaler_log_is_no_facts(self):
        r = Rig(self)
        os.remove(r.runlog)
        res = r.report(ok=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn('runner-updater: REFUSE no facts: no runscaler log %s\n' % r.runlog, res.stdout)
        self.assertFalse(os.path.exists(os.path.join(r.pass_dir, 'idle.json')))


class TestPosition(unittest.TestCase):
    """The order: the process, then the log position, then the process again; no byte past the position is read."""

    def test_a_write_after_the_capture_is_not_in_this_pass(self):
        r = Rig(self)
        r.report()
        late = '2026-11-01 05:00:00 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n'
        r.ps_append(4, late)          # this pass's second ps call (calls 3 and 4): after the capture
        before = r.log_bytes()
        r.append_log('2026-11-01 04:59:00 INFO mac-a: Listening for jobs maxRunners=2 minRunners=0\n')
        r.report()
        self.assertEqual(r.ps_calls(), 4)
        mid = r.log_bytes()[:-len(late)]
        self.assertEqual(r.text(), mid[len(before):])
        self.assertEqual(r.facts()['position']['offset'], len(mid))
        self.assertTrue(r.facts()['continuous'])
        r.report()                    # the next pass reads it
        self.assertEqual(r.text(), late.encode())

    def test_control_a_write_before_the_capture_is_in_this_pass(self):
        r = Rig(self)
        r.report()
        early = '2026-11-01 05:00:00 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n'
        r.ps_append(3, early)         # this pass's first ps call: before the capture
        before = r.log_bytes()
        r.report()
        self.assertEqual(r.text(), early.encode())
        self.assertEqual(r.facts()['position']['offset'], len(before) + len(early))


class TestContinuity(unittest.TestCase):
    """continuous, and log.txt, against the state's boundary (the position the last pass captured)."""

    NEW = '2026-11-01 05:00:00 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n'

    def first(self):
        r = Rig(self)
        r.report()
        self.assertFalse(r.facts()['continuous'])        # a first pass has no boundary
        self.assertEqual(r.text(), b'')
        return r, r.log_bytes()

    def test_same_file(self):
        r, old = self.first()
        r.append_log(self.NEW)
        res = r.report()
        self.assertTrue(r.facts()['continuous'])
        self.assertEqual(r.text(), self.NEW.encode())
        self.assertIn('runner-updater: log: runner.log at offset %d; continuous: the same file since the last pass\n'
                      % len(r.log_bytes()), res.stdout)

    def test_a_rewritten_file_is_not_continuous(self):
        r, old = self.first()
        # the same inode, the same bytes up to one changed just before the boundary, then more
        changed = old[:-2] + (b'X' if old[-2:-1] != b'X' else b'Y') + old[-1:] + self.NEW.encode()
        with open(r.runlog, 'r+b') as f:
            f.write(changed)
        r.report()
        self.assertFalse(r.facts()['continuous'])
        self.assertEqual(r.text(), changed)              # only what can be read: the file to the position

    def test_a_cut_file_is_not_continuous(self):
        r, old = self.first()
        with open(r.runlog, 'r+b') as f:
            f.truncate(len(old) // 2)
        r.report()
        self.assertFalse(r.facts()['continuous'])
        self.assertEqual(r.text(), old[:len(old) // 2])

    def test_one_rotation(self):
        r, old = self.first()
        r.append_log('2026-11-01 04:59:00 INFO mac-a: Listening for jobs maxRunners=2 minRunners=0\n')
        rest = r.log_bytes()[len(old):]
        r.rotate()
        r.append_log(self.NEW)
        r.report()
        self.assertTrue(r.facts()['continuous'])
        self.assertEqual(r.text(), rest + self.NEW.encode())
        self.assertEqual(r.facts()['position']['inode'], str(os.stat(r.runlog).st_ino))

    def test_two_rotations_are_not_continuous(self):
        r, old = self.first()
        r.rotate()
        r.append_log('2026-11-01 04:59:00 INFO mac-a: Listening for jobs maxRunners=2 minRunners=0\n')
        r.rotate()
        r.append_log(self.NEW)
        r.report()
        self.assertFalse(r.facts()['continuous'])
        self.assertEqual(r.text(), self.NEW.encode())

    def test_two_rotations_through_a_file_with_the_same_bytes_are_not_continuous(self):
        # runner.log.1 holds the boundary file's bytes, so its sha matches at the boundary, but it is another file
        # (another inode): the log rotated twice, and the text between is lost
        r, old = self.first()
        r.rotate()
        r.write_log(old.decode('utf-8') + '2026-11-01 04:59:00 INFO mac-a: Listening for jobs maxRunners=2 minRunners=0\n')
        r.rotate()
        r.append_log(self.NEW)
        r.report()
        self.assertFalse(r.facts()['continuous'])
        self.assertEqual(r.text(), self.NEW.encode())

    def test_a_rotated_file_rewritten_at_the_boundary_is_not_continuous(self):
        r, old = self.first()
        r.rotate()
        with open(r.runlog + '.1', 'r+b') as f:      # the boundary's inode, its last byte before the boundary changed
            f.seek(len(old) - 1)
            f.write(b'X' if old[-1:] != b'X' else b'Y')
        r.append_log(self.NEW)
        r.report()
        self.assertFalse(r.facts()['continuous'])
        self.assertEqual(r.text(), self.NEW.encode())

    def test_a_removed_backup_is_not_continuous(self):
        r, old = self.first()
        r.rotate()
        os.remove(r.runlog + '.1')
        r.append_log(self.NEW)
        r.report()
        self.assertFalse(r.facts()['continuous'])


class TestProcess(unittest.TestCase):
    def test_the_same_process_before_and_after(self):
        r = Rig(self)
        r.report()
        f = r.facts()['proc']
        self.assertEqual(f, {'before': {'pid': P[0], 'start': P[2]}, 'after': {'pid': P[0], 'start': P[2]}})

    def test_a_restart_between_the_two_reads(self):
        r = Rig(self)
        r.set_ps([proc_line(*P)], call=1)
        r.set_ps([proc_line(*Q)], call=2)
        r.report()
        self.assertEqual(r.facts()['proc'], {'before': {'pid': P[0], 'start': P[2]},
                                             'after': {'pid': Q[0], 'start': Q[2]}})

    def test_no_process_is_null(self):
        r = Rig(self)
        r.set_ps([])
        r.report()
        self.assertEqual(r.facts()['proc'], {'before': None, 'after': None})

    def test_only_this_users_runscaler_run_with_this_config_counts(self):
        r = Rig(self)
        r.set_ps([proc_line(7001, P[1], uid=UID + 1),                                   # another user
                  proc_line(7002, P[1], args='{runner} validate --config {config}'),     # a validate
                  proc_line(7003, P[1], args='{runner} run --config /x/config.toml'),    # another config
                  proc_line(7004, P[1], args='/bin/zsh -f {runner} run --config {config}')])
        r.report()
        self.assertEqual(r.facts()['proc'], {'before': None, 'after': None})

    def test_control_the_same_lines_with_the_runscaler(self):
        r = Rig(self)
        r.set_ps([proc_line(7001, P[1], uid=UID + 1), proc_line(*P),
                  proc_line(7002, P[1], args='{runner} validate --config {config}')])
        r.report()
        self.assertEqual(r.facts()['proc']['before'], {'pid': P[0], 'start': P[2]})

    def test_two_runscalers_are_no_facts(self):
        r = Rig(self)
        r.set_ps([proc_line(*P), proc_line(*Q)])
        res = r.report(ok=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn('runner-updater: REFUSE no facts: 2 runscaler processes run', res.stdout)

    def test_a_ps_it_cannot_read_is_no_facts(self):
        r = Rig(self)
        r.sb.write(os.path.join(r.psd, 'out'), 'garbage\n')
        res = r.report(ok=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn('runner-updater: REFUSE no facts: ps printed no line this reads', res.stdout)

    def test_the_start_is_read_in_utc_whatever_the_callers_zone(self):
        # ps prints lstart in TZ; runner-updater exports TZ=UTC, so the stub's text is a UTC time
        for tz in ('America/New_York', 'Europe/London', 'Asia/Tokyo'):
            with self.subTest(tz=tz):
                r = Rig(self)
                r.report(env={'TZ': tz})
                self.assertEqual(r.facts()['proc']['before']['start'], P[2])


class TestRealPs(unittest.TestCase):
    """ru_proc with the REAL /bin/ps: a process whose argv is exactly "RUNNER run --config CONFIG" (zsh's exec -a sets
    argv[0]; zsh then runs the script file `run`, which waits), started by this test in a process group of its own."""

    def driver(self, sb, runner, cfg):
        lib = sb.copy_script('bin/runner-updater-lib', [])
        return sb.write(sb.path('driver'), '''#!/bin/zsh -f
export LC_ALL=C TZ=UTC
RUNNER=%s CONFIG=%s PS=/bin/ps
source %s || exit 9
ru_proc; rc=$?
print -r -- "$rc $REPLY"
''' % (runner, cfg, lib), 0o755)

    def test_real_ps_finds_the_process_and_its_start(self):
        sb = Sandbox(self)
        # the name must not start with "r": zsh run as r* is a restricted shell, and the script's /bin/sleep is refused
        runner, cfg = sb.path('fake', 'the-runner'), sb.path('config', 'config.toml')
        d = sb.mkdir('run-dir')
        sb.write(os.path.join(d, 'run'), '/bin/sleep 60\n')
        drv = self.driver(sb, runner, cfg)
        t0 = int(time.time())
        p = sb.start(['/bin/zsh', '-fc', 'cd %s && exec -a %s /bin/zsh run --config %s' % (d, runner, cfg)])
        t1 = int(time.time()) + 1
        out = {}

        def seen():
            out['r'] = sb.run([drv]).stdout.strip()
            return out['r'] != '0 null'
        sb.wait_for(seen, 'the process in ps')
        rc, js = out['r'].split(' ', 1)
        self.assertEqual(rc, '0', out['r'])
        got = json.loads(js)
        self.assertEqual(got['pid'], p.pid)
        self.assertTrue(t0 - 1 <= got['start'] <= t1, (t0, got, t1))

    def test_control_no_such_process_is_null(self):
        sb = Sandbox(self)
        drv = self.driver(sb, sb.path('fake', 'runner'), sb.path('config', 'config.toml'))
        self.assertEqual(sb.run([drv]).stdout, '0 null\n')


class TestConfig(unittest.TestCase):
    def test_the_config_is_read_after_the_process(self):
        # a config installed after the process started (here: as the second process read runs) has the later mtime,
        # which proves nothing; read before the process, the old mtime would prove the new config ran
        r = Rig(self)
        r.sb.write(os.path.join(r.psd, 'mtime.2'), '202611010801.40')   # touch -t, UTC: P's start + 100 s
        r.report()
        self.assertEqual(r.facts()['config']['installed'], P[2] + 100)

    def refused(self, cfg, why):
        r = Rig(self, cfg=cfg)
        res = r.report(ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE no facts: %s%s\n' % (r.config, why), res.stdout)
        self.assertFalse(os.path.exists(os.path.join(r.pass_dir, 'facts.json')))

    def test_the_example_config_is_read(self):
        r = Rig(self, cfg=config((('mac-a', IMG), ('mac-b', IMG2))))
        r.report()
        c = r.facts()['config']
        self.assertEqual(c, {'installed': INSTALLED, 'lines': {'mac-a': IMG, 'mac-b': IMG2}})
        self.assertEqual(r.facts()['sets'], ['mac-a', 'mac-b'])

    def test_installed_is_the_mtime(self):
        r = Rig(self)
        os.utime(r.config, (1793000000, 1793000000))
        r.report()
        self.assertEqual(r.facts()['config']['installed'], 1793000000)

    def test_a_comment_line_is_no_image(self):
        cfg = config((('mac-a', None),)).replace('disable-update = false\n',
                                                 'disable-update = false\n# runner-image = "liveapp-mac-golden-20260101"\n')
        r = Rig(self, cfg=cfg)
        r.report()
        self.assertEqual(r.facts()['config']['lines'], {})
        self.assertEqual(r.facts()['sets'], ['mac-a'])

    def test_a_block_with_two_names(self):
        self.refused(config().replace('name = "mac-a"\n', 'name = "mac-a"\nname = "mac-b"\n'),
                     ' line 40: a [[scaleset]] block has two names')

    def test_a_block_with_two_images(self):
        self.refused(config().replace('disable-update = false\n', 'disable-update = false\nrunner-image = "%s"\n' % IMG2),
                     ' line 47: a [[scaleset]] block has two runner-image lines')

    def test_an_image_line_at_the_top(self):
        self.refused(config(top='runner-image = "%s"\n' % IMG), ' line 5: a runner-image line outside a [[scaleset]] block')

    def test_an_image_line_in_another_table(self):
        self.refused(config().replace('[tart]\n', '[tart]\nrunner-image = "%s"\n' % IMG),
                     ' line 12: a runner-image line outside a [[scaleset]] block')

    def test_an_image_line_after_a_block_in_another_table(self):
        self.refused(config() + '[docker]\nrunner-image = "%s"\n' % IMG,
                     ' line 48: a runner-image line outside a [[scaleset]] block')

    def test_a_block_with_no_name(self):
        self.refused(config().replace('name = "mac-a"\n', ''), ': a [[scaleset]] block has no name')

    def test_two_blocks_with_one_name(self):
        self.refused(config((('mac-a', IMG), ('mac-a', IMG2))), ": two [[scaleset]] blocks are named 'mac-a'")

    def test_an_image_line_it_cannot_read(self):
        for line in ("runner-image = 'x'", 'runner-image = "a\\"b"', '"runner-image" = "x"', 'runner-image = ""'):
            with self.subTest(line):
                self.refused(config().replace('runner-image = "%s"' % IMG, line),
                             ' line 45: a runner-image line this does not read (a plain "..." string)')


class TestFamilies(unittest.TestCase):
    def refused(self, text, why):
        r = Rig(self, families=text)
        res = r.report(ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE no facts: %s %s' % (r.families, why), res.stdout)

    def test_a_set_in_two_families(self):
        self.refused('fx tart mac-a\nfy tart mac-b mac-a\n', 'line 2: the set mac-a is in two families (fx, fy)')

    def test_a_family_named_twice(self):
        self.refused('fx tart mac-a\nfx tart mac-b\n', 'line 2: the family fx is named twice')

    def test_a_set_named_twice_in_a_family(self):
        self.refused('fx tart mac-a mac-a\n', 'line 1: a set is named twice in the family fx')

    def test_lines_it_does_not_read(self):
        for line in ('fx docker mac-a', 'fx tart', 'fx  tart mac-a', 'fx tart mac-a ', ' fx tart mac-a', 'Fx tart mac-a',
                     'fx tart mac-a; touch /tmp/x', 'fx tart $(id)', 'fx tart mac-a\r', 'fx=1'):
            with self.subTest(line=line):
                self.refused('# ok\nfx tart mac-b\n%s\n' % line, "line 3 is not 'FAMILY tart SET [SET ...]'")

    def test_control_the_valid_file(self):
        r = Rig(self, families='# comment\n\nfx tart mac-a\nfy tart mac-b mac-c\n')
        r.report()
        self.assertEqual(r.facts()['families'], {
            'fx': {'provider': 'tart', 'sets': ['mac-a'], 'candidate': None, 'back_until': None},
            'fy': {'provider': 'tart', 'sets': ['mac-b', 'mac-c'], 'candidate': None, 'back_until': None}})

    def test_no_families_file_is_no_family(self):
        r = Rig(self, families=None)
        res = r.report()
        self.assertEqual(r.facts()['families'], {})
        self.assertIn('runner-updater: families: no families file %s: no family is observed\n' % r.families, res.stdout)


class TestHealthz(unittest.TestCase):
    def test_two_reads(self):
        r = Rig(self)
        res = r.report()
        self.assertEqual(r.healthz(), [HEALTHZ, HEALTHZ])
        self.assertEqual([c[-1] for c in r.curl_calls()], ['http://127.0.0.1:8080/healthz'] * 2)
        self.assertEqual(r.curl_calls()[0], ['-fsS', '--noproxy', '*', '--max-time', '5', 'http://127.0.0.1:8080/healthz'])
        self.assertIn('runner-updater: healthz: 2 of 2 reads (http://127.0.0.1:8080/healthz)\n', res.stdout)

    def test_the_address_and_port_come_from_the_config(self):
        r = Rig(self, cfg=config(top='health-port = 9090\n').replace('health-address = "127.0.0.1"',
                                                                      'health-address = "127.0.0.2"'))
        r.report()
        self.assertEqual([c[-1] for c in r.curl_calls()], ['http://127.0.0.2:9090/healthz'] * 2)

    def test_a_read_that_fails_is_not_added(self):
        r = Rig(self)
        r.set_curl('FAIL', call=1)
        res = r.report()
        self.assertEqual(r.healthz(), [HEALTHZ])
        self.assertIn('runner-updater: healthz: 1 of 2 reads', res.stdout)

    def test_a_read_that_is_not_one_json_object_is_not_added(self):
        for body in ('not json', '[1]', json.dumps(HEALTHZ) + json.dumps(HEALTHZ), ''):
            with self.subTest(body=body):
                r = Rig(self)
                r.set_curl(body, call=2)
                r.report()
                self.assertEqual(r.healthz(), [HEALTHZ])

    def test_no_health_server_is_no_read(self):
        r = Rig(self, cfg=config(top='health-port = 0\n'))
        res = r.report()
        self.assertEqual((r.healthz(), r.curl_calls()), ([], []))
        self.assertIn("runner-updater: healthz: 0 of 2 reads (health-port '0': no health server this reads)", res.stdout)

    def test_the_reads_are_3_s_apart(self):
        r = Rig(self, gap='3')
        r.report()
        with open(os.path.join(r.curld, 'times')) as f:
            t = [float(x) for x in f.read().split()]
        self.assertEqual(len(t), 2)
        self.assertGreaterEqual(t[1] - t[0], 3.0)

    def test_control_the_gap_is_the_constant(self):
        r = Rig(self, gap='0')
        r.report()
        with open(os.path.join(r.curld, 'times')) as f:
            t = [float(x) for x in f.read().split()]
        self.assertLess(t[1] - t[0], 2.0)


JQ_WRAP = '''d=%(d)s
if [[ $1 == --version && -f $d/version ]]; then print -r -- "$(<$d/version)"; exit 0; fi
if [[ -f $d/fail ]]; then
  for a in "$@"; do [[ $a == */$(<$d/fail).jq ]] && { print -u2 -r -- "injected failure"; exit 5 }; done
fi
exec %(jq)s "$@"
'''


def jq_log(r):
    p = r.sb.path('logs', 'jq.log')
    return read_text(p) if os.path.exists(p) else ''


def core_calls(r):
    """the core programs the jq wrapper ran, in order (its log is read raw: a jq program's argument holds newlines)"""
    return re.findall(r"'-f' '%s/(idle|r1|keep|status)\.jq'" % re.escape(os.path.join(REPO, 'core')), jq_log(r))


class TestTestedJq(unittest.TestCase):
    def test_untested_jq_stops_before_any_core_call(self):
        for version in ('jq-1.6', 'jq-1.7.1', 'jq-1.8.0', ''):   # jq-1.6 is a row for the watchdog only
            with self.subTest(version=version):
                r = Rig(self, jq_wrap=True)
                r.sb.write(os.path.join(r.jqd, 'version'), version + '\n')
                res = r.report(ok=False)
                self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
                self.assertEqual(res.stdout, (
                    "runner-updater: STOP untested jq: %s prints '%s', which core/TESTED_JQ does not list for the core; "
                    "no new work starts. Next, in the repository: `JQ=%s python3 -I -m unittest discover -s tests/core "
                    "-t .`, then add its row to core/TESTED_JQ when they pass\n") % (r.jq, version, r.jq))
                self.assertEqual(jq_log(r), "'--version'\n")
                self.assertEqual(r.ps_calls(), 0)

    def test_control_a_tested_jq_runs_the_core(self):
        r = Rig(self, jq_wrap=True)
        r.report()
        self.assertTrue(jq_log(r).startswith("'--version'\n"), jq_log(r)[:200])
        self.assertEqual(core_calls(r), ['idle', 'r1', 'keep', 'status'])


class TestReportPass(unittest.TestCase):
    def test_the_verdict_lines(self):
        r = Rig(self)
        res = r.report()
        heads = [l.split(':')[0] for l in res.stdout.splitlines() if not l.startswith('runner-updater: ')]
        self.assertEqual(heads[:6], ['idle', 'r1', 'r1 fx', 'keep', 'keep fx', 'status'], res.stdout)
        self.assertIn('\nidle: idle (every set of the host is idle on both reads)\n', res.stdout)
        self.assertIn('\nr1 fx: none (no candidate under observation)\n', res.stdout)
        self.assertIn('\nstatus: ok (0 STOPs)\n', res.stdout)
        state = json.loads(r.state_bytes())
        self.assertEqual(state['boundary']['position'], r.facts()['position'])
        self.assertEqual(state['boundary']['owner'], {'pid': P[0], 'start': P[2]})

    def test_a_program_that_fails_writes_no_state(self):
        order = ['idle', 'r1', 'keep', 'status']
        for prog in order:
            with self.subTest(prog=prog):
                r = Rig(self, jq_wrap=True)
                r.report()
                s0 = r.state_bytes()
                r.append_log('2026-11-01 05:00:00 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n')
                r.sb.write(os.path.join(r.jqd, 'fail'), prog)
                open(r.sb.path('logs', 'jq.log'), 'w').close()
                res = r.report(ok=False)
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn('runner-updater: core could not decide (%s): exit 5: injected failure\n' % prog, res.stdout)
                self.assertIn('runner-updater: the pass did nothing: %s/state.json is as it was\n' % r.report_dir,
                              res.stdout)
                self.assertEqual(r.state_bytes(), s0)
                self.assertEqual(core_calls(r), order[:order.index(prog) + 1])

    def test_control_a_pass_that_decides_writes_the_state(self):
        r = Rig(self, jq_wrap=True)
        r.report()
        s0 = r.state_bytes()
        r.append_log('2026-11-01 05:00:00 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n')
        r.report()
        self.assertNotEqual(r.state_bytes(), s0)
        self.assertEqual(json.loads(r.state_bytes())['boundary']['position'], r.facts()['position'])


class TestObserve(unittest.TestCase):
    """--observe FAMILY: the family's current config lines are its candidate (D10's live detection cell)."""

    def two_passes(self, text):
        r = Rig(self)
        r.write_log('')
        t0 = int(time.time())
        res = r.report('--observe', 'fx')
        t1 = int(time.time())
        self.assertIn('runner-updater: observe: fx is observed from now on, on its current lines: mac-a=%s\n' % IMG,
                      res.stdout)
        cand = r.facts()['families']['fx']['candidate']
        self.assertEqual(cand['version'], 'observed')
        self.assertEqual(cand['lines'], {'mac-a': IMG})
        self.assertTrue(t0 <= cand['closed_at'] <= t1)
        self.assertIn('\nr1 fx: none (observing runner observed since ', res.stdout)
        r.append_log(fixture('studio-cut.log') + text)
        res = r.report()
        self.assertEqual(r.facts()['families']['fx']['candidate'], cand)
        self.assertTrue(r.facts()['continuous'])
        return res

    def test_three_counted_failures_on_one_set_roll_back(self):
        res = self.two_passes(fixture('three-failures.log'))
        self.assertIn('\nr1 fx: rollback (R1 on set mac-a: 3 counted failures with no proof of life between them '
                      '(connect-class only))\n', res.stdout)
        self.assertIn('\nfx: R1: a rollback is due (set mac-a, 3 counted failures, connect-class only)\n', res.stdout)

    def test_control_a_proof_of_life_between_them_is_no_rollback(self):
        res = self.two_passes(fixture('three-failures-proof-between.log'))
        self.assertIn('\nr1 fx: none (observing runner observed since ', res.stdout)
        self.assertNotIn('rollback', res.stdout)

    def test_the_record_stays_until_it_is_cleared(self):
        r = Rig(self)
        r.report('--observe', 'fx')
        cand = r.facts()['families']['fx']['candidate']
        res = r.report('--observe', 'fx')
        self.assertIn('runner-updater: observe: fx is observed already', res.stdout)
        self.assertEqual(r.facts()['families']['fx']['candidate'], cand)
        res = r.report('--observe-clear', 'fx')
        self.assertIn('runner-updater: observe: fx is no longer observed\n', res.stdout)
        self.assertIsNone(r.facts()['families']['fx']['candidate'])
        r.report()
        self.assertIsNone(r.facts()['families']['fx']['candidate'])

    def test_a_family_that_is_not_in_the_families_file(self):
        r = Rig(self)
        res = r.report('--observe', 'fz', ok=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn('runner-updater: REFUSE no facts: --observe fz: no family fz in %s\n' % r.families, res.stdout)
        self.assertFalse(os.path.exists(os.path.join(r.report_dir, 'observe.json')))

    def test_a_family_set_with_no_image_line(self):
        r = Rig(self, cfg=config((('mac-a', IMG), ('mac-b', None))), families='fx tart mac-a mac-b\n')
        res = r.report('--observe', 'fx', ok=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn('runner-updater: REFUSE no facts: --observe fx: the set mac-b has no runner-image line in %s\n'
                      % r.config, res.stdout)


class TestNoAction(unittest.TestCase):
    """report takes no action: every action tool is a stub on PATH that logs its calls to logs/actions.log, and kill is
    also a function (it is a zsh builtin), on the pass that finds a rollback due."""

    KILL = ('umask 077\n', 'umask 077\nkill() { print -r -- "kill $*" >> $ACTIONS_LOG }\n')

    def run_rollback(self, r):
        log = r.sb.path('logs', 'actions.log')
        r.write_log('')
        r.report('--observe', 'fx', env={'ACTIONS_LOG': log})
        r.append_log(fixture('three-failures.log'))
        res = r.report(env={'ACTIONS_LOG': log})
        self.assertIn('\nfx: R1: a rollback is due', res.stdout)
        return read_text(log) if os.path.exists(log) else ''

    def test_report_runs_no_action_tool(self):
        r = Rig(self, extra_rewrites=[self.KILL])
        self.assertEqual(self.run_rollback(r), '')

    def test_control_the_harness_sees_each_action(self):
        calls = 'runner-disable; runner-enable; golden-build; golden-gate x; tart list; launchctl list; kill -0 $$\nexit 0\n'
        end = '/bin/mv -f -- $pass/state.json $REPORT/state.json || refuse "cannot write $REPORT/state.json"\nexit 0\n'
        r = Rig(self, extra_rewrites=[self.KILL, (end, end.replace('exit 0\n', calls))])
        got = self.run_rollback(r).splitlines()
        self.assertEqual([l.split()[0] for l in got] if got else [],
                         ['runner-disable', 'runner-enable', 'golden-build', 'golden-gate', 'tart', 'launchctl', 'kill'] * 2)


class TestLock(unittest.TestCase):
    """The updater lock: a second report WAITS for the first (D1: a command waits)."""

    def test_a_second_report_waits_for_the_first(self):
        r = Rig(self)
        r.sb.write(os.path.join(r.curld, 'block'), '')        # the first report holds the lock in its /healthz read
        argv = ['/bin/zsh', '-f', r.script, 'report']
        first = r.sb.start(argv, name='first')
        r.sb.wait_for(lambda: len(r.curl_calls()) == 1, 'the first report in its /healthz read')
        self.assertEqual(r.ps_calls(), 2)
        second = r.sb.start(argv, name='second')
        time.sleep(2)
        self.assertIsNone(second.poll(), r.sb.output('second'))   # it waits
        self.assertEqual(r.ps_calls(), 2)                          # and has measured nothing
        r.sb.write(os.path.join(r.curld, 'go'), '')
        self.assertEqual(first.wait(timeout=60), 0, r.sb.output('first'))
        self.assertEqual(second.wait(timeout=60), 0, r.sb.output('second'))
        self.assertEqual(r.ps_calls(), 4)
        self.assertIn('runner-updater: healthz: 2 of 2 reads', r.sb.output('second')[0])

    def test_control_with_the_lock_free_a_report_runs_at_once(self):
        r = Rig(self)
        p = r.sb.start(['/bin/zsh', '-f', r.script, 'report'], name='alone')
        self.assertEqual(p.wait(timeout=60), 0, r.sb.output('alone'))
        self.assertEqual(r.ps_calls(), 2)


class TestStateDir(unittest.TestCase):
    """A report on a host with no STATEDIR creates it with an EMPTY protected list, so golden-prune (which reads an
    existing STATEDIR as "the updater is here" and then needs the list) prints what it printed before."""

    NAMES = ['liveapp-mac-golden-20261001', 'liveapp-mac-golden-20261001', 'liveapp-mac-golden-20260915',
             'liveapp-mac-golden-20260901', 'liveapp-mac-golden-20260815']

    def prune(self, sb, statedir):
        script = sb.copy_script('bin/golden-prune', [('STATEDIR=/Users/ci/.local/state/runner-updater',
                                                      'STATEDIR=' + statedir)], dest=sb.path('prune', 'golden-prune'))
        return sb.run(['/bin/zsh', '-f', script] + self.NAMES)

    def test_a_new_statedir_has_an_empty_protected_list(self):
        r = Rig(self, statedir=False)
        res = r.report()
        protected = os.path.join(r.statedir, 'protected')
        self.assertIn('runner-updater: created %s, with an empty protected list %s (it protects nothing)\n'
                      % (r.statedir, protected), res.stdout)
        self.assertEqual(os.path.getsize(protected), 0)
        self.assertEqual(os.stat(r.statedir).st_mode & 0o777, 0o700)
        with_it = self.prune(r.sb, r.statedir)
        without = self.prune(r.sb, r.sb.path('no-such-statedir'))
        self.assertEqual((with_it.returncode, with_it.stdout), (0, without.stdout))
        self.assertEqual(without.stdout, 'liveapp-mac-golden-20260815\nliveapp-mac-golden-20260901\n')

    def test_control_a_statedir_without_the_list_makes_golden_prune_refuse(self):
        sb = Sandbox(self)
        d = sb.mkdir('state', 'runner-updater')
        res = self.prune(sb, d)
        self.assertEqual((res.returncode, res.stdout), (1, ''))
        self.assertIn('has no protected list', res.stderr)

    def test_an_existing_statedir_is_not_given_a_list(self):
        r = Rig(self, protected=False)
        r.report()
        self.assertFalse(os.path.exists(os.path.join(r.statedir, 'protected')))


class TestUsage(unittest.TestCase):
    def test_usage(self):
        for args in ([], ['status'], ['report', '--bogus'], ['report', '--observe'], ['report', '--observe', 'Fx'],
                     ['report', '--observe', 'fx', '--observe-clear', 'fx'], ['report', 'fx']):
            with self.subTest(args=args):
                r = Rig(self)
                res = r.sb.run(['/bin/zsh', '-f', r.script] + args)
                self.assertEqual((res.returncode, res.stdout), (2, ''), res.stderr)
                self.assertTrue(res.stderr.startswith('runner-updater: usage: runner-updater report [--observe FAMILY]'),
                                res.stderr)
                self.assertEqual(r.ps_calls(), 0)


if __name__ == '__main__':
    unittest.main()
