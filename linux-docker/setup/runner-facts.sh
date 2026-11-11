#!/usr/bin/env bash
# runner-facts.sh — SOURCED, never run: ONE copy of what the Linux host's runner-image updater MEASURES. pool-image.sh's
# unattended modes source it (the window journals runscaler's process and its log position, checks the jq and reads
# the idle pair with it), and so does bin/runner-updater (a pass's facts: core/README.md, "facts"). It acts on
# nothing and writes only the files it is given. Needs bash 5, GNU coreutils, python3, curl, jq and `systemctl
# --user`. The caller sets R (runscaler's folder, ~/.config/runner: runner.log, runner.log.1), CORE (the release's
# core/) and RS_HEALTH_PORT (the host config's); it reads no host config itself. Its systemctl calls close fd 8 and fd 9
# (pool-image.sh's own lock, the updater lock: no systemctl client holds either). NO SHELL THAT WAITS FOR A READ HOLDS
# A LOCK (S2b-3c-1 B2a; build review r4 of B1, codex F4): the command substitution a read runs systemctl in closes
# both first (`$(exec 8>&- 9>&-; systemctl ...)`: bash need not exec systemctl in it, and measured it does not), and
# proc_now and unit_read, run in a subshell (`$(proc_now)`, `( unit_read ... )`: $BASHPID is not $$), close both in it
# first; so a window or an updater killed while a read is pending leaves no process of it holding either lock. A
# redirection on a call (`proc_now 9>&-`) is no close: bash keeps a copy to put back, and that copy holds the lock.
#
#   proc_now             runscaler as systemd reports it, in ONE read (`systemctl --user show runscaler`): "PID START"
#                        (MainPID, ActiveEnterTimestamp in epoch seconds) when its unit is active, else "none". rc 1
#                        (and "none") when that read failed or its answer is not one this reads (no ActiveState; active
#                        with no PID or no start): the window's journal reads none, a pass has no facts. A unit that
#                        is deactivating (runscaler draining after a stop) reads none too, though its process still
#                        runs: a pass then sees no boundary of one process, an evidence gap (the safe direction)
#   unit_read            runscaler's unit in ONE read (`systemctl --user show runscaler`): UNIT_ACTIVE (ActiveState),
#                        UNIT_FILE (UnitFileState: `enabled` is CI on, S2b-3c-1 operator (1)), UNIT_PID (MainPID, 0 for
#                        none), UNIT_START (ActiveEnterTimestamp, epoch seconds, or empty). rc 1 when the read failed or
#                        its answer is not one this reads (an ActiveState of another word, no MainPID, no UnitFileState)
#   runs AFTER FILE SET...
#                        THE RUNS RULE (S2b-3c-1 r3 FOLD, Opus r3 F1): runscaler RUNS when its /healthz answers and
#                        lists every SET on two reads 3 s apart (healthz_pair, into FILE, which it empties first; FILE
#                        `-`: the reads kept in memory, no file: the updater's status and its OUTAGE RULE), and
#                        proc_now gives the same "PID START" before and after those reads, with START after AFTER (an
#                        epoch: the install time). Never one `active` read: runscaler.service is Type=simple with
#                        Restart=always, so a runner-start that refuses is `active` for a second of each 31, a fresh
#                        ActiveEnterTimestamp each time, and one that hangs is `active` while it serves nothing. 0 and
#                        RUNS_PROC = that "PID START"; 1 and RUNS_WHY (it prints nothing)
#   log_pos [OUT [INODE OFFSET SHA]]
#                        runscaler's log position, R/runner.log opened ONCE: "INODE OFFSET SHA" (its inode and size from
#                        that open, and the sha256 of the 64 bytes before the size, or of all of them when fewer). With
#                        OUT, also the log TEXT since the boundary INODE OFFSET SHA (a position an earlier pass captured)
#                        into OUT, read through the same open file, so no byte past the position; and a second line
#                        "CONTINUOUS WHY" (true | false):
#                          - no boundary: false, no text (a first pass);
#                          - the boundary's inode is runner.log's, its offset is not past the size and the sha of the 64
#                            bytes before it still matches: true; the text is runner.log from the boundary;
#                          - runner.log.1 is the boundary's inode (runscaler rotated ONCE: at 10 MiB it renames
#                            runner.log to runner.log.1) and its sha matches: true; the rest of runner.log.1 from the
#                            boundary, then runner.log from 0;
#                          - anything else (a cut or rewritten file, two rotations, a removed file): false, and the
#                            text is only what can be read, runner.log from 0 (the core reads it as an evidence gap).
#                        rc 1 when runner.log cannot be read (none, not a regular file, a short read)
#   tested_jq            `jq --version` is a core row of CORE/TESTED_JQ (the core's own list); JQV = what it printed
#   healthz_pair FILE    runscaler's /healthz (127.0.0.1:RS_HEALTH_PORT) read twice, 3 s apart, each answer appended to
#                        FILE as one line (FILE `-`: printed); a read with no answer adds nothing. The pause is BETWEEN the reads: what
#                        follows the second read follows it at once (the window's rename and restart)
#   config_read FILE     FILE read through ONE open: a first line "MTIME SHA" (its mtime in whole seconds and the
#                        sha256 of the bytes read, so both are of the version parsed), then one JSON line {"sets": [SET,
#                        ...], "lines": {SET: IMAGE, ...}}: every [[scaleset]] block's `name`, in file order, and its
#                        `runner-image` when it has one. rc 1 with the why on stdout on a config whose lines the core
#                        would read wrongly (the Studio's rules where they apply, bin/runner-updater-lib's ru_config): a
#                        block with two names or two images, or with no name; two blocks with one name; a runner-image
#                        line outside a [[scaleset]] block (a table after it, [scaleset.docker], ends the block); a
#                        name or runner-image line that is not a plain "..." string; a top-level log-file line other
#                        than `log-file = "R/runner.log"` (what 03 renders: a plain "..." string of the file log_pos
#                        reads), or a log-file key in any table (each of these names `03-runscaler.sh real`), or a
#                        log-format other than "text" (runscaler would then write no runner.log the core reads, and a
#                        quiet log would look like a healthy one); a top-level log-level other than "info" (what 03
#                        renders) or "debug": runscaler accepts debug, info, warn and error, and at warn or error it
#                        writes no INFO record, so no job-completed (the proof of life R1 and KEEP read). A config with
#                        NO log-file key is read: one 03 rendered before it wrote the line, which runscaler v0.9.5 logs
#                        to the runner.log beside it, and runner-start runs it on no other runner. It reads no
#                        pool-size (a Tart rule).
#   disk_ok              DISK (PLAN D5; S2b-3c-2 E-9, r3 Opus F5: ONE copy, which pool-image.sh's switch and the
#                        updater's pass both read): RUN_USER's filesystem (/home/RUN_USER: D1's images and the
#                        registry's volume) has DISK_PCT % or more free (runscaler's min_free, 10), by one `df -Pk`:
#                        free * 100 >= size * DISK_PCT (exactly 10 % passes). Else rc 1 and DISK_WHY (its free and its
#                        size, and the hand step: free disk on /home/RUN_USER, the registry grows with each release).
#                        The caller sets RUN_USER (its host config's)
#   ci_hand CLASS        CI DISABLED's hand line by the CLASS of the close that holds it (S2b-3c-2 E-12, the r2 FOLD:
#                        ONE copy, pool-image.sh's RECOVER texts and the updater's STOP detail.hand): REPLY. target-old
#                        (an older runscaler still runs the file before the TARGET): enable, then a restart at idle
#                        (`enable --now` starts nothing on an active unit); target-idle, pre and none: `enable --now`;
#                        target-running: `enable` (it runs already); target-failed: the backup back first; any other
#                        (a file no window wrote): its validate first
#   install_time SHA MTIME DIR
#                        the INSTALL TIME of a config whose sha256 is SHA and whose mtime (whole seconds) is MTIME (PLAN
#                        D1, clocks), then the why: "EPOCH WHY". R = the `renamed` epoch of the newest closed window
#                        journal in DIR (a file named YYYYmmddHHMMSS-PID) whose last `staged-sha` is SHA and that has a
#                        `renamed` line (its last). A window's own install leaves the file's mtime at or before R (its
#                        touch comes after `rename-start`, its `renamed` after the rename): then R. An mtime AFTER R is
#                        a later write of the same bytes (`03-runscaler.sh real DIGEST`, which restarts nothing): then
#                        MTIME, never a time earlier than the file itself. No such journal: MTIME (a hand install)
#   install_of FILE DIR  FILE's install time (install_time of its sha and mtime, read through ONE config_read, the
#                        window journals in DIR) in epoch seconds, or `none` when it cannot be read
#   unstarted P INST     AN INSTALL COUNTS NOTHING UNTIL A RESTART (S2b-3c-2 B4b fix 2, review r2 F1: ONE rule, the
#                        updater's NO IDLE level and THE VERSION, and pool-image.sh's SHORTCUT'S RESTART, its gate and
#                        its read again right before `stopping`): 0 when no runscaler is proven to have started since
#                        the install INST (install_of's): P ("PID START", proc_now's, read BEFORE INST) is none, INST is
#                        none (or not "PID START"), or P started at or before INST (its own second too: a start in that second can come
#                        just before the install, the safe side). 1 when P started after INST. REPLY says which

proc_now() {
  local o k v s= p= a=
  [ "$BASHPID" = "$$" ] || exec 8>&- 9>&-   # NO SHELL THAT WAITS FOR A READ HOLDS A LOCK (the header)
  o=$(exec 8>&- 9>&-; systemctl --user show runscaler -p ActiveState -p MainPID -p ActiveEnterTimestamp --timestamp=unix 2> /dev/null < /dev/null) \
    || { echo none; return 1; }
  while IFS='=' read -r k v; do case $k in ActiveState) s=$v ;; MainPID) p=$v ;; ActiveEnterTimestamp) a=${v#@} ;; esac; done <<< "$o"
  if [ "$s" = active ] && [[ $p =~ ^[1-9][0-9]*$ ]] && [[ $a =~ ^[0-9]+$ ]]; then echo "$p $a"; return 0; fi
  echo none
  [ -n "$s" ] && [ "$s" != active ]   # 0: systemd answered that no runscaler runs; 1: an answer this does not read
}

unit_read() {
  local o k v
  UNIT_ACTIVE= UNIT_FILE= UNIT_PID= UNIT_START=
  [ "$BASHPID" = "$$" ] || exec 8>&- 9>&-   # NO SHELL THAT WAITS FOR A READ HOLDS A LOCK (the header)
  o=$(exec 8>&- 9>&-; systemctl --user show runscaler -p ActiveState -p UnitFileState -p MainPID -p ActiveEnterTimestamp \
    --timestamp=unix 2> /dev/null < /dev/null) || return 1
  while IFS='=' read -r k v; do
    case $k in ActiveState) UNIT_ACTIVE=$v ;; UnitFileState) UNIT_FILE=$v ;; MainPID) UNIT_PID=$v ;;
      ActiveEnterTimestamp) UNIT_START=${v#@} ;; esac
  done <<< "$o"
  [[ $UNIT_ACTIVE =~ ^(active|inactive|failed|activating|deactivating|reloading|maintenance)$ ]] \
    && [[ $UNIT_PID =~ ^[0-9]+$ ]] && [[ $UNIT_FILE =~ ^[a-z-]+$ ]] && [[ $UNIT_START =~ ^[0-9]*$ ]]
}

runs() {
  local a=${1-} f=${2-} p q pair
  shift 2
  RUNS_PROC= RUNS_WHY=
  [[ $a =~ ^[0-9]+$ ]] && [ "$#" -ge 1 ] || { RUNS_WHY="runs: no install time or no set"; return 1; }
  p=$(proc_now)
  [ "$p" != none ] || { RUNS_WHY="no runscaler process runs (systemd: not active)"; return 1; }
  [ "${p#* }" -gt "$a" ] || { RUNS_WHY="runscaler ($p) started at or before $a, the install"; return 1; }
  if [ "$f" = - ]; then pair=$(healthz_pair -)
  else : > "$f" || { RUNS_WHY="cannot write $f"; return 1; }; healthz_pair "$f"; pair=; fi
  printf '%s' "$pair" | python3 -I -c '
import json, sys
data = sys.stdin.buffer.read() if sys.argv[1] == "-" else open(sys.argv[1], "rb").read()
lines = data.decode("utf-8", "replace").splitlines()
want = set(sys.argv[2:])
def lists(l):
    try:
        h = json.loads(l)
        return want <= {s.get("name") for s in (h.get("scale_sets") or []) if isinstance(s, dict)}
    except (ValueError, AttributeError):
        return False
sys.exit(0 if len(lines) == 2 and all(lists(l) for l in lines) else 1)' "$f" "$@" \
    || { RUNS_WHY="runscaler's /healthz did not list every set ($*) on two reads 3 s apart"; return 1; }
  q=$(proc_now)
  [ "$q" = "$p" ] || { RUNS_WHY="runscaler changed during the /healthz reads ($p, then $q)"; return 1; }
  RUNS_PROC=$p
}

log_pos() {
  python3 -I -c '
import hashlib, os, stat, sys
log, more = sys.argv[1], sys.argv[2:]


def sha_before(f, off):
    n = min(64, off)
    f.seek(off - n)
    b = f.read(n)
    if len(b) != n:
        raise OSError("short read")
    return hashlib.sha256(b).hexdigest()


def copy(f, start, n, o):
    f.seek(start)
    while n > 0:
        b = f.read(min(n, 65536))
        if not b:
            raise OSError("short read")
        o.write(b)
        n -= len(b)


try:
    with open(log, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode):
            sys.exit(1)
        pos = st.st_size
        head = "%d %d %s" % (st.st_ino, pos, sha_before(f, pos))
        if not more:
            print(head)
            sys.exit(0)
        cont, name = False, os.path.basename(log)
        with open(more[0], "wb") as o:
            if len(more) < 4:
                why = "first pass: no boundary in the state yet, so no text"
            elif more[1] == str(st.st_ino):
                bo = int(more[2])
                if bo <= pos and sha_before(f, bo) == more[3]:
                    copy(f, bo, pos - bo, o)
                    cont, why = True, "continuous: the same file since the last pass"
                else:
                    why = "NOT continuous: the log file was cut or rewritten at the last pass\x27s position"
            else:
                try:
                    g = open(log + ".1", "rb")
                except OSError:
                    g = None
                if g is None:
                    why = "NOT continuous: the last pass\x27s log file is gone (no %s.1)" % name
                else:
                    with g:
                        s1 = os.fstat(g.fileno())
                        bo = int(more[2])
                        if not stat.S_ISREG(s1.st_mode) or str(s1.st_ino) != more[1]:
                            why = "NOT continuous: the last pass\x27s log file is gone (the log rotated more than once, or it was removed)"
                        elif bo <= s1.st_size and sha_before(g, bo) == more[3]:
                            copy(g, bo, s1.st_size - bo, o)
                            copy(f, 0, pos, o)
                            cont, why = True, "continuous: the log rotated once (the rest of %s.1, then %s)" % (name, name)
                        else:
                            why = "NOT continuous: %s.1 was cut or rewritten at the last pass\x27s position" % name
            if not cont and len(more) >= 4:   # a boundary it cannot follow: only what can be read
                copy(f, 0, pos, o)
    print(head)
    print("true" if cont else "false", why)
except (OSError, ValueError):
    sys.exit(1)
' "$R/runner.log" "$@" 2> /dev/null < /dev/null
}

tested_jq() {
  JQV=$(jq --version 2> /dev/null < /dev/null) || JQV="no jq"
  [[ $JQV =~ ^jq-[A-Za-z0-9.+-]+$ ]] || return 1
  awk -v v="$JQV" '$1 == v && $2 ~ /(^|,)core(,|$)/ { f = 1 } END { exit !f }' "$CORE/TESTED_JQ" 2> /dev/null
}

healthz_pair() {
  local i j
  for i in 1 2; do
    [ "$i" = 1 ] || sleep 3
    j=$(curl -fs -m 5 "http://127.0.0.1:${RS_HEALTH_PORT}/healthz" < /dev/null) || continue
    if [ "$1" = - ]; then printf '%s\n' "$j"; else printf '%s\n' "$j" >> "$1"; fi
  done
}

config_read() {
  python3 -I -c '
import hashlib, json, os, re, stat, sys
p, LOGF = sys.argv[1], sys.argv[2]


def no(why):
    print(why)
    sys.exit(1)


try:
    with open(p, "rb") as f:
        st = os.fstat(f.fileno())
        data = f.read() if stat.S_ISREG(st.st_mode) else None
except OSError:
    data = None
if data is None:
    no("no readable config %s" % p)
try:
    text = data.decode("utf-8")
except UnicodeDecodeError:
    no("%s is not UTF-8 text" % p)
WS, TAIL = "[ \t]*", "[ \t]*(#.*)?"


def key(k):
    return re.compile(WS + "[\"\x27]?" + k + "[\"\x27]?" + WS + "[.=]")


sets, lines, block = [], {}, None
top = True


def end():
    global block
    if block is None:
        return
    if block["name"] is None:
        no("%s: a [[scaleset]] block has no name" % p)
    if block["name"] in sets:
        no("%s: two [[scaleset]] blocks are named \x27%s\x27" % (p, block["name"]))
    sets.append(block["name"])
    if block["image"] is not None:
        lines[block["name"]] = block["image"]
    block = None


for n, l in enumerate(text.split("\n"), 1):
    if re.fullmatch(WS + "(#.*)?", l):
        continue
    if re.fullmatch(WS + r"\[\[" + WS + "scaleset" + WS + r"\]\]" + TAIL, l):
        end()
        block, top = {"name": None, "image": None}, False
    elif re.match(WS + r"\[", l):
        end()
        top = False
    elif key("runner-image").match(l):
        if block is None:
            no("%s line %d: a runner-image line outside a [[scaleset]] block" % (p, n))
        if block["image"] is not None:
            no("%s line %d: a [[scaleset]] block has two runner-image lines" % (p, n))
        m = re.fullmatch(WS + "runner-image" + WS + "=" + WS + "\"([^\"\\\\\x00-\x1f\x7f]+)\"" + TAIL, l)
        if not m:
            no("%s line %d: a runner-image line this does not read (a plain \"...\" string)" % (p, n))
        block["image"] = m.group(1)
    elif block is not None and key("name").match(l):
        if block["name"] is not None:
            no("%s line %d: a [[scaleset]] block has two names" % (p, n))
        m = re.fullmatch(WS + "name" + WS + "=" + WS + "\"([A-Za-z0-9][A-Za-z0-9._-]{0,99})\"" + TAIL, l)
        if not m:
            no("%s line %d: a scale set name this does not read ([A-Za-z0-9][A-Za-z0-9._-], at most 100)" % (p, n))
        block["name"] = m.group(1)
    elif key("log-file").match(l):
        if not top:
            no("%s line %d: a log-file key in a table: runscaler takes log-file at the top level only; remove it, and "
               "run 03-runscaler.sh real, which renders the top-level line" % (p, n))
        if not re.fullmatch(WS + "log-file" + WS + "=" + WS + "\"" + re.escape(LOGF) + "\"" + TAIL, l):
            no("%s line %d: log-file is not \"%s\", the runner.log a pass reads: runscaler then writes its log where no "
               "pass reads it, and runner.log reads as a quiet log, so R1 would be blind while the facts look normal; "
               "run 03-runscaler.sh real, which renders that line" % (p, n, LOGF))
    elif top and key("log-format").match(l) and not re.fullmatch(WS + "log-format" + WS + "=" + WS + "\"text\"" + TAIL, l):
        no("%s line %d: log-format is not \"text\": runscaler then writes records the core does not read, so R1 would "
           "be blind while the facts look normal; set log-format = \"text\" or remove the line" % (p, n))
    elif top and key("log-level").match(l) and not re.fullmatch(WS + "log-level" + WS + "=" + WS + "\"(info|debug)\"" + TAIL, l):
        no("%s line %d: log-level is not \"info\" or \"debug\": runscaler then writes no INFO record (no job-completed "
           "record, the proof of life R1 and KEEP read), so a quiet log would look like a healthy one; set log-level "
           "= \"info\" (what 03-runscaler.sh renders) or remove the line" % (p, n))
end()
print(int(st.st_mtime), hashlib.sha256(data).hexdigest())
print(json.dumps({"sets": sets, "lines": lines}, separators=(",", ":")))
' "$1" "$R/runner.log" 2> /dev/null < /dev/null
}

DISK_PCT=10   # runscaler's min_free (PLAN D5 DISK): the share of RUN_USER's filesystem a switch leaves free
disk_ok() {
  local l
  l=$(df -Pk "/home/${RUN_USER}" 2> /dev/null < /dev/null | tail -n 1)
  [[ $l =~ ^[^\ ]+\ +([0-9]+)\ +[0-9]+\ +([0-9]+)\  ]] || { DISK_WHY="df -Pk /home/${RUN_USER} printed no size: [$l]"; return 1; }
  (( BASH_REMATCH[2] * 100 >= BASH_REMATCH[1] * DISK_PCT )) && return 0
  DISK_WHY="the filesystem of /home/${RUN_USER} (D1's images and the registry) has ${BASH_REMATCH[2]} KiB free of ${BASH_REMATCH[1]}, less than ${DISK_PCT}% (runscaler's min_free): free disk on /home/${RUN_USER} first (the registry grows with each release), then the updater switches at its next pass"
  return 1
}

ci_hand() {
  case $1 in
    target-idle|pre|none) REPLY="systemctl --user enable --now runscaler" ;;
    target-old) REPLY="systemctl --user enable runscaler, then at idle systemctl --user restart runscaler" ;;
    target-running) REPLY="systemctl --user enable runscaler" ;;
    target-failed) REPLY="put the rollback's backup (windows/ID.d/config.toml.backup) back as config.toml, then systemctl --user enable --now runscaler" ;;
    *) REPLY="RUNNER_START_CONFIG=~/.config/runner/config.toml ~/bin/runner-start validate; only when it passes, systemctl --user enable --now runscaler" ;;
  esac
}

install_time() {
  local f s r best=
  for f in "$3"/*; do
    [[ ${f##*/} =~ ^[0-9]{14}-[0-9]+$ ]] && [ -f "$f" ] && [ ! -L "$f" ] || continue
    s=$(sed -n 's/^staged-sha \([0-9a-f]\{64\}\)$/\1/p' "$f" 2> /dev/null | tail -n 1)
    r=$(sed -n 's/^renamed \([0-9]\{1,12\}\)$/\1/p' "$f" 2> /dev/null | tail -n 1)
    [ "$s" = "$1" ] && [ -n "$r" ] || continue
    { [ -z "$best" ] || [ "$r" -gt "$best" ]; } && best=$r
  done
  if [ -z "$best" ]; then echo "$2 its mtime: no window journal renamed it into place"
  elif [ "$2" -gt "$best" ]; then
    echo "$2 its mtime: it was written again after the window journal that renamed these bytes into place at $best"
  else echo "$best the window journal that renamed it into place"; fi
}

install_of() {
  local cr head i
  cr=$(config_read "$1") || { echo none; return 0; }
  head=${cr%%$'\n'*}
  [[ $head =~ ^([0-9]+)\ ([0-9a-f]{64})$ ]] || { echo none; return 0; }
  i=$(install_time "${BASH_REMATCH[2]}" "${BASH_REMATCH[1]}" "$2"); i=${i%% *}
  [[ $i =~ ^[0-9]+$ ]] && echo "$i" || echo none
}

unstarted() {
  local p=${1:-none} i=${2:-none}
  if [[ ! $p =~ ^[0-9]+\ [0-9]+$ ]] || [[ ! $i =~ ^[0-9]+$ ]] || [ "${p#* }" -le "$i" ]; then
    REPLY="runscaler pid ${p% *} started at ${p#* }"
    [[ $p =~ ^[0-9]+\ [0-9]+$ ]] || REPLY="no runscaler process (systemd: not active, or an answer this does not read)"
    REPLY="$REPLY; config.toml installed at $i"
    return 0
  fi
  REPLY="runscaler pid ${p% *} started at ${p#* }, after config.toml's install at $i"
  return 1
}
