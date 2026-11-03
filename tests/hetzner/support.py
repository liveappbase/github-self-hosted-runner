"""Helpers for the tests of linux-docker/ (the Linux host's scripts), stdlib only.

Those scripts run on a Linux host (bash 5, GNU coreutils, OpenSSL, curl), so these cells run IN A THROWAWAY LINUX
CONTAINER as root (RUN_LINE by hand; the ubuntu rows of .github/workflows/release-check.yml in CI). Where they cannot
run (not Linux, or not root) each cell SKIPS. On Linux as root with no container's /.dockerenv each cell FAILS before
it runs: a copy that ran as root on a real host could still reach that host's programs, and a skip there would let a
CI row pass with no cell run (verdict, test_support.py). In a container that lacks a tool the cells need, they FAIL.

A cell makes a Sandbox: a temporary folder, removed by the cell's cleanup. In it
- home/build is linux-docker/ (the host's ~/build) plus setup/tls-excluded-spki from the repository's top-level setup/
  (the install line ships it there). Its scripts are the REAL ones with ONLY their pin lines rewritten (PIN_REWRITES):
  each rewrite must match exactly once, and the copy may then hold no host path (LEFT_OUT) at all;
- host.conf is the host config (root's file, 0644): host.conf.example's values, RUN_USER=root (the cells run as root);
- stubs/ holds the substitutes, each logging its calls to logs/: docker (driven by docker.json), systemctl, nsenter,
  ip, and curl, which hands every https call to the REAL /usr/bin/curl and answers only the registry and rootlesskit;
- a local HTTPS server (FakeGitHub) stands in for GitHub's API and its downloads. Its certificate is signed by a test
  CA that the source CA bundle (the container's real bundle, plus that CA) holds.
"""
import atexit
import hashlib
import http.server
import io
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUN_LINE = ('docker run --rm --network none -v "$PWD":/w:ro -w /w IMAGE python3 -I -B -m unittest discover -s '
            'tests/hetzner -t .   (IMAGE: an Ubuntu 24.04 or 26.04 with python3, openssl, curl and ca-certificates; '
            'the ubuntu rows of .github/workflows/release-check.yml run them so too)')
SYSTEM_PATH = '/usr/bin:/bin:/usr/sbin:/sbin'
SYSTEM_BUNDLE = '/etc/ssl/certs/ca-certificates.crt'
OPENSSL = '/usr/bin/openssl'
REAL_CURL = '/usr/bin/curl'
RS_USER = 'ci-rs'                    # host.conf.example's RS_USER
REGISTRY_PORT = '27500'              # host.conf.example's REGISTRY_PORT
IMAGE_NAME = 'linux-runner'          # host.conf.example's IMAGE_NAME
PROFILE = 'seccomp-userns-min-v29.9.0.json'
ARCH = {'x86_64': 'x64', 'aarch64': 'arm64'}.get(os.uname().machine, '?')
FLOOR = 100


def verdict(platform=None, euid=None, dockerenv=None):
    """'run': Linux, root, and a container's /.dockerenv. 'skip': not Linux or not root (the cells cannot run there).
    'fail': Linux as root with no /.dockerenv. The cells could run, but it may be a real host, so they neither run nor
    pass as skipped: a CI row whose container ever lacked the mark goes red, not green with every cell skipped."""
    platform = sys.platform if platform is None else platform
    euid = os.geteuid() if euid is None else euid
    dockerenv = os.path.exists('/.dockerenv') if dockerenv is None else dockerenv
    if not platform.startswith('linux') or euid != 0:
        return 'skip'
    return 'run' if dockerenv else 'fail'


SKIP_WHY = 'runs only as root in a throwaway Linux container: ' + RUN_LINE
FAIL_WHY = 'Linux as root, but no /.dockerenv: this may be a real host, so these cells do not run (' + RUN_LINE + ')'


def contained(v):
    """The class decorator for verdict v: run the cells, skip them, or fail each one before it runs."""
    def deco(cls):
        if v == 'skip':
            return unittest.skip(SKIP_WHY)(cls)
        if v == 'fail':
            def setUp(self):
                self.fail(FAIL_WHY)
            cls.setUp = setUp
        return cls
    return deco


needs_container = contained(verdict())


def require_tools(test):
    for p in (OPENSSL, REAL_CURL, SYSTEM_BUNDLE, '/usr/bin/sha256sum', '/usr/bin/python3'):
        if not os.path.exists(p):
            test.fail('this container lacks %s, which these cells need (%s)' % (p, RUN_LINE))


def sha256_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---- certificates: the SPKI hash computed here with no openssl (an independent reading of the DER)

def _tlv(b, i):
    """The DER element at b[i]: (tag, start of its value, end of the element)."""
    tag = b[i]
    n = b[i + 1]
    j = i + 2
    if n & 0x80:
        k = n & 0x7f
        n = int.from_bytes(b[j:j + k], 'big')
        j += k
    return tag, j, j + n


def spki_sha256(pem):
    """SHA-256 of a certificate's DER SubjectPublicKeyInfo: tbsCertificate's 7th field (6th with no version)."""
    der = ssl.PEM_cert_to_DER_cert(pem)
    _, cert, _ = _tlv(der, 0)
    _, i, _ = _tlv(der, cert)
    tag, _, end = _tlv(der, i)
    if tag == 0xa0:                       # [0] version
        i = end
    for _ in range(5):                    # serialNumber, signature, issuer, validity, subject
        _, _, i = _tlv(der, i)
    _, _, end = _tlv(der, i)
    return hashlib.sha256(der[i:end]).hexdigest()


PEM_RE = re.compile(r'-----BEGIN CERTIFICATE-----\n.*?\n-----END CERTIFICATE-----\n', re.S)


def pems(text):
    return PEM_RE.findall(text)


class Pki:
    """Two test CAs (EC P-256): CA signs the HTTPS server's certificate; OTHER is a different key that signs nothing."""

    def __init__(self, d):
        def ossl(*a):
            subprocess.run((OPENSSL,) + a, cwd=d, check=True, capture_output=True, stdin=subprocess.DEVNULL)
        for n in ('ca', 'other'):
            ossl('req', '-x509', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes',
                 '-keyout', n + '.key', '-out', n + '.pem', '-days', '3', '-subj', '/CN=liveapp test ' + n,
                 '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        with open(os.path.join(d, 'ext.cnf'), 'w') as f:
            f.write('subjectAltName=IP:127.0.0.1\nbasicConstraints=critical,CA:FALSE\n'
                    'keyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n')
        ossl('req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes', '-keyout',
             'srv.key', '-out', 'srv.csr', '-subj', '/CN=127.0.0.1')
        ossl('x509', '-req', '-in', 'srv.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key', '-set_serial', '2', '-days', '3',
             '-out', 'srv.pem', '-extfile', 'ext.cnf')
        self.dir = d
        with open(os.path.join(d, 'ca.pem')) as f:
            self.ca_pem = f.read()
        with open(os.path.join(d, 'other.pem')) as f:
            self.other_pem = f.read()
        self.ca_spki = spki_sha256(self.ca_pem)
        self.other_spki = spki_sha256(self.other_pem)
        self.srv_cert = os.path.join(d, 'srv.pem')
        self.srv_key = os.path.join(d, 'srv.key')


_PKI = []


def pki():
    if not _PKI:
        d = tempfile.mkdtemp(prefix='hz-pki-')
        atexit.register(shutil.rmtree, d, True)
        _PKI.append(Pki(d))
    return _PKI[0]


def tarball(version, extra=(), omit=()):
    """A small runner tarball of the real one's shape: bin/, externals/ and root files, members named ./… ; extra:
    (name, data) members added at the end (data None = a folder, a str starting with -> = a symlink to the rest);
    omit: top-level names left out."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz', format=tarfile.GNU_FORMAT) as t:
        def add(name, data=None):
            if name.split('/')[0] in omit:
                return
            i = tarfile.TarInfo('./' + name)
            i.mtime = 1761955200
            if data is not None and data.startswith('->'):
                i.type, i.linkname = tarfile.SYMTYPE, data[2:]
                t.addfile(i)
            elif data is None:
                i.type, i.mode = tarfile.DIRTYPE, 0o755
                t.addfile(i)
            else:
                b = data.encode()
                i.size, i.mode = len(b), 0o755
                t.addfile(i, io.BytesIO(b))
        for d in ('bin', 'externals', 'externals/node20'):
            add(d)
        add('bin/Runner.Listener', 'listener %s\n' % version)
        add('externals/node20/node', 'node\n')
        for f in ('config.sh', 'run.sh', 'env.sh'):
            add(f, '#!/bin/bash\necho %s\n' % version)
        for name, data in extra:
            add(name, data)
    return buf.getvalue()


# ---- GitHub, served locally over HTTPS

class FakeGitHub:
    """routes: path -> (status, headers, body). seen: the path of every request that reached HTTP."""

    def __init__(self, test):
        self.routes = {}
        self.seen = []
        gh = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                gh.seen.append(self.path)
                status, headers, body = gh.routes.get(self.path, (404, {}, b'{"message":"Not Found"}'))
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(pki().srv_cert, pki().srv_key)
        self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        self.httpd.handle_error = lambda *a: None
        t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        t.start()

        def stop():
            self.httpd.shutdown()
            self.httpd.server_close()
        test.addCleanup(stop)
        self.base = 'https://127.0.0.1:%d' % self.httpd.server_address[1]

    def release(self, version, tarball, digest=None, tag=None, published='2026-10-20T12:00:00Z', status=200,
                latest=False):
        """Serve release v<version> (or /releases/latest) with ONE runner asset for this machine, whose download
        redirects (as GitHub's does) to the tarball bytes; digest defaults to the tarball's sha256."""
        name = 'actions-runner-linux-%s-%s.tar.gz' % (ARCH, version)
        dl = '/actions/runner/releases/download/v%s/%s' % (version, name)
        body = {'tag_name': tag or 'v' + version, 'name': 'v' + version, 'draft': False, 'prerelease': False,
                'published_at': published,
                'assets': [{'name': name + '.sha256', 'digest': 'sha256:' + '0' * 64,
                            'browser_download_url': self.base + dl + '.sha256'},
                           {'name': name, 'digest': digest or 'sha256:' + hashlib.sha256(tarball).hexdigest(),
                            'browser_download_url': self.base + dl}]}
        api = '/repos/actions/runner/releases/' + ('latest' if latest else 'tags/v' + version)
        self.routes[api] = (status, {'Content-Type': 'application/json'}, json.dumps(body).encode())
        self.routes[dl] = (302, {'Location': self.base + '/objects/' + name}, b'')
        self.routes['/objects/' + name] = (200, {'Content-Type': 'application/octet-stream'}, tarball)
        return body


# ---- the substitutes

DOCKER_STUB = r'''#!/usr/bin/python3 -I
# docker, for the cells: logs argv as one JSON line, answers from docker.json (see tests/hetzner/support.py)
import hashlib, json, os, sys
SB = @SB@
a = sys.argv[1:]
with open(SB + '/logs/docker.log', 'a') as f:
    f.write(json.dumps(a) + '\n')
cfg = json.load(open(SB + '/docker.json'))
j = ' '.join(a)
IID = 'sha256:' + 'a' * 64


def out(s='', rc=0):
    sys.stdout.write(s)
    sys.exit(rc)


cmd = a[0] if a else ''
if cmd == 'version':
    out('Server: 29.9.0\n')
if cmd == 'info':
    out(cfg['info'].replace('@HOME@', os.environ['HOME']) + '\n')
if cmd == 'build':
    if cfg.get('build_rc'):
        out('', cfg['build_rc'])
    ctx = a[-1]
    names = sorted(os.listdir(ctx))
    files = {n: hashlib.sha256(open(os.path.join(ctx, n), 'rb').read()).hexdigest() for n in names}
    with open(SB + '/logs/build-ctx.json', 'a') as f:
        f.write(json.dumps({'argv': a, 'files': files, 'mode': oct(os.stat(ctx).st_mode & 0o777)}) + '\n')
    out(IID + '\n')
if cmd == 'push':
    out('')
if cmd == 'rm':
    out('')
if cmd == 'inspect':
    if '{{.Id}}' in j:
        out(IID + '\n')
    if 'RepoDigests' in j:
        out(cfg['repo_digest'] + '\n')
    if '{{.State.Running}}' in j:
        out('true\n')
    if 'bridge.IPAddress' in j:
        out('198.51.100.2\n')
    if 'runners.IPAddress' in j:
        out('198.51.100.7\n')
    if a[-1] == 'runner-registry':
        out('[]\n')
if cmd == 'network':
    if 'Driver' in j:
        out('bridge\n')
    if 'Gateway' in j:
        out('198.51.100.1\n')
    out('[]\n')
if cmd == 'run':
    if '-d' in a:
        out('c' * 64 + '\n')
    if './config.sh' in a:
        out(cfg['config_version'])
    if 'seccomp=unconfined' in j:
        out('ALLOWED\n')
    if any(x.startswith('seccomp=') and x.endswith('.json') for x in a):
        out('bwrap: No permissions to create new namespace\n')
    if 'Seccomp|NoNewPrivs' in j:
        out(cfg['main_checks'])
    if 'ls' in a and '/x' in a:
        out(cfg['ls_out'], cfg['ls_rc'])
    if '/x/net.env' in a:
        out('')
    if 'https://github.com' in a:
        out('200')
    if '/dev/tcp/' in j:
        hp = a[a.index('_') + 1:]
        out(''.join(('REACHED ' if x == cfg['public'] else 'refused ') + x + '\n' for x in hp))
    if 'DNS id=' in j:
        out('DNS id=True rcode=0 answers=1\n')
    if '/v2/' in j:
        out('200')
    if 'SCANNED' in j:
        out(('OPEN %s:8000\n' % a[-1] if a[-1] == '198.51.100.7' else '') + 'SCANNED 65535\n')
out('docker stub: no answer for: ' + j + '\n', 99)
'''

CURL_STUB = r'''#!/usr/bin/python3 -I
# curl, for the cells: logs argv and OPENSSL_X509_TEA_DISABLE; an https call runs the REAL curl; it answers only the
# local registry (curl.json's registry_rc) and rootlesskit's API (a unix socket)
import json, os, sys
SB = @SB@
a = sys.argv[1:]
with open(SB + '/logs/curl.log', 'a') as f:
    f.write(json.dumps({'argv': a, 'tea': os.environ.get('OPENSSL_X509_TEA_DISABLE')}) + '\n')
urls = [x for x in a if '://' in x]
if any(u.startswith('https://') for u in urls):
    os.execv('/usr/bin/curl', ['curl'] + a)
if '--unix-socket' in a:
    sys.stdout.write('{"networkDriver":{"dns":["192.0.2.1"]}}')
    sys.exit(0)
if urls and urls[0].startswith('http://127.0.0.1:') and urls[0].endswith('/v2/'):
    sys.exit(json.load(open(SB + '/curl.json')).get('registry_rc', 0))
sys.stderr.write('curl stub: no answer for: %s\n' % ' '.join(a))
sys.exit(99)
'''

GOOD_MAIN = ('Seccomp: 2\nNoNewPrivs: 1\npid1=docker-init umask=0022\nkeyctl EPERM\nsudo=refused\nbwrap=ok\n'
             'locale=ok\n')


class Sandbox:
    PIN_REWRITES = {
        'setup/02-d1.sh': [('HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=@ROOT@/host.conf\n')],
        'setup/runner-release.sh': [
            ('RR_API=https://api.github.com/repos/actions/runner\n', 'RR_API=@GH@/repos/actions/runner\n'),
            ('RR_DL=https://github.com/actions/runner/releases/download\n',
             'RR_DL=@GH@/actions/runner/releases/download\n'),
            ('RR_SRC=/etc/ssl/certs/ca-certificates.crt\n', 'RR_SRC=@ROOT@/source.pem\n')],
    }
    LEFT_OUT = {'setup/02-d1.sh': ('/etc/liveapp-ci',),
                'setup/runner-release.sh': ('api.github.com', '//github.com', '/etc/ssl')}

    def __init__(self, test):
        v = verdict()
        if v == 'skip':
            raise unittest.SkipTest(SKIP_WHY)
        if v == 'fail':
            test.fail(FAIL_WHY)
        require_tools(test)
        self.test = test
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='hz-'))
        test.addCleanup(shutil.rmtree, self.root, True)
        for d in ('home', 'tmp', 'stubs', 'logs', 'xdg'):
            os.makedirs(self.path(d))
        self.home = self.path('home')
        self.build = self.path('home', 'build')
        shutil.copytree(os.path.join(REPO, 'linux-docker'), self.build, symlinks=True)
        data = os.path.join(REPO, 'setup', 'tls-excluded-spki')
        if os.path.exists(data):
            shutil.copy(data, os.path.join(self.build, 'setup', 'tls-excluded-spki'))
        self.gh = FakeGitHub(test)
        with open(SYSTEM_BUNDLE) as f:
            self.system_bundle = f.read()
        self.write(self.path('source.pem'), self.system_bundle + pki().ca_pem)
        for rel, pairs in self.PIN_REWRITES.items():
            p = os.path.join(self.build, rel)
            if not os.path.exists(p):
                continue
            with open(p) as f:
                text = f.read()
            for old, new in pairs:
                if text.count(old) != 1:
                    raise AssertionError('%s: the pin line %r is in it %d times, want 1' % (rel, old, text.count(old)))
                text = text.replace(old, new.replace('@ROOT@', self.root).replace('@GH@', self.gh.base))
            for h in self.LEFT_OUT[rel]:
                if h in text:
                    raise AssertionError('%s: the copy still names %s: %r' % (
                        rel, h, next(l for l in text.splitlines() if h in l)))
            with open(p, 'w') as f:
                f.write(text)
        with open(os.path.join(REPO, 'linux-docker', 'host.conf.example')) as f:
            conf = f.read()
        if conf.count('\nRUN_USER=ci-run\n') != 1:
            raise AssertionError('host.conf.example: no single RUN_USER=ci-run line')
        self.write(self.path('host.conf'), conf.replace('\nRUN_USER=ci-run\n', '\nRUN_USER=root\n'), 0o644)
        os.makedirs('/home/' + RS_USER, exist_ok=True)   # step 8 must reach RS_USER's home (in the container only)
        sb = repr(self.root)
        self.write(self.path('stubs', 'docker'), DOCKER_STUB.replace('@SB@', sb), 0o755)
        self.write(self.path('stubs', 'curl'), CURL_STUB.replace('@SB@', sb), 0o755)
        for n, body in (('systemctl', 'exit 0'),
                        ('nsenter', 'echo "default via 192.0.2.1 dev tap0"'),
                        ('ip', 'echo "default via 203.0.113.1 dev eth0"')):
            self.write(self.path('stubs', n), '#!/bin/sh\nprintf "%%s\\n" "$*" >> %s/logs/%s.log\n%s\n' % (
                self.root, n, body), 0o755)
        self.docker = {'info': '[name=seccomp,profile=@HOME@/.config/docker/%s name=rootless name=no-new-privileges '
                               'name=cgroupns]' % PROFILE,
                       'repo_digest': 'localhost:%s/%s@sha256:%s' % (REGISTRY_PORT, IMAGE_NAME, 'd' * 64),
                       'config_version': '', 'main_checks': GOOD_MAIN,
                       'ls_out': "ls: cannot open directory '/x': Permission denied\n", 'ls_rc': 2,
                       'public': '203.0.113.10:22'}
        self.curl = {'registry_rc': 0}

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def write(self, path, text, mode=0o644):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)
        os.chmod(path, mode)
        return path

    def env(self):
        return {'HOME': self.home, 'PATH': self.path('stubs') + ':' + SYSTEM_PATH, 'LC_ALL': 'C',
                'TMPDIR': self.path('tmp'), 'XDG_RUNTIME_DIR': self.path('xdg')}

    def lib(self, script, *args):
        """Run bash with the copied runner-release.sh sourced, then script (its $1.. = args)."""
        return subprocess.run(['bash', '-c', 'set -u; . "$0" || exit 9\n' + script,
                               os.path.join(self.build, 'setup', 'runner-release.sh')] + list(args),
                              env=self.env(), cwd=self.home, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=300)

    def d1(self, *args):
        """Run the copied 02-d1.sh with args, docker.json and curl.json written from self.docker and self.curl."""
        self.write(self.path('docker.json'), json.dumps(self.docker))
        self.write(self.path('curl.json'), json.dumps(self.curl))
        return subprocess.run(['bash', os.path.join(self.build, 'setup', '02-d1.sh')] + list(args), env=self.env(),
                              cwd=self.home, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)

    def lines(self, name):
        """The calls of a shell stub (systemctl, nsenter, ip): one line of its arguments each."""
        p = self.path('logs', name + '.log')
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return f.read().splitlines()

    def calls(self, name):
        """The calls of a python stub (docker: its argv; curl: {argv, tea}), one JSON line each."""
        p = self.path('logs', name + '.log')
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return [json.loads(l) for l in f.read().splitlines()]

    def excluded(self, *lines):
        """Replace ~/build/setup/tls-excluded-spki with these lines."""
        return self.write(os.path.join(self.build, 'setup', 'tls-excluded-spki'), ''.join(l + '\n' for l in lines))
