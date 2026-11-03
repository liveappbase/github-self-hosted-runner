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

from tests.studio.test_runner_updater import Rig, config
from tests.studio.test_runner_updater_state import Paths, on_state

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


if __name__ == '__main__':
    unittest.main()
