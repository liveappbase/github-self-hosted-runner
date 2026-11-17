"""`status` shows the LATEST pass's outcome (W2, the r2 MODEL M-2 and the r3 FOLD N-1, N-4, N-6; issue #6): every pass,
of RS_USER and of RUN_USER, on EVERY exit path (OFF, a journal that stays, a REFUSE, a WAIT, DUE's line, the updater
lock held by another run), writes PASSDIR/last-pass by ONE rename of a temp file of its own (mktemp in PASSDIR, made
first when it is missing): its first line the pass's time and its outcome line, verbatim, and, when the pass printed one,
the recipe line (test_recipe_follows.py). `status` prints `last pass <age> ago (<UTC time>): <outcome>` (and
`last pass: <recipe line>` after it), or `last pass: none yet` with no file. So the line is always the latest pass's,
never an older DUE's. A person's command (on, off, retry, ...) and status write nothing there.

- M-4 (d): a wait pass, then `off` and a pass: status shows the OFF pass (red under the mutant "last-pass not written on
  the OFF path"); the control: `on` and a pass -> status shows that ON pass's line again.
- N-6 (c): an OFF pass on a home with no PASSDIR writes it; `REFUSE no facts` (runscaler's log gone) after a wait pass
  replaces the wait line; a pass that finds the updater lock held writes its line.
- N-6 (b): RUN_USER's build pass writes its own last-pass, and RUN_USER's own status shows it (never `none yet`).
- A FULL FILESYSTEM (build review r1, codex F1 / opus F1): a pass whose write of the temp file fails once that file
  exists (FULL_STUB: a symlink to /dev/full in its place, so every write there fails with ENOSPC) leaves the old
  last-pass byte for byte and no temp file, and keeps its own exit code; with no recipe line (red under the mutant "the
  old brace group": its status is the last `[ -z ... ]`, so the rename put the failed write in place) and with one. The
  control: the next pass, the write free -> the record replaced, status shows it.
- THE OTHER ENDS (build review r1, opus F2): a switch whose window journal stays open (exit 1) -> its `STOP the window
  journal ... stays open` line, never DUE's `is due for runner` line (red under the mutant "do_pass's last WSTOP exit
  as `echo; exit`"); `core could not decide (idle)` -> that line, not core_nothing's after it (red under the mutant
  "no OUTCOME=$LAST there"). The control: the same rig, neither fault -> `switched hz-docker to V`.
Every cell runs the real scripts (support.Pool, a throwaway container, the fake clock).
(Named for its CI part, test_[k-o][!u]*.py: .github/workflows/release-check.yml.)
"""
import fcntl
import json
import os
import unittest

from tests.hetzner.support import Pool, digest, needs_container, run_pool
from tests.hetzner.test_pass_switch import G
from tests.hetzner.test_recipe_follows import RECIPE, R
from tests.hetzner.test_release_due import CUR, FAM, STATE, V

PASSDIR = os.path.join(Pool.STATE, 'pass')
LAST_FILE = os.path.join(PASSDIR, 'last-pass')
NONE_YET = 'runner-updater: last pass: none yet'
WAITS_BUILD = "hz-docker is not due: it waits for root's build of runner %s" % V
FULL_LOG = 'full.log'

# mktemp, for the full-filesystem cells (full()): for THE LAST PASS's temp file only (a template that ends in
# /.last-pass.XXXXXXXX), the real mktemp, then a symlink to /dev/full in that file's place: every write there fails
# (ENOSPC, as on a full filesystem) once the temp file exists. Each one logged (its path) to logs/full.log: the evidence
# the fault was planted. Every other call: the real mktemp
FULL_STUB = r'''#!/usr/bin/python3 -I
import os, subprocess, sys
LOG = @LOG@
a = sys.argv[1:]
if any(x.endswith('/.last-pass.XXXXXXXX') for x in a):
    r = subprocess.run(['/usr/bin/mktemp'] + a, stdout=subprocess.PIPE, text=True)
    t = r.stdout.strip()
    if r.returncode == 0 and t:
        os.remove(t)
        os.symlink('/dev/full', t)
        with open(LOG, 'a') as f:
            f.write(t + '\n')
    sys.stdout.write(r.stdout)
    sys.exit(r.returncode)
os.execv('/usr/bin/mktemp', ['mktemp'] + a)
'''


def shown(t, p):
    """status's last-pass outcome line, without its `last pass <age> ago (<time>): ` head; NONE_YET with no file."""
    r = p.updater('status')
    t.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
    lines = [l for l in r.stdout.splitlines() if l.startswith('runner-updater: last pass')]
    t.assertTrue(lines, r.stdout[-3000:])
    if lines[0] == NONE_YET:
        return NONE_YET
    t.assertRegex(lines[0], r'^runner-updater: last pass \d+ (s|min|h|days) ago \(\d{4}-\d\d-\d\d \d\d:\d\d UTC\): ')
    return lines[0].split(' UTC): ', 1)[1]


@needs_container
class EveryExit(unittest.TestCase):
    def test_wait_then_off_then_on_each_pass_replaces_the_line(self):
        """M-4 (d): no file yet -> `none yet`; a pass that waits for RUN_USER's build -> that line; `off`, then a pass
        -> the OFF pass's line (not the wait line); the control: `on`, then a pass -> the wait line again. `off`, `on`
        and `retry` (a person's commands) and status leave the file byte for byte as it was."""
        g = G(self, built=False)
        self.assertEqual(shown(self, g.p), NONE_YET)
        g.go()
        self.assertTrue(shown(self, g.p).startswith(WAITS_BUILD), shown(self, g.p))
        before = g.p.read(LAST_FILE)
        for cmd in (('off',), ('retry', FAM)):
            g.p.clock(plus=600)
            r = g.p.updater(*cmd)
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
            self.assertEqual(g.p.read(LAST_FILE), before, '%s wrote the last pass' % cmd[0])
        g.p.clock(plus=600)
        g.go()
        self.assertEqual(shown(self, g.p), 'the updater is OFF: nothing to do')
        g.p.clock(plus=600)
        before = g.p.read(LAST_FILE)
        r = g.p.updater('on')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.read(LAST_FILE), before, 'on wrote the last pass')
        g.p.clock(plus=600)
        g.go()
        self.assertTrue(shown(self, g.p).startswith(WAITS_BUILD), shown(self, g.p))
        self.assertEqual([n for n in os.listdir(PASSDIR) if n.startswith('.last-pass')], [], 'a temp file stays')

    def test_an_off_pass_on_a_home_with_no_passdir_writes_it(self):
        """N-6 (c): the OFF exit comes before the pass's own `install -d PASSDIR`: the write makes it first."""
        g = G(self)
        st = json.loads(g.p.read(STATE))
        st['on'] = False
        g.put(st)
        self.assertFalse(os.path.lexists(PASSDIR))
        g.go()
        self.assertEqual(shown(self, g.p), 'the updater is OFF: nothing to do')
        self.assertEqual(oct(os.stat(PASSDIR).st_mode & 0o777), oct(0o700))

    def test_a_refusal_after_a_wait_pass_replaces_its_line(self):
        """N-6 (c): runscaler's log gone -> `REFUSE no facts`, exit 1: status shows the refusal, not the wait line."""
        g = G(self, built=False)
        g.go()
        self.assertTrue(shown(self, g.p).startswith(WAITS_BUILD))
        os.remove(g.p.rpath('runner.log'))
        g.p.clock(plus=600)
        r = g.go(rc=1)
        self.assertIn("runner-updater: REFUSE no facts: cannot read runscaler's log", r.stdout)
        self.assertTrue(shown(self, g.p).startswith("REFUSE no facts: cannot read runscaler's log"), shown(self, g.p))

    def test_a_pass_that_finds_the_lock_held_writes_its_line(self):
        """N-6 (c): another run holds the updater lock (this process, by another open of the file): the pass ends at
        once and its line is the last pass; the control: the lock free -> the pass's own outcome."""
        g = G(self, built=False)
        g.go()
        fd = os.open(os.path.join(Pool.STATE, 'lock'), os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            g.p.clock(plus=600)
            r = g.go()
            self.assertIn('another run holds the updater lock', r.stdout)
            self.assertTrue(shown(self, g.p).startswith('another run holds the updater lock'), shown(self, g.p))
        finally:
            os.close(fd)
        g.p.clock(plus=600)
        g.go()
        self.assertTrue(shown(self, g.p).startswith(WAITS_BUILD), shown(self, g.p))


def full(p, on=True):
    """From now on (ON) the last pass's temp file is full (FULL_STUB); off: the real mktemp again."""
    stub = p.path('stubs', 'mktemp')
    if on:
        p.write(stub, FULL_STUB.replace('@LOG@', repr(p.path('logs', FULL_LOG))), 0o755)
    elif os.path.lexists(stub):
        os.remove(stub)


def planted(p):
    """The temp files FULL_STUB made full (logs/full.log), in order."""
    log = p.path('logs', FULL_LOG)
    return p.read(log).splitlines() if os.path.exists(log) else []


@needs_container
class AFullFilesystem(unittest.TestCase):
    def test_a_failed_write_leaves_the_old_record_and_the_pass_s_exit_code_and_control_the_write_free(self):
        """Each row: a first pass writes a good record; the next pass's temp file is full: the record stays byte for
        byte (never a symlink, never empty), no temp file stays, the pass's own exit code (0, or 1 for a REFUSE) is
        kept, and status still shows the first pass's line. Rows: no recipe line (DUE's wait for RUN_USER's build);
        no recipe line, exit 1 (`REFUSE no facts`); a recipe line (`not newer`, then the recipe line). The control:
        the next pass with the write free replaces the record, and status shows that pass's line."""
        for row in ('no recipe line', 'no recipe line, exit 1', 'a recipe line'):
            with self.subTest(row):
                if row == 'a recipe line':
                    g = R(self, latest=CUR)
                    want = 'hz-docker is not due: release v%s is not newer than its runner %s' % (CUR, CUR)
                else:
                    g = G(self, built=False)
                    want = WAITS_BUILD
                r = g.go()
                self.assertEqual(any(l.startswith(RECIPE) for l in r.stdout.splitlines()), row == 'a recipe line',
                                 r.stdout[-3000:])
                self.assertTrue(shown(self, g.p).startswith(want), shown(self, g.p))
                before, first = g.p.read(LAST_FILE), want
                self.assertTrue(before, 'the premise: a good record')
                rc = 0
                if row.endswith('exit 1'):
                    os.remove(g.p.rpath('runner.log'))
                    want, rc = "REFUSE no facts: cannot read runscaler's log", 1
                full(g.p)
                g.p.clock(plus=600)
                r = g.go(rc=rc)                                       # the pass's own exit code, kept
                self.assertEqual(len(planted(g.p)), 1, 'the premise: the fault was planted: ' + r.stdout[-3000:])
                self.assertFalse(os.path.islink(LAST_FILE), 'the failed write was renamed over the record')
                self.assertEqual(g.p.read(LAST_FILE), before, 'the failed write changed the record')
                self.assertEqual([n for n in os.listdir(PASSDIR) if n.startswith('.last-pass')], [], 'a temp file stays')
                self.assertTrue(shown(self, g.p).startswith(first), shown(self, g.p))
                full(g.p, on=False)                                   # the control: the write free
                g.p.clock(plus=600)
                g.go(rc=rc)
                self.assertNotEqual(g.p.read(LAST_FILE), before, 'the control: the record is replaced')
                self.assertTrue(shown(self, g.p).startswith(want), shown(self, g.p))
                self.assertEqual(len(planted(g.p)), 1)


@needs_container
class TheOtherEnds(unittest.TestCase):
    def test_a_journal_that_stays_and_a_core_that_cannot_decide_and_control_the_switch(self):
        """The window's restart leaves its journal open (runner-start hangs after the stop: exit 1): status shows the
        pass's `STOP the window journal ... stays open` line, never DUE's `is due for runner` line. The core cannot
        decide (a planted idle.jq that errors: exit 1): status shows `core could not decide (idle): ...`, not the
        `the pass did nothing` line after it. The control: the same rig, neither fault -> `switched hz-docker to V`."""
        for row in ('journal stays', 'core could not decide', 'control: neither'):
            with self.subTest(row):
                g = G(self)
                rc = 1
                if row == 'journal stays':
                    g.p.hooks(('systemctl:stop-done', 'hang'))
                elif row == 'core could not decide':
                    g.p.write(os.path.join(g.p.build, 'core', 'idle.jq'), 'error("planted")\n')
                else:
                    rc = 0
                r = g.go(rc=rc)
                out = shown(self, g.p)
                self.assertNotIn('is due for runner', out)
                if row == 'journal stays':
                    self.assertIn("the next run's RECOVER ends it", r.stdout)
                    self.assertTrue(out.startswith('STOP the window journal '), out)
                    self.assertIn(' stays open ', out)
                elif row == 'core could not decide':
                    self.assertIn('runner-updater: core could not decide (idle): exit ', r.stdout)
                    self.assertTrue(out.startswith('core could not decide (idle): exit '), out)
                else:
                    self.assertTrue(out.startswith('switched hz-docker to %s: ' % V), out)


@needs_container
class RunUser(unittest.TestCase):
    def test_run_user_s_build_pass_writes_its_own_and_its_status_shows_it(self):
        """N-6 (b): RUN_USER's pass builds V (02-d1.sh's substitute): its own status shows `built runner V` as its last
        pass, not `none yet`. The control: before that pass, `none yet`."""
        p, _ = run_pool(self, V, digest=digest(39))
        self.assertEqual(shown(self, p), NONE_YET)
        p.clock(plus=600)
        r = p.updater('pass')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('runner-updater: pass: built runner %s' % V, r.stdout)
        self.assertEqual(shown(self, p), 'built runner %s' % V)


if __name__ == '__main__':
    unittest.main()
