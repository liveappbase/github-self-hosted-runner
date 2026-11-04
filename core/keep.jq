# core/keep.jq — KEEP (PLAN D6), per family under observation. Inputs: facts (the families, and the STOPs the glue
# holds), state (as r1.jq last wrote it), now.
# Output: verdict ok | wait; families.F = {verdict: none | observe | accept | jobs-fail | no-evidence | held, reason,
# since, keep_at, succeeded, completions, failed, canceled, other}. Rules: core/README.md, "KEEP".
import "core" as C;
import "stops" as S;

def KEEP_SECONDS: 72 * 3600;

C::now_in("keep") as $now
| C::facts_in("keep") as $facts
| C::state_in("keep") as $state
| ($facts.stops // []) as $held
| if ($held | type) == "array" and all($held[]; type == "object") then .
  else error("keep: facts.stops is not a list of STOPs: \($held | tojson)") end
| if ($state | C::state_known | not) then C::wait_output("keep"; $state) | del(.state)
  else
    ($facts.families // {} | with_entries(.key as $f | .value as $fam | .value = (
      if $fam.candidate == null then {verdict: "none", reason: "no candidate under observation"}
      else
        ($state.families[$f] // null) as $e0
        | (if C::same_window($e0; $fam.candidate) then $e0 else null end) as $e
        # what in r1's evidence bars the ACCEPT (R1's verdict, r1's STOP, a pending run): ONE predicate, which the
        # glue's `retry` reads too (core/lib/core.jq, r1_bar; S3b-4b r3 P2-1)
        | C::r1_bar($e0; $fam.candidate) as $bar
        # a STOP the glue holds for the family, other than NO EVIDENCE (which heals itself): a person answers it
        # (JOBS FAIL: `back` or `retry` to keep it), so it is never turned into ACCEPT here. It holds THIS candidate
        # when it is of the candidate's version (or names none), or when its D7 row says a newer release does NOT
        # proceed alone: check failed, ROLLED BACK and PINNED RUNNER RETIRED of an older version closed that candidate,
        # and the newer one proceeds alone (Opus r2 F2). A STOP that names no family (none, "", or not a name) holds
        # every family: fail closed, as one that names no version (none, "", or not a string) holds the candidate
        # (Opus r3 F6, Opus r4 F5, Opus r5 F4: a glue's unset variable expands to "")
        | ([$held[] | select((.family == $f or (.family | type) != "string" or .family == "") and .stop != "NO EVIDENCE"
                             and ((.version | type) != "string" or .version == "" or .version == $fam.candidate.version
                                  or (S::newer_proceeds(.stop) | not)))] | first) as $hs
        | ($e.succeeded // 0) as $ok | ($e.failed // 0) as $bad | ($e.other // 0) as $oth | ($e.canceled // 0) as $can
        | ($ok + $bad + $oth) as $done
        | {since: ($e.since // null), succeeded: $ok, completions: $done, failed: $bad, canceled: $can, other: $oth}
        + (if $bar != null and $bar.kind != "pending" then {verdict: "held", reason: $bar.reason, keep_at: null}
           elif $hs != null then
             {verdict: "held", reason: "\($hs.stop) stands: a person answers it; KEEP does not accept while it stands",
              keep_at: null}
           elif $e != null and $e.open then
             ($e.since + KEEP_SECONDS) as $at
             | if $now < $at then
                 {verdict: "observe", keep_at: $at,
                  reason: "runner \($fam.candidate.version): observing since \($e.since | C::utc), KEEP at \($at | C::utc); \($ok) succeeded of \($done) completed"}
               # never ACCEPT while a run that can still reach R1 waits for its failures to settle (r1.jq's pending:
               # the bar's last kind, the only one left here)
               elif $ok >= 1 and $bar != null then
                 {verdict: "observe", keep_at: $at, reason: "runner \($fam.candidate.version): KEEP waits: \($bar.reason)"}
               elif $ok >= 1 then
                 {verdict: "accept", keep_at: $at, reason: "runner \($fam.candidate.version): \($ok) succeeded of \($done) completed in 72 h"}
               elif $done >= 1 then
                 {verdict: "jobs-fail", keep_at: $at,
                  reason: "runner \($fam.candidate.version): \($done) jobs completed in 72 h, none succeeded (\($bad) failed, \($oth) other, \($can) canceled)"}
               else
                 {verdict: "no-evidence", keep_at: $at,
                  reason: "runner \($fam.candidate.version): no job completed in 72 h (canceled: \($can))"}
               end
           else
             ($fam.candidate.closed_at + KEEP_SECONDS) as $at
             | if $now < $at then
                 {verdict: "observe", keep_at: null,
                  reason: "runner \($fam.candidate.version): no evidence window yet (the running process is not proven to run it)"}
               else
                 {verdict: "no-evidence", keep_at: null,
                  reason: "runner \($fam.candidate.version): no evidence window in the 72 h since the switch (the running process is not proven to run it)"}
               end
           end)
      end))) as $out
    | {verdict: "ok", reason: "KEEP for \($out | length) families",
       lines: [$out | to_entries[] | select(.value.verdict != "none") | "\(.key): \(.value.verdict): \(.value.reason)"],
       families: $out}
  end
