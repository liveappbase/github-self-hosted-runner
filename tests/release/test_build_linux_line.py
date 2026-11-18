"""tools/release-check --build: the release's fifth asset, linux-install-line.txt (W4 step 3, X-6'').

--build renders linux-install-line.txt with the ONE renderer, tools/render-linux-line, from the release tarball AS
UNPACKED (the renderer and its template linux-docker/setup/install-release.run-line both from the tarball, never from
the checkout), as `bash -p` under the first bash >= 5.2 on PATH, with the tarball's URL, its sha256, the VERSION and the
tag. It checks the rendered file (ONE printable line ending in a newline, the tarball's URL and sha256 in it, no @ but
in "$@") and parses it with that bash (`bash -p -n`; it never runs it), then writes it beside the other assets and
lists it in SHA256SUMS. A refused template, a line not of that shape or a line that does not parse builds no line and
no SHA256SUMS.

Pinned here: the asset is byte for byte what the renderer of the unpacked tarball prints for those four values (a
render made here, independently); SHA256SUMS holds exactly the five lines, each the sha256 of its file; the output
names the five files to upload; a renderer or a template changed in the checkout after the tag does not reach the
asset; a template the renderer refuses, a rendered line that bash 5 does not parse (one bash 3.2 does parse, inside
$(...)), and a line that no bash parses each fail the build with its reason and leave no linux-install-line.txt and no
SHA256SUMS; BASH_ENV does not reach the renderer (-p); a renderer of the tarball that exits 0 but prints nothing, two
lines, a line and a NUL byte, a line ending in CR LF, a byte above ASCII, another sha256, another URL or a stray @
builds nothing; a BASH_ENV that answers the bash version probe does not make /bin/bash 3.2 count as bash 5; BASHOPTS=extglob does not hide a parse error, neither in
the line nor in a script of linux-docker/ (the syntax rule), each with a control that the injection reaches a plain
`bash -n`.

The release-check that runs is a copy of this tree's, in a temporary repository that holds this tree's files but core/
and tests/ (so no jq row runs), committed once and tagged. Its softnet tarball is planted: the copy's softnet literals
(release-check's LIVE_SOFTNET_*, setup/02-wall.sh's SOFTNET_*, the manifest's softnet digest) are set to the planted
tarball's, so nothing is downloaded. A stub gh answers one passing check run. With no bash >= 5.2 on PATH every cell
FAILS: a check that cannot run is never green."""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ZSH = '/bin/zsh'
SLUG = 'liveappbase/github-self-hosted-runner'
GIT_ENV = {'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}
TEMPLATE = os.path.join('linux-docker', 'setup', 'install-release.run-line')
RENDERER = os.path.join('tools', 'render-linux-line')
GH = '#!/bin/sh\nprintf "1\\tcompleted\\tsuccess\\tplanted check\\n"\n'


def bash52():
    """The first bash >= 5.2 on PATH, as release-check finds it; None if there is none."""
    for d in os.environ.get('PATH', '').split(os.pathsep):
        b = os.path.join(d, 'bash')
        if not (os.path.isfile(b) and os.access(b, os.X_OK)):
            continue
        r = subprocess.run([b, '-c', 'echo $(( BASH_VERSINFO[0] * 100 + BASH_VERSINFO[1] ))'],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip().isdigit() and int(r.stdout.strip()) >= 502:
            return b
    return None


BASH = bash52()


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def write(path, data, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data if isinstance(data, bytes) else data.encode())
    os.chmod(path, mode)


def replace_once(path, old, new):
    with open(path) as f:
        text = f.read()
    if text.count(old) != 1:
        raise AssertionError('%s: %r occurs %d times, want 1' % (path, old, text.count(old)))
    with open(path, 'w') as f:
        f.write(text.replace(old, new))


def lit(path, name):
    """The value of the ONE column-0 line NAME=VALUE of a file."""
    with open(path) as f:
        vals = [l[len(name) + 1:].rstrip('\n') for l in f if l.startswith(name + '=')]
    if len(vals) != 1:
        raise AssertionError('%s: %d lines %s=, want 1' % (path, len(vals), name))
    return vals[0]


class Build(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(BASH, 'no bash >= 5.2 on PATH: these cells cannot run (brew install bash)')
        self.d = os.path.realpath(tempfile.mkdtemp(prefix='buildline-'))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.repo = os.path.join(self.d, 'repo')
        self.out = os.path.join(self.d, 'out')
        self.stubs = os.path.join(self.d, 'stubs')
        os.makedirs(self.stubs)
        os.symlink(BASH, os.path.join(self.stubs, 'bash'))
        write(os.path.join(self.stubs, 'gh'), GH, 0o755)
        with open(os.path.join(REPO, 'VERSION')) as f:
            self.version = f.read().strip()
        self.tag = 'v%s-rc.1' % self.version
        self.name = 'github-self-hosted-runner-%s.tar.gz' % self.tag
        self.plant_tree()

    def plant_tree(self):
        """This tree's files (the working tree, so an uncommitted change is what runs) but core/ and tests/, with the
        softnet literals set to a planted tarball's."""
        r = subprocess.run(['/usr/bin/git', 'ls-files', '-z'], cwd=REPO, capture_output=True, check=True)
        for rel in r.stdout.decode().split('\0'):
            if not rel or rel.startswith(('core/', 'tests/')):
                continue
            src, dst = os.path.join(REPO, rel), os.path.join(self.repo, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        member = b'planted softnet binary\n'
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as t:
            info = tarfile.TarInfo('softnet')
            info.size, info.mode = len(member), 0o755
            t.addfile(info, io.BytesIO(member))
        self.softnet = os.path.join(self.d, 'softnet.tgz')
        write(self.softnet, buf.getvalue())
        bsha, tsha = hashlib.sha256(member).hexdigest(), sha256(self.softnet)
        rc, wall, man = (os.path.join(self.repo, p) for p in ('tools/release-check', 'setup/02-wall.sh',
                                                              'setup/downloads.manifest'))
        old_b, old_t = lit(wall, 'SOFTNET_SHA'), lit(wall, 'SOFTNET_TARBALL_SHA')
        replace_once(rc, 'LIVE_SOFTNET_SHA=%s\n' % lit(rc, 'LIVE_SOFTNET_SHA'), 'LIVE_SOFTNET_SHA=%s\n' % bsha)
        replace_once(rc, 'LIVE_SOFTNET_TARBALL_SHA=%s\n' % lit(rc, 'LIVE_SOFTNET_TARBALL_SHA'),
                     'LIVE_SOFTNET_TARBALL_SHA=%s\n' % tsha)
        replace_once(wall, 'SOFTNET_SHA=%s\n' % old_b, 'SOFTNET_SHA=%s\n' % bsha)
        replace_once(wall, 'SOFTNET_TARBALL_SHA=%s\n' % old_t, 'SOFTNET_TARBALL_SHA=%s\n' % tsha)
        replace_once(man, ' %s ' % old_t, ' %s ' % tsha)

    def template(self, line):
        """Plant this template (one line, ending in a newline) in the tree before it is committed."""
        write(os.path.join(self.repo, TEMPLATE), line)

    def real_template(self):
        with open(os.path.join(REPO, TEMPLATE)) as f:
            return f.read()

    def build(self, after_tag=None, extra_env=None):
        env = dict(GIT_ENV, HOME=self.d, PATH=self.stubs + ':/usr/bin:/bin', LC_ALL='C', **(extra_env or {}))
        for argv in (['init', '-q'], ['add', '-A'], ['commit', '-q', '-m', 'build line test'],
                     ['tag', '-a', self.tag, '-m', 'test']):
            r = subprocess.run(['/usr/bin/git'] + argv, env=env, cwd=self.repo, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        if after_tag:
            after_tag()
        plist = os.path.join(self.d, 'private.txt')
        write(plist, 'zzz-no-such-value\n')
        r = subprocess.run([ZSH, '-f', os.path.join(self.repo, 'tools', 'release-check'), '--build', self.tag,
                            '--private-list', plist, '--out', self.out, '--softnet-tarball', self.softnet],
                           env=env, cwd=self.repo, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
        self.assertIn('release-check: checking ', r.stdout, r.stderr)    # it ran
        return r

    def green(self, r):
        self.assertIn('release-check: GREEN', r.stdout.splitlines(),
                      'the planted tree is not GREEN, so no cell reaches the build:\n' + r.stdout)

    def unpack(self):
        u = os.path.join(self.d, 'unpacked')
        with tarfile.open(os.path.join(self.out, self.name)) as t:
            t.extractall(u, filter='data')
        return os.path.join(u, self.version)

    def url(self):
        return 'https://github.com/%s/releases/download/%s/%s' % (SLUG, self.tag, self.name)

    def render_here(self, top):
        """The line rendered here, independently: the unpacked tarball's renderer on its own template."""
        r = subprocess.run([BASH, '-p', os.path.join(top, RENDERER), os.path.join(top, TEMPLATE), self.url(),
                            sha256(os.path.join(self.out, self.name)), self.version, self.tag],
                           capture_output=True, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
        self.assertEqual((r.returncode, r.stderr), (0, b''), 'the independent render failed')
        return r.stdout

    def failed(self, r, why):
        """The build failed for THIS reason, and left no line and no SHA256SUMS."""
        self.green(r)
        self.assertEqual(r.returncode, 1, r.stdout)
        fails = [l for l in r.stdout.splitlines() if l.startswith('release-check: BUILD FAILED: ')]
        self.assertEqual(len(fails), 1, r.stdout)
        self.assertIn(why, fails[0])
        left = os.listdir(self.out) if os.path.isdir(self.out) else []
        for f in ('linux-install-line.txt', 'SHA256SUMS'):
            self.assertNotIn(f, left, 'a failed build left %s' % f)
        return fails[0]

    # ---- the asset
    def test_the_line_is_the_renderers_of_the_tarball(self):
        r = self.build()
        self.green(r)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('release-check: built %s in %s' % (self.tag, self.out), r.stdout.splitlines())
        five = sorted([self.name, 'install-line.txt', 'linux-install-line.txt', 'root-line.txt', 'SHA256SUMS'])
        self.assertEqual(sorted(os.listdir(self.out)), five)
        with open(os.path.join(self.out, 'linux-install-line.txt'), 'rb') as f:
            asset = f.read()
        self.assertEqual(asset, self.render_here(self.unpack()))
        tsha = sha256(os.path.join(self.out, self.name))
        self.assertEqual(asset.count(b'\n'), 1, 'not ONE line')
        self.assertIn(self.url().encode(), asset)
        self.assertIn(tsha.encode(), asset)
        # SHA256SUMS: exactly five lines, each the sha256 of its file
        with open(os.path.join(self.out, 'SHA256SUMS')) as f:
            sums = [l.rstrip('\n').split('  ', 1) for l in f]
        want = {self.name: tsha}
        for f in ('install-line.txt', 'linux-install-line.txt', 'root-line.txt'):
            want[f] = sha256(os.path.join(self.out, f))
        want['%s/setup/02-wall.sh' % self.version] = sha256(os.path.join(self.unpack(), 'setup', '02-wall.sh'))
        self.assertEqual(len(sums), 5, sums)
        self.assertEqual(dict((n, s) for s, n in sums), want)
        # the output names the five files to upload
        self.assertIn('  upload exactly these five files as the release\'s assets:', r.stdout.splitlines())
        for f in five:
            self.assertIn('    %s' % os.path.join(self.out, f), r.stdout.splitlines())

    def test_the_checkout_does_not_reach_the_line(self):
        def change_checkout():
            write(os.path.join(self.repo, RENDERER), '#!/bin/bash\necho "the checkout\'s renderer"\n', 0o755)
            self.template(self.real_template().replace('set -u; ', 'set -u; : the checkout; ', 1))
        r = self.build(after_tag=change_checkout)
        self.green(r)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.out, 'linux-install-line.txt'), 'rb') as f:
            asset = f.read()
        self.assertNotIn(b'the checkout', asset)
        self.assertEqual(asset, self.render_here(self.unpack()))

    def test_bash_env_does_not_reach_the_renderer(self):
        log = os.path.join(self.d, 'bash-env.log')
        benv = os.path.join(self.d, 'bash-env.sh')
        write(benv, 'printf "%%s\\n" "$0" >> %s\n' % log)
        # control: without -p this BASH_ENV does run before the renderer
        subprocess.run([BASH, os.path.join(REPO, RENDERER)], env={'BASH_ENV': benv, 'PATH': '/usr/bin:/bin'},
                       capture_output=True)
        with open(log) as f:
            self.assertIn('render-linux-line', f.read(), 'the injection does not work: BASH_ENV was not read')
        os.unlink(log)
        r = self.build(extra_env={'BASH_ENV': benv})
        self.green(r)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.out, 'linux-install-line.txt')), 'no line was rendered')
        seen = ''
        if os.path.exists(log):
            with open(log) as f:
                seen = f.read()
        self.assertNotIn('render-linux-line', seen, 'BASH_ENV ran before the renderer: it was not run with -p')

    # ---- a failed render or parse builds no line
    def test_a_refused_template_builds_nothing(self):
        self.template(self.real_template().replace('set -u; ', 'set -u; : @HOST@; ', 1))
        line = self.failed(self.build(), 'linux-install-line')
        self.assertIn('REFUSE: the template holds an @', line)

    def test_a_template_absent_from_the_tarball_builds_nothing(self):
        os.unlink(os.path.join(self.repo, TEMPLATE))
        self.failed(self.build(), 'install-release.run-line')

    def test_a_line_no_bash_parses_builds_nothing(self):
        self.template(self.real_template().rstrip('\n') + '; if\n')
        self.failed(self.build(), 'linux-install-line: bash ')

    # ---- the rendered line is checked before anything is written (fix 1: review r1 P2-1): a renderer of the tarball
    # that exits 0 with a wrong line builds nothing. Each planted renderer wraps the real one (tools/render-linux-line.real)
    WRAPPER = '#!/bin/bash\nout=$(bash -p "$0.real" "$@") || exit 1\n%s\n'

    def bad_renderer(self, tail, why):
        with open(os.path.join(REPO, RENDERER)) as f:
            write(os.path.join(self.repo, RENDERER + '.real'), f.read(), 0o755)
        write(os.path.join(self.repo, RENDERER), self.WRAPPER % tail, 0o755)
        self.failed(self.build(), why)

    def test_a_renderer_that_prints_nothing_builds_nothing(self):
        self.bad_renderer('exit 0', 'not ONE printable line')

    def test_a_renderer_that_prints_two_lines_builds_nothing(self):
        self.bad_renderer('printf "%s\\n%s\\n" "$out" "$out"', 'not ONE printable line')

    def test_a_line_and_a_nul_byte_builds_nothing(self):
        # a good line, then a NUL and more: zsh's read stops at the NUL, so only the size sees the rest
        self.bad_renderer('printf "%s\\n\\0: more\\n" "$out"', 'not ONE printable line')

    def test_a_line_ending_in_cr_lf_builds_nothing(self):
        # fix 2 (fix review P2-1): the printable class, not only "no newline" (a CR is no newline)
        self.bad_renderer('printf "%s\\r\\n" "$out"', 'not ONE printable line')

    def test_a_line_with_a_byte_above_ascii_builds_nothing(self):
        self.bad_renderer('printf "%s\\200\\n" "$out"', 'not ONE printable line')

    def test_bash_env_does_not_fake_the_bash_version(self):
        # fix 2 (fix review P3-1): the version probe runs with -p, so a BASH_ENV cannot make bash 3.2 read as bash 5
        os.unlink(os.path.join(self.stubs, 'bash'))
        os.symlink('/bin/bash', os.path.join(self.stubs, 'bash'))
        benv = os.path.join(self.d, 'fake-version.sh')
        write(benv, 'echo "503 5.3.99"; exit 0\n')
        # stdin /dev/null, as in build(): with a socket on stdin bash 3.2 takes itself for an sshd child and skips
        # BASH_ENV (measured), so the injection would depend on where the cells run
        probe = subprocess.run(['/bin/bash', '-c', 'echo real'], env={'BASH_ENV': benv, 'PATH': '/usr/bin:/bin'},
                               stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(probe.stdout, '503 5.3.99\n', 'the injection does not work: BASH_ENV did not answer the probe')
        out = self.build(extra_env={'BASH_ENV': benv}).stdout.splitlines()
        self.assertNotIn('5.3.99', '\n'.join(out), 'the faked version was taken')
        self.assertTrue([l for l in out if l.startswith('RED syntax (linux-docker): partial, bash 3.2 only')], out)

    def test_a_line_with_another_sha256_builds_nothing(self):
        self.bad_renderer('printf "%%s\\n" "${out//$3/%s}"' % ('0' * 64), "the tarball's URL and sha256")

    def test_a_line_with_another_url_builds_nothing(self):
        self.bad_renderer('printf "%s\\n" "${out//$2/https://example.invalid/x.tar.gz}"', "the tarball's URL and sha256")

    def test_a_line_with_a_stray_at_builds_nothing(self):
        self.bad_renderer('printf "%s; : @HOST@\\n" "$out"', 'an @ that is not')

    # ---- BASHOPTS does not reach the parse (fix 1: review r1 P2-2): both bash -n run with -p
    EXTGLOB = 'case x in +(x)) : ;; esac'

    def extglob_injection_works(self):
        p = os.path.join(self.d, 'probe.sh')
        write(p, self.EXTGLOB + '\n')
        rc = [subprocess.run([BASH, '-n', p], capture_output=True, env=dict(env, PATH='/usr/bin:/bin')).returncode
              for env in ({'BASHOPTS': 'extglob'}, {})]
        self.assertEqual(rc[0], 0, 'the injection does not work: BASHOPTS=extglob does not reach bash -n')
        self.assertNotEqual(rc[1], 0, 'the probe parses without extglob: it decides nothing')

    def test_bashopts_does_not_hide_a_parse_error_in_the_line(self):
        self.extglob_injection_works()
        self.template(self.real_template().rstrip('\n') + '; ' + self.EXTGLOB + '\n')
        self.failed(self.build(extra_env={'BASHOPTS': 'extglob'}), 'linux-install-line: bash ')

    def test_bashopts_does_not_hide_a_parse_error_in_linux_docker(self):
        self.extglob_injection_works()
        write(os.path.join(self.repo, 'linux-docker', 'probe-extglob.sh'), '#!/bin/bash\n' + self.EXTGLOB + '\n', 0o755)
        r = self.build(extra_env={'BASHOPTS': 'extglob'})
        self.assertEqual([l for l in r.stdout.splitlines() if l.startswith('RED syntax: linux-docker/probe-extglob.sh: bash ')
                          and ' -n fails' in l], [l for l in r.stdout.splitlines() if l.startswith('RED ')], r.stdout)
        self.assertTrue([l for l in r.stdout.splitlines() if l.startswith('RED ')], 'the probe was not RED')

    def test_a_line_bash_5_does_not_parse_builds_nothing(self):
        # bash 3.2 does not parse inside $(...) until it runs it, so it passes this line; bash 5 does not
        tail = '; x=$(case)'
        p = os.path.join(self.d, 'probe.sh')
        write(p, 'true' + tail + '\n')
        self.assertEqual(subprocess.run(['/bin/bash', '-n', p], capture_output=True).returncode, 0,
                         'the decoy: /bin/bash 3.2 should parse this line')
        self.template(self.real_template().rstrip('\n') + tail + '\n')
        self.failed(self.build(), 'linux-install-line: bash ')


if __name__ == '__main__':
    sys.exit(unittest.main())
