"""W4's status lines of their own (the W4 plan's X-7 and FINAL FOLD Y-4), RS_USER's `runner-updater status`, each a line
of its own right after the latest pass's line, never the outcome, with NO state member:
- THE NOTICE: RS_USER's pass, when it is ON, reads the newest published release of this repository (runner-release.sh's
  rr_self_newest: anonymous, rr_curl's -q; the newest by THE RELEASE ORDER, rr_tag_cmp: rc.10 after rc.3, a draft no
  release) and keeps the tag in its last-pass record (line 3; line 2 the recipe line or empty, so an older status reads
  it unchanged). status names it only when it is newer than RS_USER's ~/build/.release: `release <tag> is published
  (this host runs <tag>)`, never an instruction to run it (Y-4). A failed read is the line `the newest release could
  not be read: <why>`, never a STOP, and the pass's exit code stays its own. A pass while OFF reads nothing.
- THE TWO USERS' RELEASES (Y-4, direction-neutral): RUN_USER's and RS_USER's ~/build/.release differ -> one line that
  names both identities and both ways (to finish going back, to go forward); the same tag with two sha256 -> `--same` as
  both users, RUN_USER first; one with no record (a tree installed by hand) -> its way forward and the way back's
  fallback. The control: the same tag and sha256, or neither has a record -> no line.
Every cell runs the real updater (support.Pool, a throwaway container, the fake clock).
(Named for its CI part, test_re[!nt][!o]*.py: .github/workflows/release-check.yml.)
"""
import json
import os
import secrets
import shutil
import unittest

from tests.hetzner.support import SELF_RELEASES, needs_container
from tests.hetzner.test_release_due import STATE, Due

A, B = 'a' * 64, 'b' * 64
SELF_PATHS = [SELF_RELEASES]
MEMBERS = {'format', 'on', 'families', 'core', 'restart', 'last_window'}   # RS_USER's state's own (the updater's CHECK)


def record(path, tag, sha):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write('tag %s\nsha256 %s\n' % (tag, sha))


def published(g, *rows, status=200):
    """GitHub's answer for this repository's releases: rows (tag, draft)."""
    body = json.dumps([{'tag_name': t, 'draft': d, 'prerelease': '-rc.' in t} for t, d in rows]).encode()
    g.p.gh.routes[SELF_RELEASES] = (status, {'Content-Type': 'application/json'}, body)


def status(g):
    r = g.p.updater('status')
    g.t.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
    return r.stdout.splitlines()


def release_lines(lines):
    return [l for l in lines if l.startswith('runner-updater: release') or 'newest release could not' in l]


@needs_container
class TheNotice(unittest.TestCase):
    def test_a_newer_published_release_is_named_and_controls_the_same_and_an_older_one(self):
        """The newest of rc.3, rc.10 and a draft v0.4.0 is rc.10 (MUTANT: the tags compared as text -> rc.3; a draft
        read as a release -> v0.4.0: red). It is named when ~/build runs v0.2.0, right after the last pass's line;
        not when ~/build runs it, nor when ~/build runs a newer one. No state member is written."""
        for own, want in (('v0.2.0', ['runner-updater: release v0.3.0-rc.10 is published (this host runs v0.2.0)']),
                          ('v0.3.0-rc.10', []), ('v0.3.0', [])):
            with self.subTest(own=own):
                g = Due(self)
                record(os.path.join(g.p.build, '.release'), own, A)
                published(g, ('v0.3.0-rc.3', False), ('v0.3.0-rc.10', False), ('v0.4.0', True), ('junk', False))
                g.run()
                self.assertEqual(g.p.gh.seen_self, SELF_PATHS)
                lines = status(g)
                self.assertEqual(release_lines(lines), want, lines)
                if want:
                    i = lines.index(want[0])
                    self.assertTrue(lines[i - 1].startswith('runner-updater: last pass'), lines)
                st = json.loads(g.p.read(STATE))
                self.assertLessEqual(set(st), MEMBERS, 'a state member was added')
                self.assertNotIn('release', json.dumps(st.get('families', {})), 'a family member was added')

    def test_with_no_release_record_the_newest_release_is_named(self):
        g = Due(self)
        published(g, ('v0.3.0', False))
        g.run()
        self.assertEqual(release_lines(status(g)),
                         ['runner-updater: release v0.3.0 is published (this host runs a release with no '
                          '~/build/.release: installed by hand)'])

    def test_a_failed_read_is_one_line_never_a_stop_and_the_pass_s_exit_code_stays(self):
        """A 500, and an answer that is not JSON: the pass exits 0 as before (Due.run), no STOP names it, and status's
        one line says why. MUTANT: the read's failure as the pass's REFUSE -> exit 1 (red)."""
        for why, st, body, said in (('500', 500, b'{}', 'GitHub answered 500'),
                                    ('not json', 200, b'<html>', 'the answer is not a JSON list of releases')):
            with self.subTest(why):
                g = Due(self)
                g.p.gh.routes[SELF_RELEASES] = (st, {'Content-Type': 'application/json'}, body)
                g.run()
                self.assertEqual(release_lines(status(g)),
                                 ['runner-updater: the newest release could not be read: %s' % said])
                self.assertNotIn('release', json.dumps(json.loads(g.p.read(STATE)).get('families', {})))

    def test_a_pass_while_off_reads_nothing(self):
        """D11: OFF asks GitHub nothing. The control: the same rig ON reads it once."""
        g = Due(self)
        st = json.loads(g.p.read(STATE))
        st['on'] = False
        g.put(st)
        r = g.p.updater('pass')
        self.assertIn('the updater is OFF', r.stdout)
        self.assertEqual(g.p.gh.seen_self, [])
        st['on'] = True
        g.put(st)
        g.run()
        self.assertEqual(g.p.gh.seen_self, SELF_PATHS)

    def test_the_read_is_anonymous_also_with_a_curlrc(self):
        """Y-9: RS_USER's ~/.curlrc holds an Authorization header; the read sends none (rr_curl's -q)."""
        g = Due(self)
        g.p.write(os.path.join(g.p.HOME, '.curlrc'), 'header = "Authorization: token planted-by-the-cell"\n', 0o600)
        g.run()
        got = [h for p, h in g.p.gh.headers if p == SELF_RELEASES]
        self.assertEqual(len(got), 1, g.p.gh.headers)
        self.assertNotIn('authorization', got[0])


@needs_container
class TheTwoUsers(unittest.TestCase):
    """RS_USER's status reads RUN_USER's ~/build/.release (rr_read: RUN_USER's file). RUN_USER here is a name of its
    own whose /home holds that record (the status reads no more of it than its state, absent: OFF)."""

    def rig(self, own, run):
        g = Due(self)
        self.run_user = 'w4n' + secrets.token_hex(3)
        p = g.p.path('host.conf')
        conf = g.p.read(p)
        self.assertEqual(conf.count('\nRUN_USER=root\n'), 1)
        g.p.write(p, conf.replace('\nRUN_USER=root\n', '\nRUN_USER=%s\n' % self.run_user), 0o644)
        home = '/home/' + self.run_user
        os.makedirs(os.path.join(home, 'build'))
        self.addCleanup(shutil.rmtree, home, True)
        if own:
            record(os.path.join(g.p.build, '.release'), *own)
        if run:
            record(os.path.join(home, 'build', '.release'), *run)
        return g

    def test_two_releases_name_both_ways(self):
        """Y-4: both directions named, whichever user is ahead (a way back cut between the users, and a way forward).
        MUTANT: one direction only (the newer as the one behind) -> red."""
        for own, run in ((('v0.2.0', A), ('v0.3.0', B)), (('v0.3.0', B), ('v0.2.0', A))):
            with self.subTest(rs=own[0], run=run[0]):
                g = self.rig(own, run)
                u = self.run_user
                older, newer = sorted((own, run))
                on_newer, on_older = (u, 'root') if run == newer else ('root', u)
                self.assertEqual(release_lines(status(g)), [
                    'runner-updater: release: %s runs %s/%s, root runs %s/%s: to finish going back, run %s\'s line with '
                    '--older as %s; to go forward, run %s\'s line as %s' % (
                        u, run[0], run[1][:12], own[0], own[1][:12], older[0], on_newer, newer[0], on_older)])

    def test_the_same_tag_with_two_sha256(self):
        g = self.rig(('v0.3.0', A), ('v0.3.0', B))
        self.assertEqual(release_lines(status(g)), [
            'runner-updater: release: %s and root run the same tag v0.3.0 with two different sha256 (%s, %s): run the '
            'line of v0.3.0 with --same as both users, %s first' % (self.run_user, B[:12], A[:12], self.run_user)])

    def test_one_user_with_no_record(self):
        g = self.rig(None, ('v0.3.0', B))
        self.assertEqual(release_lines(status(g)), [
            'runner-updater: release: %s runs v0.3.0/%s, root runs a release with no ~/build/.release (installed by '
            'hand): to go forward, run v0.3.0\'s line as root; to finish going back to a release with no '
            'linux-install-line.txt, its way back by hand as %s (README "A release of this repository, by its install '
            'line")' % (self.run_user, B[:12], self.run_user)])

    def test_controls_the_same_release_or_no_record_at_all_name_nothing(self):
        for own, run in ((('v0.3.0', A), ('v0.3.0', A)), (None, None)):
            with self.subTest(own=own, run=run):
                g = self.rig(own, run)
                self.assertEqual(release_lines(status(g)), [])


if __name__ == '__main__':
    unittest.main()
