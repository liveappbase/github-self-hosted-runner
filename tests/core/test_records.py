"""The core tests build their log records with corejq.charm(); this pins it to runscaler's real output, byte for byte:
lines of fixtures/hz-cut.log and fixtures/studio-cut.log (real logs, host values replaced), a quoted value with
escaped quotes, an empty value, and the Studio's multi-line start failure. So a record a test builds is a record the
host writes.

V012Records pins the 5-wide level column of runscaler 0.10.0 and later to REAL lines: fixtures/v012-validate.log is
the record lines of one `runner validate --config` of the released v0.12.0 binary (runner-darwin-arm64.tar.gz, sha256
563f26ba…7011eeb; its `runner` member f9c35365…bda4e5), run offline on the Mac (HTTPS_PROXY and HTTP_PROXY at a
refusing local port, NO_PROXY empty, HOME a temp folder, a tart stub first on PATH, sandbox-exec denying every outbound
connection but localhost) on config/config.toml.example with neutral names and a log-file line, with a dummy
RUNNER_TOKEN_OWNER; the cleaning step replaced only the proxy's port (with 9). They are global records (no set): the
set-prefixed shape is from source only (charm log v2.0.1; corejq.to_v012)."""
import unittest

from tests.core.corejq import charm, fixture, to_v012
from tests.core.test_logfmt import tok


def lines(name, first, count):
    return ''.join(l + '\n' for l in fixture(name).split('\n')[first - 1:first - 1 + count])


class Records(unittest.TestCase):
    def test_global_record_with_a_quoted_value(self):
        self.assertEqual(charm('2026-10-22 15:35:22', 'INFO', None,
                               'Service stop timeout may predate drain support; reinstall the service so restarts can '
                               'wait for in-flight jobs',
                               [('serviceManager', 'systemd'), ('drainTimeout', '1h10m0s'),
                                ('action', 'runner service uninstall, then runner service install')]),
                         lines('hz-cut.log', 1, 1))

    def test_runner_removed_job_completed(self):
        self.assertEqual(charm('2026-10-25 19:37:04', 'INFO', 'linux-a', 'Runner removed',
                               [('name', 'runner-8b9b64ca'),
                                ('instanceID', '83dafc48f06300def867a2ec646706471919d09e0c2adc3daff363a7771169d1'),
                                ('reason', 'job-completed'), ('jobId', '2ce18645-b726-290f-1564-ea0902058718'),
                                ('repo', 'example-org/example'), ('workflowRunId', '15885850636'),
                                ('job', 'build (9150)'), ('result', 'failed')]),
                         lines('hz-cut.log', 35, 1))

    def test_escaped_quotes(self):
        self.assertEqual(charm('2026-10-22 15:35:52', 'ERRO', 'linux-p', 'request failed',
                               [('error', 'Get "https://broker.actions.githubusercontent.com/scalesets/message": '
                                          'context canceled'),
                                ('method', 'GET'), ('url', 'https://broker.actions.githubusercontent.com/scalesets/message')]),
                         lines('hz-cut.log', 16, 1))

    def test_empty_value(self):
        self.assertEqual(charm('2026-10-26 21:05:48', 'WARN', 'mac-a', 'Job completed for unknown runner (already removed?)',
                               [('runnerName', '')]),
                         lines('studio-cut.log', 30, 1))

    def test_studio_multi_line_start_failure(self):
        err = ("failed to start runner: runner process exited on runner-e2ddacdc right after connecting to GitHub; "
               "runner log:\n√ Connected to GitHub\n\nCurrent runner version: '2.338.0'\n"
               "2026-10-26 21:10:46Z: Listening for Jobs\n"
               "The runner no longer exists on the server. Cleaning up local configuration.\n"
               "√ Removed .credentials\n√ Removed .runner\n"
               "Runner listener exit with 0 return code, stop the service, no retry needed.\nExiting runner...")
        self.assertEqual(charm('2026-10-26 21:10:53', 'ERRO', 'mac-a', 'Failed to start runner, will retry',
                               [('error', err)]),
                         lines('studio-cut.log', 44, 12))


V012_URL = 'https://api.github.com/repos/example-org/example/actions/runners/registration-token'
V012 = [   # fixtures/v012-validate.log, line by line: (the level in the 0.9.x column, the message, the attributes)
    ('INFO', 'refreshing token', [('githubConfigUrl', 'https://github.com/example-org/example')]),
    ('INFO', 'getting runner registration token', [('registrationTokenURL', V012_URL)]),
] + [('ERRO', 'request failed', [('error', 'Post "%s": proxyconnect tcp: dial tcp 127.0.0.1:9: connect: connection '
                                           'refused' % V012_URL), ('method', 'POST'), ('url', V012_URL)])] * 4


class V012Records(unittest.TestCase):
    def lines(self):
        ls = fixture('v012-validate.log').split('\n')
        self.assertEqual(ls[-1], '')
        self.assertEqual(len(ls) - 1, len(V012))
        return [l + '\n' for l in ls[:-1]]

    def test_real_v012_lines_are_charm_in_the_5_wide_column_and_to_v012_of_the_4_letter_one(self):
        # it pins the synthesizer and the harness to real lines: a to_v012 that writes another column turns it red
        for line, (lvl, msg, attrs) in zip(self.lines(), V012):
            with self.subTest(line=line[:60]):
                t = line[:19]
                self.assertEqual(charm(t, {'INFO': 'INFO ', 'ERRO': 'ERROR'}[lvl], None, msg, attrs), line)
                self.assertEqual(to_v012(charm(t, lvl, None, msg, attrs)), line)

    def test_real_v012_lines_are_global_records(self):
        # each line is one record with no set, its 4-letter level and its message (on 0.9.x's column alone: the INFO
        # message starts with a space, and an ERROR line is no record)
        out = tok(self, fixture('v012-validate.log'), final=True)
        self.assertEqual([{k: r.get(k) for k in ('t', 'lvl', 'set', 'msg', 'attrs', 'partial')} for r in out['records']],
                         [{'t': l[:19], 'lvl': lvl, 'set': None, 'msg': msg, 'attrs': dict(attrs), 'partial': None}
                          for l, (lvl, msg, attrs) in zip(self.lines(), V012)])
        self.assertEqual(out['carry'], '')


if __name__ == '__main__':
    unittest.main()
