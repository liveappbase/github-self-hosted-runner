"""core/lib/logfmt.jq, the log tokenizer every core program shares: runscaler's text records (charm log v2) from REAL
log cuts. fixtures/hz-cut.log: lines of the Linux Docker host's runner.log (2026-10-22..30) and fixtures/studio-cut.log:
lines of the Studio's runscaler.log (2026-10-24..26), every host value replaced by a neutral one (set names, the
organization, the registry, ids, the address). Pinned: a record per header line, the other programs' lines (a Docker
pull) are no record, the set prefix, exact messages, quoted values unescaped, multi-line values joined, and the last
record held back until a following record header is read: it may yet grow, also when the text ends with a newline
(Codex r1 F1). tokenize_final reads every record (r1.jq calls it on a held record once the log has been quiet).
LevelColumns: the level column of runscaler 0.10.0 and later (5 wide) reads as 0.9.x's (census finding 2)."""
import json
import os
import re
import subprocess
import unittest

from tests.core.corejq import CORE, charm, fixture, jq, tmpdir, to_v012

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


def toks(test, texts, final=False):
    """tok() of each text, in ONE jq run (a cut cell reads a hundred texts)"""
    d = tmpdir(test)
    p = os.path.join(d, 'texts.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(list(texts), f)
    r = subprocess.run([jq(), '-n', '-c', '-L', os.path.join(CORE, 'lib'), '--slurpfile', 't', p,
                        'import "logfmt" as L; $t[0][] | L::tokenize%s' % ('_final' if final else '')],
                       capture_output=True, text=True)
    test.assertEqual(r.returncode, 0, r.stderr)
    out = [json.loads(l) for l in r.stdout.splitlines()]
    test.assertEqual(len(out), len(texts))
    return out


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


FIELDS = ('t', 'lvl', 'set', 'msg', 'attrs', 'partial')


def fields(r):
    return {k: r.get(k) for k in FIELDS}


def but_text(r):
    return {k: v for k, v in r.items() if k != 'text'}


T = '2026-11-06 20:04:01'
MULTI = ('failed to start runner: runner process exited on runner-e2ddacdc right after connecting to GitHub; runner '
         'log:\n√ Connected to GitHub\n\nThe runner no longer exists on the server. Cleaning up local configuration.\n'
         'Exiting runner...')
JOB = [('jobId', '2ce18645-b726-290f-1564-ea0902058718'), ('repo', 'example-org/example'),
       ('workflowRunId', '15885850636'), ('job', 'build (9150)')]
# each message core/r1.jq reads, at the level runscaler logs it with (v0.12.0: internal/controller/controller.go:160,
# 176, 254, 445, 560, 734; internal/provider/tart.go:350), as (the level in 0.9.x's column, set, message, attributes);
# then a DEBU and a FATA record
CORE_READS = [
    ('INFO', 'mac-a', 'Runner removed', [('name', 'runner-0000beef'), ('instanceID', 'runner-0000beef'),
                                         ('reason', 'job-completed')] + JOB + [('result', 'succeeded')]),
    ('INFO', 'mac-a', 'Runner removed', [('name', 'runner-0000beef'), ('instanceID', 'runner-0000beef'),
                                         ('reason', 'exited')]),
    ('INFO', 'mac-a', 'Runner started', [('name', 'runner-0000beef'), ('instanceID', 'runner-0000beef'),
                                         ('startupTime', '22.4s')]),
    ('ERRO', 'mac-a', 'Failed to start runner, will retry', [('error', 'failed to start runner: runner on runner-0000beef '
                                                                       'did not connect to GitHub within 5m0s')]),
    ('ERRO', 'mac-a', 'Failed to start runner, will retry', [('error', MULTI)]),
    ('WARN', 'mac-a', 'Job started for unknown runner (already removed?)', [('runnerName', 'runner-58c119b8')]),
    ('WARN', 'mac-a', 'Job completed for unknown runner (already removed?)', [('runnerName', '')]),
    ('WARN', 'mac-a', 'Runner exited before job completion; removing stale capacity', [('name', 'runner-0000beef')]),
    ('ERRO', 'tart-mac-a', 'VM exited unexpectedly', [('name', 'runner-0000beef'), ('error', 'exit status 1')]),
    ('DEBU', 'tart-mac-a', 'Runner started (cold)', [('name', 'runner-d5741c95')]),
    ('FATA', None, 'failed to start the scale sets', [('error', 'context canceled')]),
]
# the census probe (census-src/probe-logfmt/v012.log): runscaler 0.12.0's column, from source
PROBE = ('2026-11-06 20:04:01 INFO  linux-a: Runner removed name=runner-1d1af85d reason=job-completed jobId=j1 '
         'result=succeeded\n',
         '2026-11-06 20:04:02 ERROR linux-a: Failed to start runner, will retry error="did not connect to GitHub within '
         '2m"\n',
         '2026-11-06 20:04:03 WARN  linux-a: Job started for unknown runner (already removed?) '
         'runnerName=runner-58c119b8\n')
# THE CUT HEADER: a record, then a header cut short at any char (a short write, or the pass's capture inside it)
R95 = ('2026-11-06 20:04:00 INFO mac-a: Runner removed name=runner-0000beef reason=job-completed jobId=j1 '
       'result=succeeded\n')
R12 = to_v012(R95)
REC = {'t': '2026-11-06 20:04:00', 'lvl': 'INFO', 'set': 'mac-a', 'msg': 'Runner removed',
       'attrs': {'name': 'runner-0000beef', 'reason': 'job-completed', 'jobId': 'j1', 'result': 'succeeded'},
       'partial': None}
HI = '2026-11-06 20:04:01 INFO  mac-a: Runner removed'
HE = '2026-11-06 20:04:01 ERROR mac-a: Failed to start runner'


class LevelColumns(unittest.TestCase):
    """runscaler 0.10.0 and later write the level in a 5-wide column (census finding 2: charm log v2.0.1 styles.go
    :57-77, DEBUG, `INFO `, `WARN `, ERROR, FATAL, then one space), 0.9.x the 4-letter word (DEBU INFO WARN ERRO FATA).
    The census probe (logfmt.jq at 1cbc254 on the v0.12.0 lines) read the INFO and WARN lines as set null with a message
    that starts with ` linux-a:`, and an ERROR line as another program's line: no record. Pinned: each message the core
    reads gives the same record in both columns, an ERROR line is a record, a global record has no set, the real cuts
    read the same, a text may change its column mid-way (the switch, a way back), and a header cut short (the
    partial-line rules) is held from the char where it can first be a header in either column."""

    def test_each_message_the_core_reads_reads_the_same_in_both_columns(self):
        v095 = [charm(T, lvl, s, m, a) for lvl, s, m, a in CORE_READS]
        v012 = [to_v012(x) for x in v095]
        o95, o12 = toks(self, v095, final=True), toks(self, v012, final=True)
        for (lvl, s, m, a), r95, r12 in zip(CORE_READS, o95, o12):
            with self.subTest(lvl=lvl, msg=m):
                # the control against an empty pair: the v095 twin's set is the set, its msg the message
                self.assertEqual([(r['lvl'], r['set'], r['msg']) for r in r95['records']], [(lvl, s, m)])
                self.assertEqual([fields(r) for r in r12['records']], [fields(r) for r in r95['records']])

    def test_an_error_line_is_a_record(self):
        before, err, after = PROBE
        out = tok(self, before + err + after, final=True)
        self.assertEqual([fields(r) for r in out['records']], [
            {'t': '2026-11-06 20:04:01', 'lvl': 'INFO', 'set': 'linux-a', 'msg': 'Runner removed',
             'attrs': {'name': 'runner-1d1af85d', 'reason': 'job-completed', 'jobId': 'j1', 'result': 'succeeded'},
             'partial': None},
            {'t': '2026-11-06 20:04:02', 'lvl': 'ERRO', 'set': 'linux-a', 'msg': 'Failed to start runner, will retry',
             'attrs': {'error': 'did not connect to GitHub within 2m'}, 'partial': None},
            {'t': '2026-11-06 20:04:03', 'lvl': 'WARN', 'set': 'linux-a',
             'msg': 'Job started for unknown runner (already removed?)', 'attrs': {'runnerName': 'runner-58c119b8'},
             'partial': None}])
        self.assertEqual([r['text'] + '\n' for r in out['records']], list(PROBE))
        # controls: a level of neither column is no record (another program's line), and the record before it is whole
        for bad in ('NOTICE', 'ERRORS'):
            with self.subTest(bad):
                out = tok(self, before + '2026-11-06 20:04:02 %s mac-a: x\n' % bad + after, final=True)
                self.assertEqual([r['text'] + '\n' for r in out['records']], [before, after])
                self.assertEqual([r.get('partial') for r in out['records']], [None, None])

    def test_a_global_v012_record_has_no_set(self):
        out = tok(self, '2026-11-06 20:04:00 INFO  Health check server started address=127.0.0.1 port=8080\n', final=True)
        self.assertEqual([fields(r) for r in out['records']], [
            {'t': '2026-11-06 20:04:00', 'lvl': 'INFO', 'set': None, 'msg': 'Health check server started',
             'attrs': {'address': '127.0.0.1', 'port': '8080'}, 'partial': None}])

    def test_the_real_cuts_read_the_same_in_the_v012_column(self):
        for name in ('hz-cut.log', 'studio-cut.log'):
            text = fixture(name)
            for final in (False, True):
                with self.subTest(name=name, final=final):
                    a, b = toks(self, [text, to_v012(text)], final)
                    self.assertGreater(len(a['records']), 40)
                    self.assertEqual([but_text(r) for r in b['records']], [but_text(r) for r in a['records']])
                    self.assertEqual([r['text'] for r in b['records']], [to_v012(r['text']) for r in a['records']])
                    if final:
                        self.assertEqual((a['carry'], b['carry']), ('', ''))
                    else:
                        self.assertEqual(b['carry'], to_v012(a['carry']))

    def test_a_text_that_changes_column_mid_way(self):
        # v095 records then v012 ones (the switch to 0.12.0) and the reverse (a way back), in one text and across a
        # pass boundary (the first part's carry prepended to the second): the records of the all-v095 text
        text = fixture('studio-cut.log')
        ls = text.split('\n')
        heads = [i for i, l in enumerate(ls) if HEADER.match(l)]
        multi = next(i for i, l in enumerate(ls) if 'Failed to start runner' in l)
        whole = [but_text(r) for r in tok(self, text, final=True)['records']]
        # the cuts: right after the multi-line start failure (so it is the first part's carry), and one mid-way
        for cut in (next(i for i in heads if i > multi), heads[len(heads) // 2]):
            a, b = '\n'.join(ls[:cut]) + '\n', '\n'.join(ls[cut:])
            self.assertEqual(a + b, text)
            for how, first, second in (('the switch', a, to_v012(b)), ('a way back', to_v012(a), b)):
                with self.subTest(cut=cut, how=how):
                    one = tok(self, first + second, final=True)
                    self.assertEqual([but_text(r) for r in one['records']], whole)
                    p1 = tok(self, first)
                    self.assertTrue(p1['carry'])
                    p2 = tok(self, p1['carry'] + second, final=True)
                    self.assertEqual([but_text(r) for r in p1['records'] + p2['records']], whole)

    def cut(self, rec, head, held_from=None):
        """REC + HEAD[:n] for every n: tokenize_final keeps the record before whole (REC's fields and text, no
        partial). With HELD_FROM: tokenize's carry is the whole text while HEAD[:n] can be no header (n < HELD_FROM),
        and HEAD[:n] from then on, with the record before read"""
        ns = range(1, len(head) + 1)
        texts = [rec + head[:n] for n in ns]
        held = toks(self, texts) if held_from else [None] * len(texts)
        for n, f, h in zip(ns, toks(self, texts, final=True), held):
            with self.subTest(head=head[:n]):
                self.assertEqual(fields(f['records'][0]), REC)
                self.assertEqual(f['records'][0]['text'] + '\n', rec)
                if held_from:
                    self.assertEqual(h['carry'], rec + head[:n] if n < held_from else head[:n])
                    self.assertEqual([fields(r) for r in h['records']], [] if n < held_from else [REC])

    def test_a_cut_header_after_a_v095_record_leaves_it_whole(self):
        self.assertEqual((len(HI), len(HE)), (47, 55))
        self.cut(R95, HI, 25)
        self.cut(R95, HE)

    def test_a_cut_error_header_is_held_from_char_26(self):
        # an ERROR header can be a header only once its 26th char, the space after ERROR, is written
        self.cut(R95, HE, 26)

    def test_a_cut_header_after_a_v012_record(self):
        self.cut(R12, HI, 25)
        self.cut(R12, HE, 26)


if __name__ == '__main__':
    unittest.main()
