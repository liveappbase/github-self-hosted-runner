"""linux-docker/setup/01-users.sh, the root step that makes the host's two users: its CHECK of RS_USER's groups passes
when RS_USER is in group RUN_USER, whichever of the two names sorts first. (Until S2b-3b it compared the SORTED list
of RS_USER's groups with "RS_USER RUN_USER" as written, so a host whose RS_USER sorts after RUN_USER failed the check
although it was right; host.conf.example's names sort the other way, so they passed.)

The cells run a copy of the REAL script (only its HOST_CONF pin line rewritten: support.Sandbox) as root in the
throwaway container, the fresh host it expects: it makes the two users with the container's own useradd and usermod,
and the check reads the container's own `id`. A container has no systemd, so systemctl, systemd-tmpfiles and
loginctl are substitutes, and so is sudo (no cell runs a real sudo): each logs its calls and changes nothing. Other
CHECK lines fail there (no ssh key to copy, no linger, no lock file): the cells read only the group lines. Each cell's
users have names of their own; its cleanup removes them, their homes, their markers, and the lock rule and marker
folder when the run made them.
"""
import os
import secrets
import shutil
import subprocess
import unittest

from tests.hetzner.support import Sandbox, needs_container

MARK = '/var/lib/liveapp-ci'                              # 01-users.sh's MARK
TMPFILES = '/etc/tmpfiles.d/liveapp-runner-lock.conf'     # its TMPFILES
STUBS = {
    'systemctl': 'case $1 in is-active) echo active ;; esac\nexit 0',   # every unit active: no wait for one
    'systemd-tmpfiles': 'exit 0',
    'loginctl': 'exit 0',
    'sudo': 'exit 1',
}


def exists(user):
    return subprocess.run(['id', user], capture_output=True, stdin=subprocess.DEVNULL).returncode == 0


class Users:
    """A Sandbox whose host config names RUN_USER=run and RS_USER=rs, two users this container does not have yet."""

    def __init__(self, test, rs, run):
        self.t, self.rs, self.run_user = test, rs, run
        self.sb = sb = Sandbox(test)
        for u in (rs, run):
            if exists(u):
                test.fail('the user %s is already there: these cells make their own users' % u)
        with open(sb.path('host.conf')) as f:
            conf = f.read()
        for k, old, new in (('RUN_USER', 'root', run), ('RS_USER', 'ci-rs', rs)):
            line = '\n%s=%s\n' % (k, old)
            if conf.count(line) != 1:
                raise AssertionError('host.conf: no single %s line' % line.strip())
            conf = conf.replace(line, '\n%s=%s\n' % (k, new))
        sb.write(sb.path('host.conf'), conf, 0o644)
        for n, body in STUBS.items():
            sb.write(sb.path('stubs', n),
                     '#!/bin/sh\nprintf "%%s\\n" "$*" >> %s/logs/%s.log\n%s\n' % (sb.root, n, body), 0o755)
        made = {p: os.path.lexists(p) for p in (MARK, TMPFILES)}

        def clean():
            for u in (rs, run):
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

    def r1(self):
        """The copied 01-users.sh, run as root: its CompletedProcess."""
        return subprocess.run(['bash', os.path.join(self.sb.build, 'setup', '01-users.sh')], env=self.sb.env(),
                              cwd=self.sb.home, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)

    def groups(self, user):
        """The groups `id -nG` names for user (the container's own id), as a set."""
        r = subprocess.run(['id', '-nG', user], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        return set(r.stdout.split())


@needs_container
class Groups(unittest.TestCase):
    def check(self, rs, run):
        """01-users.sh with this pair: the two users are made, RS_USER is in group RUN_USER, and each group CHECK line
        is an OK."""
        u = Users(self, rs, run)
        r = u.r1()
        out = r.stdout.splitlines()
        self.assertTrue(out and out[-1] in ('R1 DONE', 'R1 HAS FAILURES: read each FAIL line. A re-run finishes a run '
                                            'that was cut off; it does not change a user R1 did not make, or a subuid '
                                            'range.'), 'it did not reach its end: ' + r.stdout[-3000:] + r.stderr)
        self.assertEqual(u.groups(rs), {rs, run}, 'the host is not right: ' + r.stdout)    # what the check checks
        self.assertEqual(u.groups(run), {run})
        self.assertIn('OK   %s groups = %s %s' % (rs, rs, run), out, r.stdout)
        self.assertIn('OK   %s groups = %s' % (run, run), out, r.stdout)
        self.assertIn('OK   group %s members = %s (D1 socket\'s access list)' % (run, rs), out, r.stdout)
        self.assertEqual([l for l in out if ' groups = ' in l and l.startswith('FAIL')], [], r.stdout)
        self.assertIn('is-active', ' '.join(u.sb.lines('systemctl')), 'the substitute answered, no systemd')
        return out

    def test_an_rs_user_that_sorts_after_run_user_passes(self):
        """S2b-3a's review: RS_USER sorts after RUN_USER ('scaler-' after 'docker-'), and RS_USER is in group
        RUN_USER: the check passes (it passed only for the other order)."""
        t = secrets.token_hex(3)
        self.assertGreater('scaler-' + t, 'docker-' + t)
        self.check('scaler-' + t, 'docker-' + t)

    def test_control_an_rs_user_that_sorts_first_passes(self):
        """The control: today's order, RS_USER before RUN_USER (host.conf.example's ci-rs and ci-run: rs before
        run), passes before the fix and after it."""
        t = secrets.token_hex(3)
        self.assertLess('hz%s-rs' % t, 'hz%s-run' % t)
        self.check('hz%s-rs' % t, 'hz%s-run' % t)

    def test_control_an_rs_user_without_the_group_fails_the_check_in_either_order(self):
        """The control that must come out the other way: the check still fails a host that is wrong. A usermod that
        changes nothing (a substitute) leaves RS_USER out of group RUN_USER, and the check names RS_USER's groups as a
        FAIL, whichever name sorts first."""
        for rs, run in (('scaler-%s', 'docker-%s'), ('hz%s-rs', 'hz%s-run')):
            with self.subTest(order='RS_USER first' if rs.startswith('hz') else 'RS_USER after'):
                t = secrets.token_hex(3)
                u = Users(self, rs % t, run % t)
                u.sb.write(u.sb.path('stubs', 'usermod'), '#!/bin/sh\nexit 0\n', 0o755)
                r = u.r1()
                self.assertEqual(u.groups(rs % t), {rs % t})
                self.assertIn('FAIL %s groups = [%s]' % (rs % t, rs % t), r.stdout.splitlines(), r.stdout)


if __name__ == '__main__':
    unittest.main()
