"""linux-docker/bin/validate-class RC OUTPUT_FILE: the ONE VALIDATE RULE (plan D5, PRE-VALIDATE) in bash, for the Linux
glue; 03-runscaler.sh classifies its validate with it. bin/validate-class is the Studio's copy, in zsh; its header
states the rule, and this copy's header states the same: PASS, API-ONLY, NON-API or UNKNOWN on stdout, exit 0; a usage
error exits 2 with one line on stderr. The two copies are pinned to agree by the shared folder
tests/studio/fixtures/validate/ (real outputs of runscaler, the class first in each file name): EVERY file there runs
through this copy and, where zsh exists (the Mac), through the zsh copy, and all must give the class of its name. The
same holds for the rule's shapes below (the cases of tests/studio/test_validate_class.py's own table).
A fixture's RC is 0 for a `pass-` file and 1 for any other: the name carries the class, not the code. These cells need a
bash 5 on PATH (the host runs bash 5) and run anywhere, the Linux images included.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from tests.hetzner.support import REPO, bash5

BASH_COPY = os.path.join(REPO, 'linux-docker', 'bin', 'validate-class')
ZSH_COPY = os.path.join(REPO, 'bin', 'validate-class')
ZSH = '/bin/zsh'
FIX = os.path.join(REPO, 'tests', 'studio', 'fixtures', 'validate')
CLASSES = {'pass': 'PASS', 'api-only': 'API-ONLY', 'non-api': 'NON-API', 'unknown': 'UNKNOWN'}
X = '  ✗ '
OK = '  ✓ '
API = X + 'scaleset[0] "linux-ci-main" GitHub API: failed to create new actions service request: context deadline exceeded'
HINT = '    Check that your token has the correct scopes (admin:org or repo)'
COBRA = 'Error: validation failed\nUsage:\n  runner validate [flags]\n'
INFO = '2026-11-02 12:03:17 INFO refreshing token githubConfigUrl=https://github.com/example-org/example'
CONFIG_CHECKS = (X + 'config: unknown key "runner-imag" in [[scaleset]]',
                 X + 'global config: health-port must be between 0 and 65535',
                 X + 'scaleset[0] "linux-ci-main": runner-image is required',
                 X + 'scale set collection: duplicate scale set name "linux-ci-main"')


def fixture(name):
    with open(os.path.join(FIX, name), encoding='utf-8') as f:
        return f.read()


def shapes():
    """(why, rc, text, class): the rule's shapes."""
    out = [('pass', 0, OK + 'scaleset[0] "linux-ci-main" — provider=docker\n' + INFO + '\n\nAll checks passed.\n',
            'PASS')]
    out += [('config check %d' % i, 1, l + '\n' + COBRA, 'NON-API') for i, l in enumerate(CONFIG_CHECKS)]
    out += [('config check %d without the indent' % i, 1, l[2:] + '\n' + COBRA, 'UNKNOWN')
            for i, l in enumerate(CONFIG_CHECKS)]
    out += [
        ('a REFUSE line', 1, 'runner-start: REFUSE token file is not 0600: /x/token-a\n', 'NON-API'),
        ('a REFUSE line after an API failure', 1, API + '\n' + HINT + '\nrunner-start: REFUSE x\n', 'NON-API'),
        ('REFUSE text not at the line start', 1, API + '\nnote: runner-start: REFUSE x\n', 'API-ONLY'),
        ('a record that quotes a check', 1, INFO + '\n2026-11-02 ERRO error="%sglobal config: x"\n' % X + API + '\n',
         'API-ONLY'),
        ('the same text as a check line', 1, INFO + '\n' + X + 'global config: x\n' + API + '\n', 'NON-API'),
        ('config then API', 1, CONFIG_CHECKS[2] + '\n' + API + '\n' + COBRA, 'NON-API'),
        ('API then config', 1, API + '\n' + HINT + '\n' + CONFIG_CHECKS[2] + '\n' + COBRA, 'API-ONLY'),
        ('a quoted name', 1, X + 'scaleset[12] "a \\"b\\" \\\\ c" GitHub API: 401 Unauthorized\n' + COBRA, 'API-ONLY'),
        ('a name that holds the API text', 1, X + 'scaleset[0] "x\\" GitHub API: y": runner-image is required\n',
         'NON-API'),
        ('rc 0, no output', 0, '', 'UNKNOWN'),
        ('rc 0, no pass line', 0, OK + 'Docker connectivity\n', 'UNKNOWN'),
        ('rc 0, a pass line with a space', 0, 'All checks passed. \n', 'UNKNOWN'),
        ('rc 0, a pass line without the dot', 0, 'All checks passed\n', 'UNKNOWN'),
        ('rc 0, a pass line with CR LF', 0, 'All checks passed.\r\n', 'UNKNOWN'),
        ('rc 0 and an API line', 0, API + '\n\nAll checks passed.\n', 'UNKNOWN'),
        ('rc 0 and a config line', 0, CONFIG_CHECKS[0] + '\n\nAll checks passed.\n', 'UNKNOWN'),
        ('rc 0 and a REFUSE line', 0, 'runner-start: REFUSE x\n\nAll checks passed.\n', 'UNKNOWN'),
        ('rc 1, a pass line only', 1, '\nAll checks passed.\n', 'UNKNOWN'),
        ('rc 1, API and a pass line', 1, API + '\n\nAll checks passed.\n', 'API-ONLY'),
        ('rc 1, no output', 1, '', 'UNKNOWN'),
        ('rc 2, no output', 2, '', 'UNKNOWN'),
        ('rc 255, no check line', 255, 'Error: failed to read config file: toml: expected newline\n' + COBRA, 'UNKNOWN'),
        ('the Docker check', 1, X + 'Docker connectivity at /home/x/run/docker.sock: refused\n' + COBRA, 'UNKNOWN'),
        ('the Tart check', 1, X + 'Tart binary not found in PATH\n' + COBRA, 'UNKNOWN'),
        ('a last line without a newline', 1, API, 'API-ONLY'),
        ('a pass line without a newline', 0, 'All checks passed.', 'PASS'),
    ]
    return out


class Copies(unittest.TestCase):
    def setUp(self):
        self.bash = bash5()
        if not self.bash:
            self.fail('no bash 5 on PATH: linux-docker/ runs under the host\'s bash 5 (Homebrew\'s on a Mac)')
        self.d = tempfile.mkdtemp(prefix='vc-')
        self.addCleanup(shutil.rmtree, self.d, True)
        self.zsh = os.path.exists(ZSH)

    def run_copy(self, shell, script, *args):
        return subprocess.run([shell] + (['-f'] if shell == ZSH else []) + [script] + list(args),
                              capture_output=True, text=True, stdin=subprocess.DEVNULL, env={'PATH': '/usr/bin:/bin'})

    def classes(self, rc, text):
        """{copy: class} for one output; each copy must exit 0 with one class line and nothing on stderr."""
        p = os.path.join(self.d, 'out.txt')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        out = {}
        for name, shell, script in (('bash', self.bash, BASH_COPY), ('zsh', ZSH, ZSH_COPY)):
            if name == 'zsh' and not self.zsh:
                continue
            r = self.run_copy(shell, script, str(rc), p)
            self.assertEqual((r.returncode, r.stderr), (0, ''), '%s: %s' % (name, r.stdout))
            self.assertRegex(r.stdout, r'^(PASS|API-ONLY|NON-API|UNKNOWN)\n$', name)
            out[name] = r.stdout.strip()
        return out

    def test_every_shared_fixture_gets_the_class_of_its_name_from_both_copies(self):
        names = sorted(os.listdir(FIX))
        self.assertGreaterEqual(len(names), 2, names)
        seen = set()
        for n in names:
            with self.subTest(n):
                kind = next((k for k in sorted(CLASSES, key=len, reverse=True) if n.startswith(k + '-')), None)
                self.assertIsNotNone(kind, '%s: no class first in its name (%s)' % (n, ', '.join(CLASSES)))
                rc = 0 if kind == 'pass' else 1
                got = self.classes(rc, fixture(n))
                self.assertEqual(set(got.values()), {CLASSES[kind]}, got)
                seen.add(kind)
                if self.zsh:   # the copies agree at the other code too
                    other = self.classes(1 - rc, fixture(n))
                    self.assertEqual(other['bash'], other['zsh'], other)
        self.assertTrue({'api-only', 'non-api'} <= seen, seen)

    def test_each_shape_of_the_rule(self):
        for why, rc, text, want in shapes():
            with self.subTest(why):
                got = self.classes(rc, text)
                self.assertEqual(set(got.values()), {want}, got)

    def test_usage_errors(self):
        p = os.path.join(self.d, 'v.txt')
        with open(p, 'w') as f:
            f.write('All checks passed.\n')
        for args in ([], ['0'], ['0', p, 'x'], ['x', p], ['-1', p], ['256', p], ['01', p], ['', p], ['1.0', p],
                     ['0', p + '.none'], ['0', self.d]):
            with self.subTest(args=args):
                r = self.run_copy(self.bash, BASH_COPY, *args)
                self.assertEqual((r.returncode, r.stdout), (2, ''))
                self.assertTrue(r.stderr.startswith('validate-class: usage: validate-class RC OUTPUT_FILE'), r.stderr)
                self.assertEqual(r.stderr.count('\n'), 1, r.stderr)
        for rc, want in (('0', 'PASS\n'), ('255', 'UNKNOWN\n')):   # the controls
            r = self.run_copy(self.bash, BASH_COPY, rc, p)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, want, ''))


if __name__ == '__main__':
    unittest.main()
