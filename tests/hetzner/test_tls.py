"""The trust of linux-docker/'s downloads (plan D2, TLS): ONE data file of excluded CA keys, setup/tls-excluded-spki,
and the filter in linux-docker/setup/runner-release.sh that builds the CA bundle each download uses.

- The data file: `#` lines are comments, empty lines are ignored, a data line is `<64 lowercase hex> <name>` (the hash
  of a certificate's DER SubjectPublicKeyInfo, ONE space, free text). A reader REFUSES the whole file on a data line
  whose first field is not 64 lowercase hex, a CR byte, a duplicate hash, or no data line: an empty list fails
  closed, it never means "nothing to exclude".
- bin/golden-emudhra holds no copy of the keys: its host part reads the file (bin/tls-excluded-lib, the one Mac reader)
  and fills its guest part's EXCLUDED_SPKI line with them. The pin cell reads its text; tests/studio/
  test_runner_updater_release.py runs it (TestGoldenEmudhraKeys) and runs the Mac reader on this file's cases.
- The filter (rr_bundle) drops every certificate of the source bundle whose key the file names, keeps at least 100,
  and rebuilds the bundle when its source, the data file, the openssl, the filter's own code, its floor or the bundle
  file itself changed. Every download (rr_curl) runs it first, so a bundle another filter left in ~/.cache is rebuilt.
  It reads each input the stamp names ONCE, so the stamp names the bytes the bundle was made from even when a file is
  replaced while it runs.
The data-file and pin cells read text and run anywhere; the reader and filter cells run the copied bash in a container
(tests/hetzner/support.py).
"""
import hashlib
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


def emudhra_pin(text):
    """What breaks the pin "golden-emudhra READS setup/tls-excluded-spki and holds no key of its own" in TEXT (its
    source): a list of findings, [] when it holds. Its one EXCLUDED_SPKI array holds only the placeholder the host part
    fills; no key of the data file is anywhere in it; its host part names the file once and reads it once."""
    found = []
    arrays = re.findall(r'^EXCLUDED_SPKI=\((.*?)\)', text, re.M | re.S)
    if arrays != ['@EXCLUDED_SPKI@']:
        found.append('its EXCLUDED_SPKI arrays are %r, not the one placeholder the host fills' % arrays)
    found += ['it holds the key %s: the data file is the one copy' % h for h, _ in read_data(DATA) if h in text]
    if len(re.findall(r'^EXCLUDED=\$\{0:A:h:h\}/setup/tls-excluded-spki(?= |$)', text, re.M)) != 1:
        found.append('it does not name setup/tls-excluded-spki once (EXCLUDED=${0:A:h:h}/setup/tls-excluded-spki)')
    if len(re.findall(r'^tls_excluded \$EXCLUDED \|\| die ', text, re.M)) != 1:
        found.append('it does not read the file once (tls_excluded $EXCLUDED || die ...)')
    return found


# THE PINNED COPIES of the keys (Opus r1 P3-3). Each runs where it cannot read the data file, so it carries the keys,
# and the cells below pin each one equal to the data file, both ways:
#   setup/emudhra-deny.sh, setup/emudhra-undeny.sh: root runs each one from a copy whose sha256 a person reviewed
#     (setup/02-wall.run-line), and the undeny also runs in a build VM's guest: a second file read at run time would be
#     bytes no one reviewed (a file ci can write, read by root).
#   examples/emudhra-check.yml: copied into another repository's .github/workflows/, where this repository is not.
KEY_COPIES = ('setup/emudhra-deny.sh', 'setup/emudhra-undeny.sh', 'examples/emudhra-check.yml')


def read_rel(rel):
    with open(os.path.join(REPO, rel)) as f:
        return f.read()


def copy_keys(text):
    """the words of TEXT's one EXCLUDED_SPKI array, in order (its # comments dropped); ValueError when TEXT does not
    assign EXCLUDED_SPKI exactly once, as one array"""
    if len(re.findall(r'EXCLUDED_SPKI\+?=', text)) != 1:
        raise ValueError('it does not assign EXCLUDED_SPKI exactly once')
    arrays = re.findall(r'(?m)^[ \t]*EXCLUDED_SPKI=\(([^)]*)\)', text)
    if len(arrays) != 1:
        raise ValueError('it has no EXCLUDED_SPKI=( ... ) array')
    return re.sub(r'#[^\n]*', '', arrays[0]).split()


def copy_pin(text, data):
    """what breaks the pin "the copy's keys are the keys DATA (the data file's), both ways" in TEXT: [] when it holds"""
    try:
        keys = copy_keys(text)
    except ValueError as e:
        return [str(e)]
    found = ['%r is not a key' % h for h in keys if not HEX64.fullmatch(h)]
    found += ['it names the key %s twice' % h for h in sorted(set(keys)) if keys.count(h) > 1]
    found += ["it lacks the data file's key %s" % h for h in data if h not in keys]
    found += ['it holds the key %s, which the data file does not' % h for h in keys if h not in data]
    return found


class DataFile(unittest.TestCase):
    def test_the_release_file_is_read_by_the_agreed_rules(self):
        rows = read_data(DATA)
        self.assertEqual(len(rows), 3)
        for h, name in rows:
            self.assertRegex(h, r'^[0-9a-f]{64}$')
            self.assertTrue(name)
        with open(DATA) as f:
            self.assertIn('# homebrew-core a2ee7ae08c6, ca-certificates.rb, EXCLUDED_SPKI_HASHES', f.read())

    def test_golden_emudhra_reads_the_file_and_holds_no_key(self):
        with open(EMUDHRA) as f:
            self.assertEqual(emudhra_pin(f.read()), [])

    def test_the_pin_sees_a_key_copied_back_or_the_read_dropped(self):
        with open(EMUDHRA) as f:
            em = f.read()
        h0, n0 = read_data(DATA)[0]
        broken = {
            'a key back in the array': em.replace('EXCLUDED_SPKI=(@EXCLUDED_SPKI@)', 'EXCLUDED_SPKI=(\n  %s  # %s\n)' % (h0, n0)),
            'a key in a comment': em.replace('\nset -u\n', '\n# %s\nset -u\n' % h0, 1),
            'a second array': em.replace('\nset -u\n', '\nset -u\nEXCLUDED_SPKI=(%s)\n' % h0, 1),
            'the read dropped': re.sub(r'(?m)^tls_excluded \$EXCLUDED \|\| die .*\n', '', em),
            'another file named': em.replace('EXCLUDED=${0:A:h:h}/setup/tls-excluded-spki',
                                             'EXCLUDED=${0:A:h:h}/setup/other-spki'),
        }
        for why, text in broken.items():
            with self.subTest(why):
                self.assertNotEqual(text, em, why)
                self.assertNotEqual(emudhra_pin(text), [], why)
        self.assertEqual(emudhra_pin(em), [])   # the control: the real file

    def test_each_pinned_copy_holds_the_data_files_keys(self):
        data = [h for h, _ in read_data(DATA)]
        for rel in KEY_COPIES:
            with self.subTest(rel):
                text = read_rel(rel)
                self.assertEqual(copy_pin(text, data), [])
                self.assertEqual(sorted(copy_keys(text)), sorted(data))
                for h in data:   # each key once, in its array: no other place of the copy names it
                    self.assertEqual(text.count(h), 1, h)

    def test_the_copy_pin_sees_drift_both_ways(self):
        data = [h for h, _ in read_data(DATA)]
        new = 'e' * 64
        for rel in KEY_COPIES:
            text = read_rel(rel)
            drifts = {
                'a key added to the data file only': (text, data + [new]),
                'a key dropped from the data file only': (text, data[1:]),
                'a key added to the copy only': (text.replace(data[0], '%s %s' % (data[0], new), 1), data),
                'a key dropped from the copy only': (text.replace(data[-1], '', 1), data),
                'a key named twice in the copy': (text.replace(data[0], '%s %s' % (data[0], data[0]), 1), data),
                'a second array': (text + '\nEXCLUDED_SPKI=(%s)\n' % new, data),
                'a key appended later': (text + '\nEXCLUDED_SPKI+=(%s)\n' % new, data),
            }
            for why, (t, d) in drifts.items():
                with self.subTest(rel, drift=why):
                    self.assertNotEqual(copy_pin(t, d), [], why)
            self.assertEqual(copy_pin(text, data), [], rel)   # the control: the copy as it is

    def test_no_other_file_holds_a_key(self):
        """the class, not the instance: a file of the tree that names a key of the data file is the data file or one of
        KEY_COPIES (a new copy must be added there, and so pinned)"""
        keys = [h.encode() for h, _ in read_data(DATA)]
        holders = []
        for top, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__')]
            for f in files:
                p = os.path.join(top, f)
                with open(p, 'rb') as fh:
                    raw = fh.read()
                if any(k in raw for k in keys):
                    holders.append(os.path.relpath(p, REPO))
        self.assertEqual(sorted(holders), sorted(('setup/tls-excluded-spki',) + KEY_COPIES))


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
    def bundle(self, sb, source='runner-release.sh', first=''):
        r = sb.lib(first + 'rr_bundle && printf "%s\\n%s\\n" "$RR_BUNDLE" "$RR_CAPATH"', source=source)
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

    def test_a_bundle_made_by_another_filter_is_rebuilt_before_a_download(self):
        """A bundle and its stamp left in ~/.cache by ANOTHER version of the filter (here one that keeps every
        certificate), with the same source, data file and openssl: this filter rebuilds it before the download, so the
        excluded CA is dropped and no request reaches the server. The control: this filter's own bundle is kept."""
        for other in (True, False):
            with self.subTest(other=other):
                sb = Sandbox(self)
                url = sb.gh.base + '/repos/actions/runner/releases/latest'
                sb.excluded(pki().ca_spki + ' the test CA (it signs the local GitHub)')
                rr = os.path.join(sb.build, 'setup', 'runner-release.sh')
                with open(rr) as f:
                    text = f.read()
                keep = text.replace("        *$'\\n'$h$'\\n'*) dropped=$((dropped + 1)) ;;",
                                    "        KEEP-EVERY-CERTIFICATE) dropped=$((dropped + 1)) ;;")
                self.assertNotEqual(keep, text)
                sb.write(os.path.join(sb.build, 'setup', 'rr-other.sh'), keep)
                r, paths = self.bundle(sb, source='rr-other.sh' if other else 'runner-release.sh')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(pki().ca_spki in self.keys(paths[0]), other)
                ino = os.stat(paths[0]).st_ino
                r = sb.lib('rr_curl -o /dev/null -w "%{http_code}" "$1"; echo " curl-rc=$?"', url)
                self.assertTrue(r.stdout.endswith(' curl-rc=60\n'), r.stdout + r.stderr)   # TLS refused
                self.assertEqual(sb.gh.seen, [])
                self.assertEqual(os.stat(paths[0]).st_ino != ino, other, 'rebuilt' if other else 'kept')
                self.assertNotIn(pki().ca_spki, self.keys(paths[0]))

    SWAP = '''#!/bin/sh
# sha256sum, for one cell: at its Kth call (counted in hook.n) it writes inject over TARGET (the same file, as `cat >`
# writes it), then runs the real sha256sum
n=$(( $(cat @ROOT@/hook.n 2>/dev/null || echo 0) + 1 )); echo "$n" > @ROOT@/hook.n
[ "$n" != @K@ ] || cat @ROOT@/inject > @TARGET@
exec /usr/bin/sha256sum "$@"
'''

    def made_from(self, sb, versions):
        """The stamp names one version of each input, and the bundle is exactly that source less that data file's
        keys: (the source, the data file) it names."""
        tls = os.path.join(sb.home, '.cache', 'liveapp-ci', 'tls')
        with open(os.path.join(tls, 'stamp')) as f:
            stamp = dict(l.split(' ', 1) for l in f.read().splitlines())
        named = {}
        for key, name in (('source', 'source'), ('excluded', 'data')):
            m = [x for x in versions[name] if hashlib.sha256(x.encode()).hexdigest() == stamp[key]]
            self.assertEqual(len(m), 1, 'the stamp names %s bytes that were never there' % name)
            named[name] = m[0]
        excluded = {l.split(' ', 1)[0] for l in named['data'].splitlines() if l and not l.startswith('#')}
        want = [k for k in (spki_sha256(p) for p in pems(named['source'])) if k not in excluded]
        self.assertEqual(self.keys(os.path.join(tls, 'bundle.pem')), want,
                         'the bundle is not what the stamp names: made from other bytes than it hashed')
        return named['source'], named['data']

    def test_an_input_replaced_during_the_check_is_never_trusted_under_a_stamp_of_other_bytes(self):
        """Each input the stamp names (the data file, the source) is read ONCE: the filter and the stamp use that one
        read. The hook: a sha256sum substitute that writes a new version of one input over it at its Kth call of the
        first rr_bundle (K 1-3: the calls that fall between two reads of a path). The new data file also excludes the
        test CA that signs the local GitHub; the new source holds one more CA. Then the stamp names the bytes the bundle
        was made from, and the next download (no hook) refuses the CA the data file now excludes: curl exit 60, no
        request. Controls: no replacement -> the next check keeps the bundle (same inode); the new data file in place
        from the start -> curl exit 60."""
        url = '/repos/actions/runner/releases/latest'

        def run(target, k=0, start=False):
            sb = Sandbox(self)
            paths = {'data': os.path.join(sb.build, 'setup', 'tls-excluded-spki'), 'source': sb.path('source.pem')}
            versions = {}
            for name, p in paths.items():
                with open(p) as f:
                    versions[name] = [f.read()]
            new = {'data': versions['data'][0] + pki().ca_spki + ' the test CA (it signs the local GitHub)\n',
                   'source': versions['source'][0] + pki().other_pem}
            if target:
                versions[target].append(new[target])
            if start:
                sb.write(paths[target], new[target])
            elif target:
                sb.write(sb.path('inject'), new[target])
                sb.write(sb.path('stubs', 'sha256sum'), self.SWAP.replace('@ROOT@', sb.root).replace(
                    '@K@', str(k)).replace('@TARGET@', paths[target]), 0o755)
            r = sb.lib('rr_bundle')
            if os.path.exists(sb.path('stubs', 'sha256sum')):
                os.remove(sb.path('stubs', 'sha256sum'))
                with open(paths[target]) as f:          # the hook ran: the input is the new version now
                    self.assertEqual(f.read(), new[target], 'the hook did not replace the %s' % target)
            bundle = os.path.join(sb.home, '.cache', 'liveapp-ci', 'tls', 'bundle.pem')
            if r.returncode == 0:
                self.made_from(sb, versions)
                ino = os.stat(bundle).st_ino
            else:                                          # it may refuse: then there is no bundle
                self.assertFalse(os.path.exists(bundle), r.stdout + r.stderr)
                ino = None
            r2 = sb.lib('rr_curl -o /dev/null -w "%{http_code}" "$1"; echo " curl-rc=$?"', sb.gh.base + url)
            return sb, versions, new, r2, ino, (os.stat(bundle).st_ino if os.path.exists(bundle) else None)

        for target in ('data', 'source'):
            for k in (1, 2, 3):
                with self.subTest(replaced=target, at_call=k):
                    sb, versions, new, r2, ino, ino2 = run(target, k)
                    source, data = self.made_from(sb, versions)      # the next check: the stamp names what is there
                    self.assertEqual((source, data), (new[target], versions['data'][0]) if target == 'source'
                                     else (versions['source'][0], new[target]))
                    if target == 'data':
                        self.assertTrue(r2.stdout.endswith(' curl-rc=60\n'), r2.stdout + r2.stderr)
                        self.assertEqual(sb.gh.seen, [])
                    else:
                        self.assertTrue(r2.stdout.endswith(' curl-rc=0\n'), r2.stdout + r2.stderr)
        with self.subTest('the control: no replacement'):
            sb, versions, new, r2, ino, ino2 = run(None)
            self.assertIn('is current', r2.stderr)
            self.assertEqual(ino2, ino)
            self.assertTrue(r2.stdout.endswith(' curl-rc=0\n'), r2.stdout + r2.stderr)
            self.assertEqual(sb.gh.seen, [url])
        with self.subTest('the control: the new data file from the start'):
            sb, versions, new, r2, ino, ino2 = run('data', start=True)
            self.assertTrue(r2.stdout.endswith(' curl-rc=60\n'), r2.stdout + r2.stderr)
            self.assertEqual(sb.gh.seen, [])

    def test_a_refusal_names_the_data_file_never_the_private_copy(self):
        """rr_bundle parses a private copy of the data file (in a .new.* folder it removes): a REFUSE about the file
        names ~/build/setup/tls-excluded-spki, the file a person can fix. The control: the good file refuses nothing."""
        for why, lines, ok in (('a bad first field', ['NOT-HEX a line'], False), ('no data line', ['# none'], False),
                               ('a duplicate', ['c' * 64 + ' a', 'c' * 64 + ' b'], False),
                               ('the control: a good file', ['c' * 64 + ' a'], True)):
            with self.subTest(why):
                sb = Sandbox(self)
                data = sb.excluded(*lines)
                r, _ = self.bundle(sb)
                self.assertEqual(r.returncode == 0, ok, r.stderr)
                self.assertNotIn('/.new.', r.stdout + r.stderr)
                if not ok:
                    refuse = [l for l in r.stderr.splitlines() if 'REFUSE' in l]
                    self.assertEqual(len(refuse), 1, r.stderr)
                    self.assertIn('REFUSE ' + data, refuse[0])

    def test_the_tls_folder_holds_only_the_bundle_its_ca_path_and_stamp_after_every_check(self):
        """After a check that builds, one that finds the bundle current, and one that refuses (a bad data file, then a
        source under the floor), the folder holds bundle.pem, capath and stamp and nothing else (no .new.* folder);
        a refusal on a fresh home leaves capath alone."""
        def tls(sb):
            return sorted(os.listdir(os.path.join(sb.home, '.cache', 'liveapp-ci', 'tls')))
        three = ['bundle.pem', 'capath', 'stamp']
        sb = Sandbox(self)
        r, _ = self.bundle(sb)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(tls(sb), three, 'after a build')
        r, _ = self.bundle(sb)
        self.assertIn('is current', r.stdout)
        self.assertEqual(tls(sb), three, 'after a check that found the bundle current')
        good = os.path.join(sb.build, 'setup', 'tls-excluded-spki')
        with open(good) as f:
            keep = f.read()
        sb.excluded('NOT-HEX a line')
        r, _ = self.bundle(sb)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(tls(sb), three, 'after a refusal of the data file')
        sb.write(good, keep)
        sb.write(sb.path('source.pem'), ''.join(pems(sb.system_bundle)[:FLOOR - 1]))
        r, _ = self.bundle(sb)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(tls(sb), three, 'after a refusal under the floor')
        fresh = Sandbox(self)
        fresh.excluded('NOT-HEX a line')
        r, _ = self.bundle(fresh)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(tls(fresh), ['capath'], 'after a refusal on a fresh home')

    def test_a_bundle_made_under_a_lower_floor_is_rebuilt(self):
        """The floor is part of what made a bundle: one made with RR_FLOOR 50 from 99 certificates is not current for
        a filter whose floor is 100, which refuses it. The control: the same floor again keeps it."""
        for floor, ok in (('', False), ('RR_FLOOR=50; ', True)):
            with self.subTest(second=floor or 'RR_FLOOR %d' % FLOOR):
                sb = Sandbox(self)
                sb.write(sb.path('source.pem'), ''.join(pems(sb.system_bundle)[:FLOOR - 1]))
                sb.excluded(pki().other_spki + ' x')
                r, paths = self.bundle(sb, first='RR_FLOOR=50; ')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(len(self.keys(paths[0])), FLOOR - 1)
                ino = os.stat(paths[0]).st_ino
                r, _ = self.bundle(sb, first=floor)
                if ok:
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertIn('is current', r.stdout)
                    self.assertEqual(os.stat(paths[0]).st_ino, ino)
                else:
                    self.assertNotEqual(r.returncode, 0, r.stdout)
                    self.assertIn('REFUSE only %d certificates' % (FLOOR - 1), r.stderr)


if __name__ == '__main__':
    unittest.main()
