# core/idle.jq — IDLE (PLAN D5): may the host's runscaler be stopped now. Inputs: healthz (this pass's reads, oldest
# first), facts (sets), state, now. Output: verdict idle | not-idle | wait, a line per set that blocks and per excused
# set, and the state with not_ready_since (when each set was first read not ready; the glue calls this program every
# pass with that pass's read, so the 24 h are measured). Rules: core/README.md, "IDLE".
import "core" as C;

def DAY: 86400;

# . = one read -> what keeps set $n from being idle on it
def blockers($n; $excused):
  ([.scale_sets[]? | select(.name == $n)] | .[0]) as $s
  | if $s == null then ["absent from /healthz"]
    elif ($s.metrics | type) != "object" then ["no metrics"]
    else
      (if $s.ready == true or $excused then [] else ["not ready"] end)
      + ([["idle", $s.idle], ["busy", $s.busy], ["provisioning", $s.provisioning], ["removing", $s.removing],
          ["available", $s.metrics.available_jobs], ["assigned", $s.metrics.assigned_jobs],
          ["running", $s.metrics.running_jobs], ["desired", $s.metrics.desired_runners]]
         | map(select((.[1] // 0) != 0) | "\(.[0]) \(.[1])"))
    end;

C::now_in("idle") as $now
| C::facts_in("idle") as $facts
| C::need("idle"; "healthz") as $reads
| C::state_in("idle") as $state
| if ($state | C::state_known | not) then C::wait_output("idle"; $state)
  else
    ((($facts.sets // []) + [$reads[-2:][]?.scale_sets[]?.name]) | unique) as $sets
    | (reduce $reads[] as $r ($state.not_ready_since // {};
         reduce ($r.scale_sets // [])[] as $s (.;
           if $s.ready == true then del(.[$s.name]) elif has($s.name) then . else .[$s.name] = $now end))
       | with_entries(select(.key as $k | any($sets[]; . == $k)))) as $nrs
    | [$nrs | to_entries[] | select($now - .value >= DAY) | .key] as $excused
    | ($state + {not_ready_since: $nrs}) as $new
    | [$excused[] as $n | "\($n): not ready since \($nrs[$n] | C::utc): excused from readiness only (its counts still count)"] as $exlines
    | if ($reads | length) < 2 then
        {verdict: "not-idle", reason: "IDLE needs two reads 3 s apart; this pass has \($reads | length)",
         lines: $exlines, state: $new}
      else
        [$sets[] as $n | (any($excused[]; . == $n)) as $ex
         | {set: $n, why: ([$reads[-2:][] | blockers($n; $ex)] | add | unique)}
         | select(.why | length > 0)] as $blk
        | if $blk == [] then
            {verdict: "idle", reason: "every set of the host is idle on both reads", lines: $exlines, state: $new}
          else
            [$blk[] | "\(.set): \(.why | join(", "))"] as $bl
            | {verdict: "not-idle", reason: $bl[0], lines: ($bl + $exlines), state: $new}
          end
      end
  end
