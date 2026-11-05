"""RUN_USER's updater state goes by the build records' channel (S2b-3b-3 fix round 1; PLAN D1, "Hetzner: one record per
user", its 11-05 line), so RS_USER's `status` can print it (D7): RUN_USER's state.json is 0640, group RUN_USER; each
folder from RUN_USER's home to its STATEDIR (~/.local/state/runner-updater) gives the group search (x) and gives others
nothing they did not have; RS_USER's STATEDIR stays 0700 and its state.json 0600 (no channel from RS_USER to RUN_USER);
the lock file, PASSDIR and RR_DIR stay private. ONE place decides those modes by the user's role: runner-release.sh's
rr_lock, which every holder of the updater lock runs (both users' updaters, 02-d1.sh in both modes; pool-image.sh's
unattended modes take none: they are the updater's child, S2b-3c-1 D-a), and
the updater writes its state with the mode rr_lock named. A folder made there gets its mode set, never the umask's or
coreutils' own (install -d made parents 0700 on Ubuntu 26.04 and 0755 on 24.04, measured).

These cells run as TWO REAL non-root users in a throwaway container (RealUsers), never root standing in for both: a
mode that keeps RS_USER out is EACCES only for a real user. The users are made by a copy of the REAL 01-users.sh (its
shape: RS_USER in group RUN_USER, the only member; homes 0750); each has its own ~/build, the cell's copy of
linux-docker/ (support.Sandbox: only the pin lines rewritten). After each writer of RUN_USER's (its first OFF timer pass
on a home with no ~/.local, on, off, a STOP written and cleared, a build pass, a person's `build V`, `02-d1.sh build V`
and the full 02-d1.sh run, with the Sandbox's substitutes for their outside calls, a pass that finds the lock held, a
folder left with the old modes), RS_USER's `status` shows RUN_USER's record (ON, OFF, or a fresh install), never
"it cannot be read". Control: RS_USER's own writers leave its folders 0700 and its state 0600.
"""
import fcntl
import os
import pwd
import re
import secrets
import shutil
import subprocess
import time
import unittest

from tests.hetzner.support import HANG, REPO, SYSTEM_PATH, Sandbox, iso, needs_container, tarball

V = '2.339.0'
OLD = '2.338.2'                                   # host.conf.example's RUNNER_VERSION: the full run's
D = '.local/state/runner-updater'                 # STATEDIR, in a home
CHAIN = ('.local', '.local/state', D)             # each folder from the home to STATEDIR
MARK = '/var/lib/liveapp-ci'                      # 01-users.sh's MARK
TMPFILES = '/etc/tmpfiles.d/liveapp-runner-lock.conf'
R1_STUBS = {                                      # 01-users.sh's outside calls (tests/hetzner/test_users.py's)
    'systemctl': 'case $1 in is-active) echo active ;; esac\nexit 0',
    'systemd-tmpfiles': 'exit 0',
    'loginctl': 'exit 0',
    'sudo': 'exit 1',
}


def exists(user):
    return subprocess.run(['id', user], capture_output=True, stdin=subprocess.DEVNULL).returncode == 0


def mode(path):
    return os.lstat(path).st_mode & 0o7777


class RealUsers:
    """Two REAL users of this container, made by the copied 01-users.sh (run as root): RUN, then RS in group RUN; their
    names are the cell's own (and the host config's RUN_USER and RS_USER). Each has ~/build, the Sandbox's copy of
    linux-docker/, owned by that user. RUN's runs reach the Sandbox's substitutes (docker, curl, systemctl, nsenter, ip)
    and its local GitHub, which serves V (the latest, 3 days old, and by its tag) and OLD (the full run's version)."""

    def __init__(self, test):
        self.t = test
        self.sb = sb = Sandbox(test)
        t = secrets.token_hex(3)
        self.rs, self.run = 'hz%s-rs' % t, 'hz%s-run' % t
        for u in (self.rs, self.run):
            if exists(u):
                test.fail('the user %s is already there: these cells make their own users' % u)
        with open(sb.path('host.conf')) as f:
            conf = f.read()
        for k, old, new in (('RUN_USER', 'root', self.run), ('RS_USER', 'ci-rs', self.rs)):
            line = '\n%s=%s\n' % (k, old)
            if conf.count(line) != 1:
                raise AssertionError('host.conf: no single %s line' % line.strip())
            conf = conf.replace(line, '\n%s=%s\n' % (k, new))
        sb.write(sb.path('host.conf'), conf, 0o644)
        for n, body in R1_STUBS.items():
            sb.write(sb.path('stubs', n),
                     '#!/bin/sh\nprintf "%%s\\n" "$*" >> %s/logs/%s.log\n%s\n' % (sb.root, n, body), 0o755)
        made = {p: os.path.lexists(p) for p in (MARK, TMPFILES)}

        def clean():
            for u in (self.rs, self.run):           # RS_USER first: the only member of RUN_USER's group
                if exists(u):
                    subprocess.run(['userdel', '-r', u], capture_output=True, stdin=subprocess.DEVNULL)
                if subprocess.run(['getent', 'group', u], capture_output=True).returncode == 0:
                    subprocess.run(['groupdel', u], capture_output=True, stdin=subprocess.DEVNULL)
                for p in (os.path.join(MARK, 'r1-created-' + u), '/home/' + u):
                    if os.path.isdir(p) and not os.path.islink(p):
                        shutil.rmtree(p, True)
                    elif os.path.lexists(p):
                        os.remove(p)
            if not made[TMPFILES] and os.path.lexists(TMPFILES):
                os.remove(TMPFILES)
            if not made[MARK] and os.path.isdir(MARK) and not os.listdir(MARK):
                os.rmdir(MARK)
        test.addCleanup(clean)
        r = subprocess.run(['bash', os.path.join(sb.build, 'setup', '01-users.sh')], env=sb.env(), cwd='/',
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
        out = r.stdout.splitlines()
        for want in ('OK   %s groups = %s %s' % (self.rs, self.rs, self.run),
                     'OK   %s groups = %s' % (self.run, self.run),
                     "OK   group %s members = %s (D1 socket's access list)" % (self.run, self.rs),
                     'OK   %s home 750 %s:%s' % (self.rs, self.rs, self.rs),
                     'OK   %s home 750 %s:%s' % (self.run, self.run, self.run)):
            test.assertIn(want, out, '01-users.sh did not make the two users: ' + r.stdout[-3000:] + r.stderr)
        self.ids = {u: (pwd.getpwnam(u).pw_uid, pwd.getpwnam(u).pw_gid) for u in (self.rs, self.run)}
        # the Sandbox: its root, logs and temp folder reachable by both users; RUN's substitutes write their state into
        # the root (docker-state.json); the host config stays root's, 0644
        os.chmod(sb.root, 0o755)
        os.chown(sb.root, *self.ids[self.run])
        for d in ('logs', 'tmp'):
            os.chmod(sb.path(d), 0o1777)
        for u in (self.rs, self.run):
            b = self.home(u, 'build')
            shutil.copytree(sb.build, b, symlinks=True)
            subprocess.run(['chown', '-R', '%s:%s' % (u, u), b], check=True, stdin=subprocess.DEVNULL)
        # what 02-d1.sh's full run reads of D1 (steps 2 and 7): its socket in ~/run and rootlesskit's pid file
        xdg = sb.path('xdg-run')
        os.makedirs(os.path.join(xdg, 'dockerd-rootless'))
        sb.write(os.path.join(xdg, 'dockerd-rootless', 'child_pid'), '1\n')
        run = self.home(self.run, 'run')
        os.makedirs(run)
        os.chmod(run, 0o750)
        sb.write(os.path.join(run, 'docker.sock'), '', 0o660)
        subprocess.run(['chown', '-R', '%s:%s' % (self.run, self.run), xdg, run], check=True,
                       stdin=subprocess.DEVNULL)
        self.tgz = {v: tarball(v) for v in (V, OLD)}
        sb.gh.release(V, self.tgz[V])
        sb.gh.release(V, self.tgz[V], latest=True, published=iso(int(time.time()) - 3 * 86400))
        sb.gh.release(OLD, self.tgz[OLD])
        self.version(V)

    def home(self, user, *rel):
        return os.path.join('/home', user, *rel)

    def version(self, v):
        """The runner version the docker substitute reads from an image (02-d1.sh's check after the push)."""
        self.sb.docker['config_version'] = '[RUNNER 2026-11-02 12:00:00Z INFO Runner] a log line\n%s\n' % v

    def as_user(self, user, *argv):
        """argv as USER (runuser: its uid, its groups), with the environment a person's ssh or the timer gives (HOME,
        the substitutes first on PATH), umask 022 (a person's ssh: the updater sets its own), bounded by timeout (124:
        it HUNG)."""
        self.sb.files()
        env = ['HOME=/home/' + user, 'USER=' + user, 'LOGNAME=' + user, 'LC_ALL=C',
               'PATH=%s:%s' % (self.sb.path('stubs'), SYSTEM_PATH), 'TMPDIR=' + self.sb.path('tmp'),
               'XDG_RUNTIME_DIR=' + self.sb.path('xdg-run' if user == self.run else 'tmp')]
        r = subprocess.run(['timeout', '-k', '10', str(HANG), 'runuser', '-u', user, '--', 'env', '-i'] + env
                           + ['sh', '-c', 'umask 022 && exec "$@"', 'sh'] + list(argv), cwd='/',
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=HANG + 60)
        self.t.assertNotEqual(r.returncode, 124, 'HUNG: %s: %s' % (argv, r.stdout[-2000:] + r.stderr))
        return r

    def upd(self, user, *args):
        return self.as_user(user, self.home(user, 'build', 'bin', 'runner-updater'), *args)

    def d1(self, *args, user=None):
        """The copied 02-d1.sh as RUN_USER (or USER, from its own ~/build), as a person runs it over ssh (`bash
        ~/build/setup/02-d1.sh ...`)."""
        user = user or self.run
        return self.as_user(user, 'bash', self.home(user, 'build', 'setup', '02-d1.sh'), *args)

    def outside(self):
        """What the Sandbox's substitutes and its local GitHub saw: {log name: its text} and the requests."""
        d = self.sb.path('logs')
        logs = {}
        for n in sorted(os.listdir(d)):
            with open(os.path.join(d, n), 'rb') as f:
                logs[n] = f.read()
        return logs, list(self.sb.gh.seen)

    def write_as(self, user, rel, text, m):
        """A file of USER's home written as that user would (owned by it), with mode m."""
        p = self.home(user, rel)
        self.sb.write(p, text, m)
        os.chown(p, *self.ids[user])

    def record(self, why):
        """RS_USER's status: exit 0 (RS_USER's own), and RUN_USER's block, its lines without their prefix."""
        r = self.upd(self.rs, 'status')
        self.t.assertEqual(r.returncode, 0, 'after %s: %s' % (why, r.stdout[-3000:] + r.stderr))
        pre = 'runner-updater: as %s: ' % self.run
        return [l[len(pre):] for l in r.stdout.splitlines() if l.startswith(pre)]

    def shown(self, why, word):
        """After WHY, RS_USER's status shows RUN_USER's record: `the updater is ON|OFF (its record: …)`, or (word
        'fresh') no file yet, a fresh install, OFF. Never "it cannot be read". Returns the block."""
        st = self.home(self.run, D, 'state.json')
        lines = self.record(why)
        want = ('status: the updater is OFF (no record: %s is not there: a fresh install)' % st if word == 'fresh'
                else 'status: the updater is %s (its record: %s)' % (word, st))
        self.t.assertEqual(lines[:1], [want], 'after %s, RS_USER sees: %s' % (why, lines))
        return lines

    def run_modes(self, why, had=None):
        """RUN_USER's modes after WHY: STATEDIR 0710 (set at each lock take); each parent of it that the home did not
        have before 0710, and one it had (HAD: {rel: its mode then}) every bit it had and the group's search; the
        state 0640 of RUN_USER's group; every other entry of STATEDIR private (no bit for the group or others: the
        lock, PASSDIR, BUILDOUT, a state.json.new); the lock 0600; RR_DIR 0700."""
        h = self.home(self.run)
        uid, gid = self.ids[self.run]
        had = had or {}
        for rel in CHAIN:
            m = mode(os.path.join(h, rel))
            want = had[rel] | 0o010 if rel in had and rel != D else 0o710
            self.t.assertEqual(m, want, 'after %s: ~/%s is %o, want %o' % (why, rel, m, want))
        sd = os.path.join(h, D)
        for n in sorted(os.listdir(sd)):
            s = os.lstat(os.path.join(sd, n))
            self.t.assertEqual(s.st_uid, uid, 'after %s: %s is not RUN_USER\'s' % (why, n))
            if n == 'state.json':
                self.t.assertEqual((s.st_mode & 0o7777, s.st_gid), (0o640, gid), 'after %s: the state is %o, gid %d'
                                   % (why, s.st_mode & 0o7777, s.st_gid))
            else:
                self.t.assertEqual(s.st_mode & 0o077, 0, 'after %s: ~/%s/%s is %o: not private' % (
                    why, D, n, s.st_mode & 0o7777))
        self.t.assertEqual(mode(os.path.join(sd, 'lock')), 0o600, 'after %s: the lock' % why)
        rr = os.path.join(h, '.cache', 'liveapp-ci')
        if os.path.lexists(rr):
            self.t.assertEqual(mode(rr), 0o700, 'after %s: RR_DIR' % why)

    def rs_modes(self, why):
        """RS_USER's modes after WHY: its folders made here 0700, its state 0600, its lock 0600; RUN_USER can read
        neither."""
        h = self.home(self.rs)
        for rel in CHAIN:
            self.t.assertEqual(mode(os.path.join(h, rel)), 0o700, 'after %s: RS_USER\'s ~/%s' % (why, rel))
        st = os.path.join(h, D, 'state.json')
        if os.path.lexists(st):
            self.t.assertEqual(mode(st), 0o600, 'after %s: RS_USER\'s state' % why)
        self.t.assertEqual(mode(os.path.join(h, D, 'lock')), 0o600, 'after %s: RS_USER\'s lock' % why)
        for p in (os.path.join(h, D), st):
            r = self.as_user(self.run, 'test', '-r', p)
            self.t.assertEqual(r.returncode, 1, 'after %s: RUN_USER can read %s' % (why, p))

    def hold(self, user):
        """USER's updater lock, held by THIS process (another open of the file: another holder), until the cell ends.
        The lock file is the one USER's updater made (its mode is not this process's to set)."""
        fd = os.open(self.home(user, D, 'lock'), os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.t.addCleanup(os.close, fd)
        return fd


def ok(t, r, why):
    t.assertEqual(r.returncode, 0, '%s: %s' % (why, r.stdout[-3000:] + r.stderr))
    return r


@needs_container
class RunUsersRecord(unittest.TestCase):
    def test_after_each_updater_writer_rs_user_reads_run_user_s_record(self):
        """RUN_USER's updater, from a home with no ~/.local: its first timer pass (OFF: it makes the folders and the
        lock, and writes no state), on, a build pass that fails (a STOP written), a person's `build V` that passes (the
        STOP cleared), off, a pass that finds the lock held. After each, RS_USER's status reads RUN_USER's record, and
        the modes are the decision's. On ee8a1f7 the first pass made STATEDIR 0700 (and the state 0600): "it cannot be
        read"."""
        g = RealUsers(self)
        self.assertFalse(os.path.lexists(g.home(g.run, '.local')))
        g.shown('nothing yet', 'fresh')                                       # the control: before any writer
        r = ok(self, g.upd(g.run, 'pass'), 'the first timer pass')
        self.assertIn('runner-updater: pass: the updater is OFF: nothing to do', r.stdout)
        g.shown('the first timer pass', 'fresh')
        g.run_modes('the first timer pass')
        ok(self, g.upd(g.run, 'on'), 'on')
        g.shown('on', 'ON')
        g.run_modes('on')
        g.sb.docker['build_rc'] = 1                                          # 02-d1.sh's docker build fails
        r = g.upd(g.run, 'pass')
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertIn('runner-updater: STOP check failed (runner %s)' % V, r.stdout)
        lines = g.shown('a STOP written', 'ON')
        g.run_modes('a STOP written')
        # RS_USER's status names the STOP and its next step, never its text (fix round 2): RUN_USER's own shows it
        self.assertIn('hz-docker: STOP check failed (runner %s): its cause: as %s, `runner-updater status` shows it. '
                      'Next: as %s: `runner-updater build %s`' % (V, g.run, g.run, V), lines)
        self.assertEqual([l for l in lines if 'FAIL' in l], [], lines)
        own = ok(self, g.upd(g.run, 'status'), "RUN_USER's own status")
        self.assertIn('hz-docker: STOP check failed (runner %s): FAIL docker build failed: no record, image.ref NOT '
                      'changed. Next: as %s: `runner-updater build %s`' % (V, g.run, V), own.stdout.splitlines())
        del g.sb.docker['build_rc']
        r = ok(self, g.upd(g.run, 'build', V), 'build V')
        self.assertIn('runner-updater: build: the STOP check failed of runner %s is cleared' % V, r.stdout)
        lines = g.shown('a person\'s build V', 'ON')
        g.run_modes('a person\'s build V (the STOP cleared)')
        self.assertEqual([l for l in lines if 'STOP' in l and 'ok (0 STOPs)' not in l], [], lines)
        ok(self, g.upd(g.run, 'off'), 'off')
        g.shown('off', 'OFF')
        g.run_modes('off')
        g.hold(g.run)
        r = ok(self, g.upd(g.run, 'pass'), 'a pass that finds the lock held')
        self.assertIn('another run holds the updater lock', r.stdout)
        g.shown('a pass that finds the lock held', 'OFF')
        g.run_modes('a pass that finds the lock held')

    def test_a_build_pass_that_builds_and_rs_user_reads_the_record(self):
        """RUN_USER's build pass (ON) that builds V with the copied 02-d1.sh as its child (its own rr_lock on the
        inherited lock), and writes BUILDOUT and PASSDIR: RS_USER reads RUN_USER's record after it; BUILDOUT and PASSDIR
        stay private."""
        g = RealUsers(self)
        ok(self, g.upd(g.run, 'on'), 'on')
        r = ok(self, g.upd(g.run, 'pass'), 'a build pass')
        self.assertIn('runner-updater: pass: built runner %s' % V, r.stdout)
        self.assertTrue(os.path.exists(g.home(g.run, D, 'build.out')))
        self.assertTrue(os.path.isdir(g.home(g.run, D, 'pass')))
        g.shown('a build pass', 'ON')
        g.run_modes('a build pass')

    def test_02_d1_sh_first_then_its_build_and_rs_user_reads_the_record(self):
        """02-d1.sh as the FIRST writer of a home with no ~/.local (a fresh host's Install runs it before any timer),
        as a person runs it over ssh (umask 022): its full run, then `02-d1.sh build V`. Each takes the updater lock
        and so makes RUN_USER's folders; after each, the modes are the decision's (the lock 0600 under umask 022 too)
        and RS_USER's status reads RUN_USER's record (no state yet: a fresh install, OFF). Then `on` (a state), and
        `02-d1.sh build V` again: the state stays 0640."""
        g = RealUsers(self)
        g.version(OLD)
        r = ok(self, g.d1(), 'the full 02-d1.sh run')
        self.assertIn('B2 DONE (D1)', r.stdout)
        g.shown('the full 02-d1.sh run', 'fresh')
        g.run_modes('the full 02-d1.sh run')
        g.version(V)
        ok(self, g.d1('build', V), '02-d1.sh build V')
        g.shown('02-d1.sh build V', 'fresh')
        g.run_modes('02-d1.sh build V')
        ok(self, g.upd(g.run, 'on'), 'on')
        ok(self, g.d1('build', V), '02-d1.sh build V, ON')
        g.shown('02-d1.sh build V, ON', 'ON')
        g.run_modes('02-d1.sh build V, ON')

    def test_a_folder_left_with_the_old_modes_is_migrated_on_the_next_lock_take(self):
        """The modes ee8a1f7 left (STATEDIR and its new parents 0700, the state 0600; ~/.local as the live host has it,
        0711, or as Ubuntu 24.04's install -d made it, 0755): the next lock take of RUN_USER's, a timer pass that is
        OFF, or one that finds the lock held, gives each folder the group's search, keeps every bit it had, and makes
        the state 0640: RS_USER reads RUN_USER's record. Control: before that lock take, RS_USER cannot read it."""
        for local, held in ((0o711, False), (0o755, False), (0o700, True)):
            with self.subTest(local=oct(local), held=held):
                g = RealUsers(self)
                h = g.home(g.run)
                for rel, m in (('.local', local), ('.local/state', 0o700), (D, 0o700)):
                    os.mkdir(os.path.join(h, rel))
                    os.chmod(os.path.join(h, rel), m)
                    os.chown(os.path.join(h, rel), *g.ids[g.run])
                g.write_as(g.run, D + '/state.json', '{"format":1,"on":false,"stops":[]}\n', 0o600)
                g.write_as(g.run, D + '/lock', '', 0o600)
                self.assertIn('is not shown: it cannot be read', ' '.join(g.record('the old modes')))  # the control
                if held:
                    g.hold(g.run)
                r = ok(self, g.upd(g.run, 'pass'), 'a pass')
                self.assertIn('another run holds the updater lock' if held else 'the updater is OFF: nothing to do',
                              r.stdout)
                g.shown('the next lock take', 'OFF')
                g.run_modes('the next lock take', had={'.local': local, '.local/state': 0o700})


@needs_container
class RsUserStaysPrivate(unittest.TestCase):
    def test_rs_user_s_own_writers_keep_its_folder_0700_and_its_state_0600(self):
        """The control that must come out the other way: the same commands as RS_USER (its first OFF timer pass on a
        home with no ~/.local, on, off, a pass that finds the lock held) leave its folders 0700 (made here: set, never
        coreutils' 0755), its state and its lock 0600, and RUN_USER can read neither (no channel from RS_USER to
        RUN_USER)."""
        g = RealUsers(self)
        self.assertFalse(os.path.lexists(g.home(g.rs, '.local')))
        ok(self, g.upd(g.rs, 'pass'), 'RS_USER\'s first timer pass')
        g.rs_modes('RS_USER\'s first timer pass')
        ok(self, g.upd(g.rs, 'on'), 'RS_USER\'s on')
        g.rs_modes('RS_USER\'s on')
        ok(self, g.upd(g.rs, 'off'), 'RS_USER\'s off')
        g.rs_modes('RS_USER\'s off')
        g.hold(g.rs)
        r = ok(self, g.upd(g.rs, 'pass'), 'RS_USER\'s pass, the lock held')
        self.assertIn('another run holds the updater lock', r.stdout)
        g.rs_modes('RS_USER\'s pass, the lock held')

    def test_02_d1_sh_as_rs_user_refuses_and_changes_nothing(self):
        """Codex r2 F3 (fix round 2): 02-d1.sh runs as RUN_USER only. As RS_USER, `02-d1.sh build V` and the full run
        REFUSE before rr_lock and before any other action, exit 1, and the line names the user to run it as (the
        host config's RUN_USER): RS_USER's STATEDIR stays 0700 and its state 0600, nothing in its home changes, and no
        substitute or the local GitHub sees a call (until fix round 2 its `rr_lock run` made them 0710 and 0640). The
        control that comes out the other way: as RUN_USER both modes go on
        (RunUsersRecord.test_02_d1_sh_first_then_its_build_and_rs_user_reads_the_record)."""
        g = RealUsers(self)
        ok(self, g.upd(g.rs, 'pass'), 'RS_USER\'s first timer pass')
        ok(self, g.upd(g.rs, 'on'), 'RS_USER\'s on')
        g.rs_modes('RS_USER\'s on')
        before, outside = home_tree(g.home(g.rs)), g.outside()
        for args in (('build', V), ()):
            with self.subTest(args or 'the full run'):
                r = g.d1(*args, user=g.rs)
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                g.rs_modes('02-d1.sh %s as RS_USER' % ' '.join(args))
                self.assertEqual(home_tree(g.home(g.rs)), before)
                self.assertEqual(g.outside(), outside)
                self.assertIn('02-d1.sh: REFUSE run me as %s' % g.run, r.stderr)
                self.assertEqual(r.stdout, '', 'it acted before it refused')


def home_tree(home):
    """{path: (mode, uid, gid, size, mtime_ns)} of HOME and every entry under it (lstat): what a write would change."""
    out = {}
    for d, dirs, names in os.walk(home):
        for p in [d] + [os.path.join(d, n) for n in dirs + names]:
            s = os.lstat(p)
            out[p] = (s.st_mode, s.st_uid, s.st_gid, s.st_size, s.st_mtime_ns)
    return out


def text(rel):
    with open(os.path.join(REPO, 'linux-docker', rel)) as f:
        return f.read()


class OnePlace(unittest.TestCase):
    def test_every_holder_of_the_lock_names_its_role_and_one_place_sets_the_modes(self):
        """rr_lock is the one place that sets the modes of the updater's folder, its lock and (by the mode it names)
        the state, by the ROLE its caller names: every call of it in linux-docker/ names one, 02-d1.sh's `run` (it runs
        as RUN_USER), the updater's its own ROLE. pool-image.sh's unattended modes take none: they are the updater's
        child (S2b-3c-1 D-a: rr_held). No other line of linux-docker/ sets the mode of that folder (an `install -d` or a
        chmod of it), and the state's mode comes from rr_lock's RR_STATE_MODE alone. Text only: it runs anywhere."""
        calls = {}
        for rel in ('setup/02-d1.sh', 'setup/pool-image.sh', 'bin/runner-updater', 'setup/runner-release.sh',
                    'setup/03-runscaler.sh', 'setup/04-timer.sh', 'setup/runner-facts.sh'):
            for l in text(rel).splitlines():
                code = l.split('#', 1)[0]
                m = re.search(r'(?:^\s*|[;&|{(!]\s*)rr_lock(?=\s|$)([^|;&)]*)', code)   # a call: a word of its own
                if m and 'rr_lock()' not in code:
                    calls.setdefault(rel, []).append(' '.join(('rr_lock' + m.group(1)).split()))
        self.assertEqual(calls, {'setup/02-d1.sh': ['rr_lock run'],
                                 'bin/runner-updater': ['rr_lock "$ROLE" -n', 'rr_lock "$ROLE"']})
        self.assertRegex(text('setup/pool-image.sh'), r'(?m)^\s*rr_held \|\| die ')
        rr = text('setup/runner-release.sh')
        body = rr.split('\nrr_lock() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('RR_STATE_MODE=', body)
        for rel in ('bin/runner-updater', 'setup/02-d1.sh', 'setup/pool-image.sh', 'setup/03-runscaler.sh'):
            for l in text(rel).splitlines():
                code = l.split('#', 1)[0]
                self.assertNotRegex(code, r'(install -d|chmod)[^|;]*(STATEDIR|RR_LOCK|runner-updater)\b(?!/)',
                                    '%s: %s' % (rel, l))
                self.assertNotIn('RR_STATE_MODE=', code, rel)
        chmods = [l for l in text('bin/runner-updater').splitlines() if re.search(r'\bchmod\b', l.split('#', 1)[0])]
        self.assertEqual(len(chmods), 1, chmods)
        self.assertIn('chmod "$RR_STATE_MODE" -- "$STATE.new"', chmods[0])


if __name__ == '__main__':
    unittest.main()
