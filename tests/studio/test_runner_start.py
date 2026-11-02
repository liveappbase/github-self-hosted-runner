"""runner-start validate [CONFIG]: with CONFIG, the token-file, shim and image checks read CONFIG and the runner
validates CONFIG; without it, the constant config. `run` takes no CONFIG. Every REFUSE is on stderr. Only `run` cuts a
log over 10 MB.

A copy runs with its host paths rewritten into a sandbox. Its PATH starts with a folder whose `tart` stub IS the
rewritten SHIM path; that stub lists the images of a scenario file. The RUNNER stub logs its argv.
"""
import os
import unittest

from tests.studio.support import Sandbox

SCRIPT = 'bin/runner-start'
BUILD = '27A123'
HAVE = 'liveapp-mac-golden-20261001'
MISSING = 'liveapp-mac-golden-20261002'
USAGE = 'runner-start: REFUSE usage: runner-start run | runner-start validate [CONFIG]\n'


def config(image, token='A'):
    return '[[scaleset]]\nname = "x"\ntoken = "env:RUNNER_TOKEN_%s"\nrunner-image = "%s"\n' % (token, image)


class Rig:
    def __init__(self, test):
        sb = self.sb = Sandbox(test)
        fake = sb.mkdir('fake')
        shimdir = sb.mkdir('shimdir')
        self.cfgdir = sb.mkdir('config')
        self.config = os.path.join(self.cfgdir, 'config.toml')
        sb.stub('runner', 'exit 0', folder=fake)
        sb.stub('tart', '[[ $* == "list --source local -q" ]] && print -rl -- %s' % HAVE, folder=shimdir)
        sb.stub('sw_vers', '[[ $1 == -buildVersion ]] && print -r -- ' + BUILD, folder=fake)
        self.script = sb.copy_script(SCRIPT, [
            ('RUNNER=/Users/ci/bin/runner', 'RUNNER=' + os.path.join(fake, 'runner')),
            ('CONFIG=/Users/ci/.config/runner/config.toml', 'CONFIG=' + self.config),
            ('TOKEN_DIR=/Users/ci/.config/runner', 'TOKEN_DIR=' + self.cfgdir),
            ('LOGDIR=/Users/ci/Library/Logs/mac-runner', 'LOGDIR=' + sb.mkdir('logdir')),
            ('SHIM=/usr/local/libexec/liveapp-ci/tart', 'SHIM=' + os.path.join(shimdir, 'tart')),
            ('STAMP=/Users/ci/.config/runner/wall-stamp', 'STAMP=' + os.path.join(self.cfgdir, 'wall-stamp')),
            ('export PATH=/usr/local/libexec/liveapp-ci:/Users/ci/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
             'export PATH=%s:/usr/bin:/bin:/usr/sbin:/sbin' % shimdir),
            ('/usr/bin/sw_vers', os.path.join(fake, 'sw_vers')),
        ], allow=['Run /Users/ci/bin/runner-disable, then /Users/ci/bin/wall-check, then /Users/ci/bin/runner-enable'])
        sb.write(os.path.join(self.cfgdir, 'wall-stamp'), 'macos %s\n' % BUILD)
        sb.write(os.path.join(self.cfgdir, 'token-a'), 'secret-a\n', 0o600)
        sb.write(self.config, config(HAVE))

    def temp_config(self, text):
        return self.sb.write(self.sb.path('tmpcfg', 'config.toml'), text)

    def run(self, *args):
        return self.sb.run(['/bin/zsh', '-f', self.script] + list(args))

    def runner(self):
        return self.sb.calls('runner')


class TestValidateConfig(unittest.TestCase):
    def test_image_missing_from_the_given_config_is_refused(self):
        r = Rig(self)
        tmp = r.temp_config(config(MISSING))
        res = r.run('validate', tmp)
        self.assertEqual((res.returncode, res.stdout), (1, ''))
        self.assertEqual(res.stderr, 'runner-start: REFUSE configured runner-image is not on this host: %s\n' % MISSING)
        self.assertEqual(r.runner(), [])

    def test_control_the_given_config_is_validated(self):
        r = Rig(self)
        tmp = r.temp_config(config(HAVE))
        res = r.run('validate', tmp)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(r.runner(), [['validate', '--config', tmp]])

    def test_token_file_named_by_the_given_config_is_checked(self):
        r = Rig(self)
        tmp = r.temp_config(config(HAVE, token='B'))
        res = r.run('validate', tmp)
        self.assertEqual((res.returncode, res.stdout), (1, ''))
        self.assertEqual(res.stderr, 'runner-start: REFUSE token file missing or empty: %s\n'
                         % os.path.join(r.cfgdir, 'token-b'))
        self.assertEqual(r.runner(), [])

    def test_no_config_uses_the_constant(self):
        r = Rig(self)
        res = r.run('validate')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(r.runner(), [['validate', '--config', r.config]])

    def test_bad_config_arguments_are_refused(self):
        def link(r, tmp):
            os.symlink(tmp, r.sb.path('tmpcfg', 'link.toml'))
            return r.sb.path('tmpcfg', 'link.toml')
        for label, args in (('relative', lambda r, tmp: ['../tmpcfg/config.toml']),   # from the sandbox's tmp
                            ('a directory', lambda r, tmp: [os.path.dirname(tmp)]),
                            ('missing', lambda r, tmp: [tmp + '.none']),
                            ('a symlink', lambda r, tmp: [link(r, tmp)]),
                            ('two configs', lambda r, tmp: [tmp, tmp])):
            with self.subTest(label):
                r = Rig(self)
                tmp = r.temp_config(config(HAVE))
                res = r.run('validate', *args(r, tmp))
                self.assertEqual((res.returncode, res.stdout), (1, ''))
                self.assertTrue(res.stderr.startswith('runner-start: REFUSE '), res.stderr)
                self.assertEqual(r.runner(), [])


class TestLogBound(unittest.TestCase):
    """The 10 MB bound on the LaunchAgent's two logs cuts only in `run` (runscaler's start): `validate` never cuts one,
    because the updater validates while runscaler writes to runscaler.log."""

    BIG = 10485760 + 1

    def logs(self, r):
        d = r.sb.path('logdir')
        out, err = os.path.join(d, 'runscaler.log'), os.path.join(d, 'runner-start.err')
        for p in (out, err):
            with open(p, 'wb') as f:
                f.truncate(self.BIG)   # sparse: over 10 MB on disk costs nothing
        return out, err

    def test_validate_never_cuts_a_log(self):
        for args in (['validate'], ['validate', None]):
            with self.subTest('validate CONFIG' if len(args) == 2 else 'validate'):
                r = Rig(self)
                out, err = self.logs(r)
                res = r.run(*[a if a else r.temp_config(config(HAVE)) for a in args])
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual((os.path.getsize(out), os.path.getsize(err)), (self.BIG, self.BIG))

    def test_control_run_cuts_both_logs(self):
        r = Rig(self)
        out, err = self.logs(r)
        res = r.run('run')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((os.path.getsize(out), os.path.getsize(err)), (0, 0))


class TestTimeZone(unittest.TestCase):
    """runscaler stamps its log in local time with no zone; the updater's core reads those times as UTC (core/README.md,
    the TZ section). So runner-start runs runscaler with TZ=UTC, for `run` and for `validate`, whatever TZ it was given
    (the Studio's zone is Europe/London)."""

    def rig(self):
        r = Rig(self)
        r.sb.stub('runner', 'print -r -- "TZ=${TZ-unset}"', folder=r.sb.path('fake'))
        return r

    def test_runscaler_runs_with_tz_utc(self):
        for args in (['run'], ['validate'], ['validate', None]):
            for given in ({'TZ': 'Europe/London'}, {}):
                with self.subTest(args=args, given=given):
                    r = self.rig()
                    argv = [a if a else r.temp_config(config(HAVE)) for a in args]
                    res = r.sb.run(['/bin/zsh', '-f', r.script] + argv, extra_env=given)
                    self.assertEqual((res.returncode, res.stdout), (0, 'TZ=UTC\n'), res.stderr)

    def test_control_the_stub_prints_the_tz_it_is_given(self):
        # the harness: the stub runner, run straight, prints the TZ of its environment (and "unset" without one)
        r = self.rig()
        stub = r.sb.path('fake', 'runner')
        self.assertEqual(r.sb.run([stub], extra_env={'TZ': 'Europe/London'}).stdout, 'TZ=Europe/London\n')
        self.assertEqual(r.sb.run([stub]).stdout, 'TZ=unset\n')


class TestRun(unittest.TestCase):
    def test_run_takes_no_config(self):
        r = Rig(self)
        res = r.run('run', r.temp_config(config(HAVE)))
        self.assertEqual((res.returncode, res.stdout, res.stderr), (1, '', USAGE))
        self.assertEqual(r.runner(), [])

    def test_control_run(self):
        r = Rig(self)
        res = r.run('run')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(r.runner(), [['run', '--config', r.config]])

    def test_usage(self):
        for args in ([], ['start'], ['validatex']):
            with self.subTest(args=args):
                r = Rig(self)
                res = r.run(*args)
                self.assertEqual((res.returncode, res.stdout, res.stderr), (1, '', USAGE))
                self.assertEqual(r.runner(), [])


if __name__ == '__main__':
    unittest.main()
