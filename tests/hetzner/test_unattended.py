"""pool-image.sh's two UNATTENDED modes, the runner-image updater's switch and rollback on the Linux host (plan D1, D5,
D6; the changed-lines list, items 21, 24, 26 and "For S2b-2b"):

- `up --unattended VERSION DIGEST`: under the updater lock, it journals runscaler's process (step 1), then the checks
  (FAMILY LINES from the live config, START STATE, DISK, the tested jq), `03-runscaler.sh render DIGEST STAGED` with
  PRE-VALIDATE's tries (API-ONLY after 3 tries counts as PASS; anything else: STOP before any restart, nothing
  installed), D3 (STAGED differs from config.toml in the runner-image lines only), the IDLE pair through core/idle.jq;
  then at once: `rename-start`, the rename of the staged file whose sha256 03 printed, `renamed`, a wait past the
  `renamed` second, and the restart, unconditionally. Not idle: nothing staged, config.toml unchanged, exit 3.
- `back --unattended`: the rollback to config.toml.prev (the switch's journaled backup), PRE-VALIDATEd by the rollback
  rules (NON-API: STOP ROLLBACK FAILED before any restart; UNKNOWN: no STOP, the caller tries again), no idle wait.
- THE RESTART of both: `from`, `stopping`, the stop, `stopped` (the log position once the old process has exited and
  before the new one starts), `starting`, the start, `running` (the new process, seen started after `renamed`): what
  the updater hands the core as facts.restart {from, to, stopped}.
- Around the rename: an independent restart before `rename-start`, between, with `renamed` missing, after `renamed`, and
  with the run delayed across the rename, each with a busy /healthz: none puts the old file back, and the next call
  finds the journal and the files the updater's next pass reads (that pass's restart is S2b-3's). AFTER THE INSTALL: a
  hand change between the rename and the restart gets no restart (`hand-change`, STOP HAND CHANGE, the journal open).

Every cell runs the real scripts (pin lines rewritten) in a throwaway container (support.Pool), with a fake clock: no
cell asserts a time it waited, only the order of the journal's lines and the clock reads the substitutes gave.
"""
import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
import unittest

from tests.hetzner.support import REPO, PASS_OUT, Pool, digest, healthz, needs_container, ref, sha256_file

FIX = os.path.join(REPO, 'tests', 'studio', 'fixtures', 'validate')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
README = os.path.join(REPO, 'linux-docker', 'README.md')
V = '2.339.0'
NEW, OLD = digest(39), digest(38)
SETS = ('linux-ci-main', 'linux-ci-small')

SWITCH_KEYS = ['window', 'kind', 'version', 'digest', 'process', 'old', 'config-sha', 'staged', 'validate',
               'staged-sha', 'target', 'idle', 'backup', 'rename-start', 'renamed', 'from', 'stopping', 'stopped',
               'starting', 'running', 'closed']
BACK_KEYS = ['window', 'kind', 'process', 'old', 'config-sha', 'staged', 'validate', 'staged-sha', 'target',
             'rename-start', 'renamed', 'from', 'stopping', 'stopped', 'starting', 'running', 'closed']


def fixture(name):
    with open(os.path.join(FIX, name), encoding='utf-8') as f:
        return f.read()


API = {'rc': 1, 'out': fixture('api-only-real.txt')}
NONAPI = {'rc': 1, 'out': fixture('non-api-real.txt')}
UNKNOWN = {'rc': 1, 'out': 'Error: failed to read config file\n'}
PASS = {'rc': 0, 'out': PASS_OUT}


def keys(lines):
    return [l.split(' ', 1)[0] for l in lines]


def value(lines, key):
    """The value of the LAST line with KEY ('' for a key with an empty value), or None."""
    vals = [l.split(' ', 1)[1] if ' ' in l else '' for l in lines if l.split(' ', 1)[0] == key]
    return vals[-1] if vals else None


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def files(g):
    """The home's files as Pool.snapshot reads them, less the two lock files (a run writes its pid into its lock)."""
    return {k: v for k, v in g.p.snapshot().items() if not k.endswith(('/pool-image.lock', '/runner-updater/lock'))}


class Rig:
    """A Pool whose production runs OLD; the registry serves OLD and NEW; a fake clock."""

    def __init__(self, test, clock=True):
        self.t = test
        self.p = p = Pool(test)
        p.curl['served'] = [OLD, NEW]
        p.production(OLD)
        p.write(p.path('logs', 'runner.log'), '')      # the validates of the production's own 03 real are not counted
        self.old = p.config()
        self.prev = p.rpath('config.toml.prev')
        self.staged = p.rpath('config.staged.toml')
        if clock:
            p.fake_clock()

    def up(self, *, prefix=()):
        return self.p.unattended('up', '--unattended', V, NEW, prefix=prefix)

    def back(self):
        return self.p.unattended('back', '--unattended')

    def calls(self, what):
        """systemctl's stop, start and restart calls."""
        return [l for l in self.p.lines('systemctl') if l.split(' ')[1:2] == [what]]

    def healthz_reads(self):
        return [c for c in self.p.calls('curl') if any(x.endswith('/healthz') for x in c['argv'])]

    def validates(self):
        return [c for c in self.p.calls('runner') if c['argv'][:1] == ['validate']]

    def unchanged(self, r, rc):
        """Nothing was changed: config.toml is the old one, nothing staged, no backup, no restart."""
        t = self.t
        t.assertEqual(r.returncode, rc, r.stdout[-3000:] + r.stderr)
        t.assertEqual(self.p.config(), self.old)
        t.assertFalse(os.path.lexists(self.staged))
        t.assertFalse(os.path.lexists(self.prev))
        t.assertEqual(self.calls('stop') + self.calls('start') + self.calls('restart'), [])

    def stopped_with(self, r, name, *says):
        """A STOP before any change: exit 1, the journal closed with `stop NAME: …`, nothing changed."""
        self.unchanged(r, 1)
        t = self.t
        t.assertIsNone(self.p.window())
        (wid, lines), = self.p.closed()
        stop = value(lines, 'stop')
        t.assertIsNotNone(stop, lines)
        t.assertTrue(stop.startswith(name + ': '), stop)
        for s in says:
            t.assertIn(s, stop)
        t.assertEqual(keys(lines)[-2:], ['stop', 'closed'])
        t.assertIn('STOP %s: ' % name, r.stdout)
        return lines

    def not_now(self, r, *says):
        self.unchanged(r, 3)
        t = self.t
        t.assertIsNone(self.p.window())
        t.assertEqual(self.p.closed(), [])
        t.assertIn('POOL IMAGE NOT NOW (up --unattended): ', r.stdout)
        for s in says:
            t.assertIn(s, r.stdout)


@needs_container
class Switch(unittest.TestCase):
    def test_up_switches_at_idle_and_journals_each_step_first(self):
        g = Rig(self)
        g.p.hooks()                                     # no hook: the dd and mv substitutes log the order
        before = g.p.unit_now()
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('POOL IMAGE DONE (up --unattended): %s' % ref(NEW), r.stdout)
        self.assertEqual(g.p.images(), [ref(NEW)] * 2)
        with open(g.prev) as f:
            self.assertEqual(f.read(), g.old)
        self.assertFalse(os.path.lexists(g.staged))
        self.assertIsNone(g.p.window())
        (wid, lines), = g.p.closed()
        self.assertEqual(keys(lines), SWITCH_KEYS, lines)
        self.assertRegex(wid, r'^[0-9]{14}-[0-9]+$')
        self.assertEqual(value(lines, 'window'), wid)
        self.assertEqual(value(lines, 'kind'), 'switch')
        self.assertEqual(value(lines, 'version'), V)
        self.assertEqual(value(lines, 'digest'), NEW)
        self.assertEqual(value(lines, 'process'), '100 %d' % before['start'])
        self.assertEqual(value(lines, 'old'), ref(OLD))
        self.assertEqual(value(lines, 'config-sha'), sha(g.old))
        self.assertEqual(value(lines, 'staged'), g.staged)
        self.assertEqual(value(lines, 'validate'), 'pre 1 PASS')
        self.assertEqual(value(lines, 'staged-sha'), sha256_file(g.p.rpath('config.toml')))
        self.assertEqual(value(lines, 'target'), ' '.join('%s=%s' % (s, ref(NEW)) for s in SETS))
        self.assertEqual(value(lines, 'idle'), 'idle')
        self.assertEqual(value(lines, 'backup'), g.prev)
        renamed = int(value(lines, 'renamed'))
        self.assertLessEqual(int(value(lines, 'rename-start')), renamed)
        self.assertGreater(int(value(lines, 'stopping')), renamed, 'the restart is past the `renamed` second')
        pid, start = map(int, value(lines, 'running').split())
        self.assertGreater(start, renamed)
        self.assertEqual(g.p.unit_now()['pid'], pid)
        self.assertEqual(g.p.unit_now()['start'], start)
        self.assertEqual((len(g.calls('stop')), len(g.calls('start')), len(g.calls('restart'))), (1, 1, 0))
        # the order: each journal line is on disk before its step; the rename, then the clock read past `renamed`,
        # then the stop
        ev = g.p.events()
        at = {e: i for i, e in reversed(list(enumerate(ev)))}
        self.assertLess(at['journal rename-start'], at['mv config.toml'])
        self.assertLess(at['mv config.toml'], at['journal renamed'])
        past = [i for i, e in enumerate(ev) if e.startswith('date ') and int(e.split()[1]) > renamed]
        self.assertTrue(past, ev)
        self.assertLess(at['journal renamed'], past[0])
        self.assertLess(past[0], at['journal stopping'])
        self.assertLess(at['journal stopping'], at['process 100 stopped'])
        self.assertLess(at['process 100 stopped'], at['journal stopped'])
        self.assertLess(at['journal stopped'], at['journal starting'])
        self.assertLess(at['journal starting'], at['process %d started %d' % (pid, start)])

    def test_the_idle_pair_is_two_reads_3_s_apart_and_the_rename_follows_the_second(self):
        g = Rig(self)
        g.p.hooks()
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        ev = g.p.events()
        reads = [i for i, e in enumerate(ev) if e == 'healthz read']
        self.assertEqual(len(reads), 2, ev)
        self.assertEqual([e for e in ev[reads[0] + 1:reads[1]] if e.startswith('sleep ')], ['sleep 3'])
        self.assertLess(reads[1], ev.index('journal idle'))
        self.assertEqual([e for e in ev[reads[1]:ev.index('mv config.toml')] if e.startswith(('healthz', 'sleep'))], [
            'healthz read'], 'nothing waits between the second read and the rename')

    def test_not_idle_stages_nothing_changes_nothing_and_exits_3(self):
        busy_main = healthz(**{'linux-ci-main': {'busy': 1}})
        cases = (
            ('a busy set on both reads', {'healthz': busy_main}, 'busy 1'),
            ('busy on the second read only', {'healthz_seq': [healthz(), busy_main]}, 'busy 1'),
            ('a set of the host that is no set of the family: busy', {'healthz': {'scale_sets': healthz()['scale_sets'] + [
                {'name': 'linux-ci-other', 'ready': True, 'idle': 0, 'busy': 2, 'metrics': {}}]}}, 'linux-ci-other'),
            ('a set not ready', {'healthz': healthz(**{'linux-ci-small': {'ready': False}})}, 'not ready'),
            ('a job assigned', {'healthz': healthz(**{'linux-ci-small': {'metrics': {'assigned_jobs': 1}}})},
             'assigned 1'),
            ('a set absent', {'healthz': {'scale_sets': healthz()['scale_sets'][:1]}}, 'absent from /healthz'),
            ('no answer', {'healthz': None}, 'two reads'),
        )
        for why, curl, says in cases:
            with self.subTest(why):
                g = Rig(self)
                g.p.curl.update(curl)
                st = os.stat(g.p.rpath('config.toml'))
                r = g.up()
                g.not_now(r, 'not idle', says)
                self.assertEqual(os.stat(g.p.rpath('config.toml')).st_mtime_ns, st.st_mtime_ns)
                self.assertEqual(len(g.validates()), 1, 'the render ran before the idle pair')

    def test_start_state_not_met_is_not_now_before_the_render(self):
        for why in ('the unit is inactive', 'the unit is disabled', 'config.toml installed after the start'):
            with self.subTest(why):
                g = Rig(self)
                if why == 'the unit is inactive':
                    g.p.set_unit(active=False)
                elif why == 'the unit is disabled':
                    g.p.set_unit(enabled=False)
                else:
                    g.p.set_unit(start=int(os.stat(g.p.rpath('config.toml')).st_mtime))   # equal: not proven
                r = g.up()
                g.not_now(r, 'START STATE')
                self.assertEqual(g.validates(), [])
                self.assertEqual(g.healthz_reads(), [])

    def test_family_lines_that_do_not_name_one_image_stop_before_anything(self):
        g = Rig(self)
        bad = g.old[::-1].replace(ref(OLD)[::-1], ref(NEW)[::-1], 1)[::-1]     # the small set's line names another
        g.p.write(g.p.rpath('config.toml'), bad, 0o600)
        g.old = bad
        g.p.set_unit(start=int(os.stat(g.p.rpath('config.toml')).st_mtime) + 1)   # START STATE holds: only the lines fail
        r = g.up()
        g.stopped_with(r, 'check failed', 'ONE runner image')
        self.assertEqual(g.validates(), [])
        self.assertEqual(g.healthz_reads(), [])

    def test_an_old_image_the_registry_does_not_serve_stops(self):
        for why, served, rc in (('it does not serve it', [NEW], 0), ('it does not answer', [OLD, NEW], 7)):
            with self.subTest(why):
                g = Rig(self)
                g.p.curl.update(served=served, registry_rc=rc)
                r = g.up()
                g.stopped_with(r, 'check failed', ref(OLD))
                self.assertEqual(g.validates(), [])

    def test_disk_below_runscaler_s_min_free_stops(self):
        for avail, ok in ((99, False), (100, True)):
            with self.subTest(avail_k=avail):
                g = Rig(self)
                g.p.disk(1000, avail)
                r = g.up()
                if ok:
                    self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                    continue
                g.stopped_with(r, 'DISK', '10%')
                self.assertEqual(g.validates(), [])
                self.assertIn('/home/root', ' '.join(g.p.lines('df')))     # RUN_USER's home: D1 and the registry

    def test_an_untested_jq_stops_new_work(self):
        g = Rig(self)
        g.p.jq_version('jq-9.9')
        r = g.up()
        g.stopped_with(r, 'untested jq', 'jq-9.9')
        self.assertEqual(g.validates(), [])
        self.assertEqual(g.healthz_reads(), [])

    def test_a_pinned_file_that_is_not_this_release_s_stops(self):
        """The PINS: what 03 runs and installs, as ~/build holds it. Changed: STOP before 03 runs. The control: the happy
        path, where every pinned file is the reviewed copy."""
        for rel in ('setup/03-runscaler.sh', 'bin/runner-start'):
            with self.subTest(rel):
                g = Rig(self)
                with open(os.path.join(g.p.build, rel), 'a') as f:
                    f.write('\n# changed\n')
                r = g.up()
                g.stopped_with(r, 'check failed', 'is not the reviewed copy', rel)
                self.assertEqual(g.validates(), [])

    def test_prevalidate_tries_three_times_20_s_apart_and_api_only_counts_as_pass(self):
        for seq, classes in (([API, API, PASS], ['API-ONLY', 'API-ONLY', 'PASS']),
                             ([API, API, API], ['API-ONLY', 'API-ONLY', 'API-ONLY']), ([PASS], ['PASS'])):
            with self.subTest(classes=classes):
                g = Rig(self)
                g.p.runner = {'seq': seq}
                r = g.up()
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                (wid, lines), = g.p.closed()
                self.assertEqual([l for l in lines if l.startswith('validate ')],
                                 ['validate pre %d %s' % (i + 1, c) for i, c in enumerate(classes)])
                self.assertEqual(len(g.validates()), len(classes))
                self.assertEqual([e for e in g.p.events() if e == 'sleep 20'], ['sleep 20'] * (len(classes) - 1))
                self.assertEqual(g.p.images(), [ref(NEW)] * 2)
                out = os.path.join(g.p.STATE, 'windows', wid + '.d', 'validate-pre-%d.out' % len(classes))
                with open(out) as f:
                    self.assertIn(seq[-1]['out'].splitlines()[0], f.read(), 'the journal keeps the WHOLE output')

    def test_a_validate_that_is_not_pass_or_api_only_stops_before_any_restart(self):
        for cls, seq in (('NON-API', [NONAPI]), ('UNKNOWN', [UNKNOWN]), ('NON-API', [API, NONAPI])):
            with self.subTest(cls, tries=len(seq)):
                g = Rig(self)
                g.p.runner = {'seq': seq}
                r = g.up()
                lines = g.stopped_with(r, 'check failed', 'VALIDATE %s' % cls)
                self.assertEqual([l for l in lines if l.startswith('validate ')][-1], 'validate pre %d %s' % (len(seq), cls))
                self.assertEqual(g.healthz_reads(), [])

    def test_a_render_that_changes_more_than_the_image_lines_stops_d3(self):
        g = Rig(self)
        g.p.pool_env(CONCURRENT=3, MAX=2)
        r = g.up()
        g.stopped_with(r, 'check failed', 'more than the runner-image lines')
        self.assertEqual(len(g.validates()), 1)
        self.assertEqual(g.healthz_reads(), [])

    def test_a_staged_file_changed_after_its_validate_is_not_renamed(self):
        g = Rig(self)
        g.p.hooks(('journal:idle', 'edit-staged'))
        r = g.up()
        g.stopped_with(r, 'check failed', 'not the file 03 validated')

    def test_a_rejected_digest_stops_and_nothing_is_staged(self):
        g = Rig(self)
        g.p.rejected(NEW + '\n')
        r = g.up()
        g.stopped_with(r, 'check failed', 'rejected')
        self.assertEqual(g.validates(), [])

    def test_a_hand_change_before_the_rename_is_hand_change_and_nothing_is_renamed(self):
        g = Rig(self)
        g.p.hooks(('journal:idle', 'edit-config'))
        r = g.up()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), g.old + '# a hand change\n')
        self.assertFalse(os.path.lexists(g.staged))
        self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), [])
        (wid, lines), = g.p.closed()
        self.assertTrue(value(lines, 'stop').startswith('HAND CHANGE: '), lines)
        self.assertNotIn('rename-start', keys(lines))

    def test_a_journal_line_that_is_not_synced_stops_before_its_step(self):
        """PLAN D1: each line is synced BEFORE its side effect, dd's exit status checked; a failure stops the window
        before that step, the journal open. `rename-start` not synced: no rename. `stopping`: no stop. The control: the
        happy path, where every sync passes."""
        for key in ('rename-start', 'stopping'):
            with self.subTest(key):
                g = Rig(self)
                g.p.hooks(('ddfail:' + key,))
                r = g.up()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertIn('injected ddfail:' + key, g.p.events())
                self.assertIn("could not record '%s'" % key, r.stdout)
                lines = g.p.window()
                self.assertEqual(keys(lines)[-1], key, 'the journal stays open, at the line that was not synced')
                if key == 'rename-start':
                    self.assertEqual(g.p.config(), g.old)
                    self.assertTrue(os.path.lexists(g.staged))
                else:
                    self.assertEqual(g.p.images(), [ref(NEW)] * 2)
                self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), [])

    def test_a_config_that_already_runs_the_digest_is_no_switch_and_its_rollback_stays(self):
        """up --unattended of the image config.toml already runs (a second call): nothing to switch, so nothing renamed or
        restarted, and config.toml.prev, the switch's rollback, is NOT overwritten with the candidate. The control: the
        first call, which switched."""
        g = Rig(self)
        self.assertEqual(g.up().returncode, 0)
        with open(g.prev) as f:
            self.assertEqual(f.read(), g.old)
        cand, unit = g.p.config(), g.p.unit_now()
        r = g.up()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        with open(g.prev) as f:
            self.assertEqual(f.read(), g.old, 'the rollback was overwritten')
        self.assertEqual(g.p.config(), cand)
        self.assertEqual(g.p.unit_now()['pid'], unit['pid'])
        lines = g.p.closed()[-1][1]
        self.assertIn('already runs', value(lines, 'end'))
        self.assertNotIn('rename-start', keys(lines))

    def test_an_open_window_journal_refuses_and_changes_nothing(self):
        g = Rig(self)
        os.makedirs(g.p.STATE, exist_ok=True)
        j = g.p.write(os.path.join(g.p.STATE, 'window'), 'window 20261103000000-1\nkind switch\n', 0o600)
        r = g.up()
        g.unchanged(r, 1)
        self.assertIn('open window journal', r.stdout)
        with open(j) as f:
            self.assertEqual(f.read(), 'window 20261103000000-1\nkind switch\n')
        self.assertEqual(g.p.closed(), [])
        self.assertEqual(g.validates(), [])

    def test_usage(self):
        g = Rig(self)
        for args in (('up', '--unattended', V), ('up', '--unattended', V, 'sha256:' + 'a' * 63),
                     ('up', '--unattended', '2.339', NEW), ('up', '--unattended', V, NEW, 'x'), ('up', '--attended', V, NEW),
                     ('up', V, NEW), ('back', '--unattended', 'x'), ('back', '--attended'), ('accept', '--unattended'),
                     ('up', '--unattended', V, ref(NEW))):
            with self.subTest(args=args):
                r = g.p.unattended(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn('usage', r.stdout)
                self.assertIn('--unattended', r.stdout)
                g.unchanged(r, 2)
                self.assertFalse(os.path.lexists(os.path.join(g.p.STATE, 'window')))

    def test_a_held_pool_image_lock_refuses(self):
        g = Rig(self)
        with open(g.p.rpath('pool-image.lock'), 'a') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            r = g.up()
        g.unchanged(r, 1)
        self.assertIn('pool-image.lock', r.stdout)
        self.assertIsNone(g.p.window())
        self.assertEqual(g.p.closed(), [])


@needs_container
class UpdaterLock(unittest.TestCase):
    """THE UPDATER LOCK (runner-release.sh's RR_LOCK): an unattended run holds it; a run whose parent holds it on fd 9
    (the updater runs pool-image.sh as its child) takes it there at once, and another holder makes it wait, saying so
    first, with nothing journaled."""

    def lock(self, g):
        os.makedirs(g.p.STATE, mode=0o700, exist_ok=True)
        return os.path.join(g.p.STATE, 'lock')

    def test_a_parent_that_holds_it_on_fd_9_shares_it(self):
        g = Rig(self)
        lock = self.lock(g)
        r = g.up(prefix=['bash', '-c', 'exec 9>> "$0" && flock -n 9 || exit 99; exec "$@"', lock])
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertNotIn('WAIT', r.stdout)

    def test_the_updater_lock_is_held_from_the_window_s_start_to_its_end(self):
        """Probed by another open of the lock (another holder's view) when `process` and `running` are on disk. The
        control: the same probe after the run reads it free."""
        g = Rig(self)
        g.p.hooks(('journal:process', 'probe-lock'), ('journal:running', 'probe-lock'))
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual([e for e in g.p.events() if e.startswith('updater lock')], ['updater lock held'] * 2)
        c = subprocess.run(['python3', '-I', '-c', 'import sys; sys.path.insert(0, sys.argv[1]); import hzlib; '
                            'hzlib.act("probe-lock")', g.p.path('stubs')], env=g.p.env(), capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stderr)
        self.assertEqual(g.p.events()[-1], 'updater lock FREE')

    def test_another_holder_makes_it_wait_with_nothing_journaled(self):
        g = Rig(self)
        lock = self.lock(g)
        f = open(lock, 'a')
        self.addCleanup(f.close)
        fcntl.flock(f, fcntl.LOCK_EX)
        g.p.files()
        p = subprocess.Popen(['bash', os.path.join(g.p.build, 'setup', 'pool-image.sh'), 'up', '--unattended', V, NEW],
                             env=g.p.env(), cwd=g.p.HOME, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, start_new_session=True)
        self.addCleanup(lambda: p.poll() is None and os.killpg(p.pid, 9))
        line = p.stdout.readline()
        while line and 'WAIT' not in line:
            line = p.stdout.readline()
        self.assertIn('updater lock', line)
        self.assertIsNone(g.p.window(), 'nothing is journaled while it waits')
        self.assertEqual(g.validates(), [])
        fcntl.flock(f, fcntl.LOCK_UN)
        out = p.communicate(timeout=600)[0]
        self.assertEqual(p.returncode, 0, out[-3000:])
        self.assertEqual(g.p.images(), [ref(NEW)] * 2)


def position(log, offset):
    """The log position {inode, offset, sha} (the sha256 of the 64 bytes before offset) as the core reads it."""
    with open(log, 'rb') as f:
        b = f.read()
    return '%d %d %s' % (os.stat(log).st_ino, offset, hashlib.sha256(b[max(0, offset - 64):offset]).hexdigest())


def restart_fact(lines):
    """facts.restart (core/README.md) from a closed window journal: from, running (`to`) and stopped; None when one
    of them is `none`."""
    f, t, s = value(lines, 'from'), value(lines, 'running'), value(lines, 'stopped')
    if 'none' in (f, t, s):
        return None
    (fp, fs), (tp, ts), (si, so, sh) = f.split(), t.split(), s.split()
    return {'from': {'pid': int(fp), 'start': int(fs)}, 'to': {'pid': int(tp), 'start': int(ts)},
            'stopped': {'inode': si, 'offset': int(so), 'sha': sh}}


@needs_container
class OwnRestart(unittest.TestCase):
    def test_stopped_is_the_log_position_between_the_old_process_and_the_new(self):
        for mode in ('up', 'back'):
            with self.subTest(mode):
                g = Rig(self)
                if mode == 'back':
                    self.assertEqual(g.up().returncode, 0)
                    g.p.curl['healthz'] = g.p.curl['busy']
                old = g.p.unit_now()
                r = g.up() if mode == 'up' else g.back()
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                lines = g.p.closed()[-1][1]
                new = g.p.unit_now()
                log = g.p.rpath('runner.log')
                with open(log, 'rb') as f:
                    text = f.read()
                first_q = text.index(b'runscaler started pid=%d' % new['pid'])
                q_line = text.rindex(b'\n', 0, first_q) + 1
                self.assertTrue(text[:q_line].endswith(b'runscaler stopped pid=%d\n' % old['pid']))
                self.assertEqual(value(lines, 'stopped'), position(log, q_line))
                self.assertEqual(value(lines, 'from'), '%d %d' % (old['pid'], old['start']))
                self.assertEqual(value(lines, 'running'), '%d %d' % (new['pid'], new['start']))
                self.assertGreater(new['start'], int(value(lines, 'renamed')))

    def test_a_runscaler_that_runs_at_the_capture_gives_stopped_none(self):
        g = Rig(self)
        g.p.hooks(('systemctl:stop-done', 'start'))      # systemd (or a person) starts it right after the stop
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        (wid, lines), = g.p.closed()
        self.assertEqual(value(lines, 'stopped'), 'none')
        self.assertIsNone(restart_fact(lines))

    def test_a_runscaler_that_starts_during_the_capture_gives_stopped_none(self):
        """It starts right after the read that found none, so the captured position may hold its first bytes: the read
        after the capture sees it, and `stopped` is none."""
        g = Rig(self)
        g.p.hooks(('systemctl:show-after-stop-1', 'start'))
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('hook systemctl:show-after-stop-1: start', g.p.events())
        (wid, lines), = g.p.closed()
        self.assertEqual(value(lines, 'stopped'), 'none')

    def test_a_process_that_started_before_the_install_is_never_the_target(self):
        """After the stop, the OLD process runs again (systemd says stopped, but it is not): no process that started
        after `renamed` is seen, so no `running` line, and the journal stays open. The control: the happy path."""
        g = Rig(self)
        g.p.hooks(('systemctl:stop-done', 'revive'))
        r = g.up()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertIn('process 100 revived', ' '.join(g.p.events()))
        lines = g.p.window()
        self.assertIsNotNone(lines)
        self.assertNotIn('running', keys(lines))
        self.assertEqual(value(lines, 'stopped'), 'none')
        self.assertIn('no runscaler started after the install', r.stdout)

    def test_the_journal_gives_the_core_its_restart_fact(self):
        """facts.restart made from the journal's from, running and stopped is one the core accepts (idle.jq reads its
        facts through lib/core.jq's facts_in). The control: an offset that is no number is refused."""
        g = Rig(self)
        self.assertEqual(g.up().returncode, 0)
        (wid, lines), = g.p.closed()
        fact = restart_fact(lines)
        core = os.path.join(g.p.build, 'core')
        reads = g.p.path('reads.json')
        g.p.write(reads, json.dumps(healthz()) + '\n' + json.dumps(healthz()) + '\n')
        for f, rc in ((fact, 0), (dict(fact, stopped=dict(fact['stopped'], offset='x')), 5)):
            with self.subTest(rc=rc):
                facts = g.p.write(g.p.path('facts.json'), json.dumps({'format': 1, 'sets': list(SETS), 'restart': f}))
                state = g.p.write(g.p.path('state.json'), '')
                r = subprocess.run(['jq', '-n', '-L', os.path.join(core, 'lib'), '-f', os.path.join(core, 'idle.jq'),
                                    '--slurpfile', 'state', state, '--slurpfile', 'facts', facts, '--slurpfile',
                                    'healthz', reads, '--arg', 'now', str(int(time.time()))],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)


@needs_container
class AroundTheRename(unittest.TestCase):
    """PLAN D5: a kill around the rename. An independent restart, and the run killed, at each point, with a busy
    /healthz: the old file is never put back, and the next call changes nothing (the journal is open: the updater's
    next pass, S2b-3, resolves it from the journal and the files asserted here)."""

    CASES = (
        # (why, hook, the journal's last key, config.toml is the candidate, STAGED left, the backup written)
        ('an independent restart before rename-start', 'journal:backup', 'backup', False, True, False),
        ('between rename-start and the rename', 'journal:rename-start', 'rename-start', False, True, True),
        ('the rename done, renamed missing', 'mv-done:config.toml', 'rename-start', True, False, True),
        ('after renamed', 'journal:renamed', 'renamed', True, False, True),
    )

    def test_a_kill_around_the_rename_leaves_what_the_next_pass_reads(self):
        for why, at, last, candidate, staged, backup in self.CASES:
            with self.subTest(why):
                g = Rig(self)
                g.p.hooks((at, 'restart', 'busy', 'kill'))
                r = g.up()
                self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
                self.assertIn('hook %s: restart busy kill' % at, g.p.events())
                lines = g.p.window()
                self.assertIsNotNone(lines, 'the window journal stays open')
                self.assertEqual(keys(lines)[-1], last, lines)
                csha = sha256_file(g.p.rpath('config.toml'))
                self.assertEqual(csha, value(lines, 'staged-sha') if candidate else value(lines, 'config-sha'))
                self.assertEqual(g.p.config() == g.old, not candidate)
                self.assertEqual(os.path.lexists(g.staged), staged)
                if backup:
                    with open(g.prev) as f:
                        self.assertEqual(f.read(), g.old)
                self.assertEqual(g.p.unit_now()['independent'], 1)
                self.assertEqual(g.calls('stop') + g.calls('start'), [])
                snap = files(g)
                for nxt in (g.up, g.back):         # the next call: the open journal, a busy pool
                    r = nxt()
                    self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                    self.assertIn('open window journal', r.stdout)
                    self.assertEqual(files(g), snap, 'the next call changed a file (the old one put back?)')
                    self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), [])

    def test_a_run_delayed_across_the_rename_still_restarts_past_renamed(self):
        g = Rig(self)
        g.p.hooks(('mv:config.toml', 'restart', 'busy'))
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        (wid, lines), = g.p.closed()
        self.assertEqual(g.p.unit_now()['independent'], 1)
        s101 = [int(e.split()[3]) for e in g.p.events() if e.startswith('process 101 started ')]
        self.assertEqual(value(lines, 'from'), '101 %d' % s101[0], 'from: the process the restart stopped')
        pid, start = map(int, value(lines, 'running').split())
        self.assertEqual(pid, 102)
        self.assertGreater(start, int(value(lines, 'renamed')))
        self.assertEqual(g.p.images(), [ref(NEW)] * 2)
        with open(g.prev) as f:
            self.assertEqual(f.read(), g.old)
        self.assertEqual((len(g.calls('stop')), len(g.calls('start'))), (1, 1), 'restarted with a busy /healthz')

    def test_a_hand_change_after_the_install_gets_no_restart(self):
        """PLAN D5 AFTER THE INSTALL: config.toml changed by hand after the rename: no restart on it, `hand-change`,
        STOP HAND CHANGE naming the hand step, the journal open. During the drain (after the stop): no start, the
        unit stays stopped. Right after the start: the process may have read either file, so it is no `running`
        target. The control: the journaled sha restarts (the happy path)."""
        for at, stops, starts in (('journal:renamed', 0, 0), ('systemctl:stop-done', 1, 0), ('systemctl:start-done', 1, 1)):
            with self.subTest(at):
                g = Rig(self)
                g.p.hooks((at, 'edit-config'))
                r = g.up()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                lines = g.p.window()
                self.assertIsNotNone(lines, 'the journal stays open')
                self.assertEqual(keys(lines)[-2:], ['hand-change', 'stop'])
                self.assertNotIn('running', keys(lines), 'a process on a file the window cannot name is no target')
                self.assertEqual(value(lines, 'hand-change'), sha256_file(g.p.rpath('config.toml')))
                self.assertTrue(value(lines, 'stop').startswith('HAND CHANGE: '))
                self.assertIn('runner-start validate', value(lines, 'stop'))
                self.assertIn('STOP HAND CHANGE: ', r.stdout)
                self.assertTrue(g.p.config().endswith('# a hand change\n'))
                self.assertEqual((len(g.calls('stop')), len(g.calls('start'))), (stops, starts))
                self.assertEqual(g.p.unit_now()['active'], stops == starts)


class BackRig(Rig):
    """A Rig after a switch to NEW (config.toml.prev holds the old config), /healthz busy."""

    def __init__(self, test):
        super().__init__(test)
        r = self.up()
        test.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.candidate = self.p.config()
        self.p.curl['healthz'] = self.p.curl['busy']
        self.p.write(self.p.path('logs', 'systemctl.log'), '')
        self.p.write(self.p.path('logs', 'curl.log'), '')
        self.p.write(self.p.path('logs', 'runner.log'), '')

    def kept(self, r):
        """Nothing restarted, config.toml is still the candidate, nothing staged."""
        t = self.t
        t.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        t.assertEqual(self.p.config(), self.candidate)
        t.assertFalse(os.path.lexists(self.p.rpath('config.rollback.toml')))
        t.assertEqual(self.calls('stop') + self.calls('start') + self.calls('restart'), [])
        t.assertIsNone(self.p.window())
        return self.p.closed()[-1][1]


@needs_container
class Back(unittest.TestCase):
    def test_back_restores_the_backup_at_once_with_no_idle_wait(self):
        g = BackRig(self)
        r = g.back()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('POOL IMAGE DONE (back --unattended): %s' % ref(OLD), r.stdout)
        self.assertEqual(g.p.config(), g.old)
        self.assertEqual(g.healthz_reads(), [], 'no idle wait')
        lines = g.p.closed()[-1][1]
        self.assertEqual(keys(lines), BACK_KEYS, lines)
        self.assertEqual(value(lines, 'kind'), 'rollback')
        self.assertEqual(value(lines, 'old'), ref(OLD))
        self.assertEqual(value(lines, 'config-sha'), sha(g.candidate))
        self.assertEqual(value(lines, 'staged-sha'), sha(g.old))
        self.assertEqual(value(lines, 'target'), ' '.join('%s=%s' % (s, ref(OLD)) for s in SETS))
        self.assertEqual(len(g.validates()), 1)
        self.assertGreater(int(value(lines, 'running').split()[1]), int(value(lines, 'renamed')))
        self.assertEqual((len(g.calls('stop')), len(g.calls('start'))), (1, 1))

    def test_a_config_that_already_is_the_rollback_restarts_nothing(self):
        """A second back (a person's, after the updater's): config.toml already is config.toml.prev and runs, so it is
        done (exit 0, `running` the process that runs) with no restart. The control: the first back restarted."""
        g = BackRig(self)
        self.assertEqual(g.back().returncode, 0)
        unit = g.p.unit_now()
        r = g.back()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.unit_now()['pid'], unit['pid'], 'it restarted')
        self.assertEqual((len(g.calls('stop')), len(g.calls('start'))), (1, 1), 'only the first back restarted')
        lines = g.p.closed()[-1][1]
        self.assertEqual(keys(lines)[-2:], ['running', 'closed'])
        self.assertEqual(value(lines, 'running'), '%d %d' % (unit['pid'], unit['start']))
        self.assertNotIn('rename-start', keys(lines))

    def test_api_only_three_times_counts_as_pass(self):
        g = BackRig(self)
        g.p.runner = {'seq': [API, API, API]}
        r = g.back()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), g.old)
        self.assertEqual([l for l in g.p.closed()[-1][1] if l.startswith('validate ')],
                         ['validate pre %d API-ONLY' % i for i in (1, 2, 3)])

    def test_non_api_is_rollback_failed_before_any_restart(self):
        for seq in ([NONAPI], [API, NONAPI]):
            with self.subTest(tries=len(seq)):
                g = BackRig(self)
                g.p.runner = {'seq': seq}
                r = g.back()
                lines = g.kept(r)
                self.assertTrue(value(lines, 'stop').startswith('ROLLBACK FAILED: '), lines)
                self.assertIn('STOP ROLLBACK FAILED: ', r.stdout)
                self.assertNotIn('rename-start', keys(lines))

    def test_unknown_is_no_stop_and_the_caller_tries_again(self):
        g = BackRig(self)
        g.p.runner = {'seq': [UNKNOWN]}
        r = g.back()
        lines = g.kept(r)
        self.assertIsNone(value(lines, 'stop'), lines)
        self.assertIn('UNKNOWN', value(lines, 'end'))
        self.assertNotRegex(r.stdout, r'(?m)^STOP ')

    def test_a_rollback_that_cannot_be_made_is_rollback_failed(self):
        def no_prev(g):
            os.remove(g.prev)

        def prev_with_other_numbers(g):
            with open(g.prev) as f:
                t = f.read()
            g.p.write(g.prev, t.replace('max-runners = 3', 'max-runners = 2'), 0o600)

        def not_served(g):
            g.p.curl['served'] = [NEW]
        for why, change in (('no config.toml.prev', no_prev), ('it differs in more than the image', prev_with_other_numbers),
                            ('the registry does not serve its image', not_served)):
            with self.subTest(why):
                g = BackRig(self)
                change(g)
                r = g.back()
                lines = g.kept(r)
                self.assertTrue(value(lines, 'stop').startswith('ROLLBACK FAILED: '), lines)

    def test_a_pending_hand_edit_is_hand_change(self):
        """config.toml installed after runscaler started (a hand 03 run): the rollback would replace it unseen. The
        control: the first cell, whose config.toml runs."""
        g = BackRig(self)
        g.p.set_unit(start=int(os.stat(g.p.rpath('config.toml')).st_mtime))
        r = g.back()
        lines = g.kept(r)
        self.assertTrue(value(lines, 'stop').startswith('HAND CHANGE: '), lines)

    def test_a_unit_a_person_stopped_or_disabled_is_rollback_pending(self):
        for kw in ({'active': False}, {'enabled': False}):
            with self.subTest(**kw):
                g = BackRig(self)
                g.p.set_unit(**kw)
                r = g.back()
                lines = g.kept(r)
                self.assertIsNone(value(lines, 'stop'), lines)
                self.assertIn('rollback pending: CI disabled by a person', value(lines, 'end'))

    def test_a_hand_change_after_the_rollback_s_install_gets_no_restart(self):
        g = BackRig(self)
        g.p.hooks(('journal:renamed', 'edit-config'))
        r = g.back()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        lines = g.p.window()
        self.assertEqual(keys(lines)[-2:], ['hand-change', 'stop'])
        self.assertEqual(g.calls('stop') + g.calls('start'), [])


class Text(unittest.TestCase):
    def header(self):
        with open(PIMG) as f:
            return f.read().split('\nset -uo pipefail\n', 1)[0]

    def test_the_header_names_both_modes_their_journal_and_exit_codes(self):
        h = self.header()
        for s in ('up --unattended VERSION DIGEST', 'back --unattended', '~/.local/state/runner-updater/window'):
            self.assertIn(s, h)
        for k in sorted(set(SWITCH_KEYS + BACK_KEYS + ['hand-change', 'stop', 'end'])):
            self.assertRegex(h, r'#\s+\[?%s[ \]]' % re.escape(k), 'the header names no journal line %s' % k)
        for code in ('0', '1', '2', '3'):
            self.assertRegex(h, r'#\s+%s\s' % code, 'the header names no exit code %s' % code)

    def test_the_readme_says_what_the_journal_shows_and_how_back_is_used_by_hand(self):
        with open(README) as f:
            text = f.read()
        sec = text.split('\n## The updater\'s switch and rollback\n', 1)[1].split('\n## ', 1)[0]
        self.assertIn('~/.local/state/runner-updater/window', sec)
        self.assertIn("ssh <RS_USER>@<host> 'bash ~/build/setup/pool-image.sh back --unattended'", sec)
        for k in ('rename-start', 'renamed', 'stopped', 'running', 'hand-change'):
            self.assertIn('`%s' % k, sec)

    def test_the_install_line_ships_the_core(self):
        with open(README) as f:
            line = [l for l in f.read().splitlines() if l.strip().startswith('COPYFILE_DISABLE=1 tar -C linux-docker')]
        self.assertEqual(len(line), 1)
        self.assertIn(' setup/tls-excluded-spki core |', line[0])


if __name__ == '__main__':
    unittest.main()
