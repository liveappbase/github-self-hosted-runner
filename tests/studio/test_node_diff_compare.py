"""bin/node-diff-compare NAMED_FILE CENSUS_FILE: the host PASSes a complete census that is a subset of the named list
(each lost entry printed NODE-DIFF-LOST) and FAILs on a new entry, a missing or unclosed block, no END, a count
mismatch, or an absent named file. Fixtures: tests/studio/fixtures/node-diff/ (the real line shapes of
setup/emudhra.node-diff and of the guest's census). Every FAIL cell runs its control (the equal census) too.
"""
import os
import unittest

from tests.studio.support_emudhra import FIXTURES, ZSH, copy_script, run, tmpdir

FX = os.path.join(FIXTURES, 'node-diff')
PREFIX = 'node-diff-compare: '
LOST = {
    'A': 'node20 3f034bb5704d44b2d08545a02057de93ebf3905fce721acbc730c06ddaee904e SecureSign Root CA12',
    'B': 'node20 4200f5043ac8590ebb527d209ed1503029fbcbd41ca1b506ec27f15ade7dac69 Secure Global CA',
    'C': 'node20 86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b emSign ECC Root CA - G3',
    'D': 'node20 bef256daf26e9c69bdec1602359798f3caf71821a03e018257c53c65617f3d4a FIRMAPROFESIONAL CA ROOT-A WEB',
}


def fx(name):
    return os.path.join(FX, name)


class NodeDiffCompare(unittest.TestCase):
    def setUp(self):
        self.d = tmpdir(self)
        self.tool = os.path.join(self.d, 'bin', 'node-diff-compare')
        copy_script(self, 'bin/node-diff-compare', self.tool)

    def compare(self, named, census):
        r = run([ZSH, '-f', self.tool, named, census], cwd=self.d)
        out = r.stdout.splitlines()
        for l in out:
            self.assertTrue(l.startswith(PREFIX), 'a line without the prefix: %r' % l)
        self.assertEqual(r.stderr, '')
        return r, [l[len(PREFIX):] for l in out]

    def lost(self, out):
        return [l[len('NODE-DIFF-LOST '):] for l in out if l.startswith('NODE-DIFF-LOST ')]

    def assert_pass(self, named, census, lost=()):
        r, out = self.compare(named, census)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual([l for l in out if l.startswith('FAIL')], [])
        self.assertEqual(self.lost(out), list(lost))
        self.assertTrue(out and out[-1].startswith('PASS'), r.stdout)
        return out

    def assert_fail(self, named, census, reason, control_named=None):
        r, out = self.compare(named, census)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(any(l.startswith('FAIL ') and reason in l for l in out), r.stdout)
        self.assertFalse(any(l.startswith('PASS') for l in out), r.stdout)
        # the control: the named list (the same one, unless the named file is the injected failure) with the equal
        # census PASSes
        self.assert_pass(control_named or named, fx('census-equal.txt'))
        return out

    def test_equal_passes(self):
        self.assert_pass(fx('named.node-diff'), fx('census-equal.txt'))

    def test_comment_and_blank_lines_are_skipped(self):
        self.assert_pass(fx('named-comments.node-diff'), fx('census-equal.txt'))

    def test_valid_empty_difference_and_empty_named_list_pass(self):
        self.assert_pass(fx('named-empty.node-diff'), fx('census-empty.txt'))
        # control: an empty named list FAILs a census that computed entries (each is new)
        r, out = self.compare(fx('named-empty.node-diff'), fx('census-equal.txt'))
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_one_entry_lost_passes_with_one_lost_line(self):
        out = self.assert_pass(fx('named.node-diff'), fx('census-lost-one.txt'), lost=[LOST['B']])
        self.assertEqual(out[-1], 'PASS: 3 computed entries in 2 block(s), each in the named list; 1 named entries lost')

    def test_whole_folder_lost_passes_with_its_lost_lines(self):
        self.assert_pass(fx('named.node-diff'), fx('census-lost-folder.txt'),
                         lost=[LOST['A'], LOST['B'], LOST['C'], LOST['D']])

    def test_new_entry_fails_and_is_listed(self):
        out = self.assert_fail(fx('named.node-diff'), fx('census-new-entry.txt'), 'a new entry')
        new = [l for l in out if l.startswith('FAIL ') and 'a new entry' in l]
        self.assertEqual(len(new), 1, out)
        self.assertIn('node20 0c2cd63df7806fa399ede809116b575bf87989f06518975b6d9658f3f4bb6c50 Example New Root CA', new[0])

    def test_new_folder_fails(self):
        out = self.assert_fail(fx('named.node-diff'), fx('census-new-folder.txt'), 'a new entry')
        self.assertTrue(any('node26 d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4' in l for l in out))

    def test_block_without_done_fails(self):
        out = self.assert_fail(fx('named.node-diff'), fx('census-no-done.txt'), 'node20 has no DONE line')
        # a block that did not complete proves nothing about its entries: they are not reported lost
        self.assertEqual(self.lost(out), [])

    def test_end_count_not_the_blocks_fails(self):
        self.assert_fail(fx('named.node-diff'), fx('census-end-count.txt'), 'END says 3 blocks')

    def test_no_end_fails(self):
        self.assert_fail(fx('named.node-diff'), fx('census-no-end.txt'), 'no END line')

    def test_count_mismatch_fails(self):
        self.assert_fail(fx('named.node-diff'), fx('census-count-mismatch.txt'), 'DONE says 3')

    def test_a_block_after_end_fails(self):
        self.assert_fail(fx('named.node-diff'), fx('census-after-end.txt'), 'after the END line')

    def test_named_file_absent_fails(self):
        self.assert_fail(os.path.join(self.d, 'no-such.node-diff'), fx('census-equal.txt'), 'absent or unreadable',
                         control_named=fx('named.node-diff'))

    def test_named_file_unreadable_fails(self):
        named = os.path.join(self.d, 'named.node-diff')
        with open(fx('named.node-diff')) as f, open(named, 'w') as g:
            g.write(f.read())
        os.chmod(named, 0)
        self.addCleanup(os.chmod, named, 0o644)
        self.assert_fail(named, fx('census-equal.txt'), 'absent or unreadable', control_named=fx('named.node-diff'))
        os.chmod(named, 0o644)
        self.assert_pass(named, fx('census-equal.txt'))   # control: readable again

    def test_census_file_absent_fails(self):
        self.assert_fail(fx('named.node-diff'), os.path.join(self.d, 'no-census.txt'), 'absent or unreadable')


if __name__ == '__main__':
    unittest.main()
