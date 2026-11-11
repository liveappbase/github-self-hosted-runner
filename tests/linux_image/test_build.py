"""linux-image-build: the git-core PPA key is checked by its fingerprint before apt trusts it, in the one file apt
trusts, and the images are named from the host's linux-image.conf, never from the script.

The REAL bin/linux-image-build runs with its host paths rewritten into a sandbox, beside bin/linux-image-lib with the
conf's path rewritten to the sandbox's conf (tests/linux_image/support.py): a substitute tart answers the guest's
commands from RULES below, a substitute real-run ends when its VM is stopped. Every conf value is a placeholder.
- GitPpaKey: the key the guest fetched has another fingerprint -> the build STOPs with the fingerprint line, and no
  call after it writes the PPA's apt source, runs apt-get update or installs git. CONTROL: the pinned fingerprint ->
  it goes on, installs git from the PPA and ends DONE. A file with a second key beside the pinned one STOPs too.
- DockerKey (--docker): Docker's key file holds a second primary key beside Docker's -> the build STOPs with the
  fingerprint line before any call writes Docker's apt source, runs apt-get update or installs Docker. CONTROL:
  Docker's key alone -> it goes on and installs Docker. The rule is the git-core key's: every primary key in the file
  must be the pinned one.
- KeyringPaths: for each pinned key (git-core's, Docker's), the file the guest fetches the key into, the file whose
  fingerprints are checked and the file the apt source's signed-by names are ONE path (the substitute tart keeps no
  file contents, so only the paths can say it).
- ImageNameFromConf: with `image = NAME` the build makes NAME-tart-<date>, and with --docker NAME-docker-tart-<date>,
  and the smoke (the same conf) accepts both. CONTROL: another NAME -> other names, and the smoke refuses the first
  NAME's form. No conf, or a conf the reader refuses -> STOP before any tart call.
(That a whole run makes the calls the pre-move builder made, but for the named differences, is the move's private
proof, beside its keyed compare: the pre-move copy is not public.)
"""
import os
import re
import unittest

from tests.linux_image.support import DATE, REPO, TARGETS, Sandbox, conf_text, constant, smoke_rules

SCRIPT = os.path.join(REPO, 'bin', 'linux-image-build')
SMOKE = os.path.join(REPO, 'bin', 'linux-image-smoke')
WRONG_FPR = '0123456789ABCDEF0123456789ABCDEF01234567'
DOCKER_FPR = '9DC858229FC7DD38854AE2D88D81803C0EBFCD88'


def colons(*fprs):
    """gpg --show-keys --with-colons for one primary key per fingerprint (each with a subkey)"""
    out = []
    for f in fprs:
        out += ['pub:-:4096:1:%s:1713952998:::-:::scSC::::::23::0:' % f[-16:], 'fpr:::::::::%s:' % f,
                'uid:-::::1713952998::0::Test Key::::::::::0:', 'sub:-:4096:1:%s:1713952998::::::e::::::23:' % f[:16],
                'fpr:::::::::%s:' % (f[8:] + f[:8])]
    return '\n'.join(out)


def rules(git_fpr_out, docker_fpr_out=None):
    return [
        ('id -u', 0, '501'),
        ('id -un', 0, 'admin'),
        ('uname -m', 0, 'aarch64'),
        ('sh -c . /etc/os-release; echo $PRETTY_NAME', 0, 'Ubuntu 24.04.3 LTS'),
        ('hostname', 0, 'admin-vm'),
        ('locale -a', 0, 'C\nen_US.utf8\nPOSIX'),
        ('git --version', 0, 'git version 2.51.2'),
        ('*/config.sh --version', 0, '2.338.2'),
        ('sudo -n runuser -u runner -- sudo -n true', 1, ''),
        ('sysctl -n kernel.apparmor_restrict_unprivileged_userns', 0, '1'),
        ('systemctl is-active ssh.service ssh.socket', 3, ''),
        ('sudo -n runuser -u nobody -- docker info', 1, ''),
        ('*docker version --format*', 0, '28.5.1'),
        ('*docker compose version --short', 0, '2.40.0'),
        ('df -k /', 0, 'Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/vda1 41000000 6000000 33000000 16% /'),
        ('df -h /', 0, 'Filesystem Size Used Avail Use% Mounted on\n/dev/vda1 40G 6G 33G 16% /'),
        ('sh -c gpg --show-keys --with-colons /etc/apt/keyrings/docker.asc*', 0,
         colons(DOCKER_FPR) if docker_fpr_out is None else docker_fpr_out),
        ('sh -c gpg --show-keys --with-colons /etc/apt/keyrings/git-core*', 0, git_fpr_out),
    ]


class Build:
    def __init__(self, test, script, git_fpr_out, name='linux-image-build', conf='example-linux', docker_fpr_out=None):
        """CONF: the image NAME of the sandbox's linux-image.conf; None: no conf; a str with a newline: the whole file.
        DOCKER_FPR_OUT: what gpg answers for Docker's key file (None: Docker's key alone)"""
        self.sb = Sandbox(test, rules(git_fpr_out, docker_fpr_out))
        if conf is not None:
            self.sb.write_conf(conf if '\n' in conf else conf_text(conf))
        self.copy = self.sb.install(script, name, extra=[
            ('/bin/df -Pk /Users/ci/.tart', self.sb.path('stubs', 'df') + ' -Pk ' + self.sb.path('home'))])

    def run(self, *args):
        self.r = self.sb.run(['/bin/zsh', '-f', self.copy] + list(args))
        return self.r


def pinned(test):
    fpr = constant(SCRIPT, 'GIT_PPA_KEY_FPR')
    test.assertIsNotNone(fpr, 'bin/linux-image-build has no GIT_PPA_KEY_FPR constant')
    test.assertRegex(fpr, r'^[0-9A-F]{40}$')
    return fpr


class GitPpaKey(unittest.TestCase):
    def pinned(self):
        return pinned(self)

    def key_check_index(self, execs):
        at = [i for i, c in enumerate(execs) if 'gpg --show-keys' in c and 'git-core' in c]
        self.assertEqual(len(at), 1, 'one fingerprint read of the git-core key: %r' % execs)
        return at[0]

    def test_another_fingerprint_stops_before_apt_reads_the_ppa(self):
        pin = self.pinned()
        b = Build(self, SCRIPT, colons(WRONG_FPR))
        r = b.run()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('linux-image-build: STOP the git-core PPA key has fingerprint [%s], want %s' % (WRONG_FPR, pin),
                      r.stdout)
        execs = b.sb.execs()
        after = execs[self.key_check_index(execs) + 1:]
        self.assertEqual([c for c in after if 'apt-get update' in c or 'ppa.launchpadcontent.net' in c
                          or re.search(r'apt-get install .* git( |$)', c)], [], after)
        self.assertFalse(any('ppa.launchpadcontent.net' in c for c in execs), execs)
        self.assertNotIn('DONE', r.stdout)
        self.assertEqual(b.sb.vms(), [], 'the build VM is deleted, no image made')

    def test_control_the_pinned_fingerprint_goes_on_to_install_git(self):
        pin = self.pinned()
        b = Build(self, SCRIPT, colons(pin))
        r = b.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        execs = b.sb.execs()
        k = self.key_check_index(execs)
        after = execs[k + 1:]
        src = [i for i, c in enumerate(after) if 'ppa.launchpadcontent.net/git-core/ppa/ubuntu' in c]
        upd = [i for i, c in enumerate(after) if 'apt-get update' in c]
        git = [i for i, c in enumerate(after) if re.search(r'apt-get install .* git( |$)', c)]
        self.assertTrue(src and upd and git, after)
        self.assertLess(src[0], upd[0])
        self.assertLess(upd[0], git[0])
        self.assertIn('signed-by=/etc/apt/keyrings/git-core', after[src[0]])
        self.assertRegex(r.stdout, r'\nlinux-image-build: [0-9:]{8} DONE: example-linux-tart-%s ' % DATE)
        self.assertEqual(b.sb.vms(), ['example-linux-tart-' + DATE], 'the one image, the build VM deleted')

    def test_a_second_key_beside_the_pinned_one_stops(self):
        pin = self.pinned()
        b = Build(self, SCRIPT, colons(pin, WRONG_FPR))
        r = b.run()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('linux-image-build: STOP the git-core PPA key has fingerprint [%s %s], want %s'
                      % (pin, WRONG_FPR, pin), r.stdout)
        self.assertFalse(any('ppa.launchpadcontent.net' in c for c in b.sb.execs()))


KEYRING_GIT = '/etc/apt/keyrings/git-core-ppa.asc'
KEYRING_DOCKER = '/etc/apt/keyrings/docker.asc'
FETCHED = re.compile(r'curl [^&]* -o (\S+) ')
CHECKED = re.compile(r'gpg --show-keys --with-colons (\S+)')
SIGNED_BY = re.compile(r'signed-by=([^] ]+)\]')


class KeyringPaths(unittest.TestCase):
    """For a pinned key: the call that fetches it (curl -o FILE, from its URL), the fingerprint read that comes next
    (gpg --show-keys FILE) and the apt source that comes next (signed-by=FILE, for its repository) name ONE file, and
    it is KEYRING. Each must be there once."""

    def one_path(self, execs, url, repo, keyring):
        fetch = [i for i, c in enumerate(execs) if url in c and FETCHED.search(c)]
        self.assertEqual(len(fetch), 1, 'one fetch of the key from %s: %r' % (url, execs))
        src = [i for i, c in enumerate(execs) if repo in c and SIGNED_BY.search(c)]
        self.assertEqual(len(src), 1, 'one apt source for %s: %r' % (repo, execs))
        self.assertLess(fetch[0], src[0])
        between = execs[fetch[0] + 1:src[0]]
        checked = [CHECKED.search(c).group(1) for c in between if CHECKED.search(c)]
        self.assertEqual(len(checked), 1, 'one fingerprint read between the fetch and the source: %r' % between)
        paths = {'fetched': FETCHED.search(execs[fetch[0]]).group(1), 'checked': checked[0],
                 'signed-by': SIGNED_BY.search(execs[src[0]]).group(1)}
        self.assertEqual(paths, {k: keyring for k in paths})

    def test_the_git_ppa_key_is_one_file(self):
        b = Build(self, SCRIPT, colons(pinned(self)))
        r = b.run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.one_path(b.sb.execs(), 'keyserver.ubuntu.com', 'ppa.launchpadcontent.net/git-core/ppa/ubuntu', KEYRING_GIT)

    def test_dockers_key_is_one_file(self):
        b = Build(self, SCRIPT, colons(pinned(self)))
        r = b.run('--docker')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.one_path(b.sb.execs(), 'download.docker.com/linux/ubuntu/gpg', 'download.docker.com/linux/ubuntu ',
                      KEYRING_DOCKER)


class DockerKey(unittest.TestCase):
    def docker_check_index(self, execs):
        at = [i for i, c in enumerate(execs) if 'gpg --show-keys' in c and 'docker' in c]
        self.assertEqual(len(at), 1, 'one fingerprint read of Docker\'s key: %r' % execs)
        return at[0]

    def reads_dockers_repository(self, calls):
        return [c for c in calls if 'download.docker.com/linux/ubuntu ' in c or 'docker.list' in c
                or 'apt-get update' in c or re.search(r'apt-get install .*docker-ce', c)]

    def test_a_second_key_beside_dockers_stops_before_apt_reads_its_repository(self):
        b = Build(self, SCRIPT, colons(pinned(self)), docker_fpr_out=colons(DOCKER_FPR, WRONG_FPR))
        r = b.run('--docker')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('linux-image-build: STOP Docker\'s apt key has fingerprint [%s %s], want %s'
                      % (DOCKER_FPR, WRONG_FPR, DOCKER_FPR), r.stdout)
        execs = b.sb.execs()
        after = execs[self.docker_check_index(execs) + 1:]
        self.assertEqual(self.reads_dockers_repository(after), [], after)
        self.assertNotIn('DONE', r.stdout)
        self.assertEqual(b.sb.vms(), [], 'the build VM is deleted, no image made')

    def test_control_dockers_key_alone_goes_on_to_install_docker(self):
        b = Build(self, SCRIPT, colons(pinned(self)), docker_fpr_out=colons(DOCKER_FPR))
        r = b.run('--docker')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        execs = b.sb.execs()
        after = execs[self.docker_check_index(execs) + 1:]
        src = [i for i, c in enumerate(after) if 'docker.list' in c]
        upd = [i for i, c in enumerate(after) if 'apt-get update' in c]
        ins = [i for i, c in enumerate(after) if re.search(r'apt-get install .*docker-ce', c)]
        self.assertTrue(src and upd and ins, after)
        self.assertLess(src[0], upd[0])
        self.assertLess(upd[0], ins[0])
        self.assertEqual(b.sb.vms(), ['example-linux-docker-tart-' + DATE])


class ImageNameFromConf(unittest.TestCase):
    def build(self, name, *args):
        b = Build(self, SCRIPT, colons(pinned(self)), conf=name)
        r = b.run(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return b, r

    def smoke(self, b, image):
        """the smoke, in the build's sandbox (its conf, the image the build made) -> its result"""
        b.sb.set_rules(smoke_rules())
        return b.sb.run(['/bin/zsh', '-f', b.sb.install(SMOKE, 'linux-image-smoke'), image])

    def names(self, name):
        for args, image in (((), name + '-tart-' + DATE), (('--docker',), name + '-docker-tart-' + DATE)):
            with self.subTest(name=name, args=args):
                b, r = self.build(name, *args)
                self.assertRegex(r.stdout, r'(^|\n)linux-image-build: [0-9:]{8} start: %s from ' % image)
                self.assertRegex(r.stdout, r'\nlinux-image-build: [0-9:]{8} DONE: %s ' % image)
                self.assertEqual(b.sb.vms(), [image])
                s = self.smoke(b, image)
                self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
                self.assertRegex(s.stdout, r'SMOKE PASS\n')
                self.assertIn(['clone', image, 's1-linux-' + DATE], b.sb.calls())

    def test_the_confs_name_names_both_images_and_the_smoke_takes_them(self):
        self.names('example-linux')

    def test_control_another_name_other_images_and_the_first_form_is_refused(self):
        self.names('other-linux')
        b, _ = self.build('other-linux')
        b.sb.add_vm('example-linux-tart-' + DATE)
        n = len(b.sb.calls())
        s = self.smoke(b, 'example-linux-tart-' + DATE)
        self.assertEqual(s.returncode, 1, s.stdout + s.stderr)
        self.assertIn('linux-image-smoke: STOP usage: linux-image-smoke other-linux[-docker]-tart-<yyyymmdd>', s.stdout)
        self.assertEqual(b.sb.calls()[n:], [], 'no tart call after the refusal')

    def stops_before_tart(self, conf, why):
        for args in ((), ('--docker',)):
            with self.subTest(why=why, args=args):
                b = Build(self, SCRIPT, colons(pinned(self)), conf=conf)
                r = b.run(*args)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertRegex(r.stdout, r'^linux-image-build: STOP .*linux-image\.conf')
                self.assertEqual((b.sb.calls(), b.sb.calls('real-run'), b.sb.vms()), ([], [], []))
                self.assertEqual(os.listdir(b.sb.path('logdir')), [], 'no log: it stopped before the lock')

    def test_no_conf_stops_before_tart(self):
        self.stops_before_tart(None, 'no conf')

    def test_a_conf_the_reader_refuses_stops_before_tart(self):
        t = ' '.join(TARGETS)
        for text, why in (('wall-targets = %s\n' % t, 'no image line'),
                          ('image = Example_Linux\nwall-targets = %s\n' % t, 'a name of another shape'),
                          ('image = example-linux\nimage = other-linux\nwall-targets = %s\n' % t, 'two image lines'),
                          ('image = example-linux\nwall-targets = %s\nname = x\n' % t, 'an unknown line'),
                          ('image = example-linux\n', 'no wall-targets line')):
            self.stops_before_tart(text, why)


if __name__ == '__main__':
    unittest.main()
