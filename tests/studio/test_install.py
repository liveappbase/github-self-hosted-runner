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
import json
import os
import plistlib
import pwd
import re
import shutil
import stat
import subprocess
import unittest

from tests.studio.support import REPO, Sandbox
from tests.studio.test_runner_updater import read_text, the_jq
from tests.studio.test_runner_updater_state import state

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

    def unpack(self, name='.unpack.abc123', updater=()):
        """the release tree at BASE/NAME/VERSION (UPDATER: more rewrites of its runner-updater) -> its install"""
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
        real = {'runner-updater': [('JQ=/usr/bin/jq', 'JQ=' + the_jq())] + list(updater),
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

    def updater(self, *args):
        """the INSTALLED runner-updater (the link install made), as ci would run it"""
        return self.sb.run(['/bin/zsh', '-f', os.path.join(self.bin, 'runner-updater')] + list(args))

    def statedir_with_list(self, names=''):
        """STATEDIR (0700) with its protected list (0600), as an earlier install or report made them"""
        os.makedirs(self.statedir, mode=0o700)
        self.sb.write(os.path.join(self.statedir, 'protected'), names, 0o600)

    def hold_updater_lock(self):
        """a process that holds the updater lock (zsystem flock, as a pass or a window) until the test ends"""
        ready = self.sb.path('locked')
        lockfile = os.path.join(self.statedir, 'lock')
        self.sb.start(['/bin/zsh', '-f', '-c', 'zmodload zsh/system; : >> %s; zsystem flock -f fd %s || exit 1; '
                       ': > %s; /bin/sleep 600' % (lockfile, lockfile, ready)], name='updater-lock-holder')
        self.sb.wait_for(lambda: os.path.exists(ready), 'the updater lock to be held')

    def try_updater_lock(self):
        """zsystem flock -t 0.01 on the updater lock now: 0 free, 2 held"""
        return subprocess.run(['/bin/zsh', '-f', '-c', 'zmodload zsh/system; zsystem flock -t 0.01 -f fd %s 2>/dev/null; '
                               'print -r -- $?' % os.path.join(self.statedir, 'lock')],
                              capture_output=True, text=True).stdout.strip()

    def unchanged(self, before, unpacked):
        """nothing changed: the host tree is BEFORE, the release is still in its unpack folder, no launchctl call,
        no download"""
        after = tree(self.ci)
        lock = os.path.relpath(os.path.join(self.statedir, 'lock'), self.ci)
        if lock not in before and lock in after:      # the lock file, made to take the lock (as runner-updater makes it)
            self.test.assertEqual(after.pop(lock), ('file', 0o600, hashlib.sha256(b'').hexdigest()))
        self.test.assertEqual(after, before)
        self.test.assertTrue(os.path.isfile(unpacked))
        self.test.assertEqual(self.launchctl(), [])
        self.test.assertEqual(self.sb.calls('fetch.sh'), [])

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



UPDATER = 'sh.liveapp.runner-updater'
SECTION = 'README "An unfinished window the updater cannot end"'
RECORD_STOP = ('install: STOP an updater window is unfinished: run %s pass (its RECOVER ends the window), then run '
               'install again. If that pass says RECOVER cannot read or act on the window record: ' + SECTION + '\n')
OFF_NEXT = ('install: NEXT (optional): the updater is OFF; README "The updater" says how to write its families file and '
            'turn it on\n')


class TestTheUpdaterAgent(unittest.TestCase):
    """install links runner-updater (the link the plist and the watchdog run) and loads the second agent, by the ONE
    function that loads the first: when its plist differs or it is not loaded, the old plist kept as
    BASE/updater-plist.prev; the link exists before its bootstrap."""

    def test_install_links_runner_updater_and_names_the_plist_s_label(self):
        h = Inst(self)
        self.assertIn('runner-updater', h.tools_list())
        self.assertEqual(const('UPDATER_LABEL'), UPDATER)

    def test_a_fresh_install_loads_both_agents_the_link_first(self):
        h = Inst(self)
        res = h.install()
        self.assertEqual(h.loaded(), [LABEL, UPDATER])
        self.assertIn('install: LaunchAgent %s loaded from %s\n' % (UPDATER, os.path.join(h.agents, UPDATER + '.plist')),
                      res.stdout)
        links = dict(l.split(' ', 1) for l in read_text(os.path.join(h.launchd, 'bootstrap.links')).splitlines())
        self.assertEqual(links[UPDATER], os.path.join(h.base, 'current', 'bin', 'runner-updater'))
        with open(os.path.join(h.agents, UPDATER + '.plist'), 'rb') as f, \
                open(os.path.join(REPO, 'config', UPDATER + '.plist'), 'rb') as g:
            self.assertEqual(f.read(), g.read())
        self.assertFalse(os.path.exists(os.path.join(h.base, 'updater-plist.prev')))

    def test_a_changed_updater_plist_is_reloaded_and_the_old_one_kept(self):
        h = Inst(self)
        h.install()
        dst = os.path.join(h.agents, UPDATER + '.plist')
        old = read_text(dst).replace('<integer>600</integer>', '<integer>900</integer>')   # an older release's plist
        h.sb.write(dst, old)
        n = len(h.launchctl())
        res = h.install(os.path.join(h.base, h.version, 'install'))
        self.assertEqual([c[:2] for c in h.launchctl()[n:] if c[0] in ('bootout', 'bootstrap')],
                         [['bootout', 'gui/%d/%s' % (UID, UPDATER)], ['bootstrap', 'gui/%d' % UID]])
        self.assertEqual(read_text(os.path.join(h.base, 'updater-plist.prev')), old)
        self.assertEqual(read_text(dst), read_text(os.path.join(REPO, 'config', UPDATER + '.plist')))
        self.assertIn('install: kept the old plist as %s\n' % os.path.join(h.base, 'updater-plist.prev'), res.stdout)
        self.assertEqual(h.loaded(), [LABEL, UPDATER])

    def test_an_updater_agent_that_is_not_loaded_is_loaded(self):
        h = Inst(self)
        h.install()
        os.remove(os.path.join(h.launchd, 'loaded', UPDATER))       # booted out by hand
        n = len(h.launchctl())
        h.install(os.path.join(h.base, h.version, 'install'))
        self.assertEqual([c[:2] for c in h.launchctl()[n:] if c[0] in ('bootout', 'bootstrap')],
                         [['bootstrap', 'gui/%d' % UID]])
        self.assertEqual(h.loaded(), [LABEL, UPDATER])


class TestTheStateFolder(unittest.TestCase):
    """A host with no STATEDIR gets it, with its empty protected list, from the release's own `runner-updater protect`
    (run for real: the one-step folder), before install tries the updater lock. Its failure is a STOP; an existing folder
    and list are left byte-equal."""

    AS_BEFORE = 'liveapp-mac-golden-20260815\nliveapp-mac-golden-20260901\n'   # golden-prune with no updater

    def prune(self, h):
        script = h.sb.copy_script('bin/golden-prune', [('STATEDIR=/Users/ci/.local/state/runner-updater',
                                                        'STATEDIR=' + h.statedir)], dest=h.sb.path('prune', 'golden-prune'))
        return h.sb.run(['/bin/zsh', '-f', script] + TestStateDirNames)

    def test_a_fresh_host_gets_statedir_and_an_empty_list_by_the_real_protect(self):
        h = Inst(self)
        res = h.install()
        protected = os.path.join(h.statedir, 'protected')
        self.assertIn('install: runner-updater: created %s, with an empty protected list %s (it protects nothing)\n'
                      % (h.statedir, protected), res.stdout)
        self.assertEqual(os.stat(h.statedir).st_mode & 0o777, 0o700)
        self.assertEqual((os.path.getsize(protected), os.stat(protected).st_mode & 0o777), (0, 0o600))
        self.assertEqual(sorted(os.listdir(h.statedir)), ['lock', 'protected'])   # no state.json
        p = self.prune(h)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, self.AS_BEFORE, ''))
        # `on` passes the list check (no "protected list" refusal) with a families file
        h.sb.write(os.path.join(h.ci, '.config', 'runner-updater', 'families'), 'mac-golden tart mac-ci-REPO\n')
        on = h.updater('on')
        self.assertEqual(on.returncode, 0, on.stdout + on.stderr)
        self.assertEqual(on.stdout, 'runner-updater: on: the updater is ON\n')

    def test_protect_failing_is_a_stop_and_nothing_else_changes(self):
        h = Inst(self)
        state = os.path.join(h.ci, '.local', 'state')
        os.makedirs(state)
        os.chmod(state, 0o500)                                 # no new folder can be made beside STATEDIR
        self.addCleanup(os.chmod, state, 0o700)
        unpacked = h.unpack()
        before = tree(h.ci)
        res = h.install(unpacked, ok=False)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertEqual(res.stdout, "install: STOP the updater's state folder: runner-updater: REFUSE cannot create a "
                                     "new folder beside %s\n" % h.statedir)
        h.unchanged(before, unpacked)

    def test_control_an_existing_folder_and_list_stay_byte_equal(self):
        h = Inst(self)
        h.statedir_with_list('liveapp-mac-golden-20260901\n')
        h.sb.write(os.path.join(h.statedir, 'state.json'), json.dumps(state()) + '\n', 0o600)
        before = tree(h.statedir)
        res = h.install()
        self.assertNotIn('protected list', res.stdout)
        after = tree(h.statedir)
        self.assertEqual(after.pop('lock'), ('file', 0o600, hashlib.sha256(b'').hexdigest()))   # the lock file, made
        self.assertEqual(after, before)

    KILL_BLOCK = 'if [[ ! -e $STATEDIR && ! -L $STATEDIR ]]; then\n'
    KILL_AFTER = '[[ -d $STATEDIR && ! -L $STATEDIR ]] || refuse "$STATEDIR is not a folder"\n'

    def test_a_kill_of_protect_at_each_step_never_leaves_statedir_without_its_list(self):
        seen = {'no STATEDIR': 0, 'STATEDIR with its list': 0}
        for n in range(1, 60):
            h = Inst(self)
            trap = "ru_k=0; trap '(( ! ZSH_SUBSHELL && ++ru_k == %d )) && kill -9 $$' DEBUG\n" % n
            unpacked = h.unpack(updater=[(self.KILL_BLOCK, trap + self.KILL_BLOCK),
                                         (self.KILL_AFTER, 'trap - DEBUG\n' + self.KILL_AFTER)])
            res = h.install(unpacked, ok=False)
            if res.returncode == 0:      # the block has fewer than n commands: no kill
                break
            with self.subTest(killed_before_command=n):
                self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
                self.assertTrue(res.stdout.startswith("install: STOP the updater's state folder: "), res.stdout)
                self.assertEqual(h.launchctl(), [])
                if os.path.lexists(h.statedir):
                    seen['STATEDIR with its list'] += 1
                    p = os.path.join(h.statedir, 'protected')
                    self.assertTrue(os.path.isfile(p) and not os.path.islink(p), os.listdir(h.statedir))
                    self.assertEqual(os.path.getsize(p), 0)
                else:
                    seen['no STATEDIR'] += 1
                p = self.prune(h)
                self.assertEqual((p.returncode, p.stdout), (0, self.AS_BEFORE), p.stderr)
        else:
            self.fail('every run was killed: the trap never ran out of commands')
        self.assertGreater(seen['no STATEDIR'], 0, seen)
        self.assertGreater(seen['STATEDIR with its list'], 0, seen)
        # the last host, after a run that was not killed: STATEDIR with its list, and install went on
        self.assertEqual(sorted(os.listdir(h.statedir)), ['lock', 'protected'])
        self.assertEqual(h.loaded(), [LABEL, UPDATER])


TestStateDirNames = ['liveapp-mac-golden-20261001', 'liveapp-mac-golden-20261001', 'liveapp-mac-golden-20260915',
                     'liveapp-mac-golden-20260901', 'liveapp-mac-golden-20260815']


class TestTheUpdaterLock(unittest.TestCase):
    """install's OUTER process TRIES the updater lock (zsystem flock -t 0.01) and holds it to its end; the `--locked`
    child never tries it. Held: STOP, nothing changed. The runner lock held alone: the existing STOP, and the updater
    lock is free after the exit."""

    def test_the_updater_lock_held_is_a_stop_and_nothing_changes(self):
        h = Inst(self)
        h.statedir_with_list()
        h.hold_updater_lock()
        unpacked = h.unpack()
        before = tree(h.ci)
        res = h.install(unpacked, ok=False)
        self.assertEqual((res.returncode, res.stdout), (1, 'install: STOP an updater run holds its lock (a pass or a '
                                                           'window): run install again when it has ended\n'), res.stderr)
        h.unchanged(before, unpacked)

    def test_control_the_updater_lock_free_install_goes_on_and_its_child_does_not_try_it(self):
        h = Inst(self)
        h.statedir_with_list()
        h.install()                                      # the outer process holds the lock while its child runs
        self.assertEqual(h.loaded(), [LABEL, UPDATER])
        self.assertEqual(h.try_updater_lock(), '0')     # and lets it go at its end

    def test_a_lock_file_it_cannot_take_is_a_stop(self):
        h = Inst(self)
        h.statedir_with_list()
        os.mkdir(os.path.join(h.statedir, 'lock'))       # not a file: flock cannot open it
        unpacked = h.unpack()
        before = tree(h.ci)
        res = h.install(unpacked, ok=False)
        self.assertEqual(res.stdout, 'install: STOP cannot take the updater lock %s (rc 1)\n'
                         % os.path.join(h.statedir, 'lock'))
        h.unchanged(before, unpacked)

    def test_the_runner_lock_held_alone_is_the_existing_stop_and_the_updater_lock_is_free_after(self):
        h = Inst(self)
        h.statedir_with_list()
        h.sb.start(['/usr/bin/lockf', '-k', '-t', '0', h.lock, '/bin/sleep', '600'], name='runner-lock-holder')
        h.sb.wait_for(lambda: subprocess.run(['/usr/bin/lockf', '-k', '-s', '-t', '0', h.lock, '/usr/bin/true'])
                      .returncode == 75, 'the runner lock to be held')
        res = h.install(ok=False)
        self.assertEqual(res.returncode, 1)
        self.assertEqual(res.stdout, "install: STOP runner-lock-free says 'held': runscaler, wall-check, golden-build or "
                                     "golden-gate is running\n")
        self.assertEqual(h.try_updater_lock(), '0')


class TestAnOpenWindowRecord(unittest.TestCase):
    """An open window record (STATEDIR/window, -e or -L), under the updater lock and BEFORE the FLAG check: STOP, and
    nothing changes (no move-in, no download, no link, no launchctl call). The STOP names the link when it exists, else
    BASE/current/bin/runner-updater when current is a 0.2.x release, else the 0.2.x folder written down at the way back."""

    def record(self, h, shape='lines'):
        """STATEDIR/window as SHAPE: 'lines', 'symlink' (dangling), 'empty' (a power loss before its first line was
        flushed), 'folder'. -> its path"""
        h.statedir_with_list()
        w = os.path.join(h.statedir, 'window')
        if shape == 'symlink':
            os.symlink(h.sb.path('no-such-record'), w)
        elif shape == 'folder':
            os.mkdir(w, 0o700)
        else:
            h.sb.write(w, '' if shape == 'empty' else 'window 20261105000000-1\nfamily mac-golden\n', 0o600)
        return w

    def stopped(self, h, text, flag=False, hide=None):
        """install STOPs with TEXT and changes nothing. HIDE: a file made mode 000 for the install only (the tree is
        read before and after with its mode 0600; it is still 000 when install has ended)"""
        if flag:
            h.sb.write(h.flag, '')
        unpacked = h.unpack()
        before = tree(h.ci)
        if hide:
            os.chmod(hide, 0)
            self.assertFalse(os.access(hide, os.R_OK))
        res = h.install(unpacked, ok=False)
        if hide:
            self.assertEqual(stat.S_IMODE(os.lstat(hide).st_mode), 0)
            os.chmod(hide, 0o600)
        self.assertEqual((res.returncode, res.stdout), (1, text), res.stderr)
        h.unchanged(before, unpacked)

    def written_down(self, h):
        return RECORD_STOP % ('the runner-updater of the 0.2.x folder written down at the way back (%s/<VERSION>'
                              '/bin/runner-updater)' % h.base)

    # review r1 P3-1: a record of any shape is a record (install tests -e or -L, never its size, kind or mode)
    def test_an_empty_record_is_a_record(self):
        h = Inst(self)
        self.record(h, 'empty')
        self.stopped(h, self.written_down(h))

    def test_a_record_install_cannot_read_is_a_record(self):
        h = Inst(self)
        w = self.record(h)
        self.stopped(h, self.written_down(h), hide=w)

    def test_a_folder_record_is_a_record(self):
        h = Inst(self)
        self.record(h, 'folder')
        self.stopped(h, self.written_down(h))

    def test_with_the_link_the_stop_names_it(self):
        h = Inst(self)
        self.record(h)
        os.makedirs(h.bin)
        h.sb.write(h.sb.path('old', 'runner-updater'), '#!/bin/zsh -f\n', 0o755)
        os.symlink(h.sb.path('old', 'runner-updater'), os.path.join(h.bin, 'runner-updater'))
        self.stopped(h, RECORD_STOP % os.path.join(h.bin, 'runner-updater'))

    def test_with_no_link_and_a_0_2_x_current_the_stop_names_current(self):
        h = Inst(self)
        self.record(h)
        h.sb.write(os.path.join(h.base, '0.2.0', 'VERSION'), '0.2.0\n')
        h.sb.write(os.path.join(h.base, '0.2.0', 'bin', 'runner-updater'), '#!/bin/zsh -f\n', 0o755)
        os.symlink('0.2.0', os.path.join(h.base, 'current'))
        self.stopped(h, RECORD_STOP % os.path.join(h.base, 'current', 'bin', 'runner-updater'))

    def test_with_no_link_and_an_older_current_the_stop_names_the_written_down_folder(self):
        h = Inst(self)
        self.record(h, 'symlink')                    # a dangling symlink is a record too
        h.sb.write(os.path.join(h.base, '0.1.0', 'VERSION'), '0.1.0\n')
        # rc.6 had a report-only runner-updater: its `pass` runs no RECOVER
        h.sb.write(os.path.join(h.base, '0.1.0', 'bin', 'runner-updater'), '#!/bin/zsh -f\n', 0o755)
        os.symlink('0.1.0', os.path.join(h.base, 'current'))
        self.stopped(h, RECORD_STOP % ('the runner-updater of the 0.2.x folder written down at the way back (%s/<VERSION>'
                                       '/bin/runner-updater)' % h.base))

    def test_the_record_check_comes_before_the_flag_check(self):
        h = Inst(self)
        self.record(h)
        self.stopped(h, RECORD_STOP % ('the runner-updater of the 0.2.x folder written down at the way back (%s/<VERSION>'
                                       '/bin/runner-updater)' % h.base), flag=True)

    def test_control_no_record_install_goes_on(self):
        h = Inst(self)
        h.statedir_with_list()
        h.install()
        self.assertEqual(h.loaded(), [LABEL, UPDATER])

    def test_control_no_record_with_flag_is_the_flag_stop(self):
        h = Inst(self)
        h.statedir_with_list()
        h.sb.write(h.flag, '')
        res = h.install(ok=False)
        self.assertEqual(res.stdout, 'install: STOP the agent is enabled: run %s/runner-disable first (it waits for a '
                                     'running job), then run the same line again\n' % h.bin)


class TestTheUpdaterState(unittest.TestCase):
    """install never writes state.json and never runs `on` or `off`: a fresh install is OFF (D11), an upgrade keeps ON
    or OFF. Step 6 prints the first line of `runner-updater status`, and when OFF the optional NEXT."""

    def test_a_fresh_install_is_off_and_says_how_to_turn_it_on(self):
        h = Inst(self)
        res = h.install()
        self.assertFalse(os.path.exists(os.path.join(h.statedir, 'state.json')))
        self.assertIn('install: UPDATER     runner-updater: status: the updater is OFF\n', res.stdout)
        self.assertTrue(res.stdout.endswith(OFF_NEXT), res.stdout)

    def test_an_on_state_stays_on_byte_equal(self):
        h = Inst(self)
        h.statedir_with_list()
        text = json.dumps(state(on=True), indent=2) + '\n'
        h.sb.write(os.path.join(h.statedir, 'state.json'), text, 0o600)
        res = h.install()
        self.assertEqual(read_text(os.path.join(h.statedir, 'state.json')), text)
        self.assertIn('install: UPDATER     runner-updater: status: the updater is ON\n', res.stdout)
        self.assertNotIn('NEXT (optional)', res.stdout)


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
