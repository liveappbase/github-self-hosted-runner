"""03-runscaler.sh: the image it renders, `render DIGEST STAGED`, the rejected digests, and the unit's clock (plan D2,
D5; the changed-lines list, items 30-33 and 41).

- `real [DIGEST]`: with a DIGEST, that digest of the local registry; with none, the image the installed
  config.toml runs NOW (pool-image.sh's image_of, the same function), and ~/run/image.ref of RUN_USER only when there is
  no config.toml (a fresh host). So a person's `03 real` after a change of pool.env's numbers keeps the running image.
  The one-off modes `probe` and `c1` are cut (the changed-lines list, item 34): `real` and `render` are the modes, and the
  host config's five keys only they read are gone with them.
- `render DIGEST STAGED` (the updater's switch): renders the real sets with that digest into STAGED (a .toml file of
  ~/.config/runner) and validates it; it installs nothing (no binary, no unit, no daemon-reload, no config.toml), runs none
  of real's refusal controls, and refuses a set list other than config.toml's (an image switch never changes one). It
  refuses when a file 03 installs, as installed, is not the one this release pins: each one's PIN is read from ONE copy,
  pool-image.sh's PINS (~/build/setup/pool-image.sh), and runscaler's binary is BIN_SHA.
- The validate (`runner-start validate`, stdout AND stderr: runner-start's REFUSE lines are on stderr) is classified by
  the ONE VALIDATE RULE (linux-docker/bin/validate-class, installed and pinned as runner-start is). render: PASS exits 0,
  API-ONLY exits 4 with STAGED kept (the window's tries decide), anything else exits 1 with nothing staged. real installs
  only on PASS.
- REJECTED: 03, as RS_USER, refuses a digest listed in ~/.local/state/runner-updater/rejected (the updater lock's folder):
  one `sha256:<64 hex>` per line; no file, or an empty one, lists none; any other content REFUSES, never "none".
- The unit runs runscaler with TZ=UTC (runscaler stamps its log in local time with no zone; the core requires UTC).
The text cells run anywhere; the others run the real scripts (pin lines rewritten) in a container (support.Pool).
"""
import os
import re
import unittest

from tests.hetzner.support import REPO, PASS_OUT, Pool, digest, needs_container, ref, sha256_file

S03 = os.path.join(REPO, 'linux-docker', 'setup', '03-runscaler.sh')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
RR = os.path.join(REPO, 'linux-docker', 'setup', 'runner-release.sh')
UNIT = os.path.join(REPO, 'linux-docker', 'config', 'runscaler.service')
FIX = os.path.join(REPO, 'tests', 'studio', 'fixtures', 'validate')
V0, V2, X = digest(10), digest(12), digest(20)
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
                     ('probe', X), ('upgrade',), ('probe',), ('c1',)):
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


if __name__ == '__main__':
    unittest.main()
