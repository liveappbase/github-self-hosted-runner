"""Where the cells of tests/hetzner run (support.py's verdict and its class decorator):
- 'run' as root on Linux in a container (/.dockerenv): the throwaway container of support.RUN_LINE, and the ubuntu
  rows of .github/workflows/release-check.yml;
- 'skip' where they cannot run: not Linux, or not root;
- 'fail' on Linux as root with no /.dockerenv. They could run there, but it may be a real host, so they neither run
  nor pass as skipped: a CI row whose container ever lacked the mark goes red, never green with every cell skipped.
Pure; runs anywhere.
"""
import unittest

from tests.hetzner.support import contained, verdict


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


if __name__ == '__main__':
    unittest.main()
