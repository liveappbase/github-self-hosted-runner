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
  rolls back as before. Each cell that claims a pair starts, or not, runs the INSTALLED runner-start's guard on it
  (test_render.guard: the systemctl substitute runs no runner-start; H2a review r1, Opus F3).
- THE ONE DOOR, over the tree (R-8; slice H2b-1): the programs of linux-docker/ write ~/bin/runner only by 03's two
  renames of ~/bin/runner.new (a fresh host's, and the stage of `pool-image.sh runscaler`), and runner.new only by 03's
  one install of a checked `runner`. THE STAGED SELECTOR (R-2): `runner-start validate --staged` validates with
  ~/bin/runner.new, and its log-file guard hashes that file; `validate` takes no other argument; `run` (with any
  argument, or any env var) and `delete` exec ~/bin/runner and hash it. A fresh host's 03 real that ends between the
  install into runner.new and its rename leaves neither name (H2a review r1, Opus F4: the trap's cleanup).
The Text cells run anywhere; the others run the real scripts (pin lines rewritten) in a container (support.Pool). The
pool's PINNED runscaler is Pool's substitute (03's BIN_SHA rewritten to it); the WAY-BACK one is test_render.way_back's
(the same program, other bytes; 03's WAYBACK_BIN_SHA and runner-start's V095_SHA rewritten to it). An UNKNOWN one is
the pinned substitute with a line more.
"""
import os
import re
import unittest

from tests.hetzner.support import REPO, Pool, digest, needs_container, ref, sha256_file
from tests.hetzner.test_render import UPNEW, UPV, Before, assignment, guard, starts, way_back, without_log_file

S03 = os.path.join(REPO, 'linux-docker', 'setup', '03-runscaler.sh')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
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


def code_lines(path):
    """(line number, line) of each line of a program that is not a whole-line comment."""
    with open(path, errors='replace') as f:
        return [(i, l.rstrip('\n')) for i, l in enumerate(f, 1) if not l.lstrip().startswith('#')]


BIN = r'(?:bin/runner|\$RB|\$NEWBIN|\$RUNNER)(?![-_A-Za-z.])'   # ~/bin/runner (or runner.new), by any name a program uses
WRITE = re.compile(r'(?:^\s*|[;&|({]\s*)(?:mv|cp|install|ln|tar|dd|tee|rsync|curl)\b[^;&|]*' + BIN
                   + r'|>>?\s*"?' + BIN)


class Census(unittest.TestCase):
    def test_only_03_s_two_renames_write_bin_runner(self):
        """R-8: every program of linux-docker/ (not the README): a command (mv, cp, install, ln, tar, dd, tee, rsync,
        curl) whose arguments name ~/bin/runner or runner.new (bin/runner, $RB, $NEWBIN, runner-start's $RUNNER; not
        runner-start or runner-updater), or a redirection into one, is one of 03's three: the install of a checked
        `runner` into ~/bin/runner.new (one function, for a fresh host and for the stage), and the two renames of
        runner.new over ~/bin/runner (a fresh host's at once, the stage's after config.toml). The build log has the git
        grep of the same census. 3c0e0aa has the fresh host's two lines only (its install names $BIN_SHA)."""
        found = []
        root = os.path.join(REPO, 'linux-docker')
        for d, _, names in os.walk(root):
            for n in sorted(names):
                f = os.path.join(d, n)
                if n.endswith('.md'):
                    continue
                for i, l in code_lines(f):
                    if WRITE.search(l):
                        found.append((os.path.relpath(f, root), l.strip()))
        s03 = 'setup/03-runscaler.sh'
        want = [(s03, 'install -m 755 "$tmp/runner" "$NEWBIN"; sha "$NEWBIN" "$BIN"'),
                (s03, 'mv -f "$NEWBIN" "$RB"; NEWBIN='), (s03, 'mv -f "$NEWBIN" "$RB"; NEWBIN=')]
        self.assertEqual(sorted(found), sorted(want))

    def test_the_h2_7_texts_say_what_03_s_header_says(self):
        """H2a review r1, Opus F1: 03 real --image-only refuses a drifted render after its validate and before it
        installs config.real.toml or config.toml, by which time it HAS installed this release's runner-start,
        pool-ready, validate-class and the unit (NoExposure measures it). No H2-7 text says "before it installs anything";
        README sends a pool.env mismatch to up's own check (holds_pool, before 03 runs)."""
        def between(path, a, b):
            with open(path) as f:
                text = f.read()
            self.assertEqual(text.count(a), 1, (path, a))
            return text.split(a, 1)[1].split(b, 1)[0]
        texts = (between(PIMG, '\n# up:   refuses', '\n# back: '),
                 between(S03, '\n# NO EXPOSURE BEFORE THE COMPARE', "\n# RUNSCALER'S LOG"),
                 between(S03, '\nif [ -n "$ONLY" ]; then', '\n'),
                 readme().split('\n## The log-file line\n', 1)[1].split('\n## ', 1)[0],
                 between(os.path.abspath(__file__), '\nclass NoExposure(', '\n    def test_control_a_bare_03'))
        for text in texts:   # the H2-7 texts (the stage's own compare does come before anything is installed)
            self.assertNotIn('before it installs ' + 'anything', text)
            self.assertNotIn('before anything ' + 'is installed', text)
        with open(PIMG) as f:   # the header's lines joined
            self.assertIn('before it installs config.real.toml or config.toml (this release\'s runner-start, '
                          'pool-ready, validate-class and the unit are installed by then', re.sub(r'\n#\s+', ' ', f.read()))
        sec = readme().split('\n## The log-file line\n', 1)[1].split('\n## ', 1)[0]
        for w in ('`up` itself stops before it runs 03', 'before it installs config.real.toml or config.toml',
                  'this release\'s `runner-start`'):
            self.assertIn(w, sec)

    def test_no_text_says_render_needs_the_pinned_runscaler(self):
        """H2a review r1, Opus F2: render takes the pinned or the way-back runscaler, so no text says that runscaler,
        or its binary, is (or goes by) the pinned BIN_SHA alone (the pattern below); the control: 03's ONE DOOR
        paragraph names both BIN_SHA and WAYBACK_BIN_SHA."""
        pat = re.compile(r"runscaler('s binary)? (is|by) BIN_SHA")
        for d in (os.path.join(REPO, 'linux-docker'), os.path.join(REPO, 'tests', 'hetzner')):
            for dd, _, names in os.walk(d):
                for n in names:
                    if n.endswith(('.py', '.sh', '.md')) or '.' not in n:
                        with open(os.path.join(dd, n), errors='replace') as f:
                            hits = [l for l in f if pat.search(l) and 'pat = re.compile' not in l]
                        self.assertEqual(hits, [], n)
        with open(S03) as f:
            head = f.read().split('\n# ONE DOOR ', 1)[1].split('\n# NO EXPOSURE', 1)[0]
        self.assertIn('BIN_SHA', head.replace('WAYBACK_BIN_SHA', ''))
        self.assertIn('WAYBACK_BIN_SHA', head)


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

    def test_a_fresh_host_s_03_real_that_ends_before_the_rename_leaves_neither_name(self):
        """H2a review r1, Opus F4: a fresh host's 03 real that ends after the install into ~/bin/runner.new and before
        its rename (runner.new's bytes change before its second sha check: a hook) exits 1 and leaves no ~/bin/runner
        and no ~/bin/runner.new (the trap removes the runner.new this run made). The control: the cell above (the
        rename logged, nothing left). The trap mutant leaves runner.new."""
        p = Pool(self)
        p.image_ref(V2)
        p.hooks(('install-done:runner.new', 'taint-runner-new'))
        r = p.s03('real')
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertIn('tainted runner.new', p.events())
        self.assertIn('FAIL sha256 %s' % os.path.join(p.HOME, 'bin', 'runner.new'), r.stdout)
        for n in ('runner', 'runner.new'):
            self.assertFalse(os.path.lexists(os.path.join(p.HOME, 'bin', n)), n)

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
        and before it installs config.real.toml or config.toml (it has installed this release's runner-start by then:
        its mtime moved, its bytes the pinned ones): no rename onto config.toml or config.real.toml at any point (the mv
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
        rs = os.path.join(p.HOME, 'bin', 'runner-start')
        rs0 = os.stat(rs).st_mtime_ns
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
        # what the texts say (H2a review r1, Opus F1): by its refusal 03 has installed this release's runner-start
        self.assertNotEqual(os.stat(rs).st_mtime_ns, rs0)
        self.assertEqual(sha256_file(rs), sha256_file(os.path.join(p.build, 'bin', 'runner-start')))

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
        # the belt's premise, by the INSTALLED guard: that pair (the pinned substitute, the kept config) is refused
        rg, ran = guard(g.p, g.p.rpath('config.toml.pre-image'))
        self.assertIn('runner-start: REFUSE the config has no log-file key', rg.stderr)
        self.assertEqual(ran, [])

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
        starts(self, g.p)    # the INSTALLED guard starts that pair (v0.9.5, the config with no line)

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
        starts(self, g.p)


@needs_container
class Selector(unittest.TestCase):
    """R-2: ~/bin/runner is the pinned substitute (not v0.9.5's), ~/bin/runner.new the way-back one (runner-start's
    V095_SHA, as installed). A config with no log-file key tells which file the guard hashed: on v0.9.5's it runs, on
    any other it is refused. runscaler's log names the file that ran (support.POOL_RUNNER's exe)."""

    def rig(self):
        p = Pool(self)
        p.production(V2)
        s = way_back(self, p, install=False)
        with open(os.path.join(p.HOME, 'bin', 'runner'), 'rb') as f:
            wb = f.read() + b'# the way-back runscaler of the cell: the same program, other bytes\n'
        new = os.path.join(p.HOME, 'bin', 'runner.new')
        with open(new, 'wb') as f:
            f.write(wb)
        os.chmod(new, 0o755)
        self.assertEqual(sha256_file(new), s)
        bare = p.write(p.rpath('bare.toml'), without_log_file(p.config()), 0o600)
        return p, bare

    def start(self, p, cfg, *args, env=None):
        p.write(p.path('logs', 'runner.log'), '')
        r = p.run([os.path.join(p.HOME, 'bin', 'runner-start')] + list(args),
                  env=dict(p.env(), RUNNER_START_CONFIG=cfg, **(env or {})))
        return r, [c['exe'] for c in p.calls('runner')]

    def test_validate_staged_validates_with_runner_new_and_hashes_it(self):
        """`validate --staged` hashes ~/bin/runner.new (v0.9.5's here: the config with no key passes the guard) and
        execs it; `validate` alone hashes ~/bin/runner (not v0.9.5's: refused) and execs nothing. b2eb739's and
        3c0e0aa's runner-start ignore the selector (Opus r3 F2, measured)."""
        p, bare = self.rig()
        r, ran = self.start(p, bare, 'validate', '--staged')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(ran, [os.path.join(p.HOME, 'bin', 'runner.new')])
        r, ran = self.start(p, bare, 'validate')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('the config has no log-file key, and %s is not' % os.path.join(p.HOME, 'bin', 'runner'),
                      r.stderr)
        self.assertEqual(ran, [])

    def test_validate_takes_no_other_argument(self):
        """The selector names the staged file and no other path: any other argument of validate is a usage refusal
        that runs nothing."""
        p, bare = self.rig()
        for args in (('validate', p.rpath('x')), ('validate', '--staged', 'x'), ('validate', '--runner')):
            with self.subTest(args=args):
                r, ran = self.start(p, p.rpath('config.toml'), *args)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('runner-start: REFUSE usage', r.stderr)
                self.assertEqual(ran, [])

    def test_run_with_any_argument_execs_bin_runner_and_hashes_it(self):
        """`run` with the selector (or any argument, or an env var naming another runner) execs ~/bin/runner, and its
        v0.9.5 rule hashes ~/bin/runner: the config with no key is refused (~/bin/runner is not v0.9.5's), the config
        with the line runs on ~/bin/runner."""
        p, bare = self.rig()
        cfg = p.rpath('config.toml')
        for args, env in ((('run', '--staged'), None), (('run', 'x', 'y'), None),
                          (('run',), {'RUNNER': os.path.join(p.HOME, 'bin', 'runner.new'),
                                      'RUNNER_START_RUNNER': os.path.join(p.HOME, 'bin', 'runner.new')})):
            with self.subTest(args=args, env=bool(env)):
                r, ran = self.start(p, cfg, *args, env=env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(ran, [os.path.join(p.HOME, 'bin', 'runner')])
                r, ran = self.start(p, bare, *args, env=env)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('the config has no log-file key, and %s is not' % os.path.join(p.HOME, 'bin', 'runner'),
                              r.stderr)
                self.assertEqual(ran, [])


if __name__ == '__main__':
    unittest.main()
