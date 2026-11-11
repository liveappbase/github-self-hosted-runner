"""linux-image-smoke: the host's values reach the smoke. The image-name form and the wall's fixed targets come from the
host's linux-image.conf (docs/operations.md, "Building the Linux images"), never from the script.

The REAL bin/linux-image-smoke runs with its host paths rewritten into a sandbox, beside bin/linux-image-lib with the
conf's path rewritten to the sandbox's conf (tests/linux_image/support.py). Every value here is a placeholder:
documentation addresses (RFC 5737) and made-up names.
- WallTargets: the wall cells call exactly the gateway and then the conf's targets, in its order, from the job user;
  on a -docker image the container cells call the same list. CONTROL: another conf -> that other list.
- ImageName: an image of the conf's form is smoked; a name outside it is refused before any tart call, as is a run
  with no conf. (That the build's names are the forms the smoke accepts: test_build's ImageNameFromConf.)
"""
import os
import re
import unittest

from tests.linux_image.support import DATE, GW, REPO, Sandbox, conf_text as conf, smoke_rules

SCRIPT = os.path.join(REPO, 'bin', 'linux-image-smoke')
CONN = re.compile(r'^sudo -n -u runner timeout 6 bash -c exec 3<>/dev/tcp/([^/ ]+)/([0-9]+)$')
CCONN = re.compile(r'^sudo -n -u runner docker run --rm \S+ timeout 6 bash -c exec 3<>/dev/tcp/([^/ ]+)/([0-9]+)$')


class Smoke:
    def __init__(self, test, conf_text, targets=()):
        self.sb = Sandbox(test, smoke_rules(list(targets)))
        if conf_text is not None:
            self.sb.write_conf(conf_text)
        self.copy = self.sb.install(SCRIPT, 'linux-image-smoke')

    def run(self, image):
        self.r = self.sb.run(['/bin/zsh', '-f', self.copy, image])
        return self.r

    def walls(self, pat):
        return [m.group(1) + ':' + m.group(2) for m in (pat.match(c) for c in self.sb.execs()) if m]


A = ['192.0.2.10:80', '198.51.100.20:22', '203.0.113.30:22']
B = ['203.0.113.77:443', 'gw-placeholder.example:22']


class WallTargets(unittest.TestCase):
    def smoke(self, image, targets):
        s = Smoke(self, conf('example-linux', targets), targets)
        s.sb.add_vm(image)
        r = s.run(image)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('linux-image-smoke: ', r.stdout)
        self.assertRegex(r.stdout, r'SMOKE PASS\n')
        return s

    def test_the_wall_cells_call_the_confs_targets(self):
        s = self.smoke('example-linux-tart-' + DATE, A)
        self.assertEqual(s.walls(CONN), ['github.com:22', GW + ':22'] + A)
        self.assertEqual(s.walls(CCONN), [])
        for t in A:
            self.assertIn('ok   %s dropped (timeout)' % t, s.r.stdout)

    def test_docker_the_container_cells_call_them_too(self):
        s = self.smoke('example-linux-docker-tart-' + DATE, A)
        self.assertEqual(s.walls(CONN), ['github.com:22', GW + ':22'] + A)
        self.assertEqual(s.walls(CCONN), ['github.com:22', GW + ':22'] + A)

    def test_control_another_conf_another_list(self):
        s = self.smoke('example-linux-docker-tart-' + DATE, B)
        self.assertEqual(s.walls(CONN), ['github.com:22', GW + ':22'] + B)
        self.assertEqual(s.walls(CCONN), ['github.com:22', GW + ':22'] + B)


class ImageName(unittest.TestCase):
    def test_a_name_of_another_form_is_refused_before_tart(self):
        s = Smoke(self, conf('example-linux', A), A)
        s.sb.add_vm('other-linux-tart-' + DATE)
        r = s.run('other-linux-tart-' + DATE)
        self.assertEqual(r.returncode, 1)
        self.assertIn('linux-image-smoke: STOP usage: linux-image-smoke example-linux[-docker]-tart-<yyyymmdd>', r.stdout)
        self.assertEqual(s.sb.calls(), [])

    def test_control_the_confs_form_is_smoked(self):
        s = Smoke(self, conf('other-linux', A), A)
        s.sb.add_vm('other-linux-tart-' + DATE)
        r = s.run('other-linux-tart-' + DATE)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(['clone', 'other-linux-tart-' + DATE, 's1-linux-' + DATE], s.sb.calls())

    def test_no_conf_is_refused_before_tart(self):
        s = Smoke(self, None, A)
        s.sb.add_vm('example-linux-tart-' + DATE)
        r = s.run('example-linux-tart-' + DATE)
        self.assertEqual(r.returncode, 1)
        self.assertIn('linux-image-smoke: STOP ', r.stdout)
        self.assertIn('linux-image.conf', r.stdout)
        self.assertEqual(s.sb.calls(), [])


if __name__ == '__main__':
    unittest.main()
