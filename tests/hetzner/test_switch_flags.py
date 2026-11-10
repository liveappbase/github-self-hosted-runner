"""`pool-image.sh up --unattended VERSION DIGEST [--now] [--keep-prev]` (S2b-3c-2 B3; the slice plan's E-3, E-7 (b)/(c),
E-14 with its r2 and r3 FOLDs): the switch's two options and THE CORE-STATE EXCUSE of its idle pair. The usage and the
header cells are test_unattended.py's; RECOVER's `--now` and its `keep-prev` backup, test_recover.py's; a SIGKILL after
the new lines, test_kills.py's.

- `--keep-prev` (E-3; the updater decides it, pool-image.sh obeys it and reads no state): `keep-prev P` journaled right
  after `digest`, before any effect; THE BACKUP goes into the window's own folder (windows/ID.d/config.toml.backup, its
  `backup` line names it) and never into config.toml.prev, which stays byte for byte (sha and mtime) as it was; the
  closing `prev` line still names config.toml.prev's sha. A STOP after that backup says where it is and that
  config.toml.prev is as it was. The control: no option: THE BACKUP replaces config.toml.prev, as before.
- `--now` (E-7 (b)/(c): a person's switch-now): no idle pair (no /healthz read before the backup, no core), `idle
  skipped` where `idle idle` is, then the restart as without it: a BUSY pool is restarted (its drain lets running jobs
  finish). The control: no `--now`, busy: exit 3, no journal. Both options in either order.
- THE CORE-STATE EXCUSE (E-14, the r3 FOLD: the pass's switch only): the idle pair gives core/idle.jq a copy of the
  updater's core state, ~/.local/state/runner-updater/pass/state.json, so a set its `not_ready_since` names 86400 s or
  more before the idle pair's own clock read is excused from READINESS only (its counts still count). The controls:
  86399 s, `busy 1` on that set, no copy, a copy that is not a core state (another format; not JSON): not idle, exit 3,
  and the NOT NOW line says why no set was excused. With `--now` no pair, so no copy matters.
Every cell runs a real window of the real scripts in a throwaway container (support.Pool, a fake clock: the excuse's
age is planted against the clock the idle pair reads, which each cell checks from the substitutes' events). (Named for
its CI part, test_[sv-z]*.py: .github/workflows/release-check.yml.)
"""
import json
import os
import unittest

from tests.hetzner.support import Pool, digest, healthz, needs_container, ref, sha256_file
from tests.hetzner.test_unattended import NEW, OLD, SWITCH_KEYS, Rig, content, installed, keys, sha, value

CORE_COPY = os.path.join(Pool.STATE, 'pass', 'state.json')
SMALL = 'linux-ci-small'
DAY = 86400
KEEP_KEYS = SWITCH_KEYS[:SWITCH_KEYS.index('digest') + 1] + ['keep-prev'] + SWITCH_KEYS[SWITCH_KEYS.index('digest') + 1:]


def plant_keep(g):
    """An open candidate's keep: config.toml.prev is the config the pool ran before it (another image): its text and
    os.stat."""
    text = g.old.replace(ref(OLD), ref(digest(37)))
    assert text != g.old
    g.p.write(g.prev, text, 0o600)
    g.p.curl['served'] = g.p.curl['served'] + [digest(37)]   # the registry serves the keep (B4a item 13 (b) checks it)
    return text, os.stat(g.prev)


def window_backup(lines):
    return os.path.join(Pool.STATE, 'windows', value(lines, 'window') + '.d', 'config.toml.backup')


def idle_clock(test, g):
    """The clock the idle pair's core read: the first `date +%s` after the pair's second /healthz read."""
    ev = g.p.events()
    reads = [i for i, e in enumerate(ev) if e == 'healthz read']
    test.assertGreaterEqual(len(reads), 2, ev)
    dates = [int(e.split()[1]) for e in ev[reads[1]:] if e.startswith('date ')]
    test.assertTrue(dates, ev)
    return dates[0]


@needs_container
class KeepPrev(unittest.TestCase):
    def test_keep_prev_backs_up_into_the_window_s_folder_and_keeps_config_toml_prev(self):
        for flag in (True, False):
            with self.subTest(keep_prev=flag):
                g = Rig(self)
                g.p.hooks()                                 # no hook: the dd and mv substitutes log the order
                text, st = plant_keep(g)
                r = g.up('--keep-prev') if flag else g.up()
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.p.images(), [ref(NEW)] * 2)
                wid, lines = g.done()
                if not flag:   # the control: as before, THE BACKUP replaces config.toml.prev
                    self.assertEqual(keys(lines), SWITCH_KEYS, lines)
                    self.assertEqual(value(lines, 'backup'), g.prev)
                    self.assertEqual(g.p.read(g.prev), g.old)
                    self.assertEqual(value(lines, 'prev'), sha(g.old))
                    self.assertFalse(os.path.lexists(window_backup(lines)))
                    continue
                self.assertEqual(keys(lines), KEEP_KEYS, lines)
                self.assertEqual(value(lines, 'keep-prev'), g.prev)
                self.assertEqual(value(lines, 'backup'), window_backup(lines))
                self.assertEqual(g.p.read(window_backup(lines)), g.old, 'the backup is the config before the window')
                self.assertEqual(oct(os.stat(window_backup(lines)).st_mode & 0o777), '0o600')
                self.assertEqual((sha256_file(g.prev), os.stat(g.prev).st_mtime_ns), (sha(text), st.st_mtime_ns),
                                 'config.toml.prev changed')
                self.assertEqual(value(lines, 'prev'), sha(text), 'the closing prev line: config.toml.prev then')
                self.assertEqual(installed(lines), (sha(g.p.config()), content(g.p.config()), 'target-running'))
                ev = g.p.events()
                at = {e: i for i, e in reversed(list(enumerate(ev)))}
                self.assertLess(at['journal digest'], at['journal keep-prev'])
                self.assertLess(at['journal keep-prev'], at['journal process'], 'keep-prev comes before any effect')
                self.assertLess(at['journal backup'], at['mv config.toml.backup'])
                self.assertNotIn('mv config.toml.prev', ev)

    def test_a_stop_after_the_keep_prev_backup_says_config_toml_prev_is_as_it_was(self):
        """THE BACKUP done, then STAGED changed before the rename: STOP check failed, closed pre, nothing renamed. With
        --keep-prev the line names the backup's folder and that config.toml.prev is as it was (byte for byte); the
        control (no option): the line says config.toml.prev holds the window's backup."""
        for flag in (True, False):
            with self.subTest(keep_prev=flag):
                g = Rig(self)
                text, st = plant_keep(g)
                g.p.hooks(('mv-done:config.toml.backup' if flag else 'mv-done:config.toml.prev', 'edit-staged'))
                r = g.up('--keep-prev') if flag else g.up()
                self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.p.config(), g.old)
                wid, lines = g.done()
                self.assertTrue(value(lines, 'stop').startswith('check failed: '), lines)
                self.assertEqual(installed(lines)[2], 'pre')
                if flag:
                    self.assertEqual((sha256_file(g.prev), os.stat(g.prev).st_mtime_ns), (sha(text), st.st_mtime_ns))
                    self.assertEqual(g.p.read(window_backup(lines)), g.old)
                    self.assertIn('config.toml.prev is as it was', r.stdout)
                    self.assertIn(window_backup(lines), r.stdout)
                    self.assertNotIn('the keep of an earlier switch is replaced', r.stdout)
                else:
                    self.assertEqual(g.p.read(g.prev), g.old)
                    self.assertIn('the keep of an earlier switch is replaced', r.stdout)


@needs_container
class Now(unittest.TestCase):
    def test_now_skips_the_idle_pair_and_restarts_a_busy_pool(self):
        """--now: no /healthz read before the backup, `idle skipped`, one stop, one start, closed target-running, with
        the main set busy. The control: the same busy pool with no --now: exit 3, no journal, nothing changed."""
        busy = healthz(**{'linux-ci-main': {'busy': 1}})
        g = Rig(self)
        g.p.curl['healthz'] = busy
        g.not_now(g.up(), 'not idle', 'busy 1')
        g = Rig(self)
        g.p.curl['healthz'] = busy
        g.p.hooks()
        r = g.up('--now')
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        wid, lines = g.done()
        self.assertEqual(keys(lines), SWITCH_KEYS, lines)
        self.assertEqual(value(lines, 'idle'), 'skipped')
        self.assertEqual(value(lines, 'backup'), g.prev, 'no --keep-prev: config.toml.prev is the backup')
        self.assertEqual(g.p.images(), [ref(NEW)] * 2)
        self.assertEqual((len(g.calls('stop')), len(g.calls('start')), len(g.calls('restart'))), (1, 1, 0))
        self.assertEqual(installed(lines)[2], 'target-running')
        ev = g.p.events()
        self.assertNotIn('healthz read', ev[:ev.index('journal backup')], 'an idle pair was read')
        self.assertLess(ev.index('journal idle'), ev.index('journal backup'))

    def test_both_options_in_either_order(self):
        for more in (('--now', '--keep-prev'), ('--keep-prev', '--now')):
            with self.subTest(more=more):
                g = Rig(self)
                text, st = plant_keep(g)
                g.p.curl['healthz'] = healthz(**{'linux-ci-small': {'busy': 2}})
                r = g.up(*more)
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                wid, lines = g.done()
                self.assertEqual(keys(lines), KEEP_KEYS, lines)
                self.assertEqual(value(lines, 'idle'), 'skipped')
                self.assertEqual(value(lines, 'backup'), window_backup(lines))
                self.assertEqual((sha256_file(g.prev), os.stat(g.prev).st_mtime_ns), (sha(text), st.st_mtime_ns))


@needs_container
class CoreStateExcuse(unittest.TestCase):
    """E-14: the idle pair reads the core state copy's not_ready_since; the small set reads ready=false, all its counts
    0, on both reads; the main set idle. The age is planted against the clock the pair's core reads (the fake clock at
    the window's start, plus the pair's `sleep 3`: checked from the events)."""

    def window(self, copy, small=None, more=()):
        """A switch with the small set not ready (SMALL: more of its fields) and COPY at the core state copy's path
        (None: none; a dict: {'age': seconds} -> a core state of format 1 whose not_ready_since names the small set that
        long before the pair's clock; a str: those bytes). The rig, its result, and the clock the pair planted against."""
        g = Rig(self)
        s = dict({'ready': False}, **(small or {}))
        g.p.curl['healthz'] = healthz(**{SMALL: s})
        t0 = g.p.clock() + 3    # the clock the pair's core reads: the window's start plus the pair's `sleep 3`
        if isinstance(copy, dict):
            g.p.write(CORE_COPY, json.dumps({'format': 1, 'not_ready_since': {SMALL: t0 - copy['age']}}) + '\n', 0o600)
        elif isinstance(copy, str):
            g.p.write(CORE_COPY, copy, 0o600)
        r = g.up(*more)
        return g, r, t0

    def test_a_set_not_ready_for_24_h_is_excused_from_readiness_only(self):
        g, r, t0 = self.window({'age': DAY})
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(idle_clock(self, g), t0, 'the harness planted the age against another clock')
        wid, lines = g.done()
        self.assertEqual(value(lines, 'idle'), 'idle')
        self.assertEqual((len(g.calls('stop')), len(g.calls('start'))), (1, 1))
        self.assertIn('%s: not ready since' % SMALL, r.stdout)
        self.assertIn('excused from readiness only', r.stdout)

    def test_controls_no_set_is_excused(self):
        """Each: exit 3, not idle, no journal, nothing changed; the NOT NOW line says why (the small set not ready; with
        `busy 1` on it its counts: it is excused from readiness, and that line says so)."""
        for why, copy, small, says in (
                ('86399 s', {'age': DAY - 1}, None, ('%s: not ready' % SMALL,)),
                ('86400 s, but busy 1 on that set', {'age': DAY}, {'busy': 1}, ('busy 1',)),
                ('no copy', None, None, ('not ready', CORE_COPY, 'no set is excused', 'is absent')),
                ('a copy of another format', json.dumps({'format': 2, 'not_ready_since': {SMALL: 1}}) + '\n', None,
                 ('not ready', CORE_COPY, 'no set is excused', 'not a core state')),
                ('a copy that is not JSON', '{"format": 1, "not_ready_since": \n', None,
                 ('not ready', CORE_COPY, 'no set is excused', 'not a core state')),
                ('not_ready_since not of numbers', json.dumps({'format': 1, 'not_ready_since': {SMALL: 'x'}}) + '\n',
                 None, ('not ready', CORE_COPY, 'no set is excused', 'not a core state'))):
            with self.subTest(why):
                g, r, t0 = self.window(copy, small)
                g.not_now(r, 'not idle')
                line = [l for l in r.stdout.splitlines() if l.startswith('POOL IMAGE NOT NOW (up --unattended): ')]
                self.assertEqual(len(line), 1, r.stdout)
                for s in says:
                    self.assertIn(s, line[0], 'the NOT NOW line says why')
                self.assertEqual(idle_clock(self, g), t0)
                if small:   # excused from readiness, and its counts still count: `busy 1` keeps it from idle
                    self.assertIn('%s: not ready since' % SMALL, r.stdout)
                    self.assertNotIn('not ready', line[0])
                else:
                    self.assertNotIn('excused from readiness only', r.stdout)

    def test_with_now_no_pair_reads_the_copy(self):
        g, r, t0 = self.window({'age': DAY - 1}, more=('--now',))
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        wid, lines = g.done()
        self.assertEqual(value(lines, 'idle'), 'skipped')



@needs_container
class KeepPrevRegistry(unittest.TestCase):
    """B3 review r1, Opus F2 (B4a item 13 (b)): with --keep-prev the rollback this window keeps is config.toml.prev's
    config, so `up`'s registry check asks for config.toml.prev's image, and its STOP names that image as the
    rollback's, before `backup` (nothing staged is backed up, config.toml.prev byte for byte as it was). The controls:
    the registry serves it: the window goes on; no --keep-prev with that image unserved: the window goes on (its
    rollback is config.toml's image, which the registry serves)."""

    def test_keep_prev_checks_that_the_registry_serves_config_toml_prev_s_image(self):
        kept = ref(digest(37))
        for name, flag, served in (('not served', True, False), ('served', True, True),
                                   ('no --keep-prev, not served', False, False)):
            with self.subTest(name):
                g = Rig(self)
                text, st = plant_keep(g)
                if not served:
                    g.p.curl['served'] = [OLD, NEW]
                r = g.up('--keep-prev') if flag else g.up()
                wid, lines = g.done()
                if flag and not served:
                    self.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
                    stop = value(lines, 'stop')
                    self.assertTrue(stop.startswith('check failed: '), lines)
                    self.assertIn(kept, stop)
                    self.assertIn('config.toml.prev', stop)
                    self.assertIn("the rollback's", stop)
                    self.assertNotIn(ref(OLD), stop, "the image config.toml runs is not this window's rollback")
                    self.assertNotIn('backup', keys(lines))
                    self.assertEqual(g.p.config(), g.old)
                    self.assertEqual((sha256_file(g.prev), os.stat(g.prev).st_mtime_ns), (sha(text), st.st_mtime_ns))
                    continue
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.p.images(), [ref(NEW)] * 2)


@needs_container
class OneDiskCheck(unittest.TestCase):
    """B4a item 5 (r3 Opus F5): ONE disk_ok, runner-facts.sh's, which pool-image.sh and the updater both source: the
    switch's own check at its boundary is test_unattended.py's (Checks, test_disk_below_runscaler_s_min_free_stops);
    the updater's DUE and its level read the same function at exactly 10 % and 10 % less 1 KiB: test_pass_switch.py."""

    def test_one_copy_in_runner_facts_sh(self):
        b = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'linux-docker')
        texts = {}
        for rel in ('setup/runner-facts.sh', 'setup/pool-image.sh', 'bin/runner-updater'):
            with open(os.path.join(b, rel)) as f:
                texts[rel] = f.read()
        self.assertEqual(texts['setup/runner-facts.sh'].count('\ndisk_ok() {'), 1)
        for rel in ('setup/pool-image.sh', 'bin/runner-updater'):
            self.assertNotIn('disk_ok() {', texts[rel], rel + ' has a disk_ok of its own')
            self.assertNotIn('DISK_PCT=', texts[rel], rel + ' has a DISK_PCT of its own')
        self.assertIn('. "$B/setup/runner-facts.sh"', texts['bin/runner-updater'])


if __name__ == '__main__':
    unittest.main()
