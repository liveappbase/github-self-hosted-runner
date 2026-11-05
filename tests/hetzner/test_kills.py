"""A SIGKILL after EACH journal line of both window modes, then RECOVER: the documented end (S2b-3c-1 D-c's cells; PLAN
D1: every line is on disk before its step, so a cut after it leaves a journal RECOVER ends by the header's routes).

The updater and its window are killed (support.Pool's `kill` hook: the holder's whole process group) right after the
line KEY is synced; RECOVER then runs as the updater's child, once, and must leave the journal CLOSED at WINDOW with the
class, the config.toml and the starts and stops the table below names: never a second restart, never the old file put
back under a process that started after the rename, never a validate of the pre-window file. Then RECOVER's own lines:
a SIGKILL after each line of an idle restart (a switch) and of THE RESTORE (a rollback whose TARGET fails its validate),
then RECOVER again: the same end as an uncut RECOVER. The window keys are the happy path's (test_unattended.SWITCH_KEYS,
BACK_KEYS): a key the window no longer writes fails the coverage cell. Each cell: a real window of the real scripts in a
throwaway container (support.Pool), a fake clock; no time asserted.
"""
import unittest

from tests.hetzner.support import needs_container
from tests.hetzner.test_recover import Rec, cut, own
from tests.hetzner.test_unattended import BACK_KEYS, NONAPI, SWITCH_KEYS, BackRig, Rig, keys, value

# THE DOCUMENTED END, key -> (the closing class, config.toml: the window's TARGET (new) or its pre-window file (old),
# RECOVER's starts, RECOVER's stops)
SWITCH_END = {
    'window': ('none', 'old', 0, 0), 'kind': ('none', 'old', 0, 0), 'version': ('none', 'old', 0, 0),
    'digest': ('none', 'old', 0, 0), 'process': ('none', 'old', 0, 0), 'old': ('none', 'old', 0, 0),
    'config-sha': ('pre', 'old', 0, 0), 'staged': ('pre', 'old', 0, 0), 'validate': ('pre', 'old', 0, 0),
    'staged-sha': ('pre', 'old', 0, 0), 'target': ('pre', 'old', 0, 0), 'target-content': ('pre', 'old', 0, 0),
    'idle': ('pre', 'old', 0, 0),
    'backup': ('pre', 'old', 0, 0), 'rename-start': ('pre', 'old', 0, 0),       # 4: nothing installed
    'renamed': ('target-running', 'new', 1, 1), 'from': ('target-running', 'new', 1, 1),   # 3c: the idle restart
    'stopping': ('target-running', 'new', 1, 1),
    'stopped': ('target-running', 'new', 1, 0),                                  # 3b: THE START
    'starting': ('target-running', 'new', 1, 0),                                 # 3b: the start in progress
    'running': ('target-running', 'new', 0, 0), 'prev': ('target-running', 'new', 0, 0),   # 3a
    'installed': ('target-running', 'new', 0, 0),                                # only `closed`
}
BACK_END = {
    'window': ('none', 'old', 0, 0), 'kind': ('none', 'old', 0, 0), 'why': ('none', 'old', 0, 0),
    'verdict': ('none', 'old', 0, 0), 'old-version': ('none', 'old', 0, 0), 'target-version': ('none', 'old', 0, 0),
    'process': ('none', 'old', 0, 0), 'old': ('none', 'old', 0, 0),
    'config-sha': ('pre', 'old', 0, 0), 'staged': ('pre', 'old', 0, 0), 'validate': ('pre', 'old', 0, 0),
    'staged-sha': ('pre', 'old', 0, 0), 'target': ('pre', 'old', 0, 0), 'target-content': ('pre', 'old', 0, 0),
    'backup': ('pre', 'old', 0, 0), 'rename-start': ('pre', 'old', 0, 0),
    'renamed': ('target-running', 'new', 1, 1), 'from': ('target-running', 'new', 1, 1),   # 3c: at once
    'stopping': ('target-running', 'new', 1, 1),
    'stopped': ('target-running', 'new', 1, 0),                                  # 3b: validated, then THE START
    'starting': ('pre', 'old', 1, 0),                                            # DECIDED: THE RESTORE
    'running': ('target-running', 'new', 0, 0),
    'installed': ('target-running', 'new', 0, 0),
}


@needs_container
class KillAfterEachLine(unittest.TestCase):
    def test_the_tables_cover_every_line_of_both_modes(self):
        """A key the window writes is in its table (but `closed`: a cut after it left nothing open)."""
        self.assertEqual(sorted(SWITCH_END), sorted(set(SWITCH_KEYS) - {'closed'}))
        self.assertEqual(sorted(BACK_END), sorted(set(BACK_KEYS) - {'closed'}))

    def end(self, mode, key, want):
        cls, cfg, starts, stops = want
        g = cut(self, mode, ('journal:' + key, 'kill'))
        x = Rec(self, g)
        x.run(0)
        lines = x.closed(cls)
        if mode == 'up':
            self.assertEqual(g.p.config() == g.old, cfg == 'old', 'config.toml')
        else:
            self.assertEqual(g.p.config() == g.candidate, cfg == 'old', 'config.toml')
            self.assertEqual(g.p.config() == g.old, cfg == 'new')
        self.assertEqual((len(x.calls('start')), len(x.calls('stop'))), (starts, stops), lines)
        self.assertEqual(x.calls('restart'), [])
        if key == 'installed':
            self.assertEqual(lines[:-1], g.cut, 'a cut after `installed` gets `closed` alone')
        if mode == 'up':
            self.assertEqual(g.validates(), [], 'RECOVER validated a switch\'s validated file')

    def test_up(self):
        for key in SWITCH_KEYS[:-1]:
            with self.subTest(key):
                self.end('up', key, SWITCH_END[key])

    def test_back(self):
        for key in BACK_KEYS[:-1]:
            with self.subTest(key):
                self.end('back', key, BACK_END[key])

    def test_a_cut_after_closed_leaves_the_apply_step_s_journal(self):
        for mode in ('up', 'back'):
            with self.subTest(mode):
                r = Rig(self) if mode == 'up' else BackRig(self)
                r.p.hooks(('journal:closed', 'kill'))
                res = r.up() if mode == 'up' else r.back()
                self.assertEqual(res.returncode, -9, res.stdout[-3000:] + res.stderr)
                before = r.p.window()
                self.assertEqual(keys(before)[-1], 'closed')
                rr = r.p.recover()
                self.assertEqual(rr.returncode, 0, rr.stdout + rr.stderr)
                self.assertEqual(r.p.window(), before)


@needs_container
class KillRecover(unittest.TestCase):
    """A SIGKILL after each of RECOVER's own lines, then RECOVER again: the same end as an uncut one. A switch cut after
    `renamed` (an older runscaler runs, the pool idle): the idle restart; a rollback cut after `renamed` whose TARGET's
    validate is NON-API: THE RESTORE (the backup back, ROLLBACK FAILED once, the start on the backup)."""

    def test_an_idle_restart_cut_at_each_of_its_lines(self):
        for key in ('recover-start', 'from', 'stopping', 'stopped', 'starting', 'running', 'prev', 'installed'):
            with self.subTest(key):
                g = cut(self, 'up', ('journal:renamed', 'kill'))
                g.p.hooks(('journal:' + key, 'kill'))
                x = Rec(self, g)
                x.run(-9)
                g.p.hooks()
                x.run(0)
                lines = x.closed('target-running')
                self.assertEqual(g.p.config() == g.old, False)
                self.assertLessEqual(len(x.calls('start')), 1, 'a second start')
                self.assertLessEqual(len(x.calls('stop')), 1, 'a second stop')
                self.assertEqual(keys(lines).count('recover-start'), 1)

    def test_a_restore_cut_at_each_of_its_lines(self):
        for key in ('validate', 'stop', 'restore', 'rename-start', 'renamed', 'recover-target', 'starting', 'running',
                    'installed'):
            with self.subTest(key):
                g = cut(self, 'back', ('journal:renamed', 'kill'))
                g.p.runner = {'seq': [NONAPI]}
                g.p.hooks(('journal:' + key, 'kill'))
                x = Rec(self, g)
                x.run(-9)
                g.p.hooks()
                x.run(0)
                lines = x.closed('pre')
                self.assertEqual(g.p.config(), g.candidate)
                self.assertEqual(len([v for v in x.stops(lines) if v.startswith('ROLLBACK FAILED')]), 1, lines)
                self.assertEqual(len(g.validates()), 1, 'the TARGET was validated again')
                self.assertNotIn('hand-change', own(lines))
                self.assertLessEqual(len(x.calls('start')), 1)
                self.assertEqual(value(lines, 'restore'), value(lines, 'backup'))


if __name__ == '__main__':
    unittest.main()
