"""bin/runner-updater's timer `pass` ACTS on its verdicts (S3b-4b): R1's `rollback` starts the rollback window
(ru_rollback, with SINCE kept in the state: the 2-h bound), a connect-only rollback allows one retry after 1 h and the
second rejects (the count in the state), a DUE release starts the switch window (ru_window, one family per pass), a
due family that waits 3 days at START STATE or IDLE holds NO IDLE, KEEP's ACCEPT, JOBS FAIL and NO EVIDENCE, and the
7-day deletion of the previous image.

The rig is test_runner_updater_window's (Win: a fake host, the release's bin/ beside the updater, the real core), with
the pass's clock from the test (RU_TEST_NOW; the windows keep the real clock: the pass hands them how long a verdict or
a release has waited, never a date of its own clock), and, for the cells that switch, test_runner_updater_release's
GitHub stub and the mac-golden recipe files under the release folder. Multi-pass scenarios move the pass's clock, never
sleep.
"""
import fcntl
import hashlib
import json
import os
import shutil
import time
import unittest

from tests.studio.support import REPO
from tests.studio.test_runner_updater import INSTALLED, Rig, config, fixture, read_text
from tests.studio.test_runner_updater_recover import assert_closed, assert_runs, n_disable, stops
from tests.studio.test_runner_updater_rollback import CONNECT, NEW, V2, rb_win, rollback, switched
from tests.studio.test_runner_updater_state import KEEP, SUCCESS, Paths, cand, fam, lines_of, on_state, state, stop
from tests.studio.test_runner_updater_window import FAM, KILLED, OLD, V0, Win, healthz, switched_config, today
from tests.studio import test_runner_updater_release as rel

# the pass's clock, from the test when it sets RU_TEST_NOW (every other command keeps the real clock)
CLOCK = ('now=$(/bin/date -u +%s)', 'now=${RU_TEST_NOW:-$(/bin/date -u +%s)}')
MIN, HOUR, DAY = 60, 3600, 86400
# mac-golden's recipe files (bin/runner-updater-release, RL_RECIPE)
RL_FILES = ('bin/golden-build bin/golden-emudhra bin/node-diff-compare bin/real-run bin/tls-excluded-lib '
            'setup/emudhra.node-diff setup/tls-excluded-spki')


def failures(hour=5, connect=False):
    """three counted failures on mac-a at HOUR:00 of 2026-11-01 (log time), settled by a record 2 min later. CONNECT:
    every one connect-class (runscaler's text), else none (another `Failed to start runner` error)"""
    text = fixture('three-failures.log').replace('2026-11-01 05:', '2026-11-01 %02d:' % hour)
    if not connect:
        for i in (1, 2, 3):
            text = text.replace('runner process exited on runner-0000000%d before connecting to GitHub' % i,
                                'tart clone failed for runner-0000000%d' % i)
    return text


def utc(t):
    return time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(t))


def pass_(w, at=None, env=None):
    e = {'RU_TEST_NOW': str(at if at is not None else int(time.time()))}
    e.update(env or {})
    return w.r.cmd('pass', ok=False, env=e)


def family(w):
    return w.u.get()['families'].get(FAM)


class LockHeld:
    """the updater lock held by this test (a POSIX record lock, as zsh's zsystem flock takes it)"""

    def __init__(self, w):
        self.path = os.path.join(w.r.statedir, 'lock')

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.lockf(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self

    def __exit__(self, *a):
        fcntl.lockf(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def gh_rig(w):
    """W's release file answers from test_runner_updater_release's GitHub stub (W.gh) and filters a copy of the system
    bundle; the mac-golden recipe files are under the release folder (RELBIN/..). -> their recipe"""
    sb = w.sb
    w.gh = sb.mkdir('gh')
    curl = sb.write(sb.path('tools-gh2', 'curl'), '#!/bin/zsh -f\n' + rel.GH_STUB.replace('@D@', w.gh), 0o755)
    source = sb.write(sb.path('ca', 'cert.pem'), read_text(rel.SYSTEM_BUNDLE))
    sb.copy_script('bin/runner-updater-release', [('RL_CURL=/usr/bin/curl', 'RL_CURL=' + curl),
                                                  ('RL_SRC=/etc/ssl/cert.pem', 'RL_SRC=' + source)])
    files = dict(rel.BUILDER)
    files['setup/tls-excluded-spki'] = read_text(rel.DATA)
    for path, text in files.items():
        sb.write(sb.path(path), text)
    return rel.recipe_of(files)


def latest(w, v=V2, published=None):
    """GitHub's latest release is runner V (published 3 days ago by the real clock), with its tarball"""
    def route(url, body):
        k = os.path.join(w.gh, rel.key(url))
        w.sb.write(k + '.code', '200\n')
        with open(k + '.body', 'wb') as f:
            f.write(body if isinstance(body, bytes) else body.encode())
    route(rel.API + '/releases/latest', rel.release(v, published=published or int(time.time()) - 3 * DAY))
    route('%s/v%s/actions-runner-osx-arm64-%s.tar.gz' % (rel.DL, v, v), rel.tarball_bytes(v))
    return hashlib.sha256(rel.tarball_bytes(v)).hexdigest()


def journals(w):
    """every window journal, closed (oldest first) and then the open one: a list of lines each"""
    d = os.path.join(w.r.statedir, 'windows')
    out = [lines_of(os.path.join(d, n)) for n in sorted(os.listdir(d)) if not n.endswith('.d')] if os.path.isdir(d) else []
    return out + ([lines_of(w.u.window)] if os.path.exists(w.u.window) else [])


def jvalue(lines, key):
    vals = [l.split(' ', 1)[1] if ' ' in l else '' for l in lines if l.split(' ', 1)[0] == key]
    assert len(vals) == 1, (key, lines)
    return vals[0]


def armed(test, log=None, gh=False, **kw):
    """a Win whose family mac-golden switched to NEW (runner V2; previous OLD); one pass opened its evidence window,
    and the log then gained LOG (default: three counted failures, none connect-class): the next pass's R1 says
    rollback. GH: the GitHub stub and the recipe files (the family's baseline: their recipe; the latest release V2)"""
    f = kw.pop('fam', None) or switched()
    w = Win(test, cfg=config((('mac-a', NEW),)), extra_rewrites=[CLOCK],
            s=state(on=True, families={FAM: f}, images={OLD: V0, NEW: V2}), **kw)
    w.sb.write(os.path.join(w.vms, NEW), '')
    if gh:
        s = w.u.get()
        s['families'][FAM]['recipe'] = w.recipe = gh_rig(w)
        w.u.put(s)
        w.tsha = latest(w)
    w.r.write_log('')
    res = pass_(w)
    test.assertEqual(res.returncode, 0, res.stdout + res.stderr)
    w.r.append_log(fixture('studio-cut.log') + (log if log is not None else failures()))
    return w


class TestR1RollsBack(unittest.TestCase):
    """An R1 `rollback` verdict: the pass calls ru_rollback FAMILY "<r1's verdict>" SINCE. SINCE is the first pass that
    saw the verdict, kept in the state (`r1_since`); the window gets how long it has held."""

    def test_an_r1_verdict_rolls_the_family_back(self):
        w = armed(self)
        res = pass_(w)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('\nr1 %s: rollback (R1 on set mac-a: 3 counted failures' % FAM, res.stdout)
        self.assertIn('runner-updater: pass: rolled back %s: it runs %s again\n' % (FAM, OLD), res.stdout)
        assert_runs(self, w, config((('mac-a', OLD),)).encode())
        assert_closed(self, w)
        self.assertEqual((w.value('kind'), w.value('command'), w.value('reject')), ('rollback', 'pass', V2))
        f = family(w)
        self.assertEqual((f['candidate'], f['previous'], f['rejected']), (None, None, [V2]))
        (s,) = f['stops']
        self.assertEqual((s['stop'], s['version'], len(s['detail']['failures']), s['detail']['connect_only']),
                         ('ROLLED BACK', V2, 3, False))
        self.assertFalse(os.path.exists(os.path.join(w.vms, NEW)))   # the image it left, deleted by its name
        # the next pass: the verdict is gone with the candidate, and so is its SINCE; no second rollback
        res = pass_(w)
        self.assertEqual((res.returncode, n_disable(w)), (0, 1), res.stdout)
        self.assertNotIn('r1_since', family(w))

    def test_control_no_verdict_no_rollback(self):
        w = armed(self, log='')
        res = pass_(w)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertNotIn('rollback', res.stdout.replace('rollback pending', ''))
        self.assertEqual((n_disable(w), family(w)['candidate']['version']), (0, V2))
        self.assertNotIn('r1_since', family(w))

    def test_since_is_the_first_pass_that_saw_the_verdict(self):
        w = armed(self)
        w.validate('unknown')                 # every validate UNKNOWN: the rollback cannot start, it is pending
        t = int(time.time())
        res = pass_(w, t)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn('runner-updater: rollback pending: pre-window validate (pre) is UNKNOWN', res.stdout)
        self.assertEqual((family(w)['r1_since'], n_disable(w)), (t, 0))
        pass_(w, t + 30 * MIN)
        self.assertEqual(family(w)['r1_since'], t)   # kept, never moved

    def test_the_2_h_bound_runs_from_since_also_across_passes_that_found_the_lock_held(self):
        w = armed(self)
        w.validate('unknown')
        t = int(time.time())
        pass_(w, t)
        with LockHeld(w):                     # a timer pass that finds the lock held ends at once
            res = pass_(w, t + HOUR)
        self.assertEqual((res.returncode, res.stdout),
                         (0, 'runner-updater: pass: another run holds the updater lock; this pass ends\n'))
        res = pass_(w, t + 2 * HOUR - MIN)    # the control: within the bound, still pending
        self.assertIn('runner-updater: rollback pending: ', res.stdout)
        self.assertEqual(stops(w), [])
        res = pass_(w, t + 2 * HOUR)          # from SINCE, not from the pass after the lock
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP ROLLBACK FAILED: ', res.stdout)
        self.assertEqual((stops(w), n_disable(w)), (['ROLLBACK FAILED'], 0))

    def test_a_held_rollback_failed_starts_no_rollback_and_retry_restarts_since(self):
        # P3-a: `retry` clears a ROLLBACK FAILED raised by the 2-h bound and SINCE restarts, else the next call would
        # fail again at once
        w = armed(self)
        w.validate('unknown')
        t = int(time.time())
        pass_(w, t)
        pass_(w, t + 2 * HOUR)
        self.assertEqual(stops(w), ['ROLLBACK FAILED'])
        res = pass_(w, t + 2 * HOUR + 10 * MIN)
        self.assertIn('runner-updater: pass: %s: R1\'s rollback is due, but ROLLBACK FAILED holds it: '
                      '`runner-updater retry %s`' % (FAM, FAM), res.stdout)
        self.assertNotIn('runner-updater: STOP', res.stdout)
        self.assertEqual(w.r.cmd('retry', FAM).returncode, 0)
        self.assertNotIn('r1_since', family(w))
        res = pass_(w, t + 3 * HOUR)
        self.assertIn('runner-updater: rollback pending: ', res.stdout)
        self.assertEqual((stops(w), family(w)['r1_since']), ([], t + 3 * HOUR))

    def test_a_rollback_whose_journal_stays_open_is_ended_by_the_next_pass(self):
        w = armed(self)
        w.put('disable-fail')                 # runner-disable times out: the rollback could not start
        res = pass_(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertTrue(os.path.exists(w.u.window))
        os.remove(os.path.join(w.scn, 'disable-fail'))
        res = pass_(w)                        # RECOVER brings CI back, then R1 (still armed) rolls back
        self.assertIn('runner-updater: recover: ', res.stdout)
        self.assertIn('runner-updater: pass: rolled back %s' % FAM, res.stdout)
        assert_closed(self, w)
        assert_runs(self, w, config((('mac-a', OLD),)).encode())
        self.assertIsNone(family(w)['candidate'])


class TestConnectOnlyCount(unittest.TestCase):
    """CONNECT-ONLY (PLAN D6 :320; S3b-4a r1 P3-5): the count of a version's connect-only rollbacks lives IN THE STATE
    (the family's `connect_only`: {VERSION: {n, at}}), never in a STOP: the first rejects nothing and is counted; one
    with the count already there is the second and rejects, whatever STOP is held; `retry` never resets it."""

    def test_the_first_connect_only_rollback_is_counted_and_rejects_nothing(self):
        w = rb_win(self)
        t = int(time.time())
        self.assertEqual(rollback(w, reason=CONNECT).returncode, 0)
        f = family(w)
        self.assertEqual((f['rejected'], jvalue(journals(w)[-1], 'reject')), ([], 'none'))
        c = f['connect_only'][V2]
        self.assertEqual(c['n'], 1)
        self.assertLessEqual(abs(c['at'] - t), 5)

    def test_with_the_count_and_no_stop_the_second_rejects(self):
        # the STOP is gone (`retry`, or the pass's 1-h retry cleared it): the count alone makes it the second
        w = rb_win(self, families={FAM: switched(connect_only={V2: {'n': 1, 'at': int(time.time()) - 2 * HOUR}})})
        self.assertEqual(rollback(w, reason=CONNECT).returncode, 0)
        self.assertEqual((family(w)['rejected'], jvalue(journals(w)[-1], 'reject')), ([V2], V2))

    def test_control_the_count_of_another_version_does_not(self):
        w = rb_win(self, families={FAM: switched(connect_only={'2.338.9': {'n': 1, 'at': int(time.time())}})})
        self.assertEqual(rollback(w, reason=CONNECT).returncode, 0)
        self.assertEqual(family(w)['rejected'], [])

    def test_retry_never_resets_the_count(self):
        held = [stop(FAM, 'ROLLED BACK', version=V2, detail={'connect_only': True, 'failures': []})]
        count = {V2: {'n': 1, 'at': int(time.time())}}
        w = rb_win(self, families={FAM: fam(previous={'mac-a': OLD}, rejected=[V2], stops=held, connect_only=count)})
        self.assertEqual(w.r.cmd('retry', FAM).returncode, 0)
        f = family(w)
        self.assertEqual((f['stops'], f['rejected'], f['connect_only']), ([], [], count))


class TestConnectOnlyRetryAfter1h(unittest.TestCase):
    """The pass: a connect-only ROLLED BACK of V holds V (it is of the eligible release) until 1 h after that rollback;
    then the pass clears it and V is due again: ONE retry (a switch window); R1 again rolls it back, and that second
    rollback rejects V."""

    def test_one_retry_after_1_h_and_the_second_rollback_rejects(self):
        w = armed(self, log=failures(connect=True), gh=True)
        res = pass_(w)                                     # the first connect-only rollback
        self.assertIn('runner-updater: pass: rolled back %s' % FAM, res.stdout)
        self.assertEqual((family(w)['rejected'], stops(w)), ([], ['ROLLED BACK']))
        t1, n = int(time.time()), n_disable(w)
        res = pass_(w, t1 + HOUR - MIN)                    # the control: before 1 h, V2 is held
        self.assertIn('runner-updater: pass: %s is not due: STOP ROLLED BACK (runner %s): it is of the eligible '
                      'release' % (FAM, V2), res.stdout)
        self.assertNotIn('the one retry', res.stdout)
        self.assertEqual((n_disable(w), stops(w)), (n, ['ROLLED BACK']))
        res = pass_(w, t1 + HOUR)                          # 1 h on: its one retry
        self.assertIn('runner-updater: pass: %s: its connect-only rollback of runner %s was 1 h ago or more: the one '
                      'retry of %s may start (a second rollback rejects it)' % (FAM, V2, V2), res.stdout)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['stops'], n_disable(w)), (V2, [], n + 1))
        self.assertEqual(jvalue(journals(w)[-1], 'command'), 'pass')
        # R1 again: the second rollback rejects it
        pass_(w)
        w.r.append_log(failures(hour=6, connect=True))
        res = pass_(w)
        self.assertIn('runner-updater: pass: rolled back %s' % FAM, res.stdout)
        self.assertEqual((family(w)['rejected'], jvalue(journals(w)[-1], 'reject')), ([V2], V2))
        # it is counted too, so its ROLLED BACK stays past 1 h (status keeps naming `retry`)
        t2 = int(time.time())
        res = pass_(w, t2 + 2 * HOUR)
        self.assertNotIn('the one retry', res.stdout)
        self.assertEqual((stops(w), family(w)['connect_only'][V2]['n']), (['ROLLED BACK'], 2))


def due_win(test, families='mac-golden tart mac-a\n', images=None, **famkw):
    """a Win whose family mac-golden runs OLD (runner V0) with the recipe of its files as its baseline (unless FAMKW
    says otherwise); GitHub's latest release V2 is 3 days old: a pass finds the family DUE"""
    w = Win(test, families=families, extra_rewrites=[CLOCK])
    w.recipe = gh_rig(w)
    f = dict(recipe=w.recipe)
    f.update(famkw)
    w.u.put(state(on=True, families={FAM: fam(**f)}, images=images or {OLD: V0}))
    w.tsha = latest(w)
    return w


def busy(w):
    """every /healthz read: mac-a ready and busy (START STATE passes, the idle pair says not idle)"""
    h = healthz('mac-a')
    h['scale_sets'][0]['busy'] = 1
    w.r.set_curl(json.dumps(h))


class TestDueSwitches(unittest.TestCase):
    """A DUE release (bin/runner-updater-release, rl_pass) starts the switch window (ru_window FAMILY V SHA idle SINCE
    pass): one window per pass, only when no journal is open. ONE OPEN RELEASE PER FAMILY: an open candidate, or a
    previous image kept for `back`, holds it."""

    def test_a_due_release_switches_the_family(self):
        w = due_win(self)
        res = pass_(w)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        out = 'liveapp-mac-golden-' + today()
        self.assertIn('runner-updater: pass: %s is due: runner %s\n' % (FAM, V2), res.stdout)
        self.assertIn('runner-updater: pass: switched %s to %s (runner %s)\n' % (FAM, out, V2), res.stdout)
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['candidate']['lines'], f['previous']),
                         (V2, {'mac-a': out}, {'mac-a': OLD}))
        j = journals(w)[-1]
        self.assertEqual([jvalue(j, k) for k in ('kind', 'command', 'version', 'runner-sha', 'idle')],
                         ['switch', 'pass', V2, w.tsha, 'idle'])
        assert_runs(self, w, switched_config(w.pre, out))
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V2, w.tsha))
        res = pass_(w)                                       # one open release per family
        self.assertIn('runner-updater: pass: %s is not due: an open candidate (runner %s)' % (FAM, V2), res.stdout)
        self.assertEqual(n_disable(w), 1)

    def test_control_a_rejected_release_starts_no_window(self):
        w = due_win(self, rejected=[V2])
        res = pass_(w)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn('runner-updater: pass: %s is not due: release v%s is rejected for %s' % (FAM, V2, FAM), res.stdout)
        self.assertEqual((n_disable(w), journals(w), family(w)['candidate']), (0, [], None))

    def test_a_previous_image_kept_for_back_holds_the_family(self):
        until = int(time.time()) + DAY
        w = due_win(self, previous={'mac-a': 'liveapp-mac-golden-20260901'}, back_until=until)
        res = pass_(w)
        self.assertIn('runner-updater: pass: %s is not due: its previous image is kept for `back` until %s: one open '
                      'release per family' % (FAM, time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(until))), res.stdout)
        self.assertEqual(n_disable(w), 0)

    def test_control_after_back_until_the_family_is_due(self):
        w = due_win(self, previous={'mac-a': 'liveapp-mac-golden-20260901'}, back_until=int(time.time()) - MIN)
        res = pass_(w)
        self.assertIn('runner-updater: pass: switched %s to ' % FAM, res.stdout)

    def test_one_window_per_pass(self):
        # a second family with a builder (both wired here by the test; this release wires mac-golden alone) that is
        # due too waits for the next pass
        w = due_win(self, families='mac-golden tart mac-a\nfx tart mac-b\n',
                    images={OLD: V0, 'liveapp-mac-golden-20260902': V0})
        w.sb.copy_script('bin/runner-updater-release', [
            ('RL_CURL=/usr/bin/curl', 'RL_CURL=' + w.sb.path('tools-gh2', 'curl')),
            ('RL_SRC=/etc/ssl/cert.pem', 'RL_SRC=' + w.sb.path('ca', 'cert.pem')),
            ("RL_RECIPE=(mac-golden '", "RL_RECIPE=(fx '%s' mac-golden '" % RL_FILES)])
        w.sb.write(w.r.config, config((('mac-a', OLD), ('mac-b', 'liveapp-mac-golden-20260902'))))
        os.utime(w.r.config, (INSTALLED, INSTALLED))
        w.r.set_curl(json.dumps(healthz('mac-a', 'mac-b')))   # the idle pair reads every set of the config
        s = w.u.get()
        s['families']['fx'] = fam(recipe=w.recipe)
        w.u.put(s)
        w.sb.write(os.path.join(w.vms, 'liveapp-mac-golden-20260902'), '')
        w.r.script = w.r.copy('runner-updater', [CLOCK, ('BUILDERS=(mac-golden)', 'BUILDERS=(mac-golden fx)')])
        res = pass_(w)
        self.assertIn('runner-updater: pass: switched %s to ' % FAM, res.stdout)
        self.assertIn('runner-updater: pass: fx: one window per pass: the next pass switches it to %s\n' % V2, res.stdout)
        self.assertEqual((n_disable(w), len(journals(w))), (1, 1))
        self.assertEqual(w.u.get()['families']['fx']['stops'], [])


class TestDueSince(unittest.TestCase):
    """The pass keeps when the family became due for a release (`due`: {version, since}), the first pass that found it
    due, and gives the window how long it has waited: NO IDLE (PLAN D5 :285) after 3 days at START STATE or IDLE."""

    def test_since_is_kept_across_passes_that_were_not_now(self):
        w = due_win(self)
        busy(w)
        t = int(time.time())
        res = pass_(w, t)
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn('runner-updater: pass %s: not now: IDLE: ' % FAM, res.stdout)
        self.assertEqual(family(w)['due'], {'version': V2, 'since': t})
        pass_(w, t + HOUR)
        self.assertEqual((family(w)['due'], n_disable(w)), ({'version': V2, 'since': t}, 0))

    def test_no_idle_3_days_after_the_family_became_due(self):
        w = due_win(self)
        busy(w)
        t = int(time.time())
        pass_(w, t)
        res = pass_(w, t + 3 * DAY - MIN)                  # the control: a minute short of 3 days
        self.assertIn('runner-updater: pass %s: not now: IDLE: ' % FAM, res.stdout)
        self.assertEqual(stops(w), [])
        res = pass_(w, t + 3 * DAY)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: STOP NO IDLE: IDLE: ', res.stdout)
        (s,) = family(w)['stops']
        self.assertEqual((s['stop'], s['version'], s['detail']['sha']), ('NO IDLE', V2, w.tsha))
        self.assertIn('Next: `runner-updater switch-now %s`' % FAM, w.status())
        self.assertEqual(n_disable(w), 0)
        res = pass_(w, t + 3 * DAY + HOUR)                 # NO IDLE holds the family: no window
        self.assertIn('runner-updater: pass: %s is not due: STOP NO IDLE (runner %s)' % (FAM, V2), res.stdout)
        # switch-now takes its release; the next pass finds the candidate, and `due` is gone
        res = w.run('switch-now')
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        pass_(w, t + 3 * DAY + 2 * HOUR)
        f = family(w)
        self.assertEqual((f['candidate']['version'], f['stops'], 'due' in f), (V2, [], False))


class TestRecipeStops(unittest.TestCase):
    """NO BASELINE and recipe changed (PLAN D2 :143) are STOPs the pass HOLDS for a family with no candidate, so status
    shows them with `rebuild FAMILY`; it drops them when the recipe is the baseline again, and for a family with a
    candidate (a rebuild's: its ACCEPT writes the baseline), before the core reads the STOPs."""

    def test_no_baseline_is_held(self):
        w = due_win(self, recipe=None)
        res = pass_(w)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: pass: %s is not due: STOP NO BASELINE: the family has no recipe baseline (its '
                      'recipe now: %s)' % (FAM, w.recipe), res.stdout)
        (s,) = family(w)['stops']
        self.assertEqual((s['family'], s['stop'], s['version']), (FAM, 'NO BASELINE', None))
        self.assertIn('\n%s: STOP NO BASELINE: the family has no recipe baseline (its recipe now: %s)' % (FAM, w.recipe),
                      w.status())
        self.assertIn('Next: `runner-updater rebuild %s`' % FAM, w.status())
        res = pass_(w)                                      # held once; the next pass changes nothing
        self.assertEqual((res.returncode, stops(w)), (0, ['NO BASELINE']))

    def test_recipe_changed_is_held(self):
        w = due_win(self, recipe='a' * 64)
        pass_(w)
        (s,) = family(w)['stops']
        self.assertEqual(s['stop'], 'recipe changed')
        self.assertIn('its recipe is %s, its baseline %s' % (w.recipe, 'a' * 64), s['detail']['text'])
        self.assertEqual(n_disable(w), 0)

    def test_a_recipe_stop_goes_when_the_recipe_is_the_baseline(self):
        held = [stop(FAM, 'NO BASELINE', version=None, detail={'text': 'x'})]
        w = due_win(self, rejected=[V2], stops=held)
        res = pass_(w)
        self.assertIn('is not due: release v%s is rejected' % V2, res.stdout)
        self.assertEqual(stops(w), [])

    def test_a_recipe_stop_goes_for_a_family_with_a_candidate_before_keep_reads_it(self):
        held = [stop(FAM, 'NO BASELINE', version=None, detail={'text': 'x'})]
        w = due_win(self, recipe=None, stops=held, candidate=cand(V0, {'mac-a': OLD}, int(time.time()) - HOUR),
                    previous={'mac-a': 'liveapp-mac-golden-20260901'})
        res = pass_(w)
        self.assertIn('\nkeep %s: observe (' % FAM, res.stdout)
        self.assertEqual(stops(w), [])


def core_copy(r, prog, verdict):
    """a copy of core/ in R's sandbox whose PROG prints VERDICT (one exact edit at its end); -> its path"""
    d = r.sb.path('core-copy')
    shutil.copytree(os.path.join(REPO, 'core'), d)
    p = os.path.join(d, prog + '.jq')
    text = read_text(p).rstrip('\n')
    r.sb.write(p, text + '\n| .verdict = %s\n' % json.dumps(verdict))
    return d


class TestDecided(unittest.TestCase):
    """decided() accepts only the verdicts core/README.md gives each program (idle: idle, not-idle, wait; r1, keep and
    status: ok, wait). Another verdict is "core could not decide" (exit 1, the state as it was); `wait` is a WAIT: exit
    4 and the state byte-equal (a pass's STATE; a report's REPORT/state.json)."""

    def run_with(self, cmd, prog, verdict):
        r = Rig(self)
        u = Paths(r)
        u.put(on_state())
        if cmd == 'report':
            r.report()
        else:
            r.cmd('pass')
        core = core_copy(r, prog, verdict)
        script = r.copy('runner-updater', [('CORE=' + os.path.join(REPO, 'core'), 'CORE=' + core)])
        before = (u.raw(), r.state_bytes())
        res = r.cmd(cmd, script=script, ok=False)
        return res, before, (u.raw(), r.state_bytes())

    def test_a_verdict_the_program_does_not_give_is_could_not_decide(self):
        for cmd in ('pass', 'report'):
            for prog, verdict in (('idle', 'ok'), ('r1', 'idle'), ('keep', 'accept'), ('status', 'maybe'),
                                  ('r1', None)):
                with self.subTest(cmd=cmd, prog=prog, verdict=verdict):
                    res, before, after = self.run_with(cmd, prog, verdict)
                    self.assertEqual(res.returncode, 1, res.stdout)
                    self.assertIn('runner-updater: core could not decide (%s)' % prog, res.stdout)
                    self.assertEqual(after, before)

    def test_control_each_programs_own_verdicts_decide(self):
        for cmd in ('pass', 'report'):
            for prog, verdict in (('idle', 'not-idle'), ('r1', 'ok'), ('keep', 'ok'), ('status', 'ok')):
                with self.subTest(cmd=cmd, prog=prog, verdict=verdict):
                    res, before, after = self.run_with(cmd, prog, verdict)
                    self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_wait_is_exit_4_with_the_state_byte_equal(self):
        for cmd in ('pass', 'report'):
            for prog in ('idle', 'r1', 'keep', 'status'):
                with self.subTest(cmd=cmd, prog=prog):
                    res, before, after = self.run_with(cmd, prog, 'wait')
                    self.assertEqual(res.returncode, 4, res.stdout)
                    self.assertIn('runner-updater: WAIT the core waits (%s): ' % prog, res.stdout)
                    self.assertEqual(after, before)

    def test_status_takes_only_its_own_verdicts_too(self):
        for verdict, rc in (('maybe', 1), ('accept', 1), ('ok', 0), ('wait', 0)):
            with self.subTest(verdict=verdict):
                r = Rig(self)
                Paths(r).put(on_state())
                script = r.copy('runner-updater', [('CORE=' + os.path.join(REPO, 'core'),
                                                    'CORE=' + core_copy(r, 'status', verdict))])
                res = r.cmd('status', script=script, ok=False)
                self.assertEqual(res.returncode, rc, res.stdout)
                if rc:
                    self.assertIn('runner-updater: STOP core could not decide (status)', res.stdout)

    def test_a_core_state_of_another_format_waits(self):
        # the real core: a state whose `core` member has another format makes idle.jq (the first) say wait
        r = Rig(self)
        u = Paths(r)
        s = on_state()
        s['core'] = {'format': 2}
        raw = u.put(s)
        res = r.cmd('pass', ok=False)
        self.assertEqual(res.returncode, 4, res.stdout)
        self.assertIn('runner-updater: WAIT the core waits (idle): unknown state format: idle: the state has format 2; '
                      'this core reads format 1: waiting\n', res.stdout)
        self.assertEqual(u.raw(), raw)


class TestCiDisabledCleared(unittest.TestCase):
    """S3b-4a r3 P3-b: RECOVER's no-action STOP CI DISABLED (CI down, and a journal that shows no runner-disable of
    its own) holds the family until a window disables CI again; when no window journal is open, CI's flag is present
    and one runscaler runs (a person ran runner-enable), the pass clears it, before the core reads the STOPs. The
    controls: no flag; no runscaler."""

    HELD = [stop(FAM, 'CI DISABLED', version=None, detail={'text': 'x', 'hand': '/x/runner-enable'})]

    def win(self):
        w = Win(self, cfg=config((('mac-a', NEW),)), extra_rewrites=[CLOCK],
                s=state(on=True, families={FAM: switched(stops=self.HELD)}, images={OLD: V0, NEW: V2}))
        w.sb.write(os.path.join(w.vms, NEW), '')
        return w

    def test_ci_up_again_clears_it_before_the_core_reads_it(self):
        w = self.win()
        res = pass_(w)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('runner-updater: pass: CI is enabled and runscaler runs: STOP CI DISABLED of %s is cleared\n' % FAM,
                      res.stdout)
        self.assertIn('\nkeep %s: observe (' % FAM, res.stdout)
        self.assertEqual(stops(w), [])

    def test_control_no_flag_keeps_it(self):
        w = self.win()
        os.remove(w.r.flag)
        res = pass_(w)
        self.assertIn('\nkeep %s: held (CI DISABLED stands' % FAM, res.stdout)
        self.assertEqual(stops(w), ['CI DISABLED'])

    def test_control_no_runscaler_keeps_it(self):
        w = self.win()
        w.r.set_ps([])
        pass_(w)
        self.assertEqual(stops(w), ['CI DISABLED'])


def job(result, hour=9):
    """one job of mac-a completed with RESULT at HOUR:30 of 2026-11-01 (log time), and a record a minute later"""
    return SUCCESS.replace('2026-11-01 09:', '2026-11-01 %02d:' % hour).replace('result=succeeded', 'result=' + result)


def switched_and_open(test, **kw):
    """a due_win whose pass switched mac-golden to V2 (t0), and whose next pass (t1, returned) opened its evidence
    window through the window's own restart"""
    w = due_win(test, **kw)
    res = pass_(w)
    test.assertIn('runner-updater: pass: switched %s to ' % FAM, res.stdout)
    t1 = int(time.time())
    res = pass_(w, t1)
    test.assertIn('\nkeep %s: observe (runner %s: observing since ' % (FAM, V2), res.stdout)
    return w, t1


class TestAccept(unittest.TestCase):
    """KEEP's ACCEPT (PLAN D6 :324, :330; D2 :143): 72 h after the evidence window opened, a job succeeded: the pass
    writes the recipe baseline (the candidate's: the recipe its window built with), sets back_until = now + 7 days,
    clears the candidate and keeps `previous` until then (the protected list keeps it), and the pin follows D2's ONE
    RULE. A switch, KEEP over 72 h on the pass's clock, then ACCEPT, and the deletion after 7 days."""

    def test_switch_keep_accept_then_the_deletion_after_7_days(self):
        w, t1 = switched_and_open(self)
        out = family(w)['candidate']['lines']['mac-a']
        self.assertEqual(family(w)['candidate']['recipe'], w.recipe)
        w.r.append_log(job('succeeded'))
        res = pass_(w, t1 + KEEP - 1)                    # the control: a second short of 72 h
        self.assertIn('\nkeep %s: observe (' % FAM, res.stdout)
        self.assertEqual(family(w)['candidate']['version'], V2)
        res = pass_(w, t1 + KEEP)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        until = t1 + KEEP + 7 * DAY
        self.assertIn('runner-updater: pass: accepted %s: runner %s: 1 succeeded of 1 completed in 72 h; `runner-updater '
                      'back %s` restores %s until %s\n' % (FAM, V2, FAM, OLD, utc(until)), res.stdout)
        f = family(w)
        self.assertEqual((f['candidate'], f['previous'], f['back_until'], f['recipe'], f['stops']),
                         (None, {'mac-a': OLD}, until, w.recipe, []))
        self.assertEqual(lines_of(w.u.protected), [OLD])  # previous, kept for `back`
        self.assertIn('%s: `runner-updater back %s` restores the previous image until %s' % (FAM, FAM, utc(until)),
                      w.status())
        n = n_disable(w)
        res = pass_(w, until - 1)                         # the control: a second before back_until
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertEqual(family(w)['previous'], {'mac-a': OLD})
        res = pass_(w, until)                             # 7 days on: deleted by its recorded name
        self.assertIn('runner-updater: pass: deleted %s (the previous image of %s, kept for `back` until %s)\n'
                      % (OLD, FAM, utc(until)), res.stdout)
        self.assertFalse(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertEqual(lines_of(w.u.actions)[-1], 'delete ' + OLD)
        f = family(w)
        self.assertEqual((f['previous'], f['back_until']), (None, None))
        self.assertEqual(lines_of(w.u.protected), [])
        self.assertEqual(n_disable(w), n)                 # no window
        self.assertTrue(os.path.exists(os.path.join(w.vms, out)))

    def test_the_pin_follows_the_one_rule(self):
        # the pin was removed (off, then on): the accept writes it again, the version the config runs, with the sha
        # of its family's closed journal; journaled first in ACTIONS
        w, t1 = switched_and_open(self)
        os.remove(w.pin)
        w.r.append_log(job('succeeded'))
        pass_(w, t1 + KEEP)
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V2, w.tsha))
        self.assertEqual(lines_of(w.u.actions), ['pin-write %s %s %s' % (FAM, V2, w.tsha)])

    def test_control_a_pin_that_follows_the_rule_already_is_left(self):
        w, t1 = switched_and_open(self)
        w.r.append_log(job('succeeded'))
        pass_(w, t1 + KEEP)
        self.assertEqual(read_text(w.pin), '%s %s\n' % (V2, w.tsha))
        self.assertFalse(os.path.exists(w.u.actions))


class TestRebuildBaseline(unittest.TestCase):
    """D2: NO BASELINE until `rebuild FAMILY`; its ACCEPT writes the recipe (the one its window built with, kept in
    the candidate)."""

    def test_the_accept_of_a_rebuild_writes_the_baseline(self):
        w = due_win(self, recipe=None, rejected=[V2])
        pass_(w)
        self.assertEqual(stops(w), ['NO BASELINE'])
        self.assertEqual(w.run('rebuild').returncode, 0)
        self.assertEqual(family(w)['candidate']['recipe'], w.recipe)
        t1 = int(time.time())
        pass_(w, t1)
        self.assertEqual(stops(w), [])                   # a family with a candidate holds no recipe STOP
        w.r.append_log(job('succeeded'))
        pass_(w, t1 + KEEP)
        self.assertEqual((family(w)['recipe'], family(w)['candidate']), (w.recipe, None))


class TestJobsFail(unittest.TestCase):
    """72 h, completions, none succeeded: STOP JOBS FAIL ON THE NEW IMAGE, held with the job counts; its status line
    names `back` and `retry`. The candidate stays (R1 stays armed)."""

    def test_jobs_fail(self):
        w, t1 = switched_and_open(self)
        w.r.append_log(job('failed'))
        res = pass_(w, t1 + KEEP)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: pass: %s holds STOP JOBS FAIL ON THE NEW IMAGE: runner %s: 1 jobs completed in '
                      '72 h, none succeeded' % (FAM, V2), res.stdout)
        f = family(w)
        (s,) = f['stops']
        self.assertEqual((s['stop'], s['version'], s['detail']['counts']),
                         ('JOBS FAIL ON THE NEW IMAGE', V2, {'completions': 1, 'succeeded': 0, 'failed': 1, 'canceled': 0}))
        self.assertEqual(f['candidate']['version'], V2)
        st = w.status()
        self.assertIn('%s: STOP JOBS FAIL ON THE NEW IMAGE (runner %s): 1 completed, 0 succeeded, 1 failed, 0 canceled. '
                      'Next: `runner-updater back %s` (until the keep date), or `runner-updater retry %s` to keep it'
                      % (FAM, V2, FAM, FAM), st)
        res = pass_(w, t1 + KEEP + HOUR)                  # held once
        self.assertEqual((res.returncode, stops(w)), (0, ['JOBS FAIL ON THE NEW IMAGE']))


class TestNoEvidence(unittest.TestCase):
    """72 h and no job completed: STOP NO EVIDENCE, held; it heals by itself: a later success accepts and drops it."""

    def test_no_evidence_then_a_success_heals_it(self):
        w, t1 = switched_and_open(self)
        res = pass_(w, t1 + KEEP)
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn('runner-updater: pass: %s holds STOP NO EVIDENCE: runner %s: no job completed in 72 h'
                      % (FAM, V2), res.stdout)
        self.assertEqual(stops(w), ['NO EVIDENCE'])
        self.assertIn('Next: `runner-updater retry %s`' % FAM, w.status())
        res = pass_(w, t1 + KEEP + HOUR)                  # held once
        self.assertEqual((res.returncode, stops(w)), (0, ['NO EVIDENCE']))
        w.r.append_log(job('succeeded'))
        res = pass_(w, t1 + KEEP + 2 * HOUR)
        self.assertIn('runner-updater: pass: accepted %s' % FAM, res.stdout)
        self.assertEqual((stops(w), family(w)['candidate']), ([], None))


class TestDeletion(unittest.TestCase):
    """DELETION (PLAN D6 :332): after back_until, `previous` is deleted by its recorded name, only when no non-comment
    config line names it (and no window journal is open), journaled first in ACTIONS; the state drops it, and so does
    the protected list. An image the updater never recorded (a person's) is never deleted."""

    def win(self, cfg=None, images=None, families=None):
        until = int(time.time()) - MIN
        w = Win(self, cfg=cfg or config((('mac-a', NEW),)), extra_rewrites=[CLOCK],
                s=state(on=True, families=families or {FAM: fam(previous={'mac-a': OLD}, back_until=until)},
                        images=images if images is not None else {OLD: V0, NEW: V2}))
        w.sb.write(os.path.join(w.vms, NEW), '')
        return w

    def test_a_config_line_that_names_it_keeps_it(self):
        w = self.win(cfg=config((('mac-a', NEW), ('mac-c', OLD))))
        res = pass_(w)
        self.assertIn('runner-updater: pass: %s stays: a line of %s names it' % (OLD, w.r.config), res.stdout)
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertFalse(os.path.exists(w.u.actions))
        self.assertEqual(family(w)['previous'], None)    # no longer the updater's to keep

    def test_a_persons_image_is_never_deleted(self):
        w = self.win(images={NEW: V2})
        res = pass_(w)
        self.assertIn('runner-updater: pass: %s stays: the updater has no record of it' % OLD, res.stdout)
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))

    def test_control_a_recorded_image_no_line_names_is_deleted(self):
        w = self.win()
        pass_(w)
        self.assertFalse(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertEqual(lines_of(w.u.actions), ['delete ' + OLD])

    def test_a_delete_that_fails_keeps_previous_for_the_next_pass(self):
        w = self.win()
        os.remove(os.path.join(w.vms, OLD))
        os.mkdir(os.path.join(w.vms, OLD))                # the fake tart cannot delete it (tart delete fails)
        res = pass_(w)
        self.assertIn('runner-updater: pass: cannot delete %s (tart delete failed): the next pass tries again' % OLD,
                      res.stdout)
        self.assertEqual(family(w)['previous'], {'mac-a': OLD})
        os.rmdir(os.path.join(w.vms, OLD))
        w.sb.write(os.path.join(w.vms, OLD), '')
        pass_(w)                                          # the next pass deletes it
        self.assertEqual((os.path.exists(os.path.join(w.vms, OLD)), family(w)['previous']), (False, None))

    def test_a_family_dropped_from_the_families_file_is_cleaned_up_too(self):
        # S3b-2a r1 carry: no 7-day refusal of every pass; its previous image goes after back_until
        w = self.win(families={'fz': fam(previous={'mac-c': OLD}, back_until=int(time.time()) - MIN)})
        res = pass_(w)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertEqual(w.u.get()['families']['fz']['previous'], None)

    def test_a_kill_after_the_journal_line_leaves_the_image_and_the_next_pass_deletes_it(self):
        w = self.win()
        res = pass_(w, env={'RU_KILL_AT': 'delete'})       # runner-journal kills the pass right after its line
        self.assertEqual(res.returncode, KILLED, res.stdout)
        self.assertTrue(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertEqual(family(w)['previous'], {'mac-a': OLD})
        pass_(w)
        self.assertFalse(os.path.exists(os.path.join(w.vms, OLD)))
        self.assertEqual((lines_of(w.u.actions), family(w)['previous']), (['delete ' + OLD] * 2, None))


if __name__ == '__main__':
    unittest.main()
