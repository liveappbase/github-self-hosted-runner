"""core/lib/logfmt.jq, the log tokenizer every core program shares: runscaler's text records (charm log v2) from REAL
log cuts. fixtures/hz-cut.log: lines of the Linux Docker host's runner.log (2026-10-22..30) and fixtures/studio-cut.log:
lines of the Studio's runscaler.log (2026-10-24..26), every host value replaced by a neutral one (set names, the
organization, the registry, ids, the address). Pinned: a record per header line, the other programs' lines (a Docker
pull) are no record, the set prefix, exact messages, quoted values unescaped, multi-line values joined, and the last
record held back until a following record header is read: it may yet grow, also when the text ends with a newline
(Codex r1 F1). tokenize_final reads every record (r1.jq calls it on a held record once the log has been quiet)."""
import json
import os
import re
import subprocess
import unittest

from tests.core.corejq import CORE, fixture, jq, tmpdir

# hz-cut.log:3, a line of a Docker pull (another program's line in runscaler's log), here with no newline
PULL_LINE = fixture('hz-cut.log').split('\n')[2]
HEADER = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (DEBU|INFO|WARN|ERRO|FATA) ')


def tok(test, text, final=False):
    d = tmpdir(test)
    p = os.path.join(d, 'log.txt')
    with open(p, 'w', encoding='utf-8', errors='surrogateescape') as f:   # surrogates: bytes that are not UTF-8
        f.write(text)
    r = subprocess.run([jq(), '-n', '-c', '-L', os.path.join(CORE, 'lib'), '--rawfile', 'log', p,
                        'import "logfmt" as L; $log | L::tokenize%s' % ('_final' if final else '')],
                       capture_output=True, text=True)
    test.assertEqual(r.returncode, 0, r.stderr)
    return json.loads(r.stdout)


class RealCuts(unittest.TestCase):
    def test_hz_cut_one_record_per_header_and_docker_lines_are_none(self):
        text = fixture('hz-cut.log')
        out = tok(self, text, final=True)
        headers = [l for l in text.split('\n') if HEADER.match(l)]
        self.assertEqual(len(out['records']), len(headers))
        self.assertEqual(out['carry'], '')
        self.assertFalse(any('Pulling from' in r['msg'] or r['msg'].startswith('Digest') for r in out['records']))
        # read as a pass: every record but the last, which is held whole
        held = tok(self, text)
        self.assertEqual(held['records'], out['records'][:-1])
        self.assertEqual(held['carry'], out['records'][-1]['text'] + '\n')

    def test_global_record_has_no_set_and_its_quoted_value_is_unquoted(self):
        r = tok(self, fixture('hz-cut.log'), final=True)['records'][0]
        self.assertIsNone(r['set'])
        self.assertEqual(r['t'], '2026-10-22 15:35:22')
        self.assertEqual(r['lvl'], 'INFO')
        self.assertEqual(r['msg'], 'Service stop timeout may predate drain support; reinstall the service so restarts '
                                   'can wait for in-flight jobs')
        self.assertEqual(r['attrs']['serviceManager'], 'systemd')
        self.assertEqual(r['attrs']['action'], 'runner service uninstall, then runner service install')

    def test_set_record_runner_removed_with_job_and_result(self):
        rs = [r for r in tok(self, fixture('hz-cut.log'), final=True)['records']
              if r['msg'] == 'Runner removed' and r['attrs'].get('result') == 'failed']
        self.assertTrue(rs)
        r = rs[0]
        self.assertEqual(r['set'], 'linux-a')
        self.assertEqual(r['attrs']['reason'], 'job-completed')
        self.assertRegex(r['attrs']['jobId'], r'^[0-9a-f-]{36}$')
        self.assertRegex(r['attrs']['job'], r'^build \([0-9a-f]{4}\)$')

    def test_escaped_quotes_inside_a_quoted_value(self):
        rs = [r for r in tok(self, fixture('hz-cut.log'), final=True)['records'] if r['msg'] == 'request failed']
        self.assertTrue(rs)
        self.assertTrue(rs[0]['attrs']['error'].startswith('Get "https://broker.actions.githubusercontent.com/'))
        self.assertTrue(rs[0]['attrs']['error'].endswith('": context canceled'))
        self.assertEqual(rs[0]['attrs']['method'], 'GET')

    def test_exited_without_job(self):
        rs = [r for r in tok(self, fixture('hz-cut.log'), final=True)['records']
              if r['msg'] == 'Runner removed' and r['attrs'].get('reason') == 'exited']
        self.assertTrue(any('jobId' not in r['attrs'] for r in rs))
        self.assertTrue(any('jobId' in r['attrs'] for r in rs))

    def test_studio_multi_line_value_is_joined(self):
        out = tok(self, fixture('studio-cut.log'), final=True)
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
        rs = [r for r in tok(self, fixture('studio-cut.log'), final=True)['records'] if 'runnerName' in r['attrs']]
        self.assertEqual(rs[0]['attrs']['runnerName'], '')


class Shapes(unittest.TestCase):
    def test_exact_message_runner_started_cold_is_not_runner_started(self):
        out = tok(self, '2026-10-26 21:11:09 DEBU tart-linux-a: Runner started (cold) name=runner-d5741c95\n', final=True)
        self.assertEqual(out['records'][0]['msg'], 'Runner started (cold)')

    def test_a_key_after_a_multi_line_value(self):
        # charm log v2 text.go: after a multi-line value with more keys a newline, then " key=value"
        text = ('2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n  │ one\n  │ two\n'
                ' name=runner-e2ddacdc\n2026-10-26 21:10:54 INFO mac-a: Scaling up runner currentCount=1\n')
        out = tok(self, text, final=True)
        self.assertEqual(out['records'][0]['attrs'], {'error': 'one\ntwo', 'name': 'runner-e2ddacdc'})
        self.assertEqual(len(out['records']), 2)

    def test_a_partial_last_line_holds_its_whole_record(self):
        head = '2026-10-26 21:10:52 INFO mac-a: Scaling up runner currentCount=1\n'
        rec = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n  │ runner process ex'
        out = tok(self, head + rec)
        self.assertEqual([r['msg'] for r in out['records']], ['Scaling up runner'])
        self.assertEqual(out['carry'], rec)
        nxt = '2026-10-26 21:10:54 INFO mac-a: Scaling up runner currentCount=1\n'
        whole = tok(self, out['carry'] + 'ited on runner-x before connecting to GitHub; runner log:\n' + nxt)
        self.assertEqual(whole['records'][0]['attrs']['error'],
                         'runner process exited on runner-x before connecting to GitHub; runner log:')
        self.assertEqual(whole['carry'], nxt)

    def test_a_record_that_ends_on_a_key_line_is_held(self):
        rec = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n'
        out = tok(self, rec)
        self.assertEqual(out['records'], [])
        self.assertEqual(out['carry'], rec)

    def test_the_last_record_is_held_also_when_the_text_ends_with_a_newline(self):
        text = fixture('studio-cut.log')
        out = tok(self, text)
        last = [l for l in text.split('\n') if HEADER.match(l)][-1]
        self.assertTrue(out['carry'].startswith(last + '\n'), out['carry'][:200])
        self.assertTrue(out['carry'].endswith('\n'))
        self.assertFalse(any(r['text'].startswith(last) for r in out['records']))
        # control: tokenize_final reads it and holds nothing
        self.assertEqual(tok(self, text, final=True)['carry'], '')

    def test_a_multi_line_record_cut_at_any_newline_is_never_read_from_its_first_part(self):
        out = tok(self, fixture('studio-cut.log'), final=True)
        rec = [r for r in out['records'] if r['msg'] == 'Failed to start runner, will retry'][0]['text'] + '\n'
        head = '2026-10-26 21:10:52 INFO mac-a: Scaling up runner currentCount=1\n'
        nxt = '2026-10-26 21:10:54 INFO mac-a: Scaling up runner currentCount=1\n'
        cuts = [i + 1 for i, c in enumerate(rec) if c == '\n']
        self.assertGreaterEqual(len(cuts), 10)
        for cut in cuts:
            first = tok(self, head + rec[:cut])
            self.assertEqual([r['msg'] for r in first['records']], ['Scaling up runner'], cut)
            self.assertEqual(first['carry'], rec[:cut], cut)
            whole = tok(self, first['carry'] + rec[cut:] + nxt)
            self.assertEqual(whole['records'][0]['text'] + '\n', rec, cut)
            self.assertIn('no longer exists on the server', whole['records'][0]['attrs']['error'], cut)

    def test_a_line_of_another_program_ends_the_record_before_it(self):
        text = ('2026-10-22 15:35:22 INFO Pulling runner image image=localhost:5000/example-runner platform=""\n'
                'Digest: sha256:00\n  │ not a value of the pull record\n'
                '2026-10-22 15:35:22 INFO Health check server started address=127.0.0.1 port=8080\n')
        out = tok(self, text, final=True)
        self.assertEqual(out['records'][0]['attrs'], {'image': 'localhost:5000/example-runner', 'platform': ''})
        self.assertEqual(out['records'][0]['text'].count('\n'), 0)   # neither the Digest line nor the orphan value line
        self.assertEqual(len(out['records']), 2)

    def test_tokenize_final_marks_the_record_its_partial_last_line_belongs_to(self):
        head = '2026-10-26 21:10:52 INFO mac-a: Scaling up runner currentCount=1\n'
        for part in ('2026-10-26 21:10:53 INFO mac-a: Runner removed name=runner-x reason=job-comp',
                     '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n  │ runner process ex',
                     '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n  │ one\n name=runn'):
            out = tok(self, head + part, final=True)
            self.assertEqual([r.get('partial') for r in out['records']], [None, True], part)
            # control: the same text with its newline is no partial record
            self.assertEqual([r.get('partial') for r in tok(self, head + part + '\n', final=True)['records']],
                             [None, None], part)
        # a partial line of another program ends the record before it, which is whole
        out = tok(self, head + PULL_LINE, final=True)
        self.assertEqual([r.get('partial') for r in out['records']], [None])

    def test_tokenize_final_a_cut_at_the_start_of_a_continuation_line_marks_the_record_before_it(self):
        # Codex r3 F1, Opus r3 F2: a short write that ends at the start of a continuation line leaves a last line of no
        # kind ("  ", "  │" cut inside the "│", "  err", " nam", " "): it starts with a space, the shape of a
        # continuation, so it belongs to the record before it, which is partial (not ended whole)
        head = '2026-10-26 21:10:52 INFO mac-a: Scaling up runner currentCount=1\n'
        rec = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n  │ one\n  │ two\n name=runner-x\n'
        cut_bar = rec[:rec.index('  │ two')] + '  ' + b'\xe2\x94'.decode('utf-8', 'surrogateescape')   # bytes, not a char
        for part in (rec[:rec.index('  │ two') + 2], cut_bar, rec[:rec.index('  error=') + 5],
                     rec[:rec.index(' name=') + 4], rec[:rec.index(' name=') + 1]):
            with self.subTest(repr(part[-12:])):
                out = tok(self, head + part, final=True)
                self.assertEqual([r.get('partial') for r in out['records']], [None, True])
                self.assertEqual(out['records'][1]['msg'], 'Failed to start runner, will retry')
                # its text: the record's lines as written, the cut line last
                self.assertEqual(out['records'][1]['text'].count('\n'), part.count('\n'))
        # controls: a cut inside the next record's header, or a line of another program, ends the record before it,
        # which is whole (one write per record: it was written with its newline)
        for part in (rec + '2026-10-26 21:10:5', rec + PULL_LINE):
            out = tok(self, head + part, final=True)
            self.assertEqual([r.get('partial') for r in out['records']], [None, None], repr(part[-12:]))
            self.assertEqual(out['records'][1]['attrs'], {'error': 'one\ntwo', 'name': 'runner-x'}, repr(part[-12:]))

    def test_tokenize_final_a_partial_line_that_can_no_longer_become_a_continuation_leaves_the_record_whole(self):
        # Codex r4 F1: only a prefix of a charm continuation line (`  key=`, `  │ …`, and ` key=value` right after a
        # value line) marks the record before it partial. Another program's unterminated line that starts with a space
        # (` ---> Running in abcdef`, one space then a character no key starts with, two spaces then no key or bar, a
        # one-space key after a line that is no value line) is foreign text: the record before it was written with its
        # newline and is whole
        head = '2026-10-26 21:10:52 INFO mac-a: Scaling up runner currentCount=1\n'
        rec = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n  │ one\n  │ two\n name=runner-x\n'
        one = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry error="one" name=runner-x\n'
        for whole, part in ((rec, ' ---> Running in abcdef'), (rec, ' -'), (rec, '  ->'), (rec, '  -->'), (rec, '  err or'),
                            (rec, '  error=x'), (rec, ' nam'), (one, ' nam'), (one, ' ---> Running in abcdef')):
            with self.subTest(repr(part)):
                out = tok(self, head + whole + part, final=True)
                self.assertEqual([r.get('partial') for r in out['records']], [None, None])
                self.assertEqual(out['records'][1]['text'] + '\n', whole)
        # controls: on the same records, a line that can still become a continuation line marks the record partial
        for whole, part in ((rec[:rec.index(' name=')], ' nam'), (rec[:rec.index(' name=')], ' '), (one, ' '),
                            (one, '  '), (one, '  err'), (one, '  ' + b'\xe2\x94'.decode('utf-8', 'surrogateescape'))):
            with self.subTest('control ' + repr(part)):
                out = tok(self, head + whole + part, final=True)
                self.assertEqual([r.get('partial') for r in out['records']], [None, True])

    def test_tokenize_final_a_one_space_key_line_is_a_continuation_only_right_after_a_value_line(self):
        # Codex r5 F3, Opus r5 F1: charm writes ` key=value` only right after a multi-line value's last value line, so a
        # partial last line that starts with one space and a key and `=` (the tokenizer's attribute shape) is foreign
        # text after any other line, as a partial ` key` already is: the record before it is whole. After a record
        # header, after a ` key=value` line, after a `  key=` line
        head = '2026-10-26 21:10:52 INFO mac-a: Scaling up runner currentCount=1\n'
        rec = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n  │ one\n  │ two\n name=runner-x\n'
        one = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry error="one" name=runner-x\n'
        key = '2026-10-26 21:10:53 ERRO mac-a: Failed to start runner, will retry\n  error=\n'
        for whole in (one, rec, key):
            for part in (' name=', ' name=x', ' FOO=bar', ' FOO=', ' nam=x'):
                with self.subTest((whole.count('\n'), part)):
                    out = tok(self, head + whole + part, final=True)
                    self.assertEqual([r.get('partial') for r in out['records']], [None, None])
                    self.assertEqual(out['records'][1]['text'] + '\n', whole)
        # control: the same lines right after a value line can still become a continuation: the record is partial
        upto = rec[:rec.index(' name=')]
        for part in (' name=', ' name=x', ' FOO=bar', ' FOO=', ' nam=x'):
            with self.subTest('control ' + repr(part)):
                out = tok(self, head + upto + part, final=True)
                self.assertEqual([r.get('partial') for r in out['records']], [None, True])
                self.assertEqual(out['records'][1]['text'], upto + part)

    def test_continuation_lines_with_no_record_before_them_are_ignored(self):
        out = tok(self, '  │ tail of a record of an earlier interval\n'
                        '2026-10-26 21:10:54 INFO mac-a: Scaling up runner currentCount=1\n', final=True)
        self.assertEqual(len(out['records']), 1)
        self.assertEqual(out['records'][0]['msg'], 'Scaling up runner')


if __name__ == '__main__':
    unittest.main()
