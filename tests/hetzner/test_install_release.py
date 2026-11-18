"""W4: ONE verified install line per release for the Linux host (the W4 plan's V-1 and STUDIO'S SPLIT, the r3 MODEL
X-1..X-9, X-6' THE SHARED RENDERER and the FINAL FOLD Y-1..Y-9). A release's linux-install-line.txt is the template
linux-docker/setup/install-release.run-line, rendered by studio's tools/render-linux-line with the release's tarball
URL, its sha256, its VERSION and its tag; run as each host user (`ssh <user>@<host> 'bash -s -- FLAGS' <
linux-install-line.txt`), it downloads the tarball, checks its sha256, unpacks it, and execs the release's own
linux-docker/setup/install-release.sh, which does today's Install steps 3 and 4 for that user, checked first.

Every cell here runs the RENDERED line (Y-8: `bash -s -- FLAGS` with the line on stdin), never the installer directly,
as TWO REAL users of the throwaway container (useradd there, as root there: RUN_USER, and RS_USER in RUN_USER's group,
F3), each with its own home under /home, its own updater lock and its own ~/build. THE FIXTURE (X-9): a release tree is
built and pinned FIRST (linux-docker/, core/, setup/tls-excluded-spki and VERSION of this repository, with only its
pin lines changed: install-release.sh's HOST_CONF, 03-runscaler.sh's runscaler pins, and bin/runner-updater replaced by
the cells' own UPDATER), then archived as git archive makes a release tarball (one top folder <VERSION>/, folders and
programs 0775, other files 0664), then hashed, then served and installed unchanged. THE PARITY (X-6'): each line is
rendered by `bash -p REPO/tools/render-linux-line <the fixture's template> URL SHA VERSION TAG` (X-6''), the renderer
the release build uses (studio's step 1 of the LANDING ORDER): while that file is absent every cell FAILS, never skips. GitHub is a
local HTTPS server under github.com's name (a certificate of the test CA); a curl substitute on PATH runs the real curl
with the user's own arguments first (so `-q` stays the first one) and adds only where github.com answers and that CA.

Items (each cell's docstring names its own; MUTANT names the change that turns it red):
- X-1: root, and a user the host config does not name, are refused; nothing is downloaded or changed.
- X-2: a tarball of another sha256 is refused, nothing unpacked; the unpack admits only plain files and folders under
  <VERSION>/ (a symlink, a hard link, a device, a FIFO, `..`, an absolute path, a member outside: refused); the modes
  are 0755/0644 under the user's umask 077 and 002; RS_USER's runscaler download goes into the new tree BEFORE the
  switch (a wrong sha256 leaves the old ~/build).
- X-3: a cut between the switch's two renames is healed by the next run; the updater lock (and RS_USER's pool-image.sh
  lock) held -> refused; a window journal -> refused, `--anyway` -> installed; only the last 3 ~/build.prev.* kept.
- X-4/Y-5: each user's NEXT lines: its own timer units; RS_USER's pinned ~/bin files and the runscaler pin.
- X-5/Y-9: the release order (rc.10 after rc.3; a final after its rcs; unknown identity), `--older`, `--same`, the same
  tag again (already installed), and RS_USER before RUN_USER refused.
- Y-1: one install at a time per user (the second run, during the first's download, is refused).
- Y-3: the way-back download is found by its sha256 under any name; none -> NOT KEPT, never a refusal.
- Y-6: DONE reads the pass; Y-7: a host-config key the release needs and the host lacks refuses before any change.
- Y-8: the flags reach the installer through `bash -s --` (the template passes "$@").
- Y-9: every curl starts with -q (a ~/.curlrc with an Authorization header sends none).
- Fix round 1 (build review r1): a pass that fails with no output (codex F1); one tag spelling, no leading zero
  (codex F2); a re-run of the installed release still names its NEXT lines and runs the pass (opus F1); the install
  lock 0600 and its folders the role's modes after an early refusal (opus F2); a killed run's download and unpack
  removed by the next run (opus F3); a file the release adds to INSTALLS named (opus F4); the README names the first
  release with the line by its asset (opus F6).
- Fix round 2 (build review r2, codex F1): the line takes the install lock before its download and the installer keeps
  it, so a run while another downloads or unpacks is refused by the line and removes nothing of the live run; a run
  that was killed leaves files the next run removes.
(Named for its CI part, test_[c-jv-z]*.py: .github/workflows/release-check.yml.)
"""
import hashlib
import http.server
import io
import json
import os
import re
import secrets
import shutil
import signal
import ssl
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest

from tests.hetzner.support import (FAIL_WHY, OPENSSL, REPO, SKIP_WHY, needs_container, pki, require_tools,
                                   sha256_file, verdict)

TEMPLATE_REL = os.path.join('linux-docker', 'setup', 'install-release.run-line')
INSTALLER_REL = os.path.join('linux-docker', 'setup', 'install-release.sh')
RENDERER = os.path.join(REPO, 'tools', 'render-linux-line')
SLUG = 'liveappbase/github-self-hosted-runner'
STUDIO_WAITS = ('tools/render-linux-line is not in this tree: the cells render the line with the renderer the release '
                'build uses (X-6\'), studio\'s step 1 of the W4 LANDING ORDER; they wait for it, and never use a copy')
SYS_PATH = '/usr/bin:/bin:/usr/sbin:/sbin'
RS_PATH = '/ysya/runscaler/releases/download/v%s/runner-linux-amd64.tar.gz'
RSCALER = b'the cells\' runscaler v0.22.0 tarball\n'          # the pinned download (03's TGZ_SHA is pinned to it)
WAYBACK = b'the cells\' runscaler v0.12.0 tarball\n'          # the way-back download (WAYBACK_TGZ_SHA)
RS_DL = {'runner-linux-amd64.tar.gz': RSCALER, 'runner-v0.12.0-linux-amd64.tar.gz': WAYBACK}   # RS_USER's ~/build/dl
BINARY = b'the cells\' runscaler binary\n'                    # ~/bin/runner of a host that runs the pinned one
OLD = 'v0.2.0'
OLD_SHA = 'a' * 64

# The cells' runner-updater (the fixture's bin/runner-updater): each call logged; a pass whose user's updater lock a
# FRESH open cannot take says what the real pass says then (runner-updater's `pass: another run holds the updater lock
# ...`: the installer must release it before its pass, Y-6); a cell's answer is the file @ROOT@/updater/<user>.<cmd>,
# bash that the stub sources (it may exit); else a pass is OFF's line, and status names an open window journal when one
# is there, as the real status does
UPDATER = r'''#!/bin/bash
d=@ROOT@/updater u=$(id -un) c=${1-}
printf '%s\n' "$c" >> "$d/$u.calls"
L=$HOME/.local/state/runner-updater/lock
if [ "$c" = pass ] && [ -e "$L" ] && ! flock -n "$L" true 2> /dev/null < /dev/null; then
  echo "runner-updater: pass: another run holds the updater lock $L; this pass ends"; exit 0
fi
[ ! -f "$d/$u.$c" ] || . "$d/$u.$c"
case $c in
  pass) echo "runner-updater: pass: the updater is OFF: nothing to do" ;;
  status) [ ! -e "$HOME/.local/state/runner-updater/window" ] \
            || echo "runner-updater: status: a window journal is open: $HOME/.local/state/runner-updater/window"
          echo "runner-updater: status: the updater is OFF" ;;
esac
exit 0
'''

# curl, for the cells: the REAL curl with the caller's arguments FIRST (so a -q stays the first one, Y-9), then where
# github.com answers (the cell's server) and the test CA that signed that server's certificate
CURL = '''#!/bin/bash
exec /usr/bin/curl "$@" --connect-to github.com:443:127.0.0.1:@PORT@ --cacert @CA@
'''

_CERT = []


def github_cert():
    """(cert, key) of a server certificate for github.com, signed by support's test CA (made once per process)."""
    if not _CERT:
        d = tempfile.mkdtemp(prefix='w4-cert-')
        p = pki().dir

        def ossl(*a):
            subprocess.run((OPENSSL,) + a, cwd=d, check=True, capture_output=True, stdin=subprocess.DEVNULL)
        with open(os.path.join(d, 'ext.cnf'), 'w') as f:
            f.write('subjectAltName=DNS:github.com\nbasicConstraints=critical,CA:FALSE\n'
                    'keyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n')
        ossl('req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes', '-keyout', 'gh.key',
             '-out', 'gh.csr', '-subj', '/CN=github.com')
        ossl('x509', '-req', '-in', 'gh.csr', '-CA', os.path.join(p, 'ca.pem'), '-CAkey', os.path.join(p, 'ca.key'),
             '-set_serial', '7', '-days', '3', '-out', 'gh.pem', '-extfile', 'ext.cnf')
        _CERT.append((os.path.join(d, 'gh.pem'), os.path.join(d, 'gh.key')))
    return _CERT[0]


class Hub:
    """github.com, served locally over HTTPS: routes path -> (status, body, delay: seconds, or a GATE, a
    threading.Event the answer waits for, so a cell waits for a state and never for a time); requests: (path, headers)
    of each request that reached HTTP; arrived[path]: an Event set when a request for path arrives."""

    def __init__(self, test):
        self.routes, self.requests, self.arrived = {}, [], {}
        hub = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hub.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
                if self.path in hub.arrived:
                    hub.arrived[self.path].set()
                status, body, delay = hub.routes.get(self.path, (404, b'Not Found', 0))
                if isinstance(delay, threading.Event):
                    delay.wait(300)
                elif delay:
                    time.sleep(delay)
                self.send_response(status)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(*github_cert())
        self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        self.httpd.handle_error = lambda *a: None
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

        def stop():
            self.httpd.shutdown()
            self.httpd.server_close()
        test.addCleanup(stop)
        self.port = self.httpd.server_address[1]

    def paths(self):
        return [p for p, _ in self.requests]


class Release:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Host:
    """The throwaway container as a Linux host with its two users (RUN_USER, RS_USER in RUN_USER's group), the host
    config naming them (root's, 0644), the cells' curl on PATH, github.com (Hub) and the fixture releases."""

    def __init__(self, test):
        v = verdict()
        if v == 'skip':
            raise unittest.SkipTest(SKIP_WHY)
        if v == 'fail':
            test.fail(FAIL_WHY)
        require_tools(test)
        for p in ('/usr/sbin/useradd', '/usr/sbin/userdel', '/usr/sbin/runuser', '/usr/bin/flock', '/usr/bin/tar'):
            if not os.path.exists(p):
                test.fail('this container lacks %s, which these cells need' % p)
        self.t = test
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='w4-'))
        os.chmod(self.root, 0o755)
        test.addCleanup(shutil.rmtree, self.root, True)
        sfx = secrets.token_hex(3)
        self.run, self.rs, self.other = 'w4r' + sfx, 'w4s' + sfx, 'w4x' + sfx
        for u in (self.run, self.rs):
            self.sh('useradd', '-m', '-U', '-s', '/bin/bash', u)
            test.addCleanup(self.drop_user, u)
        self.sh('usermod', '-aG', self.run, self.rs)
        os.chmod(self.home(self.run), 0o750)
        with open(os.path.join(REPO, 'linux-docker', 'host.conf.example')) as f:
            conf = f.read()
        for k, u in (('RUN_USER', self.run), ('RS_USER', self.rs)):
            if len(re.findall(r'^%s=.*$' % k, conf, re.M)) != 1:
                raise AssertionError('host.conf.example: no single %s line' % k)
            conf = re.sub(r'^%s=.*$' % k, '%s=%s' % (k, u), conf, flags=re.M)
        self.conf = os.path.join(self.root, 'host.conf')
        self.write(self.conf, conf, 0o644)
        self.hub = Hub(test)
        os.makedirs(os.path.join(self.root, 'stubs'))
        self.write(os.path.join(self.root, 'ca.pem'), pki().ca_pem, 0o644)
        self.write(os.path.join(self.root, 'stubs', 'curl'),
                   CURL.replace('@PORT@', str(self.hub.port)).replace('@CA@', os.path.join(self.root, 'ca.pem')), 0o755)
        os.makedirs(os.path.join(self.root, 'updater'))
        os.chmod(os.path.join(self.root, 'updater'), 0o1777)
        self.serve(RS_PATH % '0.22.0', RSCALER)
        self.n = 0

    # ---- plumbing
    def sh(self, *argv):
        r = subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise AssertionError('%s: %s' % (' '.join(argv), r.stdout + r.stderr))
        return r

    def drop_user(self, u):
        subprocess.run(['pkill', '-KILL', '-u', u], capture_output=True)
        time.sleep(0.2)
        subprocess.run(['userdel', '-r', '-f', u], capture_output=True)

    @staticmethod
    def home(u):
        return '/home/' + u

    def write(self, path, text, mode=0o644, owner=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb' if isinstance(text, bytes) else 'w') as f:
            f.write(text)
        os.chmod(path, mode)
        if owner:
            shutil.chown(path, owner, owner)
        return path

    def own(self, u, path):
        """chown -R u:u PATH (a home's file a cell made as root)."""
        subprocess.run(['chown', '-R', '%s:%s' % (u, u), path], check=True)

    def serve(self, path, body, status=200, delay=0):
        self.hub.routes[path] = (status, body, delay)

    def answer(self, u, cmd, text):
        """The cells' updater answers CMD as user U with TEXT (bash, sourced; it may exit)."""
        self.write(os.path.join(self.root, 'updater', '%s.%s' % (u, cmd)), text, 0o644)

    def calls(self, u):
        p = os.path.join(self.root, 'updater', u + '.calls')
        return open(p).read().split() if os.path.exists(p) else []

    # ---- the fixture release (X-9: built and pinned FIRST, then archived and hashed, then installed unchanged)
    def release(self, tag, edit=None, extra=(), served=None, sha=None, rscaler=RSCALER, wayback=WAYBACK,
                binary=BINARY):
        """A release TAG (v<N.N.N> or v<N.N.N>-rc.<N>): its tree pinned (EDIT(tree) last), archived, hashed, served;
        EXTRA: (TarInfo, bytes or None) members added to the archive (the unpack cells); SERVED: other bytes served
        under its URL; SHA: another sha256 rendered into the line. Returns a Release (tag, version, tree, sha, url,
        line: the rendered line's file)."""
        if not os.path.isfile(RENDERER):
            self.t.fail(STUDIO_WAITS)
        self.n += 1
        version = re.fullmatch(r'v([0-9]+\.[0-9]+\.[0-9]+)(?:-rc\.[0-9]+)?', tag).group(1)
        top = os.path.join(self.root, 'fx%d' % self.n)
        tree = os.path.join(top, version)
        shutil.copytree(os.path.join(REPO, 'linux-docker'), os.path.join(tree, 'linux-docker'), symlinks=True)
        shutil.copytree(os.path.join(REPO, 'core'), os.path.join(tree, 'core'), symlinks=True)
        os.makedirs(os.path.join(tree, 'setup'))
        shutil.copy(os.path.join(REPO, 'setup', 'tls-excluded-spki'), os.path.join(tree, 'setup'))
        with open(os.path.join(tree, 'VERSION'), 'w') as f:
            f.write(version + '\n')
        self.pin(tree, INSTALLER_REL, 'HOST_CONF=/etc/liveapp-ci/host.conf\n', 'HOST_CONF=%s\n' % self.conf)
        s03 = os.path.join('linux-docker', 'setup', '03-runscaler.sh')
        for name, data in (('TGZ_SHA', rscaler), ('BIN_SHA', binary), ('WAYBACK_TGZ_SHA', wayback)):
            self.pin(tree, s03, None, '%s=%s\n' % (name, hashlib.sha256(data).hexdigest()), name=name)
        self.write(os.path.join(tree, 'linux-docker', 'bin', 'runner-updater'),
                   UPDATER.replace('@ROOT@', self.root), 0o755)
        if edit:
            edit(tree)
        data = archive(top, version, extra)
        h = hashlib.sha256(data).hexdigest()
        name = 'github-self-hosted-runner-%s.tar.gz' % tag
        path = '/%s/releases/download/%s/%s' % (SLUG, tag, name)
        self.serve(path, served if served is not None else data)
        url = 'https://github.com' + path
        r = subprocess.run(['bash', '-p', RENDERER, os.path.join(tree, TEMPLATE_REL), url, sha or h, version, tag],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.t.assertEqual((r.returncode, r.stderr), (0, ''), 'the renderer refused the fixture: ' + r.stderr)
        line = self.write(os.path.join(self.root, 'line-%d.txt' % self.n), r.stdout, 0o644)
        return Release(tag=tag, version=version, tree=tree, sha=h, url=url, path=path, line=line, text=r.stdout)

    def pin(self, tree, rel, old, new, name=None):
        p = os.path.join(tree, rel)
        with open(p) as f:
            text = f.read()
        if name:
            found = re.findall(r'^%s=[0-9a-f]{64}\n' % name, text, re.M)
            old = found[0] if len(found) == 1 else None
        if old is None or text.count(old) != 1:
            raise AssertionError('%s: the pin line %r is not in it once' % (rel, old or name))
        with open(p, 'w') as f:
            f.write(text.replace(old, new))

    # ---- a user's host state
    def seed(self, u, tag=OLD, sha=OLD_SHA, record=True, name='build'):
        """U's ~/build (or ~/NAME) as an older release left it: a marker file, a program, and its .release (none
        with record=False: a tree installed by hand before W4)."""
        b = os.path.join(self.home(u), name)
        self.write(os.path.join(b, 'OLD-RELEASE'), '%s\n' % tag)
        self.write(os.path.join(b, 'bin', 'runner-updater'), '#!/bin/sh\necho old\n', 0o755)
        if record:
            self.write(os.path.join(b, '.release'), 'tag %s\nsha256 %s\n' % (tag, sha))
        os.chmod(b, 0o755)
        self.own(u, b)
        return b

    def settle(self, u, rel, wayback=True):
        """U as REL's files leave a host whose other steps are done: the updater's link and timer units (both users);
        RS_USER's ~/bin files 03 installs, its unit, a runscaler binary of REL's pin and (WAYBACK) the way back's
        download that the release before kept in ~/build/dl."""
        h = self.home(u)
        src = os.path.join(rel.tree, 'linux-docker')
        for n in ('runner-updater.service', 'runner-updater.timer'):
            self.write(os.path.join(h, '.config', 'systemd', 'user', n), open(os.path.join(src, 'config', n)).read())
        os.makedirs(os.path.join(h, 'bin'), exist_ok=True)
        if not os.path.lexists(os.path.join(h, 'bin', 'runner-updater')):
            os.symlink(os.path.join(h, 'build', 'bin', 'runner-updater'), os.path.join(h, 'bin', 'runner-updater'))
        if u == self.rs:
            for s, d in (('bin/runner-start', 'bin/runner-start'), ('bin/pool-ready', 'bin/pool-ready'),
                         ('bin/validate-class', 'bin/validate-class'),
                         ('config/runscaler.service', '.config/systemd/user/runscaler.service')):
                shutil.copy(os.path.join(src, s), os.path.join(h, d))
            self.write(os.path.join(h, 'bin', 'runner'), BINARY, 0o755)
            os.makedirs(os.path.join(h, '.config', 'runner'), exist_ok=True)
            if wayback:
                self.write(os.path.join(h, 'build', 'dl', 'runner-v0.12.0-linux-amd64.tar.gz'), WAYBACK)
                self.own(u, os.path.join(h, 'build'))
        for d in ('bin', '.config'):
            self.own(u, os.path.join(h, d))

    # ---- the line, as a user (Y-8: the rendered line through bash -s -- FLAGS, the line on stdin)
    def argv(self, u, flags, umask):
        env = ['HOME=' + self.home(u), 'USER=' + u, 'LOGNAME=' + u, 'LC_ALL=C',
               'PATH=%s:%s' % (os.path.join(self.root, 'stubs'), SYS_PATH)]
        inner = ['bash', '-c', 'umask %s; exec bash -s -- "$@"' % umask, 'bash'] + list(flags)
        if u == 'root':
            return ['env', '-i', 'HOME=/root', 'LC_ALL=C', 'PATH=%s:%s' % (os.path.join(self.root, 'stubs'), SYS_PATH)] \
                + inner
        return ['runuser', '-u', u, '--', 'env', '-i'] + env + inner

    def line(self, u, rel, *flags, umask='022', rc=None, timeout=300):
        with open(rel.line) as f:
            r = subprocess.run(self.argv(u, flags, umask), stdin=f, capture_output=True, text=True, timeout=timeout,
                               cwd='/')
        if rc is not None:
            self.t.assertEqual(r.returncode, rc, r.stdout[-4000:] + r.stderr[-2000:])
        return r

    def start(self, u, rel, *flags):
        f = open(rel.line)
        p = subprocess.Popen(self.argv(u, flags, '022'), stdin=f, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, cwd='/', start_new_session=True)

        def stop():
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.communicate()
            f.close()
        self.t.addCleanup(stop)
        return p

    def hold(self, u, path):
        """A process of U that holds flock(PATH) until the cell ends (or until the function it returns is called);
        returns once it holds it."""
        ready = os.path.join(self.home(u), '.held-%s' % secrets.token_hex(3))
        p = subprocess.Popen(['runuser', '-u', u, '--', 'bash', '-c',
                              'mkdir -p "${1%/*}" && exec 9>> "$1" && flock 9 && : > "$2" && exec sleep 600', 'x',
                              path, ready], start_new_session=True, stdin=subprocess.DEVNULL)

        def stop():
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
        self.t.addCleanup(stop)
        for _ in range(200):
            if os.path.exists(ready):
                return stop
            time.sleep(0.05)
        self.t.fail('the holder of %s did not start' % path)

    # ---- what a home holds
    def build(self, u):
        return os.path.join(self.home(u), 'build')

    def tree(self, path):
        """{relative path: (kind, mode, sha256 or link target)} of the tree at PATH (PATH itself as '.')."""
        out = {}
        for d, dirs, names in os.walk(path):
            dirs.sort()
            for n in ['.'] + sorted(dirs + names) if d == path else sorted(dirs + names):
                p = path if n == '.' else os.path.join(d, n)
                st = os.lstat(p)
                rel = os.path.relpath(p, path)
                if stat.S_ISLNK(st.st_mode):
                    out[rel] = ('link', 0, os.readlink(p))
                elif stat.S_ISDIR(st.st_mode):
                    out[rel] = ('dir', stat.S_IMODE(st.st_mode), None)
                else:
                    out[rel] = ('file', stat.S_IMODE(st.st_mode), sha256_file(p))
        return out

    def wanted(self, rel):
        """The tree today's README Install step 3 makes from REL (linux-docker/ as ~/build, with setup/tls-excluded-spki
        and core/), modes 0755/0644 (F9's parity), plus .release; {relative path: (kind, mode, sha256)}."""
        out = {}
        for sub, at in (('linux-docker', ''), ('core', 'core'), (os.path.join('setup', 'tls-excluded-spki'),
                                                                 os.path.join('setup', 'tls-excluded-spki'))):
            src = os.path.join(rel.tree, sub)
            if os.path.isfile(src):
                out[at] = ('file', 0o644, sha256_file(src))
                continue
            for k, (kind, mode, h) in self.tree(src).items():
                key = os.path.normpath(os.path.join(at, k)) if at else k
                x = 0o755 if kind == 'dir' or mode & 0o100 else 0o644
                out[key] = (kind, x, h)
        out['.release'] = ('file', 0o644, hashlib.sha256(('tag %s\nsha256 %s\n' % (rel.tag, rel.sha)).encode())
                           .hexdigest())
        return out

    def installed(self, u, rel, dl=None):
        """U's ~/build is REL's whole tree (wanted), and with DL ({name: bytes}) its dl/ holds exactly those."""
        got = self.tree(self.build(u))
        dls = {k: v for k, v in got.items() if k == 'dl' or k.startswith('dl/')}
        for k in dls:
            del got[k]
        self.t.assertEqual(got, self.wanted(rel), 'the installed ~/build of %s is not %s' % (u, rel.tag))
        if dl is not None:
            want = {'dl/' + n: ('file', 0o644, hashlib.sha256(b).hexdigest()) for n, b in dl.items()}
            if want:
                want['dl'] = ('dir', 0o755, None)
            self.t.assertEqual(dls, want)

    def leftovers(self, u):
        """What a run must never leave in U's home: staging (~/build.new.*), the line's own download and unpack."""
        return sorted(n for n in os.listdir(self.home(u))
                      if n.startswith('build.new') or n.startswith('.release-dl.') or n.startswith('.release-unpack.'))

    def prevs(self, u):
        return sorted(n for n in os.listdir(self.home(u)) if n.startswith('build.prev.'))


def archive(top, version, extra=()):
    """The tarball of TOP/<VERSION>/ as `git archive --prefix=<VERSION>/` makes it (members <VERSION>/..., folders and
    programs 0775, other files 0664, owner 0), gzip; EXTRA (TarInfo, bytes or None) appended."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz', format=tarfile.PAX_FORMAT) as t:
        for d, dirs, names in os.walk(os.path.join(top, version)):
            dirs.sort()
            rel = os.path.relpath(d, top)
            i = tarfile.TarInfo(rel + '/')
            i.type, i.mode, i.mtime = tarfile.DIRTYPE, 0o775, 1763337600
            t.addfile(i)
            for n in sorted(names):
                p = os.path.join(d, n)
                with open(p, 'rb') as f:
                    b = f.read()
                i = tarfile.TarInfo(os.path.join(rel, n))
                i.size, i.mtime = len(b), 1763337600
                i.mode = 0o775 if os.stat(p).st_mode & 0o100 else 0o664
                t.addfile(i, io.BytesIO(b))
        for i, b in extra:
            t.addfile(i, io.BytesIO(b) if b is not None else None)
    return buf.getvalue()


def member(name, kind='file', data=b'x\n', target=None):
    i = tarfile.TarInfo(name)
    i.mtime, i.mode = 1763337600, 0o664
    if kind == 'file':
        i.size = len(data)
        return i, data
    i.type = {'symlink': tarfile.SYMTYPE, 'hardlink': tarfile.LNKTYPE, 'chardev': tarfile.CHRTYPE,
              'fifo': tarfile.FIFOTYPE}[kind]
    if target:
        i.linkname = target
    if kind == 'chardev':
        i.devmajor, i.devminor = 1, 3
    return i, None


def last(r):
    lines = r.stdout.strip().splitlines()
    return lines[-1] if lines else ''


def finals(r):
    """The run's DONE, REFUSE and NEXT lines."""
    return [l for l in r.stdout.splitlines() if re.match(r'(DONE|REFUSE|NEXT) ', l)]


@needs_container
class TheLine(unittest.TestCase):
    """X-1, X-2 (the line's half), Y-9's -q."""

    def test_x1_root_is_refused_before_anything_is_downloaded_and_control_run_user_installs(self):
        """X-1. MUTANT: the line without its root check -> the download reaches the server (red)."""
        h = Host(self)
        rel = h.release('v0.3.0')
        r = h.line('root', rel, rc=1)
        self.assertEqual(finals(r), ['REFUSE v0.3.0: run this line as the host\'s RUN_USER or RS_USER, never as root: '
                                     'nothing downloaded'], r.stdout + r.stderr)
        self.assertEqual(h.hub.paths(), [], 'root\'s run reached the server')
        self.assertFalse([n for n in os.listdir('/root') if n.startswith('.release-')], os.listdir('/root'))
        h.seed(h.run)
        r = h.line(h.run, rel, rc=0)                                   # the control
        self.assertEqual(last(r), 'DONE v0.3.0: nothing else to do', r.stdout)
        h.installed(h.run, rel)

    def test_x1_a_user_the_host_config_does_not_name_is_refused_and_nothing_changes(self):
        """X-1: the role comes from the host config. MUTANT: no role check -> it installs (red)."""
        h = Host(self)
        h.sh('useradd', '-m', '-U', '-s', '/bin/bash', h.other)
        self.addCleanup(h.drop_user, h.other)
        b = h.seed(h.other)
        before = h.tree(b)
        rel = h.release('v0.3.0')
        r = h.line(h.other, rel, rc=1)
        self.assertEqual(finals(r), ['REFUSE v0.3.0: run this line as %s or %s (the host config\'s RUN_USER and RS_USER), '
                                     'not as %s: nothing changed' % (h.run, h.rs, h.other)], r.stdout + r.stderr)
        self.assertEqual(h.tree(b), before)
        self.assertEqual(h.leftovers(h.other), [])

    def test_x2_a_tarball_of_another_sha256_is_refused_nothing_unpacked_and_control(self):
        """X-2: the sha256 baked into the line decides; MUTANT: no compare -> it installs the other bytes (red)."""
        h = Host(self)
        b = h.seed(h.run)
        before = h.tree(b)
        good = h.release('v0.3.0')
        bad = h.release('v0.3.0-rc.9', served=b'not the release\n' * 64)
        r = h.line(h.run, bad, rc=1)
        self.assertEqual(finals(r), ['REFUSE v0.3.0-rc.9: the download failed, or it is not this release (sha256 %s): '
                                     'nothing unpacked' % bad.sha], r.stdout + r.stderr)
        self.assertEqual(h.tree(b), before)
        self.assertEqual(h.leftovers(h.run), [])
        self.assertIn(bad.path, h.hub.paths(), 'the premise: it downloaded the bytes it refused')
        r = h.line(h.run, good, rc=0)                                  # the control
        h.installed(h.run, good)

    def test_x2_the_unpack_admits_only_plain_files_and_folders_under_the_version_folder(self):
        """X-2: a symlink, a hard link, a character device, a FIFO, a `..` member, an absolute path and a member
        outside <VERSION>/ each refuse, with nothing unpacked and ~/build as it was. The control: one more plain file
        under <VERSION>/ installs. MUTANT: no member check -> the symlink row installs (red)."""
        rows = (('symlink', member('0.3.0/linux-docker/evil', 'symlink', target='/etc/passwd')),
                ('hard link', member('0.3.0/linux-docker/evil', 'hardlink', target='0.3.0/VERSION')),
                ('device', member('0.3.0/linux-docker/evil', 'chardev')),
                ('fifo', member('0.3.0/linux-docker/evil', 'fifo')),
                ('dot dot', member('0.3.0/../evil')),
                ('absolute', member('/tmp/w4-evil')),
                ('outside', member('evil')))
        for why, extra in rows:
            with self.subTest(why):
                h = Host(self)
                b = h.seed(h.run)
                before = h.tree(b)
                rel = h.release('v0.3.0', extra=(extra,))
                r = h.line(h.run, rel, rc=1)
                self.assertEqual(finals(r), ['REFUSE v0.3.0: the tarball holds a member that is not a plain file or a '
                                             'folder under 0.3.0/ (a link, a device, a FIFO, a .. or an absolute '
                                             'path): nothing unpacked'], r.stdout + r.stderr)
                self.assertEqual(h.tree(b), before)
                self.assertEqual(h.leftovers(h.run), [])
                self.assertFalse(os.path.lexists('/tmp/w4-evil'))
        h = Host(self)                                                 # the control
        h.seed(h.run)
        rel = h.release('v0.3.0', extra=(member('0.3.0/linux-docker/plain', data=b'plain\n'),))
        r = h.line(h.run, rel, rc=0)
        self.assertEqual(h.tree(h.build(h.run))['plain'], ('file', 0o644, hashlib.sha256(b'plain\n').hexdigest()))

    def test_x2_modes_are_0755_and_0644_under_umask_077_and_002(self):
        """X-2/X-9: a git-archive tarball's 0775/0664, unpacked under the caller's umask 077 and 002: every folder
        0755, every program 0755, every other file 0644 (wanted). MUTANT: no `umask 022` in the line -> 0700/0600
        and 0775/0664 (red)."""
        for um in ('077', '002'):
            with self.subTest(umask=um):
                h = Host(self)
                h.seed(h.run)
                rel = h.release('v0.3.0')
                r = h.line(h.run, rel, umask=um, rc=0)
                h.installed(h.run, rel)
                self.assertEqual(stat.S_IMODE(os.stat(h.build(h.run)).st_mode), 0o755, r.stdout)

    def test_y9_a_curlrc_with_an_authorization_header_sends_none(self):
        """Y-9 (opus r3 F7): each user's ~/.curlrc holds an Authorization header; the line's download and RS_USER's
        runscaler download send none (each curl starts with -q). MUTANT: the line's curl without -q -> the header
        reaches the server (red)."""
        h = Host(self)
        rel = h.release('v0.3.0')
        for u in (h.run, h.rs):
            h.seed(u)
            h.settle(u, rel)
            h.write(os.path.join(h.home(u), '.curlrc'), 'header = "Authorization: token planted-by-the-cell"\n', 0o600,
                    owner=u)
        h.line(h.run, rel, rc=0)
        h.line(h.rs, rel, rc=0)
        self.assertEqual(h.hub.paths().count(rel.path), 2, h.hub.paths())          # the premise: both were sent
        self.assertIn(RS_PATH % '0.22.0', h.hub.paths())
        self.assertEqual([p for p, hd in h.hub.requests if 'authorization' in hd], [])


@needs_container
class Order(unittest.TestCase):
    """X-5, Y-8, Y-9 (F10)."""

    def test_x5_newer_by_the_release_order_installs(self):
        """rc.10 after rc.3 (numeric rc); a final release after its rcs; a tree with no .release (installed by hand
        before W4) is unknown and takes any release. MUTANT: the tags compared as text -> rc.10 refused (red)."""
        for cur, new in (('v0.3.0-rc.3', 'v0.3.0-rc.10'), ('v0.3.0-rc.3', 'v0.3.0'), (None, 'v0.3.0-rc.1')):
            with self.subTest(cur=cur, new=new):
                h = Host(self)
                h.seed(h.run, tag=cur or OLD, record=cur is not None)
                rel = h.release(new)
                r = h.line(h.run, rel, rc=0)
                self.assertEqual(last(r), 'DONE %s: nothing else to do' % new, r.stdout)
                h.installed(h.run, rel)

    def test_x5_an_older_release_is_refused_and_y8_older_through_bash_s_installs_it(self):
        """An older tag REFUSEs with nothing changed; the same line with `bash -s -- --older` installs it (the template
        passes "$@"). MUTANT: the template without "$@" -> --older never arrives, refused (red)."""
        h = Host(self)
        b = h.seed(h.run, tag='v0.3.0')
        before = h.tree(b)
        rel = h.release('v0.3.0-rc.3')
        r = h.line(h.run, rel, rc=1)
        self.assertEqual(finals(r), ['REFUSE v0.3.0-rc.3: ~/build runs v0.3.0, newer than v0.3.0-rc.3: nothing changed; '
                                     'to go back to v0.3.0-rc.3 on purpose, run this line with --older'], r.stdout)
        self.assertEqual(h.tree(b), before)
        r = h.line(h.run, rel, '--older', rc=0)
        h.installed(h.run, rel)

    def test_y9_the_same_tag_again_is_already_installed_and_same_installs_it_again(self):
        """F10: the line of the installed tag and sha256 again: `DONE <tag>: already installed`, exit 0, no switch;
        `--same` installs a fresh copy (a new ~/build.prev.*). A tree of the same tag with another sha256 needs
        --same."""
        h = Host(self)
        h.seed(h.run)
        rel = h.release('v0.3.0')
        h.line(h.run, rel, rc=0)
        prevs, ino = h.prevs(h.run), os.stat(h.build(h.run)).st_ino
        r = h.line(h.run, rel, rc=0)
        self.assertEqual(last(r), 'DONE v0.3.0: already installed (~/build/.release names it, sha256 %s): nothing '
                                  'changed; --same installs it again' % rel.sha, r.stdout)
        self.assertEqual((h.prevs(h.run), os.stat(h.build(h.run)).st_ino), (prevs, ino))
        r = h.line(h.run, rel, '--same', rc=0)
        self.assertEqual(len(h.prevs(h.run)), len(prevs) + 1, r.stdout)
        h.installed(h.run, rel)
        other = Host(self)
        other.seed(other.run, tag='v0.3.0', sha='b' * 64)
        rel2 = other.release('v0.3.0')
        r = other.line(other.run, rel2, rc=1)
        self.assertEqual(finals(r), ['REFUSE v0.3.0: ~/build runs v0.3.0 of another sha256 (%s): nothing changed; '
                                     '--same installs this one' % ('b' * 12)], r.stdout)
        other.line(other.run, rel2, '--same', rc=0)

    def test_f2_one_tag_spelling_a_leading_zero_is_refused_where_a_tag_is_read(self):
        """codex r1 F2 (fix round 1): ONE spelling of a tag, no leading zero in any number. The line of a release
        tagged v00.3.0 (the renderer takes it) refuses at the installer's first check, nothing changed; a
        ~/build/.release that names v0.03.0 cannot be read (rr_release_record), so the line of v0.3.0 refuses. The
        control: a record of v0.2.0 -> v0.3.0 installs. MUTANT: leading zeros allowed -> the first row installs and
        the second compares v0.3.0 equal to v0.03.0 (red)."""
        why = 'is not a release tag v<N.N.N> or v<N.N.N>-rc.<N> (each N a number with no leading zero)'
        h = Host(self)
        b = h.seed(h.run)
        before = h.tree(b)
        rel = h.release('v00.3.0')
        r = h.line(h.run, rel, rc=1)
        self.assertEqual(finals(r), ['REFUSE v00.3.0: [v00.3.0] %s: nothing changed' % why], r.stdout + r.stderr)
        self.assertEqual((h.tree(b), h.leftovers(h.run)), (before, []))
        h.seed(h.run, tag='v0.03.0')
        before = h.tree(b)
        rel = h.release('v0.3.0')
        r = h.line(h.run, rel, rc=1)
        self.assertEqual(finals(r), ['REFUSE v0.3.0: ~/build/.release cannot be read (its tag [v0.03.0] %s): nothing '
                                     'changed' % why], r.stdout + r.stderr)
        self.assertEqual((h.tree(b), h.leftovers(h.run)), (before, []))
        h.seed(h.run, tag='v0.2.0')                                     # the control
        h.line(h.run, rel, rc=0)
        h.installed(h.run, rel)

    def test_f1_a_re_run_of_the_installed_release_names_its_next_lines_and_as_rs_user_runs_the_pass(self):
        """opus r1 F1 (fix round 1; its probe p1 measured the shape): the README sends a cut run back to "run the same
        line again", and a cut after the switch leaves the release installed, so the re-run is `already installed`. It
        changes nothing (no switch: no new ~/build.prev.*, ~/build's inode kept), but it still checks and prints the
        NEXT lines the first run printed, and as RS_USER it still runs `pass` and `status` and reads them by Y-6 (exit
        3 when the pass did not end well). The control: nothing outstanding -> only `DONE <tag>: already installed
        ...`. MUTANT: the identity's early exit kept -> the re-runs print no NEXT line and run no pass (red)."""
        def rig(u, wayback=True):
            h = Host(self)
            rel = h.release('v0.3.0')
            h.seed(h.run)
            if u == 'rs':
                h.line(h.run, rel, rc=0)                                # RUN_USER first
                h.seed(h.rs)
            h.settle(h.run if u == 'run' else h.rs, rel, wayback=wayback)
            return h, rel, h.run if u == 'run' else h.rs

        def moved_pin(h, u):
            h.write(os.path.join(h.home(u), 'bin', 'runner'), b'another runscaler\n', 0o755, owner=u)

        def old_timer(h, u):
            h.write(os.path.join(h.home(u), '.config', 'systemd', 'user', 'runner-updater.timer'), '[Timer]\nold\n',
                    owner=u)
        for name, who, wayback, change, nexts in (
                ('RS_USER, a moved runscaler pin', 'rs', True, moved_pin, 1),
                ('RS_USER, the way back not kept', 'rs', False, None, 1),
                ('RUN_USER, a changed timer unit', 'run', True, old_timer, 1),
                ('RS_USER, nothing outstanding (the control)', 'rs', True, None, 0),
                ('RUN_USER, nothing outstanding (the control)', 'run', True, None, 0)):
            with self.subTest(name):
                h, rel, u = rig(who, wayback)
                if change:
                    change(h, u)
                first = h.line(u, rel, rc=0)
                f1 = finals(first)
                self.assertEqual(len(f1), 1 + nexts, first.stdout)
                self.assertEqual(f1[0], 'DONE v0.3.0' if nexts else 'DONE v0.3.0: nothing else to do', first.stdout)
                prevs, ino = h.prevs(u), os.stat(h.build(u)).st_ino
                r = h.line(u, rel, rc=0)
                self.assertEqual(finals(r), ['DONE v0.3.0: already installed (~/build/.release names it, sha256 %s): '
                                             'nothing changed; --same installs it again' % rel.sha] + f1[1:], r.stdout)
                self.assertEqual((h.prevs(u), os.stat(h.build(u)).st_ino), (prevs, ino), 'the re-run switched')
                self.assertEqual(h.calls(u), ['pass', 'status', 'pass', 'status'] if who == 'rs' else [])
                self.assertEqual(h.leftovers(u), [])
        h, rel, u = rig('rs')                                           # Y-6 on the re-run
        h.line(u, rel, rc=0)
        h.answer(u, 'pass', 'echo "runner-updater: REFUSE no facts"; exit 1\n')
        r = h.line(u, rel, rc=3)
        self.assertEqual(finals(r), ['DONE v0.3.0: the files are installed, but the pass says: runner-updater: REFUSE no '
                                     'facts (README Install step 3; "An unfinished window the updater cannot end")'],
                         r.stdout)
        self.assertEqual(h.calls(u), ['pass', 'status', 'pass', 'status'])

    def test_x5_rs_user_before_run_user_is_refused_and_control_run_user_first(self):
        """RS_USER refuses until RUN_USER's ~/build/.release names the same tag and sha256 (--older too). MUTANT: no
        check -> RS_USER installs first (red)."""
        h = Host(self)
        h.seed(h.run)
        b = h.seed(h.rs)
        rel = h.release('v0.3.0')
        h.settle(h.rs, rel)
        before = h.tree(b)
        for flags in ((), ('--older',)):
            with self.subTest(flags=flags):
                r = h.line(h.rs, rel, *flags, rc=1)
                self.assertEqual(finals(r), ['REFUSE v0.3.0: run this line as %s first (its ~/build/.release names %s, '
                                             'sha256 %s): nothing changed' % (h.run, OLD, OLD_SHA[:12])], r.stdout)
                self.assertEqual(h.tree(b), before)
        h.line(h.run, rel, rc=0)                                       # the control
        h.line(h.rs, rel, rc=0)
        h.installed(h.rs, rel, dl=RS_DL)

    def test_x5_the_order_function_and_its_grammar(self):
        """runner-release.sh's rr_tag_cmp, the ONE order function (the installer and the notice): RR_CMP of A and B;
        a tag outside the renderer's grammar, v<N.N.N> or v<N.N.N>-rc.<N> with N from 1 and no leading zero (Y-9 F11,
        X-6''), is refused (rc 1), and so is a leading zero in any number (codex r1 F2: ONE spelling of a tag; the
        controls v0.3.0 and v10.0.0 are accepted). MUTANT: leading zeros allowed -> the v00.3.0 rows go on (red)."""
        lib = os.path.join(REPO, 'linux-docker', 'setup', 'runner-release.sh')
        for a, b, want in (('v0.3.0-rc.3', 'v0.3.0-rc.10', '-1'), ('v0.3.0-rc.10', 'v0.3.0-rc.3', '1'),
                           ('v0.3.0-rc.3', 'v0.3.0', '-1'), ('v0.3.0', 'v0.3.0-rc.99', '1'), ('v0.3.0', 'v0.3.0', '0'),
                           ('v0.10.0', 'v0.9.0', '1'), ('v1.0.0', 'v0.99.99', '1'), ('v0.3.1-rc.1', 'v0.3.0', '1'),
                           ('v0.3.0-rc.1', 'v0.3.0-rc.9', '-1'), ('v10.0.0', 'v9.9.9', '1'), ('v10.0.0', 'v0.3.0', '1'),
                           ('v0.0.0', 'v0.0.1', '-1')):
            r = subprocess.run(['bash', '-c', '. "$0" && rr_tag_cmp "$1" "$2" && echo "$RR_CMP"', lib, a, b],
                               capture_output=True, text=True, env={'HOME': '/nonexistent', 'PATH': SYS_PATH})
            self.assertEqual((r.returncode, r.stdout.strip()), (0, want), (a, b, r.stderr))
        for bad in ('v0.3', '0.3.0', 'v0.3.0-beta.1', 'v0.3.0+b', 'v0.3.0-rc.', 'v0.3.0-rc.1x', 'v0.3.0\nv0.4.0', '',
                    'v0.3.0-rc.0', 'v0.3.0-rc.01',      # X-6'': an rc number starts at 1, with no leading zero
                    'v00.3.0', 'v0.03.0', 'v0.3.00', 'v01.0.0'):   # codex r1 F2: nor any other number
            r = subprocess.run(['bash', '-c', '. "$0" && rr_tag_cmp "$1" v0.3.0; echo "rc=$? [$RR_CMP]"', lib, bad],
                               capture_output=True, text=True, env={'HOME': '/nonexistent', 'PATH': SYS_PATH})
            self.assertEqual(r.stdout.strip(), 'rc=1 []', repr(bad))


@needs_container
class Switch(unittest.TestCase):
    """X-3, Y-1, Y-6."""

    def test_x3_a_cut_between_the_two_renames_is_healed_by_the_next_run(self):
        """codex r1 F4 / r3 F2's shape: the cut left no ~/build, the old tree as ~/build.prev.<UTC> and a complete
        staging folder. The next run moves the newest prev back (and says so), removes the staging leftover, and
        installs. MUTANT: no heal -> the old tree is not kept as a prev, the line says nothing (red)."""
        h = Host(self)
        h.seed(h.run, name='build.prev.20261101T000000Z')
        h.seed(h.run, tag='v0.1.0', name='build.prev.20261001T000000Z')
        rel = h.release('v0.3.0')
        cut = os.path.join(h.home(h.run), 'build.new.CUTCUTCU')
        shutil.copytree(os.path.join(rel.tree, 'linux-docker'), cut)
        h.own(h.run, cut)
        r = h.line(h.run, rel, rc=0)
        self.assertIn('HEALED: ~/build was missing (a cut between the two renames of an install): moved '
                      '~/build.prev.20261101T000000Z back to ~/build', r.stdout)
        h.installed(h.run, rel)
        self.assertEqual(h.leftovers(h.run), [])
        kept = [p for p in h.prevs(h.run) if os.path.exists(os.path.join(h.home(h.run), p, 'OLD-RELEASE'))
                and open(os.path.join(h.home(h.run), p, 'OLD-RELEASE')).read() == OLD + '\n']
        self.assertEqual(len(kept), 1, h.prevs(h.run))
        self.assertNotEqual(kept[0], 'build.prev.20261101T000000Z', 'the healed tree is a new prev, of this switch')

    def test_x3_the_updater_lock_held_refuses_and_control_released(self):
        """Under the user's updater lock: held (a pass runs) -> REFUSE, nothing changed. MUTANT: no updater lock ->
        it switches (red)."""
        h = Host(self)
        b = h.seed(h.run)
        before = h.tree(b)
        rel = h.release('v0.3.0')
        lock = os.path.join(h.home(h.run), '.local', 'state', 'runner-updater', 'lock')
        free = h.hold(h.run, lock)
        r = h.line(h.run, rel, rc=1)
        self.assertEqual(finals(r), ['REFUSE v0.3.0: the updater runs now (it holds %s): nothing changed; run this line '
                                     'again when its pass ends' % lock], r.stdout)
        self.assertEqual(h.tree(b), before)
        self.assertEqual(h.leftovers(h.run), [])
        free()                                                          # the control: the holder gone
        h.line(h.run, rel, rc=0)
        h.installed(h.run, rel)

    def test_x3_rs_user_s_pool_image_lock_held_refuses(self):
        """RS_USER takes pool-image.sh's lock too (after the updater lock, as the updater's child does): held -> REFUSE,
        nothing changed; the control: free -> DONE."""
        h = Host(self)
        rel = h.release('v0.3.0')
        h.seed(h.run)
        h.line(h.run, rel, rc=0)
        b = h.seed(h.rs)
        h.settle(h.rs, rel)
        before = h.tree(b)
        lock = os.path.join(h.home(h.rs), '.config', 'runner', 'pool-image.lock')
        h.hold(h.rs, lock)
        r = h.line(h.rs, rel, rc=1)
        self.assertEqual(finals(r), ['REFUSE v0.3.0: a pool-image.sh run holds %s: nothing changed; run this line again '
                                     'when it ends' % lock], r.stdout)
        self.assertEqual(h.tree(b), before)

    def test_x3_a_window_journal_refuses_anyway_installs_and_y6_done_reads_the_pass(self):
        """RS_USER's window journal there -> REFUSE, nothing changed; `--anyway` installs, and its pass and status
        decide DONE (Y-6): a journal status still shows -> `DONE <tag>: the files are installed, but the pass says`,
        exit 3; a pass that ends it -> DONE, exit 0. MUTANT: no journal check -> the first row installs (red)."""
        for ends in (False, True):
            with self.subTest(the_pass_ends_it=ends):
                h = Host(self)
                rel = h.release('v0.3.0')
                h.seed(h.run)
                h.line(h.run, rel, rc=0)
                b = h.seed(h.rs)
                h.settle(h.rs, rel)
                win = os.path.join(h.home(h.rs), '.local', 'state', 'runner-updater', 'window')
                h.write(win, 'kind switch\n', 0o600, owner=h.rs)
                h.own(h.rs, os.path.join(h.home(h.rs), '.local'))
                before = h.tree(b)
                r = h.line(h.rs, rel, rc=1)
                self.assertEqual(last(r), 'REFUSE v0.3.0: a window journal is there (%s): nothing changed. Run '
                                          '~/bin/runner-updater pass, then status, until status shows no window journal '
                                          'line, then this line again; an updater too old to end it (STOP RECOVER '
                                          'needed): this line with --anyway' % win, r.stdout)
                self.assertEqual(h.tree(b), before)
                if ends:
                    h.answer(h.rs, 'pass', 'rm -f "$HOME/.local/state/runner-updater/window"\n')
                r = h.line(h.rs, rel, '--anyway', rc=0 if ends else 3)
                h.installed(h.rs, rel, dl=RS_DL)
                self.assertEqual(h.calls(h.rs), ['pass', 'status'])
                if ends:
                    self.assertEqual(last(r), 'DONE v0.3.0: nothing else to do', r.stdout)
                else:
                    self.assertIn('DONE v0.3.0: the files are installed, but the pass says: runner-updater: status: a '
                                  'window journal is open: %s' % win, r.stdout)

    def test_y6_done_reads_the_pass_and_the_locks_are_released_before_it(self):
        """Y-6: the pass's exit code not 0, or a WAIT -> `DONE <tag>: the files are installed, but the pass says: <its
        line>`, exit 3; a pass that fails with no output (codex r1 F1: its failure is tracked apart from its text) ->
        `DONE <tag>: the files are installed, but the pass failed (exit N)`, exit 3. The control: the pass is free to
        take the updater lock (the cells' updater says `another run holds the updater lock` when a fresh open cannot
        take it) -> DONE, exit 0. MUTANT: the updater lock held through the pass -> exit 3 on the control (red);
        the failure read from the text alone -> the silent row is DONE, exit 0 (red)."""
        for name, answer, rc, said in (
                ('rc 1', 'echo "runner-updater: REFUSE no facts"; exit 1', 3,
                 'the pass says: runner-updater: REFUSE no facts'),
                ('wait', 'echo "runner-updater: WAIT the state holds members this release does not read"; exit 4', 3,
                 'the pass says: runner-updater: WAIT the state holds members this release does not read'),
                ('rc 5, no output', 'exit 5', 3, 'the pass failed (exit 5)'),
                ('control', None, 0, None)):
            with self.subTest(name):
                h = Host(self)
                rel = h.release('v0.3.0')
                h.seed(h.run)
                h.line(h.run, rel, rc=0)
                h.seed(h.rs)
                h.settle(h.rs, rel)
                if answer:
                    h.answer(h.rs, 'pass', answer + '\n')
                r = h.line(h.rs, rel, rc=rc)
                if said:
                    self.assertIn('DONE v0.3.0: the files are installed, but %s' % said, r.stdout)
                    self.assertEqual(len([l for l in finals(r) if l.startswith('DONE ')]), 1, r.stdout)
                else:
                    self.assertEqual(last(r), 'DONE v0.3.0: nothing else to do', r.stdout)
                self.assertEqual(h.calls(h.rs), ['pass', 'status'])

    def test_x3_only_the_last_3_prevs_are_kept(self):
        h = Host(self)
        for i in range(1, 6):
            h.seed(h.run, name='build.prev.2026100%dT000000Z' % i)
        h.seed(h.run)
        rel = h.release('v0.3.0')
        h.line(h.run, rel, rc=0)
        p = h.prevs(h.run)
        self.assertEqual(len(p), 3, p)
        self.assertEqual(p[:2], ['build.prev.20261004T000000Z', 'build.prev.20261005T000000Z'])

    def test_y1_one_install_at_a_time_the_second_run_during_the_first_s_download_refuses(self):
        """Y-1 (opus r3 F1, measured): RS_USER's first run is in its runscaler download (the server holds it 6 s);
        a second run of the same line starts then: it REFUSEs `another install runs`, the first is DONE, ~/build is
        the release's whole tree, and no staging is left. The control: one run is DONE (the first). MUTANT: the
        install lock only around the switch -> the second run removes the first's staging, the first fails (red).
        Fix round 1 (opus r1 F3): the server holds the first run's download until the cell lets it go (a gate, not a
        time), and while it waits, after the second run's REFUSE, the first run's own unpack is still there: the second
        run removed no leftover, because it was refused before that step. MUTANT: the leftovers removed before the
        install lock -> the first run's unpack is gone (red). Fix round 2 (codex r2 F1): the LINE takes the install
        lock before its download and the installer keeps it, so the second run is refused by the line, with nothing
        downloaded (its tarball is not asked for); a second run that is not refused would get its runscaler download at
        once. MUTANT: the installer releases the lock before the switch -> the second run goes on and removes the
        first's unpack (red)."""
        h = Host(self)
        rel = h.release('v0.3.0')
        h.seed(h.run)
        h.line(h.run, rel, rc=0)
        h.seed(h.rs)
        h.settle(h.rs, rel)
        gate = threading.Event()
        h.serve(RS_PATH % '0.22.0', RSCALER, delay=gate)
        self.addCleanup(gate.set)
        ev = threading.Event()
        h.hub.arrived[RS_PATH % '0.22.0'] = ev
        p1 = h.start(h.rs, rel)
        self.assertTrue(ev.wait(120), 'the first run never reached its download')
        h.serve(RS_PATH % '0.22.0', RSCALER)       # a second run that is not refused gets its download at once
        asked = h.hub.paths().count(rel.path)
        p2 = h.start(h.rs, rel)
        o2, _ = p2.communicate(timeout=300)
        self.assertIsNone(p1.poll(), 'the premise: the first run still waits in its download')
        self.assertEqual(len([n for n in os.listdir(h.home(h.rs)) if n.startswith('.release-unpack.')]), 1,
                         'the first run\'s own unpack is gone: %r' % h.leftovers(h.rs))
        gate.set()
        o1, _ = p1.communicate(timeout=300)
        self.assertEqual((p1.returncode, o1.strip().splitlines()[-1]), (0, 'DONE v0.3.0: nothing else to do'), o1)
        self.assertEqual(p2.returncode, 1, o2)
        lock = os.path.join(h.home(h.rs), '.local', 'state', 'runner-updater', 'install.lock')
        self.assertEqual(o2.strip().splitlines()[-1], 'REFUSE v0.3.0: another install runs (it holds %s): nothing '
                                                      'downloaded' % lock, o2)
        self.assertEqual(h.hub.paths().count(rel.path), asked, 'the second run downloaded the tarball')
        h.installed(h.rs, rel, dl=RS_DL)
        self.assertEqual(h.leftovers(h.rs), [])

    def gated(self, where, role):
        """Run B of the line, as ROLE's user, held by a GATE in its tarball download (`download`: the server holds the
        answer) or in its unpack (`unpack`: the cells' tar stops at its first -x until the cell lets it go), before the
        installer runs. Returns (host, user, release, B, its lock path, release: the function that lets B go). A
        request for the tarball after B's is answered at once (so a run A of the unfixed line does not wait)."""
        h = Host(self)
        rel = h.release('v0.3.0')
        h.seed(h.run)
        u = h.run
        if role == 'rs':
            h.line(h.run, rel, rc=0)
            h.seed(h.rs)
            h.settle(h.rs, rel)
            u = h.rs
        body = h.hub.routes[rel.path][1]
        gate = threading.Event()
        self.addCleanup(gate.set)
        mark = os.path.join(h.root, 'updater', 'tar.stopped')
        go = os.path.join(h.root, 'updater', 'tar.go')
        if where == 'download':
            h.serve(rel.path, body, delay=gate)
            h.hub.arrived[rel.path] = threading.Event()
            there = h.hub.arrived[rel.path].is_set
        else:
            h.write(os.path.join(h.root, 'stubs', 'tar'),
                    '#!/bin/bash\ncase " $* " in *" -xzf "*) if [ ! -e %s ]; then : > %s; until [ -e %s ]; do sleep 0.05; '
                    'done; fi ;; esac\nexec /usr/bin/tar "$@"\n' % (mark, mark, go), 0o755)
            self.addCleanup(lambda: os.path.isdir(h.root) and open(go, 'a').close())
            there = lambda: os.path.exists(mark)
        b = h.start(u, rel)
        for _ in range(2400):
            if there():
                break
            time.sleep(0.05)
        else:
            self.fail('run B never reached its %s' % where)
        h.serve(rel.path, body)

        def release():
            gate.set()
            open(go, 'a').close()
        lock = os.path.join(h.home(u), '.local', 'state', 'runner-updater', 'install.lock')
        return h, u, rel, b, lock, release

    def test_r2_a_run_while_another_downloads_or_unpacks_is_refused_by_the_line_and_the_other_finishes(self):
        """codex r2 F1 (fix round 2): run B of the line is held in its tarball download, then in its unpack (before
        its installer runs); run A of the same line starts then, as RUN_USER and as RS_USER. A is REFUSEd `another
        install runs` by the line, before it downloads anything (no request for the tarball); B's download and unpack
        are untouched (the same files, the same inode); B, let go, is DONE, and ~/build is the release's whole tree,
        with no leftover. The control (the next cell): B killed while it is held, then a retry removes B's files. RED on
        e3dfe25: the line took no lock before the installer, so A downloaded, unpacked, took the free install lock and
        removed B's files as a killed run's leftovers. MUTANT: the template without the lock -> red; the installer
        taking the lock again on an open of its own -> every run refused (red)."""
        for where in ('download', 'unpack'):
            for role in ('run', 'rs'):
                with self.subTest(where=where, role=role):
                    h, u, rel, b, lock, release = self.gated(where, role)
                    before = h.leftovers(u)
                    want = ['.release-dl.'] + (['.release-unpack.'] if where == 'unpack' else [])
                    self.assertEqual(sorted(n[:len(n) - 8] for n in before), sorted(want),
                                     'the premise: B\'s own files: %r' % before)
                    ino = {n: os.lstat(os.path.join(h.home(u), n)).st_ino for n in before}
                    asked = h.hub.paths().count(rel.path)
                    a = h.line(u, rel, rc=1)
                    self.assertEqual(finals(a), ['REFUSE v0.3.0: another install runs (it holds %s): nothing '
                                                 'downloaded' % lock], a.stdout + a.stderr)
                    self.assertEqual(h.hub.paths().count(rel.path), asked, 'run A downloaded the tarball')
                    self.assertEqual(h.leftovers(u), before, 'run A changed B\'s files')
                    self.assertEqual({n: os.lstat(os.path.join(h.home(u), n)).st_ino for n in before}, ino)
                    self.assertIsNone(b.poll(), 'the premise: B still waits in its %s' % where)
                    release()
                    o, _ = b.communicate(timeout=300)
                    self.assertEqual((b.returncode, o.strip().splitlines()[-1]),
                                     (0, 'DONE v0.3.0: nothing else to do'), o)
                    h.installed(u, rel, dl=RS_DL if role == 'rs' else None)
                    self.assertEqual(h.leftovers(u), [], o)

    def test_r2_the_control_a_run_killed_while_it_downloads_or_unpacks_leaves_files_the_retry_removes(self):
        """codex r2 F1's control (fix round 2): run B, held as in the cell before, is SIGKILLed (its process group: an
        OOM, a reboot); its files stay. The retry of the line takes the free install lock, removes them (`OK   removed
        ~/.release-dl.*`, and the unpack's), and is DONE with no leftover: the lock the line takes keeps nothing of a
        run that is gone. MUTANT: no removal of the line's leftovers -> they stay (red)."""
        for where in ('download', 'unpack'):
            for role in ('run', 'rs'):
                with self.subTest(where=where, role=role):
                    h, u, rel, b, lock, release = self.gated(where, role)
                    left = h.leftovers(u)
                    os.killpg(b.pid, signal.SIGKILL)
                    b.communicate(timeout=60)
                    self.assertEqual(h.leftovers(u), left, 'the premise: the kill left B\'s files')
                    release()
                    r = h.line(u, rel, rc=0)
                    self.assertEqual(last(r), 'DONE v0.3.0: nothing else to do', r.stdout)
                    for n in left:
                        self.assertIn('OK   removed ~/%s, left by a run of a line that was cut' % n, r.stdout)
                    self.assertEqual(h.leftovers(u), [], r.stdout)
                    h.installed(u, rel, dl=RS_DL if role == 'rs' else None)

    def test_r2_the_installer_keeps_the_line_s_lock_it_is_never_free_between_the_line_and_the_installer(self):
        """codex r2 F1 (fix round 2): the installer keeps the open the line took the install lock on (fd 7): at its
        `flock -n 7`, a FRESH open of install.lock cannot take the lock (it is held), as RUN_USER and as RS_USER. The
        cells' flock (a stub on PATH that runs the real one) records, for each `flock -n 7`, whether a fresh open could
        take the lock just then: the line's take finds it free, the installer's finds it held. RED: an installer that
        opens the lock again on fd 7 (the line's open closed: the lock free until it takes it again, the e3dfe25 open)
        -> `free` at the installer's (red); one that takes it on an open of its own -> refused (red)."""
        for role in ('run', 'rs'):
            with self.subTest(role=role):
                h = Host(self)
                rel = h.release('v0.3.0')
                h.seed(h.run)
                u = h.run
                if role == 'rs':
                    h.line(h.run, rel, rc=0)
                    h.seed(h.rs)
                    h.settle(h.rs, rel)
                    u = h.rs
                log = os.path.join(h.root, 'updater', u + '.flock7')
                h.write(os.path.join(h.root, 'stubs', 'flock'),
                        '#!/bin/bash\nif [ "$*" = "-n 7" ]; then\n  /usr/bin/flock -n -E 75 '
                        '"$HOME/.local/state/runner-updater/install.lock" true 7>&- < /dev/null; rc=$?\n'
                        '  case $rc in 0) w=free ;; 75) w=held ;; *) w=error$rc ;; esac\n  echo "$w" >> %s\nfi\n'
                        'exec /usr/bin/flock "$@"\n' % log, 0o755)
                r = h.line(u, rel, rc=0)
                self.assertEqual(last(r), 'DONE v0.3.0: nothing else to do', r.stdout)
                with open(log) as f:
                    self.assertEqual(f.read().split(), ['free', 'held'], 'the line\'s take, then the installer\'s')

    def test_f3_a_killed_run_leaves_its_download_or_unpack_and_the_next_run_removes_them(self):
        """opus r1 F3 (fix round 1; its probe p4 measured the SIGKILL shape): a run killed (SIGKILL: an OOM, a reboot)
        during its download leaves ~/.release-dl.*; one killed between the switch's two renames leaves
        ~/.release-unpack.* and ~/build.new.*. The next run removes every one of them under its install lock at its
        start (its own unpack excepted: it runs from it), heals, and is DONE with no leftover. MUTANT: no removal of
        the line's leftovers -> they stay (red)."""
        for where in ('the download', 'between the two renames'):
            with self.subTest(where):
                h = Host(self)
                rel = h.release('v0.3.0')
                h.seed(h.run)
                body = h.hub.routes[rel.path][1]
                mark = os.path.join(h.root, 'updater', 'mv.stopped')
                stub = os.path.join(h.root, 'stubs', 'mv')
                gate = threading.Event()
                self.addCleanup(gate.set)
                if where == 'the download':
                    h.serve(rel.path, body, delay=gate)
                    h.hub.arrived[rel.path] = threading.Event()
                    want = '.release-dl.'
                else:                                                   # opus p4's mv: stops on the second rename
                    h.write(stub, '#!/bin/bash\nfor a in "$@"; do case $a in */build.new.*) : > %s; exec sleep 600 ;; '
                                  'esac; done\nexec /usr/bin/mv "$@"\n' % mark, 0o755)
                    want = '.release-unpack.'
                p = h.start(h.run, rel)
                for _ in range(2400):
                    if (h.hub.arrived[rel.path].is_set() if where == 'the download' else os.path.exists(mark)):
                        break
                    time.sleep(0.05)
                else:
                    self.fail('the run never reached %s' % where)
                os.killpg(p.pid, signal.SIGKILL)
                p.communicate(timeout=60)
                self.assertTrue([n for n in h.leftovers(h.run) if n.startswith(want)],
                                'the premise: the kill left %s*: %r' % (want, h.leftovers(h.run)))
                if os.path.exists(stub):
                    os.remove(stub)
                h.serve(rel.path, body)
                gate.set()
                r = h.line(h.run, rel, rc=0)
                self.assertEqual(last(r), 'DONE v0.3.0: nothing else to do', r.stdout)
                self.assertEqual(h.leftovers(h.run), [], r.stdout)
                h.installed(h.run, rel)

    def test_f2_the_install_lock_is_0600_and_its_folders_have_the_role_s_modes_after_an_early_refusal(self):
        """opus r1 F2 (fix round 1): THE MODES (runner-release.sh; rr_modes, the one place, which rr_lock runs too)
        hold for the installer's own lock: RUN_USER's first run on a home with no ~/.local, refused before any change
        (an older release), leaves each folder from the home to STATEDIR 0710 (RS_USER may search it) and install.lock
        and the updater lock 0600 (a lock RS_USER could open, it could hold). The control: RS_USER's, refused early
        too (before RUN_USER), are 0700; and an install.lock an earlier release left 0644 is 0600 after the next run.
        MUTANT: the installer makes its folders itself, 0700 -> RUN_USER's row (red); install.lock made under the
        umask -> 0644 (red)."""
        def modes(u):
            h0 = h.home(u)
            out = {}
            for rel in ('.local', '.local/state', '.local/state/runner-updater',
                        '.local/state/runner-updater/install.lock', '.local/state/runner-updater/lock'):
                p = os.path.join(h0, rel)
                out[rel] = stat.S_IMODE(os.lstat(p).st_mode) if os.path.lexists(p) else None
            return out
        h = Host(self)
        rel = h.release('v0.3.0')
        old = h.release('v0.3.0-rc.1')
        h.seed(h.run, tag='v0.3.0')
        self.assertFalse(os.path.lexists(os.path.join(h.home(h.run), '.local')), 'the premise: no ~/.local')
        r = h.line(h.run, old, rc=1)
        self.assertIn('newer than v0.3.0-rc.1', last(r), r.stdout)
        self.assertEqual(modes(h.run), {'.local': 0o710, '.local/state': 0o710, '.local/state/runner-updater': 0o710,
                                        '.local/state/runner-updater/install.lock': 0o600,
                                        '.local/state/runner-updater/lock': 0o600})
        h.seed(h.rs)                                                    # the control: RS_USER's, before RUN_USER
        self.assertFalse(os.path.lexists(os.path.join(h.home(h.rs), '.local')), 'the premise: no ~/.local')
        h.line(h.rs, rel, rc=1)
        self.assertEqual(modes(h.rs), {'.local': 0o700, '.local/state': 0o700, '.local/state/runner-updater': 0o700,
                                       '.local/state/runner-updater/install.lock': 0o600,
                                       '.local/state/runner-updater/lock': 0o600})
        il = os.path.join(h.home(h.rs), '.local', 'state', 'runner-updater', 'install.lock')
        os.chmod(il, 0o644)                                             # as the first W4 build left it
        h.line(h.rs, rel, rc=1)
        self.assertEqual(stat.S_IMODE(os.lstat(il).st_mode), 0o600)


@needs_container
class Downloads(unittest.TestCase):
    """X-2 (RS_USER's downloads before the switch), Y-3."""

    def test_x2_a_wrong_runscaler_download_leaves_the_old_build_and_no_staging(self):
        """The pinned download is REQUIRED: another sha256 -> REFUSE, the old ~/build untouched, no staging left."""
        h = Host(self)
        rel = h.release('v0.3.0')
        h.seed(h.run)
        h.line(h.run, rel, rc=0)
        b = h.seed(h.rs)
        h.settle(h.rs, rel)
        before = h.tree(b)
        h.serve(RS_PATH % '0.22.0', b'another runscaler\n')
        r = h.line(h.rs, rel, rc=1)
        self.assertEqual(finals(r), ['REFUSE v0.3.0: the download of runscaler v0.22.0 failed, or its sha256 is not '
                                     '03-runscaler.sh\'s TGZ_SHA: nothing changed'], r.stdout)
        self.assertEqual(h.tree(b), before)
        self.assertEqual(h.leftovers(h.rs), [])

    def rig(self, place):
        h = Host(self)
        rel = h.release('v0.3.0')
        h.seed(h.run)
        h.line(h.run, rel, rc=0)
        h.seed(h.rs)
        h.settle(h.rs, rel, wayback=False)
        for where, name, data in place:
            h.write(os.path.join(h.home(h.rs), where, 'dl', name), data)
            if where != 'build':
                h.seed(h.rs, name=where)
            h.own(h.rs, os.path.join(h.home(h.rs), where))
        return h, rel

    def test_y3_the_way_back_download_is_found_by_its_sha256_under_any_name(self):
        """Y-3 (codex r3 F3, opus r3 F4): the pin moved, so the way back's tarball is the current tree's pinned file
        (dl/runner-linux-amd64.tar.gz); or it is in a ~/build.prev.*/dl/ under its own name: copied into the new tree
        under the candidate's name for it, KEPT. MUTANT: looked up by the candidate's name -> the pin-move row is
        NOT KEPT (red)."""
        for name, place in (('pin moved', [('build', 'runner-linux-amd64.tar.gz', WAYBACK)]),
                            ('in a prev', [('build.prev.20261101T000000Z', 'runner-v0.12.0-linux-amd64.tar.gz',
                                            WAYBACK)])):
            with self.subTest(name):
                h, rel = self.rig(place)
                r = h.line(h.rs, rel, rc=0)
                self.assertRegex(r.stdout, r'(?m)^KEPT /home/%s/build[^ ]*/dl/runner-[^ ]+ as '
                                           r'~/build/dl/runner-v0\.12\.0-linux-amd64\.tar\.gz$' % h.rs)
                h.installed(h.rs, rel, dl={'runner-linux-amd64.tar.gz': RSCALER,
                                           'runner-v0.12.0-linux-amd64.tar.gz': WAYBACK})
                self.assertEqual(last(r), 'DONE v0.3.0: nothing else to do', r.stdout)

    def test_y3_no_way_back_copy_is_not_kept_never_a_refusal_and_control_a_name_of_other_bytes(self):
        """None anywhere, or a file of the candidate's name with other bytes: NOT KEPT, a NEXT line that names the way
        back's download, DONE exit 0; the other bytes are never copied."""
        for name, place in (('none', []), ('the name, other bytes',
                                           [('build', 'runner-v0.12.0-linux-amd64.tar.gz', b'other bytes\n')])):
            with self.subTest(name):
                h, rel = self.rig(place)
                r = h.line(h.rs, rel, rc=0)
                self.assertIn('NOT KEPT: no runscaler v0.12.0 download (none has the way back\'s sha256, '
                              'WAYBACK_TGZ_SHA)', r.stdout)
                self.assertEqual(finals(r), ['DONE v0.3.0',
                                             'NEXT as %s: the way back\'s runscaler v0.12.0 download is NOT KEPT: the '
                                             'README\'s "runscaler: the release this one pins, and the way back" '
                                             'downloads it, when you take the way back' % h.rs], r.stdout)
                h.installed(h.rs, rel, dl={'runner-linux-amd64.tar.gz': RSCALER})


@needs_container
class Next(unittest.TestCase):
    """X-4, Y-5, Y-7."""

    def test_y7_a_host_config_key_the_release_needs_refuses_before_any_change(self):
        """Y-7 (opus r3 F3): the release's host.conf.example names NEW_KEY, the host config lacks it: as RUN_USER and as
        RS_USER, REFUSE before any change, naming root's Install step 1. The control: the key there -> DONE. MUTANT:
        the check after the switch -> ~/build changed (red)."""
        def edit(tree):
            p = os.path.join(tree, 'linux-docker', 'host.conf.example')
            with open(p, 'a') as f:
                f.write('# a key this release adds\nNEW_KEY=value\n')
        h = Host(self)
        rel = h.release('v0.3.0', edit=edit)
        want = ['REFUSE v0.3.0 needs root\'s step first: %s lacks NEW_KEY, or holds it more than once (README Install '
                'step 1): nothing changed' % h.conf]
        b = h.seed(h.run)
        before = h.tree(b)
        r = h.line(h.run, rel, rc=1)
        self.assertEqual(finals(r), want, r.stdout)
        self.assertEqual((h.tree(b), h.leftovers(h.run)), (before, []))
        h.seed(h.run, tag=rel.tag, sha=rel.sha)     # RS_USER's row: RUN_USER's .release names the release, as a run
        b = h.seed(h.rs)                            # of RUN_USER's that passed leaves it
        h.settle(h.rs, rel)
        before = h.tree(b)
        r = h.line(h.rs, rel, rc=1)
        self.assertEqual(finals(r), want, r.stdout)
        self.assertEqual((h.tree(b), h.leftovers(h.rs)), (before, []))
        with open(h.conf, 'a') as f:                                   # the control
            f.write('NEW_KEY=value\n')
        h.seed(h.run)
        h.line(h.run, rel, rc=0)
        h.line(h.rs, rel, rc=0)
        h.installed(h.rs, rel)

    def test_y5_each_user_names_its_own_timer_units(self):
        """Y-5 (codex r3 F5): a timer unit of RUN_USER's that is not this release's -> RUN_USER's run names
        04-timer.sh as RUN_USER; RS_USER's (its units this release's) names none. MUTANT: only RS_USER's units
        checked -> RUN_USER's row has no NEXT (red)."""
        h = Host(self)
        rel = h.release('v0.3.0')
        for u in (h.run, h.rs):
            h.seed(u)
            h.settle(u, rel)
        h.write(os.path.join(h.home(h.run), '.config', 'systemd', 'user', 'runner-updater.timer'), '[Timer]\nold\n',
                owner=h.run)
        r = h.line(h.run, rel, rc=0)
        self.assertEqual(finals(r), ['DONE v0.3.0', 'NEXT as %s: the updater\'s timer units are not this release\'s: '
                                     'bash ~/build/setup/04-timer.sh (README Install step 11)' % h.run], r.stdout)
        r = h.line(h.rs, rel, rc=0)
        self.assertEqual(finals(r), ['DONE v0.3.0: nothing else to do'], r.stdout)

    def test_x4_rs_user_names_its_pinned_files_and_a_moved_runscaler_pin(self):
        """X-4: RS_USER's ~/bin/runner-start not this release's -> a NEXT naming it; its runscaler binary not the one
        this release pins -> a NEXT naming the runscaler step (never run). The control: both this release's ->
        nothing else to do (the other cells)."""
        h = Host(self)
        rel = h.release('v0.3.0')
        h.seed(h.run)
        h.line(h.run, rel, rc=0)
        h.seed(h.rs)
        h.settle(h.rs, rel)
        h.write(os.path.join(h.home(h.rs), 'bin', 'runner-start'), '#!/bin/sh\nold\n', 0o755, owner=h.rs)
        h.write(os.path.join(h.home(h.rs), 'bin', 'runner'), b'another runscaler\n', 0o755, owner=h.rs)
        r = h.line(h.rs, rel, rc=0)
        self.assertEqual(finals(r), [
            'DONE v0.3.0',
            'NEXT as %s: bin/runner-start is not this release\'s: the next pool-image.sh up installs it (or '
            '03-runscaler.sh real: README Install step 9)' % h.rs,
            'NEXT as %s: this release pins runscaler v0.22.0, and another one runs: the runscaler step, a person\'s, at '
            'a quiet time (README "runscaler: the release this one pins, and the way back")' % h.rs], r.stdout)

    def test_f4_a_file_the_release_adds_to_installs_is_named_on_a_host_past_install_step_9(self):
        """opus r1 F4 (fix round 1; its probe p5 measured the shape): the release adds bin/new-thing to 03-runscaler.sh's
        INSTALLS; RS_USER's host has Install step 9's files (the INSTALLS of the release before), not that one -> a
        NEXT line names it, as for a file that differs. The control: a host with none of the INSTALLS files (before
        Install step 9, which installs them all) -> no NEXT line. MUTANT: an absent file skipped (the first build) ->
        the first row says nothing else to do (red)."""
        def edit(tree):
            p = os.path.join(tree, 'linux-docker', 'setup', '03-runscaler.sh')
            with open(p) as f:
                t = f.read()
            old = 'INSTALLS="bin/runner-start bin/runner-start 755\n'
            self.assertEqual(t.count(old), 1)
            with open(p, 'w') as f:
                f.write(t.replace(old, old + 'bin/new-thing bin/new-thing 755\n'))
            with open(os.path.join(tree, 'linux-docker', 'bin', 'new-thing'), 'w') as f:
                f.write('#!/bin/sh\n')
            os.chmod(os.path.join(tree, 'linux-docker', 'bin', 'new-thing'), 0o755)
        for step9 in (True, False):
            with self.subTest(past_install_step_9=step9):
                h = Host(self)
                rel = h.release('v0.3.0', edit=edit)
                h.seed(h.run)
                h.line(h.run, rel, rc=0)
                h.seed(h.rs)
                h.settle(h.rs, rel)
                if not step9:
                    for d in ('bin/runner-start', 'bin/pool-ready', 'bin/validate-class',
                              '.config/systemd/user/runscaler.service'):
                        os.remove(os.path.join(h.home(h.rs), d))
                r = h.line(h.rs, rel, rc=0)
                self.assertEqual(finals(r), [
                    'DONE v0.3.0', 'NEXT as %s: bin/new-thing is not installed: the next pool-image.sh up installs it '
                    '(or 03-runscaler.sh real: README Install step 9)' % h.rs] if step9
                    else ['DONE v0.3.0: nothing else to do'], r.stdout)


class Texts(unittest.TestCase):
    """The template's form (X-6' OUR TEMPLATE'S CONDITION, Y-8) and the README's lines (Y-2, Y-8). Text only: these run
    anywhere."""

    def test_the_template_is_one_bash_line_with_the_four_placeholders_no_other_at_and_passes_its_arguments(self):
        """X-6'': ONE line, each placeholder once, no control character; its only other `@` is the exact `"$@"`."""
        with open(os.path.join(REPO, TEMPLATE_REL), 'rb') as f:
            b = f.read()
        self.assertTrue(b.endswith(b'\n') and b.count(b'\n') == 1, 'not ONE line')
        t = b.decode('ascii')
        self.assertNotRegex(t[:-1], r'[\x00-\x1f\x7f]')
        for p in ('@URL@', '@SHA@', '@VERSION@', '@TAG@'):
            self.assertEqual(t.count(p), 1, p)
        rest = t.replace('@URL@', '').replace('@SHA@', '').replace('@VERSION@', '').replace('@TAG@', '')
        self.assertIn('"$@"', rest, 'the flags reach the installer (Y-8)')
        self.assertNotIn('@', rest.replace('"$@"', ''), 'an @ that is neither a placeholder nor the exact "$@" (X-6\'\')')
        self.assertNotRegex(t, r'bash -c|zsh|\bssh\b', 'the line is a bare bash script (X-1), run by `bash -s`')
        r = subprocess.run(['bash', '-n'], input=t, capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (0, ''))

    def test_the_readme_names_the_line_its_flags_and_the_first_way_back(self):
        """Y-8: the README's lines for the flags; Y-2: the way back to a release with no linux-install-line.txt. Fix
        round 1 (opus r1 F6): the section names the releases with the line by their asset, never by a tag (a tag cut
        between the LANDING ORDER's steps 2 and 3 has no line). MUTANT: the first build's wording, by the tag
        v0.2.0-rc.3 -> red. Studio's step 3 review (P3): the section sends the operator to the asset's check
        ("Check a release" in ../README.md: the hashes and `gh release verify-asset`) before the run."""
        with open(os.path.join(REPO, 'linux-docker', 'README.md')) as f:
            t = f.read()
        for l in ("ssh <RUN_USER>@<host> 'bash -s' < linux-install-line.txt",
                  "ssh <RS_USER>@<host> 'bash -s' < linux-install-line.txt",
                  "ssh <RUN_USER>@<host> 'bash -s -- --older' < linux-install-line.txt",
                  "'bash -s -- --same' < linux-install-line.txt", "'bash -s -- --anyway' < linux-install-line.txt"):
            self.assertIn(l, t)
        m = re.search(r'^## A release of this repository, by its install line\n(.*?)(?=^## )', t, re.M | re.S)
        self.assertTrue(m, 'no section "A release of this repository, by its install line"')
        s = m.group(1)
        for w in ('SHA256SUMS', 'Install step 3', 'Install step 4', 'RUN_USER first', 'linux-install-line.txt',
                  'A release whose assets include `linux-install-line.txt`',
                  'The way back to a release whose assets do not include `linux-install-line.txt`',
                  'Check the asset first ("Check a release" in [../README.md](../README.md))'):
            self.assertIn(w, s)
        self.assertNotRegex(s, r'\bv[0-9]+\.[0-9]+\.[0-9]+', 'the section names a release by its tag')


if __name__ == '__main__':
    unittest.main()
