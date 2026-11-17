# Upgrading runscaler: the read points and the procedure

runscaler (ysya/runscaler) moves fast, and each host pins its own version:

- the Studio: `setup/downloads.manifest`, the `runner-darwin-arm64.tar.gz` line (v0.22.1 when this file was written);
- the Linux host: `linux-docker/setup/03-runscaler.sh`, `PINNED=` (v0.22.0 when this file was written).

A read point is a place where this repository's code depends on what runscaler writes or does: a log message and its
keys, a `/healthz` field, a `runner validate` line, a config key, or an interface. The tables below list them, one half
per host. Rows marked SHARED are read by the shared `core/`, so they hold for both hosts.

## The procedure for an upstream bump

Every version a host runs is a pin in a reviewed release of this repository that a person merges. An upstream bump is
a pull request that changes that host's pin.

1. Read the upstream diff from the host's pinned version (FROM) to the new one (TO), the whole tag range, with
   `git diff --no-color FROM TO` in a clone of ysya/runscaler. Check that it printed hunks (a diff with no hunk, or one
   that says a file is binary, is no answer: read the files).
2. Check each row of that host's half and every SHARED row against the diff: a changed literal or key, a change in a
   named function or declaration block (a `var`, `const` or `type` block, such as a key list), a removed or renamed file,
   or a NEW call site of the same kind in any file (a new Tart call, a new log message our rules would need), and the
   listed `go.mod` modules.
3. No row is touched: the bump is a pin change with no behaviour change for this host. One build round and one review
   round, then a person merges it, and the host installs the merged release. On the Studio, until its own runscaler
   install path exists, that install is an attended move: a person's step.
4. A row is touched: the full plan and review rounds for the touched rows, before the pin moves. Add or change the rows
   the change needs in the same pull request.
5. Write what you read into the pull request: FROM, TO, the rows you checked, and each hit or "no hit".

The tables are a checklist for a reader, not the input of a tool: a row says where to look and what breaks if it
changes. A new read point in this repository's code gets its row in the same pull request that adds it.

## The Studio's read points (owner: the Studio's maintainers)

Upstream paths are as at v0.22.1; "ours" is this repository unless a row names the Studio's move script
(`steps.zsh`, kept by the Studio's maintainers). Line numbers are hints: look for the literal in the named file.

### 1. Log messages the core and the move read (runner.log, charm text form)

| upstream file | literal | ours | if it changes |
|---|---|---|---|
| internal/controller/controller.go | `Runner removed` (keys name instanceID reason jobId repo workflowRunId job result) | core/r1.jq (Runner removed rule), logfmt | R1 misses removals (SHARED) |
| internal/controller/state.go | reasons `job-completed` `exited` `readiness-failed` `scaled-down` | core/r1.jq; steps.zsh m8 (`readiness-failed`) | R1 classifies wrong (SHARED) |
| internal/controller/controller.go | `Runner started` (keys name instanceID startupTime) | core/r1.jq; logfmt; steps.zsh m6 (`$5 == "Runner" && $6 == "started" && $7 ~ /^name=runner-/`) | proof of life + m6 lost (SHARED) |
| internal/controller/controller.go | `Job started for unknown runner (already removed?)`, `Job completed for unknown runner (already removed?)` | core/r1.jq | bug #15 watch blind (SHARED) |
| internal/controller/controller.go | `Failed to start runner, will retry` | core/r1.jq; logfmt | start-failure count lost: this is where an Apple 2-VM fault shows (SHARED) |
| internal/controller/controller.go | `failed to generate JIT config` | core/r1.jq | (SHARED) |
| internal/controller/controller.go | `deregister runner`, `cannot safely deregister runner with unknown ID` | steps.zsh m8 | m8 blind |
| internal/controller/controller.go | `Runner exited before job completion; scheduling cleanup` | logfmt (dead entry: old text `…; removing stale capacity`) | none today |
| internal/provider/tart.go | `runner process exited on %s before connecting to GitHub`, `… right after connecting to GitHub`, `did not connect to GitHub within`, `runner readiness check failed on %s` | core/r1.jq (connect / non-connect class) | R1 classifies wrong (SHARED) |
| internal/provider/tart.go | `VM exited unexpectedly` | logfmt | |
| internal/provider/tart.go | `Failed to set fixed MAC (will use random)` | read by a person | a HOME/TART_HOME fault hides |
| cmd/runner/tart_guests.go | `Detected Tart guest` (slog: `msg="Detected Tart guest" image=X os=Y`; charm: `INFO  Detected Tart guest image=X os=Y`) | steps.zsh m3, m7 | guest check lost |
| (log writer) internal/config/logfile.go, the charm handler | the 5-wide level column (`INFO `, `WARN `, `ERROR`), `<set>: ` prefix, time form `YYYY-MM-DD HH:MM:SS ` (host local time, no zone) | core reader (logfmt), steps.zsh m7, log_since (m6/m8) | every log read (SHARED) |
| internal/config/logfile.go | APPEND on start; rotate at 10 MiB to ONE `runner.log.1` | steps.zsh m8 (reads .1 then the log), bin/runner-updater RUNLOG | m8's "reach back" rule |
| cmd/runner/logpath.go | `log-file` used as written for a non-system process; `Warning: cannot open log file` | config.toml.example:5; ru_config | log lands elsewhere |

### 2. /healthz (JSON)

| upstream file | literal | ours | if it changes |
|---|---|---|---|
| internal/health/health.go | field names `ready idle busy provisioning removing`, `metrics.available_jobs assigned_jobs running_jobs desired_runners`, `last_error`, `failure_reason`; HTTP 200 always | bin/runner-updater-lib ru_healthz; core/idle.jq; core/r1.jq (NOT SERVING); bin/runner-updater-window (START STATE, idle pair); steps.zsh hz_summary, m0, m5, m8 | idle detection and readiness checks (SHARED) |
| internal/health/health.go, internal/controller/runtime.go | `ready` = ready && !draining && !degraded (the Degraded rule) | the same | a set reads ready when it is not |
| cmd/runner/main.go | health address default 127.0.0.1:8080 | steps.zsh HZ | reads fail |

### 3. `runner validate` (stdout text, exit code)

| upstream file | literal | ours | if it changes |
|---|---|---|---|
| cmd/runner/cmd_validate.go, cmd/runner/scaleset.go | `  ✗ scaleset[N] "…" GitHub API: ` (api_re), `  ✗ (config: \|global config: \|scale set collection: \|scaleset[N] "…": )` (config_re), `  ✓ … GitHub API is reachable; scale set registered`, `All checks passed.`; exit 1 on any failure | bin/validate-class (classes PASS / API-ONLY / NON-API / UNKNOWN; zsh copy AND linux-docker/bin bash copy) | a failure reads as PASS (SHARED via the shared fixtures) |
| cmd/runner/tart_guests.go | `  ✓ scaleset[N] "…" Tart guest: <os>`, `  ✗ scaleset[N] "…" Tart image check: `, `  ✗ detect guest OS of Tart image`, `  - … detected at startup (image not pulled; …)`, the macOS min-runners / pool-size lines | bin/validate-class; steps.zsh m3 (one guest line per set) | |
| cmd/runner/scaleset.go | the API probe timeout (5 s) and the CONFIGURED group probe | the three-API-ONLY = PASS rule | API-ONLY rate |
| cmd/runner/main.go | exit codes 1/0; `run` fails at start on a detection or macOS min/pool error (stderr) | bin/runner-start, runner-start.err | |

### 4. Interfaces (any change in the named place = a person's step)

| upstream file | interface | ours | why |
|---|---|---|---|
| internal/provider/tart.go, internal/provider/tart_guest_network.go, internal/cachestore/tart.go, cmd/runner/main.go | every `"tart", "<subcommand>"` call and `runArgs` (`run NAME --no-graphics`, `--net-bridged=` only when set), `set --cpu/--memory`, `prune`, `list --format json`, guest `exec`s | bin/tart-shim (admits only `run runner-<8 hex> --no-graphics`, passes `list pull clone set get stop delete exec prune ip`, REFUSEs others) | a new subcommand or a new run arg is REFUSED by the shim: CI stops |
| internal/provider/tart_guest.go | Tart home: `[tart] home`, else `$TART_HOME`, else `~/.tart`; config.json at `<home>/vms/<name>/config.json` | bin/runner-start (PATH, no HOME), bin/tart-shim (HOME=/Users/ci) | guest detection fails |
| internal/provider/tart.go | the host coordinator: one slot per live VM, MAC `02:`+index, written before `run` | bin/tart-shim `set --random-mac` after it | MAC conflict |
| internal/provider/tart.go, cmd/runner/tart_guests.go | macOS VM limit (2 per host, Apple), `concurrent` lease, per-set `max-runners`, the macOS permit | config (concurrent 2 now, 4 at N1) | capacity, start failures |
| internal/provider/tart.go | Tart readiness: `tart exec <vm> true` (2 min), `test -x <runner-dir>/run.sh`, `nohup <runner-dir>/run.sh`, `pgrep -f Runner.Listener`, `grep -q "Listening for Jobs" /tmp/runner.log` (5 min) | bin/linux-image-build (run.sh wrapper, /opt/liveapp-runner), the golden image | a VM never becomes ready |
| internal/provider/tart_network.go, internal/provider/tart_guest_network.go | DNS (`dns = []` keeps Tart's resolver), MTU auto (`/sbin/route -n get github.com`; guest `sudo -n ip link set … mtu`) | Linux set config (`dns []`, no mtu), the image's sudo | new guest commands |
| internal/config/config.go, internal/config/load.go, internal/config/defaults.go | config keys and tables (`log-file concurrent health-address drain-timeout provider max-runners`; `[tart] runner-dir cpu memory pool-size cache-budget dns`; per set `url name token provider labels runner-group max-runners runner-image disable-update`; `[scaleset.tart] …`), removed-key hard errors, defaults (runner-dir, health, retry, drain 60m) | config.toml.example; ru_config / ru_pools (bin/runner-updater-lib) | the live config stops loading, or ru_config refuses |
| internal/lock/lock.go, cmd/runner/main.go | `/tmp/runner.lock`, flock EX|NB, taken first in `run` | bin/runner-lock-free, runner-enable (`lockf -k -t 0`), golden-build, linux-image-smoke, runner-updater-window | the lock test lies |
| cmd/runner/service_env.go, cmd/runner/platform_guard.go | service WARN only for `io.github.ysya.runner`; root refusal | plist Label `sh.liveapp.mac-runner` | |
| internal/controller/controller.go, cmd/runner/main.go | drain on SIGTERM: drain-timeout, then `Runner drain timed out; forcing remaining runners to stop` | bin/runner-disable (WAIT_S 3700), plist ExitTimeOut 3660 | disable waits wrong |
| cmd/runner/update_notice.go, cmd/runner/cmd_update.go | `runner update` is the only self-replace; `run` only WARNs | setup/downloads.manifest (the pin); never run `runner update` | |
| release assets (.goreleaser.yaml) | asset `runner-darwin-arm64.tar.gz`, member `runner` | setup/downloads.manifest, install | install fails |

### 5. Not in runscaler: also check these by hand

- Tart itself (cirruslabs/tart; our pin ec6d2f79… in downloads.manifest): `list --source local -q` (one name per line; steps.zsh m0, m3), `clone`, `set --random-mac`, guest agent for `exec`.
- launchd: ThrottleInterval 300 (one restart inside 300 s waits), ExitTimeOut.
- macOS: Apple's 2 macOS VMs per host.

## The Linux host's read points (owner: the Linux host's maintainers)

Upstream paths are as at v0.22.1; "ours" is this repository, and a path without a folder is in `linux-docker/`. Line
numbers are hints: look for the literal in the named file. Each literal was found at v0.22.1 in its named file, except
those under "Not found upstream" at the end (kept for the way back to an older runscaler). Rows of the Studio's half
marked SHARED are not repeated here: section 0 names the ones this host depends on too, and adds the core read points
the Studio's half does not have.

### 0. SHARED rows (the Studio's half) Hetzner depends on, and core read points the Studio's half does not have

Hetzner depends on these SHARED rows of the Studio's half (by literal), through the same core/*.jq copy (installed as
~/build/core/ on the Linux host):

- `Runner removed` (keys name instanceID reason jobId repo workflowRunId job result): core/r1.jq; also pool-image.sh
  (section 1 below adds what pool-image reads by word position).
- reasons `job-completed` `exited` `readiness-failed` `scaled-down`: core/r1.jq; on Hetzner `readiness-failed` with no
  jobId is read as `exited` (r1.jq:90, the `$p != "tart"` rule).
- `Runner started`: core/r1.jq reads it as nothing on a Docker family (r1.jq:93); pool-image.sh counts it (section 1).
- `Job started for unknown runner (already removed?)`, `Job completed for unknown runner (already removed?)`: core/r1.jq
  (the pairing), and pool-image.sh (section 1).
- `Failed to start runner, will retry`, `failed to generate JIT config`: core/r1.jq; pool-image.sh.
- the tart.go connect texts (`runner process exited on %s before connecting to GitHub`, `… right after connecting to
  GitHub`, `did not connect to GitHub within`): r1.jq:102-104 reads them on EVERY family, not only Tart (no `$p` gate).
  Hetzner depends on them only in that a Docker start error never holds them; a Docker provider text that came to hold
  one would class as connect-class.
- the log writer row (5-wide level column, `<set>: ` prefix, `YYYY-MM-DD HH:MM:SS ` in host local time): core/lib/logfmt.jq;
  pool-image.sh rec()/words() (section 1); config/runscaler.service sets TZ=UTC for it.
- /healthz field names `ready idle busy provisioning removing`, `metrics.available_jobs assigned_jobs running_jobs
  desired_runners`, `last_error`, and HTTP 200 always: core/idle.jq, core/r1.jq (NOT SERVING); bin/pool-ready,
  pool-image.sh counts(), runner-facts.sh runs (section 2).
- the Degraded rule (`ready` = ready && !draining && !degraded): the same readers.
- the `runner validate` lines api_re / config_re and `All checks passed.`, exit 1: bin/validate-class (the bash copy;
  section 3 adds its Hetzner-only lines).

Core read points the Studio's half does not have (each is read by core/*.jq, so it is SHARED too):

| upstream file | literal | ours | if it changes |
|---|---|---|---|
| internal/health/health.go:118, :61 | the top-level array `scale_sets` and each entry's `name` (json tags `scale_sets`, `name`) | core/idle.jq:11,33,35 (`.scale_sets[]? \| select(.name == $n)`); core/r1.jq:302 ns_read; Hetzner: bin/pool-ready:31, pool-image.sh:761, runner-facts.sh:142 | every /healthz reader reads "absent from /healthz" / "NOT LISTED" / "does not serve": IDLE never, RUNS never, READY never (SHARED) |
| internal/health/health.go:69 (`metrics,omitempty`; set only once the set's metrics exist, :283-296) | `metrics` may be ABSENT (not an empty object) | core/idle.jq:13 ("no metrics" blocks idle); pool-image.sh:764 (`s.get("metrics") or {}`) | idle reads wrong while a set starts (SHARED) |
| internal/controller/controller.go:177-199 (HandleJobCompleted), internal/controller/state.go:339-348 (markDone: `instance.job.result = result`), go.mod:8 (`github.com/actions/scaleset v0.5.0`) | `Runner removed reason=job-completed result=…`: the result passed through as the scaleset library gives it, values `succeeded` `failed` `canceled` (anything else is "other") | core/r1.jq:119; core/keep.jq:36-56 (KEEP accepts on succeeded); core/status.jq:36,68 | KEEP's counts lie: a release accepted or held on the wrong numbers (SHARED) |
| internal/provider/ownership.go:28, :38 | runner names `runner-` + 8 hex (`^runner-[0-9a-f]{8}$`, NewRunnerName) | core/r1.jq:74 (vms: `runner-[0-9a-f]{8}` in the error text, the shim pairing) | the shim pairing finds no VM (SHARED; Tart only in effect) |
| internal/provider/tart.go:893, :913 (the error appends `runner log:\n%s`, the guest runner's own log) | the runner's texts `deprecated and cannot receive messages` (r1.jq:101, Tart-gated) and `no longer exists on the server` (r1.jq:103) | core/r1.jq:101,103 | PINNED RUNNER RETIRED or the "none" class lost (SHARED; the texts are actions/runner's: section 5) |
| internal/config/config.go:802-860 (NewLoggerWithWriter, NewScaleSetLoggerWithWriter: `TimeFormat: time.DateTime`, `Prefix: name`, charm text formatter), :863-865 (`demoteMessages`: `"Getting next message": true`), internal/config/logfile.go:204-209 (outputWriter: `colorprofile.NoTTY`), :149-163 (one Write per record, under one mutex) | the record form the core parses: local time `2006-01-02 15:04:05`, the set name as charm's prefix, no ANSI in runner.log, only the listed messages demoted to DEBUG, records written whole and in order | core/lib/logfmt.jq:28-33,76-80; core/r1.jq:22-27 (ORDER 10 s: "writes it under one lock") | a message we read demoted to DEBUG vanishes at info; ANSI or a new time form makes every record "no record" (SHARED) |
| go.mod:7 | `charm.land/log/v2 v2.0.1` (the level column, the `key="quoted \"value\""` quoting, the multi-line `  key=` / `  │ ` form) | core/lib/logfmt.jq:3-11,31,61-66; pool-image.sh:832-835,864-868 | a charm bump in go.mod alone changes the column or the quoting: the Studio row names "the charm handler" but not this pin (SHARED) |

### 1. Log messages Hetzner's own code reads (runner.log, charm text form)

pool-image.sh's runscaler-check reads records by WORD POSITION with awk (field split on blanks), not by key, so the
ORDER of a record's attributes is part of the read point (marked "order").

| upstream file | literal | ours | if it changes |
|---|---|---|---|
| internal/controller/controller.go:747-767 (logRemoved) | `Runner removed` INFO, order: `name` FIRST (f[3]), then the first `reason=` word, `jobId=` RIGHT AFTER `reason=` (attrs name instanceID reason [jobId repo workflowRunId job [result]]) | pool-image.sh:842-849 (removal(), accepted(), jobid()), :870-896 (THE START RULE, the cut records) | removals, cuts and start failures miscounted; the way back given or withheld wrongly |
| internal/controller/state.go:24-29 | reasons `scaled-down` and `drain` (accepted: GitHub took the DELETE); `exited`, `readiness-failed` (no jobId = a start failure); `job-completed` (closes a set's start failures). Not read: `shutdown` (:28) | pool-image.sh:848 (accepted()), :892-896 | "the fix works" / the way back answer wrong; `drain` is NOT in the Studio's reason row |
| internal/controller/controller.go:317-321 (removeClaimedInstance) | `Failed to remove runner, will retry` ERROR, order: `name` FIRST (f[7] after the 6 message words), then `retryIn`, then `error` | pool-image.sh:901-904 | removal errors keyed to the wrong runner; "over an hour" open errors missed |
| internal/controller/controller.go:356 (deregister) | the error `deregister runner %s: %w`, as `error="deregister runner NAME: …"` on the record's line, or charm's multi-line form `  error=` then `  │ deregister runner NAME: …` | pool-image.sh:864-868, :903 | deregister errors read as 0: the closed-error way back never fires |
| internal/controller/controller.go:341 | `cannot safely deregister runner with unknown ID` (NOT a deregister error; counted as a removal error only) | pool-image.sh:901-904 (any error text) | none today; a rename into `deregister runner …` would count it as a GitHub refusal |
| internal/controller/controller.go:352 | `Runner holds a job GitHub assigned before JobStarted arrived; keeping it` INFO, its ONE attribute `name` LAST (f[k]) | pool-image.sh:897-900 | "protected a job" lost; open removal errors never closed |
| internal/controller/controller.go:169, :187 | the unknown-runner WARNs, `runnerName` their LAST (only) attribute | pool-image.sh:909-912 (`substr(f[k], 12)`), :2475 (the restart-cut scan: `sub(/.*runnerName=/, "")`, the rest of the line) | the pairing and the cut records name the wrong runner |
| internal/controller/controller.go:471-475 (startInstanceWithLease) | `Runner started` INFO, `name` FIRST (`Runner started name=`), logged BEFORE readiness on Docker | pool-image.sh:907 (counted only) | count lost; no verdict depends on it |
| internal/controller/controller.go:271 | `Failed to start runner, will retry` at level ERROR (no name attribute) | pool-image.sh:905 (`$3 == "ERROR" \|\| "ERRO"`) | start failures lost |
| cmd/runner/main.go:529 | `Starting scale sets` INFO, a GLOBAL record (no `<set>: ` prefix: `$4 == "Starting"`), keys count concurrent | pool-image.sh:652-653 (stamp_write: THE STEP'S STAMP), :645 | no stamp: the check answers "the step's start is not known" forever |
| cmd/runner/service_env.go:54, :121-124 | WARN `Service definition predates this runner's template` (attrs `fix`, `upgrade_requirements`) | pool-image.sh:806 (svc), :1037 (marked expected, "never run its fix") | the expected WARN shows unmarked (text only) |
| cmd/runner/update_notice.go:22-27 (logAvailableUpdate) | WARN `A newer version of runner is available; review release notes for breaking changes and sunset notices before running 'runner update'. Updating does not validate compatibility or restart services` | pool-image.sh:808 (upd: v0.12.0's text or this one, no third), :1038 | the notice shows unmarked |
| cmd/runner/main.go:786, :777 | `Runner drain timed out; forcing remaining runners to stop`, `Runner drain disabled; stopping immediately` | (read by a person: journal/runner.log after a restart; pool-image.sh:2475's cut scan is the effect) | a cut drain unnamed |
| internal/controller/controller.go:604 (handleExit) | `Runner exited before job completion; scheduling cleanup` WARN | none (core/lib/logfmt.jq:39 holds the old text, dead: SHARED row) | none today |
| internal/provider/docker.go:263, :281 | `Runner image is missing locally, pulling it`, `Runner image pulled successfully` | none (a person reads them) | |
| (log writer) internal/config/logfile.go:20, :149-185 (Write, rotate), :121-124 (newLogFileWriter) | APPEND on start; rotate when the next write passes 10 MiB (`DefaultLogMaxSize`) by unlink `runner.log.1` + RENAME runner.log to `runner.log.1` (the inode moves) + a new runner.log; ONE backup | runner-facts.sh:152-223 (log_pos: follows ONE rotation by the boundary's INODE now at runner.log.1, and the sha of the 64 bytes before it); pool-image.sh:650, :829-831 (reads .1 then the log) | a copy-truncate or a second backup makes every pass "NOT continuous" (an evidence gap) and the check's counts short |
| cmd/runner/logpath.go:35-60 (resolveLogFile), :91-113 (openRunLog) | `log-file` used as written for a non-system identity (`if !id.System()`); `log-file = ""` disables file logging; no key = the layout default (~/.local/state/runner/runner.log); `cannot open log file %s: %v` | runner-start:99-114 (refuses any other log-file, a table one, or none); runner-facts.sh:314-321; 03-runscaler.sh:357 | the log lands where no pass reads: a quiet log that looks healthy |
| cmd/runner/logpath.go:115-146 (diagnosticDirectory), internal/diagnostics/store.go | a `diagnostics` folder BESIDE the log (~/.config/runner/diagnostics) | runner-start TOKEN_DIR, runner-updater, 03, pool-image's lock and staged files: all name their files in ~/.config/runner | a file of runscaler's with a name we use (config.toml, token-*, pool.env, runner.log.*) |

### 2. /healthz (JSON)

| upstream file | literal | ours | if it changes |
|---|---|---|---|
| internal/health/health.go:136 | route `GET /healthz` on `health-address`:`health-port`, HTTP 200 always (curl -f fails on any other) | bin/pool-ready:26; pool-image.sh:757; runner-facts.sh:236 (healthz_pair); runner-start:174 (refuses a bound health port) | every reader reads "does not answer" |
| internal/health/health.go:61-70 | per set `name`, `ready`, `idle`, `busy` (no omitempty: read as `!= 0`, `== 0`), `provisioning`/`removing` (omitempty: `or 0`), `last_error` (omitempty) | bin/pool-ready:31-39 (exactly these sets, each `ready: true`; prints idle busy last_error); pool-image.sh:761-768 (counts(): quiet = idle 0, provisioning 0, busy 0, no desired/assigned/running) | READY or the quiet restart wrong: a restart that cuts a job |
| internal/health/health.go:75-81 | `metrics.desired_runners` (NOT omitempty at v0.22.1), `available_jobs` `assigned_jobs` `running_jobs` (omitempty) | pool-image.sh:767 (`any(m.get(k) …)`: a 0 and an absent key read the same) | none while 0 reads as absent; a renamed key reads as 0: a restart in a busy moment |
| internal/health/health.go:272-275 | Degraded: `ready` false and `last_error` = `runner startup failed: <reason>` when the set's startup is degraded | bin/pool-ready:37 (prints it) | pool-ready's line only |
| internal/health/health.go:229-300 (handleHealthz) | `ready` per set false while draining | runner-facts.sh:124-148 (RUNS: lists every set on two reads; does not read ready) | none |
| internal/config/config.go:34-35, internal/config/defaults.go:19-20 | keys `health-port`, `health-address` (defaults 8080, 127.0.0.1) | 03-runscaler.sh:359-360 renders both (RS_HEALTH_PORT) | the reads go to a port nothing listens on |

### 3. `runner validate` (stdout text, exit code)

Hetzner's copy is linux-docker/bin/validate-class (bash); the Studio's row covers api_re, config_re and `All checks
passed.` (SHARED). Hetzner-only:

| upstream file | literal | ours | if it changes |
|---|---|---|---|
| cmd/runner/cmd_validate.go:75, :81, :90, :94 | `  ✗ Docker client for %s: %s`, `  ✗ Docker connectivity at %s: %s`, `  ✗ Docker at %s: %s` (the API version check), `  ✓ Docker is reachable at %s` | validate-class:26-29 (a first ✗ of these = UNKNOWN: they test the host) | a host fault reads NON-API (the window stops) or API-ONLY (it tries again) |
| cmd/runner/cmd_validate.go:34-145 (the order) | config checks, then Docker ping + API version, then the GitHub API, then only with `--preflight` image pulls (`Bool("preflight", false`, :31; we never pass it) | the "three API-ONLY = PASS" rule (pool-image.sh unattended VALIDATE TRIES; 03-runscaler.sh:497 exit 4) | a check added after the API line is skipped by API-ONLY = PASS |
| cmd/runner/main.go:834, :844, :822 | `invalid global capacity: %w`, `scaleset[%d] %q duplicates scaleset[%d] name; …`, `scaleset[%d] %q: %w` (printed as `  ✗ %s`, cmd_validate.go:172) | validate-class:45-47 (NON-API) | a config fault reads UNKNOWN |
| cmd/runner/tart_guests.go:67, :70, :120 | `combined min-runners of macOS `, `combined tart pool-size of macOS ` (NON-API), `  - scaleset[%d] %q Tart guest: ` (undetected: UNKNOWN on RC 0) | validate-class:48-51 (Docker sets never print them) | none on Hetzner (shared fixtures) |
| internal/config/config.go:670, cmd/runner/cmd_validate.go:160 | `log-level must be debug, info, warn, or error`, printed `  ✗ global config: …` (NON-API), checked before any Docker or GitHub call | 03-runscaler.sh:482-486 (the strict validate's CONTROL: `log-level = "liveapp-bogus"` must be NON-API and say `log-level must be`) | 03 real/stage refuse every render: "control … proves nothing" |
| internal/config/config.go:675 | `log-format must be text or json` | runner-facts.sh:322-324 (refuses any log-format but "text": no facts) | |
| cmd/runner/cmd_validate.go:76-91, :143, cmd/runner/main.go (cobra) | exit 1 with `validation failed` after a ✗ line; exit 0 after `\nAll checks passed.`; validate takes NO lock (no runnerlock.Acquire in cmd_validate.go) | validate-class:61-67; 03-runscaler.sh:28 (validate with the pool running), runner-start:31-32,184 (no lock check for validate) | a validate that took the lock would fail while the pool runs: every switch UNKNOWN |

### 4. Interfaces (any change in the named place = a person's step)

| upstream file | interface | ours | why |
|---|---|---|---|
| internal/provider/docker.go:121-237 (StartInstance), :359-373 (runnerCmd), :376-388 (buildContainerEnv), :390-405 (containerResources) | the runner container: `Image` (runner-image), `User: "runner"`, `Cmd` `/home/runner/run.sh` (plain, with no workspace, volume or local cache), `Env` `ACTIONS_RUNNER_INPUT_JITCONFIG=…`, `Labels` managed-by=runner, `HostConfig`: `SecurityOpt` `label:disable` ONLY (no seccomp, no Privileged, no CapAdd, no Init), `NetworkMode` = network, no socket mount when dind=false, `Name` = runner name; Memory MB->bytes, NanoCPUs = cpu cores, PidsLimit | image/Dockerfile (actions-runner base: /home/runner/run.sh, USER runner), image/install-runner.sh (/home/runner); 02-d1.sh:115-128 (the DAEMON's seccomp profile, no-new-privileges, init: they apply only because runscaler sets none); 03-runscaler.sh:365-371, :388-390 (socket dind network cpu memory pids-limit); pool.env numbers | a new command, env, mount or security option: jobs stop, or the hardening 02-d1.sh proves no longer applies |
| internal/provider/docker_workspace.go:104-107 (prepareWorkspace) | no workspace (and so no socket proxy, no extra mount) when `workspace-root` is unset | runner-start:120 (refuses workspace-root: not a rendered key) | a default workspace changes the container |
| internal/provider/docker_readiness.go:16-90 (WaitReady), internal/provider/docker.go:93-95, internal/config/defaults.go:125 | Docker readiness: marker `Listening for Jobs` on stdout or stderr via ContainerLogs (`Tail: "200"`), then settle `defaultReadySettle` 5 s, poll 500 ms, timeout `DefaultReadyTimeout` 5 min; exited before ready = ErrExitedBeforeReady; logs unreadable = unavailable | image (run.sh prints the marker); D1's json-file logging driver; core/idle.jq:16 and pool-image.sh:765 count `provisioning` as not idle | a runner never ready: `readiness-failed` removals, the check's start failures |
| internal/controller/readiness.go:11 (waitReady), internal/controller/state.go:130-145 (readinessResult), :182-200 (markExited), internal/controller/controller.go:562-604 (watchInstance, handleExit), :403-476 (startInstanceWithLease) | `Runner started` is logged BEFORE readiness; a container that EXITS first ends `Runner removed reason=exited` with no jobId (the exit watcher's takeover); only a live never-ready one ends `reason=readiness-failed` | pool-image.sh:892-895 (THE START RULE: both, no jobId = a start failure), :907 (`Runner started` closes nothing); core/r1.jq:88-91 | the start rule counts the wrong events |
| internal/controller/retry.go:15-43 (recordStartFailureFor), internal/config/defaults.go:118-121 (retry 5 s / 1 min / cooldown after 5 / 5 min) | a readiness failure writes NO `Failed to start runner` line; backoff + 5-min cooldown | pool-image.sh:905, :1094-1098, :1111-1114 (the "over an hour" rule) | a start failure with no record, or a new record counted twice |
| internal/controller/controller.go:177-199 (HandleJobCompleted), :161-175 (HandleJobStarted) | the unknown-runner WARN comes when the runner was already removed (the race the 110 s pairing reads: hz-cut.log) | pool-image.sh:939-946 (THE PAIRING, 110 s = core/r1.jq SETTLE - ORDER), core/r1.jq:38 (in_window) | a race read as a start failure: a false way back |
| internal/controller/controller.go:295-358 (removeClaimedInstance, deregister), internal/controller/state.go:297-320, :419-440 (removalRetryMax 80 s) | `Runner removed reason=scaled-down\|drain` only after GitHub accepted the DELETE; JobStillRunning = `keeping it`; a failed removal retried at most every 80 s | pool-image.sh:848 ("accepted"), :1108 ("runscaler retries each, every 80 s at the most") | "the fix works" claimed on removals GitHub never accepted |
| internal/provider/docker_cleanup.go:27-170 (RemoveRunnerContainer) | removal: stop (timeout 0), list ALL containers, remove the children tied to the runner (`runscaler.runner-id` label, references), then the runner; anonymous and runner-owned volumes only: shared/cache volumes, images, build caches kept | D1's `runner-registry` container and its `runner-registry` volume (02-d1.sh:144-146): neither is a runner's child | a widened child rule removes the registry or its volume: no runner image can start |
| internal/provider/ownership.go:20-63 (ManagedByLabel `managed-by`, ManagedByValue `runner`, runnerNamePattern, OwnsContainer), cmd/runner/orphans_tart.go:71-100 (reconcileOrphans), cmd/runner/orphans.go:38-60, cmd/runner/main.go:423 | at EVERY `run` start, on D1: remove every container labelled managed-by=runner or named `runner-<8 hex>` | D1's `runner-registry` (no label; `registry` is not 8 hex) and any other container on D1 | a widened rule deletes the registry container at a start |
| internal/cachestore/docker.go:96-140 (garbage store), :191-260 (build cache), internal/cachestore/store.go:28-48 (tiers), cmd/runner/sweepers.go:23-50, :108-152, internal/diskguard/guard.go, internal/config/defaults.go:69-113 | the disk guard is ON by default (`DefaultDiskGuard = true`, min-free `10%`, target-free 20%, max-tier 3): Tier1 prunes ALL stopped containers and dangling images older than prune-ttl (24 h) on D1, Tier2 the build cache; the periodic prune is off (`DefaultDockerPrune = false`) | runner-facts.sh:335-341 (DISK_PCT 10 = "runscaler's min_free"); D1's `runner-registry` (a STOPPED registry container older than 24 h is pruned at disk pressure; its volume stays) | the updater's disk rule drifts from runscaler's; a pruned registry container: CI down until 02-d1.sh |
| cmd/runner/image_preflight.go:55-110 (prepareRunnerImages, pullDockerRunnerImage), cmd/runner/main.go:383, internal/provider/docker.go:239-292 (ensureRunnerImage, pullRunnerImage), internal/provider/docker_image_pull.go | `run` pulls each set's runner-image at start (a failure is fatal to `run`); a pruned image is pulled again before a container is created, and a failed pull stops that creation (one pull per image across sets) | runner-start:173 (refuses when the local registry does not answer: "runscaler's start pull would fail"); 03-runscaler.sh:161,383 (`localhost:PORT/NAME@sha256:<64 hex>`); pool-image.sh:624-628 (pulls) | a start that fails on an image the registry serves, or one that runs a stale image |
| cmd/runner/image_preflight.go:23-36 (requireDockerAPIVersion: `minDockerAPIVersion = "1.49"`), cmd/runner/main.go:357, cmd/runner/cmd_validate.go:88 | Docker API 1.49+ (Engine 28.1+) at `run` and in validate | runner-start:60,170-172 (runs only Docker 29.9.0, API 1.56) | a raised minimum refuses the pinned Docker: CI down |
| cmd/runner/main.go:341, cmd/runner/cmd_validate.go:72 | the Docker client host is `"unix://"+socket`: `[docker] socket` is a PATH | 03-runscaler.sh:366; runner-start:158-159 (docker.socket = D1's socket path) | the render's socket no longer reaches D1 |
| internal/config/config.go:30-140 (Config, ScaleSetConfig, DockerConfig mapstructure keys), internal/config/load.go:13-60 (globalOnlyKeys, identityKeys, rejectRetiredKeys, Load's per-set merge), internal/config/defaults.go | the keys the render writes: top `log-level log-file concurrent health-address health-port drain-timeout provider`; `[docker] socket dind network cpu memory pids-limit` (memory MB, cpu cores); per set `url name token runner-group labels max-runners runner-image`; `[scaleset.docker] cpu memory` merged over `[docker]` (a key present in the set wins, `dind = false` too); global-only and identity keys never inherited; removed keys are hard errors: `config key %q has been removed; use %q` for `backend`, `docker.shared-volume-ttl`, `tart.cache-space-budget`; defaults relied on: `DefaultDisableUpdate = true`, `DefaultLogFormat "text"`, provider `docker`, dind `true` (refused) | 03-runscaler.sh:352-392 (the render); runner-start:120-165 (ALLOWED, GLOBAL, IDENTITY, builtin = load.go's copy: upstream's lists add `diagnostics`, `actions-cache`, `github-app`, which runner-start refuses as unrendered keys anyway; the `backend` refusal); runner-facts.sh:241-332 (config_read: log-file, log-format, log-level, name, runner-image) | the live config stops loading, a key's meaning or inheritance changes, or runner-start's resolution disagrees with runscaler's |
| internal/config/config.go:525-545 (resolveEnvToken) | `token = "env:NAME"` -> `os.Getenv(NAME)` (no fallback after `env:`); an EMPTY token falls back to `RUNNER_TOKEN`; a `github-app` set takes no ambient token; ambient `RUNSCALER_TOKEN` gone (H6) | 03-runscaler.sh:379 (`token = "env:${TOKEN_ENV}"`); runner-start:162-165 (`env:RUNNER_TOKEN_[A-Z0-9_]+`), :176-181 (exports it from a 0600 file); host.conf.example:30-33 | the token is not found: every set fails at start |
| internal/lock/lock.go:16-140 (DefaultPath `/tmp/runner.lock`, openLockFile O_EXCL 0666, fchmod 0666 by its owner, nlink 1, `unix.LOCK_EX\|unix.LOCK_NB`), cmd/runner/main.go:155 (`run`), cmd/runner/scaleset.go:255 (`scaleset delete`) | the machine lock: flock on /tmp/runner.lock, taken by `run` and `scaleset delete`, never by validate | runner-start:31-32, :182-189 (finds the holder in /proc/locks by FLOCK and dev:inode; only for run and delete) | the holder check names nobody, or validate starts to fail under a running pool |
| cmd/runner/main.go:170, :197-230 (handleShutdownSignals), :770-790, internal/controller/controller.go:621 (Drain), cmd/runner/cmd_service.go:1289-1291 (serviceStopTimeout) | SIGTERM (and SIGQUIT) = drain up to drain-timeout, a 2nd signal cancels work, a 3rd force-exits; SIGINT stops at once; a unit needs drain-timeout + 1 min to stop | config/runscaler.service:17-18 (TimeoutStopSec 4260 = 70 min + 60 s + margin); 03-runscaler.sh:361 (`drain-timeout = "70m"`); pool-image.sh:180, :774-778 (restart = drain) | a restart kills running jobs, or a stop waits wrong |
| cmd/runner/service_env.go:17-60 (startedByServiceManager: `INVOCATION_ID`; `RUNNER_SERVICE_VERSION` < `currentServiceVersion = 3`; `RUNNER_SERVICE_STOP_TIMEOUT`), :112-126 (warnOutdatedService), cmd/runner/platform_guard.go | under systemd the WARN fires at every start (our unit sets neither variable); a 2nd WARN `Service stop timeout %ds is shorter than drain-timeout plus one minute` only when RUNNER_SERVICE_STOP_TIMEOUT is set; root refusal | config/runscaler.service (a hand-made user unit; never `runner service install`); pool-image.sh:806 | a new WARN, or a refusal to run under a unit runscaler did not write |
| cmd/runner/loadconfig.go:60-80 (loadConfigAtPath: `viper.SetConfigFile`, type from the extension), cmd/runner/installation.go:197-225 (managedConfigPath), cmd/runner/main.go:49 (`--config`), :265 (`run`), cmd/runner/scaleset.go:216-260 (`scaleset delete NAME`), cmd/runner/cmd_version.go:12 (`version`) | the CLI runner-start and 03 call: `run --config F`, `validate --config F`, `scaleset delete NAME --config F`, `version` (exit 0); the explicit --config is used unless runscaler finds a service it installed | runner-start:66-72, :190 (`exec "$RUNNER" "${args[@]}" --config "$CONFIG"`, the .toml rule); 03-runscaler.sh:345 (`runner version`, first line shown) | runner-start's exec fails or runs another config |
| cmd/runner/main.go (the `run` command: no fork, no daemonize, no re-exec) | the runscaler process is the one runner-start execs: systemd's MainPID, its /proc/PID/exe the installed binary | pool-image.sh:677-684 (running_sha), runner-facts.sh:99-123 (proc_now, unit_read: MainPID, ActiveEnterTimestamp) | THE RUNNING BINARY reads another file: the check answers "v0.22.0 is not running" |
| internal/controller/controller.go:403-476, internal/capacity/broker.go, cmd/runner/main.go:520-531 (effectiveConcurrent) | `concurrent` caps all sets together; per-set `max-runners` | 03-runscaler.sh:235-238 (CONCURRENT = MAX + 1: the small lane's slot) | the small lane loses its slot |
| cmd/runner/update_notice.go:22-27, cmd/runner/main.go:534-542 (versioncheck.Latest at start), cmd/runner/cmd_update.go, internal/versioncheck/update.go | `run` only WARNs of a newer release (a GitHub call at start); `runner update` is the only self-replace (downloads `runner-%s-%s.tar.gz` + checksums.txt); `disable-update` default true | 03-runscaler.sh:363 (relies on the default); pool-image.sh:1038, README (never run `runner update`) | a `run` that replaces its own binary: ~/bin/runner no longer BIN_SHA |
| release assets (.goreleaser.yaml:7, :32, :35), internal/versioncheck/update.go:19-37 | asset `runner-linux-amd64.tar.gz` (`runner-{{ .Os }}-{{ .Arch }}`), member `runner` at the archive's top level, `checksums.txt`, tag `vX.Y.Z` in `https://github.com/ysya/runscaler/releases/download/<tag>/<asset>` | 03-runscaler.sh:145-155 (PINNED/TGZ_SHA/BIN_SHA, WAYBACK/…, dl_of), :336-337 (`tar -xzf "$DL" -C "$tmp" runner`); pool-image.sh:664-676 (dl_of, wayback_lines URL), :786; README.md:71-75, :205 | install and the way back fail (sha or member not found) |

### 5. Not in runscaler: also check these by hand

- actions/runner and its image (ghcr.io/actions/actions-runner, our pin in image/Dockerfile:16; RUNNER_VERSION): `/home/runner/run.sh`, the `runner` user (uid 1001, gid 123: runnerCmd's chown), the `Listening for Jobs` marker the listener prints (Docker readiness), `ACTIONS_RUNNER_INPUT_JITCONFIG` read by the runner, and the runner's own texts the core reads through Tart's error (`deprecated and cannot receive messages`, `no longer exists on the server`).
- GitHub (through github.com/actions/scaleset v0.5.0, go.mod:8): the job result values `succeeded` `failed` `canceled`; JobStillRunning on a DELETE (`keeping it`); a job given to a runner before JobStarted (the cut records); the 10-min `lost communication` end of a cut job (pool-image.sh:160, :2476).
- Docker Engine on D1 (pinned 29.9.0, runner-start:60): API >= 1.49, the json-file logging driver (ContainerLogs for readiness), the daemon defaults the hardening relies on (seccomp profile, no-new-privileges, init: 02-d1.sh:115), rootless socket path, `docker network` `runners`, prune semantics (`until`, `dangling`).
- systemd (user unit, linger): `INVOCATION_ID` in the service env, MainPID and ActiveEnterTimestamp (`systemctl --user show runscaler`), Type=simple + exec (MainPID = runscaler), TimeoutStopSec, Restart=always, `Environment=TZ=UTC` (runscaler stamps local time).
- viper v1.21.0 (go.mod:20): config type from the file's extension, case-insensitive keys, the longest-dotted-prefix lookup (runner-start:76-91 refuses quoted dotted and non-ASCII keys because of it).
- The local registry (`runner-registry`, D1): runscaler's start pull and its re-pull read from it.

### Not found upstream (our literal has no match at v0.22.1 in the named file)

- `  ✗ scale set collection: ` — linux-docker/bin/validate-class:45 (config_re; also the Studio's row). Present at v0.12.0 (cmd/runner/cmd_validate.go:59), gone at v0.22.1 (0 hits in the whole tree). Kept for the way back (v0.12.0); harmless.
- v0.12.0's update notice ` … run 'runner update' to upgrade` — pool-image.sh:808 (upd's first alternative). At v0.12.0 cmd/runner/main.go:546 (`A newer version of runner is available — run 'runner update' to upgrade`), 0 hits at v0.22.1. Kept for the way back; text only.
- `Runner exited before job completion; removing stale capacity` — core/lib/logfmt.jq:39 (SHARED, already in the Studio file as a dead entry). v0.22.1 has `…; scheduling cleanup` (controller.go:604).
- `migrate --user` (v0.12.0's service `fix=`) — pool-image.sh comments and README.md:212 only, as text; 0 hits at v0.22.1. No code reads it.
- `API 1.49+` (an older note's quote) — not a literal upstream: image_preflight.go:30 formats `(API %s+)` with `minDockerAPIVersion = "1.49"` (:23). Our code reads only the `  ✗ Docker at ` prefix, which is found (cmd_validate.go:90).
