"""Helpers for the watchdog's tests (stdlib only; this area shares no helper with another).

A Sandbox runs watchdog/run (a copy of watchdog/ and core/TESTED_JQ, so a test may break a file) with PATH = a stubs
folder and the system folders, and nothing else of the caller's environment:
- `gh`: a stub that answers `gh api PATH ...` from a map the test writes (PATH -> body, or an rc), and logs each call;
- `jq`: the jq under test (the environment variable JQ, a path or a name on PATH, default `jq`), or a stub that
  prints another `--version` and runs the real one for everything else.
Every run of these tests prints the jq under test once with its version.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
SYSTEM_PATH = '/usr/bin:/bin'
_named = []

GH_STUB = r'''#!%(py)s -I
import json, sys
with open(%(map)r) as f:
    m = json.load(f)
with open(%(log)r, 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\n')
args = sys.argv[1:]
path = next((a for a in args[1:] if not a.startswith('-')), '') if args[:1] == ['api'] else ''
key = path + (' --jq ' + args[args.index('--jq') + 1] if '--jq' in args else '')
ans = m.get(key)
if ans is None:
    sys.stderr.write('gh: Not Found (HTTP 404)\n')
    sys.exit(1)
if 'rc' in ans and ans['rc']:
    sys.stderr.write(ans.get('err', 'gh: error\n'))
    sys.exit(ans['rc'])
sys.stdout.write(ans['out'])
'''

JQ_STUB = r'''#!%(py)s -I
import os, sys
if sys.argv[1:] == ['--version']:
    print(%(version)r)
    sys.exit(0)
os.execv(%(real)r, [%(real)r] + sys.argv[1:])
'''


def jq():
    j = os.environ.get('JQ', 'jq')
    path = j if os.sep in j else shutil.which(j)
    if not path:
        raise RuntimeError('the jq under test (JQ=%s) is not found' % j)
    if not _named:
        v = subprocess.run([path, '--version'], capture_output=True, text=True).stdout.strip()
        _named.append(v)
        sys.stderr.write('tests/watchdog: jq under test: %s (%s)\n' % (path, v))
    return path


def jq_version():
    jq()
    return _named[0]


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as f:
        return f.read()


class Sandbox:
    def __init__(self, test):
        self.test = test
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='watchdog-'))
        test.addCleanup(shutil.rmtree, self.root, True)
        self.stubs = os.path.join(self.root, 'stubs')
        os.makedirs(self.stubs)
        self.repo = os.path.join(self.root, 'release')
        shutil.copytree(os.path.join(REPO, 'watchdog'), os.path.join(self.repo, 'watchdog'))
        os.makedirs(os.path.join(self.repo, 'core'))
        shutil.copy(os.path.join(REPO, 'core', 'TESTED_JQ'), os.path.join(self.repo, 'core', 'TESTED_JQ'))
        self.ghmap = {}
        self.gh_log = os.path.join(self.root, 'gh.log')
        self.use_jq()

    def use_jq(self, version=None):
        p = os.path.join(self.stubs, 'jq')
        if os.path.lexists(p):
            os.remove(p)
        if version is None:
            os.symlink(jq(), p)
        else:
            with open(p, 'w') as f:
                f.write(JQ_STUB % {'py': sys.executable, 'version': version, 'real': jq()})
            os.chmod(p, 0o755)

    def answer(self, path, out=None, rc=0, jq_expr=None):
        key = path + (' --jq ' + jq_expr if jq_expr else '')
        self.ghmap[key] = {'out': out if isinstance(out, str) else json.dumps(out), 'rc': rc}

    def gh_calls(self):
        if not os.path.exists(self.gh_log):
            return []
        with open(self.gh_log) as f:
            return [json.loads(l) for l in f]

    def run(self, args):
        mp = os.path.join(self.root, 'ghmap.json')
        with open(mp, 'w') as f:
            json.dump(self.ghmap, f)
        gh = os.path.join(self.stubs, 'gh')
        with open(gh, 'w') as f:
            f.write(GH_STUB % {'py': sys.executable, 'map': mp, 'log': self.gh_log})
        os.chmod(gh, 0o755)
        env = {'PATH': self.stubs + ':' + SYSTEM_PATH, 'HOME': self.root, 'TMPDIR': self.root, 'LC_ALL': 'C'}
        p = subprocess.run(['bash', os.path.join(self.repo, 'watchdog', 'run')] + args, capture_output=True, text=True,
                           env=env, cwd=self.root)
        return p.returncode, p.stdout, p.stderr
