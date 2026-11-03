"""The trust of linux-docker/'s downloads (plan D2, TLS): ONE data file of excluded CA keys, setup/tls-excluded-spki,
and the filter in linux-docker/setup/runner-release.sh that builds the CA bundle each download uses.

- The data file: `#` lines are comments, empty lines are ignored, a data line is `<64 lowercase hex> <name>` (the hash
  of a certificate's DER SubjectPublicKeyInfo, ONE space, free text). A reader REFUSES the whole file on a data line
  whose first field is not 64 lowercase hex, a CR byte, a duplicate hash, or no data line: an empty list fails
  closed, it never means "nothing to exclude".
- bin/golden-emudhra still holds its own copy (its EXCLUDED_SPKI array): the two are pinned equal, both ways.
- The filter (rr_bundle) drops every certificate of the source bundle whose key the file names, keeps at least 100,
  and rebuilds the bundle when its source, the data file, the openssl or the bundle file itself changed.
The data-file and pin cells read text and run anywhere; the reader and filter cells run the copied bash in a container
(tests/hetzner/support.py).
"""
import os
import re
import shutil
import tempfile
import unittest

from tests.hetzner.support import REPO, FLOOR, Sandbox, needs_container, pems, pki, spki_sha256

DATA = os.path.join(REPO, 'setup', 'tls-excluded-spki')
EMUDHRA = os.path.join(REPO, 'bin', 'golden-emudhra')
HEX64 = re.compile(r'[0-9a-f]{64}')


def read_data(path):
    """The agreed reading, in Python: [(hash, name)], or ValueError naming why the whole file is refused."""
    with open(path, 'rb') as f:
        raw = f.read()
    if b'\r' in raw:
        raise ValueError('a CR byte')
    out = []
    for l in raw.decode().split('\n'):
        if l == '' or l.startswith('#'):
            continue
        h, _, name = l.partition(' ')    # field 1 is the text before the first space; the name is the rest
        if not HEX64.fullmatch(h):
            raise ValueError('a first field that is not 64 lowercase hex')
        if any(h == x for x, _ in out):
            raise ValueError('a duplicate hash')
        out.append((h, name))
    if not out:
        raise ValueError('no data line')
    return out


def read_emudhra(path):
    """golden-emudhra's EXCLUDED_SPKI=( … ) array: [(hash, name)], each line `  <hash>  # <name>`."""
    with open(path) as f:
        text = f.read()
    m = re.search(r'^EXCLUDED_SPKI=\(\n(.*?)^\)\n', text, re.M | re.S)
    if not m:
        raise ValueError('no EXCLUDED_SPKI=( … ) array')
    out = []
    for l in m.group(1).splitlines():
        mm = re.fullmatch(r'  ([0-9a-f]{64})  # (.+)', l)
        if not mm:
            raise ValueError('an array line of another shape: %r' % l)
        out.append((mm.group(1), mm.group(2)))
    return out


def compare(emudhra, data):
    """(in golden-emudhra but not in the file, in the file but not in golden-emudhra)."""
    a, b = read_emudhra(emudhra), read_data(data)
    return [x for x in a if x not in b], [x for x in b if x not in a]


class DataFile(unittest.TestCase):
    def test_the_release_file_is_read_by_the_agreed_rules(self):
        rows = read_data(DATA)
        self.assertEqual(len(rows), 3)
        for h, name in rows:
            self.assertRegex(h, r'^[0-9a-f]{64}$')
            self.assertTrue(name)
        with open(DATA) as f:
            self.assertIn('# homebrew-core a2ee7ae08c6, ca-certificates.rb, EXCLUDED_SPKI_HASHES', f.read())

    def test_golden_emudhra_holds_the_same_keys_both_ways(self):
        only_emudhra, only_file = compare(EMUDHRA, DATA)
        self.assertEqual(only_emudhra, [], 'bin/golden-emudhra excludes a key setup/tls-excluded-spki does not')
        self.assertEqual(only_file, [], 'setup/tls-excluded-spki excludes a key bin/golden-emudhra does not')

    def test_the_pin_sees_drift_in_each_direction(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with open(EMUDHRA) as f:
            em = f.read()
        with open(DATA) as f:
            data = f.read()
        h0, n0 = read_data(DATA)[0]
        line = '  %s  # %s\n' % (h0, n0)
        self.assertEqual(em.count(line), 1)
        with open(os.path.join(d, 'em'), 'w') as f:
            f.write(em.replace(line, ''))
        with open(os.path.join(d, 'data'), 'w') as f:
            f.write(data.replace('%s %s\n' % (h0, n0), ''))
        self.assertEqual(compare(os.path.join(d, 'em'), DATA), ([], [(h0, n0)]))
        self.assertEqual(compare(EMUDHRA, os.path.join(d, 'data')), ([(h0, n0)], []))
        self.assertEqual(compare(EMUDHRA, DATA), ([], []))   # the control: the real pair


@needs_container
class Reader(unittest.TestCase):
    def read(self, sb, path):
        return sb.lib('rr_excluded "$1"', path)

    def test_the_release_file_is_read_in_order(self):
        sb = Sandbox(self)
        r = self.read(sb, os.path.join(sb.build, 'setup', 'tls-excluded-spki'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), [h for h, _ in read_data(DATA)])

    def test_comments_empty_lines_and_free_names_are_read(self):
        sb = Sandbox(self)
        h1, h2 = 'a' * 64, 'b' * 64
        p = sb.excluded('# a comment', '', '#', h1 + ' a name with  two spaces, a # and a \\', '', h2)
        r = self.read(sb, p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), [h1, h2])

    def test_each_refusal_refuses_the_whole_file(self):
        good = 'c' * 64 + ' the good line'
        cases = {
            'a first field in upper case': ['A' * 64 + ' x', good],
            'a first field of 63 hex': ['c' * 63 + ' x', good],
            'a first field of 65 hex': ['c' * 65 + ' x', good],
            'a leading space': [' ' + good],
            'a tab after the hash': ['d' * 64 + '\tx', good],
            'a line of spaces': [good, '   '],
            'a duplicate hash': [good, 'c' * 64 + ' again'],
            'zero data lines (comments only)': ['# nothing excluded', ''],
            'zero data lines (an empty file)': [],
        }
        for why, lines in cases.items():
            with self.subTest(why):
                sb = Sandbox(self)
                r = self.read(sb, sb.excluded(*lines))
                self.assertNotEqual(r.returncode, 0, why)
                self.assertEqual(r.stdout, '', why)
                self.assertIn('REFUSE', r.stderr, why)
        for why, text in (('a CR byte in a data line', good + '\r\n'), ('a CR byte in a comment', '# x\r\n' + good + '\n')):
            with self.subTest(why):
                sb = Sandbox(self)
                p = sb.write(os.path.join(sb.build, 'setup', 'tls-excluded-spki'), text)
                r = self.read(sb, p)
                self.assertNotEqual(r.returncode, 0, why)
                self.assertEqual(r.stdout, '', why)
                self.assertIn('REFUSE', r.stderr, why)
        sb = Sandbox(self)   # the control: the same good line alone is read
        r = self.read(sb, sb.excluded(good))
        self.assertEqual((r.returncode, r.stdout), (0, 'c' * 64 + '\n'), r.stderr)


@needs_container
class Filter(unittest.TestCase):
    def bundle(self, sb):
        r = sb.lib('rr_bundle && printf "%s\\n%s\\n" "$RR_BUNDLE" "$RR_CAPATH"')
        return r, (r.stdout.splitlines()[-2:] if r.returncode == 0 else None)

    def keys(self, path):
        with open(path) as f:
            return [spki_sha256(p) for p in pems(f.read())]

    def test_an_excluded_key_is_dropped_and_the_rest_kept(self):
        sb = Sandbox(self)
        sb.excluded(pki().ca_spki + ' liveapp test ca')
        r, paths = self.bundle(sb)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = self.keys(paths[0])
        self.assertNotIn(pki().ca_spki, got)
        want = [spki_sha256(p) for p in pems(sb.system_bundle)]
        self.assertEqual(got, want)                    # every other certificate, in the source's order
        self.assertGreaterEqual(len(got), FLOOR)
        self.assertEqual(os.listdir(paths[1]), [])     # the CA path curl gets is an empty folder

    def test_a_list_that_excludes_a_different_key_keeps_the_certificate(self):
        sb = Sandbox(self)
        sb.excluded(pki().other_spki + ' liveapp test other')
        r, paths = self.bundle(sb)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = self.keys(paths[0])
        self.assertIn(pki().ca_spki, got)
        self.assertEqual(len(got), len(pems(sb.system_bundle)) + 1)

    def test_the_release_file_on_this_system_bundle(self):
        sb = Sandbox(self)
        r, paths = self.bundle(sb)
        self.assertEqual(r.returncode, 0, r.stderr)
        excluded = {h for h, _ in read_data(DATA)}
        want = [k for k in (spki_sha256(p) for p in pems(sb.system_bundle + pki().ca_pem)) if k not in excluded]
        self.assertEqual(self.keys(paths[0]), want)
        self.assertGreaterEqual(len(want), FLOOR)

    def test_fewer_than_100_kept_refuses(self):
        for n, ok in ((FLOOR - 1, False), (FLOOR, True)):
            with self.subTest(kept=n):
                sb = Sandbox(self)
                sb.write(sb.path('source.pem'), ''.join(pems(sb.system_bundle)[:n]))
                sb.excluded(pki().other_spki + ' x')
                r, paths = self.bundle(sb)
                if ok:
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertEqual(len(self.keys(paths[0])), n)
                else:
                    self.assertNotEqual(r.returncode, 0)
                    self.assertIn('REFUSE', r.stderr)
                    self.assertFalse(os.path.exists(os.path.join(sb.home, '.cache/liveapp-ci/tls/bundle.pem')))

    def test_a_certificate_openssl_cannot_read_refuses(self):
        for bad, ok in (('-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n', False), ('', True)):
            with self.subTest(bad=bool(bad)):
                sb = Sandbox(self)
                sb.write(sb.path('source.pem'), sb.system_bundle + bad + pki().ca_pem)
                r, _ = self.bundle(sb)
                self.assertEqual(r.returncode == 0, ok, r.stderr)
                if not ok:
                    self.assertIn('REFUSE', r.stderr)

    def test_a_ca_path_folder_that_is_not_empty_refuses(self):
        for planted, ok in ((True, False), (False, True)):
            with self.subTest(planted=planted):
                sb = Sandbox(self)
                cap = os.path.join(sb.home, '.cache', 'liveapp-ci', 'tls', 'capath')
                os.makedirs(cap)
                if planted:
                    sb.write(os.path.join(cap, 'deadbeef.0'), pki().ca_pem)
                r, _ = self.bundle(sb)
                self.assertEqual(r.returncode == 0, ok, r.stderr)

    def test_zero_data_lines_builds_no_bundle(self):
        sb = Sandbox(self)
        sb.excluded('# nothing')
        r, _ = self.bundle(sb)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('REFUSE', r.stderr)
        self.assertFalse(os.path.exists(os.path.join(sb.home, '.cache/liveapp-ci/tls/bundle.pem')))

    def test_the_bundle_is_rebuilt_only_when_an_input_or_the_bundle_changed(self):
        def ino(p):
            return os.stat(p).st_ino

        def changes(name, change):
            sb = Sandbox(self)
            r, paths = self.bundle(sb)
            self.assertEqual(r.returncode, 0, r.stderr)
            before = ino(paths[0])
            change(sb, paths[0])
            r, paths2 = self.bundle(sb)
            self.assertEqual(r.returncode, 0, r.stderr)
            return before != ino(paths2[0]), paths2[0], sb

        def nothing(sb, b):
            pass

        def source(sb, b):
            with open(sb.path('source.pem'), 'a') as f:
                f.write(pki().other_pem)

        def data(sb, b):
            with open(os.path.join(sb.build, 'setup', 'tls-excluded-spki'), 'a') as f:
                f.write('e' * 64 + ' one more\n')

        def tamper(sb, b):
            with open(b, 'a') as f:
                f.write(pki().other_pem)

        rebuilt, _, _ = changes('nothing', nothing)
        self.assertFalse(rebuilt, 'the same inputs rebuilt the bundle')        # the control
        rebuilt, b, _ = changes('source', source)
        self.assertTrue(rebuilt, 'a changed source did not rebuild the bundle')
        self.assertIn(pki().other_spki, self.keys(b))
        rebuilt, _, _ = changes('data', data)
        self.assertTrue(rebuilt, 'a changed data file did not rebuild the bundle')
        rebuilt, b, _ = changes('tamper', tamper)
        self.assertTrue(rebuilt, 'a bundle changed by hand was used as it was')
        self.assertNotIn(pki().other_spki, self.keys(b))


if __name__ == '__main__':
    unittest.main()
