"""pool-image.sh's two UNATTENDED window modes, the runner-image updater's switch and rollback on the Linux host (plan D1,
D5, D6; the changed-lines list, items 21, 24, 26, "For S2b-2b" and "For S2b-3"; S2b-3c-1 D-a, D-b (a), D-h and its r3
FOLD). RECOVER, the third mode, has its own module (test_recover.py); a SIGKILL after each journal line, test_kills.py.

- THE UPDATER'S CHILD (D-a): `up|back|recover --unattended` run only as the child of a process that holds the updater
  lock on fd 9 (runner-updater): fd 9 is the lock file, a FRESH open of it cannot take it, and fd 9 can. Opus r2 F9's
  five callers: no fd 9, a shell's own unlocked fd 9, the child of a holder (PASS), its own open while another holds the
  lock, and the flock(1) idiom (PASS: the named residual). Every other cell runs the window as the child of a holder.
- `up --unattended VERSION DIGEST`: it journals runscaler's process (step 1), then the checks (FAMILY LINES from the live
  config, START STATE, DISK, the tested jq), `03-runscaler.sh render DIGEST STAGED` with PRE-VALIDATE's tries (API-ONLY
  after 3 tries counts as PASS; anything else: STOP before any restart, nothing installed), D3, the IDLE pair; then at
  once: THE BACKUP (config.toml.prev), `rename-start`, the install time, the rename, `renamed`, and the restart.
  `target-content` (the CONTENT sha of the TARGET: whole-line comments and blank lines left out) comes before `backup`.
  config.toml already on DIGEST: no switch; done only when it RUNS, checked once after the journal lines.
- `back --unattended --why r1|r1-connect|back [--verdict FILE] [--old-version V]`: the rollback to config.toml.prev; its
  `why`, `verdict` (FILE copied to the window's folder, by sha), `old-version` and `target-version` (the build record of
  config.toml.prev's digest) come before any effect; no `--why` is a usage error. An enabled unit that is inactive or
  failed with no process goes on (operator (1)); a disabled one is "rollback pending".
- THE CLOSING LINES (D-b (a)): every close writes a switch's `prev SHA` (config.toml.prev's sha then), `installed SHA
  CONTENT CLASS` (target-running after `running`, from the window's own last TARGET check, never a new read; pre, other
  or none before the rename), then `closed E`, and the journal STAYS at WINDOW (the updater's apply step archives it). A
  window refuses on a closed journal with its own text.
- THE RESTART: `from`, `stopping`, the stop, `stopped`, the unit still enabled (else CI DISABLED, no start), `starting`,
  the start, `running` only when runscaler RUNS: /healthz lists every set on two reads 3 s apart and the same process
  started after `renamed` is there before and after them (one `active` read is no proof: Type=simple + Restart=always).
  No RUNS in 10 min: `pre-close-failure`, the journal open.
- Each validate try under `timeout -k 10 120` in its own process group, the updater lock (fd 9) never reaching the
  validate: a cut try is UNKNOWN.
- Each check of a file comes after the journal line of the step it guards, right before that step, and a copy is checked
  after it is made; around the rename an independent restart and a kill leave what RECOVER reads.

Every cell runs the real scripts (pin lines rewritten) in a throwaway container (support.Pool), with a fake clock: no
cell asserts a time it waited, only the order of the journal's lines and the clock reads the substitutes gave. The
one exception is InstallTime, on the REAL clock (the fake one starts ahead of every real mtime): it asserts the order
of whole seconds, never a duration.
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

SWITCH_KEYS = ['window', 'kind', 'version', 'digest', 'process', 'old', 'config-sha', 'start-state', 'staged',
               'validate', 'staged-sha', 'target', 'target-content', 'idle', 'backup', 'rename-start', 'renamed', 'from',
               'stopping', 'stopped', 'starting', 'running', 'prev', 'installed', 'closed']
BACK_KEYS = ['window', 'kind', 'why', 'verdict', 'old-version', 'target-version', 'process', 'old', 'config-sha',
             'start-state', 'staged', 'validate', 'staged-sha', 'target', 'target-content', 'backup', 'rename-start',
             'renamed', 'from', 'stopping', 'stopped', 'starting', 'running', 'installed', 'closed']


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


def content(text):
    """PLAN D1's CONTENT sha: the lines whose first non-blank character is not `#` and that are not blank, each with its
    newline (the Studio's ru_w_shas)."""
    kept = [l for l in text.split('\n') if not re.match(r'^[ \t]*(#|$)', l)]
    return sha(''.join(l + '\n' for l in kept))


def installed(lines):
    """The `installed` line: (SHA, CONTENT, CLASS)."""
    v = value(lines, 'installed')
    return tuple(v.split(' ')) if v is not None else None


def alive(pid):
    """The process PID runs (a zombie, ended and not yet reaped by the container's first process, does not)."""
    try:
        with open('/proc/%d/stat' % pid) as f:
            return f.read().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return False


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
        self.archived = 0
        if clock:
            p.fake_clock()

    def up(self, **kw):
        return self.p.unattended('up', '--unattended', V, NEW, **kw)

    def back(self, *more, why='back', **kw):
        return self.p.unattended('back', '--unattended', '--why', why, *more, **kw)

    def archive(self):
        """The updater's apply step's last act on a closed journal (B2 builds it): archived to windows/ID."""
        self.p.archive()
        self.archived += 1

    def done(self):
        """(ID, lines) of the CLOSED window journal: it stays at WINDOW (pool-image.sh archives nothing: the apply step
        does), its last line `closed`, the line before it `installed`, and before that a switch's `prev`."""
        t = self.t
        t.assertEqual(len(self.p.closed()), self.archived, 'pool-image.sh archived a window journal')
        lines = self.p.window()
        t.assertIsNotNone(lines, 'no window journal at WINDOW')
        t.assertEqual(keys(lines)[-1], 'closed', lines)
        t.assertEqual(keys(lines)[-2], 'installed', lines)
        t.assertRegex(lines[-2], r'^installed ([0-9a-f]{64}|none) ([0-9a-f]{64}|none) '
                                 r'(target-running|target-idle|target-old|target-failed|pre|other|none)$')
        if value(lines, 'kind') == 'switch':
            t.assertEqual(keys(lines)[-3], 'prev', lines)
            t.assertRegex(lines[-3], r'^prev ([0-9a-f]{64}|none)$')
        else:
            t.assertNotIn('prev', keys(lines))
        return value(lines, 'window'), lines

    def body(self, lines):
        """The journal's lines before its closing lines (prev, installed, closed)."""
        n = 3 if value(lines, 'kind') == 'switch' else 2
        return lines[:-n]

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

    def stopped_with(self, r, name, *says, cls='pre'):
        """A STOP before any change: exit 1, the journal closed with `stop NAME: …` and its closing lines (CLASS: what
        config.toml is), nothing changed."""
        self.unchanged(r, 1)
        t = self.t
        wid, lines = self.done()
        stop = value(lines, 'stop')
        t.assertIsNotNone(stop, lines)
        t.assertTrue(stop.startswith(name + ': '), stop)
        for s in says:
            t.assertIn(s, stop)
        t.assertEqual(keys(self.body(lines))[-1], 'stop')
        t.assertEqual(installed(lines), (sha(self.old), content(self.old), cls), lines)
        t.assertEqual(value(lines, 'prev'), 'none', 'config.toml.prev was never written')
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
        wid, lines = g.done()
        self.assertEqual(keys(lines), SWITCH_KEYS, lines)
        self.assertRegex(wid, r'^[0-9]{14}-[0-9]+$')
        self.assertEqual(value(lines, 'kind'), 'switch')
        self.assertEqual(value(lines, 'version'), V)
        self.assertEqual(value(lines, 'digest'), NEW)
        self.assertEqual(value(lines, 'process'), '100 %d' % before['start'])
        self.assertEqual(value(lines, 'old'), ref(OLD))
        self.assertEqual(value(lines, 'config-sha'), sha(g.old))
        self.assertEqual(value(lines, 'staged'), g.staged)
        self.assertEqual(value(lines, 'validate'), 'pre 1 PASS')
        cand = g.p.config()
        self.assertEqual(value(lines, 'staged-sha'), sha(cand))
        self.assertEqual(value(lines, 'target'), ' '.join('%s=%s' % (s, ref(NEW)) for s in SETS))
        self.assertEqual(value(lines, 'target-content'), content(cand))
        self.assertNotEqual(content(cand), sha(cand), 'the cell tells the CONTENT sha from the sha (a comment line)')
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
        # the closing lines: config.toml.prev's sha then; the TARGET, from the last TARGET check, runs
        self.assertEqual(value(lines, 'prev'), sha(g.old))
        self.assertEqual(installed(lines), (sha(cand), content(cand), 'target-running'))
        # the order: each journal line is on disk before its step; the rename, then the clock read past `renamed`,
        # then the stop
        ev = g.p.events()
        at = {e: i for i, e in reversed(list(enumerate(ev)))}
        self.assertLess(at['journal target-content'], at['journal backup'])
        self.assertLess(at['journal backup'], at['mv config.toml.prev'])
        self.assertLess(at['mv config.toml.prev'], at['journal rename-start'])
        self.assertLess(at['journal rename-start'], at['touch config.staged.toml'])
        self.assertLess(at['touch config.staged.toml'], at['mv config.toml'])
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
        self.assertLess(at['journal running'], at['journal prev'])
        self.assertLess(at['journal prev'], at['journal installed'])
        self.assertLess(at['journal installed'], at['journal closed'])

    def test_the_idle_pair_is_two_reads_3_s_apart_and_the_rename_follows_the_second(self):
        g = Rig(self)
        g.p.hooks()
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        ev = g.p.events()
        end = ev.index('journal running')
        reads = [i for i, e in enumerate(ev[:ev.index('journal backup')]) if e == 'healthz read']
        self.assertEqual(len(reads), 2, ev)
        self.assertEqual([e for e in ev[reads[0] + 1:reads[1]] if e.startswith('sleep ')], ['sleep 3'])
        self.assertLess(reads[1], ev.index('journal idle'))
        self.assertEqual([e for e in ev[reads[1]:ev.index('mv config.toml')] if e.startswith(('healthz', 'sleep'))], [
            'healthz read'], 'nothing waits between the second read and the rename')
        self.assertLess(ev.index('mv config.toml'), end)

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
        """A STOP before `config-sha`: its closing class is none (the journal has no pre-window sha to compare)."""
        g = Rig(self)
        bad = g.old[::-1].replace(ref(OLD)[::-1], ref(NEW)[::-1], 1)[::-1]     # the small set's line names another
        g.p.write(g.p.rpath('config.toml'), bad, 0o600)
        g.old = bad
        g.p.set_unit(start=int(os.stat(g.p.rpath('config.toml')).st_mtime) + 1)   # START STATE holds: only the lines fail
        r = g.up()
        lines = g.stopped_with(r, 'check failed', 'ONE runner image', cls='none')
        self.assertNotIn('config-sha', keys(lines))
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
        """`jq --version` must be a CORE row of core/TESTED_JQ: a version it does not list, a watchdog-only row (jq-1.6:
        the core does not run under it), and no jq at all each STOP before the render. The STOP names the jq to test
        (JQ=<its path>), and with no jq it names none (no empty `JQ=`): it says to install one. The control: the happy
        path, under the image's jq (a core row)."""
        for version, says in (('jq-9.9', 'jq-9.9'), ('jq-1.6', 'jq-1.6'), (None, 'TESTED_JQ')):
            with self.subTest(version=version):
                g = Rig(self)
                g.p.jq_version(version)
                r = g.up()
                lines = g.stopped_with(r, 'untested jq', says)
                self.assertEqual(g.validates(), [])
                self.assertEqual(g.healthz_reads(), [])
                stop = value(lines, 'stop')
                if version is None:
                    self.assertNotIn('JQ=', stop + r.stdout, 'a STOP with no jq names no JQ=')
                    self.assertIn('install', stop)
                else:
                    self.assertRegex(stop, r'\(JQ=/\S+ python3 ', 'the STOP names the jq to test by its path')

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
                wid, lines = g.done()
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
        """The closing class is other: config.toml is not the window's pre-window file (`config-sha`)."""
        g = Rig(self)
        g.p.hooks(('journal:idle', 'edit-config'))
        r = g.up()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        hand = g.old + '# a hand change\n'
        self.assertEqual(g.p.config(), hand)
        self.assertFalse(os.path.lexists(g.staged))
        self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), [])
        wid, lines = g.done()
        self.assertTrue(value(lines, 'stop').startswith('HAND CHANGE: '), lines)
        self.assertNotIn('rename-start', keys(lines))
        self.assertEqual(installed(lines), (sha(hand), content(hand), 'other'))

    def test_a_hand_change_at_the_backup_line_is_hand_change_and_writes_no_rollback(self):
        """Opus r1 F3: config.toml changed once `backup` is synced (before the copy): the COPY is checked against
        `config-sha` after it is made, so the hand change becomes no rollback. A closed STOP HAND CHANGE, no
        `rename-start`, no restart, config.toml the hand change, and no config.toml.prev (nor its temp copy) is left.
        The control: the happy path, whose config.toml.prev is the window-start config (sha `config-sha`)."""
        g = Rig(self)
        g.p.hooks(('journal:backup', 'edit-config'))
        r = g.up()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), g.old + '# a hand change\n')
        self.assertFalse(os.path.lexists(g.prev), 'a rollback was written')
        self.assertFalse(os.path.lexists(g.prev + '.tmp'))
        self.assertFalse(os.path.lexists(g.staged))
        self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), [])
        wid, lines = g.done()
        self.assertEqual(keys(g.body(lines))[-2:], ['backup', 'stop'], lines)
        self.assertTrue(value(lines, 'stop').startswith('HAND CHANGE: '), lines)
        self.assertIn('STOP HAND CHANGE: ', r.stdout)
        self.assertEqual(installed(lines)[2], 'other')
        self.assertEqual(value(lines, 'prev'), 'none')

    def test_a_core_that_cannot_decide_ends_the_window_and_switches_nothing(self):
        """Opus r1 F2: the core is not pinned, so this branch alone keeps a core that fails, or that answers a verdict
        other than idle and not-idle, from reading as IDLE: an idle.jq that does not compile, and one that answers
        `wait`. Each: exit 1, the journal closed with `end the decision core could not decide IDLE: …`, no `idle` and no
        `rename-start`, no stop or start, config.toml unchanged, STAGED removed. The control: the happy path, where the
        core says idle and the switch happens."""
        for why, prog in (('it does not compile', 'this is not jq (\n'),
                          ('it answers wait', '{"verdict": "wait", "reason": "a test core that waits"}\n')):
            with self.subTest(why):
                g = Rig(self)
                g.p.write(os.path.join(g.p.build, 'core', 'idle.jq'), prog)
                r = g.up()
                g.unchanged(r, 1)
                wid, lines = g.done()
                self.assertEqual(keys(g.body(lines))[-1], 'end', lines)
                self.assertTrue(value(lines, 'end').startswith('the decision core could not decide IDLE: '), lines)
                self.assertNotIn('idle', keys(lines))
                self.assertNotIn('rename-start', keys(lines))
                self.assertEqual(len(g.healthz_reads()), 2, 'the pair was read, and the core asked')
                self.assertIn('END the decision core could not decide IDLE: ', r.stdout)
                self.assertEqual(installed(lines)[2], 'pre')

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

    def test_a_config_that_already_names_the_digest_is_no_switch_and_its_rollback_stays(self):
        """up --unattended of the image config.toml already names (a second call, once the apply step archived the
        first): nothing to switch, so nothing renamed or restarted, and config.toml.prev, the switch's rollback, is NOT
        overwritten with the candidate (Opus r1 F4):
        - a runscaler that started after config.toml's install RUNS it: done, exit 0, `running` that process, and the
          closing lines name config.toml as the pre-window file (pre: there is no `target` line);
        - the unit stopped, or its process started at (or before) the install: not done (exit 1, `end`), and no line
          says that it runs.
        The control: the first call, to another digest, which switched."""
        for why in ('a process started after the install runs it', 'the unit is stopped',
                    'its process started at the install'):
            with self.subTest(why):
                g = Rig(self)
                self.assertEqual(g.up().returncode, 0)
                g.archive()
                with open(g.prev) as f:
                    self.assertEqual(f.read(), g.old)
                prev = os.stat(g.prev).st_mtime_ns
                if why == 'the unit is stopped':
                    g.p.set_unit(active=False)
                elif why == 'its process started at the install':
                    g.p.set_unit(start=int(os.stat(g.p.rpath('config.toml')).st_mtime))
                cand, unit = g.p.config(), g.p.unit_now()
                calls = g.calls('stop') + g.calls('start') + g.calls('restart')
                r = g.up()
                with open(g.prev) as f:
                    self.assertEqual(f.read(), g.old, 'the rollback was overwritten')
                self.assertEqual(os.stat(g.prev).st_mtime_ns, prev)
                self.assertEqual(g.p.config(), cand)
                self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), calls)
                wid, lines = g.done()
                self.assertNotIn('rename-start', keys(lines))
                self.assertNotIn('target', keys(lines))
                self.assertEqual(installed(lines), (sha(cand), content(cand), 'pre'))
                self.assertEqual(value(lines, 'prev'), sha(g.old))
                if why == 'a process started after the install runs it':
                    self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                    self.assertEqual(keys(g.body(lines))[-1], 'running', lines)
                    self.assertEqual(value(lines, 'running'), '%d %d' % (unit['pid'], unit['start']))
                    self.assertIn('POOL IMAGE DONE (up --unattended): %s' % ref(NEW), r.stdout)
                    continue
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertEqual(keys(g.body(lines))[-1], 'end', lines)
                self.assertNotIn('running', keys(lines))
                for text in (r.stdout, '\n'.join(lines)):
                    self.assertNotIn('already runs', text)
                    self.assertNotIn('DONE', text)

    def test_an_open_window_journal_refuses_and_changes_nothing(self):
        g = Rig(self)
        os.makedirs(g.p.STATE, exist_ok=True)
        j = g.p.write(os.path.join(g.p.STATE, 'window'), 'window 20261103000000-1\nkind switch\n', 0o600)
        r = g.up()
        g.unchanged(r, 1)
        self.assertIn('open window journal', r.stdout)
        self.assertIn('RECOVER', r.stdout)
        self.assertNotIn('not applied', r.stdout)
        with open(j) as f:
            self.assertEqual(f.read(), 'window 20261103000000-1\nkind switch\n')
        self.assertEqual(g.p.closed(), [])
        self.assertEqual(g.validates(), [])

    def test_a_closed_window_journal_not_yet_applied_refuses_with_its_own_text(self):
        """D-b: a window's journal stays at WINDOW once closed, until the updater's apply step archives it. A window
        refuses on it, saying so ("closed, not applied: the updater's next pass applies it"), never "open". Both modes.
        The control: the open journal of the cell above."""
        for mode in ('up', 'back'):
            with self.subTest(mode):
                g = Rig(self)
                os.makedirs(g.p.STATE, exist_ok=True)
                text = 'window 20261103000000-1\nkind switch\nend nothing\nprev none\ninstalled %s %s pre\nclosed 9\n' % (
                    sha(g.old), content(g.old))
                j = g.p.write(os.path.join(g.p.STATE, 'window'), text, 0o600)
                r = g.up() if mode == 'up' else g.back()
                g.unchanged(r, 1)
                self.assertIn("closed, not applied: the updater's next pass applies it", r.stdout)
                self.assertNotIn('open window journal', r.stdout)
                with open(j) as f:
                    self.assertEqual(f.read(), text)
                self.assertEqual(g.validates(), [])

    def test_usage(self):
        g = Rig(self)
        verdict = g.p.write(g.p.path('verdict.json'), '{}\n')
        for args in (('up', '--unattended', V), ('up', '--unattended', V, 'sha256:' + 'a' * 63),
                     ('up', '--unattended', '2.339', NEW), ('up', '--unattended', V, NEW, 'x'), ('up', '--attended', V, NEW),
                     ('up', V, NEW), ('back', '--unattended', 'x'), ('back', '--attended'), ('accept', '--unattended'),
                     ('up', '--unattended', V, ref(NEW)),
                     ('back', '--unattended'), ('back', '--unattended', '--why'), ('back', '--unattended', '--why', 'r2'),
                     ('back', '--unattended', '--why', 'back', '--why', 'back'),
                     ('back', '--unattended', '--why', 'r1', '--old-version', '2.339'),
                     ('back', '--unattended', '--why', 'r1', '--verdict', g.p.path('no-such-file')),
                     ('back', '--unattended', '--why', 'r1', '--verdict'),
                     ('back', '--unattended', '--why', 'r1', '--verdict', verdict, '--verdict', verdict),
                     ('back', '--unattended', '--why', 'r1', 'x'),
                     ('recover', '--unattended', 'x'), ('recover',), ('recover', '--attended')):
            with self.subTest(args=args):
                r = g.p.unattended(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn('usage', r.stdout)
                self.assertIn('--unattended', r.stdout)
                self.assertIn('--why r1|r1-connect|back', r.stdout)
                self.assertIn('recover --unattended', r.stdout)
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
class UpdaterOnly(unittest.TestCase):
    """D-a, THE UPDATER'S CHILD: the unattended modes are the updater's only. They run when fd 9 is the updater lock, a
    FRESH open of the lock cannot take it (someone holds it), and fd 9 can (this open file description is the holder's).
    Opus r2 F9's five callers, as measured there: 1 no fd 9: REFUSE; 2 a shell's own fd 9 on the lock, held by nobody:
    REFUSE (flock -n 9 alone would TAKE it); 3 the child of a holder: PASS; 4 its own open of the lock while another
    process holds it: REFUSE (it never waits any more); 5 the flock(1) idiom, a shell that took the lock on fd 9 itself:
    PASS (the named residual: no fd test tells it from the updater). Also fd 9 on another file: REFUSE. Each REFUSE: exit
    1, nothing journaled, nothing changed, the line names the updater. up, back and recover."""

    def callers(self, g):
        lock = os.path.join(Pool.STATE, 'lock')
        other = g.p.path('tmp', 'not-the-lock') if g else None
        mk = 'install -d -m 700 "${0%/*}" && '
        return (('1 no fd 9', (), False),
                ('2 a shell that opened the lock on fd 9 and holds nothing', ['bash', '-c', mk + 'exec 9>> "$0" && exec "$@"',
                                                                             lock], False),
                ('3 the child of a holder', None, True),
                ('4 its own open while another holds the lock', ['timeout', '-k', '5', '60', 'bash', '-c',
                                                                 mk + 'exec 9>> "$0" && exec "$@"', lock], False),
                ('5 the flock(1) idiom', ['bash', '-c', mk + 'exec 9>> "$0" && flock -n 9 || exit 99; exec "$@"', lock],
                 True),
                ('fd 9 on another file, locked', ['bash', '-c', 'exec 9>> "$0" && flock -n 9 || exit 99; exec "$@"',
                                                  other], False),
                ('4 fd 9 on another file while another holds the lock', ['bash', '-c',
                                                                         'exec 9>> "$0" && flock -n 9 || exit 99; exec "$@"',
                                                                         other], False))

    def refused(self, g, r, why):
        self.assertEqual(r.returncode, 1, '%s: %s' % (why, r.stdout[-3000:] + r.stderr))
        self.assertIn("REFUSE", r.stdout)
        self.assertIn("the updater's only", r.stdout)
        self.assertNotIn('WAIT', r.stdout)
        self.assertIsNone(g.p.window(), 'a refused run journaled')
        self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), [])
        self.assertEqual(g.validates(), [])

    ROWS = 7

    def test_up_runs_only_as_the_updater_s_child(self):
        for i in range(self.ROWS):
            g = Rig(self)
            why, prefix, ok = self.callers(g)[i]
            with self.subTest(why):
                os.makedirs(g.p.STATE, mode=0o700, exist_ok=True)
                with open(os.path.join(g.p.STATE, 'lock'), 'a') as other:
                    if why.startswith('4 '):
                        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    r = g.up(prefix=prefix)
                if ok:
                    self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                    self.assertEqual(g.p.images(), [ref(NEW)] * 2)
                    continue
                self.refused(g, r, why)
                self.assertEqual(g.p.config(), g.old)
                self.assertEqual(g.p.closed(), [])

    def test_back_and_recover_run_only_as_the_updater_s_child(self):
        for mode in ('back', 'recover'):
            for i in range(self.ROWS):
                if self.callers(None)[i][2]:
                    continue                   # PASS: every other cell of back and recover runs as row 3
                g = BackRig(self)
                why, prefix, ok = self.callers(g)[i]
                with self.subTest(mode, caller=why):
                    with open(os.path.join(g.p.STATE, 'lock'), 'a') as other:
                        if why.startswith('4 '):
                            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        r = g.back(prefix=prefix) if mode == 'back' else g.p.recover(prefix=prefix)
                    self.refused(g, r, why)
                    self.assertEqual(g.p.config(), g.candidate)

    def test_a_parent_that_holds_it_on_fd_9_shares_it(self):
        g = Rig(self)
        r = g.up()
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
                    g.archive()
                    g.p.curl['healthz'] = g.p.curl['busy']
                old = g.p.unit_now()
                r = g.up() if mode == 'up' else g.back()
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                lines = g.done()[1]
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
        wid, lines = g.done()
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
        wid, lines = g.done()
        self.assertEqual(value(lines, 'stopped'), 'none')

    def test_a_process_that_started_before_the_install_is_never_the_target(self):
        """After the stop, the OLD process runs again (systemd says stopped, but it is not): no process that started
        after `renamed` RUNS, so no `running` line; in 10 min of the clock, one `pre-close-failure` and the journal stays
        open (RECOVER's next START is the second try). The control: the happy path."""
        g = Rig(self)
        g.p.hooks(('systemctl:stop-done', 'revive'))
        r = g.up()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertIn('process 100 revived', ' '.join(g.p.events()))
        lines = g.p.window()
        self.assertIsNotNone(lines)
        self.assertNotIn('running', keys(lines))
        self.assertNotIn('closed', keys(lines))
        self.assertEqual(keys(lines)[-2:], ['starting', 'pre-close-failure'], lines)
        self.assertEqual(value(lines, 'stopped'), 'none')
        self.assertIn('no runscaler', r.stdout)

    def test_the_journal_gives_the_core_its_restart_fact(self):
        """facts.restart made from the journal's from, running and stopped is one the core accepts (idle.jq reads its
        facts through lib/core.jq's facts_in). The control: an offset that is no number is refused."""
        g = Rig(self)
        self.assertEqual(g.up().returncode, 0)
        wid, lines = g.done()
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
class Runs(unittest.TestCase):
    """r3 FOLD RUNS (Opus r3 F1, Codex r3 F3): the window's `running` needs runscaler to RUN: /healthz answers and lists
    every set config.toml names on two reads 3 s apart, and the same "PID START" is there before and after them, START
    after `renamed`. runscaler.service is Type=simple with Restart=always: a runner-start that REFUSEs is `active` for a
    second of each 31 (a fresh ActiveEnterTimestamp each time), and one that hangs is `active` throughout; neither serves
    /healthz. Each: no `running` in 10 min of the clock, `pre-close-failure`, the journal open, exit 1. The control: a
    runner-start that serves: `running` at once. Both modes."""

    def run_with(self, mode, runner):
        g = BackRig(self) if mode == 'back' else Rig(self)
        g.p.set_unit(runner='serves')                   # /healthz from now on follows the unit
        g.p.hooks(('journal:starting', runner))
        r = g.back() if mode == 'back' else g.up()
        return g, r

    def test_a_crash_loop_or_a_hang_is_no_running(self):
        for mode in ('up', 'back'):
            for runner in ('crash', 'hang'):
                with self.subTest(mode, runner=runner):
                    g, r = self.run_with(mode, runner)
                    self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                    lines = g.p.window()
                    self.assertNotIn('running', keys(lines), lines)
                    self.assertEqual(keys(lines)[-2:], ['starting', 'pre-close-failure'], lines)
                    if runner == 'crash':      # the unit WAS active, with a start after `renamed`, at some read
                        actives = [e for e in g.p.events() if e.startswith('process ') and ' started ' in e]
                        self.assertTrue(actives)
                    reads = [c for c in g.healthz_reads()]
                    self.assertTrue(reads, 'RUNS read /healthz')

    def test_control_a_runner_start_that_serves_is_running(self):
        for mode in ('up', 'back'):
            with self.subTest(mode):
                g, r = self.run_with(mode, 'serve')
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                lines = g.done()[1]
                self.assertEqual(keys(g.body(lines))[-1], 'running')
                self.assertEqual(installed(lines)[2], 'target-running')


@needs_container
class AroundTheRename(unittest.TestCase):
    """PLAN D5: a kill around the rename. An independent restart, and the run killed, at each point, with a busy
    /healthz: the old file is never put back, and the next call changes nothing (the journal is open: RECOVER ends it,
    test_recover.py, from the journal and the files asserted here)."""

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
        wid, lines = g.done()
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

    def test_an_edit_after_running_is_no_hand_change_of_the_window(self):
        """Opus r3 F14 (a): the closing class comes from the window's own last TARGET check (the one right before
        `running`), never a new read after it: an edit between `running` and `installed` closes as target-running with
        the TARGET's sha and content. The control: the edit right after the start (the cell above) is a hand change."""
        g = Rig(self)
        g.p.hooks(('journal:running', 'edit-config'))
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        wid, lines = g.done()
        self.assertTrue(g.p.config().endswith('# a hand change\n'))
        self.assertEqual(installed(lines), (value(lines, 'staged-sha'), value(lines, 'target-content'),
                                            'target-running'))
        self.assertNotIn('hand-change', keys(lines))


class BackRig(Rig):
    """A Rig after a switch to NEW (config.toml.prev holds the old config; its journal applied and archived, as the
    updater's apply step does), /healthz busy."""

    def __init__(self, test, clock=True):
        super().__init__(test, clock)
        r = self.up()
        test.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.archive()
        self.candidate = self.p.config()
        self.p.curl['healthz'] = self.p.curl['busy']
        self.p.write(self.p.path('logs', 'systemctl.log'), '')
        self.p.write(self.p.path('logs', 'curl.log'), '')
        self.p.write(self.p.path('logs', 'runner.log'), '')

    def kept(self, r):
        """Nothing restarted, config.toml is still the candidate, nothing staged; the journal closed."""
        t = self.t
        t.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        t.assertEqual(self.p.config(), self.candidate)
        t.assertFalse(os.path.lexists(self.p.rpath('config.rollback.toml')))
        t.assertEqual(self.calls('stop') + self.calls('start') + self.calls('restart'), [])
        return self.done()[1]


@needs_container
class Back(unittest.TestCase):
    def test_back_restores_the_backup_at_once_with_no_idle_wait(self):
        g = BackRig(self)
        r = g.back()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('POOL IMAGE DONE (back --unattended): %s' % ref(OLD), r.stdout)
        self.assertEqual(g.p.config(), g.old)
        self.assertEqual(len(g.healthz_reads()), 2, 'no idle wait: the two reads are the RUNS of `running`')
        wid, lines = g.done()
        self.assertEqual(keys(lines), BACK_KEYS, lines)
        self.assertEqual(value(lines, 'kind'), 'rollback')
        self.assertEqual(value(lines, 'old'), ref(NEW), 'old: the image config.toml names at the window start, as in up')
        self.assertEqual(value(lines, 'config-sha'), sha(g.candidate))
        # the BACKUP (Codex r1 F3): the pre-window config, in the window's folder, 0600, its sha `config-sha`
        bk = value(lines, 'backup')
        self.assertEqual(os.path.dirname(bk), os.path.join(g.p.STATE, 'windows', wid + '.d'))
        with open(bk) as f:
            self.assertEqual(f.read(), g.candidate)
        self.assertEqual(sha256_file(bk), value(lines, 'config-sha'))
        self.assertEqual(os.stat(bk).st_mode & 0o777, 0o600)
        self.assertEqual(value(lines, 'staged-sha'), sha(g.old))
        self.assertEqual(value(lines, 'target'), ' '.join('%s=%s' % (s, ref(OLD)) for s in SETS))
        self.assertEqual(value(lines, 'target-content'), content(g.old))
        self.assertEqual(len(g.validates()), 1)
        self.assertGreater(int(value(lines, 'running').split()[1]), int(value(lines, 'renamed')))
        self.assertEqual((len(g.calls('stop')), len(g.calls('start'))), (1, 1))
        self.assertEqual(installed(lines), (sha(g.old), content(g.old), 'target-running'))
        self.assertEqual((value(lines, 'why'), value(lines, 'verdict'), value(lines, 'old-version'),
                          value(lines, 'target-version')), ('back', 'none', 'none', 'none'))

    def test_why_verdict_and_the_versions_are_journaled_before_any_effect(self):
        """D-e (r2 Codex F12, Opus F10): a rollback's `why`, its `verdict` (the --verdict FILE copied to the window's
        folder as verdict.json, journaled by its sha), `old-version` (--old-version, else none) and `target-version` (the
        ONE build record whose digest config.toml.prev names, read by runner-release.sh's reader; none when no record
        names it) come before every other line of the rollback but `window` and `kind`. The controls: no record, and
        two records of that digest (no ONE record): `target-version none`."""
        verdict = '{"set": "hz-docker", "failures": 3, "connect_only": false, "reason": "a test verdict"}\n'
        for why, records in (('r1', ['2.338.0']), ('r1-connect', []), ('back', ['2.338.0', '2.338.1'])):
            with self.subTest(why, records=records):
                g = BackRig(self)
                for i, v in enumerate(records):
                    g.p.record(v, OLD, recipe=('%02d' % (40 + i)) * 32 if i else None)
                f = g.p.write(g.p.path('verdict-in.json'), verdict)
                r = g.back('--verdict', f, '--old-version', V, why=why)
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                wid, lines = g.done()
                self.assertEqual(keys(lines)[:6], ['window', 'kind', 'why', 'verdict', 'old-version', 'target-version'])
                self.assertEqual(value(lines, 'why'), why)
                kept = os.path.join(g.p.STATE, 'windows', wid + '.d', 'verdict.json')
                with open(kept) as fh:
                    self.assertEqual(fh.read(), verdict)
                self.assertEqual(value(lines, 'verdict'), sha(verdict))
                self.assertEqual(value(lines, 'old-version'), V)
                self.assertEqual(value(lines, 'target-version'), '2.338.0' if len(records) == 1 else 'none')

    def test_a_config_that_already_is_the_rollback_restarts_nothing(self):
        """A second back (a person's `runner-updater back`, after the updater's, its journal applied): config.toml
        already is config.toml.prev and RUNS, so it is done (exit 0, `running` the process that runs) with no restart,
        and the closing class is pre (there is no `target` line). The control: the first back restarted."""
        g = BackRig(self)
        self.assertEqual(g.back().returncode, 0)
        g.archive()
        unit = g.p.unit_now()
        r = g.back()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.unit_now()['pid'], unit['pid'], 'it restarted')
        self.assertEqual((len(g.calls('stop')), len(g.calls('start'))), (1, 1), 'only the first back restarted')
        lines = g.done()[1]
        self.assertEqual(keys(g.body(lines))[-1], 'running')
        self.assertEqual(value(lines, 'running'), '%d %d' % (unit['pid'], unit['start']))
        self.assertNotIn('rename-start', keys(lines))
        self.assertEqual(installed(lines), (sha(g.old), content(g.old), 'pre'))

    def test_api_only_three_times_counts_as_pass(self):
        g = BackRig(self)
        g.p.runner = {'seq': [API, API, API]}
        r = g.back()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.config(), g.old)
        self.assertEqual([l for l in g.done()[1] if l.startswith('validate ')],
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
                self.assertEqual(installed(lines), (sha(g.candidate), content(g.candidate), 'pre'))

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

        def config_names_two_images(g):     # changed-lines "For S2b-3", Opus r2 F3: back's own ONE-image guard
            bad = g.candidate[::-1].replace(ref(NEW)[::-1], ref(OLD)[::-1], 1)[::-1]
            g.p.write(g.p.rpath('config.toml'), bad, 0o600)
            g.candidate = bad
            g.p.set_unit(start=int(os.stat(g.p.rpath('config.toml')).st_mtime) + 1)
        for why, change, says in (('no config.toml.prev', no_prev, 'no rollback config'),
                                  ('it differs in more than the image', prev_with_other_numbers, 'more than the runner'),
                                  ('the registry does not serve its image', not_served, 'no longer serves'),
                                  ('config.toml does not name ONE image', config_names_two_images,
                                   'config.toml does not name ONE runner image')):
            with self.subTest(why):
                g = BackRig(self)
                change(g)
                r = g.back()
                lines = g.kept(r)
                self.assertTrue(value(lines, 'stop').startswith('ROLLBACK FAILED: '), lines)
                self.assertIn(says, value(lines, 'stop'))
                self.assertEqual(g.validates(), [])

    def test_a_pending_hand_edit_is_hand_change(self):
        """config.toml installed after runscaler started (a hand 03 run): the rollback would replace it unseen. The
        control: the first cell, whose config.toml runs."""
        g = BackRig(self)
        g.p.set_unit(start=int(os.stat(g.p.rpath('config.toml')).st_mtime))
        r = g.back()
        lines = g.kept(r)
        self.assertTrue(value(lines, 'stop').startswith('HAND CHANGE: '), lines)

    def test_a_unit_a_person_disabled_is_rollback_pending(self):
        """PLAN D5's ROLLBACK precondition: a disabled unit (CI disabled by a person) gets no rollback window's
        restart: `end rollback pending: CI disabled by a person`, nothing changed. The control: the cell below (an
        enabled unit that is down)."""
        for kw in ({'enabled': False}, {'enabled': False, 'active': False}):
            with self.subTest(**kw):
                g = BackRig(self)
                g.p.set_unit(**kw)
                r = g.back()
                lines = g.kept(r)
                self.assertIsNone(value(lines, 'stop'), lines)
                self.assertIn('rollback pending: CI disabled by a person', value(lines, 'end'))

    def test_an_enabled_unit_that_is_down_is_rolled_back_and_started(self):
        """OPERATOR (1) ON EVERY ROUTE (Opus r3 F4 (a)): the unit ENABLED means CI on. Inactive, or failed, with no
        process (a person's plain `systemctl --user stop`): the rollback goes on with no started_after test (nothing
        runs), and its restart starts the unit on the rollback target: `running`, target-running, no `end … CI
        disabled`, no HAND CHANGE. The control: the cell above (disabled)."""
        for kw in ({'active': False}, {'active': False, 'failed': True}):
            with self.subTest(**kw):
                g = BackRig(self)
                g.p.set_unit(**kw)
                r = g.back()
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.p.config(), g.old)
                lines = g.done()[1]
                self.assertNotIn('end', keys(lines))
                self.assertIsNone(value(lines, 'stop'))
                self.assertEqual(installed(lines)[2], 'target-running')
                self.assertTrue(g.p.unit_now()['active'])
                self.assertEqual(len(g.calls('start')), 1)

    def test_a_hand_change_after_the_rollback_s_install_gets_no_restart(self):
        g = BackRig(self)
        g.p.hooks(('journal:renamed', 'edit-config'))
        r = g.back()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        lines = g.p.window()
        self.assertEqual(keys(lines)[-2:], ['hand-change', 'stop'])
        self.assertEqual(g.calls('stop') + g.calls('start'), [])

    def test_a_hand_change_during_the_rollback_s_validate_is_hand_change(self):
        """Opus r1 F5 (its mutant M2): config.toml changed while back validates its copy: the check of the backup's
        copy, right after `backup` is synced, finds it. A closed STOP HAND CHANGE, no `rename-start`, config.toml the
        hand change, nothing restarted, the closing class other. The control: the first cell."""
        g = BackRig(self)
        g.p.hooks(('journal:validate', 'edit-config'))
        r = g.back()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        hand = g.candidate + '# a hand change\n'
        self.assertEqual(g.p.config(), hand)
        self.assertFalse(os.path.lexists(g.p.rpath('config.rollback.toml')))
        self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), [])
        lines = g.done()[1]
        self.assertEqual(keys(g.body(lines))[-1], 'stop', lines)
        self.assertTrue(value(lines, 'stop').startswith('HAND CHANGE: '), lines)
        self.assertNotIn('rename-start', keys(lines))
        self.assertEqual(installed(lines), (sha(hand), content(hand), 'other'))

    def test_a_rollback_copy_changed_after_its_validate_is_rollback_failed(self):
        """Opus r1 F5 (its mutant M3): back's copy (STAGED) changed after its validate: its check right before the
        rename finds it. A closed STOP ROLLBACK FAILED (config.toml is the window's own pre-window file), nothing
        renamed or restarted. The control: the first cell."""
        g = BackRig(self)
        g.p.hooks(('journal:validate', 'edit-rollback'))
        r = g.back()
        lines = g.kept(r)
        self.assertTrue(value(lines, 'stop').startswith('ROLLBACK FAILED: '), lines)
        self.assertIn('changed after its validate', value(lines, 'stop'))
        self.assertNotIn('renamed', keys(lines))

    def test_a_rollback_changed_before_its_copy_is_rollback_failed(self):
        """A copy is checked after it is made: config.toml.prev changed by hand once `staged` is synced (after back
        read the rollback's image and asked the registry for it, before it copies the file): the copy, the file back
        validates and installs, is what is checked (one image, the one asked for; config.toml's other lines). A content
        line that is no image line (the main set's max-runners), and another image in both its image lines: a closed
        STOP ROLLBACK FAILED, nothing validated or renamed. The control: the first cell, and a COMMENT line added the
        same way, which is no content (runscaler 0.12 bump, slice H2a: comments are not content; b2eb739's
        'a line that is no image line' subtest was that comment line, and refused): the rollback goes on, its copy with
        the comment installed and running."""
        for why, edit in (('a content line that is no image line', 'edit-prev-value'),
                          ('another image', 'edit-prev-image')):
            with self.subTest(why):
                g = BackRig(self)
                g.p.hooks(('journal:staged', edit))
                r = g.back()
                lines = g.kept(r)
                self.assertTrue(value(lines, 'stop').startswith('ROLLBACK FAILED: '), lines)
                self.assertNotIn('rename-start', keys(lines))
                self.assertEqual(g.validates(), [], 'the changed copy was validated')
        with self.subTest('control: a comment line'):
            g = BackRig(self)
            prev = g.p.read(g.prev)
            g.p.hooks(('journal:staged', 'edit-prev'))
            r = g.back()
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
            self.assertEqual(g.p.config(), prev + '# a hand change of the rollback\n')
            self.assertEqual(installed(g.done()[1])[2], 'target-running')


def mode_rig(test, mode, clock=True):
    """(the rig, its run, STAGED's base name) for MODE: up on a Rig, back on a BackRig."""
    if mode == 'up':
        g = Rig(test, clock)
        return g, g.up, 'config.staged.toml'
    g = BackRig(test, clock)
    return g, g.back, 'config.rollback.toml'


@needs_container
class WindowFixes(unittest.TestCase):
    """The changed-lines list's "For S2b-3" items (D-h), each with its control."""

    def test_a_person_s_disable_during_the_window_gets_no_start(self):
        """Opus r2 F4: a person's `systemctl --user disable --now runscaler` (03's own documented line) during a window:
        after the drain, before `starting`, the unit must still be enabled. Else no start, exit 1, and the journal
        closes with `stop CI DISABLED: …` (the TARGET is installed and runs when a person starts runscaler) and the
        closing class target-idle (no process). up at `journal:idle`, back at `journal:validate`, and up during the
        drain. The control: the happy path (enabled: stop + start, exit 0)."""
        for mode, at in (('up', 'journal:idle'), ('back', 'journal:validate'), ('up', 'systemctl:stop-done')):
            with self.subTest(mode, at=at):
                g, run, staged = mode_rig(self, mode)
                g.p.hooks((at, 'disable'))
                r = run()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.calls('start') + g.calls('restart'), [])
                unit = g.p.unit_now()
                self.assertEqual((unit['active'], unit['enabled']), (False, False))
                lines = g.done()[1]
                self.assertNotIn('starting', keys(lines))
                self.assertTrue(value(lines, 'stop').startswith('CI DISABLED: '), lines)
                self.assertIn('systemctl --user enable --now runscaler', value(lines, 'stop'))
                self.assertEqual(installed(lines), (value(lines, 'staged-sha'), value(lines, 'target-content'),
                                                    'target-idle'))
                self.assertIn('STOP CI DISABLED: ', r.stdout)

    def test_the_success_shortcuts_check_once_right_before_running(self):
        """Opus r2 F2 + Codex r2 F1(a): up's "already names the digest" and back's "already the rollback" check ONCE,
        after their journal lines, right before `running`: config.toml still `config-sha` (and still naming the digest)
        in one read, and runscaler RUNS. A hand change once `config-sha` is synced: not exit 0, no `running`. A restart
        between the two reads of RUNS: not exit 0. The control: each mode's second call above (stable: exit 0)."""
        for mode in ('up', 'back'):
            for at, act in (('journal:config-sha', 'edit-config'), ('healthz-read', 'restart')):
                with self.subTest(mode, at=at):
                    g = Rig(self)
                    self.assertEqual(g.up().returncode, 0)
                    g.archive()
                    if mode == 'back':
                        self.assertEqual(g.back().returncode, 0)
                        g.archive()
                    g.p.hooks((at, act))
                    r = g.up() if mode == 'up' else g.back()
                    self.assertNotEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                    self.assertIn('hook %s: %s' % (at, act), g.p.events())
                    lines = g.p.window()
                    self.assertNotIn('running', keys(lines), lines)
                    self.assertNotIn('DONE', r.stdout)

    def test_the_texts_are_true_once_the_backup_replaced_config_toml_prev(self):
        """Opus r2 F1 (wording): STAGED changed after `rename-start` (after THE BACKUP replaced config.toml.prev): the
        STOP's text must not say that nothing changed; it names config.toml.prev as this window's backup. The control:
        a STOP before the backup still says nothing changed."""
        g = Rig(self)
        g.p.hooks(('journal:rename-start', 'edit-staged'))
        r = g.up()
        self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        self.assertNotIn('Nothing changed', r.stdout)
        self.assertIn('config.toml.prev', r.stdout.split('STOP ', 1)[1])
        self.assertIn('now holds', r.stdout)
        g = Rig(self)
        g.p.pool_env(CONCURRENT=3, MAX=2)
        r = g.up()
        self.assertIn('Nothing changed', r.stdout)

    def test_each_validate_try_is_bounded_and_never_holds_the_updater_lock(self):
        """r3 FOLD P3 / Opus r3 F15, r2 Codex F15, Opus F13 (b): every validate try of the window (03 render in up;
        runner-start validate in back) runs under `timeout -k 10 120` in its own process group, and the updater lock
        (fd 9) never reaches the validate; a try the bound cuts is UNKNOWN (up: STOP check failed; back: `end`, no STOP),
        and no process of it is left. Here `timeout` divides its durations by 40 (support.Pool.short_timeout) and
        runscaler's validate ignores SIGTERM. The control: a validate that ends is classified (the happy path), and its
        try was bounded the same way."""
        for mode in ('up', 'back'):
            for hang in (True, False):
                with self.subTest(mode, hang=hang):
                    g, run, staged = mode_rig(self, mode)
                    g.p.short_timeout()
                    g.p.runner = {'hang': True, 'rc': 1, 'out': 'never\n'} if hang else PASS
                    r = run()
                    bounds = [a for a in g.p.timeouts() if a[:3] == ['-k', '10', '120']]
                    self.assertEqual(len(bounds), 1, g.p.timeouts())
                    vs = g.validates()
                    self.assertTrue(vs)
                    self.assertEqual([c['fd9'] for c in vs], [False] * len(vs), 'the updater lock reached a validate')
                    if not hang:
                        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                        continue
                    lines = g.done()[1]
                    self.assertEqual(value(lines, 'validate'), 'pre 1 UNKNOWN', lines)
                    if mode == 'up':
                        self.assertTrue(value(lines, 'stop').startswith('check failed: '), lines)
                    else:
                        self.assertIsNone(value(lines, 'stop'), lines)
                        self.assertIn('UNKNOWN', value(lines, 'end'))
                    with open(g.p.path('logs', 'hang.pid')) as f:
                        pid = int(f.read().split()[0])
                    self.assertFalse(alive(pid), 'the cut validate still runs')


@needs_container
class EachCheckRightBeforeItsStep(unittest.TestCase):
    """Codex r1 F1, Codex r1 F2 and the class: each check of a file comes AFTER the journal line of the step it guards
    and right before that step, so a hand change injected at that line is seen before the step, in up and in back. What
    the updater's RECOVER reads then: a closed journal only where config.toml is provably the window's own pre-window
    file (checked); else the journal stays OPEN with `hand-change`."""

    def test_a_staged_file_changed_after_rename_start_is_not_renamed(self):
        """Codex r1 F1: STAGED changed once `rename-start` is synced. Its check right before the rename finds it:
        nothing renamed, config.toml the pre-window file (checked just before), so the journal is closed with the STOP
        (up: check failed; back: ROLLBACK FAILED) and no `renamed`; no restart. The control: an unchanged STAGED
        installs exactly the validated sha (up: the one 03's render printed)."""
        for mode in ('up', 'back'):
            for edit in (True, False):
                with self.subTest(mode, edit=edit):
                    g, run, staged = mode_rig(self, mode)
                    pre = g.p.config()
                    if edit:
                        g.p.hooks(('journal:rename-start', 'edit-staged' if mode == 'up' else 'edit-rollback'))
                    r = run()
                    if not edit:
                        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                        wid, lines = g.done()
                        self.assertEqual(sha256_file(g.p.rpath('config.toml')), value(lines, 'staged-sha'))
                        if mode == 'up':
                            out = os.path.join(g.p.STATE, 'windows', wid + '.d', 'validate-pre-1.out')
                            with open(out) as f:
                                printed = re.findall(r'^03 STAGED \(render\): .* sha256 ([0-9a-f]{64})\. ', f.read(), re.M)
                            self.assertEqual(printed, [value(lines, 'staged-sha')])
                        continue
                    self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                    self.assertEqual(g.p.config(), pre, 'the changed STAGED was renamed over config.toml')
                    self.assertFalse(os.path.lexists(g.p.rpath(staged)))
                    self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), [])
                    wid, lines = g.done()
                    self.assertEqual(keys(g.body(lines))[-1], 'stop', lines)
                    self.assertIn('rename-start', keys(lines))
                    self.assertNotIn('renamed', keys(lines))
                    self.assertTrue(value(lines, 'stop').startswith(
                        'check failed: ' if mode == 'up' else 'ROLLBACK FAILED: '), lines)
                    self.assertEqual(installed(lines), (sha(pre), content(pre), 'pre'))

    def test_a_hand_change_after_rename_start_is_not_renamed_over(self):
        """config.toml changed once `rename-start` is synced: its check right before the rename finds it, so the rename
        does not replace the hand change and nothing restarts: `hand-change` (its sha), STOP HAND CHANGE, and the
        journal stays OPEN (config.toml is no longer the pre-window file: RECOVER reads it, sha neither `config-sha` nor
        `staged-sha`: leave as found). runscaler runs on as it was. The control: the happy path."""
        for mode in ('up', 'back'):
            with self.subTest(mode):
                g, run, staged = mode_rig(self, mode)
                pre, unit = g.p.config(), g.p.unit_now()
                g.p.hooks(('journal:rename-start', 'edit-config'))
                r = run()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.p.config(), pre + '# a hand change\n', 'the rename replaced the hand change')
                self.assertFalse(os.path.lexists(g.p.rpath(staged)))
                self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), [])
                self.assertEqual(g.p.unit_now()['pid'], unit['pid'])
                lines = g.p.window()
                self.assertIsNotNone(lines, 'the journal stays open')
                self.assertEqual(keys(lines)[-3:], ['rename-start', 'hand-change', 'stop'], lines)
                self.assertEqual(value(lines, 'hand-change'), sha256_file(g.p.rpath('config.toml')))
                self.assertTrue(value(lines, 'stop').startswith('HAND CHANGE: '))
                self.assertIn('STOP HAND CHANGE: ', r.stdout)

    def test_a_hand_change_at_the_stop_or_the_start_gets_neither(self):
        """Codex r1 F2 and the stop: config.toml changed once `stopping` is synced: its check right before the stop
        finds it, so nothing is stopped (the old process runs its own config on); once `starting` is synced: nothing is
        started (runscaler stays stopped). Each: `hand-change`, STOP HAND CHANGE, the journal OPEN, no `running`. Up
        and back. The control: the happy path, where the target starts."""
        for mode in ('up', 'back'):
            for at, stops in (('journal:stopping', 0), ('journal:starting', 1)):
                with self.subTest(mode, at=at):
                    g, run, staged = mode_rig(self, mode)
                    g.p.hooks((at, 'edit-config'))
                    r = run()
                    self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                    lines = g.p.window()
                    self.assertIsNotNone(lines, 'the journal stays open')
                    self.assertEqual(keys(lines)[-3:], [at.split(':')[1], 'hand-change', 'stop'], lines)
                    self.assertNotIn('running', keys(lines))
                    self.assertEqual(value(lines, 'hand-change'), sha256_file(g.p.rpath('config.toml')))
                    self.assertTrue(value(lines, 'stop').startswith('HAND CHANGE: '))
                    self.assertTrue(g.p.config().endswith('# a hand change\n'))
                    self.assertEqual((len(g.calls('stop')), len(g.calls('start')), len(g.calls('restart'))),
                                     (stops, 0, 0))
                    self.assertEqual(g.p.unit_now()['active'], stops == 0)


@needs_container
class BackAroundTheRename(unittest.TestCase):
    """Codex r1 F3, PLAN D1 + RECOVER step 4: a rollback window keeps the config it replaces. A back killed at each
    point around the rename, and its journal's newest line then cut in half (a power loss): each journal that may have
    renamed names `backup P`, and P holds the pre-window config's bytes (sha `config-sha`, 0600): what RECOVER puts
    back when the rollback target fails validate. Killed once `backup` is synced (before the copy): no `rename-start`,
    and config.toml is the pre-window file itself. The control: Back's first cell (the happy path's backup)."""

    def test_a_back_killed_around_the_rename_leaves_its_backup(self):
        for at, last_key, renamed in (('journal:rename-start', 'rename-start', False),
                                      ('mv-done:config.toml', 'rename-start', True), ('journal:renamed', 'renamed', True)):
            with self.subTest(at):
                g = BackRig(self)
                g.p.hooks((at, 'kill'))
                r = g.back()
                self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
                self.assertIn('hook %s: kill' % at, g.p.events())
                with open(os.path.join(g.p.STATE, 'window')) as f:
                    text = f.read()
                self.assertEqual(keys(text.split('\n')[:-1])[-1], last_key)
                csha = sha256_file(g.p.rpath('config.toml'))
                for cut in (False, True):
                    t = text
                    if cut:                                  # the newest line half written
                        last = t[:-1].rsplit('\n', 1)[1]
                        t = t[:len(t) - 1 - len(last) // 2]
                    lines = t.split('\n')[:-1]               # whole lines only: a reader drops a cut one
                    with self.subTest(at, cut=cut):
                        bk = value(lines, 'backup')
                        self.assertIsNotNone(bk, lines)
                        with open(bk) as f:
                            self.assertEqual(f.read(), g.candidate, 'the backup is not the pre-window config')
                        self.assertEqual(sha256_file(bk), value(lines, 'config-sha'))
                        self.assertEqual(os.stat(bk).st_mode & 0o777, 0o600)
                        self.assertEqual(csha, value(lines, 'staged-sha') if renamed else value(lines, 'config-sha'))

    def test_a_back_killed_at_its_backup_line_renamed_nothing(self):
        g = BackRig(self)
        g.p.hooks(('journal:backup', 'kill'))
        r = g.back()
        self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
        lines = g.p.window()
        self.assertEqual(keys(lines)[-1], 'backup', lines)
        self.assertNotIn('rename-start', keys(lines))
        self.assertEqual(g.p.config(), g.candidate)
        self.assertEqual(sha256_file(g.p.rpath('config.toml')), value(lines, 'config-sha'))


@needs_container
class InstallTime(unittest.TestCase):
    """Opus r1 F1, PLAN D1: the Hetzner install time is the journaled `renamed` epoch, never the staged file's render or
    copy time. config.toml's mtime (what started_after reads) is set by the clock once `rename-start` is synced and
    before the rename: rename-start's second <= its second <= renamed's. These cells run on the REAL clock (the fake
    one starts ahead of every real mtime, so it cannot place a start between a file's mtime and its rename); they
    assert the order of whole seconds, never a duration."""

    def test_the_install_time_is_between_rename_start_and_renamed(self):
        """up and back, each with a whole second between the render or copy and `rename-start` (tick), and another
        after the time is set: config.toml's mtime second is rename-start's or later and renamed's or earlier, and
        the time is set after `rename-start` and before the rename."""
        for mode in ('up', 'back'):
            with self.subTest(mode):
                g, run, staged = mode_rig(self, mode, clock=False)
                g.p.hooks(('journal:idle' if mode == 'up' else 'journal:validate', 'tick'),
                          ('touch-done:' + staged, 'tick'))
                r = run()
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                lines = g.done()[1]
                rs, rn = int(value(lines, 'rename-start')), int(value(lines, 'renamed'))
                m = int(os.stat(g.p.rpath('config.toml')).st_mtime)
                self.assertLessEqual(rs, m, 'the install time is before rename-start: the render or copy time?')
                self.assertLessEqual(m, rn)
                ev = g.p.events()
                self.assertLess(ev.index('journal rename-start'), ev.index('touch ' + staged))
                self.assertLess(ev.index('touch ' + staged), ev.index('mv config.toml'))

    def cut_back(self, *hooks):
        """A switch, then a back cut right after `renamed` (SIGKILL: no restart of its own), its journal then moved
        aside by hand (a planted state: RECOVER is test_recover.py's), and back again: (the rig, the unit after the
        cut, the cut window's lines, the second back's result and journal)."""
        g = BackRig(self, clock=False)
        g.p.hooks(*hooks)
        r = g.back()
        self.assertEqual(r.returncode, -9, r.stdout[-3000:] + r.stderr)
        lines = g.p.window()
        self.assertEqual(keys(lines)[-1], 'renamed', lines)
        self.assertEqual(g.p.config(), g.old, 'config.toml is the rollback target')
        unit = g.p.unit_now()
        self.assertEqual(unit['independent'], 1)
        os.rename(os.path.join(g.p.STATE, 'window'), os.path.join(g.p.STATE, 'windows', value(lines, 'window')))
        g.archived += 1
        calls = g.calls('stop') + g.calls('start') + g.calls('restart')
        r = g.back()
        self.assertEqual(g.calls('stop') + g.calls('start') + g.calls('restart'), calls, 'the second back restarted')
        return g, unit, lines, r, g.done()[1]

    def test_a_runscaler_start_before_the_rename_is_not_the_rollback_s(self):
        """Opus r1 F1 (p1x): an independent restart in a whole second after back's copy and at or before `rename-start`:
        that process read the candidate, so the next back must not report it as running the rollback: no `running`
        of it, exit != 0."""
        g, unit, lines, r, last = self.cut_back(('journal:validate', 'tick', 'restart'), ('journal:renamed', 'kill'))
        self.assertLessEqual(unit['start'], int(value(lines, 'rename-start')))
        self.assertNotEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertNotIn('running', keys(last), last)
        self.assertNotIn('DONE', r.stdout)

    def test_a_runscaler_start_after_renamed_is_the_rollback_s(self):
        """The control (p1c): the restart in a whole second after `renamed`: that process read the rollback, so the next
        back is done with no restart: exit 0, `running` that process."""
        g, unit, lines, r, last = self.cut_back(('journal:renamed', 'tick', 'restart', 'kill'))
        self.assertGreater(unit['start'], int(value(lines, 'renamed')))
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(value(last, 'running'), '%d %d' % (unit['pid'], unit['start']))


class Text(unittest.TestCase):
    def header(self):
        with open(PIMG) as f:
            return f.read().split('\nset -uo pipefail\n', 1)[0]

    def test_the_header_names_the_modes_their_journal_and_exit_codes(self):
        h = self.header()
        for s in ('up --unattended VERSION DIGEST', 'back --unattended --why', 'recover --unattended',
                  '~/.local/state/runner-updater/window', 'An unfinished window the updater cannot end'):
            self.assertIn(s, h)
        for k in sorted(set(SWITCH_KEYS + BACK_KEYS + ['hand-change', 'stop', 'end', 'pre-close-failure',
                                                       'recover-start', 'recover-target', 'restore'])):
            self.assertRegex(h, r'#\s+\[?%s[ \]]' % re.escape(k), 'the header names no journal line %s' % k)
        for code in ('0', '1', '2', '3', '4', '5', '6'):
            self.assertRegex(h, r'#\s+%s\s' % code, 'the header names no exit code %s' % code)

    def test_the_readme_says_what_the_journal_shows_and_who_runs_the_modes(self):
        """S2b-3c-1 D-a, D-b: the modes are the updater's only (a person's rollback is `runner-updater back hz-docker`,
        and no line gives a person `pool-image.sh back --unattended`: test_back.py, Text), RECOVER is the third, and a
        closed journal stays at `window` until the updater's next run applies and archives it."""
        with open(README) as f:
            text = f.read()
        sec = text.split('\n## The updater\'s switch and rollback\n', 1)[1].split('\n## ', 1)[0]
        self.assertIn('~/.local/state/runner-updater/window', sec)
        self.assertNotIn("ssh <RS_USER>@<host> 'bash ~/build/setup/pool-image.sh back --unattended'", sec)
        for s in ('runner-updater back hz-docker', 'recover --unattended', "the updater's only",
                  'stays at `window` with the closing lines', 'until the updater\'s next run'):
            self.assertIn(s, sec)
        for k in ('rename-start', 'renamed', 'stopped', 'running', 'hand-change', 'backup', 'why', 'verdict',
                  'old-version', 'target-version', 'installed', 'closed'):
            self.assertIn('`%s' % k, sec)
        self.assertIn('config.toml.backup', sec, "back's backup of the config it replaces")

    def test_the_readme_s_prerequisites_name_a_tested_jq(self):
        """Codex r1 F4: the unattended switch STOPs under a jq that core/TESTED_JQ does not list for the core, so
        Install's prerequisites name jq and that list."""
        with open(README) as f:
            need = [l for l in f.read().splitlines() if l.startswith('You need: ')]
        self.assertEqual(len(need), 1)
        self.assertIn('`jq`', need[0])
        self.assertIn('core/TESTED_JQ', need[0])

    def test_the_install_line_ships_the_core(self):
        with open(README) as f:
            line = [l for l in f.read().splitlines() if l.strip().startswith('COPYFILE_DISABLE=1 tar -C linux-docker')]
        self.assertEqual(len(line), 1)
        self.assertIn(' setup/tls-excluded-spki core |', line[0])


if __name__ == '__main__':
    unittest.main()
