# core/r1.jq — the log pass (PLAN D6). Inputs: log (the text since the state's boundary, up to this pass's captured
# position), healthz (this pass's reads), facts, state, now. Output: verdict ok | wait; families.F = {verdict: none |
# rollback | stop, reason, set, connect_only, failures, stops, open, since, gaps, pending}; the new state (the boundary,
# the held record, the refused VMs, each observed family's evidence). Rules: core/README.md, "The rules".
#
# A family's evidence per set: fails (counted failures: t, s = its log second, c = connect-class, x, seen = the `now`
# of the pass that read it, settled), proofs (log seconds of proofs of life), starts (Tart `Runner started` of a runner
# not yet removed: a proof unless it is removed `reason=exited` with no jobId), exits (those removals, within SETTLE of
# log time, that a `Job started|completed for unknown runner` naming the runner still takes back; each holds the start
# it took back, a proof for R1 until the exit is final), ns (NOT SERVING), completed.
import "core" as C;
import "logfmt" as L;

def NS_SECONDS: 1800;
# SETTLE: a counted failure is settled when no proof of life can still arrive for it: a later record of the log is
# this far past it in log time, or the log is quiet (nothing held) and a later pass's `now` is this far past the `now`
# of the pass that read it. The same quiet reads a held record (the glue's clock, the text unchanged).
def SETTLE: 120;

# a log time "YYYY-MM-DD HH:MM:SS" -> seconds, compared only with other log times (the log's times have no zone: a
# clock that steps back more than SETTLE is an evidence gap, see read)
def lsec: strptime("%Y-%m-%d %H:%M:%S") | mktime;

def fresh($cand): {version: $cand.version, lines: $cand.lines, closed_at: $cand.closed_at, open: false, since: null,
                   gaps: 0, succeeded: 0, failed: 0, canceled: 0, other: 0, sets: {}, verdict: null, stops: [],
                   pending: null, newest: null};
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
  # a removal of a runner other than `reason=exited` with no jobId confirms its Tart start: the start is a proof, and
  # leaves .starts (which so holds only runners not yet removed)
  if $ev.k == "completed" then
    .sets[$s] = ((.sets[$s] // set0)
                 | ([.starts[] | select(.n == $ev.name) | .s] | max) as $st
                 | .proofs += [$sec, ($st // empty)] | .starts |= map(select(.n != $ev.name)) | .completed = true)
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
# that no unknown-runner line took back in time; .newest = the newest log second read (. = family evidence)
def settle_log($sec):
  .sets |= map_values(.fails |= map(if .settled != true and $sec - .s >= SETTLE then .settled = true else . end)
                      | .exits |= map(select($sec - .s < SETTLE)))
  | .newest = ([.newest, $sec] | max);

# SETTLE by the clock, when the log is quiet (nothing held): a failure read SETTLE or more before `now`. (An exit
# ends only by the log: a later unknown-runner line inside its SETTLE of log time still takes the failure back.)
def settle_quiet($now):
  .sets |= map_values(.fails |= map(if .settled != true and $now - .seen >= SETTLE then .settled = true else . end));

# . = one set's evidence -> the log seconds of its proofs of life: its proofs and its Tart starts not taken back
def barriers: [.proofs[]?, .starts[]?.s];

# ... and, for R1, the Tart start an exited removal took back while that exit is not final (its failure not settled):
# an unknown-runner line inside SETTLE may still give it back, so it is taken back only when none follows in SETTLE,
# the rule the D6 AMENDMENT gives the exit itself (Opus r3 F1). `pending` counts it taken back (KEEP waits)
def barriers_r1:
  . as $e
  | barriers + [.exits[]? | . as $x
                | select($x.start != null and any($e.fails[]?; .n == $x.n and .s == $x.s and .settled != true))
                | .start];

# $fs = failures, $b = log seconds of proofs of life -> runs: in log order, a new run starts at a failure when a proof
# of life lies between it and the one before (the same second as either = between)
def runs($fs; $b):
  reduce ($fs | sort_by(.s))[] as $f ([];
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
              | (.value | runs([.fails[] | select(.settled)]; barriers_r1))[] | select(length >= 3)
              | rollback($s; .)) // null) as $v
       | if $v != null then .verdict = $v else . end
  end;

# what can still matter (Codex r2 F4, Opus r2 F3, F5): $c = the newest proof (in .proofs, a Tart start not taken back
# excluded) at or before the oldest failure that is not settled yet (any, when all are), and SETTLE or more before the
# newest log second read: a record still to come may be written up to SETTLE out of order (what SETTLE rests on), so
# a failure still to come is never before $c (Opus r3 F3). Every failure before $c is settled and judged, and $c keeps
# it from every later one: it goes, unless a Tart start that may still be taken back is all that keeps it from R1 — a
# run of three or more with only Tart starts between them stays, with the first proof after it. A Tart start stays
# until its runner is removed. Proofs before $c go; $c's own second stays (same second = between)
def prune:
  .newest as $n
  | .sets |= map_values(
    ([.fails[] | select(.settled != true) | .s] | min) as $u
    | ([.proofs[] | select($n != null and . <= $n - SETTLE and ($u == null or . <= $u))] | max) as $c
    | if $c == null then .
      else .proofs as $b
        | ([.fails[] | select(.s < $c)] | sort_by(.s)
           | reduce .[] as $f ([]; (if length > 0 then .[-1][-1].s else null end) as $p
                                 | if $p != null and (any($b[]; . >= $p and . <= $f.s) | not) then .[-1] += [$f]
                                   else . + [[$f]] end)
           | map(select(length >= 3))) as $kept
        | .fails = ([$kept[][]] + [.fails[] | select(.s >= $c)])
        | .proofs = ([$kept[] | .[-1].s as $l | [$b[] | select(. >= $l)] | min] + [$b[] | select(. >= $c)] | unique)
      end);

# a run that can still reach R1 (KEEP waits for it): three counted failures, settled or not, with no proof of life
# between them, with $pot = {SET: [failures the held record may be]}
def pending($pot):
  if .verdict != null then null
  else first(.sets | to_entries | sort_by(.key)[] | .key as $s
             | (.value | runs(.fails + ($pot[$s] // []); barriers))[] | select(length >= 3)
             | {set: $s, failures: length, settled: ([.[] | select(.settled == true)] | length)}) // null
  end;

# . = family evidence: a window opens (the KEEP clock starts at $now; counts, NOT SERVING and the log times read start
# from zero)
def open_at($now): .open = true | .since = $now | .sets = {} | .pending = null | .succeeded = 0 | .failed = 0
                   | .canceled = 0 | .other = 0 | .newest = null;

# . = {obs, refused}: records $recs read for every family whose .[$flag] is true, by the pass of $seen ($now: this
# pass's). Each record settles by its log time; a partial record (a short write, read after SETTLE quiet or at P's exit)
# is only what a proof of life is, any other truncated record is unknown text. A record more than SETTLE before the
# newest log time read is no out-of-order write (SETTLE rests on those being less): the log's clock stepped back (it
# has no zone: summer time, or a clock set back), and the times before it cannot be compared with the times after it.
# It is an evidence gap (Opus r4 F2): what is settled is judged, then the window starts again at it, as after UNKNOWN
# text (counts, NOT SERVING, the KEEP clock), its log times (newest, the settle and prune points) from the new times
def read($recs; $flag; $seen; $now):
  reduce $recs[] as $r (.;
    ($r.t | lsec) as $sec
    | .obs |= map_values(if .[$flag] and .ev.newest != null and $sec < .ev.newest - SETTLE
                         then .ev |= (judge | .gaps += 1 | open_at($now)) else . end)
    | .obs |= map_values(if .[$flag] then .ev |= settle_log($sec) else . end)
    | if $r.set == null then .
      else
        .refused as $refused
        | reduce (.obs | to_entries[] | select(.value[$flag] and any(.value.sets[]; . == $r.set)) | .key) as $f (.;
            .obs[$f].provider as $prov
            | ($r | classify($prov; $refused)
               | if $r.partial == true and (.k != "completed" and .k != "start" and .k != "unknown") then {k: "none"}
                 else . end) as $ev
            | .obs[$f].ev |= apply($ev; $r.set; $r.t; $sec; $seen)
            | if $ev.k == "refused" then .refused = (.refused + $ev.vms | unique)
              elif $ev.k == "paired" then .refused -= $ev.vms
              else . end)
      end);

# . = a text; $b = a byte offset in it -> the index of the character that starts there (jq slices strings by
# character), or null when none does (inside a character, before the text or past it)
def char_at($b):
  . as $s
  | [0, ($s | length)]
  | until(.[0] >= .[1]; (((.[0] + .[1]) / 2) | floor) as $m
                       | if ($s[:$m] | utf8bytelength) < $b then [$m + 1, .[1]] else [.[0], $m] end)
  | .[0] as $i | if ($s[:$i] | utf8bytelength) == $b then $i else null end;

# the updater's own restart: the byte offset of `stopped` ($st) in this pass's text of $n bytes, which runs from the
# state's boundary ($bnd) to `position` ($pos), or null when it cannot be placed: on the boundary's file, the text holds
# exactly the $pos.offset - $bnd.offset bytes of it; when the log rotated (the glue read across it: continuous), the
# text is the boundary's file to its end and then the new file to `position`, and `stopped` is on one of the two (on
# the boundary's file, before that file's part of the text ends). Outside the text: null (char_at)
def stop_offset($bnd; $pos; $st; $n):
  if ([$bnd.offset, $pos.offset, $st.offset] | all(type == "number") | not) then null
  elif $bnd.inode == $pos.inode then
    (if $st.inode == $bnd.inode and $n == $pos.offset - $bnd.offset then $st.offset - $bnd.offset else null end)
  elif $pos.offset > $n then null
  elif $st.inode == $bnd.inode then
    (if $st.offset - $bnd.offset <= $n - $pos.offset then $st.offset - $bnd.offset else null end)
  elif $st.inode == $pos.inode then $n - ($pos.offset - $st.offset)
  else null end;

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
    # the updater's own restart (PLAN D6: its own switches leave no gap, and the text is owned by position): the glue
    # stopped the state's boundary process P, captured `stopped` once P had exited, then started this pass's process
    # Q. Text up to `stopped` is P's, after it Q's. One runscaler serves every family, so the restart is host-wide. A
    # restart fact whose from/to do not match the process reads, or whose `stopped` cannot be placed between the
    # boundary and `position`, is a foreign restart: a gap like any other
    | ($facts.restart // null) as $rs
    | (if (C::same_proc($prev; $owner) | not) and $rs != null and C::same_proc($rs.from; $prev)
          and C::same_proc($rs.to; $owner) and $facts.continuous == true
       then stop_offset($state.boundary.position; $facts.position; $rs.stopped; $log | utf8bytelength) as $b
            | if $b == null then null else ($log | char_at($b)) end
       else null end) as $split
    | ($split != null) as $own_restart
    | ($facts.families // {}) as $fams
    # each family with a candidate: its evidence (fresh for a new window) and provenance now (this pass's process)
    | ($fams | with_entries(select(.value.candidate != null)
        | .key as $f | .value as $fam
        | ($state.families[$f] // null) as $old
        | (if C::same_window($old; $fam.candidate) then $old else fresh($fam.candidate) end) as $ev
        | .value = {ev: $ev, prov: C::runs_candidate($owner; $facts.config; $fam), provider: $fam.provider,
                    sets: $fam.sets})) as $obs
    | (if $own_restart then
         # P's text: from the state's boundary to `stopped`, its held record first. P has exited, so it is all there:
         # read it whole, once, for every family whose window was open at the boundary (P ran its candidate)
         ((($state.carry // "") + $log[:$split]) | L::tokenize_final) as $tp
         | ($log[$split:] | L::tokenize) as $tq
         | {obs: ($obs | map_values(.p = .ev.open)), refused: ($state.refused // [])}
         | read($tp.records; "p"; $now; $now)
         # at `stopped`: a window whose candidate Q does not run is judged on P's text and closes (a gap); a family
         # whose candidate Q runs counts Q's text, in its open window or in one that opens here
         | .obs |= map_values(if .ev.open and (.prov | not) then .ev |= (judge | .gaps += 1 | .open = false)
                              elif (.ev.open | not) and .prov then .ev |= open_at($now)
                              else . end
                              | .q = .prov)
         | read($tq.records; "q"; $now; $now)
         | {done: ., tok: {records: ($tp.records + $tq.records), carry: $tq.carry,
                           carry_at: (if $tq.carry == "" then null else $now end)}}
       else
         # an open window that does not count this interval (the text is not its process's, or the process does not
         # run its candidate): an evidence gap. It closes the window; the window that opens again starts its counts,
         # NOT SERVING and the KEEP clock from zero
         ($obs | map_values(.q = (.ev.open and $owned and .prov)
                            | if .ev.open and (.q | not) then .ev |= (.gaps += 1 | .open = false) else . end)) as $obs
         # the text: the record held at the last pass, then this interval's. The last record is held to the next pass
         # (it may yet grow); once the log has been quiet for SETTLE it is read as it is. runscaler writes a record
         # with one write, so a held text still partial then is a short write (a full disk): its partial record counts
         # only as a proof of life (Codex r2 F2, Opus r2 F4: a partial line must not hold R1 for ever)
         | (if $owned then
              ($state.carry // "") as $c0
              | if $log == "" and $c0 != "" and ($state.carry_at | type) == "number" and $now - $state.carry_at >= SETTLE
                # read now, as of the pass that held it unchanged
                then ($c0 | L::tokenize_final) + {carry_at: null, seen: $state.carry_at}
                else ($c0 + $log | L::tokenize) as $t
                     | $t + {carry_at: (if $t.carry == "" then null elif $t.carry == $c0 then ($state.carry_at // $now)
                                        else $now end), seen: $now}
                end
            else {records: [], carry: "", carry_at: null, seen: $now} end) as $tok
         | {done: ({obs: $obs, refused: (if $owned then ($state.refused // []) else [] end)}
                   | read($tok.records; "q"; $tok.seen; $now)),
            tok: $tok}
       end) as $pass
    | $pass.done as $done
    | $pass.tok as $tok
    # the record still held may be a counted failure of a family set: R1 may still come with it (KEEP waits). A held
    # text that ends in a partial line may hold the start of one more record, on any set
    | ($tok.carry | if . == "" then [] else L::tokenize_final.records end) as $held
    # the end of the pass, for every family that counts this pass's (last) text: SETTLE by the clock when nothing is
    # held, then R1 on the settled failures, then what can no longer matter goes, then the run that may still reach R1
    | ($done.obs | map_values(
        if .q then
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
    | ($obs0 | map_values(if (.ev.open | not) and .prov then .ev |= open_at($now) else . end)) as $obs
    # NOT SERVING, from this pass's reads (each read at this pass's `now`), on the sets of an open window whose process
    # runs the candidate: at least 3 NOT SERVING reads whose first and last are NS_SECONDS or more apart, no other read
    # between them. The reads measure the 30 min, never the clock: a pass with no read adds nothing (Opus r1 F2)
    | ($obs | map_values(
        if .ev.open and .prov then
          .sets as $sets
          | .ev |= (reduce $sets[] as $s (.;
                .sets[$s] = ((.sets[$s] // set0)
                  | (if .completed then .ns = null else . end)
                  | reduce $reads[] as $rd (.;
                      if ($rd | ns_read($s)) then .ns = ((.ns // {first: $now, reads: 0}) | .reads += 1 | .last = $now)
                      else .ns = null end))
                | if .verdict == null and .sets[$s].ns != null and .sets[$s].ns.reads >= 3
                     and .sets[$s].ns.last - .sets[$s].ns.first >= NS_SECONDS
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
       reason: "the log pass of \($tok.records | length) records\(if $owned then "" elif $own_restart then " (the updater's own restart: P's text to `stopped`, then Q's)" else " (the text before this boundary is UNKNOWN: it counts neither way)" end)",
       lines: [$out | to_entries[] | select(.value.reason != "no candidate under observation") | "\(.key): \(.value.reason)"],
       families: $out,
       state: ($state + {boundary: {owner: $owner, position: $facts.position}, carry: $tok.carry,
                         carry_at: $tok.carry_at, refused: $done.refused, families: ($obs | map_values(.ev))}
               | del(.last_t))}
  end
