"""The unattended modes' fix round 2 (S2b-3c-1 B1; build review r2: codex F1-F4, opus F1): what RECOVER and the
rollback window must do where fix round 1 left a start or a close wrong. Each class names its finding; each cell has
the control that must come out the other way. RECOVER's main routes are test_recover.py's, fix round 1's edges
test_urecover.py's, a SIGKILL after each journal line test_kills.py's.

- A RESUMED START IS OF THE FILE IT STARTS: RECOVER waits for an open `starting` only when it is of the file RECOVER is
  to start now (its WHAT: target, pre or other; for pre and other also the sha the `recover-target` before it names).
  Else that start is no failure of the file now installed: RECOVER journals a `starting E WHAT` of its own before it
  starts. A `pre-close-failure` is the TARGET's only when the start it closes was journaled as the TARGET's.
- A START IS CHECKED RIGHT BEFORE IT: every `systemctl --user start` RECOVER makes, a resumed one too, comes right
  after the check that config.toml is still the sha proven for that start (else no start, STOP HAND CHANGE, the
  journal open); a rollback's TARGET start in progress is resumed only on a sha a line proves (a comment edit is
  validated first).
- NO EFFECT, NO TARGET: a journal with no window `rename-start` installed nothing, so a config.toml with the TARGET's
  content is a person's file: `other`, with its STOP HAND CHANGE, whether RECOVER starts it or a runscaler runs it.
- AN OPEN JOURNAL SAYS CI IS DOWN: a rollback that found the enabled unit down and ends before its rename leaves its
  journal open, and its last word says that runscaler is down and CI is down until RECOVER starts it (an `end` for
  UNKNOWN, with no STOP; ROLLBACK FAILED for NON-API).
Every cell cuts or ends a REAL window of the real scripts (support.Pool, a throwaway container, a fake clock) and runs
RECOVER as the updater's child; no cell asserts a time it waited.
"""
import unittest

from tests.hetzner.support import needs_container, sha256_file
from tests.hetzner.test_recover import Rec, cut, own
from tests.hetzner.test_unattended import NONAPI, PASS, UNKNOWN, BackRig, keys, sha, value
from tests.hetzner.test_urecover import ended, starts, stops

CI_DOWN = "CI is down until the updater's RECOVER starts it"


def h(text):
    """A person's file H: the main set's max-runners 3 -> 2 (support's hand-file)."""
    out = text.replace('max-runners = 3\n', 'max-runners = 2\n', 1)
    assert out != text, 'no max-runners = 3 line to change'
    return out


def whats(lines):
    """The WHAT field of each `starting` line ([] for the window's own)."""
    return [s.split(' ')[1:] for s in starts(lines)]


def journaled_first(test, g, ev0):
    """Each runscaler start the systemctl substitute made since its event EV0 has a `starting` line of its own before
    it (the Nth start after the Nth journaled `starting`). The number of starts."""
    ev = g.p.events()[ev0:]
    n_lines = n_starts = 0
    for e in ev:
        if e == 'journal starting':
            n_lines += 1
        elif e.startswith('process ') and ' started ' in e:
            n_starts += 1
            test.assertLessEqual(n_starts, n_lines, 'a start with no `starting` of its own before it: %r' % ev)
    return n_starts


@needs_container
class ResumedStart(unittest.TestCase):
    """Item 1 (opus r2 F1): a rollback window cut right after its `starting` (its stop done, its start not issued), then
    a person's file in place and runscaler down: H, or the file from before the rollback put back. RECOVER's start of
    that file is no TARGET start: its own `starting E other` before it, and a failure of it is that start's own
    pre-close failure: no ROLLBACK FAILED, no `restore`. The control: the TARGET still installed under that open start
    and never running: ONE pre-close failure of the TARGET, THE RESTORE (test_urecover's never-runs cell)."""

    def test_another_file_under_the_window_s_open_target_start(self):
        for what in ('H, inside the start\'s 10 min', 'the pre-window file, past them', 'control: the TARGET'):
            with self.subTest(what):
                g = cut(self, 'back', ('journal:starting', 'kill'))
                x = Rec(self, g)
                ev0 = len(g.p.events())
                if what.startswith('control'):
                    g.p.set_unit(runner='crash')
                    g.p.clock(plus=601)
                    g.p.hooks(('journal:restore', 'serve'))
                    x.run(0)
                    lines = x.closed('pre')
                    self.assertEqual(keys(lines).count('pre-close-failure'), 1, lines)
                    self.assertEqual(own(lines)[:3], ['pre-close-failure', 'stop', 'restore'], lines)
                    self.assertEqual(len(stops(lines, 'ROLLBACK FAILED')), 1, lines)
                    self.assertEqual(g.p.config(), g.candidate)
                    continue
                text = h(g.p.config()) if what.startswith('H') else g.candidate
                g.p.write(g.p.rpath('config.toml'), text, 0o600)
                g.p.runner = PASS
                if what.startswith('H'):        # it serves: one start, closed
                    x.run(0)
                    pcf = 0
                else:                           # its first start crash-loops: that start's own failure, open
                    g.p.clock(plus=601)
                    g.p.set_unit(runner='crash')
                    x.run(5)
                    lines = x.open()
                    self.assertEqual(keys(lines)[-1], 'pre-close-failure', lines)
                    e = starts(lines)[-1].split(' ')[0]
                    self.assertEqual(value(lines, 'pre-close-failure').split(' ')[:4], ['the', 'start', 'at', e],
                                     'the failure is not of RECOVER\'s own start')
                    g.p.set_unit(runner='serves')
                    x.run(0)
                    pcf = 1
                lines = x.closed('other')
                self.assertEqual(whats(lines), [[], ['other']], lines)
                self.assertEqual(journaled_first(self, g, ev0), 1)
                self.assertEqual(keys(lines).count('pre-close-failure'), pcf, lines)
                self.assertEqual(stops(lines, 'ROLLBACK FAILED'), [], lines)
                self.assertNotIn('restore', keys(lines))
                self.assertEqual(g.p.config(), text)

    def test_another_person_s_file_is_a_start_of_its_own(self):
        """Item 1, the subject of an `other` start is its file: a switch cut after `stopped` (its TARGET installed,
        runscaler down), a person's file H; RECOVER validates it and is cut right after its `starting E other`. Then
        the person puts J in place: RECOVER validates J, and its start of J has a `starting E other` of its own before
        it. The control: H still in place: its start in progress is waited for, with no new line."""
        for j in (True, False):
            with self.subTest(j=j):
                g = cut(self, 'up', ('journal:stopped', 'kill'))
                cfg = g.p.rpath('config.toml')
                g.p.write(cfg, h(g.p.config()), 0o600)
                g.p.runner = PASS
                g.p.hooks(('journal:starting', 'kill'))
                x = Rec(self, g)
                x.run(-9)
                self.assertEqual(own(x.lines())[-1], 'starting')
                g.p.hooks()
                if j:
                    g.p.write(cfg, g.p.config() + '# J\n', 0o600)
                ev0 = len(g.p.events())
                x.run(0)
                lines = x.closed('other')
                self.assertEqual(whats(lines), [['other'], ['other']] if j else [['other']], lines)
                self.assertEqual(len(x.calls('start')), 1)
                if j:
                    self.assertEqual(journaled_first(self, g, ev0), 1)
                    self.assertEqual(value(lines, 'recover-target').split(' ')[0], sha256_file(cfg))


@needs_container
class CheckedRightBeforeTheStart(unittest.TestCase):
    """Item 1 (codex r2 F2): every start RECOVER makes, a resumed one too, comes right after the check that config.toml
    is still the sha proven for it. A rollback window cut right after its `starting`, then (a) a person's file H (codex
    F2's input) or (b) the TARGET with a comment added, which no line proves: the window's start in progress, resumed
    once a copy validates. During that validate a person installs J, which never validated: no start on J, STOP HAND
    CHANGE naming J, the journal open. The control: no J: H and the TARGET are validated, then started, and run."""

    def test_a_file_changed_during_the_validate_is_never_started(self):
        for what in ('H', 'the TARGET with a comment'):
            for j in (True, False):
                with self.subTest(what, j=j):
                    g = cut(self, 'back', ('journal:starting', 'kill'))
                    cfg = g.p.rpath('config.toml')
                    text = h(g.p.config()) if what == 'H' else g.p.config() + '# a comment\n'
                    g.p.write(cfg, text, 0o600)
                    g.p.runner = PASS
                    if j:   # J: right after RECOVER's copy, before its validate (H + a comment; the TARGET's H)
                        g.p.hooks(('mv-done:config.recover.toml', 'edit-config' if what == 'H' else 'hand-file'))
                    x = Rec(self, g)
                    if j:
                        x.run(5)
                        lines = x.open()
                        self.assertNotEqual(g.p.config(), text, 'no J was installed')
                        self.assertEqual(len(g.validates()), 1, lines)
                        self.assertEqual(x.calls('start'), [], 'runscaler was started on J')
                        self.assertEqual(value(lines, 'hand-change'), sha256_file(cfg))
                        self.assertEqual(keys(lines)[-1], 'stop', lines)
                        self.assertTrue(lines[-1].startswith('stop HAND CHANGE: '), lines)
                        continue
                    x.run(0)
                    lines = x.closed('other' if what == 'H' else 'target-running')
                    self.assertEqual(len(g.validates()), 1, 'no validate of a sha no line proves')
                    self.assertEqual(len(x.calls('start')), 1)
                    self.assertEqual(whats(lines), [[], ['other']] if what == 'H' else [[]], lines)
                    self.assertEqual(stops(lines, 'ROLLBACK FAILED'), [], lines)


@needs_container
class NoEffectNoTarget(unittest.TestCase):
    """Item 2 (codex r2 F3): a window cut before its `rename-start` installed nothing; a person then installs the
    TARGET's file (the switch's STAGED, the rollback's config.toml.prev) and stops runscaler: its close is `other`, with
    STOP HAND CHANGE, both when RECOVER starts that file and when a runscaler the person started runs it, from step 1
    (cut before `backup`) and from steps 3-5 (cut at `backup`). The control: a window past its rename (`renamed`; or
    the rename done and its `renamed` line lost) closes target-running when the TARGET runs."""

    def test_the_target_s_file_before_the_window_s_rename_is_a_person_s(self):
        for mode, at, runs in (('up', 'journal:target-content', False), ('up', 'journal:target-content', True),
                               ('up', 'journal:backup', False), ('back', 'journal:backup', False)):
            with self.subTest(mode=mode, at=at, runs=runs):
                g = cut(self, mode, (at, 'stop', 'kill'))
                cfg = g.p.rpath('config.toml')
                t = g.p.read(g.staged if mode == 'up' else g.prev)
                self.assertEqual(sha(t), value(g.cut, 'staged-sha'), 'not the TARGET\'s file')
                g.p.write(cfg, t, 0o600)
                if runs:
                    g.p.set_unit(active=True, start=g.p.clock(plus=2), pid=900)
                x = Rec(self, g)
                x.run(0)
                lines = x.closed('other')
                self.assertEqual(len(stops(lines, 'HAND CHANGE')), 1, lines)
                self.assertEqual(value(lines, 'hand-change'), sha(t))
                self.assertEqual(len(x.calls('start')), 0 if runs else 1)

    def test_control_a_window_past_its_rename_closes_target_running(self):
        for at in ('journal:renamed', 'mv-done:config.toml'):
            with self.subTest(at):
                g = cut(self, 'up', (at, 'stop', 'kill'))
                x = Rec(self, g)
                x.run(0)
                lines = x.closed('target-running')
                self.assertEqual(len(x.calls('start')), 1)
                self.assertEqual(stops(lines, 'HAND CHANGE'), [], lines)


@needs_container
class OpenJournalSaysCiDown(unittest.TestCase):
    """Item 3 (codex r2 F4): a rollback that found the enabled unit down ends before its rename with its journal open,
    and its last word says runscaler is down and CI is down until RECOVER starts it: the validate UNKNOWN (an `end`, no
    STOP: the updater tries again; the next RECOVER starts the pre-window file), NON-API (ROLLBACK FAILED), a hand change
    at `rename-start` (HAND CHANGE). The control: the unit active and healthy, UNKNOWN: its `end` says nothing of CI
    down, and the journal closes."""

    def test_a_down_rollback_s_last_word_says_ci_is_down(self):
        for why, out, hooks, last, name in (('UNKNOWN', UNKNOWN, (), 'end', None),
                                            ('NON-API', NONAPI, (), 'stop', 'ROLLBACK FAILED'),
                                            ('a hand change at rename-start', PASS,
                                             (('journal:rename-start', 'edit-config'),), 'stop', 'HAND CHANGE')):
            with self.subTest(why):
                g = BackRig(self)
                g.p.set_unit(active=False, pid=0)
                g.p.runner = out
                g.p.hooks(*hooks)
                r = g.back()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                lines = g.p.window()
                self.assertEqual(keys(lines)[-1], last, lines)
                self.assertNotIn('installed', keys(lines))
                self.assertIn('runscaler is down', lines[-1])
                self.assertIn(CI_DOWN, lines[-1])
                self.assertEqual([l.split(': ', 1)[0] for l in lines if l.startswith('stop ')],
                                 ['stop ' + name] if name else [], lines)
                if why != 'UNKNOWN':
                    continue
                ended(self, g)
                g.p.runner = PASS
                x = Rec(self, g)
                x.run(0)
                x.closed('pre')
                self.assertTrue(g.p.unit_now()['active'], 'CI left down')

    def test_control_an_active_unit_s_unknown_says_nothing_of_ci_down(self):
        g = BackRig(self)
        g.p.runner = UNKNOWN
        r = g.back()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        lines = g.done()[1]
        self.assertNotIn('CI is down', value(lines, 'end'))
        self.assertEqual(stops(lines, 'ROLLBACK FAILED'), [])


if __name__ == '__main__':
    unittest.main()
