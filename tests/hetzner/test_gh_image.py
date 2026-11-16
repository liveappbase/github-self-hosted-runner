"""H4: the Linux runner image installs gh from GitHub's own apt repository (cli.github.com), never Ubuntu's: the recipe's
files in linux-docker/image/ and 02-d1.sh step 6 (b)'s floor. (Named for its CI part, test_[c-jv-z]*.py:
.github/workflows/release-check.yml.)

- THE KEY (D1, R-4): image/githubcli-archive-key.asc is GitHub CLI's public key, armored, as keyserver.ubuntu.com serves
  it under the pin: ONE primary key. The pin's one spelling on this host is the Dockerfile's argument to the check; the
  committed key's only primary fingerprint must be that argument (the cell reads the repository only). Control: a copy
  with a planted second primary key is refused.
- THE CHECK (D2, A1, R-4, S-5): image/apt-key-pinned.sh FILE PIN exits 0 only when the primary keys of FILE are PIN
  alone (gpg --show-keys --with-colons: each `pub`'s own `fpr`; a subkey's is no primary), else 1 naming what it saw.
  It is the Studio's rule (bin/linux-image-build's key_pinned: the primaries' fingerprints, joined by one space, must be
  PIN), a second copy in another runtime, pinned to agree on shared fixtures made in the cell (each a primary key with a
  subkey; no network): the pin alone, the pin and another primary in BOTH orders (the published keyring puts the other
  first), the other alone, an empty file. The bash copy runs everywhere; the zsh copy where /bin/zsh exists (the Mac).
  A "first primary only" copy of either is caught by the pin-first two-key fixture (the mutant rows).
- THE DOCKERFILE (D3, A3, R-1 (a), R-7): Ubuntu's apt line installs no gh; ONE RUN names cli.github.com, every command
  of it joined by `&&` (no `;`, no `||`, no `set +e`), in this order: the key file dearmored to the ONE keyring path, the
  check on THAT path, the source whose signed-by names it (arch from dpkg), apt-get update, gh, the floor, the lists
  removed. Each mutant row (`|| true` after the check, signed-by another file, the check after apt-get update, ...)
  draws its own reason; the shipped text draws none.
- THE FLOOR (S-4, T-1, T-2): image/gh-floor is one line N.N.N; image/gh-floor-ok.sh FLOOR_FILE VERSION is the ONE
  compare, field by field as numbers (2.45.0 is below 2.102.0), read by the Dockerfile's RUN and by 02-d1.sh step 6 (b),
  which takes both files from the build context (the recipe the build hashed), never ~/build/image live. A floor file of
  any other form fails closed. The 02-d1.sh cells (R-2: exactly one `gh=N.N.N` marker) run in a container (support.py).
The text and script cells run anywhere with a bash 5 and, for the key cells, gpg on PATH; without them they FAIL.
"""
import atexit
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tests.hetzner.support import GOOD_MAIN, REPO, Sandbox, bash5, needs_container
from tests.hetzner.test_build import OLD, VERSION, Rig, full_rig, recipe

IMAGE = os.path.join(REPO, 'linux-docker', 'image')
DOCKERFILE = os.path.join(IMAGE, 'Dockerfile')
CHECK = os.path.join(IMAGE, 'apt-key-pinned.sh')
FLOOR_OK = os.path.join(IMAGE, 'gh-floor-ok.sh')
FLOOR = os.path.join(IMAGE, 'gh-floor')
KEY = os.path.join(IMAGE, 'githubcli-archive-key.asc')
STUDIO = os.path.join(REPO, 'bin', 'linux-image-build')
D1 = os.path.join(REPO, 'linux-docker', 'setup', '02-d1.sh')
ZSH = '/bin/zsh'
KEYRING = '/etc/apt/keyrings/githubcli-archive-keyring.gpg'
FPR_RE = re.compile(r'[0-9A-F]{40}')


def text(path):
    with open(path) as f:
        return f.read()


def need_bash(test):
    b = bash5()
    if not b:
        test.fail("no bash 5 on PATH: linux-docker/ runs under the host's bash 5 (Homebrew's on a Mac)")
    return b


def need_gpg(test):
    g = shutil.which('gpg')
    if not g:
        test.fail('no gpg on PATH: these cells need it (the hetzner CI jobs install gnupg; support.require_tools)')
    return g


# ---- fixture keys, made once per run of this module (a primary key with a subkey each; no network)

_KEYS = {}


def keys(test):
    """{name: path}: pin, other (each `gpg --export`, binary: the dearmored shape the Dockerfile checks), pin-asc
    (armored, the committed file's shape), pin-other and other-pin (both primaries in one file, each order), empty;
    and the fingerprints of the two primaries and of the pin's subkey (fpr:pin, fpr:other, fpr:pin-sub)."""
    if _KEYS:
        return _KEYS
    gpg = need_gpg(test)
    d = tempfile.mkdtemp(prefix='ghk-')
    home = os.path.join(d, 'g')
    os.mkdir(home, 0o700)

    def stop():
        subprocess.run(['gpgconf', '--homedir', home, '--kill', 'all'], capture_output=True, stdin=subprocess.DEVNULL)
        shutil.rmtree(d, True)
    atexit.register(stop)

    def run(*a):
        r = subprocess.run([gpg, '--homedir', home, '--batch', '--pinentry-mode', 'loopback', '--passphrase', '']
                           + list(a), capture_output=True, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise AssertionError('gpg %s: %s' % (' '.join(a), r.stderr.decode('utf-8', 'replace')))
        return r.stdout
    out = {}
    for n in ('pin', 'other'):
        uid = 'liveapp h4 test %s <%s@example.invalid>' % (n, n)
        run('--quick-gen-key', uid, 'ed25519', 'sign', 'never')
        rows = [l.split(':') for l in run('--list-keys', '--with-colons', uid).decode().splitlines()]
        fprs = [r[9] for r in rows if r[0] == 'fpr']
        run('--quick-add-key', fprs[0], 'cv25519', 'encr', 'never')
        rows = [l.split(':') for l in run('--list-keys', '--with-colons', uid).decode().splitlines()]
        kinds = [r[0] for r in rows if r[0] in ('pub', 'sub', 'fpr')]
        fprs = [r[9] for r in rows if r[0] == 'fpr']
        if kinds != ['pub', 'fpr', 'sub', 'fpr']:
            raise AssertionError('fixture %s is not one primary key with one subkey: %r' % (n, kinds))
        out['fpr:' + n], out['fpr:%s-sub' % n] = fprs
        b = run('--export', fprs[0])
        out[n] = os.path.join(d, n + '.gpg')
        with open(out[n], 'wb') as f:
            f.write(b)
        if n == 'pin':
            out['pin-asc'] = os.path.join(d, 'pin.asc')
            with open(out['pin-asc'], 'wb') as f:
                f.write(run('--armor', '--export', fprs[0]))
    for a, b in (('pin', 'other'), ('other', 'pin')):
        out[a + '-' + b] = os.path.join(d, '%s-%s.gpg' % (a, b))
        with open(out[a + '-' + b], 'wb') as f:
            for n in (a, b):
                with open(out[n], 'rb') as g:
                    f.write(g.read())
    out['empty'] = os.path.join(d, 'empty.gpg')
    open(out['empty'], 'wb').close()
    subprocess.run(['gpgconf', '--homedir', home, '--kill', 'all'], capture_output=True, stdin=subprocess.DEVNULL)
    _KEYS.update(out)
    return _KEYS


def primaries(test, path):
    """The fingerprints of FILE's primary keys, in order, read here (an independent reading: each `pub`'s next fpr)."""
    gpg = need_gpg(test)
    home = tempfile.mkdtemp(prefix='ghp-')
    test.addCleanup(shutil.rmtree, home, True)
    r = subprocess.run([gpg, '--homedir', home, '--batch', '--show-keys', '--with-colons', path], capture_output=True,
                       text=True, stdin=subprocess.DEVNULL)
    subprocess.run(['gpgconf', '--homedir', home, '--kill', 'all'], capture_output=True, stdin=subprocess.DEVNULL)
    out, want = [], False
    for l in r.stdout.splitlines():
        f = l.split(':')
        if f[0] == 'pub':
            want = True
        elif f[0] == 'fpr' and want:
            out.append(f[9])
            want = False
    return out


# FIXTURES: name -> the verdict of THE RULE (both copies must give it)
VERDICTS = {'pin': True, 'pin-asc': True, 'pin-other': False, 'other-pin': False, 'other': False, 'empty': False}


class Copies:
    """The two copies of THE RULE, run on a fixture with the pin's fingerprint: True (passes) or False (refused)."""

    def __init__(self, test):
        self.t = test
        self.bash = need_bash(test)
        self.gpg = need_gpg(test)
        self.d = tempfile.mkdtemp(prefix='ghc-')
        test.addCleanup(shutil.rmtree, self.d, True)
        self.home = os.path.join(self.d, 'gnupg')
        os.mkdir(self.home, 0o700)
        test.addCleanup(subprocess.run, ['gpgconf', '--homedir', self.home, '--kill', 'all'], capture_output=True,
                        stdin=subprocess.DEVNULL)
        self.env = {'PATH': os.path.dirname(self.gpg) + ':/usr/bin:/bin', 'TMPDIR': self.d, 'GNUPGHOME': self.home,
                    'LC_ALL': 'C'}

    def check(self, path, pin, script=CHECK):
        """apt-key-pinned.sh (or a copy of it, SCRIPT): the CompletedProcess."""
        return subprocess.run([self.bash, script, path, pin], capture_output=True, text=True, env=self.env,
                              stdin=subprocess.DEVNULL, timeout=120)

    def studio_text(self):
        """bin/linux-image-build's key_pinned, as written (exactly one definition)."""
        fs = re.findall(r'(?ms)^key_pinned\(\) \{.*?^\}$', text(STUDIO))
        self.t.assertEqual(len(fs), 1, 'bin/linux-image-build: key_pinned() is not defined once')
        return fs[0]

    def studio(self, path, pin, func=None):
        """key_pinned in zsh -f, its guest run here: gexec runs its command, die prints and exits 1. True / False."""
        f = func if func is not None else self.studio_text()
        script = os.path.join(self.d, 'studio.zsh')
        with open(script, 'w') as fh:
            fh.write('gexec() { "$@" }\ndie() { print -r -- "STOP $*"; exit 1 }\n%s\nkey_pinned $1 $2 "the key"\n'
                     'print OK\n' % f)
        r = subprocess.run([ZSH, '-f', script, path, pin], capture_output=True, text=True, env=self.env,
                           stdin=subprocess.DEVNULL, timeout=120)
        self.t.assertIn(r.returncode, (0, 1), r.stdout + r.stderr)
        self.t.assertEqual(r.stdout.endswith('OK\n'), r.returncode == 0, r.stdout + r.stderr)
        return r.returncode == 0


class TheCheck(unittest.TestCase):
    def test_the_pin_alone_passes_and_every_other_shape_is_refused_naming_what_it_saw(self):
        """A1 (both orders: S-5): the pin with its subkey, binary or armored: exit 0; the pin and another primary (each
        order): exit 1 naming both fingerprints; the other alone: exit 1 naming it; an empty file: exit 1. The subkey
        is never read as a primary."""
        k = keys(self)
        c = Copies(self)
        for name, want in VERDICTS.items():
            with self.subTest(name):
                r = c.check(k[name], k['fpr:pin'])
                self.assertEqual(r.returncode, 0 if want else 1, r.stdout + r.stderr)
                if want:
                    self.assertIn('OK', r.stdout)
                    continue
                self.assertIn('FAIL', r.stderr)
                for n in ('pin', 'other'):
                    if n in name.split('-'):
                        self.assertIn(k['fpr:' + n], r.stderr, 'the refusal names %s' % n)
                self.assertNotIn(k['fpr:pin-sub'], r.stderr, 'a subkey is no primary key')
        r = c.check(k['pin'], k['fpr:other'])           # the control: the same file, another pin
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_usage(self):
        c = Copies(self)
        for args in ([], ['f'], ['f', '7f38bbb59d064dbcb3d84d725612b36462313325'], ['f', 'ABC'], ['f', 'x', 'y']):
            with self.subTest(args):
                r = subprocess.run([c.bash, CHECK] + args, capture_output=True, text=True, env=c.env,
                                   stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn('usage', r.stderr)


class TheStudiosRule(unittest.TestCase):
    def test_both_copies_give_every_fixture_the_same_verdict(self):
        """R-4's AGREEMENT cell: apt-key-pinned.sh and bin/linux-image-build's key_pinned on the same fixtures, with
        the same pin, give each fixture its verdict (VERDICTS). The zsh copy runs where /bin/zsh exists."""
        k = keys(self)
        c = Copies(self)
        zsh = os.path.exists(ZSH)
        for name, want in VERDICTS.items():
            with self.subTest(name):
                r = c.check(k[name], k['fpr:pin'])
                self.assertIn(r.returncode, (0, 1), r.stdout + r.stderr)   # it ran: a missing copy is no verdict
                self.assertEqual(r.returncode == 0, want, 'apt-key-pinned.sh')
                if zsh:
                    self.assertEqual(c.studio(k[name], k['fpr:pin']), want, 'key_pinned')

    def test_a_first_primary_only_copy_of_either_is_caught(self):
        """The fixtures' power (S-5): each copy with its awk changed to read only the FIRST primary passes the pin-first
        two-key file, which its verdict refuses; the other order still fails, so only the pin-first fixture catches
        it. The mutant's text is checked to differ (it ran)."""
        k = keys(self)
        c = Copies(self)
        real = text(CHECK)
        awk = "$1 == \"pub\" {p = 1; next}"
        self.assertEqual(real.count(awk), 1, 'apt-key-pinned.sh: the awk rule is not written once')
        m = os.path.join(c.d, 'first-only.sh')
        with open(m, 'w') as f:
            f.write(real.replace(awk, "$1 == \"pub\" && !n {p = 1; n = 1; next}"))
        self.assertEqual(c.check(k['pin-other'], k['fpr:pin'], m).returncode, 0, 'the mutant did not pass pin-first')
        self.assertEqual(c.check(k['other-pin'], k['fpr:pin'], m).returncode, 1)
        self.assertEqual(c.check(k['pin-other'], k['fpr:pin']).returncode, 1, 'the real copy')
        if os.path.exists(ZSH):
            st = c.studio_text()
            self.assertEqual(st.count(awk), 1, 'key_pinned: the awk rule is not written once')
            mut = st.replace(awk, '$1 == "pub" && !n {p = 1; n = 1; next}')
            self.assertNotEqual(mut, st)
            self.assertTrue(c.studio(k['pin-other'], k['fpr:pin'], mut), 'the zsh mutant did not pass pin-first')
            self.assertFalse(c.studio(k['pin-other'], k['fpr:pin']), 'the real key_pinned')


def instructions(t):
    """The Dockerfile's instructions: comment lines dropped, continuation lines joined (one string each)."""
    out, cur = [], ''
    for l in t.splitlines():
        if not cur and (not l.strip() or l.startswith('#')):
            continue
        cur += l
        if cur.endswith('\\'):
            cur = cur[:-1]
            continue
        out.append(' '.join(cur.split()))
        cur = ''
    return out


FLOOR_CMD = ('bash /tmp/gh/gh-floor-ok.sh /tmp/gh/gh-floor '
             '"$(gh --version | sed -n \'1s/^gh version \\([^ ]*\\).*/\\1/p\')"')
STEPS = (('keyrings', r'install -d -m 755 /etc/apt/keyrings'),
         ('gpg home', r'install -d -m 700 /tmp/gh/gnupg'),
         ('dearmor', r'gpg --homedir /tmp/gh/gnupg --batch --dearmor -o (\S+) /tmp/gh/(\S+)'),
         ('mode', r'chmod 644 (\S+)'),
         ('check', r'bash /tmp/gh/apt-key-pinned\.sh (\S+) ([0-9A-F]{40})'),
         ('source', r'echo "deb \[arch=(.+?) signed-by=(\S+)\] https://cli\.github\.com/packages stable main" > '
                    r'/etc/apt/sources\.list\.d/github-cli\.list'),
         ('update', r'apt-get update'),
         ('install', r'DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gh'),
         ('floor', re.escape(FLOOR_CMD)),
         ('lists removed', r'rm -rf /var/lib/apt/lists/\* /tmp/gh'))


def gh_why(t):
    """The reasons the Dockerfile text T breaks D3 / R-1 (a) / R-7 / S-4 ([] when it holds), and the pin its check
    names (R-4's one home on this host): (reasons, pin)."""
    why, pin = [], None
    ins = instructions(t)
    apt = [i for i in ins if i.startswith('RUN ') and 'bubblewrap' in i]
    if len(apt) != 1:
        why.append('not ONE Ubuntu apt RUN (the one with bubblewrap): %d' % len(apt))
    elif re.search(r'(^|\s)gh(\s|$)', apt[0].split('apt-get install', 1)[-1].split('&&')[0]):
        why.append("Ubuntu's apt line installs gh")
    cli = [n for n, i in enumerate(ins) if 'cli.github.com' in i]
    if len(cli) != 1 or not ins[cli[0]].startswith('RUN '):
        why.append('not ONE RUN that names cli.github.com: %r' % [ins[n] for n in cli])
        return why, pin
    run = ins[cli[0]][4:]
    for bad in (';', '||', 'set +e'):
        if bad in run:
            why.append('the gh RUN has %r: every command must be joined by &&' % bad)
    cmds = [c.strip() for c in run.split('&&')]
    at, m = {}, {}
    for name, pat in STEPS:
        hits = [n for n, c in enumerate(cmds) if re.fullmatch(pat, c)]
        if len(hits) != 1:
            why.append('the gh RUN: not one %r command (%s): %d' % (name, pat, len(hits)))
        else:
            at[name], m[name] = hits[0], re.fullmatch(pat, cmds[hits[0]])
    if len(at) == len(STEPS):
        got = [k for k, _ in sorted(at.items(), key=lambda x: x[1])]
        if got != [k for k, _ in STEPS]:
            why.append('the gh RUN in the wrong order: %s' % ', '.join(got))
    if len(cmds) != len(at):
        why.append('the gh RUN has a command no step names: %r' % [c for n, c in enumerate(cmds) if n not in at.values()])
    if all(k in m for k in ('dearmor', 'mode', 'check', 'source')):
        pin = m['check'].group(2)
        paths = (m['dearmor'].group(1), m['mode'].group(1), m['check'].group(1), m['source'].group(2))
        if set(paths) != {KEYRING}:
            why.append('the dearmor output, its mode, the checked file and signed-by are not ONE path, %s: %s'
                       % (KEYRING, ' '.join(paths)))
        if m['source'].group(1) != '$(dpkg --print-architecture)':
            why.append('the source names its architecture by hand: %s' % m['source'].group(1))
        cp = [n for n, i in enumerate(ins) if i.startswith('COPY ') and i.endswith(' /tmp/gh/')]
        if len(cp) != 1 or sorted(ins[cp[0]].split()[1:-1]) != ['apt-key-pinned.sh', 'gh-floor', 'gh-floor-ok.sh',
                                                                'githubcli-archive-key.asc']:
            why.append('not ONE COPY of the four files to /tmp/gh/: %r' % [ins[n] for n in cp])
        elif m['dearmor'].group(2) != 'githubcli-archive-key.asc' or cp[0] > cli[0]:
            why.append('the dearmor does not read the key file COPY put in /tmp/gh/ before the gh RUN')
    if [n for n, i in enumerate(ins) if '/tmp/gh/' in i and not i.startswith('COPY ')] != cli:
        why.append('/tmp/gh/ is used outside the gh RUN')
    return why, pin


class TheDockerfile(unittest.TestCase):
    def test_the_shipped_recipe_installs_gh_from_github_s_repository_after_the_check(self):
        why, pin = gh_why(text(DOCKERFILE))
        self.assertEqual(why, [])
        self.assertRegex(pin or '', r'^[0-9A-F]{40}$')

    def test_each_mutant_draws_its_reason(self):
        """A3 / R-1 (a)'s mutants, each a text edit of the shipped Dockerfile (the edit must apply: the mutant ran)."""
        t = text(DOCKERFILE)
        chk = re.search(r'bash /tmp/gh/apt-key-pinned\.sh \S+ [0-9A-F]{40}', t).group(0)
        upd = ' && apt-get update \\\n'
        line = ' && ' + chk + ' \\\n'

        def sub(s, old, new):
            self.assertEqual(s.count(old), 1, 'the edit does not apply once: %r' % old)
            return s.replace(old, new)
        rows = (
            ('|| true after the check', lambda s: sub(s, chk, chk + ' || true'), '||'),
            ('; in place of an &&', lambda s: sub(s, upd, ' ; apt-get update \\\n'), "';'"),
            ('set +e first', lambda s: sub(s, 'RUN install -d -m 755', 'RUN set +e && install -d -m 755'), 'set +e'),
            ('signed-by another file', lambda s: sub(s, 'signed-by=' + KEYRING, 'signed-by=/etc/apt/keyrings/o.gpg'),
             'ONE path'),
            ('the check names another file',
             lambda s: sub(s, chk, chk.replace(KEYRING, '/tmp/gh/githubcli-archive-key.asc')), 'ONE path'),
            ('no check', lambda s: sub(s, line, ''), "not one 'check'"),
            ('the check after apt-get update', lambda s: sub(sub(s, line, ''), upd, upd + line), 'wrong order'),
            ("gh back in Ubuntu's apt line", lambda s: sub(s, 'bubblewrap build-essential', 'bubblewrap gh build-essential'),
             "Ubuntu's apt line installs gh"),
            ('arch by hand', lambda s: sub(s, 'arch=$(dpkg --print-architecture)', 'arch=amd64'), 'by hand'),
            ('no floor', lambda s: sub(s, ' && ' + FLOOR_CMD + ' \\\n', ''), "not one 'floor'"),
            ('another command', lambda s: sub(s, upd, upd + ' && true \\\n'), 'no step names'),
        )
        for why, edit, says in rows:
            with self.subTest(why):
                m = edit(t)
                self.assertNotEqual(m, t)
                got, _ = gh_why(m)
                self.assertTrue([w for w in got if says in w], got)


class TheKey(unittest.TestCase):
    def test_the_committed_key_has_one_primary_key_and_it_is_the_dockerfile_s_pin(self):
        """D1 + R-4's REQUIRED cell: the committed key's only primary fingerprint is the pin the Dockerfile's check
        names (its one spelling on this host), and apt-key-pinned.sh passes the file with it. Control: a copy with a
        planted second primary key is refused (A2)."""
        _, pin = gh_why(text(DOCKERFILE))
        self.assertTrue(pin)
        self.assertEqual(primaries(self, KEY), [pin])
        self.assertTrue(text(KEY).startswith('-----BEGIN PGP PUBLIC KEY BLOCK-----\n'), 'armored')
        c = Copies(self)
        r = c.check(KEY, pin)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        k = keys(self)
        planted = os.path.join(c.d, 'planted.asc')
        with open(planted, 'w') as f:
            f.write(text(KEY) + text(k['pin-asc']))
        self.assertEqual(primaries(self, planted), [pin, k['fpr:pin']])
        r = c.check(planted, pin)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(k['fpr:pin'], r.stderr)


class TheFloor(unittest.TestCase):
    def run_it(self, floor_text, version, name='gh-floor'):
        b = need_bash(self)
        d = tempfile.mkdtemp(prefix='ghf-')
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, name)
        if floor_text is not None:
            with open(p, 'wb') as f:
                f.write(floor_text)
        return subprocess.run([b, FLOOR_OK, p, version], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, timeout=60)

    def test_the_shipped_floor_is_one_line(self):
        """S-4: one file holds the floor, one line N.N.N, in image/ (so a raised floor is a new recipe)."""
        self.assertRegex(text(FLOOR), r'^[0-9]+\.[0-9]+\.[0-9]+\n\Z')

    def test_a_floor_file_of_any_other_form_fails_closed(self):
        """T-1: empty, missing, `2.102`, `v2.102.0`, `2.102.0\\r`, two lines, a blank second line, a NUL: exit 1 (the
        line says what is wrong with it); the controls `2.102.0\\n` and `2.102.0` (no newline) pass."""
        for why, t in (('empty', b''), ('missing', None), ('two fields', b'2.102\n'), ('a v', b'v2.102.0\n'),
                       ('a CR', b'2.102.0\r\n'), ('two lines', b'2.102.0\n2.103.0\n'), ('a blank line', b'2.102.0\n\n'),
                       ('a space', b'2.102.0 \n'), ('a NUL', b'2.102.0\x00\n'), ('four fields', b'2.102.0.1\n')):
            with self.subTest(why):
                r = self.run_it(t, '2.104.0')
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('FAIL', r.stderr)
                self.assertIn('floor', r.stderr)
        for t in (b'2.102.0\n', b'2.102.0'):
            with self.subTest(control=t):
                r = self.run_it(t, '2.104.0')
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_compare_is_field_by_field_as_numbers(self):
        """D4 / R-2's compare (A4): with the shipped floor, 2.101.0 and 2.45.0 fail naming the version (a string
        compare would pass 2.45.0); 2.102.0, 2.102.1, 2.104.0 and 10.0.0 pass; a version not N.N.N fails; and a floor
        one patch above the version fails (T-4's shape)."""
        floor = text(FLOOR).encode()
        for v, ok in (('2.101.0', False), ('2.45.0', False), ('1.999.999', False), ('2.102.0', True),
                      ('2.102.1', True), ('2.104.0', True), ('10.0.0', True), ('2.200.0', True), ('', False),
                      ('2.x', False), ('v2.104.0', False), ('2.104', False), ('2.104.0 ', False)):
            with self.subTest(v):
                r = self.run_it(floor, v)
                self.assertEqual(r.returncode, 0 if ok else 1, r.stdout + r.stderr)
                self.assertIn('[%s]' % v, r.stdout + r.stderr, 'the line names what it read')
        r = self.run_it(b'2.104.1\n', '2.104.0')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_usage(self):
        b = need_bash(self)
        for args in ([], [FLOOR], [FLOOR, '2.104.0', 'x']):
            with self.subTest(args):
                r = subprocess.run([b, FLOOR_OK] + args, capture_output=True, text=True, stdin=subprocess.DEVNULL)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class D1Text(unittest.TestCase):
    def test_step_6_b_reads_the_floor_from_the_build_context(self):
        """T-2: 02-d1.sh runs the ONE compare from the context's copy of image/ (the recipe the build hashed): both the
        script and the floor file by $CTX; never ~/build/image ($B/image) for them; the context outlives that check."""
        t = text(D1)
        calls = re.findall(r'^.*gh-floor-ok\.sh.*$', t, re.M)
        self.assertEqual([c for c in calls if not c.lstrip().startswith('#')],
                         [c for c in calls if '"$CTX/gh-floor-ok.sh" "$CTX/gh-floor"' in c])
        self.assertEqual(len([c for c in calls if not c.lstrip().startswith('#')]), 1, calls)
        self.assertNotIn('$B/image/gh-floor', t)
        rm = t.index('rm -rf -- "${CTX:?}"; trap - EXIT')
        self.assertLess(t.index('"$CTX/gh-floor-ok.sh"'), rm)
        self.assertLess(rm, t.index('say "7. (c)'))


@needs_container
class D1Floor(unittest.TestCase):
    """02-d1.sh step 6 (b) (R-2, T-1, T-2): the image prints `gh=<version>`; exactly one such line, N.N.N, at or above
    image/gh-floor (gh-floor-ok.sh, from the build context) is a pass; else no build record (and, in the full run, no
    image.ref), and the FAIL line names what it read."""

    def marker(self, lines, mode='build'):
        g = full_rig(self) if mode == 'full' else Rig(self)
        g.sb.docker['main_checks'] = GOOD_MAIN.replace('gh=2.104.0\n', lines)
        r = g.sb.d1() if mode == 'full' else g.sb.d1('build', VERSION)
        return g, r

    def test_good_main_carries_the_marker(self):
        self.assertEqual(GOOD_MAIN.count('gh=2.104.0\n'), 1)

    def test_one_marker_at_or_above_the_floor_passes(self):
        for v in ('2.102.0', '2.104.0'):
            with self.subTest(v):
                g, r = self.marker('gh=%s\n' % v)
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.records(), ['%s-%s' % (VERSION, recipe(g.sb.build))])
                self.assertRegex(r.stdout, r'(?m)^OK .*\[%s\]' % re.escape(v))

    def test_any_other_marker_writes_no_record(self):
        for why, lines, says in (('below the floor', 'gh=2.101.0\n', '[2.101.0]'), ('2.45.0', 'gh=2.45.0\n', '[2.45.0]'),
                                 ('no marker', '', '0 gh= lines'), ('an empty marker', 'gh=\n', '[]'),
                                 ('no version', 'gh=2.x\n', '[2.x]'),
                                 ('two markers', 'gh=2.104.0\ngh=2.104.0\n', '2 gh= lines')):
            with self.subTest(why):
                g, r = self.marker(lines)
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.records(), [])
                self.assertRegex(r.stdout, r'(?m)^FAIL .*%s' % re.escape(says))
                self.assertIn('no record', r.stdout.splitlines()[-1])

    def test_the_full_run_writes_no_image_ref_below_the_floor(self):
        g, r = self.marker('gh=2.101.0\n', mode='full')
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertFalse(g.image_ref())
        self.assertEqual(g.records(), [])
        g, r = self.marker('gh=2.102.0\n', mode='full')          # the control
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertTrue(g.image_ref())

    def test_a_floor_file_of_another_form_fails_closed(self):
        """T-1 through 02-d1.sh: ~/build/image/gh-floor `2.102` (a new recipe, built): the check fails, no record."""
        g = Rig(self)
        g.sb.write(os.path.join(g.sb.build, 'image', 'gh-floor'), '2.102\n')
        r = g.sb.d1('build', VERSION)
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.records(), [])
        self.assertRegex(r.stdout, r'(?m)^FAIL .*floor')

    def test_the_floor_is_the_one_the_build_hashed(self):
        """T-2: ~/build/image/gh-floor raised to 9.0.0 while the image builds (after the recipe was copied and hashed):
        the check reads the context's copy (2.102.0), so it passes, and the record names the recipe the build hashed.
        The control: the same raise BEFORE the build fails the check."""
        for when in ('during', 'before'):
            with self.subTest(when):
                g = Rig(self)
                p = os.path.join(g.sb.build, 'image', 'gh-floor')
                hashed = recipe(g.sb.build)
                if when == 'during':
                    g.sb.docker['after_build'] = {p: '9.0.0\n'}
                else:
                    g.sb.write(p, '9.0.0\n')
                r = g.sb.d1('build', VERSION)
                if when == 'during':
                    self.assertEqual(text(p), '9.0.0\n', 'the raise did not happen')
                    self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                    self.assertEqual(g.records(), ['%s-%s' % (VERSION, hashed)])
                else:
                    self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                    self.assertEqual(g.records(), [])


@needs_container
class TheRecipe(unittest.TestCase):
    def test_the_floor_and_the_three_new_files_are_part_of_the_recipe(self):
        """T-2: rr_recipe's list of the shipped image/ (the names it hashes) holds gh-floor, gh-floor-ok.sh,
        apt-key-pinned.sh and the key file, beside the Dockerfile and install-runner.sh."""
        sb = Sandbox(self)
        r = sb.lib('rr_recipe "$1" || exit 1; printf "%s\\n" "$RR_NAMES"', os.path.join(sb.build, 'image'))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.split(), ['Dockerfile', 'apt-key-pinned.sh', 'gh-floor', 'gh-floor-ok.sh',
                                            'githubcli-archive-key.asc', 'install-runner.sh'])


if __name__ == '__main__':
    unittest.main()
