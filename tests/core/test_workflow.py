"""The CI legs of core/TESTED_JQ: .github/workflows/release-check.yml's jq-linux matrix is exactly TESTED_JQ's ci rows
(version, image, areas), its job name is the one tools/release-check reads on a tag ("jq VERSION (IMAGE)"), each leg
checks that the image's jq prints the row's version, and the hosted macOS job runs the tests with /usr/bin/jq (the
local row), all of tests/ through tools/run-tests. tests/hetzner (linux-docker/'s scripts: no jq, so not a TESTED_JQ
area) runs in the hetzner job, in the images of the ubuntu rows and only those, split into parts by module name: the
parts run every module of tests/hetzner exactly once, in a container (its cells fail rather than skip without one),
and its setup step installs what those cells need. Every jq-linux leg waits for that job and fails unless all of it
passed (the CI's own view; a tag's tools/release-check --build reads every check run of the commit). The jobs hetzner
and jq-linux keep a CLOSED shape (shape()): no continue-on-error, no step `if`, closed key sets, a hetzner matrix of
image and part only, jq-linux's `if` exactly `${{ !cancelled() }}`: an edit that could let a leg or a row pass while
cells failed or never ran is a test edit too. The stdlib has no YAML parser: the rows are read as text, and shape()
reads the workflow with read(), a reader of the block YAML it is written in that refuses any other spelling."""
import os
import re
import unittest

from tests.core.corejq import REPO, tested_rows

WF = os.path.join(REPO, '.github', 'workflows', 'release-check.yml')


def workflow():
    with open(WF) as f:
        return f.read()


def job(name):
    """The text of one job of the workflow: from its `  NAME:` line to the next job's (or the end)."""
    m = re.search(r'^  %s:\n(.*?)(?=^  \S|\Z)' % re.escape(name), workflow(), re.M | re.S)
    return m.group(1) if m else ''


def matrix():
    return re.findall(r'^\s+- \{jq: (\S+), image: "([^"]+)", areas: "([a-z ]+)"\}$', job('jq-linux'), re.M)


def hetzner_matrix(key):
    """The hetzner job's matrix list KEY (image or part): its quoted items, in order."""
    m = re.search(r'^        %s: \[(.*)\]$' % key, job('hetzner'), re.M)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def flat(s):
    if isinstance(s, unittest.TestSuite):
        for t in s:
            yield from flat(t)
    else:
        yield s


def modules(pattern):
    """The modules of tests/hetzner that unittest's discovery loads for PATTERN (-p), as the hetzner job runs it."""
    suite = unittest.TestLoader().discover(os.path.join(REPO, 'tests', 'hetzner'), pattern=pattern, top_level_dir=REPO)
    return sorted(set(type(t).__module__ for t in flat(suite)))


def split(parts):
    """[] when the parts run every module the plain line runs (unittest's default pattern) exactly once, else what
    is wrong: a module no part runs, one that two parts run, a part that runs none."""
    every, seen, why = modules('test*.py'), {}, []
    for p in parts:
        got = modules(p)
        if not got:
            why.append('the part %s runs no module' % p)
        for m in got:
            seen.setdefault(m, []).append(p)
    why += ['%s: no part runs it' % m for m in every if m not in seen]
    why += ['%s: run by %s' % (m, ' and '.join(ps)) for m, ps in sorted(seen.items()) if len(ps) > 1]
    why += ['%s: a part runs it, the plain line does not' % m for m in sorted(seen) if m not in every]
    return why


class Unreadable(Exception):
    """A line of the workflow that read() does not know: a shape these cells cannot check is a failure, never a pass."""


KEY = re.compile(r'([A-Za-z][A-Za-z0-9_-]*):(?: +(.*))?$')     # no quoted key, no merge key, no tab
BLOCK = ('|', '|-', '|+', '>', '>-', '>+')                          # no indent digit


def tokens(text):
    """The workflow's lines as [number, indent, key, value]: key '-' for a list item (its content follows as a token
    two columns deeper), None for a list item's scalar. Blank and comment lines are dropped; a block scalar (`run: |`)
    is folded into its value, so a `#` or a `key:` inside a script is never read as YAML."""
    out, src, i = [], text.split('\n'), 0
    while i < len(src):
        n, line = i + 1, src[i]
        i += 1
        body = line.lstrip(' ')
        if not body.strip() or body.startswith('#'):
            continue
        ind, dash = len(line) - len(body), body.startswith('- ')
        if dash:
            out.append([n, ind, '-', None])
            ind, body = ind + 2, body[2:]
        m = KEY.match(body)
        if m:
            key, value = m.group(1), (m.group(2) or '').rstrip() or None
        elif dash:
            key, value = None, body.rstrip()
        else:
            raise Unreadable('line %d: not KEY: VALUE, - ITEM or a comment' % n)
        if value and value[0] in '&*!':
            raise Unreadable('line %d: an anchor, an alias or a tag' % n)
        if value and value[0] in '|>':
            if value not in BLOCK:
                raise Unreadable('line %d: a block scalar header this reader does not know' % n)
            lines, deep = [], None
            while i < len(src):
                s = src[i]
                if s.strip():
                    d = len(s) - len(s.lstrip(' '))
                    if d < (ind + 1 if deep is None else deep):
                        break
                    deep = d if deep is None else deep
                lines.append(s[deep:] if deep is not None else '')
                i += 1
            value = '\n'.join(lines)
        out.append([n, ind, key, value])
    return out


def read(text):
    """The workflow as dicts, lists and strings, for the block YAML it is written in and nothing more. A flow
    collection ([…], {…}) and a scalar stay their text, so a job, a step or a matrix in flow form is a string where
    shape() wants a dict; a quoted key, a merge or `?` key, an anchor, an alias, a tag, a key twice, a tab or a second
    document, a plain value over two lines and a list at its key's indent raise Unreadable."""
    toks = tokens(text)

    def node(p, ind):
        if toks[p][2] != '-':
            return mapping(p, ind)
        got = []
        while p < len(toks) and toks[p][1] == ind and toks[p][2] == '-':
            if toks[p + 1][2] is None:
                got.append(toks[p + 1][3])
                p += 2
            else:
                v, p = mapping(p + 1, ind + 2)
                got.append(v)
        return got, p

    def mapping(p, ind):
        got = {}
        while p < len(toks) and toks[p][1] >= ind:
            n, i, key, value = toks[p]
            if i > ind or key == '-' or key in got:
                raise Unreadable('line %d: not a new key of the mapping at column %d' % (n, ind + 1))
            p += 1
            if value is None and p < len(toks) and toks[p][1] > ind:
                got[key], p = node(p, toks[p][1])
            else:
                got[key] = value
        return got, p

    return mapping(0, 0)[0]     # it reads every line, or raises


TOP = {'name', 'on', 'permissions', 'jobs'}     # a defaults: or env: here would reach every job
JOBS = {     # the closed shape of the two jobs a tag's CI rests on: the keys each has, no other
    'hetzner': {'name', 'runs-on', 'timeout-minutes', 'container', 'strategy', 'steps'},
    'jq-linux': {'name', 'runs-on', 'needs', 'if', 'timeout-minutes', 'container', 'strategy', 'steps'},
}
MATRIX = {'hetzner': {'image', 'part'}, 'jq-linux': {'include'}}
STEP = {'name', 'run', 'working-directory', 'env'}


def anywhere(node):
    """every key and every string at any depth of node"""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from anywhere(v)
    elif isinstance(node, list):
        for v in node:
            yield from anywhere(v)
    elif isinstance(node, str):
        yield node


def shape(text):
    """[] when the jobs hetzner and jq-linux keep their closed shape, else what is wrong: no continue-on-error
    anywhere in either; no step with an `if`; each key set closed (the workflow's, each job's, each step's); the
    hetzner matrix exactly image and part, jq-linux's exactly include; jq-linux's job `if` exactly
    `${{ !cancelled() }}` (it runs after a failed hetzner job, and then fails on its last step)."""
    try:
        w = read(text)
    except Unreadable as e:
        return ['the workflow is not in the block shape these cells read, so they cannot read it: %s' % e]
    why = []
    if not isinstance(w, dict) or set(w) != TOP:
        why.append('the workflow keys %s, want exactly %s' % (sorted(w) if isinstance(w, dict) else w, sorted(TOP)))
    jobs = w.get('jobs') if isinstance(w, dict) else None
    for name, keys in sorted(JOBS.items()):
        j = jobs.get(name) if isinstance(jobs, dict) else None
        if not isinstance(j, dict):
            why.append('no job %s in block form' % name)
            continue
        if [x for x in anywhere(j) if 'continue-on-error' in x]:
            why.append('job %s: a continue-on-error' % name)
        if set(j) != keys:
            why.append('job %s: keys %s, want exactly %s' % (name, sorted(j), sorted(keys)))
        s = j.get('strategy')
        m = s.get('matrix') if isinstance(s, dict) else None
        if not isinstance(m, dict) or set(m) != MATRIX[name]:
            why.append('job %s: matrix keys %s, want exactly %s' % (name, sorted(m) if isinstance(m, dict) else m,
                                                                     sorted(MATRIX[name])))
        steps = j.get('steps')
        for i, st in enumerate(steps if isinstance(steps, list) else [steps], 1):
            if not isinstance(st, dict):
                why.append('job %s step %d: not a block mapping: %r' % (name, i, st))
                continue
            if 'if' in st:
                why.append('job %s step %d: a step if' % (name, i))
            if not set(st) <= STEP:
                why.append('job %s step %d: keys %s, want only %s' % (name, i, sorted(st), sorted(STEP)))
    jq = jobs.get('jq-linux') if isinstance(jobs, dict) else None
    if isinstance(jq, dict) and jq.get('if') != '${{ !cancelled() }}':
        why.append("job jq-linux's if is %r, want exactly '${{ !cancelled() }}'" % jq.get('if'))
    return why


LAST = '        run: test "${{ needs.hetzner.result }}" = success\n'    # the jq rows' last step
GATE = ("      - name: every hetzner job of this commit passed (a tag's release-check reads this job's result, "
        "not theirs)\n" + LAST)
CELLS = "        run: python3 -I -m unittest discover -s tests/hetzner -t . -p '${{ matrix.part }}' -v\n"
HNAME = '    name: hetzner ${{ matrix.part }} (${{ matrix.image }})\n'
HMATRIX = '      matrix:\n        image: ['
EDITS = [   # (what, the text, its replacement, the rule that refuses it)
    ('continue-on-error on the jq rows\' last step', LAST, '        continue-on-error: true\n' + LAST,
     'a continue-on-error'),
    ('an if on that step: skipped when hetzner failed', LAST,
     "        if: ${{ needs.hetzner.result == 'success' }}\n" + LAST, 'a step if'),
    ('continue-on-error on the hetzner cells step', CELLS, '        continue-on-error: true\n' + CELLS,
     'a continue-on-error'),
    ('an if on that step: 24.04 runs no cell', CELLS, "        if: matrix.image != 'ubuntu:24.04'\n" + CELLS,
     'a step if'),
    ('continue-on-error on the hetzner job', HNAME, HNAME + '    continue-on-error: true\n', 'a continue-on-error'),
    ('a default shell for the hetzner job', HNAME, HNAME + '    defaults:\n      run:\n        shell: true {0}\n',
     'job hetzner: keys'),
    ('a matrix exclude, block form', HMATRIX,
     '      matrix:\n        exclude:\n          - {image: "ubuntu:24.04", part: "test_un*.py"}\n        image: [',
     'matrix keys'),
    ('a matrix exclude, flow form', HMATRIX,
     '      matrix:\n        exclude: [{image: "ubuntu:24.04"}]\n        image: [', 'matrix keys'),
    ('a matrix include', HMATRIX,
     '      matrix:\n        include: [{image: "ubuntu:22.04", part: "x"}]\n        image: [', 'matrix keys'),
    ("jq-linux's if: always()", '    if: ${{ !cancelled() }}\n', '    if: ${{ always() }}\n', "jq-linux's if"),
    ('a shell that runs nothing on the cells step', CELLS, "        shell: 'true {0}'\n" + CELLS, 'want only'),
    ('a default shell for every job', '\njobs:\n', '\ndefaults:\n  run:\n    shell: true {0}\njobs:\n',
     'the workflow keys'),
    ('a quoted key the reader does not know', CELLS, '        "continue-on-error": true\n' + CELLS, 'cannot read'),
    ('the last step in flow form, with continue-on-error', GATE,
     "      - {name: x, continue-on-error: true, run: 'test \"${{ needs.hetzner.result }}\" = success'}\n",
     'not a block mapping'),
]


class Workflow(unittest.TestCase):
    def test_the_jq_linux_matrix_is_the_ci_rows(self):
        want = sorted((v, w[3:], ' '.join(a)) for v, a, w in tested_rows() if w.startswith('ci:'))
        self.assertEqual(sorted(matrix()), want)

    def test_the_hetzner_job_runs_in_the_ubuntu_rows_images_and_only_those(self):
        ubuntu = sorted(i for _, i, _ in matrix() if i.startswith('ubuntu:'))
        self.assertTrue(ubuntu, 'no ubuntu row')
        self.assertEqual(sorted(hetzner_matrix('image')), ubuntu)
        j = job('hetzner')
        self.assertIn('    name: hetzner ${{ matrix.part }} (${{ matrix.image }})\n', j)
        # in the image's container: the cells fail rather than skip on a Linux root without /.dockerenv (support.py)
        self.assertIn('    container: ${{ matrix.image }}\n', j)
        self.assertIn("        run: python3 -I -m unittest discover -s tests/hetzner -t . -p '${{ matrix.part }}' -v\n",
                      j)
        # what those cells need beyond the tests' own: jq, curl, openssl and the system's CA bundle (support.py)
        self.assertIn('DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends ca-certificates curl git '
                      'jq openssl python3\n', j)

    def test_the_parts_run_every_module_of_tests_hetzner_exactly_once(self):
        parts = hetzner_matrix('part')
        self.assertGreaterEqual(len(parts), 2, parts)
        self.assertEqual(split(parts), [])
        # the controls: the check finds a module no part runs, one run twice, and a part that runs none
        self.assertTrue([w for w in split(parts[1:]) if w.endswith('no part runs it')])
        self.assertTrue([w for w in split(parts + parts[:1]) if ' and ' in w])
        self.assertIn('the part nothing*.py runs no module', split(parts + ['nothing*.py']))

    def test_every_jq_row_waits_for_the_hetzner_job_and_fails_unless_all_of_it_passed(self):
        """The CI's own view: each jq row passes only when every hetzner leg did (a tag's release-check reads every
        check run of the commit as well: tests/release/test_jq_matrix.py). It runs its own tests even when one did not
        (!cancelled()), then fails."""
        j = job('jq-linux')
        self.assertIn('    needs: hetzner\n', j)
        self.assertIn('    if: ${{ !cancelled() }}\n', j)
        steps = j.split('\n    steps:\n', 1)[1]
        self.assertTrue(steps.rstrip('\n').endswith('\n        run: test "${{ needs.hetzner.result }}" = success'),
                        'the last step of each jq row is the hetzner check')
        self.assertNotIn('hetzner', ' '.join(a for _, _, a in matrix()), 'a jq row runs tests/hetzner itself')

    def test_the_hetzner_and_jq_linux_jobs_keep_a_closed_shape(self):
        """Each edit in EDITS is valid (actionlint passes it) and is refused, by the rule it breaks; all but the
        include let a jq row or a hetzner leg pass while hetzner cells failed or never ran. The workflow as it is
        passes."""
        w = workflow()
        self.assertEqual(shape(w), [])
        for label, old, new, rule in EDITS:
            with self.subTest(label):
                self.assertEqual(w.count(old), 1, 'the control %r: its anchor is not in the workflow once' % label)
                why = shape(w.replace(old, new))
                self.assertTrue([y for y in why if rule in y], '%s: %r has no %r' % (label, why, rule))

    def test_the_reader_refuses_a_shape_it_does_not_know(self):
        """shape() trusts read(): each spelling it would misread raises, so it is a failure, never a pass. The
        control: the shapes the workflow is written in are read."""
        ok = '# x\na:\n  b: 1\n  c:\n    # y\n    - d: |\n        x: y\n        # z\n      e: f\n    - "g"\n  h:\n'
        self.assertEqual(read(ok), {'a': {'b': '1', 'c': [{'d': 'x: y\n# z', 'e': 'f'}, '"g"'], 'h': None}})
        for label, text in (('a key twice', 'a: 1\na: 2\n'), ('a quoted key', '"a": 1\n'),
                            ('a merge key', 'a:\n  <<: *x\n'), ('an anchor', 'a: &x 1\n'), ('an alias', 'a: *x\n'),
                            ('a tag', 'a: !!str 1\n'), ('a ? key', '? a\n: 1\n'), ('a tab', 'a:\n\tb: 1\n'),
                            ('a second document', 'a: 1\n---\nb: 2\n'), ('a plain value over two lines', 'a: b\n  c\n'),
                            ("a list at its key's indent", 'a:\n- b: 1\n'),
                            ('a block scalar with an indent digit', 'a: |2\n  b\n'),
                            ('deeper than its key', 'a: 1\n  b: 2\n'),
                            ('a key after a list item at its indent', 'a:\n  - b\n  c: 1\n')):
            with self.subTest(label):
                self.assertRaises(Unreadable, read, text)

    def test_the_job_name_release_check_reads(self):
        self.assertIn('    name: jq ${{ matrix.jq }} (${{ matrix.image }})\n', workflow())

    def test_each_leg_checks_its_jq_version_and_runs_with_it(self):
        w = workflow()
        self.assertIn('test "$(/usr/bin/jq --version)" = "${{ matrix.jq }}"', w)
        self.assertIn('run: for a in ${{ matrix.areas }}; do python3 -I -m unittest discover -s tests/$a -t . -v || exit 1; done',
                      w)

    def test_the_hosted_mac_runs_the_tests_with_the_local_row(self):
        local = [w[len('local:'):] for v, a, w in tested_rows() if w.startswith('local:')]
        self.assertEqual(local, ['/usr/bin/jq'])
        m = re.search(r'- name: tests\n\s+working-directory: src\n\s+env:\n\s+JQ: (\S+)\n\s+run: (.*)\n', workflow())
        self.assertTrue(m, 'the tests step of the macOS job names JQ')
        self.assertEqual(m.group(1), '/usr/bin/jq')
        # every area of tests/, through the parallel runner (the same tests as the plain discover line), at its default
        # -j: the Mac's CPU count
        self.assertEqual(m.group(2), 'python3 -I tools/run-tests -v')


if __name__ == '__main__':
    unittest.main()
