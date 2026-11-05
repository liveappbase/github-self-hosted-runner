"""install, run whole in a harness (S3b-5 A1): a copy of install, and of the release tree it runs, with every host path
rewritten into the test's own folder, run under an EXEC ALLOW-LIST and a WRITE WALL (macOS sandbox-exec).

The rig (Inst):
- install's copy: the prefixes /Users/ci, /tmp/runner.lock and /usr/local/libexec/liveapp-ci rewritten into the
  sandbox (each rewrite must match; the copy may then hold no host path), and its tool constants (ID, SYSCTL, LOCKF,
  LAUNCHCTL) pointed at stubs.
- the release tree it runs, as the install line unpacks it (BASE/.unpack.X/VERSION/): runner-updater (for `protect`
  and `status`), its lib and window file, runner-journal, validate-class and runner-lock-free are the REAL scripts,
  rewritten the same way (so the one-copy STATEDIR is made by the real `protect`); the core, the plists, the example
  config, 02-wall.sh and the manifest are copied as data; every other tool of bin/ is a stub that must never run
  (logs/never.log).
- stateful stubs: launchctl (print, bootout and bootstrap per label, in launchd/: `gui` is the GUI session, loaded/LABEL
  a loaded agent; each bootstrap writes what BIN/runner-updater pointed at then), id (`-un`: ci), sysctl (32 GB, 10
  CPUs), lockf (logs, then the real lockf on the sandbox's lock), fetch.sh (puts a runscaler in place), wall-files-check
  (FILES green), the shim (its check passes) and tart (an empty list).
- THE WALL: no program may start but the system tools install and the scripts it runs need (by path) and the sandbox's
  own files; no file may be written outside the sandbox. So a missed rewrite of /bin/launchctl is DENIED (zsh prints
  "operation not permitted: /bin/launchctl"), never run: the control cell shows it, by a read-only `print` of a label
  that cannot exist.
"""
import hashlib
import os
import plistlib
import pwd
import re
import shutil
import subprocess
import unittest

from tests.studio.support import REPO, Sandbox
from tests.studio.test_runner_updater import read_text, the_jq

UID = os.getuid()
ME = pwd.getpwuid(UID).pw_name
LABEL = 'sh.liveapp.mac-runner'
TOOLS_RE = re.compile(r'^TOOLS=\(([^)]*)\)$', re.M)

# what install, and the scripts of the release it runs, may start (by path); the sandbox's own files are allowed too
RUNS = ('/bin/zsh', '/usr/bin/shasum', '/usr/bin/perl', '/usr/bin/grep', '/usr/bin/awk', '/usr/bin/sed', '/bin/mv',
        '/bin/ln', '/usr/bin/readlink', '/bin/rm', '/bin/mkdir', '/bin/chmod', '/bin/cp', '/bin/rmdir', '/usr/bin/cmp',
        '/bin/sleep', '/usr/bin/sw_vers', '/usr/bin/env', '/usr/bin/lockf', '/usr/bin/id', '/usr/bin/stat',
        '/usr/sbin/lsof', '/usr/bin/true', '/bin/cat', '/bin/date', '/usr/bin/mktemp', '/bin/dd', '/usr/bin/head',
        '/usr/bin/tail', '/usr/bin/plutil', '/bin/ls')
DENIED = 'operation not permitted: %s'

LAUNCHCTL = r'''D=%(d)s B=%(bin)s
case $1 in
  (print)
    t=${2#gui/}
    if [[ $t == */* ]]; then [[ -e $D/loaded/${t#*/} ]] && { print -r -- "${t#*/} = { state = running }"; exit 0 }; exit 113; fi
    [[ -e $D/gui ]] && exit 0
    exit 113 ;;
  (bootout)
    l=${2##*/}
    [[ -e $D/loaded/$l ]] || exit 3
    /bin/rm -f -- $D/loaded/$l ;;
  (bootstrap)
    l=$(/usr/bin/plutil -extract Label raw -o - $3) || exit 5
    [[ ! -e $D/loaded/$l ]] || exit 5
    /bin/mkdir -p $D/loaded && /bin/cp $3 $D/loaded/$l || exit 5
    print -r -- "$l $(/usr/bin/readlink $B/runner-updater 2>/dev/null || print -r -- none)" >> $D/bootstrap.links ;;
  (*) exit 2 ;;
esac
'''
FETCH = '''R=%(runner)s
[[ $1 == --replace && -f $2 ]] || exit 2
[[ -f %(scn)s/fetch-fail ]] && { print -r -- "fetch.sh: STOP the download failed"; exit 1 }
[[ -f $R ]] || { print -r -- runscaler > $R; /bin/chmod 755 $R }
'''


def lit(name):
    m = re.search(r'^%s=([0-9a-f]{64})$' % name, read_text(os.path.join(REPO, 'setup', '02-wall.sh')), re.M)
    return m.group(1)


def tree(path):
    """every file, folder and link below PATH: its kind, mode and (a file) its sha256, (a link) its target"""
    out = {}
    for top, dirs, files in os.walk(path):
        for n in dirs + files:
            p = os.path.join(top, n)
            st = os.lstat(p)
            if os.path.islink(p):
                out[os.path.relpath(p, path)] = ('link', os.readlink(p))
            elif os.path.isdir(p):
                out[os.path.relpath(p, path)] = ('dir', st.st_mode & 0o7777)
            else:
                with open(p, 'rb') as f:
                    out[os.path.relpath(p, path)] = ('file', st.st_mode & 0o7777, hashlib.sha256(f.read()).hexdigest())
    return out


class Inst:
    """the host as install sees it, in a sandbox; `unpack()` puts a release where the install line would"""

    def __init__(self, test):
        self.test = test
        sb = self.sb = Sandbox(test)
        self.version = read_text(os.path.join(REPO, 'VERSION')).strip()
        self.ci = sb.mkdir('ci')                                     # /Users/ci
        self.base = os.path.join(self.ci, 'mac-runner')
        self.bin = os.path.join(self.ci, 'bin')
        self.confdir = os.path.join(self.ci, '.config', 'runner')
        self.config = os.path.join(self.confdir, 'config.toml')
        self.flag = os.path.join(self.confdir, 'enabled')
        self.logdir = os.path.join(self.ci, 'Library', 'Logs', 'mac-runner')
        self.agents = os.path.join(self.ci, 'Library', 'LaunchAgents')
        self.statedir = os.path.join(self.ci, '.local', 'state', 'runner-updater')
        self.runner = os.path.join(self.bin, 'runner')
        self.lock = sb.path('runner.lock')
        self.libexec = sb.mkdir('libexec')                           # /usr/local/libexec/liveapp-ci
        self.launchd = sb.mkdir('launchd')
        self.scn = sb.mkdir('scn')
        self.tools = sb.mkdir('tools')
        sb.write(os.path.join(self.launchd, 'gui'), '')              # ci's GUI session
        sb.stub('id', 'case $1 in (-un) print -r -- ci ;; (-u) print -r -- %d ;; (*) exit 2 ;; esac' % UID,
                folder=self.tools)
        sb.stub('sysctl', 'case $2 in (hw.memsize) print -r -- 34359738368 ;; (hw.ncpu) print -r -- 10 ;; (*) exit 1 ;; esac',
                folder=self.tools)
        sb.stub('lockf', 'exec /usr/bin/lockf "$@"', folder=self.tools)
        sb.stub('launchctl', LAUNCHCTL % {'d': self.launchd, 'bin': self.bin}, folder=self.tools)
        # what the root line and the downloads left: the shim (its check passes), the record of the root files, tart
        sb.stub('tart', 'exit 0', folder=self.libexec, log=sb.path('logs', 'shim.log'))
        sb.write(os.path.join(self.libexec, 'install.digests'),
                 'shim %s\nshim.conf %s\nsoftnet %s\nsoftnet-tarball %s\n' % (
                     lit('SHIM_SHA'), lit('CONF_SHA'), lit('SOFTNET_SHA'), lit('SOFTNET_TARBALL_SHA')))
        sb.stub('tart', '[[ $1 == list ]] && /bin/cat %s/tart-list 2>/dev/null; exit 0' % self.scn,
                folder=os.path.join(self.ci, 'Applications', 'tart.app', 'Contents', 'MacOS'))
        self.prefix = [('/Users/ci', self.ci), ('/tmp/runner.lock', self.lock),
                       ('/usr/local/libexec/liveapp-ci', self.libexec)]

    # the release, as the install line unpacks it
    def rewrite(self, rel, extra=(), dest=None):
        """REPO/rel with the host prefixes (those it holds) and EXTRA rewritten, to DEST"""
        text = read_text(os.path.join(REPO, rel))
        rw = [(a, b) for a, b in self.prefix if a in text] + list(extra)
        return self.sb.copy_script(rel, rw, dest=dest)

    def unpack(self, name='.unpack.abc123'):
        """the release tree at BASE/NAME/VERSION -> its install"""
        rel = os.path.join(self.base, name, self.version)
        os.makedirs(os.path.join(rel, 'bin'))
        self.rewrite('install', [('ID=/usr/bin/id', 'ID=' + os.path.join(self.tools, 'id')),
                                 ('SYSCTL=/usr/sbin/sysctl', 'SYSCTL=' + os.path.join(self.tools, 'sysctl')),
                                 ('LOCKF=/usr/bin/lockf', 'LOCKF=' + os.path.join(self.tools, 'lockf')),
                                 ('LAUNCHCTL=/bin/launchctl', 'LAUNCHCTL=' + os.path.join(self.tools, 'launchctl'))],
                     dest=os.path.join(rel, 'install'))
        shutil.copy(os.path.join(REPO, 'VERSION'), rel)
        for d in ('core', 'config'):
            shutil.copytree(os.path.join(REPO, d), os.path.join(rel, d))
        os.makedirs(os.path.join(rel, 'setup'))
        for f in ('02-wall.sh', 'downloads.manifest'):   # data: install reads them, never runs them
            shutil.copy(os.path.join(REPO, 'setup', f), os.path.join(rel, 'setup', f))
        relbin = os.path.join(rel, 'bin')
        real = {'runner-updater': [('JQ=/usr/bin/jq', 'JQ=' + the_jq())],
                'runner-updater-lib': [], 'runner-updater-window': [], 'runner-journal': [], 'validate-class': [],
                'runner-lock-free': [('CI_USER=ci', 'CI_USER=' + ME)]}
        for n, extra in real.items():
            self.rewrite('bin/' + n, extra, dest=os.path.join(relbin, n))
        never = self.sb.path('logs', 'never.log')
        for n in os.listdir(os.path.join(REPO, 'bin')):
            if n not in real:
                self.sb.stub(n, 'print -r -- "${0:t} must never run"; exit 99', folder=relbin, log=never)
        self.sb.stub('fetch.sh', FETCH % {'runner': self.runner, 'scn': self.scn}, folder=relbin)
        self.sb.stub('wall-files-check', 'print -r -- "FILES green"', folder=relbin)
        return os.path.join(rel, 'install')

    def profile(self):
        allowed = set(RUNS) | {the_jq()}
        allowed |= {os.path.realpath(p) for p in allowed}
        return ('(version 1)(allow default)(deny process-exec*)(allow process-exec*%s (subpath "%s"))'
                '(deny file-write*)(allow file-write* (literal "/dev/null") (literal "/dev/dtracehelper") (subpath "%s"))'
                % (''.join(' (literal "%s")' % p for p in sorted(allowed)), self.sb.root, self.sb.root))

    def walled(self, argv, extra_env=None):
        return self.sb.run(['/usr/bin/sandbox-exec', '-p', self.profile()] + argv, extra_env=extra_env)

    def install(self, path=None, ok=True):
        res = self.walled(['/bin/zsh', '-f', path or self.unpack()])
        if ok:
            self.test.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.test.assertNotIn('operation not permitted', res.stdout + res.stderr)
        self.test.assertFalse(os.path.exists(self.sb.path('logs', 'never.log')), read_text(self.sb.path('logs', 'never.log'))
                              if os.path.exists(self.sb.path('logs', 'never.log')) else '')
        return res

    # what it left
    def loaded(self):
        d = os.path.join(self.launchd, 'loaded')
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def launchctl(self, verb=None):
        calls = self.sb.calls('launchctl')
        return [c for c in calls if verb is None or c[:1] == [verb]]

    def tools_list(self):
        return TOOLS_RE.search(read_text(os.path.join(REPO, 'install'))).group(1).split()


class TestTheWall(unittest.TestCase):
    """The harness's own guard: under the rig's profile a program by an absolute path it does not list is DENIED, and a
    write outside the sandbox too. The launchctl probe is read-only (`print` of a label that cannot exist), so a wall
    that is missing loads nothing. Controls: the sandbox's own stub runs, and a write inside the sandbox works."""

    def test_control_launchctl_by_its_absolute_path_is_denied(self):
        h = Inst(self)
        res = h.walled(['/bin/zsh', '-f', '-c', '/bin/launchctl print gui/%d/sh.liveapp.no-such-label-a1-wall' % UID])
        self.assertNotEqual(res.returncode, 0)
        self.assertIn(DENIED % '/bin/launchctl', res.stderr)
        # the control: the rig's launchctl (in the sandbox) runs under the same profile, and answers
        res = h.walled(['/bin/zsh', '-f', '-c', '%s print gui/%d' % (os.path.join(h.tools, 'launchctl'), UID)])
        self.assertEqual((res.returncode, res.stderr), (0, ''))
        self.assertEqual(h.launchctl(), [['print', 'gui/%d' % UID]])

    def test_control_a_write_outside_the_sandbox_is_denied(self):
        h = Inst(self)
        outside = os.path.join(os.path.dirname(h.sb.root), os.path.basename(h.sb.root) + '-outside')
        self.addCleanup(lambda: os.path.exists(outside) and os.remove(outside))
        res = h.walled(['/bin/zsh', '-f', '-c', ': > %s' % outside])
        self.assertNotEqual(res.returncode, 0)
        self.assertFalse(os.path.exists(outside))
        res = h.walled(['/bin/zsh', '-f', '-c', ': > %s' % h.sb.path('inside')])   # the control
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(os.path.exists(h.sb.path('inside')))


class TestFreshInstall(unittest.TestCase):
    """A fresh host: install runs to its end under the wall, by the rig's stubs only."""

    def test_a_fresh_install(self):
        h = Inst(self)
        res = h.install()
        r = os.path.join(h.base, h.version)
        self.assertEqual(os.readlink(os.path.join(h.base, 'current')), h.version)
        self.assertTrue(os.path.isfile(os.path.join(r, 'VERSION')))
        self.assertFalse([n for n in os.listdir(h.base) if n.startswith('.unpack.')])
        for t in h.tools_list():
            self.assertEqual(os.readlink(os.path.join(h.bin, t)), os.path.join(h.base, 'current', 'bin', t), t)
        self.assertIn(LABEL, h.loaded())
        self.assertTrue(os.path.isfile(h.config))
        self.assertIn('install: NEXT ', res.stdout)
        self.assertIn('install: ROOT LINE   not needed', res.stdout)
        # the lock: the runner lock by the rig's lockf, on the sandbox's lock file
        self.assertEqual(h.sb.calls('lockf')[0][:4], ['-k', '-t', '0', h.lock])

    def test_a_second_run_reloads_nothing_and_changes_nothing(self):
        h = Inst(self)
        h.install()
        before, n = tree(h.ci), len(h.launchctl())
        res = h.install(os.path.join(h.base, h.version, 'install'))
        self.assertIn('install: release %s is already in place' % h.version, res.stdout)
        self.assertEqual([c for c in h.launchctl()[n:] if c[0] in ('bootout', 'bootstrap')], [])
        after = tree(h.ci)
        self.assertEqual({k: v for k, v in after.items() if k != 'mac-runner/runscaler.sha256'},
                         {k: v for k, v in before.items() if k != 'mac-runner/runscaler.sha256'})



def const(name, rel='install'):
    """NAME's value on its NAME=VALUE line (column 0) of REPO/rel"""
    m = re.findall(r'^%s=(\S+)' % name, read_text(os.path.join(REPO, rel)), re.M)
    assert len(m) == 1, (name, m)
    return m[0]


class TestUpdaterPlist(unittest.TestCase):
    """config/sh.liveapp.runner-updater.plist, the updater's timer, pinned against install: it runs the link install
    makes (BIN/runner-updater) as `pass --log FILE`, FILE and both output paths in the folder install creates (LOGDIR);
    every 600 s, not at load, no KeepAlive, no AbandonProcessGroup, ProcessType Interactive."""

    def plist(self):
        with open(os.path.join(REPO, 'config', 'sh.liveapp.runner-updater.plist'), 'rb') as f:
            return plistlib.load(f)

    def test_it_runs_the_link_install_makes_as_a_logged_pass(self):
        p = self.plist()
        self.assertEqual(p['Label'], 'sh.liveapp.runner-updater')
        args = p['ProgramArguments']
        self.assertEqual(args[0], const('BIN') + '/runner-updater')
        self.assertEqual(args[1:3], ['pass', '--log'])
        self.assertEqual(len(args), 4)
        self.assertEqual(os.path.dirname(args[3]), const('LOGDIR'))
        self.assertEqual(os.path.basename(args[3]), 'runner-updater.log')

    def test_its_output_goes_to_logdir(self):
        p = self.plist()
        self.assertEqual(p['StandardOutPath'], const('LOGDIR') + '/runner-updater.err')
        self.assertEqual(p['StandardErrorPath'], const('LOGDIR') + '/runner-updater.err')

    def test_its_schedule_and_process_keys(self):
        p = self.plist()
        self.assertEqual(p['StartInterval'], 600)
        self.assertIs(p['RunAtLoad'], False)
        self.assertEqual(p['ProcessType'], 'Interactive')
        for k in ('KeepAlive', 'AbandonProcessGroup', 'ExitTimeOut', 'EnvironmentVariables'):
            self.assertNotIn(k, p)
        self.assertEqual(sorted(p), ['Label', 'ProcessType', 'ProgramArguments', 'RunAtLoad', 'StandardErrorPath',
                                     'StandardOutPath', 'StartInterval'])

    def test_plutil_lints_it(self):
        res = subprocess.run(['/usr/bin/plutil', '-lint', os.path.join(REPO, 'config', 'sh.liveapp.runner-updater.plist')],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


if __name__ == '__main__':
    unittest.main()
