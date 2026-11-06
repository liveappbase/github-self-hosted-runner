"""`runner-updater back hz-docker`, a person's rollback (S2b-3c-1 D-e, D-f; PLAN D7; B2b item 3): as RS_USER, under
the updater lock (it waits), RECOVER first (B2a's rule for every lock-taking command), then, while the updater is ON
(the Studio's do_back), with a candidate (before ACCEPT) or before back_until (after ACCEPT), `pool-image.sh back
--unattended --why back [--old-version V]` as its CHILD, then the apply step; else REFUSE "nothing to go back to".
The unit not enabled: REFUSE with the line "rollback pending: CI disabled by a person". Exit 0 rolled back, 5 pending
(the window's `end`: no STOP), 1 a STOP or a REFUSE, 2 usage. (Named for its CI part, test_[a-j]*.py:
.github/workflows/release-check.yml.)

- It rejects the version it leaves only when that is newer than the restored image's (the apply step's `why back`), and
  holds no ROLLED BACK; old-version is the candidate's version, or (no candidate) RUN_USER's build record of the image
  config.toml names. A back drops the family's JOBS FAIL ON THE NEW IMAGE and NO EVIDENCE (r2 Opus F2 (a)).
- The pass's preconditions hold for it too: the family lines of config.toml must be the candidate's (else STOP HAND
  CHANGE, the Studio's ru_rb_hand), config.toml.prev's the state's `previous`; a config.toml that already is `previous`
  is nothing to go back to.
- Its validate is bounded with no timer around it (r3 Opus F15): a try that hangs is cut (UNKNOWN: pending, exit 5).
- B2b review r1: THE OUTAGE RULE runs after its RECOVER FIRST and its window (Codex F3: a window whose start fails holds
  POOL DOWN); its last line says "nothing changed" only when nothing did (Opus F2, off's rule); the README's Install
  step 3 runs this release's updater before step 9 (Codex F4), and no README sentence says an OFF pass asks GitHub
  nothing (Opus F3).
Every cell runs the real scripts (support.Pool, a throwaway container, a fake clock) and the updater as RS_USER.
"""
import os
import re
import unittest

from tests.hetzner.support import REPO, digest, needs_container, ref
from tests.hetzner.test_unattended import PASS, UNKNOWN, alive, keys, value
from tests.hetzner.test_updater import FAM, MAIN, OLD, SMALL, V, WINDOW, WINDOWS
from tests.hetzner.test_verdict import PREV, REJECTED, Armed

USAGE = 'usage: runner-updater status | on | off | pass | back hz-docker | build VERSION'
README = os.path.join(REPO, 'linux-docker', 'README.md')
UPD = os.path.join(REPO, 'linux-docker', 'bin', 'runner-updater')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')


def jobs_fail(version=V):
    return {'family': FAM, 'stop': 'JOBS FAIL ON THE NEW IMAGE', 'version': version, 'user': None,
            'detail': {'text': 'planted', 'counts': {'completions': 2, 'succeeded': 0, 'failed': 2, 'canceled': 0}}}


class B(Armed):
    """test_verdict's Armed rig with the REAL core (no verdict): candidate runner V on OLD's lines (config.toml's),
    previous PREV's (config.toml.prev's)."""

    def __init__(self, test, fam=None):
        super().__init__(test, fam=fam, plant=False)

    def back(self, rc=None, *args):
        r = self.p.updater('back', *(args or (FAM,)))
        if rc is not None:
            self.t.assertEqual(r.returncode, rc, r.stdout[-4000:] + r.stderr)
        self.r = r
        return r

    def unchanged(self, r, before):
        """Nothing changed: no window, no restart, config.toml as it was, the state as it was."""
        self.no_window(r)
        self.t.assertEqual(self.raw(), before)


@needs_container
class WithACandidate(unittest.TestCase):
    def test_back_rolls_back_and_rejects_only_a_newer_version(self):
        """A candidate (before ACCEPT): ONE window, `why back`, old-version V (the candidate's): rolled back to PREV
        (exit 0), no candidate, no ROLLED BACK. target-version from RUN_USER's ONE build record of PREV's digest: an
        older one (2.338.0): V rejected (OLD's digest in the rejected file); none: not rejected, and the line says why.
        A held JOBS FAIL ON THE NEW IMAGE of V is dropped (r2 Opus F2 (a)), so the next pass's DUE is not held by it."""
        for record in ('2.338.0', None):
            with self.subTest(record=record):
                b = B(self, fam={'stops': [jobs_fail()]})
                if record:
                    b.p.record(record, PREV)
                r = b.back(0)
                self.assertEqual(len(b.windows()), 1, r.stdout[-3000:])
                (wid, lines), = b.windows()
                self.assertEqual((value(lines, 'why'), value(lines, 'old-version'), value(lines, 'target-version')),
                                 ('back', V, record or 'none'))
                self.assertEqual(lines[-2].split(' ')[-1], 'target-running', lines)
                self.assertEqual(b.p.images(), [ref(PREV)] * 2)
                f = b.fam()
                self.assertEqual((f.get('candidate'), f.get('previous')), (None, None))
                self.assertEqual(b.held(), [], 'a STOP stays: ' + r.stdout[-3000:])
                self.assertEqual(f.get('rejected', []), [V] if record else [])
                self.assertEqual(b.p.read(REJECTED), (OLD + '\n') if record else None)
                self.assertIn('runner-updater: back hz-docker: rolled back', r.stdout)
                if not record:
                    self.assertIn('target-version none', r.stdout)
                self.assertEqual((len(b.since('stop')), len(b.since('start'))), (1, 1))
                r = b.ok('pass')
                self.assertNotIn('STOP JOBS FAIL', [l for l in r.stdout.splitlines() if ' is not due: ' in l][0])

    def test_a_pending_hand_edit_is_hand_change_and_no_window(self):
        """The Studio's ru_rb_hand for `back` too: config.toml names another image for hz-docker than its candidate's
        lines (a person's hand switch, restarted): STOP HAND CHANGE held, no window, exit 1."""
        b = B(self)
        b.p.curl['served'] = [OLD, PREV, digest(36)]
        b.p.write(b.p.rpath('config.toml'), b.p.config().replace(ref(OLD), ref(digest(36))), 0o600)
        b.p.set_unit(start=max(int(os.stat(b.p.rpath('config.toml')).st_mtime), b.p.clock()) + 1, pid=200)
        b.mark()
        r = b.back(1)
        self.assertEqual(b.windows(), [])
        self.assertEqual(b.held(), ['HAND CHANGE'], r.stdout[-3000:])
        self.assertEqual(b.since('stop') + b.since('start'), [])
        self.assertEqual(b.p.images(), [ref(digest(36))] * 2)

    def test_its_validate_is_bounded_with_no_timer_around_it(self):
        """r3 Opus F15: a person's back has no timer's TimeoutStartSec around it; its window's validate try runs under
        `timeout -k 10 120` (here divided by 40: support.Pool.short_timeout), so runscaler's validate that ignores
        SIGTERM is cut: UNKNOWN, the window's `end`, exit 5 (pending: nothing changed), the cut validate ended. The
        control: the first cell (a validate that ends is classified)."""
        b = B(self)
        b.p.short_timeout()
        b.p.runner = {'hang': True, 'rc': 1, 'out': 'never\n'}
        r = b.back(5)
        self.assertEqual(len([a for a in b.p.timeouts() if a[:3] == ['-k', '10', '120']]), 1, b.p.timeouts())
        self.assertEqual(len(b.windows()), 1, r.stdout[-3000:])
        (wid, lines), = b.windows()
        self.assertEqual(value(lines, 'validate'), 'pre 1 UNKNOWN', lines)
        self.assertIn('UNKNOWN', value(lines, 'end'))
        self.assertIn('runner-updater: back hz-docker: rollback pending', r.stdout)
        self.assertEqual(b.fam()['candidate']['version'], V)
        with open(b.p.path('logs', 'hang.pid')) as f:
            self.assertFalse(alive(int(f.read().split()[0])), 'the cut validate still runs')


@needs_container
class AfterAccept(unittest.TestCase):
    def test_before_back_until_it_rolls_back_and_after_it_refuses(self):
        """No candidate (an ACCEPT kept `previous` until back_until): before back_until, ONE window to PREV;
        old-version from RUN_USER's build record of the image config.toml names (OLD's: V), target-version PREV's
        (2.338.0): V rejected. At or after back_until, and with no back_until at all: REFUSE "nothing to go back to",
        nothing changed."""
        for when, ok in (('before', True), ('after', False), ('none', False)):
            with self.subTest(when):
                b = B(self, fam={'candidate': None})
                now = b.p.clock()
                st = b.state()
                st['families'][FAM]['back_until'] = {'before': now + 3600, 'after': now - 1, 'none': None}[when]
                b.put(st)
                b.p.record(V, OLD)
                b.p.record('2.338.0', PREV)
                before = b.raw()
                r = b.back(0 if ok else 1)
                if not ok:
                    self.assertIn('runner-updater: REFUSE back hz-docker: nothing to go back to', r.stdout)
                    b.unchanged(r, before)
                    continue
                self.assertEqual(len(b.windows()), 1, r.stdout[-3000:])
                (wid, lines), = b.windows()
                self.assertEqual((value(lines, 'old-version'), value(lines, 'target-version')), (V, '2.338.0'))
                self.assertEqual(b.p.images(), [ref(PREV)] * 2)
                f = b.fam()
                self.assertEqual((f.get('previous'), f.get('back_until'), f.get('rejected')), (None, None, [V]))

    def test_a_config_that_already_runs_previous_is_nothing_to_go_back_to(self):
        """Before back_until with config.toml already on `previous` (a person's back by hand): REFUSE, nothing
        changed (the window's shortcut would close with no target, and change nothing)."""
        b = B(self, fam={'candidate': None, 'previous': {MAIN: ref(OLD), SMALL: ref(OLD)}})
        st = b.state()
        st['families'][FAM]['back_until'] = b.p.clock() + 3600
        b.put(st)
        before = b.raw()
        r = b.back(1)
        self.assertIn('runner-updater: REFUSE back hz-docker runs %s already' % ref(OLD), r.stdout)
        b.unchanged(r, before)


@needs_container
class Refusals(unittest.TestCase):
    def test_off_a_disabled_unit_and_its_usage(self):
        """OFF (the Studio's do_back): REFUSE, nothing changed. The unit not enabled (a person's `disable --now`):
        REFUSE with the line "rollback pending: CI disabled by a person", nothing changed. `back` with no family or
        another one: usage, exit 2; as RUN_USER: REFUSE."""
        b = B(self)
        st = b.state()
        st['on'] = False
        b.put(st)
        before = b.raw()
        r = b.back(1)
        self.assertIn('runner-updater: REFUSE the updater is OFF: back runs only while it is ON', r.stdout)
        b.unchanged(r, before)
        st['on'] = True
        b.put(st)
        b.p.set_unit(enabled=False, active=False)
        before = b.raw()
        r = b.back(1)
        self.assertIn('runner-updater: REFUSE back hz-docker: rollback pending: CI disabled by a person', r.stdout)
        self.assertEqual(b.windows(), [])
        self.assertEqual(b.raw(), before)
        for args in ((), ('hz-other',), (FAM, 'x')):
            with self.subTest(args=args):
                r = b.p.updater('back', *args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(USAGE, r.stderr)
        b.p.run_user()
        r = b.back(1)
        self.assertIn('runner-updater: REFUSE back is a command of RS_USER', r.stdout)


@needs_container
class RecoverFirst(unittest.TestCase):
    def test_recover_runs_first_and_an_open_journal_starts_no_window(self):
        """B2a's rule for every lock-taking command: a window journal cut right after its first line (the unit
        serving): RECOVER closes it, the apply step archives it, then back goes on (rolled back). A journal RECOVER
        cannot read (exit 6): its STOP (README's section), no window, exit 1."""
        for what in ('closes', 'cannot read'):
            with self.subTest(what):
                b = B(self)
                os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
                text = 'window 20261106010000-4242\n' + ('a line no pattern reads\n' if what == 'cannot read' else '')
                b.p.write(WINDOW, text, 0o600)
                b.mark()
                r = b.back(0 if what == 'closes' else 1)
                if what == 'closes':
                    ids = [w for w, _ in b.windows()]
                    self.assertEqual(ids[0], '20261106010000-4242')
                    self.assertEqual(len(ids), 2, ids)
                    self.assertEqual(b.p.images(), [ref(PREV)] * 2)
                    continue
                self.assertIn('runner-updater: STOP RECOVER cannot read or act on the window journal', r.stdout)
                self.assertIn('An unfinished window the updater cannot end', r.stdout)
                self.assertEqual(b.p.read(WINDOW), text)
                self.assertEqual(b.windows(), [])
                self.assertEqual(b.fam()['candidate']['version'], V)


def pool_down(b):
    """The detail texts of the family's held POOL DOWN STOPs."""
    return [(x.get('detail') or {}).get('text', '') for x in b.fam().get('stops', []) if x['stop'] == 'POOL DOWN']


def last(r):
    return [l for l in r.stdout.splitlines() if l.startswith('runner-updater: ')][-1]


@needs_container
class OutageAndWords(unittest.TestCase):
    def test_back_whose_start_fails_holds_pool_down_naming_its_journal(self):
        """B2b review r1, Codex F3 for `back hz-docker` too: its window stops runscaler, and its start crash-loops
        (`pre-close-failure`, the journal open, exit 1): THE OUTAGE RULE runs after it: POOL DOWN held once, naming the
        open journal; the window's one stop and one start. The control: OFF with the enabled unit down and no journal:
        back ran neither RECOVER nor a window, so it holds nothing and writes nothing (POOL DOWN is the next pass's)."""
        b = B(self)
        b.p.hooks(('journal:starting', 'crash'))
        r = b.back(1)
        self.assertEqual(keys(b.p.window())[-1], 'pre-close-failure', b.p.window())
        down = pool_down(b)
        self.assertEqual(len(down), 1, r.stdout[-3000:])
        for s in ('CI is down', WINDOW, 'pre-close-failure'):
            self.assertIn(s, down[0])
        self.assertEqual((len(b.since('stop')), len(b.since('start')), b.since('restart')), (1, 1, []))
        c = B(self)                                                                     # the control
        st = c.state()
        st['on'] = False
        c.put(st)
        c.p.set_unit(active=False)
        before = c.raw()
        r = c.back(1)
        self.assertEqual(c.raw(), before)
        self.assertIn('nothing changed', last(r))

    def test_back_never_says_nothing_changed_after_recover_acted(self):
        """Opus F2 (B2a's rule for `off`, now for `back`): (off) the updater OFF, a window journal cut right after its
        first line, the enabled unit down: RECOVER FIRST starts runscaler, then back refuses (OFF, exit 1); (pending)
        ON, the enabled unit down, the window's validate UNKNOWN: its journal stays open, RECOVER right after it starts
        runscaler, exit 5. Neither last line says "nothing changed", nor that CI is down; each says what RECOVER did
        stays. The controls: OFF with no journal (exit 1), and ON with the unit serving and the validate UNKNOWN (exit
        5, no start): "nothing changed"."""
        for what, acted in (('off', True), ('pending', True), ('off', False), ('pending', False)):
            with self.subTest(what=what, acted=acted):
                b = B(self)
                if what == 'off':
                    st = b.state()
                    st['on'] = False
                    b.put(st)
                    if acted:
                        os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
                        b.p.write(WINDOW, 'window 20261106010000-4242\n', 0o600)
                else:
                    b.p.runner = {'seq': [UNKNOWN, PASS]}
                if acted:
                    b.p.set_unit(active=False)
                b.mark()
                r = b.back(1 if what == 'off' else 5)
                self.assertEqual(len(b.since('start')), 1 if acted else 0, 'the premise: RECOVER started runscaler')
                self.assertEqual(b.since('stop'), [])
                line = last(r)
                if acted:
                    self.assertTrue(b.p.unit_now()['active'], 'the premise: runscaler runs')
                    self.assertNotIn('nothing changed', line)
                    self.assertNotIn('CI is down', line)
                    self.assertIn('what RECOVER', line)
                else:
                    self.assertIn('nothing changed', line)


# ---- the README (B2b item 4; runs anywhere)

def readme():
    with open(README) as f:
        return f.read()


def section(text, title):
    if '\n## %s\n' % title not in text:
        raise AssertionError('the README has no section "%s"' % title)
    return text.split('\n## %s\n' % title, 1)[1].split('\n## ', 1)[0]


def one(text):
    return ' '.join(text.split())


class Text(unittest.TestCase):
    def test_back_hz_docker_is_the_person_s_rollback_and_no_person_runs_an_unattended_mode(self):
        """D-a, D-e, PLAN D7: the README's person's rollback is `runner-updater back hz-docker` (its command line, what
        it refuses, its exit codes), and no line of the README gives a person `pool-image.sh back --unattended` (or any
        unattended mode) to run. The control: the README still names the unattended modes (for the updater)."""
        text = readme()
        sec = section(text, 'The updater: status, on, off, pass, build')
        self.assertIn("ssh <RS_USER>@<host> '~/bin/runner-updater back hz-docker'", sec)
        line = one([b for b in sec.split('\n- ') if b.startswith('`runner-updater back hz-docker`')][0])
        for s in ('while the updater is ON', 'nothing to go back to', 'rollback pending: CI disabled by a person',
                  'newer than the one it restores', 'Exit 0 rolled back', '5 pending'):
            self.assertIn(s, line)
        self.assertNotRegex(text, r"'bash [^']*pool-image\.sh (up|back|recover) --unattended")
        self.assertIn('`back --unattended`', text)                                     # the control
        self.assertIn("runner-updater back hz-docker", section(text, "The updater's switch and rollback"))

    def test_install_step_3_begins_with_status_and_ends_a_window_journal_before_step_9(self):
        """D-f (r2 Opus F8, Codex F2; r3 Opus F16): the update steps (Install step 3) begin with RS_USER's
        `runner-updater status`; a window journal is ended first (a pass runs RECOVER first). B2b review r1, Codex F4:
        one that an updater too old to end it shows is ended by THIS release's updater, which the step runs as RS_USER
        right after RS_USER's copy (`status`, then `pass`), and the steps go on only once `status` shows no window
        journal, since step 9's `03-runscaler.sh real` refuses while one is there; one it cannot end goes to "An
        unfinished window the updater cannot end". No sentence promises that a first pass ends it with no step that runs
        one. The control: a host with no journal goes on at once ("With no `window journal` line, go on"), before the
        tar line, as before."""
        text = readme()
        install = section(text, 'Install')
        step3 = install.split('\n3. ', 1)[1].split('\n4. ', 1)[0]
        flat = one(step3)
        status = step3.find("ssh <RS_USER>@<host> '~/bin/runner-updater status'")
        tar = step3.find('COPYFILE_DISABLE=1 tar')
        after = step3.find("ssh <RS_USER>@<host> '~/bin/runner-updater pass; ~/bin/runner-updater status'")
        self.assertGreaterEqual(status, 0, step3)
        self.assertGreater(tar, status, 'the status line comes after the files')
        self.assertGreater(after, tar, "no line runs this release's pass after the files")
        self.assertIn('With no `window journal` line, go on.', one(step3[:tar]))      # the control
        tail = one(step3[tar:])
        for s in ("this release's updater as RS_USER", 'only once `status` shows no `window journal` line',
                  '`03-runscaler.sh real` (step 9) refuses while a window journal is there',
                  'An unfinished window the updater cannot end'):
            self.assertIn(s, tail)
        self.assertNotIn('its first pass ends it', flat)
        self.assertIn("ssh <RS_USER>@<host> 'bash -s -- real' < linux-docker/setup/03-runscaler.sh",
                      install.split('\n9. ', 1)[1].split('\n10. ', 1)[0])

    def test_no_readme_sentence_says_an_off_pass_asks_github_nothing(self):
        """B2b review r1, Opus F3 (B2a review r2 Opus F3's class, in the README): no sentence says a pass while OFF (or
        the updater) asks GitHub nothing unless it says that the updater ITSELF does (RECOVER may validate a config and
        start runscaler, which reach GitHub): test_timer's matcher, over the whole README. The control: the matcher
        finds 67449a0's sentence."""
        old = re.compile(r'(?i)(no GitHub call|(?<!itself )asks (the core and )?GitHub nothing)')
        self.assertRegex('While the updater is OFF the pass ends there, and asks GitHub nothing.', old)   # control
        self.assertNotRegex(one(readme()), old)

    def test_no_text_says_back_changed_nothing_whatever_its_recover_did(self):
        """B2b review r1, Opus F2, Codex F5: the README's `back hz-docker` bullet and the program's header (its
        COMMANDS entry and exit 5) never say that a refused or pending back changed nothing whatever its RECOVER first
        did: each says the line names what the run changed. The control: the matcher finds 67449a0's four sentences."""
        old = re.compile(r'(?i)(refuses, and changes nothing|UNKNOWN: nothing changed|no STOP, nothing changed|'
                         r'\(`end`\), nothing changed)')
        for s in ('It refuses, and changes nothing, while the updater is OFF',
                  '5 pending (its validate was UNKNOWN: nothing changed, run it again later)',
                  "`end`: no STOP, nothing changed; the Studio's", '(`end`), nothing changed (the Studio'):
            self.assertRegex(s, old)                                                     # the control
        with open(UPD) as f:
            header = one(''.join(l[1:] for l in f.read().split('\nset -uo pipefail\n', 1)[0].splitlines(True)
                                 if l.startswith('#')))
        self.assertNotRegex(header, old)
        self.assertNotRegex(one(readme()), old)

    def test_no_readme_sentence_says_a_pass_whose_core_waits_changes_nothing(self):
        """B2b review r1 (Codex F5's class: B2a's core_nothing, in the README): a pass whose decision core waits ran
        RECOVER, the apply step and THE OUTAGE RULE before it asked the core, so the README says that the core's own
        state stays and what the pass did before stays, never that it changes nothing. The control: the matcher finds
        67449a0's sentence."""
        old = re.compile(r'(?i)whose decision core waits[^.]*?changes nothing')
        self.assertRegex('A pass or `status` whose decision core waits (the core\'s own state, kept in the state '
                         'file, is of a format it does not read) prints `WAIT` (exit 4) too, `status` after its lines, '
                         'and changes nothing.', old)                                     # the control
        text = one(readme())
        self.assertNotRegex(text, old)
        self.assertIn('what it did before it asked the core', text)

    def test_the_readme_says_what_a_pass_while_off_does_and_its_2_hour_bound(self):
        """B2a's README sentences (build3c1-B2a.log :148-168, fix3c1-B2a-1.log :136-146): no sentence says a pass
        while OFF ends at once or starts nothing, that a pass prints `STOP RECOVER needed (S2b-3c)`, that a journal
        moves to windows/ when its window ends, or a 1 hour bound (the unit's TimeoutStartSec, read here). Each names
        what a pass does: RECOVER, the apply step, POOL DOWN; and the bound in hours. The control: the matcher finds
        the old sentences."""
        old = re.compile(r'(?i)(pass (while OFF )?ends at once|OFF, that pass ends at once|each pass ends at once|'
                         r'is OFF and starts nothing|it starts nothing while the updater is OFF|'
                         r'STOP RECOVER needed \(S2b-3c\)|'
                         r'its journal moves to|longer than 1 hour|its 1 hour bound|cut each hour|'
                         r'starts, stops, switches and edits nothing)')
        for s in ('While the updater is OFF, that pass ends at once (exit 0)', 'its journal moves to `windows/`',
                  'A pass that runs longer than 1 hour', 'it prints `STOP RECOVER needed (S2b-3c)`'):
            self.assertRegex(s, old)                                                    # the control
        text = readme()
        self.assertNotRegex(one(text), old)
        with open(os.path.join(REPO, 'linux-docker', 'config', 'runner-updater.service')) as f:
            hours = re.search(r'^TimeoutStartSec=(\d+)h$', f.read(), re.M).group(1)
        sec = one(section(text, 'The updater: status, on, off, pass, build'))
        self.assertIn('longer than %s hours' % hours, sec)
        self.assertIn('at its %s hour bound' % hours, sec)
        for s in ('a pass while OFF only ends a window journal a cut left', 'holds or clears `STOP POOL DOWN`',
                  'the updater itself asks the core and GitHub nothing', 'RECOVER may validate a config'):
            self.assertIn(s, one(text))

    def test_the_readme_s_status_off_and_files_lines_are_this_release_s(self):
        """B2a's sentences (build3c1-B2a.log :139 :143, B2a's status and off): `status` names which of three a window
        journal is, its last STOP and whether a runscaler runs, no evidence of a departed candidate, and the line of an
        unreadable verdict; `off` runs RECOVER and the apply step first, says whether its run changed something, and
        stops a pending rollback's clock; the Files table's runner-updater row names `back hz-docker` and the rollback.
        The control: the bullets are found."""
        text = readme()
        sec = section(text, 'The updater: status, on, off, pass, build')
        status = one([b for b in sec.split('\n- ') if b.startswith('`status` prints')][0])
        for s in ('open (with its last STOP, and whether a runscaler runs)', 'closed and not applied',
                  'applied and not archived', 'a departed candidate', "R1's failures are not readable",
                  'An unfinished window the updater cannot end'):
            self.assertIn(s, status)
        onoff = one([b for b in sec.split('\n- ') if b.startswith('`runner-updater on`')][0])
        for s in ('first end a window journal a cut left and apply a closed one',
                  'its line says whether that run changed something', 'stops the clock of a pending rollback'):
            self.assertIn(s, onoff)
        row, = [l for l in text.splitlines() if l.startswith('| `bin/runner-updater` |')]
        for s in ('`back hz-docker`', "rolls the pool back on R1's verdict", 'it switches nothing in this release'):
            self.assertIn(s, row)

    def test_the_rollback_section_is_what_status_shows_and_the_stop_s_hand_line_names_it(self):
        """D-e and the r3 FOLD as a person sees them: README "The rollback, and what status shows of it" names R1's
        rollback, the rejection (the rejected file), STOP ROLLED BACK and "R1's failures are not readable", the
        connect-only retry after 1 hour, each precondition's line (CI disabled by a person, HAND CHANGE, ROLLBACK
        FAILED, one restart per pass), the 2 hours of tries, THE OUTAGE RULE's POOL DOWN and CI DISABLED's install
        boundary, and that `retry` and `rebuild` are a later release's. The updater's ROLLBACK FAILED hand line names
        that section by its own title (HAND_OF). The control: the section is found."""
        text = readme()
        sec = one(section(text, 'The rollback, and what status shows of it'))
        for s in ("R1's counted failures", "R1's failures are not readable", '~/.local/state/runner-updater/rejected',
                  'STOP ROLLED BACK', 'one retry after 1 hour', 'rollback pending: CI disabled by a person',
                  'STOP HAND CHANGE', 'STOP ROLLBACK FAILED', 'one restart per pass', '2 hours',
                  'runner-updater back hz-docker', 'STOP POOL DOWN', 'STOP CI DISABLED',
                  'started after `config.toml` was installed', 'come in a later release'):
            self.assertIn(s, sec)
        with open(UPD) as f:
            hand = re.search(r'"ROLLBACK FAILED" then \{hand: "read linux-docker/README\.md, \\"([^"\\]+)\\""\}',
                             f.read())
        self.assertIsNotNone(hand)
        self.assertIn('\n## %s\n' % hand.group(1), text)

    def test_the_unfinished_window_section_names_every_record_no_run_ends_and_d_f_s_order(self):
        """D-g (B1's Notes to B2; B2a's FOR B2b): README "An unfinished window the updater cannot end" names every way a
        run stops on a journal: each rc_cannot site of pool-image.sh (RECOVER's exit 6) and each REPLY of the apply
        step's reader and decision (apply_read, close_rule, stop_rule, apply_rejection) that apply_cannot prints, the
        archive, and the rejected file, by the table below; a site that is not in the table fails here (so a new one
        must be named). Its hand steps come in D-f's order: the timer stopped first (r2 Opus F13 (e)), the record read,
        CI brought back by hand (validate before a restart), the record moved aside, then off, Install step 11, and on
        last. The control: each site's own text is found by the patterns."""
        sec = one(section(readme(), 'An unfinished window the updater cannot end'))
        with open(PIMG) as f:
            recover = re.findall(r'rc_cannot "([^"]*)"', f.read())
        with open(UPD) as f:
            upd = f.read()
        apply = []
        for fn in ('apply_read', 'close_rule', 'stop_rule', 'apply_rejection'):
            body = upd.split('\n%s() {' % fn, 1)[1].split('\n}\n', 1)[0]
            apply += re.findall(r'REPLY="([^"]*)"', body)
        with open(UPD) as f:
            rej = re.findall(r'REPLY="([^"]*)"', upd.split('\nrejected_add() {', 1)[1].split('\n}\n', 1)[0])
        named = {
            'it is not a readable plain file': 'a journal that is not a readable plain file',
            'it cannot be read': 'a journal that is not a readable plain file',
            "line $n is not 'KEY VALUE'": 'a line that is not `KEY VALUE`',
            "line $n: a '$k' line RECOVER does not read (linux-docker/setup/pool-image.sh's header names each)":
                "no pattern of `setup/pool-image.sh`'s header reads",
            'its first line is not \\`window ID\\`': 'no `window` first line',
            'it names a backup, but not its kind, config-sha, staged, staged-sha and target':
                'a `backup` line with no `kind`, `config-sha`, `staged`, `staged-sha` or `target` line before it',
            "its backup line is not its kind's backup": "a `backup` line that is not its kind's backup",
            'its folder $WDIR cannot be made': 'a window folder it cannot make',
            'line $n is no first line \\`window ID\\`': 'no `window` first line',
            'line $n: a STOP this release does not know': "a STOP name the window's grammar has not",
            'its kind is not switch or rollback': 'a `kind`, `why`, `target` or `old` line of another shape',
            "its installed line is not 'SHA CONTENT CLASS'": 'an `installed` line of another shape',
            'it has no installed line (a journal of an earlier release), and no line of it says what it installed':
                'a journal of an earlier release with no line that says what it installed',
            "a switch's close of CLASS $A_CLASS with no version line": "a line it needs missing (a switch's `version`)",
            'its target line is not SET=IMAGE ...': 'a `kind`, `why`, `target` or `old` line of another shape',
            'its old line is no image': 'a `kind`, `why`, `target` or `old` line of another shape',
            "a switch's close of CLASS $A_CLASS, a class only a rollback has": 'a CLASS its kind has not',
            'jq could not read its STOP lines': 'one jq cannot read',
            'jq could not make its ROLLED BACK': 'one jq cannot read',
            'jq could not read its connect-only count': 'one jq cannot read',
            'its why line is not r1, r1-connect or back': 'a `kind`, `why`, `target` or `old` line of another shape',
            'its old line names no image digest to reject': 'a `kind`, `why`, `target` or `old` line of another shape',
        }
        self.assertGreaterEqual(len(recover), 8, recover)                   # the control: the patterns find them
        self.assertGreaterEqual(len(apply), 14, apply)
        for site in recover + apply:
            with self.subTest(site):
                self.assertIn(site, named, 'a site the README section does not name')
                self.assertIn(named[site], sec)
        self.assertEqual(len(rej), 4, rej)
        self.assertIn('its rejection cannot be written', sec)
        self.assertIn('one `sha256:<64 hex>` per line', sec)
        self.assertIn('`windows/<id>` is there already', sec)
        order = [sec.find(s) for s in ('systemctl --user disable --now runner-updater.timer', 'Read the record',
                                       'runner-start validate', 'systemctl --user restart runscaler',
                                       'mv ~/.local/state/runner-updater/window ~/.local/state/runner-updater/aside/',
                                       '~/bin/runner-updater off', 'Install step 11', '~/bin/runner-updater on')]
        self.assertNotIn(-1, order, order)
        self.assertEqual(order, sorted(order), "the hand steps are not in D-f's order")


if __name__ == '__main__':
    unittest.main()
