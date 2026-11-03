"""bin/runner-updater's STATE slice: its own PATH, the config keys that would blind the log pass, the updater's state
(STATEDIR/state.json), `status`, `on` and `off`, the protected-list writer and `protect`, and the timer's `pass`.

The rig is test_runner_updater's (every path constant rewritten into a sandbox; stubs for ps and curl; the real core).
"""
import json
import os
import unittest

from tests.studio.test_runner_updater import Rig, config

SYSTEM = '/usr/bin:/bin:/usr/sbin:/sbin'


def lines_of(path):
    with open(path) as f:
        return f.read().splitlines()


class TestOwnPath(unittest.TestCase):
    """runner-updater sets its own PATH at the top: the weekly watchdog runs it over a non-interactive ssh with a PATH
    of its own, so nothing may depend on the caller's. The ps stub logs the PATH it is run with."""

    def test_report_works_with_a_path_that_holds_nothing(self):
        r = Rig(self)
        r.report(env={'PATH': '/nonexistent'})
        self.assertEqual(set(lines_of(os.path.join(r.psd, 'path'))), {r.sb.stubs + ':' + SYSTEM})

    def test_control_a_copy_that_sets_no_path_shows_the_callers(self):
        r = Rig(self)
        own = 'export PATH=%s:%s' % (r.sb.stubs, SYSTEM)
        script = r.copy('runner-updater-nopath', [(own, ': ' + own)])
        r.cmd('report', script=script, env={'PATH': '/nonexistent'})
        self.assertEqual(set(lines_of(os.path.join(r.psd, 'path'))), {'/nonexistent'})


if __name__ == '__main__':
    unittest.main()
