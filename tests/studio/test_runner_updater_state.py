"""bin/runner-updater's STATE slice: its own PATH, the config keys that would blind the log pass, the updater's state
(STATEDIR/state.json), `status`, `on` and `off`, the protected-list writer and `protect`, and the timer's `pass`.

The rig is test_runner_updater's (every path constant rewritten into a sandbox; stubs for ps and curl; the real core).
"""
import calendar
import json
import os
import subprocess
import time
import unittest

from tests.studio.test_runner_updater import IMG, IMG2, Rig, config, read_text

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


# every member the state holds, and one this release does not know (it is kept as it is)
FULL = state(on=False, families={
    'fx': fam(candidate=cand(), previous={'mac-a': IMG}, rejected=[V1], recipe='a' * 64,
              stops=[stop('fx', 'NO EVIDENCE', detail={'text': 'no job completed in 72 h'})]),
    'fy': fam(previous={'mac-c': IMG0}, back_until=T0 + 7 * 86400)},
    images={IMG2: V2, IMG: V0}, core={'format': 1, 'not_ready_since': {}}, later={'kept': [1, 2]})


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
    LIB_REWRITES) and runner-journal (the real one, or a stub with JOURNAL_BODY); -> the script's path"""
    d = r.sb.mkdir(name)
    r.sb.copy_script('bin/runner-updater-lib', list(lib_rewrites), dest=os.path.join(d, 'runner-updater-lib'))
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

    def test_control_a_copy_that_sets_no_path_shows_the_callers(self):
        r = Rig(self)
        own = 'export PATH=%s:%s' % (r.sb.stubs, SYSTEM)
        script = r.copy('runner-updater-nopath', [(own, ': ' + own)])
        r.cmd('report', script=script, env={'PATH': '/nonexistent'})
        self.assertEqual(set(lines_of(os.path.join(r.psd, 'path'))), {'/nonexistent'})


WAIT = 'runner-updater: WAIT the state %s has format %s; this updater reads format 1: it waits and changes nothing\n'
OFF_LINE = 'runner-updater: status: the updater is OFF\n'
ON_LINE = 'runner-updater: status: the updater is ON\n'


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
           'a core that is not an object': dict(FULL, core=[1])}

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

    def test_off_with_an_open_window_refuses_and_touches_no_pin(self):
        for text in ('family fx\n', ''):
            with self.subTest(window=text):
                r = Rig(self)
                u = Paths(r)
                raw = u.put(dict(FULL, on=True))
                pins = u.pins(**OFF_PINS)
                r.sb.write(u.window, text, 0o600)
                res = r.cmd('off', ok=False)
                self.assertEqual((res.returncode, res.stdout), (1, (
                    'runner-updater: REFUSE a window is open (%s): off never strands a window, so nothing changed. '
                    'Run off again when the window has ended\n') % u.window), res.stderr)
                self.assertEqual(u.pin_files(), pins)
                self.assertEqual(u.raw(), raw)
                self.assertIsNone(u.raw(u.actions))

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
        stub = r.sb.stub('dd', self.DD_BODY % (u.protected, seen, 'exit 1' if fail else 'exec /bin/dd "$@"'),
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
        self.assertIn('runner-updater: STOP the protected list cannot be written (cannot sync %s.new to disk): %s is as '
                      'it was\n' % (u.protected, u.protected), res.stdout)
        self.assertEqual(lines_of(u.protected), [IMG])
        self.assertFalse(os.path.lexists(u.protected + '.new'))


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


LOG_FILE = (' line 5: a top-level log-file key: runscaler then writes its log elsewhere or nowhere, and runner.log beside '
            'the config reads as a quiet, continuous log, so R1 would be blind while the facts look normal; remove the key')
LOG_FORMAT = (' line 5: log-format is not "text": runscaler then writes records that the core\'s log reader ignores, so R1 '
              'would be blind while the facts look normal; set log-format = "text" or remove the line')


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

    def test_control_log_format_text_and_a_log_file_key_in_a_table(self):
        for cfg in (config(top='log-format = "text"\n'), config(top='log-format = "text"   # the default\n'),
                    config().replace('[tart]\n', '[tart]\nlog-file = "x"\n')):
            with self.subTest(cfg=cfg[:200]):
                r = Rig(self, cfg=cfg)
                r.report()
                self.assertEqual(r.facts()['format'], 1)


if __name__ == '__main__':
    unittest.main()
