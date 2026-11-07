"""03-runscaler.sh: the image it renders, `render DIGEST STAGED`, the rejected digests, and the unit's clock (plan D2,
D5; the changed-lines list, items 30-33 and 41).

- `real [DIGEST]`: with a DIGEST, that digest of the local registry; with none, the image the installed
  config.toml runs NOW (pool-image.sh's image_of, the same function), and ~/run/image.ref of RUN_USER only when there is
  no config.toml (a fresh host), read as hostile (runner-release.sh's rr_read: a FIFO, a symlink or a folder in its
  place is refused at once). So a person's `03 real` after a change of pool.env's numbers keeps the running image.
  The one-off modes `probe` and `c1` are cut (the changed-lines list, item 34): `real` and `render` are the modes, and the
  host config's five keys only they read are gone with them.
- `render DIGEST STAGED` (the updater's switch): renders the real sets with that digest into STAGED (a .toml file of
  ~/.config/runner) and validates it; it installs nothing (no binary, no unit, no daemon-reload, no config.toml), runs none
  of real's refusal controls, and refuses a set list other than config.toml's (an image switch never changes one). It
  refuses when a file 03 installs, as installed, is not the one this release pins: each one's PIN is read from ONE copy,
  pool-image.sh's PINS (~/build/setup/pool-image.sh), and runscaler's binary is one of the two THE RUNSCALERS names
  (BIN_SHA, the pinned v0.12.0, or WAYBACK_BIN_SHA, the way back: test_one_door).
- The validate (`runner-start validate`, stdout AND stderr: runner-start's REFUSE lines are on stderr) is classified by
  the ONE VALIDATE RULE (linux-docker/bin/validate-class, installed and pinned as runner-start is). render: PASS exits 0,
  API-ONLY exits 4 with STAGED kept (the window's tries decide), anything else exits 1 with nothing staged. real installs
  only on PASS.
- REJECTED: 03, as RS_USER, refuses a digest listed in ~/.local/state/runner-updater/rejected (the updater lock's folder):
  one `sha256:<64 hex>` per line; no file, or an empty one, lists none; any other content REFUSES, never "none".
- The unit runs runscaler with TZ=UTC (runscaler stamps its log in local time with no zone; the core requires UTC).
- THE LOG'S PLACE (runscaler 0.12 bump, slice H1): from runscaler v0.10.0 a config with no log-file key has runscaler
  write its log to ~/.local/state/runner/runner.log, and the runner.log beside the config, the file the updater and
  pool-image.sh read, stays and never grows (a quiet log that looks healthy: R1 blind, KEEP never accepts). 03 renders a
  top-level log-file of that file, built from the host config's RS_USER; runner-start runs a config only when its
  log-file is exactly that file, or, with no log-file key, only on the runscaler v0.9.5 runner (V095_SHA: the one
  release that then writes runner.log beside the config); else it REFUSES, naming `03-runscaler.sh real`.
The text cells run anywhere; the others run the real scripts (pin lines rewritten) in a container (support.Pool).
"""
import hashlib
import os
import re
import tarfile
import time
import unittest

from tests.hetzner.support import REPO, PASS_OUT, Pool, digest, needs_container, ref, sha256_file

S03 = os.path.join(REPO, 'linux-docker', 'setup', '03-runscaler.sh')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
RR = os.path.join(REPO, 'linux-docker', 'setup', 'runner-release.sh')
UNIT = os.path.join(REPO, 'linux-docker', 'config', 'runscaler.service')
START = os.path.join(REPO, 'linux-docker', 'bin', 'runner-start')
FACTS = os.path.join(REPO, 'linux-docker', 'setup', 'runner-facts.sh')
UPD = os.path.join(REPO, 'linux-docker', 'bin', 'runner-updater')
README = os.path.join(REPO, 'linux-docker', 'README.md')
FIX = os.path.join(REPO, 'tests', 'studio', 'fixtures', 'validate')
V0, V2, X = digest(10), digest(12), digest(20)
V095 = 'd9d1e5779ad5c7220dddcba1a2464f50f680f9d8102f784da63f15a052523948'   # runscaler v0.9.5's linux-amd64 runner
INSTALLED = ('bin/runner', 'bin/runner-start', 'bin/pool-ready', 'bin/validate-class',
             '.config/systemd/user/runscaler.service')


def fixture(name):
    with open(os.path.join(FIX, name), encoding='utf-8') as f:
        return f.read()


def changed(a, b):
    """The lines in which two texts of one line count differ: [(a's, b's)]."""
    la, lb = a.splitlines(), b.splitlines()
    if len(la) != len(lb):
        return ['line counts %d and %d' % (len(la), len(lb))]
    return [(x, y) for x, y in zip(la, lb) if x != y]


def function(path, name):
    with open(path) as f:
        text = f.read()
    m = re.search(r'^%s\(\) \{.*?^\}\n' % name, text, re.M | re.S)
    return m.group(0) if m else None


def assignment(path, name):
    with open(path) as f:
        return re.findall(r'^%s=(.*)$' % name, f.read(), re.M)


class Text(unittest.TestCase):
    def test_image_of_is_pool_image_sh_s_own(self):
        """`03 real` with no DIGEST renders the image config.toml runs by pool-image.sh's rule (D2): the same function
        and the same pattern, byte for byte."""
        mine, theirs = function(S03, 'image_of'), function(PIMG, 'image_of')
        self.assertIsNotNone(theirs)
        self.assertEqual(mine, theirs)
        self.assertEqual(assignment(S03, 'IMGRE'), assignment(PIMG, 'IMGRE'))
        self.assertEqual(len(assignment(S03, 'IMGRE')), 1)

    def test_the_rejected_file_is_in_the_updater_lock_s_folder(self):
        lock = assignment(RR, 'RR_LOCK')
        rej = assignment(S03, 'REJECTED')
        self.assertEqual((len(lock), len(rej)), (1, 1), (lock, rej))
        self.assertEqual(rej[0], lock[0].rsplit('/', 1)[0] + '/rejected')

    def test_the_one_off_modes_probe_and_c1_are_cut(self):
        with open(S03) as f:
            text = f.read()
        for gone in ('PROBE_SET', 'PROBE_LABEL', 'C1_SET', 'C1_GROUP', 'C1_LABEL', 'MODE probe', 'MODE c1'):
            self.assertNotIn(gone, text)
        with open(os.path.join(REPO, 'linux-docker', 'host.conf.example')) as f:
            self.assertNotRegex(f.read(), r'(?m)^(PROBE|C1)_')

    def test_the_unit_runs_runscaler_in_utc(self):
        with open(UNIT) as f:
            text = f.read()
        service = text.split('\n[Service]\n', 1)[1].split('\n[', 1)[0]
        self.assertIn('\nEnvironment=TZ=UTC\n', '\n' + service + '\n')

    def test_the_readers_read_runner_log_in_runscaler_s_folder(self):
        """THE LOG'S PLACE: the file 03's log-file names is the one the readers read. pool-image.sh and the updater set
        R to ~/.config/runner; runner-facts.sh's log_pos opens "$R/runner.log", and so does pool-image.sh's restart-cut
        scan. (LogFile's cells run log_pos with R set so.)"""
        with open(PIMG) as f:
            pimg = f.read()
        with open(UPD) as f:
            upd = f.read()
        with open(FACTS) as f:
            facts = f.read()
        self.assertEqual(re.findall(r'^R=([^;\s]+)', pimg, re.M), ['$HOME/.config/runner'])
        self.assertEqual(re.findall(r'^R=([^;\s]+)', upd, re.M), ['$HOME/.config/runner'])
        self.assertEqual(facts.count('\' "$R/runner.log" "$@" 2> /dev/null < /dev/null\n}'), 1)   # log_pos's one open
        cut = [l for l in pimg.splitlines() if l.startswith('cut=$(awk ')]
        self.assertEqual(len(cut), 1, cut)
        self.assertIn(' "$R/runner.log" ', cut[0])

    def test_runner_start_s_v0_9_5_runner_is_03_s_way_back(self):
        """runner-start runs a config with NO log-file key only on the runner V095_SHA names (runscaler v0.9.5's): from
        runscaler 0.12 bump slice H2a that is 03's WAY-BACK runscaler (THE RUNSCALERS: WAYBACK_BIN_SHA, ONE value in two
        files, bound here), and no longer the one 03 pins (BIN_SHA, v0.12.0's): a live config of an older 03, with no
        log-file key, keeps starting on a host that still runs v0.9.5, and on the way back. V095_SHA is runscaler
        v0.9.5's linux-amd64 `runner` by its own constant (b2eb739's 03 BIN_SHA)."""
        self.assertEqual(assignment(START, 'V095_SHA'), [V095], 'runner-start names the v0.9.5 runner once, by sha256')
        self.assertEqual(assignment(START, 'V095_SHA'), assignment(S03, 'WAYBACK_BIN_SHA'))
        self.assertEqual(len(assignment(S03, 'BIN_SHA')), 1)
        self.assertNotEqual(assignment(S03, 'BIN_SHA'), assignment(START, 'V095_SHA'))

    def test_the_readme_says_03_renders_the_log_file_line_and_the_next_up_adds_it(self):
        """Install step 9 says what 03 renders for runscaler's log and what runner-start refuses. The upgrade notes and
        the hand-copy move point to "The log-file line", which gives NO command (H1 review r1, Opus F1: its hand step,
        03 real and a bare restart, put every host-config value live unchecked): a host installed before this release
        runs on unchanged (v0.9.5), and the next `pool-image.sh up`, or the updater's switch, adds the line with its
        checks and its idle restart, and a `back` to a config kept before the line is accepted (LogFileUp runs each).
        The hand-copy move's promise holds again: an `up` whose host config is not the one the pool runs stops with
        config.toml as it was, and nothing restarts (LogFileUp's control); no sentence sends a person to a hand step."""
        with open(README) as f:
            text = f.read()
        step9 = text.split('\n9. **runscaler (RS_USER).**', 1)[1].split('\n10. ', 1)[0]
        for w in ('`log-file`', '`runner.log`', '`runner-start` refuses', 'v0.9.5'):
            self.assertIn(w, step9)
        up = text.split('\n## Upgrading from a release before this one\n', 1)[1].split('\n## ', 1)[0]
        self.assertIn('"The log-file line"', up)
        self.assertEqual(text.count('\n## The log-file line\n'), 1)
        sec = text.split('\n## The log-file line\n', 1)[1].split('\n## ', 1)[0]
        self.assertEqual(sec.count('```'), 0, 'the section gives no command: the next up puts the line in')
        for w in ('`log-file`', 'v0.9.5', 'unchanged', '`pool-image.sh up`', "the updater's switch", 'idle', '`back`'):
            self.assertIn(w, sec)
        hand = text.split('\n## A host that already runs these scripts from a hand copy\n', 1)[1].split('\n## ', 1)[0]
        self.assertIn('"The log-file line"', hand)
        self.assertIn('If a value of the host config is not the one the pool runs, that `up` stops with config.toml as '
                      'it was, and nothing restarts.', hand)
        self.assertIn('do not run 03-runscaler.sh by hand on the running pool', hand.lower())
        for s in ('do "The log-file line"', 'Apart from that one run', 'systemctl --user restart runscaler && sleep'):
            self.assertNotIn(s, text)

    def test_the_compare_s_log_file_key_line_is_03_s(self):
        """THE LOG-FILE LINE's one spelling (runscaler 0.12 bump, slice H2a: the KEY line alone, and comments are not
        content): the line THE CONFIG COMPARE (runner-release.sh's rr_same_but_image, ONE copy) lets a newer config add
        is RR_LOGK, `log-file = "$HOME/.config/runner/runner.log"`: the key line 03's header() renders right after its
        log-level line (a comment line between them is no content), `log-file = "$LOGF"` in 03 (LOGF, RS_USER's
        ~/.config/runner/runner.log, runner-start's spelling): the same file on a host, whose RS_USER's home is
        /home/RS_USER. pool-image.sh has no compare of its own (no same_but_image, LOGC or LOGK): its five callers call
        rr_same_but_image. LogFileUp runs it on 03's real render."""
        hdr = function(S03, 'header')
        self.assertIsNotNone(hdr)
        self.assertEqual(re.findall(r'\nlog-level = "info"\n(?:#[^\n]*\n)*(log-file = [^\n]*)\n', hdr),
                         ['log-file = "$LOGF"'], hdr)
        self.assertEqual(assignment(S03, 'LOGF')[0].split('   #')[0], '/home/${RS_USER}/.config/runner/runner.log')
        with open(RR) as f:
            rr = f.read()
        self.assertEqual(re.findall(r'^RR_LOGK=("[^"\\]*(?:\\.[^"\\]*)*")', rr, re.M),
                         [r'"log-file = \"$HOME/.config/runner/runner.log\""'])
        with open(PIMG) as f:
            pimg = f.read()
        self.assertEqual(re.findall(r'(?m)^(same_but_image\(\)|LOGC=|LOGK=)', pimg), [])
        self.assertEqual(len(re.findall(r'\brr_same_but_image "\$', pimg)), 5, 'the five callers')


@needs_container
class DefaultImage(unittest.TestCase):
    """D2 :120-122: production runs D(V2), image.ref names an older D(V0), pool.env's numbers change: `03 real` keeps
    D(V2) and changes only the numbers. Control: with no config.toml it renders image.ref's digest."""

    def test_real_with_no_digest_renders_the_image_config_toml_runs_not_image_ref(self):
        p = Pool(self)
        p.production(V2)
        old = p.config()
        p.image_ref(V0)
        p.pool_env(CONCURRENT=3, MAX=2)
        r = p.s03('real')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('03 DONE (real)', r.stdout)
        self.assertEqual(p.images(), [ref(V2)] * 2)
        self.assertEqual(changed(old, p.config()), [('concurrent = 4', 'concurrent = 3'),
                                                    ('max-runners = 3', 'max-runners = 2')])

    def test_control_with_no_config_toml_it_renders_image_ref(self):
        p = Pool(self)
        p.image_ref(V0)
        r = p.s03('real')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(p.images(), [ref(V0)] * 2)

    def test_a_hostile_image_ref_is_refused_at_once(self):
        """PLAN D1: RUN_USER's files are HOSTILE to RS_USER. With no config.toml, 03 reads RUN_USER's image.ref through
        runner-release.sh's rr_read (one open, no symlink, never blocks): a FIFO (no writer: `cat` would wait for ever),
        a symlink (to a file that names another image) or a folder in its place is refused at once, exit 1, and nothing
        is installed. Under `timeout` (support.Pool.bounded: exit 124 is a hang; no time is asserted). Control: the
        plain image.ref above (test_control_with_no_config_toml_it_renders_image_ref)."""
        for kind in ('fifo', 'link', 'folder'):
            with self.subTest(kind):
                p = Pool(self)
                f = os.path.join(p.HOME, 'run', 'image.ref')
                if kind == 'fifo':
                    os.mkfifo(f)
                elif kind == 'link':
                    os.symlink(p.write(p.path('elsewhere'), ref(X) + '\n'), f)
                else:
                    os.mkdir(f)
                r = p.bounded(['bash', os.path.join(p.build, 'setup', '03-runscaler.sh'), 'real'])
                self.assertNotEqual(r.returncode, 124, '03 hung on a %s as image.ref' % kind)
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertIn('FAIL no config.toml and no image.ref from B2: %s: it is not a plain file' % f, r.stdout)
                self.assertIsNone(p.config())
                self.assertNotIn(ref(X), r.stdout)

    def test_a_digest_argument_renders_that_digest_and_nothing_else_changes(self):
        p = Pool(self)
        p.production(V2)
        old = p.config()
        r = p.s03('real', X)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(changed(old, p.config()), [('runner-image = "%s"' % ref(V2), 'runner-image = "%s"' % ref(X))] * 2)

    def test_a_config_toml_that_names_no_one_image_refuses(self):
        p = Pool(self)
        p.production(V2)
        text = p.config()
        bad = text[::-1].replace(ref(V2)[::-1], ref(V0)[::-1], 1)[::-1]     # the small set's line names another
        p.write(p.rpath('config.toml'), bad, 0o600)
        before = p.snapshot()
        r = p.s03('real')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('config.toml does not name ONE runner image', r.stdout)
        self.assertEqual(p.snapshot(), before)


class Rig:
    """A Pool whose production runs D(V2), and STAGED = ~/.config/runner/config.staged.toml."""

    def __init__(self, test):
        self.p = Pool(test)
        self.p.production(V2)
        self.staged = self.p.rpath('config.staged.toml')

    def render(self, d=X):
        self.p.write(self.p.path('logs', 'runner.log'), '')
        self.p.write(self.p.path('logs', 'systemctl.log'), '')
        self.p.write(self.p.path('logs', 'docker.log'), '')
        return self.p.s03('render', d, self.staged)

    def validated(self):
        """The configs runscaler's validate ran on during the last render: their sha256s."""
        return [c['config'] for c in self.p.calls('runner') if c['argv'][:1] == ['validate']]

    def without_staged(self, snap):
        return {k: v for k, v in snap.items() if not k.endswith('/config.staged.toml')}


@needs_container
class Render(unittest.TestCase):
    def test_render_stages_the_digest_validated_and_installs_nothing(self):
        g = Rig(self)
        before = g.p.snapshot()
        r = g.render()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('VALIDATE PASS', r.stdout)
        self.assertEqual(g.p.images('config.staged.toml'), [ref(X)] * 2)
        self.assertEqual(changed(g.p.config(), g.p.config('config.staged.toml')),
                         [('runner-image = "%s"' % ref(V2), 'runner-image = "%s"' % ref(X))] * 2)
        self.assertEqual(os.stat(g.staged).st_mode & 0o777, 0o600)
        self.assertEqual(g.without_staged(g.p.snapshot()), before, 'render changed a file other than STAGED')
        self.assertNotIn('--user daemon-reload', g.p.lines('systemctl'))
        self.assertEqual(g.validated(), [sha256_file(g.staged)], 'one validate, of STAGED itself')
        # none of real's refusal controls: D1 is asked twice (03's own check, and runner-start's validate of STAGED)
        asked = [c for c in g.p.calls('docker') if c[:1] == ['-H'] and 'version' in c]
        self.assertEqual(len(asked), 2, asked)

    def test_control_real_runs_its_controls(self):
        g = Rig(self)
        g.render()                       # the logs reset
        g.p.write(g.p.path('logs', 'docker.log'), '')
        r = g.p.s03('real', X)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        asked = [c for c in g.p.calls('docker') if c[:1] == ['-H'] and 'version' in c]
        self.assertGreater(len(asked), 2)

    def test_render_refuses_a_set_list_other_than_config_toml_s(self):
        g = Rig(self)
        text = g.p.config()
        g.p.write(g.p.rpath('config.toml'), text.replace('name = "linux-ci-small"', 'name = "linux-ci-other"'), 0o600)
        r = g.render()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('sets', r.stdout)
        self.assertFalse(os.path.lexists(g.staged))
        self.assertEqual(g.validated(), [])

    def test_render_refuses_an_installed_file_that_is_not_its_pin(self):
        for rel in INSTALLED:
            with self.subTest(rel):
                g = Rig(self)
                with open(os.path.join(g.p.HOME, rel), 'a') as f:
                    f.write('\n# changed by hand\n')
                r = g.render()
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(os.path.join(g.p.HOME, rel), r.stdout)
                self.assertFalse(os.path.lexists(g.staged))
                self.assertEqual(g.validated(), [])

    def test_render_reads_the_pins_of_pool_image_sh(self):
        """ONE copy of the pins: what pool-image.sh in ~/build pins is what render compares with. Its runner-start pin
        moved, its validate-class pin gone, or a PINS line of another shape: refused. The control: as it is, staged."""
        pimg = None

        def edit(g, change):
            nonlocal pimg
            pimg = os.path.join(g.p.build, 'setup', 'pool-image.sh')
            with open(pimg) as f:
                text = f.read()
            new = change(text)
            self.assertNotEqual(new, text)
            g.p.write(pimg, new, 0o644)

        cases = (
            ('runner-start pinned to other bytes', 'bin/runner-start',
             lambda t: re.sub(r'(\$B/bin/runner-start=)[0-9a-f]{64}', r'\g<1>' + 'e' * 64, t)),
            ('no pin for validate-class', 'bin/validate-class',
             lambda t: re.sub(r'\n\$B/bin/validate-class=[0-9a-f]{64}', '', t)),
            ('a PINS line of another shape (the one pinning 03 itself, no file render checks)', 'PINS block',
             lambda t: re.sub(r'(PINS="\$S03=[0-9a-f]{64})', r'\1 # a comment', t)),
        )
        for why, says, change in cases:
            with self.subTest(why):
                g = Rig(self)
                edit(g, change)
                r = g.render()
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn(says, r.stdout)
                self.assertFalse(os.path.lexists(g.staged))
        g = Rig(self)
        r = g.render()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)

    def test_render_classifies_its_validate_by_the_one_rule(self):
        cases = (('PASS', 0, PASS_OUT, 0, True), ('API-ONLY', 1, fixture('api-only-real.txt'), 4, True),
                 ('NON-API', 1, fixture('non-api-real.txt'), 1, False),
                 ('UNKNOWN', 1, 'Error: failed to read config file\n', 1, False),
                 ('UNKNOWN', 0, '  ✓ Docker connectivity\n', 1, False))
        for cls, rc, out, exit_, kept in cases:
            with self.subTest(cls, rc=rc):
                g = Rig(self)
                g.p.write(g.staged, 'a stale file\n', 0o600)
                g.p.runner = {'rc': rc, 'out': out}
                r = g.render()
                self.assertEqual(r.returncode, exit_, r.stdout[-3000:] + r.stderr)
                self.assertIn('VALIDATE %s\n' % cls, r.stdout)
                self.assertEqual(os.path.lexists(g.staged), kept)
                if kept:
                    self.assertEqual(g.p.images('config.staged.toml'), [ref(X)] * 2)
                    self.assertIn(out.splitlines()[0], r.stdout)        # the whole output, for the journal

    def test_a_refuse_on_stderr_only_is_non_api(self):
        """runner-start's REFUSE lines go to stderr: 03 classifies stdout AND stderr. The local registry does not
        answer: runner-start refuses on stderr alone. The control: it answers, PASS."""
        for registry_rc, cls, code in ((7, 'NON-API', 1), (0, 'PASS', 0)):
            with self.subTest(registry_rc=registry_rc):
                g = Rig(self)
                g.p.curl['registry_rc'] = registry_rc
                r = g.render()
                self.assertEqual(r.returncode, code, r.stdout[-3000:] + r.stderr)
                self.assertIn('VALIDATE %s\n' % cls, r.stdout)
                if registry_rc:
                    self.assertIn('runner-start: REFUSE the local registry does not answer', r.stdout)
                    self.assertFalse(os.path.lexists(g.staged))

    def test_real_installs_only_on_pass(self):
        for cls, rc, out, ok in (('API-ONLY', 1, fixture('api-only-real.txt'), False), ('PASS', 0, PASS_OUT, True)):
            with self.subTest(cls):
                g = Rig(self)
                before = g.p.config()
                g.p.runner = {'rc': rc, 'out': out}
                r = g.p.s03('real', X)
                self.assertEqual(r.returncode == 0, ok, r.stdout[-3000:] + r.stderr)
                self.assertIn('VALIDATE %s\n' % cls, r.stdout)
                self.assertEqual(g.p.images(), [ref(X) if ok else ref(V2)] * 2)
                if not ok:
                    self.assertEqual(g.p.config(), before)

    def test_a_host_config_refusal_leaves_no_staged_file(self):
        """render's header: a failure leaves nothing staged, a STAGED from before included; the host config's refusal
        comes first of all, so the cleanup is set before it. The control: the stale STAGED of the classify cell, which
        a PASS replaces."""
        g = Rig(self)
        g.p.write(g.staged, 'a stale file\n', 0o600)
        os.rename(g.p.path('host.conf'), g.p.path('host.conf.away'))
        r = g.render()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('REFUSE no host config', r.stderr)
        self.assertFalse(os.path.lexists(g.staged))
        self.assertEqual(g.validated(), [])

    def test_render_without_the_token_stages_nothing(self):
        g = Rig(self)
        os.remove(g.p.rpath('token-owner'))
        r = g.render()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse(os.path.lexists(g.staged))

    def test_usage(self):
        g = Rig(self)
        R = g.p.R
        for args in (('render',), ('render', X), ('render', 'sha256:' + 'a' * 63, g.staged), ('render', X, g.staged, 'x'),
                     ('render', X, '/tmp/config.staged.toml'), ('render', X, R + '/config.toml'),
                     ('render', X, R + '/config.real.toml'), ('render', X, R + '/staged.txt'),
                     ('render', X, R + '/sub/x.toml'), ('render', ref(X), g.staged), ('real', 'x'), ('real', X, 'x'),
                     ('probe', X), ('upgrade',), ('probe',), ('c1',), ('real', '--image-only'),
                     ('real', X, '--image'), ('real', X, '--image-only', '--image-only'),
                     ('render', X, g.staged, '--image-only'), ('stage',), ('stage', '0.12.0'),
                     ('stage', '0.12.0', 'all'), ('stage', '0.12', 'content'), ('stage', '0.12.0', 'bytes', 'x'),
                     ('stage', X, 'content')):
            with self.subTest(args=args):
                before = g.p.snapshot()
                g.p.write(g.p.path('logs', 'docker.log'), '')
                r = g.p.s03(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn('usage', r.stdout + r.stderr)
                self.assertEqual(g.p.snapshot(), before)
                self.assertEqual(g.p.calls('docker'), [])


@needs_container
class Rejected(unittest.TestCase):
    def test_a_listed_digest_is_refused_and_nothing_staged(self):
        g = Rig(self)
        g.p.rejected('%s\n%s\n' % (V0, X))
        g.p.write(g.staged, 'a stale file\n', 0o600)
        before = g.without_staged(g.p.snapshot())
        r = g.render()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('rejected', r.stdout)
        self.assertIn(X, r.stdout)
        self.assertFalse(os.path.lexists(g.staged))
        self.assertEqual(g.without_staged(g.p.snapshot()), before)
        self.assertEqual(g.validated(), [])

    def test_an_unlisted_digest_renders(self):
        for why, text in (('no file', None), ('an empty file', ''), ('another digest', V0 + '\n'),
                          ('another digest, no final newline', V0)):
            with self.subTest(why):
                g = Rig(self)
                g.p.rejected(text)
                r = g.render()
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.p.images('config.staged.toml'), [ref(X)] * 2)

    def test_a_malformed_file_refuses_never_reads_as_none(self):
        cases = (('a blank line', V0 + '\n\n'), ('upper-case hex', V0.upper() + '\n'), ('63 hex', V0[:-1] + '\n'),
                 ('no sha256: prefix', V0[7:] + '\n'), ('a CR', V0 + '\r\n'), ('a trailing space', V0 + ' \n'),
                 ('a comment', '# none yet\n'), ('a NUL byte', V0[:20] + '\0' + V0[20:] + '\n'),
                 ('an image reference', ref(V0) + '\n'), ('a second field', V0 + ' 2.338.2\n'))
        for why, text in cases:
            with self.subTest(why):
                g = Rig(self)
                g.p.rejected(text)
                r = g.render()
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('rejected', r.stdout)
                self.assertFalse(os.path.lexists(g.staged))
        with self.subTest('a folder'):
            g = Rig(self)
            p = g.p.rejected(None)
            os.makedirs(p)
            r = g.render()
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertFalse(os.path.lexists(g.staged))

    def test_real_refuses_a_rejected_digest_and_keeps_config_toml(self):
        for why, listed, args in (('the argument', X, (X,)), ('the image config.toml runs', V2, ())):
            with self.subTest(why):
                g = Rig(self)
                g.p.rejected(listed + '\n')
                before = g.p.snapshot()
                r = g.p.s03('real', *args)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('rejected', r.stdout)
                self.assertEqual(g.p.snapshot(), before)
        g = Rig(self)                      # the control: not listed
        g.p.rejected(V0 + '\n')
        r = g.p.s03('real', X)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.images(), [ref(X)] * 2)


@needs_container
class WhileAWindowIsThere(unittest.TestCase):
    """S2b-3c-1 r3 FOLD (Opus r3 F8): `03 real` and `03 render` REFUSE while the updater's window journal is there
    (~/.local/state/runner-updater/window: open, or closed and not yet applied), naming `runner-updater status`, and
    change nothing: no config.toml, no STAGED (a STAGED of the window's own is left as it is), no validate. A person's
    `03 real` of new numbers would otherwise complete a switch the window left waiting, as a hand change. The one
    exception: `render` run BY the window, the updater's child holding the updater lock on fd 9 (runner-release.sh's
    rr_held), which stages, and whose validate never gets fd 9 (03 closes it). The controls: no journal: `real`
    installs the new numbers, `render` stages."""

    OPEN = 'window 20261105000000-1\nkind switch\n'
    CLOSED = 'window 20261105000000-1\nkind switch\nend nothing\nprev none\ninstalled none none none\nclosed 9\n'

    def plant(self, g, text):
        os.makedirs(Pool.STATE, mode=0o700, exist_ok=True)
        return g.p.write(os.path.join(Pool.STATE, 'window'), text, 0o600)

    def test_real_refuses_while_a_window_journal_is_there(self):
        for why, text in (('open', self.OPEN), ('closed, not applied', self.CLOSED)):
            with self.subTest(why):
                g = Rig(self)
                self.plant(g, text)
                g.p.pool_env(CPU=5)
                g.p.write(g.p.path('logs', 'runner.log'), '')
                before = g.p.snapshot()
                r = g.p.s03('real')
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertIn('runner-updater status', r.stdout)
                self.assertIn('REFUSE', r.stdout)
                self.assertEqual(g.p.snapshot(), before)
                self.assertEqual(g.validated(), [])

    def test_control_real_with_no_journal_installs_the_new_numbers(self):
        g = Rig(self)
        g.p.pool_env(CPU=5)
        r = g.p.s03('real')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('\ncpu = 5\n', g.p.config())

    def test_render_refuses_unless_the_window_runs_it(self):
        """A person's render (no fd 9), and one with fd 9 open on the lock but held by nobody: REFUSE, and a STAGED that
        was there stays as it was. The window's own (the HOLDER's child): it stages, and the validate it runs has no fd
        9. With no journal, a person's render stages (the cells above)."""
        unheld = ['bash', '-c', 'install -d -m 700 "${0%/*}" && exec 9>> "$0" && exec "$@"',
                  os.path.join(Pool.STATE, 'lock')]
        for why, holder, ok in (('a person', None, False), ('fd 9 on the lock, held by nobody', unheld, False),
                                ('the window, the updater lock held', 'holder', True)):
            for text in (self.OPEN, self.CLOSED):
                with self.subTest(why, journal=text.splitlines()[-1]):
                    g = Rig(self)
                    self.plant(g, text)
                    g.p.write(g.staged, 'a staged file of the window\n', 0o600)
                    g.p.write(g.p.path('logs', 'runner.log'), '')
                    argv = ['bash', os.path.join(g.p.build, 'setup', '03-runscaler.sh'), 'render', X, g.staged]
                    r = g.p.run((g.p.holder() if holder == 'holder' else holder or []) + argv)
                    if ok:
                        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                        self.assertEqual(g.p.images('config.staged.toml'), [ref(X)] * 2)
                        vs = [c for c in g.p.calls('runner') if c['argv'][:1] == ['validate']]
                        self.assertEqual([c['fd9'] for c in vs], [False])
                        continue
                    self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                    self.assertIn('runner-updater status', r.stdout)
                    self.assertEqual(g.p.read(g.staged), 'a staged file of the window\n')
                    self.assertEqual(g.validated(), [])


@needs_container
class Clock(unittest.TestCase):
    def unit_env(self, p):
        """The Environment= assignments of the INSTALLED unit (KEY=VALUE, one per line)."""
        with open(os.path.join(p.HOME, '.config', 'systemd', 'user', 'runscaler.service')) as f:
            return dict(l[len('Environment='):].split('=', 1) for l in f.read().splitlines()
                        if l.startswith('Environment='))

    def test_runscaler_s_clock_is_utc_under_the_unit_whatever_the_zone(self):
        """runner-start run, as the unit starts it (the installed unit's Environment over the zone the user manager
        has), execs runscaler, whose `date +%z` is +0000. The control: the same start without the unit's Environment
        reads the zone's own offset."""
        p = Pool(self)
        p.production(V2)
        env = self.unit_env(p)
        start = os.path.join(p.HOME, 'bin', 'runner-start')
        for zone, offset in (('XST-5', '+0500'), ('YST+3', '-0300')):
            with self.subTest(zone=zone):
                base = dict(p.env(), TZ=zone)
                r = p.run([start, 'run'], env=dict(base, **env))
                self.assertEqual((r.returncode, r.stdout), (0, 'TZ-CHECK +0000\n'), r.stderr)
                r = p.run([start, 'run'], env=base)
                self.assertEqual((r.returncode, r.stdout), (0, 'TZ-CHECK %s\n' % offset), r.stderr)


def without_log_file(text):
    """A config less its log-file line: the render as 03 made it before this release."""
    return re.sub(r'^log-file = .*\n', '', text, flags=re.M)


@needs_container
class LogFile(unittest.TestCase):
    """THE LOG'S PLACE (the module's header): 03's render pins runscaler's log to the file the readers read, and
    runner-start runs no config whose log is another file. Each refusal names `03-runscaler.sh real`, which renders the
    right line. A config with no log-file key (the live config until 03 renders again) runs only on the runscaler
    v0.9.5 runner, by sha256; the pool cells' runscaler is a substitute, so it is that runner only where a cell makes
    the INSTALLED runner-start name it (its V095_SHA line)."""

    def rig(self):
        p = Pool(self)
        p.production(V2)
        return p, os.path.join(p.R, 'runner.log')

    def start(self, p, text):
        """runner-start validate (the installed one) of text as ~/.config/runner/c.toml: (its result, the configs
        runscaler's validate ran on)."""
        cfg = p.write(p.rpath('c.toml'), text, 0o600)
        p.write(p.path('logs', 'runner.log'), '')
        r = p.run([os.path.join(p.HOME, 'bin', 'runner-start'), 'validate'], env=dict(p.env(), RUNNER_START_CONFIG=cfg))
        return r, [c['config'] for c in p.calls('runner') if c['argv'][:1] == ['validate']]

    def variants(self, p, logf):
        """The render with no log-file line (bare); top(v): bare with a top-level log-file of v; table(head): the right
        top-level line, plus a log-file key of that file in the first table under head (so each config breaks ONE
        rule: the table's key alone)."""
        bare = without_log_file(p.config())
        self.assertEqual(bare.count('\nlog-level = "info"\n'), 1)
        for head in ('[docker]\n', '[[scaleset]]\n', '[scaleset.docker]\n'):
            self.assertIn(head, bare)

        def top(v):
            return bare.replace('\nlog-level = "info"\n', '\nlog-level = "info"\nlog-file = %s\n' % v)

        def table(head):
            return top('"%s"' % logf).replace(head, head + 'log-file = "%s"\n' % logf, 1)
        return bare, top, table

    def test_the_render_names_the_file_the_readers_read_once_at_the_top_level(self):
        """Item 1: config.toml, as 03 real renders and installs it, has exactly one log-file line, at the top level
        (before its first table, and so in no [docker] or [[scaleset]] table), naming RS_USER's
        ~/.config/runner/runner.log; and that is the file log_pos opens, R set as the readers set it (Text): the inode it
        reports is that file's."""
        import tomllib
        p, logf = self.rig()
        text = p.config()
        lines = text.splitlines()
        want = 'log-file = "%s"' % logf
        self.assertEqual([l for l in lines if 'log-file' in l and not l.startswith('#')], [want])
        first_table = next(i for i, l in enumerate(lines) if l.startswith('['))
        self.assertLess(lines.index(want), first_table)
        data = tomllib.loads(text)
        self.assertEqual(data['log-file'], logf)
        self.assertNotIn('log-file', data['docker'])
        for s in data['scaleset']:
            self.assertNotIn('log-file', s)
            self.assertNotIn('log-file', s.get('docker', {}))
        r = p.lib('R=$HOME/.config/runner; log_pos', source='runner-facts.sh')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(int(r.stdout.split()[0]), os.stat(data['log-file']).st_ino)

    def test_runner_start_refuses_every_other_log_file_naming_03(self):
        """Item 2: another file (v0.12.0's own default among them), a relative path, an empty one (no log at all), a
        value that is no string, the key inside a table the render writes, or NO key while the runner is not v0.9.5's:
        REFUSE (stderr, exit 1) by its own rule's line, naming `03-runscaler.sh real`, and runscaler's validate never
        runs."""
        p, logf = self.rig()
        bare, top, table = self.variants(p, logf)
        v012 = os.path.join(p.HOME, '.local', 'state', 'runner', 'runner.log')
        other = 'log-file is %s, not the runner.log the updater reads'
        intable = 'the key %slog-file is in a table'
        for why, text, says in (
                ("v0.12.0's own default", top('"%s"' % v012), other % repr(v012)),
                ('another file', top('"/tmp/runner.log"'), other % "'/tmp/runner.log'"),
                ('a relative path', top('"runner.log"'), other % "'runner.log'"),
                ('an empty one (no log at all)', top('""'), other % "''"),
                ('no string', top('1'), other % '1'),
                ('in [docker]', table('[docker]\n'), intable % 'docker.'),
                ('in a [[scaleset]]', table('[[scaleset]]\n'), intable % 'scaleset[0].'),
                ('in [scaleset.docker]', table('[scaleset.docker]\n'), intable % 'scaleset[1].docker.'),
                ('no log-file key, and the runner is not v0.9.5', bare,
                 "the config has no log-file key, and %s is not runscaler v0.9.5's runner" %
                 os.path.join(p.HOME, 'bin', 'runner'))):
            with self.subTest(why):
                r, ran = self.start(p, text)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertTrue(r.stderr.startswith('runner-start: REFUSE ' + says), r.stderr)
                self.assertIn('03-runscaler.sh real', r.stderr)
                self.assertEqual(ran, [], 'runscaler ran on it')

    def test_control_the_readers_file_runs_on_any_runner(self):
        """The control of the refusals: the log-file line 03 renders (its own render, and the line put into the bare
        render by hand) runs, on a runner that is not v0.9.5's too."""
        p, logf = self.rig()
        bare, top, table = self.variants(p, logf)
        for why, text in (("03's render", p.config()), ('the line, at the top', top('"%s"' % logf))):
            with self.subTest(why):
                r, ran = self.start(p, text)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(ran, [sha256_file(p.rpath('c.toml'))])

    def test_control_no_log_file_key_runs_on_the_v0_9_5_runner(self):
        """The decision for a config with NO log-file key: on the v0.9.5 runner (V095_SHA: here the INSTALLED
        runner-start made to name the substitute) it runs, so the live config keeps starting until 03 renders the
        line; the same config on any other runner is refused (test_runner_start_refuses_every_other_log_file_naming_03)."""
        p, logf = self.rig()
        bare, top, table = self.variants(p, logf)
        rs = os.path.join(p.HOME, 'bin', 'runner-start')
        with open(rs) as f:
            t = f.read()
        pins = re.findall(r'^V095_SHA=[0-9a-f]{64}$', t, re.M)
        self.assertEqual(len(pins), 1, 'runner-start names the v0.9.5 runner by ONE V095_SHA line')
        p.write(rs, t.replace(pins[0] + '\n', 'V095_SHA=%s\n' % sha256_file(os.path.join(p.HOME, 'bin', 'runner'))),
                0o755)
        r, ran = self.start(p, bare)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(ran, [sha256_file(p.rpath('c.toml'))])


UPV, UPOLDV = '2.339.0', '2.338.2'
UPOLD, UPNEW = digest(38), digest(39)
LEVEL = 'log-level = "info"\n'
TWO = re.compile(r'^log-level = "info"\n((# log-file: [^\n]*\n)(log-file = [^\n]*\n))', re.M)


def after_level(text, add):
    """TEXT with ADD put right after its one log-level line: the render's place of the two log-file lines."""
    if text.count('\n' + LEVEL) != 1:
        raise AssertionError('no single log-level line: %r' % text[:400])
    return text.replace('\n' + LEVEL, '\n' + LEVEL + add, 1)


OLDC = '# a comment line of a config an older release rendered\n'
H1HEAD = '# runscaler v0.9.5 config, MODE real, rendered by 03-runscaler.sh. 0600.\n'   # b2eb739's header line


def older(text):
    """TEXT with OLDC right after its first line (03's header comment): a config whose comments differ, as one an
    older release rendered (no release this cell knows renders OLDC, b2eb739's neither)."""
    head, rest = text.split('\n', 1)
    return head + '\n' + OLDC + rest


WAYBACK_MARK = b'# the way-back runscaler of the cell: the same program, other bytes\n'


def guard(p, path=None):
    """THE INSTALLED GUARD: ~/bin/runner-start validate (the one installed now, its own V095_SHA and ~/bin/runner) of a
    .toml copy of PATH (default config.toml), as the unit's start would check that pair: (its result, [the
    runscaler validates it ran: {exe, sha, config}]). support.py's systemctl substitute does not run runner-start, so a
    cell that claims a pair starts runs this."""
    path = path or p.rpath('config.toml')
    cfg = p.write(p.rpath('guard.toml'), p.read(path), 0o600)
    p.write(p.path('logs', 'runner.log'), '')
    r = p.run([os.path.join(p.HOME, 'bin', 'runner-start'), 'validate'], env=dict(p.env(), RUNNER_START_CONFIG=cfg))
    ran = [c for c in p.calls('runner') if c['argv'][:1] == ['validate']]
    os.remove(cfg)
    return r, ran


def starts(test, p, path=None):
    """The installed guard passes the pair (~/bin/runner, PATH): no REFUSE, and runscaler's validate ran, by
    ~/bin/runner."""
    r, ran = guard(p, path)
    test.assertNotIn('runner-start: REFUSE', r.stderr, 'the installed guard refuses the pair')
    test.assertEqual([c['exe'] for c in ran], [os.path.join(p.HOME, 'bin', 'runner')], r.stdout + r.stderr)


def way_back(test, p, install=True):
    """THE WAY-BACK RUNSCALER of a Pool (03's WAYBACK_BIN_SHA and runner-start's V095_SHA: v0.9.5 on a host) as a
    substitute of its own: the pinned substitute (the `runner` of ~/build/dl's tarball, Pool's) with WAYBACK_MARK added,
    the same program with other bytes. 03's WAYBACK_BIN_SHA line (when 03 has one; test_one_door's Pins requires it
    once) and runner-start's V095_SHA line, in ~/build and in the installed ~/bin/runner-start, name its sha256, and
    pool-image.sh's PINS follow (Pool.rewrite_pins). INSTALL: it is ~/bin/runner (0755), the runscaler the host runs
    (and the one the running process runs, when one runs: Pool.ran). Returns its sha256."""
    with tarfile.open(os.path.join(p.build, 'dl', 'runner-linux-amd64.tar.gz')) as t:
        wb = t.extractfile('runner').read() + WAYBACK_MARK
    s = hashlib.sha256(wb).hexdigest()
    with open(os.path.join(p.build, 'setup', '03-runscaler.sh')) as f:
        n = len(re.findall(r'^WAYBACK_BIN_SHA=[0-9a-f]{64}$', f.read(), re.M))
    test.assertLessEqual(n, 1, "03 names WAYBACK_BIN_SHA %d times" % n)
    if n:
        p.pin('setup/03-runscaler.sh', 'WAYBACK_BIN_SHA', s)
    p.pin('bin/runner-start', 'V095_SHA', s)
    rs = os.path.join(p.HOME, 'bin', 'runner-start')
    if os.path.exists(rs):
        t = p.read(rs)
        pins = re.findall(r'^V095_SHA=[0-9a-f]{64}$', t, re.M)
        test.assertEqual(len(pins), 1)
        p.write(rs, t.replace(pins[0] + '\n', 'V095_SHA=%s\n' % s), 0o755)
    p.rewrite_pins()
    if install:
        rb = os.path.join(p.HOME, 'bin', 'runner')
        with open(rb + '.cell', 'wb') as f:
            f.write(wb)
        os.chmod(rb + '.cell', 0o755)
        os.replace(rb + '.cell', rb)
        if p.unit_now().get('active'):
            p.ran()    # the process that runs is that runscaler (THE RUNNING BINARY: support.Pool.ran)
    return s


class Before:
    """A Pool whose production runs UPOLD on a config.toml of BEFORE THIS RELEASE: 03's render less its two log-file
    lines (the comment and the key, taken from 03's own render), installed in the second 03 installed it, so runscaler
    (started after that second) runs it. The registry serves UPOLD and UPNEW, UPNEW's runner is UPV, and UPV's build
    record names UPNEW. h1: 03's render of this release (UPOLD); pre: the config.toml it runs; comment, key: the two.
    LABEL: the host config's MAIN_LABEL from the start (the pool runs it)."""

    def __init__(self, test, label=None):
        self.t = test
        p = self.p = Pool(test)
        p.docker['versions'] = {ref(UPOLD): UPOLDV + '\n', ref(UPNEW): UPV + '\n'}
        p.curl['served'] = [UPOLD, UPNEW]
        if label:
            self.label(label)
        p.production(UPOLD)
        self.cfg = p.rpath('config.toml')
        self.h1 = p.config()
        found = TWO.findall(self.h1)
        if len(found) != 1:
            raise AssertionError("03's render: %d log-level lines with the two log-file lines after them, want 1" %
                                 len(found))
        both, self.comment, self.key = found[0]
        self.pre = self.h1.replace(LEVEL + both, LEVEL, 1)
        self.put(self.cfg, self.pre)
        p.record(UPV, UPNEW)

    def put(self, path, text):
        """TEXT at PATH (0600), its mtime the whole second of the file it replaces (or of now)."""
        m = int(os.stat(path).st_mtime) if os.path.exists(path) else int(time.time())
        self.p.write(path, text, 0o600)
        os.utime(path, (m, m))

    @staticmethod
    def on(text, d):
        """TEXT with its runner-image lines naming d (UPOLD's lines replaced)."""
        return text.replace(ref(UPOLD), ref(d))

    def after_up(self, kept):
        """The state an up from pre to UPNEW leaves, made by hand so that a cell reads its `back` alone: KEPT (the
        rollback: config.toml.pre-image of a person's up, config.toml.prev of the updater's switch) is pre, config.toml
        03's render of UPNEW (with the line), and runscaler started after its install (in a later second, never in the
        future: the clock waited for, a state)."""
        self.put(self.p.rpath(kept), self.pre)
        r = self.p.s03('real', UPNEW)
        self.t.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.t.assertEqual(self.p.config(), self.on(self.h1, UPNEW))
        m = int(os.stat(self.cfg).st_mtime)
        while int(time.time()) <= m:
            time.sleep(0.05)
        self.p.set_unit(start=int(time.time()), pid=self.p.unit_now()['pid'] + 1)

    def label(self, value):
        """The host config's MAIN_LABEL becomes VALUE (03 renders it from then on)."""
        conf = self.p.read(self.p.path('host.conf'))
        self.t.assertEqual(conf.count('\nMAIN_LABEL=linux-ci\n'), 1)
        self.p.write(self.p.path('host.conf'), conf.replace('\nMAIN_LABEL=linux-ci\n', '\nMAIN_LABEL=%s\n' % value),
                     0o644)

    def way_back(self, install=True):
        """The host runs THE WAY-BACK RUNSCALER (way_back): runner-start's V095_SHA, so a config with no log-file line
        validates and starts on it (LogFile's own control), and a person's `back` to one is accepted (BACK'S PAIR
        GUARD, test_one_door)."""
        return way_back(self.t, self.p, install)

    def unattended(self, *args):
        """pool-image.sh ARGS as the updater's child, on a fake clock (the window's sleeps return at once)."""
        self.p.write(self.p.path('logs', 'runner.log'), '')
        self.p.fake_clock()
        return self.p.unattended(*args)

    def state(self):
        """config.toml as a refusal must leave it: (its sha256, its mtime in ns)."""
        return sha256_file(self.cfg), os.stat(self.cfg).st_mtime_ns

    def restarts(self):
        """systemctl's stop, start and restart calls of runscaler."""
        return [l for l in self.p.lines('systemctl') if l.split(' ')[1:2] in (['stop'], ['start'], ['restart'])]

    def closed(self, cls):
        """The window journal is closed, config.toml of CLASS."""
        lines = self.p.window()
        self.t.assertIsNotNone(lines)
        self.t.assertTrue(lines[-1].startswith('closed '), lines)
        self.t.assertRegex(lines[-2], r'^installed [0-9a-f]{64} [0-9a-f]{64} %s$' % cls)
        return lines


@needs_container
class LogFileUp(unittest.TestCase):
    """THE LOG-FILE LINE GOES IN THROUGH `up` (H1 review r1: Opus F1, Codex F1, Opus F2), and COMMENTS ARE NOT CONTENT
    (runscaler 0.12 bump, slice H2a: the plan's H2-2', H2-6). A host installed before H1 runs a config.toml with no
    log-file line. The next `pool-image.sh up` to another image (a person's, or the updater's switch: `up --unattended`)
    adds the line with every check of its own and its own idle restart, because THE CONFIG COMPARE (runner-release.sh's
    rr_same_but_image A B, ONE copy for every caller; A is the config that runs or was kept, B the newer one) reads each
    config less its whole-line comments and blank lines (PLAN D1's CONTENT) and less its runner-image lines, and also
    accepts B = A plus 03's log-file KEY line once, right after A's first log-level line, only when A has no log-file key
    at all (TOML keys as runner-start reads them: bare or quoted, any case and spacing, at the top level, dotted or in a
    table). A `back` to the config kept before the line is accepted the same way (on the way-back runscaler: BACK'S PAIR
    GUARD, test_one_door). Any other difference still refuses, config.toml as it was (sha and mtime), nothing
    restarted. Each of the five callers (a person's up after 03, the pending-restart up, a person's back, the switch's
    D3 and back --unattended) accepts a difference in comments alone."""

    def test_a_person_s_up_on_a_config_from_before_the_line_adds_it_and_restarts_at_idle(self):
        """The rollback it keeps is the config with no line; config.toml is this release's render of the new image;
        restart() restarts once, after the idle pair of `counts quiet` (two /healthz reads)."""
        g = Before(self)
        g.p.write(g.p.path('logs', 'events.log'), '')
        r = g.p.pool('up', UPV)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('POOL IMAGE DONE (up): %s' % ref(UPNEW), r.stdout)
        self.assertEqual(g.p.config(), g.on(g.h1, UPNEW))
        self.assertEqual(g.p.config('config.toml.pre-image'), g.pre)
        self.assertEqual(g.p.unit_now()['restarts'], 1)
        ev = g.p.events()
        stop = [i for i, e in enumerate(ev) if re.fullmatch(r'process [0-9]+ stopped', e)]
        self.assertTrue(stop, ev)
        self.assertGreaterEqual(ev[:stop[0]].count('healthz read'), 2, ev)

    def test_up_unattended_on_a_config_from_before_the_line_adds_it(self):
        """The updater's switch: D3 accepts the render, the window switches at idle (`idle idle`) and restarts by its own
        steps (`running`); config.toml.prev, the rollback, is the config with no line."""
        g = Before(self)
        r = g.unattended('up', '--unattended', UPV, UPNEW)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), g.on(g.h1, UPNEW))
        self.assertEqual(g.p.config('config.toml.prev'), g.pre)
        lines = g.closed('target-running')
        self.assertIn('idle idle', lines)
        self.assertEqual([l.split(' ')[1] for l in g.restarts()], ['stop', 'start'])

    def test_a_person_s_back_to_the_config_kept_before_the_line_is_accepted(self):
        """After that up, on the way-back runscaler (v0.9.5, the one that runs a config with no line: BACK'S PAIR GUARD
        refuses it on any other, test_one_door): `back` puts the kept config (no line) back as config.toml and restarts
        once."""
        g = Before(self)
        g.after_up('config.toml.pre-image')
        g.way_back()
        r = g.p.pool('back')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('POOL IMAGE DONE (back): %s' % ref(UPOLD), r.stdout)
        self.assertEqual(g.p.config(), g.pre)
        self.assertEqual(g.p.unit_now()['restarts'], 1)
        starts(self, g.p)    # the pair it claims: the way-back runscaler and the config with no line

    def test_back_unattended_to_the_config_kept_before_the_line_is_accepted(self):
        """After the updater's switch: its rollback validates the copy of config.toml.prev (no line: runner-start starts
        it on the way-back runscaler v0.9.5 only, its V095_SHA) and puts it back, running."""
        g = Before(self)
        g.after_up('config.toml.prev')
        g.way_back()
        r = g.unattended('back', '--unattended', '--why', 'back')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), g.pre)
        g.closed('target-running')

    def test_a_label_holding_the_text_log_file_on_a_config_from_before_the_line_passes(self):
        """H2-2' (the plan's F6; H1 review r2, Codex F1 / Opus F2): "A has no log-file key" is a TOML key test, never a
        text match, so a host value that holds the text `log-file` (MAIN_LABEL, a label the pool runs) is no key: a
        person's up from a config before the line adds it, as for any other label. b2eb739's test read every line for
        the text and refused."""
        g = Before(self, label='log-file')
        self.assertIn('labels = ["self-hosted", "log-file"]\n', g.pre)
        r = g.p.pool('up', UPV)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('POOL IMAGE DONE (up): %s' % ref(UPNEW), r.stdout)
        self.assertEqual(g.p.config(), g.on(g.h1, UPNEW))
        self.assertEqual(g.p.unit_now()['restarts'], 1)

    def test_a_person_s_up_from_a_config_whose_comments_differ_passes(self):
        """H2-2 (a person's up after its 03, and 03's own compare: test_one_door's NoExposure): the config the pool runs
        has a comment line no render of this release has (OLDC), or the header of the release before this one (03's
        header names the runscaler release): comments are not content, so the up goes on, keeps that config as the
        rollback and restarts once. OLDC is red on b2eb739 (its compare read comments); the header subtest is the case
        a host meets, which b2eb739 cannot tell apart (its render has that header)."""
        for why, a in (('a comment line of its own', lambda g: older(g.pre)),
                       ('the header of the release before', lambda g: H1HEAD + g.pre.split('\n', 1)[1])):
            with self.subTest(why):
                g = Before(self)
                kept = a(g)
                g.put(g.cfg, kept)
                r = g.p.pool('up', UPV)
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertIn('POOL IMAGE DONE (up): %s' % ref(UPNEW), r.stdout)
                self.assertEqual(g.p.config(), g.on(g.h1, UPNEW))
                self.assertEqual(g.p.config('config.toml.pre-image'), kept)
                self.assertEqual(g.p.unit_now()['restarts'], 1)

    def test_up_unattended_from_a_config_whose_comments_differ_passes(self):
        """H2-2 at D3 (the switch's compare, A config.toml, B STAGED): the config the pool runs has OLDC; the switch
        goes on, config.toml.prev is that config."""
        g = Before(self)
        g.put(g.cfg, older(g.pre))
        r = g.unattended('up', '--unattended', UPV, UPNEW)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), g.on(g.h1, UPNEW))
        self.assertEqual(g.p.config('config.toml.prev'), older(g.pre))
        g.closed('target-running')

    def test_back_unattended_to_a_rollback_whose_comments_differ_passes(self):
        """H2-2 at back --unattended (A the copy of config.toml.prev, B config.toml): the rollback has OLDC (and the line,
        so it validates on any runscaler); it goes back, running."""
        g = Before(self)
        g.after_up('config.toml.prev')
        g.put(g.p.rpath('config.toml.prev'), older(g.h1))
        r = g.unattended('back', '--unattended', '--why', 'back')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), older(g.h1))
        g.closed('target-running')

    def test_the_pending_restart_up_reads_the_kept_config_as_the_older_one(self):
        """H2-6 (the 5th caller, pool-image.sh's pending-restart up: config.toml already names the record's image, and
        runscaler has not started since it was installed): A is the kept config (no line), B config.toml (a bare `03
        real` of the new image, with the line): the compare accepts it and restarts once; with A's arguments swapped
        it would read B as the older one and refuse (the mutant). A with comments of its own (OLDC) too (red on
        b2eb739). The control: a label changed under that 03 refuses, nothing restarted."""
        for why, kept, label, ok in (('the kept config has no line', lambda g: g.pre, None, True),
                                     ('and comments of its own', lambda g: older(g.pre), None, True),
                                     ('control: a changed label', lambda g: g.pre, 'linux-ci-x', False)):
            with self.subTest(why):
                g = Before(self)
                g.put(g.p.rpath('config.toml.pre-image'), kept(g))
                if label:
                    g.label(label)
                r = g.p.s03('real', UPNEW)
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertGreaterEqual(int(os.stat(g.cfg).st_mtime), g.p.unit_now()['start'],
                                        'a restart is pending: runscaler started before this config.toml')
                before = g.state()
                r = g.p.pool('up', UPV)
                self.assertIn('config.toml already runs the build record\'s image', r.stdout)
                if ok:
                    self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                    self.assertIn('POOL IMAGE DONE (up): %s' % ref(UPNEW), r.stdout)
                    self.assertEqual(g.p.unit_now()['restarts'], 1)
                    continue
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertIn('config.toml differs from the rollback in more than the image: nothing restarted', r.stdout)
                self.assertEqual(g.state(), before)
                self.assertEqual(g.restarts(), [])

    def test_up_s_own_compare_after_03_puts_the_rollback_back(self):
        """A person's up keeps its own compare after 03 (the plan's H2-7: 03's compare comes first, this one stays): a
        config.toml that changes between 03's install and that compare (a person's hand install of another
        max-runners at 03's last rename: the hook) refuses, and the rollback goes back with config.toml's old mtime,
        nothing restarted."""
        g = Before(self)
        before = g.state()
        g.p.hooks(('mv-done:config.toml', 'hand-file'))
        r = g.p.pool('up', UPV)
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertIn('hand install hand-file', g.p.events())
        self.assertIn("03's config differed from the rollback in more than the image", r.stdout)
        self.assertEqual(g.state(), before)
        self.assertEqual(g.p.config(), g.pre)
        self.assertEqual(g.restarts(), [])

    def test_control_the_line_and_another_change_refuse(self):
        """The control of the accept cells: the line AND one other change. A person's up whose host config's MAIN_LABEL
        is not the one the pool runs (the hand-copy move's promise: that `up` stops with config.toml as it was, and
        nothing restarts; from H2a its 03 refuses it before it installs: test_one_door's NoExposure), and the updater's
        switch whose pool.env holds another number (D3)."""
        for why in ('up, MAIN_LABEL changed', 'up --unattended, a pool.env number changed'):
            with self.subTest(why):
                g = Before(self)
                if why.startswith('up,'):
                    g.label('linux-ci-x')
                    before = g.state()
                    r = g.p.pool('up', UPV)
                    says = ('FAIL the render differs from config.toml in more than the runner-image lines',
                            '03 real failed: config.toml was not changed')
                else:
                    g.p.pool_env(CONCURRENT=3, MAX=2)
                    before = g.state()
                    r = g.unattended('up', '--unattended', UPV, UPNEW)
                    says = ('STOP check failed: 03\'s render differs from config.toml in more than the runner-image '
                            'lines',)
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                for s in says:
                    self.assertIn(s, r.stdout)
                self.assertEqual(g.state(), before)
                self.assertEqual(g.restarts(), [])
                if 'unattended' in why:
                    g.closed('pre')
                    self.assertFalse(os.path.lexists(g.p.rpath('config.toml.prev')), 'no rollback was kept')

    def test_the_key_line_alone_or_a_difference_in_comments_is_accepted(self):
        """H2-2': a person's `back` from config.toml B (the image UPNEW) to the kept config A, on the way-back
        runscaler, is accepted when B is A plus the KEY line alone right after log-level (no comment line above it),
        B is A plus a comment alone, or A has comments of its own (OLDC). Two of these were H1's controls ('the key line
        alone', 'the comment alone' of test_control_any_other_log_file_difference_refuses), which refused: they flip
        here."""
        for why, kept, newer in (
                ('the key line alone', lambda g: g.pre, lambda g, new: after_level(new, g.key)),
                ('the comment alone', lambda g: g.pre, lambda g, new: after_level(new, g.comment)),
                ('the kept config has comments of its own', lambda g: older(g.pre),
                 lambda g, new: after_level(g.on(g.pre, UPNEW), g.comment + g.key))):
            with self.subTest(why):
                g = Before(self)
                g.way_back()
                a = kept(g)
                g.put(g.p.rpath('config.toml.pre-image'), a)
                g.put(g.cfg, newer(g, g.on(a, UPNEW)))
                r = g.p.pool('back')
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertIn('POOL IMAGE DONE (back): %s' % ref(UPOLD), r.stdout)
                self.assertEqual(g.p.config(), a)
                self.assertEqual(g.p.unit_now()['restarts'], 1)
                starts(self, g.p)    # the pair it claims (the way-back runscaler, the kept config)

    def test_control_any_other_log_file_difference_refuses(self):
        """The controls of the KEY line once, in the render's place, A with no log-file key (and of comments are not
        content: a value is): a person's `back` from config.toml B (the image UPNEW) to the kept config A, on the
        way-back runscaler (so the compare decides, not BACK'S PAIR GUARD), refuses, config.toml as it was, nothing
        restarted, when B is A plus anything else than that key line once right after log-level (another value, the
        line twice, in another place, with an inline comment, with a value changed too, or a value changed alone), or
        when A has a log-file key itself: the render's, or one spelled otherwise (quoted, upper case, spaced), dotted, or
        in a table (never read as "no key")."""
        other = 'log-file = "/home/root/.local/state/runner/runner.log"\n'

        def elsewhere(text, add):
            if text.count('\n\n[docker]\n') != 1:
                raise AssertionError('no single [docker] table after a blank line')
            return text.replace('\n\n[docker]\n', '\n' + add + '\n[docker]\n', 1)

        def after(text, line, add):
            if text.count('\n' + line) != 1:
                raise AssertionError('no single line %r' % line)
            return text.replace('\n' + line, '\n' + line + add, 1)

        def logf(g):
            return re.fullmatch(r'log-file = "(.*)"\n', g.key).group(1)

        def spelled(fmt):
            return lambda g: after_level(g.pre, fmt % logf(g))

        def with_key(g, new):
            return after_level(new, g.comment + g.key)
        for why, kept, newer in (
                ('another log-file value', lambda g: g.pre, lambda g, new: after_level(new, g.comment + other)),
                ('the two lines twice', lambda g: g.pre, lambda g, new: after_level(new, (g.comment + g.key) * 2)),
                ('the key line twice', lambda g: g.pre, lambda g, new: after_level(new, g.key * 2)),
                ('the two lines in another place', lambda g: g.pre, lambda g, new: elsewhere(new, g.comment + g.key)),
                ('the key line after another key', lambda g: g.pre,
                 lambda g, new: after(new, 'concurrent = 4\n', g.key)),
                ('the key line with an inline comment', lambda g: g.pre,
                 lambda g, new: after_level(new, g.key[:-1] + '   # the runner.log the readers read\n')),
                ('the key line and a value changed', lambda g: g.pre,
                 lambda g, new: with_key(g, new).replace('max-runners = 3\n', 'max-runners = 2\n', 1)),
                ('a value changed alone', lambda g: g.pre,
                 lambda g, new: new.replace('max-runners = 3\n', 'max-runners = 2\n', 1)),
                ('A has the line, B has it twice', lambda g: g.h1, lambda g, new: with_key(g, new)),
                ('A has the line, B has not', lambda g: g.h1, lambda g, new: g.on(g.pre, UPNEW)),
                ('A has the key quoted', spelled('"log-file" = "%s"\n'), with_key),
                ('A has the key in upper case', spelled('LOG-FILE = "%s"\n'), with_key),
                ('A has the key spaced, its value a literal string', spelled("  log-file   =   '%s'\n"), with_key),
                ('A has a dotted log-file key', spelled('log-file.path = "%s"\n'), with_key),
                ('A has a log-file key in a table', lambda g: after(g.pre, '[docker]\n', 'log-file = "%s"\n' % logf(g)),
                 with_key)):
            with self.subTest(why):
                g = Before(self)
                g.way_back()
                a = kept(g)
                b = newer(g, g.on(a, UPNEW))
                self.assertNotEqual(b, g.on(a, UPNEW))
                g.put(g.p.rpath('config.toml.pre-image'), a)
                g.put(g.cfg, b)
                before = g.state()
                r = g.p.pool('back')
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertIn('config.toml differs from the rollback in more than the image', r.stdout)
                self.assertEqual(g.state(), before)
                self.assertEqual(g.restarts(), [])


if __name__ == '__main__':
    unittest.main()
