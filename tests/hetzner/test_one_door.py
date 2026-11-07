"""ONE DOOR FOR THE BINARY (runscaler 0.12 bump, Hetzner slice H2a; the H2 plan's M-1, M-2, R-8, H2-7 and R-4's belt).

- THE RUNSCALERS (M-2): 03-runscaler.sh names, in ONE block, the two runscalers this release knows: PINNED v0.12.0
  (TGZ_SHA, the release tarball's sha256; BIN_SHA, its `runner`'s) and WAY-BACK v0.9.5 (WAYBACK_TGZ_SHA,
  WAYBACK_BIN_SHA), each by its constant (the builder re-derived v0.12.0's from the release tarball). runner-start's
  V095_SHA is the way-back BIN_SHA (test_render's Text binds the two). README Install step 4 downloads the pinned one.
- ONE DOOR (M-1, H2a's half; R-8): `03 real` installs ~/bin/runner only on a fresh host (none there), through
  ~/bin/runner.new and a rename once its sha256 is checked (no partial binary under the name); on a host with one it
  leaves it as it is (bytes, inode, mtime) and validates with it. `03 real` (bare, or from a person's `up`), `03 render`
  (the updater's D3) and a person's `up` REFUSE, before any change, an installed runscaler that is neither the pinned
  nor the way-back one, naming `pool-image.sh runscaler` (the one step that changes it). The way-back one stages and
  switches images as the pinned one does (an image switch runs on v0.12.0, or after a way back on v0.9.5).
- NO EXPOSURE BEFORE THE COMPARE (H2-7): a person's `up` runs `03 real DIGEST --image-only`, and 03 then refuses, after
  its validate and before it installs config.real.toml or config.toml, a render that differs from config.toml in more
  than the runner-image lines (runner-release.sh's rr_same_but_image: comments and the log-file key line aside): a
  drifted host value never reaches config.toml, not for a moment (no rename onto it at any point, its sha, mtime and
  inode as they were), and nothing restarts. A bare `03 real` (Install step 9, a pool.env change) keeps its rule: it
  installs what it renders.
- BACK'S PAIR GUARD (R-4's belt): a person's `back` refuses, before any put, a kept config.toml.pre-image with no
  log-file key while ~/bin/runner is not the way-back runscaler (03's WAYBACK_BIN_SHA): runner-start would refuse that
  pair at the restart, and CI would be down. On the way-back runscaler, or with a kept config that has the key, it
  rolls back as before.
The Text cells run anywhere; the others run the real scripts (pin lines rewritten) in a container (support.Pool). The
pool's PINNED runscaler is Pool's substitute (03's BIN_SHA rewritten to it); the WAY-BACK one is test_render.way_back's
(the same program, other bytes; 03's WAYBACK_BIN_SHA and runner-start's V095_SHA rewritten to it). An UNKNOWN one is
the pinned substitute with a line more.
"""
import os
import re
import unittest

from tests.hetzner.support import REPO, Pool, digest, needs_container, ref, sha256_file
from tests.hetzner.test_render import UPNEW, UPV, Before, assignment, way_back

S03 = os.path.join(REPO, 'linux-docker', 'setup', '03-runscaler.sh')
README = os.path.join(REPO, 'linux-docker', 'README.md')
V2, X = digest(12), digest(20)
RUNSCALERS = (('PINNED', '0.12.0'),
              ('TGZ_SHA', '76a8130fd553cfff5437fe70dd6ec1badd723469ea13e1679958d0200b67794c'),
              ('BIN_SHA', '4b8b45ae91430bd20391837955d0e44a90127ae8383710930596c302b2ffae74'),
              ('WAYBACK', '0.9.5'),
              ('WAYBACK_TGZ_SHA', 'f0e024d181954fb6d29d254b43907152be0f5fa8f91b3e054e9e199be29ec25f'),
              ('WAYBACK_BIN_SHA', 'd9d1e5779ad5c7220dddcba1a2464f50f680f9d8102f784da63f15a052523948'))
DOOR = '`pool-image.sh runscaler`'


def readme():
    with open(README) as f:
        return f.read()


def step(text, n):
    """README Install step N's text."""
    ins = text.split('\n## Install\n', 1)[1].split('\n## ', 1)[0]
    return ins.split('\n%d. ' % n, 1)[1].split('\n%d. ' % (n + 1), 1)[0]


def binary(p):
    """~/bin/runner as a change would show it: (sha256, mtime in ns, inode)."""
    rb = os.path.join(p.HOME, 'bin', 'runner')
    s = os.stat(rb)
    return sha256_file(rb), s.st_mtime_ns, s.st_ino


def unknown(p):
    """~/bin/runner becomes a runscaler this release does not know (the pinned substitute with a line more)."""
    rb = os.path.join(p.HOME, 'bin', 'runner')
    with open(rb, 'ab') as f:
        f.write(b'# another runscaler\n')


def files(p):
    """The home's files as Pool.snapshot reads them, less pool-image.sh's lock (a run writes its pid into it)."""
    return {k: v for k, v in p.snapshot().items() if not k.endswith('/pool-image.lock')}


class Pins(unittest.TestCase):
    def test_03_names_the_pinned_and_the_way_back_runscaler_in_one_block(self):
        """M-2: the six lines, each once, one after the other, in this order: the pinned runscaler (v0.12.0: the
        tarball's and its runner's sha256, the builder's evidence in the build log) and the way-back one (v0.9.5)."""
        for name, value in RUNSCALERS:
            self.assertEqual(assignment(S03, name), [value], name)
        with open(S03) as f:
            text = f.read()
        block = ''.join('%s=%s\n' % kv for kv in RUNSCALERS)
        self.assertEqual(text.count('\n' + block), 1, 'the six lines are one block')

    def test_the_readme_downloads_the_pinned_runscaler(self):
        """M-2: Install step 4 downloads runscaler v<PINNED>'s tarball (PINNED as the cell above reads it in 03) into
        ~/build/dl/runner-linux-amd64.tar.gz, the file 03 checks by TGZ_SHA; no line of the README puts another release
        into that file."""
        text = readme()
        pinned = dict(RUNSCALERS)['PINNED']
        url = 'https://github.com/ysya/runscaler/releases/download/v%s/runner-linux-amd64.tar.gz' % pinned
        self.assertIn('-o ~/build/dl/runner-linux-amd64.tar.gz %s' % url, step(text, 4))
        into = re.findall(r'-o ~/build/dl/runner-linux-amd64\.tar\.gz (\S+?)\'?(?:\s|$)', text)
        self.assertEqual(sorted(set(into)), [url])

    def test_the_readme_says_what_03_does_with_the_runscaler(self):
        """M-1 as a person reads it: Install step 4 says 03 installs the download on a fresh host only, and step 9 that
        03 keeps a runscaler that is there (v0.12.0, or v0.9.5, the way back), refuses any other before it changes
        anything, and names the one step that changes it. The Files table says it too. "The log-file line" no longer
        says that 03 installs v0.9.5, and says a `back` to a config with no line needs the way-back runscaler."""
        text = readme()
        s4, s9 = step(text, 4), step(text, 9)
        for w in ('v0.12.0', 'fresh host', DOOR):
            self.assertIn(w, s4)
        for w in ('fresh host', '`~/bin/runner.new`', 'v0.12.0', 'v0.9.5', 'the way back', DOOR,
                  'before it changes anything'):
            self.assertIn(w, s9)
        row = [l for l in text.splitlines() if l.startswith('| `setup/03-runscaler.sh` |')]
        self.assertEqual(len(row), 1)
        self.assertIn('fresh host', row[0])
        sec = text.split('\n## The log-file line\n', 1)[1].split('\n## ', 1)[0]
        self.assertNotIn('the release 03 installs', sec)
        for w in ('comment', 'way back', '`back` refuses'):
            self.assertIn(w, sec)


@needs_container
class Door(unittest.TestCase):
    def test_a_fresh_host_s_03_real_installs_the_pinned_runscaler_by_a_rename(self):
        """R-8: no ~/bin/runner: 03 real installs the pinned one (the tarball by TGZ_SHA, its runner by BIN_SHA) into
        ~/bin/runner.new and renames it over ~/bin/runner (the mv substitute logs the rename), 0755, no runner.new left.
        b2eb739 wrote it in place (`install` onto the name: a cut leaves a partial binary)."""
        p = Pool(self)
        p.image_ref(V2)
        p.hooks()
        r = p.s03('real')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        rb = os.path.join(p.HOME, 'bin', 'runner')
        self.assertEqual(sha256_file(rb), assignment(os.path.join(p.build, 'setup', '03-runscaler.sh'), 'BIN_SHA')[0])
        self.assertEqual(os.stat(rb).st_mode & 0o777, 0o755)
        self.assertFalse(os.path.lexists(rb + '.new'))
        self.assertIn('mv runner', p.events())

    def test_a_host_with_a_runscaler_keeps_it(self):
        """M-1: a re-run of `03 real` on a host whose ~/bin/runner is the pinned runscaler, or the way-back one, leaves
        it as it is (bytes, mtime, inode) and validates with it. b2eb739 installed its pin over it each time."""
        for which in ('pinned', 'way back'):
            with self.subTest(which):
                p = Pool(self)
                p.production(V2)
                if which == 'way back':
                    way_back(self, p)
                before = binary(p)
                r = p.s03('real')
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertIn('03 DONE (real)', r.stdout)
                self.assertEqual(binary(p), before)

    def test_up_keeps_the_installed_runscaler(self):
        """M-1: a person's `up` to another image (its `03 real DIGEST --image-only`) leaves ~/bin/runner as it is, the
        pinned runscaler or the way-back one: an image switch never changes it. The mutant (03 real installs the
        pinned one whatever is there) replaces the way-back one."""
        for which in ('pinned', 'way back'):
            with self.subTest(which):
                g = Before(self)
                if which == 'way back':
                    g.way_back()
                before = binary(g.p)
                r = g.p.pool('up', UPV)
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertIn('POOL IMAGE DONE (up): %s' % ref(UPNEW), r.stdout)
                self.assertEqual(binary(g.p), before)

    def test_render_stages_with_the_way_back_runscaler(self):
        """M-1: the updater's D3 (`03 render`) on a host that runs the way-back runscaler stages and validates (an image
        switch runs on v0.9.5 after a way back). b2eb739 refused every runscaler but its BIN_SHA."""
        p = Pool(self)
        p.production(V2)
        way_back(self, p)
        staged = p.rpath('config.staged.toml')
        r = p.s03('render', X, staged)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('VALIDATE PASS', r.stdout)
        self.assertEqual(p.images('config.staged.toml'), [ref(X)] * 2)

    def test_an_unknown_runscaler_refuses_before_any_change(self):
        """M-1: ~/bin/runner neither the pinned nor the way-back runscaler: a bare `03 real`, `03 render` and a person's
        `up` refuse (exit 1), naming `pool-image.sh runscaler`, and change no file of the home (no config, no keep, no
        STAGED, no installed file; render: no validate). The controls: the two cells above."""
        for how in ('03 real', '03 render', "a person's up"):
            with self.subTest(how):
                g = Before(self)
                p = g.p
                unknown(p)
                p.write(p.path('logs', 'runner.log'), '')
                before = files(p)
                if how == '03 real':
                    r = p.s03('real')
                elif how == '03 render':
                    r = p.s03('render', X, p.rpath('config.staged.toml'))
                else:
                    r = p.pool('up', UPV)
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertIn('pool-image.sh runscaler', r.stdout)
                self.assertIn(os.path.join(p.HOME, 'bin', 'runner'), r.stdout)
                self.assertEqual(files(p), before)
                self.assertEqual([c for c in p.calls('runner') if c['argv'][:1] == ['validate']], [])
                self.assertEqual(g.restarts(), [])


@needs_container
class NoExposure(unittest.TestCase):
    def test_a_drifted_host_value_refuses_inside_03_and_config_toml_never_moves(self):
        """H2-7: the host config's MAIN_LABEL is not the one the pool runs. A person's `up` runs `03 real DIGEST
        --image-only`, which refuses after its validate (the render differs from config.toml in more than the image)
        and before it installs anything: no rename onto config.toml or config.real.toml at any point (the mv
        substitute's log), each one's sha256, mtime and inode as they were, nothing restarted. b2eb739 installed the
        render and then put the rollback back (a new inode, and the drifted values on disk in between)."""
        g = Before(self)
        p = g.p
        g.label('linux-ci-x')
        p.hooks()

        def st(name):
            f = p.rpath(name)
            s = os.stat(f)
            return sha256_file(f), s.st_mtime_ns, s.st_ino
        before = {n: st(n) for n in ('config.toml', 'config.real.toml')}
        r = p.pool('up', UPV)
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertIn('VALIDATE PASS', r.stdout)
        self.assertIn('FAIL the render differs from config.toml in more than the runner-image lines', r.stdout)
        self.assertIn('03 real failed: config.toml was not changed', r.stdout)
        self.assertEqual({n: st(n) for n in before}, before)
        moved = [e for e in p.events() if e in ('mv config.toml', 'mv config.real.toml')]
        self.assertEqual(moved, [])
        self.assertIn('mv config.toml.pre-image', p.events(), 'the cell saw the renames (its control)')
        self.assertEqual(g.restarts(), [])

    def test_control_a_bare_03_real_installs_what_it_renders(self):
        """H2-7's other side: a bare `03 real` (Install step 9, a change of pool.env's numbers or of the host config)
        keeps its rule and installs the render with the new value."""
        g = Before(self)
        g.label('linux-ci-x')
        r = g.p.s03('real')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('labels = ["self-hosted", "linux-ci-x"]\n', g.p.config())


@needs_container
class Belt(unittest.TestCase):
    def test_back_refuses_a_rollback_with_no_log_file_key_off_the_way_back_runscaler(self):
        """R-4's belt: after an up from a config with no log-file line (config.toml.pre-image has none), ~/bin/runner
        is not the way-back runscaler (here the pinned one): `back` refuses before any put, naming what is wrong, and
        changes no file; nothing restarts. b2eb739 put it back and restarted into a pair runner-start refuses."""
        g = Before(self)
        g.after_up('config.toml.pre-image')
        before = files(g.p)
        r = g.p.pool('back')
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertIn('no log-file key', r.stdout)
        self.assertIn('the way-back runscaler', r.stdout)
        self.assertEqual(files(g.p), before)
        self.assertEqual(g.restarts(), [])

    def test_control_on_the_way_back_runscaler_it_rolls_back(self):
        """The belt's control: the same back on the way-back runscaler (v0.9.5, which runs a config with no line) puts
        the kept config back and restarts once, as before."""
        g = Before(self)
        g.after_up('config.toml.pre-image')
        g.way_back()
        r = g.p.pool('back')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), g.pre)
        self.assertEqual(g.p.unit_now()['restarts'], 1)

    def test_control_a_rollback_with_the_key_rolls_back_on_any_runscaler(self):
        """The belt's other control: a kept config WITH the log-file key (03's render of the old image) goes back on
        the pinned runscaler."""
        g = Before(self)
        g.after_up('config.toml.pre-image')
        g.put(g.p.rpath('config.toml.pre-image'), g.h1)
        r = g.p.pool('back')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), g.h1)
        self.assertEqual(g.p.unit_now()['restarts'], 1)


if __name__ == '__main__':
    unittest.main()
