"""02-d1.sh build VERSION (plan D2, the Linux host's build): ONE build path of a runner release, for the updater and a
person alike, and the full run that a fresh host's install runs.

BUILD VERSION fetches release v<VERSION> of actions/runner (GitHub's API, then the download, every call with the
filtered CA bundle and no CA folder), checks the tarball's sha256 against the asset's digest, puts the tarball into a
fresh build context beside image/'s files (the RECIPE: the tarball is not part of it), builds on the pinned base with
--no-cache, pushes, reads the runner version from the image, runs step 3's read-only checks and the image checks of
steps 6 and 8 (never steps 1, 2, 4 or 7: BUILD makes nothing of D1's), and writes ONE BUILD RECORD per (version, recipe):
~/run/builds/<VERSION>-<RECIPE>, 0640, four strict `key value` lines (format, version, digest, recipe), written whole
and renamed into place. A digest mismatch, another runner version in the image, a failed check, a hostile digest, or a
kill before the rename: no record. GitHub's 403 or 429: WAIT, exit 75. It never writes ~/run/image.ref; the full run
(no argument) builds the host config's RUNNER_VERSION the same way, and is image.ref's only writer. Both modes hold the
host user's ONE updater lock for the whole run (a second run waits), give each build its own tag, and write a record
only for the digest of the image just built. Every download checks the filtered CA bundle first.

Each cell runs a copy of the real 02-d1.sh and runner-release.sh (only their pin lines rewritten) against the stubs and
the local HTTPS GitHub of tests/hetzner/support.py, in a container. The Header cell reads text and runs anywhere.
OtherUsersFiles and ReadOnce: RS_USER reads a file of RUN_USER's (a build record, image.ref) only through
runner-release.sh's rr_read: one open, no symlink, never blocking, a regular file only (PLAN D1: they are hostile).
"""
import calendar
import fcntl
import hashlib
import json
import os
import re
import time
import unittest

from tests.hetzner.support import (REPO, Pool, Sandbox, digest, needs_container, pki, run_pool, sha256_file, tarball,
                                   ARCH, IMAGE_NAME, REGISTRY_PORT)

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

    def recipes(self):
        """{image ID: the recipe of the context the docker stub built it from} (the tarball is no part of a recipe)."""
        out = {}
        p = self.sb.path('logs', 'build-ctx.json')
        if os.path.exists(p):
            with open(p) as f:
                for l in f.read().splitlines():
                    b = json.loads(l)
                    lines = ''.join('%s  %s\n' % (h, n) for n, h in sorted(b['files'].items()) if n != 'runner.tar.gz')
                    out[b['id']] = hashlib.sha256(lines.encode()).hexdigest()
        return out

    def own_images(self, test):
        """Every record names the image built from ITS recipe: the record's digest is, in the stub's registry, an image
        that a build of that very recipe made. Returns the records' digests."""
        digests, recipes = self.sb.state()['digests'], self.recipes()
        out = []
        for name in self.records():
            text, _ = self.record(name)
            m = RECORD_RE.fullmatch(text)
            test.assertTrue(m, text)
            iid = digests.get(m.group(2))
            test.assertIn(iid, recipes, '%s names %s, an image no build of this run made' % (name, m.group(2)))
            test.assertEqual(recipes[iid], m.group(3), '%s names the image of another recipe' % name)
            out.append(m.group(2))
        return out


def full_rig(test, version=OLD):
    """A Rig for the FULL run: D1's sockets and rootlesskit's pid file, as steps 2 and 7 read them."""
    g = Rig(test, version=version)
    os.makedirs(os.path.join(g.sb.home, 'run'), mode=0o750)
    g.sb.write(os.path.join(g.sb.home, 'run', 'docker.sock'), '', 0o660)
    g.sb.write(g.sb.path('xdg', 'dockerd-rootless', 'child_pid'), '1\n')
    return g


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
        # never steps 1, 2, 4 or 7: none of their calls. D1 is whole here, so step 4 would make nothing: its own reads
        # (the network's driver, the registry's state) are what show it ran (BuildMakesNothingOfD1: a D1 it would fix)
        self.assertEqual(g.sb.lines('systemctl'), [])
        j = [' '.join(a) for a in g.sb.calls('docker')]
        for never in ('network create', 'run -d', '{{.Driver}}', '{{.State.Running}}', 'Gateway', 'bridge.IPAddress',
                      '/dev/tcp/', 'SCANNED', 'https://github.com'):
            self.assertFalse([c for c in j if never in c], never)
        self.assertFalse([c for c in j if c.startswith('start ')])
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
class BuildMakesNothingOfD1(unittest.TestCase):
    """BUILD's stand-in for step 4 is read only: the `runners` network and the registry must be there already (the full
    run made them), and BUILD creates, runs or starts nothing of D1's. The stub's D1 here lacks them, so step 4's own
    calls are possible: the full run with the same D1 makes them (the control)."""
    MAKES = (['network', 'create'], ['run', '-d'], ['start'])

    def makes(self, sb):
        return [c for c in sb.calls('docker') if any(c[:len(m)] == m for m in self.MAKES)]

    def test_no_runners_network_and_no_running_registry(self):
        for registry in ('stopped', 'absent'):
            with self.subTest(registry=registry):
                g = Rig(self)
                g.sb.docker.update(network=False, registry=registry)
                r = g.sb.d1('build', VERSION)
                self.assertEqual(self.makes(g.sb), [])
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('FAIL no runners network: run the full 02-d1.sh first', r.stdout)
                self.assertEqual((g.built(), g.records()), ([], []))
                f = full_rig(self)     # the control: the full run, the same D1
                f.sb.docker.update(network=False, registry=registry)
                r = f.sb.d1()
                self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
                made = [' '.join(c) for c in self.makes(f.sb)]
                self.assertIn('network create runners', made)
                if registry == 'stopped':
                    self.assertIn('start runner-registry', made)
                else:
                    self.assertTrue([c for c in made if c.startswith('run -d --name runner-registry ')], made)

    def test_a_registry_that_does_not_answer(self):
        g = Rig(self)
        g.sb.curl['registry_rc'] = 7
        r = g.sb.d1('build', VERSION)
        self.assertEqual(self.makes(g.sb), [])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('FAIL the registry does not answer on 127.0.0.1:%s: run the full 02-d1.sh first' % REGISTRY_PORT,
                      r.stdout)
        self.assertEqual((g.built(), g.records()), ([], []))


@needs_container
class OneBuildAtATime(unittest.TestCase):
    """Two builds never cross (plan D1, THE UPDATER LOCK): 02-d1.sh holds the host user's ONE updater lock (its path is
    RR_LOCK of runner-release.sh, which the updater sources too) for its whole run, and a second run WAITS for it with a
    line that names it. Each build's tag is its own beyond the second, and the pushed digest must be the image just
    built, so a tag that moved before the push writes no record of another image."""

    def lock_path(self, sb):
        r = sb.lib('printf "%s\\n" "$RR_LOCK"')
        self.assertEqual(r.returncode, 0, r.stderr)
        p = r.stdout.strip()
        self.assertTrue(p.startswith(sb.home + '/'), p)
        return p

    def waiter_on(self, path):
        """A process waits for a flock on path (/proc/locks: a `->` line on its inode)."""
        ino = os.stat(path).st_ino
        with open('/proc/locks') as f:
            return [l for l in f.read().splitlines()
                    if ' -> FLOCK ' in l and l.split()[-3].rsplit(':', 1)[-1] == str(ino)]

    def test_a_second_run_waits_for_the_updater_lock(self):
        g = Rig(self)
        lock = self.lock_path(g.sb)
        os.makedirs(os.path.dirname(lock), mode=0o700, exist_ok=True)
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)          # another run holds it
        p = g.sb.d1_start('build', VERSION)
        first = p.stdout.readline()
        self.assertTrue(first.startswith('WAIT ') and lock in first, 'no WAIT line that names the lock: %r' % first)
        for _ in range(600):                    # wait for the STATE (it waits for the lock), never for a time
            if self.waiter_on(lock) or p.poll() is not None:
                break
            time.sleep(0.05)
        self.assertTrue(self.waiter_on(lock), 'the run does not wait for the lock')
        self.assertEqual((g.sb.calls('docker'), g.sb.calls('curl')), ([], []))   # nothing ran while it waited
        fcntl.flock(fd, fcntl.LOCK_UN)
        out, _ = p.communicate(timeout=600)
        self.assertEqual(p.returncode, 0, out[-2000:])
        self.assertIn('BUILD DONE', out)
        self.assertEqual(len(g.records()), 1)
        r = g.sb.d1('build', VERSION)            # the control: a free lock, no WAIT
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('WAIT', r.stdout + r.stderr)

    def test_a_child_of_the_lock_holder_shares_its_lock(self):
        """The updater holds the lock for its whole pass and may run 02-d1.sh as its child, fd 9 passed on: the child
        takes the lock there, at once, and builds. The control: a holder whose child gets no fd 9 makes it WAIT."""
        for passed in (True, False):
            with self.subTest(fd9_passed_on=passed):
                g = Rig(self)
                lock = self.lock_path(g.sb)
                fd = 9 if passed else 8
                holder = ('mkdir -p "${1%%/*}" && exec %d>> "$1" && flock -n %d || exit 9\n'
                          'bash "$2" build "$3" %s; echo "child rc=$?"\n' % (fd, fd, '' if passed else '8>&-'))
                p = g.sb.start(['bash', '-c', holder, 'holder', lock, os.path.join(g.sb.build, 'setup', '02-d1.sh'),
                                VERSION])
                first = p.stdout.readline()
                if not passed:
                    self.assertTrue(first.startswith('WAIT ') and lock in first, first)
                    continue                     # the cleanup ends the holder and its waiting child
                self.assertFalse(first.startswith('WAIT'), first)
                out, _ = p.communicate(timeout=600)
                self.assertIn('child rc=0', out, out[-2000:])
                self.assertEqual(len(g.records()), 1)

    def test_two_builds_in_one_second_get_their_own_tags_and_records(self):
        g = Rig(self)
        g.sb.docker['repo_digest'] = None        # each image its own digest
        g.sb.write(g.sb.path('stubs', 'date'), '#!/bin/sh\necho 20261103T020000Z\n', 0o755)   # one second
        self.assertEqual(g.sb.d1('build', VERSION).returncode, 0)
        with open(os.path.join(g.sb.build, 'image', 'Dockerfile'), 'a') as f:
            f.write('# another recipe\n')
        self.assertEqual(g.sb.d1('build', VERSION).returncode, 0)
        tags = [b[b.index('-t') + 1] for b in g.built()]
        self.assertEqual(len(tags), 2)
        self.assertNotEqual(tags[0], tags[1], 'two builds in one second got one tag')
        self.assertEqual(len(set(g.own_images(self))), 2)    # two records, each its own image

    def test_a_tag_moved_before_the_push_writes_no_record_of_the_other_image(self):
        for moved in (True, False):
            with self.subTest(moved=moved):
                g = Rig(self)
                g.sb.docker.update(repo_digest=None, interleave=moved)
                r = g.sb.d1('build', VERSION)
                self.assertEqual(r.returncode != 0, moved, r.stdout + r.stderr)
                self.assertEqual(len(g.own_images(self)), 0 if moved else 1)
                if moved:
                    self.assertIn('is not the image just built', r.stdout)
                    self.assertEqual(g.records(), [])


@needs_container
class TrustBeforeEveryDownload(unittest.TestCase):
    """EVERY download checks the filtered CA bundle first (rr_curl runs rr_bundle): an input that changes after the
    release was read and before the tarball's download (a key added to the data file, the file emptied or broken)
    holds for that download. The hook: a python3 substitute that runs the real one and, right after rr_release's own
    parse (the API call is done; the download is next), records the bundle's inode and writes inject.txt over the data
    file."""
    HOOK = '''#!/bin/sh
/usr/bin/python3 "$@"; rc=$?
if [ "$1 $2" = "-I -" ] && [ ! -e @ROOT@/hooked ]; then
  stat -c %i @HOME@/.cache/liveapp-ci/tls/bundle.pem > @ROOT@/hooked
  [ ! -f @ROOT@/inject.txt ] || cat @ROOT@/inject.txt > @HOME@/build/setup/tls-excluded-spki
fi
exit $rc
'''

    def run_with(self, change):
        g = Rig(self)
        with open(os.path.join(g.sb.build, 'setup', 'tls-excluded-spki')) as f:
            data = f.read()
        if change is not None:
            g.sb.write(g.sb.path('inject.txt'), change(data))
        g.sb.write(g.sb.path('stubs', 'python3'),
                   self.HOOK.replace('@ROOT@', g.sb.root).replace('@HOME@', g.sb.home), 0o755)
        r = g.sb.d1('build', VERSION)
        with open(g.sb.path('hooked')) as f:      # the hook ran: the release was read
            ino = int(f.read())
        now = os.stat(os.path.join(g.sb.home, '.cache', 'liveapp-ci', 'tls', 'bundle.pem')).st_ino
        api = '/repos/actions/runner/releases/tags/v' + VERSION
        dl = '/actions/runner/releases/download/v%s/actions-runner-linux-%s-%s.tar.gz' % (VERSION, ARCH, VERSION)
        return g, r, now != ino, api, dl

    def test_a_key_excluded_after_the_release_was_read_stops_the_download(self):
        for why, key, ok in (('the server CA', pki().ca_spki, False), ('another key', pki().other_spki, True)):
            with self.subTest(why):
                g, r, rebuilt, api, dl = self.run_with(lambda t: t + key + ' added after the release was read\n')
                self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
                self.assertTrue(rebuilt, 'the data file changed, and the download used the bundle made before')
                self.assertEqual(dl in g.sb.gh.seen, ok, g.sb.gh.seen)
                self.assertEqual(len(g.records()), 1 if ok else 0)
                if not ok:
                    self.assertEqual(g.sb.gh.seen, [api])
                    self.assertEqual(g.built(), [])

    def test_a_data_file_broken_after_the_release_was_read_refuses_before_the_download(self):
        for why, change in (('emptied', lambda t: ''), ('comments only', lambda t: '# nothing excluded\n'),
                            ('a bad first field', lambda t: t + 'NOT-64-HEX a broken line\n')):
            with self.subTest(why):
                g, r, _, api, dl = self.run_with(change)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn('runner-release: REFUSE', r.stderr)
                self.assertEqual(g.sb.gh.seen, [api])
                self.assertEqual(len([c for c in g.sb.calls('curl') if any(x.startswith('https://') for x in c['argv'])]),
                                 1, 'a download was asked for')
                self.assertEqual((g.records(), g.built()), ([], []))

    def test_an_unchanged_input_set_keeps_the_bundle(self):
        g, r, rebuilt, api, dl = self.run_with(None)     # the control: nothing changes between the two downloads
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(rebuilt, 'the bundle was rebuilt with no input changed')
        self.assertIn(dl, g.sb.gh.seen)
        self.assertEqual(len(g.records()), 1)


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
class Eligible(unittest.TestCase):
    """rr_eligible NOW (plan D2, the release's trust: "at least 2 days old (latest only)"; the ONE copy both users'
    updaters call): rr_release latest, then published at least RR_AGE = 172800 s (2 days) before NOW: 0, with the release's
    facts set; younger: 1 and a REFUSE line that names when it becomes eligible; GitHub's 403 or 429: 75 (WAIT); an
    answer it cannot read: 1. NOW is an input: every cell passes it, relative to the stub's published_at, and none reads
    a clock."""
    PUBLISHED = '2026-10-20T12:00:00Z'
    P = calendar.timegm((2026, 10, 20, 12, 0, 0))
    RUN = 'rr_eligible "$1"; rc=$?; printf "rc=%s %s\\n" "$rc" "$RR_VERSION"'

    def eligible(self, now, **release):
        sb = Sandbox(self)
        sb.gh.release(VERSION, tarball(VERSION), latest=True, published=self.PUBLISHED, **release)
        r = sb.lib(self.RUN, str(now))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.splitlines()[-1], r.stderr, sb

    def test_two_days_old_or_more_is_eligible(self):
        for why, now in (('2 days + 1 s', P2 + 1), ('exactly 2 days', P2)):
            with self.subTest(why):
                last, err, sb = self.eligible(now)
                self.assertEqual(last, 'rc=0 %s' % VERSION, err)
                self.assertNotIn('REFUSE', err)
                self.assertEqual(sb.gh.seen, ['/repos/actions/runner/releases/latest'])

    def test_younger_than_two_days_is_not_eligible_and_says_from_when(self):
        last, err, _ = self.eligible(P2 - 1)
        self.assertEqual(last.split(' ')[0], 'rc=1', err)
        self.assertIn('runner-release: REFUSE release v%s is younger than 2 days: published 2026-10-20 12:00:00 UTC, '
                      'eligible from 2026-10-22 12:00:00 UTC' % VERSION, err)

    def test_a_rate_limit_waits(self):
        for status in (429, 403):
            with self.subTest(status=status):
                last, err, _ = self.eligible(P2 + 1, status=status)
                self.assertEqual(last.split(' ')[0], 'rc=75', err)
                self.assertIn('runner-release: WAIT GitHub answered %d' % status, err)

    def test_an_answer_it_cannot_read_is_not_eligible(self):
        for why, body in (('not JSON', b'{"tag_name": '), ('no published time', None)):
            with self.subTest(why):
                sb = Sandbox(self)
                if body is None:
                    sb.gh.release(VERSION, tarball(VERSION), latest=True, published='yesterday')
                else:
                    sb.gh.routes['/repos/actions/runner/releases/latest'] = (200, {}, body)
                r = sb.lib(self.RUN, str(P2 + 1))
                self.assertEqual(r.stdout.splitlines()[-1].split(' ')[0], 'rc=1', r.stderr)
                self.assertIn('runner-release: REFUSE', r.stderr)

    def test_now_is_whole_epoch_seconds(self):
        for now in ('', 'soon', '-1', '1.5'):
            with self.subTest(now=now):
                sb = Sandbox(self)
                sb.gh.release(VERSION, tarball(VERSION), latest=True, published=self.PUBLISHED)
                r = sb.lib(self.RUN, now)
                self.assertEqual(r.stdout.splitlines()[-1].split(' ')[0], 'rc=1', r.stderr)
                self.assertIn('runner-release: REFUSE', r.stderr)
                self.assertEqual(sb.gh.seen, [], 'it asked GitHub with no NOW to compare')


P2 = Eligible.P + 172800

RR = os.path.join(REPO, 'linux-docker', 'setup', 'runner-release.sh')
D1 = os.path.join(REPO, 'linux-docker', 'setup', '02-d1.sh')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
UPD = os.path.join(REPO, 'linux-docker', 'bin', 'runner-updater')


def defs(path, name):
    with open(path) as f:
        return len(re.findall(r'^%s\(\) \{' % re.escape(name), f.read(), re.M))


class OneCopy(unittest.TestCase):
    """ONE copy (S2b-3b-2, the class): the RECIPE of an image/ folder and the BUILD RECORD reader are runner-release.sh's
    rr_recipe, rr_record (by version and recipe) and rr_record_of (by digest), which 02-d1.sh, pool-image.sh and
    bin/runner-updater source. No caller keeps a listing of image/ or a pattern of the record's lines of its own (the
    two copies before: 02-d1.sh's loop and pool-image.sh's recipe_of; pool-image.sh's record_digest). Text: runs
    anywhere."""

    def test_one_recipe_function_and_one_build_record_reader(self):
        for name in ('rr_recipe', 'rr_record', 'rr_record_of'):
            with self.subTest(name):
                self.assertEqual([defs(p, name) for p in (RR, D1, PIMG, UPD)], [1, 0, 0, 0])
        for name in ('recipe_of', 'record_digest'):
            with self.subTest(name):
                self.assertEqual([defs(p, name) for p in (RR, D1, PIMG, UPD)], [0, 0, 0, 0])
        text = {}
        for p in (D1, PIMG, UPD):
            with open(p) as f:
                text[p] = f.read()
        for p, calls in ((D1, ('rr_recipe ',)), (PIMG, ('rr_recipe ', 'rr_record ')),
                         (UPD, ('rr_recipe ', 'rr_record ', 'rr_record_of '))):
            for c in calls:
                with self.subTest(file=os.path.basename(p), call=c):
                    self.assertIn(c, text[p])
        for p in (D1, PIMG, UPD):
            with self.subTest(file=os.path.basename(p)):
                self.assertNotIn('ls -A', text[p], 'a listing of image/ of its own')
                self.assertNotIn('recipe ([0-9a-f]{64})', text[p], "a pattern of the record's lines of its own")
        with open(RR) as f:
            rr = f.read()
        self.assertEqual(rr.count('recipe ([0-9a-f]{64})'), 1)


# a path in RUN_USER's home, as the scripts and the README spell it
RUN_HOME = re.compile(r'/home/(?:\$\{RUN_USER\}|<RUN_USER>|\$\(sed -n .s/\^RUN_USER=//p.)')
# what a line that names RUN_USER's home may do without reading a file of it: the one reader, or no read at all
NO_FILE_READ = (('rr_read ', 'the one reader of another user\'s file'),
                ('docker.sock', 'a socket: a connection to D1 (the design), no file read'),
                ('df -Pk', 'the free space of its filesystem (statfs), no file read'),
                ('DISK_WHY=', 'a message'),
                ('BUILDS=', 'the folder\'s name: rr_record and rr_record_of read its records, through rr_read'))


class OtherUsersFiles(unittest.TestCase):
    """THE CLASS of Opus r1 F1 (PLAN D1: RUN_USER's files are HOSTILE to RS_USER): every read by RS_USER of a file
    RUN_USER owns goes through runner-release.sh's rr_read (ONE open that never follows a symlink and never blocks; a
    regular file only, by fstat of that open). The census: each line of linux-docker/ (scripts, README) that names a
    path in RUN_USER's home either calls rr_read or reads no file (NO_FILE_READ, each with why); RUN_USER's build
    records are read only by rr_record and rr_record_of, whose reader rr_record_read opens its file only through
    rr_read. Before this, 03-runscaler.sh and the README's move check read ~/run/image.ref with `cat`, and
    rr_record_read with a type check and then `head`. Text: runs anywhere."""

    def test_every_line_that_names_run_user_s_home_reads_its_file_through_rr_read(self):
        """A line is a command's whole text: a line that ends in a backslash goes on in the next (its number: the
        first)."""
        bad, seen = [], 0
        for d, _, names in sorted(os.walk(os.path.join(REPO, 'linux-docker'))):
            for n in sorted(names):
                p = os.path.join(d, n)
                with open(p, encoding='utf-8', errors='replace') as f:
                    raw = f.read().splitlines()
                lines, k = [], 0
                while k < len(raw):
                    start, text = k + 1, raw[k]
                    while text.endswith('\\') and k + 1 < len(raw):
                        k += 1
                        text = text[:-1] + raw[k]
                    lines.append((start, text))
                    k += 1
                for i, l in lines:
                    if not RUN_HOME.search(l) or l.lstrip().startswith('#'):
                        continue
                    seen += 1
                    if not any(m in l for m, _ in NO_FILE_READ):
                        bad.append('%s:%d' % (os.path.relpath(p, REPO), i))
        self.assertGreater(seen, 5, 'the census found almost nothing: its pattern is broken')
        self.assertEqual(bad, [], 'these lines name a path in RUN_USER\'s home and read it without rr_read')

    def test_the_build_record_reader_opens_its_file_only_through_rr_read(self):
        with open(RR) as f:
            body = f.read().split('\nrr_record_read() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('rr_read "$f" ', body)
        self.assertEqual(body.count('"$f"'), body.count('rr_read "$f" '), 'another use of the record\'s path')
        for p in (PIMG, UPD):
            with open(p) as f:
                uses = [l for l in f.read().splitlines() if '"$BUILDS' in l and not l.lstrip().startswith('#')]
            with self.subTest(os.path.basename(p)):
                self.assertTrue(uses)
                for l in uses:
                    self.assertRegex(l, r'\brr_record(_of)? "\$BUILDS"', 'a read of the records but rr_record')


@needs_container
class ReadOnce(unittest.TestCase):
    """runner-release.sh's rr_read FILE MAX (OtherUsersFiles): at most MAX bytes of FILE on stdout through ONE open
    (O_NONBLOCK, O_NOFOLLOW) whose fstat must say a regular file; else rc 1 and RR_WHY: `there is none`, `it is not a
    plain file` (a FIFO, with a writer or none, a symlink, a folder, a device), `it cannot be read`. Never blocks: each
    call runs under `timeout` (60 s: a bound on a hang, never a time it asserts; its exit 124 is a hang)."""

    RUN = (r'''timeout -k 5 60 bash -c '. "$0" || exit 9; rr_read "$1" "$2" > "$3"; echo "rc=$? why=$RR_WHY"' '''
           r'''"$0" "$@"; echo "bounded=$?"''')

    def read(self, sb, path, cap=1025):
        out = sb.path('out')
        r = sb.lib(self.RUN, path, str(cap), out)
        self.assertIn('bounded=0', r.stdout, 'rr_read hung, or its bash did not run: ' + r.stdout + r.stderr)
        rc_why = [l for l in r.stdout.splitlines() if l.startswith('rc=')]
        self.assertEqual(len(rc_why), 1, r.stdout + r.stderr)
        with open(out, 'rb') as f:
            return rc_why[0], f.read()

    def test_a_plain_file_and_its_first_max_bytes(self):
        sb = Sandbox(self)
        p = sb.write(sb.path('home', 'a-record'), 'format 1\n' + 'x' * 2000, 0o640)
        self.assertEqual(self.read(sb, p), ('rc=0 why=', ('format 1\n' + 'x' * 2000).encode()[:1025]))
        self.assertEqual(self.read(sb, p, 3), ('rc=0 why=', b'for'))

    def test_anything_but_a_regular_file_is_none_at_once(self):
        sb = Sandbox(self)
        good = sb.write(sb.path('home', 'good'), 'format 1\n', 0o640)
        fifo = sb.path('home', 'fifo')
        os.mkfifo(fifo)
        busy = sb.path('home', 'busy')                       # a FIFO whose writer is there and wrote a record's text
        os.mkfifo(busy)
        w = os.open(busy, os.O_RDWR)
        self.addCleanup(os.close, w)
        os.write(w, b'format 1\nversion 2.339.0\n')
        link = sb.path('home', 'link')
        os.symlink(good, link)
        folder = sb.path('home', 'folder')
        os.mkdir(folder)
        for why, path, says in (('none', sb.path('home', 'none'), 'there is none'),
                                ('a FIFO with no writer', fifo, 'it is not a plain file'),
                                ('a FIFO whose writer wrote a record', busy, 'it is not a plain file'),
                                ('a symlink to a plain file', link, 'it is not a plain file'),
                                ('a folder', folder, 'it is not a plain file'),
                                ('a device', '/dev/null', 'it is not a plain file')):
            with self.subTest(why):
                self.assertEqual(self.read(sb, path), ('rc=1 why=' + says, b''))


def plant(build, kind, name):
    """In BUILD's image/: NAME as a plain FILE, a DIR or a LINK (to Dockerfile)."""
    p = os.path.join(build, 'image', name)
    if kind == 'file':
        with open(p, 'w') as f:
            f.write('planted\n')
    elif kind == 'dir':
        os.mkdir(p)
    else:
        os.symlink('Dockerfile', p)


@needs_container
class Recipe(unittest.TestCase):
    """The three callers of rr_recipe agree (S2b-3b-2 item 1): for one image/ folder, 02-d1.sh build (the record's name),
    pool-image.sh up (the record it looks for) and the updater's build pass as RUN_USER (the build it starts) use ONE
    recipe, the one support.Pool.recipe computes; and each refuses a folder whose entries are not all plain files, or
    that holds runner.tar.gz (the checked tarball's name in a build context), at the recipe, before anything else."""

    def recipes(self, kind=None, name=None):
        """{caller: the recipe it used} for the shipped image/ (+ NAME planted as KIND)."""
        out = {}
        b = Sandbox(self)                                      # 02-d1.sh build, the real script (stubs: support)
        if kind:
            plant(b.build, kind, name)
        b.gh.release(VERSION, tarball(VERSION))
        b.docker['config_version'] = VERSION + '\n'
        r = b.d1('build', VERSION)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
        (rec,) = os.listdir(os.path.join(b.home, 'run', 'builds'))
        out['02-d1.sh'] = rec.split('-', 1)[1]
        p = Pool(self)                                         # pool-image.sh up, no record: it names the one it reads
        if kind:
            plant(p.build, kind, name)
        p.curl['served'] = [digest(38)]
        p.production(digest(38))
        out['python'] = p.recipe()
        r = p.pool('up', VERSION)
        self.assertEqual(r.returncode, 1, r.stdout[-2000:] + r.stderr)
        m = re.search(r'/home/root/run/builds/%s-([0-9a-f]{64})\)' % re.escape(VERSION), r.stdout)
        self.assertTrue(m, r.stdout[-2000:])
        out['pool-image.sh'] = m.group(1)
        q, _ = run_pool(self, VERSION)                         # the build pass: the build it starts
        if kind:
            plant(q.build, kind, name)
        r = q.updater('pass')
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
        m = re.search(r"^runner-updater: pass: building runner %s for this release's image \(recipe ([0-9a-f]{64})\)"
                      % re.escape(VERSION), r.stdout, re.M)
        self.assertTrue(m, r.stdout[-2000:])
        out['runner-updater'] = m.group(1)
        return out

    def test_the_three_callers_give_one_recipe_for_one_folder(self):
        shipped = None
        for why, kind, name in (('the shipped image/', None, None), ('an extra plain file', 'file', 'notes.txt')):
            with self.subTest(why):
                got = self.recipes(kind, name)
                self.assertEqual(len(set(got.values())), 1, got)
                if shipped is None:
                    shipped = got['python']
                else:
                    self.assertNotEqual(got['python'], shipped, 'the extra file is no part of the recipe')

    def test_a_folder_that_is_not_plain_files_is_refused_by_all_three(self):
        for why, kind, name in (('a symbolic link', 'link', 'link'), ('a folder', 'dir', 'sub'),
                                ('a file named runner.tar.gz', 'file', 'runner.tar.gz')):
            with self.subTest(why):
                b = Sandbox(self)
                plant(b.build, kind, name)
                b.gh.release(VERSION, tarball(VERSION))
                b.docker['config_version'] = VERSION + '\n'
                r = b.d1('build', VERSION)
                self.assertNotEqual(r.returncode, 0, '02-d1.sh: ' + r.stdout[-2000:])
                self.assertRegex(r.stdout, r'(?m)^FAIL .*image/%s' % re.escape(name))
                self.assertEqual([a for a in b.calls('docker') if a[:1] == ['build']], [])
                p = Pool(self)
                plant(p.build, kind, name)
                p.curl['served'] = [digest(38)]
                p.production(digest(38))
                r = p.pool('up', VERSION)
                self.assertEqual(r.returncode, 1, 'pool-image.sh: ' + r.stdout[-2000:] + r.stderr)
                self.assertRegex(r.stdout, r'(?m)^FAIL .*image/%s' % re.escape(name))
                self.assertNotIn('no usable build record', r.stdout, 'pool-image.sh refused later than the recipe')
                self.assertNotIn('== 03-runscaler.sh real', r.stdout)
                q, _ = run_pool(self, VERSION)
                plant(q.build, kind, name)
                r = q.updater('pass')
                self.assertEqual(r.returncode, 1, 'runner-updater: ' + r.stdout[-2000:] + r.stderr)
                self.assertRegex(r.stdout, r'(?m)^runner-updater: REFUSE .*image/%s' % re.escape(name))
                self.assertEqual(q.d1_calls(), [])


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
        g = full_rig(self)
        sb = g.sb
        r = sb.d1()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('B2 DONE (D1)', r.stdout)
        ref = 'localhost:%s/%s@%s' % (REGISTRY_PORT, IMAGE_NAME, DIGEST)
        with open(os.path.join(sb.home, 'run', 'image.ref')) as f:
            self.assertEqual(f.read(), ref + '\n')
        self.assertEqual(g.records(), ['%s-%s' % (OLD, recipe(sb.build))])
        self.assertTrue(os.path.exists(os.path.join(sb.home, 'run', 'net.env')))
        self.assertTrue(sb.lines('systemctl'))    # steps 1 and 2 ran


class Header(unittest.TestCase):
    def test_the_header_says_what_follows_a_build_as_the_readme_does(self):
        """What a person does after BUILD: `pool-image.sh up VERSION` as RS_USER, which reads the build record of
        VERSION (README "A new runner release", step 2). The release before this one's up read ~/run/image.ref, so the
        header and step 2 sent a person through RUNNER_VERSION and the full run first; neither says so now. Text only:
        it runs anywhere."""
        with open(os.path.join(REPO, 'linux-docker', 'README.md')) as f:
            sec = f.read().split('\n## A new runner release\n', 1)[1].split('\n## ', 1)[0]
        step2 = re.search(r'^2\. .*$', sec, re.M).group(0)
        self.assertIn('build record', step2)
        for w in ('Until then', 'image.ref', 'RUNNER_VERSION', 'Install step 5'):
            self.assertNotIn(w, step2)
        with open(os.path.join(REPO, 'linux-docker', 'setup', '02-d1.sh')) as f:
            text = f.read()
        para = re.search(r'^# BUILD VERSION:.*?(?=^# [A-Z][A-Z ]*:)', text, re.M | re.S).group(0)
        lo = para.lower()
        for w in ('pool-image.sh up', 'build record'):
            self.assertIn(w, lo, para)
        for w in ('runner_version in the host', 'until then', 'does the full run'):
            self.assertNotIn(w, lo, para)


if __name__ == '__main__':
    unittest.main()
