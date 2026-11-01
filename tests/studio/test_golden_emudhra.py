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


class GateHost(unittest.TestCase):
    """golden-emudhra --gate VM: the guest steps save and gate only, then the cleanup; GATE GREEN (0) or GATE RED (1)."""

    VM = 's1-gate-20261101120000'

    def setUp(self):
        self.d = tmpdir(self)
        self.tool = emudhra_copy(self, self.d, named_src=fx('named.node-diff'))
        scenario(self.d, 'save', out='1. save\n')
        scenario(self.d, 'gate', out='the gate\ncensus: control USERTrust RSA: verify-cert exits 0 (pass)\n')

    def gate(self, *args):
        r = run([ZSH, '-f', self.tool, *(args or ('--gate', self.VM))], env={'HOME': self.d}, cwd=self.d)
        self.assertFalse(os.path.exists(os.path.join(self.d, 'unexpected')))
        return r, r.stdout.splitlines()

    def steps(self):
        return [c.split('|')[0] for c in lines(os.path.join(self.d, 'calls')) if not c.startswith('rm ')]

    def test_gate_green(self):
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(out[-1], 'golden-emudhra: GATE GREEN')
        self.assertEqual(self.steps(), ['save', 'gate'])   # never probe, fix, census or report
        self.assertEqual(set(lines(os.path.join(self.d, 'exec-vms'))), {self.VM})
        self.assertIn('rm -rf -- ' + GUEST_W, lines(os.path.join(self.d, 'calls')))   # the cleanup ran

    def test_gate_red(self):
        scenario(self.d, 'gate', out='FAIL census: AAA Certificate Services (SHA-1 X): no deny in the admin trust settings (none)\n', rc=1)
        r, out = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(out[-1], 'golden-emudhra: GATE RED')
        self.assertIn('golden-emudhra: FAIL census: AAA Certificate Services (SHA-1 X): no deny in the admin trust settings (none)', out)
        self.assertIn('golden-emudhra: FAIL the gate found a FAIL (above)', out)
        self.assertEqual(self.steps(), ['save', 'gate'])

    def test_a_save_that_did_not_complete_is_red(self):
        scenario(self.d, 'save', out='STOP missing in the guest: /opt/homebrew/bin/node\n', rc=2)
        r, out = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(out[-1], 'golden-emudhra: GATE RED')
        self.assertEqual(self.steps(), ['save'])   # the gate did not run on an incomplete save

    def test_a_gate_step_that_did_not_complete_is_red(self):
        scenario(self.d, 'gate', out='STOP missing in the guest: /opt/homebrew/bin/gtimeout\n', rc=2)
        r, out = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(out[-1], 'golden-emudhra: GATE RED')

    def test_the_vm_must_be_an_s1_clone(self):
        for bad in ('gold-20261101', 'runner-x', 'n1-x', 's1-', 's1-a b', '-s1-x'):
            r, out = self.gate('--gate', bad)
            self.assertEqual(r.returncode, 1, bad)
            self.assertTrue(out and out[-1].startswith('golden-emudhra: STOP'), bad + r.stdout)
            self.assertFalse(os.path.exists(os.path.join(self.d, 'exec-vms')), bad)   # no tart call
        r, out = self.gate('--gate', self.VM, 'extra')
        self.assertTrue(out[-1].startswith('golden-emudhra: STOP usage'), r.stdout)
        r, out = self.gate('--gate', 's1-x')   # control
        self.assertEqual(r.returncode, 0, r.stdout)


class GuestGate(unittest.TestCase):
    """The guest step `gate`: census_deny alone on a saved image. Exit 1 on any FAIL, else 0; it never writes a deny."""

    SHA1 = 'D1EB23A46D17D68FD92564C2F1F1601764D8E349'
    CONTROLS = ('e793c9b02fd8aa13e21c31228accb08119643b749c898964b1746d46c3d4cbd2',
                '4ff460d54b9c86dabfbcfc5712e0400d2bed3fbc4d4fbdaa86e06adcd2a9ad7a',
                '96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6')

    def setUp(self):
        import plistlib
        self.d = tmpdir(self)
        gt = stub(os.path.join(self.d, 'stub', 'gtimeout'), 'shift 3\nexec "$@"\n')
        self.sec = os.path.join(self.d, 'sec')
        os.makedirs(self.sec)
        sec = stub(os.path.join(self.d, 'stub', 'security'), r"""S=%s
print -r -- "$*" >> $S/calls
case $1 in
  (trust-settings-export)
    [[ -f $S/ts.plist ]] || { print -r -- "SecTrustSettingsCreateExternalRepresentation: No Trust Settings were found."; exit 1 }
    /bin/cp $S/ts.plist $3; exit 0 ;;
  (verify-cert)
    rc=1; [[ -f $S/rc.${3:t} ]] && rc=$(<$S/rc.${3:t})
    print -r -- "...certificate verification $rc"; exit $rc ;;
  (*) print -r -- "stub security: unexpected $1" >> $S/unexpected; exit 1 ;;
esac
""" % self.sec)
        self.guest, self.w = guest_copy(self, self.d, [
            ('T=/opt/homebrew/bin/gtimeout', 'T=' + gt), ('SEC=/usr/bin/security', 'SEC=' + sec)])
        excl = write(os.path.join(self.w, 'excl', 'x.pem'), 'PEM\n')
        write(os.path.join(self.w, 'excluded.tsv'),
              '%s\t%s\t%s\tAAA Certificate Services\tkc\t%s\n' % (self.SHA1, 'a' * 64, 'b' * 64, excl))
        ctl = ''
        for h in self.CONTROLS:
            ctl += '%s\tcontrol %s\t%s\n' % (h, h[:6], write(os.path.join(self.w, 'ctl', h + '.pem'), 'PEM\n'))
            write(os.path.join(self.sec, 'rc.%s.pem' % h), '0\n')   # a control root stays trusted
        write(os.path.join(self.w, 'controls.tsv'), ctl)
        write(os.path.join(self.w, 'fail.txt'), '')
        with open(os.path.join(self.sec, 'ts.plist'), 'wb') as f:   # the admin trust settings: a deny (result 3)
            plistlib.dump({'trustList': {self.SHA1: {'trustSettings': [{'kSecTrustSettingsResult': 3}]}}}, f)

    def gate(self):
        r = run([ZSH, '-f', self.guest, 'gate', self.w], cwd=self.d)
        self.assertFalse(os.path.exists(os.path.join(self.sec, 'unexpected')), 'the gate called security for more than reading')
        return r, r.stdout.splitlines()

    def test_deny_present_and_controls_trusted_pass(self):
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertFalse([l for l in out if l.startswith('FAIL')], r.stdout)

    def test_no_deny_fails(self):
        os.remove(os.path.join(self.sec, 'ts.plist'))
        r, out = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(any(l.startswith('FAIL census: AAA Certificate Services') and 'no deny' in l for l in out), r.stdout)

    def test_an_excluded_anchor_still_trusted_fails(self):
        write(os.path.join(self.sec, 'rc.x.pem'), '0\n')
        r, out = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(any('verify-cert exits 0: Apple still trusts it' in l for l in out), r.stdout)

    def test_a_control_root_not_trusted_fails(self):
        write(os.path.join(self.sec, 'rc.%s.pem' % self.CONTROLS[2]), '1\n')
        r, out = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(any('a control root must stay trusted' in l for l in out), r.stdout)

    def test_no_records_from_save_fails(self):
        os.remove(os.path.join(self.w, 'excluded.tsv'))
        r, out = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_a_fail_left_by_an_earlier_step_does_not_count(self):
        write(os.path.join(self.w, 'fail.txt'), 'an earlier FAIL\n')
        r, out = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == '__main__':
    unittest.main()
