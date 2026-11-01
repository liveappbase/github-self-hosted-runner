"""Test helpers for S3a-emudhra: runner-journal, node-diff-compare, golden-emudhra (its census, --gate) and golden-gate.

Each test makes its own temp folder (removed with addCleanup). A script under test runs as a COPY in that folder, with
its path constants rewritten by exact string replacement; each replacement must match at least once, and the copy may
hold no /Users/ci string except those the test names, so a missed rewrite fails the test instead of touching a host
path. Stub programs are small zsh scripts the test writes.
"""
import os
import shutil
import subprocess
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ZSH = '/bin/zsh'
FIXTURES = os.path.join(REPO, 'tests', 'studio', 'fixtures')
BASE_ENV = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C'}


def tmpdir(tc):
    d = tempfile.mkdtemp(prefix='s3a-emudhra.')
    tc.addCleanup(shutil.rmtree, d, True)
    return os.path.realpath(d)


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    os.chmod(path, mode)
    return path


def stub(path, body):
    """A stub program: a zsh script with BODY."""
    return write(path, '#!/bin/zsh -f\n' + body, 0o755)


def assert_no_ci(tc, text, allow, label):
    rest = text
    for a in allow:
        rest = rest.replace(a, '')
    tc.assertNotIn('/Users/ci', rest, '%s: a /Users/ci string is left after the rewrites' % label)


def rewrite(tc, text, rewrites, label):
    for old, new in rewrites:
        tc.assertGreaterEqual(text.count(old), 1, '%s: the rewrite %r matched nothing' % (label, old))
        text = text.replace(old, new)
    return text


def copy_script(tc, src_rel, dst, rewrites=(), allow_ci=()):
    """Copy REPO/SRC_REL to DST with REWRITES applied; assert no /Users/ci is left but ALLOW_CI."""
    text = rewrite(tc, read(os.path.join(REPO, src_rel)), rewrites, src_rel)
    assert_no_ci(tc, text, allow_ci, src_rel)
    write(dst, text, 0o755)
    return text


def run(argv, env=None, cwd=None, timeout=90):
    e = dict(BASE_ENV)
    e.update(env or {})
    return subprocess.run(argv, env=e, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def lines(path):
    if not os.path.exists(path):
        return []
    return read(path).splitlines()
