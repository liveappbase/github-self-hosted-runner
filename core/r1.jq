# core/r1.jq — the log pass (PLAN D6). Inputs: log (the text since the state's boundary, up to this pass's captured
# position), healthz (this pass's reads), facts, state, now. Output: verdict ok | wait; families.F = {verdict: none |
# rollback | stop, reason, set, connect_only, failures, stops, open, since, gaps}; the new state (the boundary, the
# held record, the refused VMs, each observed family's evidence). Rules: core/README.md, "The rules".
import "core" as C;
import "logfmt" as L;

def NS_SECONDS: 1800;
# SETTLE: a held record is read once the log has been quiet this long (the glue's clock; the text unchanged)
def SETTLE: 120;

def fresh($cand): {version: $cand.version, lines: $cand.lines, open: false, since: null, gaps: 0,
                   succeeded: 0, failed: 0, canceled: 0, other: 0, sets: {}, verdict: null, stops: []};
def set0: {fails: [], starts: [], proof: null, ns: null, completed: false};

# every value of the record's attributes, one text
def rtext: [.attrs[]? | strings] | join("\n");
def shim_reason: (rtext | capture("liveapp-ci-shim: REFUSE (?<r>[^\n\"]*)") | .r) // "";
def vms: [(.attrs.name // ""), rtext | match("runner-[0-9a-f]{8}"; "g") | .string] | unique;
def first_line: split("\n")[0] | .[0:200];

# the classification table (core/README.md); $p = the family's provider, $refused = VMs the shim refused
def classify($p; $refused):
  if .msg == "Runner removed" then
    if .attrs.reason == "job-completed" then {k: "completed", name: .attrs.name, result: (.attrs.result // "")}
    elif .attrs.reason == "exited" and .attrs.jobId == null then {k: "exited", name: .attrs.name}
    else {k: "removed", name: .attrs.name} end
  elif .msg == "Runner started" then (if $p == "tart" then {k: "start", name: .attrs.name} else {k: "none"} end)
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

def prune: .proof as $p | if $p == null then . else .fails |= map(select(.t > $p)) | .starts |= map(select(.t > $p)) end;

# . = family evidence; one classified event of set $s at log time $t
def apply($ev; $s; $t):
  if $ev.k == "completed" then
    .sets[$s] = ((.sets[$s] // set0) | .proof = ([.proof, $t] | max) | .completed = true | prune)
    | if $ev.result == "succeeded" then .succeeded += 1 elif $ev.result == "failed" then .failed += 1
      elif $ev.result == "canceled" then .canceled += 1 else .other += 1 end
  elif $ev.k == "exited" then
    .sets[$s] = ((.sets[$s] // set0) | .fails += [{t: $t, c: false, x: "Runner removed reason=exited, no job: \($ev.name)"}]
                 | .starts |= map(select(.n != $ev.name)))
  elif $ev.k == "removed" then
    .sets[$s] = ((.sets[$s] // set0)
                 | ([.starts[] | select(.n == $ev.name) | .t] | max) as $st
                 | if $st != null then .proof = ([.proof, $st] | max) | .starts |= map(select(.n != $ev.name)) | prune
                   else . end)
  elif $ev.k == "start" then .sets[$s] = ((.sets[$s] // set0) | .starts += [{n: $ev.name, t: $t}])
  elif $ev.k == "fail" then .sets[$s] = ((.sets[$s] // set0) | .fails += [{t: $t, c: $ev.c, x: $ev.x}])
  elif $ev.k == "retired" then add_stop("PINNED RUNNER RETIRED"; "set \($s): \($ev.x)")
  elif $ev.k == "shim" or $ev.k == "refused" then add_stop("SHIM REFUSED"; "set \($s): \($ev.reason)")
  else . end;


def rollback($s; $run):
  {verdict: "rollback", set: $s, failures: $run, connect_only: all($run[]; .c)};

# R1 over every set of a family's evidence
def judge:
  if .verdict != null then .
  else (first(.sets | to_entries | sort_by(.key)[] | (.value | C::run_of) as $run | select(($run | length) >= 3)
              | rollback(.key; $run)) // null) as $v
       | if $v != null then .verdict = $v else . end
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
           then ($c0 | L::tokenize_final) + {carry_at: null}
           else ($c0 + $log | L::tokenize) as $t
                | $t + {carry_at: (if $t.carry == "" then null elif $t.carry == $c0 then ($state.carry_at // $now)
                                   else $now end)}
           end
       else {records: [], carry: "", carry_at: null} end) as $tok
    | (reduce $tok.records[] as $r ({obs: $obs, last_t: (if $owned then $state.last_t else null end),
                                     refused: (if $owned then ($state.refused // []) else [] end)};
         (if .last_t != null and $r.t > .last_t then .obs |= map_values(if .counting then .ev |= judge else . end)
          else . end)
         | .last_t = ([.last_t, $r.t] | max)
         | if $r.set == null then .
           else
             .refused as $refused
             | reduce (.obs | to_entries[] | select(.value.counting and any(.value.sets[]; . == $r.set)) | .key) as $f (.;
                 .obs[$f].provider as $prov | ($r | classify($prov; $refused)) as $ev
                 | .obs[$f].ev |= apply($ev; $r.set; $r.t)
                 | if $ev.k == "refused" then .refused = (.refused + $ev.vms | unique)
                   elif $ev.k == "paired" then .refused -= $ev.vms
                   else . end)
           end)) as $done
    # windows that open at this boundary: the process runs the candidate (the KEEP clock starts now)
    | ($done.obs | map_values(if (.ev.open | not) and .prov
                              then .ev |= (.open = true | .since = $now | .sets = {}
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
                               failures: [], stops: [], open: false, since: null, gaps: 0}
          elif $ev.verdict != null then
            {verdict: "rollback",
             reason: "R1 on set \($ev.verdict.set): \($ev.verdict.failures | length) counted failures with no proof of life between them\(if $ev.verdict.connect_only then " (connect-class only)" else "" end)",
             set: $ev.verdict.set, connect_only: $ev.verdict.connect_only, failures: $ev.verdict.failures,
             stops: $ev.stops, open: $ev.open, since: $ev.since, gaps: $ev.gaps}
          elif ($ev.stops | length) > 0 then
            {verdict: "stop", reason: "\($ev.stops[0].stop): \($ev.stops[0].reason)", set: null, connect_only: null,
             failures: [], stops: $ev.stops, open: $ev.open, since: $ev.since, gaps: $ev.gaps}
          else
            {verdict: "none",
             reason: (if $ev.open then "observing runner \($ev.version) since \($ev.since | C::utc)"
                      else "runner \($ev.version): no evidence window (the running process is not proven to run it)" end),
             set: null, connect_only: null, failures: [], stops: [], open: $ev.open, since: $ev.since, gaps: $ev.gaps}
          end))) as $out
    | {verdict: "ok",
       reason: "the log pass of \($tok.records | length) records\(if $owned then "" else " (the text before this boundary is UNKNOWN: it counts neither way)" end)",
       lines: [$out | to_entries[] | select(.value.reason != "no candidate under observation") | "\(.key): \(.value.reason)"],
       families: $out,
       state: ($state + {boundary: {owner: $owner, position: $facts.position}, carry: $tok.carry,
                         carry_at: $tok.carry_at, last_t: $done.last_t,
                         refused: $done.refused, families: ($obs | map_values(.ev))})}
  end
