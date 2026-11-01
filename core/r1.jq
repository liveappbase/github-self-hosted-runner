# core/r1.jq — the log pass (PLAN D6). Inputs: log (the text since the state's boundary, up to this pass's captured
# position), healthz (this pass's reads), facts, state, now. Output: verdict ok | wait; families.F = {verdict: none |
# rollback | stop, reason, set, connect_only, failures, stops, open, since, gaps, pending}; the new state (the boundary,
# the held record, the refused VMs, each observed family's evidence). Rules: core/README.md, "The rules".
#
# A family's evidence per set: fails (counted failures: t, s = its log second, c = connect-class, x, seen = the `now`
# of the pass that read it, settled), proofs (log seconds of proofs of life), starts (Tart `Runner started`: a proof
# until that runner is removed `reason=exited` with no jobId), exits (those removals, within SETTLE of log time, that
# a `Job started|completed for unknown runner` naming the runner still takes back), ns (NOT SERVING), completed.
import "core" as C;
import "logfmt" as L;

def NS_SECONDS: 1800;
# SETTLE: a counted failure is settled when no proof of life can still arrive for it: a later record of the log is
# this far past it in log time, or the log is quiet (nothing held) and a later pass's `now` is this far past the `now`
# of the pass that read it. The same quiet reads a held record (the glue's clock, the text unchanged).
def SETTLE: 120;

# a log time "YYYY-MM-DD HH:MM:SS" -> seconds, compared only with other log times (the log's times have no zone)
def lsec: strptime("%Y-%m-%d %H:%M:%S") | mktime;

def fresh($cand): {version: $cand.version, lines: $cand.lines, open: false, since: null, gaps: 0,
                   succeeded: 0, failed: 0, canceled: 0, other: 0, sets: {}, verdict: null, stops: [], pending: null};
def set0: {fails: [], starts: [], proofs: [], exits: [], ns: null, completed: false};

# every value of the record's attributes, one text
def rtext: [.attrs[]? | strings] | join("\n");
def shim_reason: (rtext | capture("liveapp-ci-shim: REFUSE (?<r>[^\n\"]*)") | .r) // "";
def vms: [(.attrs.name // ""), rtext | match("runner-[0-9a-f]{8}"; "g") | .string] | unique;
def first_line: split("\n")[0] | .[0:200];

# the classification table (core/README.md, PLAN D6 with its AMENDMENT); $p = the family's provider, $refused = VMs
# the shim refused. -> k: completed (proof of life; KEEP's counts) | exited (`Runner removed reason=exited` with no
# jobId: a counted failure, unless an unknown-runner line naming that runner follows within SETTLE, see apply) |
# unknown (`Job started|completed for unknown runner`: proof of life for the set when it names such a runner) |
# removed (confirms a Tart start) | start (Tart: proof unless taken back) | fail (c = connect-class) | retired | shim |
# refused | paired | none
def classify($p; $refused):
  if .msg == "Runner removed" then
    if .attrs.reason == "job-completed" then {k: "completed", name: .attrs.name, result: (.attrs.result // "")}
    elif .attrs.reason == "exited" and .attrs.jobId == null then {k: "exited", name: .attrs.name}
    else {k: "removed", name: .attrs.name} end
  elif .msg == "Runner started" then (if $p == "tart" then {k: "start", name: .attrs.name} else {k: "none"} end)
  elif .msg == "Job started for unknown runner (already removed?)"
       or .msg == "Job completed for unknown runner (already removed?)" then {k: "unknown", name: (.attrs.runnerName // "")}
  elif .msg == "Failed to start runner, will retry" then
    (.attrs.error // "") as $e
    | if ($e | contains("liveapp-ci-shim: REFUSE")) then {k: "shim", reason: shim_reason}
      elif any(vms[]; . as $v | any($refused[]; . == $v)) then {k: "paired", vms: vms}
      elif ($e | contains("failed to generate JIT config")) then {k: "none"}
      elif $p == "tart" and ($e | contains("deprecated and cannot receive messages")) then {k: "retired", x: ($e | first_line)}
      elif ($e | test("runner process exited on [^ ]+ (before|right after) connecting to GitHub")) then
        (if ($e | contains("no longer exists on the server")) then {k: "none"} else {k: "fail", c: true, x: ($e | first_line)} end)
      elif ($e | contains("did not connect to GitHub within")) then {k: "fail", c: true, x: ($e | first_line)}
      else {k: "fail", c: false, x: ($e | first_line)} end
  elif (rtext | contains("liveapp-ci-shim: REFUSE")) then {k: "refused", reason: shim_reason, vms: vms}
  else {k: "none"} end;

def add_stop($name; $reason): if any(.stops[]; .stop == $name) then . else .stops += [{stop: $name, reason: $reason}] end;

# . = family evidence; one classified event of set $s at log time $t (log second $sec), read by the pass of $seen
def apply($ev; $s; $t; $sec; $seen):
  if $ev.k == "completed" then
    .sets[$s] = ((.sets[$s] // set0) | .proofs += [$sec] | .completed = true)
    | if $ev.result == "succeeded" then .succeeded += 1 elif $ev.result == "failed" then .failed += 1
      elif $ev.result == "canceled" then .canceled += 1 else .other += 1 end
  elif $ev.k == "exited" then
    .sets[$s] = ((.sets[$s] // set0)
                 | ([.starts[] | select(.n == $ev.name) | .s] | max) as $st
                 | .fails += [{t: $t, s: $sec, c: false, x: "Runner removed reason=exited, no job: \($ev.name)",
                               seen: $seen, settled: false, n: $ev.name}]
                 | .exits += [{n: $ev.name, s: $sec, seen: $seen, start: $st}]
                 | .starts |= map(select(.n != $ev.name)))
  # the D6 AMENDMENT: a `Job started|completed for unknown runner` naming a runner removed `reason=exited` with no
  # jobId less than SETTLE before (.exits holds only those: settle_log and settle_quiet end the others): that runner
  # ran a job. Its exited failure is not counted, the line is proof of life for the set, and the runner's start is
  # proof again
  elif $ev.k == "unknown" then
    .sets[$s] = ((.sets[$s] // set0)
                 | ([.exits[] | select($ev.name != "" and .n == $ev.name)] | first) as $x
                 | if $x == null then .
                   else .exits |= map(select(.n != $ev.name))
                        | .fails |= map(select((.n == $ev.name and .s == $x.s) | not))
                        | .proofs += [$sec, ($x.start // empty)]
                   end)
  elif $ev.k == "removed" then
    .sets[$s] = ((.sets[$s] // set0)
                 | ([.starts[] | select(.n == $ev.name) | .s] | max) as $st
                 | if $st != null then .proofs += [$st] | .starts |= map(select(.n != $ev.name)) else . end)
  elif $ev.k == "start" then .sets[$s] = ((.sets[$s] // set0) | .starts += [{n: $ev.name, t: $t, s: $sec}])
  elif $ev.k == "fail" then
    .sets[$s] = ((.sets[$s] // set0) | .fails += [{t: $t, s: $sec, c: $ev.c, x: $ev.x, seen: $seen, settled: false}])
  elif $ev.k == "retired" then add_stop("PINNED RUNNER RETIRED"; "set \($s): \($ev.x)")
  elif $ev.k == "shim" or $ev.k == "refused" then add_stop("SHIM REFUSED"; "set \($s): \($ev.reason)")
  else . end;

# SETTLE by the log: a record of log second $sec settles every failure SETTLE or more before it, and ends the exits
# that no unknown-runner line took back in time (. = family evidence)
def settle_log($sec):
  .sets |= map_values(.fails |= map(if .settled != true and $sec - .s >= SETTLE then .settled = true else . end)
                      | .exits |= map(select($sec - .s < SETTLE)));

# SETTLE by the clock, when the log is quiet (nothing held): a failure read SETTLE or more before `now`. (An exit
# ends only by the log: a later unknown-runner line inside its SETTLE of log time still takes the failure back.)
def settle_quiet($now):
  .sets |= map_values(.fails |= map(if .settled != true and $now - .seen >= SETTLE then .settled = true else . end));

# . = one set's evidence; $fs = failures -> runs: in log order, a new run starts at a failure when a proof of life
# (a proof, or a start not taken back) lies between it and the one before (the same second as either = between)
def runs($fs):
  [.proofs[]?, .starts[]?.s] as $b
  | reduce ($fs | sort_by(.s))[] as $f ([];
      if length == 0 then [[$f]]
      else .[-1][-1].s as $p
        | if any($b[]; . >= $p and . <= $f.s) then . + [[$f]] else .[-1] += [$f] end
      end);

def rollback($s; $run):
  {verdict: "rollback", set: $s, failures: [$run[] | {t, c, x}], connect_only: all($run[]; .c)};

# R1 over every set of a family's evidence: three SETTLED counted failures with no proof of life between them
def judge:
  if .verdict != null then .
  else (first(.sets | to_entries | sort_by(.key)[] | .key as $s
              | (.value | runs([.fails[] | select(.settled)]))[] | select(length >= 3) | rollback($s; .)) // null) as $v
       | if $v != null then .verdict = $v else . end
  end;

# a confirmed proof of life ends the failures before it once they are all settled (they were judged)
def prune:
  .sets |= map_values(([.proofs[]] | max) as $p
    | if $p != null and all(.fails[]; .s > $p or .settled) then
        .fails |= map(select(.s > $p)) | .starts |= map(select(.s > $p)) | .proofs = [$p]
      else . end);

# a run that can still reach R1 (KEEP waits for it): three counted failures, settled or not, with no proof of life
# between them, with $pot = {SET: [failures the held record may be]}
def pending($pot):
  if .verdict != null then null
  else first(.sets | to_entries | sort_by(.key)[] | .key as $s
             | (.value | runs(.fails + ($pot[$s] // [])))[] | select(length >= 3)
             | {set: $s, failures: length, settled: ([.[] | select(.settled == true)] | length)}) // null
  end;

def ns_read($s):
  ([.scale_sets[]? | select(.name == $s)] | .[0]) as $x
  | $x != null and $x.ready == true and ($x.idle // 0) >= 1 and ($x.busy // 0) == 0
    and (($x.metrics.assigned_jobs // 0) >= 1);

C::now_in("r1") as $now
| C::facts_in("r1") as $facts
| C::need("r1"; "log") as $log
| C::need("r1"; "healthz") as $reads
| C::state_in("r1") as $state
| if ($state | C::state_known | not) then C::wait_output("r1"; $state)
  else
    (if C::same_proc($facts.proc.before; $facts.proc.after) then $facts.proc.before else null end) as $owner
    | ($state.boundary.owner // null) as $prev
    | (C::same_proc($prev; $owner) and $facts.continuous == true) as $owned
    | ($facts.families // {}) as $fams
    # each family with a candidate: its evidence (fresh for a new candidate), provenance now, counting this interval
    | ($fams | with_entries(select(.value.candidate != null)
        | .key as $f | .value as $fam
        | ($state.families[$f] // null) as $old
        | (if $old != null and $old.version == $fam.candidate.version and $old.lines == $fam.candidate.lines
           then $old else fresh($fam.candidate) end) as $ev
        | C::runs_candidate($owner; $facts.config; $fam) as $prov
        | .value = {ev: $ev, prov: $prov, counting: ($ev.open and $owned and $prov), provider: $fam.provider,
                    sets: $fam.sets})) as $obs
    # an open window that does not count this interval: an evidence gap. It closes the window; the window that
    # opens again starts its counts, NOT SERVING and the KEEP clock from zero (below)
    | ($obs | map_values(if .ev.open and (.counting | not) then .ev |= (.gaps += 1 | .open = false) else . end)) as $obs
    # the text: the record held at the last pass, then this interval's. The last record is held to the next pass
    # (it may yet grow); a held record that ends with a newline is read whole once the log has been quiet for SETTLE
    | (if $owned then
         ($state.carry // "") as $c0
         | if $log == "" and $c0 != "" and ($c0 | endswith("\n")) and ($state.carry_at | type) == "number"
              and $now - $state.carry_at >= SETTLE
           # read now, as of the pass that held it unchanged
           then ($c0 | L::tokenize_final) + {carry_at: null, seen: $state.carry_at}
           else ($c0 + $log | L::tokenize) as $t
                | $t + {carry_at: (if $t.carry == "" then null elif $t.carry == $c0 then ($state.carry_at // $now)
                                   else $now end), seen: $now}
           end
       else {records: [], carry: "", carry_at: null, seen: $now} end) as $tok
    | (reduce $tok.records[] as $r ({obs: $obs, refused: (if $owned then ($state.refused // []) else [] end)};
         ($r.t | lsec) as $sec
         | .obs |= map_values(if .counting then .ev |= settle_log($sec) else . end)
         | if $r.set == null then .
           else
             .refused as $refused
             | reduce (.obs | to_entries[] | select(.value.counting and any(.value.sets[]; . == $r.set)) | .key) as $f (.;
                 .obs[$f].provider as $prov | ($r | classify($prov; $refused)) as $ev
                 | .obs[$f].ev |= apply($ev; $r.set; $r.t; $sec; $tok.seen)
                 | if $ev.k == "refused" then .refused = (.refused + $ev.vms | unique)
                   elif $ev.k == "paired" then .refused -= $ev.vms
                   else . end)
           end)) as $done
    # the record still held may be a counted failure of a family set: R1 may still come with it (KEEP waits). A held
    # text that ends in a partial line may hold the start of one more record, on any set
    | ($tok.carry | if . == "" then [] else L::tokenize_final.records end) as $held
    # the end of the pass: SETTLE by the clock when nothing is held, then R1 on the settled failures, then the
    # failures a proof of life ended, then the run that may still reach R1
    | ($done.obs | map_values(
        if .counting then
          .provider as $prov | .sets as $fsets
          | (reduce ($held[] | select(.set as $hs | $hs != null and any($fsets[]; . == $hs))) as $r ({};
               ($r | classify($prov; $done.refused)) as $ev
               | if $ev.k == "fail" or $ev.k == "exited" then .[$r.set] += [{s: ($r.t | lsec), settled: false}]
                 else . end)
             | if $tok.carry == "" or ($tok.carry | endswith("\n")) then .
               else reduce $fsets[] as $s (.; .[$s] += [{s: 1e18, settled: false}]) end) as $pot
          | .ev |= ((if $tok.carry == "" then settle_quiet($now) else . end) | judge | prune | .pending = pending($pot))
        else . end)) as $obs0
    # windows that open at this boundary: the process runs the candidate (the KEEP clock starts now)
    | ($obs0 | map_values(if (.ev.open | not) and .prov
                          then .ev |= (.open = true | .since = $now | .sets = {} | .pending = null
                                       | .succeeded = 0 | .failed = 0 | .canceled = 0 | .other = 0)
                          else . end)) as $obs
    # NOT SERVING, from this pass's reads, on the sets of an open window whose process runs the candidate
    | ($obs | map_values(
        if .ev.open and .prov then
          .sets as $sets
          | .ev |= (reduce $sets[] as $s (.;
                .sets[$s] = ((.sets[$s] // set0)
                  | (if .completed then .ns = null else . end)
                  | reduce $reads[] as $rd (.;
                      if ($rd | ns_read($s)) then .ns = ((.ns // {since: $now, reads: 0}) | .reads += 1) else .ns = null end))
                | if .verdict == null and .sets[$s].ns != null and .sets[$s].ns.reads >= 3
                     and $now - .sets[$s].ns.since >= NS_SECONDS
                  then .verdict = rollback($s; (.sets[$s] | C::run_of)
                                           + [{t: "NOT SERVING", c: true, x: "set \($s) read ready, idle, not busy, assigned, for 30 min, no job completed"}])
                  else . end))
        else . end)
      | map_values(.ev.sets |= map_values(.completed = false))) as $obs
    | ($fams | with_entries(.key as $f | .value = (
        ($obs[$f].ev // null) as $ev
        | if $ev == null then {verdict: "none", reason: "no candidate under observation", set: null, connect_only: null,
                               failures: [], stops: [], open: false, since: null, gaps: 0, pending: null}
          elif $ev.verdict != null then
            {verdict: "rollback",
             reason: "R1 on set \($ev.verdict.set): \($ev.verdict.failures | length) counted failures with no proof of life between them\(if $ev.verdict.connect_only then " (connect-class only)" else "" end)",
             set: $ev.verdict.set, connect_only: $ev.verdict.connect_only, failures: $ev.verdict.failures,
             stops: $ev.stops, open: $ev.open, since: $ev.since, gaps: $ev.gaps, pending: null}
          elif ($ev.stops | length) > 0 then
            {verdict: "stop", reason: "\($ev.stops[0].stop): \($ev.stops[0].reason)", set: null, connect_only: null,
             failures: [], stops: $ev.stops, open: $ev.open, since: $ev.since, gaps: $ev.gaps, pending: $ev.pending}
          else
            {verdict: "none",
             reason: (if $ev.open then "observing runner \($ev.version) since \($ev.since | C::utc)"
                        + (if $ev.pending != null then "; set \($ev.pending.set): \($ev.pending.failures) counted failures with no proof of life between them, \($ev.pending.failures - $ev.pending.settled) not settled yet (R1 may still come)" else "" end)
                      else "runner \($ev.version): no evidence window (the running process is not proven to run it)" end),
             set: null, connect_only: null, failures: [], stops: [], open: $ev.open, since: $ev.since, gaps: $ev.gaps,
             pending: $ev.pending}
          end))) as $out
    | {verdict: "ok",
       reason: "the log pass of \($tok.records | length) records\(if $owned then "" else " (the text before this boundary is UNKNOWN: it counts neither way)" end)",
       lines: [$out | to_entries[] | select(.value.reason != "no candidate under observation") | "\(.key): \(.value.reason)"],
       families: $out,
       state: ($state + {boundary: {owner: $owner, position: $facts.position}, carry: $tok.carry,
                         carry_at: $tok.carry_at, refused: $done.refused, families: ($obs | map_values(.ev))}
               | del(.last_t))}
  end
