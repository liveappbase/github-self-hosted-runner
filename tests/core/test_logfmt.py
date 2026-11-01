"""core/lib/logfmt.jq, the log tokenizer every core program shares: runscaler's text records (charm log v2) from REAL
log cuts. fixtures/hz-cut.log: lines of the Linux Docker host's runner.log (2026-10-22..30) and fixtures/studio-cut.log:
lines of the Studio's runscaler.log (2026-10-24..26), every host value replaced by a neutral one (set names, the
organization, the registry, ids, the address). Pinned: a record per header line, the other programs' lines (a Docker
pull) are no record, the set prefix, exact messages, quoted values unescaped, multi-line values joined, and the last
record held back while it may be incomplete."""
import json
import os
import re
import subprocess
import unittest

from tests.core.corejq import CORE, fixture, jq, tmpdir

HEADER = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (DEBU|INFO|WARN|ERRO|FATA) ')


def tok(test, text):
    d = tmpdir(test)
    p = os.path.join(d, 'log.txt')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    r = subprocess.run([jq(), '-n', '-c', '-L', os.path.join(CORE, 'lib'), '--rawfile', 'log', p,
                        'import "logfmt" as L; $log | L::tokenize'], capture_output=True, text=True)
    test.assertEqual(r.returncode, 0, r.stderr)
    return json.loads(r.stdout)


class RealCuts(unittest.TestCase):
    def test_hz_cut_one_record_per_header_and_docker_lines_are_none(self):
        text = fixture('hz-cut.log')
        out = tok(self, text)
        headers = [l for l in text.split('\n') if HEADER.match(l)]
        self.assertEqual(len(out['records']), len(headers))
        self.assertEqual(out['carry'], '')
        self.assertFalse(any('Pulling from' in r['msg'] or r['msg'].startswith('Digest') for r in out['records']))

    def test_global_record_has_no_set_and_its_quoted_value_is_unquoted(self):
        r = tok(self, fixture('hz-cut.log'))['records'][0]
        self.assertIsNone(r['set'])
        self.assertEqual(r['t'], '2026-10-22 15:35:22')
        self.assertEqual(r['lvl'], 'INFO')
        self.assertEqual(r['msg'], 'Service stop timeout may predate drain support; reinstall the service so restarts '
                                   'can wait for in-flight jobs')
        self.assertEqual(r['attrs']['serviceManager'], 'systemd')
        self.assertEqual(r['attrs']['action'], 'runner service uninstall, then runner service install')

    def test_set_record_runner_removed_with_job_and_result(self):
        rs = [r for r in tok(self, fixture('hz-cut.log'))['records']
              if r['msg'] == 'Runner removed' and r['attrs'].get('result') == 'failed']
        self.assertTrue(rs)
        r = rs[0]
        self.assertEqual(r['set'], 'linux-a')
        self.assertEqual(r['attrs']['reason'], 'job-completed')
        self.assertRegex(r['attrs']['jobId'], r'^[0-9a-f-]{36}$')
        self.assertRegex(r['attrs']['job'], r'^build \([0-9a-f]{4}\)$')

    def test_escaped_quotes_inside_a_quoted_value(self):
        rs = [r for r in tok(self, fixture('hz-cut.log'))['records'] if r['msg'] == 'request failed']
        self.assertTrue(rs)
        self.assertTrue(rs[0]['attrs']['error'].startswith('Get "https://broker.actions.githubusercontent.com/'))
        self.assertTrue(rs[0]['attrs']['error'].endswith('": context canceled'))
        self.assertEqual(rs[0]['attrs']['method'], 'GET')

    def test_exited_without_job(self):
        rs = [r for r in tok(self, fixture('hz-cut.log'))['records']
              if r['msg'] == 'Runner removed' and r['attrs'].get('reason') == 'exited']
        self.assertTrue(any('jobId' not in r['attrs'] for r in rs))
        self.assertTrue(any('jobId' in r['attrs'] for r in rs))

    def test_studio_multi_line_value_is_joined(self):
        out = tok(self, fixture('studio-cut.log'))
        rs = [r for r in out['records'] if r['msg'] == 'Failed to start runner, will retry']
        self.assertEqual(len(rs), 1)
        e = rs[0]['attrs']['error']
        self.assertTrue(e.startswith('failed to start runner: runner process exited on runner-e2ddacdc right after '
                                     'connecting to GitHub; runner log:\n√ Connected to GitHub\n\nCurrent runner'))
        self.assertIn('\nThe runner no longer exists on the server. Cleaning up local configuration.\n', e)
        self.assertTrue(e.endswith('\nExiting runner...'))
        self.assertEqual(rs[0]['set'], 'mac-a')
        i = out['records'].index(rs[0])
        self.assertEqual(out['records'][i + 1]['msg'], 'Scaling up runner')   # the record after it is its own

    def test_empty_quoted_value(self):
        rs = [r for r in tok(self, fixture('studio-cut.log'))['records'] if 'runnerName' in r['attrs']]
        self.assertEqual(rs[0]['attrs']['runnerName'], '')


class Shapes(unittest.TestCase):
    def test_exact_message_runner_started_cold_is_not_runner_started(self):
        out = tok(self, '2026-10-26 21:11:09 DEBU tart-linux-a: Runner started (cold) name=runner-d5741c95\n')
        self.assertEqual(out['records'][0]['msg'], 'Runner started (cold)')

    def test_a_key_after_a_multi_line_value(self):
        # charm log v2 text.go: after a multi-line value with more keys a newline, then " key=value"
        text = ('2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n  │ one\n  │ two\n'
                ' name=runner-e2ddacdc\n2026-10-26 21:10:54 INFO mac-a: Scaling up runner currentCount=1\n')
        out = tok(self, text)
        self.assertEqual(out['records'][0]['attrs'], {'error': 'one\ntwo', 'name': 'runner-e2ddacdc'})
        self.assertEqual(len(out['records']), 2)

    def test_a_partial_last_line_holds_its_whole_record(self):
        head = '2026-10-26 21:10:52 INFO mac-a: Scaling up runner currentCount=1\n'
        rec = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n  │ runner process ex'
        out = tok(self, head + rec)
        self.assertEqual([r['msg'] for r in out['records']], ['Scaling up runner'])
        self.assertEqual(out['carry'], rec)
        whole = tok(self, out['carry'] + 'ited on runner-x before connecting to GitHub; runner log:\n')
        self.assertEqual(whole['records'][0]['attrs']['error'],
                         'runner process exited on runner-x before connecting to GitHub; runner log:')
        self.assertEqual(whole['carry'], '')

    def test_a_record_that_ends_on_a_key_line_is_held(self):
        rec = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n'
        out = tok(self, rec)
        self.assertEqual(out['records'], [])
        self.assertEqual(out['carry'], rec)

    def test_text_that_ends_with_a_newline_holds_nothing(self):
        out = tok(self, fixture('studio-cut.log'))
        self.assertEqual(out['carry'], '')

    def test_a_line_of_another_program_ends_the_record_before_it(self):
        text = ('2026-10-22 15:35:22 INFO Pulling runner image image=localhost:5000/example-runner platform=""\n'
                'Digest: sha256:00\n  │ not a value of the pull record\n'
                '2026-10-22 15:35:22 INFO Health check server started address=127.0.0.1 port=8080\n')
        out = tok(self, text)
        self.assertEqual(out['records'][0]['attrs'], {'image': 'localhost:5000/example-runner', 'platform': ''})
        self.assertEqual(out['records'][0]['text'].count('\n'), 0)   # neither the Digest line nor the orphan value line
        self.assertEqual(len(out['records']), 2)

    def test_continuation_lines_with_no_record_before_them_are_ignored(self):
        out = tok(self, '  │ tail of a record of an earlier interval\n'
                        '2026-10-26 21:10:54 INFO mac-a: Scaling up runner currentCount=1\n')
        self.assertEqual(len(out['records']), 1)
        self.assertEqual(out['records'][0]['msg'], 'Scaling up runner')


if __name__ == '__main__':
    unittest.main()
