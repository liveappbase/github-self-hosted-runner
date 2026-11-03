"""linux-docker/README.md, "Upgrading from a release before this one": a host installed from an older release has a
host config without RUNNER_VERSION, and this release's 02-d1.sh refuses to run without it. The section's lines are
taken from its text and run as written, in order: a laptop line runs in a fresh checkout of the release (no host.conf:
it is no tracked file), and an `ssh U@<host> '…'` line runs its quoted command here, in the container that plays the
host. Step 1 reads the version the pool runs (not run here: it needs the pool's image). Step 2 sets RUNNER_VERSION in
the INSTALLED host config and keeps every other line as it was; step 3 checks the installed file against every key of
host.conf.example, which are the keys this release's scripts read (Keys pins that, both ways). The same step 2 line
also sets a new version over an old one ("A new runner release", step 2).
Step 2 takes the version ONCE, at its start (the one place a person edits), and refuses a version that is not N.N.N
before it writes anything: every script refuses a host config whose RUNNER_VERSION line is not KEY=value (a trailing
space, an empty value), so a line that wrote one would stop the pool's next start. Root's shell may be bash or dash: the
step 2 cells run it with each. Step 3 says why it fails: a key missing, a key held twice, or a RUNNER_VERSION that is
not N.N.N, each a WANT line the README names a fix for.
The Keys and Lines cells read text and run anywhere; the others run in a container (tests/hetzner/support.py).
"""
import os
import re
import shutil
import stat
import subprocess
import unittest

from tests.hetzner.support import REPO, Sandbox, needs_container, sha256_file, tarball

README = os.path.join(REPO, 'linux-docker', 'README.md')
EXAMPLE = os.path.join(REPO, 'linux-docker', 'host.conf.example')
V = '2.338.2'          # what step 1 printed: host.conf.example's RUNNER_VERSION
BUILD = '2.339.0'
LEFT = object()        # run_line's version: the placeholder left in the line as it is


def section():
    with open(README) as f:
        text = f.read()
    return text.split('\n## Upgrading from a release before this one\n', 1)[1].split('\n## ', 1)[0]


def steps():
    return [b.strip() for b in re.findall(r'```\n(.*?)\n *```', section(), re.S)]


def readers(sb):
    """{script: (rc, stderr)}: each linux-docker/ script's OWN host_conf function and host_conf line, run on the
    sandbox's installed host config. rc 0: that script reads the file."""
    out = {}
    for d, _, files in os.walk(os.path.join(REPO, 'linux-docker')):
        for n in files:
            p = os.path.join(d, n)
            with open(p, 'rb') as f:
                text = f.read().decode('utf-8', 'replace')
            call = re.search(r'^host_conf \S+ .*$', text, re.M)
            if not call:
                continue
            fn = re.search(r'^host_conf\(\) \{.*?^\}\n', text, re.M | re.S)
            if not fn:
                raise AssertionError('%s: a host_conf line and no host_conf function' % p)
            r = subprocess.run(['bash', '-c', 'HOST_CONF=$1\n' + fn.group(0) + call.group(0) + '\n', 'readers',
                                sb.path('host.conf')], env=sb.env(), stdin=subprocess.DEVNULL, capture_output=True,
                               text=True, timeout=60)
            out[os.path.relpath(p, REPO)] = (r.returncode, r.stderr)
    if len(out) < 7:
        raise AssertionError('fewer host_conf readers than the 7 of this release: %s' % sorted(out))
    return out


class Lines(unittest.TestCase):
    def test_step_2_takes_the_version_once_at_its_start(self):
        line = steps()[1]
        self.assertEqual(line.count('<version>'), 1, line)
        self.assertTrue(line.startswith('ssh root@<host> \'v="<version>"; '), line)

    def test_the_readme_names_what_to_do_for_each_line_the_check_prints(self):
        check = steps()[-1]
        forms = re.findall(r'echo "(WANT [^"$]*)', check)
        self.assertGreaterEqual(len(forms), 2, check)        # a key's count; RUNNER_VERSION's form
        prose = re.sub(r'```.*?```', '', section().split('\n3. ', 1)[1], flags=re.S)
        for f in forms:
            self.assertIn('`' + f, prose)
        for c in ('found 0', 'found 2'):
            self.assertIn(c, prose)


def keys_of(text):
    return re.findall(r'^([A-Z][A-Z0-9_]*)=', text, re.M)


def script_keys():
    """{script: the keys its `host_conf NAME KEY...` line reads}, for every script of linux-docker/."""
    out = {}
    for d, _, files in os.walk(os.path.join(REPO, 'linux-docker')):
        for n in files:
            with open(os.path.join(d, n), 'rb') as f:
                text = f.read().decode('utf-8', 'replace')
            for m in re.finditer(r'^host_conf (\S+) (.*)$', text, re.M):
                out[os.path.relpath(os.path.join(d, n), REPO)] = m.group(2).split()
    return out


class Keys(unittest.TestCase):
    def test_the_example_names_every_key_a_script_reads_and_no_other(self):
        with open(EXAMPLE) as f:
            example = keys_of(f.read())
        self.assertEqual(len(example), len(set(example)), 'host.conf.example names a key twice')
        per = script_keys()
        self.assertGreaterEqual(len(per), 7, sorted(per))       # 01-users, its undo, 02-d1, 03, pool-image, 2 bins
        for script, keys in per.items():
            for k in keys:
                self.assertRegex(k, r'^[A-Z][A-Z0-9_]*$', '%s: a host_conf line of another shape' % script)
        read = set(k for keys in per.values() for k in keys)
        self.assertEqual(sorted(read - set(example)), [], 'a script reads a key host.conf.example lacks')
        self.assertEqual(sorted(set(example) - read), [], 'host.conf.example names a key no script reads')


@needs_container
class Upgrade(unittest.TestCase):
    def laptop(self, sb):
        """A fresh checkout's folder: this release's linux-docker/, and no host.conf."""
        d = sb.path('laptop')
        shutil.copytree(os.path.join(REPO, 'linux-docker'), os.path.join(d, 'linux-docker'))
        return d

    def run_line(self, sb, line, cwd, version=V, remote='bash'):
        """The README's line as it runs here: `ssh [-o X] U@<host> '…'` -> `REMOTE -c '…'` (REMOTE: the host user's
        shell, bash or dash), <version> -> version (LEFT: left as it is), and the host config's folder -> the sandbox
        (the copies' HOST_CONF is its host.conf)."""
        here = re.sub(r"ssh (?:-o \S+ )?\S+@<host> '", remote + " -c '", line)
        if version is not LEFT:
            here = here.replace('<version>', version)
        here = here.replace('/etc/liveapp-ci', sb.root)
        self.assertNotRegex(here.replace('<version>', ''), r'<[A-Za-z_ ]+>', 'a placeholder this cell does not fill')
        return subprocess.run(['bash', '-c', here], cwd=cwd, env=sb.env(), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=120)

    def installed(self, sb, text=None):
        p = sb.path('host.conf')
        if text is not None:
            sb.write(p, text, 0o644)
        with open(p) as f:
            return f.read()

    def reset(self, sb, text):
        """The installed host config is TEXT (root's, 0644), and nothing else of the host config's folder is there."""
        for n in os.listdir(sb.root):
            if n.startswith('host.conf'):
                os.remove(sb.path(n))
        self.installed(sb, text)

    def conf_files(self, sb):
        """The host config's folder: {name: (sha256, mode, uid, inode)} of each host.conf* entry."""
        out = {}
        for n in sorted(os.listdir(sb.root)):
            if n.startswith('host.conf'):
                s = os.lstat(sb.path(n))
                out[n] = (sha256_file(sb.path(n)) if stat.S_ISREG(s.st_mode) else None, s.st_mode, s.st_uid, s.st_ino)
        return out

    def test_the_steps_add_one_line_to_the_installed_host_config_and_keep_every_other(self):
        sb = Sandbox(self)
        full = self.installed(sb)
        self.assertEqual(full.count('\nRUNNER_VERSION=%s\n' % V), 1)
        old = self.installed(sb, full.replace('\nRUNNER_VERSION=%s\n' % V, '\n'))   # a release before this one's
        self.assertEqual(len(keys_of(old)), len(keys_of(full)) - 1)
        before = {s: rc for s, (rc, _) in readers(sb).items()}
        self.assertEqual(sorted(s for s, rc in before.items() if rc), ['linux-docker/setup/02-d1.sh'])
        lap = self.laptop(sb)
        self.assertFalse(os.path.exists(os.path.join(lap, 'host.conf')))
        ss = steps()
        self.assertGreaterEqual(len(ss), 3, ss)
        for line in ss[1:]:
            r = self.run_line(sb, line, lap)
            self.assertEqual(r.returncode, 0, line + '\n' + r.stdout + r.stderr)
        self.assertEqual(r.stdout, 'RUNNER_VERSION=%s\n' % V)                    # the check's one line
        self.assertEqual(self.installed(sb), old + 'RUNNER_VERSION=%s\n' % V)   # every line kept, one added
        s = os.stat(sb.path('host.conf'))
        self.assertEqual((s.st_mode & 0o777, s.st_uid), (0o644, 0))
        with open(sb.path('host.conf.prev')) as f:                              # the file before is kept
            self.assertEqual(f.read(), old)
        self.assertEqual({s: rc for s, (rc, _) in readers(sb).items()}, {s: 0 for s in before})   # every script reads it
        # this release's scripts read it: 02-d1.sh builds; runner-start gets past the host config
        sb.gh.release(BUILD, tarball(BUILD))
        sb.docker['config_version'] = BUILD + '\n'
        r = sb.d1('build', BUILD)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
        r = subprocess.run(['bash', os.path.join(sb.build, 'bin', 'runner-start'), 'validate'],
                           env=dict(sb.env(), RUNNER_START_CONFIG=sb.path('none.toml')), cwd=sb.home,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.stderr, 'runner-start: REFUSE no config: %s\n' % sb.path('none.toml'))

    def test_the_check_fails_when_a_key_a_script_reads_is_missing(self):
        sb = Sandbox(self)
        lap = self.laptop(sb)
        check = steps()[-1]
        full = self.installed(sb)
        r = self.run_line(sb, check, lap)                                       # the control: every key
        self.assertEqual((r.returncode, r.stdout), (0, 'RUNNER_VERSION=%s\n' % V), r.stderr)
        for k in keys_of(full):
            with self.subTest(missing=k):
                self.installed(sb, re.sub(r'(?m)^%s=.*\n' % k, '', full))
                r = self.run_line(sb, check, lap)
                self.assertNotEqual(r.returncode, 0, k)
                self.assertIn(k, r.stdout)
        with self.subTest('the one-line file of the steps before this fix'):
            self.installed(sb, '\nRUNNER_VERSION=%s\n' % V)
            r = self.run_line(sb, check, lap)
            self.assertNotEqual(r.returncode, 0)

    def test_the_check_fails_on_a_key_held_twice_and_names_it(self):
        sb = Sandbox(self)
        lap = self.laptop(sb)
        check = steps()[-1]
        full = self.installed(sb)
        r = self.run_line(sb, check, lap)                                       # the control: every key once
        self.assertEqual((r.returncode, r.stdout), (0, 'RUNNER_VERSION=%s\n' % V), r.stderr)
        for k in ('HOST_IP', 'RUNNER_VERSION'):
            with self.subTest(twice=k):
                self.installed(sb, full + re.search(r'(?m)^%s=.*\n' % k, full).group(0))
                self.assertTrue(all(rc for rc, _ in readers(sb).values()), 'a script read a key held twice')
                r = self.run_line(sb, check, lap)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertTrue([l for l in r.stdout.splitlines() if l.startswith('WANT') and ' %s ' % k in l
                                 and l.endswith('found 2')], r.stdout + r.stderr)

    def test_the_check_fails_on_a_RUNNER_VERSION_that_is_not_N_N_N_and_names_it(self):
        sb = Sandbox(self)
        lap = self.laptop(sb)
        check = steps()[-1]
        full = self.installed(sb)
        r = self.run_line(sb, check, lap)                                       # the control: 2.338.2
        self.assertEqual((r.returncode, r.stdout), (0, 'RUNNER_VERSION=%s\n' % V), r.stderr)
        for bad in ('2.338', '2.338.2 ', '', 'v2.338.2'):
            with self.subTest(bad=bad):
                self.installed(sb, full.replace('\nRUNNER_VERSION=%s\n' % V, '\nRUNNER_VERSION=%s\n' % bad))
                r = self.run_line(sb, check, lap)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertTrue([l for l in r.stdout.splitlines() if l.startswith('WANT') and 'RUNNER_VERSION' in l],
                                r.stdout + r.stderr)

    def test_step_2_refuses_a_version_that_is_not_N_N_N_and_writes_nothing(self):
        bad = (('a trailing space', '2.338.2 '), ('an empty version', ''), ('the placeholder left in', LEFT),
               ('a leading v', 'v2.338.2'), ('two numbers', '2.338'), ('four numbers', '2.338.2.1'),
               ('an empty number', '2..338'), ('a leading space', ' 2.338.2'), ('a second line', '2.338.2\n2.338.2'))
        sb = Sandbox(self)
        lap = self.laptop(sb)
        full = self.installed(sb)
        old = full.replace('\nRUNNER_VERSION=%s\n' % V, '\n')                  # a release before this one's
        line = steps()[1]
        for remote in ('bash', 'dash'):
            for why, v in bad:
                with self.subTest(why, root_shell=remote):
                    self.reset(sb, old)
                    before = self.conf_files(sb)
                    r = self.run_line(sb, line, lap, version=v, remote=remote)
                    self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertIn('[%s]' % ('<version>' if v is LEFT else v), r.stdout + r.stderr)
                    self.assertEqual(self.conf_files(sb), before, 'the line wrote: ' + r.stdout + r.stderr)
            with self.subTest('the control: ' + V, root_shell=remote):
                self.reset(sb, old)
                r = self.run_line(sb, line, lap, remote=remote)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.installed(sb), old + 'RUNNER_VERSION=%s\n' % V)
                self.assertEqual([s for s, (rc, _) in readers(sb).items() if rc], [])

    def test_step_2_puts_a_new_version_in_place_of_the_old_one(self):
        sb = Sandbox(self)
        lap = self.laptop(sb)
        full = self.installed(sb)
        old = self.installed(sb, full.replace('\nRUNNER_VERSION=%s\n' % V, '\nRUNNER_VERSION=2.330.0\n'))
        r = self.run_line(sb, steps()[1], lap)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installed(sb), full.replace('\nRUNNER_VERSION=%s\n' % V, '\n') + 'RUNNER_VERSION=%s\n' % V)
        with open(sb.path('host.conf.prev')) as f:
            self.assertEqual(f.read(), old)
        r = self.run_line(sb, steps()[-1], lap)
        self.assertEqual((r.returncode, r.stdout), (0, 'RUNNER_VERSION=%s\n' % V), r.stderr)


if __name__ == '__main__':
    unittest.main()
