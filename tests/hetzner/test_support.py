"""Where the cells of tests/hetzner run (support.py's verdict and its class decorator):
- 'run' as root on Linux in a container (/.dockerenv): the throwaway container of support.RUN_LINE, and the ubuntu
  rows of .github/workflows/release-check.yml;
- 'skip' where they cannot run: not Linux, or not root;
- 'fail' on Linux as root with no /.dockerenv. They could run there, but it may be a real host, so they neither run
  nor pass as skipped: a CI row whose container ever lacked the mark goes red, never green with every cell skipped.
Pure; runs anywhere. So does Tools: a container that lacks a tool the cells need (jq among them: the unattended switch
asks core/idle.jq) fails each cell by name. And (Copies, in a container): the copies a cell runs are the real scripts
with only their pin lines rewritten (HOST_CONF, RR_API/RR_DL/RR_SRC, 03's TGZ_SHA and BIN_SHA, pool-image.sh's PINS):
Sandbox.pin_lines_only finds any other difference, and a planted one is found.
"""
import os
import re
import time
import unittest
from unittest import mock

from tests.hetzner import support
from tests.hetzner.support import Pool, Sandbox, contained, digest, needs_container, verdict


class Verdict(unittest.TestCase):
    def test_each_case(self):
        cases = {('linux', 0, True): 'run', ('linux', 0, False): 'fail', ('linux', 1000, True): 'skip',
                 ('linux', 1000, False): 'skip', ('darwin', 0, True): 'skip', ('darwin', 501, False): 'skip'}
        for (platform, euid, mark), want in cases.items():
            with self.subTest(platform=platform, euid=euid, dockerenv=mark):
                self.assertEqual(verdict(platform, euid, mark), want)

    def test_the_decorator_runs_skips_or_fails_each_cell(self):
        for v, want in (('run', (1, 0, 0)), ('skip', (1, 0, 1)), ('fail', (1, 1, 0))):
            with self.subTest(verdict=v):
                @contained(v)
                class Cell(unittest.TestCase):
                    def test_x(self):
                        pass
                res = unittest.TestResult()
                unittest.defaultTestLoader.loadTestsFromTestCase(Cell).run(res)
                self.assertEqual((res.testsRun, len(res.failures) + len(res.errors), len(res.skipped)), want)


class Tools(unittest.TestCase):
    def test_a_container_without_jq_fails_each_cell_by_name(self):
        """Opus r1 F6: the unattended cells run core/idle.jq under /usr/bin/jq, so require_tools names it when it is not
        there, and RUN_LINE's image has it. The control: every tool there, no failure. Pure; runs anywhere."""
        self.assertRegex(support.RUN_LINE.split('IMAGE:', 1)[1], r'\bjq\b')
        for missing in ('/usr/bin/jq', '/usr/bin/sha256sum', None):
            with self.subTest(missing=missing):
                fails = []

                class Cell:
                    def fail(self, msg):
                        fails.append(msg)
                with mock.patch.object(support.os.path, 'exists', lambda p: p != missing):
                    support.require_tools(Cell())
                if missing is None:
                    self.assertEqual(fails, [])
                else:
                    self.assertEqual(len(fails), 1, fails)
                    self.assertIn('lacks %s' % missing, fails[0])
                    self.assertTrue(re.search(r'\bjq\b', fails[0]), 'the message names the image to use (RUN_LINE)')


@needs_container
class Copies(unittest.TestCase):
    def test_the_copies_differ_from_the_scripts_only_in_their_pin_lines(self):
        for rig in (Sandbox, Pool):
            with self.subTest(rig.__name__):
                sb = rig(self)
                self.assertEqual(sb.pin_lines_only(), [])
                p = os.path.join(sb.build, 'setup', '03-runscaler.sh')
                with open(p) as f:
                    text = f.read()
                self.assertEqual(text.count('\nset -euo pipefail\n'), 1)
                with open(p, 'w') as f:                      # a planted change in another line
                    f.write(text.replace('\nset -euo pipefail\n', '\nset -uo pipefail\n'))
                n = text.split('\n').index('set -euo pipefail') + 1
                self.assertEqual([x[:2] for x in sb.pin_lines_only()], [('setup/03-runscaler.sh', n)])


@needs_container
class PoolProduction(unittest.TestCase):
    def test_the_unit_starts_after_the_install_and_never_in_the_future(self):
        """Pool.production's runscaler start is a time that has come: after config.toml's second (pool-image.sh's
        started_after, whole seconds) and not after now. A start stamped in the future read a later install (the up's,
        within that second) as "already running it": no restart (seen once on ubuntu:24.04, where 03 real takes 1 s)."""
        p = Pool(self)
        p.production(digest(1))
        start, now = p.unit_now()['start'], time.time()
        self.assertGreater(start, int(os.stat(p.rpath('config.toml')).st_mtime))
        self.assertLessEqual(start, now)


if __name__ == '__main__':
    unittest.main()
