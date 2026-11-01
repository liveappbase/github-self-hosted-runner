"""Helpers for the decision core's tests (stdlib only; this area shares no helper with another).

The jq under test is the environment variable JQ (a path, or a name looked up on PATH), default `jq`. Every run of
these tests prints it once, with its `--version`, and test_tested_jq.py fails when that version is not a row of
core/TESTED_JQ for the area `core`: a run under an untested jq is RED, never a silent green.

run() calls a core program exactly as the glue does (core/README.md, "The call"):
  jq -n -L core/lib -f core/<name>.jq [--slurpfile state F] [--rawfile log F] [--slurpfile healthz F]
     [--slurpfile facts F] [--arg now EPOCH]
and returns (rc, the one JSON object it printed or None, stderr).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORE = os.path.join(REPO, 'core')
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')

_named = []


def jq():
    j = os.environ.get('JQ', 'jq')
    path = j if os.sep in j else shutil.which(j)
    if not path:
        raise RuntimeError('the jq under test (JQ=%s) is not found' % j)
    if not _named:
        v = subprocess.run([path, '--version'], capture_output=True, text=True).stdout.strip()
        _named.append(v)
        sys.stderr.write('tests/core: jq under test: %s (%s)\n' % (path, v))
    return path


def jq_version():
    jq()
    return _named[0]


def tested_rows(path=None):
    """core/TESTED_JQ -> [(version, [areas], where)]."""
    rows = []
    with open(path or os.path.join(CORE, 'TESTED_JQ')) as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            w = line.split()
            rows.append((w[0], w[1].split(','), w[2]))
    return rows


def tmpdir(test):
    d = tempfile.mkdtemp(prefix='core-')
    test.addCleanup(shutil.rmtree, d, True)
    return d


def fixture(*parts):
    with open(os.path.join(FIXTURES, *parts), encoding='utf-8') as f:
        return f.read()


def run(test, name, state=None, log=None, healthz=None, facts=None, now=None, raw_state=None):
    """state/facts: a JSON value (or None = not passed; state=[] passes an EMPTY file). healthz: a list of reads.
    raw_state: the state file's exact text (for a malformed or unknown-format state)."""
    d = tmpdir(test)
    argv = [jq(), '-n', '-L', os.path.join(CORE, 'lib'), '-f', os.path.join(CORE, name + '.jq')]

    def put(fname, text):
        p = os.path.join(d, fname)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        return p

    if raw_state is not None:
        argv += ['--slurpfile', 'state', put('state.json', raw_state)]
    elif state is not None:
        argv += ['--slurpfile', 'state', put('state.json', '' if state == [] else json.dumps(state))]
    if log is not None:
        argv += ['--rawfile', 'log', put('log.txt', log)]
    if healthz is not None:
        argv += ['--slurpfile', 'healthz', put('healthz.json', '\n'.join(json.dumps(r) for r in healthz))]
    if facts is not None:
        argv += ['--slurpfile', 'facts', put('facts.json', json.dumps(facts))]
    if now is not None:
        argv += ['--arg', 'now', str(now)]
    p = subprocess.run(argv, capture_output=True, text=True, cwd=d)
    out = None
    if p.returncode == 0:
        out, end = json.JSONDecoder().raw_decode(p.stdout.lstrip())
        test.assertEqual(p.stdout.lstrip()[end:].strip(), '', 'a core program prints ONE JSON value: %r' % p.stdout[:400])
        test.assertIsInstance(out, dict)
        for k in ('verdict', 'reason', 'lines'):
            test.assertIn(k, out, 'the call shape {verdict, reason, lines}: %r' % out)
        test.assertIsInstance(out['lines'], list)
    return p.returncode, out, p.stderr


def ok(test, name, **kw):
    rc, out, err = run(test, name, **kw)
    test.assertEqual(rc, 0, 'core/%s.jq failed: %s' % (name, err))
    return out
