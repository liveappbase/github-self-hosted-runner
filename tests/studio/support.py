"""Helpers for the tests of the host tools (stdlib only).

A test makes a Sandbox: a temporary folder, removed by the test's cleanup. In it the test
- copies a script of bin/ with exact-string rewrites. Each rewrite must match at least once, and the copy may
  then hold no host path (HOST_PATHS) except the strings the test names, so a missed rewrite fails the test
  instead of touching the host;
- writes stubs: small zsh scripts that log each call (one line, its argv quoted) and then run a body;
- holds a lock with a REAL lockf that WAITS for it (hold_lock), so a probe that takes the lock for a moment delays
  the holder and never ends it;
- runs a command with a clean environment: HOME and TMPDIR in the sandbox, PATH = the stubs folder and the
  system folders, LC_ALL=C. Nothing else of the caller's environment passes.
"""
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOST_PATHS = ('/Users/ci', '/tmp/runner.lock', '/usr/local/libexec/liveapp-ci')
SYSTEM_PATH = '/usr/bin:/bin:/usr/sbin:/sbin'
LOCK_WAIT = 120   # seconds a lock holder waits for its lock (hold_lock): well over wait_for's 60 s


def _rmtree(path):
    # a test may leave a folder or file with mode 000: give the owner its rights back first
    for top, dirs, _ in os.walk(path):
        for d in dirs:
            try:
                os.chmod(os.path.join(top, d), 0o700, follow_symlinks=False)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


class Sandbox:
    def __init__(self, test):
        self.test = test
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='studio-'))
        test.addCleanup(_rmtree, self.root)
        self.home = self.mkdir('home')
        self.tmp = self.mkdir('tmp')
        self.stubs = self.mkdir('stubs')
        self.logs = self.mkdir('logs')

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def mkdir(self, *parts):
        p = self.path(*parts)
        os.makedirs(p, exist_ok=True)
        return p

    def write(self, path, text, mode=0o644):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)
        os.chmod(path, mode)
        return path

    def copy_script(self, rel, rewrites, allow=(), dest=None):
        """Copy REPO/rel to dest (default: sandbox/tools/<name>) with each (old, new) replaced everywhere.
        Raises when an old string is absent, or when a HOST_PATHS string is left outside the allowed strings."""
        with open(os.path.join(REPO, rel)) as f:
            text = f.read()
        for old, new in rewrites:
            if old not in text:
                raise AssertionError('%s: the rewrite target is not in the script: %r' % (rel, old))
            text = text.replace(old, new)
        rest = text
        for a in allow:
            if a not in rest:
                raise AssertionError('%s: the allowed string is not in the copy: %r' % (rel, a))
            rest = rest.replace(a, '')
        for h in HOST_PATHS:
            if h in rest:
                line = next(l for l in rest.splitlines() if h in l)
                raise AssertionError('%s: the copy still names %s: %r' % (rel, h, line))
        dest = dest or self.path('tools', os.path.basename(rel))
        return self.write(dest, text, 0o755)

    def stub(self, name, body='', folder=None, log=None):
        """A zsh stub at folder/name (default: the stubs folder). Each call appends its argv to log (default:
        logs/<name>.log), then runs body."""
        folder = folder or self.stubs
        log = log or self.path('logs', name + '.log')
        text = '#!/bin/zsh -f\nprint -r -- ${(qq)@} >> %s\n%s\n' % (shlex.quote(log), body)
        return self.write(os.path.join(folder, name), text, 0o755)

    def calls(self, name, log=None):
        """The argv of each call of the stub `name`, in order."""
        log = log or self.path('logs', name + '.log')
        if not os.path.exists(log):
            return []
        with open(log) as f:
            return [shlex.split(l) for l in f.read().splitlines()]

    def env(self, extra=None):
        e = {'HOME': self.home, 'TMPDIR': self.tmp + '/', 'PATH': self.stubs + ':' + SYSTEM_PATH, 'LC_ALL': 'C'}
        e.update(extra or {})
        return e

    def run(self, argv, extra_env=None, timeout=120):
        return subprocess.run(argv, env=self.env(extra_env), cwd=self.tmp, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def start(self, argv, extra_env=None, name='proc'):
        """Start argv in a process group of its own; stdout and stderr go to files. The test's cleanup kills
        the group if anything of it is left."""
        out = open(self.path('logs', name + '.out'), 'w')
        err = open(self.path('logs', name + '.err'), 'w')
        p = subprocess.Popen(argv, env=self.env(extra_env), cwd=self.tmp, stdin=subprocess.DEVNULL,
                             stdout=out, stderr=err, start_new_session=True)
        out.close()
        err.close()

        def stop():
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            p.wait()
        self.test.addCleanup(stop)
        return p

    def output(self, name='proc'):
        with open(self.path('logs', name + '.out')) as f:
            out = f.read()
        with open(self.path('logs', name + '.err')) as f:
            return out, f.read()

    def hold_lock(self, lock, argv=('/bin/sleep', '600'), name='lock-holder'):
        """Hold lock (an flock, as runscaler's runner-start takes it) with a REAL lockf that runs argv until the test
        ends -> the lockf process, once it holds the lock. The holder WAITS for the lock (-t LOCK_WAIT): another
        process that takes it for a moment (a probe: lockf -t 0) delays the holder and never ends it. lockf runs its
        command only once it holds the lock, and the command prints `held` first: that line is the proof. A holder
        that ends before it fails the test."""
        p = self.start(['/usr/bin/lockf', '-k', '-t', str(LOCK_WAIT), lock, '/bin/zsh', '-f', '-c',
                        'print -r -- held; exec "$@"', 'holder'] + list(argv), name=name)
        self.wait_for(lambda: self.output(name)[0].startswith('held\n') or p.poll() is not None,
                      'the holder of ' + lock)
        self.test.assertIsNone(p.poll(), 'the holder could not take %s: %r' % (lock, self.output(name)))
        rc = subprocess.run(['/usr/bin/lockf', '-k', '-s', '-t', '0', lock, '/usr/bin/true']).returncode
        self.test.assertEqual(rc, 75, 'a probe reads %s free under its holder' % lock)
        return p

    def wait_for(self, check, what, timeout=60):
        """Poll until check() is true; fail the test with `what` when it never is."""
        end = time.monotonic() + timeout
        while not check():
            if time.monotonic() > end:
                self.test.fail('timed out waiting for ' + what)
            time.sleep(0.05)
