# core/keep.jq — KEEP (PLAN D6), per family under observation. Inputs: facts (the families, and the STOPs the glue
# holds), state (as r1.jq last wrote it), now.
# Output: verdict ok | wait; families.F = {verdict: none | observe | accept | jobs-fail | no-evidence | held, reason,
# since, keep_at, succeeded, completions, failed, canceled, other}. Rules: core/README.md, "KEEP".
import "core" as C;

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
        | (if $e0 != null and $e0.version == $fam.candidate.version and $e0.lines == $fam.candidate.lines
           then $e0 else null end) as $e
        # a STOP the glue holds for the family, other than NO EVIDENCE (which heals itself): a person answers it
        # (JOBS FAIL: `back` or `retry` to keep it), so it is never turned into ACCEPT here
        | ([$held[] | select(.family == $f and .stop != "NO EVIDENCE")] | first) as $hs
        | ($e.succeeded // 0) as $ok | ($e.failed // 0) as $bad | ($e.other // 0) as $oth | ($e.canceled // 0) as $can
        | ($ok + $bad + $oth) as $done
        | {since: ($e.since // null), succeeded: $ok, completions: $done, failed: $bad, canceled: $can, other: $oth}
        + (if $e != null and $e.verdict != null then
             {verdict: "held", reason: "R1 on set \($e.verdict.set): the rollback is due", keep_at: null}
           elif $e != null and ($e.stops | length) > 0 then
             {verdict: "held", reason: "\($e.stops[0].stop): \($e.stops[0].reason)", keep_at: null}
           elif $hs != null then
             {verdict: "held", reason: "\($hs.stop) stands: a person answers it; KEEP does not accept while it stands",
              keep_at: null}
           elif $e != null and $e.open then
             ($e.since + KEEP_SECONDS) as $at
             | if $now < $at then
                 {verdict: "observe", keep_at: $at,
                  reason: "runner \($fam.candidate.version): observing since \($e.since | C::utc), KEEP at \($at | C::utc); \($ok) succeeded of \($done) completed"}
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
