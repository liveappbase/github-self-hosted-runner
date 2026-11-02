# The decision core

The runner-image updater's decisions, as jq programs: ONE copy for both hosts (the Studio's zsh glue and the Linux
host's bash glue call the same files). A program reads facts and prints one verdict. It does no I/O beyond its
inputs: no clock (the glue passes `now`), no file, no network. The glue measures, asks the core, journals, acts.

| Program | Decides |
|---|---|
| `idle.jq` | IDLE: may the host's runscaler be stopped now (two `/healthz` reads 3 s apart, every set) |
| `r1.jq` | the log pass: ownership by position, provenance, the classification table, R1 and NOT SERVING, per family |
| `keep.jq` | KEEP: ACCEPT, JOBS FAIL ON THE NEW IMAGE, NO EVIDENCE, per family (reads only the state r1 wrote) |
| `status.jq` | the STOP table: each STOP's line, next step and properties; the evidence lines |
| `lib/logfmt.jq` | runscaler's log text (charm log v2, text format) into records; shared by the programs |
| `lib/core.jq` | the formats, the state's shape, provenance and the time format; shared |
| `lib/stops.jq` | the STOP table (PLAN D7), ONE copy: status.jq prints its properties, keep.jq reads it |

The jq builds they are tested with: [TESTED_JQ](TESTED_JQ). The glue refuses new work under another jq ("untested
jq", a STOP).

## The call

```
jq -n -L <repo>/core/lib -f <repo>/core/<program>.jq \
   --slurpfile state <file> --slurpfile facts <file> --rawfile log <file> --slurpfile healthz <file> --arg now <epoch>
```

- Each program reads only the inputs it names below; the others may be passed and are ignored, so the glue may pass
  the same five to every program. An input a program needs and did not get: rc != 0.
- `now`: the glue's UTC clock, whole seconds since the epoch, in [1700000000, 4102444800); anything else (a clock in
  milliseconds, 1e999, a clock that never ran) is rc != 0 on every program. The core never compares a log time with it
  (the log's times have no zone): log times are compared only with each other, and `now` only with an earlier `now`.
- `state`: the core's own state, the `state` member of the program's last output (an EMPTY file = a fresh state).
- `facts`: what the glue measured or holds this pass (below). Its `format` must be 1, else rc != 0.
- `log`: the log text from the state's boundary to this pass's captured position (no byte past it).
- `healthz`: the `/healthz` reads of this pass, oldest first (one JSON document per read, in one file).

Output: ONE JSON object on stdout:

```
{"verdict": "...", "reason": "...", "lines": ["...", ...], "families": {...}, "state": {...}}
```

`verdict`, `reason` and `lines` are always there; `lines` are status text, one line each. `families` (r1, keep):
the verdict per family. `state` (idle, r1): the new state; the glue writes it back by rename, and a later program of
the same pass reads it. rc != 0 = the core could not decide: the glue does nothing this pass and says so in status.

A state whose `format` is not 1 (a newer or older updater wrote it): verdict `wait`, one status line, the state
returned unchanged, rc 0.

## facts (format 1)

```
{
  "format": 1,
  "host": "studio" | "hz",
  "sets": ["SET", ...],                 every set of the config runscaler runs (IDLE covers them all); idle.jq:
                                        missing, empty or not a list of names is rc != 0
  "proc": {"before": {"pid": N, "start": EPOCH} | null,
           "after":  {"pid": N, "start": EPOCH} | null},
                                        runscaler read before, and again after, the log position was captured;
                                        a read that is not null and not {pid: a positive integer, start: a number}
                                        is rc != 0 on every program (it would prove ownership it does not have)
  "position": {"inode": "...", "offset": N, "sha": "..."},
                                        the captured position: the log file's inode, the byte offset in it, the
                                        sha of the 64 bytes before it
  "continuous": true | false,           the glue read the log from the state's boundary to the position with no
                                        loss: same file or the rotation followed, and the boundary's sha matched
  "restart": {"from": {"pid": N, "start": EPOCH}, "to": {"pid": N, "start": EPOCH},
              "stopped": {"inode": "...", "offset": N, "sha": "..."}} | null,
                                        the updater's OWN restart in this interval (r1.jq): the glue stopped
                                        runscaler `from` itself, waited until it had exited, captured the log
                                        position then (`stopped`, the shape of `position`: the inode, the byte
                                        offset, the sha of the 64 bytes before it, checked by the glue as it checks
                                        `position`), then started `to` and saw it running. Set on the pass after the
                                        restart (a switch, a rollback, a RECOVER), else null or absent. Not null and
                                        not two process reads and a position: rc != 0 on every program
  "config": {"installed": EPOCH, "lines": {"SET": "IMAGE", ...}},
                                        the config installed now and its install time (Studio: its mtime; the
                                        Linux host: the journaled `renamed` epoch)
  "families": {"FAMILY": {"provider": "tart" | "docker", "sets": ["SET", ...],
                          "candidate": {"version": "V", "lines": {"SET": "IMAGE", ...}, "closed_at": EPOCH} | null,
                                        (closed_at: when the switch window closed; a retry's new window has its
                                        own, so its evidence and verdict start fresh)
                          "back_until": EPOCH | null}},
                                        the candidate = the release under observation (switched, not accepted);
                                        back_until = after an ACCEPT, the end of the 7 days `back` restores the
                                        previous image (status.jq only)
  "stops": [{"family": "F", "stop": "NAME", "version": "V", "user": "USER" | null, "detail": {...}}]
                                        the STOPs the glue holds (status.jq, and keep.jq: see KEEP; not a list is
                                        rc != 0; one with no family, or "", holds every family); version: the release the
                                        STOP is of; detail, as the STOP needs it:
                                        text (the failing line or step), hand (the hand line), failures and
                                        connect_only (r1's), counts (keep's), step "build" and build_user (the Linux
                                        host's build), jq {version, path}, reason
}
```

## The rules

**Ownership by position.** The captured position is a boundary of process P when `proc.before` and `proc.after` are
the same P (pid and start), else it is ambiguous. The text between the state's boundary and this one belongs to P
when both boundaries are P's and `continuous` is true; across the updater's own restart it is P's up to `stopped` and
Q's after it (below); otherwise it is UNKNOWN: it counts neither way, and it is an EVIDENCE GAP for every family under
observation (its R1 counts, NOT SERVING and the KEEP clock restart, and counting pauses: **Evidence gaps**; the shim's
unpaired refusals are dropped).

**The updater's own restart is no gap, and nothing in it is dropped** (PLAN D6: its own switches leave no gap; another
family's window does not end X's evidence). When `facts.restart` says the glue restarted runscaler from P to Q in this
interval, P is the state's boundary process, Q this pass's, `continuous` is true and `stopped` lies between the
boundary and `position`, the text is split at `stopped` by ownership: up to it is P's (P was the only runscaler and has
exited, so P's held record is complete and is read once, with P's provenance: for every family whose window was open at
the boundary), after it Q's. The restart is host-wide (one runscaler serves every family): every open window whose
candidate Q's config still names stays open with its counts, failures, pending run, NOT SERVING and KEEP clock, and
counts Q's text too; a window whose candidate Q does not run is judged on P's text and closes (a gap); a family whose
candidate Q runs and whose window is not open (the family the restart switched) opens it at `stopped` and counts Q's
text. `stopped` lies between when it is on the boundary's file and the text holds exactly `position.offset -
boundary.offset` bytes of that file, or, when the log rotated in the interval (runscaler may rotate at Q's first
write), when it is on the boundary's file within that file's part of the text, or on the new file at or before
`position`. Offsets are bytes; the text is split at the character that starts there. Otherwise, or with no such fact,
or a `from` or `to` that does not match the process reads, it is a foreign restart: a gap.

**Provenance.** P runs the config `facts.config` when `config.installed < P.start` (whole seconds; equal is not
proven). Family X's events count when the text is P's and P's config names X's candidate on every set of X. An
evidence window opens at a boundary of P with provenance (the KEEP clock starts at `now`); text after it counts. At the
updater's own restart the window opens at `stopped` (the KEEP clock still starts at `now`). A
pass whose P has no provenance closes the window; the next one with provenance opens a new one.

**The log.** Records are runscaler's text format: `YYYY-MM-DD HH:MM:SS LEVEL [SET: ]MESSAGE key=value ...`,
multi-line values as `  key=` and `  │ ` lines (joined with newlines), and lines of other programs (a Docker pull)
ignored. A record is complete only when a following record header is read, so the last record of a pass is always
held to the next one (`state.carry`), also when the text ends with a newline: a record cut at the captured position
is never read from its first part. A held record is read once the log has been quiet for SETTLE (120 s of the glue's
clock with the text unchanged, `state.carry_at`). runscaler writes each record with one write, so a held text that
still ends in a partial line then is a short write (a full disk): the record that line belongs to is read only as what
a proof of life is (a job completed, a Tart start, an unknown-runner line); any other truncated record is unknown text,
never a counted failure or a STOP. A partial line that can still become a continuation line is one cut short (` `,
`  `, `  err`, `  ` and a cut `│`, and right after a value line ` nam` or ` name=x`) and belongs to the record before
it; a cut header or another program's line, also one that starts with a space (` ---> Running in …`, or ` name=x`
after a line that is no value line: charm writes ` key=value` only right after a value line), leaves the record before
it whole (it was written with its newline). So a partial line never holds R1: the failures before it
settle. A short write that ends exactly at a newline leaves no partial line: the lines before it are read as a whole
record (a counted failure when they say one). The cuts the text cannot show end right after a value line (`  │ …`)
or a ` key=value` line (the value or the keys may have ended there), or right after a header whose message may have
no more lines. Two cuts at a newline that the text could show are read as whole records too: right after the header
of a `Failed to start runner` with no `error` (runscaler always writes one) and right after a `  key=` line (a `  │ `
line always follows one).

**The classification** (a record of a set of family X, with provenance):

| Record | Counted |
|---|---|
| `Failed to start runner` whose error holds `liveapp-ci-shim: REFUSE` | no: STOP SHIM REFUSED |
| any record holding `liveapp-ci-shim: REFUSE` (e.g. `VM exited unexpectedly`) | no: STOP SHIM REFUSED; its VM names wait in the state |
| `Failed to start runner` that names a waiting refused VM | no (paired; the VM leaves the state) |
| `Failed to start runner`: `failed to generate JIT config` | no |
| `Failed to start runner` on Tart: `is deprecated and cannot receive messages` | no: STOP PINNED RUNNER RETIRED |
| `Failed to start runner`: `runner process exited on VM before / right after connecting to GitHub` | yes, connect-class; no if its runner log holds `no longer exists on the server` |
| `Failed to start runner`: `did not connect to GitHub within` | yes, connect-class |
| `Failed to start runner`: `failed to create / start runner container` | yes |
| any other `Failed to start runner` | yes |
| `Runner removed reason=exited` with no `jobId` | yes (and, once it is final, it takes back that runner's `Runner started`), unless a `Job started\|completed for unknown runner (already removed?) runnerName=<that runner>` comes less than SETTLE - ORDER (110 s) before or after it, by their own log times: such a partner, written at most ORDER late, is read before any record SETTLE past the other one, so before any failure the pair could separate settles, and where a pass ends changes no verdict; one 110 s away or more is no partner (each waits SETTLE + ORDER of log time for the other) (PLAN D6 AMENDMENT, both providers: on the Linux host all 8 such removals were followed by it, 0-16 s later; runscaler logs the removal only after RemoveInstance, so a job message in between logs the line first) |
| `Job started\|completed for unknown runner (already removed?)` naming a runner removed so | no: proof of life for the set, each such line at its own log time, before or after the removal (a job's started and completed lines can lie apart); that runner's failure is not counted and its `Runner started` is proof again (it is not taken back) |
| `Runner exited before job completion` alone | no (unknown) |

Proof of life on a set: `Runner removed reason=job-completed`; the unknown-runner line above; on Tart also `Runner
started`, unless that runner is later removed `reason=exited` with no `jobId` and no unknown-runner line takes that
back. The removal takes the start back only when it is final, by the same rule as its own failure: no such line comes
less than SETTLE - ORDER (110 s) after it before its failure settles (by the log SETTLE + ORDER past it, or by the
clock); a line inside that window, written at most ORDER late, is always read before then. Until then the start is still a proof of life for R1,
so where a pass's capture falls between the removal and the unknown-runner line changes no verdict; `pending` counts
the start as taken back (KEEP waits for the removal to be final).

**SETTLE.** A counted failure is settled only when no proof of life can still arrive for it: a later record of the log
is 120 s of log time past it (an exited removal's: SETTLE + ORDER, 130 s, as its unknown-runner line may still be read
ORDER late), or the log is quiet (no record held) and this pass's `now` is 120 s or more past the
`now` of the pass that read it. A failure that is not settled waits; nothing is judged from a partial second.

**ORDER and the log's clock.** runscaler stamps a record when it logs it and writes it under one lock, so records
reach the log out of order only by goroutine scheduling: well under a second (the Linux host's real log: 0 records out
of order in 4,455). The core claims no more than ORDER = 10 s of log time: a record more than ORDER before the newest
log time read is outside what it reads, an EVIDENCE GAP (below). That is a record written far out of order, or a log
clock that stepped back (runscaler stamps local time with no zone: summer time ended, or the clock was set back), and
the times before it cannot be compared with the times after it. The gap: the failures settled before it are judged
first (R1 may come), but only those whose settlement the step's record does not contradict (the failure lies more than
ORDER after it, in the clock's old times, or the step's record is itself SETTLE past it; a failure near it was settled
only by a record it contradicts, such as one stamped before a step back and written after it); then the window starts
again at it, as after UNKNOWN text (its counts, NOT SERVING and the KEEP clock from zero, at the pass that reads it;
the other failures go; counting pauses), and every log time it keeps (the newest read, the settle and prune points)
starts from the new times. A record whose header the pass holds (its time is whole) is read first by the next pass, so
a step back it shows is judged at the end of the pass that holds it as that step will judge it. That is all a held
step changes: a run whose last failure is settled only in the pass that reads a step back may be dropped there, where a
capture that ended before the step judged it (Opus r6 F3: the safe direction, a real R1 lost, never a false one;
TZ=UTC removes the step). A record ORDER or less out of order is no gap. A clock that steps forward is no gap: the
first record after it settles the failures before it, as any later record does. SETTLE is not disorder: it is how long
a later proof may take to arrive.

**Evidence gaps.** A gap is a record more than ORDER before the newest log time read, UNKNOWN text (a foreign restart
included), or a window the updater's own restart closes; the window's first opening and the own restart are none. A
gap judges what settled before it (above), then the window starts again and counting pauses for SETTLE + ORDER (130 s)
of log time from an anchor: a counted failure (a start failure, an exited removal) stamped less than 130 s after it is
not counted (operator decision O8). The anchor is the later of the gap's record (the first record the window reads
after the gap) and the newest log time read before the gap (a later gap before that keeps the later anchor). Why: the
gap drops the window's evidence, and with it the half of a pair read before it (a proof between failures read after
it; an exited removal whose unknown-runner line comes after it; a line whose removal comes after it, Opus r6 F2).
Everything it drops is stamped at most the newest log time read before it, and a partner lies less than 110 s from it,
so every failure it could join wrongly lies in the pause, however late the gap's record was written. A step back of D s
so pauses D + 130 s of the new clock (TZ=UTC, below, leaves only a clock set back). Everything else still applies in
the pause: proofs, completions, STOPs, Tart starts, the pairing lists, NOT SERVING. The pause is in the state (one value
per family), so it holds across passes. A real run still rolls back once the pause ends; gaps that keep coming hold R1
off while they last (the plan's O7 residual; status shows the gap count).

The glue MUST run runscaler with `TZ=UTC` (on Linux in the service unit's `Environment=`, on macOS in the launchd
plist's `EnvironmentVariables` or the script it starts): then its log times never step back with summer time. The core
turns a step back that it sees into a gap, but it cannot see every step. An idle runscaler writes about one record an
hour (the Linux host: every 58 to 60.5 min), so a one-hour step back in an idle hour can show as ORDER or less back, or
not at all; the records on the two sides of it are then read as one stretch of time, and failures from both sides can
meet in one run (a false R1).

**R1.** Three SETTLED counted failures on one set with no proof of life on it between them → ROLLBACK of the family. A
proof in the same second as a failure counts as between them; a proof after the run does not take it back.
`connect_only` is true when every counted failure of that run is connect-class (CONNECT-ONLY: the glue retries once
after 1 h before it rejects the version). The verdict holds for the candidate's window; no STOP takes it back. A
window is the candidate's version, lines AND `closed_at`: a retry that switches to the same lines in a new window
(a new `closed_at`) starts fresh evidence, with no verdict (r1 and keep alike). A run of three
that is not settled yet is `pending` (r1's output and state): R1 may still come.

**The state stays bounded.** Per set, r1 keeps only what can still matter: the newest proof of life that is at or
before the oldest failure not settled yet (any, when every failure is settled) and SETTLE or more before the newest log
time read — a record still to come is at most ORDER out of order (one more is a gap), so a failure still to come is
never before that proof — and everything from its second on (the failures and proofs of the last SETTLE of log time,
the newest proof before them, and the settled failures since that proof: at most two, a third is R1); the Tart starts
of runners not yet removed, at most 16 (a runner leaves by a `Runner removed` line, also at runscaler's stop,
`reason=shutdown`, but one whose RemoveInstance fails never does: beyond 16, the oldest start is read as confirmed, a
proof of life, which loses only a take-back and so can only delay R1; Apple allows 2 macOS VMs per host); the
runs of three or more settled failures that only such a start keeps apart (R1 if it is taken back), each with the
first proof after it; and the exited removals and the unknown-runner lines of the last SETTLE + ORDER of log time. Everything
else before that proof is settled and judged, and the proof keeps it from every later failure. So a set's entries are
bounded by what it logs in SETTLE (plus a pass's records not yet settled by the clock) and by 16 starts, never by the
hours, and neither is a pass's time.

**NOT SERVING.** A family set that reads ready, idle ≥ 1, busy 0 and assigned ≥ 1 on every read for 30 min, with no
job completed on it: it counts as the set's third failure, connect-class. The reads measure the 30 min, never the
clock: at least 3 such reads (each at its pass's `now`) whose first and last are 30 min or more apart; a pass with no
`/healthz` read adds nothing. A read that is not like that (not ready included), a job completed on the set, or a gap
starts the 30 min again.

**KEEP.** 72 h after the evidence window opened: at least one `result=succeeded` → `accept`; completions (results
other than `canceled`) but none succeeded → `jobs-fail`; none → `no-evidence`. Before 72 h: `observe`. A family whose
R1 verdict or STOP stands, r1's own or one the glue holds in `facts.stops`: `held` (a person answers it: JOBS FAIL's
lines are `back` or `retry` to keep it). Only NO EVIDENCE heals itself: held or not, a later success accepts. A held
STOP holds every family when it names none (no `family`, `""`, or one that is not a name: fail closed, as for
`version`).
It holds the candidate only when it is of the candidate's `version` (or names none: no `version`, `""`, or one that is
not a string), or when its D7 row says a newer
release does NOT proceed alone (`lib/stops.jq`): check failed, ROLLED BACK and PINNED RUNNER RETIRED of an older version
closed that version's candidate, and a newer release proceeds alone past them. KEEP never
accepts while r1's `pending` stands (three counted failures, not all settled, the held record counted as one when it
may be): `observe` until they settle.

**IDLE.** Over every set in `facts.sets` (required: IDLE is never said of nothing) and every set the reads list: two
reads; each set present with `metrics` on both (a read that does not list a set of `facts.sets` is not idle:
runscaler lists no set before they register), `ready` on both (a set read not ready for 24 h is excused from READINESS
only), and idle, busy, provisioning, removing, available, assigned, running and desired all 0 on both (an absent key
reads 0).

## The programs' outputs

- `idle.jq` (healthz, facts, state, now): verdict `idle` | `not-idle` | `wait`; a line per set that blocks and per
  excused set; `state.not_ready_since` (when each set was first read not ready). The glue calls it every pass with
  that pass's read, so the 24 h are measured; a pass with fewer than two reads is never `idle`.
- `r1.jq` (log, healthz, facts, state, now): verdict `ok` | `wait`; `families.F` = `{"verdict": "none" | "rollback" |
  "stop", "reason", "set", "connect_only", "failures", "stops", "open", "since", "gaps", "pending"}` (`rollback`
  outranks a STOP; `stops` = `[{"stop", "reason"}]`; `pending` = `{"set", "failures", "settled"}` or null); the new
  state.
- `keep.jq` (facts, state, now): verdict `ok` | `wait`; `families.F` = `{"verdict": "none" | "observe" | "accept" |
  "jobs-fail" | "no-evidence" | "held", "reason", "since", "keep_at", "succeeded", "completions", "failed",
  "canceled"}`.
- `status.jq` (facts, state, now): verdict `ok` | `wait`; `stops`: one object per STOP (`family`, `stop`, `version`,
  `known`, `closes_candidate`, `rejects`, `newer_proceeds`, `line`), the glue's STOPs and then the core's own (r1's
  SHIM REFUSED and PINNED RUNNER RETIRED) unless the glue already holds them; `lines`: the STOP lines, the evidence
  lines, then each `back_until`. The STOP table is PLAN D7's; `rejects` is `after-retry` for a connect-class-only
  ROLLED BACK. SHIM REFUSED has no row in D7 (D6 names it): candidate not closed, version not rejected, a newer
  release does not proceed alone. A STOP this core does not know: `known` false, its properties null, never guessed.
