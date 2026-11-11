"""Helpers for the tests of bin/linux-image-build and bin/linux-image-smoke (stdlib only).

A Sandbox is a temporary folder, removed by the test's cleanup. In it a test
- copies a script with its host paths rewritten into the sandbox (copy_script). Each rewrite must match; then no line
  of code (a line that is not a comment) may name a host path, so a missed rewrite fails the test instead of touching
  the host. The same rewrites serve the repo script and an older copy of it (the move's proof, test_build);
- gets a SUBSTITUTE tart: it appends each call's argv to logs/tart.log, keeps its VMs as files in vms/, and answers
  `tart exec VM CMD...` from the test's RULES: (glob, rc, stdout), the first glob that matches CMD (its words joined by
  one space) wins; no match is rc 0 with no output. `tart stop VM` marks VM stopped; the substitute real-run waits
  for that mark (or its kill) and then ends, as the real one does when its VM stops;
- gets substitutes for date (`+%Y%m%d` is DATE), sleep (returns at once) and df (a large free disk) on PATH;
- runs a command with a clean environment: HOME and TMPDIR in the sandbox, PATH = the substitutes and the system
  folders, LC_ALL=C. Nothing else of the caller's environment passes. No real tart, no VM, no network: the runner
  lock is a file in the sandbox;
- installs a script (install): the script and, beside it, bin/linux-image-lib (the one reader of the host's
  linux-image.conf, which both scripts source), with the conf's path rewritten to the sandbox's conf (write_conf).
Every conf value here is a placeholder (made-up names, RFC 5737 documentation addresses).
"""
import os
import re
import shlex
import shutil
import subprocess
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(REPO, 'bin', 'linux-image-lib')
CONF = '/Users/ci/.config/runner/linux-image.conf'
HOST_PATHS = ('/Users/ci', '/tmp/runner.lock')
SYSTEM_PATH = '/usr/bin:/bin:/usr/sbin:/sbin'
DATE = '20261111'

TART = r'''#!/bin/zsh -f
print -r -- ${(qq)@} >> %(log)s
VMS=%(vms)s RULES=%(rules)s
cmd=$1; shift
case $cmd in
  (list)
    if [[ ${@[-1]} == -q ]]; then /bin/ls -1 $VMS
    else print -r -- 'Source Name Disk Size SizeOnDisk State'; for v in $VMS/*(N); do print -r -- "local ${v:t} 50 20 20 stopped"; done
    fi ;;
  (pull|set) ;;
  (clone) [[ ! -e $VMS/$2 ]] || { print -u2 -r -- "tart substitute: $2 exists"; exit 1 }; : > $VMS/$2 ;;
  (stop) : > %(marks)s/stopped-$1 ;;
  (delete) [[ -e $VMS/$1 ]] || exit 1; /bin/rm -f -- $VMS/$1 ;;
  (exec)
    shift
    c="$*"
    source $RULES
    for (( i = 1; i <= ${#pats}; i++ )); do
      if [[ $c == ${~pats[i]} ]]; then
        [[ -n $outs[i] ]] && print -r -- $outs[i]
        exit $rcs[i]
      fi
    done ;;
  (*) print -u2 -r -- "tart substitute: unknown subcommand $cmd"; exit 2 ;;
esac
exit 0
'''

REALRUN = r'''#!/bin/zsh -f
print -r -- ${(qq)@} >> %(log)s
n=0
until [[ -e %(marks)s/stopped-$1 ]]; do (( n++ < 2400 )) || exit 1; /bin/sleep 0.05; done
exit 0
'''

DATE_STUB = r'''#!/bin/zsh -f
if [[ $* == +%%Y%%m%%d ]]; then print -r -- %(date)s; else exec /bin/date "$@"; fi
'''

SLEEP_STUB = '#!/bin/zsh -f\nprint -r -- ${(qq)@} >> %(log)s\n'

DF_STUB = r'''#!/bin/zsh -f
print -r -- 'Filesystem 1024-blocks Used Available Capacity Mounted on'
print -r -- '/dev/disk3s5 2000000000 100000000 1900000000 6% /System/Volumes/Data'
'''


GW = '192.0.2.1'
TARGETS = ['192.0.2.10:80', '198.51.100.20:22', '203.0.113.30:22']


def conf_text(image, targets=TARGETS):
    """a linux-image.conf: a comment, then its two lines"""
    return '# the host values of the Linux images\nimage = %s\nwall-targets = %s\n' % (image, ' '.join(targets))


def smoke_rules(targets=TARGETS):
    """RULES for a smoke that passes: the wall drops the gateway and TARGETS, github.com:22 connects"""
    r = [
        ('id -un', 0, 'admin'),
        ('cat /etc/machine-id', 0, '0123456789abcdef0123456789abcdef'),
        ('grep -v ^# /etc/resolv.conf', 0, 'nameserver 1.1.1.1\nnameserver 8.8.8.8'),
        ('hostname', 0, 'admin-vm'),
        ('sh -c ip route*', 0, GW),
        ('cat /tmp/runner.log', 0, 'An error occurred: the JIT config is not valid'),
        ('cat /tmp/runner-ctl.log', 0, 'Not configured. Run config.(sh/cmd) to configure the runner.'),
        ('sudo -n -u nobody docker info', 1, ''),
        ('sudo -n -u runner docker compose version --short', 0, '2.40.0'),
        ('sh -c command -v docker', 1, ''),
        ('*/dev/tcp/github.com/22', 0, ''),
    ]
    return r + [('*/dev/tcp/' + t.replace(':', '/'), 124, '') for t in list(targets) + [GW + ':22']]


def zglob(p):
    """a zsh pattern from P where only * is special"""
    return ''.join('*' if c == '*' else ('\\' + c if not c.isalnum() and c not in ' -_/.,=:' else c) for c in p)


class Sandbox:
    def __init__(self, test, rules=()):
        self.test = test
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='linux-image-'))
        test.addCleanup(shutil.rmtree, self.root, True)
        for d in ('home', 'tmp', 'stubs', 'logs', 'vms', 'marks', 'logdir', 'tools'):
            os.makedirs(self.path(d))
        self.write(self.path('stubs', 'date'), DATE_STUB % {'date': DATE}, 0o755)
        self.write(self.path('stubs', 'sleep'), SLEEP_STUB % {'log': shlex.quote(self.path('logs', 'sleep.log'))}, 0o755)
        self.write(self.path('stubs', 'df'), DF_STUB, 0o755)
        q = {'log': shlex.quote(self.path('logs', 'tart.log')), 'vms': shlex.quote(self.path('vms')),
             'rules': shlex.quote(self.path('rules.zsh')), 'marks': shlex.quote(self.path('marks'))}
        self.write(self.path('tart'), TART % q, 0o755)
        self.write(self.path('real-run'), REALRUN % {'log': shlex.quote(self.path('logs', 'real-run.log')),
                                                     'marks': shlex.quote(self.path('marks'))}, 0o755)
        self.conf = self.path('linux-image.conf')
        self.set_rules(rules)

    def write_conf(self, text):
        return self.write(self.conf, text)

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def write(self, path, text, mode=0o644):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)
        os.chmod(path, mode)
        return path

    def set_rules(self, rules):
        """RULES: (glob, rc, stdout) for `tart exec`, first match wins"""
        lines = ['pats=(' + ' '.join(shlex.quote(zglob(g)) for g, _, _ in rules) + ')',
                 'rcs=(' + ' '.join(str(rc) for _, rc, _ in rules) + ')',
                 'outs=(' + ' '.join(shlex.quote(o) for _, _, o in rules) + ')']
        self.write(self.path('rules.zsh'), '\n'.join(lines) + '\n')

    def add_vm(self, name):
        self.write(self.path('vms', name), '')

    def vms(self):
        return sorted(os.listdir(self.path('vms')))

    def rewrites(self):
        return [
            ('REAL=/Users/ci/Applications/tart.app/Contents/MacOS/tart', 'REAL=' + self.path('tart')),
            ('REALRUN=/Users/ci/bin/real-run', 'REALRUN=' + self.path('real-run')),
            ('LOCK=/tmp/runner.lock', 'LOCK=' + self.path('runner.lock')),
            ('FLAG=/Users/ci/.config/runner/enabled', 'FLAG=' + self.path('enabled')),
            ('LOGDIR=/Users/ci/Library/Logs/mac-runner', 'LOGDIR=' + self.path('logdir')),
            ('HOME=/Users/ci ', 'HOME=' + self.path('home') + ' '),
        ]

    def copy_script(self, src, name, extra=(), base=True):
        """Copy SRC (a path) to tools/NAME with the host paths rewritten (and EXTRA (old, new) pairs); BASE False: only
        EXTRA. The conf's path is rewritten to the sandbox's conf wherever it is named."""
        with open(src) as f:
            text = f.read()
        for old, new in (self.rewrites() if base else []) + list(extra):
            if old not in text:
                raise AssertionError('%s: the rewrite target is not in the script: %r' % (src, old))
            text = text.replace(old, new)
        text = text.replace('LINUXCONF=' + CONF, 'LINUXCONF=' + self.conf)
        for n, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith('#'):
                continue
            for h in HOST_PATHS:
                if h in line:
                    raise AssertionError('%s line %d: the copy still names %s: %r' % (src, n, h, line))
        return self.write(self.path('tools', name), text, 0o755)

    def install(self, src, name, extra=()):
        """copy_script SRC to tools/NAME and, when the repo has it, bin/linux-image-lib beside it -> the copy's path"""
        if os.path.exists(LIB):
            self.copy_script(LIB, 'linux-image-lib', base=False)
        return self.copy_script(src, name, extra)

    def env(self):
        return {'HOME': self.path('home'), 'TMPDIR': self.path('tmp') + '/', 'PATH': self.path('stubs') + ':' + SYSTEM_PATH,
                'LC_ALL': 'C'}

    def run(self, argv, timeout=180):
        return subprocess.run(argv, env=self.env(), cwd=self.path('tmp'), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def calls(self, name='tart'):
        """the argv of each call of the substitute NAME, in order"""
        p = self.path('logs', name + '.log')
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return [shlex.split(l) for l in f.read().splitlines()]

    def execs(self):
        """the CMD of each `tart exec VM CMD...`, its words joined by one space"""
        return [' '.join(c[2:]) for c in self.calls() if c[:1] == ['exec']]

    def transcript(self):
        """every tart and real-run call, in tart's order, with the sandbox's own path made generic"""
        return [' '.join(c).replace(self.root, '<ROOT>') for c in self.calls()]


def constant(path, name):
    with open(path) as f:
        m = re.search(r'^%s=(\S+)' % name, f.read(), re.M)
    return m.group(1) if m else None
