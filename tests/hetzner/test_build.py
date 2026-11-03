"""02-d1.sh build VERSION (plan D2, the Linux host's build): ONE build path of a runner release, for the updater and a
person alike, and the full run that a fresh host's install runs.

BUILD VERSION fetches release v<VERSION> of actions/runner (GitHub's API, then the download, every call with the
filtered CA bundle and no CA folder), checks the tarball's sha256 against the asset's digest, puts the tarball into a
fresh build context beside image/'s files (the RECIPE: the tarball is not part of it), builds on the pinned base with
--no-cache, pushes, reads the runner version from the image, runs step 3's read-only checks and the image checks of
steps 6 and 8 (never steps 1, 2, 4 or 7), and writes ONE BUILD RECORD per (version, recipe):
~/run/builds/<VERSION>-<RECIPE>, 0640, four strict `key value` lines (format, version, digest, recipe), written whole
and renamed into place. A digest mismatch, another runner version in the image, a failed check, a hostile digest, or a
kill before the rename: no record. GitHub's 403 or 429: WAIT, exit 75. It never writes ~/run/image.ref; the full run
(no argument) builds the host config's RUNNER_VERSION the same way, and is image.ref's only writer.

Each cell runs a copy of the real 02-d1.sh and runner-release.sh (only their pin lines rewritten) against the stubs and
the local HTTPS GitHub of tests/hetzner/support.py, in a container.
"""
import calendar
import hashlib
import json
import os
import re
import unittest

from tests.hetzner.support import (Sandbox, needs_container, pki, sha256_file, tarball, ARCH, IMAGE_NAME,
                                   REGISTRY_PORT)

VERSION = '2.339.0'
OLD = '2.338.2'           # host.conf.example's RUNNER_VERSION
DIGEST = 'sha256:' + 'd' * 64
RECORD_RE = re.compile(r'format 1\nversion ([0-9]+\.[0-9]+\.[0-9]+)\ndigest (sha256:[0-9a-f]{64})\n'
                       r'recipe ([0-9a-f]{64})\n')
NAME_RE = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+-[0-9a-f]{64}')


def recipe(build):
    d = os.path.join(build, 'image')
    lines = ''.join('%s  %s\n' % (sha256_file(os.path.join(d, n)), n) for n in sorted(os.listdir(d)))
    return hashlib.sha256(lines.encode()).hexdigest()


class Rig:
    def __init__(self, test, version=VERSION, **release):
        self.sb = sb = Sandbox(test)
        self.version = version
        self.tgz = tarball(version)
        sb.gh.release(version, self.tgz, **release)
        sb.docker['config_version'] = '[RUNNER 2026-11-02 12:00:00Z INFO Runner] a log line\n%s\n' % version
        self.builds = os.path.join(sb.home, 'run', 'builds')

    def records(self):
        if not os.path.isdir(self.builds):
            return []
        return sorted(n for n in os.listdir(self.builds) if NAME_RE.fullmatch(n))

    def record(self, name):
        p = os.path.join(self.builds, name)
        with open(p) as f:
            return f.read(), os.stat(p).st_mode & 0o777

    def built(self):
        return [a for a in self.sb.calls('docker') if a[:1] == ['build']]

    def image_ref(self):
        return os.path.exists(os.path.join(self.sb.home, 'run', 'image.ref'))


@needs_container
class Build(unittest.TestCase):
    def test_a_digest_match_writes_the_record_and_nothing_else(self):
        g = Rig(self)
        r = g.sb.d1('build', VERSION)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        name = '%s-%s' % (VERSION, recipe(g.sb.build))
        self.assertEqual(g.records(), [name])
        text, mode = g.record(name)
        self.assertEqual(text, 'format 1\nversion %s\ndigest %s\nrecipe %s\n' % (VERSION, DIGEST, recipe(g.sb.build)))
        self.assertTrue(RECORD_RE.fullmatch(text))
        self.assertEqual(mode, 0o640)
        self.assertEqual(os.listdir(g.builds), [name])
        self.assertFalse(g.image_ref(), 'BUILD wrote image.ref: only the full run may')
        # the build: --no-cache, a 0700 context of image/'s files plus the CHECKED tarball, removed afterwards
        (b,) = g.built()
        self.assertIn('--no-cache', b)
        with open(g.sb.path('logs', 'build-ctx.json')) as f:
            ctx = json.loads(f.read())
        want = {n: sha256_file(os.path.join(g.sb.build, 'image', n)) for n in os.listdir(os.path.join(g.sb.build, 'image'))}
        want['runner.tar.gz'] = hashlib.sha256(g.tgz).hexdigest()
        self.assertEqual(ctx['files'], want)
        self.assertEqual(ctx['mode'], '0o700')
        self.assertFalse(os.path.exists(b[-1]), 'the build context is left behind')
        # the version was read from the pushed digest
        ref = 'localhost:%s/%s@%s' % (REGISTRY_PORT, IMAGE_NAME, DIGEST)
        self.assertTrue(any(ref in a and './config.sh' in a for a in g.sb.calls('docker')))
        # never steps 1, 2, 4 or 7
        self.assertEqual(g.sb.lines('systemctl'), [])
        j = [' '.join(a) for a in g.sb.calls('docker')]
        for never in ('network create', 'run -d', '/dev/tcp/', 'SCANNED', 'https://github.com'):
            self.assertFalse([c for c in j if never in c], never)
        self.assertFalse(os.path.exists(os.path.join(g.sb.home, 'run', 'net.env')))
        self.assertIn('BUILD DONE', r.stdout)

    def test_a_digest_mismatch_writes_no_record_and_builds_nothing(self):
        g = Rig(self, digest='sha256:' + hashlib.sha256(b'another tarball').hexdigest())
        r = g.sb.d1('build', VERSION)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(g.records(), [])
        self.assertEqual(g.built(), [])
        self.assertIn('digest', (r.stdout + r.stderr).lower())

    def test_an_image_whose_runner_is_not_VERSION_writes_no_record(self):
        for out in ('a line\n%s\n' % OLD, ''.join('%s\n' % v for v in (VERSION, VERSION)), 'no version at all\n'):
            with self.subTest(out=out):
                g = Rig(self)
                g.sb.docker['config_version'] = out
                r = g.sb.d1('build', VERSION)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(g.records(), [])
                self.assertIn('not %s' % VERSION, r.stdout)

    def test_a_failed_check_writes_no_record(self):
        cases = {
            'step 3: the daemon is not rootless': ('info', '[name=seccomp,profile=@HOME@/.config/docker/'
                                                   'seccomp-userns-min-v29.9.0.json name=no-new-privileges]',
                                                   'FAIL not rootless'),
            'step 6: keyctl is allowed': ('main_checks', 'Seccomp: 2\nNoNewPrivs: 1\npid1=docker-init umask=0022\n'
                                          'keyctl ALLOWED\nsudo=refused\nbwrap=ok\nlocale=ok\n',
                                          'FAIL missing: keyctl EPERM'),
            'step 8: container root lists another home': ('ls_rc', 0, 'FAIL escape check'),
        }
        for why, (k, v, says) in cases.items():
            with self.subTest(why):
                g = Rig(self)
                g.sb.docker[k] = v
                r = g.sb.d1('build', VERSION)
                self.assertNotEqual(r.returncode, 0, why)
                self.assertEqual(g.records(), [], why)
                self.assertIn(says, r.stdout, why)       # it failed AT that check

    def test_a_hostile_digest_from_the_registry_writes_no_record(self):
        g = Rig(self)
        g.sb.docker['repo_digest'] = 'localhost:%s/%s@%s;touch %s' % (REGISTRY_PORT, IMAGE_NAME, DIGEST, g.sb.path('x'))
        r = g.sb.d1('build', VERSION)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('FAIL unexpected digest reference', r.stdout)
        self.assertEqual(g.records(), [])
        self.assertFalse(os.path.exists(g.sb.path('x')))

    def test_a_kill_before_the_rename_leaves_no_record(self):
        g = Rig(self)
        g.sb.write(g.sb.path('stubs', 'dd'), '#!/bin/sh\ncase "$*" in *of=*/run/builds/*) kill -9 "$PPID"; '
                                              'sleep 30 ;; esac\nexec /usr/bin/dd "$@"\n', 0o755)
        r = g.sb.d1('build', VERSION)
        self.assertEqual(r.returncode, -9, 'the kill did not happen: ' + r.stdout[-400:])
        self.assertEqual(g.records(), [])
        # it was MID-WRITE: the whole text is in a temporary name, which no reader takes for a record
        temps = [n for n in os.listdir(g.builds) if not NAME_RE.fullmatch(n)]
        self.assertEqual(len(temps), 1)
        with open(os.path.join(g.builds, temps[0])) as f:
            self.assertTrue(RECORD_RE.fullmatch(f.read()))

    def test_every_download_uses_the_filtered_bundle_and_no_ca_folder(self):
        g = Rig(self)
        r = g.sb.d1('build', VERSION)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        tls = os.path.join(g.sb.home, '.cache', 'liveapp-ci', 'tls')
        https = [c for c in g.sb.calls('curl') if any(x.startswith('https://') for x in c['argv'])]
        self.assertEqual(len(https), 2, 'want the API call and the download')
        for c in https:
            a = c['argv']
            self.assertEqual(a[0], '-q', 'curl reads ~/.curlrc unless -q comes first')
            self.assertEqual(c['tea'], '1')
            self.assertEqual(a[a.index('--cacert') + 1], os.path.join(tls, 'bundle.pem'))
            self.assertEqual(a[a.index('--capath') + 1], os.path.join(tls, 'capath'))
            self.assertEqual(a[a.index('--proto') + 1], '=https')

    def test_an_excluded_ca_downloads_nothing(self):
        for key, ok in ((pki().ca_spki, False), (pki().other_spki, True)):
            with self.subTest(excluded='the server CA' if not ok else 'another key'):
                g = Rig(self)
                g.sb.excluded(key + ' a test key')
                r = g.sb.d1('build', VERSION)
                self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
                self.assertEqual(len(g.records()), 1 if ok else 0)
                if not ok:
                    self.assertEqual(g.sb.gh.seen, [], 'a request reached GitHub through an excluded CA')
                    self.assertEqual(g.built(), [])

    def test_zero_data_lines_downloads_nothing(self):
        g = Rig(self)
        g.sb.excluded('# no key at all')
        r = g.sb.d1('build', VERSION)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('REFUSE', r.stderr)
        self.assertEqual([c for c in g.sb.calls('curl') if any(x.startswith('https://') for x in c['argv'])], [])
        self.assertEqual(g.sb.gh.seen, [])
        self.assertEqual(g.records(), [])

    def test_a_rate_limit_waits_and_another_error_fails(self):
        for status, rc in ((403, 75), (429, 75), (404, 1), (500, 1), (200, 0)):
            with self.subTest(status=status):
                g = Rig(self, status=status)
                r = g.sb.d1('build', VERSION)
                self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
                self.assertEqual(len(g.records()), 1 if rc == 0 else 0)
                if rc == 75:
                    self.assertIn('WAIT', r.stdout)

    def test_a_release_that_is_not_the_one_asked_for_refuses(self):
        api = '/repos/actions/runner/releases/tags/v' + VERSION
        for why in ('another release, whole and consistent', 'a version-less tag'):
            with self.subTest(why):
                g = Rig(self)
                if why == 'a version-less tag':
                    g.sb.gh.release(VERSION, g.tgz, tag='latest')
                else:   # GitHub answers tags/v2.339.0 with release v2.339.1, its own assets and addresses all right
                    g.sb.gh.release('2.339.1', tarball('2.339.1'))
                    g.sb.gh.routes[api] = g.sb.gh.routes['/repos/actions/runner/releases/tags/v2.339.1']
                r = g.sb.d1('build', VERSION)
                self.assertNotEqual(r.returncode, 0, why)
                self.assertIn('REFUSE', r.stderr, why)
                self.assertEqual(g.sb.gh.seen, [api], why)
                self.assertEqual(g.records(), [], why)
        # the asset's download URL is not the one the release's name gives
        g = Rig(self)
        st, h, body = g.sb.gh.routes[api]
        g.sb.gh.routes[api] = (st, h, body.replace(b'/actions/runner/releases/download/', b'/elsewhere/'))
        r = g.sb.d1('build', VERSION)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('REFUSE', r.stderr)
        self.assertEqual(g.sb.gh.seen, [api])
        self.assertEqual(g.records(), [])

    def test_usage(self):
        for args in (('build',), ('build', '2.339'), ('build', 'v2.339.0'), ('build', VERSION, 'x'),
                     ('rebuild', VERSION), ('build', '2.339.0 ')):
            with self.subTest(args=args):
                g = Rig(self)
                r = g.sb.d1(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn('usage', r.stdout + r.stderr)
                self.assertEqual(g.sb.calls('docker'), [])
                self.assertEqual(g.sb.calls('curl'), [])

    def test_one_record_per_version_and_recipe(self):
        g = Rig(self)
        self.assertEqual(g.sb.d1('build', VERSION).returncode, 0)
        g.sb.docker['repo_digest'] = 'localhost:%s/%s@sha256:%s' % (REGISTRY_PORT, IMAGE_NAME, 'e' * 64)
        self.assertEqual(g.sb.d1('build', VERSION).returncode, 0)   # the same (version, recipe): replaced
        (name,) = g.records()
        self.assertIn('digest sha256:' + 'e' * 64 + '\n', g.record(name)[0])
        r1 = recipe(g.sb.build)
        with open(os.path.join(g.sb.build, 'image', 'Dockerfile'), 'a') as f:
            f.write('# another recipe\n')
        self.assertEqual(g.sb.d1('build', VERSION).returncode, 0)
        self.assertEqual(g.records(), sorted(['%s-%s' % (VERSION, r1), '%s-%s' % (VERSION, recipe(g.sb.build))]))

    def test_an_image_folder_that_is_not_plain_files_refuses(self):
        for name, make in (('runner.tar.gz', 'file'), ('sub', 'dir'), ('link', 'link')):
            with self.subTest(name=name):
                g = Rig(self)
                p = os.path.join(g.sb.build, 'image', name)
                if make == 'file':
                    g.sb.write(p, 'x')
                elif make == 'dir':
                    os.mkdir(p)
                else:
                    os.symlink('Dockerfile', p)
                r = g.sb.d1('build', VERSION)
                self.assertNotEqual(r.returncode, 0, name)
                self.assertIn('FAIL', r.stdout, name)
                self.assertIn('image/%s' % name, r.stdout, name)    # it failed AT the recipe's check
                self.assertEqual(g.built(), [], name)


@needs_container
class Release(unittest.TestCase):
    """rr_release latest, the updater's call (the same code as `tag`): the newest release's facts, read strictly."""
    FACTS = 'rr_release "$@" && printf "%s\\n" "$RR_VERSION" "$RR_PUBLISHED" "$RR_DIGEST" "$RR_URL"'

    def test_latest_reads_the_newest_release(self):
        sb = Sandbox(self)
        tgz = tarball(VERSION)
        sb.gh.release(VERSION, tgz, latest=True, published='2026-10-20T12:00:00Z')
        r = sb.lib(self.FACTS, 'latest')
        self.assertEqual(r.returncode, 0, r.stderr)
        name = 'actions-runner-linux-%s-%s.tar.gz' % (ARCH, VERSION)
        self.assertEqual(r.stdout.splitlines()[-4:], [
            VERSION, str(calendar.timegm((2026, 10, 20, 12, 0, 0))), 'sha256:' + hashlib.sha256(tgz).hexdigest(),
            sb.gh.base + '/actions/runner/releases/download/v%s/%s' % (VERSION, name)])
        self.assertEqual(sb.gh.seen, ['/repos/actions/runner/releases/latest'])

    def test_latest_refuses_what_tag_refuses(self):
        for why, kw, args in (('a tag that is not vN.N.N', {'tag': 'v2.339.0-beta'}, ('latest',)),
                              ('no published time', {'published': 'yesterday'}, ('latest',)),
                              ('a version argument', {}, ('latest', VERSION))):
            with self.subTest(why):
                sb = Sandbox(self)
                sb.gh.release(VERSION, tarball(VERSION), latest=True, **kw)
                r = sb.lib(self.FACTS, *args)
                self.assertEqual(r.returncode, 1, why)
                self.assertIn('REFUSE', r.stderr, why)
                self.assertEqual(r.stdout.count(VERSION), 0, why)


@needs_container
class HostConfig(unittest.TestCase):
    """A host installed before RUNNER_VERSION existed: 02-d1.sh refuses in BOTH modes before anything runs, and the
    refusal names the fix, the key and the file (linux-docker/README.md, "Upgrading from a release before this one")."""

    def conf(self, sb, line):
        p = sb.path('host.conf')
        with open(p) as f:
            text = f.read()
        self.assertEqual(text.count('\nRUNNER_VERSION=2.338.2\n'), 1)
        sb.write(p, text.replace('\nRUNNER_VERSION=2.338.2\n', '\n' + line), 0o644)

    def test_a_host_config_without_RUNNER_VERSION_refuses_in_both_modes(self):
        for args in (('build', VERSION), ()):
            with self.subTest(args=args):
                g = Rig(self)
                self.conf(g.sb, '')
                r = g.sb.d1(*args)
                self.assertEqual(r.returncode, 1)
                self.assertEqual(r.stderr, '02-d1.sh: REFUSE %s lacks RUNNER_VERSION (linux-docker/host.conf.example)\n'
                                 % g.sb.path('host.conf'))
                self.assertEqual((r.stdout, g.sb.calls('docker'), g.sb.calls('curl')), ('', [], []))

    def test_a_RUNNER_VERSION_that_is_no_version_refuses_the_full_run_and_names_the_file(self):
        g = Rig(self)
        self.conf(g.sb, 'RUNNER_VERSION=2.338\n')
        r = g.sb.d1()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stderr, '02-d1.sh: REFUSE %s: RUNNER_VERSION is not N.N.N: [2.338]\n' % g.sb.path('host.conf'))
        self.assertEqual((r.stdout, g.sb.calls('docker')), ('', []))
        r = g.sb.d1('build', VERSION)    # the control: BUILD names its version itself
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


@needs_container
class FullRun(unittest.TestCase):
    def test_the_full_run_builds_the_host_config_version_and_writes_image_ref(self):
        g = Rig(self, version=OLD)
        sb = g.sb
        os.makedirs(os.path.join(sb.home, 'run'), mode=0o750)
        sb.write(os.path.join(sb.home, 'run', 'docker.sock'), '', 0o660)
        sb.write(sb.path('xdg', 'dockerd-rootless', 'child_pid'), '1\n')
        r = sb.d1()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('B2 DONE (D1)', r.stdout)
        ref = 'localhost:%s/%s@%s' % (REGISTRY_PORT, IMAGE_NAME, DIGEST)
        with open(os.path.join(sb.home, 'run', 'image.ref')) as f:
            self.assertEqual(f.read(), ref + '\n')
        self.assertEqual(g.records(), ['%s-%s' % (OLD, recipe(sb.build))])
        self.assertTrue(os.path.exists(os.path.join(sb.home, 'run', 'net.env')))
        self.assertTrue(sb.lines('systemctl'))    # steps 1 and 2 ran


if __name__ == '__main__':
    unittest.main()
