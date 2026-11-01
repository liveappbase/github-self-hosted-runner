"""bin/golden-emudhra: the guest's Node census blocks, the host's node-diff compare after the census step, and --gate.

The guest part runs locally as a copy of the text between its EOS markers, with gtimeout, the runner folder and the
Homebrew bundle rewritten into the test's folder, and stub Node executables. The host part runs as a copy whose tart is
a stub that answers each guest step (the argument after golden-emudhra-guest) from scenario files.
"""
import os
import unittest

from tests.studio.support_emudhra import (FIXTURES, GUEST_W, RUNNER_SHA, ZSH, emudhra_copy, guest_copy, read, run,
                                          scenario, stub, tmpdir, write, lines)

FX = os.path.join(FIXTURES, 'node-diff')
FP = {
    'A': '3f034bb5704d44b2d08545a02057de93ebf3905fce721acbc730c06ddaee904e SecureSign Root CA12',
    'B': '4200f5043ac8590ebb527d209ed1503029fbcbd41ca1b506ec27f15ade7dac69 Secure Global CA',
    'C': '86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b emSign ECC Root CA - G3',
    'D': 'bef256daf26e9c69bdec1602359798f3caf71821a03e018257c53c65617f3d4a FIRMAPROFESIONAL CA ROOT-A WEB',
    'NEW': '0c2cd63df7806fa399ede809116b575bf87989f06518975b6d9658f3f4bb6c50 Example New Root CA',
}


def fx(name):
    return os.path.join(FX, name)


class GuestNodeCensus(unittest.TestCase):
    """The guest prints one block per externals Node executable and an END line; it compares nothing."""

    def setUp(self):
        self.d = tmpdir(self)
        gt = stub(os.path.join(self.d, 'stub', 'gtimeout'), 'shift 3\nexec "$@"\n')
        self.runner = os.path.join(self.d, 'runner')
        self.bundle = write(os.path.join(self.d, 'brew-cert.pem'), 'not read by the stub Node\n')
        self.guest, self.w = guest_copy(self, self.d, [
            ('T=/opt/homebrew/bin/gtimeout', 'T=' + gt),
            ('RUNNER_DIR=/Users/admin/actions-runner', 'RUNNER_DIR=' + self.runner),
            ('BREW_BUNDLE=/opt/homebrew/etc/ca-certificates/cert.pem', 'BREW_BUNDLE=' + self.bundle),
            ('  (fix) fix ;;\n', '  (fix) fix ;;\n  (t-nodediff) census_nodediff ;;\n'),   # the test's own entry
        ])

    def node(self, folder, out_lines, rc=0):
        """A stub Node: it checks it got `-e JS <the Homebrew bundle>`, prints OUT_LINES, exits RC."""
        body = '[[ $1 == -e && ${@[-1]} == %s ]] || { print -r -- "stub node: bad arguments"; exit 7 }\n' % self.bundle
        body += ''.join("print -r -- '%s'\n" % l for l in out_lines) + 'exit %d\n' % rc
        stub(os.path.join(self.runner, 'externals', folder, 'bin', 'node'), body)

    def census(self):
        r = run([ZSH, '-f', self.guest, 't-nodediff', self.w], cwd=self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r, [l for l in r.stdout.splitlines() if l.startswith(('NODE-', 'FAIL '))]

    def test_one_block_per_node_then_end(self):
        self.node('node20', [FP['D'], FP['A']])   # unsorted: the guest sorts each block
        self.node('node24', [])
        self.node('node26', ['ERROR 1 certificate(s) of the bundle cannot be read'], rc=1)
        r, out = self.census()
        fail26 = 'FAIL census: node26: the Node difference cannot be computed: ERROR 1 certificate(s) of the bundle cannot be read'
        self.assertEqual(out, [
            'NODE-CENSUS BEGIN node20',
            'NODE-DIFF node20 ' + FP['A'],
            'NODE-DIFF node20 ' + FP['D'],
            'NODE-CENSUS DONE node20 2',
            'NODE-CENSUS BEGIN node24',
            'NODE-CENSUS DONE node24 0',
            'NODE-CENSUS BEGIN node26',
            fail26,
            'NODE-CENSUS END 3',
        ])
        self.assertEqual(lines(os.path.join(self.w, 'fail.txt')), [fail26[len('FAIL '):]])

    def test_no_node_gives_an_empty_census(self):
        os.makedirs(os.path.join(self.runner, 'externals'))
        r, out = self.census()
        self.assertEqual(out, ['NODE-CENSUS END 0'])

    def test_the_host_reads_what_the_guest_prints(self):
        compare = os.path.join(self.d, 'node-diff-compare')
        from tests.studio.support_emudhra import copy_script
        copy_script(self, 'bin/node-diff-compare', compare)
        self.node('node20', [FP['D'], FP['B'], FP['C'], FP['A']])
        self.node('node24', [])
        r, _ = self.census()
        census = write(os.path.join(self.d, 'census.txt'), r.stdout)
        c = run([ZSH, '-f', compare, fx('named.node-diff'), census], cwd=self.d)
        self.assertEqual(c.returncode, 0, c.stdout)
        # control: one entry more than the named list
        self.node('node20', [FP['D'], FP['B'], FP['C'], FP['A'], FP['NEW']])
        r, _ = self.census()
        census = write(os.path.join(self.d, 'census.txt'), r.stdout)
        c = run([ZSH, '-f', compare, fx('named.node-diff'), census], cwd=self.d)
        self.assertEqual(c.returncode, 1, c.stdout)
        self.assertIn('a new entry', c.stdout)


class HostNodeDiff(unittest.TestCase):
    """golden-emudhra (the build, three arguments): after the census step the HOST runs node-diff-compare on the named
    list and the guest's raw census lines; a FAIL makes the stage RED."""

    def setUp(self):
        self.d = tmpdir(self)
        self.tool = emudhra_copy(self, self.d, named_src=fx('named.node-diff'))
        self.hosttmp = os.path.join(self.d, 'hosttmp')
        os.makedirs(self.hosttmp)
        for step in ('save', 'probe', 'fix', 'report'):
            scenario(self.d, step, out='the %s step\n' % step)

    def stage(self):
        r = run([ZSH, '-f', self.tool, 'gold-20261101', '/tmp/runner.tgz', RUNNER_SHA],
                env={'TMPDIR': self.hosttmp + '/', 'HOME': self.d}, cwd=self.d)
        self.assertFalse(os.path.exists(os.path.join(self.d, 'unexpected')), read(os.path.join(self.d, 'unexpected'))
                         if os.path.exists(os.path.join(self.d, 'unexpected')) else '')
        self.assertEqual(os.listdir(self.hosttmp), [], 'the host temp file was not removed')
        return r, r.stdout.splitlines()

    def test_census_with_a_new_entry_ends_red(self):
        scenario(self.d, 'census', out=read(fx('census-new-entry.txt')))
        r, out = self.stage()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(any(l.startswith('golden-emudhra: node-diff-compare: FAIL a new entry') for l in out), r.stdout)
        self.assertTrue(out[-1].startswith('golden-emudhra: RED'), r.stdout)

    def test_census_equal_to_the_named_list_ends_green(self):
        scenario(self.d, 'census', out=read(fx('census-equal.txt')))
        r, out = self.stage()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(any(l.startswith('golden-emudhra: node-diff-compare: PASS') for l in out), r.stdout)
        self.assertTrue(out[-1].startswith('golden-emudhra: GREEN'), r.stdout)
        # the host's census file was made in TMPDIR (the test's folder) while the census step ran, and removed after it
        tmp = lines(os.path.join(self.d, 'census-tmp'))
        self.assertEqual(len(tmp), 1, tmp)
        self.assertRegex(tmp[0], r'^golden-emudhra-census\.[A-Za-z0-9]+$')

    def test_a_lost_entry_stays_green_and_is_printed(self):
        scenario(self.d, 'census', out=read(fx('census-lost-one.txt')))
        r, out = self.stage()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn('golden-emudhra: node-diff-compare: NODE-DIFF-LOST node20 ' + FP['B'], out)

    def test_census_without_end_ends_red(self):
        scenario(self.d, 'census', out=read(fx('census-no-end.txt')))
        r, out = self.stage()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('golden-emudhra: node-diff-compare: FAIL no END line: the census is incomplete', out)

    def test_named_list_absent_ends_red(self):
        os.remove(os.path.join(self.d, 'setup', 'emudhra.node-diff'))
        scenario(self.d, 'census', out=read(fx('census-equal.txt')))
        r, out = self.stage()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(any('node-diff-compare: FAIL the named list' in l for l in out), r.stdout)

    def test_the_census_step_gets_no_named_list(self):
        scenario(self.d, 'census', out=read(fx('census-equal.txt')))
        self.stage()
        calls = lines(os.path.join(self.d, 'calls'))
        self.assertIn('census|%s|/tmp/runner.tgz|%s' % (GUEST_W, RUNNER_SHA), calls)
        steps = [c.split('|')[0] for c in calls if not c.startswith('rm ')]
        self.assertEqual(steps, ['save', 'probe', 'fix', 'probe', 'census', 'report'])


if __name__ == '__main__':
    unittest.main()
