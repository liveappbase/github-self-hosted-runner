# core/lib/core.jq — shared by the core's programs: the input formats, the state, provenance and the time format
# (core/README.md, "The call" and "facts").

def state_format: 1;
def facts_format: 1;

# the program's inputs; one it needs and did not get is an error (rc != 0: could not decide)
def need($prog; $name): $ARGS.named[$name] // error("\($prog): --\(if $name == "log" then "rawfile" elif $name == "now" then "arg" else "slurpfile" end) \($name) is required");

# `now`: whole seconds since the epoch, in [2023-11-14, 2100-01-01): a clock in milliseconds, 1e999 (read as the
# largest double) or a clock that never ran (1e9) is no `now` (Codex r1 F5, Opus r1 F4)
def NOW_MIN: 1700000000;
def NOW_END: 4102444800;
def now_in($prog):
  need($prog; "now") as $n
  | ($n | tonumber? // null) as $v
  | if $v != null and $v == ($v | floor) and $v >= NOW_MIN and $v < NOW_END then $v
    else error("\($prog): now is not whole epoch seconds in [\(NOW_MIN), \(NOW_END)): \($n)") end;

# a process observation: null (no process), or {pid: a positive integer, start: a number}. Anything else proves
# nothing and is refused (Codex r1 F4: a missing pid equals a missing pid; a string start compares below a number)
def proc_ok: . == null or ((type == "object") and (.pid | type) == "number" and .pid >= 1 and .pid == (.pid | floor)
                           and (.start | type) == "number");

# a log position {inode, offset, sha}: the file's inode (a string or a number), the byte offset (a whole number >= 0),
# the sha of the 64 bytes before it
def position_ok: type == "object" and ((.inode | type) == "string" or (.inode | type) == "number")
                 and (.offset | type) == "number" and .offset >= 0 and .offset == (.offset | floor)
                 and (.sha | type) == "string";

def facts_in($prog):
  need($prog; "facts") as $f
  | if ($f | length) == 1 and ($f[0] | type) == "object" and $f[0].format == facts_format then $f[0]
    else error("\($prog): facts: not one JSON object of format \(facts_format)") end
  | if .proc == null or ((.proc | type) == "object" and (.proc.before | proc_ok) and (.proc.after | proc_ok)) then .
    else error("\($prog): facts: a proc read is not null or {pid: a positive integer, start: a number}: \(.proc | tojson)") end
  # restart: the updater's own restart of runscaler in this interval, {from: P, to: Q, stopped: the position captured
  # once P had exited, before Q started}, or null
  | if .restart == null or ((.restart | type) == "object" and .restart.from != null and .restart.to != null
                            and (.restart.from | proc_ok) and (.restart.to | proc_ok) and (.restart.stopped | position_ok))
    then .
    else error("\($prog): facts: restart is not null or {from: a process read, to: a process read, stopped: a position}: \(.restart | tojson)") end;

# an EMPTY state file is a fresh state
def state_in($prog):
  need($prog; "state") as $s
  | if ($s | length) == 0 then {format: state_format}
    elif ($s | length) == 1 and ($s[0] | type) == "object" then $s[0]
    else error("\($prog): the state file is not one JSON object") end;

def state_known: .format == state_format;

def wait_output($prog; $state):
  {verdict: "wait", reason: "unknown state format",
   lines: ["\($prog): the state has format \($state.format | tojson); this core reads format \(state_format): waiting"],
   state: $state};

# epoch seconds -> "YYYY-MM-DD HH:MM UTC"
def utc: floor | strftime("%Y-%m-%d %H:%M UTC");

# r1's evidence $e is of the candidate's window: the same version and lines, and the same switch (closed_at). A retry
# switches to the same lines in a new window, which starts fresh: a verdict belongs to its window (Opus r1 F6)
def same_window($e; $cand):
  $e != null and $cand != null and $e.version == $cand.version and $e.lines == $cand.lines
  and $e.closed_at == $cand.closed_at;

# what in r1's evidence $e keeps KEEP from accepting the candidate $cand, apart from a STOP the glue holds and the 72 h:
# null, or {kind, reason}. Only the evidence of the candidate's own window counts (same_window). ONE copy (S3b-4b r3
# P2-1): keep.jq reads it, and so does the glue's `retry`, whose ACCEPT on JOBS FAIL ON THE NEW IMAGE (a person's call)
# holds where KEEP's would, so the two cannot drift. The kinds, first match:
#   rollback  R1's verdict stands: the rollback is due (no STOP takes it back);
#   stop      r1's own STOP in the window (SHIM REFUSED);
#   pending   in the OPEN window, a run that can still reach R1 (r1.jq's pending: three counted failures with no proof
#             of life between them, not all settled). A closed window reads no log, and the window that opens again
#             starts its sets from zero (r1.jq's open_at), so its pending never becomes a verdict: it bars nothing.
# keep.jq: `held` on rollback and stop; on pending, no accept (`observe` until the failures settle)
def r1_bar($e; $cand):
  if same_window($e; $cand) | not then null
  elif $e.verdict != null then {kind: "rollback", reason: "R1 on set \($e.verdict.set): the rollback is due"}
  elif ($e.stops | length) > 0 then {kind: "stop", reason: "\($e.stops[0].stop): \($e.stops[0].reason)"}
  elif $e.open and $e.pending != null then
    {kind: "pending",
     reason: "set \($e.pending.set) has \($e.pending.failures) counted failures with no proof of life between them, \($e.pending.failures - $e.pending.settled) not settled yet (R1 may still come)"}
  else null end;

# a process read {pid, start}: the same process when both are there and equal
def same_proc($a; $b): $a != null and $b != null and $a.pid == $b.pid and $a.start == $b.start;

# provenance: process $p started after the config was installed (whole seconds; equal is NOT proven), and that config
# names family $fam's candidate on every set of the family
def runs_candidate($p; $config; $fam):
  $p != null and $fam.candidate != null and ($config.installed | type) == "number" and $config.installed < $p.start
  and ($fam.sets | length) > 0
  and all($fam.sets[]; . as $s | $config.lines[$s] != null and $config.lines[$s] == $fam.candidate.lines[$s]);

# the counted failures of one set's evidence (r1.jq's state) since its newest proof of life, settled or not (a proof
# in the same second is between): log seconds
def run_of: ([.proofs[]?, .starts[]?.s] | max) as $b | [.fails[]? | select($b == null or .s > $b)];
