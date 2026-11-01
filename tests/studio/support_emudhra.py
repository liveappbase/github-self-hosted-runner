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


# ---- golden-emudhra

GUEST_START = "GUEST=$(cat <<'EOS'\n"
GUEST_END = '\nEOS\n)\n'
GUEST_W = '/private/tmp/golden-emudhra.T3st'   # the guest work folder the stub tart's mktemp prints (never touched)
RUNNER_SHA = '25a065af409ffa317ab4d5a3b614dd15fc9c40f2172bc1b35a1b1258e919a388'


def guest_text(tc):
    """The guest part of bin/golden-emudhra (the text between the EOS markers)."""
    text = read(os.path.join(REPO, 'bin', 'golden-emudhra'))
    tc.assertEqual(text.count(GUEST_START), 1)
    start = text.index(GUEST_START) + len(GUEST_START)
    return text[start:text.index(GUEST_END, start)]


def guest_copy(tc, d, rewrites):
    """Write the guest part to D/guest.zsh with REWRITES applied, and the W pattern rewritten into D. Returns
    (path, W): run it as `zsh -f path STEP W ARGS…`."""
    w = os.path.join(d, 'w.guest')
    os.makedirs(w)
    rw = list(rewrites) + [('[[ $W == /private/tmp/golden-emudhra.* && -d $W ]]', '[[ $W == %s && -d $W ]]' % w)]
    text = rewrite(tc, guest_text(tc), rw, 'the guest part of bin/golden-emudhra')
    assert_no_ci(tc, text, (), 'the guest part')
    tc.assertNotIn('/private/tmp/golden-emudhra', text)
    return write(os.path.join(d, 'guest.zsh'), text), w


EMUDHRA_TART = r'''D=@D@
case $1 in
  (list) /bin/cat $D/vms 2>/dev/null; exit 0 ;;
  (exec) ;;
  (*) print -r -- "stub tart: unexpected: $*" >> $D/unexpected; exit 1 ;;
esac
vm=$2; shift 2
print -r -- "$vm" >> $D/exec-vms
case $1 in
  (/usr/bin/true) exit 0 ;;
  (/usr/bin/mktemp) print -r -- @W@; exit 0 ;;
  (/bin/rm) print -r -- "rm ${@[2,-1]}" >> $D/calls; exit 0 ;;
  (/bin/test) [[ -f $D/guest-folder-stays ]] && exit 0; exit 1 ;;   # `test -e W` after the rm: gone, unless told
  (/bin/zsh)
    [[ $2 == -f && $3 == -c && $5 == golden-emudhra-guest ]] || { print -r -- "stub tart: guest shape: $1 $2 $3" >> $D/unexpected; exit 9 }
    /bin/zsh -f -n -c "$4" || { print -r -- "stub tart: the guest part does not parse" >> $D/unexpected; exit 9 }
    step=$6; shift 5
    print -r -- "${(j:|:)@}" >> $D/calls
    [[ $step == census && -d $D/hosttmp ]] && /bin/ls $D/hosttmp > $D/census-tmp 2>&1
    [[ -f $D/scenario/$step.out ]] && /bin/cat $D/scenario/$step.out
    [[ -f $D/scenario/$step.sleep ]] && { : > $D/scenario/$step.started; /bin/sleep $(<$D/scenario/$step.sleep) }
    [[ -f $D/scenario/$step.rc ]] && exit $(<$D/scenario/$step.rc)
    exit 0 ;;
  (*) print -r -- "stub tart: unexpected exec: $*" >> $D/unexpected; exit 1 ;;
esac
'''


def emudhra_copy(tc, d, named_src=None):
    """bin/golden-emudhra and bin/node-diff-compare copied into D/bin, REAL rewritten to a stub tart (D/stub/tart)
    whose `exec` answers each guest step from D/scenario/<step>.out and <step>.rc; the named list is D/setup/
    emudhra.node-diff (a copy of NAMED_SRC, when given). Returns the copy's path."""
    tart = stub(os.path.join(d, 'stub', 'tart'), EMUDHRA_TART.replace('@D@', d).replace('@W@', GUEST_W))
    os.makedirs(os.path.join(d, 'scenario'))
    tool = os.path.join(d, 'bin', 'golden-emudhra')
    copy_script(tc, 'bin/golden-emudhra', tool,
                rewrites=[('REAL=/Users/ci/Applications/tart.app/Contents/MacOS/tart', 'REAL=' + tart)],
                allow_ci=('HOME=/Users/ci ',))
    if os.path.exists(os.path.join(REPO, 'bin', 'node-diff-compare')):
        copy_script(tc, 'bin/node-diff-compare', os.path.join(d, 'bin', 'node-diff-compare'))
    if named_src:
        write(os.path.join(d, 'setup', 'emudhra.node-diff'), read(named_src))
    return tool


def scenario(d, step, out='', rc=0, sleep=None):
    write(os.path.join(d, 'scenario', step + '.out'), out)
    write(os.path.join(d, 'scenario', step + '.rc'), '%d\n' % rc)
    if sleep is not None:
        write(os.path.join(d, 'scenario', step + '.sleep'), '%s\n' % sleep)
