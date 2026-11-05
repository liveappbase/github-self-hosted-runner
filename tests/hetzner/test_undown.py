"""The unattended modes' fix round 3 (S2b-3c-1 B1; build review r3: opus F1, F2, codex F1, F2): a STOP that leaves CI
down says so, and says it only while it is true; and the resume rule's last direction. Each class names its finding;
each cell has the control that must come out the other way. RECOVER's main routes are test_recover.py's, fix round 1's
edges test_urecover.py's, fix round 2's test_closes.py's.

- A STOP THAT LEAVES CI DOWN SAYS SO: an exit of RECOVER or of the window that leaves the journal open with the enabled
  unit down and nothing started has a journal line that says CI is down. A person's file that does not validate while
  runscaler is down: after its STOP HAND CHANGE (once per file), STOP POOL DOWN, once per file, with the validate's
  class and its output's path. THE ONE RULE's other open exits (a file changed right before a start, while RECOVER
  reads it, before THE RESTORE's rename; a switch's comment-edited TARGET that does not validate): the STOP HAND CHANGE
  says CI is down when the unit is down. A config.toml that cannot be read, none running: STOP POOL DOWN. The window's
  hand change after its rename (before its stop, and after it): its STOP says CI is down when the unit is down.
- THE CI-DOWN WORDS ARE TRUE WHEN WRITTEN: they go in only when ONE read of the unit right then finds it enabled and
  down; a rollback that found the unit down and ends before its rename leaves its journal open either way.
- THE RESUME RULE'S LAST DIRECTION: an open `starting E other`, then the TARGET put back: the TARGET's start is a start
  of its own, and its failure decides the rollback.
Every cell cuts or ends a REAL window of the real scripts (support.Pool, a throwaway container, a fake clock) and runs
RECOVER as the updater's child; no cell asserts a time it waited.
"""
import os
import unittest

from tests.hetzner.support import needs_container, sha256_file
from tests.hetzner.test_closes import CI_DOWN, h, journaled_first, whats
from tests.hetzner.test_recover import Rec, cut, own
from tests.hetzner.test_unattended import NONAPI, PASS, UNKNOWN, BackRig, Rig, installed, keys, value
from tests.hetzner.test_urecover import ended, starts, stops

DOWN = 'runscaler is down'


def mine(g, lines):
    """RECOVER's lines: those after the window's (g.cut)."""
    return lines[len(g.cut):]


def last_stop(lines):
    """The journal's last `stop` line, or None."""
    s = [l for l in lines if l.startswith('stop ')]
    return s[-1] if s else None


@needs_container
class CiDownStop(unittest.TestCase):
    """Item 1 (opus r3 F2; S2B-3C-PLAN r3 FOLD OPERATOR (1): "on another file only after a copy validates, else a STOP
    that says CI is down"): RECOVER step 5, a switch cut after `stopped` (runscaler down, its unit enabled), a person's
    file H whose copy does not validate (NON-API, UNKNOWN): no start, the journal open, and after H's STOP HAND CHANGE a
    `stop POOL DOWN` that says runscaler is down and CI is down, with the validate's class and its output's path. Once
    per file however many passes validate it again (ONCE-LINES: keyed on the STOP line), one HAND CHANGE (THE ONE RULE).
    The control: the same file with a runscaler that RUNS: its STOP HAND CHANGE restarts nothing, closed other, no line
    of RECOVER's says CI is down, nothing validated."""

    def test_a_person_s_file_that_does_not_validate_with_runscaler_down(self):
        for out, cls in ((NONAPI, 'NON-API'), (UNKNOWN, 'UNKNOWN')):
            with self.subTest(cls):
                g = cut(self, 'up', ('journal:stopped', 'kill'))
                g.p.write(g.p.rpath('config.toml'), h(g.p.config()), 0o600)
                g.p.runner = out
                x = Rec(self, g)
                for n in (1, 2):
                    x.run(5)
                    lines = x.open()
                    self.assertEqual(x.calls('start'), [], 'a file that failed its validate was started')
                    self.assertFalse(g.p.unit_now()['active'])
                    self.assertEqual(len(stops(lines, 'HAND CHANGE')), 1, lines)
                    self.assertEqual(len([l for l in mine(g, lines) if l.startswith('validate hand ')]), n, lines)
                    down = stops(lines, 'POOL DOWN')
                    self.assertEqual(len(down), 1, lines)
                    self.assertTrue(last_stop(lines).startswith('stop POOL DOWN: '), lines)
                    self.assertIn(DOWN, down[0])
                    self.assertIn('CI is down', down[0])
                    path = os.path.join(g.p.STATE, 'windows', value(lines, 'window') + '.d', 'validate-hand-1.out')
                    self.assertTrue(os.path.exists(path), path)
                    self.assertIn('(%s; its whole output: %s)' % (cls, path), down[0])

    def test_control_a_runscaler_that_runs_restarts_nothing_and_says_nothing_of_ci_down(self):
        g = cut(self, 'up', ('journal:stopped', 'kill'))
        g.p.write(g.p.rpath('config.toml'), h(g.p.config()), 0o600)
        g.p.runner = NONAPI
        g.p.set_unit(active=True, start=g.p.clock(plus=2), pid=900)
        x = Rec(self, g)
        x.run(0)
        lines = x.closed('other')
        hand = stops(lines, 'HAND CHANGE')
        self.assertEqual(len(hand), 1, lines)
        self.assertIn('restarts nothing', hand[0])
        self.assertEqual([l for l in mine(g, lines) if 'CI is down' in l or DOWN in l], [], lines)
        self.assertEqual(stops(lines, 'POOL DOWN'), [], lines)
        self.assertEqual(g.validates(), [])
        self.assertEqual(x.calls('start') + x.calls('stop') + x.calls('restart'), [])


@needs_container
class CiDownWordsAreTrue(unittest.TestCase):
    """Item 2 (codex r3 F2): a rollback that found its enabled unit in the auto-restart wait (activating, MainPID 0: a
    crash loop between two tries) goes on as on a stopped unit; its validate is UNKNOWN: `end`, no STOP, the journal
    open. The unit came back by itself during the validate (it serves): its last word, and its printed line, say nothing
    of runscaler or CI down; the next RECOVER finds a runscaler that RUNS and closes pre, starting nothing. The control:
    the unit still down at that end: the sentence is there (test_closes's OpenJournalSaysCiDown: an inactive unit)."""

    def test_the_sentence_goes_in_only_while_the_unit_is_down(self):
        for back_by_itself in (True, False):
            with self.subTest(back_by_itself=back_by_itself):
                g = BackRig(self)
                g.p.set_unit(runner='crash', start=g.p.clock() - 10)
                g.p.runner = UNKNOWN
                if back_by_itself:
                    g.p.hooks(('journal:validate', 'serve'))
                r = g.back()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                lines = g.p.window()
                self.assertEqual(keys(lines)[-1], 'end', lines)
                self.assertNotIn('installed', keys(lines))
                self.assertNotIn('start-state', keys(lines), 'the unit did not read down when the rollback began')
                self.assertEqual(g.calls('start') + g.calls('stop') + g.calls('restart'), [])
                if not back_by_itself:
                    self.assertIn(DOWN, lines[-1])
                    self.assertIn(CI_DOWN, lines[-1])
                    self.assertIn(DOWN, r.stdout)
                    continue
                self.assertNotIn('is down', lines[-1])
                self.assertNotIn(DOWN, r.stdout)
                ended(self, g)
                x = Rec(self, g)
                x.run(0)
                x.closed('pre')
                self.assertEqual(x.calls('start') + x.calls('stop') + x.calls('restart'), [])


@needs_container
class EveryOpenExit(unittest.TestCase):
    """Item 1's class: every exit of RECOVER and of the window that leaves the journal open with the enabled unit down
    and nothing started says CI is down in its own line. THE ONE RULE's open exits of RECOVER (rc_hand): a change right
    before RECOVER's start, a change while RECOVER reads the file to validate it, a switch's TARGET with a comment that
    does not validate, a change right before THE RESTORE's rename (after its stop): the STOP HAND CHANGE says runscaler
    is down and CI is down. A config.toml that cannot be read with none running (step 5, step 1): STOP POOL DOWN, once.
    The window's hand change after its rename: a rollback that found the unit down, before its stop; a switch after its
    stop: its STOP HAND CHANGE says so (and never that runscaler runs on). The controls: the same exits with a runscaler
    running (the switch's TARGET with a comment under an older runscaler; a config.toml that cannot be read under one
    that RUNS: closed none; a rollback with the unit active, before its stop): no line says CI is down."""

    def test_the_one_rule_s_open_exits_say_ci_is_down_when_the_unit_is_down(self):
        for site in ('a change right before the start', 'a change while RECOVER reads the file',
                     'the switch\'s TARGET with a comment that does not validate',
                     'a change right before the restore\'s rename',
                     'control: the switch\'s TARGET with a comment under an older runscaler'):
            with self.subTest(site):
                if site.endswith('the start'):
                    g = cut(self, 'up', ('journal:stopped', 'kill'))
                    g.p.hooks(('journal:starting', 'edit-config'))
                elif site.endswith('reads the file'):
                    g = cut(self, 'up', ('journal:stopped', 'kill'))
                    g.p.write(g.p.rpath('config.toml'), h(g.p.config()), 0o600)
                    g.p.runner = PASS
                    g.p.hooks(('journal:hand-change', 'edit-config'))
                elif site.endswith('rename'):
                    g = cut(self, 'back', ('journal:renamed', 'kill'))
                    g.p.runner = {'seq': [NONAPI]}
                    g.p.hooks(('journal:rename-start', 'edit-config'))
                else:
                    g = cut(self, 'up', ('journal:renamed' if site.startswith('control') else 'journal:stopped',
                                         'kill'))
                    g.p.write(g.p.rpath('config.toml'), g.p.config() + '# a comment\n', 0o600)
                    g.p.runner = NONAPI
                x = Rec(self, g)
                x.run(5)
                lines = x.open()
                self.assertEqual(x.calls('start'), [], lines)
                self.assertTrue(last_stop(lines).startswith('stop HAND CHANGE: '), lines)
                self.assertEqual(value(lines, 'hand-change'), sha256_file(g.p.rpath('config.toml')))
                if site.endswith('rename'):
                    self.assertIn('restore', own(lines))
                if site.startswith('control'):
                    self.assertTrue(g.p.unit_now()['active'], 'no older runscaler runs')
                    self.assertEqual([l for l in mine(g, lines) if 'CI is down' in l or DOWN in l], [], lines)
                    continue
                self.assertFalse(g.p.unit_now()['active'], 'runscaler runs: no CI down to say')
                self.assertIn(DOWN, last_stop(lines))
                self.assertIn(CI_DOWN, last_stop(lines))

    def test_a_config_toml_that_cannot_be_read_with_none_running(self):
        for site, at in (('step 5', ('journal:stopped',)), ('step 1', ('journal:staged', 'stop')),
                         ('control: a runscaler runs', ('journal:staged',))):
            with self.subTest(site):
                g = cut(self, 'up', at + ('kill',))
                os.remove(g.p.rpath('config.toml'))
                x = Rec(self, g)
                if site.startswith('control'):
                    x.run(0)
                    lines = x.lines()
                    self.assertEqual(keys(lines)[-1], 'closed', lines)
                    self.assertEqual(installed(lines), ('none', 'none', 'none'), lines)
                    self.assertEqual(stops(lines, 'POOL DOWN'), [], lines)
                    self.assertEqual([l for l in mine(g, lines) if 'CI is down' in l], [], lines)
                    continue
                for _ in (1, 2):
                    x.run(5)
                    lines = x.open()
                    down = stops(lines, 'POOL DOWN')
                    self.assertEqual(len(down), 1, lines)
                    self.assertIn('cannot be read', down[0])
                    self.assertIn(DOWN, down[0])
                    self.assertIn('CI is down', down[0])
                    self.assertEqual(x.calls('start'), [])
                    self.assertFalse(g.p.unit_now()['active'])

    def test_the_window_s_hand_change_after_its_rename_says_ci_is_down_when_the_unit_is_down(self):
        for site in ('a rollback that found the unit down, before its stop', 'a switch, after its stop',
                     'control: a rollback with the unit active, before its stop'):
            with self.subTest(site):
                if site.startswith('a switch'):
                    g = Rig(self)
                    g.p.hooks(('journal:starting', 'edit-config'))
                    r = g.up()
                else:
                    g = BackRig(self)
                    if not site.startswith('control'):
                        g.p.set_unit(active=False, pid=0)
                    g.p.hooks(('journal:stopping', 'edit-config'))
                    r = g.back()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                lines = g.p.window()
                self.assertTrue(lines[-1].startswith('stop HAND CHANGE: '), lines)
                self.assertIn('renamed', keys(lines))
                self.assertNotIn('installed', keys(lines))
                if site.startswith('control'):
                    self.assertTrue(g.p.unit_now()['active'])
                    self.assertNotIn('CI is down', lines[-1])
                    self.assertNotIn(DOWN, lines[-1])
                    continue
                self.assertFalse(g.p.unit_now()['active'])
                self.assertIn(DOWN, lines[-1])
                self.assertIn(CI_DOWN, lines[-1])
                self.assertNotIn('runs on as it was', lines[-1])


@needs_container
class ResumeOtherThenTarget(unittest.TestCase):
    """Item 3 (opus r3 F1, codex r3 F1: codex r2 F1's own input, the direction no cell drove): a rollback cut after
    `stopped` (its TARGET installed, runscaler down); a person's file H; RECOVER validates H and is cut right after its
    `starting E other`; the person puts the TARGET back. The next RECOVER journals its own `starting E target` before
    its start (an open start of another file is no failure of the TARGET and is not resumed). The TARGET never runs (a
    crash loop): that start's own `pre-close-failure` (exit 5, open); the next pass is DECIDED: THE RESTORE, ROLLBACK
    FAILED once, one TARGET `starting` in all, closed pre. The TARGET serves: closed target-running. The control: H
    stays: its open start is resumed with no new line, closed other, no ROLLBACK FAILED."""

    def other_start_cut(self, put_target, runner):
        g = cut(self, 'back', ('journal:stopped', 'kill'))
        cfg = g.p.rpath('config.toml')
        tgt = g.p.config()
        self.assertEqual(tgt, g.old, 'the TARGET is not installed after the cut')
        g.p.write(cfg, h(tgt), 0o600)
        g.p.runner = PASS
        g.p.hooks(('journal:starting', 'kill'))
        x = Rec(self, g)
        x.run(-9)
        self.assertEqual(whats(x.lines()), [['other']], x.lines())
        g.p.hooks()
        if put_target:
            g.p.write(cfg, tgt, 0o600)
        g.p.set_unit(runner=runner)
        return g, x

    def test_the_target_put_back_under_an_open_other_start(self):
        for runner in ('crash', 'serves'):
            with self.subTest(runner=runner):
                g, x = self.other_start_cut(True, runner)
                ev0 = len(g.p.events())
                if runner == 'serves':
                    x.run(0)
                    lines = x.closed('target-running')
                    self.assertEqual(whats(lines), [['other'], ['target']], lines)
                    self.assertEqual(journaled_first(self, g, ev0), 1)
                    self.assertEqual(stops(lines, 'ROLLBACK FAILED'), [], lines)
                    self.assertNotIn('restore', keys(lines))
                    continue
                x.run(5)
                lines = x.open()
                self.assertEqual(whats(lines), [['other'], ['target']], lines)
                self.assertEqual(keys(lines)[-1], 'pre-close-failure', lines)
                e = starts(lines)[-1].split(' ')[0]
                self.assertEqual(value(lines, 'pre-close-failure').split(' ')[:4], ['the', 'start', 'at', e],
                                 'the failure is not of the TARGET\'s own start')
                self.assertEqual(stops(lines, 'ROLLBACK FAILED'), [], lines)
                self.assertNotIn('restore', keys(lines))
                self.assertEqual(journaled_first(self, g, ev0), 1)
                g.p.hooks(('journal:restore', 'serve'))
                x.run(0)
                lines = x.closed('pre')
                self.assertEqual(whats(lines), [['other'], ['target'], ['pre']], lines)
                rbf = stops(lines, 'ROLLBACK FAILED')
                self.assertEqual(len(rbf), 1, lines)
                self.assertIn('did not run after its start', rbf[0])
                self.assertIn('restore', own(lines))
                self.assertEqual(journaled_first(self, g, ev0), 2)
                self.assertEqual(g.p.config(), g.candidate)

    def test_control_the_person_s_file_stays(self):
        g, x = self.other_start_cut(False, 'serves')
        x.run(0)
        lines = x.closed('other')
        self.assertEqual(whats(lines), [['other']], lines)
        self.assertEqual(len(x.calls('start')), 1)
        self.assertEqual(stops(lines, 'ROLLBACK FAILED'), [], lines)
        self.assertNotIn('restore', keys(lines))


if __name__ == '__main__':
    unittest.main()
