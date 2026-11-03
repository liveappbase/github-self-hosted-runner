"""pool-image.sh up VERSION, a person's runner release (plan D2; the changed-lines list, items 22, 23, 25, 28, 29):
after `02-d1.sh build VERSION` as RUN_USER, `up VERSION` as RS_USER reads RUN_USER's BUILD RECORD of VERSION, ONCE and as
untrusted data, and puts its digest into the pool with `03-runscaler.sh real DIGEST`; it never reads ~/run/image.ref.

The record it reads is ~/run/builds/<VERSION>-<RECIPE> of RUN_USER, RECIPE being 02-d1.sh's recipe of this release's
image/ (RS_USER's ~/build/image/, the same release's files). It is copied once and parsed from that copy: exactly the four
lines 02-d1.sh writes (`format 1`, `version N.N.N`, `digest sha256:<64 hex>`, `recipe <64 hex>`), the version the one
asked for, the recipe the one of its name, never sourced. A record that is missing, not a plain file, of another form,
of another version or recipe, or whose digest the local registry does not serve: REFUSED, nothing changed, and the line
names the fix (`ssh RUN_USER@<host> 'bash ~/build/setup/02-d1.sh build VERSION'`). The image's own runner version must
still be VERSION (02-d1.sh's read, unchanged). PINS: what 03 runs and installs, validate-class among them.

The README's "A new runner release" steps 1 and 2 are run as written. The text cells run anywhere; the others run the
real scripts (pin lines rewritten) in a container (support.Pool).
"""
import os
import re
import shutil
import subprocess
import unittest

from tests.hetzner.support import REPO, Pool, Sandbox, digest, needs_container, ref, tarball

V = '2.339.0'
OLDV = '2.338.2'
NEW, OLD, REF = digest(39), digest(38), digest(30)
README = os.path.join(REPO, 'linux-docker', 'README.md')
PIMG = os.path.join(REPO, 'linux-docker', 'setup', 'pool-image.sh')
FIX = "ssh root@<host> 'bash ~/build/setup/02-d1.sh build %s'" % V     # RUN_USER is root in the cells


class Rig:
    """A Pool whose production runs OLD (runner OLDV); the registry serves OLD and NEW, NEW's runner is V; image.ref names
    REF, another digest (up must not read it)."""

    def __init__(self, test):
        self.test = test
        self.p = p = Pool(test)
        p.docker['versions'] = {ref(OLD): OLDV + '\n', ref(NEW): '[RUNNER 2026-11-03 INFO] a log line\n%s\n' % V}
        p.curl['served'] = [OLD, NEW]
        p.production(OLD)
        p.image_ref(REF)
        self.keep = p.rpath('config.toml.pre-image')

    def up(self):
        return self.p.pool('up', V)

    def refused(self, r, *says):
        """up refused before it changed anything: no rollback kept, config.toml as it was, no 03 run, no restart."""
        t = self.test
        t.assertEqual(r.returncode, 1, r.stdout[-3000:] + r.stderr)
        for s in says:
            t.assertIn(s, r.stdout)
        t.assertFalse(os.path.lexists(self.keep))
        t.assertEqual(self.p.images(), [ref(OLD)] * 2)
        t.assertNotIn('== 03-runscaler.sh real', r.stdout)
        t.assertEqual(self.p.unit_now().get('restarts', 0), 0)


@needs_container
class UpReadsTheRecord(unittest.TestCase):
    def test_up_puts_the_record_s_digest_into_the_pool(self):
        g = Rig(self)
        g.p.record(V, NEW)
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertIn('POOL IMAGE DONE (up): %s' % ref(NEW), r.stdout)
        self.assertEqual(g.p.images(), [ref(NEW)] * 2)
        self.assertEqual(g.p.images('config.toml.pre-image'), [ref(OLD)] * 2)
        self.assertEqual(g.p.unit_now()['restarts'], 1)
        self.assertNotIn(ref(REF), r.stdout)

    def test_a_missing_record_refuses_and_names_the_fix(self):
        for why in ('no record at all', 'a record of another recipe only', 'a record of another version only'):
            with self.subTest(why):
                g = Rig(self)
                if why == 'a record of another recipe only':
                    g.p.record(V, NEW, recipe='e' * 64)
                elif why == 'a record of another version only':
                    g.p.record('2.339.1', NEW)
                r = g.up()
                g.refused(r, FIX, 'build record')

    def test_a_record_of_another_form_refuses_and_names_the_fix(self):
        good = 'format 1\nversion %s\ndigest %s\nrecipe %%s\n' % (V, NEW)
        pwned = '/tmp/hz-pool-image-sourced'
        cases = {
            'another format': lambda rc: good.replace('format 1', 'format 2') % rc,
            'two lines swapped': lambda rc: 'version %s\nformat 1\ndigest %s\nrecipe %s\n' % (V, NEW, rc),
            'no final newline': lambda rc: (good % rc)[:-1],
            'a fifth line': lambda rc: good % rc + 'note x\n',
            'an empty line at the end': lambda rc: good % rc + '\n',
            'CR LF': lambda rc: (good % rc).replace('\n', '\r\n'),
            'upper-case hex': lambda rc: good.replace(NEW, 'sha256:' + 'AB' * 32) % rc,
            'a digest of 63 hex': lambda rc: good.replace(NEW, NEW[:-1]) % rc,
            'two spaces': lambda rc: good.replace('digest ', 'digest  ') % rc,
            'key=value': lambda rc: good.replace('digest ', 'digest=') % rc,
            'a command in the digest': lambda rc: good.replace(NEW, '$(touch %s)' % pwned) % rc,
            'a NUL byte': lambda rc: good.replace(NEW, NEW[:30] + '\0' + NEW[30:]) % rc,
            'an empty file': lambda rc: '',
            'the version of another release': lambda rc: good.replace('version ' + V, 'version 2.338.2') % rc,
            'another recipe than its name': lambda rc: good % ('f' * 64),
        }
        for why, text in cases.items():
            with self.subTest(why):
                g = Rig(self)
                g.p.record(V, NEW, text=text(g.p.recipe()))
                r = g.up()
                g.refused(r, FIX)
                self.assertFalse(os.path.exists(pwned))
        for why in ('a symlink to a good record', 'a folder'):
            with self.subTest(why):
                g = Rig(self)
                name = '%s-%s' % (V, g.p.recipe())
                b = os.path.join(g.p.HOME, 'run', 'builds')
                if why == 'a folder':
                    os.makedirs(os.path.join(b, name))
                else:
                    g.p.record(V, NEW, name='good')
                    os.symlink('good', os.path.join(b, name))
                g.refused(g.up(), FIX)

    def test_a_digest_the_registry_does_not_serve_refuses(self):
        for why, served, registry_rc, says in (('it answers that it does not serve it', [OLD], 0, FIX),
                                               ('it does not answer', [OLD, NEW], 7, 'does not answer')):
            with self.subTest(why):
                g = Rig(self)
                g.p.record(V, NEW)
                g.p.curl.update(served=served, registry_rc=registry_rc)
                g.refused(g.up(), says)

    def test_an_image_whose_runner_is_not_the_version_refuses_and_names_the_rebuild(self):
        g = Rig(self)
        g.p.record(V, NEW)
        g.p.docker['versions'][ref(NEW)] = OLDV + '\n'
        r = g.up()
        g.refused(r, FIX, 'not %s' % V)
        self.assertNotIn('Dockerfile', r.stdout)

    def test_the_record_is_read_once(self):
        """After up copied the record, it is replaced by one of another form (a `tr` substitute, the first program up
        runs on the copy): up goes on with the digest it read. The control: the same replacement before up runs
        refuses."""
        hook = ('#!/bin/sh\n[ -e @ROOT@/hooked ] || { cat @ROOT@/inject > @REC@; : > @ROOT@/hooked; }\n'
                'exec /usr/bin/tr "$@"\n')
        for before in (False, True):
            with self.subTest(replaced_before_up=before):
                g = Rig(self)
                rec = g.p.record(V, NEW)
                bad = 'format 1\nversion %s\ndigest not-a-digest\nrecipe %s\n' % (V, g.p.recipe())
                if before:
                    g.p.write(rec, bad, 0o640)
                    g.refused(g.up(), FIX)
                    continue
                g.p.write(g.p.path('inject'), bad)
                g.p.write(g.p.path('stubs', 'tr'), hook.replace('@ROOT@', g.p.root).replace('@REC@', rec), 0o755)
                r = g.up()
                with open(rec) as f:
                    self.assertEqual(f.read(), bad, 'the hook did not run: the cell proves nothing')
                self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
                self.assertEqual(g.p.images(), [ref(NEW)] * 2)

    def test_a_pinned_file_that_is_not_this_release_s_refuses(self):
        for rel in ('bin/validate-class', 'bin/runner-start', 'setup/03-runscaler.sh', 'config/runscaler.service'):
            with self.subTest(rel):
                g = Rig(self)
                g.p.record(V, NEW)
                with open(os.path.join(g.p.build, rel), 'a') as f:
                    f.write('\n# changed\n')
                g.refused(g.up(), 'is not the reviewed copy')


@needs_container
class TheRecordBuildWrites(unittest.TestCase):
    def test_up_reads_the_record_02_d1_build_wrote(self):
        """The two copies of the recipe rule agree: the record a real `02-d1.sh build V` wrote (RUN_USER's ~/build) is
        the one up computes the name of from RS_USER's ~/build, the same release."""
        b = Sandbox(self)
        b.gh.release(V, tarball(V))
        b.docker['config_version'] = '%s\n' % V
        r = b.d1('build', V)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
        (name,) = os.listdir(os.path.join(b.home, 'run', 'builds'))
        with open(os.path.join(b.home, 'run', 'builds', name)) as f:
            text = f.read()
        d = re.search(r'^digest (sha256:[0-9a-f]{64})$', text, re.M).group(1)
        g = Rig(self)
        self.assertEqual(name, '%s-%s' % (V, g.p.recipe()))
        g.p.record(V, d, text=text)
        g.p.curl['served'].append(d)
        g.p.docker['versions'][ref(d)] = V + '\n'
        r = g.up()
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        self.assertEqual(g.p.images(), [ref(d)] * 2)


def release_section():
    with open(README) as f:
        return f.read().split('\n## A new runner release\n', 1)[1].split('\n## ', 1)[0]


def release_steps():
    return [b.strip() for b in re.findall(r'```\n(.*?)\n *```', release_section(), re.S)]


class Text(unittest.TestCase):
    def test_the_readme_s_release_steps_are_build_then_up(self):
        steps = release_steps()
        self.assertEqual(steps[:2], ["ssh <RUN_USER>@<host> 'bash ~/build/setup/02-d1.sh build <runner version>'",
                                     "ssh -o ServerAliveInterval=60 <RS_USER>@<host> 'bash -s -- up <runner version>' "
                                     "< linux-docker/setup/pool-image.sh"])
        step2 = re.search(r'^2\. .*$', release_section(), re.M).group(0)
        self.assertIn('build record', step2)
        for gone in ('Until then', 'image.ref', 'RUNNER_VERSION', 'Install step 5', 'Coming'):
            self.assertNotIn(gone, step2)
        with open(README) as f:
            self.assertIn('\n## Upgrading from a release before this one\n', f.read())   # kept for older hosts

    def test_the_readme_names_every_pinned_file(self):
        with open(PIMG) as f:
            pins = re.findall(r'^(?:PINS=")?\$B/([A-Za-z0-9._/-]+)=', f.read(), re.M)
        self.assertIn('bin/validate-class', pins)
        with open(README) as f:
            line = [l for l in f.read().splitlines() if l.startswith('`setup/pool-image.sh` pins ')]
        self.assertEqual(len(line), 1)
        for p in pins + ['setup/03-runscaler.sh']:
            self.assertIn('`%s`' % p, line[0])

    def test_pool_image_sh_says_what_up_reads_and_what_03_renders(self):
        """Item 29: the header says up reads the build record, and that `03 real` with no digest renders the image
        config.toml runs now; the NOTE of `back` says it too, and nothing names image.ref."""
        with open(PIMG) as f:
            text = f.read()
        head = text.split('\nset -uo pipefail\n', 1)[0]
        self.assertIn('build record', head)
        self.assertIn('config.toml runs', head)
        self.assertNotIn('image.ref', text)
        note = [l for l in text.splitlines() if 'echo "NOTE ' in l]
        self.assertEqual(len(note), 1, note)
        self.assertIn('03 real', note[0])
        self.assertNotIn('another Dockerfile', text)


@needs_container
class ReadmePath(unittest.TestCase):
    def test_the_readme_s_steps_1_and_2_run_as_written(self):
        """Step 1 as RUN_USER (a Sandbox: RS_USER is another user there, as 02-d1.sh's escape check needs), step 2 as
        RS_USER (a Pool) on the same host: RS_USER reads RUN_USER's ~/run/builds (here a link to it). Each line runs
        as written: `ssh [-o X] U@<host> '…'` runs its quoted command here, `< linux-docker/…` reads the release's
        file (here the copy with its pin lines rewritten), <runner version> is V."""
        b = Sandbox(self)
        b.gh.release(V, tarball(V))
        b.docker['config_version'] = '%s\n' % V
        g = Rig(self)
        os.makedirs(os.path.join(b.home, 'run', 'builds'), mode=0o750)
        os.symlink(os.path.join(b.home, 'run', 'builds'), os.path.join(g.p.HOME, 'run', 'builds'))
        laptop = g.p.path('laptop')
        os.makedirs(laptop)
        os.symlink(g.p.build, os.path.join(laptop, 'linux-docker'))
        d = 'sha256:' + 'd' * 64                       # the docker stub's pushed digest
        g.p.curl['served'].append(d)
        g.p.docker['versions'][ref(d)] = V + '\n'
        steps = release_steps()
        for i, (sb, line) in enumerate(((b, steps[0]), (g.p, steps[1]))):
            here = re.sub(r"ssh (?:-o \S+ )?\S+@<host> '", "bash -c '", line).replace('<runner version>', V)
            self.assertNotRegex(here, r'<[A-Za-z_ ]+>', 'a placeholder this cell does not fill')
            sb.files()
            r = subprocess.run(['bash', '-c', here], cwd=laptop, env=sb.env(), stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=600)
            self.assertEqual(r.returncode, 0, 'step %d: %s\n%s' % (i + 1, r.stdout[-3000:], r.stderr))
        self.assertIn('POOL IMAGE DONE (up): %s' % ref(d), r.stdout)
        self.assertEqual(g.p.images(), [ref(d)] * 2)


if __name__ == '__main__':
    unittest.main()
