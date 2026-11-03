"""linux-docker/image/: the runner image's recipe. The Dockerfile builds on the PINNED base (GitHub's runner image by
digest), COPYs install-runner.sh and the checked runner tarball (02-d1.sh puts it into the build context as
runner.tar.gz), and runs install-runner.sh, which puts that release's runner in place of the base's:

- it removes the base's bin/ and externals/ and the TARBALL's root files, and moves the tarball's in, owned by the
  owner of the base's bin/ (the base gives its runner to the runner user);
- everything else of the home stays: the runner user's dotfiles, other folders, a root file the tarball lacks;
- a tarball of another top-level shape (a folder other than bin/ and externals/, a dotfile, a link, bin/ or externals/
  missing) is REFUSED with the home unchanged.

The Dockerfile cell reads text and runs anywhere; the install-runner.sh cells run the real script, as root, on a fake
home in a container (tests/hetzner/support.py).
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.hetzner.support import REPO, needs_container, tarball

IMAGE = os.path.join(REPO, 'linux-docker', 'image')
OWNER = (1001, 123)      # the base image's runner:docker


def snapshot(top):
    """{relative path: (kind, mode, uid, gid, content sha256 or link target)} of everything under top."""
    out = {}
    for d, dirs, files in os.walk(top):
        for n in dirs + files:
            p = os.path.join(d, n)
            st = os.lstat(p)
            if os.path.islink(p):
                what = ('link', os.readlink(p))
            elif os.path.isdir(p):
                what = ('dir', '')
            else:
                with open(p, 'rb') as f:
                    what = ('file', hashlib.sha256(f.read()).hexdigest())
            out[os.path.relpath(p, top)] = (what[0], st.st_mode & 0o7777, st.st_uid, st.st_gid, what[1])
    return out


class Dockerfile(unittest.TestCase):
    def test_the_recipe_builds_on_the_pinned_base_and_installs_the_checked_tarball(self):
        with open(os.path.join(IMAGE, 'Dockerfile')) as f:
            lines = [l for l in f.read().splitlines() if l and not l.startswith('#')]
        self.assertRegex(lines[0], r'^FROM ghcr\.io/actions/actions-runner@sha256:[0-9a-f]{64}$')
        self.assertEqual([l for l in lines if l.startswith('FROM')], [lines[0]], 'one stage, on the pinned base')
        self.assertIn('COPY install-runner.sh runner.tar.gz /tmp/runner/', lines)
        self.assertIn('RUN bash /tmp/runner/install-runner.sh /tmp/runner/runner.tar.gz /home/runner '
                      '&& rm -rf /tmp/runner', lines)
        self.assertEqual([l for l in lines if l.startswith('USER')][-1], 'USER runner')
        self.assertEqual(sorted(os.listdir(IMAGE)), ['Dockerfile', 'install-runner.sh'])


@needs_container
class InstallRunner(unittest.TestCase):
    def home(self):
        root = tempfile.mkdtemp(prefix='hz-ir-')
        self.addCleanup(shutil.rmtree, root, True)
        h = os.path.join(root, 'runner')
        files = {'bin/Runner.Listener': 'old listener\n', 'bin/old-only.dll': 'old\n',
                 'externals/node16/node': 'old node\n', 'config.sh': 'old config\n', 'run.sh': 'old run\n',
                 'safe_sleep.sh': 'a base root file the tarball lacks\n', '.bashrc': 'rc\n', '.profile': 'p\n',
                 'k8s/index.js': 'hooks\n'}
        for rel, text in files.items():
            p = os.path.join(h, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w') as f:
                f.write(text)
        for d, dirs, fs in os.walk(h):
            for n in [d] + [os.path.join(d, x) for x in dirs + fs]:
                os.chown(n, *OWNER)
        tgz = os.path.join(root, 'runner.tar.gz')
        return root, h, tgz

    def run_it(self, tgz, h):
        return subprocess.run(['bash', os.path.join(IMAGE, 'install-runner.sh'), tgz, h], capture_output=True,
                              text=True, stdin=subprocess.DEVNULL, timeout=120,
                              env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})

    def test_the_runner_is_replaced_and_the_rest_of_the_home_kept(self):
        root, h, tgz = self.home()
        with open(tgz, 'wb') as f:
            f.write(tarball('2.339.0'))
        before = snapshot(h)
        r = self.run_it(tgz, h)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = snapshot(h)
        self.assertEqual(sorted(k for k in after if k.split('/')[0] in ('bin', 'externals')),
                         ['bin', 'bin/Runner.Listener', 'externals', 'externals/node20', 'externals/node20/node'])
        with open(os.path.join(h, 'bin', 'Runner.Listener')) as f:
            self.assertEqual(f.read(), 'listener 2.339.0\n')
        for n in ('config.sh', 'run.sh', 'env.sh'):
            with open(os.path.join(h, n)) as f:
                self.assertEqual(f.read(), '#!/bin/bash\necho 2.339.0\n', n)
        for k in ('.bashrc', '.profile', 'k8s', 'k8s/index.js', 'safe_sleep.sh'):
            self.assertEqual(after[k], before[k], k)
        for k, v in after.items():
            self.assertEqual(v[2:4], OWNER, k)
        self.assertEqual(sorted(after), sorted(['.bashrc', '.profile', 'k8s', 'k8s/index.js', 'safe_sleep.sh',
                                                'config.sh', 'run.sh', 'env.sh', 'bin', 'bin/Runner.Listener',
                                                'externals', 'externals/node20', 'externals/node20/node']))

    def test_a_tarball_of_another_shape_changes_nothing(self):
        cases = {'another top-level folder': dict(extra=[('docs', None), ('docs/a', 'x')]),
                 'a top-level dotfile': dict(extra=[('.bashrc', 'theirs\n')]),
                 'a top-level link': dict(extra=[('runlink', '->/bin/sh')]),
                 'no bin/': dict(omit=('bin',)),
                 'no externals/': dict(omit=('externals',))}
        for why, kw in cases.items():
            with self.subTest(why):
                root, h, tgz = self.home()
                with open(tgz, 'wb') as f:
                    f.write(tarball('2.339.0', **kw))
                before = snapshot(h)
                r = self.run_it(tgz, h)
                self.assertNotEqual(r.returncode, 0, why)
                self.assertIn('REFUSE', r.stderr, why)
                self.assertEqual(snapshot(h), before, why)


if __name__ == '__main__':
    unittest.main()
