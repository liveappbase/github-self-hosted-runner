"""The release half of the runner-image updater on the Studio (S3b-2b): bin/runner-updater-release (which release a
family may switch to: the TLS filter, the release checks, the recipe, REJECTED, the STOPs DUE reads, the pass hook and
its no-action proof on a DUE pass), bin/tls-excluded-lib (the ONE Mac reader of setup/tls-excluded-spki, which
golden-emudhra and the filter source), and the warm-pool read of bin/runner-updater-lib (a pool-size KEY only).

The pass cells run bin/runner-updater in test_runner_updater's Rig (every path constant rewritten into a sandbox). The
function cells source a copy of the file under test in a small zsh driver. GitHub is a curl stub (no network): it logs
each call (its argv and the OPENSSL_X509_TEA_DISABLE it saw) and answers from files. The TLS filter runs the real
/usr/bin/openssl on the real /etc/ssl/cert.pem plus test certificates this file makes, and real public roots
(tests/studio/fixtures/tls/). The LIVE cells reach GitHub and a public eMudhra test host: they skip unless
RUNNER_UPDATER_LIVE_TLS=1.
"""
import calendar
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import unittest

from tests.hetzner.support import pems, spki_sha256
from tests.hetzner.test_tls import read_data
from tests.studio.support_emudhra import EXCLUDED_LINE, data_keys, emudhra_copy, guest_text, scenario, write as ewrite
from tests.studio.support import REPO, Sandbox
from tests.studio.test_runner_updater import IMG, P, Rig, config, read_text, the_jq
from tests.studio.test_runner_updater_state import (DENIED, KILL, PASS_RUNS, Paths, actions_seen, cand, fam, on_state,
                                                   only_these_start, state, stop)

ZSH = '/bin/zsh'
DATA = os.path.join(REPO, 'setup', 'tls-excluded-spki')
GOOD = 'c' * 64 + ' the good line'

POOL_UNREAD = ('runner-updater: REFUSE on: %(c)s line %(line)d: a pool-size this does not read (it reads only '
               '`pool-size = N` in the [tart] table), and the family fx runs the Tart set mac-a: the updater\'s rules '
               'for a Tart set (R1, NOT SERVING) assume no warm pool, as config.toml.example sets it; set it in [tart] '
               'alone, to 0: the updater is as it was\n')


class TestWarmPoolKey(unittest.TestCase):
    """The warm-pool read (S3b-2a review r2 P3 (a)) matches a pool-size KEY, never the text "pool-size" anywhere in a
    line: a URL, a label or a trailing comment that holds the text does not make `on` refuse. A key that names
    pool-size still does: a bare, dotted or quoted key, or a key of an inline table (fail closed). The control for the
    text cells: the same config with a real key refuses."""

    def on(self, cfg):
        r = Rig(self, jq_wrap=True, cfg=cfg)
        u = Paths(r)
        raw = u.put(dict(on_state(), on=False))
        return r, u, raw, r.cmd('on', ok=False)

    TEXT = {   # the text "pool-size" where it is no key
        'a URL': ('url = "https://github.com/OWNER/REPO"', 'url = "https://github.com/OWNER/pool-size-tools"'),
        'a trailing comment': ('cpu = 4 ', 'cpu = 4   # not a pool-size '),
        'a label': ('labels = ["mac-ci"]', 'labels = ["mac-ci", "pool-size"]'),
        'an escaped quote before it': ('labels = ["mac-ci"]', 'labels = ["a\\" pool-size = 1"]'),
    }

    def test_the_text_in_a_value_or_a_comment_does_not_refuse(self):
        for how, (old, new) in self.TEXT.items():
            with self.subTest(how=how):
                c = config()
                self.assertEqual(c.count(old), 1)
                r, u, raw, res = self.on(c.replace(old, new))
                self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
                self.assertTrue(u.get()['on'])

    KEYS = {   # a key that names pool-size, added after the [scaleset] block's url line (or in [tart])
        'a bare key in the scale set': 'pool-size = 0',
        'a dotted key': 'tart.pool-size = 0',
        'a dotted key with spaces': 'tart . pool-size = 0',
        'a quoted key': '"pool-size" = 0',
        'a literal quoted key': "'pool-size' = 0",
        'a quoted dotted key': 'tart."pool-size" = 0',
        'an inline table': 'tart = { pool-size = 0 }',
        'an inline table, quoted': 'tart = {cpu = 4, "pool-size" = 0}',
        'after a URL on the same line': 'tart = { url = "https://x/", pool-size = 0 }',
        'a string that does not end on its line': 'tart = """pool-size = 1',
    }

    def test_a_key_that_names_pool_size_refuses(self):
        for how, line in self.KEYS.items():
            with self.subTest(how=how):
                c = config().replace('url = "https://github.com/OWNER/REPO"\n',
                                     'url = "https://github.com/OWNER/REPO"\n%s\n' % line)
                n = c.splitlines().index(line) + 1
                r, u, raw, res = self.on(c)
                self.assertEqual((res.returncode, res.stdout), (1, POOL_UNREAD % {'c': r.config, 'line': n}), res.stderr)
                self.assertEqual(u.raw(), raw)

    def test_control_the_text_cells_with_a_real_key_refuse(self):
        for how, (old, new) in self.TEXT.items():
            with self.subTest(how=how):
                c = config().replace(old, new).replace('disable-update = false\n',
                                                       'disable-update = false\ntart.pool-size = 1\n')
                n = c.splitlines().index('tart.pool-size = 1') + 1
                r, u, raw, res = self.on(c)
                self.assertEqual((res.returncode, res.stdout), (1, POOL_UNREAD % {'c': r.config, 'line': n}), res.stderr)

    def test_control_the_tart_line_is_still_read(self):
        c = config().replace('pool-size = 0 ', 'pool-size = 2 ')
        r, u, raw, res = self.on(c)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('[tart] pool-size = 2 (a warm pool)', res.stdout)


# ---- the ONE Mac reader of setup/tls-excluded-spki (bin/tls-excluded-lib)

READER = '''set -u
export LC_ALL=C
source %s || { print -r -- "cannot source"; exit 9 }
tls_excluded "$1"; rc=$?
print -r -- "rc $rc"
if (( rc == 0 )); then print -rl -- $tls_keys; else print -r -- "why $REPLY"; fi
'''

# the reader's cases: the same as linux-docker's reader (tests/hetzner/test_tls.py, Reader), so the two agree
REFUSALS = {
    'a first field in upper case': ['A' * 64 + ' x', GOOD],
    'a first field of 63 hex': ['c' * 63 + ' x', GOOD],
    'a first field of 65 hex': ['c' * 65 + ' x', GOOD],
    'a leading space': [' ' + GOOD],
    'a tab after the hash': ['d' * 64 + '\tx', GOOD],
    'a line of spaces': [GOOD, '   '],
    'a duplicate hash': [GOOD, 'c' * 64 + ' again'],
    'zero data lines (comments only)': ['# nothing excluded', ''],
    'zero data lines (an empty file)': [],
}
CR = {'a CR byte in a data line': GOOD + '\r\n', 'a CR byte in a comment': '# x\r\n' + GOOD + '\n'}


class Reader:
    """a copy of bin/tls-excluded-lib, sourced by a driver; read(text) -> (rc, keys, why)"""

    def __init__(self, test):
        self.sb = Sandbox(test)
        lib = self.sb.copy_script('bin/tls-excluded-lib', [])
        self.driver = self.sb.write(self.sb.path('driver'), READER % lib, 0o755)

    def read(self, text=None, path=None):
        if path is None:
            path = self.sb.write(self.sb.path('data'), text)
        r = self.sb.run([ZSH, '-f', self.driver, path])
        out = r.stdout.splitlines()
        self.sb.test.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rc = int(out[0].split()[1])
        return rc, (out[1:] if rc == 0 else []), (out[1][len('why '):] if rc else '')


class TestExcludedReader(unittest.TestCase):
    """tls_excluded FILE: every key, in file order, once all lines passed; one bad line REFUSES the whole file (the
    data file's header has the rules). The same cases as linux-docker's reader, and the same answers as the Python
    reading the Hetzner cells pin (read_data)."""

    def test_the_release_file_is_read_in_order(self):
        rc, keys, why = Reader(self).read(path=DATA)
        self.assertEqual((rc, keys), (0, [h for h, _ in read_data(DATA)]), why)

    def test_comments_empty_lines_free_names_and_no_name_are_read(self):
        h1, h2, h3 = 'a' * 64, 'b' * 64, 'e' * 64
        text = '# a comment\n\n#\n%s a name with  two spaces, a # and a \\\n\n%s\n%s last line, no newline' % (h1, h2, h3)
        rc, keys, why = Reader(self).read(text)
        self.assertEqual((rc, keys), (0, [h1, h2, h3]), why)

    def test_each_refusal_refuses_the_whole_file(self):
        rd = Reader(self)
        for why, lines in REFUSALS.items():
            with self.subTest(why):
                rc, keys, said = rd.read(''.join(l + '\n' for l in lines))
                self.assertEqual((rc, keys), (1, []), why)
                self.assertIn('refused', said, why)
        for why, text in CR.items():
            with self.subTest(why):
                rc, keys, said = rd.read(text)
                self.assertEqual((rc, keys), (1, []), why)
                self.assertIn('CR byte', said)
        with self.subTest('no file'):
            rc, keys, said = rd.read(path=rd.sb.path('absent'))
            self.assertEqual((rc, keys), (1, []))
            self.assertIn('cannot read the excluded keys', said)

    def test_control_the_good_line_alone_is_read(self):
        rc, keys, why = Reader(self).read(GOOD + '\n')
        self.assertEqual((rc, keys), (0, ['c' * 64]), why)

    def test_the_python_reading_agrees_on_every_case(self):
        # the Hetzner cells pin linux-docker's reader to read_data: the same answer here pins the two readers equal
        rd = Reader(self)
        for why, text in list((w, ''.join(l + '\n' for l in ls)) for w, ls in REFUSALS.items()) + list(CR.items()) + [
                ('good', GOOD + '\n'), ('release', open(DATA).read())]:
            with self.subTest(why):
                p = rd.sb.write(rd.sb.path('agree'), text)
                try:
                    want = (0, [h for h, _ in read_data(p)])
                except ValueError:
                    want = (1, [])
                rc, keys, said = rd.read(path=p)
                self.assertEqual((rc, keys), want, said)


# ---- golden-emudhra: the keys from setup/tls-excluded-spki, filled into the guest part

class TestGoldenEmudhraKeys(unittest.TestCase):
    """golden-emudhra holds no key: it reads setup/tls-excluded-spki through bin/tls-excluded-lib and fills the guest
    part's EXCLUDED_SPKI line with those keys (ONE copy). A data file the reader refuses STOPs it before any tart exec.
    The guest part STOPs (exit 2) when its line was not filled."""

    def gate(self, data=None):
        """golden-emudhra --gate on a stub tart whose save and gate steps succeed; DATA replaces the data file"""
        d = os.path.realpath(self.sb.path('e'))
        tool = emudhra_copy(self, d)
        if data is not None:
            ewrite(os.path.join(d, 'setup', 'tls-excluded-spki'), data)
        scenario(d, 'save', '1. save\n')
        scenario(d, 'gate', 'gate: no FAIL\n')
        r = self.sb.run([ZSH, '-f', tool, '--gate', 's1-test'])
        guest = os.path.join(d, 'guest.txt')
        return r, d, (open(guest).read() if os.path.exists(guest) else None)

    def setUp(self):
        self.sb = Sandbox(self)

    def test_the_guest_gets_the_files_keys(self):
        r, d, guest = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('golden-emudhra: GATE GREEN', r.stdout)
        self.assertIn('\nEXCLUDED_SPKI=(%s)\n' % ' '.join(data_keys()), guest)
        self.assertNotIn(EXCLUDED_LINE, guest)

    def test_a_changed_file_changes_the_guests_keys(self):
        r, d, guest = self.gate('# two keys\n%s\n%s planted\n' % ('a' * 64, 'f' * 64))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('\nEXCLUDED_SPKI=(%s %s)\n' % ('a' * 64, 'f' * 64), guest)
        for k in data_keys():
            self.assertNotIn(k, guest)          # no key of golden-emudhra's own: the file is the one copy

    def test_a_file_the_reader_refuses_stops_before_any_tart_exec(self):
        for why, text in list((w, ''.join(l + '\n' for l in ls)) for w, ls in REFUSALS.items()) + list(CR.items()):
            with self.subTest(why):
                self.sb = Sandbox(self)
                r, d, guest = self.gate(text)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertTrue(r.stdout.startswith('golden-emudhra: STOP the excluded keys: '), r.stdout)
                self.assertFalse(os.path.exists(os.path.join(d, 'exec-vms')), 'a tart exec ran')
                self.assertIsNone(guest)

    def test_control_the_good_line_alone_reaches_the_guest(self):
        r, d, guest = self.gate(GOOD + '\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(os.path.join(d, 'exec-vms')))
        self.assertIn('\nEXCLUDED_SPKI=(%s)\n' % ('c' * 64), guest)

    def test_no_reader_beside_it_stops(self):
        d = os.path.realpath(self.sb.path('e'))
        tool = emudhra_copy(self, d)
        os.remove(os.path.join(d, 'bin', 'tls-excluded-lib'))
        r = self.sb.run([ZSH, '-f', tool, '--gate', 's1-test'])
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('golden-emudhra: STOP cannot load %s/bin/tls-excluded-lib' % d, r.stdout)
        self.assertFalse(os.path.exists(os.path.join(d, 'exec-vms')))

    def guest_run(self, filled):
        w = self.sb.mkdir('w')
        text = guest_text(self).replace('[[ $W == /private/tmp/golden-emudhra.* && -d $W ]]', '[[ $W == %s && -d $W ]]' % w)
        if filled:
            text = text.replace(EXCLUDED_LINE, 'EXCLUDED_SPKI=(%s)' % ' '.join(data_keys()))
        g = self.sb.write(self.sb.path('guest.zsh'), text)
        return self.sb.run([ZSH, '-f', g, 'no-such-step', w])

    def test_the_guest_part_stops_when_its_line_was_not_filled(self):
        r = self.guest_run(False)
        self.assertEqual((r.returncode, r.stdout), (2, 'STOP the guest part holds no excluded key from the host '
                                                       '(@EXCLUDED_SPKI@)\n'))

    def test_control_a_filled_guest_part_runs_its_step(self):
        r = self.guest_run(True)
        self.assertEqual((r.returncode, r.stdout), (2, "STOP unknown step 'no-such-step'\n"))


# ---- the release half: bin/runner-updater-release

OPENSSL = '/usr/bin/openssl'
SYSTEM_BUNDLE = '/etc/ssl/cert.pem'   # read, never written
API = 'https://api.github.com/repos/actions/runner'
DL = 'https://github.com/actions/runner/releases/download'
V0, V1, V2 = '2.338.2', '2.338.9', '2.339.0'
DAY = 86400
NOW = calendar.timegm((2026, 11, 3, 12, 0, 0, 0, 0, 0))

# GitHub: a curl stub. It logs its argv (one line, quoted) to D/calls and the OPENSSL_X509_TEA_DISABLE it saw to D/tea,
# needs its --cacert to be a file, then answers the URL (its last operand) from D/<key>.code and D/<key>.body (key: the
# URL with every other character than a letter or digit made _), or exits D/<key>.exit. A URL with no route: exit 7 (no
# connection), as with no network.
GH_STUB = r"""D=@D@
print -r -- "${(qq)@}" >> $D/calls
print -r -- "${OPENSSL_X509_TEA_DISABLE-unset}" >> $D/tea
out= fmt= url= ca=
while (( $# )); do
  case $1 in
    (-o) out=$2; shift 2 ;;
    (-w) fmt=$2; shift 2 ;;
    (--cacert) ca=$2; shift 2 ;;
    (-H|--max-time|--max-redirs|--max-filesize|--proto|--proto-redir|--capath) shift 2 ;;
    (-*) shift ;;
    (*) url=$1; shift ;;
  esac
done
[[ -f $ca ]] || { print -u2 -r -- "stub curl: --cacert is not a file: '$ca'"; exit 77 }
k=${url//[^A-Za-z0-9]/_}
[[ -f $D/$k.exit ]] && exit $(<$D/$k.exit)
[[ -f $D/$k.code ]] || exit 7
[[ -n $out ]] && { if [[ -f $D/$k.body ]]; then /bin/cat $D/$k.body > $out; else : > $out; fi }
[[ -n $fmt ]] && print -rn -- $(<$D/$k.code)
exit 0
"""

DRIVER = """set -u
export LC_ALL=C TZ=UTC
umask 077
STATEDIR=%(statedir)s RELBIN=%(bin)s JQ=%(jq)s DD=/bin/dd CONFIG=%(config)s CORE=%(core)s
source $RELBIN/runner-updater-lib || { print -r -- "cannot source the lib"; exit 9 }
source $RELBIN/runner-updater-release || { print -r -- "cannot source the release file"; exit 9 }
%(snippet)s
"""


def key(url):
    return re.sub(r'[^A-Za-z0-9]', '_', url)


def tarball_bytes(v):
    return ('a runner tarball of v%s\n' % v).encode()


def digest_of(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def iso(epoch):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(epoch))


def release(v=V2, published=NOW - 3 * DAY, digest=None, tag=None, assets=None, **drop):
    """GitHub's answer for release v: the Linux asset and the darwin-arm64 one (DIGEST: the stub tarball's)"""
    name = 'actions-runner-osx-arm64-%s.tar.gz' % v
    r = {'tag_name': tag or 'v' + v, 'name': 'v' + v, 'published_at': iso(published) if published is not None else None,
         'assets': assets if assets is not None else [
             {'name': 'actions-runner-linux-x64-%s.tar.gz' % v, 'digest': 'sha256:' + 'e' * 64,
              'browser_download_url': '%s/v%s/actions-runner-linux-x64-%s.tar.gz' % (DL, v, v)},
             {'name': name, 'digest': digest if digest is not None else digest_of(tarball_bytes(v)),
              'browser_download_url': '%s/v%s/%s' % (DL, v, name)}]}
    for k in drop:
        r.pop(k)
    return json.dumps(r)


def make_ca(d, name):
    """a self-signed test CA (EC P-256) made with the filter's openssl -> (its PEM, the SHA-256 of its SPKI)"""
    os.makedirs(d, exist_ok=True)
    subprocess.run([OPENSSL, 'req', '-x509', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1',
                    '-nodes', '-keyout', name + '.key', '-out', name + '.pem', '-days', '3', '-subj',
                    '/CN=liveapp test ' + name], cwd=d, check=True, capture_output=True, stdin=subprocess.DEVNULL)
    pem = read_text(os.path.join(d, name + '.pem'))
    return pem, spki_sha256(pem)


def system_pems():
    return pems(read_text(SYSTEM_BUNDLE))


class Kit:
    """runner-updater-lib, tls-excluded-lib and runner-updater-release copied into a release bin/ of a sandbox (its
    setup/ holds a copy of the data file), RL_CURL rewritten to the GitHub stub and RL_SRC to SOURCE (a file of the
    sandbox: a copy of the system bundle unless given); run(SNIPPET) runs a zsh driver that sources the two files."""

    def __init__(self, test, source=None, rewrites=(), release_text=None):
        sb = self.sb = Sandbox(test)
        self.test = test
        self.root = sb.mkdir('rel')
        self.bin = sb.mkdir('rel', 'bin')
        self.statedir = sb.path('state', 'runner-updater')
        os.makedirs(self.statedir)
        self.rdir = os.path.join(self.statedir, 'release')
        self.bundle = os.path.join(self.rdir, 'bundle.pem')
        self.gh = sb.mkdir('gh')
        self.curl = sb.write(sb.path('tools-gh', 'curl'), '#!/bin/zsh -f\n' + GH_STUB.replace('@D@', self.gh), 0o755)
        self.source = sb.write(sb.path('ca', 'cert.pem'), source if source is not None else read_text(SYSTEM_BUNDLE))
        self.data = sb.write(os.path.join(self.root, 'setup', 'tls-excluded-spki'), read_text(DATA))
        sb.copy_script('bin/runner-updater-lib', [], dest=os.path.join(self.bin, 'runner-updater-lib'))
        sb.copy_script('bin/tls-excluded-lib', [], dest=os.path.join(self.bin, 'tls-excluded-lib'))
        self.rewrites = [('RL_CURL=/usr/bin/curl', 'RL_CURL=' + self.curl),
                         ('RL_SRC=/etc/ssl/cert.pem', 'RL_SRC=' + self.source)] + list(rewrites)
        self.release = self.copy_release(release_text)

    def copy_release(self, text=None):
        """the release file (or TEXT: a mutant of it) with the kit's rewrites"""
        if text is None:
            return self.sb.copy_script('bin/runner-updater-release', self.rewrites,
                                       dest=os.path.join(self.bin, 'runner-updater-release'))
        for old, new in self.rewrites:
            self.test.assertIn(old, text)
            text = text.replace(old, new)
        return self.sb.write(os.path.join(self.bin, 'runner-updater-release'), text)

    def run(self, snippet, env=None):
        d = self.sb.write(self.sb.path('driver'), DRIVER % {
            'statedir': self.statedir, 'bin': self.bin, 'jq': the_jq(), 'config': self.sb.path('config.toml'),
            'core': os.path.join(REPO, 'core'), 'snippet': snippet}, 0o755)
        return self.sb.run([ZSH, '-f', d], extra_env=env)

    def route(self, url, code=200, body='', exit=None):
        k = key(url)
        if exit is not None:
            self.sb.write(os.path.join(self.gh, k + '.exit'), '%d\n' % exit)
            return
        self.sb.write(os.path.join(self.gh, k + '.code'), '%d\n' % code)
        with open(os.path.join(self.gh, k + '.body'), 'wb') as f:
            f.write(body if isinstance(body, bytes) else body.encode())

    def latest(self, body=None, code=200, v=V2, tarball=None, tcode=200):
        """the latest release answers BODY (default: release(v)), and its darwin-arm64 tarball TARBALL"""
        self.route(API + '/releases/latest', code, body if body is not None else release(v))
        name = 'actions-runner-osx-arm64-%s.tar.gz' % v
        self.route('%s/v%s/%s' % (DL, v, name), tcode, tarball if tarball is not None else tarball_bytes(v))

    def calls(self):
        p = os.path.join(self.gh, 'calls')
        return [shlex.split(l) for l in read_text(p).splitlines()] if os.path.exists(p) else []

    def urls(self):
        return [c[-1] for c in self.calls()]

    def tea(self):
        p = os.path.join(self.gh, 'tea')
        return read_text(p).splitlines() if os.path.exists(p) else []

    def keys(self, path=None):
        return [spki_sha256(p) for p in pems(read_text(path or self.bundle))]


# ---- the TLS filter

BUNDLE = 'rl_bundle; rc=$?; print -r -- "rc $rc"; (( rc == 0 )) && print -r -- "bundle $RL_BUNDLE" || print -r -- "why $REPLY"'


class TestFilter(unittest.TestCase):
    """rl_bundle: the filtered bundle = the host bundle (RL_SRC) less every certificate whose SPKI sha256 the data file
    names, in the source's order; at least RL_FLOOR (100) kept, else a STOP and no bundle; a certificate openssl cannot
    read: a STOP. Rebuilt when its source, the data file, the openssl, the filter's code, the floor or the bundle
    itself changed; else kept (the same file). The filter's openssl is /usr/bin/openssl (LibreSSL)."""

    def test_a_planted_test_ca_is_dropped_and_every_other_kept_in_order(self):
        d = Sandbox(self).path('pki')
        ca, ca_spki = make_ca(d, 'ca')
        k = Kit(self, source=read_text(SYSTEM_BUNDLE) + ca)
        k.sb.write(k.data, read_text(DATA) + ca_spki + ' liveapp test ca\n')
        r = k.run(BUNDLE)
        self.assertIn('rc 0\n', r.stdout, r.stdout + r.stderr)
        got = k.keys()
        self.assertNotIn(ca_spki, got)
        excluded = {h for h, _ in read_data(DATA)}
        self.assertEqual(got, [s for s in (spki_sha256(p) for p in system_pems()) if s not in excluded])
        self.assertGreaterEqual(len(got), 100)
        self.assertIn('runner-updater: tls: the filtered CA bundle: %d certificates of %s kept, 1 dropped'
                      % (len(got), k.source), r.stdout)

    def test_control_an_unlisted_test_ca_is_kept(self):
        d = Sandbox(self).path('pki')
        ca, ca_spki = make_ca(d, 'ca')
        other, other_spki = make_ca(d, 'other')
        k = Kit(self, source=read_text(SYSTEM_BUNDLE) + ca)
        k.sb.write(k.data, read_text(DATA) + other_spki + ' liveapp test other (in no bundle)\n')
        r = k.run(BUNDLE)
        self.assertIn('rc 0\n', r.stdout, r.stdout + r.stderr)
        self.assertEqual(k.keys()[-1], ca_spki)

    def test_fewer_than_100_kept_stops_and_writes_no_bundle(self):
        first = system_pems()[:100]
        for listed, ok in ((spki_sha256(first[0]), False), ('f' * 64, True)):
            with self.subTest(ok=ok):
                k = Kit(self, source=''.join(first))
                k.sb.write(k.data, listed + ' one key\n')
                r = k.run(BUNDLE)
                if ok:
                    self.assertIn('rc 0\n', r.stdout, r.stdout + r.stderr)
                    self.assertEqual(len(k.keys()), 100)
                else:
                    self.assertIn('rc 1\nwhy STOP the filtered CA bundle: only 99 certificates of %s kept (1 '
                                  'excluded), want 100 or more\n' % k.source, r.stdout)
                    self.assertFalse(os.path.exists(k.bundle))

    def test_a_certificate_openssl_cannot_read_stops(self):
        bad = '-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n'
        for extra, ok in ((bad, False), ('', True)):
            with self.subTest(ok=ok):
                k = Kit(self, source=read_text(SYSTEM_BUNDLE) + extra)
                r = k.run(BUNDLE)
                self.assertIn('rc %d\n' % (0 if ok else 1), r.stdout, r.stdout + r.stderr)
                if not ok:
                    self.assertIn('a certificate whose key %s cannot read' % OPENSSL, r.stdout)
                    self.assertFalse(os.path.exists(k.bundle))

    def test_a_data_file_the_reader_refuses_stops(self):
        for text, ok in (('# nothing\n', False), (GOOD + '\r\n', False), (GOOD + '\n', True)):
            with self.subTest(text=text):
                k = Kit(self)
                k.sb.write(k.data, text)
                r = k.run(BUNDLE)
                self.assertIn('rc %d\n' % (0 if ok else 1), r.stdout, r.stdout + r.stderr)
                if not ok:
                    self.assertIn('why STOP the filtered CA bundle: ', r.stdout)

    def test_the_bundle_is_rebuilt_only_when_an_input_or_the_bundle_changed(self):
        d = Sandbox(self).path('pki')
        other, other_spki = make_ca(d, 'other')

        def change(how):
            k = Kit(self)
            r = k.run(BUNDLE)
            self.assertIn('rc 0\n', r.stdout, r.stdout + r.stderr)
            ino = os.stat(k.bundle).st_ino
            how(k)
            r = k.run(BUNDLE)
            self.assertIn('rc 0\n', r.stdout, r.stdout + r.stderr)
            return os.stat(k.bundle).st_ino != ino, k, r

        rebuilt, k, r = change(lambda k: None)
        self.assertFalse(rebuilt, 'the same inputs rebuilt the bundle')     # the control
        self.assertNotIn('runner-updater: tls:', r.stdout)                   # a current bundle says nothing
        rebuilt, k, r = change(lambda k: k.sb.write(k.source, read_text(k.source) + other))
        self.assertTrue(rebuilt, 'a changed source did not rebuild the bundle')
        self.assertEqual(k.keys()[-1], other_spki)
        rebuilt, k, r = change(lambda k: k.sb.write(k.data, read_text(k.data) + 'e' * 64 + ' one more\n'))
        self.assertTrue(rebuilt, 'a changed data file did not rebuild the bundle')
        rebuilt, k, r = change(lambda k: k.sb.write(k.bundle, read_text(k.bundle) + other, 0o600))
        self.assertTrue(rebuilt, 'a bundle changed by hand was used as it was')
        self.assertNotIn(other_spki, k.keys())
        rebuilt, k, r = change(lambda k: k.copy_release(read_text(os.path.join(REPO, 'bin', 'runner-updater-release'))
                                                         .replace('RL_FLOOR=100', 'RL_FLOOR=99')))
        self.assertTrue(rebuilt, 'a bundle made under another floor was kept')


# the real roots, public certificates (tests/studio/fixtures/tls/, each file's first line names its source): the two
# excluded roots on this Mac, by the data file's name and the key type LibreSSL must hash, and a real unlisted root
TLS_FIXTURES = os.path.join(REPO, 'tests', 'studio', 'fixtures', 'tls')
REAL_EXCLUDED = (('aaa-certificate-services.pem', 'AAA Certificate Services', 'rsaEncryption'),
                 ('emsign-ecc-root-ca-g3.pem', 'emSign ECC Root CA - G3', 'id-ecPublicKey'))
REAL_KEPT = 'telia-root-ca-v2.pem'


def real_root(name):
    """the one certificate of the fixture NAME"""
    found = pems(read_text(os.path.join(TLS_FIXTURES, name)))
    assert len(found) == 1, (name, len(found))
    return found[0]


class TestFilterRealRoots(unittest.TestCase):
    """rl_bundle with the real data file on the REAL excluded roots (Opus r1 P3-1): AAA Certificate Services (an RSA
    key) and emSign ECC Root CA - G3 (an EC key), appended to a copy of the system bundle, are each dropped by their
    SPKI sha256 as the filter's real /usr/bin/openssl (LibreSSL) reads it. /etc/ssl/cert.pem holds neither, and this
    Mac has no copy of the third excluded root (emSign Root TLS CA - G3). The control: Telia Root CA v2, a real RSA root
    the file does not list and the system bundle does not hold, is kept."""

    def setUp(self):
        self.data = {name: h for h, name in read_data(DATA)}
        self.system = [spki_sha256(p) for p in system_pems()]
        self.kept = real_root(REAL_KEPT)
        self.kept_spki = spki_sha256(self.kept)
        self.assertNotIn(self.kept_spki, self.data.values())
        self.assertNotIn(self.kept_spki, self.system)

    def test_the_real_excluded_roots_are_dropped_by_their_keys(self):
        extra = ''
        for f, name, alg in REAL_EXCLUDED:
            pem = real_root(f)
            self.assertEqual(spki_sha256(pem), self.data[name], f)   # the fixture holds the key the file names
            text = subprocess.run([OPENSSL, 'x509', '-noout', '-text'], input=pem, capture_output=True, text=True,
                                  check=True).stdout
            self.assertIn('Public Key Algorithm: %s\n' % alg, text, f)
            extra += pem
        k = Kit(self, source=read_text(SYSTEM_BUNDLE) + extra + self.kept)
        r = k.run(BUNDLE)
        self.assertIn('rc 0\n', r.stdout, r.stdout + r.stderr)
        got = k.keys()
        for _, name, _ in REAL_EXCLUDED:
            self.assertNotIn(self.data[name], got, name)
        want = [s for s in self.system if s not in self.data.values()] + [self.kept_spki]
        self.assertEqual(got, want)
        dropped = len(REAL_EXCLUDED) + sum(s in self.data.values() for s in self.system)
        self.assertIn('%d certificates of %s kept, %d dropped by their excluded keys' % (len(want), k.source, dropped),
                      r.stdout)

    def test_control_a_real_unlisted_root_is_kept(self):
        k = Kit(self, source=read_text(SYSTEM_BUNDLE) + self.kept)
        r = k.run(BUNDLE)
        self.assertIn('rc 0\n', r.stdout, r.stdout + r.stderr)
        got = k.keys()
        self.assertEqual(got[-1], self.kept_spki)
        self.assertEqual(got.count(self.kept_spki), 1)


class TestCurlLine(unittest.TestCase):
    """EVERY download of the release half is rl_curl: OPENSSL_X509_TEA_DISABLE=1 /usr/bin/curl --cacert <the filtered
    bundle> (measured 11-03: without the variable, Apple's curl falls back to the keychain and ignores the bundle). The
    pure cell reads the stub's log of each call the release check makes; the mutant without the variable goes red."""

    def calls_of_a_check(self, text=None):
        k = Kit(self, release_text=text)
        k.latest()
        r = k.run('rl_release latest; print -r -- "rc $?"; rl_tarball; print -r -- "rc $?"')
        self.assertEqual(r.stdout.count('rc 0\n'), 2, r.stdout + r.stderr)
        return k

    def test_every_call_carries_the_variable_and_the_bundle(self):
        k = self.calls_of_a_check()
        self.assertEqual(k.urls(), [API + '/releases/latest', '%s/v%s/actions-runner-osx-arm64-%s.tar.gz' % (DL, V2, V2)])
        self.assertEqual(k.tea(), ['1', '1'])
        for c in k.calls():
            self.assertEqual(c[c.index('--cacert') + 1], k.bundle)
            self.assertEqual(c[:6], ['-q', '--proto', '=https', '--proto-redir', '=https', '--tlsv1.2'])

    def test_mutant_without_the_variable_is_seen(self):
        text = read_text(os.path.join(REPO, 'bin', 'runner-updater-release'))
        self.assertEqual(text.count('OPENSSL_X509_TEA_DISABLE=1 $RL_CURL'), 1)
        k = self.calls_of_a_check(text.replace('OPENSSL_X509_TEA_DISABLE=1 $RL_CURL', '$RL_CURL'))
        self.assertEqual(k.tea(), ['unset', 'unset'])   # what the cell above would see: it goes red


# ---- release eligibility

CHECK = 'rl_release %s; rc=$?; print -r -- "rc $rc"; (( rc == 0 )) && print -r -- "facts $rl_version $rl_published $rl_digest $rl_url" || print -r -- "why $REPLY"'


class TestRelease(unittest.TestCase):
    """rl_release latest | tag V: GitHub's answer (releases/latest, releases/tags/v<V>) through rl_curl, checked: the
    tag is v<N.N.N> (tag: the version asked), ONE darwin-arm64 asset with a sha256 digest and its release's own
    download address, a published_at time. 403 and 429: WAIT (rc 75), never a refusal; any other answer: refused."""

    def check(self, body, code=200, kind='latest', v=V2):
        k = Kit(self)
        url = API + ('/releases/latest' if kind == 'latest' else '/releases/tags/v' + v)
        k.route(url, code, body)
        r = k.run(CHECK % ('latest' if kind == 'latest' else 'tag ' + v))
        lines = r.stdout.splitlines()
        self.assertIn(lines[0], ('rc 0', 'rc 1', 'rc 75'), r.stdout + r.stderr)
        self.assertEqual(k.urls(), [url])
        return int(lines[0].split()[1]), lines[1]

    def test_a_good_latest_release(self):
        rc, line = self.check(release())
        self.assertEqual((rc, line), (0, 'facts %s %d %s %s/v%s/actions-runner-osx-arm64-%s.tar.gz' % (
            V2, NOW - 3 * DAY, digest_of(tarball_bytes(V2)), DL, V2, V2)))

    BAD = {   # each check: (the answer, the refusal); its control is test_a_good_latest_release
        'a tag that is not v<N.N.N>': (release(tag='v2.339'), "its tag \"v2.339\" is not v<N.N.N>"),
        'a tag with a suffix': (release(tag='v2.339.0-beta'), 'is not v<N.N.N>'),
        'a tag with no v': (release(tag='2.339.0'), 'is not v<N.N.N>'),
        'no tag': (release(tag_name=None), 'is not v<N.N.N>'),
        'no darwin-arm64 asset': (release(assets=[]), 'has 0 assets named actions-runner-osx-arm64-2.339.0.tar.gz, want 1'),
        'two darwin-arm64 assets': (json.dumps(dict(json.loads(release()), assets=json.loads(release())['assets'] * 2)),
                                    'has 2 assets named'),
        'no digest': (release(digest=''), 'has no sha256 digest'),
        'a digest of another kind': (release(digest='sha512:' + 'a' * 64), 'has no sha256 digest'),
        'a download from elsewhere': (json.dumps(dict(json.loads(release()), assets=[
            dict(json.loads(release())['assets'][1], browser_download_url='https://example.com/x.tar.gz')])),
            "is not downloaded from its release's own address"),
        'no published_at': (release(published=None), 'has no published_at time'),
        'not JSON': ('<html>', 'the answer could not be read'),
        'not an object': ('[1]', 'not a JSON object'),
    }

    def test_each_check_refuses(self):
        for why, (body, said) in self.BAD.items():
            with self.subTest(why):
                rc, line = self.check(body)
                self.assertEqual(rc, 1, line)
                self.assertTrue(line.startswith('why %s/releases/latest: ' % API), line)
                self.assertIn(said, line)

    def test_403_and_429_wait(self):
        for code in (403, 429):
            with self.subTest(code=code):
                rc, line = self.check('{"message": "API rate limit exceeded"}', code=code)
                self.assertEqual((rc, line), (75, 'why GitHub answered %d (a rate limit) for %s/releases/latest'
                                              % (code, API)))

    def test_control_other_answers_refuse_and_never_wait(self):
        for code in (404, 500, 401):
            with self.subTest(code=code):
                rc, line = self.check('{}', code=code)
                self.assertEqual((rc, line), (1, 'why GitHub answered %d for %s/releases/latest' % (code, API)))

    def test_no_answer_refuses(self):
        k = Kit(self)
        k.route(API + '/releases/latest', exit=6)
        r = k.run(CHECK % 'latest')
        self.assertIn("rc 1\nwhy GitHub's API did not answer %s/releases/latest (curl exit 6)\n" % API, r.stdout)

    def test_a_named_release_reads_its_tag(self):
        rc, line = self.check(release(), kind='tag')
        self.assertEqual(rc, 0, line)
        self.assertTrue(line.startswith('facts %s ' % V2), line)

    def test_a_named_release_must_answer_its_own_version(self):
        rc, line = self.check(release(v=V1), kind='tag')
        self.assertEqual(rc, 1)
        self.assertIn('the answer is release v%s, not v%s' % (V1, V2), line)

    def test_a_named_version_that_is_not_one_is_refused_before_any_call(self):
        k = Kit(self)
        r = k.run(CHECK % 'tag 2.339')
        self.assertIn("rc 1\nwhy not a runner version: '2.339'\n", r.stdout)
        self.assertEqual(k.calls(), [])


ELIGIBLE = 'rl_eligible %d; rc=$?; print -r -- "rc $rc"; (( rc == 0 )) && print -r -- "v $rl_version" || print -r -- "why $REPLY"'


class TestAge(unittest.TestCase):
    """rl_eligible NOW: the latest release, at least 2 days old against NOW (the glue's UTC clock)."""

    def at(self, published, now=NOW):
        k = Kit(self)
        k.latest(release(published=published))
        r = k.run(ELIGIBLE % now)
        return r.stdout.splitlines()

    def test_two_days_old_is_eligible(self):
        self.assertEqual(self.at(NOW - 2 * DAY), ['rc 0', 'v ' + V2])

    def test_a_second_younger_is_not(self):
        out = self.at(NOW - 2 * DAY + 1)
        self.assertEqual(out[0], 'rc 1')
        self.assertEqual(out[1], 'why release v%s is younger than 2 days: published %s, eligible from %s'
                         % (V2, '2026-11-01 12:00:01 UTC', '2026-11-03 12:00:01 UTC'))

    def test_a_release_from_the_future_is_not(self):
        self.assertEqual(self.at(NOW + 60)[0], 'rc 1')


TARBALL = 'rl_release latest; rl_tarball; rc=$?; print -r -- "rc $rc"; (( rc == 0 )) || print -r -- "why $REPLY"'


class TestTarball(unittest.TestCase):
    """rl_tarball: the darwin-arm64 tarball's sha256 equals the asset's digest. It downloads it (through rl_curl) into
    STATEDIR/release, hashes it and removes it; a version and digest it has verified are recorded (release/verified),
    so a later pass does not download them again. 403 and 429: WAIT."""

    def test_a_tarball_that_matches_its_digest(self):
        k = Kit(self)
        k.latest()
        r = k.run(TARBALL)
        self.assertEqual(r.stdout, 'rc 0\n', r.stderr)
        self.assertEqual(read_text(os.path.join(k.rdir, 'verified')), '%s %s\n' % (V2, digest_of(tarball_bytes(V2))))
        self.assertEqual(sorted(os.listdir(k.rdir)), ['bundle.pem', 'bundle.stamp', 'verified'])   # the download is gone

    def test_a_tarball_that_does_not_match_is_refused_and_removed(self):
        k = Kit(self)
        k.latest(tarball=b'other bytes\n')
        r = k.run(TARBALL)
        self.assertEqual(r.stdout.splitlines()[0], 'rc 1')
        self.assertIn('its sha256 is %s, not the release asset\'s digest %s' % (
            hashlib.sha256(b'other bytes\n').hexdigest(), digest_of(tarball_bytes(V2))), r.stdout)
        self.assertEqual(sorted(os.listdir(k.rdir)), ['bundle.pem', 'bundle.stamp'])   # no record, no download left

    def test_a_verified_release_is_not_downloaded_again(self):
        k = Kit(self)
        k.latest()
        k.run(TARBALL)
        n = len(k.calls())
        r = k.run(TARBALL)
        self.assertEqual(r.stdout, 'rc 0\n')
        self.assertEqual(k.urls()[n:], [API + '/releases/latest'])   # the API only

    def test_control_a_record_of_another_digest_downloads(self):
        k = Kit(self)
        k.latest()
        os.makedirs(k.rdir, mode=0o700)
        k.sb.write(os.path.join(k.rdir, 'verified'), '%s sha256:%s\n' % (V2, 'a' * 64), 0o600)
        r = k.run(TARBALL)
        self.assertEqual(r.stdout, 'rc 0\n')
        self.assertEqual(len(k.urls()), 2)

    def test_403_and_429_on_the_download_wait(self):
        for code, rc in ((403, 75), (429, 75), (404, 1)):
            with self.subTest(code=code):
                k = Kit(self)
                k.latest(tcode=code)
                r = k.run(TARBALL)
                self.assertEqual(r.stdout.splitlines()[0], 'rc %d' % rc, r.stdout)
                self.assertFalse(os.path.exists(os.path.join(k.rdir, 'verified')))


# ---- the recipe

BUILDER = {   # a fixture tree of the mac-golden family's recipe files (hashed, never run)
    'bin/golden-build': ('#!/bin/zsh -f\nBASE=ghcr.io/cirruslabs/macos-golden-gate-base@sha256:%s\n'
                         'RUNNER_SHA=%s\nRUNNER_VERSION=%s   # with RUNNER_SHA, the release literal\nsay build\n'
                         % ('5' * 64, '2' * 64, V0)),
    'bin/golden-emudhra': '#!/bin/zsh -f\nsay emudhra\n',
    'bin/node-diff-compare': '#!/bin/zsh -f\nsay compare\n',
    'bin/real-run': '#!/bin/zsh -f\nsay run\n',
    'bin/tls-excluded-lib': '#!/bin/zsh -f\ntls_excluded() { :; }\n',
    'setup/emudhra.node-diff': '# named\n',
    'setup/tls-excluded-spki': GOOD + '\n',
}
RECIPE = 'rl_recipe %s %s; rc=$?; print -r -- "rc $rc"; print -r -- "$REPLY"'


def recipe_of(files):
    """the recipe's definition, independently: the sha256 of one line `<sha256>  <path>` per file in the family's
    order, golden-build's RUNNER_VERSION and RUNNER_SHA values masked"""
    text = ''
    for path in ('bin/golden-build', 'bin/golden-emudhra', 'bin/node-diff-compare', 'bin/real-run',
                 'bin/tls-excluded-lib', 'setup/emudhra.node-diff', 'setup/tls-excluded-spki'):
        data = files[path]
        if path == 'bin/golden-build':
            data = re.sub(r'(?m)^RUNNER_VERSION=[0-9]+\.[0-9]+\.[0-9]+', 'RUNNER_VERSION=(runner)', data)
            data = re.sub(r'(?m)^RUNNER_SHA=[0-9a-f]{64}', 'RUNNER_SHA=(runner)', data)
        text += '%s  %s\n' % (hashlib.sha256(data.encode()).hexdigest(), path)
    return hashlib.sha256(text.encode()).hexdigest()


class TestRecipe(unittest.TestCase):
    """rl_recipe FAMILY ROOT: per family, the sha256 of its builder files, the node-diff file and the base pin (BASE=,
    a line of golden-build), with the runner lines (golden-build's RUNNER_VERSION and RUNNER_SHA values) masked. Only
    mac-golden has one in this release."""

    def tree(self, k, files):
        for path, text in files.items():
            k.sb.write(os.path.join(k.root, 'x', path), text)
        return os.path.join(k.root, 'x')

    def recipe(self, files, family='mac-golden'):
        k = Kit(self)
        r = k.run(RECIPE % (family, self.tree(k, files)))
        rc, reply = r.stdout.splitlines()[:2]
        return int(rc.split()[1]), reply

    def test_the_definition(self):
        self.assertEqual(self.recipe(BUILDER), (0, recipe_of(BUILDER)))

    def test_a_runner_version_only_change_keeps_the_recipe(self):
        f = dict(BUILDER)
        f['bin/golden-build'] = f['bin/golden-build'].replace('RUNNER_SHA=' + '2' * 64, 'RUNNER_SHA=' + '9' * 64).replace(
            'RUNNER_VERSION=' + V0, 'RUNNER_VERSION=' + V2)
        self.assertNotEqual(f, BUILDER)
        self.assertEqual(self.recipe(f), self.recipe(BUILDER))

    CHANGES = {
        'a builder line': ('bin/golden-build', 'say build\n', 'say build twice\n'),
        'the base pin': ('bin/golden-build', '5' * 64, '6' * 64),
        'a runner line beyond its value': ('bin/golden-build', 'the release literal', 'the literal'),
        'golden-emudhra': ('bin/golden-emudhra', 'emudhra', 'emudhra!'),
        'node-diff-compare': ('bin/node-diff-compare', 'compare', 'compare!'),
        'real-run': ('bin/real-run', 'run', 'run!'),
        'the keys reader': ('bin/tls-excluded-lib', ':;', ': ;'),
        'the node-diff file': ('setup/emudhra.node-diff', 'named', 'named, one more'),
        'the excluded keys': ('setup/tls-excluded-spki', 'the good line', 'the good line, renamed'),
    }

    def test_a_builder_change_changes_the_recipe(self):
        base = self.recipe(BUILDER)
        for why, (path, old, new) in self.CHANGES.items():
            with self.subTest(why):
                f = dict(BUILDER)
                self.assertIn(old, f[path])
                f[path] = f[path].replace(old, new)
                rc, r = self.recipe(f)
                self.assertEqual(rc, 0)
                self.assertNotEqual(r, base[1], why)

    def test_the_real_tree_masks_its_runner_lines(self):
        files = {}
        for path in BUILDER:   # the real files, hashed, never run (its host paths rewritten in every copy alike)
            files[path] = read_text(os.path.join(REPO, path)).replace('/Users/ci', '/private/var/ci-test')
        rc, real = self.recipe(files)
        self.assertEqual((rc, real), (0, recipe_of(files)))
        f = dict(files)
        f['bin/golden-build'] = re.sub(r'(?m)^RUNNER_VERSION=[0-9.]+', 'RUNNER_VERSION=9.9.9',
                                       re.sub(r'(?m)^RUNNER_SHA=[0-9a-f]{64}', 'RUNNER_SHA=' + '0' * 64, f['bin/golden-build']))
        self.assertNotEqual(f['bin/golden-build'], files['bin/golden-build'])
        self.assertEqual(self.recipe(f), (0, real))

    def test_no_recipe_for_another_family(self):
        self.assertEqual(self.recipe(BUILDER, family='fx'),
                         (1, 'this release builds no image for the family fx (no recipe)'))

    def test_a_missing_file_has_no_recipe(self):
        f = dict(BUILDER)
        del f['setup/emudhra.node-diff']
        rc, why = self.recipe(f)
        self.assertEqual(rc, 1)
        self.assertIn('the recipe of mac-golden: cannot read ', why)


# ---- REJECTED

UNREJECT = 'rl_unreject "$(<%s)" %s %s; rc=$?; print -r -- "rc $rc"; print -r -- "$REPLY"'


class TestUnreject(unittest.TestCase):
    """rl_unreject STATE FAMILY VERSION: the state with VERSION no longer rejected for FAMILY (`retry FAMILY` uses it in
    a later release); 1 when VERSION is not rejected for it (nothing to clear)."""

    def unreject(self, s, family, v):
        k = Kit(self)
        p = k.sb.write(k.sb.path('state.json'), json.dumps(s))
        r = k.run(UNREJECT % (p, family, v))
        rc, reply = r.stdout.splitlines()[:2]
        return int(rc.split()[1]), reply

    def test_it_clears_one_version_and_keeps_the_rest(self):
        s = state(on=True, families={'mac-golden': fam(rejected=[V1, V2]), 'fy': fam(rejected=[V2])})
        rc, new = self.unreject(s, 'mac-golden', V2)
        self.assertEqual(rc, 0)
        want = json.loads(json.dumps(s))
        want['families']['mac-golden']['rejected'] = [V1]
        self.assertEqual(json.loads(new), want)

    def test_control_a_version_that_is_not_rejected(self):
        s = state(on=True, families={'mac-golden': fam(rejected=[V1])})
        self.assertEqual(self.unreject(s, 'mac-golden', V2), (1, '%s is not rejected for mac-golden: nothing to clear' % V2))
        self.assertEqual(self.unreject(s, 'fz', V1)[0], 1)


# ---- the pass hook

class PassRig:
    """a Rig whose families file names mac-golden (its set mac-a: IMG), whose release bin/ holds the recipe's files
    (BUILDER), and whose release file answers from the GitHub stub and filters a copy of the system bundle. The state:
    ON, mac-golden with the recipe of those files as its baseline, IMG recorded as runner V0. EXTRA_REWRITES go into the
    runner-updater copy (after the clock's), RELEASE_REWRITES into the release file's copy. These cells end at the
    hook's decision: the pass's switch step (pass_switch, which starts the window of a due family) is cut out of the
    copy; the switch's own cells are test_runner_updater_pass."""

    def __init__(self, test, extra_rewrites=(), release_rewrites=(), **fam_kw):
        self.r = r = Rig(test, jq_wrap=True, families='mac-golden tart mac-a\n', extra_rewrites=[(
            'now=$(/bin/date -u +%s)', 'now=$RU_TEST_NOW'), (NO_SWITCH, ': ' + NO_SWITCH)] + list(extra_rewrites))
        self.u = Paths(r)
        sb = r.sb
        self.gh = sb.mkdir('gh')
        self.curl = curl = sb.write(sb.path('tools-gh2', 'curl'), '#!/bin/zsh -f\n' + GH_STUB.replace('@D@', self.gh),
                                    0o755)
        source = sb.write(sb.path('ca', 'cert.pem'), read_text(SYSTEM_BUNDLE))
        sb.copy_script('bin/runner-updater-release', [('RL_CURL=/usr/bin/curl', 'RL_CURL=' + curl),
                                                      ('RL_SRC=/etc/ssl/cert.pem', 'RL_SRC=' + source)]
                       + list(release_rewrites))
        # the recipe's files under the release folder, RELBIN/.. (the rig's RELBIN is tools/, so its bin/ is apart);
        # its setup/ also holds the filter's data file
        files = dict(BUILDER)
        files['setup/tls-excluded-spki'] = read_text(DATA)
        for path, text in files.items():
            sb.write(sb.path(path), text)
        self.recipe = recipe_of(files)
        kw = dict(recipe=self.recipe)
        kw.update(fam_kw)
        self.state = state(on=True, families={'mac-golden': fam(**kw)}, images={IMG: V0})

    def route(self, url, code=200, body=''):
        with open(os.path.join(self.gh, key(url) + '.code'), 'w') as f:
            f.write('%d\n' % code)
        with open(os.path.join(self.gh, key(url) + '.body'), 'wb') as f:
            f.write(body if isinstance(body, bytes) else body.encode())

    def latest(self, body=None, code=200, v=V2, tcode=200, tarball=None):
        self.route(API + '/releases/latest', code, body if body is not None else release(v))
        self.route('%s/v%s/actions-runner-osx-arm64-%s.tar.gz' % (DL, v, v), tcode,
                   tarball if tarball is not None else tarball_bytes(v))

    def urls(self):
        p = os.path.join(self.gh, 'calls')
        return [shlex.split(l)[-1] for l in read_text(p).splitlines()] if os.path.exists(p) else []

    def pass_(self, s=None, now=NOW):
        self.u.put(s or self.state)
        return self.r.cmd('pass', env={'RU_TEST_NOW': str(now)}, ok=False)   # a STOP it holds anew: exit 1

    def lines(self, res):
        return [l for l in res.stdout.splitlines() if l.startswith('runner-updater: pass: ') and
                ('mac-golden' in l or ' fx ' in l)]


SWITCH = 'runner-updater: pass: mac-golden is due: runner %s' % V2
NO_SWITCH = '    pass_switch $now\n'   # the pass's switch step: PassRig's copies cut it out
NOT = 'runner-updater: pass: mac-golden is not due: '


class TestPassHook(unittest.TestCase):
    """The pass hook: for each family of the families file, what it would switch to, or why not. DUE: the eligible
    latest release is newer than the family's current version (the updater's record of the image its lines name) and
    the family has no open candidate. Not due, each printed: an open candidate, NO BASELINE, recipe changed, WAIT,
    rejected, not newer, a release check. The order is the rule: what needs no network comes first."""

    def test_due_would_switch(self):
        p = PassRig(self)
        p.latest()
        res = p.pass_()
        self.assertEqual(p.lines(res), [SWITCH])
        self.assertEqual(p.urls(), [API + '/releases/latest', '%s/v%s/actions-runner-osx-arm64-%s.tar.gz' % (DL, V2, V2)])
        self.assertIn('runner-updater: tls: the filtered CA bundle: ', res.stdout)

    def test_an_open_candidate_is_not_due_and_asks_github_nothing(self):
        p = PassRig(self, candidate=cand(version=V1, lines={'mac-a': IMG}, closed_at=P[2] + 100))
        p.latest()
        res = p.pass_()
        self.assertEqual(p.lines(res), [NOT + 'an open candidate (runner %s): one open release per family' % V1])
        self.assertEqual(p.urls(), [])

    def test_no_baseline_is_a_stop_and_asks_github_nothing(self):
        p = PassRig(self, recipe=None)
        p.latest()
        res = p.pass_()
        self.assertEqual(p.lines(res), [NOT + 'STOP NO BASELINE: the family has no recipe baseline (its recipe now: %s): '
                                        'the accept of a rebuild\'s image writes it; `runner-updater rebuild mac-golden`'
                                        % p.recipe, 'runner-updater: pass: mac-golden holds STOP NO BASELINE'])
        self.assertEqual(p.urls(), [])

    def test_a_changed_recipe_is_a_stop(self):
        p = PassRig(self, recipe='a' * 64)
        p.latest()
        res = p.pass_()
        self.assertEqual(p.lines(res), [NOT + 'STOP recipe changed: its recipe is %s, its baseline %s (a builder file, '
                                        'the node-diff file or the base pin changed): the accept of a rebuild\'s image '
                                        'writes the new one; `runner-updater rebuild mac-golden`' % (p.recipe, 'a' * 64),
                                        'runner-updater: pass: mac-golden holds STOP recipe changed'])
        self.assertEqual(p.urls(), [])

    def test_a_builder_change_after_the_baseline_is_a_stop(self):
        p = PassRig(self)
        p.latest()
        p.r.sb.write(p.r.sb.path('bin', 'golden-emudhra'), BUILDER['bin/golden-emudhra'] + 'say more\n')
        res = p.pass_()
        self.assertTrue(p.lines(res)[0].startswith(NOT + 'STOP recipe changed: '), res.stdout)

    def test_control_a_runner_line_change_after_the_baseline_is_due(self):
        p = PassRig(self)
        p.latest()
        p.r.sb.write(p.r.sb.path('bin', 'golden-build'), BUILDER['bin/golden-build'].replace(
            'RUNNER_VERSION=' + V0, 'RUNNER_VERSION=' + V1))
        self.assertEqual(p.lines(p.pass_()), [SWITCH])

    def test_wait_on_403_and_429(self):
        for code in (403, 429):
            with self.subTest(code=code):
                p = PassRig(self)
                p.latest(code=code)
                self.assertEqual(p.lines(p.pass_()), [NOT + 'WAIT GitHub answered %d (a rate limit) for %s/releases/latest'
                                                      % (code, API)])

    def test_a_rejected_release_is_never_due(self):
        p = PassRig(self, rejected=[V2])
        p.latest()
        self.assertEqual(p.lines(p.pass_()), [NOT + 'release v%s is rejected for mac-golden' % V2])

    def test_control_another_rejected_version_is_due(self):
        p = PassRig(self, rejected=[V1])
        p.latest()
        self.assertEqual(p.lines(p.pass_()), [SWITCH])

    def test_cleared_by_rl_unreject_it_is_due_again(self):
        p = PassRig(self, rejected=[V2])
        p.latest()
        self.assertEqual(p.lines(p.pass_())[0], NOT + 'release v%s is rejected for mac-golden' % V2)
        k = Kit(self)
        sp = k.sb.write(k.sb.path('s.json'), json.dumps(p.u.get()))
        r = k.run(UNREJECT % (sp, 'mac-golden', V2))
        self.assertEqual(r.stdout.splitlines()[0], 'rc 0')
        self.assertEqual(p.lines(p.pass_(json.loads(r.stdout.splitlines()[1]))), [SWITCH])

    def test_not_newer_than_its_current_version(self):
        for cur in (V2, '2.340.0'):
            with self.subTest(cur=cur):
                p = PassRig(self)
                p.latest()
                s = dict(p.state, images={IMG: cur})
                self.assertEqual(p.lines(p.pass_(s)), [NOT + 'release v%s is not newer than its runner %s' % (V2, cur)])

    def test_a_current_version_the_updater_has_no_record_of(self):
        p = PassRig(self)
        p.latest()
        self.assertEqual(p.lines(p.pass_(dict(p.state, images={}))),
                         [NOT + 'the runner version of its image %s is not known (the updater has no record of it)' % IMG])
        self.assertEqual(p.urls(), [])

    def test_younger_than_two_days(self):
        p = PassRig(self)
        p.latest(body=release(published=NOW - DAY))
        self.assertTrue(p.lines(p.pass_())[0].startswith(NOT + 'release v%s is younger than 2 days' % V2))

    def test_a_tarball_that_does_not_match_its_digest(self):
        p = PassRig(self)
        p.latest(tarball=b'other bytes\n')
        line = p.lines(p.pass_())[0]
        self.assertTrue(line.startswith(NOT), line)
        self.assertIn("not the release asset's digest", line)

    def test_a_bundle_under_the_floor_is_a_stop_and_downloads_nothing(self):
        for n, ok in ((99, False), (100, True)):
            with self.subTest(kept=n):
                p = PassRig(self)
                p.r.sb.write(p.r.sb.path('ca', 'cert.pem'), ''.join(system_pems()[:n]))
                p.latest()
                lines = p.lines(p.pass_())
                if ok:
                    self.assertEqual(lines, [SWITCH])
                else:
                    self.assertEqual(lines, [NOT + 'STOP the filtered CA bundle: only 99 certificates of %s kept (0 '
                                             'excluded), want 100 or more' % p.r.sb.path('ca', 'cert.pem')])
                    self.assertEqual(p.urls(), [])

    def test_a_family_with_no_builder_asks_github_nothing(self):
        p = PassRig(self)
        p.r.sb.write(p.r.families, 'mac-golden tart mac-a\nfx tart mac-b\n')
        p.latest()
        res = p.pass_()
        self.assertEqual(p.lines(res), [SWITCH, 'runner-updater: pass: fx is not due: this release builds no image for '
                                                'the family fx (no recipe)'])
        self.assertEqual(len(p.urls()), 2)   # mac-golden's check alone

    def test_a_verified_tarball_is_not_downloaded_by_the_next_pass(self):
        p = PassRig(self)
        p.r.sb.write(p.r.families, 'mac-golden tart mac-a\n')
        p.latest()
        p.pass_()
        n = len(p.urls())
        p.pass_()
        self.assertEqual(p.urls()[n:], [API + '/releases/latest'])   # the tarball is verified once


# ---- the STOPs a family holds (PLAN D7; the ONE table is core/lib/stops.jq)

# The D7 rows, spelled here on purpose: test_the_rows_are_the_cores_table pins them to the core's table, both ways, so
# a new row gets its cell. A newer release does NOT proceed alone past a STOP of NO_ROWS; past one of YES_ROWS it does,
# so that STOP holds only its own version.
NO_ROWS = ('JOBS FAIL ON THE NEW IMAGE', 'ROLLBACK FAILED', 'CI DISABLED', 'POOL DOWN', 'HAND CHANGE', 'recipe changed',
           'NO BASELINE', 'NO EVIDENCE', 'NO IDLE', 'untested jq', 'SHIM REFUSED', 'DISK')
YES_ROWS = ('check failed', 'ROLLED BACK', 'PINNED RUNNER RETIRED')
UNKNOWN = 'A STOP THIS CORE DOES NOT KNOW'
NO_PROCEED = 'a newer release does not proceed alone past it'
NOT_KNOWN = 'a STOP this release does not know holds every release'
NO_VERSION = 'a STOP that names no version holds every release'
OF_ELIGIBLE = 'it is of the eligible release'


def held(name, version, why, family='mac-golden'):
    """the pass line of FAMILY held by the STOP NAME of VERSION"""
    shown = 'no runner version' if version in (None, '') else 'runner ' + version
    return 'runner-updater: pass: %s is not due: STOP %s (%s): %s; `runner-updater status` names its next step' % (
        family, name, shown, why)


class TestPassHookStops(unittest.TestCase):
    """DUE reads the STOPs (PLAN D7, Opus r1 P1-1). A family is not due while a STOP holds it: one that a newer release
    does not proceed alone past (the core's S::newer_proceeds from core/lib/stops.jq, never a table of this release's
    own; a name the table does not know is one), one that names no version, or one of the eligible version. It holds
    when it names the family, or names no family. The line names the STOP and its version. A STOP that holds whatever
    the release is asks GitHub nothing; one of the eligible version is known only after the release check."""

    def stopped(self, name, version, **kw):
        p = PassRig(self, stops=[stop('mac-golden', name, version=version)], **kw)
        p.latest()
        return p, p.lines(p.pass_())

    def test_the_rows_are_the_cores_table(self):
        out = subprocess.run([the_jq(), '-n', '-c', '-L', os.path.join(REPO, 'core', 'lib'),
                              'import "stops" as S; [S::table | keys[] | [., S::newer_proceeds(.)]]'],
                             capture_output=True, text=True, check=True, stdin=subprocess.DEVNULL).stdout
        self.assertEqual(sorted(map(tuple, json.loads(out))),
                         sorted([(n, False) for n in NO_ROWS] + [(n, True) for n in YES_ROWS]))

    def test_a_stop_no_newer_release_proceeds_past_holds_and_asks_github_nothing(self):
        # NO BASELINE and recipe changed are the hook's own: it decides them from the recipe on each pass (a held one
        # whose recipe is the baseline again goes: test_runner_updater_pass, TestRecipeStops)
        for name in (n for n in NO_ROWS if n not in ('NO BASELINE', 'recipe changed')):
            with self.subTest(stop=name):
                p, lines = self.stopped(name, V1)   # an OLDER version: only its row holds it
                self.assertEqual(lines, [held(name, V1, NO_PROCEED)])
                self.assertEqual(p.urls(), [])

    def test_a_stop_the_table_does_not_know_holds(self):
        p, lines = self.stopped(UNKNOWN, V1)
        self.assertEqual(lines, [held(UNKNOWN, V1, NOT_KNOWN)])
        self.assertEqual(p.urls(), [])

    def test_a_stop_of_the_eligible_version_holds(self):
        for name in YES_ROWS:
            with self.subTest(stop=name):
                p, lines = self.stopped(name, V2)
                self.assertEqual(lines, [held(name, V2, OF_ELIGIBLE)])
                self.assertEqual(p.urls(), [API + '/releases/latest'])   # the release check, and no download

    def test_control_a_stop_of_an_older_version_lets_a_newer_release_proceed(self):
        for name in YES_ROWS:
            with self.subTest(stop=name):
                self.assertEqual(self.stopped(name, V1)[1], [SWITCH])

    def test_a_stop_that_names_no_version_holds_and_asks_github_nothing(self):
        for v in (None, ''):
            for name in (YES_ROWS[0], NO_ROWS[0]):
                with self.subTest(version=v, stop=name):
                    p, lines = self.stopped(name, v)
                    self.assertEqual(lines, [held(name, v, NO_VERSION)])
                    self.assertEqual(p.urls(), [])

    def test_control_no_stop_is_due(self):
        p = PassRig(self, stops=[])
        p.latest()
        self.assertEqual(p.lines(p.pass_()), [SWITCH])

    def test_control_a_stop_of_another_family_does_not_hold_this_one(self):
        p = PassRig(self)
        p.r.sb.write(p.r.families, 'mac-golden tart mac-a\nfx tart mac-b\n')
        p.latest()
        s = json.loads(json.dumps(p.state))
        s['families']['fx'] = fam(stops=[stop('fx', 'HAND CHANGE', version=V1)])
        self.assertEqual(p.lines(p.pass_(s)), [SWITCH, held('HAND CHANGE', V1, NO_PROCEED, family='fx')])


# rl_pass on a state set by hand (the updater's own load refuses a STOP whose family is not its family's key, so these
# shapes reach rl_pass only from a later release's state): families mac-golden and fx, neither with a recipe tree here,
# so a family no STOP holds prints "the recipe of FAMILY: cannot read ..."
HAND_PASS = 'ru_fam_order=(mac-golden fx)\nru_state=$(<%s)\nrl_pass %d\nprint -r -- "rc $?"'


class TestStopsOnAStateByHand(unittest.TestCase):
    """A STOP that names no family (none, "", or not a string) holds every family, as keep.jq does; a STOP the jq
    cannot read holds every family too (fail closed): the line says the STOPs could not be read."""

    def pass_lines(self, s):
        k = Kit(self)
        p = k.sb.write(k.sb.path('state.json'), json.dumps(s))
        r = k.run(HAND_PASS % (p, NOW))
        self.assertIn('rc 0\n', r.stdout, r.stdout + r.stderr)
        return [l for l in r.stdout.splitlines() if l.startswith('runner-updater: pass: ')]

    def a_state(self, s):
        return state(on=True, families={'mac-golden': fam(), 'fx': fam(stops=[s])})

    def test_a_stop_that_names_no_family_holds_every_family(self):
        for how in ('absent', '', None, 5):
            with self.subTest(family=how):
                s = stop('fx', 'HAND CHANGE', version=V1)
                if how == 'absent':
                    del s['family']
                else:
                    s['family'] = how
                self.assertEqual(self.pass_lines(self.a_state(s)), [
                    held('HAND CHANGE', V1, NO_PROCEED), held('HAND CHANGE', V1, NO_PROCEED, family='fx')])

    def test_control_a_stop_that_names_another_family_holds_only_it(self):
        lines = self.pass_lines(self.a_state(stop('fx', 'HAND CHANGE', version=V1)))
        self.assertEqual(lines[1], held('HAND CHANGE', V1, NO_PROCEED, family='fx'))
        self.assertTrue(lines[0].startswith(NOT + 'the recipe of mac-golden: cannot read '), lines)

    def test_stops_the_jq_cannot_read_hold_every_family(self):
        s = stop('fx', 'HAND CHANGE', version=V1)
        s['stop'] = 5   # S::newer_proceeds cannot index the table with a number: jq fails
        why = 'jq could not read the STOPs of the state; a family is never due while they cannot be read'
        self.assertEqual(self.pass_lines(self.a_state(s)), [NOT + why, 'runner-updater: pass: fx is not due: ' + why])


# THE NO-ACTION PROOF OF A DUE PASS (Opus r1 P2-1). test_runner_updater_state's TestNoActionAnyPath runs a pass whose
# family has an open candidate, so the hook stops at its first check. This one runs the hook to its end: the profile
# lets start what a pass may start (PASS_RUNS) and exactly what the hook adds: the filter's openssl, mktemp, and the
# GitHub stub (PassRig's curl).
HOOK_RUNS = PASS_RUNS + ('/usr/bin/openssl', '/usr/bin/mktemp')
WOULD_SWITCH_AT = '    ru_say "pass: $f is due: runner $rl_version"\n'
ABSOLUTE = '/bin/launchctl list > /dev/null'


class TestNoActionDuePass(unittest.TestCase):
    """The hook of a DUE pass, under macOS's sandbox (test_runner_updater_state, only_these_start), with the pass's
    switch step cut out (PassRig: a due family's window is its own cells', test_runner_updater_pass): it prints "is due"
    (positive evidence that the hook ran to its end), its stderr is empty (no start was denied), and no action stub ran.
    The controls, under the same profile: an action by its absolute path planted at the is-due line is denied and the
    cell sees the denial; without openssl in the allowlist the hook never reaches "is due" (the profile binds the
    hook)."""

    def due_pass(self, runs, plant=None):
        p = PassRig(self, extra_rewrites=[KILL],
                    release_rewrites=[(WOULD_SWITCH_AT, '    %s\n%s' % (plant, WOULD_SWITCH_AT))] if plant else ())
        p.latest()
        p.u.put(p.state)
        res = p.r.sb.run(['/usr/bin/sandbox-exec', '-p', only_these_start(p.r, runs + (p.curl,)), '/bin/zsh', '-f',
                          p.r.script, 'pass'],
                         extra_env={'RU_TEST_NOW': str(NOW), 'ACTIONS_LOG': p.r.sb.path('logs', 'actions.log')})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return p, res

    def test_a_due_pass_starts_only_what_it_may(self):
        p, res = self.due_pass(HOOK_RUNS)
        self.assertEqual(p.lines(res), [SWITCH])
        self.assertEqual(res.stderr, '')                 # no denied start
        self.assertEqual(actions_seen(p.r), [])          # no action stub reached
        self.assertEqual(p.urls(), [API + '/releases/latest',
                                    '%s/v%s/actions-runner-osx-arm64-%s.tar.gz' % (DL, V2, V2)])

    def test_control_an_action_at_the_would_switch_line_is_denied_and_seen(self):
        p, res = self.due_pass(HOOK_RUNS, plant=ABSOLUTE)
        self.assertEqual(res.stderr.count(DENIED % '/bin/launchctl'), 1, res.stderr)
        self.assertEqual(p.lines(res), [SWITCH])
        self.assertEqual(actions_seen(p.r), [])          # the stub never ran: the call was by its path

    def test_control_without_openssl_the_hook_does_not_switch(self):
        p, res = self.due_pass(tuple(x for x in HOOK_RUNS if x != '/usr/bin/openssl'))
        self.assertNotIn(SWITCH, p.lines(res))
        self.assertEqual(p.lines(res), [NOT + 'STOP the filtered CA bundle: no /usr/bin/openssl'])
        self.assertEqual(p.urls(), [])


# ---- LIVE: real GitHub through the real filter (the operator runs these)

LIVE = os.environ.get('RUNNER_UPDATER_LIVE_TLS') == '1'
LIVE_WHY = ('LIVE: reaches GitHub (its API and its download host) and a public eMudhra test host over the network; '
            'run with RUNNER_UPDATER_LIVE_TLS=1')
EMSIGN_PATH = 'https://dv-g3b-emudhra.we-have-a-problem.com/'   # its chain ends at emSign ECC Root CA - G3 (PLAN D2)


@unittest.skipUnless(LIVE, LIVE_WHY)
class TestLiveTLS(unittest.TestCase):
    """The real /usr/bin/curl through rl_curl: api.github.com gives 200 through the filtered bundle of the real system
    bundle and the real data file. A one-root bundle (ISRG Root X1, which does not chain api.github.com; RL_FLOOR 1 for
    this cell) gives curl exit 60 WITH OPENSSL_X509_TEA_DISABLE=1, and 200 WITHOUT it (the measured control: Apple's
    curl then falls back to the keychain). PLAN D2's emSign test path gives curl exit 60 through the filtered bundle of
    a source that holds its root (the real emSign ECC Root CA - G3, a fixture): the filter dropped it; the control,
    the same source with that root's key not excluded, reaches the host (any HTTP answer). The release tarball's host
    (a HEAD of a past darwin-arm64 asset, its redirect followed) gives 200. Run them on the Studio: the log does not
    say which host ran it."""

    def kit(self, source=None, text=None):
        k = Kit(self, source=source, rewrites=[('RL_FLOOR=100', 'RL_FLOOR=1')] if source else ())
        k.rewrites[0] = ('RL_CURL=/usr/bin/curl', 'RL_CURL=/usr/bin/curl')   # the real curl
        k.copy_release(text if text is not None else read_text(os.path.join(REPO, 'bin', 'runner-updater-release')))
        return k

    def get(self, k, url='https://api.github.com/', opts=''):
        r = k.run('code=$(rl_curl %s--max-time 30 -o /dev/null -w "%%{http_code}" %s); print -r -- "rc $? code $code"'
                  % (opts, url))
        return r.stdout.splitlines()[-1]

    def emsign_source(self):
        return read_text(SYSTEM_BUNDLE) + real_root('emsign-ecc-root-ca-g3.pem')

    def one_root(self):
        isrg = [p for p in system_pems() if spki_sha256(p) == ISRG_X1_SPKI]
        self.assertEqual(len(isrg), 1, 'ISRG Root X1 is not in %s' % SYSTEM_BUNDLE)
        return isrg[0]

    def test_api_github_com_through_the_filtered_bundle(self):
        self.assertEqual(self.get(self.kit()), 'rc 0 code 200')

    def test_a_one_root_bundle_gives_60_with_the_variable(self):
        self.assertTrue(self.get(self.kit(source=self.one_root())).startswith('rc 60 '))

    def test_control_the_same_bundle_without_the_variable_gives_200(self):
        text = read_text(os.path.join(REPO, 'bin', 'runner-updater-release')).replace(
            'OPENSSL_X509_TEA_DISABLE=1 $RL_CURL', '$RL_CURL')
        self.assertEqual(self.get(self.kit(source=self.one_root(), text=text)), 'rc 0 code 200')

    def test_the_emsign_test_path_gives_60_through_the_filtered_bundle(self):
        k = self.kit(source=self.emsign_source())
        self.assertTrue(self.get(k, EMSIGN_PATH).startswith('rc 60 '))
        self.assertNotIn(spki_sha256(real_root('emsign-ecc-root-ca-g3.pem')), k.keys())

    def test_control_the_emsign_test_path_with_its_root_kept_is_reached(self):
        k = self.kit(source=self.emsign_source())
        emsign = {h for h, name in read_data(DATA) if name == 'emSign ECC Root CA - G3'}
        self.assertEqual(len(emsign), 1)
        k.sb.write(k.data, ''.join(l for l in read_text(DATA).splitlines(True) if l.split(' ')[0] not in emsign))
        self.assertTrue(self.get(k, EMSIGN_PATH).startswith('rc 0 code '))
        self.assertIn(emsign.pop(), k.keys())

    def test_the_release_tarball_host_gives_200(self):
        url = '%s/v%s/actions-runner-osx-arm64-%s.tar.gz' % (DL, V0, V0)   # a past release, as rl_tarball asks it
        self.assertEqual(self.get(self.kit(), url, opts='-L --max-redirs 5 --head '), 'rc 0 code 200')


ISRG_X1_SPKI = '0b9fa5a59eed715c26c1020c711b4f6ec42d58b0015e14337a39dad301c5afc3'


if __name__ == '__main__':
    unittest.main()
