"""An unfinished window the updater cannot end (S3b-5 A5; PLAN D1 "A RECORD RECOVER CANNOT READ OR ACT ON").

The texts: RECOVER's "cannot read" (a line no pattern reads, a key it does not know) and "cannot act" (its backup gone
or changed) STOPs, a state WAIT or REFUSE that comes before RECOVER while a record is open, the pass's last line for a
record that stays open, and `status`'s window line, each name README "An unfinished window the updater cannot end" in
these cases, and only in these. And the plan owner's cells: `off` while such a record is open refuses; after the
maintainer's move, `off`, then a pass is OFF and does nothing; a pass with a record it cannot read takes no action.
And the README's hand steps as text (review r1): the first checks the updater lock, each "step N" names the step it
means, and every `lsof` line reads the updater lock.

The rig is test_runner_updater_window's (Win): a window SIGKILLed at a step leaves its record open.
"""
import calendar
import json
import os
import re
import shutil
import time
import unittest

from tests.studio.support import REPO, Sandbox
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

    def lost_state(self, w):
        """state.json is lost, and the protected list holds a name: the lost-state REFUSE of load_state, which comes
        before RECOVER"""
        os.remove(w.u.state)
        w.sb.write(w.u.protected, 'gold-20290101\n', 0o600)

    def lost_state_refused(self, w, cmd, record):
        """CMD exits 1 with ONE line, the lost-state REFUSE; nothing acts; the state stays lost, the list and the
        record as they were. -> that line"""
        listed = read_text(w.u.protected)
        window = read_text(w.u.window) if record else None
        before = counts(w)
        res = recover(w, cmd=cmd)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertTrue(res.stdout.startswith('runner-updater: REFUSE there is no state %s, but the protected list %s '
                                              'is not empty: ' % (w.u.state, w.u.protected)), res.stdout)
        self.assertEqual(res.stdout.count('\n'), 1, res.stdout)
        self.assertEqual(acted(w, before), {})
        self.assertEqual((os.path.lexists(w.u.state), read_text(w.u.protected)), (False, listed))
        if record:
            self.assertEqual(read_text(w.u.window), window)
        return res.stdout

    def test_a_lost_state_with_a_record_open_names_the_section(self):
        # review r1 P2-2: the third `$open` site of load_state, the lost-state REFUSE
        for cmd in ('pass', 'off'):
            with self.subTest(cmd=cmd):
                w = killed(self, 'build-start')
                self.lost_state(w)
                out = self.lost_state_refused(w, cmd, record=True)
                self.assertTrue(out.endswith('move the list aside and run %s again; an updater window is unfinished (%s): '
                                             '%s\n' % (cmd, w.u.window, SECTION)), out)

    def test_control_the_same_lost_state_with_no_record_names_no_section(self):
        for cmd in ('pass', 'off'):
            with self.subTest(cmd=cmd):
                w = Win(self)
                self.lost_state(w)
                self.assertFalse(os.path.lexists(w.u.window))
                out = self.lost_state_refused(w, cmd, record=False)
                self.assertTrue(out.endswith('move the list aside and run %s again\n' % cmd), out)
                self.assertNotIn(SECTION, out)
                self.assertNotIn('unfinished', out)


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


# ---- README's hand steps, as text (S3b-5 review r1)
README = os.path.join(REPO, 'README.md')
HAND = 'An unfinished window the updater cannot end'
LOCK_LINE = '`/usr/sbin/lsof /Users/ci/.local/state/runner-updater/lock`'


def readme_steps(heading):
    """the FIRST numbered list of README's section HEADING: {N: step N's text, its indented lines joined by newlines}"""
    lines = read_text(README).split('\n')
    at = [i for i, l in enumerate(lines) if re.fullmatch(r'#+ ' + re.escape(heading), l)]
    if len(at) != 1:
        raise AssertionError('README has %d sections %r' % (len(at), heading))
    steps, n = {}, None
    for l in lines[at[0] + 1:]:
        if l.startswith('#'):
            break
        m = re.match(r'(\d+)\. (.*)$', l)
        if m:
            n = int(m.group(1))
            if n in steps:
                raise AssertionError('README %r numbers step %d twice' % (heading, n))
            steps[n] = m.group(2)
        elif n is not None and (l == '' or l.startswith('   ')):
            steps[n] += '\n' + l
        elif n is not None:
            break
    return steps


class TestTheHandStepsText(unittest.TestCase):
    """README "An unfinished window the updater cannot end": its first step checks that no run holds the updater lock
    (review r1 P3-2: a window that is RUNNING has its record open, and `status` may name the section during it); the
    steps are numbered 1-9 in this order, and every "step N" in them names the step it means."""

    STARTS = ('No run holds the updater lock', 'Leave the record as it is', 'CI ALREADY RIGHT', "The window's tools",
              "The window's VMs", 'When `/Users/ci/.config/runner/enabled` exists', 'THE CHOICES',
              'On the first choice that passes', 'Tell the maintainer')
    # every step reference in the steps, by the step that makes it
    REFS = {1: ['wait as "Update" step 1 says'], 3: ['do steps 4 and 5 only, then step 9'],
            7: ['go to step 8', 'the copy of step 6'], 8: ["go back to step 6's wait", "step 3's `TZ=UTC0 ps` line",
                                                           "is one of step 5's (a record VM still runs): step 5, then"]}

    def test_the_first_step_checks_that_no_run_holds_the_updater_lock(self):
        first = readme_steps(HAND)[1]
        self.assertIn(LOCK_LINE + ' prints nothing', first)
        self.assertIn('wait as "Update" step 1 says, then run `/Users/ci/bin/runner-updater status` again', first)

    def test_the_steps_in_their_order(self):
        steps = readme_steps(HAND)
        self.assertEqual(sorted(steps), list(range(1, len(self.STARTS) + 1)))
        for n, start in enumerate(self.STARTS, 1):
            self.assertTrue(steps[n].startswith(start), (n, steps[n][:80]))

    def test_every_step_reference_names_the_step_it_means(self):
        for n, text in readme_steps(HAND).items():
            refs = self.REFS.get(n, [])
            for ref in refs:
                self.assertIn(ref, text, n)
            self.assertEqual(len(re.findall(r'\bsteps? \d', text)), sum(len(re.findall(r'\bsteps? \d', r)) for r in refs),
                             (n, re.findall(r'.{0,40}\bsteps? \d.{0,20}', text)))

    def test_every_lsof_line_reads_the_updater_lock(self):
        # one line in every place: the way back, the clear, the hand steps, Update step 2 (review r1 P3-4)
        statedir = re.search(r'^STATEDIR=(\S+)', read_text(os.path.join(REPO, 'install')), re.M).group(1)
        self.assertEqual(LOCK_LINE, '`/usr/sbin/lsof %s/lock`' % statedir)
        self.assertEqual(set(re.findall(r'`[^`]*\blsof\b[^`]*`', read_text(README))), {LOCK_LINE})



PS_LINE = "TZ=UTC0 ps -ax -o pid,lstart,args | grep '/Users/ci/bin/runne[r] run'"
WEST = 'ABC8'          # a zone 8 h west of UTC (POSIX form: no zoneinfo file), as a person's shell may have


def backticked(text, pattern):
    """the `code` spans of TEXT that match PATTERN"""
    return [c for c in re.findall(r'`([^`]+)`', text) if re.search(pattern, c)]


class TestTheStartChecksReadOneClock(unittest.TestCase):
    """review r1 P2-1: `ps -o lstart` prints a start time in the caller's zone, `date -u` in UTC. Step 3 (CI ALREADY
    RIGHT) compares the runscaler's start with the record's EPOCH, and step 8's start check compares it with the time
    of runner-enable: each reads both in UTC, so a host west of UTC never reads a later start as an earlier one."""

    def test_each_start_is_read_in_utc_beside_a_utc_time(self):
        steps = readme_steps(HAND)
        right, enable = steps[3], steps[8]
        self.assertEqual(backticked(right, r'\bps\b'), [PS_LINE])
        self.assertIn('`date -u -r EPOCH`', right)
        self.assertIn('note the time, `date -u`, then `/Users/ci/bin/runner-enable`', enable)
        self.assertIn("ONE runscaler runs that started AFTER that time (step 3's `TZ=UTC0 ps` line; both are UTC)", enable)
        # the class: no line of the README reads a start time in the caller's zone
        for c in backticked(read_text(README), r'lstart'):
            self.assertTrue(c.startswith('TZ=UTC0 ps '), c)

    def start_read_by(self, line, zone):
        """a process whose args end in `<sandbox>/bin/runner run`; LINE (README's, its /Users/ci now the sandbox) run
        by zsh in ZONE -> (its start as epoch seconds, read as UTC, the earliest it can be, the latest)"""
        sb = Sandbox(self)
        runner = sb.write(sb.path('bin', 'runner'), '#!/bin/zsh -f\n/bin/sleep 600\n', 0o755)
        line = line.replace('/Users/ci', sb.root)
        self.assertNotIn('/Users/ci', line)
        t0 = int(time.time())
        p = sb.start(['/bin/zsh', '-f', runner, 'run'], name='runner')
        t1 = int(time.time())
        res = sb.run(['/bin/zsh', '-f', '-c', line], extra_env={'TZ': zone})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        rows = res.stdout.splitlines()
        self.assertEqual(len(rows), 1, res.stdout)
        m = re.fullmatch(r'\s*(\d+)\s+(\w{3} \w{3} [ \d]\d \d\d:\d\d:\d\d \d{4})\s+/bin/zsh -f %s run'
                         % re.escape(runner), rows[0])
        self.assertTrue(m, rows[0])
        self.assertEqual(int(m.group(1)), p.pid)
        return calendar.timegm(time.strptime(m.group(2), '%a %b %d %H:%M:%S %Y')), t0, t1

    def readme_line(self, pattern):
        """step 3's one `code` span that matches PATTERN"""
        lines = backticked(readme_steps(HAND)[3], pattern)
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def test_step_3s_ps_line_reads_the_start_in_utc_in_a_zone_west_of_it(self):
        start, t0, t1 = self.start_read_by(self.readme_line(r'\bps\b'), WEST)
        self.assertTrue(t0 <= start <= t1, (start, t0, t1))

    def test_control_that_line_without_a_zone_setting_reads_8_h_early_there(self):
        start, t0, t1 = self.start_read_by(self.readme_line(r'\bps\b').replace('TZ=UTC0 ', ''), WEST)
        self.assertTrue(t0 - 8 * 3600 <= start <= t1 - 8 * 3600, (start, t0, t1))

    def test_step_3s_date_line_prints_the_epoch_in_utc_in_that_zone(self):
        sb = Sandbox(self)
        t = int(time.time())
        line = self.readme_line(r'\bdate\b.*EPOCH')
        res = sb.run(['/bin/zsh', '-f', '-c', line.replace('EPOCH', str(t))], extra_env={'TZ': WEST})
        self.assertEqual(calendar.timegm(time.strptime(res.stdout.strip(), '%a %b %d %H:%M:%S UTC %Y')), t, res.stdout)



class TestTheEnableStepsBranches(unittest.TestCase):
    """review r1 P3-3: step 8 names each branch of a runner-enable refusal, as the DOCS WALK's row 18 has them: the
    runner lock is not free (back to step 6's wait), a record VM still runs (step 5, then again), any other text (stop:
    the validated choice stays in place, CI down, the maintainer told at once). When every choice fails, the last one
    tried did not validate, or did not start. Each refusal step 8 quotes is a text runner-enable prints."""

    def test_each_refusal_has_its_branch(self):
        enable = readme_steps(HAND)[8]
        self.assertIn("When it says `the runner lock is not free`, a runscaler still drains: go back to step 6's wait, "
                      "then runner-enable again.", enable)
        self.assertIn("When it says `a VM outside runscaler is running` and each VM it names is one of step 5's (a record "
                      "VM still runs): step 5, then runner-enable again.", enable)
        self.assertIn('Any other text (another VM too): stop here, with the validated choice in place and CI down, and '
                      'tell the maintainer at once.', enable)

    def test_every_choice_fails_says_did_not_validate_or_did_not_start(self):
        enable = readme_steps(HAND)[8]
        self.assertIn('When every choice fails, CI stays down and the last choice tried is the config left in place: it '
                      'did not validate, or did not start.', enable)

    def test_each_refusal_it_quotes_is_runner_enable_s(self):
        quoted = re.findall(r'When it says `([^`]+)`', readme_steps(HAND)[8])
        self.assertEqual(len(quoted), 2, quoted)
        dies = re.findall(r'\bdie "([^"]*)"', read_text(os.path.join(REPO, 'bin', 'runner-enable')))
        for q in quoted:
            self.assertTrue([d for d in dies if d.startswith(q)], (q, dies))


if __name__ == '__main__':
    unittest.main()
