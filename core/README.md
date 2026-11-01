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
                                        the captured position (the sha of the 64 bytes before it)
  "continuous": true | false,           the glue read the log from the state's boundary to the position with no
                                        loss: same file or the rotation followed, and the boundary's sha matched
  "config": {"installed": EPOCH, "lines": {"SET": "IMAGE", ...}},
                                        the config installed now and its install time (Studio: its mtime; the
                                        Linux host: the journaled `renamed` epoch)
  "families": {"FAMILY": {"provider": "tart" | "docker", "sets": ["SET", ...],
                          "candidate": {"version": "V", "lines": {"SET": "IMAGE", ...}, "closed_at": EPOCH} | null,
                          "back_until": EPOCH | null}},
                                        the candidate = the release under observation (switched, not accepted);
                                        back_until = after an ACCEPT, the end of the 7 days `back` restores the
                                        previous image (status.jq only)
  "stops": [{"family": "F", "stop": "NAME", "version": "V", "user": "USER" | null, "detail": {...}}]
                                        the STOPs the glue holds (status.jq, and keep.jq: any but NO EVIDENCE holds
                                        the family's ACCEPT; not a list is rc != 0); detail, as the STOP needs it:
                                        text (the failing line or step), hand (the hand line), failures and
                                        connect_only (r1's), counts (keep's), step "build" and build_user (the Linux
                                        host's build), jq {version, path}, reason
}
```

## The rules

**Ownership by position.** The captured position is a boundary of process P when `proc.before` and `proc.after` are
the same P (pid and start), else it is ambiguous. The text between the state's boundary and this one belongs to P
when both boundaries are P's and `continuous` is true; otherwise it is UNKNOWN: it counts neither way, and it is an
EVIDENCE GAP for every family under observation (its R1 counts, NOT SERVING and the KEEP clock restart; the shim's
unpaired refusals are dropped).

**Provenance.** P runs the config `facts.config` when `config.installed < P.start` (whole seconds; equal is not
proven). Family X's events count when the text is P's and P's config names X's candidate on every set of X. An
evidence window opens at a boundary of P with provenance (the KEEP clock starts at `now`); text after it counts. A
pass whose P has no provenance closes the window; the next one with provenance opens a new one.

**The log.** Records are runscaler's text format: `YYYY-MM-DD HH:MM:SS LEVEL [SET: ]MESSAGE key=value ...`,
multi-line values as `  key=` and `  │ ` lines (joined with newlines), and lines of other programs (a Docker pull)
ignored. A record is complete only when a following record header is read, so the last record of a pass is always
held to the next one (`state.carry`), also when the text ends with a newline: a record cut at the captured position
is never read from its first part. A held record that ends with a newline is read whole once the log has been quiet
for SETTLE (120 s of the glue's clock with the text unchanged, `state.carry_at`); a partial last line never is.

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
| `Runner removed reason=exited` with no `jobId` | yes (and it takes back that runner's `Runner started`), unless a `Job started\|completed for unknown runner (already removed?) runnerName=<that runner>` follows within SETTLE (PLAN D6 AMENDMENT, both providers: on the Linux host all 8 such removals were followed by it, 0-16 s later) |
| `Job started\|completed for unknown runner (already removed?)` naming a runner removed so | no: proof of life for the set; that runner's failure is not counted and its `Runner started` is proof again |
| `Runner exited before job completion` alone | no (unknown) |

Proof of life on a set: `Runner removed reason=job-completed`; the unknown-runner line above; on Tart also `Runner
started`, unless that runner is later removed `reason=exited` with no `jobId` (and no unknown-runner line takes that
back).

**SETTLE.** A counted failure is settled only when no proof of life can still arrive for it: a later record of the log
is 120 s of log time past it, or the log is quiet (no record held) and this pass's `now` is 120 s or more past the
`now` of the pass that read it. A failure that is not settled waits; nothing is judged from a partial second.

**R1.** Three SETTLED counted failures on one set with no proof of life on it between them → ROLLBACK of the family. A
proof in the same second as a failure counts as between them; a proof after the run does not take it back.
`connect_only` is true when every counted failure of that run is connect-class (CONNECT-ONLY: the glue retries once
after 1 h before it rejects the version). The verdict holds for the candidate; no STOP takes it back. A run of three
that is not settled yet is `pending` (r1's output and state): R1 may still come.

**NOT SERVING.** A family set that reads ready, idle ≥ 1, busy 0 and assigned ≥ 1 on every read for 30 min, with no
job completed on it: it counts as the set's third failure, connect-class. The reads measure the 30 min, never the
clock: at least 3 such reads (each at its pass's `now`) whose first and last are 30 min or more apart; a pass with no
`/healthz` read adds nothing. A read that is not like that (not ready included), a job completed on the set, or a gap
starts the 30 min again.

**KEEP.** 72 h after the evidence window opened: at least one `result=succeeded` → `accept`; completions (results
other than `canceled`) but none succeeded → `jobs-fail`; none → `no-evidence`. Before 72 h: `observe`. A family whose
R1 verdict or STOP stands, r1's own or one the glue holds in `facts.stops`: `held` (a person answers it: JOBS FAIL's
lines are `back` or `retry` to keep it). Only NO EVIDENCE heals itself: held or not, a later success accepts. KEEP never
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
