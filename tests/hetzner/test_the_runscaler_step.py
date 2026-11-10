"""`pool-image.sh runscaler [VERSION]`, THE ONE DOOR FOR THE BINARY (runscaler 0.12 bump, Hetzner slice H2b-1; the H2
plan's M-3 with its r3 FOLD R-1 to R-6, and M-6). It changes ~/bin/runner, and only it (03's ONE DOOR: test_one_door):

- VERSION: 03's PINNED (the default, v0.12.0) or its WAYBACK (v0.9.5); any other refuses. Under the ONE RUN AT A TIME
  lock. (a) Each precondition refuses with nothing changed and names its fix: pool-image.sh's PINS, VERSION, no
  updater window journal, no open image release (a config.toml.pre-image byte-equal to config.toml is one a `back`
  closed: removed, and said so, once every other check passed, when runscaler started after config.toml's install or
  the unit is down; with config.toml installed after runscaler started it is a `back` cut before its restart: refused,
  naming `pool-image.sh back`, which finishes it; any other refuses, "accept, or back": R-4), the unit enabled,
  VERSION's download in ~/build/dl by its sha256 (03's dl_of: the pinned one Install step 4's file, the way back's its
  own name). The unit: active and started after config.toml's install (runscaler runs config.toml), or active with
  config.toml installed after its start (a pending config: only this step's own render, byte for byte, goes on: R-1),
  or enabled and down (failed, inactive, a crash loop: R-3), in both directions. The INSTALLED binary may be unknown:
  this step is the fix.
- (b) DONE ALREADY (R-5): runscaler started after config.toml's install, its process and ~/bin/runner are VERSION's,
  and config.toml has the log-file line: no stage and no restart, but READY, the running binary and the restart-cut
  scan; exit 0 only when READY. A config.toml installed after runscaler started is never DONE ALREADY (R-1).
- (c)+(d) `03-runscaler.sh stage VERSION content|bytes`: the render (config.toml's image) is compared with config.toml
  BEFORE anything is installed (THE CONFIG COMPARE, image lines as content; or byte for byte); then this release's
  runner-start, pool-ready, validate-class and unit (R-2), each PUBLISHED WHOLE (03's THE PUBLISH: into DEST.new in the
  same folder, checked against its PIN, then renamed over DEST; the live file is never written in place, and a DEST.new
  a cut left is removed by the next run), VERSION's runner into ~/bin/runner.new (both sha256s), and `runner-start
  validate --staged`: the strict control, the version line and the validate run THE STAGED BINARY; PASS only; then
  config.toml (only when it differs), THEN the rename of runner.new over ~/bin/runner. 03 real (a person's up) publishes
  the four the same way (its check: each copy is its ~/build source byte for byte).
- (e) the restart at idle (none when the unit is down); both shortcuts need THE RUNNING BINARY (R-6: the process's
  /proc/<MainPID>/exe, the cells' fake process table) to be VERSION's too; READY; the running binary VERSION's; the
  restart-cut scan; a FAIL there names the way back's two lines (or, on the way back, the way forward's). (f) NEXT: the
  way back's lines, or the way forward's.
- RESUME: a SIGKILL at each boundary of (c)-(e) and the same line again: test_step_resume.py (its own module since
  S2b-3c-2 B3, for its CI part's time). A copy cut midway (each of the four, forward and back, and in a person's up)
  leaves each live file whole.
- R-1's last sentence: an image `up` after the step was cut before its restart refuses and names the line that finishes
  that pending config: `pool-image.sh runscaler`, or `pool-image.sh back` while a release is open; no text names a
  document that is not in this repository.
- M-6: the updater's pass (this release's, ON and OFF) after the step and after the way back, a pass DURING the step's
  restart (its drain), and a pass that starts before the step and ends after it (the step runs inside it: the two
  locks do not exclude each other): what it holds, measured; its control: the same pass with a candidate whose lines
  are not config.toml's holds STOP HAND CHANGE.
Every Pool cell runs the real scripts (support.Pool; a fake clock, so no wait is real) in a throwaway container, each
subtest on a rig of its own. The pinned runscaler is Pool's substitute; the way-back one test_render.way_back's (other
bytes), with its own download. The host before the step: Install step 3 done, so its ~/bin/runner-start is the release
before's (no selector: old_wrapper). (Named for its CI part, test_t*.py: .github/workflows/release-check.yml.)
"""
import collections
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import time
import types
import unittest

from tests.hetzner.support import REPO, Pool, digest, healthz, needs_container, ref, sha256_file
from tests.hetzner.test_one_door import binary, files, unknown
from tests.hetzner.test_render import (H1HEAD, UPOLD, UPOLDV, UPNEW, UPV, WAYBACK_MARK, Before, assignment, fixture,
                                       function, older, starts, way_back)
from tests.hetzner.test_updater import MAIN, SMALL, candidate
from tests.hetzner.test_verdict import plant_r1

S03 = os.path.join(REPO, 'linux-docker', 'setup', '03-runscaler.sh')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
RR = os.path.join(REPO, 'linux-docker', 'setup', 'runner-release.sh')
README = os.path.join(REPO, 'linux-docker', 'README.md')
PINNED, WAYBACK = '0.12.0', '0.9.5'
V2, V2V = digest(12), '2.330.1'   # on_pinned's image, and the runner version its record names
STATE = os.path.join(Pool.STATE, 'state.json')
WBDL = 'runner-v%s-linux-amd64.tar.gz' % WAYBACK
URL = 'https://github.com/ysya/runscaler/releases/download/v%s/runner-linux-amd64.tar.gz'
H1_CASE = '  run|validate) args=("$mode") ;;\n'   # b2eb739's runner-start: it reads no selector (the plan's r3, Opus F2)


def readme():
    with open(README) as f:
        return f.read()


def old_wrapper(text):
    """runner-start as the release before this one installed it (Install step 3 changes ~/build, not ~/bin): the same
    script with no validate selector, `run|validate` alike, so `validate --staged` validates ~/bin/runner."""
    if H1_CASE in text:
        return text
    new = re.findall(r'(?m)^  run\) .*\n  validate\) .*\n', text)
    if len(new) != 1:
        raise AssertionError("runner-start: no single `run)` + `validate)` pair of lines: %r" % new)
    return text.replace(new[0], H1_CASE)


def wb_download(test, p):
    """The way back's download: a tarball of the way-back substitute (way_back's: 03's WAYBACK_BIN_SHA and runner-start's
    V095_SHA name it) at ~/build/dl/runner-v0.9.5-linux-amd64.tar.gz, 03's WAYBACK_TGZ_SHA its sha256 (PINS follow).
    Returns the way-back runner's sha256."""
    s = way_back(test, p, install=False)
    with tarfile.open(os.path.join(p.build, 'dl', 'runner-linux-amd64.tar.gz')) as t:
        wb = t.extractfile('runner').read() + WAYBACK_MARK
    test.assertEqual(hashlib.sha256(wb).hexdigest(), s)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        i = tarfile.TarInfo('runner')
        i.size, i.mode, i.mtime = len(wb), 0o755, 1761955200
        t.addfile(i, io.BytesIO(wb))
    tgz = buf.getvalue()
    with open(os.path.join(p.build, 'dl', WBDL), 'wb') as f:
        f.write(tgz)
    p.pin('setup/03-runscaler.sh', 'WAYBACK_TGZ_SHA', hashlib.sha256(tgz).hexdigest())
    p.rewrite_pins()
    return s


def plant_old_wrapper(p):
    rs = os.path.join(p.HOME, 'bin', 'runner-start')
    p.write(rs, old_wrapper(p.read(rs)), 0o755)


def forward(test):
    """THE HOST BEFORE THE STEP: a pool of the release before (test_render.Before: config.toml with no log-file line,
    image UPOLD) on the way-back runscaler v0.9.5 (~/bin/runner and the running process), this release's ~/build
    (Install step 3) with runner-start still the release before's (old_wrapper), the way back's download too; a fake
    clock; the substitutes that log every install and mv (hooks)."""
    g = Before(test)
    p = g.p
    g.wb = wb_download(test, p)
    g.way_back()
    plant_old_wrapper(p)
    p.fake_clock()
    p.hooks()
    g.bin = assignment(os.path.join(p.build, 'setup', '03-runscaler.sh'), 'BIN_SHA')[0]
    return g, p


def on_pinned(test):
    """THE HOST AFTER THE STEP: a fresh host's 03 real (runscaler v0.12.0, the pinned substitute; config.toml this
    release's render, with the line) running, the way back's download in ~/build/dl; a fake clock; hooks."""
    p = Pool(test)
    p.production(V2)
    wb = wb_download(test, p)
    p.fake_clock()
    p.hooks()
    return p, wb, assignment(os.path.join(p.build, 'setup', '03-runscaler.sh'), 'BIN_SHA')[0]


def step(p, *args):
    """`pool-image.sh runscaler ARGS` as a person runs it, in a session of its own (a `kill` hook kills its group)."""
    p.write(p.path('logs', 'runner.log'), '')
    return p.unattended('runscaler', *args, prefix=())


def restarts(p):
    return [l for l in p.lines('systemctl') if l.split(' ')[1:2] in (['stop'], ['start'], ['restart'])]


def rb(p):
    return sha256_file(os.path.join(p.HOME, 'bin', 'runner'))


def staged_calls(test, p, sha):
    """The stage ran THE STAGED BINARY: its version line, the strict control and the validate (3 calls or more), each
    by ~/bin/runner.new of that sha256 (support.POOL_RUNNER's log of which file ran)."""
    calls = p.calls('runner')
    test.assertGreaterEqual(len([c for c in calls if c['argv'][:1] == ['validate']]), 2, calls)
    test.assertIn(['version'], [c['argv'] for c in calls])
    test.assertEqual(sorted(set((c['exe'], c['sha']) for c in calls)),
                     [(os.path.join(p.HOME, 'bin', 'runner.new'), sha)])


def left(p, before):
    """The home as before, less the one file a refusal of the stage leaves: its render, config.real.new.toml (the
    file its FAIL line names for a person to compare), which must be there."""
    now = files(p)
    new = os.path.join(p.home, '.config', 'runner', 'config.real.new.toml')   # files() names the sandbox's paths
    assert new in now, 'the render the FAIL line names'
    return {k: v for k, v in now.items() if k != new} == {k: v for k, v in before.items() if k != new}


def ino(p, name):
    f = p.rpath(name)
    s = os.stat(f)
    return sha256_file(f), s.st_mtime_ns, s.st_ino


def forward_h1(test):
    """THE HOST AT H1 (b2eb739): forward() with config.toml H1's render, this release's but its first line (H1HEAD: the
    one comment line that differs, so the step installs config.toml), in the second it was installed (runscaler runs
    it)."""
    g, p = forward(test)
    g.put(p.rpath('config.toml'), H1HEAD + g.h1.split('\n', 1)[1])
    return g, p


WAYS = ('pre-H1 forward', 'H1 forward', 'the way back')


def rig(test, way):
    """A host before the step, for each of WAYS: (its Pool, the step's arguments, the runscaler the step installs
    (sha256), the config.toml it ends with)."""
    if way == 'the way back':
        p, wb, pin = on_pinned(test)
        return p, (WAYBACK,), wb, p.config()
    g, p = (forward if way == 'pre-H1 forward' else forward_h1)(test)
    return p, (), g.bin, g.h1


# THE PUBLISH (03's header): the four files 03 installs from ~/build, each (SOURCE in ~/build, DEST in the home)
PUBLISHED = (('bin/runner-start', 'bin/runner-start'), ('bin/pool-ready', 'bin/pool-ready'),
             ('bin/validate-class', 'bin/validate-class'),
             ('config/runscaler.service', '.config/systemd/user/runscaler.service'))


def live(p):
    """{DEST: sha256 (None: no file)} of the four files 03 publishes, as installed."""
    return {d: sha256_file(os.path.join(p.HOME, d)) if os.path.isfile(os.path.join(p.HOME, d)) else None
            for s, d in PUBLISHED}


def sources(p):
    """{DEST: sha256 of its ~/build SOURCE}: what each one is once published."""
    return {d: sha256_file(os.path.join(p.build, s)) for s, d in PUBLISHED}


def left_new(p):
    """The four's DEST.new files that are there (a copy a cut left)."""
    return [d + '.new' for s, d in PUBLISHED if os.path.lexists(os.path.join(p.HOME, d + '.new'))]


def disk(p):
    """What a start meets: ~/bin/runner, config.toml and the four published files: {name: sha256}."""
    return dict(live(p), **{'bin/runner': rb(p), 'config.toml': sha256_file(p.rpath('config.toml'))})


def on_disk(p, before, want, cfg):
    """The pair a cut left on disk, as a key that is the same in every rig of a way (each Pool's substitute runscaler
    has bytes of its own: its sandbox path): each of disk()'s files is `before` (as BEFORE, disk() before the cut),
    `after` (what the step ends with: WANT, CFG's text, its ~/build source), both, or `other`."""
    goal = dict(sources(p), **{'bin/runner': want, 'config.toml': hashlib.sha256(cfg.encode()).hexdigest()})
    return tuple(sorted((k, ('before ' if v == before[k] else '') + ('after' if v == goal[k] else '') or 'other')
                        for k, v in disk(p).items()))


def reboot(test, p):
    """runscaler started again on the pair on disk (a reboot, or systemd's own restart): its process runs ~/bin/runner's
    bytes (hzlib.ran); the INSTALLED runner-start's guard starts that pair (the substitute runs no runner-start)."""
    p.act('restart')
    test.assertEqual(p.exe(), rb(p), 'the process a reboot started runs the binary on disk')
    starts(test, p)


def cut_step(test, at='mv-done:runner'):
    """forward(), then the step cut by a SIGKILL of its group AT (by default after both renames, before its restart:
    config.toml and ~/bin/runner installed, runscaler not restarted). Returns (g, p)."""
    g, p = forward(test)
    p.hooks((at, 'kill'))
    step(p)
    test.assertTrue([e for e in p.events() if e.startswith('kill ')], 'the cut ran')
    p.hooks()
    test.assertLessEqual(p.unit_now()['start'], int(os.stat(p.rpath('config.toml')).st_mtime), 'pending: no restart')
    return g, p


def cut_back(test):
    """forward(), a person's `up` to UPV, then its `back` cut in its idle wait (at its first /healthz read: an ssh drop),
    after it put the rollback back as config.toml and before its restart (Opus r1 F1's probe): config.toml.pre-image is
    config.toml byte for byte, installed after the running process (UPNEW's) started. Returns (g, p, the rollback)."""
    g, p = forward(test)
    r = p.pool('up', UPV)
    test.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
    keep = p.rpath('config.toml.pre-image')
    # the process up started: a start in REAL seconds after up's install (the fake clock runs ahead of every real
    # mtime, so back's install would read as older than that start), the clock waited for (a state), then named
    m = int(os.stat(p.rpath('config.toml')).st_mtime)
    while int(time.time()) <= m:
        time.sleep(0.05)
    p.set_unit(start=m + 1, pid=p.unit_now()['pid'])
    while int(time.time()) <= m + 1:
        time.sleep(0.05)
    p.hooks(('healthz-read', 'kill'))
    p.write(p.path('logs', 'runner.log'), '')
    r = p.unattended('back', prefix=())
    test.assertTrue([e for e in p.events() if e.startswith('kill ')], 'the cut ran')
    p.hooks()
    test.assertEqual(sha256_file(keep), sha256_file(p.rpath('config.toml')), 'back put the rollback in place')
    test.assertLessEqual(p.unit_now()['start'], int(os.stat(p.rpath('config.toml')).st_mtime), 'pending: no restart')
    return g, p, keep


def up_record(p, version, d):
    """The build record of runner VERSION naming image d (the registry serves d; d's runner is VERSION)."""
    p.record(version, d)
    p.docker['versions'][ref(d)] = version + '\n'
    if d not in p.curl['served']:
        p.curl['served'] = p.curl['served'] + [d]


PLAN = re.compile(r'(?i)\bplan\s*§|\bplan\s+D[0-9]')   # a section of a plan: `plan §4 B4`, `PLAN D3`


def code_part(line):
    """LINE less a comment: a whole-line one, or one that starts at a `#` after a blank outside quotes (a shell's word
    that starts with #; python's comment too), a backslash escaping the next character outside single quotes."""
    if line.lstrip().startswith('#'):
        return ''
    q, i = None, 0
    while i < len(line):
        c = line[i]
        if q is None and c in '"\'':
            q = c
        elif q is None and c == '\\' or q == '"' and c == '\\':
            i += 1
        elif q is None and c == '#' and (i == 0 or line[i - 1] in ' \t'):
            return line[:i]
        elif c == q:
            q = None
        i += 1
    return line


def plan_refs(root):
    """[(file relative to ROOT, the line stripped)] of each line of ROOT that names a plan's section (PLAN): every line
    of a *.md file, the code part (code_part) of any other; a file that is not UTF-8 text is no text."""
    out = []
    for d, dirs, names in os.walk(root):
        dirs.sort()
        for n in sorted(names):
            try:
                with open(os.path.join(d, n), encoding='utf-8') as f:
                    lines = f.read().splitlines()
            except UnicodeDecodeError:
                continue
            for l in lines:
                if PLAN.search(l if n.endswith('.md') else code_part(l)):
                    out.append((os.path.relpath(os.path.join(d, n), root), l.strip()))
    return out


class Text(unittest.TestCase):
    def test_the_download_s_name_is_one_rule_in_03_and_pool_image_sh(self):
        """dl_of VERSION: the file of VERSION's download in ~/build/dl, byte for byte the same function in both (03
        extracts from it, pool-image.sh checks it before anything changes)."""
        mine, theirs = function(S03, 'dl_of'), function(PIMG, 'dl_of')
        self.assertIsNotNone(mine)
        self.assertEqual(mine, theirs)
        self.assertIn('runner-linux-amd64.tar.gz', mine)
        self.assertIn('runner-v$1-linux-amd64.tar.gz', mine)

    def test_the_running_binary_is_one_function_of_one_process_table(self):
        """R-6: pool-image.sh reads the running binary in ONE function (running_sha: systemd's MainPID, then sha256 of
        PROCFS/<pid>/exe) of ONE pin line PROCFS=/proc (the cells rewrite it: support.Sandbox.OPTIONAL_REWRITES); no
        other code line names /proc; the two restart shortcuts and the final check read it through runs_this or
        running_sha."""
        self.assertEqual(assignment(PIMG, 'PROCFS'), ['/proc'])
        f = function(PIMG, 'running_sha')
        self.assertIsNotNone(f)
        self.assertIn('"$PROCFS/$pid/exe"', f)
        self.assertIn('-p MainPID', f)
        with open(PIMG) as fh:
            code = [l for l in fh if not l.lstrip().startswith('#')]
        self.assertEqual([l for l in code if '/proc' in l], ['PROCFS=/proc\n'])
        r = function(PIMG, 'restart')
        self.assertIn('if runs_this; then', r)
        self.assertEqual(len([l for l in code if 'if runs_this; then' in l]), 2, 'both shortcuts')

    def test_the_stage_s_compare_is_runner_release_sh_s(self):
        """THE CONFIG COMPARE stays ONE construction in runner-release.sh: rr_same_config (the image lines are content)
        and rr_same_but_image (they are not) share it; 03's stage calls rr_same_config, before anything is installed."""
        with open(RR) as f:
            rr = f.read()
        for n in ('rr_same_config', 'rr_same_but_image', 'rr_same_'):
            self.assertIsNotNone(function(RR, n), n)
        self.assertIn('rr_same_ keep', function(RR, 'rr_same_config'))
        self.assertIn('rr_same_ drop', function(RR, 'rr_same_but_image'))
        with open(S03) as f:
            s03 = f.read()
        self.assertEqual(s03.count('rr_same_config "$R/config.toml" "$NEW"'), 1)
        for path in (S03, PIMG):
            for n in ('rr_same_', 'rr_same_config', 'rr_same_but_image'):
                self.assertIsNone(function(path, n), (path, n))
        self.assertEqual(rr.count('\nrr_same_() {'), 1)

    def test_no_text_names_a_document_that_is_not_in_this_repository(self):
        """R-1's last sentence (Codex F3, Opus F3): every text of linux-docker/ (its programs, configs and README) that
        names a document (a file name ending .md, or a path under docs/) names one that is in this repository (from
        its root, from linux-docker/, or from the naming file's folder). 49a2004's up named docs/runners.md section 3b.
        The control: the references that are there (README.md, core/README.md) are found."""
        root = os.path.join(REPO, 'linux-docker')
        pat = re.compile(r'(?:[A-Za-z0-9_.~-]+/)*[A-Za-z0-9_.-]+\.md\b|docs/[A-Za-z0-9_./-]+')
        found, missing = set(), []
        for d, _, names in os.walk(root):
            for n in sorted(names):
                try:
                    with open(os.path.join(d, n), encoding='utf-8') as f:
                        lines = f.read().splitlines()
                except UnicodeDecodeError:
                    continue
                for i, l in enumerate(lines, 1):
                    for m in pat.finditer(l):
                        ref_ = m.group(0).rstrip('.')
                        found.add(ref_)
                        if not any(os.path.exists(os.path.join(b, ref_)) for b in (REPO, root, d)):
                            missing.append('%s:%d %s' % (os.path.relpath(os.path.join(d, n), REPO), i, ref_))
        self.assertEqual(missing, [])
        self.assertTrue({'core/README.md', 'linux-docker/README.md'} <= found, sorted(found))

    def test_no_text_names_a_section_of_a_private_plan(self):
        """Review r2, Opus F4 (the class, by plan_refs: N = 5 at 8407d35): no text of linux-docker/ names a section of a
        plan this repository does not hold (`plan §4 B4`, `PLAN D3`): the code part of each program line (a comment,
        whole-line or trailing, may name one: it is the maintainers' note, never printed) and every line of the
        README. 8407d35's five: runner-start's Docker refusal (plan §2.2: now the README's seccomp text), 03's no
        pool.env (plan §4 B4: README Install step 6) and no token (plan §4 B3: step 8), 01-users-undo.sh's token
        file (plan §3 R1-UNDO: README "Uninstall"), pool-image.sh's unattended compare (plan D3). A line of each
        shape planted in a COPY is found; the control: the same text as a whole-line or a trailing comment is not,
        and a `#` inside quotes starts no comment."""
        tree = plan_refs(os.path.join(REPO, 'linux-docker'))
        with self.subTest('the tree'):
            self.assertEqual(tree, [])
        for rel, line, found in (('setup/03-runscaler.sh', '[ -e "$POOL" ] || die "no $POOL (plan §4 B4)"', True),
                                 ('bin/runner-start', "  sys.exit(f'see PLAN D5 for {cfg}')", True),
                                 ('setup/pool-image.sh', 'echo "a # (plan §2.2) is no comment here"', True),
                                 ('README.md', 'Run it as plan D3 says.', True),
                                 ('setup/03-runscaler.sh', '  # plan §4 B4: the numbers', False),
                                 ('setup/pool-image.sh', 'DISK_PCT=10   # (plan D5 DISK)', False)):
            with self.subTest(file=rel, line=line):
                with tempfile.TemporaryDirectory() as tmp:
                    root = os.path.join(tmp, 'linux-docker')
                    shutil.copytree(os.path.join(REPO, 'linux-docker'), root)
                    with open(os.path.join(root, rel), 'a') as f:
                        f.write(line + '\n')
                    added = collections.Counter(plan_refs(root)) - collections.Counter(tree)   # the planted line's own
                    self.assertEqual(dict(added), {(rel, line.strip()): 1} if found else {})


class Readme(unittest.TestCase):
    def section(self):
        text = readme()
        self.assertEqual(text.count('\n## runscaler: the release this one pins, and the way back\n'), 1)
        return text.split('\n## runscaler: the release this one pins, and the way back\n', 1)[1].split('\n## ', 1)[0]

    def test_the_section_says_what_the_step_does_in_order(self):
        """Item 6: the step's command, its order (the checks, the stage, config then binary, the idle restart, READY,
        the running binary, the cut scan, NEXT), R-1's sentence, and the steps around it."""
        sec = self.section()
        self.assertIn("'bash -s -- runscaler' < linux-docker/setup/pool-image.sh", sec)
        order = ('`~/bin/runner.new`', 'config.toml first', 'then renames', 'at idle', 'for READY', 'the process that runs',
                 'any job a restart cut')
        at = [sec.find(w) for w in order]
        self.assertNotIn(-1, at, list(zip(order, at)))
        self.assertEqual(at, sorted(at), list(zip(order, at)))
        self.assertIn('a config.toml that a bare `03-runscaler.sh real` installed and runscaler has not started yet '
                      'goes live with this restart', sec)
        for w in ('Install step 3 for both users', 'Install step 4', 'at a quiet time', 'DONE ALREADY',
                  'accept or back', 'enable'):
            self.assertIn(w, sec)

    def test_what_a_cut_leaves_and_the_back_it_waits_for(self):
        """THE PUBLISH (Codex r1 F1): each file 03 installs is copied beside itself and renamed over it, so a cut never
        leaves a partial file. R-4 (Opus r1 F1): the rollback that config.toml already is goes only once runscaler runs
        it (or its unit is down); a `back` cut before its restart stops the step, which names `pool-image.sh back`."""
        sec = self.section()
        for w in ('renamed over it, so a cut never leaves a partial file', 'a `back` cut before its restart',
                  'run `pool-image.sh back` again first'):
            self.assertIn(w, sec)

    def test_a_release_a_back_closed_and_the_lines_up_names_after_a_bare_03(self):
        """Review r2, Opus F1 and F2 (PendingLines, Keep): the section's check list says a kept config that names
        config.toml's image is a release a back closed (also after a bare 03 real changed config.toml), which the step
        removes; the text on running 03 by hand says what `up` then names: the step, or on a host whose runscaler is
        v0.9.5 both lines, each with its case (review r1 of H2c, opus F3: a host that took the way back, or a step to
        v0.12.0 a cut stopped before it replaced the binary), or `back` while a release is open, which puts the kept
        config back over a config.toml runscaler never ran."""
        sec = self.section()
        for w in ('names another image than config.toml', 'The kept config of a release a `back` closed names '
                  'config.toml\'s image', 'or config.toml changed since, by a bare `03-runscaler.sh real`'):
            self.assertIn(w, sec)
        hand = readme().split('Do not run 03-runscaler.sh by hand on the running pool', 1)[1].split('\n', 1)[0]
        for w in ('that `up` names the line that finishes it', '`pool-image.sh runscaler`, or, on a host whose runscaler '
                  'is v0.9.5, both `pool-image.sh runscaler 0.9.5` (a host that took the way back) and `pool-image.sh '
                  'runscaler` (a step to v0.12.0 that a cut stopped before v0.12.0 replaced the binary)',
                  '`pool-image.sh back` while one is', 'over a config.toml runscaler never ran'):
            self.assertIn(w, hand)

    def test_the_way_back_s_two_lines_are_the_files_the_step_reads(self):
        """The way back: its download line (v0.9.5's release asset into 03's dl_of name for it) and the step with that
        version; the way forward again: the step with no version, from Install step 4's download."""
        sec = self.section()
        dl = "mkdir -p ~/build/dl && curl -fsSL -o ~/build/dl/%s %s'" % (WBDL, URL % WAYBACK)
        self.assertIn(dl, sec)
        self.assertIn("'bash -s -- runscaler %s' < linux-docker/setup/pool-image.sh" % WAYBACK, sec)
        self.assertEqual(readme().count(URL % WAYBACK), 1)

    def test_the_warn_is_expected_and_its_fix_is_never_run(self):
        """F7: v0.12.0's start WARN is expected; its `fix=… migrate --user` and `runner update` are never run."""
        sec = self.section()
        self.assertIn('`Service definition predates this runner\'s template', sec)
        self.assertIn('expected', sec)
        self.assertRegex(sec, r'(?i)never run its `fix=[^`]*migrate --user`')
        self.assertRegex(sec, r'(?i)never `runner update`')

    def test_the_updater_after_the_step_as_measured(self):
        """M-6, as measured (UpdaterAfterTheStep): no candidate and no rollback; a pass during the step's restart, or one
        that started before the step and reads runscaler while it restarts (Codex r1's M-6 row), holds STOP POOL DOWN,
        and the next pass clears it once runscaler runs."""
        sec = self.section()
        for w in ('no candidate', 'rolls nothing back', '`STOP POOL DOWN`', 'the next pass clears it',
                  'one that started before the step and reads runscaler while it restarts'):
            self.assertIn(w, sec)

    def test_every_text_that_names_the_step(self):
        """The Files row of pool-image.sh, Install steps 4 and 9, "A new runner release", the upgrade note and "The
        log-file line" name the step (and its section)."""
        text = readme()
        row = [l for l in text.splitlines() if l.startswith('| `setup/pool-image.sh` |')]
        self.assertEqual(len(row), 1)
        self.assertIn('`runscaler`', row[0])
        ins = text.split('\n## Install\n', 1)[1].split('\n## ', 1)[0]
        s4 = ins.split('\n4. ', 1)[1].split('\n5. ', 1)[0]
        s9 = ins.split('\n9. ', 1)[1].split('\n10. ', 1)[0]
        for s in (s4, s9):
            self.assertIn('"runscaler: the release this one pins, and the way back"', s)
        up = text.split('\n## Upgrading from a release before this one\n', 1)[1].split('\n## ', 1)[0]
        self.assertIn('`pool-image.sh runscaler`', up)
        lf = text.split('\n## The log-file line\n', 1)[1].split('\n## ', 1)[0]
        self.assertIn('`pool-image.sh runscaler`', lf)


@needs_container
class Forward(unittest.TestCase):
    def test_from_v0_9_5_and_a_config_before_the_line_it_installs_the_line_then_the_binary(self):
        """M-3 (b) of the plan's acceptance: config.toml and config.real.toml become this release's render (the line),
        THEN ~/bin/runner the pinned runscaler (by a rename of runner.new: the mv log's order), one restart at idle
        (two /healthz reads before it), the running process runs the pinned bytes; the stage ran the staged binary
        under THIS release's runner-start (the old one ignores the selector: R-2); the pair starts under the installed
        guard; NEXT names the way back's two lines."""
        g, p = forward(self)
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        staged_calls(self, p, g.bin)
        self.assertEqual(p.config(), g.h1)
        self.assertEqual(p.config('config.real.toml'), g.h1)
        self.assertEqual(rb(p), g.bin)
        self.assertFalse(os.path.lexists(os.path.join(p.HOME, 'bin', 'runner.new')))
        ev = p.events()
        mv = [e for e in ev if e in ('mv config.real.toml', 'mv config.toml', 'mv runner')]
        self.assertEqual(mv, ['mv config.real.toml', 'mv config.toml', 'mv runner'])
        self.assertEqual(restarts(p), ['--user restart runscaler'])
        first = next(i for i, e in enumerate(ev) if re.fullmatch(r'process [0-9]+ stopped', e))
        self.assertGreaterEqual(ev[:first].count('healthz read'), 2, ev)
        self.assertEqual(p.exe(), g.bin)
        self.assertEqual(sha256_file(os.path.join(p.HOME, 'bin', 'runner-start')),
                         sha256_file(os.path.join(p.build, 'bin', 'runner-start')))
        self.assertIn('POOL RUNSCALER DONE: runscaler v%s runs' % PINNED, r.stdout)
        self.assertIn("curl -fsSL -o ~/build/dl/%s %s" % (WBDL, URL % WAYBACK), r.stdout)
        self.assertIn('pool-image.sh runscaler %s' % WAYBACK, r.stdout)
        starts(self, p)

    def test_a_drifted_host_value_refuses_before_anything_is_installed(self):
        """M-3 (c): the host config's MAIN_LABEL is not the one the pool runs: the stage refuses at its compare, which
        comes before any install: config.toml, config.real.toml and every file of the home as they were (config.toml's
        inode too) but the render its FAIL line names (config.real.new.toml), ~/bin/runner the same file, no
        runner.new, no runscaler call, nothing restarted."""
        g, p = forward(self)
        g.label('linux-ci-x')
        before, cfg, b0 = files(p), ino(p, 'config.toml'), binary(p)
        r = step(p)
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        self.assertIn('FAIL the render differs from config.toml in more than its comment lines and the log-file line',
                      r.stdout)
        self.assertTrue(left(p, before))
        self.assertEqual(ino(p, 'config.toml'), cfg)
        self.assertEqual(binary(p), b0)
        self.assertFalse(os.path.lexists(os.path.join(p.HOME, 'bin', 'runner.new')))
        self.assertEqual(p.calls('runner'), [])
        self.assertEqual(restarts(p), [])

    def test_a_validate_that_is_not_pass_changes_neither_config_nor_binary(self):
        """M-3 (c): runscaler's validate (by the staged binary) NON-API or API-ONLY: config.toml and config.real.toml
        (sha, mtime, inode) and ~/bin/runner as they were, no runner.new, nothing restarted. What it did install:
        this release's runner-start, pool-ready, validate-class and unit (each starts with either runscaler)."""
        for cls, out in (('NON-API', fixture('non-api-real.txt')), ('API-ONLY', fixture('api-only-real.txt'))):
            with self.subTest(cls):
                g, p = forward(self)
                p.runner = {'rc': 1, 'out': out}
                cfg, real, b0 = ino(p, 'config.toml'), ino(p, 'config.real.toml'), binary(p)
                r = step(p)
                self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
                self.assertIn('VALIDATE %s' % cls, r.stdout)
                self.assertEqual((ino(p, 'config.toml'), ino(p, 'config.real.toml'), binary(p)), (cfg, real, b0))
                self.assertFalse(os.path.lexists(os.path.join(p.HOME, 'bin', 'runner.new')))
                self.assertEqual(restarts(p), [])
                self.assertEqual(sha256_file(os.path.join(p.HOME, 'bin', 'runner-start')),
                                 sha256_file(os.path.join(p.build, 'bin', 'runner-start')))

    def test_a_runner_new_a_cut_left_is_removed(self):
        """(c), THE PUBLISH: a ~/bin/runner.new a SIGKILL left (other bytes), and a DEST.new of each of the four files 03
        publishes (a copy a cut left), are gone after the next run of the step, a refusal at its compare too (the trap:
        03 names them from its start), and a run that goes on installs VERSION's own runner and this release's four.
        49a2004 leaves each DEST.new (it made none)."""
        for how in ('a refusal', 'a run that goes on'):
            with self.subTest(how):
                g, p = forward(self)
                new = os.path.join(p.HOME, 'bin', 'runner.new')
                p.write(new, '#!/bin/sh\nexit 99\n', 0o755)
                for s, d in PUBLISHED:
                    p.write(os.path.join(p.HOME, d + '.new'), 'a copy a cut left\n', 0o600)
                if how == 'a refusal':
                    g.label('linux-ci-x')
                r = step(p)
                self.assertEqual(r.returncode, 1 if how == 'a refusal' else 0, r.stdout[-4000:] + r.stderr)
                self.assertFalse(os.path.lexists(new))
                self.assertEqual(left_new(p), [])
                self.assertEqual(rb(p), g.wb if how == 'a refusal' else g.bin)
                if how != 'a refusal':
                    self.assertEqual(live(p), sources(p))

    def test_the_stage_installs_only_the_pinned_files(self):
        """R-2: `03 stage` itself (a person may run it by hand, past pool-image.sh's PINS) refuses a ~/build file that is
        not its PIN before it installs that file: runner-start is this release's, pool-ready not, so 03 stops at
        pool-ready, config.toml and ~/bin/runner as they were, no runner.new. THE PUBLISH's control (Codex F1): the
        live pool-ready as it was, and no DEST.new left."""
        g, p = forward(self)
        with open(os.path.join(p.build, 'bin', 'pool-ready'), 'a') as f:
            f.write('# not the pinned copy\n')
        cfg, b0, pr = ino(p, 'config.toml'), binary(p), sha256_file(os.path.join(p.HOME, 'bin', 'pool-ready'))
        r = p.s03('stage', PINNED, 'content')
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        self.assertIn('build/bin/pool-ready is not the bin/pool-ready this release pins', r.stdout)
        self.assertEqual((ino(p, 'config.toml'), binary(p)), (cfg, b0))
        self.assertEqual(sha256_file(os.path.join(p.HOME, 'bin', 'pool-ready')), pr)
        self.assertFalse(os.path.lexists(os.path.join(p.HOME, 'bin', 'runner.new')))
        self.assertEqual(left_new(p), [])

    def test_r_3_forward_with_a_down_unit(self):
        """R-3 forward (Opus r1 F5; Codex's coverage table): runscaler v0.9.5's unit enabled and failed (or crash-looping):
        the step compares with config.toml, installs v0.12.0 and starts it with no idle wait (no /healthz read before
        the start), and v0.12.0 runs. (Green on 49a2004: a cell it lacked; its red is the mutants of R-3, P6 and P7.)"""
        for how in ('failed', 'crash loop'):
            with self.subTest(how):
                g, p = forward(self)
                if how == 'failed':
                    p.set_unit(active=False, failed=True)
                else:
                    p.set_unit(runner='crash')
                    p.hooks(('systemctl:restart-begin', 'serve'))
                r = step(p)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertEqual((rb(p), p.exe(), p.config()), (g.bin, g.bin, g.h1))
                ev = p.events()
                started = next(i for i, e in enumerate(ev) if re.fullmatch(r'process [0-9]+ started [0-9]+', e))
                self.assertNotIn('healthz read', ev[:started])
                self.assertEqual(restarts(p), ['--user restart runscaler'])

    def test_a_fail_after_the_restart_names_the_other_way_s_lines(self):
        """(e), Opus r3 F3 (r1 F5): a pool that is not READY after the restart: FAIL, exit 1, and its line names the way
        back's two lines (its download, then `pool-image.sh runscaler 0.9.5`); on the way back, the way forward's
        (`pool-image.sh runscaler`). 49a2004's again() named only the README section."""
        for way in ('forward', 'the way back'):
            with self.subTest(way):
                if way == 'forward':
                    g, p = forward(self)
                    args = ()
                else:
                    p, wb, pin = on_pinned(self)
                    args = (WAYBACK,)
                p.curl['healthz'] = healthz(**{'linux-ci-main': {'ready': False}})
                r = step(p, *args)
                self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
                fail = [l for l in r.stdout.splitlines() if l.startswith('FAIL ')]
                self.assertEqual(len(fail), 1, fail)
                self.assertIn('not READY', fail[0])
                if way == 'forward':
                    self.assertIn('mkdir -p ~/build/dl && curl -fsSL -o ~/build/dl/%s %s' % (WBDL, URL % WAYBACK),
                                  fail[0])
                    self.assertIn('pool-image.sh runscaler %s' % WAYBACK, fail[0])
                else:
                    self.assertRegex(fail[0], r'the way forward again: pool-image\.sh runscaler(?! ?[0-9])')

    def test_a_restart_that_leaves_the_old_binary_running_is_a_fail(self):
        """(e): after READY the step reads the running binary: the restart's stop did not stop the old process (it
        runs again: the hook `revive` at the restart's end), so the process runs v0.9.5's bytes: FAIL naming
        journalctl, exit 1, no DONE line."""
        g, p = forward(self)
        p.hooks(('systemctl:restart-done', 'revive'))
        r = step(p)
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        self.assertIn('FAIL the runscaler that runs is not v%s: its process runs runscaler v%s' % (PINNED, WAYBACK),
                      r.stdout)
        self.assertIn('journalctl --user -u runscaler', r.stdout)
        self.assertNotIn('POOL RUNSCALER DONE', r.stdout)

    def test_an_unknown_installed_runscaler_is_what_the_step_replaces(self):
        """(a): the installed binary may be unknown (every other door refuses it, naming this step): the step installs
        the pinned one, and it runs."""
        g, p = forward(self)
        unknown(p)
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertEqual((rb(p), p.exe()), (g.bin, g.bin))

    def test_a_crash_restart_between_the_renames_restarts_again(self):
        """R-6, M-3 (e): runscaler restarts by itself (a crash) after config.toml's rename and before the binary's: that
        process runs the OLD binary on the new config, and started after config.toml was installed. The step's
        shortcuts need the running binary to be VERSION's, so it restarts once more; the process then runs the pinned
        bytes. Mutants: either shortcut without the running-binary test."""
        g, p = forward(self)
        p.hooks(('mv-done:config.toml', 'restart'))
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        ev = p.events()
        hook = ev.index('hook mv-done:config.toml: restart')
        exe = [e for e in ev[hook:] if e.startswith('exe ')]
        self.assertRegex(exe[0], r'^exe [0-9]+ %s$' % g.wb[:12], 'that process ran the old binary')
        self.assertRegex(exe[-1], r'^exe [0-9]+ %s$' % g.bin[:12], 'the step restarted it on the pinned one')
        self.assertEqual(p.unit_now()['independent'], 1)
        self.assertEqual(restarts(p), ['--user restart runscaler'])
        self.assertEqual(p.exe(), g.bin)


@needs_container
class TheWayBack(unittest.TestCase):
    def test_the_way_back_installs_v0_9_5_the_same_way_and_restarts(self):
        """M-3's control: `runscaler 0.9.5` on the pinned host: the way-back runner from its own download, through the
        staged binary; config.toml is already this step's render (no rename onto it: its mtime as it was), so
        runscaler started after its install, and the old binary still runs: one restart (R-6's control; the mutant of
        the outer shortcut says "no restart"), then v0.9.5 runs that config with the line (the installed guard
        starts it). NEXT names the way forward."""
        p, wb, pin = on_pinned(self)
        cfg = ino(p, 'config.toml')
        r = step(p, WAYBACK)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        staged_calls(self, p, wb)
        self.assertEqual((rb(p), p.exe()), (wb, wb))
        self.assertEqual(ino(p, 'config.toml'), cfg)
        self.assertNotIn('mv config.toml', p.events())
        self.assertEqual(restarts(p), ['--user restart runscaler'])
        self.assertIn('POOL RUNSCALER DONE: runscaler v%s runs' % WAYBACK, r.stdout)
        self.assertIn('pool-image.sh runscaler\n', r.stdout)
        starts(self, p)

    def test_the_way_back_works_with_a_down_pool(self):
        """R-3: v0.12.0 cannot run (its unit failed, or crash-loops: activating, MainPID 0, between 1-s starts); the
        unit is enabled: `runscaler 0.9.5` compares with config.toml, installs v0.9.5 and starts it with no idle wait
        (no /healthz read before the start), and v0.9.5 runs."""
        for how in ('failed', 'crash loop'):
            with self.subTest(how):
                p, wb, pin = on_pinned(self)
                if how == 'failed':
                    p.set_unit(active=False, failed=True)
                else:
                    p.set_unit(runner='crash')
                    p.hooks(('systemctl:restart-begin', 'serve'))
                r = step(p, WAYBACK)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertEqual((rb(p), p.exe()), (wb, wb))
                ev = p.events()
                started = next(i for i, e in enumerate(ev) if re.fullmatch(r'process [0-9]+ started [0-9]+', e))
                self.assertNotIn('healthz read', ev[:started])
                self.assertEqual(restarts(p), ['--user restart runscaler'])

    def test_control_a_disabled_unit_refuses_naming_the_enable_line(self):
        """R-3's other side: a unit a person disabled (CI off) refuses, naming the enable line; nothing changed."""
        p, wb, pin = on_pinned(self)
        p.set_unit(enabled=False)
        before = files(p)
        r = step(p, WAYBACK)
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        self.assertIn('systemctl --user enable --now runscaler', r.stdout)
        self.assertEqual(files(p), before)
        self.assertEqual((p.calls('runner'), restarts(p)), ([], []))


@needs_container
class Publish(unittest.TestCase):
    """THE PUBLISH (Codex r1 F1, P1): 03 (the stage and real) installs runner-start, pool-ready, validate-class and the
    unit into DEST.new in the same folder, checks it (the stage: its PIN; real: its ~/build source byte for byte), then
    renames it over DEST: the live file is never written in place. The fault (support.INSTALL_STUB's cut-copy): the
    copy of one named file writes half of it into its destination, then pool-image.sh's group is SIGKILLed. 49a2004
    copies onto the live file: it is then partial (an empty unit file reads as masked after a reboot, Codex F1)."""

    def cut_copy(self, p, src, run):
        """RUN (a callable) with the copy of ~/build's SRC cut midway: the cut ran, RUN did not end well, and each of
        the four live files is whole: as it was, or its source (a partial one is neither)."""
        before, srcs = live(p), sources(p)
        p.hooks(('cut-copy:' + os.path.basename(src),))
        r = run()
        self.assertTrue([e for e in p.events() if e.startswith('cut-copy ')], 'the cut ran')
        self.assertTrue([e for e in p.events() if e.startswith('kill ')], 'the cut ran')
        self.assertNotEqual(r.returncode, 0)
        p.hooks()
        now = live(p)
        for k in now:
            self.assertIn(now[k], (before[k], srcs[k]), 'the live %s is not whole' % k)

    def test_a_copy_cut_midway_leaves_each_live_file_whole_and_the_same_line_finishes(self):
        """Each of the four, forward (from v0.9.5 and a config before H1) and on the way back (from v0.12.0): the step
        cut inside the copy of that file: each live file whole; after a reboot (runscaler started again on the pair on
        disk) the INSTALLED runner-start's guard starts that pair; the same line then finishes (VERSION's runscaler
        runs, the four are this release's, no DEST.new left)."""
        for way in ('forward', 'the way back'):
            for s, d in PUBLISHED:
                with self.subTest(way=way, file=d):
                    if way == 'forward':
                        g, p = forward(self)
                        args, want = (), g.bin
                    else:
                        p, wb, pin = on_pinned(self)
                        args, want = (WAYBACK,), wb
                    self.cut_copy(p, s, lambda: step(p, *args))
                    reboot(self, p)
                    r = step(p, *args)
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                    self.assertEqual((rb(p), p.exe()), (want, want))
                    self.assertEqual(live(p), sources(p))
                    self.assertEqual(left_new(p), [])

    def test_03_real_from_a_person_s_up_publishes_each_file_whole_too(self):
        """03 real (here a person's `up`, its `03 real DIGEST --image-only`) the same way: each of the four, the copy cut
        midway: each live file whole, config.toml not changed; after a reboot the installed guard starts the pair; the
        same `up` line then ends with POOL IMAGE DONE, the four this release's, no DEST.new left."""
        for s, d in PUBLISHED:
            with self.subTest(file=d):
                g = Before(self)
                g.way_back()
                p = g.p
                p.fake_clock()
                cfg = ino(p, 'config.toml')
                self.cut_copy(p, s, lambda: p.unattended('up', UPV, prefix=()))
                self.assertEqual(ino(p, 'config.toml'), cfg)
                reboot(self, p)
                r = p.unattended('up', UPV, prefix=())
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertIn('POOL IMAGE DONE (up): %s' % ref(UPNEW), r.stdout)
                self.assertEqual(live(p), sources(p))
                self.assertEqual(left_new(p), [])

    def test_a_copy_that_is_not_its_source_is_refused_and_the_live_file_stays(self):
        """THE PUBLISH's check: a copy that gets a line more after it was made (support.INSTALL_STUB's taint-copy) is
        refused before its rename: the stage by its PIN, real (a person's up) by its source's bytes. Exit 1, the live
        file as it was, no DEST.new left (the trap), nothing restarted, ~/bin/runner and config.toml as they were.
        49a2004 checks the live file after it wrote it (the stage), or not at all (real)."""
        for how in ('the stage', "a person's up"):
            for s, d in PUBLISHED:
                with self.subTest(how=how, file=d):
                    if how == 'the stage':
                        g, p = forward(self)
                    else:
                        g = Before(self)
                        g.way_back()
                        p = g.p
                        p.fake_clock()
                        p.hooks()
                    before, cfg, b0 = live(p), ino(p, 'config.toml'), binary(p)
                    p.hooks(('taint-copy:' + os.path.basename(s),))
                    r = step(p) if how == 'the stage' else p.unattended('up', UPV, prefix=())
                    self.assertTrue([e for e in p.events() if e.startswith('taint-copy ')], 'the taint ran')
                    self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
                    self.assertEqual(live(p)[d], before[d])
                    self.assertEqual(left_new(p), [])
                    self.assertEqual((ino(p, 'config.toml'), binary(p)), (cfg, b0))
                    self.assertEqual(restarts(p), [])


@needs_container
class Keep(unittest.TestCase):
    def test_a_release_closed_by_back_is_removed_first_and_said_so(self):
        """R-4: config.toml.pre-image byte-equal to config.toml (an image release `back` closed; it has no line): the
        step removes it, says so, and goes on; v0.12.0 runs. A later person's `back` then has nothing to put back (no
        config with no line under v0.12.0), and refuses before any put."""
        g, p = forward(self)
        g.put(p.rpath('config.toml.pre-image'), g.pre)
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertIn('removed %s' % p.rpath('config.toml.pre-image'), r.stdout)
        self.assertFalse(os.path.lexists(p.rpath('config.toml.pre-image')))
        self.assertEqual((rb(p), p.exe()), (g.bin, g.bin))
        cfg, n = ino(p, 'config.toml'), len(restarts(p))
        r = p.pool('back')
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        self.assertIn('there is no open release to roll back', r.stdout)
        self.assertEqual((ino(p, 'config.toml'), len(restarts(p))), (cfg, n))

    def test_control_an_open_release_refuses(self):
        """R-4's other side: an open image release, an `up` with neither its `accept` nor its `back`: its
        config.toml.pre-image names another image than config.toml's (review r2, Opus F1's control): refused ("accept,
        or back"), nothing changed. (8407d35's cell planted a rollback of config.toml's own image with other comments:
        by accept's rule that is a release a `back` closed: the cell below.)"""
        g, p = forward(self)
        r = p.pool('up', UPV)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertNotEqual(p.images('config.toml.pre-image'), p.images())
        before = files(p)
        r = step(p)
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        self.assertIn('pool-image.sh accept', r.stdout)
        self.assertIn('pool-image.sh back', r.stdout)
        self.assertEqual(files(p), before)
        self.assertEqual(p.calls('runner'), [])
        self.assertEqual(restarts(p), ['--user restart runscaler'], 'up\'s own restart, and no other')

    def test_a_release_a_back_closed_then_a_numbers_change_is_closed_too(self):
        """Review r2, Opus F1 (its probeA): an `up`, its `back` (config.toml.pre-image stays, config.toml byte for byte),
        then a change of pool.env's numbers and a bare `03 real` (Install step 9), runscaler restarted on it: the
        rollback names config.toml's image (accept's own rule: after a back there is nothing to accept), so the release
        is closed, though the bytes differ (the numbers): the step removes it, says so, and goes on: v0.12.0 runs
        config.toml with the new numbers. 8407d35 refused ("an image release is open"), and accept and back refused
        too: no line cleared it."""
        g, p = forward(self)
        for args in (('up', UPV), ('back',)):
            r = p.pool(*args)
            self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        keep = p.rpath('config.toml.pre-image')
        self.assertEqual(sha256_file(keep), sha256_file(p.rpath('config.toml')))
        p.pool_env(CONCURRENT=3, MAX=2)
        r = p.s03('real')
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        ran_it(self, p)   # runscaler restarted on it, after its real install (the class of opus F5: ran_it)
        cfg = p.config()
        self.assertIn('concurrent = 3\n', cfg)
        self.assertEqual(p.images(), p.images('config.toml.pre-image'))
        self.assertNotEqual(sha256_file(keep), sha256_file(p.rpath('config.toml')))
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertIn('removed %s' % keep, r.stdout)
        self.assertFalse(os.path.lexists(keep))
        self.assertEqual((rb(p), p.exe(), p.config()), (g.bin, g.bin, cfg))
        starts(self, p)

    def test_a_back_cut_before_its_restart_is_finished_by_back_first(self):
        """R-4, Opus r1 F1 (P2): a person's `back` cut in its idle wait (cut_back: config.toml.pre-image is config.toml
        byte for byte, installed after the running process started, the unit active) is not a release a back closed:
        the step refuses before any change (the rollback and config.toml keep sha256 and mtime: every file of the home
        as it was), runs no runscaler, restarts nothing, and its line names `pool-image.sh back`, which finishes it.
        Then `back`: exit 0, one restart; then the step: the rollback removed (runscaler now started after config.toml's
        install), exit 0, v0.12.0 runs. 49a2004 removed the rollback and then refused at its stage: `back` and `up`
        refused too."""
        g, p, keep = cut_back(self)
        before, b0, n = files(p), binary(p), len(restarts(p))
        r = step(p)
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        fail = [l for l in r.stdout.splitlines() if l.startswith('FAIL ')]
        self.assertTrue([l for l in fail if re.search(r'(?i)\brun pool-image\.sh back\b', l)],
                        'no FAIL line names the line to run, `pool-image.sh back` (a cause it names is not one): %r' % fail)
        self.assertEqual(len(fail), 1, fail)
        self.assertIn('nothing changed', fail[0])
        self.assertEqual(files(p), before)
        self.assertEqual(binary(p), b0)
        self.assertFalse(os.path.lexists(os.path.join(p.HOME, 'bin', 'runner.new')))
        self.assertEqual((p.calls('runner'), len(restarts(p))), ([], n))
        r = p.pool('back')
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertEqual(len(restarts(p)), n + 1)
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertIn('removed %s' % keep, r.stdout)
        self.assertFalse(os.path.lexists(keep))
        self.assertEqual((rb(p), p.exe(), p.config()), (g.bin, g.bin, g.h1))

    def test_control_a_down_unit_s_byte_equal_rollback_is_removed(self):
        """R-4's control for a down unit (Opus r1 F1): config.toml.pre-image byte-equal to config.toml, the unit enabled
        and failed: nothing runs, so the step's own start runs config.toml: the rollback is removed, said so, and the
        step goes on; v0.12.0 runs."""
        g, p = forward(self)
        g.put(p.rpath('config.toml.pre-image'), g.pre)
        p.set_unit(active=False, failed=True)
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertIn('removed %s' % p.rpath('config.toml.pre-image'), r.stdout)
        self.assertFalse(os.path.lexists(p.rpath('config.toml.pre-image')))
        self.assertEqual((rb(p), p.exe()), (g.bin, g.bin))

    def test_a_byte_equal_rollback_stays_when_a_later_check_refuses(self):
        """R-4's order (a builder's choice, Opus r1 F5): a byte-equal config.toml.pre-image (runscaler started after
        config.toml's install) is removed only once every other check passed: with no download (a later check) the step
        refuses with every file of the home as it was, the rollback too. The mutant (the removal above the download
        check) removes it."""
        g, p = forward(self)
        g.put(p.rpath('config.toml.pre-image'), g.pre)
        os.remove(os.path.join(p.build, 'dl', 'runner-linux-amd64.tar.gz'))
        before = files(p)
        r = step(p)
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        self.assertIn(URL % PINNED, r.stdout)
        self.assertEqual(files(p), before)
        self.assertTrue(os.path.lexists(p.rpath('config.toml.pre-image')))

    def test_r_4_on_the_way_back(self):
        """R-4 on the way back (Opus r3 F4, r1 F5): on v0.12.0, an image `up`, then its `back` (config.toml.pre-image
        stays, byte-equal to config.toml, and runscaler restarted on it), then `runscaler 0.9.5`: the rollback is
        removed, said so, exit 0, v0.9.5 runs config.toml."""
        p, wb, pin = on_pinned(self)
        p.curl['served'] = [V2]           # the registry serves the image the pool runs (the rollback's): back needs it
        up_record(p, UPV, UPNEW)
        r = p.pool('up', UPV)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        r = p.pool('back')
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        keep = p.rpath('config.toml.pre-image')
        self.assertEqual(sha256_file(keep), sha256_file(p.rpath('config.toml')))
        cfg = p.config()
        r = step(p, WAYBACK)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertIn('removed %s' % keep, r.stdout)
        self.assertFalse(os.path.lexists(keep))
        self.assertEqual((rb(p), p.exe(), p.config()), (wb, wb, cfg))
        starts(self, p)


@needs_container
class UpAfterACut(unittest.TestCase):
    """R-1's last sentence (Codex r1 F3, Opus r1 F3): a person's `up` that refuses a config.toml installed after
    runscaler started names the line that finishes that pending config, in both of its branches (another image; the
    running version): `pool-image.sh runscaler` (no release open: the step cut before its restart), or `pool-image.sh
    back` (a release open: its back cut before its restart). Nothing changed, and no document outside this repository
    (49a2004 named docs/runners.md section 3b, or nothing). Each control: that line, then the same up passes."""

    def refuses(self, p, version, names):
        before, b0 = files(p), binary(p)
        r = p.pool('up', version)
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        fail = [l for l in r.stdout.splitlines() if l.startswith('FAIL ')]
        self.assertEqual(len(fail), 1, fail)
        self.assertRegex(fail[0], LINE % re.escape(names), 'the line to run (not a cause it names), and no version after it '
                         '(review r2, Opus F2: the forward cut renamed v0.12.0, so the bare line, not the way back\'s)')
        self.assertNotIn('pool-image.sh runscaler %s' % WAYBACK, fail[0], 'v0.12.0 renamed into place: one line (the '
                         'control of PendingLines\' cut before that rename, review r1 of H2c, opus F3)')
        self.assertNotIn('docs/', fail[0])
        self.assertEqual((files(p), binary(p)), (before, b0))

    def test_an_up_after_a_cut_names_the_line_that_finishes_it(self):
        for case in ('another image', 'the running version', 'the running version, a release open'):
            with self.subTest(case):
                if case == 'the running version, a release open':
                    g, p, keep = cut_back(self)
                    fix = 'pool-image.sh back'
                else:
                    g, p = cut_step(self)
                    fix = 'pool-image.sh runscaler'
                up_record(p, UPOLDV, UPOLD)
                version = UPV if case == 'another image' else UPOLDV
                n = len(restarts(p))
                self.refuses(p, version, fix)
                self.assertEqual(len(restarts(p)), n)
                r = step(p) if fix == 'pool-image.sh runscaler' else p.pool('back')
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                r = p.pool('up', version)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertIn('POOL IMAGE DONE (up)', r.stdout)


# a FAIL line names LINE as the line to run: `run LINE`, and no version follows it (`pool-image.sh runscaler` is not
# `pool-image.sh runscaler 0.9.5`)
LINE = r'(?i)\brun %s(?![0-9.]| [0-9])'


def pending(test, p, start=None):
    """config.toml, just installed by a bare 03 real, is pending: runscaler started before it (at START, by default 5 s
    before its install), as a real clock gives (the fake clock ran each start ahead of every real mtime: Opus r2's
    probeC)."""
    m = int(os.stat(p.rpath('config.toml')).st_mtime)
    p.set_unit(start=m - 5 if start is None else start, pid=p.unit_now()['pid'])
    test.assertLessEqual(p.unit_now()['start'], m, 'pending')


def ran_it(test, p):
    """runscaler restarted on config.toml after its install (hzlib's `restart`: a reboot's, or systemd's own), as a real
    clock gives, pending()'s other side: the fake clock, which gives that start, moved on past config.toml's REAL mtime
    first. (fake_clock runs ahead of the real clock only by its own seconds, so a bare 03 real that many real seconds
    after the rig was made read as never run: review r1 of H2c, opus F5.)"""
    m = int(os.stat(p.rpath('config.toml')).st_mtime)
    p.clock(now=max(p.clock(), m + 1))
    p.act('restart')
    test.assertGreater(p.unit_now()['start'], m, 'runscaler ran it')


def names_line(test, r, line):
    """R refused (exit 1), with ONE FAIL line, which names LINE as the line to run (not a cause it names)."""
    test.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
    fail = [l for l in r.stdout.splitlines() if l.startswith('FAIL ')]
    test.assertEqual(len(fail), 1, fail)
    test.assertRegex(fail[0], LINE % re.escape(line), 'the line to run')
    test.assertIn('nothing', fail[0])


@needs_container
class PendingLines(unittest.TestCase):
    """Review r2's folds of up's pending refusals (a config.toml installed after runscaler started, in up's two branches):
    each names a line that, run in that refusal's own state, ends with exit 0 and clears it, and the same `up` passes
    after it. Opus F2: on a host whose ~/bin/runner is v0.9.5 (the way back) the step's line names that version
    (`pool-image.sh runscaler 0.9.5`: the bare line would put v0.12.0 back); UpAfterACut's forward cut (v0.12.0 renamed)
    keeps the bare line (the control). Opus F1: after a release a `back` closed (its rollback names config.toml's
    image) and a bare `03 real` of new numbers, up's third and fourth refusals named `pool-image.sh back`, which then
    refused (the numbers): it is no open release, so the line is the step's; and an OPEN release whose pending
    config.toml changed in more than the image (a bare 03 real of new numbers after an up cut before its restart):
    `back`, which puts the rollback back over a config.toml runscaler never ran (its control: one runscaler ran,
    refused). Nothing changes at a refusal. Each pair a cell says runs after its line, the INSTALLED runner-start's
    guard starts (test_render.starts; review r1 of H2c, opus F4), and "runscaler ran it" is a start after config.toml's
    real install (ran_it; opus F5)."""

    def refuses(self, p, version, line):
        before, b0, n = files(p), binary(p), len(restarts(p))
        r = p.pool('up', version)
        names_line(self, r, line)
        self.assertEqual((files(p), binary(p), len(restarts(p))), (before, b0, n))
        return r

    def test_a_way_back_host_s_pending_config_names_the_step_with_v0_9_5(self):
        """Opus F2 (its probeC): on v0.12.0, the way back (`runscaler 0.9.5`: v0.9.5 runs), then a change of pool.env's
        numbers and a bare `03 real` (pending); `up` to another image and `up` of the running version each refuse
        naming `pool-image.sh runscaler 0.9.5`; that line keeps v0.9.5 (and starts it on config.toml), and the same
        up then passes on v0.9.5. 8407d35 named the bare line, which installs v0.12.0 again."""
        for case in ('another image', 'the running version'):
            with self.subTest(case):
                p, wb, pin = on_pinned(self)
                r = step(p, WAYBACK)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                p.pool_env(CONCURRENT=3, MAX=2)
                r = p.s03('real')
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                pending(self, p)
                p.curl['served'] = [V2]
                up_record(p, V2V, V2)
                up_record(p, UPV, UPNEW)
                version = UPV if case == 'another image' else V2V
                self.refuses(p, version, 'pool-image.sh runscaler %s' % WAYBACK)
                r = step(p, WAYBACK)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertEqual((rb(p), p.exe()), (wb, wb))
                starts(self, p)   # the pair it claims runs, by the INSTALLED guard (review r1 of H2c, opus F4)
                r = p.pool('up', version)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertEqual((rb(p), p.exe()), (wb, wb))

    def test_a_forward_step_cut_before_its_binary_rename_names_both_lines(self):
        """Review r1 of H2c, opus F3: the forward step cut between its two renames (test_step_resume's boundary
        `mv-done:config.toml`: config.toml this release's render, pending; ~/bin/runner still v0.9.5, as on a host that
        took the way back); `up` to another image and `up` of the running version each refuse, nothing changed, naming
        BOTH lines, each with its case: `pool-image.sh runscaler 0.9.5` (a host that took the way back) and
        `pool-image.sh runscaler` (a step to v0.12.0 a cut stopped before v0.12.0 replaced the binary). Each line, run in
        that state, ends with exit 0, its pair starts (the INSTALLED guard), and the same up passes; the bare one
        finishes the forward step (v0.12.0 runs). Nothing on disk tells the two hosts apart: a ~/bin/runner.new is left
        only by a cut at which 03's EXIT trap does not run (a SIGKILL). 8b917c7 named the way back's line only, which
        turned the forward step into the way back. UpAfterACut (the cut after that rename) names one line."""
        for case in ('another image', 'the running version'):
            for line in ('pool-image.sh runscaler', 'pool-image.sh runscaler %s' % WAYBACK):
                with self.subTest(case=case, line=line):
                    g, p = cut_step(self, at='mv-done:config.toml')
                    self.assertEqual(rb(p), g.wb, 'the cut left v0.9.5 installed (the binary not renamed yet)')
                    up_record(p, UPOLDV, UPOLD)
                    version = UPV if case == 'another image' else UPOLDV
                    r = self.refuses(p, version, 'pool-image.sh runscaler')
                    fail = [l for l in r.stdout.splitlines() if l.startswith('FAIL ')][0]
                    self.assertRegex(fail, (LINE % re.escape('pool-image.sh runscaler %s' % WAYBACK))
                                     + r' \(on a host that took the way back\)')
                    self.assertRegex(fail, (LINE % re.escape('pool-image.sh runscaler'))
                                     + r' \(to finish a step to v0\.12\.0 that a cut stopped before v0\.12\.0 replaced '
                                       r'the binary\)')
                    r = step(p, *line.split()[2:])
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                    want = g.wb if line.endswith(WAYBACK) else g.bin
                    self.assertEqual((rb(p), p.exe()), (want, want))
                    starts(self, p)
                    r = p.pool('up', version)
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                    self.assertEqual((rb(p), p.exe()), (want, want))

    def test_a_closed_release_s_pending_config_names_the_step(self):
        """Opus F1, up's third and fourth refusals: an `up`, its `back`, a change of pool.env's numbers and a bare `03
        real` (pending), then `up` of the running version: with the unit active (the rollback is older than the
        process: 8407d35's third refusal) and with it down (8407d35's fourth): the rollback names config.toml's image,
        a release a back closed, so the line is the step's (v0.9.5 here, forward()'s); run, it removes that rollback
        and starts runscaler on config.toml, and the up then passes. 8407d35 named `pool-image.sh back`, which refused
        (the numbers)."""
        for unit in ('active', 'down'):
            with self.subTest(unit=unit):
                g, p = forward(self)
                for args in (('up', UPV), ('back',)):
                    r = p.pool(*args)
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                k = int(os.stat(p.rpath('config.toml.pre-image')).st_mtime)
                while int(time.time()) <= k + 1:     # the real clock past the rollback's second and the next (a state)
                    time.sleep(0.05)
                p.pool_env(CONCURRENT=3, MAX=2)
                r = p.s03('real')
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                pending(self, p, start=k + 1)        # back's restart: after the rollback was kept, before this install
                if unit == 'down':
                    p.set_unit(active=False, failed=True)
                up_record(p, UPOLDV, UPOLD)
                self.refuses(p, UPOLDV, 'pool-image.sh runscaler %s' % WAYBACK)
                r = step(p, WAYBACK)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertFalse(os.path.lexists(p.rpath('config.toml.pre-image')))
                starts(self, p)
                r = p.pool('up', UPOLDV)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)

    def test_an_open_release_s_pending_config_changed_in_more_than_the_image_names_back(self):
        """Opus F1, up's fourth refusal on an OPEN release: an `up` cut in its idle wait (config.toml.pre-image kept,
        config.toml the new image, runscaler not restarted), then a change of pool.env's numbers and a bare `03 real`
        (config.toml the new image with the new numbers: never run); the same `up` refuses naming `pool-image.sh back`;
        back puts the rollback back over that config.toml (runscaler never ran it) and says so; once pool.env holds the
        numbers the pool runs again, the up passes. The control: runscaler restarted on that config.toml (it ran): back
        refuses ("a rollback would undo that too"), nothing changed; and when its unit stopped since, the up's line is
        the start of the unit, after which the same up passes. 8407d35's text named back only "once config.toml differs
        from the rollback in the image alone", and back refused."""
        for case in ('never ran', 'ran', 'ran, the unit down'):
            with self.subTest(case):
                g, p = forward(self)
                p.hooks(('healthz-read', 'kill'))
                p.write(p.path('logs', 'runner.log'), '')
                p.unattended('up', UPV, prefix=())
                self.assertTrue([e for e in p.events() if e.startswith('kill ')], 'the cut ran')
                p.hooks()
                keep = p.rpath('config.toml.pre-image')
                self.assertEqual(p.images(), [ref(UPNEW)] * 2)
                self.assertEqual(p.images('config.toml.pre-image'), [ref(UPOLD)] * 2)
                p.pool_env(CONCURRENT=3, MAX=2)
                r = p.s03('real')
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertEqual(p.images(), [ref(UPNEW)] * 2)
                if case == 'never ran':
                    self.assertLessEqual(p.unit_now()['start'], int(os.stat(p.rpath('config.toml')).st_mtime))
                    self.refuses(p, UPV, 'pool-image.sh back')
                    r = p.pool('back')
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                    self.assertIn('runscaler never ran it', r.stdout)
                    self.assertEqual(sha256_file(p.rpath('config.toml')), sha256_file(keep))
                    starts(self, p)   # the rollback (no log-file line) on v0.9.5: BACK'S PAIR GUARD's pair (opus F4)
                    p.pool_env()
                    r = p.pool('up', UPV)
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                    self.assertIn('POOL IMAGE DONE (up)', r.stdout)
                    continue
                ran_it(self, p)
                if case == 'ran':
                    before, n = files(p), len(restarts(p))
                    r = p.pool('back')
                    self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
                    self.assertIn('a rollback would undo that too', r.stdout)
                    self.assertEqual((files(p), len(restarts(p))), (before, n))
                    continue
                p.act('fail')
                self.refuses(p, UPV, 'systemctl --user start runscaler')
                p.act('start')
                starts(self, p)
                r = p.pool('up', UPV)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertIn('POOL IMAGE DONE (up)', r.stdout)


@needs_container
class DoneAlready(unittest.TestCase):
    def test_done_already_restarts_nothing_and_still_checks(self):
        """R-5: after the step, the same line: DONE ALREADY, no stage (no runscaler call), no restart, no file changed,
        exit 0 when READY. A job a restart cut (a `Job started for unknown runner` record since config.toml's install,
        a cut before the first run's scan) is named; a pool that is not READY exits 1. Each case on a rig and a first
        step of its own (Opus r1 F6: no case reads what another one left)."""
        for case in ('ready', 'a cut job', 'not ready'):
            with self.subTest(case):
                g, p = forward(self)
                r = step(p)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                n = len(restarts(p))
                if case == 'a cut job':
                    with open(p.rpath('runner.log'), 'a') as f:
                        f.write('%s WARN linux-ci-main: Job started for unknown runner runnerName=runner-cut01\n'
                                % time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()))
                if case == 'not ready':
                    p.curl['healthz'] = healthz(**{'linux-ci-main': {'ready': False}})
                before = files(p)
                r = step(p)
                self.assertIn('DONE ALREADY', r.stdout)
                self.assertEqual(r.returncode, 1 if case == 'not ready' else 0, r.stdout[-4000:] + r.stderr)
                self.assertEqual(files(p), before)
                self.assertEqual((p.calls('runner'), len(restarts(p))), ([], n))
                if case == 'a cut job':
                    self.assertRegex(r.stdout, r'WARN a restart since this config was installed .*runner-cut01')
                if case == 'not ready':
                    self.assertIn('not READY', r.stdout)

    def test_a_config_installed_after_runscaler_started_is_never_done_already(self):
        """R-1 and R-5 (a builder's choice, Opus r1 F5 and its ProbePendingOnPinned): on the pinned host (v0.12.0 runs,
        ~/bin/runner v0.12.0), a bare `03 real` installs config.toml again after runscaler started: the step is not
        DONE ALREADY: its stage (rule bytes: config.toml is its render, not installed again) and ONE restart, exit 0, so
        that config goes live with this restart. The mutant (DONE ALREADY with no started_after) restarts nothing."""
        p, wb, pin = on_pinned(self)
        r = p.s03('real')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertGreaterEqual(int(os.stat(p.rpath('config.toml')).st_mtime), p.unit_now()['start'], 'pending')
        cfg = ino(p, 'config.toml')
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertNotIn('DONE ALREADY', r.stdout)
        self.assertIn('== 03-runscaler.sh stage %s bytes' % PINNED, r.stdout)
        self.assertEqual(ino(p, 'config.toml'), cfg)
        self.assertEqual(restarts(p), ['--user restart runscaler'])
        self.assertEqual(p.exe(), pin)
        self.assertGreater(p.unit_now()['start'], int(os.stat(p.rpath('config.toml')).st_mtime))


@needs_container
class Refusals(unittest.TestCase):
    def test_each_precondition_refuses_naming_its_fix_and_changes_nothing(self):
        """(a): each refuses with exit 1 before any change (every file of the home, ~/bin/runner's inode too), runs no
        runscaler and restarts nothing, and its line names its fix."""
        def append(path, data):
            with open(path, 'ab') as f:
                f.write(data)
        cases = (('a window journal', lambda g, p: p.write(os.path.join(Pool.STATE, 'window'), 'window 1-1\n', 0o600),
                  (), 'runner-updater pass'),
                 ('a pinned file changed', lambda g, p: append(os.path.join(p.build, 'bin', 'pool-ready'), b'#\n'),
                  (), 'Install step 3'),
                 ('a version this release does not know', None, ('0.10.0',), 'v%s' % WAYBACK),
                 ('no download', lambda g, p: os.remove(os.path.join(p.build, 'dl', 'runner-linux-amd64.tar.gz')),
                  (), URL % PINNED),
                 ('a download of other bytes',
                  lambda g, p: append(os.path.join(p.build, 'dl', 'runner-linux-amd64.tar.gz'), b'x'),
                  (), URL % PINNED),
                 ('no way-back download', lambda g, p: os.remove(os.path.join(p.build, 'dl', WBDL)), (WAYBACK,),
                  URL % WAYBACK),
                 ('a stop in progress', lambda g, p: p.set_unit(drain_until=p.clock() + 600), (), 'run this again'))
        for why, plant, args, says in cases:
            with self.subTest(why):
                g, p = forward(self)
                if plant:
                    plant(g, p)
                before, b0 = files(p), binary(p)
                r = step(p, *args)
                self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
                self.assertIn(says, r.stdout)
                self.assertIn('nothing changed', r.stdout)
                self.assertEqual((files(p), binary(p)), (before, b0))
                self.assertEqual((p.calls('runner'), restarts(p)), ([], []))

    def test_usage(self):
        p = Pool(self)
        for args in (('runscaler', 'x'), ('runscaler', PINNED, 'x'), ('runscaler', '0.12')):
            with self.subTest(args=args):
                r = p.pool(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn('runscaler [VERSION]', r.stdout)


def state(p, on=False, fam=None):
    """The updater's state.json: ON or OFF, hz-docker's family FAM (none: no family yet)."""
    os.makedirs(Pool.STATE, mode=0o700, exist_ok=True)
    p.write(STATE, json.dumps({'format': 1, 'on': on, 'families': {'hz-docker': fam} if fam else {}}) + '\n', 0o600)


def held(p):
    """hz-docker's held STOPs in the updater's state."""
    st = json.loads(p.read(STATE))
    return [s['stop'] for s in st.get('families', {}).get('hz-docker', {}).get('stops', [])]


@needs_container
class UpdaterAfterTheStep(unittest.TestCase):
    """M-6 MEASURED: this release's updater (3c-1: it switches nothing, so it has no candidate) after the step and after
    the way back, OFF then ON, a pass DURING the step's restart (the stop job's drain: the hook at its start runs
    `runner-updater pass`), and a pass that starts before the step and ends after it. The fix log has the measured
    lines. Each subtest on a rig of its own (Opus r1 F6)."""

    def on(self, p, on):
        st = json.loads(p.read(STATE))
        st['on'] = on
        p.write(STATE, json.dumps(st) + '\n', 0o600)

    def test_a_pass_after_the_step_and_after_the_way_back_holds_no_hand_change(self):
        """A pass during the restart's drain holds STOP POOL DOWN (no runscaler runs then); the next pass (OFF) clears
        it once runscaler runs; a pass ON then runs the core (r1, keep) and holds nothing: no candidate, no rollback
        window, no STOP (no HAND CHANGE for a config whose content changed by the log-file line and comments, a binary
        changed, a restart outside a window). The same after the way back, from the pinned host."""
        for way in ('forward', 'the way back'):
            with self.subTest(way):
                if way == 'forward':
                    g, p = forward(self)
                    args = ()
                else:
                    p, wb, pin = on_pinned(self)
                    args = (WAYBACK,)
                state(p)
                p.set_unit(drain=60)
                p.hooks(('systemctl:stop-begin', 'updater-pass'))
                r = step(p, *args)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                during = p.updater_passes()[-1][1]
                self.assertIn('STOP POOL DOWN', during)
                for on in (False, True):
                    self.on(p, on)
                    rr = p.updater('pass')
                    self.assertEqual(rr.returncode, 0, rr.stdout[-4000:] + rr.stderr)
                    if not on:
                        self.assertIn('STOP POOL DOWN is cleared', rr.stdout)
                    else:
                        self.assertIn('r1: ok (', rr.stdout)
                    self.assertNotIn('HAND CHANGE', rr.stdout)
                    st = json.loads(p.read(STATE))
                    fam = st.get('families', {}).get('hz-docker', {})
                    self.assertIsNone(fam.get('candidate'), st)
                    self.assertEqual([s['stop'] for s in fam.get('stops', [])], [], st)
                    self.assertIsNone(p.window())

    def test_control_a_candidate_whose_lines_are_not_config_toml_s_holds_hand_change(self):
        """Opus r1 F4 (its r3 F9 (d)): the cell above's "no HAND CHANGE" can fail. After the step, a pass ON with R1
        planted to say rollback (test_verdict.plant_r1, the real core's answer with hz-docker's verdict set): with a
        candidate whose lines are not config.toml's (UPNEW's; config.toml runs UPOLD), it holds STOP HAND CHANGE (a
        rollback would replace a file its window did not write); with no candidate (the cell above's rig, as this
        release makes it), it holds none."""
        for cand in (False, True):
            with self.subTest(candidate=cand):
                g, p = forward(self)
                r = step(p)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                lines = {MAIN: ref(UPNEW), SMALL: ref(UPNEW)}
                self.assertNotIn(ref(UPNEW), p.config())
                state(p, True, {'candidate': candidate(p.clock() - 60, lines=lines),
                                'previous': {MAIN: ref(UPOLD), SMALL: ref(UPOLD)}} if cand else None)
                plant_r1(types.SimpleNamespace(p=p, plant=lambda rel, text: p.write(os.path.join(p.build, rel), text)))
                rr = p.updater('pass')
                if cand:
                    self.assertIn('STOP HAND CHANGE', rr.stdout, rr.stdout[-4000:] + rr.stderr)
                    self.assertEqual(held(p), ['HAND CHANGE'])
                else:
                    self.assertEqual(rr.returncode, 0, rr.stdout[-4000:] + rr.stderr)
                    self.assertIn("R1 says rollback for hz-docker, but it has no candidate", rr.stdout)
                    self.assertNotIn('HAND CHANGE', rr.stdout)
                    self.assertEqual(held(p), [])
                self.assertIsNone(p.window())

    def test_a_pass_that_starts_before_the_step_and_ends_after_it(self):
        """Codex r1's M-6 row, MEASURED: the locks do not exclude it (the step takes pool-image.sh's own lock, a pass
        the updater lock), so the whole step runs inside a pass (support's runscaler-step action at the pass's Nth
        `systemctl show`, each N a plain pass reaches; OFF and ON). Each: the step ends with POOL RUNSCALER DONE, the
        pass exits 0 and holds no HAND CHANGE, no candidate and no window. Per mode, by show (review r2, Codex F2):
        shows 2 and 3 hold STOP POOL DOWN (the step's restart inside THE OUTAGE RULE's RUNS check: show 2, the process
        changes during the /healthz reads; show 3, after RUNS's last read, which only the deciding read's final PID
        check sees), and the next pass clears it (runscaler RUNS); every other show (1, 4, and ON's 5 and 6) holds
        none."""
        for on in (False, True):
            g, p = forward(self)
            state(p, on)
            p.count_shows()
            r = p.updater('pass')
            self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
            n = p.unit_now()['shows']
            self.assertGreaterEqual(n, 4, 'a pass reads the unit 4 times or more (THE OUTAGE RULE)')
            for k in range(1, n + 1):
                with self.subTest(on=on, show=k):
                    want = ['POOL DOWN'] if k in (2, 3) else []
                    g, p = forward(self)
                    state(p, on)
                    p.set_unit(drain=60)
                    p.count_shows()
                    p.hooks(('systemctl:show-%d' % k, 'runscaler-step'))
                    r = p.updater('pass')
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                    steps = p.runscaler_steps()
                    self.assertEqual(len(steps), 1, 'the step ran inside the pass')
                    self.assertEqual(steps[0][0], 0, steps[0][1][-3000:])
                    self.assertIn('POOL RUNSCALER DONE', steps[0][1])
                    self.assertNotIn('HAND CHANGE', r.stdout)
                    self.assertEqual(held(p), want, r.stdout[-3000:])
                    self.assertIsNone(json.loads(p.read(STATE)).get('families', {}).get('hz-docker', {}).get(
                        'candidate'))
                    self.assertIsNone(p.window())
                    r = p.updater('pass')
                    self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                    if want:
                        self.assertIn('STOP POOL DOWN is cleared: runscaler RUNS', r.stdout)
                    self.assertEqual(held(p), [])
                    self.assertEqual((rb(p), p.exe()), (g.bin, g.bin))

if __name__ == '__main__':
    unittest.main()
