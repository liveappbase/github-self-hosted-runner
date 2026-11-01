# core/lib/core.jq — shared by the core's programs: the input formats, the state, provenance and the time format
# (core/README.md, "The call" and "facts").

def state_format: 1;
def facts_format: 1;

# the program's inputs; one it needs and did not get is an error (rc != 0: could not decide)
def need($prog; $name): $ARGS.named[$name] // error("\($prog): --\(if $name == "log" then "rawfile" elif $name == "now" then "arg" else "slurpfile" end) \($name) is required");

def now_in($prog):
  need($prog; "now") as $n
  | ($n | tonumber? // null) as $v
  | if $v != null and $v >= 0 and $v == ($v | floor) then $v else error("\($prog): now is not whole seconds: \($n)") end;

def facts_in($prog):
  need($prog; "facts") as $f
  | if ($f | length) == 1 and ($f[0] | type) == "object" and $f[0].format == facts_format then $f[0]
    else error("\($prog): facts: not one JSON object of format \(facts_format)") end;

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

# a process read {pid, start}: the same process when both are there and equal
def same_proc($a; $b): $a != null and $b != null and $a.pid == $b.pid and $a.start == $b.start;

# provenance: process $p started after the config was installed (whole seconds; equal is NOT proven), and that config
# names family $fam's candidate on every set of the family
def runs_candidate($p; $config; $fam):
  $p != null and $fam.candidate != null and ($config.installed | type) == "number" and $config.installed < $p.start
  and ($fam.sets | length) > 0
  and all($fam.sets[]; . as $s | $config.lines[$s] != null and $config.lines[$s] == $fam.candidate.lines[$s]);
