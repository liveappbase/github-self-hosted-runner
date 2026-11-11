"""`runner-updater retry hz-docker`, a person's command (S2b-3c-2 B4b; the slice plan's E-5 and its r2 FOLD; PLAN D7
:384-393; the Studio's do_retry): as RS_USER, under the updater lock, RECOVER first (B2a's rule for every lock-taking
command), while the updater is ON or OFF; it starts nothing. (Named for its CI part, test_re[!c]*.py:
.github/workflows/release-check.yml.)

- It clears every held STOP whose status line (status.jq's, D7's) names `runner-updater retry hz-docker`: check failed
  (a window's), ROLLED BACK, JOBS FAIL ON THE NEW IMAGE, NO EVIDENCE and ROLLBACK FAILED, in ONE state write; r1_since
  goes when a ROLLBACK FAILED is among them; `rejected` is emptied (this host has no PINNED RUNNER RETIRED). A STOP that
  names another next step (HAND CHANGE, NO IDLE, DISK, CI DISABLED, POOL DOWN) stays; connect_only is never reset.
- ROLLBACK FAILED's hand line names linux-docker/README.md's section, then `runner-updater retry hz-docker` (the Studio's
  THE HAND RULE), also on a ROLLBACK FAILED an earlier release held with its own hand text (no version): status shows
  today's line, and retry clears it.
- A JOBS FAIL ON THE NEW IMAGE of the candidate's version with core.jq's r1_bar null IS the person's ACCEPT (KEEP's
  accept: back_until now + 7 days, no candidate, `previous` kept); with R1's rollback due it is not, and the line says
  why; a NO EVIDENCE it clears accepts nothing.
- THE REJECTED FILE becomes empty by a rename of an empty full copy BEFORE the state write: a kill right after that
  rename leaves the versions rejected in the state (DUE switches none), and the next retry ends it; a kill right after the
  state write leaves the file empty already. A file it cannot replace: a STOP, nothing written. A pass with no retry
  keeps the digests.
- A cleared release with no build record of RUN_USER for this release's image, newer than the runner of RUN_USER's
  record of the image config.toml names (B4b fix 1, opus F4: DUE switches only a newer one): DUE's "waits for RUN_USER's
  build" text and RUN_USER's `build V` line, built from the host config's RUN_USER, HOST_IP and SSH_PORT (here root,
  host.conf.example's 203.0.113.10 and 22; opus F3: `ssh -p`), never a literal. One that is not newer, or with no such
  record: only the clear.
- THE OUTAGE RULE as its last step after its RECOVER (the r2 FOLD).
- The usage of the three commands and their user: RS_USER's only.
Every cell runs the real scripts (support.Pool, a throwaway container, the fake clock) and the updater as RS_USER.
"""
import json
import os
import unittest

from tests.hetzner.support import REPO, digest, needs_container, ref
from tests.hetzner.test_back import one, readme, section
from tests.hetzner.test_updater import FAM, MAIN, OLD, SMALL, STATEDIR, V, WINDOW, WINDOWS, Rig, candidate, stop

REJECTED = os.path.join(STATEDIR, 'rejected')
PREV = digest(37)
OLD_HAND = 'read linux-docker/README.md, "The rollback, and what status shows of it"'   # S2b-3c-1's
NEW_HAND = ('fix what it names (linux-docker/README.md, "The rollback, and what status shows of it"), then '
            'runner-updater retry hz-docker')
USAGE = ('usage: runner-updater status | on | off | pass | back hz-docker | retry hz-docker | rebuild hz-docker [VERSION] '
         '| switch-now hz-docker [VERSION] | build VERSION')
BUILD_LINE = "as root: `ssh -p 22 root@203.0.113.10 '~/bin/runner-updater build %s'`"
CLEARED = ('check failed', 'ROLLED BACK', 'JOBS FAIL ON THE NEW IMAGE', 'NO EVIDENCE', 'ROLLBACK FAILED')
KEPT = ('HAND CHANGE', 'NO IDLE', 'DISK', 'CI DISABLED', 'POOL DOWN')
CUR = '2.338.2'   # the runner of RUN_USER's record of the image config.toml names (OLD), when a cell plants one


def held(name, version=V):
    """A STOP of NAME as the updater holds it (the detail each raiser writes, near enough for status.jq)."""
    d = {'text': 'planted'}
    if name == 'ROLLED BACK':
        d = {'set': MAIN, 'failures': [], 'connect_only': False, 'reason': 'planted'}
    elif name == 'JOBS FAIL ON THE NEW IMAGE':
        d['counts'] = {'completions': 2, 'succeeded': 0, 'failed': 2, 'canceled': 0}
    elif name == 'NO IDLE':
        d.update(digest=digest(39), hand='runner-updater switch-now hz-docker')
    elif name == 'POOL DOWN':
        d['hand'] = 'journalctl --user -u runscaler'
    elif name == 'CI DISABLED':
        d['hand'] = 'systemctl --user enable --now runscaler'
    return stop(name, None if name in ('DISK', 'POOL DOWN', 'CI DISABLED') else version, **d)


class R(Rig):
    """test_updater's Rig (production OLD, the fake clock); hz-docker's family FAM_ planted; the updater ON or OFF."""

    def __init__(self, test, fam, on=True):
        super().__init__(test, on=on, families={FAM: fam})

    def retry(self, rc=0):
        r = self.run('retry', FAM)
        self.t.assertEqual(r.returncode, rc, r.stdout[-4000:] + r.stderr)
        return r

    def fam(self):
        return self.state()['families'][FAM]

    def names(self):
        return [s['stop'] for s in self.fam().get('stops', [])]

    def restarts(self):
        return [l for l in self.p.lines('systemctl') if l.split(' ')[1:2] in (['stop'], ['start'], ['restart'])]


@needs_container
class TheStopsItClears(unittest.TestCase):
    def test_it_clears_each_stop_whose_line_names_retry_and_keeps_the_others(self):
        """E-5 (the updater OFF: retry runs while OFF too): every STOP whose status line names retry is cleared in ONE
        state write, r1_since with ROLLBACK FAILED, `rejected` emptied, THE REJECTED FILE empty; HAND CHANGE, NO IDLE,
        DISK, CI DISABLED and POOL DOWN stay (their next step is another), and connect_only stays; nothing starts or
        stops. The control: the same with no ROLLBACK FAILED keeps r1_since."""
        for rf in (True, False):
            with self.subTest(rollback_failed=rf):
                stops = [held(n) for n in CLEARED if rf or n != 'ROLLBACK FAILED'] + [held(n) for n in KEPT]
                g = R(self, {'stops': stops, 'r1_since': 1761955200, 'rejected': [V],
                             'connect_only': {V: {'n': 1, 'at': 1761955200}}}, on=False)
                g.p.rejected(OLD + '\n')
                r = g.retry()
                f = g.fam()
                self.assertEqual(g.names(), list(KEPT), r.stdout[-3000:])
                self.assertEqual('r1_since' in f, not rf)
                self.assertEqual(f['rejected'], [])
                self.assertEqual(f['connect_only'], {V: {'n': 1, 'at': 1761955200}})
                self.assertEqual(g.p.read(REJECTED), '')
                self.assertFalse(g.state()['on'])
                self.assertEqual(g.restarts(), [])
                self.assertIn('runner-updater: retry hz-docker: cleared STOP check failed (runner %s), STOP ROLLED BACK '
                              '(runner %s)' % (V, V), r.stdout)
                self.assertIn('; rejected: %s, now none; still held: HAND CHANGE, NO IDLE, DISK, CI DISABLED, POOL DOWN '
                              '(`runner-updater status` names the next step of each)' % V, r.stdout)
                self.assertIn('runner-updater: retry hz-docker: %s is empty now' % REJECTED, r.stdout)

    def test_a_rollback_failed_of_an_earlier_release_names_retry_and_retry_clears_it(self):
        """THE HAND RULE (E-5): ROLLBACK FAILED's hand line is the README section, then `runner-updater retry hz-docker`;
        one S2b-3c-1 held (no version, its own hand text) shows today's line in status, and retry clears it. The
        control: a HAND CHANGE of no version stays (its next step is rebuild)."""
        rbf = stop('ROLLBACK FAILED', None, text='planted by an earlier release', hand=OLD_HAND)
        g = R(self, {'stops': [rbf, held('HAND CHANGE', None)]})
        s = g.ok('status').stdout
        self.assertIn('hz-docker: STOP ROLLBACK FAILED: planted by an earlier release. Next, by hand: `%s`' % NEW_HAND, s)
        self.assertNotIn(OLD_HAND, s)
        r = g.retry()
        self.assertEqual(g.names(), ['HAND CHANGE'], r.stdout[-3000:])
        self.assertIn('runner-updater: retry hz-docker: cleared STOP ROLLBACK FAILED; rejected: none; still held: '
                      'HAND CHANGE', r.stdout)


@needs_container
class TheAccept(unittest.TestCase):
    def test_jobs_fail_of_the_candidate_with_no_r1_bar_is_the_accept(self):
        """PLAN D7 :393: a cleared JOBS FAIL ON THE NEW IMAGE of the candidate's version, with r1_bar null (no R1
        evidence of its window) -> KEEP's accept in the same write: no candidate, back_until = now + 7 days, previous
        kept. The controls: R1's rollback due for the candidate's window (r1_bar `rollback`) -> the STOP cleared, the
        candidate stays, and the line says why; a NO EVIDENCE cleared -> no accept; a JOBS FAIL of another version ->
        no accept."""
        for why in ('accept', 'r1 says rollback', 'no evidence', 'another version'):
            with self.subTest(why):
                cand = candidate(1761955200, lines={MAIN: ref(OLD), SMALL: ref(OLD)})
                st = held('NO EVIDENCE') if why == 'no evidence' else \
                    held('JOBS FAIL ON THE NEW IMAGE', '2.338.0' if why == 'another version' else V)
                g = R(self, {'candidate': cand, 'previous': {MAIN: ref(PREV), SMALL: ref(PREV)}, 'stops': [st]})
                now0 = g.p.clock()
                if why == 'r1 says rollback':
                    s = g.state()
                    s['core'] = {'format': 1, 'families': {FAM: dict(cand, open=True, since=cand['closed_at'], gaps=0,
                                 succeeded=0, failed=3, other=0, sets={}, stops=[],
                                 verdict={'set': MAIN, 'failures': [{'t': 1, 'c': False, 'x': 'planted'}] * 3,
                                          'connect_only': False, 'reason': 'planted'})}}
                    g.put(s)
                r = g.retry()
                f = g.fam()
                self.assertEqual(g.names(), [], r.stdout[-3000:])
                self.assertEqual(f['previous'], {MAIN: ref(PREV), SMALL: ref(PREV)})
                if why == 'accept':
                    self.assertIsNone(f['candidate'])
                    self.assertEqual(f['back_until'], now0 + 604800)
                    self.assertIn('runner-updater: retry hz-docker: accepted runner %s: JOBS FAIL ON THE NEW IMAGE is '
                                  'your call' % V, r.stdout)
                    continue
                self.assertEqual(f['candidate'], cand)
                self.assertIsNone(f.get('back_until'))
                self.assertNotIn('accepted runner', r.stdout)
                if why == 'r1 says rollback':
                    self.assertIn("runner-updater: retry hz-docker: runner %s is not accepted: R1's rollback is due "
                                  'for it' % V, r.stdout)


@needs_container
class TheRejectedFile(unittest.TestCase):
    def test_it_is_emptied_before_the_state_write_so_a_kill_between_ends_right(self):
        """E-5's file (r2 FOLD): rejected [V], its digest in the file, ROLLED BACK of V. A kill right after the file's
        rename (before the state write): the file is empty, the state is as it was (V still rejected: the next pass's
        DUE switches nothing to it), and the next retry ends it. A kill right after the state write: both are done
        already (the file first). The control: no kill. A pass with no retry keeps the digest (Opus r1 F8)."""
        for at in ('mv-done:rejected', 'mv-done:state.json', None):
            with self.subTest(at=at):
                g = R(self, {'stops': [held('ROLLED BACK')], 'rejected': [V]})
                g.p.rejected(OLD + '\n')
                before = g.raw()
                if at:
                    g.p.hooks((at, 'kill-updater'))
                    r = g.run('retry', FAM)
                    self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
                    self.assertIn('kill-updater', '\n'.join(g.p.events()), 'the premise: the kill came')
                    g.p.hooks()
                    self.assertEqual(g.p.read(REJECTED), '', 'the file is not emptied first')
                    if at == 'mv-done:rejected':
                        self.assertEqual(g.raw(), before)
                    else:
                        self.assertEqual((g.fam()['rejected'], g.names()), ([], []))
                r = g.retry()
                self.assertEqual((g.fam()['rejected'], g.names(), g.p.read(REJECTED)), ([], [], ''), r.stdout[-3000:])
        p = R(self, {'stops': [held('ROLLED BACK')], 'rejected': [V]})
        p.p.rejected(OLD + '\n')
        p.ok('pass')
        self.assertEqual(p.p.read(REJECTED), OLD + '\n')

    def test_a_file_it_cannot_replace_is_a_stop_and_nothing_is_written(self):
        """A folder where the file is: STOP, the state as it was. The control: no file at all -> retry clears, no file
        made."""
        for what in ('a folder', 'none'):
            with self.subTest(what):
                g = R(self, {'stops': [held('ROLLED BACK')], 'rejected': [V]})
                if what == 'a folder':
                    os.makedirs(REJECTED)
                before = g.raw()
                r = g.run('retry', FAM)
                if what == 'a folder':
                    self.assertEqual(r.returncode, 1, r.stdout[-3000:])
                    self.assertIn('runner-updater: STOP retry hz-docker: the rejected file cannot be emptied (%s is not a '
                                  'readable plain file): nothing is written' % REJECTED, r.stdout)
                    self.assertEqual(g.raw(), before)
                    continue
                self.assertEqual(r.returncode, 0, r.stdout[-3000:])
                self.assertEqual(g.names(), [])
                self.assertFalse(os.path.lexists(REJECTED))


@needs_container
class TheBuildRecordLine(unittest.TestCase):
    def test_a_cleared_release_with_no_build_record_names_run_user_s_build(self):
        """PLAN D7 :384-386's words (E-5): the cleared release V, newer than CUR (RUN_USER's record of the image
        config.toml names), has no build record of RUN_USER for this release's image: DUE's "waits for RUN_USER's build"
        text, DUE's switch once that record is there, and RUN_USER's `build V` line from host.conf's RUN_USER, HOST_IP and
        SSH_PORT (Opus r1 F11; B4b fix 1, review r1 opus F3: `ssh -p SSH_PORT`, here 22, and 2222 in a host.conf that says
        so). B4b fix 1 (opus F4): DUE switches only a release newer than that record's, so a cleared release that is not
        newer (2.300.0), or one with no record of config.toml's image to compare with (NO BASELINE holds DUE), gets no
        line about a switch or a build: only the clear. The control: V's record is there: no such line."""
        for row in ('newer', 'built', 'port 2222', 'older', 'no running record'):
            with self.subTest(row):
                v = '2.300.0' if row == 'older' else V
                g = R(self, {'stops': [held('ROLLED BACK', v)], 'rejected': [v]})
                if row != 'no running record':
                    g.p.record(CUR, OLD)
                if row == 'built':
                    g.p.record(V, digest(39))
                port = '22'
                if row == 'port 2222':
                    port = '2222'
                    conf = g.p.read(g.p.path('host.conf'))
                    self.assertEqual(conf.count('\nSSH_PORT=22\n'), 1)
                    g.p.write(g.p.path('host.conf'), conf.replace('\nSSH_PORT=22\n', '\nSSH_PORT=2222\n'), 0o644)
                r = g.retry()
                self.assertIn('runner-updater: retry hz-docker: cleared STOP ROLLED BACK (runner %s); rejected: %s, now '
                              'none' % (v, v), r.stdout)
                line = [l for l in r.stdout.splitlines() if l.startswith('runner-updater: retry hz-docker: runner %s: '
                                                                         % v)]
                if row in ('built', 'older', 'no running record'):
                    self.assertEqual(line, [], r.stdout[-3000:])
                    self.assertNotIn("DUE's next pass switches", r.stdout)
                    self.assertNotIn('~/bin/runner-updater build', r.stdout)
                    continue
                self.assertEqual(len(line), 1, r.stdout[-3000:])
                self.assertIn("it waits for root's build of runner %s (no usable build record of runner %s for this "
                              "release's image, recipe " % (V, V), line[0])
                self.assertIn("retry starts nothing, and DUE's next pass switches it once that record is there; "
                              + (BUILD_LINE % V).replace('-p 22 ', '-p %s ' % port) + ' builds it', line[0])


@needs_container
class AfterItsRecover(unittest.TestCase):
    def test_the_outage_rule_runs_after_its_recover(self):
        """The r2 FOLD (THE OUTAGE RULE after every command): a journal a cut left right after its first line, the unit
        enabled and down, POOL DOWN held: retry's RECOVER starts runscaler (exactly one start), and THE OUTAGE RULE as
        its last step clears POOL DOWN. The control: no journal (no RECOVER): retry reads nothing of the pool, and
        POOL DOWN stays."""
        for journal in (True, False):
            with self.subTest(journal=journal):
                g = R(self, {'stops': [held('POOL DOWN'), held('ROLLED BACK')]})
                if journal:
                    os.makedirs(WINDOWS, mode=0o700, exist_ok=True)
                    g.p.write(WINDOW, 'window 20261106010000-4242\n', 0o600)
                    g.p.act('stop')
                r = g.retry()
                self.assertEqual(g.names(), [] if journal else ['POOL DOWN'], r.stdout[-3000:])
                starts = [l for l in g.restarts() if l.split(' ')[1] == 'start']
                self.assertEqual(len(starts), 1 if journal else 0)
                if journal:
                    self.assertIn('runner-updater: retry hz-docker: STOP POOL DOWN is cleared', r.stdout)


@needs_container
class UsageAndUser(unittest.TestCase):
    def test_the_three_commands_take_the_family_and_rs_user_runs_them(self):
        """usage (exit 2) for a wrong family or argument; as RUN_USER each well-formed one is a REFUSE (RS_USER's
        command, exit 1: the control that the usage rows are the arguments' doing)."""
        g = Rig(self, on=True, clock=False, production=False)
        for args in (('retry',), ('retry', 'hz-other'), ('retry', FAM, V), ('rebuild',), ('rebuild', FAM, '2.3'),
                     ('rebuild', FAM, V, V), ('switch-now', 'hz-other'), ('switch-now', FAM, 'x')):
            with self.subTest(args):
                r = g.run(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(USAGE, r.stderr)
        g.p.run_user()
        for args in (('retry', FAM), ('rebuild', FAM, V), ('switch-now', FAM)):
            with self.subTest(args, user='RUN_USER'):
                r = g.run(*args)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('runner-updater: REFUSE %s is a command of RS_USER (ci-rs): run it as ci-rs' % args[0],
                              r.stdout)


class Text(unittest.TestCase):
    """The README's three commands as a person reads them (B4b item 7: every sentence a cell can read has a cell here,
    or in the cells named: test_back's rollback section and STOP table, test_pass_switch.Text's NO IDLE path), and the
    updater's header and usage (item 6). Runs anywhere."""

    def test_the_readme_names_each_command_its_rules_and_its_exit_codes(self):
        upd = one(section(readme(), 'The updater: status, on, off, pass, build'))
        for s in ("- `runner-updater retry hz-docker` (RS_USER) clears every STOP whose next step in `status` is "
                  "`runner-updater retry hz-docker`", 'empties `~/.local/state/runner-updater/rejected` first',
                  'A STOP with another next step stays', 'retry accepts the candidate (`accepted runner <version>`',
                  'unless R1\'s rollback is due for it', 'It starts nothing, and works while the updater is OFF',
                  "names RUN_USER's `build` line", "ssh <RS_USER>@<host> '~/bin/runner-updater retry hz-docker'",
                  '- `runner-updater rebuild hz-docker [<runner version>]` (RS_USER) is one switch window to RUN_USER\'s '
                  'build of the runner version config.toml names',
                  'the next step of `STOP HAND CHANGE`, `STOP NO BASELINE` and `STOP recipe changed`',
                  'Its version is the open candidate\'s when config.toml names the candidate\'s lines', '`--keep-prev`',
                  # B4b fix 1: opus F6 (rebuild's refusal of an open candidate whose lines config.toml does not name),
                  # F4 (retry promises no switch of a release that is not newer), F1 and F2 (switch-now)
                  'with an open candidate whose lines config.toml does not name (a hand edit: `STOP HAND CHANGE`), '
                  'rebuild refuses: put the candidate\'s config back first, then `runner-updater rebuild hz-docker <its '
                  'runner version>`',
                  'When a cleared release is newer than the runner of RUN_USER\'s build record of the image config.toml '
                  'names (a pass switches only to a newer release)',
                  'A cleared release that is not newer gets no such line: no pass switches to it',
                  'rebuild refuses, restarts nothing (it never skips the wait for idle) and names `runner-updater '
                  'switch-now hz-docker`, which restarts runscaler into it',
                  'A version you name must be the one it switches (for a waiting switch, the version of its journal): '
                  'another is refused',
                  'the window restarts runscaler into it once (`idle skipped`, no backup: `config.toml.prev` stays as it '
                  'is)', 'that restart cut after its stop began waits for idle as any other switch',
                  'with none (`STOP NO BASELINE`) the version you name', 'and so is a rejected one',
                  'a pool that is not idle changes nothing (exit 5, "not now"), and it never holds `STOP NO IDLE`',
                  'it holds no `STOP DISK`', 'Exit 0 switched (the new image runs); 5 not now; 1 a STOP or a REFUSE',
                  '- `runner-updater switch-now hz-docker [<runner version>]` (RS_USER) is a switch that does not wait '
                  'for idle', 'the next step of `STOP NO IDLE`', '(RECOVER restarts it now: `idle skipped`',
                  'the release of a held `STOP NO IDLE`', 'else the image `rebuild hz-docker` switches to',
                  'A journal kept open for another reason than idle (`STOP HAND CHANGE`, say) restarts nothing',
                  'makes at most one restart of runscaler', 'Exit 0 switched, or the switch is done; 5 not now',
                  '`runner-updater rebuild hz-docker <runner version>`, below, or "A new runner release", puts one in',
                  '`runner-updater rebuild hz-docker <its runner version>`, below'):
            self.assertIn(s, upd)
        for s in ('come in a later release', 'in a later release the updater', '(a later release)'):
            self.assertNotIn(s, one(readme()))
        # opus F5: no line says the pool runs an image from config.toml alone (the README's grep: the build log)
        for s in ('build of the version the pool runs', 'build of the runner version the pool runs',
                  'the image the pool runs', 'when the pool runs the candidate', 'one the pool runs already',
                  'image config.toml runs', 'the config runscaler runs'):
            self.assertNotIn(s, one(readme()))

    def test_the_header_and_usage_name_the_three_commands(self):
        with open(os.path.join(REPO, 'linux-docker', 'bin', 'runner-updater')) as f:
            text = f.read()
        head = one(' '.join(l[2:] for l in text.split('\nset -uo pipefail\n', 1)[0].splitlines() if l.startswith('# ')))
        for s in ('retry hz-docker | rebuild hz-docker [VERSION] | switch-now hz-docker [VERSION] | build VERSION',
                  'retry hz-docker RS_USER\'s only', 'rebuild hz-docker [VERSION] RS_USER\'s only',
                  'switch-now hz-docker [VERSION] RS_USER\'s only', '`rebuild` or `switch-now` not now'):
            self.assertIn(s, head)
        self.assertIn('runner-updater: usage: runner-updater status | on | off | pass | back hz-docker | retry hz-docker | '
                      'rebuild hz-docker [VERSION] | switch-now hz-docker [VERSION] | build VERSION', text)


if __name__ == '__main__':
    unittest.main()
