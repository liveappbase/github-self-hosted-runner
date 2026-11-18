"""tools/render-linux-line: the ONE renderer of a release's linux-install-line.txt (W4 X-6').

`bash tools/render-linux-line TEMPLATE URL SHA VERSION TAG` prints the template with its four placeholders (@URL@,
@SHA@, @VERSION@, @TAG@) replaced, or one `REFUSE: …` line on stderr, exit 1 and NOTHING on stdout. tools/release-check
--build and the linux-docker cells both call this file, so the shipped line and the tested line come from one piece of
code. Pinned here: the output for good input (a final tag and an rc tag), each value's strict form (so no value can
carry an @, a quote, a space or a `&`, which bash 5.2's patsub_replacement would expand), each template refusal (a
placeholder missing, not exactly one line, a control or non-ASCII byte, an @ outside the four placeholders), and the
argument count. Every cell runs under macOS's /bin/bash 3.2 (release-check parses tools/ with it) and under the first
bash >= 5.2 on PATH (release-check --build runs the renderer with it; the Linux hosts run bash 5). With no such bash,
the 5.x cells FAIL: a check that cannot run is never green."""
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RENDER = os.path.join(REPO, 'tools', 'render-linux-line')

SLUG = 'owner/repo'
SHA = '0123456789abcdef' * 4
TEMPLATE = ('set -eu; u=@URL@; h=@SHA@; v=@VERSION@; t=@TAG@; echo "$u $h $v $t"; '
            'test "$h" = @SHA@\n')


def url(tag, slug=SLUG):
    return 'https://github.com/%s/releases/download/%s/github-self-hosted-runner-%s.tar.gz' % (slug, tag, tag)


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


class Base(unittest.TestCase):
    BASH = None   # set by the subclasses

    def setUp(self):
        self.assertIsNotNone(self.BASH, 'no bash >= 5.2 on PATH: these cells cannot run (brew install bash)')
        self.d = os.path.realpath(tempfile.mkdtemp(prefix='render-'))
        self.addCleanup(shutil.rmtree, self.d, True)

    def tpl(self, data):
        p = os.path.join(self.d, 'line.tpl')
        with open(p, 'wb') as f:
            f.write(data if isinstance(data, bytes) else data.encode())
        return p

    def run_render(self, *args):
        r = subprocess.run([self.BASH, RENDER] + list(args), capture_output=True, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'en_US.UTF-8'})
        return r.returncode, r.stdout, r.stderr.decode('utf-8', 'replace')

    def ok(self, template, u, sha, version, tag):
        rc, out, err = self.run_render(self.tpl(template), u, sha, version, tag)
        self.assertEqual((rc, err), (0, ''), 'a good input was refused')
        return out.decode()

    def refused(self, template, u, sha, version, tag, why):
        rc, out, err = self.run_render(self.tpl(template), u, sha, version, tag)
        self.assertEqual(rc, 1, '%s: not refused (rc %d, stdout %r)' % (why, rc, out))
        self.assertEqual(out, b'', '%s: refused, but something was printed on stdout' % why)
        lines = err.splitlines()
        self.assertEqual(len(lines), 1, '%s: stderr is not ONE line: %r' % (why, err))
        self.assertTrue(lines[0].startswith('REFUSE: '), '%s: stderr is not a REFUSE line: %r' % (why, err))


class Cells:
    # ---- good input (the controls of every refusal below)
    def test_final_tag(self):
        out = self.ok(TEMPLATE, url('v1.2.3'), SHA, '1.2.3', 'v1.2.3')
        want = TEMPLATE.replace('@URL@', url('v1.2.3')).replace('@SHA@', SHA).replace('@VERSION@', '1.2.3') \
            .replace('@TAG@', 'v1.2.3')
        self.assertEqual(out, want)
        self.assertEqual(out.count('\n'), 1)
        self.assertNotIn('@', out)

    def test_rc_tag(self):
        out = self.ok(TEMPLATE, url('v0.2.0-rc.10'), SHA, '0.2.0', 'v0.2.0-rc.10')
        self.assertIn('t=v0.2.0-rc.10;', out)
        self.assertIn('v=0.2.0;', out)
        self.assertEqual(out.count(SHA), 2, 'every occurrence of a placeholder is replaced')

    def test_the_line_runs(self):
        """The rendered line is a bash script: it runs, and prints the four values."""
        out = self.ok(TEMPLATE, url('v1.2.3'), SHA, '1.2.3', 'v1.2.3')
        r = subprocess.run([self.BASH, '-s'], input=out.encode(), capture_output=True)
        self.assertEqual((r.returncode, r.stdout.decode()), (0, '%s %s 1.2.3 v1.2.3\n' % (url('v1.2.3'), SHA)))

    # ---- the values' forms
    def test_url_forms(self):
        good = url('v1.2.3')
        for bad, why in [
                (good.replace('https://', 'http://'), 'http'),
                (good.replace('github.com', 'example.com'), 'another host'),
                (good.replace('github.com', 'github.com.example.com'), 'a host that starts with github.com'),
                (url('v1.2.4'), 'the URL names another tag'),
                (good.replace('/download/v1.2.3/', '/download/v1.2.4/'), 'the folder names another tag'),
                (good.replace('runner-v1.2.3.tar.gz', 'runner-v1.2.4.tar.gz'), 'the file names another tag'),
                (good.replace('.tar.gz', '.tgz'), 'another file name'),
                (url('v1.2.3', 'owner'), 'a slug with no repository'),
                (url('v1.2.3', 'own er/repo'), 'a space'),
                (url('v1.2.3', "own'er/repo"), 'a quote'),
                (url('v1.2.3', 'own&er/repo'), 'an ampersand'),
                (url('v1.2.3', 'own@er/repo'), 'an @'),
                (url('v1.2.3', 'own$er/repo'), 'a dollar'),
                (url('v1.2.3', 'a/b/c'), 'a slug of three parts'),
                (good + '?x=1', 'a query'),
                (good + '\n', 'a newline'),
                ('', 'empty')]:
            with self.subTest(why=why):
                self.refused(TEMPLATE, bad, SHA, '1.2.3', 'v1.2.3', 'URL ' + why)

    def test_sha_forms(self):
        for bad, why in [(SHA[:-1], '63 hex'), (SHA + '0', '65 hex'), (SHA.upper(), 'upper case'),
                         (SHA[:-1] + 'g', 'not hex'), (SHA[:-1] + '&', 'an ampersand'), ('', 'empty'),
                         (SHA + '\n', 'a newline')]:
            with self.subTest(why=why):
                self.refused(TEMPLATE, url('v1.2.3'), bad, '1.2.3', 'v1.2.3', 'SHA ' + why)

    def test_version_forms(self):
        for bad, why in [('1.2', 'two parts'), ('1.2.3.4', 'four parts'), ('1.2.3a', 'a letter'),
                         ('1.2.3&', 'an ampersand'), ('1.2.x', 'a letter part'), ('', 'empty'), ('v1.2.3', 'a v')]:
            with self.subTest(why=why):
                tag = 'v' + bad
                self.refused(TEMPLATE, url(tag), SHA, bad, tag, 'VERSION ' + why)

    def test_tag_forms(self):
        for bad, why in [('v1.2.4', 'another version'), ('1.2.3', 'no v'), ('v1.2.3-rc.', 'rc with no number'),
                         ('v1.2.3-rc.1x', 'rc with a letter'), ('v1.2.3-beta.1', 'not rc'), ('v1.2.3-rc.1-rc.2', 'two rcs'),
                         ('v1.2.31', 'a version that starts with the version'), ('v1x2x3', 'dots as a pattern'),
                         ('', 'empty')]:
            with self.subTest(why=why):
                self.refused(TEMPLATE, url(bad), SHA, '1.2.3', bad, 'TAG ' + why)

    # ---- the template
    def test_template_placeholders(self):
        for ph in ['@URL@', '@SHA@', '@VERSION@', '@TAG@']:
            with self.subTest(missing=ph):
                self.refused(TEMPLATE.replace(ph, 'x'), url('v1.2.3'), SHA, '1.2.3', 'v1.2.3', 'no ' + ph)

    def test_template_other_at(self):
        for extra, why in [('@HOST@', 'another placeholder'), ('a@b', 'a lone @'), ('@URL', 'half a placeholder'),
                           ('@@SHA@', 'an @ before a placeholder')]:
            with self.subTest(why=why):
                self.refused(TEMPLATE.replace('echo', 'echo ' + extra, 1), url('v1.2.3'), SHA, '1.2.3', 'v1.2.3',
                             'template ' + why)

    def test_template_one_line(self):
        t = TEMPLATE.rstrip('\n')
        for data, why in [(t, 'no newline at the end'), (t + '\n\n', 'an empty second line'),
                          (t + '\necho x\n', 'two lines'), (b'', 'an empty file'), ('\n', 'one empty line')]:
            with self.subTest(why=why):
                self.refused(data, url('v1.2.3'), SHA, '1.2.3', 'v1.2.3', 'template ' + why)

    def test_template_bytes(self):
        for c, why in [(b'\t', 'a tab'), (b'\r', 'a CR'), (b'\x00', 'a NUL'), (b'\x1b', 'an escape'),
                       (b'\xc3\xa9', 'a non-ASCII letter'), (b'\x7f', 'a DEL')]:
            with self.subTest(why=why):
                data = TEMPLATE.encode().replace(b'echo', b'echo ' + c, 1)
                self.refused(data, url('v1.2.3'), SHA, '1.2.3', 'v1.2.3', 'template ' + why)

    def test_template_not_a_file(self):
        for p, why in [(os.path.join(self.d, 'absent'), 'absent'), (self.d, 'a folder')]:
            with self.subTest(why=why):
                rc, out, err = self.run_render(p, url('v1.2.3'), SHA, '1.2.3', 'v1.2.3')
                self.assertEqual((rc, out), (1, b''))
                self.assertTrue(err.startswith('REFUSE: ') and err.count('\n') == 1, err)

    def test_argument_count(self):
        good = [self.tpl(TEMPLATE), url('v1.2.3'), SHA, '1.2.3', 'v1.2.3']
        for args, why in [(good[:4], 'four'), (good + ['x'], 'six'), ([], 'none')]:
            with self.subTest(why=why):
                rc, out, err = self.run_render(*args)
                self.assertEqual((rc, out), (1, b''), why)
                self.assertTrue(err.startswith('REFUSE: ') and err.count('\n') == 1, err)


class Bash32(Base, Cells):
    BASH = '/bin/bash'


class Bash52(Base, Cells):
    BASH = bash52()


if __name__ == '__main__':
    unittest.main()
