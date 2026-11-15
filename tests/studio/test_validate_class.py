"""bin/validate-class RC OUTPUT_FILE: the ONE VALIDATE RULE (PLAN, PRE-VALIDATE). One validate's result is PASS,
API-ONLY, NON-API or UNKNOWN, from runscaler's real output (cmd/runner/cmd_validate.go, the same four prints at v0.9.5
and v0.12.0: each `  ✗ ` print is followed by a return; the scaleset client logs INFO and ERRO records on the same
stdout, from 0.10.0 INFO and ERROR in a 5-wide column; cobra adds `Error:` and the usage). From v0.22.0 validate prints
every local config problem before it returns, and the first `  ✗ ` line still decides (TestV022Source).

The *-v022-src* fixtures are NOT real outputs: they are built by hand from runscaler v0.22.0's print statements, and
each file's `# ` header cites the source lines (file:line at the v0.22.0 tag); src_fixture strips that header. R2 adds
the real v0.22.0 outputs as *-v022* beside them.

The fixtures in fixtures/validate/ are real outputs of runscaler (darwin-arm64), made by the LIVE cell below with no
network. From the pinned v0.12.0: api-only-real-v012.txt (the GitHub API part fails: the proxy refuses) and
non-api-real-v012.txt (the same config with `runner-image = ""`), on config/config.toml.example with neutral names and
its log-file pin on the sandbox's runner.log. From v0.9.5, the pin before: api-only-real.txt and non-api-real.txt, the
same two runs (kept for a way back; they predate the log-file line). The cleaning step replaces only the refusing
proxy's port. The live cell runs when RUNSCALER_TARBALL names the pinned release tarball (runner-darwin-arm64.tar.gz;
its sha256 must be setup/downloads.manifest's), else it skips and says so. With RUNSCALER_FIXTURE_OUT=DIR it also
writes its two cleaned outputs into DIR, under the -v012 names, to re-make those fixtures.
"""
import hashlib
import os
import re
import socket
import subprocess
import tarfile
import unittest

from tests.studio.support import REPO, Sandbox

SCRIPT = 'bin/validate-class'
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'validate')
X = '  \u2717 '          # the start of runscaler's failed-check line ("  ✗ ")
OK = '  \u2713 '         # a passed check ("  ✓ ")
API = X + 'scaleset[0] "mac-ci-example" GitHub API: failed to create new actions service request: context deadline exceeded'
HINT = '    Check that your token has the correct scopes (admin:org or repo)'
COBRA = 'Error: validation failed\nUsage:\n  runner validate [flags]\n'
INFO = '2026-11-02 12:03:17 INFO refreshing token githubConfigUrl=https://github.com/example-org/example'
CONFIG_CHECKS = (X + 'config: unknown key "runner-imag" in [[scaleset]]',
                 X + 'global config: health-port must be between 0 and 65535',
                 X + 'scaleset[0] "mac-ci-example": runner-image is required',
                 X + 'scale set collection: duplicate scale set name "mac-ci-example"')


def fixture(name):
    with open(os.path.join(FIX, name), encoding='utf-8') as f:
        return f.read()


class Rig:
    def __init__(self, test):
        self.test = test
        self.sb = Sandbox(test)
        self.script = self.sb.copy_script(SCRIPT, [])

    def classify(self, rc, text):
        p = self.sb.write(self.sb.path('out', 'validate.txt'), text)
        return self.run(str(rc), p)

    def run(self, *args):
        return self.sb.run(['/bin/zsh', '-f', self.script] + list(args))

    def cls(self, rc, text):
        r = self.classify(rc, text)
        self.test.assertEqual((r.returncode, r.stderr), (0, ''), r.stdout)
        self.test.assertRegex(r.stdout, r'^(PASS|API-ONLY|NON-API|UNKNOWN)\n$')
        return r.stdout.strip()


class TestClasses(unittest.TestCase):
    def setUp(self):
        self.r = Rig(self)

    def test_pass(self):
        out = OK + 'scaleset[0] "mac-ci-example" \u2014 provider=tart\n' + OK + 'Tart binary found\n' + INFO + '\n' + \
            OK + 'scaleset[0] "mac-ci-example" GitHub API is reachable\n\nAll checks passed.\n'
        self.assertEqual(self.r.cls(0, out), 'PASS')

    def test_real_api_failure_is_api_only(self):
        self.assertEqual(self.r.cls(1, fixture('api-only-real.txt')), 'API-ONLY')

    def test_real_config_failure_is_non_api(self):
        self.assertEqual(self.r.cls(1, fixture('non-api-real.txt')), 'NON-API')

    def test_real_v012_api_failure_is_api_only(self):
        # the pinned runscaler 0.12.0: its log records in the 5-wide level column (INFO, ERROR) are ignored as well
        self.assertEqual(self.r.cls(1, fixture('api-only-real-v012.txt')), 'API-ONLY')

    def test_real_v012_config_failure_is_non_api(self):
        self.assertEqual(self.r.cls(1, fixture('non-api-real-v012.txt')), 'NON-API')

    def test_each_config_check_is_non_api(self):
        for line in CONFIG_CHECKS:
            with self.subTest(line):
                self.assertEqual(self.r.cls(1, line + '\n' + COBRA), 'NON-API')

    def test_control_each_config_check_line_shape_is_needed(self):
        # the same texts without runscaler's two-space indent are no ✗ line: UNKNOWN
        for line in CONFIG_CHECKS:
            with self.subTest(line):
                self.assertEqual(self.r.cls(1, line[2:] + '\n' + COBRA), 'UNKNOWN')

    def test_refuse_line_is_non_api(self):
        self.assertEqual(self.r.cls(1, 'runner-start: REFUSE configured runner-image is not on this host: img-x\n'),
                         'NON-API')

    def test_refuse_line_after_an_api_failure_is_non_api(self):
        out = fixture('api-only-real.txt') + 'runner-start: REFUSE token file is not 0600: /x/token-a\n'
        self.assertEqual(self.r.cls(1, out), 'NON-API')

    def test_control_refuse_text_not_at_the_line_start_is_ignored(self):
        out = fixture('api-only-real.txt') + 'note: runner-start: REFUSE token file is not 0600\n'
        self.assertEqual(self.r.cls(1, out), 'API-ONLY')

    def test_a_record_that_holds_check_text_is_ignored(self):
        # a log record that quotes a config check is not a ✗ line: the first ✗ line is still the API one
        rec = '2026-11-02 12:03:17 ERRO request failed error="%sglobal config: x"' % X
        out = INFO + '\n' + rec + '\n' + fixture('api-only-real.txt')
        self.assertEqual(self.r.cls(1, out), 'API-ONLY')

    def test_control_the_same_text_as_a_check_line_is_non_api(self):
        out = INFO + '\n' + X + 'global config: x\n' + fixture('api-only-real.txt')
        self.assertEqual(self.r.cls(1, out), 'NON-API')

    def test_first_check_line_rules_config_then_api(self):
        out = CONFIG_CHECKS[2] + '\n' + API + '\n' + HINT + '\n' + COBRA
        self.assertEqual(self.r.cls(1, out), 'NON-API')

    def test_first_check_line_rules_api_then_config(self):
        out = API + '\n' + HINT + '\n' + CONFIG_CHECKS[2] + '\n' + COBRA
        self.assertEqual(self.r.cls(1, out), 'API-ONLY')

    def test_api_line_with_a_quoted_name(self):
        out = X + 'scaleset[12] "a \\"b\\" \\\\ c" GitHub API: 401 Unauthorized\n' + HINT + '\n' + COBRA
        self.assertEqual(self.r.cls(1, out), 'API-ONLY')

    def test_a_name_that_holds_the_api_text_is_a_config_check(self):
        out = X + 'scaleset[0] "x\\" GitHub API: y": runner-image is required\n' + COBRA
        self.assertEqual(self.r.cls(1, out), 'NON-API')

    def test_rc_0_without_the_pass_line_is_unknown(self):
        for out in ('', OK + 'Tart binary found\n', 'All checks passed. \n', 'All checks passed\n'):
            with self.subTest(out=out):
                self.assertEqual(self.r.cls(0, out), 'UNKNOWN')

    def test_rc_0_with_a_failure_line_is_unknown(self):
        for extra in (API, CONFIG_CHECKS[0], 'runner-start: REFUSE x'):
            with self.subTest(extra):
                self.assertEqual(self.r.cls(0, extra + '\n\nAll checks passed.\n'), 'UNKNOWN')

    def test_pass_line_with_rc_not_0_is_not_pass(self):
        self.assertEqual(self.r.cls(1, '\nAll checks passed.\n'), 'UNKNOWN')
        self.assertEqual(self.r.cls(1, API + '\n\nAll checks passed.\n'), 'API-ONLY')

    def test_empty_output_is_unknown(self):
        for rc in (0, 1, 2):
            with self.subTest(rc=rc):
                self.assertEqual(self.r.cls(rc, ''), 'UNKNOWN')

    def test_no_check_line_is_unknown(self):
        # a config file that does not parse: cobra's error only
        out = 'Error: failed to read config file: While parsing config: toml: expected newline\n' + COBRA
        self.assertEqual(self.r.cls(1, out), 'UNKNOWN')

    def test_another_check_is_unknown(self):
        for line in (X + 'Tart binary not found in PATH', X + 'Docker connectivity at /var/run/docker.sock: refused',
                     X + 'Docker client for /var/run/docker.sock: bad'):
            with self.subTest(line):
                self.assertEqual(self.r.cls(1, line + '\n' + COBRA), 'UNKNOWN')


def src_fixture(name):
    """A v0.22.0 SOURCE fixture (fixtures/validate/*-v022-src*): built by hand from runscaler v0.22.0's print
    statements, not a real output. Its header lines (each starts with "# ") cite the source lines and are stripped."""
    lines = fixture(name).splitlines(keepends=True)
    n = next(i for i, l in enumerate(lines) if not l.startswith('# '))
    head = ''.join(lines[:n])
    if 'v0.22.0 SOURCE fixture, NOT a real output' not in head or 'file:line at v0.22.0' not in head:
        raise AssertionError('%s: no v0.22.0 source header' % name)
    return ''.join(lines[n:])


class TestV022Source(unittest.TestCase):
    """The v0.22.0 forms (PLAN D4, census B6), from the v0.22.0 source (each fixture's header cites its lines).
    v0.22.0 prints EVERY local config problem (cmd/runner/cmd_validate.go:152-177) and every macOS limit problem
    (tart_guests.go:123-126) before it returns; the first `  ✗ ` line still decides. Its validate also runs, after the
    GitHub API check, the Tart image check, the guest detection and the macOS limits (cmd_validate.go:118-141)."""

    def setUp(self):
        self.r = Rig(self)

    def test_pass_with_the_guest_lines(self):
        # `level=INFO msg="Detected Tart guest"` (tart_guests.go:33) and `  ✓ … Tart guest: macos|linux` (:118)
        self.assertEqual(self.r.cls(0, src_fixture('pass-v022-src.txt')), 'PASS')

    def test_a_set_detected_only_at_startup_is_not_pass(self):
        # tart_guests.go:120: the image is not local, so validate did not detect its guest; rc 0 all the same
        self.assertEqual(self.r.cls(0, src_fixture('pass-not-pulled-v022-src.txt')), 'UNKNOWN')

    def test_control_the_not_pulled_line_with_rc_not_0_keeps_the_first_failure_line(self):
        out = src_fixture('pass-not-pulled-v022-src.txt').replace('\nAll checks passed.\n', '') + API + '\n'
        self.assertEqual(self.r.cls(1, out), 'API-ONLY')

    def test_each_new_config_line_is_non_api(self):
        # red before R1: main.go:834, main.go:844, tart_guests.go:67, tart_guests.go:70
        for name in ('non-api-v022-src-capacity.txt', 'non-api-v022-src-duplicate.txt',
                     'non-api-v022-src-combined-min.txt', 'non-api-v022-src-combined-pool.txt'):
            with self.subTest(name):
                self.assertEqual(self.r.cls(1, src_fixture(name)), 'NON-API')

    def test_control_a_macos_set_limit_line_is_non_api(self):
        # tart_guests.go:57, :61: today's `scaleset[N] "NAME": ` pattern matches them already (review r1 F11)
        for name in ('non-api-v022-src-macos-min.txt', 'non-api-v022-src-macos-pool.txt'):
            with self.subTest(name):
                self.assertEqual(self.r.cls(1, src_fixture(name)), 'NON-API')

    def test_control_detect_guest_and_the_image_check_are_unknown(self):
        # a host fact (a missing image, a failed clone), not a config fact: tart_guests.go:30,110 and :102
        self.assertEqual(self.r.cls(1, src_fixture('unknown-v022-src-detect.txt')), 'UNKNOWN')
        line = X + 'scaleset[0] "mac-ci-example" Tart image check: exit status 1\nvalidation failed\n'
        self.assertEqual(self.r.cls(1, line), 'UNKNOWN')

    def test_control_the_new_line_texts_need_their_place(self):
        # a duplicates text that is not the name check, and a capacity text inside another check: UNKNOWN
        for line in (X + 'scaleset[1] "a" duplicates scaleset[x] name; y', X + 'Tart: invalid global capacity: x',
                     X + 'other combined min-runners of macOS guest scale sets is 4'):
            with self.subTest(line):
                self.assertEqual(self.r.cls(1, line + '\nvalidation failed\n'), 'UNKNOWN')

    def test_control_a_fixture_without_its_header_is_refused(self):
        with self.assertRaises(AssertionError):
            src_fixture('non-api-real-v012.txt')


class TestUsage(unittest.TestCase):
    def test_usage_errors(self):
        r = Rig(self)
        f = r.sb.write(r.sb.path('out', 'v.txt'), 'All checks passed.\n')
        for args in ([], ['0'], ['0', f, 'x'], ['x', f], ['-1', f], ['256', f], ['01', f], ['', f],
                     ['0', f + '.none'], ['0', os.path.dirname(f)]):
            with self.subTest(args=args):
                res = r.run(*args)
                self.assertEqual((res.returncode, res.stdout), (2, ''))
                self.assertTrue(res.stderr.startswith('validate-class: usage: validate-class RC OUTPUT_FILE'),
                                res.stderr)

    def test_control_valid_arguments(self):
        r = Rig(self)
        f = r.sb.write(r.sb.path('out', 'v.txt'), 'All checks passed.\n')
        for rc, want in (('0', 'PASS\n'), ('255', 'UNKNOWN\n')):
            res = r.run(rc, f)
            self.assertEqual((res.returncode, res.stdout, res.stderr), (0, want, ''))


# ---- the live cell: the real pinned binary, no network

def manifest_sha():
    with open(os.path.join(REPO, 'setup', 'downloads.manifest')) as f:
        for line in f:
            w = line.split()
            if len(w) == 5 and w[0] == 'file' and w[1].endswith('/runner-darwin-arm64.tar.gz'):
                return w[2]
    raise AssertionError('setup/downloads.manifest has no runscaler row')


def refusing_port():
    """A local port that refuses: bound, then closed; the cell checks it refuses before it uses it."""
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def clean(text, port):
    """The cleaning step: only the refusing proxy's port changes (to 9). The config the binary ran on has neutral
    names only; the cell asserts that no other host value is in the output."""
    return text.replace('127.0.0.1:%d' % port, '127.0.0.1:9')


class TestLiveBinary(unittest.TestCase):
    """The real pinned runscaler runs `validate` through a runner-start copy (its token files, its tart check, its
    exec), with HTTPS_PROXY and HTTP_PROXY at a refusing local port and NO_PROXY empty: nothing leaves the Mac."""

    def binary(self, sb):
        tarball = os.environ.get('RUNSCALER_TARBALL', '')
        if not tarball or not os.path.isfile(tarball):
            self.skipTest('RUNSCALER_TARBALL is not set to the pinned runscaler darwin-arm64 tarball: the live '
                          'validate cell did not run (the fixtures stay as committed)')
        with open(tarball, 'rb') as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), manifest_sha(),
                             'RUNSCALER_TARBALL is not the pinned runscaler (setup/downloads.manifest)')
        d = sb.mkdir('rs')
        with tarfile.open(tarball) as t:
            m = t.getmember('runner')
            self.assertTrue(m.isfile())
            with t.extractfile(m) as src, open(os.path.join(d, 'runner'), 'wb') as dst:
                dst.write(src.read())
        os.chmod(os.path.join(d, 'runner'), 0o755)
        return os.path.join(d, 'runner')

    def run_validate(self, image_line, keep):
        sb = Sandbox(self)
        runner = self.binary(sb)
        cfgdir = sb.mkdir('config')
        shimdir = sb.mkdir('shimdir')
        sb.stub('tart', '[[ $* == "list --source local -q" ]] && print -rl -- liveapp-mac-golden-20261001',
                folder=shimdir)
        with open(os.path.join(REPO, 'config', 'config.toml.example')) as f:
            text = f.read()
        for old, new in (('https://github.com/OWNER/REPO', 'https://github.com/example-org/example'),
                         ('"mac-ci-REPO"', '"mac-ci-example"'),
                         ('runner-image = "liveapp-mac-golden-YYYYMMDD"', image_line),
                         # the example's log-file pin, on the sandbox's runner.log
                         ('log-file = "/Users/ci/.config/runner/runner.log"',
                          'log-file = "%s"' % os.path.join(cfgdir, 'runner.log'))):
            self.assertIn(old, text)
            text = text.replace(old, new)
        config = sb.write(os.path.join(cfgdir, 'config.toml'), text, 0o600)
        sb.write(os.path.join(cfgdir, 'token-owner'), 'dummy-token-not-a-secret\n', 0o600)
        script = sb.copy_script('bin/runner-start', [
            ('RUNNER=/Users/ci/bin/runner', 'RUNNER=' + runner),
            ('CONFIG=/Users/ci/.config/runner/config.toml', 'CONFIG=' + config),
            ('TOKEN_DIR=/Users/ci/.config/runner', 'TOKEN_DIR=' + cfgdir),
            ('LOGDIR=/Users/ci/Library/Logs/mac-runner', 'LOGDIR=' + sb.mkdir('logdir')),
            ('SHIM=/usr/local/libexec/liveapp-ci/tart', 'SHIM=' + os.path.join(shimdir, 'tart')),
            ('STAMP=/Users/ci/.config/runner/wall-stamp', 'STAMP=' + os.path.join(cfgdir, 'wall-stamp')),
            ('export PATH=/usr/local/libexec/liveapp-ci:/Users/ci/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
             'export PATH=%s:/usr/bin:/bin:/usr/sbin:/sbin' % shimdir),
        ], allow=['Run /Users/ci/bin/runner-disable, then /Users/ci/bin/wall-check, then /Users/ci/bin/runner-enable'])
        port = refusing_port()
        with self.assertRaises(ConnectionRefusedError):   # the control on the proxy: it refuses
            socket.create_connection(('127.0.0.1', port), timeout=2).close()
        proxy = 'http://127.0.0.1:%d' % port
        out = sb.path('out.txt')
        with open(out, 'w') as f:
            p = subprocess.run(['/bin/zsh', '-f', script, 'validate', config], stdin=subprocess.DEVNULL, stdout=f,
                               stderr=subprocess.STDOUT, cwd=sb.tmp, timeout=120,
                               env=sb.env({'HTTPS_PROXY': proxy, 'HTTP_PROXY': proxy, 'NO_PROXY': '',
                                           'https_proxy': proxy, 'http_proxy': proxy, 'no_proxy': ''}))
        with open(out, encoding='utf-8') as f:
            text = clean(f.read(), port)
        self.assertNotIn(sb.root, text)
        self.assertNotIn('dummy-token', text)
        self.assertIsNone(re.search(r'/Users/(?!admin/)', text), text)
        d = os.environ.get('RUNSCALER_FIXTURE_OUT')
        if d:   # to re-make the fixtures: the cleaned output, before it is classified
            with open(os.path.join(d, keep), 'w', encoding='utf-8') as f:
                f.write(text)
        cleaned = sb.write(sb.path('cleaned.txt'), text)
        res = sb.run(['/bin/zsh', '-f', sb.copy_script(SCRIPT, []), str(p.returncode), cleaned])
        self.assertEqual((res.returncode, res.stderr), (0, ''))
        return p.returncode, text, res.stdout.strip()

    def test_real_binary_api_failure_is_api_only(self):
        rc, text, cls = self.run_validate('runner-image = "liveapp-mac-golden-20261001"', 'api-only-real-v012.txt')
        self.assertNotEqual(rc, 0, text)
        self.assertIn('proxyconnect tcp: dial tcp 127.0.0.1:9: connect: connection refused', text)
        self.assertEqual(cls, 'API-ONLY', text)

    def test_control_real_binary_broken_image_line_is_non_api(self):
        rc, text, cls = self.run_validate('runner-image = ""', 'non-api-real-v012.txt')
        self.assertNotEqual(rc, 0, text)
        self.assertEqual(cls, 'NON-API', text)


if __name__ == '__main__':
    unittest.main()
