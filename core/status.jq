# core/status.jq — the STOP lines (PLAN D7), ONE program for both hosts. Inputs: facts (the STOPs the glue holds, the
# families), state (r1.jq's evidence and its own STOPs), now. Output: verdict ok | wait; stops: one object per STOP
# {family, stop, version, known, closes_candidate, rejects, newer_proceeds, line}; lines: the STOP lines, then the
# evidence lines, then the dates until which `back` restores a family's previous image. Rules: core/README.md. The
# STOP table itself is core/lib/stops.jq (one copy; keep.jq reads it too).
import "core" as C;
import "stops" as S;

def plural($n; $word): "\($n) \($word)\(if $n == 1 then "" else "s" end)";
def as_user($u; $cmd): (if $u != null and $u != "" then "as \($u): " else "" end) + "`\($cmd)`";
def what($d): if ($d.text // "") != "" then ": \($d.text)" else "" end;

# . = one STOP {family, stop, version, user, detail}
def render:
  .family as $f | .stop as $n | (.detail // {}) as $d | .user as $u
  | ("\($f): STOP \($n)" + (if .version != null then " (runner \(.version))" else "" end)) as $head
  | S::props($n) as $p
  | {family: $f, stop: $n, version: .version, known: ($p != null),
     closes_candidate: (if $p == null then null else $p[0] end),
     rejects: (if $p == null then null elif $n == "ROLLED BACK" and $d.connect_only == true then "after-retry" else $p[1] end),
     newer_proceeds: S::newer_proceeds($n),
     line: ($head + (
       if $n == "check failed" then
         what($d) + ". Next: "
         + (if $d.step == "build" then as_user($d.build_user; "runner-updater build \(.version)") else as_user($u; "runner-updater retry \($f)") end)
       elif $n == "ROLLED BACK" then
         ($d.failures // []) as $fl
         | ": \(plural($fl | length; "counted failure"))" + (if ($fl | length) > 0 then ", the last: \($fl[-1].x)" else "" end)
           + (if $d.connect_only == true then " (connect-class only: one retry after 1 h comes first; a second rollback rejects the version)" else "" end)
           + ". Next: " + as_user($u; "runner-updater retry \($f)")
       elif $n == "PINNED RUNNER RETIRED" then
         ": GitHub refuses this runner version" + (if ($d.reason // "") != "" then " (\($d.reason))" else "" end)
         + ". Next: a newer runner release; the updater takes it when it is out"
       elif $n == "JOBS FAIL ON THE NEW IMAGE" then
         ($d.counts // {}) as $c
         | ": \($c.completions // 0) completed, \($c.succeeded // 0) succeeded, \($c.failed // 0) failed, \($c.canceled // 0) canceled. Next: "
           + as_user($u; "runner-updater back \($f)") + " (until the keep date), or `runner-updater retry \($f)` to keep it"
       elif $n == "ROLLBACK FAILED" or $n == "CI DISABLED" or $n == "POOL DOWN" then
         what($d) + ". Next, by hand: " + (if ($d.hand // "") != "" then "`\($d.hand)`" else "see docs/operations.md" end)
       elif $n == "HAND CHANGE" or $n == "recipe changed" or $n == "NO BASELINE" then
         what($d) + ". Next: " + as_user($u; "runner-updater rebuild \($f)")
       elif $n == "NO EVIDENCE" then what($d) + ". Next: " + as_user($u; "runner-updater retry \($f)")
       elif $n == "NO IDLE" then what($d) + ". Next: " + as_user($u; "runner-updater switch-now \($f)")
       elif $n == "untested jq" then
         ": \($d.jq.version // "?") at \($d.jq.path // "?") is not in core/TESTED_JQ; no new work starts. Next, in the repository: "
         + "`JQ=\($d.jq.path // "PATH") python3 -I -m unittest discover -s tests/core -t .`, then add its row to core/TESTED_JQ when they pass"
       elif $n == "DISK" then
         what($d) + ". Next, by hand: free disk on the host (docs/operations.md, \"Disk\"); the next window of \($f) checks it again"
       elif $n == "SHIM REFUSED" then
         ": \($d.reason // "the shim refused a VM start"). Next: docs/operations.md, \"When the shim refuses\""
       else ": this core does not know this STOP" + what($d) end))};

C::now_in("status") as $now
| C::facts_in("status") as $facts
| C::state_in("status") as $state
| if ($state | C::state_known | not) then C::wait_output("status"; $state) | del(.state)
  else
    ($facts.stops // []) as $held
    | ($held + [($state.families // {}) | to_entries[] | .key as $f | .value as $e | $e.stops[]?
                | select(. as $s | any($held[]; .family == $f and .stop == $s.stop) | not)
                | {family: $f, stop: .stop, version: $e.version, user: null, detail: {reason: .reason}}]
       | map(render)) as $stops
    | [($state.families // {}) | to_entries[] | .key as $f | .value as $e
       | if $e.verdict != null then
           "\($f): R1: a rollback is due (set \($e.verdict.set), \(plural($e.verdict.failures | length; "counted failure"))\(if $e.verdict.connect_only then ", connect-class only" else "" end))"
         else empty end,
         (if $e.open then
            "\($f): runner \($e.version): observing since \($e.since | C::utc), \(plural($e.gaps; "gap")); \($e.succeeded) succeeded of \($e.succeeded + $e.failed + $e.other) completed"
            + ([$e.sets | to_entries[] | (.value | C::run_of | length) as $k | select($k > 0)
                | "; set \(.key): \(plural($k; "counted failure")) since its last proof of life"] | join(""))
          else "\($f): runner \($e.version): no evidence window (the running process is not proven to run it)" end)] as $ev
    | [($facts.families // {}) | to_entries[] | select(.value.back_until != null)
       | "\(.key): `runner-updater back \(.key)` restores the previous image until \(.value.back_until | C::utc)"] as $back
    | {verdict: "ok", reason: "\($stops | length) STOPs", stops: $stops, lines: ([$stops[].line] + $ev + $back)}
  end
