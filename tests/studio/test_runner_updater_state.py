"""bin/runner-updater's STATE slice: its own PATH, the config keys that would blind the log pass, the updater's state
(STATEDIR/state.json), `status`, `on` and `off`, the protected-list writer and `protect`, and the timer's `pass`.

The rig is test_runner_updater's (every path constant rewritten into a sandbox; stubs for ps and curl; the real core).
"""
import calendar
import contextlib
import json
import os
import subprocess
import time
import unittest

from tests.studio.test_runner_updater import IMG, IMG2, P, Rig, config, core_calls, fixture, read_text, the_jq

SYSTEM = '/usr/bin:/bin:/usr/sbin:/sbin'
V0, V1, V2 = '2.338.2', '2.338.9', '2.339.0'
SHA1, SHA2 = '1' * 64, '2' * 64
T0 = calendar.timegm((2026, 11, 1, 8, 0, 0, 0, 0, 0))
IMG0 = 'liveapp-mac-golden-20260915'


def lines_of(path):
    with open(path) as f:
        return f.read().splitlines()


def fam(**kw):
    """one family of the updater's state, every member present"""
    f = {'candidate': None, 'previous': None, 'back_until': None, 'rejected': [], 'recipe': None, 'stops': []}
    f.update(kw)
    return f


def cand(version=V2, lines=None, closed_at=T0):
    return {'version': version, 'lines': lines or {'mac-a': IMG2}, 'closed_at': closed_at}


def stop(family, name, version=V2, user=None, detail=None):
    return {'family': family, 'stop': name, 'version': version, 'user': user, 'detail': detail}


def state(on=False, families=None, images=None, **extra):
    s = {'format': 1, 'on': on, 'families': families or {}, 'images': images or {}}
    s.update(extra)
    return s


# a window's own restart of runscaler, kept for the next pass (bin/runner-updater-window; the pass passes it as
# facts.restart once, then clears it)
RESTART = {'from': {'pid': P[0], 'start': P[2]}, 'to': {'pid': 5151, 'start': P[2] + 600},
           'stopped': {'inode': '123', 'offset': 45, 'sha': 'b' * 64}}
# every member the state holds (a member this release does not read makes every command WAIT: TestUnknownMembers)
FULL = state(on=False, families={
    'fx': fam(candidate=cand(), previous={'mac-a': IMG}, rejected=[V1], recipe='a' * 64,
              stops=[stop('fx', 'NO EVIDENCE', detail={'text': 'no job completed in 72 h'})]),
    'fy': fam(previous={'mac-c': IMG0}, back_until=T0 + 7 * 86400)},
    images={IMG2: V2, IMG: V0}, core={'format': 1, 'not_ready_since': {}}, restart=RESTART)


class Paths:
    """the updater's own files in a rig"""

    def __init__(self, r):
        self.r = r
        self.state = os.path.join(r.statedir, 'state.json')
        self.pindir = os.path.join(r.statedir, 'pin')
        self.window = os.path.join(r.statedir, 'window')
        self.actions = os.path.join(r.statedir, 'actions')
        self.protected = os.path.join(r.statedir, 'protected')
        self.passdir = os.path.join(r.statedir, 'pass')

    def put(self, s, raw=None):
        """the state file: S as JSON (or RAW text); -> its bytes"""
        text = raw if raw is not None else json.dumps(s, indent=2) + '\n'
        self.r.sb.write(self.state, text, 0o600)
        return text.encode()

    def put_by_rename(self, s):
        tmp = self.state + '.test'
        self.r.sb.write(tmp, json.dumps(s, indent=2) + '\n', 0o600)
        os.rename(tmp, self.state)

    def get(self):
        with open(self.state) as f:
            return json.load(f)

    def raw(self, path=None):
        path = path or self.state
        if not os.path.lexists(path):
            return None
        with open(path, 'rb') as f:
            return f.read()

    def pins(self, **pins):
        """PINDIR/NAME = TEXT for each NAME=TEXT; -> {name: text} as written"""
        os.makedirs(self.pindir, exist_ok=True)
        for name, text in pins.items():
            self.r.sb.write(os.path.join(self.pindir, name.replace('_', '-')), text, 0o600)
        return self.pin_files()

    def pin_files(self):
        if not os.path.isdir(self.pindir):
            return None
        return {n: read_text(os.path.join(self.pindir, n)) for n in sorted(os.listdir(self.pindir))}


def pair(r, name, lib_rewrites=(), script_rewrites=(), journal_body=None):
    """a release bin/ of its own, sandbox/NAME/: runner-updater (the rig's rewrites), runner-updater-lib (with
    LIB_REWRITES), the rig's runner-updater-window, runner-updater-release and tls-excluded-lib, and runner-journal
    (the real one, or a stub with JOURNAL_BODY); -> the script's path"""
    d = r.sb.mkdir(name)
    r.sb.copy_script('bin/runner-updater-lib', list(lib_rewrites), dest=os.path.join(d, 'runner-updater-lib'))
    for f in ('tls-excluded-lib', 'runner-updater-release', 'runner-updater-window'):   # the pass's files, as the rig has them
        r.sb.write(os.path.join(d, f), read_text(r.sb.path('tools', f)))
    if journal_body is None:
        r.sb.copy_script('bin/runner-journal', [], dest=os.path.join(d, 'runner-journal'))
    else:
        r.sb.stub('runner-journal', journal_body, folder=d)
    return r.sb.copy_script('bin/runner-updater', r.rewrites + list(script_rewrites), dest=os.path.join(d, 'runner-updater'))


def lock_holders(r):
    out = subprocess.run(['/usr/sbin/lsof', '-t', '--', os.path.join(r.statedir, 'lock')],
                         capture_output=True, text=True).stdout
    return [int(x) for x in out.split()]


def hold_lock(r):
    """a report that holds the updater lock in its /healthz read until release(r, holder)"""
    r.sb.write(os.path.join(r.curld, 'block'), '')
    p = r.sb.start(['/bin/zsh', '-f', r.script, 'report'], name='holder')
    r.sb.wait_for(lambda: p.poll() is not None or len(r.curl_calls()) == 1, 'the holder in its /healthz read')
    r.test.assertIsNone(p.poll(), r.sb.output('holder'))
    return p


def release(r, holder):
    r.sb.write(os.path.join(r.curld, 'go'), '')
    r.test.assertEqual(holder.wait(timeout=60), 0, r.sb.output('holder'))


class TestOwnPath(unittest.TestCase):
    """runner-updater sets its own PATH at the top: the weekly watchdog runs it over a non-interactive ssh with a PATH
    of its own, so nothing may depend on the caller's. The ps stub logs the PATH it is run with."""

    def test_report_works_with_a_path_that_holds_nothing(self):
        r = Rig(self)
        r.report(env={'PATH': '/nonexistent'})
        self.assertEqual(set(lines_of(os.path.join(r.psd, 'path'))), {r.sb.stubs + ':' + SYSTEM})

    def test_status_and_pass_work_with_a_path_that_holds_nothing(self):
        r = Rig(self, jq_wrap=True)
        Paths(r).put(on_state())
        for c in ('status', 'pass'):
            r.cmd(c, env={'PATH': '/nonexistent'})
        self.assertEqual(set(lines_of(os.path.join(r.jqd, 'path'))), {r.sb.stubs + ':' + SYSTEM})
        self.assertEqual(set(lines_of(os.path.join(r.psd, 'path'))), {r.sb.stubs + ':' + SYSTEM})

    def test_control_a_copy_that_sets_no_path_shows_the_callers(self):
        r = Rig(self)
        own = 'export PATH=%s:%s' % (r.sb.stubs, SYSTEM)
        script = r.copy('runner-updater-nopath', [(own, ': ' + own)])
        r.cmd('report', script=script, env={'PATH': '/nonexistent'})
        self.assertEqual(set(lines_of(os.path.join(r.psd, 'path'))), {'/nonexistent'})


WAIT = 'runner-updater: WAIT the state %s has format %s; this updater reads format 1: it waits and changes nothing\n'
OFF_LINE = 'runner-updater: status: the updater is OFF\n'
ON_LINE = 'runner-updater: status: the updater is ON\n'
# a folder on the path to STATEDIR's files that exists but cannot be searched (D: that folder; S: STATEDIR; C: the
# command)
CLOSED = ('runner-updater: REFUSE %(d)s cannot be searched, so the files in %(s)s would look absent (a state as a fresh '
          'one: OFF). Look at its mode (ci must be able to search it), then run %(c)s again\n')
PIN_CLOSED = ('runner-updater: STOP %s cannot be read and searched: off removes the pins in it, and would not see them. '
              'The updater is OFF; the pins stay. Look at its mode (ci must be able to read and search it), then run '
              'off again\n')


def lib_run(r, body):
    """BODY in a zsh that sourced the REAL runner-updater-lib (the rig's copy, beside the script), with JQ the rig's
    jq: -> the finished process"""
    driver = r.sb.write(r.sb.path('driver', 'drive'), 'set -u\nexport LC_ALL=C TZ=UTC\numask 077\nJQ=%s\nDD=/bin/dd\n'
                        'source %s || exit 9\n%s\n' % (r.jq, r.lib, body), 0o755)
    return r.sb.run(['/bin/zsh', '-f', driver])


@contextlib.contextmanager
def closed(d, mode):
    """D's mode is MODE until the with block ends (then 0700 again, also when the block fails)"""
    os.chmod(d, mode)
    try:
        yield
    finally:
        os.chmod(d, 0o700)


class TestState(unittest.TestCase):
    """The updater's state, STATEDIR/state.json: JSON with format 1, written by rename, read under the lock (status
    alone reads it without the lock, ONCE). A missing file is a fresh install: OFF, no family, nothing held."""

    def test_fresh_is_off_and_status_writes_nothing(self):
        for statedir in (True, False):
            with self.subTest(statedir=statedir):
                r = Rig(self, statedir=statedir)
                u = Paths(r)
                res = r.cmd('status')
                self.assertIn(OFF_LINE, res.stdout)
                self.assertIn('runner-updater: status: no family in the state\n', res.stdout)
                self.assertIn('\nstatus: ok (0 STOPs)\n', res.stdout)
                self.assertIsNone(u.raw())
                if not statedir:
                    self.assertFalse(os.path.lexists(r.statedir))

    def test_round_trip_keeps_every_member(self):
        r = Rig(self)
        u = Paths(r)
        u.put(FULL)
        r.cmd('on')
        self.assertEqual(u.get(), dict(FULL, on=True))
        self.assertEqual(os.stat(u.state).st_mode & 0o777, 0o600)
        r.cmd('off')
        self.assertEqual(u.get(), dict(FULL, on=False))
        self.assertFalse(os.path.lexists(u.state + '.new'))

    def test_an_unknown_format_waits_and_leaves_the_file_byte_equal(self):
        for fmt, shown in ((2, '2'), ('1', '"1"'), (None, 'null'), (0, '0')):
            for cmd in ('status', 'on', 'off'):
                with self.subTest(format=fmt, cmd=cmd):
                    r = Rig(self)
                    u = Paths(r)
                    s = dict(FULL, on=True)
                    if fmt is None:
                        del s['format']
                    else:
                        s['format'] = fmt
                    raw = u.put(s)
                    pins = u.pins(mac_golden='%s %s\n' % (V2, SHA2))
                    res = r.cmd(cmd, ok=False)
                    self.assertEqual((res.returncode, res.stdout), (4, WAIT % (u.state, shown)), res.stderr)
                    self.assertEqual(u.raw(), raw)
                    self.assertEqual(u.pin_files(), pins)
                    self.assertIsNone(u.raw(u.actions))
        # the control: format 1
        r = Rig(self)
        u = Paths(r)
        raw = u.put(FULL)
        r.cmd('on')
        self.assertNotEqual(u.raw(), raw)

    BAD = {'not JSON': 'not json\n', 'two objects': '{"format":1}\n{"format":1}\n', 'an array': '[{"format":1}]\n',
           'empty': '',
           'on is not true or false': dict(FULL, on='yes'),
           'no families': {k: v for k, v in FULL.items() if k != 'families'},
           'a family name it does not read': dict(FULL, families={'Fx': fam()}),
           'a candidate with no lines': dict(FULL, families={'fx': fam(candidate=cand(lines={'mac-a': IMG2}) | {'lines': {}})}),
           'a candidate version it does not read': dict(FULL, families={'fx': fam(candidate=cand(version='v2'))}),
           'an image name it does not read': dict(FULL, families={'fx': fam(candidate=cand(lines={'mac-a': 'a b'}))}),
           'a closed_at that is not epoch seconds': dict(FULL, families={'fx': fam(candidate=cand(closed_at='today'))}),
           'a back_until that is not epoch seconds': dict(FULL, families={'fx': fam(back_until=1.5)}),
           'a rejected version that is not one': dict(FULL, families={'fx': fam(rejected=['x'])}),
           'a recipe that is not a sha256': dict(FULL, families={'fx': fam(recipe='abc')}),
           'a stop of another family': dict(FULL, families={'fx': fam(stops=[stop('fy', 'NO EVIDENCE')])}),
           'a stop with no name': dict(FULL, families={'fx': fam(stops=[stop('fx', '')])}),
           'an image record of a name it does not read': dict(FULL, images={'a/b': V2}),
           'a core that is not an object': dict(FULL, core=[1]),
           'a restart with no stopped': dict(FULL, restart={k: v for k, v in RESTART.items() if k != 'stopped'}),
           'a restart whose process has no pid': dict(FULL, restart=dict(RESTART, to={'start': 1})),
           'a restart whose inode is a number': dict(FULL, restart=dict(RESTART, stopped=dict(RESTART['stopped'], inode=123))),
           'a restart whose sha is not one': dict(FULL, restart=dict(RESTART, stopped=dict(RESTART['stopped'], sha='x')))}

    def test_a_state_it_cannot_read_is_refused_and_left_as_it_is(self):
        for why, s in self.BAD.items():
            for cmd in ('status', 'on'):
                with self.subTest(why=why, cmd=cmd):
                    r = Rig(self)
                    u = Paths(r)
                    raw = u.put(None, raw=s) if isinstance(s, str) else u.put(s)
                    res = r.cmd(cmd, ok=False)
                    self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
                    self.assertTrue(res.stdout.startswith('runner-updater: REFUSE %s ' % u.state), res.stdout)
                    self.assertTrue(res.stdout.endswith(': it is left as it is\n'), res.stdout)
                    self.assertEqual(u.raw(), raw)

    def test_a_state_folder_it_cannot_search_is_refused_never_read_as_fresh(self):
        # behind a folder it cannot search, the state would look absent, which reads as OFF (every level and every
        # command: TestClosedFolders)
        for mode in (0o000, 0o600):
            with self.subTest(mode=oct(mode)):
                r = Rig(self)
                u = Paths(r)
                u.put(dict(FULL, on=True))
                os.chmod(r.statedir, mode)
                res = r.cmd('status', ok=False)
                os.chmod(r.statedir, 0o700)
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertEqual(res.stdout, CLOSED % {'d': r.statedir, 's': r.statedir, 'c': 'status'})
                self.assertIn(ON_LINE, r.cmd('status').stdout)    # the control: the same state, the folder 0700

    RENAME = '/bin/mv -f -- $f.new $f ||'   # ru_write's rename (bin/runner-updater-lib)

    def torn(self, before_rename):
        r = Rig(self)
        u = Paths(r)
        raw = u.put(FULL)
        script = pair(r, 'torn', lib_rewrites=[(self.RENAME, before_rename + self.RENAME)])
        return r, u, raw, r.cmd('on', script=script, ok=False)

    def test_a_kill_between_the_write_and_the_rename_leaves_the_old_file(self):
        r, u, raw, res = self.torn('kill -9 $$; ')
        self.assertEqual(res.returncode, -9, res.stdout + res.stderr)
        self.assertEqual(u.raw(), raw)
        with open(u.state + '.new') as f:            # the write happened: the new state, never renamed
            self.assertEqual(json.load(f), dict(FULL, on=True))
        res = r.cmd('status')
        self.assertIn(OFF_LINE, res.stdout)
        r.cmd('on')                                   # the next run writes over the left .new
        self.assertEqual(u.get(), dict(FULL, on=True))

    def test_control_the_same_copy_with_no_kill_renames(self):
        r, u, raw, res = self.torn(': ; ')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(u.get(), dict(FULL, on=True))


COMMANDS = ('status', 'on', 'off', 'pass', 'protect', 'report')
WAIT_MEMBERS = ('runner-updater: WAIT the state %s holds members this release does not read (%s): a later release wrote '
                'them, and they may name an image to keep or hold a STOP; it waits and changes nothing\n')


class TestUnknownMembers(unittest.TestCase):
    """A member of a format-1 state that this release does not read: a later release may use it to name an image the
    protected list must keep, or to hold a STOP. This release would drop it from the list or from status, so every
    command that reads the state WAITs (exit 4) and names the members; the state, the protected list and the pins stay
    byte-equal, and no core program runs. The control: the same state with only the members it reads."""

    HOSTWIDE = {'family': None, 'stop': 'CI DISABLED', 'version': None, 'user': None, 'detail': None}

    def cases(self):
        def with_(fn, shown):
            s = on_state()
            fn(s, s['families']['fx'])
            return s, shown
        return {
            'a per-family checked member': with_(lambda s, fx: fx.update(checked={'mac-a': IMG3}), 'families.fx.checked'),
            'a top-level stops member': with_(lambda s, fx: s.update(stops=[self.HOSTWIDE]), 'stops'),
            'an unknown per-family key': with_(lambda s, fx: fx.update(zz=1), 'families.fx.zz'),
            'an unknown top-level key': with_(lambda s, fx: s.update(later={'kept': [1, 2]}), 'later'),
            'a candidate member': with_(lambda s, fx: fx['candidate'].update(checked=True), 'families.fx.candidate.checked'),
            'a member of a STOP': with_(lambda s, fx: fx.update(stops=[dict(stop('fx', 'NO EVIDENCE'), scope='host')]),
                                        'families.fx.stops[0].scope'),
            'a name with a newline': with_(lambda s, fx: s.update({'a\nb': 1}), '"a\\nb"'),
            'two at once': with_(lambda s, fx: (s.update(stops=[self.HOSTWIDE]), fx.update(checked={'mac-a': IMG3})),
                                 'stops, families.fx.checked'),
            'a member of the restart': with_(lambda s, fx: s.update(restart=dict(RESTART, later=1)), 'restart.later'),
            'a member of a restart read': with_(lambda s, fx: s.update(restart=dict(RESTART, to=dict(RESTART['to'], uid=5))),
                                                'restart.to.uid'),
            'a member of the restart position': with_(
                lambda s, fx: s.update(restart=dict(RESTART, stopped=dict(RESTART['stopped'], file='runner.log'))),
                'restart.stopped.file'),
        }

    def test_every_command_that_reads_the_state_waits(self):
        for why, (s, shown) in self.cases().items():
            for cmd in ('status', 'on', 'off', 'pass', 'protect'):
                with self.subTest(why=why, cmd=cmd):
                    r = Rig(self, jq_wrap=True)
                    u = Paths(r)
                    raw = u.put(s)
                    r.sb.write(u.protected, IMG3 + '\n', 0o600)
                    pins = u.pins(mac_golden='%s %s\n' % (V2, SHA2))
                    res = r.cmd(cmd, ok=False)
                    self.assertEqual((res.returncode, res.stdout), (4, WAIT_MEMBERS % (u.state, shown)), res.stderr)
                    self.assertEqual(u.raw(), raw)
                    self.assertEqual(read_text(u.protected), IMG3 + '\n')
                    self.assertEqual(u.pin_files(), pins)
                    self.assertIsNone(u.raw(u.actions))
                    self.assertEqual((core_calls(r), r.ps_calls()), ([], 0))

    def test_control_the_members_it_reads(self):
        for cmd in ('status', 'on', 'off', 'pass', 'protect'):
            with self.subTest(cmd=cmd):
                r = Rig(self, jq_wrap=True)
                u = Paths(r)
                s = on_state(restart=RESTART)
                s['families']['fx']['stops'] = [stop('fx', 'NO EVIDENCE')]
                u.put(s)
                r.sb.write(u.protected, IMG3 + '\n', 0o600)
                res = r.cmd(cmd)
                self.assertNotIn('WAIT', res.stdout)
                if cmd in ('pass', 'protect'):
                    self.assertEqual(lines_of(u.protected), [IMG0, IMG])
                if cmd == 'status':
                    self.assertIn(ON_LINE, res.stdout)
                    self.assertIn('\nstatus: ok (1 STOPs)\n', res.stdout)



class TestClosedFolders(unittest.TestCase):
    """ONE rule for every folder on the path to a file the updater reads (bin/runner-updater-lib, ru_reach): a folder
    that exists but cannot be searched hides what is behind it (a stat there fails as if nothing were there), so a
    state would read as fresh (OFF), the protected list as missing, a pin as absent. Every command refuses before it
    reads or writes anything when STATEDIR's parent or STATEDIR is 0000 or 0600 (no search right). off also lists
    PINDIR, so a PINDIR it cannot read and search is a STOP that leaves every pin. The controls: the same folders at
    0700."""

    LIST = IMG0 + '\n' + IMG + '\n'

    def run_closed(self, level, mode, cmd):
        r = Rig(self)
        u = Paths(r)
        raw = u.put(on_state())
        r.sb.write(u.protected, self.LIST, 0o600)
        d = r.statedir if level == 'STATEDIR' else os.path.dirname(r.statedir)
        with closed(d, mode):
            res = r.cmd(cmd, ok=False)
        return r, u, raw, d, res

    def test_every_command_refuses_a_folder_it_cannot_search_on_the_path_to_the_state(self):
        for level in ('the parent of STATEDIR', 'STATEDIR'):
            for mode in (0o000, 0o600):
                for cmd in COMMANDS:
                    with self.subTest(level=level, mode=oct(mode), cmd=cmd):
                        r, u, raw, d, res = self.run_closed(level, mode, cmd)
                        self.assertEqual((res.returncode, res.stdout), (1, CLOSED % {'d': d, 's': r.statedir, 'c': cmd}),
                                         res.stderr)
                        self.assertEqual(u.raw(), raw)
                        self.assertEqual(read_text(u.protected), self.LIST)
                        self.assertEqual(sorted(os.listdir(r.statedir)), ['protected', 'state.json'])
                        self.assertEqual(r.ps_calls(), 0)

    def test_control_the_same_folders_at_0700(self):
        for level in ('the parent of STATEDIR', 'STATEDIR'):
            for cmd in COMMANDS:
                with self.subTest(level=level, cmd=cmd):
                    r, u, raw, d, res = self.run_closed(level, 0o700, cmd)
                    self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
                    if cmd == 'status':
                        self.assertIn(ON_LINE, res.stdout)

    def test_off_stops_at_a_pin_folder_it_cannot_read_and_search_and_every_pin_stays(self):
        for mode in (0o000, 0o600, 0o300, 0o100):
            with self.subTest(mode=oct(mode)):
                r = Rig(self)
                u = Paths(r)
                u.put(on_state())
                pins = u.pins(**OFF_PINS)
                with closed(u.pindir, mode):
                    res = r.cmd('off', ok=False)
                self.assertEqual((res.returncode, res.stdout),
                                 (1, 'runner-updater: off: the updater is OFF\n' + PIN_CLOSED % u.pindir), res.stderr)
                self.assertEqual(u.pin_files(), pins)
                self.assertIsNone(u.raw(u.actions))
                self.assertFalse(u.get()['on'])
        # the control: the same pins, PINDIR 0700
        r = Rig(self)
        u = Paths(r)
        u.put(on_state())
        u.pins(**OFF_PINS)
        with closed(u.pindir, 0o700):
            r.cmd('off')
        self.assertEqual(u.pin_files(), {})
        self.assertEqual(lines_of(u.actions), OFF_JOURNAL)

    def test_a_families_file_behind_a_folder_it_cannot_search_is_no_facts(self):
        # report and pass read the families file (bin/runner-updater-lib, ru_families): "no file" is "no family"
        for cmd in ('report', 'pass'):
            for mode in (0o000, 0o600, 0o700):
                with self.subTest(cmd=cmd, mode=oct(mode)):
                    r = Rig(self)
                    Paths(r).put(on_state())
                    d = r.sb.mkdir('updater-config')
                    fams = r.sb.write(os.path.join(d, 'families'), 'fx tart mac-a\n')
                    script = pair(r, 'deep-families', script_rewrites=[('FAMILIES=' + r.families, 'FAMILIES=' + fams)])
                    with closed(d, mode):
                        res = r.cmd(cmd, script=script, ok=False)
                    if mode == 0o700:   # the control
                        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
                        self.assertIn('\nr1 fx: ', res.stdout)
                    else:
                        self.assertEqual(res.returncode, 1, res.stdout)
                        self.assertIn('runner-updater: REFUSE no facts: %s cannot be searched: the families file %s '
                                      'would look absent\n' % (d, fams), res.stdout)


class TestClosedFoldersInTheLib(unittest.TestCase):
    """The lib's own readers keep the rule whoever calls them (bin/runner-updater checks STATEDIR's path first, so
    these cells call the REAL lib directly): ru_state_load (the state), ru_protect (an open window's journal) and
    ru_observe (report's observe file). Each injection has its control: the same folder at 0700."""

    def test_ru_state_load(self):
        for mode in (0o000, 0o600, 0o700):
            with self.subTest(mode=oct(mode)):
                r = Rig(self)
                u = Paths(r)
                u.put(on_state())
                parent = os.path.dirname(r.statedir)
                with closed(parent, mode):
                    res = lib_run(r, 'ru_state_load %s; print -rl -- "rc=$?" "${REPLY-}" "${ru_state-}"' % u.state)
                out = res.stdout.splitlines()
                if mode == 0o700:
                    self.assertEqual(out[0], 'rc=0', res.stdout + res.stderr)
                    self.assertTrue(json.loads(out[2])['on'])
                else:
                    self.assertEqual(out[:2], ['rc=1', '%s cannot be searched: a state behind it would look absent'
                                               % parent], res.stdout + res.stderr)

    def test_ru_protect(self):
        for mode in (0o000, 0o600, 0o700):
            with self.subTest(mode=oct(mode)):
                r = Rig(self)
                d = r.sb.mkdir('windows')
                window = r.sb.write(os.path.join(d, 'window'), 'family fx\nimage %s\n' % IMG3, 0o600)
                lst = r.sb.write(r.sb.path('lists', 'protected'), IMG + '\n', 0o600)
                with closed(d, mode):
                    res = lib_run(r, 'PROTECTED=%s WINDOW=%s\nru_protect \'%s\' 0; print -rl -- "rc=$?" "${REPLY-}"'
                                  % (lst, window, json.dumps(state())))
                out = res.stdout.splitlines()
                if mode == 0o700:
                    self.assertEqual(out[0], 'rc=0', res.stdout + res.stderr)
                    self.assertEqual(read_text(lst), IMG3 + '\n')
                else:
                    self.assertEqual(out, ['rc=1', '%s cannot be searched: an open window\'s journal %s would look '
                                                   'absent' % (d, window)], res.stderr)
                    self.assertEqual(read_text(lst), IMG + '\n')

    def test_ru_observe(self):
        for mode in (0o000, 0o600, 0o700):
            with self.subTest(mode=oct(mode)):
                r = Rig(self)
                d = r.sb.mkdir('observed')
                obs = {'fx': {'version': 'observed', 'closed_at': T0, 'lines': {'mac-a': IMG}}}
                f = r.sb.write(os.path.join(d, 'observe.json'), json.dumps(obs), 0o600)
                with closed(d, mode):
                    res = lib_run(r, 'ru_observe_add=() ru_observe_clear=()\nru_observe %s %d; '
                                     'print -rl -- "rc=$?" "${REPLY-}" "${ru_observed-}"' % (f, T0))
                out = res.stdout.splitlines()
                if mode == 0o700:
                    self.assertEqual(out[0], 'rc=0', res.stdout + res.stderr)
                    self.assertEqual(json.loads(out[2]), obs)
                else:
                    self.assertEqual(out[:2], ['rc=1', '%s cannot be searched: the observe file %s would look absent'
                                               % (d, f)], res.stdout + res.stderr)


class TestStatus(unittest.TestCase):
    """status: no lock; it reads the state once, builds facts from it (its candidates, back_until and STOPs), calls
    status.jq, and prints ON or OFF, each family, status.jq's lines, and each STOP's D7 properties."""

    def status(self, s):
        r = Rig(self)
        Paths(r).put(s)
        return r.cmd('status').stdout

    def test_each_family_its_candidate_back_until_and_rejected(self):
        out = self.status(FULL)
        self.assertIn(OFF_LINE, out)
        self.assertIn('runner-updater: family fx: candidate runner %s (mac-a=%s), switched 2026-11-01 08:00 UTC; back: '
                      'none; rejected: %s\n' % (V2, IMG2, V1), out)
        self.assertIn('runner-updater: family fy: no candidate; back until 2026-11-08 08:00 UTC; rejected: none\n', out)
        self.assertIn('\nstatus: ok (1 STOPs)\n', out)
        self.assertIn('\nfx: STOP NO EVIDENCE (runner %s): no job completed in 72 h. Next: `runner-updater retry fx`\n'
                      % V2, out)
        self.assertIn('\nfy: `runner-updater back fy` restores the previous image until 2026-11-08 08:00 UTC\n', out)

    def test_a_held_stop_prints_its_d7_line(self):
        s = state(families={'fx': fam(candidate=cand(), stops=[stop(
            'fx', 'ROLLED BACK', detail={'failures': [{'x': 'set mac-a: the VM did not start'}], 'connect_only': False})])})
        out = self.status(s)
        self.assertIn('\nfx: STOP ROLLED BACK (runner %s): 1 counted failure, the last: set mac-a: the VM did not start. '
                      'Next: `runner-updater retry fx`\n' % V2, out)
        self.assertIn('\nrunner-updater: STOP fx ROLLED BACK: known true; candidate closed: yes; version rejected: yes; '
                      'a newer release proceeds alone: yes\n', out)

    def test_an_unknown_stop_prints_known_false_never_guessed(self):
        out = self.status(state(families={'fx': fam(candidate=cand(), stops=[stop('fx', 'BOGUS')])}))
        self.assertIn('\nfx: STOP BOGUS (runner %s): this core does not know this STOP\n' % V2, out)
        self.assertIn('\nrunner-updater: STOP fx BOGUS: known false; candidate closed: unknown; version rejected: '
                      'unknown; a newer release proceeds alone: no\n', out)

    # macOS's sandbox: every file write denied but /dev/null (a pipe or a process substitution writes no file)
    NO_WRITE = '(version 1)(allow default)(deny file-write*)(allow file-write* (literal "/dev/null"))'

    def under_no_write(self, r, c):
        return r.sb.run(['/usr/bin/sandbox-exec', '-p', self.NO_WRITE, '/bin/zsh', '-f', r.script, c])

    def test_status_writes_no_file_anywhere(self):
        # the slice writes only under STATEDIR, and status writes nothing at all: not even a temporary file (macOS's
        # mktemp -d writes in the user's own temporary folder, whatever TMPDIR says)
        r = Rig(self)
        u = Paths(r)
        u.put(FULL)
        res = self.under_no_write(r, 'status')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('\nfx: STOP NO EVIDENCE (runner %s)' % V2, res.stdout)
        self.assertIn('\nrunner-updater: STOP fx NO EVIDENCE: known true;', res.stdout)

    def test_control_the_sandbox_stops_a_command_that_writes(self):
        r = Rig(self)
        u = Paths(r)
        raw = u.put(FULL)
        res = self.under_no_write(r, 'on')
        self.assertNotEqual(res.returncode, 0, res.stdout)
        self.assertEqual(u.raw(), raw)

    def test_a_core_that_cannot_decide_is_a_stop(self):
        r = Rig(self, jq_wrap=True)
        Paths(r).put(FULL)
        r.sb.write(os.path.join(r.jqd, 'fail'), 'status')
        res = r.cmd('status', ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertTrue(res.stdout.endswith('runner-updater: STOP core could not decide (status): exit 5: injected '
                                            'failure\n'), res.stdout)
        os.remove(os.path.join(r.jqd, 'fail'))       # the control
        self.assertIn('\nstatus: ok (1 STOPs)\n', r.cmd('status').stdout)

    def test_untested_jq_stops_status_before_any_core_call(self):
        # status runs status.jq, so it checks the jq as report does (review r1 P3-2: no cell held this check)
        r = Rig(self, jq_wrap=True)
        Paths(r).put(dict(FULL, on=True))
        r.sb.write(os.path.join(r.jqd, 'version'), 'jq-1.6\n')
        res = r.cmd('status', ok=False)
        self.assertEqual((res.returncode, res.stdout), (3, (
            "runner-updater: STOP untested jq: %s prints 'jq-1.6', which core/TESTED_JQ does not list for the core; no "
            "new work starts. Next, in the repository: `JQ=%s python3 -I -m unittest discover -s tests/core -t .`, then "
            "add its row to core/TESTED_JQ when they pass\n") % (r.jq, r.jq)), res.stderr)
        self.assertEqual(core_calls(r), [])
        os.remove(os.path.join(r.jqd, 'version'))   # the control: the tested jq
        res = r.cmd('status')
        self.assertIn(ON_LINE, res.stdout)
        self.assertEqual(core_calls(r), ['status'])

    def test_status_takes_no_lock(self):
        r = Rig(self)
        Paths(r).put(dict(FULL, on=True))
        holder = hold_lock(r)
        res = r.cmd('status')
        self.assertIn(ON_LINE, res.stdout)
        self.assertIsNone(holder.poll())
        release(r, holder)

    READ = 'load_state   # ONE read of the renamed file'
    PAUSE = '; : > %(d)s/paused; until [[ -e %(d)s/go ]]; do /bin/sleep 0.05; done'

    def test_a_state_renamed_in_while_status_runs_is_not_mixed_in(self):
        # status pauses right after its read; a pass renames a new state in; what status prints is the old state only
        r = Rig(self)
        u = Paths(r)
        u.put(FULL)
        d = r.sb.mkdir('pause')
        script = r.copy('runner-updater-pause', [(self.READ, 'load_state' + self.PAUSE % {'d': d} + '   # ONE read')])
        p = r.sb.start(['/bin/zsh', '-f', script, 'status'], name='st')
        r.sb.wait_for(lambda: p.poll() is not None or os.path.exists(os.path.join(d, 'paused')), 'status after its read')
        new = state(on=True, families={'fz': fam(candidate=cand(version=V1)), 'fy': fam(rejected=[V0])})
        u.put_by_rename(new)
        r.sb.write(os.path.join(d, 'go'), '')
        self.assertEqual(p.wait(timeout=60), 0, r.sb.output('st'))
        out = r.sb.output('st')[0]
        self.assertIn(OFF_LINE, out)
        self.assertIn('runner-updater: family fx: candidate runner %s' % V2, out)
        self.assertIn('runner-updater: family fy: no candidate; back until 2026-11-08 08:00 UTC; rejected: none\n', out)
        self.assertIn('fx: STOP NO EVIDENCE', out)
        self.assertNotIn('fz', out)
        # the control: a status after the rename prints the new state
        out = r.cmd('status').stdout
        self.assertIn(ON_LINE, out)
        self.assertIn('runner-updater: family fz: candidate runner %s' % V1, out)
        self.assertIn('runner-updater: family fy: no candidate; back: none; rejected: %s\n' % V0, out)


OFF_PINS = dict(mac_golden='%s %s\n' % (V2, SHA2), linux_tart='%s %s\n' % (V1, SHA1), junk='not a pin\n')
OFF_JOURNAL = ['pin-remove junk (not one line VERSION SHA256)', 'pin-remove linux-tart %s %s' % (V1, SHA1),
               'pin-remove mac-golden %s %s' % (V2, SHA2)]


class TestOnOff(unittest.TestCase):
    """on and off (D11), under the lock. off sets OFF, then removes every pin of PINDIR, each journaled first through
    runner-journal into the action journal STATEDIR/actions; it refuses while a window journal is open."""

    def test_on_then_status_says_on(self):
        r = Rig(self)
        u = Paths(r)
        res = r.cmd('on')
        self.assertIn('runner-updater: on: the updater is ON\n', res.stdout)
        self.assertEqual(u.get(), state(on=True))
        self.assertIn(ON_LINE, r.cmd('status').stdout)

    def test_off_removes_every_pin_and_journals_each_removal_first(self):
        r = Rig(self)
        u = Paths(r)
        u.put(dict(FULL, on=True))
        u.pins(**OFF_PINS)
        seen = r.sb.path('logs', 'journal-saw')
        # a journal that notes whether the pin is still there when it is called, then runs the real one
        body = ('[[ -e %s/${${3}%%%% *} ]] && print present >> %s || print absent >> %s\nexec /bin/zsh -f %s "$@"'
                % (u.pindir, seen, seen, r.journal))
        res = r.cmd('off', script=pair(r, 'witness', journal_body=body))
        self.assertIn('runner-updater: off: the updater is OFF\n', res.stdout)
        self.assertEqual(u.pin_files(), {})
        self.assertEqual(lines_of(u.actions), OFF_JOURNAL)
        self.assertEqual(lines_of(seen), ['present'] * 3)
        self.assertEqual(u.get(), dict(FULL, on=False))
        for n in ('junk', 'linux-tart', 'mac-golden'):
            self.assertIn('runner-updater: off: removed the pin %s (journaled first in %s)\n'
                          % (os.path.join(u.pindir, n), u.actions), res.stdout)

    def test_a_journal_that_cannot_be_written_stops_before_the_removal(self):
        r = Rig(self)
        u = Paths(r)
        u.put(dict(FULL, on=True))
        pins = u.pins(**OFF_PINS)
        os.mkdir(u.actions)                          # runner-journal: "FILE exists and is not a regular file"
        res = r.cmd('off', ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP the action journal could not record the removal of %s (above): the pin '
                      'stays. The updater is OFF; run off again when the journal can be written\n'
                      % os.path.join(u.pindir, 'junk'), res.stdout)
        self.assertEqual(u.pin_files(), pins)
        self.assertEqual(u.get(), dict(FULL, on=False))

    def test_a_journal_that_fails_on_the_second_pin_leaves_it_and_the_rest(self):
        r = Rig(self)
        u = Paths(r)
        u.put(dict(FULL, on=True))
        u.pins(**OFF_PINS)
        count = r.sb.path('logs', 'journal-count')
        body = ('n=0; [[ -f %s ]] && n=$(<%s); (( n++ )); print $n > %s; (( n == 2 )) && exit 1\nexec /bin/zsh -f %s "$@"'
                % (count, count, count, r.journal))
        res = r.cmd('off', script=pair(r, 'fail2', journal_body=body), ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertEqual(sorted(u.pin_files()), ['linux-tart', 'mac-golden'])
        self.assertEqual(lines_of(u.actions), OFF_JOURNAL[:1])

    def test_off_with_a_window_that_stays_open_refuses_and_touches_no_pin(self):
        # off runs RECOVER first (test_runner_updater_recover.py); a journal it leaves open (here: a line it does not
        # read) stops off before anything changes
        r = Rig(self)
        u = Paths(r)
        raw = u.put(dict(FULL, on=True))
        pins = u.pins(**OFF_PINS)
        r.sb.write(u.window, 'family fx\nsurprise x\n', 0o600)
        res = r.cmd('off', ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP the window journal %s stays open: the next run\'s RECOVER tries again; '
                      'nothing else starts\n' % u.window, res.stdout)
        self.assertNotIn('off: the updater is OFF', res.stdout)
        self.assertEqual(u.pin_files(), pins)
        self.assertEqual(u.raw(), raw)
        self.assertIsNone(u.raw(u.actions))

    def test_control_off_after_recover_closed_the_journal(self):
        for text in ('family fx\n', ''):              # it disabled nothing: RECOVER closes it, then off goes on
            with self.subTest(window=text):
                r = Rig(self)
                u = Paths(r)
                u.put(dict(FULL, on=True))
                u.pins(**OFF_PINS)
                r.sb.write(u.window, text, 0o600)
                res = r.cmd('off', ok=False)
                self.assertEqual(res.returncode, 0, res.stdout)
                self.assertIn('runner-updater: recover: nothing was disabled', res.stdout)
                self.assertFalse(os.path.exists(u.window))
                self.assertFalse(u.get()['on'])

    def test_on_and_off_wait_for_the_lock(self):
        for cmd, want in (('on', True), ('off', False)):
            with self.subTest(cmd=cmd):
                r = Rig(self)
                u = Paths(r)
                raw = u.put(dict(FULL, on=not want))
                holder = hold_lock(r)
                p = r.sb.start(['/bin/zsh', '-f', r.script, cmd], name=cmd)
                r.sb.wait_for(lambda: p.poll() is not None or p.pid in lock_holders(r), cmd + ' at the lock')
                time.sleep(0.5)
                self.assertIsNone(p.poll(), r.sb.output(cmd))
                self.assertEqual(u.raw(), raw)
                release(r, holder)
                self.assertEqual(p.wait(timeout=60), 0, r.sb.output(cmd))
                self.assertEqual(u.get()['on'], want)

    def test_control_with_the_lock_free_on_and_off_run_at_once(self):
        for cmd, want in (('on', True), ('off', False)):
            with self.subTest(cmd=cmd):
                r = Rig(self)
                u = Paths(r)
                u.put(dict(FULL, on=not want))
                p = r.sb.start(['/bin/zsh', '-f', r.script, cmd], name=cmd)
                self.assertEqual(p.wait(timeout=30), 0, r.sb.output(cmd))
                self.assertEqual(u.get()['on'], want)


IMG3 = 'liveapp-mac-golden-20261020'
G = 'liveapp-mac-golden-'


def prune(r, names):
    """the REAL golden-prune, its STATEDIR the rig's: (rc, stdout, stderr)"""
    script = r.sb.copy_script('bin/golden-prune', [('STATEDIR=/Users/ci/.local/state/runner-updater',
                                                    'STATEDIR=' + r.statedir)], dest=r.sb.path('prune', 'golden-prune'))
    p = r.sb.run(['/bin/zsh', '-f', script] + names)
    return p.returncode, p.stdout, p.stderr


class TestProtected(unittest.TestCase):
    """The protected list (D6), PROTECTED: computed from the state, written by rename, one image name per line in name
    order. Its sources: each family's candidate (a checked candidate); the window's old image, `previous`, until
    ACCEPT + 7 days (while there is a candidate, and after an ACCEPT until back_until); an open window's journaled
    names (WINDOW's `image NAME` lines). `protect` runs the writer under the lock."""

    def written(self, s, window=None):
        r = Rig(self)
        u = Paths(r)
        u.put(s)
        if window is not None:
            r.sb.write(u.window, window, 0o600)
        res = r.cmd('protect')
        self.assertEqual(os.stat(u.protected).st_mode & 0o777, 0o600)
        return r, u, lines_of(u.protected), res

    def test_a_candidates_images(self):
        r, u, got, res = self.written(state(families={'fx': fam(candidate=cand(lines={'mac-a': IMG2, 'mac-b': IMG3}))}))
        self.assertEqual(got, [IMG2, IMG3])
        self.assertIn('runner-updater: protect: %s holds 2 image names\n' % u.protected, res.stdout)

    def test_control_no_candidate_no_image(self):
        r, u, got, res = self.written(state(families={'fx': fam(rejected=[V1], recipe='a' * 64)}))
        self.assertEqual(got, [])
        self.assertEqual(os.path.getsize(u.protected), 0)

    def test_the_old_image_while_a_candidate_is_observed(self):
        r, u, got, res = self.written(state(families={'fx': fam(candidate=cand(), previous={'mac-a': IMG})}))
        self.assertEqual(got, [IMG, IMG2])

    def test_control_the_old_image_with_no_candidate_and_no_back_until(self):
        r, u, got, res = self.written(state(families={'fx': fam(previous={'mac-a': IMG})}))
        self.assertEqual(got, [])

    def test_the_old_image_until_back_until(self):
        now = int(time.time())
        r, u, got, res = self.written(state(families={'fy': fam(previous={'mac-c': IMG0}, back_until=now + 86400)}))
        self.assertEqual(got, [IMG0])

    def test_control_the_old_image_after_back_until(self):
        now = int(time.time())
        r, u, got, res = self.written(state(families={'fy': fam(previous={'mac-c': IMG0}, back_until=now - 60)}))
        self.assertEqual(got, [])

    WINDOW = 'id w1\nfamily fx\nkind switch\ntarget mac-a=%s\nimage %s\nimage gold-20261020\n' % (IMG3, IMG3)

    def test_an_open_windows_journaled_names(self):
        r, u, got, res = self.written(state(), window=self.WINDOW)
        self.assertEqual(got, ['gold-20261020', IMG3])

    def test_control_no_open_window(self):
        r, u, got, res = self.written(state())
        self.assertEqual(got, [])

    def test_every_source_at_once_in_name_order_each_once(self):
        now = int(time.time())
        s = state(families={'fx': fam(candidate=cand(lines={'mac-a': IMG3}), previous={'mac-a': IMG}),
                            'fy': fam(candidate=cand(lines={'mac-c': IMG3}), previous={'mac-c': IMG0}),
                            'fz': fam(previous={'mac-d': G + '20260101'}, back_until=now + 60)})
        r, u, got, res = self.written(s, window=self.WINDOW)
        self.assertEqual(got, ['gold-20261020', G + '20260101', IMG0, IMG, IMG3])   # byte order

    def test_a_window_line_that_is_not_an_image_name_stops_and_the_old_list_stays(self):
        for line in ('image a b', 'image ', 'image', 'image -x'):
            with self.subTest(line=line):
                r = Rig(self)
                u = Paths(r)
                u.put(state(families={'fx': fam(candidate=cand())}))
                r.sb.write(u.protected, IMG + '\n', 0o600)
                r.sb.write(u.window, 'family fx\n%s\nimage %s\n' % (line, IMG3), 0o600)
                res = r.cmd('protect', ok=False)
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn('runner-updater: STOP the protected list cannot be written (%s holds an image line that is '
                              'not an image name): %s is as it was\n' % (u.window, u.protected), res.stdout)
                self.assertEqual(read_text(u.protected), IMG + '\n')

    def test_golden_prune_reads_the_list_and_never_prints_what_it_holds(self):
        names = [G + d for d in ('20261001', '20260901', '20260815', '20260801')]
        r, u, got, res = self.written(state(families={'fx': fam(candidate=cand(lines={'mac-a': G + '20260815'}))}))
        self.assertEqual(prune(r, [G + '20261001'] + names), (0, G + '20260801\n', ''))
        # the control: the same names, the list empty
        r.sb.write(u.protected, '', 0o600)
        self.assertEqual(prune(r, [G + '20261001'] + names), (0, G + '20260801\n' + G + '20260815\n', ''))

    def test_a_list_that_cannot_be_written_stops_and_the_old_list_stays(self):
        for how in ('new is a folder', 'list is a folder'):
            with self.subTest(how=how):
                r = Rig(self)
                u = Paths(r)
                u.put(state(families={'fx': fam(candidate=cand())}))
                if how == 'new is a folder':
                    r.sb.write(u.protected, IMG + '\n', 0o600)
                    os.makedirs(os.path.join(u.protected + '.new', 'x'))
                else:
                    os.remove(u.protected)
                    os.makedirs(os.path.join(u.protected, 'x'))
                before = sorted(os.listdir(r.statedir))
                res = r.cmd('protect', ok=False)
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn('runner-updater: STOP the protected list cannot be written (', res.stdout)
                self.assertIn('): %s is as it was\n' % u.protected, res.stdout)
                if how == 'new is a folder':
                    self.assertEqual(read_text(u.protected), IMG + '\n')
                else:
                    self.assertEqual(os.listdir(u.protected), ['x'])
                self.assertEqual(sorted(os.listdir(r.statedir)), sorted(before + ['lock']))

    def test_protect_with_a_state_of_another_format_waits(self):
        r = Rig(self)
        u = Paths(r)
        u.put(dict(FULL, format=2))
        r.sb.write(u.protected, IMG + '\n', 0o600)
        res = r.cmd('protect', ok=False)
        self.assertEqual((res.returncode, res.stdout), (4, WAIT % (u.state, '2')))
        self.assertEqual(read_text(u.protected), IMG + '\n')

    def test_protect_writes_a_missing_or_unreadable_list(self):
        for how in ('missing', 'symlink', 'unreadable'):
            with self.subTest(how=how):
                r = Rig(self)
                u = Paths(r)
                u.put(state(families={'fx': fam(candidate=cand())}))
                if how == 'missing':
                    os.remove(u.protected)
                elif how == 'symlink':
                    os.remove(u.protected)
                    os.symlink(r.sb.write(r.sb.path('elsewhere'), ''), u.protected)
                else:
                    os.chmod(u.protected, 0)
                r.cmd('protect')
                self.assertTrue(os.path.isfile(u.protected) and not os.path.islink(u.protected))
                self.assertEqual(lines_of(u.protected), [IMG2])

    # the writer syncs the new file to disk before it renames it: a power cut after the rename must not leave an empty
    # list (golden-prune would then print what it protects). The dd stub notes what the new file and the list hold
    DD_BODY = ('f=${2#of=}; print -r -- "$f $(/bin/cat $f | /usr/bin/tr \'\\n\' +) list=$(/bin/cat %s 2>/dev/null | '
               '/usr/bin/tr \'\\n\' +)" >> %s\n%s')

    def dd_rig(self, fail):
        r = Rig(self)
        u = Paths(r)
        u.put(state(families={'fx': fam(candidate=cand())}))
        r.sb.write(u.protected, IMG + '\n', 0o600)
        seen = r.sb.path('logs', 'dd-saw')
        stub = r.sb.stub('dd', self.DD_BODY % (u.protected, seen, 'print -u2 -r -- "dd: injected failure"; exit 1'
                                              if fail else 'exec /bin/dd "$@"'),
                         folder=r.sb.mkdir('dd'))
        script = pair(r, 'with-dd', script_rewrites=[('DD=/bin/dd', 'DD=' + stub)])
        return r, u, seen, r.cmd('protect', script=script, ok=False)

    def test_the_new_list_is_synced_before_the_rename(self):
        r, u, seen, res = self.dd_rig(fail=False)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertEqual(lines_of(seen), ['%s.new %s+ list=%s+' % (u.protected, IMG2, IMG)])
        self.assertEqual(lines_of(u.protected), [IMG2])

    def test_a_sync_that_fails_stops_and_the_old_list_stays(self):
        r, u, seen, res = self.dd_rig(fail=True)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP the protected list cannot be written (cannot sync %s.new to disk: dd: '
                      'injected failure): %s is as it was\n' % (u.protected, u.protected), res.stdout)
        self.assertEqual(lines_of(u.protected), [IMG])
        self.assertFalse(os.path.lexists(u.protected + '.new'))


LOST = ('runner-updater: REFUSE there is no state %(s)s, but the protected list %(p)s is not empty: a state existed and '
        'is lost, and a fresh one would drop what the list protects. Put the state back; or, when no image in the list '
        'must be kept, move the list aside and run %(c)s again\n')


class TestLostState(unittest.TestCase):
    """A missing state is a fresh install (OFF, nothing held). But the updater writes a name into the protected list only
    from a state, so a list that is not empty says a state existed and is lost. A fresh state there drops what the list
    protects: protect would write the shorter list at once; on, and then the next pass, would; off would write a fresh
    state that hides the evidence. So every command that reads the state REFUSEs on a missing state beside a list that
    is not an empty regular file, and writes nothing (review r1 P3-1). The controls: a missing state beside an empty
    list, or beside no list."""

    def lost(self, cmd, make_list):
        r = Rig(self, jq_wrap=True)
        u = Paths(r)
        make_list(r, u)
        before = sorted(os.listdir(r.statedir))

        def the_list():   # its bytes when it is a readable file; what lstat says in every case
            st = os.lstat(u.protected)
            readable = os.path.isfile(u.protected) and os.access(u.protected, os.R_OK)
            return (st.st_ino, st.st_size, st.st_mtime_ns, st.st_mode, u.raw(u.protected) if readable else None)
        listed = the_list()
        res = r.cmd(cmd, ok=False)
        self.assertEqual((res.returncode, res.stdout), (1, LOST % {'s': u.state, 'p': u.protected, 'c': cmd}), res.stderr)
        self.assertFalse(os.path.lexists(u.state))
        self.assertEqual(the_list(), listed)
        self.assertEqual(sorted(set(os.listdir(r.statedir)) - {'lock'}), before)
        self.assertEqual((core_calls(r), r.ps_calls()), ([], 0))

    def test_a_missing_state_beside_a_list_with_names_is_refused(self):
        def names(r, u):
            r.sb.write(u.protected, IMG + '\n' + IMG2 + '\n', 0o600)
        for cmd in ('status', 'on', 'off', 'pass', 'protect'):
            with self.subTest(cmd=cmd):
                self.lost(cmd, names)

    def test_a_missing_state_beside_a_list_that_is_not_an_empty_file_is_refused(self):
        # on and off refuse such a list before they read the state (TestListRefusals); these three read the state first
        def symlink(r, u):
            os.remove(u.protected)
            os.symlink(r.sb.write(r.sb.path('elsewhere'), ''), u.protected)

        def folder(r, u):
            os.remove(u.protected)
            os.mkdir(u.protected)

        def unreadable(r, u):
            r.sb.write(u.protected, IMG + '\n', 0o000)
        for how, make in (('a symlink', symlink), ('a folder', folder), ('unreadable, with a name', unreadable)):
            for cmd in ('status', 'pass', 'protect'):
                with self.subTest(how=how, cmd=cmd):
                    self.lost(cmd, make)

    def test_control_a_missing_state_beside_an_empty_list_or_none(self):
        for how in ('an empty list', 'no list'):
            for cmd in ('status', 'pass', 'protect', 'on', 'off'):
                if how == 'no list' and cmd in ('on', 'off'):
                    continue   # they refuse a missing list on their own (TestListRefusals)
                with self.subTest(how=how, cmd=cmd):
                    r = Rig(self, jq_wrap=True)
                    u = Paths(r)
                    if how == 'no list':
                        os.remove(u.protected)
                    res = r.cmd(cmd)
                    self.assertNotIn('REFUSE', res.stdout)
                    if cmd == 'protect':
                        self.assertEqual(u.raw(u.protected), b'')
                    if cmd == 'on':
                        self.assertEqual(u.get(), state(on=True))


class TestListRefusals(unittest.TestCase):
    """A STATEDIR without its list, or a list that is not a readable regular file: report, on and off refuse, and say
    how to get the list back WITHOUT emptying it: `protect` writes it from the state (S3b-1 review r2 P3)."""

    MISSING = ('runner-updater: REFUSE %(d)s has no protected list %(p)s, and golden-prune refuses until it has one. Do '
               'not create it empty: it lists the images the updater keeps. `%(s)s protect` writes it from the '
               'updater\'s state (a pass does too, while the updater is ON); then run %(c)s again\n')
    NOT_FILE = ('runner-updater: REFUSE %(p)s is not a readable regular file, and golden-prune refuses it too. Do not '
                'make it an empty file: it lists the images the updater keeps. Look at what it is and move it aside, '
                'then `%(s)s protect` writes it from the updater\'s state (a pass does too, while the updater is ON); '
                'then run %(c)s again\n')

    def test_following_the_text_gives_the_list_back_with_what_it_protects(self):
        for c in ('report', 'on', 'off'):
            with self.subTest(cmd=c):
                r = Rig(self)
                u = Paths(r)
                raw = u.put(state(on=True, families={'fx': fam(candidate=cand(lines={'mac-a': G + '20260815'}))}))
                os.remove(u.protected)
                res = r.cmd(c, ok=False)
                self.assertEqual((res.returncode, res.stdout), (1, self.MISSING % {
                    'd': r.statedir, 'p': u.protected, 's': r.script, 'c': c}), res.stderr)
                self.assertEqual(u.raw(), raw)
                self.assertEqual(r.ps_calls(), 0)
                r.cmd('protect')                        # what it says to do
                self.assertEqual(lines_of(u.protected), [G + '20260815'])
                r.cmd(c)
                names = [G + d for d in ('20261001', '20260901', '20260815', '20260801')]
                self.assertEqual(prune(r, [G + '20261001'] + names), (0, G + '20260801\n', ''))

    def test_a_list_that_is_not_a_readable_regular_file(self):
        for kind in ('symlink', 'folder', 'unreadable'):
            for c in ('report', 'on', 'off'):
                with self.subTest(kind=kind, cmd=c):
                    r = Rig(self)
                    u = Paths(r)
                    u.put(state(on=True, families={'fx': fam(candidate=cand())}))
                    os.remove(u.protected)
                    if kind == 'symlink':
                        os.symlink(r.sb.write(r.sb.path('elsewhere'), ''), u.protected)
                    elif kind == 'folder':
                        os.mkdir(u.protected)
                    else:
                        r.sb.write(u.protected, IMG + '\n', 0o000)
                    res = r.cmd(c, ok=False)
                    self.assertEqual((res.returncode, res.stdout), (1, self.NOT_FILE % {
                        'p': u.protected, 's': r.script, 'c': c}), res.stderr)
                    self.assertEqual(r.ps_calls(), 0)


NOW = ('now=$(/bin/date -u +%s)', 'now=$RU_TEST_NOW')   # the pass's clock, from the test
KEEP = 72 * 3600
SUCCESS = ('2026-11-01 09:30:00 INFO mac-a: Runner removed name=runner-0000aa03 instanceID=runner-0000aa03 '
           'reason=job-completed jobId=5f8432ad-50ed-b843-40be-f42f87083259 repo=example-org/example '
           'workflowRunId=39746588065 job="build (fef3)" result=succeeded\n'
           '2026-11-01 09:31:00 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n')
KILL = ('umask 077\n', 'umask 077\nkill() { print -r -- "kill $*" >> $ACTIONS_LOG }\n')   # kill is a builtin
WOULD = '  pass_act $now   # the pass acts on its verdicts'   # where a planted call goes: before the pass acts
ACTION_CALLS = 'runner-disable; runner-enable; golden-build; golden-gate x; tart list; launchctl list; kill -0 $$; '


def on_state(restart=None, **kw):
    """ON, family fx's candidate = the rig's config lines (mac-a: IMG), its old image IMG0; RESTART: a restart member"""
    s = state(on=True, families={'fx': fam(candidate=cand(lines={'mac-a': IMG}, closed_at=P[2] + 100),
                                           previous={'mac-a': IMG0}, **kw)})
    if restart is not None:
        s['restart'] = restart
    return s


# THE NO-ACTION CELLS. macOS's sandbox lets start only the programs a command is meant to start, each by the path it
# starts it by (with the rig's jq, the jq a wrapper runs, and its ps and curl stubs), and the action stubs of the
# rig's stubs folder, so a bare name still reaches its logging stub (the second witness). zsh prints a denied start
# on stderr: "...: operation not permitted: PATH".
STATUS_RUNS = ('/bin/zsh', '/bin/cat', '/bin/date')
PASS_RUNS = STATUS_RUNS + ('/bin/mkdir', '/bin/rm', '/bin/mv', '/bin/dd', '/bin/sleep', '/usr/bin/head', '/usr/bin/shasum',
                           '/usr/bin/perl')   # shasum is a perl script
REPORT_RUNS = PASS_RUNS + ('/bin/cp',)
DENIED = ': operation not permitted: %s\n'
ACTIONS_SEEN = ['runner-disable', 'runner-enable', 'golden-build', 'golden-gate', 'tart', 'launchctl', 'kill']


def only_these_start(r, programs, writes=False):
    """a sandbox-exec profile: no program may start but PROGRAMS, the rig's jq and stubs, and the action stubs. WRITES:
    also no file write but under STATEDIR, /dev/null and the stubs' own log folders (ps, curl, jq and logs/)"""
    allowed = set(programs) | {r.jq, the_jq(), r.sb.path('tools-ps', 'ps'), r.sb.path('tools-curl', 'curl')}
    allowed |= {os.path.realpath(p) for p in allowed}
    profile = ('(version 1)(allow default)(deny process-exec*)(allow process-exec*%s (subpath "%s"))'
               % (''.join(' (literal "%s")' % p for p in sorted(allowed)), r.sb.stubs))
    if writes:
        here = [r.statedir, r.psd, r.curld, r.jqd, r.sb.logs]
        profile += ('(deny file-write*)(allow file-write* (literal "/dev/null")%s)'
                    % ''.join(' (subpath "%s")' % os.path.realpath(d) for d in here))
    return profile


def sandboxed(test, r, profile, *args, env=None):
    """runner-updater ARGS under sandbox-exec with PROFILE; it must exit 0"""
    res = r.sb.run(['/usr/bin/sandbox-exec', '-p', profile, '/bin/zsh', '-f', r.script] + list(args), extra_env=env)
    test.assertEqual(res.returncode, 0, res.stdout + res.stderr)
    return res


def actions_seen(r):
    log = r.sb.path('logs', 'actions.log')
    return [l.split()[0] for l in read_text(log).splitlines()] if os.path.exists(log) else []


class TestNoActionAnyPath(unittest.TestCase):
    """A pass with no work, report and status take no action, whatever path an action tool is called by. Each runs under a profile
    that lets start only what it is meant to start (above): an action tool called by its ABSOLUTE path (the repo's
    style) is denied, and zsh prints the denial. The action stubs, found through PATH, stay the second witness, and
    `kill` (a builtin) is a logging function. The controls, under the same profile: `/bin/launchctl list` by its
    absolute path is denied and the cell sees the denial (and the launchctl stub sees nothing); bare names reach their
    stubs. The pass's profile also denies every file write outside STATEDIR (and the stubs' own log folders), so an edit
    of the config by a builtin or by a program it may start (mv) is seen too; its control writes beside the config and
    must be denied. Bound: a call whose stderr and exit status are both thrown away is seen by neither witness."""

    ABSOLUTE = '/bin/launchctl list > /dev/null'
    # where each command's planted call goes
    PASS_AT = WOULD
    REPORT_AT = '/bin/mv -f -- $pass/state.json $REPORT/state.json || refuse "cannot write $REPORT/state.json"\nexit 0\n'
    STATUS_AT = "  print -r -- $out | $JQ -r 'def yn:"

    def plant(self, at, calls):
        if at == self.REPORT_AT:
            return [KILL, (at, at.replace('exit 0\n', calls + '\nexit 0\n'))]
        return [KILL, (at, '  ' + calls + '\n' + at)]

    def a_pass(self, calls=None):
        """two passes with no work, under the profile: the window opens, then the log gains jobs and no failure (KEEP
        observes; no verdict, no release: a pass acts on a verdict only, test_runner_updater_pass)"""
        r = Rig(self, jq_wrap=True, extra_rewrites=self.plant(self.PASS_AT, calls) if calls else [KILL])
        Paths(r).put(on_state())
        profile = only_these_start(r, PASS_RUNS, writes=True)
        env = {'ACTIONS_LOG': r.sb.path('logs', 'actions.log')}
        r.write_log('')
        first = sandboxed(self, r, profile, 'pass', env=env)
        r.append_log(fixture('studio-cut.log'))
        res = sandboxed(self, r, profile, 'pass', env=env)
        self.assertIn('\nr1 fx: none (', res.stdout)
        self.assertIn('\nkeep fx: observe (runner %s: observing since ' % V2, res.stdout)
        self.assertNotIn('rollback', res.stdout)
        return r, first.stderr + res.stderr

    def a_report(self, calls=None):
        """two reports, under the profile: --observe fx, then three counted failures (R1: a rollback is due)"""
        r = Rig(self, extra_rewrites=self.plant(self.REPORT_AT, calls) if calls else [KILL])
        profile = only_these_start(r, REPORT_RUNS)
        env = {'ACTIONS_LOG': r.sb.path('logs', 'actions.log')}
        r.write_log('')
        first = sandboxed(self, r, profile, 'report', '--observe', 'fx', env=env)
        r.append_log(fixture('three-failures.log'))
        res = sandboxed(self, r, profile, 'report', env=env)
        self.assertIn('\nfx: R1: a rollback is due', res.stdout)
        return r, first.stderr + res.stderr

    def a_status(self, calls=None):
        r = Rig(self, extra_rewrites=self.plant(self.STATUS_AT, calls) if calls else [KILL])
        Paths(r).put(dict(FULL, on=True))
        res = sandboxed(self, r, only_these_start(r, STATUS_RUNS), 'status',
                        env={'ACTIONS_LOG': r.sb.path('logs', 'actions.log')})
        self.assertIn('\nrunner-updater: STOP fx NO EVIDENCE: known true;', res.stdout)
        return r, res.stderr

    def test_each_starts_only_what_it_may(self):
        for name, run in (('pass', self.a_pass), ('report', self.a_report), ('status', self.a_status)):
            with self.subTest(cmd=name):
                r, err = run()
                self.assertEqual(err, '')                  # no denied start
                self.assertEqual(actions_seen(r), [])      # no action stub reached

    def test_control_an_action_by_its_absolute_path_is_denied_and_seen(self):
        for name, run, n in (('pass', self.a_pass, 2), ('report', self.a_report, 2), ('status', self.a_status, 1)):
            with self.subTest(cmd=name):
                r, err = run(self.ABSOLUTE)
                self.assertEqual(err.count(DENIED % '/bin/launchctl'), n, err)
                self.assertEqual(actions_seen(r), [])      # the stub never ran: the call was by its path

    # a write beside the config: a builtin redirect, and a rename by /bin/mv (a program pass may start)
    BESIDE = 'print -r -- planted > ${CONFIG:h}/planted; /bin/mv -f -- $CONFIG ${CONFIG:h}/moved; '

    def test_control_a_pass_that_writes_beside_the_config_is_denied(self):
        # the pass's profile also denies every file write outside STATEDIR (and the stubs' own log folders): an edit of
        # the config by a builtin or by mv is seen, though it starts no denied program
        r, err = self.a_pass(self.BESIDE)
        self.assertEqual(sorted(os.listdir(r.cfgdir)), ['config.toml', 'runner.log'])
        self.assertEqual(read_text(r.config), config())
        self.assertEqual(err.count(': operation not permitted: %s/planted\n' % r.cfgdir), 2, err)
        self.assertEqual(err.count('mv: rename %s to %s/moved: Operation not permitted\n' % (r.config, r.cfgdir)), 2, err)

    def test_control_bare_names_reach_their_stubs_under_the_same_profile(self):
        for name, run, n in (('pass', self.a_pass, 2), ('report', self.a_report, 2), ('status', self.a_status, 1)):
            with self.subTest(cmd=name):
                r, err = run(ACTION_CALLS)
                self.assertEqual(actions_seen(r), ACTIONS_SEEN * n)
                self.assertEqual(err, '')


class TestStderrKept(unittest.TestCase):
    """A report or a pass keeps its stderr to its last line. zsh's `exec {fd}< FILE 2>/dev/null` opens FILE AND sends
    the shell's own stderr to /dev/null for good: after the log was opened, every later error line of the run (and a
    sandbox denial) was lost. The lib opens the log, and runner.log.1 after a rotation, with the 2>/dev/null on a
    group around the exec. A line planted at the end of report and of pass must reach stderr: on a first pass (the
    log), and on a pass after one rotation (runner.log.1 too)."""

    LINE = "print -u2 -r -- 'stderr reaches the end'"

    def test_report_and_pass_keep_their_stderr(self):
        for cmd in ('report', 'pass'):
            for rotated in (False, True):
                with self.subTest(cmd=cmd, rotated=rotated):
                    at = TestNoActionAnyPath.REPORT_AT if cmd == 'report' else WOULD
                    new = (at.replace('exit 0\n', self.LINE + '\nexit 0\n') if cmd == 'report'
                           else '  ' + self.LINE + '\n' + at)
                    r = Rig(self, extra_rewrites=[(at, new)])
                    Paths(r).put(on_state())
                    if rotated:
                        r.cmd(cmd)
                        r.rotate()
                        r.append_log(fixture('studio-cut.log'))
                    res = r.cmd(cmd)
                    if rotated:
                        self.assertIn('; continuous: the log rotated once', res.stdout)
                    self.assertEqual(res.stderr, 'stderr reaches the end\n')


class TestPass(unittest.TestCase):
    """runner-updater pass, the timer's entry: it TRIES the lock (held: exit 0 at once); OFF: exit 0 at once, no core
    call; ON: the facts from the real state, idle / r1 / keep / status, the core state written back into the state,
    the protected list rewritten, the verdicts printed. What it then does on them: test_runner_updater_pass."""

    def rig(self, s=None, **kw):
        r = Rig(self, jq_wrap=True, **kw)
        u = Paths(r)
        if s is not None:
            u.put(s)
        return r, u

    def facts(self, u):
        with open(os.path.join(u.passdir, 'facts.json')) as f:
            return json.load(f)

    def test_off_ends_the_pass_at_once_with_no_core_call(self):
        for s in (None, dict(on_state(), on=False)):
            with self.subTest(fresh=s is None):
                r, u = self.rig(s)
                raw, lst = u.raw(), u.raw(u.protected)
                res = r.cmd('pass')
                self.assertEqual(res.stdout, 'runner-updater: pass: the updater is OFF: nothing to do\n')
                self.assertEqual(core_calls(r), [])
                self.assertEqual(r.ps_calls(), 0)
                self.assertEqual((u.raw(), u.raw(u.protected)), (raw, lst))
                self.assertFalse(os.path.exists(u.passdir))

    def test_control_on_the_pass_runs_the_core(self):
        r, u = self.rig(on_state())
        r.cmd('pass')
        self.assertEqual(core_calls(r), ['idle', 'r1', 'keep', 'status'])

    def test_a_held_lock_ends_the_pass_at_once(self):
        r, u = self.rig(on_state())
        raw = u.raw()
        holder = hold_lock(r)
        t0 = time.monotonic()
        res = r.cmd('pass')
        self.assertLess(time.monotonic() - t0, 10)
        self.assertEqual(res.stdout, 'runner-updater: pass: another run holds the updater lock; this pass ends\n')
        self.assertEqual(core_calls(r), [])
        self.assertEqual(r.ps_calls(), 2)            # the holder's two
        self.assertEqual(u.raw(), raw)
        self.assertIsNone(holder.poll())
        release(r, holder)

    def test_a_pass_reads_the_state_and_writes_back_the_core_state_and_the_list(self):
        held = [stop('fx', 'JOBS FAIL ON THE NEW IMAGE', detail={'counts': {'completions': 2, 'failed': 2}})]
        until = int(time.time()) + 86400
        s = state(on=True, families={'fx': fam(candidate=cand(lines={'mac-a': IMG}, closed_at=P[2] + 100),
                                               previous={'mac-a': IMG0}, rejected=[V1], stops=held),
                                     'fy': fam(previous={'mac-c': IMG3}, back_until=until)},
                  images={IMG: V2})
        r, u = self.rig(s, cfg=config((('mac-a', IMG), ('mac-c', IMG2))), families='fx tart mac-a\nfy tart mac-c\n')
        res = r.cmd('pass')
        f = self.facts(u)
        self.assertEqual(f['families'], {
            'fx': {'provider': 'tart', 'sets': ['mac-a'], 'candidate': s['families']['fx']['candidate'], 'back_until': None},
            'fy': {'provider': 'tart', 'sets': ['mac-c'], 'candidate': None, 'back_until': until}})
        self.assertEqual(f['stops'], held)
        new = u.get()
        self.assertEqual(dict(new, core=None), dict(s, core=None))
        self.assertEqual(new['core']['boundary']['position'], f['position'])
        self.assertEqual(lines_of(u.protected), sorted([IMG, IMG0, IMG3]))
        self.assertIn('\nkeep fx: held (JOBS FAIL ON THE NEW IMAGE stands: a person answers it; KEEP does not accept '
                      'while it stands)\n', res.stdout)
        self.assertIn('\nfx: STOP JOBS FAIL ON THE NEW IMAGE (runner %s): 2 completed, 0 succeeded, 2 failed, 0 canceled. '
                      'Next: `runner-updater back fx` (until the keep date), or `runner-updater retry fx` to keep it\n'
                      % V2, res.stdout)
        self.assertFalse(os.path.exists(r.report_dir))   # report's state stays apart
        r.cmd('pass')                                     # the next pass reads the boundary this one wrote
        self.assertTrue(self.facts(u)['continuous'])

    def test_a_pass_passes_the_restart_member_once_and_clears_it(self):
        r, u = self.rig(on_state(restart=RESTART))
        r.cmd('pass')
        self.assertEqual(self.facts(u)['restart'], RESTART)
        self.assertNotIn('restart', u.get())
        r.cmd('pass')
        self.assertIsNone(self.facts(u)['restart'])

    def test_control_a_pass_whose_core_cannot_decide_keeps_the_restart_member(self):
        r, u = self.rig(on_state(restart=RESTART))
        r.sb.write(os.path.join(r.jqd, 'fail'), 'r1')
        res = r.cmd('pass', ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertEqual(u.get()['restart'], RESTART)

    def test_the_next_pass_rewrites_a_missing_list(self):
        r, u = self.rig(on_state())
        os.remove(u.protected)
        r.cmd('pass')
        self.assertEqual(lines_of(u.protected), [IMG0, IMG])

    def test_control_off_a_pass_leaves_a_missing_list_missing(self):
        r, u = self.rig(dict(on_state(), on=False))
        os.remove(u.protected)
        r.cmd('pass')
        self.assertFalse(os.path.lexists(u.protected))

    def test_the_core_could_not_decide_leaves_the_state_and_the_list(self):
        for prog in ('idle', 'r1', 'keep', 'status'):
            with self.subTest(prog=prog):
                r, u = self.rig(on_state())
                r.cmd('pass')
                r.sb.write(u.protected, 'marker-image\n', 0o600)   # a rewrite would drop it
                raw, lst = u.raw(), u.raw(u.protected)
                r.append_log('2026-11-01 05:00:00 INFO mac-a: Scaling up runner currentCount=0 desiredCount=1\n')
                r.sb.write(os.path.join(r.jqd, 'fail'), prog)
                res = r.cmd('pass', ok=False)
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn('runner-updater: core could not decide (%s): exit 5: injected failure\n' % prog, res.stdout)
                self.assertIn('runner-updater: the pass did nothing: %s is as it was\n' % u.state, res.stdout)
                self.assertEqual((u.raw(), u.raw(u.protected)), (raw, lst))
        # the control: a pass that decides rewrites the list
        os.remove(os.path.join(r.jqd, 'fail'))
        r.cmd('pass')
        self.assertEqual(lines_of(u.protected), [IMG0, IMG])

    def accept_at(self, later):
        r, u = self.rig(on_state(), extra_rewrites=[NOW])
        t = P[2] + 3600
        r.write_log('')
        r.cmd('pass', env={'RU_TEST_NOW': str(t)})       # the window opens at t
        r.append_log(SUCCESS)
        return r.cmd('pass', env={'RU_TEST_NOW': str(t + later)})

    def test_72_h_after_the_window_opened_with_a_success_it_accepts(self):
        # the ACCEPT itself: test_runner_updater_pass, TestAccept
        res = self.accept_at(KEEP)
        self.assertIn('\nkeep fx: accept (runner %s: 1 succeeded of 1 completed in 72 h)\n' % V2, res.stdout)
        self.assertIn('runner-updater: pass: accepted fx: runner %s: 1 succeeded of 1 completed in 72 h; '
                      '`runner-updater back fx` restores %s until ' % (V2, IMG0), res.stdout)

    def test_control_a_second_before_72_h_it_observes(self):
        res = self.accept_at(KEEP - 1)
        self.assertIn('\nkeep fx: observe (', res.stdout)
        self.assertNotIn('accepted', res.stdout)

    def test_a_config_whose_log_the_core_cannot_read_is_no_facts_in_a_pass_too(self):
        for top, why in (('log-format = "json"\n', LOG_FORMAT), ('log-file = "/x.log"\n', LOG_FILE),
                         ('log-level = "warn"\n', LOG_LEVEL % 5)):
            with self.subTest(top=top):
                r, u = self.rig(on_state(), cfg=config(top=top))
                raw = u.raw()
                res = r.cmd('pass', ok=False)
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn('runner-updater: REFUSE no facts: %s%s\n' % (r.config, why), res.stdout)
                self.assertEqual(core_calls(r), [])
                self.assertEqual(u.raw(), raw)

    def test_a_held_candidate_of_a_family_the_families_file_does_not_name_is_no_facts(self):
        r, u = self.rig(state(on=True, families={'fz': fam(candidate=cand())}))
        res = r.cmd('pass', ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE no facts: the state holds a candidate for the family fz, which %s does '
                      'not name\n' % r.families, res.stdout)
        self.assertEqual(core_calls(r), [])

    def test_a_family_dropped_from_the_families_file_with_a_back_until_is_no_refusal(self):
        # S3b-2a r1 carry: its previous image is kept until back_until, then the pass deletes it
        # (test_runner_updater_pass, TestDeletion); every pass in between runs
        r, u = self.rig(state(on=True, families={'fz': fam(previous={'mac-c': IMG0}, back_until=int(time.time()) + 86400)}))
        res = r.cmd('pass', ok=False)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertEqual(core_calls(r), ['idle', 'r1', 'keep', 'status'])
        self.assertEqual(lines_of(u.protected), [IMG0])

    def test_control_a_held_family_the_families_file_names(self):
        r, u = self.rig(state(on=True, families={'fz': fam(candidate=cand()), 'fw': fam(rejected=[V1])}),
                        families='fx tart mac-a\nfz tart mac-b\n')
        res = r.cmd('pass', ok=False)                 # its old candidate (T0) holds NO EVIDENCE: exit 1
        self.assertEqual(core_calls(r), ['idle', 'r1', 'keep', 'status'], res.stdout)
        self.assertEqual(self.facts(u)['families']['fz']['candidate'], cand())

    def test_a_state_of_another_format_waits_with_no_core_call(self):
        r, u = self.rig(dict(FULL, on=True, format=2))
        raw = u.raw()
        res = r.cmd('pass', ok=False)
        self.assertEqual((res.returncode, res.stdout), (4, WAIT % (u.state, '2')))
        self.assertEqual(core_calls(r), [])
        self.assertEqual(u.raw(), raw)

    def test_untested_jq_stops_a_pass_that_is_on(self):
        r, u = self.rig(on_state())
        r.sb.write(os.path.join(r.jqd, 'version'), 'jq-1.6\n')
        res = r.cmd('pass', ok=False)
        self.assertEqual(res.returncode, 3, res.stdout)
        self.assertTrue(res.stdout.startswith("runner-updater: STOP untested jq: %s prints 'jq-1.6'" % r.jq), res.stdout)
        self.assertEqual((core_calls(r), r.ps_calls()), ([], 0))

    def test_control_untested_jq_and_off_ends_at_once(self):
        r, u = self.rig(dict(on_state(), on=False))
        r.sb.write(os.path.join(r.jqd, 'version'), 'jq-1.6\n')
        self.assertEqual(r.cmd('pass').stdout, 'runner-updater: pass: the updater is OFF: nothing to do\n')


LOG_FILE = (' line 5: a top-level log-file key: runscaler then writes its log elsewhere or nowhere, and runner.log beside '
            'the config reads as a quiet, continuous log, so R1 would be blind while the facts look normal; remove the key')
LOG_FORMAT = (' line 5: log-format is not "text": runscaler then writes records that the core\'s log reader ignores, so R1 '
              'would be blind while the facts look normal; set log-format = "text" or remove the line')

LOG_LEVEL = (' line %d: log-level is not "info" or "debug": runscaler then writes no INFO record (no job-completed record, '
             'the proof of life R1 and KEEP read), so a quiet log would look like a healthy one; set log-level = "info" '
             '(what config/config.toml.example sets) or remove the line')


class TestLogKeys(unittest.TestCase):
    """A config whose log the core cannot read is no facts (S3b-1 review r1 P3-1): a top-level log-file key (runscaler
    then writes elsewhere, or nowhere with ""), or a log-format other than "text" (json records the core ignores)."""

    def refused(self, top, why):
        r = Rig(self, cfg=config(top=top))
        res = r.report(ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE no facts: %s%s\n' % (r.config, why), res.stdout)
        self.assertFalse(os.path.exists(os.path.join(r.pass_dir, 'facts.json')))
        self.assertFalse(os.path.exists(os.path.join(r.pass_dir, 'idle.json')))
        return r

    def test_a_top_level_log_file_is_refused(self):
        for line in ('log-file = "/var/log/runscaler.log"', 'log-file = ""', '"log-file" = "x"', "log-file='x'",
                     'log-file.x = 1'):
            with self.subTest(line=line):
                self.refused(line + '\n', LOG_FILE)

    def test_a_log_format_other_than_text_is_refused(self):
        for line in ('log-format = "json"', 'log-format = ""', "log-format = 'text'", '"log-format" = "text"',
                     'log-format = "text" x'):
            with self.subTest(line=line):
                self.refused(line + '\n', LOG_FORMAT)

    def test_a_log_level_that_writes_no_info_record_is_refused(self):
        # S3b-4b (liveapp-9f, S2b-3a r1 F2): at warn or error runscaler writes no INFO record, so no job-completed record
        for line in ('log-level = "warn"', 'log-level = "error"', 'log-level = "INFO"', 'log-level = ""',
                     "log-level = 'info'", '"log-level" = "info"', 'log-level = "info" x'):
            with self.subTest(line=line):
                self.refused(line + '\n', LOG_LEVEL % 5)

    def test_control_log_level_info_or_debug_no_line_or_one_in_a_table(self):
        plain = config()
        self.assertEqual(plain.count('log-level = "info"\n'), 1)
        for cfg in (plain, plain.replace('log-level = "info"\n', 'log-level = "debug"\n'),
                    plain.replace('log-level = "info"\n', 'log-level = "info"   # the default\n'),
                    plain.replace('log-level = "info"\n', ''),
                    plain.replace('[tart]\n', '[tart]\nlog-level = "error"\n')):
            with self.subTest(cfg=cfg[:300]):
                r = Rig(self, cfg=cfg)
                r.report()
                self.assertEqual(r.facts()['format'], 1)

    def test_control_log_format_text_and_a_log_file_key_in_a_table(self):
        for cfg in (config(top='log-format = "text"\n'), config(top='log-format = "text"   # the default\n'),
                    config().replace('[tart]\n', '[tart]\nlog-file = "x"\n')):
            with self.subTest(cfg=cfg[:200]):
                r = Rig(self, cfg=cfg)
                r.report()
                self.assertEqual(r.facts()['format'], 1)


WHY_POOL = ("the updater's rules for a Tart set (R1, NOT SERVING) assume no warm pool, as config.toml.example sets it")
POOL = '%(c)s: [tart] pool-size = %(n)s (a warm pool), and the family fx runs the Tart set mac-a: ' + WHY_POOL + \
       '; set pool-size = 0 in [tart]'
POOL_UNREAD = ('%(c)s line %(line)d: a pool-size this does not read (it reads only `pool-size = N` in the [tart] table), '
               'and the family fx runs the Tart set mac-a: ' + WHY_POOL + '; set it in [tart] alone, to 0')


class TestWarmPool(unittest.TestCase):
    """PLAN D6: `on` refuses a Tart set with pool-size > 0. runscaler 0.9.5 reads pool-size in the [tart] table (every
    scale set inherits it) or in a scale set's own tart table, and its default is 0. The updater reads ONE spelling,
    `pool-size = N` in the top-level [tart] table; any other line that names pool-size is one it does not read. While a
    family of the families file runs a set of the config, either one makes `on` REFUSE (the state byte-equal), and a
    pass or a report no facts (no core call). The controls: pool-size = 0, no pool-size line, the same line as a
    comment, no family."""

    TART = 'pool-size = 0 '   # the example's [tart] line, from its start

    def cfg(self, pool=None, swap=None):
        c = config()
        self.assertEqual(c.count(self.TART), 1)
        if pool is not None:
            c = c.replace(self.TART, 'pool-size = %s ' % pool)
        if swap is not None:
            c = swap(c)
        return c

    @staticmethod
    def line_of(c, text):
        return c.splitlines().index(text) + 1

    def on(self, cfg, families='fx tart mac-a\n'):
        r = Rig(self, jq_wrap=True, cfg=cfg, families=families)
        u = Paths(r)
        raw = u.put(dict(on_state(), on=False))
        return r, u, raw, r.cmd('on', ok=False)

    def test_on_refuses_a_warm_pool(self):
        for n in ('1', '2', '01'):
            with self.subTest(pool=n):
                r, u, raw, res = self.on(self.cfg(pool=n))
                self.assertEqual((res.returncode, res.stdout), (1, 'runner-updater: REFUSE on: %s: the updater is as it '
                                 'was\n' % (POOL % {'c': r.config, 'n': n})), res.stderr)
                self.assertEqual(u.raw(), raw)

    UNREAD = {   # how -> (the config's change, the line it adds)
        'in the scale set': (lambda c: c.replace('disable-update = false\n', 'disable-update = false\ntart.pool-size = 1\n'),
                             'tart.pool-size = 1'),
        'in the scale set, 0 too': (lambda c: c.replace('disable-update = false\n',
                                                        'disable-update = false\ntart.pool-size = 0\n'), 'tart.pool-size = 0'),
        'in a [scaleset.tart] table': (lambda c: c + '[scaleset.tart]\npool-size = 1\n', 'pool-size = 1'),
        'a dotted key at the top': (lambda c: c.replace('log-level = "info"\n', 'log-level = "info"\ntart.pool-size = 1\n'),
                                    'tart.pool-size = 1'),
        'a value that is not a plain number': (lambda c: c.replace('pool-size = 0 ', 'pool-size = "1" '), None),
        'a second pool-size in [tart]': (lambda c: c.replace('cache-budget = 60', 'pool-size = 0\ncache-budget = 60'),
                                         'pool-size = 0'),
    }

    def test_on_refuses_a_pool_size_it_does_not_read(self):
        for how, (swap, added) in self.UNREAD.items():
            with self.subTest(how=how):
                c = self.cfg(swap=swap)
                if added is None:
                    line = next(i for i, l in enumerate(c.splitlines(), 1) if l.startswith('pool-size = "1"'))
                elif how == 'a second pool-size in [tart]':
                    line = [i for i, l in enumerate(c.splitlines(), 1) if l == added][0]
                else:
                    line = self.line_of(c, added)
                r, u, raw, res = self.on(c)
                self.assertEqual((res.returncode, res.stdout), (1, 'runner-updater: REFUSE on: %s: the updater is as it '
                                 'was\n' % (POOL_UNREAD % {'c': r.config, 'line': line})), res.stderr)
                self.assertEqual(u.raw(), raw)

    def test_control_on_with_no_warm_pool(self):
        for how, c, families in (
                ('pool-size = 0', self.cfg(), 'fx tart mac-a\n'),
                ('no pool-size line (runscaler: 0)', self.cfg(swap=lambda c: '\n'.join(
                    l for l in c.splitlines() if not l.startswith('pool-size')) + '\n'), 'fx tart mac-a\n'),
                ('the line as a comment', self.cfg(swap=lambda c: c.replace(
                    'disable-update = false\n', 'disable-update = false\n# tart.pool-size = 1\n')), 'fx tart mac-a\n'),
                ('a warm pool, but no family', self.cfg(pool='1'), None),
                ('a warm pool, but no family runs a set of the config', self.cfg(pool='1'), 'fz tart mac-z\n')):
            with self.subTest(how=how):
                r, u, raw, res = self.on(c, families=families)
                self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
                self.assertTrue(u.get()['on'])

    def test_a_pass_and_a_report_are_no_facts_with_a_warm_pool(self):
        for cmd in ('pass', 'report'):
            with self.subTest(cmd=cmd):
                r = Rig(self, jq_wrap=True, cfg=self.cfg(pool='1'))
                u = Paths(r)
                raw = u.put(on_state())
                res = r.cmd(cmd, ok=False)
                self.assertEqual(res.returncode, 1, res.stdout)
                self.assertIn('runner-updater: REFUSE no facts: %s\n' % (POOL % {'c': r.config, 'n': '1'}), res.stdout)
                self.assertEqual(core_calls(r), [])
                self.assertEqual(u.raw(), raw)
        # the control: the same pass with pool-size = 0 runs the core (and every other pass cell runs on the example)
        r = Rig(self, jq_wrap=True, cfg=self.cfg())
        Paths(r).put(on_state())
        r.cmd('pass')
        self.assertEqual(core_calls(r), ['idle', 'r1', 'keep', 'status'])


if __name__ == '__main__':
    unittest.main()
