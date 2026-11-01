"""The core tests build their log records with corejq.charm(); this pins it to runscaler's real output, byte for byte:
lines of fixtures/hz-cut.log and fixtures/studio-cut.log (real logs, host values replaced), a quoted value with
escaped quotes, an empty value, and the Studio's multi-line start failure. So a record a test builds is a record the
host writes."""
import unittest

from tests.core.corejq import charm, fixture


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


if __name__ == '__main__':
    unittest.main()
