"""golden-prune and the updater's protected list: no state folder = today's output; a folder without the list, a
list that is not a readable regular file, or a line that is not an image name = REFUSE; a protected name is never
printed. Each REFUSE has a control with a valid list.
"""
import os
import unittest

from tests.studio.support import Sandbox

SCRIPT = 'bin/golden-prune'
G = 'liveapp-mac-golden-'
CONFIGURED = G + '20261020'
NAMES = [G + '20261001', G + '20261010', G + '20261015', CONFIGURED, G + '20261025', 'runner-0123abcd']
TODAY = ''.join(G + d + '\n' for d in ('20261001', '20261010', '20261015'))   # all but configured and the newest other


class Rig:
    def __init__(self, test, cat_body=None, deep=False):
        """deep: STATEDIR is two folders below the sandbox (ci/state/runner-updater), so its parent can be closed"""
        sb = self.sb = Sandbox(test)
        self.state = sb.path('ci', 'state', 'runner-updater') if deep else sb.path('state')
        self.protected = os.path.join(self.state, 'protected')
        rewrites = [('STATEDIR=/Users/ci/.local/state/runner-updater', 'STATEDIR=' + self.state)]
        if cat_body is not None:   # a cat that reads the list as the test says
            rewrites.append(('/bin/cat -- $PROTECTED', sb.stub('cat', cat_body, folder=sb.mkdir('fake')) + ' -- $PROTECTED'))
        self.script = sb.copy_script(SCRIPT, rewrites)

    def updater(self, text=None, mode=0o600):
        os.makedirs(self.state, mode=0o700, exist_ok=True)
        if text is not None:
            self.sb.write(self.protected, text, mode)

    def run(self, *args):
        return self.sb.run(['/bin/zsh', '-f', self.script] + list(args or [CONFIGURED] + NAMES))


class TestProtected(unittest.TestCase):
    def assert_refused(self, res):
        self.assertEqual((res.returncode, res.stdout), (1, ''))
        self.assertTrue(res.stderr.startswith('golden-prune: REFUSE '), res.stderr)

    def test_no_state_folder_is_todays_output(self):
        r = Rig(self)
        res = r.run()
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, TODAY, ''))
        res = r.run(CONFIGURED, CONFIGURED, G + '20261001')   # one other generation: nothing to print
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, '', ''))

    def test_folder_without_the_list_is_refused(self):
        r = Rig(self)
        r.updater()
        self.assert_refused(r.run())

    def test_unreadable_list_is_refused(self):
        r = Rig(self)
        r.updater(G + '20261001\n', mode=0)
        self.assert_refused(r.run())
        os.chmod(r.protected, 0o600)   # the control: the same list, readable
        res = r.run()
        self.assertEqual((res.returncode, res.stdout), (0, TODAY.replace(G + '20261001\n', '')))

    def test_list_that_is_not_a_regular_file_is_refused(self):
        for label in ('a directory', 'a symlink'):
            with self.subTest(label):
                r = Rig(self)
                r.updater()
                if label == 'a directory':
                    os.mkdir(r.protected)
                else:
                    os.symlink(r.sb.write(r.sb.path('elsewhere'), G + '20261001\n'), r.protected)
                self.assert_refused(r.run())

    def test_bad_line_is_refused(self):
        for line in ('../x', 'a b', '', '-x', '.x', 'x/y', 'x\ty', 'café', 'x\0y', ' x'):
            with self.subTest(line=line):
                r = Rig(self)
                r.updater(G + '20261001\n' + line + '\n')
                self.assert_refused(r.run())

    def test_read_failure_is_refused(self):
        # cat prints the list's first line, then fails: a part of the list must never pass as the list
        r = Rig(self, cat_body='/usr/bin/head -1 $2; exit 1')
        r.updater(G + '20261001\n' + G + '20261010\n')
        self.assert_refused(r.run())
        r = Rig(self, cat_body='/usr/bin/head -1 $2; exit 0')   # the control: the same read, no failure
        r.updater(G + '20261001\n' + G + '20261010\n')
        res = r.run()
        self.assertEqual((res.returncode, res.stdout), (0, TODAY.replace(G + '20261001\n', '')))

    def test_control_valid_list(self):
        r = Rig(self)
        r.updater(G + '20261001\nrunner-0123abcd\nsome.other_image-1\n')
        res = r.run()
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, TODAY.replace(G + '20261001\n', ''), ''))

    def test_empty_list_protects_nothing(self):
        r = Rig(self)
        r.updater('')
        res = r.run()
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, TODAY, ''))

    def test_protected_name_is_never_printed(self):
        r = Rig(self)
        r.updater(G + '20261010\n' + G + '20261015')   # no final newline
        res = r.run()
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, G + '20261001\n', ''))
        r.updater(G + '20261001\n' + G + '20261010\n' + G + '20261015\n')   # all of today's list: nothing printed
        res = r.run()
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, '', ''))


class TestClosedFolders(unittest.TestCase):
    """A folder on the path to the protected list that exists but cannot be searched hides the list: a stat behind it
    fails as if nothing were there, so golden-prune would read "no updater" and protect nothing. Every such folder is a
    REFUSE (the rule of bin/runner-updater-lib's ru_reach). The control: the same folders at 0700."""

    def test_a_folder_it_cannot_search_on_the_path_to_the_list_is_refused(self):
        for level in ('the parent of STATEDIR', 'STATEDIR'):
            for mode in (0o000, 0o600):
                with self.subTest(level=level, mode=oct(mode)):
                    r = Rig(self, deep=True)
                    r.updater(G + '20261001\n')
                    d = r.state if level == 'STATEDIR' else os.path.dirname(r.state)
                    os.chmod(d, mode)
                    try:
                        res = r.run()
                    finally:
                        os.chmod(d, 0o700)
                    self.assertEqual((res.returncode, res.stdout, res.stderr), (1, '', (
                        "golden-prune: REFUSE %s cannot be searched: the updater's protected list %s would look absent "
                        "behind it\n") % (d, r.protected)))

    def test_control_the_same_folders_at_0700(self):
        r = Rig(self, deep=True)
        r.updater(G + '20261001\n')
        os.chmod(os.path.dirname(r.state), 0o700)
        res = r.run()
        self.assertEqual((res.returncode, res.stdout, res.stderr), (0, TODAY.replace(G + '20261001\n', ''), ''))


if __name__ == '__main__':
    unittest.main()
