"""No code that runs on the host calls a Command Line Tools shim (S3b-5 A7).

A shim is a /usr/bin program linked to libxcselect.dylib: on a Mac without the Command Line Tools it opens the install
dialog instead of running. SHIMS is the list on the build Mac, by this command (107 names on macOS 27.0.1, build
26A434; it reads each file's bytes, so it runs no shim):

    for f in /usr/bin/*; do [[ -f $f ]] && /usr/bin/grep -q libxcselect.dylib $f && print -r -- ${f:t}; done

THE SCOPE: every file that runs on the host: bin/*, install, setup/*.sh. Both spellings are a call: the absolute path
(/usr/bin/git) anywhere in code, and a bare name (git) where a command starts. Comments and quoted text are not code
(a `$(...)` inside double quotes is). The one exception is golden-emudhra's GUEST block (from `GUEST=$(cat <<'EOS'` to
its `EOS` line): it runs in the VM's guest, never on the host. What opened the dialog on the Studio on 2026-10-25 is
not known; this census finds nothing today, and keeps it so.
"""
import os
import re
import unittest

from tests.studio.support import REPO

SHIMS = (
    'actool', 'agvtool', 'ar', 'as', 'asa', 'atos', 'bison', 'bm4', 'c++', 'c++filt', 'c89', 'c99', 'cc', 'clang',
    'clang++', 'clangd', 'cmpdylib', 'codesign_allocate', 'cpp', 'ctags', 'ctf_insert', 'DeRez', 'desdp',
    'devicectl', 'dsymutil', 'dwarfdump', 'dyld_info', 'filtercalltree', 'flex', 'flex++', 'g++', 'gatherheaderdoc',
    'gcc', 'gcov', 'genstrings', 'GetFileInfo', 'git', 'git-receive-pack', 'git-shell', 'git-upload-archive',
    'git-upload-pack', 'gm4', 'gnumake', 'gperf', 'hdxml2manxml', 'headerdoc2html', 'heap', 'ibtool', 'ictool',
    'indent', 'install_name_tool', 'kmutil', 'ld', 'leaks', 'lex', 'libtool', 'lipo', 'lldb', 'llvm-g++', 'llvm-gcc',
    'lorder', 'm4', 'make', 'malloc_history', 'mig', 'nm', 'nmedit', 'objdump', 'opendiff', 'otool', 'pagestuff',
    'pip3', 'python3', 'ranlib', 'ResMerger', 'resolveLinks', 'Rez', 'rpcgen', 'sample', 'sdef', 'sdp', 'segedit',
    'SetFile', 'size', 'sourcekit-lsp', 'SplitForks', 'stapler', 'stringdups', 'strings', 'strip', 'swift', 'swiftc',
    'symbols', 'unifdef', 'unifdefall', 'vmmap', 'vtool', 'xcdebug', 'xcode-select', 'xcodebuild', 'xcrun',
    'xcscontrol', 'xcsdiagnose', 'xctrace', 'xed', 'xml2man', 'yacc')
GUEST_START = "GUEST=$(cat <<'EOS'\n"
GUEST_END = '\nEOS\n'
NAME = '(%s)' % '|'.join(re.escape(n) for n in sorted(SHIMS, key=len, reverse=True))
ABSOLUTE = re.compile(r'(?<![\w/.+-])/usr/bin/%s(?![\w.+-])' % NAME)
# where a command starts: the line's start, after ; & | ( { $( ` !, after a keyword that takes a command, after env and
# its options and assignments; then any VAR=value words
START = (r'(?:^|[;&|({`!]|\$\(|(?<![\w-])(?:then|do|else|elif|if|while|until|exec|command|nohup|time|noglob|builtin)\s'
         r'|(?<![\w/-])(?:/usr/bin/)?env(?:\s+-\S+)*\s)')
WORD = re.compile(r'(?<![\w/.+-])%s(?=$|[\s;&|)`])' % NAME, re.M)   # a shim's name as a word
BEFORE = re.compile(r'%s\s*(?:[A-Za-z_]\w*=\S*\s+)*$' % START)   # what comes before it on its line, when it is a command


def host_files():
    files = [os.path.join('bin', n) for n in sorted(os.listdir(os.path.join(REPO, 'bin')))]
    files += ['install'] + [os.path.join('setup', n) for n in sorted(os.listdir(os.path.join(REPO, 'setup')))
                            if n.endswith('.sh')]
    return files


def code_only(text):
    """TEXT with comments and quoted text blanked (newlines kept, so line numbers stay); the code of a $(...) or `...`
    inside double quotes stays"""
    out = []
    stack = ['code']
    i, n = 0, len(text)
    prev = '\n'
    while i < n:
        c = text[i]
        top = stack[-1]
        nxt = text[i + 1] if i + 1 < n else ''
        if c == '\n':
            out.append(c)
        elif top in ('sq',):
            if c == "'":
                stack.pop()
            out.append(' ')
        elif top == 'ansi':
            if c == '\\':
                out.append('  ' if nxt != '\n' else ' ')
                i += 1 if nxt != '\n' else 0
            elif c == "'":
                stack.pop()
                out.append(' ')
            else:
                out.append(' ')
        elif top == 'dq':
            if c == '\\' and nxt:
                out.append(' ' if nxt == '\n' else '  ')
                if nxt == '\n':
                    out[-1] = ' '
                    out.append('\n')
                i += 1
            elif c == '"':
                stack.pop()
                out.append(' ')
            elif c == '$' and nxt == '(':
                stack.append('sub')
                out.append('$(')
                i += 1
            elif c == '`':
                stack.append('bt')
                out.append('`')
            else:
                out.append(' ')
        else:   # code, sub, paren, bt
            if c == '\\' and nxt:
                out.append(c + nxt)
                i += 1
            elif c == '#' and prev in ' \t\n;' and top != 'bt':
                while i < n and text[i] != '\n':
                    out.append(' ')
                    i += 1
                continue
            elif c == "'":
                stack.append('sq')
                out.append(' ')
            elif c == '$' and nxt == "'":
                stack.append('ansi')
                out.append('  ')
                i += 1
            elif c == '"':
                stack.append('dq')
                out.append(' ')
            elif c == '$' and nxt == '(':
                stack.append('sub')
                out.append('$(')
                i += 1
            elif c == '(':
                stack.append('paren')
                out.append(c)
            elif c == ')' and top in ('sub', 'paren'):
                stack.pop()
                out.append(c)
            elif c == '`' and top == 'bt':
                stack.pop()
                out.append(c)
            elif c == '`':
                stack.append('bt')
                out.append(c)
            else:
                out.append(c)
        prev = c
        i += 1
    return ''.join(out)


def without_guest(rel, text):
    """golden-emudhra's text with its GUEST block blanked (newlines kept); every other file as it is"""
    if os.path.basename(rel) != 'golden-emudhra':
        return text
    a = text.index(GUEST_START)
    b = text.index(GUEST_END, a) + 1
    return text[:a] + re.sub(r'[^\n]', ' ', text[a:b]) + text[b:]


def calls(rel, text):
    """[(line, name)] of each shim call in TEXT (REL names the file)"""
    code = code_only(without_guest(rel, text))
    found = []
    for m in ABSOLUTE.finditer(code):
        found.append((code.count('\n', 0, m.start()) + 1, m.group(1)))
    for m in WORD.finditer(code):
        line_start = code.rfind('\n', 0, m.start()) + 1
        if BEFORE.search(code[line_start:m.start()]):
            found.append((code.count('\n', 0, m.start()) + 1, m.group(1)))
    return sorted(set(found))


def read(rel):
    with open(os.path.join(REPO, rel)) as f:
        return f.read()


class TestCensus(unittest.TestCase):
    def test_the_list_has_the_build_mac_s_107_names(self):
        self.assertEqual(len(set(SHIMS)), 107)

    def test_no_host_file_calls_a_shim(self):
        files = host_files()
        self.assertIn('bin/golden-emudhra', files)
        self.assertIn('install', files)
        self.assertGreater(len(files), 20)
        found = {rel: calls(rel, read(rel)) for rel in files}
        self.assertEqual({k: v for k, v in found.items() if v}, {})

    def test_the_guest_block_is_there_and_names_shims(self):
        text = read('bin/golden-emudhra')
        self.assertEqual(text.count(GUEST_START), 1)
        guest = text[text.index(GUEST_START):text.index(GUEST_END, text.index(GUEST_START))]
        self.assertTrue(calls('guest', guest), 'the GUEST block calls no shim: the exception would be untested')


class TestTheCensusFindsACall(unittest.TestCase):
    """The mutants: a call planted in a host file is found, both spellings, in each place a command starts. The
    controls: the same text inside the GUEST block, in a comment or in quoted prose is not."""

    PLANTS = ['/usr/bin/git status', 'git status', 'x=$(git rev-parse HEAD)', 'print -r -- "$(/usr/bin/strings f)"',
              'true && make', 'cat f | strings', 'if xcrun --find cc; then :; fi', 'env -i PATH=/usr/bin python3 -V',
              'LC_ALL=C size f', '{ otool -L f }', 'exec /usr/bin/xcodebuild -version']

    def test_a_planted_host_call_is_found(self):
        for plant in self.PLANTS:
            with self.subTest(plant=plant):
                self.assertEqual(len(calls('bin/x', '#!/bin/zsh -f\nset -u\n' + plant + '\n')), 1, plant)

    def test_every_plant_in_a_host_file_is_found(self):
        text = read('bin/runner-updater')
        at = text.index('\nset -u\n') + 1
        self.assertEqual(len(calls('bin/runner-updater', text[:at] + '\n'.join(self.PLANTS) + '\n' + text[at:])),
                         len(self.PLANTS))

    def test_control_the_same_plants_in_the_guest_block_are_not(self):
        text = read('bin/golden-emudhra')
        at = text.index(GUEST_START) + len(GUEST_START)
        self.assertEqual(calls('bin/golden-emudhra', text[:at] + '\n'.join(self.PLANTS) + '\n' + text[at:]), [])

    def test_control_comments_and_quoted_prose_are_not_calls(self):
        for line in ('# then make it so: git is not here', 'print -r -- "run git status, then make"',
                     "say 'size of git'", 'x=1   # strings and size'):
            with self.subTest(line=line):
                self.assertEqual(calls('bin/x', line + '\n'), [])


if __name__ == '__main__':
    unittest.main()
