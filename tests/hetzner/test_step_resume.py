"""THE RUNSCALER STEP's RESUME cells (`pool-image.sh runscaler [VERSION]`; runscaler 0.12 bump, Hetzner slice H2b-1;
the H2 plan's M-3 (b) with its r3 FOLD R-1): a SIGKILL at each boundary of the step's (c)-(e), the uncut run's own
install, mv, systemctl and /healthz events, forward from a config before H1, forward from H1's config, and on the way
back, leaves a pair the INSTALLED runner-start's guard starts (test_render.guard); the same line again finishes it, also
after a reboot (runscaler started again on the pair on disk) for each pair a cut leaves on disk. R-1: a config a bare
`03 real` installed (this step's render byte for byte) goes live with the step's one restart; any other pending config
refuses at the stage's compare. The class moved here unchanged from test_the_runscaler_step.py (S2b-3c-2 B3: that
module alone took 12.5 min of its CI part, run 42528284026), and uses that module's helpers. Every Pool cell runs the
real scripts (support.Pool; a fake clock) in a throwaway container, each subtest on a rig of its own. (Named for its CI
part, test_[sv-z]*.py: .github/workflows/release-check.yml.)
"""
import os
import re
import unittest

from tests.hetzner.support import needs_container
from tests.hetzner.test_one_door import binary, files
from tests.hetzner.test_render import older, starts
from tests.hetzner.test_the_runscaler_step import (disk, forward, ino, left, left_new, on_disk, rb, reboot, restarts,
                                                   rig, step)


@needs_container
class Resume(unittest.TestCase):
    """M-3 (b)'s cut cells (R-1; Opus r1 F5, Codex's coverage table): the boundaries are the uncut run's own events (each
    install and mv destination, before and after; the restart, before and after; the idle wait's first /healthz read),
    for each of WAYS. At each, a SIGKILL of the step's process group (no trap runs) leaves a pair the INSTALLED
    runner-start's guard starts (whichever runner-start is installed by then), and the same line again ends with
    VERSION's runscaler running the config it ends with, no runner.new and no DEST.new left, at most one restart. For
    each pair a cut leaves on disk (on_disk: the first boundary that leaves it), once more with a reboot before the
    rerun: runscaler started on that pair (its guard starts it), then the same line finishes. The mutant (the binary
    renamed before config.toml) leaves the pinned runscaler with the config with no line: the guard refuses. ONE CUT
    PER STATE (review r2, Opus F5): the uncut run marks the state at each boundary (support.state_key), and only the
    first boundary of each state is cut (a later one with that state leaves the same pair: about half of them, the
    install of a folder that is there, a rename right after its check); a boundary after a write no hook sees keeps a
    cut of its own (the control: `mv:config.toml`, after the copy into config.toml.tmp). Fewer cuts than boundaries,
    and fewer pairs than cuts."""

    def cut(self, way, at, boot):
        p, args, want, cfg = rig(self, way)
        before = disk(p)
        p.hooks((at, 'kill'))
        r = step(p, *args)
        self.assertTrue([e for e in p.events() if e.startswith('kill ')], 'the cut ran')
        self.assertNotEqual(r.returncode, 0)
        starts(self, p)
        p.hooks()
        pair = on_disk(p, before, want, cfg)
        if boot:
            reboot(self, p)
        n = len(restarts(p))
        r = step(p, *args)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertEqual((rb(p), p.exe(), p.config()), (want, want, cfg))
        self.assertFalse(os.path.lexists(os.path.join(p.HOME, 'bin', 'runner.new')))
        self.assertEqual(left_new(p), [])
        self.assertLessEqual(len(restarts(p)) - n, 1)
        return pair

    def matrix(self, way):
        p, args, want, cfg = rig(self, way)
        p.hooks(('*', 'mark'))
        r = step(p, *args)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        at, keys = [], {}
        for e in p.events():
            m = re.fullmatch(r'(install|mv) (\S+)', e)
            if m and '%s:%s' % m.groups() not in at:
                at += ['%s:%s' % m.groups(), '%s-done:%s' % m.groups()]
            m = re.fullmatch(r'mark (\S+) ([0-9a-f]{64})', e)
            if m and m.group(1) not in keys:      # the state at a boundary's FIRST event: where its kill hook fires
                keys[m.group(1)] = m.group(2)
        at += ['healthz-read', 'systemctl:restart-begin', 'systemctl:restart-done']
        for name in ('install:runner.new', 'mv:runner') + (('mv:config.toml',) if way != 'the way back' else ()):
            self.assertIn(name, at)
        # ONE CUT PER STATE (review r2, Opus F5): the uncut run's state at each boundary (support's state_key: the
        # home's files, the unit, the running binary); a boundary whose state an earlier one had leaves the same pair
        # to a SIGKILL, so only the first of each state is cut
        cuts, states = [], set()
        for a in at:
            self.assertIn(a, keys, 'the uncut run marked each boundary')
            if keys[a] not in states:
                states.add(keys[a])
                cuts.append(a)
        self.assertLess(len(cuts), len(at), 'states repeat across boundaries: %r' % cuts)
        if way != 'the way back':   # the control: config.toml.tmp, an unhooked copy, comes between it and the one before
            self.assertIn('mv:config.toml', cuts)
        pairs = set()
        for a in cuts:
            pair = None
            with self.subTest(way=way, at=a):
                pair = self.cut(way, a, False)
            if pair is not None and pair not in pairs:
                pairs.add(pair)
                with self.subTest(way=way, at=a, reboot=True):
                    self.cut(way, a, True)
        self.assertGreaterEqual(len(pairs), 2, 'the cuts left the pair before the step and the one after it')
        self.assertLess(len(pairs), len(cuts), 'a pair is a class of the states, not each one: %r' % sorted(pairs))

    def test_a_sigkill_at_each_boundary_leaves_a_pair_that_starts_and_the_same_line_finishes_it(self):
        """Forward from v0.9.5 and a config before H1 (no log-file line)."""
        self.matrix('pre-H1 forward')

    def test_the_same_forward_from_h1_s_config(self):
        """Forward from v0.9.5 and H1's config (the line, H1's header: the step installs config.toml for a comment)."""
        self.matrix('H1 forward')

    def test_the_same_on_the_way_back(self):
        """The way back from v0.12.0 (config.toml already the render: not installed again)."""
        self.matrix('the way back')

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


if __name__ == '__main__':
    unittest.main()
