"""The unattended modes' carry-overs of S2b-3c-1 B1 into B2a (build review r4: codex F4, F2; opus F1, F2, F3): the words
a window or RECOVER leaves in an OPEN journal are true when written and name only steps that work while it is open,
and no process the window waits for holds its locks. Each class names its finding and has the control that must come
out the other way. (Named for its CI part, test_u[!p][!a]*.py: .github/workflows/release-check.yml.)

- A READ HOLDS NO LOCK (codex r4 F4): a shell of the window or of RECOVER that waits for a read of runscaler's unit
  (udown_word's subshell, a `$(proc_now)`) holds neither fd 8 (pool-image.sh's own lock) nor fd 9 (the updater lock):
  a window killed while that read is pending leaves both locks free. The control: the live window holds both.
- POOL DOWN IS TRUE WHEN WRITTEN (opus r4 F1, codex r4 F2): RECOVER's STOP POOL DOWN for a file that does not validate
  is written only when a read right then still finds no runscaler that RUNS; the unit that came back by itself during
  the validate gets none, and the next pass closes. The control: the unit stays down: one POOL DOWN.
- THE ADVICE WORKS IN AN OPEN JOURNAL (opus r4 F2): no line RECOVER writes into an open journal tells a person to run
  `03-runscaler.sh real` (03 refuses while that journal is there); each names the hand step that works. The control:
  that hand step, followed, lets the next pass end the window, where `03 real` is refused.
- THE SENTENCE NEEDS AN ENABLED UNIT (opus r4 F3): a rollback that found the enabled unit down, disabled by a person
  during its validate (D-h: `systemctl --user disable --now runscaler`), ends with no sentence that its unit is enabled
  and CI down; the next RECOVER closes with CI DISABLED. The control: no disable: the sentence.
Every cell runs or cuts a REAL window of the real scripts (support.Pool, a throwaway container, a fake clock) and runs
RECOVER as the updater's child; no cell asserts a time it waited.
"""
import os
import re
import unittest

from tests.hetzner.support import needs_container
from tests.hetzner.test_closes import CI_DOWN, h
from tests.hetzner.test_recover import Rec, cut
from tests.hetzner.test_unattended import NONAPI, PASS, UNKNOWN, BackRig, Rig, keys
from tests.hetzner.test_urecover import ended, stops

DOWN = 'runscaler is down'


def pends(g):
    """{what: its event} of the substitutes' `pend ...` events (support.py, hzlib.pend); 'shell': a list, one per shell
    between the read and the window."""
    out = {'shell': []}
    for e in g.p.events():
        if e.startswith('pend shell '):
            out['shell'].append(e)
        for k in ('read', 'window', 'killed', 'before the kill:', 'after the kill:'):
            if e.startswith('pend %s ' % k):
                out[k] = e
    return out


@needs_container
class AReadHoldsNoLock(unittest.TestCase):
    """codex r4 F4 and its class: a window killed while a read of runscaler's unit is pending: each shell that waits for
    that read (udown_word's subshell: a rollback that found the enabled unit down, its validate UNKNOWN, its `end`; the
    window's `$(proc_now)` of its `process` line; the command substitution of a unit_read the window's own shell makes)
    holds neither lock, and once the window has ended both locks are free. The control: up to the kill, the window
    holds both locks, and both are held."""

    def test_a_killed_window_s_pending_read_holds_neither_lock(self):
        for site in ("udown_word's read", "the window's process read", "the window's own unit read"):
            with self.subTest(site):
                if site.startswith('udown'):
                    g = BackRig(self)
                    g.p.set_unit(active=False, pid=0)
                    g.p.runner = UNKNOWN
                    g.p.hooks(('journal:validate', 'count-shows'), ('systemctl:show-1', 'pend'))
                    r = g.back()
                elif site.endswith('unit read'):     # back's unit_read, in the window's own shell
                    g = BackRig(self)
                    g.p.hooks(('journal:config-sha', 'count-shows'), ('systemctl:show-1', 'pend'))
                    r = g.back()
                else:
                    g = Rig(self)
                    g.p.hooks(('journal:digest', 'count-shows'), ('systemctl:show-1', 'pend'))
                    r = g.up()
                ev = pends(g)
                self.assertIn(' window=True ', ev.get('window', ''), g.p.events())
                self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
                self.assertIn('fd8-lock=True fd9-lock=True', ev['window'], 'the control: the live window holds both')
                self.assertIn('fd8-lock=held fd9-lock=held', ev['before the kill:'])
                self.assertIn('ended: True', ev['killed'])
                self.assertIn('fd8-lock=False fd9-lock=False', ev['read'])
                self.assertGreaterEqual(len(ev['shell']), 1, g.p.events())
                for s in ev['shell']:
                    self.assertIn('fd8-lock=False fd9-lock=False', s, 'a shell that waits for the read holds a lock')
                self.assertIn('fd8-lock=FREE fd9-lock=FREE', ev['after the kill:'],
                              'a lock is held after the window ended: by its pending read')


@needs_container
class PoolDownTrueWhenWritten(unittest.TestCase):
    """opus r4 F1, codex r4 F2: RECOVER's STOP POOL DOWN of a file whose copy does not validate (UNKNOWN), written
    after up to 3 tries: a person's file H (a switch cut after `stopped`, the unit in its crash loop), and the window's
    pre-window file (a pending hand edit an up window journaled as `config-sha`, the unit stopped). The unit comes back
    by itself and serves during the validate: no POOL DOWN, no start, the journal open, and the next pass closes (other;
    pre). The control: the unit stays down: one POOL DOWN that says runscaler is down."""

    def test_pool_down_only_while_no_runscaler_runs(self):
        for what in ('other', 'pre'):
            for back in (True, False):
                with self.subTest(what, back=back):
                    if what == 'other':
                        g = cut(self, 'up', ('journal:stopped', 'kill'))
                        g.p.write(g.p.rpath('config.toml'), h(g.p.config()), 0o600)
                        g.p.set_unit(active=True, runner='crash', start=g.p.clock() - 10, pid=700)
                    else:
                        g = Rig(self)
                        g.p.write(g.p.rpath('config.toml'), h(g.old), 0o600)
                        g.p.hooks(('journal:config-sha', 'stop', 'kill'))
                        self.assertEqual(g.up().returncode, -9)
                        ended(self, g)
                    g.p.runner = UNKNOWN
                    if back:
                        g.p.hooks(('journal:validate', 'serve' if what == 'other' else 'start'))
                    x = Rec(self, g)
                    x.run(5)
                    lines = x.open()
                    self.assertEqual(x.calls('start'), [], lines)
                    down = stops(lines, 'POOL DOWN')
                    if not back:
                        self.assertEqual(len(down), 1, lines)
                        self.assertIn(DOWN, down[0])
                        continue
                    self.assertEqual(down, [], 'a POOL DOWN written after the unit came back')
                    self.assertNotIn('CI is down', x.r.stdout)
                    g.p.hooks()
                    x.run(0)
                    self.assertEqual(keys(x.lines())[-1], 'closed')
                    self.assertTrue(x.lines()[-2].endswith(' ' + what), x.lines())


@needs_container
class AdviceWorksInAnOpenJournal(unittest.TestCase):
    """opus r4 F2: RECOVER's STOPs in an open journal name no `03-runscaler.sh` (it refuses while the journal is
    there) and name the hand step that works: put a config in place by hand, checked with runner-start validate. The
    sites: a person's file that does not validate (STOP POOL DOWN), a config.toml that cannot be read (STOP POOL DOWN),
    a file whose runner images are no digest references (STOP HAND CHANGE). The control: the hand step, followed (the
    config from before the window put back), lets the next pass end the window, where `03 real` is refused."""

    def test_no_line_names_03_and_the_hand_step_works(self):
        for site in ('a file that does not validate', 'a config.toml that cannot be read', 'no digest images'):
            with self.subTest(site):
                g = cut(self, 'up', ('journal:stopped', 'kill'))
                cfg = g.p.rpath('config.toml')
                if site.startswith('a file'):
                    g.p.write(cfg, h(g.p.config()), 0o600)
                    g.p.runner = NONAPI
                elif site.startswith('a config'):
                    os.remove(cfg)
                else:
                    g.p.write(cfg, re.sub(r'(?m)^runner-image = ".*"$',
                                          'runner-image = "localhost:27500/linux-runner:pinned"', g.p.config()), 0o600)
                    g.p.runner = PASS
                x = Rec(self, g)
                x.run(5)
                lines = x.open()
                mine = lines[len(g.cut):]
                self.assertEqual([l for l in mine if '03-runscaler' in l], [], lines)
                self.assertNotIn('03-runscaler', x.r.stdout)
                last = [l for l in mine if l.startswith('stop ')][-1]
                self.assertIn('runner-start validate', last)
                # the control: 03 refuses here; the hand step works
                r = g.p.s03('real')
                self.assertNotEqual(r.returncode, 0, r.stdout[-2000:])
                g.p.write(cfg, g.old, 0o600)
                g.p.runner = PASS
                x.run(0)
                self.assertEqual(keys(x.lines())[-1], 'closed')
                self.assertEqual(len(x.calls('start')), 1)


@needs_container
class TheSentenceNeedsAnEnabledUnit(unittest.TestCase):
    """opus r4 F3: a rollback that found the enabled unit down (operator (1): it goes on, its restart would start the
    unit); a person disables it during the validate (D-h: `systemctl --user disable --now runscaler`); the validate is
    UNKNOWN: `end`, the journal open, and no sentence that runscaler is down with its unit enabled (CI is off by the
    person's own hand). The next RECOVER closes with CI DISABLED. The control: no disable: the sentence is there."""

    def test_a_down_rollback_disabled_during_its_validate(self):
        for disabled in (True, False):
            with self.subTest(disabled=disabled):
                g = BackRig(self)
                g.p.set_unit(active=False, pid=0)
                g.p.runner = UNKNOWN
                if disabled:
                    g.p.hooks(('journal:validate', 'disable'))
                r = g.back()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                lines = g.p.window()
                self.assertEqual(keys(lines)[-1], 'end', lines)
                self.assertEqual(g.p.unit_now()['enabled'], not disabled)
                if not disabled:
                    self.assertIn(DOWN, lines[-1])
                    self.assertIn(CI_DOWN, lines[-1])
                    continue
                self.assertNotIn(DOWN, lines[-1])
                self.assertNotIn(CI_DOWN, lines[-1])
                ended(self, g)
                x = Rec(self, g)
                x.run(0)
                lines = x.lines()
                self.assertEqual(keys(lines)[-1], 'closed', lines)
                self.assertEqual(len(stops(lines, 'CI DISABLED')), 1, lines)
                self.assertEqual(x.calls('start'), [])


if __name__ == '__main__':
    unittest.main()
