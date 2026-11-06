"""The updater's timer on the Linux host (S2b-3b-3; PLAN §4 "One timer per host user, every 10 minutes", D1, D11):
linux-docker/config/runner-updater.service and runner-updater.timer, the SAME two systemd user units for both host
users, and linux-docker/setup/04-timer.sh, the install step each user runs (linux-docker/README.md, Install step 11).

- The unit files, read STRICTLY (unit(): no systemd-analyze in the CI images or the local ones, so a strict key check,
  never a skip): Type=oneshot, ExecStart=%h/bin/runner-updater pass (Install step 10's link), TimeoutStartSec, every
  10 minutes by OnBootSec and OnUnitActiveSec, WantedBy=timers.target; no other section or key.
- 04-timer.sh as each user: the two files into ~/.config/systemd/user (0644, the shipped bytes), then `systemctl --user
  daemon-reload`, then `systemctl --user enable --now runner-updater.timer`, in that order; a second run rewrites no
  file; linger read only (`loginctl show-user`): none is a REFUSE with the root line (01-users.sh owns linger) and
  nothing written; so is a user other than RS_USER and RUN_USER, and a missing ~/bin/runner-updater.
- A pass started as the timer starts it (the installed ExecStart, %h expanded; cwd the user's home, as systemd starts a
  user service with no WorkingDirectory=, and / too: it needs no cwd; systemd's minimal environment, no terminal) runs,
  and while OFF (a fresh install, D11; no window journal and no enabled unit: RECOVER does not run, and THE OUTAGE RULE
  only reads the unit) it ends with exit 0 and writes no state; no header says an OFF pass "ends at once" (B2a review
  r1: RS_USER's runs RECOVER, the apply step and THE OUTAGE RULE first).

The unit-file cells read text and run anywhere; the others run the REAL 04-timer.sh and runner-updater in a throwaway
container (tests/hetzner/support.py: Pool), with systemctl and loginctl substitutes (TIMER_SYSTEMCTL, LOGINCTL) over the
Pool's own. The systemd stop of a pass during a build (TimeoutStartSec) is test_updater_build.py's.
"""
import json
import os
import re
import subprocess
import unittest

from tests.hetzner.support import REPO, Pool, needs_container

CONFIG = os.path.join(REPO, 'linux-docker', 'config')
README = os.path.join(REPO, 'linux-docker', 'README.md')
NAMES = ('runner-updater.service', 'runner-updater.timer')
UNITS = os.path.join(Pool.HOME, '.config', 'systemd', 'user')
STATE = os.path.join(Pool.STATE, 'state.json')
LINK = os.path.join(Pool.HOME, 'bin', 'runner-updater')
# The keys each file may hold, by section: every one is there, and no other
SCHEMA = {'runner-updater.service': {'Unit': {'Description'}, 'Service': {'Type', 'ExecStart', 'TimeoutStartSec'}},
          'runner-updater.timer': {'Unit': {'Description'}, 'Timer': {'OnBootSec', 'OnUnitActiveSec'},
                                   'Install': {'WantedBy'}}}
CALLS = ['--user daemon-reload', '--user enable --now runner-updater.timer', '--user is-active runner-updater.timer',
         '--user is-enabled runner-updater.timer']
# systemd's environment of a user service (the user manager's: `systemctl --user show-environment` on the host names
# these, and a service gets no terminal): what a timer's pass runs with
TIMER_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin'


def unit(text):
    """A systemd unit file read STRICTLY: {section: {key: value}}. Each line is blank, a comment (# or ; first), a
    [Section] line or Key=Value (a key of letters and digits, no space before or after the =); no line ends in a
    backslash (a continuation); no section or key comes twice; no key comes before the first section. Anything else
    raises ValueError with its line number."""
    out, sec = {}, None
    for i, line in enumerate(text.split('\n'), 1):
        if line.strip() == '' or line.lstrip()[0] in '#;':
            continue
        if line.endswith('\\'):
            raise ValueError('line %d: a continuation line' % i)
        m = re.fullmatch(r'\[([A-Za-z]+)\]', line)
        if m:
            if m.group(1) in out:
                raise ValueError('line %d: section %s twice' % (i, m.group(1)))
            sec = out[m.group(1)] = {}
            continue
        m = re.fullmatch(r'([A-Za-z][A-Za-z0-9]*)=(\S.*)', line)
        if not m:
            raise ValueError('line %d: neither a section, a Key=Value nor a comment: %r' % (i, line))
        if sec is None:
            raise ValueError('line %d: a key before the first section' % i)
        if m.group(1) in sec:
            raise ValueError('line %d: %s twice in its section' % (i, m.group(1)))
        sec[m.group(1)] = m.group(2)
    return out


def shipped(name):
    with open(os.path.join(CONFIG, name)) as f:
        return f.read()


def keys(u):
    return {s: set(kv) for s, kv in u.items()}


class Units(unittest.TestCase):
    def test_each_file_holds_its_keys_and_values_and_no_other(self):
        """The service: one pass (oneshot) of Install step 10's link, bounded by TimeoutStartSec (its comment says where
        the number comes from); the timer: every 10 minutes, counted from boot and from the last start, enabled by
        timers.target. No other key: a strict key check (no systemd-analyze where these cells run)."""
        s, t = unit(shipped(NAMES[0])), unit(shipped(NAMES[1]))
        self.assertEqual(keys(s), SCHEMA[NAMES[0]])
        self.assertEqual(keys(t), SCHEMA[NAMES[1]])
        # S2b-3c-1 D-g: 2 h, one file for both users: RS_USER's longest pass (RECOVER's drain 4260 s, its start 600 s
        # and 3 validate tries of 130 + 20 s: about 5310 s) fits, and RUN_USER's hanging build is cut every 2 h
        self.assertEqual((s['Service']['Type'], s['Service']['ExecStart'], s['Service']['TimeoutStartSec']),
                         ('oneshot', '%h/bin/runner-updater pass', '2h'))
        svc = shipped_text(NAMES[0])
        self.assertIn('5310', svc, 'the service comment does not say what the 2 h bound holds')
        self.assertEqual((t['Timer']['OnBootSec'], t['Timer']['OnUnitActiveSec'], t['Install']['WantedBy']),
                         ('10min', '10min', 'timers.target'))

    def test_control_the_reader_refuses_each_planted_defect(self):
        """The controls of the strict check: each defect planted in the shipped text is caught, by the reader or by
        the key compare; the shipped text itself passes both (the cell above)."""
        t = shipped(NAMES[1])
        for why, text in (
                ('a key misspelled', t.replace('OnUnitActiveSec=', 'OnUnitActivSec=')),
                ('a key twice', t.replace('OnBootSec=10min\n', 'OnBootSec=10min\nOnBootSec=5min\n')),
                ('a continuation line', t.replace('OnBootSec=10min\n', 'OnBootSec=10min \\\n  5min\n')),
                ('a section twice', t + '\n[Timer]\nAccuracySec=1s\n'),
                ('a key before the first section', 'OnBootSec=1min\n' + t),
                ('a line of another shape', t.replace('OnBootSec=10min\n', 'OnBootSec = 10min\n')),
                ('a section of another name', t.replace('[Install]', '[Installs]'))):
            with self.subTest(why):
                self.assertNotEqual(text, t, 'the defect was not planted')
                try:
                    caught = keys(unit(text)) != SCHEMA[NAMES[1]]
                except ValueError:
                    caught = True
                self.assertTrue(caught, text)

    def test_execstart_is_install_step_10_s_link(self):
        """ExecStart runs ~/bin/runner-updater (%h: the user's home), the link Install step 10 makes, so each pass runs
        this release's ~/build. Control: the README's link line names that path once."""
        with open(README) as f:
            links = [l for l in f.read().splitlines() if 'runner-updater ~/bin/runner-updater' in l]
        self.assertEqual(len(links), 1, links)
        self.assertIn(' ~/bin/runner-updater', links[0])
        self.assertEqual(unit(shipped(NAMES[0]))['Service']['ExecStart'].split()[0].replace('%h', '~'),
                         '~/bin/runner-updater')


# ---- 04-timer.sh and a pass as the timer starts it (a container)

TIMER_SYSTEMCTL = r'''#!/usr/bin/python3 -I
# systemctl, for the timer cells (tests/hetzner/test_timer.py): logs each call, one line of its arguments, to
# logs/systemctl.log. --user daemon-reload: 0. --user enable --now runner-updater.timer: 1 when ~/.config/systemd/user
# holds no runner-updater.timer (systemd's own refusal), else 0 and the timer is enabled and active from then on
# (timer.json). --user is-active / is-enabled runner-updater.timer: from timer.json. Any other call: 99.
import json, os, sys
SB = @SB@
a = sys.argv[1:]
with open(SB + '/logs/systemctl.log', 'a') as f:
    f.write(' '.join(a) + '\n')
p = SB + '/timer.json'
st = json.load(open(p)) if os.path.exists(p) else {'enabled': False, 'active': False}
if a == ['--user', 'daemon-reload']:
    sys.exit(0)
if a == ['--user', 'enable', '--now', 'runner-updater.timer']:
    if not os.path.isfile(os.path.join(os.environ['HOME'], '.config', 'systemd', 'user', 'runner-updater.timer')):
        sys.stderr.write('Failed to enable unit: Unit file runner-updater.timer does not exist.\n')
        sys.exit(1)
    st.update(enabled=True, active=True)
    with open(p + '.new', 'w') as f:
        json.dump(st, f)
    os.replace(p + '.new', p)
    sys.exit(0)
if a == ['--user', 'is-active', 'runner-updater.timer']:
    print('active' if st['active'] else 'inactive')
    sys.exit(0 if st['active'] else 3)
if a == ['--user', 'is-enabled', 'runner-updater.timer']:
    print('enabled' if st['enabled'] else 'disabled')
    sys.exit(0 if st['enabled'] else 1)
sys.stderr.write('systemctl stub: no answer for: %s\n' % ' '.join(a))
sys.exit(99)
'''

LOGINCTL = r'''#!/usr/bin/python3 -I
# loginctl, for the timer cells: logs each call to logs/loginctl.log; `show-user USER -p Linger --value` answers as
# loginctl.json says ({out, err, rc}); any other call: 99.
import json, sys
SB = @SB@
a = sys.argv[1:]
with open(SB + '/logs/loginctl.log', 'a') as f:
    f.write(' '.join(a) + '\n')
c = json.load(open(SB + '/loginctl.json'))
if len(a) == 5 and a[0] == 'show-user' and a[2:] == ['-p', 'Linger', '--value']:
    sys.stdout.write(c['out'])
    sys.stderr.write(c.get('err', ''))
    sys.exit(c['rc'])
sys.stderr.write('loginctl stub: no answer for: %s\n' % ' '.join(a))
sys.exit(99)
'''


def readme_line(marker):
    """The README's one line that holds MARKER, as the host runs it: `ssh <U>@<host> '…'` -> `bash -c '…'`."""
    with open(README) as f:
        lines = [l.strip() for l in f.read().splitlines() if marker in l]
    if len(lines) != 1:
        raise AssertionError('the README holds %d lines with %r, want 1: %r' % (len(lines), marker, lines))
    here = re.sub(r"^ssh <(RS_USER|RUN_USER)>@<host> '", "bash -c '", lines[0])
    if re.search(r'<[A-Za-z_ ]+>', here):
        raise AssertionError('a placeholder this cell does not fill: %r' % here)
    return here


class Rig:
    """A Pool as RS_USER (role 'run': RUN_USER alone, Pool.run_user), with the timer cells' substitutes over the Pool's
    own: systemctl (TIMER_SYSTEMCTL) and loginctl (LOGINCTL, answering LINGER: (out, rc, err)); with LINK, Install step
    10's link ~/bin/runner-updater, made by the README's own line."""

    def __init__(self, test, role='rs', linger=('yes\n', 0, ''), link=True):
        self.t = test
        self.p = p = Pool(test)
        if role == 'run':
            p.run_user()
        sb = repr(p.root)
        p.write(p.path('stubs', 'systemctl'), TIMER_SYSTEMCTL.replace('@SB@', sb), 0o755)
        p.write(p.path('stubs', 'loginctl'), LOGINCTL.replace('@SB@', sb), 0o755)
        self.linger(*linger)
        if link:
            r = self.bash(readme_line('runner-updater ~/bin/runner-updater'))
            test.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        p.files()

    def linger(self, out, rc=0, err=''):
        self.p.write(self.p.path('loginctl.json'), json.dumps({'out': out, 'rc': rc, 'err': err}))

    def bash(self, line):
        return subprocess.run(['bash', '-c', line], env=self.p.env(), cwd=Pool.HOME, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=120)

    def install(self):
        """Install step 11: the README's line."""
        return self.bash(readme_line("'bash ~/build/setup/04-timer.sh'"))

    def ok(self):
        r = self.install()
        self.t.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def calls(self):
        return self.p.lines('systemctl')

    def files(self):
        """{name: (sha256 of its bytes, mtime_ns, inode, mode)} of ~/.config/systemd/user's files ({} with no folder)."""
        out = {}
        if os.path.isdir(UNITS):
            for n in sorted(os.listdir(UNITS)):
                s = os.lstat(os.path.join(UNITS, n))
                with open(os.path.join(UNITS, n), 'rb') as f:
                    out[n] = (f.read(), s.st_mtime_ns, s.st_ino, s.st_mode & 0o7777)
        return out


@needs_container
class Install(unittest.TestCase):
    def test_the_files_land_with_their_mode_and_bytes_then_reload_then_enable(self):
        """Both users (the SAME files): each file is the shipped one, byte for byte, mode 0644, a plain file; the calls
        are daemon-reload, then enable --now runner-updater.timer, then the two reads that check it took."""
        for role in ('rs', 'run'):
            with self.subTest(role):
                g = Rig(self, role=role)
                r = g.ok()
                self.assertIn('04 DONE (root)', r.stdout)
                files = g.files()
                self.assertEqual(sorted(files), sorted(NAMES))
                for n in NAMES:
                    self.assertEqual(files[n][0], shipped(n).encode(), n)
                    self.assertEqual(files[n][3], 0o644, n)
                    self.assertFalse(os.path.islink(os.path.join(UNITS, n)))
                self.assertEqual(g.calls(), CALLS)
                self.assertEqual(g.p.lines('loginctl'), ['show-user root -p Linger --value'])

    def test_a_second_run_changes_nothing_and_a_changed_file_is_replaced(self):
        """A second run rewrites no file (the same bytes, mtime, inode and mode) and makes the same calls (they
        converge: a run cut after a write is finished by the next). Control: a file of another release (its ~/build
        copy changed) and one of another mode are each replaced, by rename (a new inode)."""
        g = Rig(self)
        g.ok()
        first = g.files()
        g.ok()
        self.assertEqual(g.files(), first)
        self.assertEqual(g.calls(), CALLS + CALLS)
        with open(os.path.join(g.p.build, 'config', NAMES[1]), 'a') as f:          # the control: a new release's file
            f.write('# a later release\n')
        os.chmod(os.path.join(UNITS, NAMES[0]), 0o600)                             # and a mode changed by hand
        g.ok()
        now = g.files()
        self.assertTrue(now[NAMES[1]][0].endswith(b'# a later release\n'))
        for n in NAMES:
            self.assertNotEqual(now[n][2], first[n][2], '%s: not replaced by rename' % n)
            self.assertEqual(now[n][3], 0o644, n)

    def test_no_linger_refuses_with_the_root_line_and_writes_nothing(self):
        """A user manager with no linger stops at the user's last logout, and its timer with it: REFUSE, the root line
        (01-users.sh, Install step 2, owns linger: this step only reads it), nothing written, no systemctl call.
        Control: linger yes installs."""
        for why, answer in (('Linger=no', ('no\n', 0, '')),
                            ('loginctl cannot answer', ('', 1, 'Failed to get user: User root is not logged in or '
                                                               'lingering\n')),
                            ('another answer', ('yes\nno\n', 0, ''))):
            with self.subTest(why):
                g = Rig(self, linger=answer)
                r = g.install()
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('04-timer.sh: REFUSE root has no linger', r.stdout)
                self.assertIn("ssh root@<host> 'bash -s' < linux-docker/setup/01-users.sh", r.stdout)
                self.assertFalse(os.path.lexists(UNITS), 'it wrote')
                self.assertEqual(g.calls(), [])
        g = Rig(self)                                                              # the control
        self.assertIn('04 DONE (root)', g.ok().stdout)

    def test_without_install_step_10_s_link_it_refuses_and_writes_nothing(self):
        """ExecStart runs ~/bin/runner-updater: with no link, every timer pass would fail. REFUSE, nothing written.
        Control: the link made, it installs."""
        g = Rig(self, link=False)
        r = g.install()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('04-timer.sh: REFUSE %s is not there' % LINK, r.stdout)
        self.assertIn('Install step 10', r.stdout)
        self.assertFalse(os.path.lexists(UNITS))
        self.assertEqual(g.calls(), [])
        r = g.bash(readme_line('runner-updater ~/bin/runner-updater'))            # the control
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('04 DONE (root)', g.ok().stdout)

    def test_a_user_other_than_rs_user_and_run_user_is_refused(self):
        g = Rig(self)
        conf = g.p.read(g.p.path('host.conf'))
        g.p.write(g.p.path('host.conf'), conf.replace('\nRUN_USER=root\n', '\nRUN_USER=ci-run\n')
                  .replace('\nRS_USER=root\n', '\nRS_USER=ci-rs\n'), 0o644)
        r = g.install()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('04-timer.sh: REFUSE run me as ci-rs or ci-run', r.stdout)
        self.assertFalse(os.path.lexists(UNITS))
        self.assertEqual((g.calls(), g.p.lines('loginctl')), ([], []))
        g.p.write(g.p.path('host.conf'), conf, 0o644)                             # the control
        g.ok()


@needs_container
class TimerPass(unittest.TestCase):
    def execstart(self):
        """The INSTALLED service's ExecStart, %h expanded to the user's home: the argv systemd runs (no shell)."""
        with open(os.path.join(UNITS, NAMES[0])) as f:
            line = unit(f.read())['Service']['ExecStart']
        return line.replace('%h', Pool.HOME).split()

    def timer_run(self, g, cwd):
        env = {'HOME': Pool.HOME, 'USER': 'root', 'LOGNAME': 'root', 'SHELL': '/bin/sh', 'PATH': TIMER_PATH,
               'XDG_RUNTIME_DIR': g.p.path('xdg')}
        return subprocess.run(self.execstart(), env=env, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=300, start_new_session=True)

    def test_a_pass_as_the_timer_starts_it_runs_and_ends_at_once_while_off(self):
        """A fresh install is OFF (D11): the timer's pass of each user, as systemd starts it (cwd the user's home: a
        user service with no WorkingDirectory= runs there, systemd.exec; and / too, which shows it needs no cwd; the
        user manager's environment, no terminal), runs its ExecStart, ends at once with exit 0, asks GitHub nothing and
        writes no state. Control: without Install step 10's link, the same ExecStart cannot start."""
        for role in ('rs', 'run'):
            for cwd in (Pool.HOME, '/'):
                with self.subTest(role=role, cwd=cwd):
                    g = Rig(self, role=role)
                    g.ok()
                    r = self.timer_run(g, cwd)
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertIn('runner-updater: pass: the updater is OFF: nothing to do', r.stdout)
                    self.assertFalse(os.path.lexists(STATE), 'a pass while OFF wrote a state')
                    self.assertEqual(g.p.gh.seen, [])
                    os.remove(LINK)                                               # the control
                    with self.assertRaises(FileNotFoundError):
                        self.timer_run(g, cwd)


def readme():
    with open(README) as f:
        return f.read()


def shipped_text(name):
    with open(os.path.join(CONFIG, name)) as f:
        return f.read()


def section(text, title):
    return text.split('\n## %s\n' % title, 1)[1].split('\n## ', 1)[0]


def header(rel):
    with open(os.path.join(REPO, 'linux-docker', rel)) as f:
        return ' '.join(l.lstrip('#').strip() for l in f.read().split('\nset -uo pipefail\n', 1)[0].splitlines())


class Text(unittest.TestCase):
    def test_the_script_s_header_names_what_it_does_and_refuses(self):
        h = header('setup/04-timer.sh')
        for s in ('RS_USER', 'RUN_USER', '~/.config/systemd/user', '0644', 'daemon-reload',
                  'enable --now runner-updater.timer', 'linger', '01-users.sh', 'D11', 'Install step 10',
                  'Install step 11'):
            self.assertIn(s, h)

    def test_install_step_11_installs_the_timer_for_each_user_after_step_10(self):
        """The README's Install: step 11, after step 10, runs 04-timer.sh as RS_USER, then the same line as RUN_USER.
        Control: step 10 is still the link's."""
        ins = section(readme(), 'Install')
        self.assertRegex(ins, r"(?s)\n10\. \*\*The updater \(RS_USER and RUN_USER\)\.\*\*.*\n11\. \*\*The updater's "
                              r"timer \(RS_USER and RUN_USER\)\.\*\*.*ssh <RS_USER>@<host> 'bash "
                              r"~/build/setup/04-timer\.sh'.*Then the same line with `<RUN_USER>`")
        self.assertIn('runner-updater ~/bin/runner-updater', ins.split('\n11. ', 1)[0].split('\n10. ', 1)[1])

    def test_the_updater_section_says_what_the_timer_does_how_to_see_it_and_how_to_stop_it(self):
        sec = section(readme(), 'The updater: status, on, off, pass, build')
        for s in ('every 10 minutes', 'Install step 11', 'systemctl --user list-timers', 'journalctl --user -u '
                  'runner-updater', 'runner-updater off', 'systemctl --user disable --now runner-updater.timer',
                  "RUN_USER's record"):
            self.assertIn(s, sec)
        for s in ('There is no timer yet', 'what the timer will run', 'a timer (a later release)'):
            self.assertNotIn(s, sec)
        self.assertNotIn('its timer comes in a later release', readme())

    def test_every_path_to_this_release_sends_a_host_to_install_step_11(self):
        """As Install step 10 (test_updater.py's cell for it): a host that gets this release by a release update, the
        upgrade notes, or a move from a hand copy, also gets its timer. Control: step 11 is Install's own."""
        text = readme()
        release = section(text, 'A new runner release')
        for why, part in (('A new runner release, its first paragraph', release.strip().split('\n\n', 1)[0]),
                          ('the upgrade notes', section(text, 'Upgrading from a release before this one')),
                          ('a hand copy', section(text, 'A host that already runs these scripts from a hand copy'))):
            with self.subTest(why):
                self.assertIn('Install step 11', part)
        self.assertIn("\n11. **The updater's timer", section(text, 'Install'))

    def test_the_files_table_names_the_timer(self):
        text = readme()
        self.assertIn('| `setup/04-timer.sh` | RS_USER, RUN_USER |', text)
        row = [l for l in text.splitlines() if l.startswith('| `config/` |')]
        self.assertEqual(len(row), 1)
        self.assertIn('runner-updater', row[0])

    def test_no_header_says_an_off_pass_ends_at_once(self):
        """B2a review r1, Opus F3 and Codex F3: RS_USER's pass while OFF runs RECOVER FIRST, THE APPLY STEP and THE
        OUTAGE RULE (it may end a window a cut left, start runscaler and write the state, and it exits 1 while a
        journal stays), so neither the updater's header nor the timer's nor 04-timer.sh's says that an OFF pass "ends
        at once", that the timer "starts nothing" until `on`, or that "nothing acts while OFF"; each names what it runs.
        The control: the matcher finds the sentence they held at 771ab99."""
        old = re.compile(r'(?i)(while (the updater is )?OFF ends at once|timer starts nothing|nothing acts while OFF)')
        self.assertRegex('A fresh install is OFF (D11): a pass while OFF ends at once.', old)   # the control
        for name, text in (('bin/runner-updater', header('bin/runner-updater')),
                           ('config/runner-updater.timer', shipped_text('runner-updater.timer')),
                           ('setup/04-timer.sh', header('setup/04-timer.sh'))):
            with self.subTest(name):
                one = ' '.join(text.replace('#', ' ').split())
                self.assertNotRegex(one, old)
                for s in ('RECOVER', 'THE OUTAGE RULE'):
                    self.assertIn(s, one)

    def test_no_header_says_an_off_pass_with_recover_asks_github_nothing(self):
        """B2a review r2, Opus F3 (B2a CLOSED): RECOVER, which RS_USER's OFF pass runs first, may validate a config
        (runner-start validate checks the GitHub API: bin/validate-class's API-ONLY) and start runscaler (which
        connects to GitHub). So no OFF sentence of the updater's header, the timer's or 04-timer.sh's says that an OFF
        pass makes "no GitHub call" or "asks the core and GitHub nothing": each says that the updater ITSELF asks
        them nothing, and that RECOVER may validate a config and start runscaler, which do. The control: the matcher
        finds the sentences of daa3ee8 (:129 and :12)."""
        old = re.compile(r'(?i)(no GitHub call|(?<!itself )asks the core and GitHub nothing)')
        for s in ('OFF: "the updater is OFF", exit 0, no core call and no GitHub call (THE OUTAGE RULE\'s /healthz '
                  'pair is runscaler\'s, on 127.0.0.1).',
                  'a pass while OFF measures nothing, asks the core and GitHub nothing and builds nothing'):   # control
            self.assertRegex(s, old)
        for name, text in (('bin/runner-updater', header('bin/runner-updater')),
                           ('config/runner-updater.timer', shipped_text('runner-updater.timer')),
                           ('setup/04-timer.sh', header('setup/04-timer.sh'))):
            with self.subTest(name):
                one = ' '.join(text.replace('#', ' ').split())
                self.assertNotRegex(one, old)
                self.assertIn('the updater itself asks the core and GitHub nothing', one)
                self.assertIn('RECOVER may validate a config', one)
                self.assertIn('start runscaler, which both reach GitHub', one)

    def test_the_updater_s_header_names_its_timer_and_the_stop_of_its_unit(self):
        h = header('bin/runner-updater')
        for s in ('config/runner-updater.timer', 'setup/04-timer.sh', 'TimeoutStartSec', 'every process of the unit',
                  "RUN_USER's record", 'rr_read', 'as RUN_USER'):
            self.assertIn(s, h)
        self.assertNotIn('the timers are a later release', h)


    def test_the_unit_and_the_readme_say_where_and_when_a_pass_runs(self):
        """Codex F6 (fix round 1): a user service with no WorkingDirectory= runs in the user's home (systemd.exec), not
        in /; the first pass after `enable --now` comes at once only when the boot is 10 minutes past, else 10 minutes
        after the boot (OnBootSec). Control: the timer's header still says when the first pass comes at once."""
        svc = shipped_text('runner-updater.service')
        self.assertNotIn('systemd runs it in /', svc)
        self.assertIn('WorkingDirectory=', svc)
        self.assertIn("the user's home", svc)
        text = readme()
        self.assertNotRegex(text, r'the first time at once(?! when the host has been up for 10 minutes)')
        for part in (section(text, 'Install').split("\n11. **The updater's timer", 1)[1].split('\n## ', 1)[0],
                     section(text, 'The updater: status, on, off, pass, build')):
            self.assertIn('10 minutes after a boot', part)
        self.assertIn('at once', shipped_text('runner-updater.timer'))                          # the control

    def test_the_unit_and_the_readme_say_what_systemd_s_sigkill_leaves(self):
        """Codex F5 (fix round 1): after the TERM of a stop, systemd sends SIGKILL at TimeoutStopSec (the unit's, or
        the manager's default): then no CUT line, the build context may stay, the lock is free once every holder has
        exited, and the state stays valid (it is written by rename). CUT is not unconditional. Control: the CUT of a
        cooperative stop is still named."""
        for name, part in (('runner-updater.service', shipped_text('runner-updater.service')),
                           ('README, The updater', section(readme(), 'The updater: status, on, off, pass, build'))):
            with self.subTest(name):
                one = ' '.join(part.replace('#', ' ').split())
                for s in ('TimeoutStopSec', 'SIGKILL', 'no CUT line', 'build context', 'every holder', 'rename'):
                    self.assertIn(s, one)
                self.assertIn('CUT', one.replace('no CUT line', ''))                            # the control

    def test_the_uninstall_s_before_list_stops_the_updater_as_each_user(self):
        """Opus F3 (fix round 1): 01-users-undo.sh's pre-flight refuses while a user has a process (a timer's pass), so
        its header's BEFORE list, which the README's Uninstall sends a person to, names the updater: `runner-updater
        off` and `systemctl --user disable --now runner-updater.timer`, as each user. Control: it still names
        runscaler's and docker's stops."""
        h = header('setup/01-users-undo.sh')
        before = h.split('BEFORE it', 1)[1].split('PRE-FLIGHT', 1)[0]
        self.assertRegex(before, r'as RS_USER and as RUN_USER,? `runner-updater off` and `systemctl --user disable '
                                 r'--now runner-updater\.timer`')
        for s in ('`systemctl --user disable --now runscaler`', '`systemctl --user disable --now docker`'):  # control
            self.assertIn(s, before)


if __name__ == '__main__':
    unittest.main()
