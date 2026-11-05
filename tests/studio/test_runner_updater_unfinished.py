"""An unfinished window the updater cannot end (S3b-5 A5; PLAN D1 "A RECORD RECOVER CANNOT READ OR ACT ON").

The texts: RECOVER's "cannot read" (a line no pattern reads, a key it does not know) and "cannot act" (its backup gone
or changed) STOPs, a state WAIT or REFUSE that comes before RECOVER while a record is open, the pass's last line for a
record that stays open, and `status`'s window line, each name README "An unfinished window the updater cannot end" in
these cases, and only in these. And the plan owner's cells: `off` while such a record is open refuses; after the
maintainer's move, `off`, then a pass is OFF and does nothing; a pass with a record it cannot read takes no action.

The rig is test_runner_updater_window's (Win): a window SIGKILLed at a step leaves its record open.
"""
import json
import os
import re
import shutil
import unittest

from tests.studio.support import REPO
from tests.studio.test_runner_updater import read_text
from tests.studio.test_runner_updater_recover import killed, n_disable, recover
from tests.studio.test_runner_updater_window import Win

SECTION = 'README "An unfinished window the updater cannot end"'
ACTIONS = ('runner-disable', 'runner-enable', 'golden-build', 'golden-gate', 'tart')


def acted(w, before):
    """the calls of the action tools since BEFORE (a dict of counts)"""
    return {a: len(w.calls(a)) - before[a] for a in ACTIONS if len(w.calls(a)) != before[a]}


def counts(w):
    return {a: len(w.calls(a)) for a in ACTIONS}


def unreadable(test, how='line'):
    """a window killed after build-start, then its record made one RECOVER cannot read"""
    w = killed(test, 'build-start')
    with open(w.u.window, 'a') as f:
        f.write('backup relative/path\n' if how == 'line' else 'surprise yes\n')
    return w


def unactable(test, how='gone'):
    """a window killed after build-start, then its backup gone (or changed): RECOVER cannot act on the record"""
    w = killed(test, 'build-start')
    backup = w.value('backup')
    if how == 'gone':
        os.remove(backup)
    else:
        with open(backup, 'a') as f:
            f.write('# changed\n')
    return w


class TestRecoverStopsNameTheSection(unittest.TestCase):
    def assert_no_action(self, w, res, before, text):
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn(text, res.stdout)
        self.assertIn('runner-updater: STOP the window journal %s stays open, and RECOVER cannot read or act on it: %s. '
                      'Nothing else starts\n' % (w.u.window, SECTION), res.stdout)
        self.assertEqual(acted(w, before), {})
        self.assertTrue(os.path.exists(w.u.window))

    def test_a_line_no_pattern_reads(self):
        w = unreadable(self)
        before, record = counts(w), read_text(w.u.window)
        res = recover(w)
        self.assert_no_action(w, res, before, "runner-updater: STOP RECOVER cannot read the window journal %s (line "
                              % w.u.window)
        self.assertRegex(res.stdout, r"STOP RECOVER cannot read the window journal \S+ \(line \d+: a 'backup' value RECOVER "
                                     r"does not read\): it changes nothing; %s\n" % re.escape(SECTION))
        self.assertEqual(read_text(w.u.window), record)

    def test_a_key_it_does_not_know(self):
        w = unreadable(self, 'key')
        before = counts(w)
        res = recover(w)
        self.assert_no_action(w, res, before, "RECOVER does not read the key 'surprise'): it changes nothing; %s\n" % SECTION)

    def test_its_backup_is_gone(self):
        w = unactable(self)
        before = counts(w)
        res = recover(w)
        self.assert_no_action(w, res, before, 'runner-updater: STOP RECOVER cannot act on the window journal %s (its '
                                              'backup ' % w.u.window)
        self.assertIn(': it changes nothing; %s\n' % SECTION, res.stdout)

    def test_its_backup_is_changed(self):
        w = unactable(self, 'changed')
        before = counts(w)
        res = recover(w)
        self.assert_no_action(w, res, before, 'is not the config-sha it journaled): it changes nothing; %s\n' % SECTION)

    def test_control_a_record_recover_can_read_but_cannot_end_yet_names_no_section(self):
        # RECOVER's own wait: a VM of a builder runs, CI DISABLED at the bound; the next pass checks again
        w = killed(self, 'build-start', Win(self, extra_rewrites=[('RECOVER_WAIT=20', 'RECOVER_WAIT=1')]))
        w.sb.write(os.path.join(w.vms, 'gold-20290101'), '')
        w.put('running-gold-20290101')
        res = recover(w, ok=1)
        self.assertIn('runner-updater: STOP CI DISABLED: ', res.stdout)
        self.assertIn("runner-updater: STOP the window journal %s stays open: the next run's RECOVER tries again; "
                      "nothing else starts\n" % w.u.window, res.stdout)
        self.assertNotIn(SECTION, res.stdout)


class TestTheStateBeforeRecover(unittest.TestCase):
    """A WAIT or REFUSE of the state comes before RECOVER: while a record is open it names the section; with no record it
    does not (a WAIT with no record is no unfinished window)."""

    def state_of_format_2(self, w):
        w.sb.write(w.u.state, json.dumps({'format': 2}) + '\n', 0o600)

    def test_a_wait_with_a_record_open_names_the_section(self):
        w = killed(self, 'build-start')
        self.state_of_format_2(w)
        before = counts(w)
        res = recover(w)
        self.assertEqual(res.returncode, 4, res.stdout)
        self.assertTrue(res.stdout.startswith('runner-updater: WAIT the state '), res.stdout)
        self.assertTrue(res.stdout.endswith('; an updater window is unfinished (%s): %s\n' % (w.u.window, SECTION)),
                        res.stdout)
        self.assertEqual(acted(w, before), {})

    def test_a_refuse_with_a_record_open_names_the_section(self):
        w = killed(self, 'build-start')
        w.sb.write(w.u.state, 'not json\n', 0o600)
        res = recover(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertTrue(res.stdout.startswith('runner-updater: REFUSE '), res.stdout)
        self.assertTrue(res.stdout.endswith('; an updater window is unfinished (%s): %s\n' % (w.u.window, SECTION)),
                        res.stdout)

    def test_control_the_same_wait_with_no_record_names_no_section(self):
        w = Win(self)
        self.state_of_format_2(w)
        res = recover(w)
        self.assertEqual(res.returncode, 4, res.stdout)
        self.assertNotIn(SECTION, res.stdout)
        self.assertNotIn('unfinished', res.stdout)


class TestStatus(unittest.TestCase):
    """status runs no RECOVER and writes nothing; its window line names the section for a record RECOVER cannot read or
    act on, and says the next pass's RECOVER ends any other."""

    def test_an_unreadable_record(self):
        w = unreadable(self)
        st = w.status()
        self.assertIn('runner-updater: status: a window journal is open: %s, and RECOVER cannot read or act on it (line '
                      % w.u.window, st)
        self.assertIn('): %s\n' % SECTION, st)
        self.assertNotIn('ends it', st)

    def test_a_record_it_cannot_act_on(self):
        w = unactable(self)
        st = w.status()
        self.assertIn('RECOVER cannot read or act on it (its backup ', st)
        self.assertIn(SECTION, st)

    def test_status_writes_nothing_while_it_reads_a_record(self):
        # the record's work folder is gone (so is its backup: RECOVER cannot act); status reads the record by RECOVER's
        # route and makes nothing, not that folder either
        w = killed(self, 'build-start')
        shutil.rmtree(os.path.dirname(w.value('backup')))
        before = sorted(os.path.relpath(os.path.join(t, n), w.r.statedir) for t, ds, fs in os.walk(w.r.statedir)
                        for n in ds + fs)
        st = w.status()
        self.assertIn('RECOVER cannot read or act on it (its backup ', st)
        after = sorted(os.path.relpath(os.path.join(t, n), w.r.statedir) for t, ds, fs in os.walk(w.r.statedir)
                       for n in ds + fs)
        self.assertEqual(after, before)

    def test_control_a_record_recover_can_end(self):
        w = killed(self, 'build-start')
        st = w.status()
        self.assertIn("runner-updater: status: a window journal is open: %s (its run holds the updater lock; when no "
                      "run does, the next pass's RECOVER ends it)\n" % w.u.window, st)
        self.assertNotIn(SECTION, st)

    def test_control_a_record_that_disabled_nothing_is_one_recover_ends(self):
        # cut before its backup line, with CI enabled: RECOVER closes it with no complete record (nothing was disabled)
        w = killed(self, 'config-sha')
        self.assertTrue(os.path.exists(w.r.flag))
        self.assertNotIn(SECTION, w.status())
        recover(w, ok=0)
        self.assertFalse(os.path.exists(w.u.window))


class TestTheMaintainersClear(unittest.TestCase):
    """The plan owner's cells: `off` while a record is open refuses; after the move aside (README's line), `off`, then a
    pass is OFF and does nothing; a pass with a record it cannot read takes no action and its STOP names the section."""

    def test_off_refuses_while_the_record_is_open(self):
        w = unreadable(self)
        state, record, before = w.u.raw(), read_text(w.u.window), counts(w)
        res = w.r.cmd('off', ok=False)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn(SECTION, res.stdout)
        self.assertEqual((w.u.raw(), read_text(w.u.window)), (state, record))   # still ON, the record as it was
        self.assertTrue(w.u.get()['on'])
        self.assertEqual(acted(w, before), {})

    def test_after_the_move_off_then_a_pass_is_off_and_does_nothing(self):
        w = unreadable(self)
        aside = os.path.join(w.r.statedir, 'aside')
        res = w.sb.run(['/bin/zsh', '-f', '-c', 'mkdir -m 700 -p %s && mv -n %s %s/window.$(date -u +%%Y%%m%%d%%H%%M%%S)'
                        % (aside, w.u.window, aside)])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(os.path.exists(w.u.window))
        self.assertEqual(len(os.listdir(aside)), 1)
        off = w.r.cmd('off')
        self.assertIn('runner-updater: off: the updater is OFF\n', off.stdout)
        self.assertFalse(w.u.get()['on'])
        before = counts(w)
        res = w.r.cmd('pass')
        self.assertEqual(res.stdout, 'runner-updater: pass: the updater is OFF: nothing to do\n')
        self.assertEqual(acted(w, before), {})
        self.assertEqual(len(os.listdir(aside)), 1)                              # nothing reads the folder aside

    def test_a_pass_with_a_record_it_cannot_read_takes_no_action(self):
        w = unreadable(self)
        before, disabled = counts(w), n_disable(w)
        res = recover(w)
        self.assertEqual(res.returncode, 1)
        self.assertIn(SECTION, res.stdout)
        self.assertEqual((acted(w, before), n_disable(w)), ({}, disabled))
        self.assertNotIn('runner-updater: pass: one pass at', res.stdout)


class TestTheSectionExists(unittest.TestCase):
    """every text that names the section names a heading the README has"""

    def test_the_readme_has_the_section_and_the_updater_s(self):
        headings = re.findall(r'^#+ (.+)$', read_text(os.path.join(REPO, 'README.md')), re.M)
        self.assertIn('An unfinished window the updater cannot end', headings)
        self.assertIn('The updater', headings)
        for rel in ('install', 'bin/runner-updater', 'bin/runner-updater-window', 'bin/runner-updater-lib'):
            for name in re.findall(r'README \\?"([^"\\]+)\\?"', read_text(os.path.join(REPO, rel))):
                self.assertIn(name, headings, rel)


if __name__ == '__main__':
    unittest.main()
