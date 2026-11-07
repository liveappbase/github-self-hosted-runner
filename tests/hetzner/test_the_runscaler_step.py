"""`pool-image.sh runscaler [VERSION]`, THE ONE DOOR FOR THE BINARY (runscaler 0.12 bump, Hetzner slice H2b-1; the H2
plan's M-3 with its r3 FOLD R-1 to R-6, and M-6). It changes ~/bin/runner, and only it (03's ONE DOOR: test_one_door):

- VERSION: 03's PINNED (the default, v0.12.0) or its WAYBACK (v0.9.5); any other refuses. Under the ONE RUN AT A TIME
  lock. (a) Each precondition refuses with nothing changed and names its fix: pool-image.sh's PINS, VERSION, no
  updater window journal, no open image release (a config.toml.pre-image byte-equal to config.toml is one a `back`
  closed: removed first, and said so; any other refuses, "accept, or back": R-4), the unit enabled, VERSION's download
  in ~/build/dl by its sha256 (03's dl_of: the pinned one Install step 4's file, the way back's its own name). The
  unit: active and started after config.toml's install (runscaler runs config.toml), or active with config.toml
  installed after its start (a pending config: only this step's own render, byte for byte, goes on: R-1), or enabled
  and down (failed, inactive, a crash loop: R-3). The INSTALLED binary may be unknown: this step is the fix.
- (b) DONE ALREADY (R-5): the running process and ~/bin/runner are VERSION's and config.toml has the log-file line: no
  stage and no restart, but READY, the running binary and the restart-cut scan; exit 0 only when READY.
- (c)+(d) `03-runscaler.sh stage VERSION content|bytes`: the render (config.toml's image) is compared with config.toml
  BEFORE anything is installed (THE CONFIG COMPARE, image lines as content; or byte for byte); then this release's
  runner-start, pool-ready, validate-class and unit (R-2), VERSION's runner into ~/bin/runner.new (both sha256s), and
  `runner-start validate --staged`: the strict control, the version line and the validate run THE STAGED BINARY; PASS
  only; then config.toml (only when it differs), THEN the rename of runner.new over ~/bin/runner.
- (e) the restart at idle (none when the unit is down); both shortcuts need THE RUNNING BINARY (R-6: the process's
  /proc/<MainPID>/exe, the cells' fake process table) to be VERSION's too; READY; the running binary VERSION's; the
  restart-cut scan. (f) NEXT: the way back's lines, or the way forward's.
- RESUME: a SIGKILL at each boundary of (c)-(e), the uncut run's own install, mv, systemctl and /healthz events, leaves
  a pair the INSTALLED runner-start's guard starts (test_render.guard), and the same line again finishes it.
- M-6: the updater's pass (this release's, ON and OFF) after the step and after the way back, and a pass DURING the
  step's restart (its drain): what it holds, measured.
Every Pool cell runs the real scripts (support.Pool; a fake clock, so no wait is real) in a throwaway container. The
pinned runscaler is Pool's substitute; the way-back one test_render.way_back's (other bytes), with its own download.
The host before the step: Install step 3 done, so its ~/bin/runner-start is the release before's (no selector:
old_wrapper). (Named for its CI part, test_[!a-qr][!np]*.py: .github/workflows/release-check.yml.)
"""
import hashlib
import io
import json
import os
import re
import tarfile
import time
import unittest

from tests.hetzner.support import REPO, Pool, digest, healthz, needs_container, sha256_file
from tests.hetzner.test_one_door import binary, files, unknown
from tests.hetzner.test_render import WAYBACK_MARK, Before, assignment, fixture, function, older, starts, way_back

S03 = os.path.join(REPO, 'linux-docker', 'setup', '03-runscaler.sh')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
RR = os.path.join(REPO, 'linux-docker', 'setup', 'runner-release.sh')
README = os.path.join(REPO, 'linux-docker', 'README.md')
PINNED, WAYBACK = '0.12.0', '0.9.5'
V2 = digest(12)
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
                 'cut')
        at = [sec.find(w) for w in order]
        self.assertNotIn(-1, at, list(zip(order, at)))
        self.assertEqual(at, sorted(at), list(zip(order, at)))
        self.assertIn('a config.toml that a bare `03-runscaler.sh real` installed and runscaler has not started yet '
                      'goes live with this restart', sec)
        for w in ('Install step 3 for both users', 'Install step 4', 'at a quiet time', 'DONE ALREADY',
                  'accept or back', 'enable'):
            self.assertIn(w, sec)

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
        """M-6, as measured (UpdaterAfterTheStep): no candidate and no rollback; a pass during the step's restart holds
        STOP POOL DOWN, and the next pass clears it once runscaler runs."""
        sec = self.section()
        for w in ('no candidate', 'rolls nothing back', '`STOP POOL DOWN`', 'the next pass clears it'):
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
        """(c): a ~/bin/runner.new a SIGKILL left (other bytes) is gone after the next run of the step, a refusal at its
        compare too (the trap: 03 names it from its start), and a run that goes on installs VERSION's own runner."""
        for how in ('a refusal', 'a run that goes on'):
            with self.subTest(how):
                g, p = forward(self)
                new = os.path.join(p.HOME, 'bin', 'runner.new')
                p.write(new, '#!/bin/sh\nexit 99\n', 0o755)
                if how == 'a refusal':
                    g.label('linux-ci-x')
                r = step(p)
                self.assertEqual(r.returncode, 1 if how == 'a refusal' else 0, r.stdout[-4000:] + r.stderr)
                self.assertFalse(os.path.lexists(new))
                self.assertEqual(rb(p), g.wb if how == 'a refusal' else g.bin)

    def test_the_stage_installs_only_the_pinned_files(self):
        """R-2: `03 stage` itself (a person may run it by hand, past pool-image.sh's PINS) refuses a ~/build file that is
        not its PIN before it installs that file: runner-start is this release's, pool-ready not, so 03 stops at
        pool-ready, config.toml and ~/bin/runner as they were, no runner.new."""
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
class Resume(unittest.TestCase):
    def test_a_sigkill_at_each_boundary_leaves_a_pair_that_starts_and_the_same_line_finishes_it(self):
        """M-3 (b)'s cut cell (R-1): the boundaries are the uncut run's own events (each install and mv destination,
        before and after; the restart, before and after; the idle wait's first /healthz read). At each, a SIGKILL of
        the step's process group (no trap runs) leaves a pair the INSTALLED runner-start's guard starts (whichever
        runner-start is installed by then), and the same line again ends with v0.12.0 running the render, no
        runner.new left, at most one restart. The mutant (the binary renamed before config.toml) leaves the pinned
        runscaler with the config with no line: the guard refuses."""
        g, p = forward(self)
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        at = []
        for e in p.events():
            m = re.fullmatch(r'(install|mv) (\S+)', e)
            if m and '%s:%s' % m.groups() not in at:
                at += ['%s:%s' % m.groups(), '%s-done:%s' % m.groups()]
        at += ['healthz-read', 'systemctl:restart-begin', 'systemctl:restart-done']
        for name in ('install:runner.new', 'mv:config.toml', 'mv:runner'):
            self.assertIn(name, at)
        for a in at:
            with self.subTest(a):
                g, p = forward(self)
                p.hooks((a, 'kill'))
                r = step(p)
                self.assertTrue([e for e in p.events() if e.startswith('kill ')], 'the cut ran')
                self.assertNotEqual(r.returncode, 0)
                starts(self, p)
                p.hooks()
                n = len(restarts(p))
                r = step(p)
                self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
                self.assertEqual((rb(p), p.exe(), p.config()), (g.bin, g.bin, g.h1))
                self.assertFalse(os.path.lexists(os.path.join(p.HOME, 'bin', 'runner.new')))
                self.assertLessEqual(len(restarts(p)) - n, 1)

    def test_a_config_a_bare_03_real_installed_goes_live_with_this_restart(self):
        """R-1: config.toml installed after runscaler started, and byte for byte this step's render (a bare `03 real`
        after a pool.env change, or this step cut before its restart): the step goes on, installs no config (its
        sha and mtime as the bare 03 left them), and its one restart runs it with the pinned binary."""
        g, p = forward(self)
        r = p.s03('real')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertGreaterEqual(int(os.stat(p.rpath('config.toml')).st_mtime), p.unit_now()['start'], 'pending')
        cfg = ino(p, 'config.toml')
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertEqual(ino(p, 'config.toml'), cfg)
        self.assertEqual(restarts(p), ['--user restart runscaler'])
        self.assertEqual(p.exe(), g.bin)

    def test_control_another_pending_config_refuses_and_changes_nothing(self):
        """R-1's other side: a pending config.toml that is NOT this step's render byte for byte (a hand edit after that
        bare 03 real: a value, or a comment alone, which THE CONFIG COMPARE would let pass): refused at the stage's
        compare, nothing installed, nothing restarted."""
        for why, edit in (('a value', lambda t: t.replace('max-runners = 3\n', 'max-runners = 2\n', 1)),
                          ('a comment alone', older)):
            with self.subTest(why):
                g, p = forward(self)
                r = p.s03('real')
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                p.write(p.rpath('config.toml'), edit(p.config()), 0o600)
                before, b0 = files(p), binary(p)
                r = step(p)
                self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
                self.assertIn('FAIL config.toml was installed after runscaler started, and it is not this step\'s '
                              'render', r.stdout)
                self.assertTrue(left(p, before))
                self.assertEqual(binary(p), b0)
                self.assertEqual((p.calls('runner'), restarts(p)), ([], []))


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
        """R-4's other side: any other config.toml.pre-image is an open image release: refused ("accept, or back"),
        nothing changed."""
        g, p = forward(self)
        g.put(p.rpath('config.toml.pre-image'), older(g.pre))
        before = files(p)
        r = step(p)
        self.assertEqual(r.returncode, 1, r.stdout[-4000:] + r.stderr)
        self.assertIn('pool-image.sh accept', r.stdout)
        self.assertIn('pool-image.sh back', r.stdout)
        self.assertEqual(files(p), before)
        self.assertEqual((p.calls('runner'), restarts(p)), ([], []))


@needs_container
class DoneAlready(unittest.TestCase):
    def test_done_already_restarts_nothing_and_still_checks(self):
        """R-5: after the step, the same line: DONE ALREADY, no stage (no runscaler call), no restart, no file changed,
        exit 0 when READY. A job a restart cut (a `Job started for unknown runner` record since config.toml's install,
        a cut before the first run's scan) is named; a pool that is not READY exits 1."""
        g, p = forward(self)
        r = step(p)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        n = len(restarts(p))
        for case in ('ready', 'a cut job', 'not ready'):
            with self.subTest(case):
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


@needs_container
class UpdaterAfterTheStep(unittest.TestCase):
    """M-6 MEASURED: this release's updater (3c-1: it switches nothing, so it has no candidate) after the step and after
    the way back, OFF then ON, and a pass DURING the step's restart (the stop job's drain: the hook at its start runs
    `runner-updater pass`). The build log has the measured lines."""

    def on(self, p, on):
        st = json.loads(p.read(STATE))
        st['on'] = on
        p.write(STATE, json.dumps(st) + '\n', 0o600)

    def test_a_pass_after_the_step_and_after_the_way_back_holds_no_hand_change(self):
        """A pass during the restart's drain holds STOP POOL DOWN (no runscaler runs then); the next pass (OFF) clears
        it once runscaler runs; a pass ON then runs the core (r1, keep) and holds nothing: no candidate, no rollback
        window, no STOP (no HAND CHANGE for a config whose content changed by the log-file line and comments, a binary
        changed, a restart outside a window). The same after the way back."""
        g, p = forward(self)
        os.makedirs(Pool.STATE, mode=0o700, exist_ok=True)
        p.write(STATE, json.dumps({'format': 1, 'on': False, 'families': {}}) + '\n', 0o600)
        p.set_unit(drain=60)
        for args in ((), (WAYBACK,)):
            with self.subTest(args=args):
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


if __name__ == '__main__':
    unittest.main()
