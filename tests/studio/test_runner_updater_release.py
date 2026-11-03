"""The release half of the runner-image updater on the Studio (S3b-2b): bin/runner-updater-release (which release a
family may switch to: the TLS filter, the release checks, the recipe, REJECTED, the pass hook), bin/tls-excluded-lib
(the ONE Mac reader of setup/tls-excluded-spki, which golden-emudhra and the filter source), and the warm-pool read of
bin/runner-updater-lib (a pool-size KEY only).

The pass cells run bin/runner-updater in test_runner_updater's Rig (every path constant rewritten into a sandbox). The
function cells source a copy of the file under test in a small zsh driver. GitHub is a curl stub (no network): it logs
each call (its argv and the OPENSSL_X509_TEA_DISABLE it saw) and answers from files. The TLS filter runs the real
/usr/bin/openssl on the real /etc/ssl/cert.pem plus test certificates this file makes. The LIVE cells reach GitHub:
they skip unless RUNNER_UPDATER_LIVE_TLS=1.
"""
import os
import unittest

from tests.hetzner.test_tls import read_data
from tests.studio.support_emudhra import (EXCLUDED_LINE, GUEST_W, data_keys, emudhra_copy, guest_text, scenario,
                                          write as ewrite)
from tests.studio.support import REPO, Sandbox
from tests.studio.test_runner_updater import Rig, config
from tests.studio.test_runner_updater_state import Paths, on_state

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


if __name__ == '__main__':
    unittest.main()
