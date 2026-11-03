"""Helpers for the watchdog's tests (stdlib only; this area shares no helper with another).

A Sandbox runs watchdog/run (a copy of watchdog/ and core/TESTED_JQ, so a test may break a file) with PATH = a stubs
folder and the system folders, and nothing else of the caller's environment:
- `gh`: a stub that answers `gh api PATH ...` from a map the test writes (PATH -> body, or an rc; or a body after a
  number of failed calls), and logs each call. It is one of the GH_MODES: `new` (the default) is a gh of 2.98.0 or
  newer, which refuses a body that holds an ESC byte unless it is given --allow-escape-sequences, and lists that flag
  in `gh api --help`; `old` is gh 2.66.1, which has no such check, and to which the flag is an unknown flag;
- `sleep`: a stub that logs its arguments (in the gh log, as ['#sleep', ...]) and returns at once;
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

FLAG = '--allow-escape-sequences'
# help: does `gh api --help` list FLAG (None: the help call fails); knows: is FLAG a flag of this gh; refuses: does it
# refuse a body that holds an ESC byte unless given FLAG
GH_MODES = {
    'new': {'help': True, 'knows': True, 'refuses': True},             # gh 2.98.0 and newer (2.98.0, 2.103.3 measured)
    'old': {'help': False, 'knows': False, 'refuses': False},          # gh 2.66.1
    'new-unlisted': {'help': False, 'knows': True, 'refuses': True},   # no real gh: a CONTROL (NEW, flag not passed)
    'no-help': {'help': None, 'knows': True, 'refuses': True},         # `gh api --help` fails
}
GH_HELP = '''Make an authenticated GitHub API request.

USAGE
  gh api <endpoint> [flags]

FLAGS
%(flag)s      --cache duration           Cache the response, e.g. "3600s", "60m", "1h"
  -F, --field key=value          Add a typed parameter in key=value format
  -H, --header key:value         Add a HTTP request header in key:value format
  -q, --jq string                Query to select values from the response using jq syntax
      --paginate                 Make additional HTTP requests to fetch all pages of results
'''
GH_HELP_FLAG = '      ' + FLAG + '   Allow printing terminal escape sequences\n'
GH_REFUSES = 'the response contains terminal escape sequences; pass ' + FLAG + ' to output it anyway\n'

GH_STUB = r'''#!%(py)s -I
import json, sys
mode, help_text = %(mode)r, %(help)r
FLAG = %(flag)r
with open(%(map)r) as f:
    m = json.load(f)
args = sys.argv[1:]
def key_of(a):
    path = next((x for x in a[1:] if not x.startswith('-')), '') if a[:1] == ['api'] else ''
    return path + (' --jq ' + a[a.index('--jq') + 1] if '--jq' in a else '')
key = key_of(args)
try:
    with open(%(log)r) as f:
        before = sum(1 for l in f if key_of(json.loads(l)) == key)
except FileNotFoundError:
    before = 0
with open(%(log)r, 'a') as f:
    f.write(json.dumps(args) + '\n')
if args == ['api', '--help']:
    if mode['help'] is None:
        sys.stderr.write('gh: cannot print the help\n')
        sys.exit(1)
    sys.stdout.write(help_text)
    sys.exit(0)
if FLAG in args and not mode['knows']:
    sys.stderr.write('unknown flag: ' + FLAG + '\n\nUsage:  gh api <endpoint> [flags]\n')
    sys.exit(1)
ans = m.get(key)
if ans is None:
    sys.stderr.write('gh: Not Found (HTTP 404)\n')
    sys.exit(1)
if ans.get('rc') or before < ans.get('fails', 0):
    sys.stderr.write(ans.get('err', 'gh: HTTP 502\n'))
    sys.exit(ans.get('rc') or 1)
if mode['refuses'] and '\x1b' in ans['out'] and FLAG not in args:
    sys.stderr.write(%(refuses)r)
    sys.exit(1)
sys.stdout.write(ans['out'])
'''

SLEEP_STUB = r'''#!%(py)s -I
import json, sys
with open(%(log)r, 'a') as f:
    f.write(json.dumps(['#sleep'] + sys.argv[1:]) + '\n')
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
    def __init__(self, test, gh='new'):
        self.test = test
        self.gh_mode = GH_MODES[gh]
        self.failing = {}
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

    def fail(self, path, times, jq_expr=None):
        """The first TIMES calls of PATH fail (rc 1, an HTTP 502 on stderr); later ones get its answer."""
        self.failing[path + (' --jq ' + jq_expr if jq_expr else '')] = times

    def timeline(self):
        """Every logged call in order: gh's argv, and ['#sleep', ...] for each sleep."""
        if not os.path.exists(self.gh_log):
            return []
        with open(self.gh_log) as f:
            return [json.loads(l) for l in f]

    def gh_calls(self):
        return [c for c in self.timeline() if c[:1] != ['#sleep']]

    def run(self, args):
        mp = os.path.join(self.root, 'ghmap.json')
        ghmap = {k: dict(v, fails=self.failing.get(k, 0)) for k, v in self.ghmap.items()}
        with open(mp, 'w') as f:
            json.dump(ghmap, f)
        gh = os.path.join(self.stubs, 'gh')
        with open(gh, 'w') as f:
            f.write(GH_STUB % {'py': sys.executable, 'map': mp, 'log': self.gh_log, 'mode': self.gh_mode, 'flag': FLAG,
                               'help': GH_HELP % {'flag': GH_HELP_FLAG if self.gh_mode['help'] else ''},
                               'refuses': GH_REFUSES})
        os.chmod(gh, 0o755)
        sleep = os.path.join(self.stubs, 'sleep')
        with open(sleep, 'w') as f:
            f.write(SLEEP_STUB % {'py': sys.executable, 'log': self.gh_log})
        os.chmod(sleep, 0o755)
        env = {'PATH': self.stubs + ':' + SYSTEM_PATH, 'HOME': self.root, 'TMPDIR': self.root, 'LC_ALL': 'C'}
        p = subprocess.run(['bash', os.path.join(self.repo, 'watchdog', 'run')] + args, capture_output=True, text=True,
                           env=env, cwd=self.root)
        return p.returncode, p.stdout, p.stderr
