"""bin/runner-updater's STATE slice: its own PATH, the config keys that would blind the log pass, the updater's state
(STATEDIR/state.json), `status`, `on` and `off`, the protected-list writer and `protect`, and the timer's `pass`.

The rig is test_runner_updater's (every path constant rewritten into a sandbox; stubs for ps and curl; the real core).
"""
import json
import os
import unittest

from tests.studio.test_runner_updater import Rig, config

SYSTEM = '/usr/bin:/bin:/usr/sbin:/sbin'


def lines_of(path):
    with open(path) as f:
        return f.read().splitlines()


class TestOwnPath(unittest.TestCase):
    """runner-updater sets its own PATH at the top: the weekly watchdog runs it over a non-interactive ssh with a PATH
    of its own, so nothing may depend on the caller's. The ps stub logs the PATH it is run with."""

    def test_report_works_with_a_path_that_holds_nothing(self):
        r = Rig(self)
        r.report(env={'PATH': '/nonexistent'})
        self.assertEqual(set(lines_of(os.path.join(r.psd, 'path'))), {r.sb.stubs + ':' + SYSTEM})

    def test_control_a_copy_that_sets_no_path_shows_the_callers(self):
        r = Rig(self)
        own = 'export PATH=%s:%s' % (r.sb.stubs, SYSTEM)
        script = r.copy('runner-updater-nopath', [(own, ': ' + own)])
        r.cmd('report', script=script, env={'PATH': '/nonexistent'})
        self.assertEqual(set(lines_of(os.path.join(r.psd, 'path'))), {'/nonexistent'})


LOG_FILE = (' line 5: a top-level log-file key: runscaler then writes its log elsewhere or nowhere, and runner.log beside '
            'the config reads as a quiet, continuous log, so R1 would be blind while the facts look normal; remove the key')
LOG_FORMAT = (' line 5: log-format is not "text": runscaler then writes records that the core\'s log reader ignores, so R1 '
              'would be blind while the facts look normal; set log-format = "text" or remove the line')


class TestLogKeys(unittest.TestCase):
    """A config whose log the core cannot read is no facts (S3b-1 review r1 P3-1): a top-level log-file key (runscaler
    then writes elsewhere, or nowhere with ""), or a log-format other than "text" (json records the core ignores)."""

    def refused(self, top, why):
        r = Rig(self, cfg=config(top=top))
        res = r.report(ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: REFUSE no facts: %s%s\n' % (r.config, why), res.stdout)
        self.assertFalse(os.path.exists(os.path.join(r.pass_dir, 'facts.json')))
        self.assertFalse(os.path.exists(os.path.join(r.pass_dir, 'idle.json')))
        return r

    def test_a_top_level_log_file_is_refused(self):
        for line in ('log-file = "/var/log/runscaler.log"', 'log-file = ""', '"log-file" = "x"', "log-file='x'",
                     'log-file.x = 1'):
            with self.subTest(line=line):
                self.refused(line + '\n', LOG_FILE)

    def test_a_log_format_other_than_text_is_refused(self):
        for line in ('log-format = "json"', 'log-format = ""', "log-format = 'text'", '"log-format" = "text"',
                     'log-format = "text" x'):
            with self.subTest(line=line):
                self.refused(line + '\n', LOG_FORMAT)

    def test_control_log_format_text_and_a_log_file_key_in_a_table(self):
        for cfg in (config(top='log-format = "text"\n'), config(top='log-format = "text"   # the default\n'),
                    config().replace('[tart]\n', '[tart]\nlog-file = "x"\n')):
            with self.subTest(cfg=cfg[:200]):
                r = Rig(self, cfg=cfg)
                r.report()
                self.assertEqual(r.facts()['format'], 1)


if __name__ == '__main__':
    unittest.main()
