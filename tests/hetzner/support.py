"""Helpers for the tests of linux-docker/ (the Linux host's scripts), stdlib only.

Those scripts run on a Linux host (bash 5, GNU coreutils, OpenSSL, curl), so these cells run IN A THROWAWAY LINUX
CONTAINER as root (RUN_LINE by hand; the hetzner jobs of .github/workflows/release-check.yml in CI). Where they cannot
run (not Linux, or not root) each cell SKIPS. On Linux as root with no container's /.dockerenv each cell FAILS before
it runs: a copy that ran as root on a real host could still reach that host's programs, and a skip there would let a
CI row pass with no cell run (verdict, test_support.py). In a container that lacks a tool the cells need, they FAIL.

A cell makes a Sandbox: a temporary folder, removed by the cell's cleanup. In it
- home/build is linux-docker/ (the host's ~/build) plus setup/tls-excluded-spki from the repository's top-level setup/
  and the decision core, core/ (the install line ships both there: ~/build/setup/ and ~/build/core/). Its scripts are
  the REAL ones with ONLY their pin lines rewritten (PIN_REWRITES; bin/runner-updater's own PATH line among them, so
  the substitutes come first):
  each rewrite must match exactly once, and the copy may then hold no host path (LEFT_OUT) at all;
- host.conf is the host config (root's file, 0644): host.conf.example's values, RUN_USER=root (the cells run as root);
- stubs/ holds the substitutes, each logging its calls to logs/: docker (driven by docker.json; it keeps D1 in
  docker-state.json: each build gets its own image ID, a tag names one image, a push gives that image a digest, and
  the `runners` network and the registry container exist, or not, until a create, run or start makes them),
  systemctl, nsenter, ip, and curl, which hands every https call to the REAL /usr/bin/curl and answers only the
  registry and rootlesskit;
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
import signal
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUN_LINE = ('docker run --rm --network none -v "$PWD":/w:ro -w /w IMAGE python3 -I -B -m unittest discover -s '
            'tests/hetzner -t .   (IMAGE: an Ubuntu 24.04 or 26.04 with python3, openssl, curl, jq and ca-certificates; '
            'the hetzner jobs of .github/workflows/release-check.yml run them so too, in parts)')
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
    for p in (OPENSSL, REAL_CURL, SYSTEM_BUNDLE, '/usr/bin/sha256sum', '/usr/bin/python3', '/usr/bin/jq'):
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
# docker, for the cells: logs argv as one JSON line, answers from docker.json, keeps D1's state in docker-state.json
# (see tests/hetzner/support.py)
import hashlib, json, os, sys
SB = @SB@
a = sys.argv[1:]
with open(SB + '/logs/docker.log', 'a') as f:
    f.write(json.dumps(a) + '\n')
cfg = json.load(open(SB + '/docker.json'))
j = ' '.join(a)
SP = SB + '/docker-state.json'
st = json.load(open(SP)) if os.path.exists(SP) else {
    'n': 0, 'tags': {}, 'digests': {}, 'network': cfg.get('network', True), 'registry': cfg.get('registry', 'running')}


def out(s='', rc=0):
    with open(SP + '.new', 'w') as f:
        json.dump(st, f)
    os.replace(SP + '.new', SP)
    sys.stdout.write(s)
    sys.exit(rc)


def new_id(why):
    st['n'] += 1
    return 'sha256:' + hashlib.sha256(('%s %d' % (why, st['n'])).encode()).hexdigest()


if a[:1] == ['-H']:              # docker -H D1 …: the one daemon of these cells
    a = a[2:]
    j = ' '.join(a)
cmd = a[0] if a else ''
if cmd == 'version':
    out('29.9.0\n' if '--format' in a else 'Server: 29.9.0\n')
if cmd == 'info':
    out(cfg['info'].replace('@HOME@', os.environ['HOME']) + '\n')
if cmd == 'build':
    if cfg.get('build_rc'):
        out('', cfg['build_rc'])
    ctx = a[-1]
    names = sorted(os.listdir(ctx))
    files = {n: hashlib.sha256(open(os.path.join(ctx, n), 'rb').read()).hexdigest() for n in names}
    iid = new_id(json.dumps(files, sort_keys=True))
    st['tags'][a[a.index('-t') + 1]] = iid
    with open(SB + '/logs/build-ctx.json', 'a') as f:
        f.write(json.dumps({'argv': a, 'files': files, 'mode': oct(os.stat(ctx).st_mode & 0o777), 'id': iid}) + '\n')
    out(iid + '\n')
if cmd == 'push':
    tag = a[-1]
    if cfg.get('interleave'):    # another build of the same tag lands between this build's check and its push
        st['tags'][tag] = new_id('another build')
    iid = st['tags'][tag]
    ref = cfg.get('repo_digest') or '%s@sha256:%s' % (tag.rsplit(':', 1)[0], hashlib.sha256(iid.encode()).hexdigest())
    st['digests'][ref.split('@', 1)[1]] = iid
    st.setdefault('repo_digests', {})[iid] = ref
    out('')
if cmd == 'rm':
    out('')
if cmd == 'start':
    if a[-1] == 'runner-registry' and st['registry'] != 'absent':
        st['registry'] = 'running'
        out('runner-registry\n')
    out('Error: no such container\n', 1)
if cmd == 'inspect':
    if '{{.Id}}' in j:
        x = a[-1]
        iid = st['tags'].get(x) or ('@' in x and st['digests'].get(x.split('@', 1)[1]))
        out(iid + '\n') if iid else out('Error: No such object: %s\n' % x, 1)
    if 'RepoDigests' in j:
        out(st.get('repo_digests', {}).get(st['tags'].get(a[-1]), '') + '\n')
    if a[-1] == 'runner-registry' and st['registry'] == 'absent':
        out('Error: No such object: runner-registry\n', 1)
    if '{{.State.Running}}' in j:
        out('%s\n' % str(st['registry'] == 'running').lower())
    if 'bridge.IPAddress' in j:
        out('198.51.100.2\n')
    if 'runners.IPAddress' in j:
        out('198.51.100.7\n')
    if a[-1] == 'runner-registry':
        out('[]\n')
if cmd == 'network':
    if a[1:3] == ['create', 'runners']:
        st['network'] = True
        out('n' * 64 + '\n')
    if a[1:3] == ['inspect', 'runners'] and not st['network']:
        out('Error: network runners not found\n', 1)
    if 'Driver' in j:
        out('bridge\n')
    if 'Gateway' in j:
        out('198.51.100.1\n')
    out('[]\n')
if cmd == 'run':
    if '-d' in a:
        if 'runner-registry' in a:
            st['registry'] = 'running'
        out('c' * 64 + '\n')
    if './config.sh' in a:          # the runner version of THAT image (docker.json's versions), else config_version
        out(cfg.get('versions', {}).get(a[a.index('./config.sh') - 1], cfg['config_version']))
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
if urls and urls[0].startswith('http://127.0.0.1:') and '/manifests/' in urls[0]:
    c = json.load(open(SB + '/curl.json'))      # the registry: 0 = it serves that digest, 22 = it does not
    if c.get('registry_rc', 0):
        sys.exit(c['registry_rc'])
    sys.exit(0 if urls[0].rsplit('/', 1)[1] in c.get('served', []) else 22)
if urls and urls[0].startswith('http://127.0.0.1:') and urls[0].endswith('/healthz'):
    with open(SB + '/logs/events.log', 'a') as f:
        f.write('healthz read\n')
    c = json.load(open(SB + '/curl.json'))     # runscaler's /healthz; None = no answer. healthz_seq: one per read,
    seq = c.get('healthz_seq')                 # in order, the last one kept for every later read
    if seq:
        h = seq[0]
        if len(seq) > 1:
            c['healthz_seq'] = seq[1:]
            with open(SB + '/curl.json.new', 'w') as f:
                json.dump(c, f)
            os.replace(SB + '/curl.json.new', SB + '/curl.json')
    else:
        h = c.get('healthz')
    hz = None
    if os.path.exists(SB + '/stubs/hzlib.py'):  # a pool cell: a unit that plays runner-start (systemd.json's `runner`)
        sys.path.insert(0, SB + '/stubs')      # answers only while it serves; the hooks of "healthz-read" fire after
        import hzlib as hz                     # each read is answered
        st = hz.load('systemd.json')
        if st is not None and 'runner' in st and not hz.serving(st):
            h = None
    if h is not None:
        sys.stdout.write(json.dumps(h))
        sys.stdout.flush()
    if hz is not None:
        hz.fire('healthz-read')
    sys.exit(7 if h is None else 0)
sys.stderr.write('curl stub: no answer for: %s\n' % ' '.join(a))
sys.exit(99)
'''

GOOD_MAIN = ('Seccomp: 2\nNoNewPrivs: 1\npid1=docker-init umask=0022\nkeyctl EPERM\nsudo=refused\nbwrap=ok\n'
             'locale=ok\n')


class Sandbox:
    PIN_REWRITES = {
        'setup/01-users.sh': [('HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=@ROOT@/host.conf\n')],
        'setup/02-d1.sh': [('HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=@ROOT@/host.conf\n')],
        'setup/03-runscaler.sh': [('HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=@ROOT@/host.conf\n')],
        'setup/04-timer.sh': [('HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=@ROOT@/host.conf\n')],
        'setup/pool-image.sh': [('HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=@ROOT@/host.conf\n')],
        'bin/runner-start': [('HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=@ROOT@/host.conf\n')],
        'bin/pool-ready': [('HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=@ROOT@/host.conf\n')],
        # the updater sets its own PATH (the system folders): the copy puts the cell's substitutes first
        'bin/runner-updater': [('HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=@ROOT@/host.conf\n'),
                               ('PATH=/usr/bin:/bin:/usr/sbin:/sbin\n', 'PATH=@ROOT@/stubs:/usr/bin:/bin:/usr/sbin:/sbin\n')],
        'setup/runner-release.sh': [
            ('RR_API=https://api.github.com/repos/actions/runner\n', 'RR_API=@GH@/repos/actions/runner\n'),
            ('RR_DL=https://github.com/actions/runner/releases/download\n',
             'RR_DL=@GH@/actions/runner/releases/download\n'),
            ('RR_SRC=/etc/ssl/certs/ca-certificates.crt\n', 'RR_SRC=@ROOT@/source.pem\n')],
    }
    LEFT_OUT = {'setup/01-users.sh': ('/etc/liveapp-ci',),
                'setup/02-d1.sh': ('/etc/liveapp-ci',), 'bin/runner-start': ('/etc/liveapp-ci',),
                'setup/03-runscaler.sh': ('/etc/liveapp-ci',), 'setup/pool-image.sh': ('/etc/liveapp-ci',),
                'setup/04-timer.sh': ('/etc/liveapp-ci',),
                'bin/pool-ready': ('/etc/liveapp-ci',), 'bin/runner-updater': ('/etc/liveapp-ci',),
                'setup/runner-release.sh': ('api.github.com', '//github.com', '/etc/ssl')}
    # The original lines a copy may differ in (pin_lines_only): the rewrites above, and the pins Pool rewrites
    PIN_LINE = re.compile(r'(HOST_CONF|RR_API|RR_DL|RR_SRC|TGZ_SHA|BIN_SHA)=.*|PATH=/usr/bin:/bin:/usr/sbin:/sbin'
                          r'|PINS="\$S03=[0-9a-f]{64}'
                          r'|\$B/[A-Za-z0-9._/-]+=[0-9a-f]{64}"?')

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
        core = os.path.join(REPO, 'core')     # the install line ships the decision core into ~/build/core
        if os.path.isdir(core):
            shutil.copytree(core, os.path.join(self.build, 'core'), symlinks=True)
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

    def lib(self, script, *args, source='runner-release.sh'):
        """Run bash with the copied runner-release.sh (or another file of ~/build/setup/) sourced, then script (its
        $1.. = args)."""
        return subprocess.run(['bash', '-c', 'set -u; . "$0" || exit 9\n' + script,
                               os.path.join(self.build, 'setup', source)] + list(args),
                              env=self.env(), cwd=self.home, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=300)

    def files(self):
        """docker.json and curl.json, the stubs' answers, written from self.docker and self.curl."""
        self.write(self.path('docker.json'), json.dumps(self.docker))
        self.write(self.path('curl.json'), json.dumps(self.curl))

    def d1(self, *args):
        """Run the copied 02-d1.sh with args, docker.json and curl.json written from self.docker and self.curl."""
        self.files()
        return subprocess.run(['bash', os.path.join(self.build, 'setup', '02-d1.sh')] + list(args), env=self.env(),
                              cwd=self.home, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)

    def d1_start(self, *args):
        """d1, started: the Popen (stdout a pipe, stderr into it). The cell's cleanup kills it if it still runs."""
        return self.start(['bash', os.path.join(self.build, 'setup', '02-d1.sh')] + list(args))

    def pin_lines_only(self):
        """[(file, line number, the shipped line)] of every line in which a copy of ~/build differs from the shipped
        linux-docker/ file and that is no pin line (PIN_LINE), and of every copy whose line count differs: [] = the
        copies are the real scripts with only their pin lines rewritten."""
        out = []
        for d, _, names in os.walk(os.path.join(REPO, 'linux-docker')):
            for n in names:
                rel = os.path.relpath(os.path.join(d, n), os.path.join(REPO, 'linux-docker'))
                with open(os.path.join(d, n), 'rb') as f:
                    a = f.read().split(b'\n')
                with open(os.path.join(self.build, rel), 'rb') as f:
                    b = f.read().split(b'\n')
                if len(a) != len(b):
                    out.append((rel, 0, 'the line count'))
                    continue
                for i, (x, y) in enumerate(zip(a, b), 1):
                    if x != y and not self.PIN_LINE.fullmatch(x.decode('utf-8', 'replace')):
                        out.append((rel, i, x.decode('utf-8', 'replace')))
        return out

    def start(self, argv):
        """argv started as d1_start starts 02-d1.sh (the same env, files and cleanup)."""
        self.files()
        p = subprocess.Popen(argv, env=self.env(), cwd=self.home, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, start_new_session=True)

        def stop():   # the whole group: a waiting child (flock, a nested 02-d1.sh) dies with it
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.communicate()
        self.test.addCleanup(stop)
        return p

    def state(self):
        """The docker stub's D1: {'tags': {tag: image id}, 'digests': {digest: image id}, 'network', 'registry', …}."""
        p = self.path('docker-state.json')
        if not os.path.exists(p):
            return {'tags': {}, 'digests': {}}
        with open(p) as f:
            return json.load(f)

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


def bash5():
    """The first bash on PATH whose major version is 5 or more (linux-docker/'s scripts run under the host's bash 5),
    or None."""
    for d in os.environ.get('PATH', '').split(os.pathsep):
        b = os.path.join(d, 'bash')
        if d and os.path.isfile(b) and os.access(b, os.X_OK):
            r = subprocess.run([b, '-c', 'echo "${BASH_VERSINFO[0]}"'], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL)
            if r.returncode == 0 and r.stdout.strip().isdigit() and int(r.stdout) >= 5:
                return b
    return None


# ---- the pool side (RS_USER): 03-runscaler.sh, pool-image.sh, runner-start, pool-ready, validate-class

def digest(n):
    """A digest of the registry, sha256:<64 hex>, one per number."""
    return 'sha256:' + ('%02d' % n) * 32


def ref(d):
    """The image reference runscaler pulls for digest d (03's and pool-image.sh's IMGRE)."""
    return 'localhost:%s/%s@%s' % (REGISTRY_PORT, IMAGE_NAME, d)


POOL_RUNNER = r'''#!/usr/bin/python3 -I
# runscaler, for the pool cells (03-runscaler.sh extracts it from the download whose pins the cell rewrote): `version`;
# `validate --config FILE` answers as runner.json says ({rc, out}), except that a config with the bogus log-level of 03's
# control fails runscaler's own check; with {"hang": true} it ignores SIGTERM, writes its pid to logs/hang.pid and
# waits (at most 60 s of the real clock: a validate that hangs); `run` prints the UTC offset its clock reads. Logs argv,
# the names of the token variables it got (never a value), the config's sha256, and fd9: whether it has a file
# descriptor 9 open (the updater lock must never reach it) (see tests/hetzner/support.py, Pool).
import hashlib, json, os, signal, subprocess, sys, time
SB = @SB@
a = sys.argv[1:]
conf = a[a.index('--config') + 1] if '--config' in a else None
try:
    os.fstat(9)
    fd9 = True
except OSError:
    fd9 = False
with open(SB + '/logs/runner.log', 'a') as f:
    f.write(json.dumps({'argv': a, 'tokens': sorted(k for k in os.environ if k.startswith('RUNNER_TOKEN_')),
                        'config': hashlib.sha256(open(conf, 'rb').read()).hexdigest() if conf else None,
                        'fd9': fd9}) + '\n')


def say(text, rc):
    sys.stdout.buffer.write(text.encode())
    sys.stdout.flush()
    sys.exit(rc)


if a[:1] == ['version']:
    say('runscaler v0.9.5 (a test substitute)\n', 0)
if a[:1] == ['validate']:
    with open(conf) as f:
        if 'log-level = "liveapp-bogus"' in f.read():
            say('  ✗ global config: log-level must be one of debug, info, warn, error\nError: validation failed\n', 1)
    v = json.load(open(SB + '/runner.json'))
    if v.get('seq'):           # one answer per validate, in order, the last one kept for every later validate
        a0 = v['seq'][0]
        if len(v['seq']) > 1:
            v['seq'] = v['seq'][1:]
            with open(SB + '/runner.json.new', 'w') as f:
                json.dump(v, f)
            os.replace(SB + '/runner.json.new', SB + '/runner.json')
        v = a0
    if v.get('hang'):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        with open(SB + '/logs/hang.pid', 'a') as f:
            f.write('%d\n' % os.getpid())
        sys.stdout.write('  hanging\n')
        sys.stdout.flush()
        time.sleep(60)
    say(v['out'], v['rc'])
if a[:1] == ['run']:
    say('TZ-CHECK ' + subprocess.run(['date', '+%z'], capture_output=True, text=True).stdout, 0)
say('runner stub: no answer for: %s\n' % ' '.join(a), 99)
'''

HZLIB = r'''# hzlib: shared by the pool cells' substitutes (tests/hetzner/support.py, Pool): the clock, runscaler's process
# (systemd.json, and the lines it writes to runscaler's log), and the cell's hooks (hooks.json)
import fcntl, json, os, re, signal, time
SB = @SB@
LOG =os.path.join(os.environ.get('HOME', '/nonexistent'), '.config', 'runner', 'runner.log')


def load(name, default=None):
    p = os.path.join(SB, name)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)


def save(name, obj):
    p = os.path.join(SB, name)
    with open(p + '.new', 'w') as f:
        json.dump(obj, f)
    os.replace(p + '.new', p)


def event(text):
    with open(os.path.join(SB, 'logs', 'events.log'), 'a') as f:
        f.write(text + '\n')


def now():
    """Whole seconds: the cell's fake clock (clock.json) when it set one, else the real clock."""
    c = load('clock.json')
    return int(c['now']) if c else int(time.time())


def runlog(msg):
    """One record of runscaler's log, as the process writes it (runscaler's text format, UTC)."""
    with open(LOG, 'a') as f:
        f.write('%s INFO %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now())), msg))


def stop(st):
    if st['active']:
        runlog('runscaler stopped pid=%d' % st['pid'])
        event('process %d stopped' % st['pid'])
        st.update(last_pid=st['pid'], last_start=st['start'])
    st.update(active=False, pid=0)


def take(at):
    """An injection hook (no action): True, once, when the cell set one for AT."""
    hooks = load('hooks.json', [])
    for h in hooks:
        if h['at'] == at and not h.get('fired'):
            h['fired'] = True
            save('hooks.json', hooks)
            event('injected ' + at)
            return True
    return False


def start(st):
    st['next_pid'] = st.get('next_pid', 100) + 1
    st.update(active=True, pid=st['next_pid'], start=now(), failed=False)
    event('process %d started %d' % (st['pid'], st['start']))
    runlog('runscaler started pid=%d' % st['pid'])


def advance(to):
    """The fake clock moved on to TO (a wait that blocks until then: a drain): only with a fake clock."""
    c = load('clock.json')
    if c is None:
        raise SystemExit('hzlib: a drain needs the fake clock (Pool.fake_clock)')
    if c['now'] < to:
        c['now'] = to
        save('clock.json', c)
        event('clock %d' % int(to))


def shown(st):
    """runscaler's unit as systemd shows it NOW (the clock): (ActiveState, MainPID, ActiveEnterTimestamp). A unit of
    Type=simple with Restart=always (RestartSec=30) whose ExecStart, runner-start, plays st['runner'] (absent: serves):
    serves = active and /healthz answers; hang = active, /healthz never answers; crash = runner-start exits 1 after 1 s,
    so the unit is active for 1 s of each 31 s, each time a new pid and a fresh ActiveEnterTimestamp, and activating
    (auto-restart, MainPID 0) between. st['drain_until']: a stop job that still drains (deactivating, the old pid) until
    that second, also when its client is gone; then the stop ends (st changed: the caller saves it). st['failed']: an
    inactive unit reads failed."""
    t = now()
    if st.get('drain_until') is not None:
        if t < st['drain_until']:
            return 'deactivating', st['pid'], st['start']
        st.pop('drain_until')
        stop(st)
        if st.pop('start_after_drain', False):   # a start or restart came during the drain (job merge): it runs now
            start(st)
    if not st['active']:
        return ('failed' if st.get('failed') else 'inactive'), 0, st['start']
    if st.get('runner') == 'crash':
        k, ph = divmod(t - st['start'], 31)
        if ph < 1:
            return 'active', st['pid'] + 1000 * k, st['start'] + 31 * k
        return 'activating', 0, st['start'] + 31 * k
    return 'active', st['pid'], st['start']


def serving(st):
    """runscaler answers /healthz now: its unit is active and its runner-start serves."""
    return shown(st)[0] == 'active' and st.get('runner', 'serves') == 'serves'


def fire(at):
    """The cell's hooks for event AT, each once: hooks.json = [{"at": AT, "do": [ACTION, ...]}]."""
    hooks = load('hooks.json', [])
    todo = [h for h in hooks if h['at'] == at and not h.get('fired')]
    if not todo:
        return
    for h in todo:
        h['fired'] = True
    save('hooks.json', hooks)
    for h in todo:
        event('hook %s: %s' % (at, ' '.join(h['do'])))
        for a in h['do']:
            act(a)


def act(a):
    if a in ('restart', 'start'):          # an INDEPENDENT restart (systemd's own, or a person's), or a start
        st = load('systemd.json')
        if st.get('drain_until') is not None and now() < st['drain_until']:
            # a stop job drains: the manager's JOB MERGE: the start or restart cancels that stop job (its client
            # exits 1), the old process drains on, and the new one starts when it has ended (shown)
            st.update(stop_canceled=True, start_after_drain=True)
            event('%s during the drain: the stop job canceled' % a)
        else:
            if a == 'restart':
                stop(st)
            start(st)
        st['independent'] = st.get('independent', 0) + 1
        save('systemd.json', st)
    elif a in ('disable', 'disable-only', 'enable', 'stop', 'fail', 'crash', 'hang', 'serve'):
        st = load('systemd.json')          # a person's `systemctl --user disable --now` (disable), `disable` without
        shown(st)                          # --now (disable-only), `enable`, a plain `stop`; the process fails (fail:
        if a in ('disable', 'stop', 'fail'):   # inactive, failed); runner-start from now on crashes, hangs or serves
            stop(st)
        if a == 'stop' and st.get('start_job'):   # a stop while a start job is queued cancels that job (its client: 1)
            st['start_canceled'] = True
        if a == 'fail':
            st['failed'] = True
        if a in ('disable', 'disable-only', 'enable'):
            st['enabled'] = a == 'enable'
        if a in ('crash', 'hang', 'serve'):
            st['runner'] = 'serves' if a == 'serve' else a
        save('systemd.json', st)
    elif a == 'revive':                    # the stopped process runs again (a stop that did not stop it)
        st = load('systemd.json')
        st.update(active=True, pid=st['last_pid'], start=st['last_start'])
        event('process %d revived %d' % (st['pid'], st['start']))
        save('systemd.json', st)
    elif a == 'probe-lock':                # is the updater lock held now? (a new open: another holder's view)
        p = os.path.join(os.environ['HOME'], '.local', 'state', 'runner-updater', 'lock')
        if not os.path.exists(p):
            event('updater lock FREE (no lock file)')
            return
        fd = os.open(p, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            event('updater lock FREE')
        except BlockingIOError:
            event('updater lock held')
        finally:
            os.close(fd)
    elif a == 'busy':                      # /healthz turns busy from here on
        c = load('curl.json')
        c['healthz'] = c['busy']
        c.pop('healthz_seq', None)
        save('curl.json', c)
    elif a == 'edit-config':               # a person edits config.toml
        with open(os.path.join(os.path.dirname(LOG), 'config.toml'), 'a') as f:
            f.write('# a hand change\n')
    elif a in ('hand-file', 'put-prev'):   # a person installs another file: the main set's max-runners 3 -> 2
        d = os.path.dirname(LOG)           # (hand-file), or config.toml.prev, the file before the switch (put-prev)
        if a == 'hand-file':
            with open(os.path.join(d, 'config.toml')) as f:
                text = f.read().replace('max-runners = 3\n', 'max-runners = 2\n', 1)
        else:
            with open(os.path.join(d, 'config.toml.prev')) as f:
                text = f.read()
        with open(os.path.join(d, 'config.toml.hand'), 'w') as f:
            f.write(text)
        os.chmod(os.path.join(d, 'config.toml.hand'), 0o600)
        os.replace(os.path.join(d, 'config.toml.hand'), os.path.join(d, 'config.toml'))
        event('hand install ' + a)
    elif a in ('edit-staged', 'edit-rollback'):   # the staged file (up's, back's) changes after it was validated
        name = 'config.staged.toml' if a == 'edit-staged' else 'config.rollback.toml'
        with open(os.path.join(os.path.dirname(LOG), name), 'a') as f:
            f.write('# changed after the validate\n')
    elif a == 'edit-prev':                 # a person edits config.toml.prev, the rollback (a comment line)
        with open(os.path.join(os.path.dirname(LOG), 'config.toml.prev'), 'a') as f:
            f.write('# a hand change of the rollback\n')
    elif a == 'edit-prev-value':           # ... or a value of it: the main set's max-runners 3 -> 2, in place
        p = os.path.join(os.path.dirname(LOG), 'config.toml.prev')
        with open(p) as f:
            text = f.read()
        if text.count('max-runners = 3\n') != 1:
            raise SystemExit('edit-prev-value: no single max-runners = 3 line in ' + p)
        with open(p, 'w') as f:
            f.write(text.replace('max-runners = 3\n', 'max-runners = 2\n'))
    elif a == 'edit-prev-image':           # ... or puts another image into both its runner-image lines
        p = os.path.join(os.path.dirname(LOG), 'config.toml.prev')
        with open(p) as f:
            text = f.read()
        with open(p, 'w') as f:
            f.write(re.sub(r'(?m)^(runner-image = ".*@sha256:)[0-9a-f]{64}"$', r'\g<1>' + '37' * 32 + '"', text))
    elif a == 'tick':                      # wait for the next whole second of the REAL clock (a state, not a time)
        t = int(time.time())
        while int(time.time()) <= t:
            time.sleep(0.02)
        event('tick %d' % int(time.time()))
    elif a == 'kill':                      # SIGKILL pool-image.sh's own process group, and nothing else
        g = os.getpgid(0)
        with open('/proc/%d/cmdline' % g, 'rb') as f:
            cmd = f.read()
        if b'pool-image.sh' not in cmd:
            event('kill REFUSED: the group leader %d is not pool-image.sh' % g)
            return
        event('kill %d' % g)
        os.killpg(g, signal.SIGKILL)
    elif a == 'kill-updater':              # SIGKILL the runner-updater run this substitute is a child (or grandchild)
        p = os.getppid()                   # of, and nothing else (S2b-3c-1 B2b: a kill at a boundary of the apply step)
        while p > 1:
            pp, cmd = ppid_cmd(p)
            if re.search(r'/bin/runner-updater( |$)', cmd):
                event('kill-updater %d' % p)
                os.kill(p, signal.SIGKILL)
                return
            p = pp
        event('kill-updater REFUSED: no runner-updater above %d' % os.getpid())
    elif a == 'count-shows':               # from now on the systemctl substitute counts its show reads (systemctl:show-N)
        st = load('systemd.json')
        st['shows'] = 0
        save('systemd.json', st)
    elif a == 'pend':                      # (at systemctl:show-N) a read of the unit that is still pending: pend()
        pend()
    else:
        event('hook action UNKNOWN: ' + a)


# THE TWO LOCKS of the unattended modes: pool-image.sh's own (fd 8) and the updater lock (fd 9)
LOCKS = (('fd8-lock', os.path.join(os.environ.get('HOME', '/nonexistent'), '.config', 'runner', 'pool-image.lock')),
         ('fd9-lock', os.path.join(os.environ.get('HOME', '/nonexistent'), '.local', 'state', 'runner-updater', 'lock')))


def holds(pid):
    """'fd8-lock=B fd9-lock=B': has process PID a descriptor open on each lock file?"""
    links = set()
    try:
        for fd in os.listdir('/proc/%d/fd' % pid):
            try:
                links.add(os.readlink('/proc/%d/fd/%s' % (pid, fd)))
            except OSError:
                pass
    except OSError:
        pass
    return ' '.join('%s=%s' % (n, os.path.realpath(p) in links) for n, p in LOCKS)


def ppid_cmd(pid):
    """(its parent's pid, its command line) of process PID."""
    with open('/proc/%d/stat' % pid) as f:
        pp = int(f.read().rsplit(')', 1)[1].split()[1])
    with open('/proc/%d/cmdline' % pid, 'rb') as f:
        return pp, f.read().replace(b'\0', b' ').decode('utf-8', 'replace').strip()


def gone(pid):
    """PID ended (a zombie has closed all its files)."""
    try:
        with open('/proc/%d/stat' % pid) as f:
            return f.read().rsplit(')', 1)[1].split()[0] == 'Z'
    except OSError:
        return True


def locks_now():
    """'fd8-lock=FREE|held fd9-lock=FREE|held': can a NEW open of each lock take it now (another holder's view)?"""
    out = []
    for n, p in LOCKS:
        fd = os.open(p, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            out.append(n + '=FREE')
        except BlockingIOError:
            out.append(n + '=held')
        finally:
            os.close(fd)
    return ' '.join(out)


def window_cmd(cmd):
    """A command line of the window: `bash .../pool-image.sh ...` (its subshells, forks of it, show the same)."""
    return re.match(r'bash \S*/pool-image\.sh ', cmd) is not None


def pend():
    """A read of runscaler's unit (this systemctl substitute) that is still pending, while the window waits for it: the
    events name what each process up to the window holds (this read; each shell of the window between it and the
    window, a fork of the window with its command line; the window, the first of them whose parent is not) and whether
    the locks are held; then the window (and its parent, when that is the cells' lock holder: a bash that took the
    lock; never the cell's own process) is killed, and once it has ended, whether the locks are held again: only the
    read's own process tree is left of the window, so a lock still held is held by it."""
    win = ppid_cmd(os.getpid())[0]
    shells = []
    while window_cmd(ppid_cmd(ppid_cmd(win)[0])[1]):
        shells.append(win)
        win = ppid_cmd(win)[0]
    par, win_cmd = ppid_cmd(win)
    par_cmd = ppid_cmd(par)[1]
    event('pend read %d %s' % (os.getpid(), holds(os.getpid())))
    for s in shells:
        event('pend shell %d %s' % (s, holds(s)))
    event('pend window %d %s window=%s cmd=%s' % (win, holds(win), window_cmd(win_cmd), win_cmd[:200]))
    event('pend before the kill: ' + locks_now())
    kill = [win] + ([par] if 'flock -n 9' in par_cmd else [])
    for p in kill:
        os.kill(p, signal.SIGKILL)
    t = time.time()
    while not all(gone(p) for p in kill) and time.time() < t + 30:   # a bound on a hang, never a time a cell asserts
        time.sleep(0.02)
    event('pend killed %s, ended: %s' % (' '.join(map(str, kill)), all(gone(p) for p in kill)))
    event('pend after the kill: ' + locks_now())
'''

SYSTEMCTL_STUB = r'''#!/usr/bin/python3 -I
# systemctl --user, for the pool cells: runscaler's unit as systemd.json holds it ({active, enabled, start, pid}, and
# what hzlib.shown reads: runner, drain, drain_until, failed); logs each call, one line of its arguments. stop: the
# process logs its last line and exits (with `drain` seconds: the unit is deactivating, the old pid, for that long of
# the fake clock, the hooks of "systemctl:stop-begin" fire, and the client returns when the drain ends; a client killed
# meanwhile leaves the stop job draining); start: a new process (a new pid, start = the clock) logs its first line,
# unless the unit already is active; restart: both. THE JOB MERGE of the real manager: a start or restart (hzlib.act)
# while a stop job drains cancels that stop job (its client exits 1 "Job ... canceled"), the old process drains on and
# the new one starts once it ended; a person's stop while a start job is queued (the hooks of "systemctl:start-begin")
# cancels the start job (its client exits 1). show: ActiveState, UnitFileState, MainPID, ActiveEnterTimestamp,
# as hzlib.shown gives them now. Each call also logs, one JSON line of logs/systemctl-fds.log, whether it has a file
# descriptor 8 or 9 open (pool-image.sh's own lock, the updater lock: no systemctl call of the unattended modes may hold
# either) (see tests/hetzner/support.py, Pool).
import json, os, sys, time
SB = @SB@
sys.path.insert(0, SB + '/stubs')
import hzlib
a = sys.argv[1:]
with open(SB + '/logs/systemctl.log', 'a') as f:
    f.write(' '.join(a) + '\n')


def fd_open(n):
    try:
        os.fstat(n)
        return True
    except OSError:
        return False


with open(SB + '/logs/systemctl-fds.log', 'a') as f:
    f.write(json.dumps({'argv': a, 'fd8': fd_open(8), 'fd9': fd_open(9)}) + '\n')
st = hzlib.load('systemd.json')
state, mpid, mstart = hzlib.shown(st)
hzlib.save('systemd.json', st)
if a[:1] == ['--user']:
    a = a[1:]
cmd = a[0] if a else ''
if cmd == 'daemon-reload':
    sys.exit(0)
if cmd == 'is-active':
    print(state)
    sys.exit(0 if state == 'active' else 3)
if cmd == 'is-enabled':
    print('enabled' if st['enabled'] else 'disabled')
    sys.exit(0 if st['enabled'] else 1)
if cmd == 'show' and a[1:2] == ['runscaler']:
    if 'show_answer' in st:                # an answer the cell planted ({rc, out}), for every show from here on
        sys.stdout.write(st['show_answer']['out'])
        sys.stdout.flush()
        sys.exit(st['show_answer']['rc'])
    vals = {'ActiveEnterTimestamp': ('@%d' % mstart) if '--timestamp=unix' in a else
            time.strftime('%a %Y-%m-%d %H:%M:%S UTC', time.gmtime(mstart)),
            'MainPID': str(mpid), 'ActiveState': state,
            'UnitFileState': 'enabled' if st['enabled'] else 'disabled'}
    props = [a[i + 1] for i, x in enumerate(a[:-1]) if x == '-p']
    if not props or any(p not in vals for p in props):
        sys.stderr.write('systemctl stub: no answer for: %s\n' % ' '.join(sys.argv[1:]))
        sys.exit(99)
    for p in props:
        print(vals[p] if '--value' in a else '%s=%s' % (p, vals[p]))
    sys.stdout.flush()
    if 'shows' in st:                      # the Nth read of a cell that counts them, once answered: "systemctl:show-N"
        st['shows'] += 1
        hzlib.save('systemd.json', st)
        hzlib.fire('systemctl:show-%d' % st['shows'])
        st = hzlib.load('systemd.json')
    if 'shows_since_stop' in st:           # the Nth read after a stop, once answered: "systemctl:show-after-stop-N"
        st['shows_since_stop'] += 1
        hzlib.save('systemd.json', st)
        hzlib.fire('systemctl:show-after-stop-%d' % st['shows_since_stop'])
    sys.exit(0)
if cmd in ('restart', 'stop', 'start') and a[1:] == ['runscaler']:
    if cmd in ('restart', 'start'):        # the start job queued: the hooks of "systemctl:start-begin" (a person's stop
        st['start_job'] = True             # then cancels it: the manager's job merge, this client exits 1)
        hzlib.save('systemd.json', st)
        hzlib.fire('systemctl:%s-begin' % cmd)
        st = hzlib.load('systemd.json')
        st.pop('start_job', None)
        if st.pop('start_canceled', False):
            hzlib.save('systemd.json', st)
            sys.stderr.write('Job for runscaler.service canceled.\n')
            sys.exit(1)
        hzlib.save('systemd.json', st)
        state = hzlib.shown(st)[0]
    if state == 'deactivating' or (cmd != 'start' and state == 'active' and st.get('drain')):
        if state != 'deactivating':        # this stop's own drain: the stop job starts, then the client waits for it
            st['drain_until'] = hzlib.now() + st['drain']
            hzlib.save('systemd.json', st)
            hzlib.event('process %d draining until %d' % (st['pid'], st['drain_until']))
            hzlib.fire('systemctl:stop-begin')
            st = hzlib.load('systemd.json')
            if st.pop('stop_canceled', False):   # a start or restart came during the drain: this stop job is canceled
                hzlib.save('systemd.json', st)   # (the old process drains on; the new one starts after it)
                sys.stderr.write('Job for runscaler.service canceled.\n')
                sys.exit(1)
        elif cmd == 'stop':
            st.pop('start_after_drain', None)    # a stop joins the stop job: the start a merge queued is gone
        hzlib.advance(st['drain_until'])   # a client joins the stop job and returns when it ends
        st = hzlib.load('systemd.json')
        state = hzlib.shown(st)[0]
    if cmd in ('restart', 'stop'):
        hzlib.stop(st)
    if cmd in ('restart', 'start') and (cmd == 'restart' or state != 'active'):
        hzlib.start(st)
    k = {'restart': 'restarts', 'stop': 'stops', 'start': 'starts'}[cmd]
    st[k] = st.get(k, 0) + 1
    if cmd == 'stop':
        st['shows_since_stop'] = 0
    hzlib.save('systemd.json', st)
    hzlib.fire('systemctl:%s-done' % cmd)
    sys.exit(0)
sys.stderr.write('systemctl stub: no answer for: %s\n' % ' '.join(sys.argv[1:]))
sys.exit(99)
'''

# The opt-in substitutes of the unattended cells (Pool.fake_clock, Pool.hooks, Pool.disk, Pool.jq_version)
DATE_STUB = r'''#!/usr/bin/python3 -I
# date, for the pool cells with a fake clock: `date +%s` reads clock.json (logged); every other call is the real date
import os, sys
SB = @SB@
sys.path.insert(0, SB + '/stubs')
import hzlib
a = sys.argv[1:]
c = hzlib.load('clock.json')
if a == ['+%s'] and c:
    hzlib.event('date %d' % int(c['now']))
    print(int(c['now']))
    sys.exit(0)
os.execv('/usr/bin/date', ['date'] + a)
'''

SLEEP_STUB = r'''#!/usr/bin/python3 -I
# sleep, for the pool cells with a fake clock: it moves clock.json on by its argument and returns at once (logged)
import os, sys
SB = @SB@
sys.path.insert(0, SB + '/stubs')
import hzlib
a = sys.argv[1:]
c = hzlib.load('clock.json')
if not c or len(a) != 1:
    os.execv('/usr/bin/sleep', ['sleep'] + a)
c['now'] += float(a[0])
hzlib.save('clock.json', c)
hzlib.event('sleep %s' % a[0])
'''

DD_STUB = r'''#!/usr/bin/python3 -I
# dd, for the pool cells with hooks: the real dd, then, when it synced the window journal, the hooks of
# "journal:KEY" (KEY: the journal's last line's key, now on disk). An injection "ddfail:KEY" makes the sync of that
# line fail instead (exit 1, no dd). Any other file it syncs: the event "dd NAME" (NAME: its base name), and the
# injection "ddfail-file:NAME" makes that sync fail (exit 1, no dd)
import os, subprocess, sys
SB = @SB@
sys.path.insert(0, SB + '/stubs')
import hzlib
a = sys.argv[1:]
of = [x[3:] for x in a if x.startswith('of=')]
k = None
if of and of[0].endswith('/runner-updater/window') and os.path.exists(of[0]):
    with open(of[0], 'rb') as f:
        last = f.read().splitlines()[-1:]
    k = last[0].split(b' ', 1)[0].decode() if last else ''
    if hzlib.take('ddfail:' + k):
        sys.exit(1)
elif of and hzlib.take('ddfail-file:' + os.path.basename(of[0])):
    sys.exit(1)
r = subprocess.run(['/usr/bin/dd'] + a)
if r.returncode == 0 and k is not None:
    hzlib.event('journal ' + k)
    hzlib.fire('journal:' + k)
elif r.returncode == 0 and of:
    hzlib.event('dd ' + os.path.basename(of[0]))
sys.exit(r.returncode)
'''

MV_STUB = r'''#!/usr/bin/python3 -I
# mv, for the pool cells with hooks: the hooks of "mv:NAME" (NAME: the destination's base name), the real mv, then
# the hooks of "mv-done:NAME"
import os, subprocess, sys
SB = @SB@
sys.path.insert(0, SB + '/stubs')
import hzlib
a = sys.argv[1:]
dest = os.path.basename([x for x in a if not x.startswith('-')][-1])
hzlib.event('mv ' + dest)
hzlib.fire('mv:' + dest)
r = subprocess.run(['/usr/bin/mv'] + a)
if r.returncode == 0:
    hzlib.fire('mv-done:' + dest)
sys.exit(r.returncode)
'''

TOUCH_STUB = r'''#!/usr/bin/python3 -I
# touch, for the pool cells with hooks: the hooks of "touch:NAME" (NAME: the last argument's base name), the real touch,
# then the hooks of "touch-done:NAME" (logged as the event "touch NAME")
import os, subprocess, sys
SB = @SB@
sys.path.insert(0, SB + '/stubs')
import hzlib
a = sys.argv[1:]
name = os.path.basename(a[-1]) if a else ''
hzlib.event('touch ' + name)
hzlib.fire('touch:' + name)
r = subprocess.run(['/usr/bin/touch'] + a)
if r.returncode == 0:
    hzlib.fire('touch-done:' + name)
sys.exit(r.returncode)
'''

DF_STUB = r'''#!/usr/bin/python3 -I
# df, for the pool cells: `df -Pk PATH` answers df.json's {size_k, avail_k} in df's POSIX form (logged)
import json, sys
SB = @SB@
a = sys.argv[1:]
with open(SB + '/logs/df.log', 'a') as f:
    f.write(' '.join(a) + '\n')
d = json.load(open(SB + '/df.json'))
used = d['size_k'] - d['avail_k']
print('Filesystem     1024-blocks      Used Available Capacity Mounted on')
print('/dev/sda1      %d %d %d %d%% /' % (d['size_k'], used, d['avail_k'], (100 * used + d['size_k'] - 1) // d['size_k']))
'''

JQ_STUB = r'''#!/usr/bin/python3 -I
# jq, for the pool cells: `jq --version` prints jq.json's version (null: it prints nothing and fails, as a shell that
# finds no jq does); every other call is the real jq
import json, os, sys
SB = @SB@
if sys.argv[1:] == ['--version']:
    v = json.load(open(SB + '/jq.json'))['version']
    if v is None:
        sys.stderr.write('jq: command not found\n')
        sys.exit(127)
    print(v)
    sys.exit(0)
os.execv('/usr/bin/jq', ['jq'] + sys.argv[1:])
'''

TIMEOUT_STUB = r'''#!/usr/bin/python3 -I
# timeout, for the bound cells (Pool.short_timeout): logs its argv (one JSON line), then execs the REAL timeout with
# each duration divided by timeout.json's `scale` (at least 1 s): a 120-s bound becomes seconds of a cell, the real
# timeout's own process group and its KILL after -k unchanged. Its pid (the real timeout's, after the exec) goes to
# logs/timeout.pids, one per line (Pool.timeout_pids)
import json, os, sys
SB = @SB@
a = sys.argv[1:]
with open(SB + '/logs/timeout.log', 'a') as f:
    f.write(json.dumps(a) + '\n')
with open(SB + '/logs/timeout.pids', 'a') as f:
    f.write('%d\n' % os.getpid())
k = json.load(open(SB + '/timeout.json'))['scale']
s = lambda x: str(max(1, int(x) // k)) if x.isdigit() else x
a = ['-k', s(a[1]), s(a[2])] + a[3:] if a[:1] == ['-k'] else [s(a[0])] + a[1:]
os.execv('/usr/bin/timeout', ['timeout'] + a)
'''

SWAP_STUB = r'''#!/usr/bin/python3 -I
# mktemp, for the hostile-file cells (support.Pool.swap): RUN_USER's rename between a reader's lookups. On its Nth call
# for a build record's private copy (a template that ends in /record.XXXXXX: runner-release.sh's rr_record_read makes
# that copy before it opens the record), it first renames swap.json's KIND over swap.json's PATH: a FIFO, a symlink to
# TARGET, or a plain file of TEXT; then (every call) it runs the real mktemp. swap.json's `done` is the evidence it did.
import json, os, sys
SB = @SB@
if any(a.endswith('/record.XXXXXX') for a in sys.argv[1:]):
    c = json.load(open(SB + '/swap.json'))
    c['seen'] = c.get('seen', 0) + 1
    if c['seen'] == c['at']:
        t = os.path.join(os.path.dirname(c['path']), '.swap.%d' % os.getpid())
        if c['kind'] == 'fifo':
            os.mkfifo(t, 0o640)
        elif c['kind'] == 'link':
            os.symlink(c['target'], t)
        else:
            with open(t, 'w') as f:
                f.write(c['text'])
            os.chmod(t, 0o640)
        os.rename(t, c['path'])
        c['done'] = True
    with open(SB + '/swap.json.new', 'w') as f:
        json.dump(c, f)
    os.replace(SB + '/swap.json.new', SB + '/swap.json')
os.execv('/usr/bin/mktemp', ['mktemp'] + sys.argv[1:])
'''

HANG = 120   # bounded(): the seconds after which a run counts as HUNG (timeout's exit 124); never a time a cell asserts

D1_STUB = r'''#!/usr/bin/python3 -I
# 02-d1.sh, for the build pass cells (support.Pool.d1_stub): logs its call to logs/d1.log, one JSON line: argv; fd9: is
# its fd 9 the updater lock (the same file); held: does a NEW open of the lock find it held (by its parent, then);
# shares: can fd 9 take it at once (the parent's own open file). Then it answers as d1.json says: out on stdout, exit
# rc; with rc 0 and a "digest", it writes the build record of argv's version for the recipe d1.json names, as 02-d1.sh
# does. With "hang", it then waits (a build that hangs) until a signal ends it, at most 600 s. It builds nothing.
import fcntl, json, os, sys, time
SB = @SB@
a = sys.argv[1:]
lock = os.path.join(os.environ['HOME'], '.local', 'state', 'runner-updater', 'lock')
try:
    fd9 = os.path.samestat(os.fstat(9), os.stat(lock))
except OSError:
    fd9 = False
try:
    fd = os.open(lock, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held = False
    except BlockingIOError:
        held = True
    finally:
        os.close(fd)
except OSError:
    held = None
try:
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
    shares = True
except OSError:
    shares = False
with open(SB + '/logs/d1.log', 'a') as f:
    f.write(json.dumps({'argv': a, 'fd9': fd9, 'held': held, 'shares': shares}) + '\n')
c = json.load(open(SB + '/d1.json'))
sys.stdout.write(c.get('out', ''))
sys.stdout.flush()
if c.get('hang'):
    time.sleep(600)
if c.get('rc', 0) == 0 and c.get('digest') and len(a) == 2:
    b = os.path.join(os.environ['HOME'], 'run', 'builds')
    os.makedirs(b, mode=0o750, exist_ok=True)
    p = os.path.join(b, '%s-%s' % (a[1], c['recipe']))
    with open(p + '.new', 'w') as f:
        f.write('format 1\nversion %s\ndigest %s\nrecipe %s\n' % (a[1], c['digest'], c['recipe']))
    os.chmod(p + '.new', 0o640)
    os.replace(p + '.new', p)
sys.exit(c.get('rc', 0))
'''

PASS_OUT = ('  ✓ scaleset[0] "linux-ci-main" — provider=docker url=https://github.com/your-org max=3 min=0\n'
            '  ✓ scaleset[1] "linux-ci-small" — provider=docker url=https://github.com/your-org max=1 min=0\n'
            '  ✓ Docker connectivity\n\nAll checks passed.\n')


def healthz(**over):
    """runscaler's /healthz: the two sets of host.conf.example, ready and idle; over: {set name: fields to change}."""
    sets = []
    for n in ('linux-ci-main', 'linux-ci-small'):
        s = {'name': n, 'ready': True, 'idle': 0, 'busy': 0, 'metrics': {}}
        s.update(over.get(n, {}))
        sets.append(s)
    return {'scale_sets': sets}


_LINKED = set()   # the homes a Pool of this process linked /home/root to


class Pool(Sandbox):
    """A Sandbox for the pool side, run as RS_USER: 03-runscaler.sh, pool-image.sh and the files 03 installs
    (runner-start, pool-ready, validate-class, the unit). RS_USER = RUN_USER = root: pool-image.sh runs only as RS_USER,
    and runner-start reads /home/RS_USER/…, so the scripts' HOME is /home/root, a symlink to this sandbox's home that only
    a container has (the cell's cleanup removes it; a /home/root that is already there fails the cell: so two Pool
    cells, of two modules run at once in one container, cannot both run). The pin lines
    rewritten on top of HOST_CONF: 03's TGZ_SHA and BIN_SHA (the download ~/build/dl/runner-linux-amd64.tar.gz holds the
    runscaler substitute POOL_RUNNER) and pool-image.sh's PINS (each the sha256 of the copy it pins). Substitutes: the
    docker and curl of Sandbox (D1, the registry, which serves the digests in curl['served'], and /healthz,
    curl['healthz']), systemctl (systemd.json, self.unit), ss. pool.env holds 4/4/4096/3/2/2048; the token file is in."""
    HOME = '/home/root'

    def __init__(self, test):
        super().__init__(test)
        if os.path.lexists(self.HOME):   # an earlier Pool of this cell (a subtest) may hold it: only that is replaced
            if not (os.path.islink(self.HOME) and os.readlink(self.HOME) in _LINKED):
                test.fail('%s is already there: the pool cells need it as their own home (this is no throwaway '
                          'container, or something else made it)' % self.HOME)
            os.remove(self.HOME)
        os.symlink(self.home, self.HOME)
        _LINKED.add(self.home)

        def unlink():
            if os.path.islink(self.HOME) and os.readlink(self.HOME) == self.home:
                os.remove(self.HOME)
        test.addCleanup(unlink)
        p = self.path('host.conf')
        with open(p) as f:
            conf = f.read()
        if conf.count('\nRS_USER=%s\n' % RS_USER) != 1:
            raise AssertionError('host.conf: no single RS_USER=%s line' % RS_USER)
        self.write(p, conf.replace('\nRS_USER=%s\n' % RS_USER, '\nRS_USER=root\n'), 0o644)
        runner = POOL_RUNNER.replace('@SB@', repr(self.root)).encode()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as t:
            i = tarfile.TarInfo('runner')
            i.size, i.mode, i.mtime = len(runner), 0o755, 1761955200
            t.addfile(i, io.BytesIO(runner))
        tgz = buf.getvalue()
        os.makedirs(os.path.join(self.build, 'dl'))
        with open(os.path.join(self.build, 'dl', 'runner-linux-amd64.tar.gz'), 'wb') as f:
            f.write(tgz)
        self.pin('setup/03-runscaler.sh', 'TGZ_SHA', hashlib.sha256(tgz).hexdigest())
        self.pin('setup/03-runscaler.sh', 'BIN_SHA', hashlib.sha256(runner).hexdigest())
        self.rewrite_pins()
        sb = repr(self.root)
        self.write(self.path('stubs', 'hzlib.py'), HZLIB.replace('@SB@', sb))
        self.write(self.path('stubs', 'systemctl'), SYSTEMCTL_STUB.replace('@SB@', sb), 0o755)
        self.write(self.path('stubs', 'ss'), '#!/bin/sh\nexit 0\n', 0o755)
        self.unit = {'active': False, 'enabled': False, 'start': 0, 'pid': 0, 'next_pid': 100}
        self.set_unit()
        self.runner = {'rc': 0, 'out': PASS_OUT}
        self.curl.update(served=[], healthz=healthz(), busy=healthz(**{'linux-ci-main': {'busy': 1}}))
        self.docker['versions'] = {}
        self.R = os.path.join(self.HOME, '.config', 'runner')
        os.makedirs(self.R, mode=0o700)
        os.makedirs(os.path.join(self.HOME, 'run'), mode=0o750)
        self.pool_env()
        self.write(os.path.join(self.R, 'token-owner'), 'a-test-token-not-a-secret\n', 0o600)

    def env(self):
        return dict(super().env(), HOME=self.HOME)

    def pin(self, rel, name, value):
        """The pin line NAME=<64 hex> of ~/build/REL (exactly one) becomes NAME=value."""
        p = os.path.join(self.build, rel)
        with open(p) as f:
            text = f.read()
        lines = re.findall(r'^%s=[0-9a-f]{64}$' % name, text, re.M)
        if len(lines) != 1:
            raise AssertionError('%s: %d pin lines %s=, want 1' % (rel, len(lines), name))
        with open(p, 'w') as f:
            f.write(text.replace(lines[0] + '\n', '%s=%s\n' % (name, value)))

    def rewrite_pins(self):
        """pool-image.sh's PINS: each hash becomes the sha256 of the copy in ~/build it pins."""
        p = os.path.join(self.build, 'setup', 'pool-image.sh')
        with open(p) as f:
            text = f.read()
        m = re.search(r'^PINS="(.*?)"$', text, re.M | re.S)
        if not m:
            raise AssertionError('pool-image.sh has no PINS="…" block')
        rows = []
        for l in m.group(1).split('\n'):
            mm = re.fullmatch(r'(\$S03|\$B/([A-Za-z0-9._/-]+))=[0-9a-f]{64}', l)
            if not mm:
                raise AssertionError('pool-image.sh: a PINS line of another shape: %r' % l)
            rel = 'setup/03-runscaler.sh' if mm.group(1) == '$S03' else mm.group(2)
            rows.append('%s=%s' % (mm.group(1), sha256_file(os.path.join(self.build, rel))))
        with open(p, 'w') as f:
            f.write(text[:m.start(1)] + '\n'.join(rows) + text[m.end(1):])

    def set_unit(self, **kw):
        """runscaler's unit, as the systemctl substitute answers: active, enabled, start (epoch), pid (its MainPID);
        kw over the unit as it is now (a substitute may have changed it)."""
        if os.path.exists(self.path('systemd.json')):
            self.unit = self.unit_now()
        self.unit.update(kw)
        self.write(self.path('systemd.json'), json.dumps(self.unit))

    def unit_now(self):
        with open(self.path('systemd.json')) as f:
            return json.load(f)

    def files(self):
        super().files()
        self.write(self.path('runner.json'), json.dumps(self.runner))

    def run(self, argv, timeout=600, env=None):
        self.files()
        return subprocess.run(argv, env=env or self.env(), cwd=self.HOME, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def s03(self, *args):
        return self.run(['bash', os.path.join(self.build, 'setup', '03-runscaler.sh')] + list(args))

    def pool(self, *args):
        return self.run(['bash', os.path.join(self.build, 'setup', 'pool-image.sh')] + list(args))

    def rpath(self, name):
        return os.path.join(self.R, name)

    def read(self, path):
        """The text of path, or None when there is none."""
        if not os.path.lexists(path):
            return None
        with open(path) as f:
            return f.read()

    def config(self, name='config.toml'):
        return self.read(self.rpath(name))

    def images(self, name='config.toml'):
        return re.findall(r'^runner-image = "(.*)"$', self.config(name) or '', re.M)

    def image_ref(self, d):
        self.write(os.path.join(self.HOME, 'run', 'image.ref'), ref(d) + '\n')

    def pool_env(self, **over):
        n = dict(CONCURRENT=4, CPU=4, MEMORY=4096, MAX=3, SMALL_CPU=2, SMALL_MEMORY=2048)
        n.update(over)
        self.write(self.rpath('pool.env'), ''.join('%s=%s\n' % kv for kv in n.items()), 0o600)

    def rejected(self, text):
        """RS_USER's rejected file (the updater writes it): text, or None for no file."""
        p = os.path.join(self.HOME, '.local', 'state', 'runner-updater', 'rejected')
        if text is None:
            if os.path.lexists(p):
                os.remove(p)
            return p
        os.makedirs(os.path.dirname(p), mode=0o700, exist_ok=True)
        return self.write(p, text, 0o600)

    def production(self, d):
        """A host whose pool runs digest d: no config.toml, image.ref = d, a fresh `03 real` with the unit stopped and
        disabled, then the unit enabled and started after that install (in a later second, and not in the future)."""
        self.image_ref(d)
        r = self.s03('real')
        if r.returncode != 0 or self.images() != [ref(d)] * 2:
            raise AssertionError('the production setup failed: ' + r.stdout[-3000:] + r.stderr)
        m = int(os.stat(self.rpath('config.toml')).st_mtime)
        while int(time.time()) <= m:     # the start comes after the install's second, and is never in the future:
            time.sleep(0.05)              # wait for the clock (a state), never for a set time
        self.set_unit(active=True, enabled=True, start=int(time.time()), pid=100)
        self.write(self.rpath('runner.log'), '%s INFO runscaler started pid=100\n' % time.strftime(
            '%Y-%m-%d %H:%M:%S', time.gmtime()), 0o600)
        return r

    # ---- the unattended cells (pool-image.sh up --unattended / back --unattended)

    def fake_clock(self, ahead=10):
        """A fake clock from now on: `date +%s` reads it, `sleep N` moves it on by N and returns at once, and the
        systemctl substitute starts a process at it. It starts AHEAD seconds past the real clock, so every start it
        gives is after every real install time."""
        self.write(self.path('clock.json'), json.dumps({'now': int(time.time()) + ahead + 0.5}))
        sb = repr(self.root)
        self.write(self.path('stubs', 'date'), DATE_STUB.replace('@SB@', sb), 0o755)
        self.write(self.path('stubs', 'sleep'), SLEEP_STUB.replace('@SB@', sb), 0o755)

    def hooks(self, *hooks):
        """The cell's hooks, each (AT, ACTION, ...): AT `journal:KEY` (after that journal line is synced), `mv:NAME`
        or `mv-done:NAME` (around a rename onto NAME), `touch:NAME` or `touch-done:NAME` (around a touch of NAME),
        `systemctl:stop-done` / `:start-done`, `systemctl:stop-begin` (a stop with a drain: the stop job started, its
        client waits; a start or restart there cancels that stop job: the job merge), `systemctl:start-begin` /
        `:restart-begin` (the start job queued: a person's `stop` there cancels it), `healthz-read` (after a /healthz read is answered); ACTION restart (an independent restart),
        start, revive (the stopped process runs again), disable (a person's `disable --now`), disable-only (`disable`
        without --now), enable, stop (a person's plain stop), fail (the process ends, the unit failed), crash / hang /
        serve (runner-start from now on: hzlib.shown), busy (/healthz turns busy), edit-config (a hand edit: a
        comment), hand-file (a person installs another file: the main set's max-runners 3 -> 2), put-prev (a person
        puts config.toml.prev back as config.toml), edit-staged, edit-rollback (back's STAGED), edit-prev
        (config.toml.prev: a comment line), edit-prev-value (a value of it: the main set's max-runners 3 -> 2), edit-prev-image (another image in its runner-image lines), tick (wait for the next second of the REAL clock), probe-lock (is the updater lock
        held?), kill (SIGKILL of the unattended run's process group: its holder and pool-image.sh), kill-updater
        (SIGKILL of the runner-updater run the hooked command is a child of: a kill at a boundary of the apply step),
        count-shows (as
        count_shows(), from that event on), pend (at `systemctl:show-N`: that read stays pending while it names who holds
        the two locks, kills the window, and names them again: hzlib.pend). An injection, AT
        with no ACTION: `ddfail:KEY` (the sync of that journal line fails), `ddfail-file:NAME` (the sync of another
        file NAME fails). `systemctl:show-N` (after the Nth `systemctl show`) needs count_shows() too."""
        self.write(self.path('hooks.json'), json.dumps([{'at': h[0], 'do': list(h[1:])} for h in hooks]))
        sb = repr(self.root)
        self.write(self.path('stubs', 'dd'), DD_STUB.replace('@SB@', sb), 0o755)
        self.write(self.path('stubs', 'mv'), MV_STUB.replace('@SB@', sb), 0o755)
        self.write(self.path('stubs', 'touch'), TOUCH_STUB.replace('@SB@', sb), 0o755)

    def disk(self, size_k, avail_k):
        """`df -Pk` answers this size and free space (KiB)."""
        self.write(self.path('df.json'), json.dumps({'size_k': size_k, 'avail_k': avail_k}))
        self.write(self.path('stubs', 'df'), DF_STUB.replace('@SB@', repr(self.root)), 0o755)

    def jq_version(self, version):
        """`jq --version` prints VERSION (None: it prints nothing and fails, as when no jq is there); every other jq
        call is the image's jq."""
        self.write(self.path('jq.json'), json.dumps({'version': version}))
        self.write(self.path('stubs', 'jq'), JQ_STUB.replace('@SB@', repr(self.root)), 0o755)

    def count_shows(self):
        """From now on the systemctl substitute counts its `show` reads: the hooks of `systemctl:show-N` fire after
        the Nth one is answered."""
        self.set_unit(shows=0)

    def show_answer(self, rc, out):
        """Every `systemctl --user show` from now on prints OUT and exits RC (systemd's answer the cell plants)."""
        self.set_unit(show_answer={'rc': rc, 'out': out})

    def updater(self, *args, env=None, timeout=300, argv0=None):
        """~/build/bin/runner-updater ARGS (or the program at ARGV0), run as the timer runs it: by its own #! line."""
        return self.run([argv0 or os.path.join(self.build, 'bin', 'runner-updater')] + list(args), timeout=timeout,
                        env=env)

    def updater_start(self, *args):
        """runner-updater ARGS, started (stdout a pipe, stderr into it), in a new session; the cleanup kills it."""
        return self.start([os.path.join(self.build, 'bin', 'runner-updater')] + list(args))

    def clock(self, now=None, plus=0):
        """The fake clock (fake_clock): set it to NOW, or move it on by PLUS seconds; returns it (whole seconds)."""
        c = json.loads(self.read(self.path('clock.json')))
        c['now'] = (c['now'] if now is None else now) + plus
        self.write(self.path('clock.json'), json.dumps(c))
        return int(c['now'])

    # THE UPDATER'S CHILD (S2b-3c-1 D-a): the unattended modes run only as the child of a process that holds the updater
    # lock on fd 9, as runner-updater runs them. HOLDER is that parent: a bash that opens the lock on fd 9, takes it
    # (flock -n), and runs its arguments as its CHILD (no exec), so the child inherits fd 9 and the lock is its parent's
    # open file description. A `kill` hook kills the holder's whole group: the updater and its window.
    HOLDER = 'install -d -m 700 "${0%/*}" && exec 9>> "$0" && flock -n 9 || exit 99; "$@"'

    def holder(self):
        return ['bash', '-c', self.HOLDER, os.path.join(self.STATE, 'lock')]

    def unattended(self, *args, prefix=None, timeout=600):
        """pool-image.sh ARGS (`up --unattended V D`, `back --unattended --why W`, `recover --unattended`) in a NEW
        SESSION (a `kill` hook kills its group, never this process), as the child of PREFIX: by default the HOLDER
        above (the updater's child); () runs it with no parent of its own (no fd 9)."""
        self.files()
        prefix = self.holder() if prefix is None else list(prefix)
        p = subprocess.Popen(prefix + ['bash', os.path.join(self.build, 'setup', 'pool-image.sh')] + list(args),
                             env=self.env(), cwd=self.HOME, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)

        def stop():
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.test.addCleanup(stop)
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop()
            out, err = p.communicate()
            return subprocess.CompletedProcess(p.args, 124, out, err)
        return subprocess.CompletedProcess(p.args, p.returncode, out, err)

    def recover(self, **kw):
        """`pool-image.sh recover --unattended`, as the updater's child (unattended)."""
        return self.unattended('recover', '--unattended', **kw)

    STATE = os.path.join(HOME, '.local', 'state', 'runner-updater')

    def window(self):
        """The window journal's lines (WINDOW: open, or closed and not yet applied), or None when there is none."""
        t = self.read(os.path.join(self.STATE, 'window'))
        return None if t is None else t.splitlines()

    def archive(self):
        """The updater's APPLY STEP (S2b-3c-1 D-b (b), B2a): a CLOSED window journal applied to the updater's state by
        its own lines, then archived to windows/ID, by the real program: `runner-updater on` when the state is ON, else
        `off` (each runs RECOVER, which leaves a closed journal as it is, then the apply step; the state's `on` stays as
        it was; neither reads the unit or /healthz, so a cell's systemctl and curl logs get nothing). A cell calls it
        where the updater's next run would apply the journal."""
        lines = self.window()
        if not lines or not lines[-1].startswith('closed ') or not lines[0].startswith('window '):
            raise AssertionError('archive: no closed window journal: %r' % (lines,))
        st = self.read(os.path.join(self.STATE, 'state.json'))
        r = self.updater('on' if st is not None and json.loads(st).get('on') is True else 'off')
        wid = lines[0].split(' ', 1)[1]
        if r.returncode != 0 or self.window() is not None or not os.path.isfile(os.path.join(self.STATE, 'windows', wid)):
            raise AssertionError('archive: the apply step did not apply and archive %s (exit %d): %s'
                                 % (wid, r.returncode, r.stdout[-3000:] + r.stderr))

    def short_timeout(self, scale=40):
        """From now on `timeout` is TIMEOUT_STUB: it logs its argv (timeouts()) and runs the real timeout with each
        duration divided by SCALE (120 s -> 3 s; -k 10 -> 1 s)."""
        self.write(self.path('timeout.json'), json.dumps({'scale': scale}))
        self.write(self.path('stubs', 'timeout'), TIMEOUT_STUB.replace('@SB@', repr(self.root)), 0o755)

    def timeouts(self):
        """The argv of each `timeout` call since short_timeout."""
        return self.calls('timeout')

    def timeout_pids(self):
        """The pid of each `timeout` call since short_timeout (the real timeout's: TIMEOUT_STUB execs it)."""
        return [int(w) for w in (self.read(self.path('logs', 'timeout.pids')) or '').split()]

    def systemctl_fds(self):
        """[{argv, fd8, fd9}] of each systemctl call: did it have fd 8 or fd 9 open?"""
        return self.calls('systemctl-fds')

    def closed(self):
        """[(ID, lines)] of the closed window journals (windows/ID), oldest first."""
        d = os.path.join(self.STATE, 'windows')
        if not os.path.isdir(d):
            return []
        names = [n for n in os.listdir(d) if not n.endswith('.d')]
        names.sort(key=lambda n: os.stat(os.path.join(d, n)).st_mtime_ns)
        return [(n, self.read(os.path.join(d, n)).splitlines()) for n in names]

    def events(self):
        """The substitutes' event lines: process starts and stops, hooks, clock reads and sleeps."""
        return (self.read(self.path('logs', 'events.log')) or '').splitlines()

    def snapshot(self):
        """{path: (sha256, mtime_ns, mode)} of every file in the home but ~/build: what an install would change."""
        out = {}
        for d, dirs, names in os.walk(self.home):
            if d == self.home:
                dirs[:] = [x for x in dirs if x != 'build']
            for n in names:
                p = os.path.join(d, n)
                if os.path.islink(p) or not os.path.isfile(p):
                    out[p] = ('not a file', 0, 0)
                    continue
                s = os.stat(p)
                out[p] = (sha256_file(p), s.st_mtime_ns, s.st_mode)
        return out

    def recipe(self):
        """02-d1.sh's RECIPE of this ~/build/image/: the sha256 of its `sha256sum` lines, names in byte order."""
        d = os.path.join(self.build, 'image')
        lines = ''.join('%s  %s\n' % (sha256_file(os.path.join(d, n)), n) for n in sorted(os.listdir(d)))
        return hashlib.sha256(lines.encode()).hexdigest()

    def record(self, version, d, recipe=None, text=None, name=None):
        """RUN_USER's build record ~/run/builds/<version>-<recipe> (0640), in 02-d1.sh's form unless text is given."""
        recipe = recipe or self.recipe()
        if text is None:
            text = 'format 1\nversion %s\ndigest %s\nrecipe %s\n' % (version, d, recipe)
        b = os.path.join(self.HOME, 'run', 'builds')
        os.makedirs(b, mode=0o750, exist_ok=True)
        return self.write(os.path.join(b, name or '%s-%s' % (version, recipe)), text, 0o640)

    # ---- the updater as RUN_USER (its build pass)

    def run_user(self):
        """From now on root is RUN_USER alone: host.conf's RS_USER goes back to host.conf.example's, so the updater
        runs in RUN_USER's role (its build pass). pool-image.sh, RS_USER's only, then refuses to run."""
        p = self.path('host.conf')
        conf = self.read(p)
        if conf.count('\nRS_USER=root\n') != 1:
            raise AssertionError('host.conf: no single RS_USER=root line')
        self.write(p, conf.replace('\nRS_USER=root\n', '\nRS_USER=%s\n' % RS_USER), 0o644)

    def d1_stub(self, rc=0, out='', digest=None, recipe=None, hang=False):
        """~/build/setup/02-d1.sh of THIS copy replaced by D1_STUB (a bash line that execs it, fd 9 kept): it logs its
        call and answers OUT and RC; with rc 0 and DIGEST it writes the build record of its version for RECIPE (default:
        this ~/build's recipe); with HANG it waits after OUT until a signal ends it (a build that hangs). The real
        02-d1.sh never runs."""
        self.write(self.path('stubs', 'd1stub.py'), D1_STUB.replace('@SB@', repr(self.root)), 0o755)
        self.write(os.path.join(self.build, 'setup', '02-d1.sh'),
                   '#!/bin/bash\nexec /usr/bin/python3 -I %s "$@"\n' % self.path('stubs', 'd1stub.py'), 0o755)
        self.write(self.path('d1.json'), json.dumps({'rc': rc, 'out': out, 'digest': digest, 'hang': hang,
                                                     'recipe': recipe or self.recipe()}))

    def d1_calls(self):
        """The calls of the 02-d1.sh substitute: [{argv, fd9, held, shares}]."""
        return self.calls('d1')

    # ---- RUN_USER's files are hostile to RS_USER (PLAN D1)

    def swap(self, path, kind, at=1, target=None):
        """From now on `mktemp` is SWAP_STUB: at the AT-th private copy of a build record (rr_record_read's mktemp), it
        renames KIND over PATH first: 'fifo', 'link' (a symlink to TARGET) or 'plain' (a new plain file of PATH's
        text now). swapped() says whether it did."""
        text = self.read(path) if kind == 'plain' else None
        self.write(self.path('swap.json'), json.dumps({'path': path, 'kind': kind, 'at': at, 'target': target,
                                                        'text': text}))
        self.write(self.path('stubs', 'mktemp'), SWAP_STUB.replace('@SB@', repr(self.root)), 0o755)

    def swapped(self):
        """The swap's evidence: did SWAP_STUB rename its KIND over the path?"""
        return json.loads(self.read(self.path('swap.json'))).get('done', False)

    def bounded(self, argv):
        """argv as run() runs it, under `timeout HANG` (and a KILL 10 s later): a run that hangs ends with timeout's
        exit 124. A bound on a hang, never a time a cell asserts."""
        return self.run(['timeout', '-k', '10', str(HANG)] + list(argv))


def iso(t):
    """Epoch seconds as GitHub's published_at (UTC, whole seconds)."""
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))


def run_pool(test, version, age=3 * 86400, on=True, stops=(), status=200, rc=0, out='BUILD DONE (D1): a substitute\n',
             digest=None):
    """A Pool in RUN_USER's role, for the updater's build pass: root is RUN_USER alone (Pool.run_user), the fake clock,
    02-d1.sh replaced by its substitute (Pool.d1_stub: RC, OUT, DIGEST), and GitHub's latest release VERSION published
    AGE seconds before the fake clock's now (STATUS: the API's answer). The updater's state ON (on=True), OFF (False) or
    none (None), holding STOPS. Returns (pool, now)."""
    p = Pool(test)
    p.run_user()
    p.fake_clock()
    now = p.clock()
    p.gh.release(version, tarball(version), latest=True, published=iso(now - age), status=status)
    p.d1_stub(rc=rc, out=out, digest=digest)
    p.files()
    if on is not None:
        os.makedirs(Pool.STATE, mode=0o700, exist_ok=True)
        p.write(os.path.join(Pool.STATE, 'state.json'),
                json.dumps({'format': 1, 'on': on, 'stops': list(stops)}) + '\n', 0o600)
    return p, now
