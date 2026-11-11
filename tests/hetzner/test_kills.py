"""A SIGKILL after EACH journal line of both window modes, then RECOVER: the documented end (S2b-3c-1 D-c's cells; PLAN
D1: every line is on disk before its step, so a cut after it leaves a journal RECOVER ends by the header's routes).

The updater and its window are killed (support.Pool's `kill` hook: the holder's whole process group) right after the
line KEY is synced; RECOVER then runs as the updater's child, once, and must leave the journal CLOSED at WINDOW with the
class, the config.toml and the starts and stops the table below names: never a second restart, never the old file put
back under a process that started after the rename, never a validate of the pre-window file. Then RECOVER's own lines:
a SIGKILL after each line of an idle restart (a switch) and of THE RESTORE (a rollback whose TARGET fails its validate),
then RECOVER again: the same end as an uncut RECOVER. The window keys are the happy path's (test_unattended.SWITCH_KEYS,
BACK_KEYS): a key the window no longer writes fails the coverage cell. S2b-3c-2 B3's rows (KillKeepPrevAndNow): a
`--keep-prev` window cut after `keep-prev`, at its `backup` line, after THE BACKUP (into the window's folder) and after
the rename; a `--now` window cut after `idle skipped`, and a `--now --keep-prev` one after `from`: the next RECOVER ends
each as the table says, config.toml.prev byte for byte as it was before a keep-prev window, the window-folder backup the
pre-window file. B4b fix 1's rows (KillShortcutRestart; review r1, opus F1): THE SHORTCUT'S RESTART (`--now` on a
config.toml that names the digest's image and that no runscaler ran) cut after `idle skipped` (nothing stopped: NO EFFECT
YET, closed pre, nothing restarted), after `stopping` (an older runscaler runs: THE IDLE RESTART; busy: the journal stays
open and nothing restarts) and after `starting` (THE START): config.toml and config.toml.prev as they were, and no
validate (its `staged-sha` proves config.toml). Each cell: a real window of the real scripts in a throwaway container
(support.Pool), a fake clock; no time asserted.
"""
import os
import unittest

from tests.hetzner.support import digest, healthz, needs_container, ref, sha256_file
from tests.hetzner.test_recover import Rec, cut, own
from tests.hetzner.test_switch_flags import installed_unstarted
from tests.hetzner.test_unattended import BACK_KEYS, NONAPI, SWITCH_KEYS, BackRig, Rig, keys, sha, value

# THE DOCUMENTED END, key -> (the closing class, config.toml: the window's TARGET (new) or its pre-window file (old),
# RECOVER's starts, RECOVER's stops)
SWITCH_END = {
    'window': ('none', 'old', 0, 0), 'kind': ('none', 'old', 0, 0), 'version': ('none', 'old', 0, 0),
    'digest': ('none', 'old', 0, 0), 'process': ('none', 'old', 0, 0), 'old': ('none', 'old', 0, 0),
    'config-sha': ('pre', 'old', 0, 0), 'start-state': ('pre', 'old', 0, 0), 'staged': ('pre', 'old', 0, 0),
    'validate': ('pre', 'old', 0, 0), 'staged-sha': ('pre', 'old', 0, 0), 'target': ('pre', 'old', 0, 0),
    'target-content': ('pre', 'old', 0, 0), 'idle': ('pre', 'old', 0, 0),
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
    'config-sha': ('pre', 'old', 0, 0), 'start-state': ('pre', 'old', 0, 0), 'staged': ('pre', 'old', 0, 0),
    'validate': ('pre', 'old', 0, 0), 'staged-sha': ('pre', 'old', 0, 0), 'target': ('pre', 'old', 0, 0),
    'target-content': ('pre', 'old', 0, 0), 'backup': ('pre', 'old', 0, 0), 'rename-start': ('pre', 'old', 0, 0),
    'renamed': ('target-running', 'new', 1, 1), 'from': ('target-running', 'new', 1, 1),   # 3c: at once
    'stopping': ('target-running', 'new', 1, 1),
    'stopped': ('target-running', 'new', 1, 0),                                  # 3b: validated, then THE START
    'starting': ('target-running', 'new', 1, 0),                                 # 3: its start in progress, waited for
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



# S2b-3c-2 B3's rows: (up's options, the cut, the documented end: the closing class, config.toml (the TARGET: new; the
# pre-window file: old), RECOVER's starts, RECOVER's stops)
KEEP_NOW_END = (
    (('--keep-prev',), 'journal:keep-prev', ('none', 'old', 0, 0)),            # 1: no config-sha yet
    (('--keep-prev',), 'journal:backup', ('pre', 'old', 0, 0)),                # before THE BACKUP: 4
    (('--keep-prev',), 'mv-done:config.toml.backup', ('pre', 'old', 0, 0)),    # after it, before the rename: 4
    (('--keep-prev',), 'journal:renamed', ('target-running', 'new', 1, 1)),    # after the rename: 3c, the idle restart
    (('--now',), 'journal:idle', ('pre', 'old', 0, 0)),                        # after `idle skipped`: 4
    (('--now', '--keep-prev'), 'journal:from', ('target-running', 'new', 1, 1)),   # before `stopping`: 3c
)


@needs_container
class KillKeepPrevAndNow(unittest.TestCase):
    def test_each_cut_ends_right_and_a_keep_prev_window_never_touches_config_toml_prev(self):
        for more, at, (cls, cfg, starts, stops) in KEEP_NOW_END:
            with self.subTest(more=more, at=at):
                keep = {}

                def before(g):
                    keep['text'] = g.old.replace(g.p.images()[0], ref(digest(37)))
                    g.p.write(g.prev, keep['text'], 0o600)
                    keep['st'] = os.stat(g.prev)
                    g.p.curl['served'] = g.p.curl['served'] + [digest(37)]   # the keep's image (up's check: B4a 13 (b))
                g = cut(self, 'up', (at, 'kill'), more=more, before=before)
                if at.startswith('journal:'):
                    self.assertEqual(keys(g.cut)[-1], at.split(':', 1)[1], 'the cut came right after its line')
                if '--now' in more and 'idle' in keys(g.cut):
                    self.assertEqual(value(g.cut, 'idle'), 'skipped')
                x = Rec(self, g)
                x.run(0)
                lines = x.closed(cls)
                self.assertEqual(g.p.config() == g.old, cfg == 'old', 'config.toml')
                self.assertEqual((len(x.calls('start')), len(x.calls('stop'))), (starts, stops), lines)
                self.assertEqual(x.calls('restart'), [])
                if '--keep-prev' in more:
                    self.assertEqual((sha256_file(g.prev), os.stat(g.prev).st_mtime_ns),
                                     (sha(keep['text']), keep['st'].st_mtime_ns), 'config.toml.prev changed')
                    self.assertEqual(value(lines, 'prev'), sha(keep['text']))
                    bk = os.path.join(g.p.STATE, 'windows', value(lines, 'window') + '.d', 'config.toml.backup')
                    if 'backup' in keys(g.cut) and at != 'journal:backup':
                        self.assertEqual(g.p.read(bk), g.old, 'the window-folder backup is the pre-window file')
                    else:
                        self.assertFalse(os.path.lexists(bk))
                self.assertEqual(g.validates(), [], 'RECOVER validated a switch\'s validated file')


# B4b fix 1's rows: (the cut, the pool, the documented end: the closing class (None: the journal stays open, exit 5),
# RECOVER's starts, RECOVER's stops)
SHORTCUT_END = (
    ('idle', 'idle', ('pre', 0, 0)),                     # before its stop: NO EFFECT YET, a runscaler runs: closed
    ('stopping', 'idle', ('target-running', 1, 1)),      # its stop began, the older runscaler runs: THE IDLE RESTART
    ('stopping', 'busy', (None, 0, 0)),                  # the same, busy: the cut --now switch waits for idle
    ('starting', 'idle', ('target-running', 1, 0)),      # the unit stopped, its start journaled: THE START
)


@needs_container
class KillShortcutRestart(unittest.TestCase):
    def test_each_cut_of_the_shortcut_s_restart_ends_right(self):
        for key, pool, (cls, starts, stops) in SHORTCUT_END:
            with self.subTest(key=key, pool=pool):
                st = {}

                def before(g):
                    st['cfg'], _, st['keep'], st['kst'] = installed_unstarted(g)
                    if pool == 'busy':
                        g.p.curl['healthz'] = healthz(**{'linux-ci-main': {'busy': 1}})
                g = cut(self, 'up', ('journal:' + key, 'kill'), more=('--now',), before=before)
                self.assertEqual(keys(g.cut)[-1], key, 'the cut came right after its line')
                self.assertEqual(value(g.cut, 'idle'), 'skipped')
                self.assertNotIn('backup', keys(g.cut))
                x = Rec(self, g)
                if cls is None:
                    x.run(5)
                    x.open()
                    self.assertIn('the switch waits for idle', x.r.stdout)
                else:
                    x.run(0)
                    x.closed(cls)
                self.assertEqual(g.p.config(), st['cfg'], 'config.toml')
                self.assertEqual((sha256_file(g.prev), os.stat(g.prev).st_mtime_ns),
                                 (sha(st['keep']), st['kst'].st_mtime_ns), 'config.toml.prev changed')
                self.assertEqual((len(x.calls('start')), len(x.calls('stop'))), (starts, stops), x.lines())
                self.assertEqual(x.calls('restart'), [])
                self.assertEqual(g.validates(), [], 'RECOVER validated a file the window validated')


if __name__ == '__main__':
    unittest.main()
