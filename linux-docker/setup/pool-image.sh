#!/usr/bin/env bash
# pool-image.sh — a RUNNER RELEASE, the POOL half: AS RS_USER, after `02-d1.sh build VERSION` (as RUN_USER) built the
# runner image of VERSION and wrote its build record. Needs this release's linux-docker/ as ~/build.
#   up:     ssh -o ServerAliveInterval=60 RS_USER@<host> 'bash -s -- up 2.338.2' < linux-docker/setup/pool-image.sh
#   back:   the same line with `back` — the rollback to the image the pool ran before this release's `up`.
#   accept: the same line with `accept` — ends the release once a job passed on the new image: the kept rollback is
#           removed, so the NEXT release's `up` keeps this config. Until then an `up` to another image refuses. It
#           closes the release whose image config.toml RUNS, whatever build records there are by then.
#   runscaler [VERSION]: the same line with `runscaler` — THE RUNSCALER STEP (below): runscaler v0.12.0, the one this
#           release pins, into ~/bin/runner, at a quiet time; with VERSION 0.9.5, the way back.
# THE BUILD RECORD (02-d1.sh's header gives its form): `up VERSION` reads RUN_USER's ~/run/builds/<VERSION>-<RECIPE>,
# RECIPE being 02-d1.sh's recipe of this release's image/ (this ~/build/image/: the same release's files as RUN_USER's
# ~/build), ONCE: a private copy, parsed by one exact pattern of 02-d1.sh's four lines, never sourced. The recipe and
# the reader are runner-release.sh's rr_recipe and rr_record (ONE copy each: 02-d1.sh and the updater use them too); an
# image/ entry that is no plain file, or one named runner.tar.gz, is no recipe: REFUSED, nothing changed. A record that
# is missing, not a plain file, of another form, version or recipe, or whose digest the local registry does not serve:
# REFUSED, nothing changed, and the line names the fix (`02-d1.sh build VERSION` as RUN_USER). Its digest is the image
# up puts into the pool (`03-runscaler.sh real DIGEST`).
# THE ROLLBACK FILE (config.toml.pre-image) belongs to ONE release: `up` writes it only when it is absent or names the
# image config.toml runs now (each up names its own new image, so "differs from the new image" would keep an unproven
# config).
# up:   refuses unless ~/bin/runner is one of the two runscalers 03 knows (ONE DOOR, below), pool.env holds the
#       numbers config.toml runs (03 renders from pool.env, so others would go live with the image) and the record's
#       image's runner is VERSION; keeps the rollback; `03 real DIGEST --image-only` (the same sets and numbers, the
#       record's image: it installs with the pool running and restarts nothing; with --image-only 03 itself refuses,
#       after its validate and before it installs config.real.toml or config.toml (this release's runner-start,
#       pool-ready, validate-class and the unit are installed by then: each starts with either runscaler), a render
#       that differs from config.toml in more than the image (THE CONFIG COMPARE): a drifted host value never reaches
#       config.toml; if 03 fails, config.toml is unchanged); if config.toml then differs from the rollback in more
#       than the image (THE CONFIG COMPARE), the
#       rollback goes back with config.toml's old mtime and nothing restarts. config.toml already on the record's image
#       with a restart pending (a run cut off before its restart, or a bare 03 run) restarts only when the rollback was
#       kept while the running process ran.
# back: puts config.toml.pre-image back with NO 03 (no build, no GitHub), only when the image is ALL it changes (THE
#       CONFIG COMPARE) and the registry still serves the old digest (runscaler pulls it at every runner start, so a
#       dead registry stops both images alike). `03 real` with no digest renders the image config.toml runs NOW, so a
#       later 03 (a change of the numbers) keeps the old image; only an `up` puts a new one in. BACK'S PAIR GUARD
#       (runscaler 0.12 bump, slice H2a; the H2 plan's R-4): a rollback with no log-file key runs only on the way-back
#       runscaler (v0.9.5: 03's WAYBACK_BIN_SHA, runner-start's V095_SHA), so on any other ~/bin/runner `back` refuses
#       it before any put (runner-start would refuse that pair at the restart: CI down). A belt: THE RUNSCALER STEP
#       refuses while a release is open and removes the rollback of one a back closed, so its steps make no such pair.
# THE CONFIG COMPARE (runscaler 0.12 bump, slices H1 and H2a): "differs in more than the image" is runner-release.sh's
#       rr_same_but_image, ONE copy for every caller (up and back here, the unattended up's D3 and back's check, and
#       03's `real --image-only`): comment lines are not content, and THE LOG-FILE LINE, 03's top-level log-file KEY
#       line (RR_LOGK), may be added once right after the older config's log-level line when that config has no
#       log-file key at all. So the next up (a person's, or the updater's switch) adds the line with all of its checks
#       and its idle restart, and a back puts the config kept before it back: no hand step (README, "The log-file
#       line").
# ONE DOOR (runscaler 0.12 bump, slice H2a; the H2 plan's M-1): an image switch never changes ~/bin/runner. 03 names the
#       two runscalers this release knows (THE RUNSCALERS: BIN_SHA, the pinned v0.12.0, and WAYBACK_BIN_SHA, v0.9.5),
#       which this script reads from $S03 as data (pin03; PINS checks $S03 first); `up` refuses before anything else
#       when ~/bin/runner is neither, naming `pool-image.sh runscaler`, the one step that changes it.
# THE RUNSCALER STEP, `runscaler [VERSION]` (runscaler 0.12 bump, slice H2b-1; the H2 plan's M-3, R-1 to R-6): the one
#       door that changes ~/bin/runner on a host that has one. VERSION: 03's PINNED (the default) or WAYBACK (THE
#       RUNSCALERS, read from $S03 as data: ver03, pin03); any other refuses. It keeps nothing (no rollback, no accept):
#       the way back is this step with the way-back version, after its download. In order, each refusing with nothing
#       changed and naming its fix: (a) PINS; VERSION; no updater window journal; no open image release: a
#       config.toml.pre-image that is config.toml byte for byte is one a `back` closed (removed once every check has
#       passed, and said so: a later `back` cannot put it under another runscaler), any other refuses ("accept, or
#       back"); the unit enabled; the unit active and runscaler started after config.toml was installed (it runs
#       config.toml: the stage compares with it), or active with config.toml installed after its start (a pending
#       config: only this step's own render, byte for byte, goes on, and goes live with this restart: R-1, a run of this
#       step cut before its restart, or a bare 03 real of the same values), or down (inactive, failed, activating: R-3,
#       its restart starts it with no idle wait); VERSION's download by its sha256 (dl_of, 03's own rule). The
#       installed binary may be any: this step is the fix the other doors name. (b) DONE ALREADY: runscaler active,
#       started after config.toml's install, its process running VERSION's binary, ~/bin/runner VERSION's, config.toml
#       with THE LOG-FILE LINE: no stage and no restart, but READY, the running binary and the restart-cut scan below
#       (exit 0 only when READY). (c)+(d) `03-runscaler.sh stage VERSION content|bytes` (03's header, THE STAGE): its
#       compare before anything is installed, this release's runner-start (and the rest, by their PINS), VERSION's
#       runner as ~/bin/runner.new, its validate by that staged binary, then config.toml (only when it differs), THEN
#       the rename over ~/bin/runner. (e) THE RESTART below, whose two shortcuts ("runscaler started after config.toml
#       was installed") hold here only when THE RUNNING BINARY is VERSION's too (a crash restart between 03's two
#       renames runs the old binary on the new config: restart again); READY; the running binary VERSION's (else a FAIL
#       naming journalctl); the restart-cut scan. (f) NEXT: the way back's two lines, or the way forward's. A cut at any
#       point leaves a pair runner-start starts (03's header), and the same line again finishes it.
# THE RUNNING BINARY (the H2 plan's R-6): running_sha, ONE function: systemd's MainPID of runscaler, then the sha256 of
#       PROCFS/<pid>/exe (/proc: the binary that process runs, read through /proc also when ~/bin/runner was renamed over
#       since and it shows "(deleted)"). The cells' copy names their own process table (PROCFS, a pin line).
# ONE RUN AT A TIME: a lock in ~/.config/runner. An ssh drop with no pty can leave the old run alive; a new one then
# refuses and names its pid.
# Then, up, back and runscaler: the restart. restart() re-reads the start time just before it restarts, so it never
# restarts a process that already runs this config.toml (and, in THE RUNSCALER STEP, VERSION's binary: runs_this). If
# runscaler already runs it, no restart; a unit that is down is started at once; else wait up to 10 min for both sets
# to be quiet (no runner, no job), then up to 60 min more for a moment with no runner in its idle phase, then restart
# (SIGTERM = drain: a running job finishes first, up to 70 min) -> READY within 10 min -> name any job a restart cut
# (the runner.log records since config.toml's install, each with its log time: one an earlier run named reads as old).
# PINS: what 03 runs, and what it installs from ~/build before it validates, by sha256. tools/release-check refuses a
# pinned file that changed without its PIN.
#
# THE UNATTENDED MODES: the runner-image updater's switch and rollback (plan D1, D5, D6; S2b-3c-1). Run from ~/build:
#   bash ~/build/setup/pool-image.sh up --unattended VERSION DIGEST   (DIGEST: sha256:<64 hex>, of the build record of
#                                                                     VERSION, which the updater read)
#   bash ~/build/setup/pool-image.sh back --unattended --why r1|r1-connect|back [--verdict FILE] [--old-version V]
#                                                                     (no --why: usage; each option once)
#   bash ~/build/setup/pool-image.sh recover --unattended               (RECOVER, below: ends a window a cut left open)
# THE UPDATER'S CHILD (S2b-3c-1 D-a; PLAN D7 "the unattended modes are the updater's only"): each runs only as the
# child of the updater lock's holder, runner-updater, which hands it the lock on fd 9: runner-release.sh's rr_held
# (fd 9 is the lock; a FRESH open of it cannot take it; fd 9 can), else REFUSE, exit 1, nothing journaled. It never
# takes or waits for that lock itself. A person's rollback is `runner-updater back hz-docker`. RESIDUAL, named: a
# person who takes the lock on fd 9 by hand (the flock(1) idiom) passes. Then this script's own lock (fd 8, -n). Each
# keeps ONE WINDOW JOURNAL, ~/.local/state/runner-updater/window: one `KEY VALUE` line per fact, each appended and
# synced (`dd conv=notrunc,fsync`, its exit status checked) BEFORE the step it names; a journal it cannot write stops
# the window before that step. A journal there at the start REFUSES, nothing changed: an OPEN one (an earlier window
# that did not close: the updater's RECOVER ends it) or a CLOSED one ("closed, not applied: the updater's next pass
# applies it"). A window that ends is CLOSED by THE CLOSING LINES, and its journal STAYS at WINDOW: the updater's apply
# step reads it (only its lines: S2b-3c-1 D-b), then archives it to ~/.local/state/runner-updater/windows/ID. Its files
# (each validate's whole output, the /healthz reads, a rollback's verdict.json and backup) are in windows/ID.d.
# THE CLOSING LINES (D-b (a)): a switch's `prev SHA` (config.toml.prev's sha256 then, or none), then `installed SHA
#   CONTENT CLASS` (config.toml's sha256 and CONTENT sha, PLAN D1: its lines less whole-line comments and blank lines),
#   then `closed E`. CLASS: target-running (the TARGET is installed and runscaler RUNS it, from the window's own last
#   check of config.toml right before `running`, never a new read after it), target-idle (the TARGET installed, none
#   runs it), target-old (the TARGET installed, an older runscaler, started at or before its install, runs: the file
#   before), target-failed (RECOVER's: the TARGET installed, its rollback DECIDED as failed and THE RESTORE could not
#   put the backup back: the candidate stays, nothing is rejected, ROLLBACK FAILED holds; never target-running or
#   target-idle, which read "rolled back"), pre (the window's pre-window file, `config-sha`), other (a file the window
#   did not write, with its STOP HAND CHANGE), none (the journal has no `config-sha` to compare, or config.toml cannot
#   be read). ONE READ PER CLOSE: a close's SHA, CONTENT and CLASS are of one read of config.toml (a close before the
#   rename reads it once for its class), never a class decided before that read; that read's content is mapped by the
#   journal's EFFECT: NO EFFECT, NO TARGET (review r2, codex F3): in a journal with no window `rename-start` the window
#   installed nothing, so a config.toml with the TARGET's content is a person's file: other, never target-*.
# up --unattended: (1) the window's start and runscaler's process (systemd's MainPID and ActiveEnterTimestamp, one read);
#   FAMILY LINES (config.toml's two sets name ONE image, the old image, which the registry must still serve: the
#   rollback's; DIGEST's image already: nothing to switch, config.toml.prev kept as it is: done, `running`, when, checked
#   ONCE after the `config-sha` line, config.toml is still `config-sha` naming DIGEST's image and runscaler RUNS since
#   its install, else `end`); START STATE (the unit active and enabled, config.toml installed before its start: else
#   not now), then `start-state` (config-sha runs: RECOVER may start it with no validate); DISK (RUN_USER's
#   filesystem, D1's data and the registry, at least DISK_PCT % free: runscaler's min_free); jq (`jq --version` a core
#   row of ~/build/core/TESTED_JQ); the PINS; then PRE-VALIDATE: `03-runscaler.sh render
#   DIGEST STAGED` (STAGED = ~/.config/runner/config.staged.toml; 03 refuses a rejected digest), up to 3 tries 20 s
#   apart, each a VALIDATE TRY: exit 0 (PASS) ends them, exit 4 (API-ONLY) tries again and after the third counts as
#   PASS, anything else (a cut try: UNKNOWN) is STOP check failed, nothing installed; then D3: STAGED names DIGEST and
#   differs from config.toml in its runner-image lines alone (THE CONFIG COMPARE). (2) THE IDLE PAIR: two /healthz
#   reads 3 s apart, decided by ~/build/core/idle.jq over every set config.toml names and every set the reads list (no
#   state: no set is excused, the updater keeps the 24 h); a core that fails or answers no idle/not-idle: `end`. Not
#   idle: STAGED removed, config.toml unchanged, the journal removed, exit 3. (3) At once: THE BACKUP to
#   config.toml.prev (the rollback; STAGED must still be the one 03 printed first, else STOP check failed and
#   config.toml.prev stays as it was), then THE RENAME and THE RESTART, below, unconditionally (no idle check again).
# back --unattended: the rollback to config.toml.prev, the backup of the switch it undoes. First, before any effect
#   (D-e): `why`, `verdict` (--verdict FILE copied to windows/ID.d/verdict.json, journaled by its sha256; none),
#   `old-version` (--old-version, else none: the version this rollback leaves, the updater's to name) and
#   `target-version` (the ONE build record of RUN_USER whose digest config.toml.prev names, read by runner-release.sh's
#   rr_record_of as a hostile file; none). THE UNIT (operator (1), 2026-11-05: ENABLED means CI on): not enabled: no
#   restart, `end rollback pending: CI disabled by a person` (the updater tries again); enabled and down (inactive or
#   failed, or activating with no process: the auto-restart wait of a crash loop): the rollback goes on with no
#   started_after test, its restart starts the unit, and a `stop` or `end` before its rename leaves the journal OPEN
#   (NO SILENT END WITH CI DOWN, review r2 codex F4: that last word says runscaler is down and CI is down until the
#   updater's RECOVER starts it, which starts runscaler on the pre-window file, validated first; UNKNOWN stays an `end`,
#   NON-API ROLLBACK FAILED; the sentence only while the unit is still down: A STOP THAT LEAVES CI DOWN, below); enabled
#   and active:
#   config.toml installed after runscaler started: STOP HAND CHANGE (a pending hand edit), else `start-state`;
#   config.toml already the backup, checked ONCE (still `config-sha` and the backup, in one read, and runscaler RUNS
#   since its install): done, `running`, no restart, else `end`; a start or a drain in progress: `end`. No backup, one
#   that does
#   not name ONE image, a config.toml that does not, one that differs from config.toml in more than its runner-image
#   lines (THE CONFIG COMPARE), or one whose image the registry does not serve: STOP ROLLBACK FAILED.
#   PRE-VALIDATE of a copy (STAGED = ~/.config/runner/config.rollback.toml, its lines checked once it is made) by the
#   ONE VALIDATE RULE
#   (~/bin/runner-start validate, stdout and stderr, ~/bin/validate-class), up to 3 tries 20 s apart, each a VALIDATE
#   TRY: PASS ends them, API-ONLY after the third counts as PASS, NON-API is STOP ROLLBACK FAILED and UNKNOWN (a cut try
#   too) is `end` (no STOP: the updater tries again), both before any restart. No idle wait: then THE BACKUP of the
#   config it replaces to windows/ID.d/config.toml.backup (what the updater's RECOVER puts back when the rollback
#   target fails validate: plan D1, RECOVER step 4), THE RENAME and THE RESTART at once (runscaler's drain lets busy
#   runners finish).
# A VALIDATE TRY (D-h; r2 Codex F15, Opus F13 (b)): under `timeout -k 10 120`, in timeout's own process group (every
#   process left in it is killed once the try ends), stdin /dev/null, fd 8 closed, and fd 9 (the updater lock) closed:
#   back's runner-start validate gets no fd 9; 03's render gets it only for its own THE UPDATER'S CHILD check, and
#   closes it at once, before anything else runs. A try the bound cuts (exit 124 or 137) is UNKNOWN. RESIDUAL, named
#   (review r1, opus F3 and codex F8): `timeout` holds fd 9 to pass it to 03, so a killed window's try holds the
#   updater lock until the try ends, at most 130 s (the 120 s bound and its 10 s KILL); the updater's passes meanwhile
#   find the lock held. Every systemctl call of the unattended modes closes fd 8 and fd 9 (`8>&- 9>&-`): a stop client
#   that outlives a killed window (a drain, up to TimeoutStopSec) holds neither lock. Nor does a shell that waits for a
#   read of the unit (S2b-3c-1 B2a; review r4 of B1, codex F4): each `$(systemctl ...)` read closes both first in its
#   command substitution, and proc_now, unit_read and start_of close both in a subshell that runs them (runner-facts.sh,
#   NO SHELL THAT WAITS FOR A READ HOLDS A LOCK): a window killed while a read is pending leaves both locks free.
# THE ORDER OF CHECK AND STEP: each check of a file comes AFTER the journal line of the step it guards and right before
#   that step, and a copy is checked after it is made. A failed check before `rename-start` closes the journal (STOP);
#   after it, the journal closes only when config.toml is provably the window's own pre-window file (just checked),
#   and else stays OPEN with `hand-change` (A HAND CHANGE: nothing restarts on that file) for the updater's RECOVER.
# THE BACKUP: `backup P`, config.toml copied to P.tmp (0600), the copy's sha checked against `config-sha` (else STOP
#   HAND CHANGE, P as it was), renamed to P. From then on a switch's texts say that config.toml.prev holds it.
# THE RENAME: `rename-start`; the INSTALL TIME: STAGED's mtime set by the clock now (`touch -c -m`), so config.toml's
#   mtime second, which started_after reads, is rename-start's or later and renamed's or earlier (never the render or
#   copy time: plan D1); config.toml still `config-sha` (else A HAND CHANGE: nothing renamed) and STAGED still
#   `staged-sha` (else STOP check failed | ROLLBACK FAILED, closed: config.toml is the pre-window file), then STAGED
#   renamed over config.toml at once, `renamed` (UTC epoch: the install time, plan D1), then a wait until the clock's
#   second is past it.
# THE RESTART: `from` (the process it stops), `stopping` (the restart's own epoch), config.toml still the TARGET (else
#   A HAND CHANGE AFTER THE INSTALL: no stop), `systemctl --user stop runscaler` (the drain), `stopped` (once no
#   runscaler runs, before and after: the log position ~/.config/runner/runner.log's inode, its size, and the sha256 of
#   the 64 bytes before it, or none); the unit still ENABLED (D-h: a person's `systemctl --user disable --now
#   runscaler` during the window), else no start, `stop CI DISABLED`, the closing lines and exit 1; `starting`, the
#   TARGET again (else no start: runscaler stays stopped), `systemctl --user start runscaler`, then up to 10 min of the
#   clock until runscaler RUNS (runner-facts.sh's runs: /healthz lists every set of the TARGET on two reads 3 s apart,
#   and the same process, started after `renamed`, before and after them; never one `active` read: runscaler.service is
#   Type=simple with Restart=always), with config.toml still the TARGET (else the hand-change STOP): `running`. No RUNS
#   in 10 min: `pre-close-failure` and the journal stays open. The updater hands the core facts.restart = {from, to:
#   running, stopped} (core/README.md). A kill anywhere after `rename-start` leaves the journal open, and the old file
#   is never put back: the updater's RECOVER ends it.
# THE RESIDUALS (instants no lock-free design closes, each a few ms): a hand edit of config.toml after the rename's
#   check and before the rename is replaced by it; a runscaler start in a later second than the install time's and
#   before the rename reads as started after the install; a change of config.toml after the start's check and before
#   runner-start reads the file is started on (the check after the start sees it: `hand-change`, the journal open,
#   but that process may run either file).
# A STOP THAT LEAVES CI DOWN SAYS SO (review r3, opus F2; the r3 FOLD's OPERATOR (1): "else a STOP that says CI is
#   down"): every exit of the window or of RECOVER that leaves the journal OPEN with the enabled unit down and nothing
#   started has a line of its own that says CI is down: a HAND CHANGE's STOP (the window's, before its rename or after
#   it, and RECOVER's ONE RULE exits) carries the sentence "runscaler is down …: CI is down until the updater's RECOVER
#   starts it"; a file that does not validate while no runscaler runs: STOP POOL DOWN with the validate's class and its
#   output's path, once per file; a config.toml that cannot be read: STOP POOL DOWN, once. THE CI-DOWN WORDS ARE TRUE
#   WHEN WRITTEN (review r3, codex F2): the sentence goes in only when ONE unit_read right then finds the unit enabled
#   and down (inactive or failed, or activating with no process), never from the unit as it was when the window began;
#   the journal stays open as before either way; and a STOP POOL DOWN of a file that does not validate is written only
#   when a RUNS read right before it still finds no runscaler that RUNS (review r4 of B1, opus F1: the read that routed
#   there came before the validate). ITS ADVICE WORKS WHILE IT IS OPEN (review r4 of B1, opus F2): a line in an open
#   journal names no `03-runscaler.sh` step (03 refuses while a window journal is there), only hand steps and
#   runner-start validate. A step that FAILED (a journal write, a copy, a touch, a rename, a systemctl call) writes no
#   such line (ufail; RECOVER's: the line printed): the next pass tries that step again.
# RECOVER, `recover --unattended` (S2b-3c-1 D-c, D-d and its r3 FOLD; PLAN D1, D5 RECOVER): it ends a window journal a
#   cut left OPEN (the window's own process is gone: the updater's lock, which a window holds for its whole run, is the
#   updater's, who runs RECOVER as its child), and leaves it CLOSED at WINDOW with THE CLOSING LINES for the updater's
#   apply step. It reads the journal ONCE, only by the grammar below: an unterminated last line is D1's lost line,
#   dropped (kept aside as windows/ID.d/journal.cut and cut from the journal before RECOVER's first own line); any other
#   line no pattern reads, or a `backup` with no kind, config-sha, staged, staged-sha or target before it, is a STOP
#   that names linux-docker/README.md "An unfinished window the updater cannot end": nothing written, exit 6. Its first
#   own line is `recover-start E` (once per journal). It decides by THE INSTALLED FILE (config.toml read once: its
#   CONTENT against the TARGET's, `target-content`, or a journal with none its sha against `staged-sha`; its sha against
#   `config-sha` and the last `recover-target`) and by THE UNIT (runner-facts.sh's unit_read, one `systemctl --user
#   show`), never by which lines survived. RECOVER needs no jq but for a switch's idle pair. Hetzner deletes nothing. In
#   order:
#   0. the last line `closed`: nothing (exit 0: the apply step's); `installed` the last line: `closed` alone.
#   ONCE-LINES (review r1, codex F6): a STOP written once is keyed on the STOP line itself: a `hand-change H` whose
#      `stop HAND CHANGE` a cut lost gets it first thing, from RECOVER (the window's marker too); other once-STOPs on
#      their own `stop` line.
#   1. NO EFFECT YET (no `config-sha`, or no `backup`): the window changed no config and stopped nothing. STAGED
#      removed; a runscaler that RUNS (whenever it started): closed (pre, other with STOP HAND CHANGE, or none); none
#      runs and the unit is enabled (OPERATOR (1)): THE START on a proven sha (below), else once a copy validates; not
#      enabled: STOP CI DISABLED unless one RUNS. A file with the TARGET's content is other here, and in steps 2-5 too
#      while the journal has no window `rename-start` (NO EFFECT, NO TARGET).
#   DECIDED LINES (a ROLLBACK, right after 0 and 1; B1 DECISIONS, the Studio's runner-updater-window :298-305): lines
#      about its TARGET only: a `validate recover N NON-API|UNKNOWN` (RECOVER's validate of the TARGET; another file's
#      is `validate hand N`), a `restore`, a `stop ROLLBACK FAILED`, or a `pre-close-failure` of a start OF THE TARGET
#      (the window's own `starting E`, written only after its `renamed`, or RECOVER's `starting E target`; RECOVER's
#      `starting E pre` and `starting E other` decide nothing): THE RESTORE, with no new validate of the TARGET;
#      NON-API and a TARGET start that did not run hold STOP ROLLBACK FAILED, UNKNOWN none. A close that finds the
#      TARGET installed is target-failed (the backup fails its check; the unit not enabled with a process running).
#   2. THE UNIT: a drain (deactivating: a stop job that outlived its client too) is waited for until it ends (4320 s of
#      the clock, else the journal open); NOT enabled (UnitFileState): nothing is stopped or started, `stop CI
#      DISABLED` naming what is installed and what runs, closed (target-running | target-idle | target-old | pre |
#      other). A rollback is done only when its TARGET runs: target-old (a person's `disable` without --now left the
#      older runscaler running) keeps the candidate at the apply step.
#   3. INSTALLED = the TARGET: (a) runscaler RUNS since the install (THE INSTALL BOUNDARY, codex F3: max(the window's
#      `renamed`, config.toml's mtime now); a start by another actor after it proves the TARGET too): closed
#      target-running; a ROLLBACK's start of its TARGET in progress (an open `starting` of the TARGET): waited for to
#      its deadline, never made again (the stopped unit started again with no new line, its sha checked right
#      before), on a sha a line proves (a comment-edited TARGET: its copy validated first, as in (c), then that start
#      resumed); expired: ONE `pre-close-failure`, DECIDED, THE RESTORE in the same pass; (c) an older runscaler runs
#      (a process of any health that started at or before that boundary: it must be stopped before the TARGET can
#      run): a SWITCH's IDLE RESTART, a ROLLBACK's restart at once (its TARGET validated first, a copy: PASS or
#      API-ONLY after 3 -> `recover-target`; NON-API -> STOP ROLLBACK FAILED and THE RESTORE; UNKNOWN -> THE
#      RESTORE); (b) none runs it: THE START (a ROLLBACK's TARGET validated first, as in (c); a SWITCH's validated sha
#      needs none: `staged-sha`, or a `recover-target`).
#   4. INSTALLED = PRE (`config-sha`) and no window `renamed`: nothing was installed: a runscaler that RUNS: closed pre
#      (its journaled STOP kept); none runs: THE START on it (OPERATOR (1); validated first unless `start-state`).
#   5. INSTALLED = OTHER (PLAN D5's ONE RULE; PRE after a window `renamed` too: a person put the old file back): STOP
#      HAND CHANGE (`hand-change` first, once per sha); a runscaler that RUNS: nothing restarts, closed other; none: a
#      copy validated (PASS, or API-ONLY after 3), `recover-target`, THE START past the file's mtime, closed other;
#      NON-API or UNKNOWN: no start, then STOP POOL DOWN (CI is down: the validate's class and its output's path; once
#      per file), the journal open (the next pass validates it again). config.toml = the last `recover-target`'s sha
#      is RECOVER's own file (validated already), never OTHER.
#   "A runscaler that RUNS" is runner-facts.sh's RUNS everywhere (codex F7): /healthz lists every set on two reads
#      3 s apart, the same process; never one `proc_now` (a process that hangs before it serves is no runscaler that
#      runs: THE START, which reports CI down). Steps 1, 4, 5 take a process that RUNS whenever it started (one older
#      than the file may run an older file: nothing restarts); 3a and THE RESTORE's backup need one since the install.
#   THE START (D-d, r3 FOLD): the unit enabled and the config's sha proven; at most ONE new start per pass. A START
#      NEEDS A VALIDATED SHA (codex F2): `staged-sha` (no failed `validate recover` after it), the last
#      `recover-target`, or `config-sha` after the window's `start-state`; any other sha (a pending hand edit the
#      window journaled before START STATE, a rollback that found the unit down) a copy validates first (`validate
#      hand N`, the ONE VALIDATE RULE): NON-API or UNKNOWN: no start, the journal open: another file: STOP HAND CHANGE,
#      then STOP POOL DOWN that says CI is down; the pre-window file: STOP POOL DOWN that says CI is down (each once per
#      file, with the validate's class and its output's path). A `recover-target` names only a proven sha, and
#      only a value its own reader reads (digest images; else STOP HAND CHANGE that says why, no start). An attempt is
#      a `starting E WHAT` (WHAT: target | pre | other, what it starts). A RESUMED START IS OF THE FILE IT STARTS
#      (review r2, opus F1, codex F1): one in progress (now < E + 600) is waited for only when it is of the file now to
#      start (its WHAT; for pre and other also its sha, the one the `recover-target` before it names), a unit that is
#      down started again with no new line; an open start of another file is no failure of this one and is not
#      resumed: a new `starting`. A START IS CHECKED RIGHT BEFORE IT (codex F2): every `systemctl --user start` of
#      RECOVER, a resumed one too, comes right after the check that config.toml is still the sha proven for that start
#      (else the ONE RULE: `hand-change`, STOP HAND CHANGE, open, nothing started). A new one waits past max(the
#      install, the file's mtime), journals `starting`, checks config.toml so, then `systemctl --user start
#      runscaler`, then up to E + 600 s of the clock (THE START'S DEADLINE: the journal's own epoch, so it holds
#      across passes; an activating unit is waited for only inside it) until runscaler RUNS, config.toml checked once
#      more: `running`, closed. Past
#      the deadline with no RUNS, whatever the unit shows (activating, failed, active and not RUNS): ONE pre-close
#      failure per journal (`pre-close-failure`; the window's own counts), the journal open; the second: STOP POOL
#      DOWN (the hand line), closed (a switch's TARGET stays installed: P for PLAN D5 RECOVER 4 :299), its class that
#      of the close's own read (a file a person put in place meanwhile: other, STOP HAND CHANGE).
#   THE IDLE RESTART (a switch, operator (2)): each pass the validate first (when the sha needs it: a SWITCH'S FAILED
#      VALIDATE is the ONE RULE: `hand-change`, STOP HAND CHANGE, no start, the journal open), then ONE idle pair (the
#      window's uidle: an untested jq, or a core that cannot decide, reads as not idle and the line says so), then at
#      once `from`, `stopping`, config.toml still that sha, the stop, `stopped`, the unit still enabled, THE START. Not
#      idle: the journal open, "the switch waits for idle". 3 days after `recover-start`: STOP NO IDLE with the hand
#      line (`systemctl --user restart runscaler` at a quiet moment: the next pass sees it run and closes), journaled
#      once, printed at each pass; never an automatic restart.
#   THE RESTORE (a decided rollback): a copy of its `backup` (windows/ID.d/config.toml.backup) checked against
#      `config-sha` FIRST (else STOP ROLLBACK FAILED, nothing stopped, closed); config.toml checked BEFORE the stop too:
#      the TARGET (`staged-sha`), or the backup already (a replay); another file: the ONE RULE (step 5), nothing
#      stopped or put back. Then `restore`, the unit stopped (`systemctl --user stop` also ends a drain or an
#      auto-restart) until inactive or failed with MainPID 0, `rename-start`, the copy's mtime set to now, no runscaler
#      process, config.toml still the TARGET (by its CONTENT; else `hand-change`), the rename, `renamed`,
#      `recover-target` (the backup's sha, once proven: validated first unless `start-state`), THE START past that
#      second (an older runscaler: stopped and started at once). The unit not enabled: the backup is put back only with
#      no process running (else CI DISABLED, target-failed), never started: CI DISABLED names the backup. A file
#      RECOVER validated and started for a person is never put back over (THE ONE RULE). No mtime is ever set back.
#   RECOVER's validate tries are VALIDATE TRIES (above): a copy of config.toml, ~/.config/runner/config.recover.toml,
#   `validate recover N CLASS` (the TARGET) or `validate hand N CLASS` (another file) each
#   (windows/ID.d/validate-STEP-N.out).
# The journal, line by line (V = N.N.N, H = 64 hex, P = an absolute path, I = an image reference, E = UTC epoch):
#   window ID                   ^window [0-9]{14}-[0-9]+$     (UTC yyyymmddHHMMSS-pid): the first line
#   kind switch|rollback        ^kind (switch|rollback)$
#   version V                   (switch)
#   digest sha256:H             (switch)
#   why r1|r1-connect|back      (rollback) why the updater rolls back: R1's verdict, R1's connect-only one, a person's
#   verdict H|none              (rollback) the sha256 of windows/ID.d/verdict.json, the --verdict FILE's copy
#   old-version V|none          (rollback) the version this rollback leaves (--old-version)
#   target-version V|none       (rollback) the version of the ONE build record of config.toml.prev's digest
#   process PID START | none    runscaler at the window's start (MainPID, ActiveEnterTimestamp)
#   old I                       the image config.toml names at the window's start (a rollback's target: `target`)
#   config-sha H                config.toml at the window's start
#   start-state E               START STATE passed (up; back: the unit active, started after the install): config-sha
#                               runs
#   staged P                    before STAGED is written
#   validate pre N CLASS        ^validate pre [1-3] (PASS|API-ONLY|NON-API|UNKNOWN)$   (windows/ID.d/validate-pre-N.out)
#   staged-sha H                the validated STAGED: the TARGET
#   target SET=I SET=I          the TARGET's lines, in config order
#   target-content H            the TARGET's CONTENT sha (whole-line comments and blank lines left out)
#   idle idle                   (switch) the idle pair said idle
#   backup P                    before THE BACKUP: P holds config.toml as it was at the window's start (`config-sha`)
#                               once `rename-start` follows: config.toml.prev (switch), windows/ID.d/config.toml.backup
#                               (rollback)
#   rename-start E              before the install time and the rename
#   renamed E                   after it: the install time
#   [hand-change H|unreadable]  config.toml after `rename-start`, not the file the window expects: the journal stays open
#   from PID START | none       the process the restart stops
#   stopping E                  before `systemctl --user stop`: the restart's own epoch
#   stopped INODE OFFSET H | none
#   starting E                  before `systemctl --user start` (the window's: of its TARGET)
#   running PID START           the new process: it RUNS, started after `renamed` (with no rename: after config.toml's
#                               install)
#   [pre-close-failure TEXT]    the start did not RUN within 10 min (once per journal): the journal stays open
#   stop NAME: TEXT             a STOP (check failed | DISK | untested jq | HAND CHANGE | ROLLBACK FAILED | CI DISABLED;
#                               RECOVER's: POOL DOWN | NO IDLE too)
#   RECOVER's own lines, after the window's (each before its step, as above):
#   [recover-start E]           RECOVER's first line, once per journal
#   [validate recover|hand N CLASS]  ^validate (recover|hand) [1-3] (PASS|API-ONLY|NON-API|UNKNOWN)$: recover is the
#                               TARGET's, hand another file's (windows/ID.d/validate-STEP-N.out)
#   [recover-target H SET=I..]  RECOVER's own TARGET: the sha and the lines of the config it starts (D1), once per sha
#   [starting E WHAT]           RECOVER's start: WHAT target | pre | other (the window's TARGET; config-sha or the
#                               restored backup; another file); pre and other start the sha of the `recover-target`
#                               before it
#   [restore P]                 THE RESTORE begins: P is the rollback's backup (windows/ID.d/config.toml.backup)
#                               and `from`, `stopping`, `stopped`, `rename-start`, `renamed`, `starting`, `running`,
#                               `pre-close-failure`, `hand-change`, `stop` and the closing lines as the window's
#   end TEXT                    the window ended with no STOP (the updater tries again later)
#   prev H|none                 (switch) THE CLOSING LINES: config.toml.prev's sha256 then
#   installed H|none H|none CLASS   THE CLOSING LINES: config.toml's sha256 and CONTENT sha, and its CLASS
#                               (target-running|target-idle|target-old|target-failed|pre|other|none)
#   closed E                    the last line: the journal stays at WINDOW for the updater's apply step
# Exit codes of the unattended modes (the updater's interface; it reads the rest from the journal and the files):
#   0  done: the target runs (a process started after `renamed`, or with nothing to switch after config.toml's install);
#      the journal closed
#   1  not done: the closed journal's `stop` or `end` line says why; or the journal is still OPEN (a step after
#      `rename-start` failed or was cut, or A HAND CHANGE found after it, or a rollback that found the enabled unit down
#      ended before its rename: its `stop` or `end` the last line): the updater's RECOVER ends it; or a
#      REFUSE before any journal (not RS_USER, not the updater's child, this script's lock, a journal at WINDOW)
#   2  usage
#   3  not now (up): START STATE not met, or not idle; nothing staged, nothing changed, no journal kept
# Exit codes of RECOVER (`recover --unattended`, the updater's interface):
#   0  the journal at WINDOW is closed (by this run, or before it): the updater's apply step applies it
#   1  a REFUSE before the journal was read (not RS_USER, not the updater's child)
#   2  usage
#   3  no window journal: nothing to recover
#   4  WAIT: another pool-image.sh run (a person's) holds this script's own lock: nothing read or changed
#   5  the journal stays OPEN: the line printed says why (a STOP: HAND CHANGE, NO IDLE, POOL DOWN of a file that does
#      not validate or cannot be read; a wait for idle; a start not run yet; a drain, a step that failed); the
#      updater's next pass runs RECOVER again
#   6  a record RECOVER cannot read or act on: STOP, nothing written (README "An unfinished window the updater cannot
#      end")
set -uo pipefail
# THE HOST CONFIG: every value of this host (users, ports, addresses, names) is in HOST_CONF, root's file, never in
# this script; linux-docker/host.conf.example names each key. Absent, not root's, writable by another user, a line that
# is not KEY=value, any key twice (read or not) or a key missing: REFUSE on stderr, exit 1, before anything else runs.
HOST_CONF=/etc/liveapp-ci/host.conf
host_conf() {   # host_conf SCRIPT KEY...: each named KEY's line in HOST_CONF sets that variable
  local me=$1 l k o seen=" "; shift
  o=$(stat -c '%a %U' "$HOST_CONF" 2>/dev/null) || { echo "$me: REFUSE no host config $HOST_CONF (linux-docker/README.md)" >&2; exit 1; }
  [[ $o =~ ^[0-7][0145][0145]\ root$ ]] || { echo "$me: REFUSE $HOST_CONF must be root's and writable by root only: [$o]" >&2; exit 1; }
  while IFS= read -r l || [ -n "$l" ]; do
    case $l in ''|'#'*) continue ;; esac
    [[ $l =~ ^([A-Z][A-Z0-9_]*)=([A-Za-z0-9][A-Za-z0-9._:/-]*)$ ]] || { echo "$me: REFUSE $HOST_CONF: want KEY=value, got [$l]" >&2; exit 1; }
    k=${BASH_REMATCH[1]}; [[ $seen != *" $k "* ]] || { echo "$me: REFUSE $HOST_CONF names $k twice" >&2; exit 1; }
    seen="$seen$k "; [[ " $* " == *" $k "* ]] || continue
    printf -v "$k" %s "${BASH_REMATCH[2]}"
  done < "$HOST_CONF"
  for k in "$@"; do [[ $seen == *" $k "* ]] || { echo "$me: REFUSE $HOST_CONF lacks $k (linux-docker/host.conf.example)" >&2; exit 1; }; done
}
host_conf pool-image.sh RUN_USER RS_USER REGISTRY_PORT RS_HEALTH_PORT IMAGE_NAME MAIN_SET SMALL_SET
MODE=${1-} VERSION= DIGEST= UN=0 WHY= VERDICT= OLDV= RSV= WANT= DONE=0 PINNED=
usage() { echo "usage: pool-image.sh up RUNNER_VERSION (for example 2.338.2) | back | accept | runscaler [VERSION]   (a person's)"
  echo "       pool-image.sh up --unattended RUNNER_VERSION DIGEST"
  echo "                   | back --unattended --why r1|r1-connect|back [--verdict FILE] [--old-version VERSION]"
  echo "                   | recover --unattended"
  echo "         (the updater's only, as its child holding the updater lock on fd 9; DIGEST: sha256:<64 hex>)"; exit 2; }
case $MODE:$# in
  up:2) VERSION=$2 ;;
  up:4) [ "$2" = --unattended ] || usage; UN=1 VERSION=$3 DIGEST=$4; [[ $DIGEST =~ ^sha256:[0-9a-f]{64}$ ]] || usage ;;
  back:1|accept:1|runscaler:1) ;;
  runscaler:2) RSV=$2; [[ $RSV =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || usage ;;
  back:*) [ "$2" = --unattended ] || usage; UN=1; shift 2
    while [ "$#" -gt 0 ]; do   # each option once, each with its value
      case $1:$# in
        --why:1|--verdict:1|--old-version:1) usage ;;
        --why:*) [ -z "$WHY" ] && [[ $2 =~ ^(r1|r1-connect|back)$ ]] || usage; WHY=$2 ;;
        --verdict:*) [ -z "$VERDICT" ] && [ -f "$2" ] && [ -r "$2" ] || usage; VERDICT=$2 ;;
        --old-version:*) [ -z "$OLDV" ] && [[ $2 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || usage; OLDV=$2 ;;
        *) usage ;;
      esac
      shift 2
    done
    [ -n "$WHY" ] || usage ;;
  recover:2) [ "$2" = --unattended ] || usage; UN=1 ;;
  *) usage ;;
esac
[ "$MODE" != up ] || [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || usage
R=$HOME/.config/runner; CFG=$R/config.toml; KEEPC=$R/config.toml.pre-image; POOL=$R/pool.env; LOCK=$R/pool-image.lock
BUILDS=/home/${RUN_USER}/run/builds; REG=http://127.0.0.1:${REGISTRY_PORT}; D1=unix:///home/${RUN_USER}/run/docker.sock; B=$HOME/build
S03=$B/setup/03-runscaler.sh
# THE RUNNING BINARY (the header): the process table whose <pid>/exe is the binary a process runs
PROCFS=/proc
# The unattended modes' files (the header): the window journal, the closed ones, the rollback, the decision core
STATE=$HOME/.local/state/runner-updater; J=$STATE/window; WINDOWS=$STATE/windows; KEEPP=$R/config.toml.prev; CORE=$B/core
DISK_PCT=10   # runscaler's min_free (plan D5 DISK): the share of D1's filesystem a switch leaves free
# What 03 runs, and what it installs from ~/build before it validates, by sha256 (the header says why).
PINS="$S03=7722523217b86c8b5cb9683e2cd0103f9092b76682a4f877aac5046d94ffe375
$B/bin/runner-start=c3ea9dc7fce283128a6fc2e908397c89290086b17e816c10a2aece075a717b1e
$B/bin/pool-ready=e6559491799be657c22fe196df119b3a051622ef99020496f92d10635ef1d22f
$B/bin/validate-class=b5127e6e18e926976b62b15f0dd0eead26085657c192ad4b111ccc2defaceda2
$B/config/runscaler.service=1f23a5c0f78c7fa6e7c8ddf0e9092c188666729177dce19ff1a8fe149e498565"
SETS="${MAIN_SET} ${SMALL_SET}"
IMGRE='^localhost:'"${REGISTRY_PORT}"'/'"${IMAGE_NAME}"'@sha256:[0-9a-f]{64}$'   # the image reference a config names
ok() { echo "OK   $*"; }
die() { echo "FAIL $*"; exit 1; }
put() {   # put SRC DEST: copy, 0600, in one rename — with a FRESH mtime: the restart rule below reads config.toml's
  # mtime as the time it was installed (`cp -p` would keep the old one, so `back` would skip the restart)
  cp "$1" "$2.tmp" && chmod 600 "$2.tmp" && mv -f "$2.tmp" "$2" || die "could not write $2: read $R"
}
image_of() {   # image_of FILE: the ONE runner-image both sets name; empty (and rc 1) when the sets disagree or name none
  local imgs; imgs=$(sed -n 's/^runner-image = "\(.*\)"$/\1/p' "$1" 2> /dev/null | sort -u)
  [ "$(grep -c '^runner-image = ' "$1" 2> /dev/null)" = 2 ] && [ "$(printf '%s\n' "$imgs" | grep -c .)" = 1 ] \
    && [[ $imgs =~ $IMGRE ]] && echo "$imgs"
}
pulls() {   # pulls IMAGE: 0 = the local registry serves this digest; 1 = it answers that it does not; 2 = no answer
  curl -fs -m 5 -o /dev/null -I -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json' \
    "$REG/v2/${IMAGE_NAME}/manifests/${1#*@}"
  case $? in 0) return 0 ;; 22) return 1 ;; *) return 2 ;; esac
}
pin03() {   # NAME: 03's pin line NAME=<64 hex> (ONE DOOR, the header), read from $S03 as data; rc 1 unless it is there once
  local v; v=$(sed -n "s/^$1=\([0-9a-f]\{64\}\)\$/\1/p" "$S03" 2> /dev/null)
  [[ $v =~ ^[0-9a-f]{64}$ ]] && echo "$v"
}
runner_sha() { local s; s=$(sha256sum < "$HOME/bin/runner" 2> /dev/null) && echo "${s%% *}"; }   # ~/bin/runner's
ver03() {   # NAME: 03's version line NAME=N.N.N (THE RUNSCALERS), read from $S03 as data; rc 1 unless it is there once
  local v; v=$(sed -n "s/^$1=\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)\$/\1/p" "$S03" 2> /dev/null)
  [[ $v =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] && echo "$v"
}
dl_of() {   # dl_of VERSION: its download (THE RUNSCALERS, ONE DOOR): the pinned one's is Install step 4's file
  if [ "$1" = "$PINNED" ]; then echo "$B/dl/runner-linux-amd64.tar.gz"; else echo "$B/dl/runner-v$1-linux-amd64.tar.gz"; fi
}
running_sha() {   # THE RUNNING BINARY (the header): the sha256 of the binary runscaler's process runs; rc 1 when no
  # process runs or its binary cannot be read
  local pid s
  pid=$(exec 8>&- 9>&-; systemctl --user show runscaler -p MainPID --value 2> /dev/null)
  [[ $pid =~ ^[1-9][0-9]*$ ]] || return 1
  s=$(sha256sum < "$PROCFS/$pid/exe" 2> /dev/null) || return 1
  s=${s%% *}; [[ $s =~ ^[0-9a-f]{64}$ ]] && echo "$s"
}
rs_name() {   # SHA: which runscaler a binary of that sha256 is (THE RUNSCALERS), for a person's line
  case ${1-} in
    "$(pin03 BIN_SHA)") echo "runscaler v$(ver03 PINNED)" ;;
    "$(pin03 WAYBACK_BIN_SHA)") echo "runscaler v$(ver03 WAYBACK)" ;;
    none|'') echo "none" ;;
    *) echo "a runscaler this release does not know (sha256 ${1:0:12})" ;;
  esac
}
pv() { sed -n "s/^$1=\([0-9][0-9]*\)$/\1/p" "$POOL" 2> /dev/null; }   # one number from pool.env (twice = no match below)
holds_pool() {   # holds_pool FILE: does this config carry pool.env's numbers, the ones 03 renders?
  local c cpu mem max scpu smem
  c=$(pv CONCURRENT); cpu=$(pv CPU); mem=$(pv MEMORY); max=$(pv MAX); scpu=$(pv SMALL_CPU); smem=$(pv SMALL_MEMORY)
  [ "$(sed -n 's/^concurrent = //p' "$1" | paste -sd ' ' -)" = "$c" ] \
    && [ "$(sed -n 's/^cpu = //p' "$1" | paste -sd ' ' -)" = "$cpu $scpu" ] \
    && [ "$(sed -n 's/^memory = //p' "$1" | paste -sd ' ' -)" = "$mem $smem" ] \
    && [ "$(sed -n 's/^max-runners = //p' "$1" | paste -sd ' ' -)" = "$max 1" ]
}
start_of() {   # runscaler's last start, in epoch seconds (systemd's own number: no date parsing)
  local a; [ "$BASHPID" = "$$" ] || exec 8>&- 9>&-   # no shell that waits for a read holds a lock (runner-facts.sh)
  a=$(exec 8>&- 9>&-; systemctl --user show runscaler -p ActiveEnterTimestamp --value --timestamp=unix 2> /dev/null); a=${a#@}
  [[ $a =~ ^[0-9]+$ ]] && echo "$a"
}
started_after() {   # runscaler is active and started after config.toml was installed: it runs this config.toml
  local a
  [ "$(exec 8>&- 9>&-; systemctl --user is-active runscaler 2> /dev/null)" = active ] && a=$(start_of) && [ "$a" -gt "$(stat -c %Y "$CFG")" ]
}
runs_this() {   # the restart's two shortcuts: runscaler runs this config.toml (started_after) and, in THE RUNSCALER
  # STEP, the binary of its VERSION too (THE RUNNING BINARY: a process older than the binary's rename runs the old one)
  started_after || return 1
  [ "$MODE" != runscaler ] || [ "$(running_sha)" = "$WANT" ]
}
ready() { "$HOME/bin/pool-ready" $SETS; }
# counts MODE: the two expected sets' COUNTS on two reads of /healthz 3 s apart — never READY (a rollback with GitHub
# down must not stall), and a set missing or no answer is "not yet". quiet = no runner and no job: idle=0 busy=0 and
# no desired_runners/assigned_jobs/running_jobs (left out of the JSON when 0). noidle = no runner in its IDLE phase
# (busy may be >0). Why both (measured): a runner started for a job GitHub has assigned reads idle=1 until
# runscaler hears "Job started", and the SIGTERM drain removes idle-phase runners — it cut two jobs that way. A
# restart with idle=0 on every set cuts nothing; a busy runner only makes the drain long.
counts() {
  local j i
  for i in 1 2; do
    # the pause is BETWEEN the reads, so the restart follows the last read at once (a job reaches a fresh runner
    # 4-5 s after it starts, and a pause after the last read would eat that margin)
    [ "$i" = 1 ] || sleep 3
    j=$(curl -fs -m 5 http://127.0.0.1:${RS_HEALTH_PORT}/healthz) || return 1
    printf '%s' "$j" | python3 -c '
import json, sys
mode, want = sys.argv[1], sys.argv[2].split()
sets = {s.get("name"): s for s in (json.load(sys.stdin).get("scale_sets") or [])}
def calm(s):
    m = s.get("metrics") or {}
    if s.get("idle") != 0:
        return False
    return mode == "noidle" or (s.get("busy") == 0 and not any(m.get(k) for k in ("desired_runners", "assigned_jobs", "running_jobs")))
sys.exit(0 if all(n in sets and calm(sets[n]) for n in want) else 1)' "$1" "$SETS" || return 1
  done
}
# restart: never in config.toml's own second. started_after compares WHOLE seconds (`-gt`, which must stay strict: a
# start in that second can come just before the install), so a restart in the install's second would read as "started
# before the install" (on a host an install and a start came 107 ms apart). And never a second time: it re-reads
# the start just before it restarts.
restart() {
  while [ "$(date +%s)" -le "$(stat -c %Y "$CFG")" ]; do sleep 0.2; done
  if runs_this; then ok "runscaler already started after config.toml was installed: no second restart"; return 0; fi
  systemctl --user restart runscaler 9>&-   # fd 8 kept: a drain that outlives this run holds ONE RUN AT A TIME's lock
}
again() {
  case $MODE in
    up) echo "Run pool-image.sh up again once that is fixed, or pool-image.sh back to go back" ;;
    back) echo "Run pool-image.sh back again once that is fixed" ;;
    *) echo "Run pool-image.sh runscaler $RSV again once that is fixed, or go the way back (README \"runscaler: the release this one pins, and the way back\")" ;;
  esac
}

pins_bad() {   # the first file PINS names whose sha256 is not its PIN (rc 0), or rc 1 when every one is the reviewed copy
  local p
  while IFS= read -r p; do
    [ "$(sha256sum "${p%=*}" 2> /dev/null | cut -d' ' -f1)" = "${p##*=}" ] || { echo "${p%=*}"; return 0; }
  done <<< "$PINS"
  return 1
}

# ---- THE UNATTENDED MODES (the header)
usay() { echo "pool-image.sh: $*"; }
clean() { REPLY=${1//[[:cntrl:]]/?}; REPLY=${REPLY:0:900}; }   # a tool's text as one journal value (LC_ALL=C: bytes)
sha_of() { REPLY=$(sha256sum < "$1" 2> /dev/null) && REPLY=${REPLY%% *} && [[ $REPLY =~ ^[0-9a-f]{64}$ ]] || REPLY=unreadable; }
uj() {   # KEY VALUE: one journal line, appended, then synced (dd's exit status checked); rc 1 when it is not on disk
  local v=${2-}
  { [[ $v != *[[:cntrl:]]* ]] && [ "${#v}" -le 1000 ]; } || return 1
  printf '%s %s\n' "$1" "$v" >> "$J" && dd if=/dev/null of="$J" conv=notrunc,fsync 2> /dev/null < /dev/null
}
UFAIL_RC=1   # the exit of a window that stops with its journal open (RECOVER's: 5)
ufail() { echo "FAIL $*"; exit "$UFAIL_RC"; }   # the window stops here; its journal stays as it is (open)
ujs() { uj "$@" || ufail "the window journal $J could not record '$1': the window stops before that step (the journal stays open)"; }
content_of() {   # FILE: REPLY = its CONTENT sha (PLAN D1): the sha256 of its lines whose first non-blank character is not
  # `#` and that are not blank, each with its newline (the Studio's ru_w_shas): runner-release.sh's rr_content, the ONE
  # copy THE CONFIG COMPARE reads too; `unreadable` when it cannot be read
  REPLY=$(rr_content "$1" | sha256sum) && REPLY=${REPLY%% *} && [[ $REPLY =~ ^[0-9a-f]{64}$ ]] || REPLY=unreadable
}
cfg_now() {   # config.toml read ONCE: a private copy, WDIR/config.now (kept until the next call: NOW_COPY), and its
  # NOW_SHA and NOW_CONTENT; both `none` when it cannot be read
  NOW_COPY=$WDIR/config.now
  rm -f -- "$NOW_COPY"
  NOW_SHA=none NOW_CONTENT=none
  cp -- "$CFG" "$NOW_COPY" 2> /dev/null < /dev/null || return 1
  sha_of "$NOW_COPY"; [ "$REPLY" = unreadable ] || NOW_SHA=$REPLY
  content_of "$NOW_COPY"; [ "$REPLY" = unreadable ] || NOW_CONTENT=$REPLY
  [ "$NOW_SHA" != none ] && [ "$NOW_CONTENT" != none ] || { NOW_SHA=none NOW_CONTENT=none; return 1; }
}
uclosing() {   # SHA CONTENT CLASS: THE CLOSING LINES (the header): a switch's `prev` (config.toml.prev's sha now),
  # `installed`, `closed`. The journal STAYS at WINDOW: the updater's apply step reads it, then archives it
  local p=none
  if [ "${KIND-}" = switch ]; then
    if [ -f "$KEEPP" ] && [ ! -L "$KEEPP" ]; then sha_of "$KEEPP"; [ "$REPLY" = unreadable ] || p=$REPLY; fi
    ujs prev "$p"
  fi
  ujs installed "$1 $2 $3"
  ujs closed "$(date +%s)"
}
BACKED=0   # THE BACKUP renamed its copy into place (up: config.toml.prev now holds this window's backup)
UDOWN=0 UOPEN=0 UWORD=0   # back found the enabled unit DOWN (CI on, nothing runs: operator (1)); a last word left it
# open; that last word says CI is down (udown_word)
udown_word() {   # TEXT [open]: REPLY = TEXT, and the sentence that says runscaler is down and CI is down (UWORD=1) when
  # the journal stays OPEN after this last word (open: a HAND CHANGE's, the window's uhand or RECOVER's rc_hand; else a
  # rollback that found the enabled unit down, UDOWN, ending before its rename) AND one unit_read right then finds the
  # unit enabled and down (inactive or failed, or activating with no process: the auto-restart wait). A STOP THAT LEAVES
  # CI DOWN SAYS SO; THE CI-DOWN WORDS ARE TRUE WHEN WRITTEN (review r3, codex F2): never from the unit as it was when
  # the window began. TEXT is cut to 700 first, so the sentence always fits a journal value
  REPLY=$1 UWORD=0
  [ "${2-}" = open ] || [ "$UDOWN" = 1 ] || return 0
  ( unit_read && [ "$UNIT_FILE" = enabled ] && [[ $UNIT_ACTIVE:$UNIT_PID =~ ^(inactive|failed|activating):0$ ]] ) || return 0
  REPLY="${1:0:700}. runscaler is down (its unit is enabled and runs no process): CI is down until the updater's RECOVER starts it"
  UWORD=1
}
uclose() {   # KEY TEXT: the window's last word (`stop NAME: TEXT` or `end TEXT`) and THE CLOSING LINES, the class from ONE
  # read of config.toml now (only before the rename: the pre-window file, or a hand change of it): pre (`config-sha`),
  # other (another file: with its STOP HAND CHANGE when the last word is another), none (no `config-sha` yet, or it
  # cannot be read). STAGED (this window's) is removed first. A rollback that found the enabled unit down (UDOWN) writes
  # its last word only, and that word says CI is down while the unit is still down (udown_word): the journal stays OPEN,
  # so the updater's RECOVER starts runscaler (CI is never left down with no line: NO SILENT END)
  local t c
  rm -f -- "$STAGED"
  clean "$2"; udown_word "$REPLY"; t=$REPLY; ujs "$1" "$t"
  if [ "$UDOWN" = 1 ]; then UOPEN=1 REPLY=$t; return 0; fi
  cfg_now
  if [ -z "$CSHA" ] || [ "$NOW_SHA" = none ]; then c=none; elif [ "$NOW_SHA" = "$CSHA" ]; then c=pre; else c=other; fi
  if [ "$c" = other ] && [ "$1:${t%%:*}" != "stop:HAND CHANGE" ]; then
    ujs stop "HAND CHANGE: config.toml changed during the window (sha256 ${NOW_SHA:0:12}…, not its config-sha ${CSHA:0:12}…): a file the window did not write. Check it"
  fi
  uclosing "$NOW_SHA" "$NOW_CONTENT" "$c"
  REPLY=$t
}
unothing() {   # what a window that closed before its rename changed: nothing, or (up, after THE BACKUP) config.toml.prev
  if [ "$UOPEN" = 1 ] && [ "$UWORD" = 1 ]; then
    echo "runscaler's unit is enabled (CI on) and runscaler is down: the window journal $J stays OPEN, and the updater's RECOVER starts runscaler on the config from before this window (validated first). config.toml is as it was"
  elif [ "$UOPEN" = 1 ]; then
    echo "runscaler was down when this rollback began, and its unit no longer reads down: the window journal $J stays OPEN, and the updater's RECOVER ends it. config.toml is as it was"
  elif [ "$BACKED" = 1 ] && [ "$KIND" = switch ]; then
    echo "config.toml is as it was and nothing restarted, but $KEEPP now holds this window's backup of it (the keep of an earlier switch is replaced) (the journal: $J, closed: the updater's next pass applies it)"
  else echo "Nothing changed: config.toml as it was, nothing restarted (the journal: $J, closed: the updater's next pass applies it)"; fi
}
ustop() { uclose stop "$1: $2"; echo "STOP $REPLY"; unothing; exit 1; }
uend() { uclose end "$1"; echo "END $REPLY"; unothing; exit 1; }
vtry() {   # 9|- OUT CMD...: ONE validate try (the header): CMD under `timeout -k 10 120` in timeout's own process group,
  # its stdout and stderr into OUT, stdin /dev/null, fd 8 (this script's lock) closed and fd 9 (the updater lock)
  # closed too unless the first word is 9 (03's render: it makes THE UPDATER'S CHILD check, then closes fd 9 itself).
  # Once the try ends, every process left in its group is killed. Its exit code; 124 or 137: the bound cut it (vcut)
  local keep=$1 out=$2 p rc
  shift 2
  if [ "$keep" = 9 ]; then timeout -k 10 120 "$@" > "$out" 2>&1 < /dev/null 8>&- &
  else timeout -k 10 120 "$@" > "$out" 2>&1 < /dev/null 8>&- 9>&- & fi
  p=$!
  wait "$p"; rc=$?
  kill -KILL -- "-$p" 2> /dev/null
  return "$rc"
}
vcut() { [ "$1" = 124 ] || [ "$1" = 137 ]; }
unot() {   # TEXT: not now: nothing staged, nothing changed, and no journal is kept
  rm -f -- "$STAGED"; rm -f -- "$J"; rm -rf -- "${WDIR:?}"
  echo "POOL IMAGE NOT NOW ($MODE --unattended): $1"; exit 3
}
uhand() {   # SHA WHAT: A HAND CHANGE found after `rename-start` (the header): `hand-change`, the STOP, the journal OPEN
  # (the STOP says CI is down when the unit is enabled and down right then, before the rename or after it: udown_word)
  ujs hand-change "$1"
  clean "$CFG changed by hand $2. This window restarts nothing on that file: check it; to keep it, run RUNNER_START_CONFIG=$CFG ~/bin/runner-start validate, and only when that passes, systemctl --user restart runscaler at idle. The window journal $J stays open: the updater's next pass ends it"
  udown_word "$REPLY" open
  ujs stop "HAND CHANGE: $REPLY"; echo "STOP HAND CHANGE: $REPLY"; exit 1
}
utarget() {   # WHEN NOTE: config.toml must still be the TARGET (TSHA), right before the step after WHEN; else uhand
  sha_of "$CFG"; [ "$REPLY" = "$TSHA" ] || uhand "$REPLY" "$1 (sha256 ${REPLY:0:12}…, not the ${TSHA:0:12}… this window validated and installed): $2"
}
sets_of() { grep -E '^name = ' "$1" 2> /dev/null | cut -d'"' -f2; }   # the sets a config names, in its order
targets() {   # FILE: "SET=IMAGE SET=IMAGE": each set's runner-image line, in config order
  awk '/^name = "/ { n = $0; sub(/^name = "/, "", n); sub(/"$/, "", n) }
       /^runner-image = "/ { i = $0; sub(/^runner-image = "/, "", i); sub(/"$/, "", i); printf "%s%s=%s", s, n, i; s = " " }' "$1"
}
disk_ok() {   # RUN_USER's filesystem (D1's data and the registry's volume) has DISK_PCT % or more free; DISK_WHY when not
  local l
  l=$(df -Pk "/home/${RUN_USER}" 2> /dev/null < /dev/null | tail -n 1)
  [[ $l =~ ^[^\ ]+\ +([0-9]+)\ +[0-9]+\ +([0-9]+)\  ]] || { DISK_WHY="df -Pk /home/${RUN_USER} printed no size: [$l]"; return 1; }
  (( BASH_REMATCH[2] * 100 >= BASH_REMATCH[1] * DISK_PCT )) && return 0
  DISK_WHY="the filesystem of /home/${RUN_USER} (D1's images and the registry) has ${BASH_REMATCH[2]} KiB free of ${BASH_REMATCH[1]}, less than ${DISK_PCT}% (runscaler's min_free): free disk first (the registry grows with each release), then the updater switches at its next pass"
  return 1
}
uidle() {   # THE IDLE PAIR (the header): 0 idle; 1 not idle; 2 the core could not decide. IDLE_WHY = the core's reason
  local h=$WDIR/idle-healthz.json f=$WDIR/idle-facts.json s=$WDIR/idle-state.json o=$WDIR/idle.json
  : > "$h" && : > "$s" || { IDLE_WHY="cannot write $WDIR"; return 2; }
  # shellcheck disable=SC2046
  jq -n -c '{format: 1, sets: $ARGS.positional}' --args $(sets_of "$CFG") > "$f" 2> /dev/null < /dev/null \
    || { IDLE_WHY="cannot write $f"; return 2; }
  healthz_pair "$h"   # 3 s apart, the pause between them: the last read is followed by the rename and the restart, at once
  jq -n -L "$CORE/lib" -f "$CORE/idle.jq" --slurpfile state "$s" --slurpfile facts "$f" --slurpfile healthz "$h" \
    --arg now "$(date +%s)" > "$o" 2> "$o.err" < /dev/null || { IDLE_WHY=$(head -n 1 "$o.err"); return 2; }
  IDLE_WHY=$(jq -r '.reason' "$o" 2> /dev/null) || { IDLE_WHY="no reason in $o"; return 2; }
  case $(jq -r '.verdict' "$o" 2> /dev/null) in idle) return 0 ;; not-idle) return 1 ;; *) return 2 ;; esac
}
ubackup() {   # DEST: THE BACKUP (the header), after its `backup DEST` line: config.toml copied to DEST.tmp (0600), the
  # COPY checked against `config-sha` (a copy is checked after it is made), then renamed to DEST. Else nothing renamed
  # and DEST as it was: the journal closes (config.toml is no file of this window's)
  { cp -- "$CFG" "$1.tmp" && chmod 600 "$1.tmp"; } || { rm -f -- "$1.tmp"; ustop "$UFAIL" "could not copy $CFG to $1.tmp (the backup): nothing was renamed"; }
  sha_of "$1.tmp"
  [ "$REPLY" = "$CSHA" ] || { rm -f -- "$1.tmp"; ustop "HAND CHANGE" "config.toml changed during the window (sha256 ${REPLY:0:12}…, the window's ${CSHA:0:12}…): nothing was renamed or restarted. Check it; a hand change belongs outside the updater's windows"; }
  mv -f -- "$1.tmp" "$1" || { rm -f -- "$1.tmp"; ustop "$UFAIL" "could not rename $1.tmp to $1 (the backup): nothing was renamed"; }
  BACKED=1
}
urename() {   # THE RENAME (the header): `rename-start`, the install time, the two checks, the rename at once, `renamed`
  ujs rename-start "$(date +%s)"
  # the INSTALL TIME, now (the clock's second is rename-start's or later): started_after reads config.toml's mtime, and
  # STAGED's own (03's render, back's copy) is earlier, so a start in between would read as after the install (review
  # Opus r1 F1). -c: never make a file
  touch -c -m -- "$STAGED" || ufail "could not set the time of $STAGED (touch): nothing was renamed, and the window journal $J stays open"
  sha_of "$CFG"
  if [ "$REPLY" != "$CSHA" ]; then
    rm -f -- "$STAGED"
    uhand "$REPLY" "after rename-start, before the rename (sha256 ${REPLY:0:12}…, the window's ${CSHA:0:12}…): nothing was renamed, and runscaler is as it was"
  fi
  sha_of "$STAGED"
  if [ "$REPLY" != "$TSHA" ]; then   # config.toml is the window's own pre-window file (just checked): the journal closes
    if [ "$MODE" = up ]; then ustop "check failed" "$STAGED is not the file 03 validated (sha256 ${REPLY:0:12}…, 03 printed ${TSHA:0:12}…): nothing was renamed"; fi
    ustop "ROLLBACK FAILED" "$STAGED changed after its validate (sha256 ${REPLY:0:12}…, the validated ${TSHA:0:12}…): nothing was renamed"
  fi
  mv -f -- "$STAGED" "$CFG" || ufail "could not rename $STAGED over $CFG (it is as it was): the window journal $J stays open"
  RENAMED=$(date +%s); ujs renamed "$RENAMED"
}
tclass() {   # AFTER: CLASS of an installed TARGET (the header's closing classes): target-running (runscaler RUNS since
  # AFTER, the install; RUN its "PID START"), target-old (a runscaler that started at or before AFTER runs: it read the
  # file before), target-idle (none runs it)
  local p
  RUN=
  if runs "$1" "$WDIR/runs-healthz.json" $TSETS; then CLASS=target-running RUN=$RUNS_PROC; return 0; fi
  p=$(proc_now)
  if [ "$p" != none ] && [ "${p#* }" -le "$1" ]; then CLASS=target-old; else CLASS=target-idle; fi
}
ucidisabled() {   # TEXT: a person disabled the unit during the window (D-h), after THE INSTALL: no start; the journal
  # closes as RECOVER's step 2 closes it: `stop CI DISABLED`, then the closing lines (the TARGET, just checked, and
  # whether a runscaler runs it)
  clean "$1"; ujs stop "CI DISABLED: $REPLY"; echo "STOP CI DISABLED: $REPLY"
  tclass "$RENAMED"
  uclosing "$TSHA" "$TCONT" "$CLASS"
  echo "config.toml is the TARGET; runscaler stays as a person left it (the journal: $J, closed: the updater's next pass applies it)"
  exit 1
}
urestart() {   # THE RESTART (the header): returns when the new process RUNS; else exit 1, the journal open
  local o p e
  while [ "$(date +%s)" -le "$RENAMED" ]; do sleep 0.2; done   # past the install's second: the start proves it
  ujs from "$(proc_now)"
  ujs stopping "$(date +%s)"
  utarget "after the rename, before the stop" "nothing was stopped, and runscaler is as it was"
  systemctl --user stop runscaler < /dev/null 8>&- 9>&- || ufail "systemctl --user stop runscaler failed (journalctl --user -u runscaler): the window journal $J stays open"
  p=none
  if [ "$(proc_now)" = none ] && o=$(log_pos) && [[ $o =~ ^[0-9]+\ [0-9]+\ [0-9a-f]{64}$ ]] && [ "$(proc_now)" = none ]; then p=$o; fi
  ujs stopped "$p"
  # the unit must still be ENABLED (D-h; changed-lines Opus r2 F4): a person's `systemctl --user disable --now
  # runscaler` during the window gets no start
  if [ "$(exec 8>&- 9>&-; systemctl --user is-enabled runscaler 2> /dev/null < /dev/null)" != enabled ]; then
    utarget "after the drain, the unit not enabled" "nothing was started"
    ucidisabled "a person disabled runscaler during this window (systemctl --user is-enabled: not enabled), after its install: config.toml is the TARGET ($(image_of "$CFG")), validated, and runs when a person starts runscaler again: systemctl --user enable --now runscaler. Nothing was started"
  fi
  e=$(date +%s); ujs starting "$e"
  utarget "while runscaler drained, before its start" "runscaler stays stopped"
  systemctl --user start runscaler < /dev/null 8>&- 9>&- || ufail "systemctl --user start runscaler failed (journalctl --user -u runscaler): the window journal $J stays open"
  while [ "$(date +%s)" -lt $((e + 600)) ]; do   # up to 10 min of the clock: until it RUNS (the header)
    if runs "$RENAMED" "$WDIR/runs-healthz.json" $TSETS; then
      # the file it read must still be the TARGET: a change around the start leaves no way to name what it runs
      utarget "around runscaler's start" "the runscaler that started meanwhile may run either file"
      RUNNING=$RUNS_PROC; ujs running "$RUNNING"; return 0
    fi
    sleep 5
  done
  clean "no runscaler RUNS on the TARGET within 10 min of its start ($RUNS_WHY)"
  ujs pre-close-failure "$REPLY"
  ufail "$REPLY (journalctl --user -u runscaler): the window journal $J stays open, and the updater's RECOVER starts it once more"
}
udone() {   # the target RUNS: THE CLOSING LINES (CLASS: the window's last check of config.toml, right before `running`,
  # never a new read: Opus r3 F14); the journal stays at WINDOW for the updater's apply step
  uclosing "$DONE_SHA" "$DONE_CONTENT" "$DONE_CLASS"
  echo "POOL IMAGE DONE ($MODE --unattended): $(image_of "$CFG") (runscaler $RUNNING runs it, started after the install; the journal: $J, closed: the updater's next pass applies it)"
  exit 0
}
j_closed() {   # the journal at WINDOW is closed: its last line, a whole one, is `closed E`
  local t
  t=$(tail -c 64 -- "$J" 2> /dev/null; echo .); t=${t%.}
  [[ $t =~ (^|$'\n')closed\ [0-9]+$'\n'$ ]]
}
unattended() {   # the window: its journal, then up or back (each ends with exit); RECOVER is its own (un_recover)
  export LC_ALL=C
  [ "$MODE" != recover ] || un_recover
  if [ -e "$J" ] || [ -L "$J" ]; then
    ! j_closed || die "the window journal $J is closed, not applied: the updater's next pass applies it; nothing changed"
    die "an open window journal $J: an earlier window did not close (it was cut off), and the updater's next pass (RECOVER) ends it; nothing changed"
  fi
  install -d -m 700 "$WINDOWS" || die "cannot make $WINDOWS: nothing changed"
  WID=$(date -u +%Y%m%d%H%M%S)-$$; WDIR=$WINDOWS/$WID.d
  mkdir -m 700 "$WDIR" || die "cannot make $WDIR: nothing changed"
  # STAGED, and the STOP of a failure that is no hand change: up's `check failed`, back's `ROLLBACK FAILED`
  if [ "$MODE" = up ]; then STAGED=$R/config.staged.toml UFAIL="check failed" KIND=switch
  else STAGED=$R/config.rollback.toml UFAIL="ROLLBACK FAILED" KIND=rollback; fi
  CSHA= TSHA= TCONT= TSETS=
  ujs window "$WID"
  if [ "$MODE" = up ]; then ujs kind switch; ujs version "$VERSION"; ujs digest "$DIGEST"; un_up; else ujs kind rollback; un_back; fi
}
utargetlines() {   # the TARGET's `target` and `target-content` lines, of the validated STAGED (TSHA): TSETS, TCONT
  ujs target "$(targets "$STAGED")"
  TSETS=$(sets_of "$STAGED" | paste -sd ' ' -)
  content_of "$STAGED"; TCONT=$REPLY
  [ "$TCONT" != unreadable ] || ustop "$UFAIL" "could not read $STAGED's content (the TARGET's): nothing was renamed"
  ujs target-content "$TCONT"
}
un_up() {
  local cur new n rc cls out f p m
  ujs process "$(proc_now)"
  cur=$(image_of "$CFG") || ustop "check failed" "config.toml does not name ONE runner image for both sets ($SETS): read $CFG"
  ujs old "$cur"
  sha_of "$CFG"; CSHA=$REPLY; ujs config-sha "$CSHA"
  new=localhost:${REGISTRY_PORT}/${IMAGE_NAME}@$DIGEST
  if [ "$cur" = "$new" ]; then   # nothing to switch, and its rollback ($KEEPP) stays as it is: done only if it RUNS,
    # checked ONCE, here, after the journal lines and right before `running` (D-h): config.toml still `config-sha` and
    # naming DIGEST's image in one read, and runscaler RUNS since its install (config.toml's mtime)
    cfg_now; m=$(stat -c %Y "$CFG" 2> /dev/null)
    if [ "$NOW_SHA" != "$CSHA" ] || [ "$(image_of "$NOW_COPY")" != "$new" ]; then
      RUNS_WHY="config.toml changed after its config-sha line (sha256 ${NOW_SHA:0:12}…)"
    elif [[ $m =~ ^[0-9]+$ ]] && runs "$m" "$WDIR/runs-healthz.json" $(sets_of "$NOW_COPY"); then
      RUNNING=$RUNS_PROC; ujs running "$RUNNING"; DONE_SHA=$NOW_SHA DONE_CONTENT=$NOW_CONTENT DONE_CLASS=pre; udone
    fi
    uend "config.toml already names $new, but it is not proven to run it ($RUNS_WHY): there is nothing to switch, its rollback ($KEEPP) stays as it is, and this mode restarts nothing"
  fi
  pulls "$cur"; case $? in
    0) ;;
    1) ustop "check failed" "the registry does not serve $cur, the image the pool runs now: its rollback could not start a runner" ;;
    *) ustop "check failed" "the registry ($REG) does not answer, so it cannot be checked that it still serves $cur, the image the pool runs now (the rollback's)" ;;
  esac
  { [ "$(exec 8>&- 9>&-; systemctl --user is-active runscaler 2> /dev/null)" = active ] && [ "$(exec 8>&- 9>&-; systemctl --user is-enabled runscaler 2> /dev/null)" = enabled ]; } \
    || unot "START STATE: runscaler is not active and enabled"
  started_after || unot "START STATE: config.toml was installed after runscaler started, so it is not proven to be the config that runs"
  ujs start-state "$(date +%s)"   # config-sha runs: RECOVER may start it with no validate (the header)
  disk_ok || ustop DISK "$DISK_WHY"
  if ! tested_jq; then
    [ "$JQV" != "no jq" ] || ustop "untested jq" "no jq answers \`jq --version\` here: install one that $CORE/TESTED_JQ lists for core (Ubuntu 26.04's and 24.04's packages are), and the updater switches at its next pass"
    ustop "untested jq" "jq here prints [$JQV], which is no core row of $CORE/TESTED_JQ: the decision core is not tested with it. Run tests/core with it (JQ=$(command -v jq) python3 -I -B -m unittest discover -s tests/core -t .), and release its row"
  fi
  p=$(pins_bad) && ustop "check failed" "$p is not the reviewed copy (sha256 of PINS): this ~/build is not one release's"
  ujs staged "$STAGED"
  for n in 1 2 3; do
    out=$WDIR/validate-pre-$n.out
    # 03 keeps fd 9 for THE UPDATER'S CHILD check of its render inside a window, and closes it at once (03's header)
    vtry 9 "$out" bash "$S03" render "$DIGEST" "$STAGED"; rc=$?
    if vcut "$rc"; then cls=UNKNOWN; else cls=$(sed -n 's/^VALIDATE \([A-Z-]*\)$/\1/p' "$out" | tail -n 1); fi
    [ -z "$cls" ] || ujs validate "pre $n $cls"
    case $rc:$cls in
      0:PASS) break ;;
      4:API-ONLY) [ "$n" = 3 ] && break; sleep 20 ;;
      *) f=$(grep '^FAIL ' "$out" | tail -n 1)
         ! vcut "$rc" || f="the try was cut at its bound (timeout -k 10 120 exited $rc)"
         ustop "check failed" "03-runscaler.sh render, try $n: VALIDATE ${cls:-none} (exit $rc): ${f#FAIL } (its whole output: $out)" ;;
    esac
  done
  TSHA=$(sed -n 's/^03 STAGED (render): .* sha256 \([0-9a-f]\{64\}\)\. Nothing was installed\.$/\1/p' "$out" | tail -n 1)
  [[ $TSHA =~ ^[0-9a-f]{64}$ ]] || ustop "check failed" "03-runscaler.sh render printed no sha256 of $STAGED ($out)"
  ujs staged-sha "$TSHA"
  { [ "$(image_of "$STAGED")" = "$new" ] && rr_same_but_image "$CFG" "$STAGED"; } \
    || ustop "check failed" "03's render differs from config.toml in more than the runner-image lines (pool.env's numbers are not the ones config.toml runs?): an unattended switch changes the runner version only (plan D3). Compare $POOL with $CFG"
  utargetlines
  uidle; case $? in
    0) ;;
    1) unot "not idle: $IDLE_WHY" ;;
    *) uend "the decision core could not decide IDLE: $IDLE_WHY" ;;
  esac
  ujs idle idle
  # at once (the header, step 3): THE BACKUP, THE RENAME, THE RESTART
  ujs backup "$KEEPP"
  # STAGED first: a window that cannot rename leaves config.toml.prev (the rollback it keeps) as it was
  sha_of "$STAGED"; [ "$REPLY" = "$TSHA" ] || ustop "check failed" "$STAGED is not the file 03 validated (sha256 ${REPLY:0:12}…, 03 printed ${TSHA:0:12}…): nothing was renamed, and $KEEPP is as it was"
  ubackup "$KEEPP"
  urename
  urestart
  DONE_SHA=$TSHA DONE_CONTENT=$TCONT DONE_CLASS=target-running
  udone
}
un_back() {
  local cur tgt n rc cls out f v m
  # THE ROLLBACK'S OWN LINES (D-e), before any effect: why, its verdict (the file copied into the window's folder,
  # journaled by its sha), the version it leaves (--old-version) and the version it restores (the ONE build record of
  # config.toml.prev's digest, read as RUN_USER's hostile file by runner-release.sh's reader)
  ujs why "$WHY"
  v=none
  if [ -n "$VERDICT" ] && cp -- "$VERDICT" "$WDIR/verdict.json" 2> /dev/null < /dev/null && chmod 600 -- "$WDIR/verdict.json"
  then sha_of "$WDIR/verdict.json"; [ "$REPLY" = unreadable ] || v=$REPLY; fi
  ujs verdict "$v"
  ujs old-version "${OLDV:-none}"
  v=none
  if tgt=$(image_of "$KEEPP") && rr_record_of "$BUILDS" "${tgt#*@}"; then v=$RR_REC_VERSION; fi
  ujs target-version "$v"
  ujs process "$(proc_now)"
  { [ -f "$KEEPP" ] && [ ! -L "$KEEPP" ]; } || ustop "ROLLBACK FAILED" "there is no rollback config $KEEPP (the backup of the switch to undo): nothing to go back to. Read $CFG and the closed window journals in $WINDOWS"
  tgt=$(image_of "$KEEPP") || ustop "ROLLBACK FAILED" "$KEEPP does not name ONE runner image for both sets: read it"
  # `old` is what it is in up: the image config.toml names at the window's start (the target's is in `target`)
  cur=$(image_of "$CFG") || ustop "ROLLBACK FAILED" "config.toml does not name ONE runner image for both sets ($SETS), so it is no config an updater's switch installed: read $CFG"
  ujs old "$cur"
  sha_of "$CFG"; CSHA=$REPLY; ujs config-sha "$CSHA"
  # THE UNIT (operator (1), 11-05): ENABLED means CI on. Not enabled: a person's, no restart. Enabled and down (inactive
  # or failed, no process): the rollback goes on with no started_after test (nothing runs) and its restart starts it.
  # Enabled and active: the started_after test, then the shortcut
  unit_read || uend "rollback pending: runscaler's unit cannot be read (systemctl --user show runscaler): nothing restarts"
  [ "$UNIT_FILE" = enabled ] || uend "rollback pending: CI disabled by a person (runscaler is $UNIT_FILE): nothing restarts"
  case $UNIT_ACTIVE:$UNIT_PID in
    active:*)
      started_after || ustop "HAND CHANGE" "config.toml was installed after runscaler started (a hand 03 run, or a window cut before its restart): a pending change, which the rollback would replace unseen. Check $CFG; restart runscaler at idle once it is the config you want"
      ujs start-state "$(date +%s)"   # config-sha runs (START STATE's twin): RECOVER may start it with no validate
      # THE SHORTCUT, checked ONCE, here, after the journal lines and right before `running` (D-h): config.toml is
      # still `config-sha` and already the rollback, in one read, and runscaler RUNS since its install
      cfg_now; m=$(stat -c %Y "$CFG" 2> /dev/null)
      sha_of "$KEEPP"
      if [ "$NOW_SHA" = "$CSHA" ] && [ "$NOW_SHA" = "$REPLY" ]; then
        if [[ $m =~ ^[0-9]+$ ]] && runs "$m" "$WDIR/runs-healthz.json" $(sets_of "$NOW_COPY"); then
          RUNNING=$RUNS_PROC; ujs running "$RUNNING"; DONE_SHA=$NOW_SHA DONE_CONTENT=$NOW_CONTENT DONE_CLASS=pre; udone
        fi
        uend "config.toml already is the rollback $KEEPP, but it is not proven to run it ($RUNS_WHY): nothing restarts"
      fi ;;
    inactive:0|failed:0|activating:0) UDOWN=1 ;;   # no process (activating with no pid: the auto-restart wait)
    *) uend "rollback pending: runscaler is $UNIT_ACTIVE (pid $UNIT_PID): a start or a drain is in progress, nothing restarts now" ;;
  esac
  pulls "$tgt"; case $? in
    0) ;;
    1) ustop "ROLLBACK FAILED" "the registry no longer serves the rollback's image $tgt: a runner of it could not start" ;;
    *) ustop "ROLLBACK FAILED" "the registry ($REG) does not answer, so no runner of either image can start: bring D1's registry back first (02-d1.sh as ${RUN_USER})" ;;
  esac
  ujs staged "$STAGED"
  { cp -- "$KEEPP" "$STAGED.tmp" && chmod 600 "$STAGED.tmp" && mv -f -- "$STAGED.tmp" "$STAGED"; } \
    || { rm -f -- "$STAGED.tmp"; ustop "ROLLBACK FAILED" "could not copy $KEEPP to $STAGED"; }
  sha_of "$STAGED"; TSHA=$REPLY
  sha_of "$KEEPP"; [ "$REPLY" = "$TSHA" ] || ustop "ROLLBACK FAILED" "the copy $STAGED is not $KEEPP"
  # the COPY is what is validated and installed, so the rollback's lines are checked on it (a copy is checked after it
  # is made): ONE image, the one the registry was asked for, and config.toml's other lines
  [ "$(image_of "$STAGED")" = "$tgt" ] || ustop "ROLLBACK FAILED" "$KEEPP changed during the rollback window: its copy $STAGED does not name ${tgt}, the image the registry was asked for, for both sets. Read it"
  rr_same_but_image "$STAGED" "$CFG" || ustop "ROLLBACK FAILED" "config.toml differs from the rollback $KEEPP in more than the runner-image lines (sets or numbers changed since the switch): the rollback would undo that too. Compare the two"
  for n in 1 2 3; do
    out=$WDIR/validate-pre-$n.out
    vtry - "$out" env RUNNER_START_CONFIG="$STAGED" "$HOME/bin/runner-start" validate; rc=$?
    if vcut "$rc"; then cls=UNKNOWN
    else cls=$("$HOME/bin/validate-class" "$rc" "$out" 2> /dev/null) || cls=UNKNOWN; fi
    ujs validate "pre $n $cls"
    case $cls in
      PASS) break ;;
      API-ONLY) [ "$n" = 3 ] && break; sleep 20 ;;
      NON-API) f=$(grep -m 1 -E '^(runner-start: REFUSE |  ✗ )' "$out")
               ustop "ROLLBACK FAILED" "the rollback config fails validate (try $n, NON-API): $f (its whole output: $out)" ;;
      *) uend "the validate of the rollback config is UNKNOWN (try $n; its whole output: $out): no STOP, the updater tries again" ;;
    esac
  done
  ujs staged-sha "$TSHA"
  utargetlines
  # THE BACKUP of the config this window replaces (the pre-window config: plan D1, RECOVER step 4), then at once THE
  # RENAME (its checks: config.toml and STAGED as validated) and THE RESTART
  ujs backup "$WDIR/config.toml.backup"
  ubackup "$WDIR/config.toml.backup"
  urename
  urestart
  DONE_SHA=$TSHA DONE_CONTENT=$TCONT DONE_CLASS=target-running
  udone
}

# ---- RECOVER (`recover --unattended`, the header: S2b-3c-1 D-c, D-d, the r3 FOLD and B1 fix round 1)
rcsay() { echo "POOL IMAGE RECOVER: $*"; }
rc_cannot() {   # TEXT: a record RECOVER cannot read or act on: STOP, nothing written, exit 6 (the header)
  echo "STOP RECOVER cannot end the window journal $J: $1. Nothing was changed or written: follow linux-docker/README.md, \"An unfinished window the updater cannot end\""
  exit 6
}
rc_open() {   # TEXT: the journal stays OPEN, and the line says why (exit 5)
  rm -f -- "$R/config.recover.toml" "$R/config.recover.toml.tmp"
  rcsay "the window journal $J stays open: $1"
  exit 5
}
rc_pats() {   # the reader's patterns, ONE copy (rc_read reads by them; rc_target writes only what they read): RC_H a
  # sha256, RC_I an image reference (IMGRE's), RC_TL a `target` line's value
  RC_H='[0-9a-f]{64}'
  RC_I=${IMGRE#^}; RC_I=${RC_I%\$}
  RC_TL="[A-Za-z0-9][A-Za-z0-9._-]{0,99}=$RC_I( [A-Za-z0-9][A-Za-z0-9._-]{0,99}=$RC_I)*"
}
rc_read() {   # the journal ONCE, by the header's patterns -> RCK (keys), RCV (values), RC_KEEP (the bytes of its whole
  # lines: an unterminated last line is D1's lost line, dropped); a line no pattern reads: rc_cannot
  local text l k v n=0 H=$RC_H E='[0-9]{1,12}' V='[0-9]+\.[0-9]+\.[0-9]+' I=$RC_I TL=$RC_TL wid=
  { [ -f "$J" ] && [ ! -L "$J" ] && [ -r "$J" ]; } || rc_cannot "it is not a readable plain file"
  text=$(cat -- "$J" && echo .) || rc_cannot "it cannot be read"
  text=${text%.}
  RC_CUT=
  if [ -n "$text" ] && [[ $text != *$'\n' ]]; then   # the cut line: dropped (kept aside by rc_trim before a write)
    if [[ $text == *$'\n'* ]]; then RC_CUT=${text##*$'\n'}; text=${text%$'\n'*}$'\n'; else RC_CUT=$text; text=; fi
  fi
  RC_KEEP=${#text}
  RCK=() RCV=()
  while IFS= read -r l; do
    n=$((n + 1))
    [[ $l =~ ^([a-z][a-z-]{0,30})\ (.*)$ ]] || rc_cannot "line $n is not 'KEY VALUE'"
    k=${BASH_REMATCH[1]} v=${BASH_REMATCH[2]}
    case $k in
      window) [[ $v =~ ^[0-9]{14}-[0-9]+$ ]] && [ "$n" = 1 ] && wid=$v ;;
      kind) [[ $v =~ ^(switch|rollback)$ ]] ;;
      version) [[ $v =~ ^$V$ ]] ;;
      digest) [[ $v =~ ^sha256:$H$ ]] ;;
      why) [[ $v =~ ^(r1|r1-connect|back)$ ]] ;;
      verdict|prev) [[ $v =~ ^($H|none)$ ]] ;;
      old-version|target-version) [[ $v =~ ^($V|none)$ ]] ;;
      process|from) [[ $v =~ ^([0-9]+\ [0-9]+|none)$ ]] ;;
      old) [[ $v =~ ^$I$ ]] ;;
      config-sha|staged-sha|target-content) [[ $v =~ ^$H$ ]] ;;
      staged) [ "$v" = "$R/config.staged.toml" ] || [ "$v" = "$R/config.rollback.toml" ] ;;
      validate) [[ $v =~ ^(pre|recover|hand)\ [1-3]\ (PASS|API-ONLY|NON-API|UNKNOWN)$ ]] ;;
      target) [[ $v =~ ^$TL$ ]] ;;
      idle) [ "$v" = idle ] ;;
      backup) [ "$v" = "$KEEPP" ] || [ "$v" = "$WINDOWS/$wid.d/config.toml.backup" ] ;;
      restore) [ "$v" = "$WINDOWS/$wid.d/config.toml.backup" ] ;;
      start-state|rename-start|renamed|stopping|recover-start|closed) [[ $v =~ ^$E$ ]] ;;
      starting) [[ $v =~ ^$E(\ (target|pre|other))?$ ]] ;;
      hand-change) [[ $v =~ ^($H|unreadable|none)$ ]] ;;
      stopped) [[ $v =~ ^([0-9]+\ [0-9]+\ $H|none)$ ]] ;;
      running) [[ $v =~ ^[0-9]+\ [0-9]+$ ]] ;;
      pre-close-failure|end) [ -n "$v" ] ;;
      stop) [[ $v =~ ^(check\ failed|DISK|untested\ jq|HAND\ CHANGE|ROLLBACK\ FAILED|POOL\ DOWN|CI\ DISABLED|NO\ IDLE):\ . ]] ;;
      recover-target) [[ $v =~ ^$H\ $TL$ ]] ;;
      installed) [[ $v =~ ^($H|none)\ ($H|none)\ (target-running|target-idle|target-old|target-failed|pre|other|none)$ ]] ;;
      *) false ;;
    esac || rc_cannot "line $n: a '$k' line RECOVER does not read (linux-docker/setup/pool-image.sh's header names each)"
    RCK+=("$k") RCV+=("$v")
  done <<< "${text%$'\n'}"
  [ -n "$wid" ] || rc_cannot "its first line is not \`window ID\`"
  WID=$wid
}
rc_facts() {   # what RECOVER decides by, from RCK/RCV (the header): the window's own lines are those before the first
  # `recover-start`. A `starting` is of the TARGET when it is the window's (no field: it comes only after `renamed`) or
  # RECOVER's `starting E target`; RECOVER's `starting E pre|other` is of the sha its last `recover-target` names
  # (OPEN_SHA); a `pre-close-failure` ends the open start before it, and is the TARGET's when that start is. A `stop
  # HAND CHANGE` right after a `hand-change H` is H's STOP (HSTOP). W_RS: the window's `rename-start` (THE EFFECT: a
  # journal with none installed nothing)
  local i k v w=1
  KIND= CSHA= TSHA= TLINES= TCONT= STAGEDP= BKP= W_RN= W_RS= RSTART= RT_SHA= PCF=0 OPEN_START= OPEN_WHAT= OPEN_SHA=
  LAST_HAND= HSTOP=
  RC_VFAIL=0 RC_NONAPI=0 RC_RESTORE=0 RC_RBF=0 RC_TPCF=0 RC_NOIDLE=0 RC_SSTATE=0 RC_RN= RC_LASTV= RC_LAST=
  RC_STOPS=$'\n'
  for i in "${!RCK[@]}"; do
    k=${RCK[$i]} v=${RCV[$i]}
    RC_LAST=$k
    case $k in
      kind) [ -n "$KIND" ] || KIND=$v ;;
      config-sha) [ -n "$CSHA" ] || CSHA=$v ;;
      start-state) [ "$w" = 0 ] || RC_SSTATE=1 ;;
      staged-sha) [ -n "$TSHA" ] || TSHA=$v ;;
      target) [ -n "$TLINES" ] || TLINES=$v ;;
      target-content) [ -n "$TCONT" ] || TCONT=$v ;;
      staged) STAGEDP=$v ;;
      backup) [ -n "$BKP" ] || BKP=$v ;;
      renamed) if [ "$w" = 1 ]; then W_RN=$v; else RC_RN=$v; fi ;;
      rename-start) [ "$w" = 0 ] || W_RS=$v ;;
      recover-start) [ -n "$RSTART" ] || RSTART=$v; w=0 ;;
      recover-target) RT_SHA=${v%% *} ;;
      starting) OPEN_START=${v%% *} OPEN_WHAT=target OPEN_SHA=
        if [[ $v == *' '* ]]; then OPEN_WHAT=${v#* }; [ "$OPEN_WHAT" = target ] || OPEN_SHA=$RT_SHA; fi ;;
      running) OPEN_START= OPEN_WHAT= OPEN_SHA= ;;
      pre-close-failure) PCF=$((PCF + 1))
        [ "$OPEN_WHAT" != target ] || [ "$RC_RESTORE" = 1 ] || RC_TPCF=1
        OPEN_START= OPEN_WHAT= OPEN_SHA= ;;
      hand-change) LAST_HAND=$v HSTOP= ;;
      validate) if [[ $v == recover\ * ]]; then
          RC_LASTV=$v
          [[ $v =~ ^recover\ [1-3]\ (NON-API|UNKNOWN)$ ]] && RC_VFAIL=1
          [[ $v =~ ^recover\ [1-3]\ NON-API$ ]] && RC_NONAPI=1
        fi ;;
      restore) RC_RESTORE=1 ;;
      stop) RC_STOPS+="$v"$'\n'
        case $v in "ROLLBACK FAILED: "*) RC_RBF=1 ;; "NO IDLE: "*) RC_NOIDLE=1 ;; "HAND CHANGE: "*) HSTOP=$LAST_HAND ;; esac ;;
    esac
  done
  TSETS=$(for v in $TLINES; do printf '%s ' "${v%%=*}"; done)
  # a window that made an effect journaled each line before it (the header): what that effect needs is there
  if [ -n "$BKP" ]; then
    { [ -n "$KIND" ] && [ -n "$CSHA" ] && [ -n "$TSHA" ] && [ -n "$TLINES" ] && [ -n "$STAGEDP" ]; } \
      || rc_cannot "it names a backup, but not its kind, config-sha, staged, staged-sha and target"
    { [ "$KIND" = switch ] && [ "$BKP" = "$KEEPP" ]; } || { [ "$KIND" = rollback ] && [ "$BKP" = "$WINDOWS/$WID.d/config.toml.backup" ]; } \
      || rc_cannot "its backup line is not its kind's backup"
  fi
}
rc_decided() {   # DECIDED LINES (the header): a ROLLBACK whose lines about its TARGET say it failed: a `validate
  # recover N NON-API|UNKNOWN`, a `restore`, a `stop ROLLBACK FAILED`, a TARGET start's `pre-close-failure`
  [ "$KIND" = rollback ] && { [ "$RC_VFAIL" = 1 ] || [ "$RC_RESTORE" = 1 ] || [ "$RC_RBF" = 1 ] || [ "$RC_TPCF" = 1 ]; }
}
rc_trim() {   # the cut last line (rc_read) is kept aside as WDIR/journal.cut and dropped from the journal, so RECOVER's
  # own lines start on a line of their own
  [ -n "$RC_CUT" ] || return 0
  printf '%s' "$RC_CUT" > "$WDIR/journal.cut" && truncate -s "$RC_KEEP" -- "$J" \
    && dd if=/dev/null of="$J" conv=notrunc,fsync 2> /dev/null < /dev/null \
    || rc_open "its cut last line could not be set aside ($WDIR/journal.cut)"
  RC_CUT=
}
rc_stopline() {   # NAME TEXT: a `stop NAME: TEXT` line, printed
  clean "$2"; ujs stop "$1: $REPLY"; echo "STOP $1: $REPLY"; RC_STOPS+="$1: $REPLY"$'\n'
}
rc_once() {   # NAME KEY [MORE]: `stop NAME: KEY MORE`, ONCE: not when the journal has a `stop NAME: KEY...` line
  # (keyed on the STOP line itself, never on a marker before it); printed either way
  clean "$1: $2"
  if [[ $RC_STOPS == *$'\n'"$REPLY"* ]]; then echo "STOP $1: $2${3-}"; else rc_stopline "$1" "$2${3-}"; fi
}
rc_handstop() {   # SHA TEXT: THE ONE RULE's two lines, each once: `hand-change SHA` (unless it is the last marker),
  # then its STOP HAND CHANGE unless that marker has its STOP (keyed on the STOP line: a cut between the two leaves
  # the next pass to write it)
  if [ "$LAST_HAND" != "$1" ]; then ujs hand-change "$1"; LAST_HAND=$1 HSTOP=; fi
  [ "$HSTOP" = "$1" ] || { rc_stopline "HAND CHANGE" "$2"; HSTOP=$1; }
}
rc_hand() {   # SHA TEXT: THE ONE RULE (PLAN D5): config.toml is no file RECOVER may act on: its lines (rc_handstop),
  # the journal OPEN (the next pass looks again). A STOP THAT LEAVES CI DOWN SAYS SO: its STOP says CI is down when the
  # unit is enabled and down right then (udown_word)
  udown_word "$2" open
  rc_handstop "$1" "$REPLY. To keep it: RUNNER_START_CONFIG=$CFG ~/bin/runner-start validate, and only when that passes, systemctl --user restart runscaler at idle; the updater's next pass sees it"
  rc_open "config.toml (sha256 ${1:0:12}…) is no file RECOVER may act on: $2"
}
rc_dangling() {   # a `hand-change` whose STOP a cut lost (the window's or an earlier RECOVER's): the STOP first, once
  [ -n "$LAST_HAND" ] && [ "$HSTOP" != "$LAST_HAND" ] || return 0
  rc_stopline "HAND CHANGE" "config.toml changed by hand (sha256 ${LAST_HAND:0:12}…: the journal's last \`hand-change\`, whose STOP a cut lost). Check it; to keep it, RUNNER_START_CONFIG=$CFG ~/bin/runner-start validate, and only when that passes, systemctl --user restart runscaler at idle"
  HSTOP=$LAST_HAND
}
rc_unit() {   # THE UNIT (step 2): one read; a drain (deactivating) is waited for until it ends (systemd kills at
  # TimeoutStopSec: 4260 s; RECOVER's bound is 4320 s of the clock)
  local t0
  unit_read || rc_open "runscaler's unit cannot be read (systemctl --user show runscaler)"
  [ "$UNIT_ACTIVE" = deactivating ] || return 0
  t0=$(date +%s)
  rcsay "runscaler is deactivating (a drain, pid $UNIT_PID): waiting for it to end"
  while [ "$UNIT_ACTIVE" = deactivating ] && [ "$(date +%s)" -lt $((t0 + 4320)) ]; do
    sleep 5
    unit_read || rc_open "runscaler's unit cannot be read (systemctl --user show runscaler)"
  done
  [ "$UNIT_ACTIVE" != deactivating ] || rc_open "runscaler still drains (pid $UNIT_PID) after 72 min"
}
rc_proven() {   # SHA: a line proves it (A START NEEDS A VALIDATED SHA): the last `recover-target`, `staged-sha` (with
  # no failed validate of the TARGET after it), or `config-sha` after the window's `start-state` (START STATE passed)
  [ "$1" = "$RT_SHA" ] && return 0
  [ "$1" = "$TSHA" ] && [[ ! $RC_LASTV =~ ^recover\ [1-3]\ (NON-API|UNKNOWN)$ ]] && return 0
  [ "$1" = "$CSHA" ] && [ "$RC_SSTATE" = 1 ]
}
rc_class() {   # config.toml now, ONE read (cfg_now: NOW_COPY, NOW_SHA, NOW_CONTENT; MTIME its mtime), then rc_cls
  cfg_now || true
  MTIME=$(stat -c %Y "$CFG" 2> /dev/null); [[ $MTIME =~ ^[0-9]+$ ]] || MTIME=0
  rc_cls
}
rc_cls() {   # CLS of that read (THE INSTALLED FILE): T (its CONTENT is the TARGET's; a journal with no target-content:
  # its sha is staged-sha; and the window's `rename-start` there: NO EFFECT, NO TARGET, a window that never reached its
  # rename installed nothing, so the TARGET's content there is a person's file), PRE (`config-sha` with no window
  # rename, or after THE RESTORE: its backup), OWNOTHER (the last recover-target's sha: RECOVER's own validated file,
  # never OTHER), OTHER (anything else), NONE (unreadable). VALID: a line proves its sha (rc_proven)
  VALID=0
  if [ "$NOW_SHA" = none ]; then CLS=NONE; return 0; fi
  ! rc_proven "$NOW_SHA" || VALID=1
  if [ -n "$TSHA" ] && [ -n "$W_RS" ] \
    && { { [ -n "$TCONT" ] && [ "$NOW_CONTENT" = "$TCONT" ]; } || { [ -z "$TCONT" ] && [ "$NOW_SHA" = "$TSHA" ]; }; }
  then CLS=T
  elif [ -n "$CSHA" ] && [ "$NOW_SHA" = "$CSHA" ] && { [ -z "$W_RN" ] || [ "$RC_RESTORE" = 1 ]; }; then CLS=PRE
  elif [ "$NOW_SHA" = "$RT_SHA" ]; then CLS=OWNOTHER
  else CLS=OTHER; fi
}
rc_after() {   # AFTER: THE INSTALL BOUNDARY a start must be past to prove config.toml: the journaled install second
  # (the window's `renamed` for its TARGET; THE RESTORE's `renamed` for its backup), never earlier than the file's
  # mtime now. RC_SETS: the sets RUNS asks /healthz for
  RC_SETS=$(sets_of "$NOW_COPY" | paste -sd ' ' -)
  [ -n "$RC_SETS" ] || RC_SETS=$SETS
  AFTER=0
  case $CLS in
    T) AFTER=${W_RN:-0}; RC_SETS=${TSETS:-$RC_SETS} ;;
    PRE) [ "$RC_RESTORE" = 0 ] || AFTER=${RC_RN:-0} ;;
  esac
  [ "$MTIME" -le "$AFTER" ] || AFTER=$MTIME
}
rc_runs_now() {   # runscaler RUNS since AFTER (the install boundary) on the sets of config.toml (RC_SETS): it proves it
  runs "$AFTER" "$WDIR/runs-healthz.json" $RC_SETS
}
rc_runs_any() {   # a runscaler RUNS, whenever it started (one that started before the file's mtime may run an older
  # file): "a runscaler runs: nothing restarts" (steps 1, 4, 5); never one active read
  runs 0 "$WDIR/runs-healthz.json" $RC_SETS
}
rc_word() {   # [ran]: RC_C, the CLASS of the read config.toml (rc_class's CLS, never one decided before it): T ->
  # target-failed in a DECIDED rollback, target-running when RUNS just held on it (ran), else tclass; PRE -> pre;
  # OTHER, OWNOTHER -> other, its STOP HAND CHANGE first (once per file); NONE, or a journal with no config-sha and no
  # TARGET to compare -> none
  case $CLS in
    T) if rc_decided; then RC_C=target-failed
       elif [ "${1-}" = ran ]; then RC_C=target-running
       else rc_after; tclass "$AFTER"; RC_C=$CLASS; fi ;;
    PRE) RC_C=pre ;;
    NONE) RC_C=none ;;
    *) if [ -z "$CSHA" ] && [ -z "$TSHA" ]; then RC_C=none
       else RC_C=other
         rc_handstop "$NOW_SHA" "config.toml (sha256 ${NOW_SHA:0:12}…) is a file the updater did not write: check it. To keep it, RUNNER_START_CONFIG=$CFG ~/bin/runner-start validate, then systemctl --user restart runscaler at idle"
       fi ;;
  esac
}
rc_finish() {   # RECOVER's close with RC_C (rc_word, of the read NOW_SHA / NOW_CONTENT): THE CLOSING LINES; its copies
  # and the window's STAGED removed; exit 0
  rm -f -- "$R/config.recover.toml" "$R/config.restore.toml"
  [ -z "$STAGEDP" ] || rm -f -- "$STAGEDP"
  uclosing "$NOW_SHA" "$NOW_CONTENT" "$RC_C"
  rcsay "the window journal $J is closed ($RC_C): the updater's apply step applies it"
  exit 0
}
rc_end() {   # [read] [ran]: RECOVER's close from ONE read of config.toml (rc_class, or `read`: the one just made): its
  # SHA, CONTENT and CLASS all of that read (ONE READ PER CLOSE)
  [ "${1-}" = read ] || rc_class
  rc_word "${2-}"
  rc_finish
}
rc_vcopy() {   # STEP (recover: the TARGET; hand: another file): THE ONE VALIDATE RULE on a COPY of config.toml
  # (R/config.recover.toml, checked against the file read: NOW_SHA): up to 3 tries 20 s apart, each `validate STEP N
  # CLASS` (whole output WDIR/validate-STEP-N.out), each under vtry's bound: VCLS = PASS (API-ONLY after the third
  # counts) | NON-API | UNKNOWN; VSHA, VLINES: the copy's; VOUT: the last try's whole output
  local step=$1 c=$R/config.recover.toml n out rc
  VCLS=UNKNOWN VSHA= VLINES= VOUT=
  { cp -- "$CFG" "$c.tmp" && chmod 600 -- "$c.tmp" && mv -f -- "$c.tmp" "$c"; } 2> /dev/null < /dev/null \
    || { rm -f -- "$c.tmp"; rc_open "could not copy $CFG to $c to validate it"; }
  sha_of "$c"; VSHA=$REPLY
  [ "$VSHA" = "$NOW_SHA" ] || { rm -f -- "$c"; rc_hand "$VSHA" "config.toml changed while RECOVER read it"; }
  VLINES=$(targets "$c")
  for n in 1 2 3; do
    out=$WDIR/validate-$step-$n.out; VOUT=$out
    vtry - "$out" env RUNNER_START_CONFIG="$c" "$HOME/bin/runner-start" validate; rc=$?
    if vcut "$rc"; then VCLS=UNKNOWN
    else VCLS=$("$HOME/bin/validate-class" "$rc" "$out" 2> /dev/null) || VCLS=UNKNOWN; fi
    ujs validate "$step $n $VCLS"
    [ "$step" != recover ] || RC_LASTV="recover $n $VCLS"
    case $VCLS in
      PASS) break ;;
      API-ONLY) if [ "$n" = 3 ]; then VCLS=PASS; break; fi; sleep 20 ;;
      *) break ;;
    esac
  done
  rm -f -- "$c"
  [ "$VCLS" != PASS ] || [[ $VLINES =~ ^[A-Za-z0-9] ]] || VCLS=UNKNOWN
}
rc_target() {   # SHA LINES: RECOVER's own TARGET (D1): `recover-target`, once per sha, only of a sha a line proves (its
  # callers) and only a value its own reader reads (strict digest images): else no start, STOP HAND CHANGE that says
  # why (once: its line), the journal open
  [ "$RT_SHA" = "$1" ] && return 0
  [[ "$1 $2" =~ ^$RC_H\ $RC_TL$ ]] || {
    rc_once "HAND CHANGE" "config.toml (sha256 ${1:0:12}…) names runner images that are no digest reference of the local registry (localhost:${REGISTRY_PORT}/${IMAGE_NAME}@sha256:…), " "so RECOVER cannot journal what it would start ($2): nothing is started, CI is down. By hand, put a config with digest images in place (the one from before this window is one) and check it: RUNNER_START_CONFIG=FILE ~/bin/runner-start validate; the updater's next pass sees it"
    rc_open "config.toml's runner images are no digest references: RECOVER starts nothing on it"
  }
  ujs recover-target "$1 $2"; RT_SHA=$1
}
rc_vproof() {   # WHAT (pre | other): THE START's sha (the read: NOW_SHA) proven: a line proves it (VALID), else a
  # copy validates first (`validate hand N`) and `recover-target` names it. NON-API or UNKNOWN: no start, the journal
  # open (the next pass validates it again): another file -> THE ONE RULE's lines (once per file: its caller's), then
  # STOP POOL DOWN; the pre-window file, or a journal with no config-sha -> STOP POOL DOWN (rc_vdown: CI is down, once)
  if [ "$VALID" = 1 ]; then rc_target "$NOW_SHA" "$(targets "$NOW_COPY")"; return 0; fi
  rc_vcopy hand
  if [ "$VCLS" != PASS ]; then
    if [ "$1" = other ]; then
      rc_handstop "$NOW_SHA" "config.toml (sha256 ${NOW_SHA:0:12}…) is no file of this window's and its copy's validate is $VCLS: nothing is started"
      rc_vdown "a file this window did not write"
    else rc_vdown "the config from before this window, which no journal line proves ran"; fi
    [ "$RC_VUP" = 0 ] || rc_open "config.toml's copy validates $VCLS and no line proves it ran: nothing is started; a runscaler runs again (pid ${RUNS_PROC% *}), so no STOP POOL DOWN, and the next pass sees it"
    rc_open "config.toml's copy validates $VCLS and no line proves it ran: nothing is started, CI is down (STOP POOL DOWN)"
  fi
  rc_target "$VSHA" "$VLINES"
}
rc_vdown() {   # WHAT: A STOP THAT LEAVES CI DOWN SAYS SO (review r3, opus F2): config.toml (NOW_SHA), WHAT, does not
  # validate and no runscaler runs (rc_vproof's callers): `stop POOL DOWN` that says CI is down and why (the validate's
  # class, its whole output), ONCE per file (keyed on the STOP line itself, by its sha). TRUE WHEN WRITTEN (review r4,
  # opus F1, codex F2): the RUNS read that routed here came before the validate, minutes before: it is read again right
  # before the line, and a runscaler that RUNS now (one that came back by itself) gets none (RC_VUP=1)
  RC_VUP=0
  if rc_runs_any; then RC_VUP=1; return 0; fi
  rc_once "POOL DOWN" "runscaler is down, and config.toml (sha256 ${NOW_SHA:0:12}…), $1, does not validate" " ($VCLS; its whole output: $VOUT): nothing is started, CI is down. Fix it by hand, or put a config that validates in place by hand and check it: RUNNER_START_CONFIG=FILE ~/bin/runner-start validate; the updater's next pass validates it again"
}
rc_unread() {   # config.toml cannot be read and no runscaler runs: `stop POOL DOWN` that says CI is down, once (its line),
  # the journal open (the next pass reads it again)
  rc_once "POOL DOWN" "config.toml cannot be read, and runscaler is down" ": nothing is started, CI is down. By hand, put a config that validates in place and check it: RUNNER_START_CONFIG=FILE ~/bin/runner-start validate; the updater's next pass sees it"
  rc_open "config.toml cannot be read, and runscaler is down: CI is down (STOP POOL DOWN)"
}
rc_stop_unit() {   # the unit stopped (`systemctl --user stop` also ends a drain in progress or an auto-restart wait),
  # until it is inactive or failed and MainPID 0; rc 1 when it is not
  systemctl --user stop runscaler < /dev/null 8>&- 9>&- || return 1
  unit_read && [[ $UNIT_ACTIVE =~ ^(inactive|failed)$ ]] && [ "$UNIT_PID" = 0 ]
}
rc_ran() {   # SHA: runscaler RUNS on SHA (RUNS_PROC): the last check of config.toml, right before `running`, is the ONE
  # read the close is of; then `running` and the close
  rc_class
  [ "$NOW_SHA" = "$1" ] || rc_hand "$NOW_SHA" "config.toml changed around RECOVER's start: the runscaler that started may run either file"
  ujs running "$RUNS_PROC"
  rc_end read ran
}
rc_wait() {   # SHA AFTER E: up to E + 600 s of the clock (THE START'S DEADLINE), until runscaler RUNS since AFTER
  while [ "$(date +%s)" -lt $(( $3 + 600 )) ]; do
    runs "$2" "$WDIR/runs-healthz.json" $RC_SETS && rc_ran "$1"
    sleep 5
  done
  return 1
}
rc_fail() {   # SHA: the start at OPEN_START did not run within 10 min: ONE pre-close failure per journal
  # (`pre-close-failure`: the TARGET's when that start was); the second: STOP POOL DOWN, the close (exit 0)
  [ "$OPEN_WHAT" != target ] || RC_TPCF=1
  if [ "$PCF" -ge 1 ]; then
    rc_stopline "POOL DOWN" "runscaler did not run on config.toml (sha256 ${1:0:12}…) within 10 min of a start, a second time (${RUNS_WHY:-it never ran}): CI is down. Read journalctl --user -u runscaler, fix what it names, then systemctl --user restart runscaler; the updater's next pass sees it run"
    rc_end
  fi
  clean "the start at $OPEN_START did not run within 10 min (${RUNS_WHY:-it never ran})"
  ujs pre-close-failure "$REPLY"
  PCF=1 OPEN_START= OPEN_WHAT=
}
rc_sha_now() {   # SHA: right before a `systemctl --user start` (A START IS CHECKED RIGHT BEFORE IT): config.toml is still
  # SHA, the sha proven for that start; else no start, THE ONE RULE (hand-change, STOP HAND CHANGE, the journal open)
  sha_of "$CFG"; [ "$REPLY" = "$1" ] || rc_hand "$REPLY" "config.toml changed right before RECOVER's start (not the sha ${1:0:12}… it validated): nothing was started"
}
rc_start() {   # SHA AFTER WHAT (target | pre | other): THE START (the header) of config.toml = SHA (proven), the unit
  # enabled. An attempt is a `starting E WHAT`. A RESUMED START IS OF THE FILE IT STARTS: one in progress (now < E +
  # 600) is waited for only when it is of this file (its WHAT; for pre and other also its sha, OPEN_SHA: the
  # `recover-target` before it), a unit that is down started again with no new line (its sha checked right before);
  # past its deadline it is a pre-close failure. An open start of another file is no failure of this one: a new start.
  # A ROLLBACK's TARGET start that failed so is DECIDED: THE RESTORE in the same pass, never a second start of the
  # TARGET. At most one new start per pass. Closes (exit 0) or exits open
  local s=$1 c=$3 e m
  AFTER=$2
  if [ -n "$OPEN_START" ] && [ "$OPEN_WHAT" = "$c" ] && { [ "$c" = target ] || [ "$OPEN_SHA" = "$s" ]; }; then
    if [ "$(date +%s)" -lt $((OPEN_START + 600)) ]; then
      unit_read || true
      if [[ $UNIT_ACTIVE =~ ^(inactive|failed)$ ]]; then
        rc_sha_now "$s"
        systemctl --user start runscaler < /dev/null 8>&- 9>&- || true
      fi
      rc_wait "$s" "$AFTER" "$OPEN_START"
    fi
    rc_fail "$s"
    [ "$STARTED" = 1 ] || [ "$c" != target ] || ! rc_decided || rc_restore
    [ "$STARTED" = 0 ] || rc_open "the start did not run within 10 min: the next pass starts it once more"
  fi
  m=$(stat -c %Y "$CFG" 2> /dev/null); [[ $m =~ ^[0-9]+$ ]] || m=0
  [ "$m" -le "$AFTER" ] || AFTER=$m   # past max(the install, the file's mtime): the start proves it (F15)
  while [ "$(date +%s)" -le "$AFTER" ]; do sleep 0.2; done
  e=$(date +%s); ujs starting "$e $c"; STARTED=1 OPEN_START=$e OPEN_WHAT=$c OPEN_SHA=
  [ "$c" = target ] || OPEN_SHA=$RT_SHA
  rc_sha_now "$s"
  systemctl --user start runscaler < /dev/null 8>&- 9>&- || rc_open "systemctl --user start runscaler failed (journalctl --user -u runscaler)"
  rc_wait "$s" "$AFTER" "$e"
  rc_fail "$s"
  rc_open "runscaler did not run within 10 min of RECOVER's start: the next pass starts it once more"
}
rc_restart() {   # SHA AFTER WHAT: RECOVER's restart at once: `from`, `stopping`, config.toml still SHA, the stop,
  # `stopped`, the unit still enabled, then THE START
  local o p
  ujs from "$(proc_now)"
  ujs stopping "$(date +%s)"
  sha_of "$CFG"; [ "$REPLY" = "$1" ] || rc_hand "$REPLY" "config.toml changed right before RECOVER's stop: nothing was stopped"
  rc_stop_unit || rc_open "runscaler did not stop (systemctl --user stop runscaler; it is $UNIT_ACTIVE, pid $UNIT_PID)"
  p=none
  if o=$(log_pos) && [[ $o =~ ^[0-9]+\ [0-9]+\ [0-9a-f]{64}$ ]] && [ "$(proc_now)" = none ]; then p=$o; fi
  ujs stopped "$p"
  unit_read || true
  [ "$UNIT_FILE" = enabled ] || rc_disabled
  rc_start "$1" "$2" "$3"
}
rc_disabled_text() {   # CLASS: the CI DISABLED text of a close with the unit not enabled (PROC: what runs)
  local imgs
  imgs=$(image_of "$CFG") || imgs="config.toml's images"
  case $1 in
    target-idle) REPLY="runscaler is not enabled (a person's \`systemctl --user disable\`) and runs nothing: config.toml is the window's TARGET ($imgs), validated, and runs when a person starts runscaler: systemctl --user enable --now runscaler" ;;
    target-old) REPLY="runscaler is not enabled, but a runscaler that started before the TARGET's install still runs (pid ${PROC% *}): it runs the image from before the window ($(value_of old)); config.toml, the TARGET ($imgs), runs only at its next start: systemctl --user enable runscaler, then restart it at idle" ;;
    target-running) REPLY="runscaler is not enabled, but runs the window's TARGET ($imgs, pid ${RUN% *}): a reboot leaves CI down: systemctl --user enable runscaler" ;;
    target-failed) if [ "$PROC" != none ]; then REPLY="runscaler is not enabled, but runs (pid ${PROC% *}): config.toml is the rollback's TARGET ($imgs), which did not run or failed its validate; the backup is $BKP. Put it back as config.toml before runscaler starts again"
                   else REPLY="runscaler is not enabled and runs nothing: CI is down. config.toml is the rollback's TARGET ($imgs), which did not run or failed its validate; the backup is $BKP: put it back as config.toml, then systemctl --user enable --now runscaler"; fi ;;
    pre|none) REPLY="runscaler is not enabled and runs nothing: this window changed no config: config.toml ($imgs) runs when a person starts runscaler: systemctl --user enable --now runscaler" ;;
    *) REPLY="runscaler is not enabled, and config.toml is no file of this window's (sha256 ${NOW_SHA:0:12}…): check it, and start runscaler only once RUNNER_START_CONFIG=$CFG ~/bin/runner-start validate passes" ;;
  esac
}
value_of() {   # KEY: the journal's first value of KEY (rc_read's), or empty
  local i
  for i in "${!RCK[@]}"; do [ "${RCK[$i]}" != "$1" ] || { printf '%s' "${RCV[$i]}"; return 0; }; done
}
rc_disabled() {   # step 2, the unit NOT enabled: nothing is stopped or started; `stop CI DISABLED`, the closing lines
  # with the class of what is installed and what runs (ONE read)
  rc_class
  PROC=$(proc_now)
  rc_word
  rc_disabled_text "$RC_C"
  rc_stopline "CI DISABLED" "$REPLY"
  rc_finish
}
rc_noeffect() {   # step 1, NO EFFECT YET (the header): the window changed no config and stopped nothing. STAGED removed;
  # a runscaler that RUNS: the close; the unit enabled and none runs (operator (1)): THE START on a proven sha, else
  # once a copy validates (rc_vproof); not enabled: CI DISABLED unless one RUNS
  [ -z "$STAGEDP" ] || rm -f -- "$STAGEDP"
  rc_unit
  rc_class   # never T: no `rename-start` (NO EFFECT, NO TARGET: the TARGET's content here is a person's file)
  rc_after
  [ "$CLS" != OTHER ] || [ -z "$CSHA" ] || rc_handstop "$NOW_SHA" "config.toml changed during the window, before it changed anything (sha256 ${NOW_SHA:0:12}…, not the window's config-sha): check it"
  if [ "$UNIT_FILE" != enabled ]; then
    PROC=$(proc_now)
    rc_word
    rc_runs_any || { rc_disabled_text "$RC_C"; rc_stopline "CI DISABLED" "$REPLY"; }
    rc_finish
  fi
  ! rc_runs_any || rc_end read
  [ "$NOW_SHA" != none ] || rc_unread
  if [ "$CLS" = PRE ] || [ -z "$CSHA" ]; then rc_vproof pre; rc_start "$NOW_SHA" "$AFTER" pre; fi
  rc_vproof other
  rc_start "$NOW_SHA" "$AFTER" other
}
rc_rb_validate() {   # a ROLLBACK's TARGET validated again (D-d THE ROLLBACK RESTART; a copy, `validate recover N`): PASS ->
  # `recover-target`; NON-API -> STOP ROLLBACK FAILED and THE RESTORE; UNKNOWN -> THE RESTORE, no STOP
  rc_vcopy recover
  case $VCLS in
    PASS) rc_target "$VSHA" "$VLINES" ;;
    NON-API) RC_NONAPI=1 RC_VFAIL=1; rc_restore ;;
    *) RC_VFAIL=1; rc_restore ;;
  esac
}
rc_switch_valid() {   # a SWITCH's installed TARGET whose sha is not validated (a comment edit): a copy validates first;
  # NON-API or UNKNOWN: PLAN's ONE RULE (Opus r3 F6): `hand-change`, STOP HAND CHANGE, the journal open, no start
  [ "$VALID" = 1 ] && return 0
  rc_vcopy recover
  [ "$VCLS" = PASS ] || rc_hand "$NOW_SHA" "config.toml has the TARGET's lines but not its bytes (sha256 ${NOW_SHA:0:12}…), and its copy's validate is $VCLS: nothing is started"
  rc_target "$VSHA" "$VLINES"
}
rc_noidle() {   # WHY: THE IDLE RESTART waits: the journal stays open; 3 days after `recover-start`: STOP NO IDLE with the
  # hand line, journaled once, printed at each pass; no automatic restart ever
  local t
  if [ $(( $(date +%s) - RSTART )) -ge 259200 ]; then
    t="the switch to the TARGET ($TLINES) waits for idle since $RSTART, 3 days ago: $1. At a quiet moment, systemctl --user restart runscaler: the updater's next pass sees it run and ends the window"
    if [ "$RC_NOIDLE" = 0 ]; then rc_stopline "NO IDLE" "$t"; else echo "STOP NO IDLE: $t"; fi
    rc_open "the switch waits for idle (STOP NO IDLE)"
  fi
  rc_open "the switch waits for idle: $1"
}
rc_idle_restart() {   # THE IDLE RESTART (a switch, an older runscaler runs its pre-window file): the validate first (when
  # the sha needs it), then ONE idle pair (uidle; an untested jq or a core that cannot decide reads as not idle), then
  # at once the stop and THE START
  rc_switch_valid
  tested_jq || rc_noidle "an untested jq (${JQV}) reads as not idle: install a jq that $CORE/TESTED_JQ lists for core"
  uidle; case $? in
    0) ;;
    1) rc_noidle "$IDLE_WHY" ;;
    *) rc_noidle "the decision core could not decide IDLE ($IDLE_WHY): read as not idle" ;;
  esac
  rc_restart "$NOW_SHA" "$AFTER" target
}
rc_installed_target() {   # step 3, INSTALLED = the TARGET, the unit enabled: 3a it RUNS since the install: closed; a
  # ROLLBACK's start of its TARGET in progress: waited for to its deadline, never made again (expired: ONE pre-close
  # failure, then THE RESTORE); 3c an older runscaler runs (a process that started at or before the install, of any
  # health: it must be stopped before the TARGET can run): a switch's IDLE RESTART, a rollback's restart at once (its
  # TARGET validated first); 3b none runs it (none at all, or one that does not RUN): THE START (a rollback's TARGET
  # validated first)
  local p
  rc_after
  ! rc_runs_now || rc_ran "$NOW_SHA"
  # a rollback's TARGET start in progress, on a sha a line proves (VALID); else (a comment edit) its copy validates
  # first, below, and rc_start then resumes it on that sha
  if [ "$KIND" = rollback ] && [ -n "$OPEN_START" ] && [ "$OPEN_WHAT" = target ] && [ "$VALID" = 1 ]; then
    rc_start "$NOW_SHA" "$AFTER" target
  fi
  p=$(proc_now)
  if [ "$p" != none ] && [ "${p#* }" -le "$AFTER" ]; then
    if [ "$KIND" = rollback ]; then rc_rb_validate; rc_restart "$VSHA" "$AFTER" target; fi
    rc_idle_restart
  fi
  if [ "$KIND" = rollback ]; then rc_rb_validate; rc_start "$VSHA" "$AFTER" target; fi
  rc_switch_valid
  rc_start "$NOW_SHA" "$AFTER" target
}
rc_route() {   # steps 3 to 5, by THE INSTALLED FILE (the header); the unit enabled and no drain
  rc_class
  rc_after
  case $CLS in
    T) rc_installed_target ;;
    PRE)   # 4: nothing was installed (or THE RESTORE's backup): a runscaler that RUNS: closed; none: THE START
      [ -z "$STAGEDP" ] || rm -f -- "$STAGEDP"
      ! rc_runs_any || rc_end read
      rc_vproof pre
      rc_start "$NOW_SHA" "$AFTER" pre ;;
    *) rc_other ;;
  esac
}
rc_other() {   # 5: OTHER (PLAN D5's ONE RULE; the unit enabled): HAND CHANGE (once per file; never for RECOVER's own
  # file); a runscaler that RUNS: nothing restarts, closed other; none: a copy validated (unless a line proves it),
  # then started past the file's mtime; else the journal open (the next pass validates again)
  [ "$CLS" = OWNOTHER ] || rc_handstop "$NOW_SHA" "config.toml (sha256 ${NOW_SHA:0:12}…) is no file of this window's: the updater restarts nothing on it. Check it; to keep it, RUNNER_START_CONFIG=$CFG ~/bin/runner-start validate, then systemctl --user restart runscaler at idle"
  ! rc_runs_any || rc_end read
  [ "$NOW_SHA" != none ] || rc_unread
  rc_vproof other
  rc_start "$NOW_SHA" "$AFTER" other
}
rc_restore() {   # THE RESTORE (the header; a DECIDED rollback): the backup (`config-sha`) back over the TARGET, with no new
  # validate of the TARGET; a close that finds the TARGET installed is target-failed
  local bk=$BKP copy=$R/config.restore.toml rn tgt t
  rc_unit   # a drain is waited for first: what follows reads a unit that is not deactivating
  # the copy, checked FIRST: else nothing is stopped
  { cp -- "$bk" "$copy.tmp" && chmod 600 -- "$copy.tmp" && mv -f -- "$copy.tmp" "$copy"; } 2> /dev/null < /dev/null \
    || rm -f -- "$copy.tmp"
  sha_of "$copy"
  if [ "$REPLY" != "$CSHA" ]; then
    t=$REPLY
    rm -f -- "$copy"
    rc_class; rc_after
    if rc_runs_any; then REPLY="runscaler runs (pid ${RUNS_PROC% *})"; else REPLY="no runscaler runs: CI is down until a person puts a config that validates in place and starts runscaler"; fi
    rc_once "ROLLBACK FAILED" "the backup $bk is not the config from before the rollback" " (sha256 ${t:0:12}…, not config-sha ${CSHA:0:12}…): nothing was stopped or put back; $REPLY"
    rc_end read
  fi
  # config.toml checked BEFORE the stop too: the TARGET, or already the backup (a replay); else a person's file
  rc_class
  if [ "$NOW_SHA" = "$CSHA" ]; then tgt=
  elif [ "$CLS" = T ]; then tgt=$NOW_SHA   # by its CONTENT (a comment changes nothing that runs)
  else   # a person's file, or one RECOVER validated and started for a person (OWNOTHER): THE ONE RULE, never put back
    rm -f -- "$copy"
    [ "$CLS" = OWNOTHER ] || rc_handstop "$NOW_SHA" "config.toml (sha256 ${NOW_SHA:0:12}…) is neither the rollback's TARGET nor its backup: nothing was stopped or put back. Check it"
    rc_after
    [ "$UNIT_FILE" = enabled ] || { PROC=$(proc_now); rc_word; rc_disabled_text "$RC_C"; rc_stopline "CI DISABLED" "$REPLY"; rc_finish; }
    rc_other
  fi
  if { [ "$RC_NONAPI" = 1 ] || [ "$RC_TPCF" = 1 ]; } && [ "$RC_RBF" = 0 ]; then
    rc_stopline "ROLLBACK FAILED" "the rollback's TARGET ($TLINES) $( [ "$RC_TPCF" = 1 ] && echo 'did not run after its start' || echo 'failed its validate (NON-API)'): the backup ($bk, the config from before the rollback) goes back. Read the window's files in $WDIR"
    RC_RBF=1
  fi
  if [ -n "$tgt" ]; then
    if [ "$UNIT_FILE" != enabled ] && [ "$(proc_now)" != none ]; then   # nothing is stopped: the close names what runs
      rm -f -- "$copy"; PROC=$(proc_now)
      rc_word
      rc_disabled_text "$RC_C"
      rc_stopline "CI DISABLED" "$REPLY"
      rc_finish
    fi
    [ "$RC_RESTORE" = 1 ] || { ujs restore "$bk"; RC_RESTORE=1; }
    if ! { [[ $UNIT_ACTIVE =~ ^(inactive|failed)$ ]] && [ "$UNIT_PID" = 0 ]; }; then
      rc_stop_unit || rc_open "runscaler did not stop for the restore (it is $UNIT_ACTIVE, pid $UNIT_PID): nothing was put back"
    fi
    ujs rename-start "$(date +%s)"
    touch -c -m -- "$copy" || rc_open "could not set the time of $copy (touch): nothing was put back"
    unit_read || true
    { [[ $UNIT_ACTIVE =~ ^(inactive|failed)$ ]] && [ "$UNIT_PID" = 0 ]; } \
      || rc_open "a runscaler started before the restore's rename ($UNIT_ACTIVE, pid $UNIT_PID): nothing was put back; the next pass restores again"
    sha_of "$CFG"; [ "$REPLY" = "$tgt" ] || rc_hand "$REPLY" "config.toml changed right before the restore's rename: nothing was put back"
    mv -f -- "$copy" "$CFG" || rc_open "could not rename $copy over $CFG"
    rn=$(date +%s); ujs renamed "$rn"; RC_RN=$rn
  fi
  rm -f -- "$copy"
  rc_class   # the backup is installed now (sha `config-sha`): PRE, RECOVER's own TARGET once proven
  rc_after
  if [ "$UNIT_FILE" != enabled ]; then
    REPLY="runscaler is not enabled: the rollback failed, and config.toml is its backup again ($bk: the config from before the rollback, $(image_of "$CFG")), which runs when a person starts runscaler: systemctl --user enable --now runscaler"
    rc_stopline "CI DISABLED" "$REPLY"
    rc_end read
  fi
  ! rc_runs_now || rc_ran "$CSHA"
  rc_vproof pre
  [ "$(proc_now)" = none ] || rc_restart "$CSHA" "$AFTER" pre
  rc_start "$CSHA" "$AFTER" pre
}
un_recover() {   # RECOVER (the header): in order 0 closed, 1 no effect, DECIDED LINES, 2 the unit, 3-5 the installed file
  UFAIL_RC=5 STARTED=0
  [ -e "$J" ] || [ -L "$J" ] || { rcsay "no window journal ($J): nothing to recover"; exit 3; }
  rc_pats
  rc_read
  rc_facts
  WDIR=$WINDOWS/$WID.d
  [ -d "$WDIR" ] || mkdir -m 700 -- "$WDIR" 2> /dev/null || rc_cannot "its folder $WDIR cannot be made"
  rc_trim
  if [ "$RC_LAST" = closed ]; then rcsay "the window journal $J is closed: the updater's apply step applies it"; exit 0; fi
  if [ "$RC_LAST" = installed ]; then   # its closing lines were written; only `closed` was cut
    ujs closed "$(date +%s)"; rcsay "the window journal $J is closed: the updater's apply step applies it"; exit 0
  fi
  [ -n "$RSTART" ] || { RSTART=$(date +%s); ujs recover-start "$RSTART"; }
  rc_dangling   # A ONCE-LINE IS KEYED ON ITSELF: a `hand-change` whose STOP a cut lost gets it first
  # 1 NO EFFECT YET
  if [ -z "$CSHA" ] || [ -z "$BKP" ]; then rc_noeffect; fi
  # DECIDED LINES (a rollback), before the unit
  ! rc_decided || rc_restore
  # 2 THE UNIT
  rc_unit
  [ "$UNIT_FILE" = enabled ] || rc_disabled
  # 3-5 THE INSTALLED FILE
  rc_route
}

[ "$(id -un)" = ${RS_USER} ] || die "run me as ${RS_USER}"
if [ "$UN" = 1 ]; then   # THE UPDATER'S CHILD first (runner-release.sh's rr_held: the updater lock on fd 9, handed down by
  # its holder, runner-updater), then this script's own lock
  # shellcheck source=runner-release.sh
  . "$B/setup/runner-release.sh" || die "cannot read $B/setup/runner-release.sh (is this release's linux-docker/ ~/build?): nothing changed"
  # the measuring helpers (proc_now, unit_read, runs, log_pos, tested_jq, healthz_pair): ONE copy, shared with
  # bin/runner-updater
  # shellcheck source=runner-facts.sh
  . "$B/setup/runner-facts.sh" || die "cannot read $B/setup/runner-facts.sh (is this release's linux-docker/ ~/build?): nothing changed"
  rr_held || die "REFUSE $MODE --unattended is the updater's only: runner-updater runs it as its child, holding the updater lock $RR_LOCK on fd 9 ($RR_WHY); a person's rollback is \`runner-updater back hz-docker\`; nothing changed"
fi
# fd 8, never 9: an unattended run holds the updater lock on fd 9, which its parent handed it
exec 8>> "$LOCK" || die "cannot open the lock $LOCK; nothing changed"
if ! flock -n 8; then   # RECOVER waits for a person's run (D-h): it reads and changes nothing, and the next pass tries again
  [ "$MODE" != recover ] || { echo "WAIT another pool-image.sh run holds $LOCK (pid $(head -n 1 "$LOCK" 2> /dev/null): a person's run): RECOVER read and changed nothing; the updater's next pass tries again"; exit 4; }
  die "another pool-image.sh run holds $LOCK: pid $(head -n 1 "$LOCK" 2> /dev/null) took it, and a child it started (a systemctl restart that still drains) holds it until that child ends. An ssh drop can leave such a run alive. Let it end, or stop it, then run this again; nothing changed"
fi
printf '%s\n' "$$" > "$LOCK"
[ "$UN" = 0 ] || unattended
cur=$(image_of "$CFG") || die "config.toml does not name ONE runner image for both sets: read it first; nothing changed"

if [ "$MODE" = accept ]; then
  [ -e "$KEEPC" ] || { ok "no rollback is kept: there is no open release to accept"; exit 0; }
  kept=$(image_of "$KEEPC") || die "$KEEPC does not name ONE runner image for both sets: read it; nothing changed"
  [ "$kept" != "$cur" ] || die "config.toml runs $cur, the rollback's own image: after a back there is nothing to accept; nothing changed"
  started_after || die "runscaler has not restarted since config.toml was installed, so $cur has not run a job yet: run pool-image.sh up again first; nothing changed"
  rm -f "${KEEPC:?}" || die "could not remove $KEEPC"
  echo "POOL IMAGE ACCEPTED: $cur (the rollback to $kept is removed; the next release's up keeps this config)"
  exit 0
fi

if [ "$MODE" = runscaler ]; then   # THE RUNSCALER STEP (the header)
  # (a) THE PRECONDITIONS, each refusing with nothing changed
  p=$(pins_bad) && die "$p is not the reviewed copy (sha256): install this release's files first (README Install step 3); nothing changed"
  { pin=$(pin03 BIN_SHA) && wb=$(pin03 WAYBACK_BIN_SHA) && ptgz=$(pin03 TGZ_SHA) && wtgz=$(pin03 WAYBACK_TGZ_SHA) \
      && PINNED=$(ver03 PINNED) && WAYBACK=$(ver03 WAYBACK); } \
    || die "$S03 does not name its two runscalers (THE RUNSCALERS) once each: nothing changed"
  RSV=${RSV:-$PINNED}
  case $RSV in
    "$PINNED") WANT=$pin TGZ=$ptgz ;;
    "$WAYBACK") WANT=$wb TGZ=$wtgz ;;
    *) die "runscaler v$RSV is not one this release knows: v$PINNED (the one it pins: pool-image.sh runscaler) or v$WAYBACK (the way back: pool-image.sh runscaler $WAYBACK); nothing changed" ;;
  esac
  { [ ! -e "$J" ] && [ ! -L "$J" ]; } || die "the updater's window journal $J is there (a switch or a rollback it has not ended or applied): run ~/bin/runner-updater pass, then ~/bin/runner-updater status, until it shows no window journal (README Install step 3); nothing changed"
  rmkeep=0
  if [ -e "$KEEPC" ] || [ -L "$KEEPC" ]; then
    cmp -s -- "$KEEPC" "$CFG" || die "an image release is open: $KEEPC, the rollback an up kept, is not config.toml. Close it first: pool-image.sh accept (its image works) or pool-image.sh back; nothing changed"
    rmkeep=1
  fi
  en=$(systemctl --user is-enabled runscaler 2> /dev/null 8>&- 9>&-)
  [ "$en" = enabled ] || die "runscaler's unit is ${en:-not readable}, not enabled (CI off by a person): enable it first (systemctl --user enable --now runscaler), then run this again; nothing changed"
  st=$(systemctl --user is-active runscaler 2> /dev/null 8>&- 9>&-)
  case $st in
    active) if started_after; then rule=content; else rule=bytes; fi ;;
    inactive|failed|activating) rule=content ;;
    *) die "runscaler's unit is ${st:-not readable} (a stop or a start in progress): run this again once it ended; nothing changed" ;;
  esac
  dl=$(dl_of "$RSV")
  got=$(sha256sum < "$dl" 2> /dev/null) || got=
  [ "${got%% *}" = "$TGZ" ] || die "$dl is not runscaler v$RSV's download (no such file, or its sha256 ${got:0:12} is not 03's): download it as RS_USER: mkdir -p ~/build/dl && curl -fsSL -o ~/build/dl/${dl##*/} https://github.com/ysya/runscaler/releases/download/v$RSV/runner-linux-amd64.tar.gz ; nothing changed"
  # shellcheck source=runner-release.sh
  . "$B/setup/runner-release.sh" || die "cannot read $B/setup/runner-release.sh (is this release's linux-docker/ ~/build?): nothing changed"
  if [ "$rmkeep" = 1 ]; then
    rm -f -- "$KEEPC" || die "could not remove $KEEPC: nothing else changed"
    ok "removed $KEEPC: it was config.toml byte for byte, the kept config of an image release a back closed"
  fi
  rs=$(runner_sha) || rs=none
  # (b) DONE ALREADY
  if [ "$st" = active ] && started_after && [ "$(running_sha)" = "$WANT" ] && [ "$rs" = "$WANT" ] \
      && [ "$(grep -c -x -F -- "$RR_LOGK" "$CFG")" = 1 ]; then
    DONE=1
    ok "DONE ALREADY: $HOME/bin/runner is runscaler v$RSV, its process runs config.toml, which has the log-file line: no stage, no restart"
  else
    # (c)+(d) THE STAGE, in 03
    echo; echo "== 03-runscaler.sh stage $RSV $rule ($HOME/bin/runner is $(rs_name "$rs"); the unit $st)"
    bash "$S03" stage "$RSV" "$rule" < /dev/null || die "03 stage failed (its FAIL line above): nothing restarted; $HOME/bin/runner is $(rs_name "$(runner_sha || echo none)"). $(again)"
    [ "$(runner_sha)" = "$WANT" ] || die "03 said DONE, but $HOME/bin/runner is not runscaler v$RSV: read it; nothing restarted"
  fi
fi

if [ "$MODE" = up ]; then
  # Only `up` reads a build record: `back` and `accept` work from what runs and what was kept.
  p=$(pins_bad) && die "$p is not the reviewed copy (sha256): nothing changed"
  # ONE DOOR (the header): an image switch runs on the runscaler that is there, one of the two 03 knows
  pin=$(pin03 BIN_SHA) && wb=$(pin03 WAYBACK_BIN_SHA) || die "$S03 does not name its two runscalers (BIN_SHA, WAYBACK_BIN_SHA) once each: nothing changed"
  rs=$(runner_sha) || rs=none
  [ "$rs" = "$pin" ] || [ "$rs" = "$wb" ] || die "$HOME/bin/runner (sha256 ${rs:0:12}) is neither of the two runscalers this release knows (03-runscaler.sh's BIN_SHA and WAYBACK_BIN_SHA): an image switch never changes it, and only pool-image.sh runscaler does; nothing changed"
  fix="build it as ${RUN_USER}, with this release's linux-docker/ as its ~/build: ssh ${RUN_USER}@<host> 'bash ~/build/setup/02-d1.sh build $VERSION'"
  # the recipe and the build record: runner-release.sh's rr_recipe and rr_record, the ONE copy 02-d1.sh and the
  # updater use too (the header)
  # shellcheck source=runner-release.sh
  . "$B/setup/runner-release.sh" || die "cannot read $B/setup/runner-release.sh (is this release's linux-docker/ ~/build?): nothing changed"
  rr_recipe "$B/image" || die "the recipe of $B/image cannot be computed: $RR_WHY: nothing changed"
  recipe=$RR_RECIPE
  rr_record "$BUILDS" "$VERSION" "$recipe" || die "no usable build record of runner $VERSION for this release's image (recipe ${recipe:0:12}…, $BUILDS/$VERSION-$recipe): $RR_WHY. To make it, $fix; nothing changed"
  digest=$RR_REC_DIGEST
  new=localhost:${REGISTRY_PORT}/${IMAGE_NAME}@$digest
  [[ $new =~ $IMGRE ]] || die "the build record's image [$new] is not one strict digest reference: nothing changed"
  pulls "$new"; case $? in 0) ;; 1) die "the registry does not serve $new, the image of the build record of runner $VERSION (removed since, or not this registry's): $fix; nothing changed" ;; *) die "the registry ($REG) does not answer: nothing changed" ;; esac
  # The runner's version, from the image itself: its labels do not carry it (measured). No network, bounded. Every
  # child here reads /dev/null: the script itself arrives on stdin (`bash -s`), and a child that reads it eats the rest.
  # The image sets ACTIONS_RUNNER_PRINT_LOG_TO_STDOUT=1, so the runner's log comes too: the version is the one line
  # that is a bare version number (two such lines = no match = refused).
  out=$(DOCKER_HOST=$D1 docker run --rm --network none --memory 512m --cpus 1 "$new" ./config.sh --version < /dev/null) \
    || die "could not run $new to read its runner version (its error is above): nothing changed"
  v=$(grep -xE '[0-9]+\.[0-9]+\.[0-9]+' <<< "$out")
  [ "$v" = "$VERSION" ] || die "the runner in $new is [$v], not $VERSION, though its build record names $VERSION: $fix; nothing changed"
  ok "build record of runner $VERSION: $new (the registry serves it; runner $v)"
  if [ "$cur" != "$new" ]; then
    if [ -e "$KEEPC" ]; then
      kept=$(image_of "$KEEPC") || die "$KEEPC does not name ONE runner image for both sets: read it; nothing changed"
      [ "$kept" = "$cur" ] || die "config.toml runs $cur, but an earlier up kept $kept as the rollback, so that release is still open. If $cur works, run pool-image.sh accept first; if not, run pool-image.sh back first. Nothing changed"
    elif [ "$(systemctl --user is-active runscaler 2> /dev/null 8>&- 9>&-)" = active ] && ! started_after; then
      # No rollback yet, so this keeps config.toml as one: it must be the config runscaler RUNS (a bare 03 run
      # installs a config under the running process).
      die "config.toml was installed after runscaler started (03 ran outside pool-image.sh?), so it is not the config the pool runs, and keeping it would be no rollback. Restart runscaler at idle first (docs/runners.md section 3b), then run up again; nothing changed"
    fi
    holds_pool "$CFG" || die "pool.env does not hold the numbers config.toml runs, and 03 renders pool.env's: they would go live with the image. Compare $POOL with $CFG first; nothing changed"
    pulls "$cur" || echo "WARN the registry does not serve the image the pool runs now ($cur): its rollback could not start a runner"
    put "$CFG" "$KEEPC"; ok "kept $KEEPC (the rollback: $cur)"
    m0=$(stat -c %Y "$CFG")
    echo; echo "== 03-runscaler.sh real $digest --image-only (the same sets and numbers, the record's image: it installs with the pool running, and restarts nothing)"
    bash "$S03" real "$digest" --image-only < /dev/null || die "03 real failed: config.toml was not changed, so the pool keeps $cur. Read 03's FAIL line above"
    [ "$(image_of "$CFG")" = "$new" ] || die "03 said DONE but config.toml does not run $new: read it; to go back run pool-image.sh back"
    if ! rr_same_but_image "$KEEPC" "$CFG"; then
      put "$KEEPC" "$R/config.real.toml"; put "$KEEPC" "$CFG"
      python3 -c 'import os, sys; t = int(sys.argv[2]); os.utime(sys.argv[1], (t, t))' "$CFG" "$m0" || die "config.toml is the old one again, but its mtime is new: do NOT restart; read $R"
      die "03's config differed from the rollback in more than the image (did pool.env change during the run?): config.toml is back as it was, mtime too, and nothing restarted"
    fi
  else
    ok "config.toml already runs the build record's image: 03 is not run again"
    if ! started_after; then   # a restart is pending: allowed only into a config this script installed
      [ -e "$KEEPC" ] || die "config.toml names the build record's image, but no rollback was kept for the config runscaler runs (03 ran outside pool-image.sh?): nothing restarted"
      if [ "$(systemctl --user is-active runscaler 2> /dev/null 8>&- 9>&-)" = active ]; then
        a=$(start_of) || die "cannot read runscaler's start time: nothing restarted"
        [ "$(stat -c %Y "$KEEPC")" -ge "$a" ] || die "the rollback $KEEPC is older than the running process, so it is not the config that process runs (03 ran outside pool-image.sh?): nothing restarted"
      fi
      rr_same_but_image "$KEEPC" "$CFG" || die "config.toml differs from the rollback in more than the image: nothing restarted. Compare $KEEPC with $CFG"
    fi
  fi
elif [ "$MODE" = back ]; then
  [ -e "$KEEPC" ] || die "no $KEEPC: there is no open release to roll back (accept removed it, or up never ran); nothing changed"
  old=$(image_of "$KEEPC") || die "$KEEPC does not name ONE runner image for both sets: read it; nothing changed"
  # THE CONFIG COMPARE and BACK'S PAIR GUARD (the header): runner-release.sh's
  # shellcheck source=runner-release.sh
  . "$B/setup/runner-release.sh" || die "cannot read $B/setup/runner-release.sh (is this release's linux-docker/ ~/build?): nothing changed"
  kc=$(rr_content "$KEEPC") || die "cannot read $KEEPC: nothing changed"
  if rr_logfile_free "$kc"; then
    wb=$(pin03 WAYBACK_BIN_SHA) || wb="unread (03 names no WAYBACK_BIN_SHA)"
    rs=$(runner_sha) || rs=none
    [ "$rs" = "$wb" ] || die "the rollback $KEEPC has no log-file key, and $HOME/bin/runner (sha256 ${rs:0:12}) is not the way-back runscaler (v0.9.5, 03-runscaler.sh's WAYBACK_BIN_SHA), the one that runs such a config: runner-start would refuse it at the restart, and CI would be down. The steps of this release do not make this pair (pool-image.sh runscaler refuses while a release is open, and removes the rollback of one a back closed): read $HOME/bin/runner and $KEEPC. To keep the image config.toml runs, run pool-image.sh accept; nothing changed"
  fi
  if cmp -s "$KEEPC" "$CFG"; then
    ok "config.toml already is the rollback ($old)"
  else
    rr_same_but_image "$KEEPC" "$CFG" || die "config.toml differs from the rollback in more than the image (sets or numbers changed since up): a rollback would undo that too. Compare $KEEPC with $CFG; nothing changed"
    pulls "$old"; case $? in
      0) ;;
      1) die "the registry no longer holds the rollback's image $old: a runner of it could not start; nothing changed" ;;
      *) die "the registry ($REG) does not answer, so no runner of either image can start: bring D1's registry back first (02-d1.sh as ${RUN_USER}); nothing changed" ;;
    esac
    put "$KEEPC" "$R/config.real.toml"; put "$KEEPC" "$CFG"; ok "config.toml and config.real.toml: back to $old"
    echo "NOTE a later 03 real with no digest renders $old, the image config.toml runs now: the new image comes back only with an up"
  fi
fi
ok "config.toml runs $(image_of "$CFG") (sha256 $(sha256sum "$CFG" | cut -c1-12))"

case $MODE in up|back) holds="config.toml runs the $MODE image" ;; *) holds="$HOME/bin/runner is runscaler v$RSV" ;; esac
echo; echo "== restart"
if [ "$DONE" = 1 ]; then
  ok "no restart (DONE ALREADY)"
elif runs_this; then
  ok "runscaler started after config.toml was installed ($(systemctl --user show runscaler -p ActiveEnterTimestamp --value 8>&- 9>&-)): it runs this image$([ "$MODE" != runscaler ] || echo " and runscaler v$RSV"), no restart"
elif [ "$(systemctl --user is-active runscaler 8>&- 9>&-)" != active ]; then
  restart || die "systemctl --user restart runscaler failed: read journalctl --user -u runscaler. $holds. $(again)"
else
  quiet=0; for _ in $(seq 1 40); do counts quiet && { quiet=1; break; }; sleep 15; done
  if [ "$quiet" = 0 ]; then
    echo "WAIT jobs still run after 10 min: the restart now waits (up to 60 min) for a moment with no runner between jobs, then drains the running ones (up to 70 min; the small lane takes no new job meanwhile)"
    calm=0; for _ in $(seq 1 240); do counts noidle && { calm=1; break; }; sleep 15; done
    [ "$calm" = 1 ] || echo "WAIT no moment without a runner in its idle phase came in 60 min: restarting anyway — a job this cuts is named at the end"
  fi
  restart || die "systemctl --user restart runscaler failed: read journalctl --user -u runscaler. $holds. $(again)"
fi
for _ in $(seq 1 40); do out=$(ready 2>&1) && break; sleep 15; done
printf '%s\n' "$out"
[ "$(systemctl --user is-active runscaler 8>&- 9>&-)" = active ] && [ "$(systemctl --user is-enabled runscaler 8>&- 9>&-)" = enabled ] || die "runscaler is not active and enabled: read journalctl --user -u runscaler. $holds. $(again)"
ready > /dev/null || die "the pool is not READY after 10 min: read journalctl --user -u runscaler. $holds. $(again)"
if [ "$MODE" = runscaler ]; then   # THE RUNNING BINARY (the header)
  rsn=$(running_sha) || rsn=none
  [ "$rsn" = "$WANT" ] || die "the runscaler that runs is not v$RSV: its process runs $(rs_name "$rsn"): read journalctl --user -u runscaler. $holds. $(again)"
  ok "the runscaler that runs is v$RSV (its process's binary, sha256 ${WANT:0:12})"
fi
# A JOB A RESTART CUT: the OLD process logs it while a busy runner drains (its listener stays up — minutes before the
# restart returns), the NEW one as it starts — either way AFTER this config.toml was installed, which is where the scan
# starts (so a re-run after an ssh drop still finds it). Each name carries its log time: a repeat on a later re-run
# reads as old.
inst=$(date -u -d "@$(stat -c %Y "$CFG")" +'%Y-%m-%d %H:%M:%S')
cut=$(awk -v s="$inst" '($1 " " $2) >= s && /Job started for unknown runner/ { r = $0; sub(/.*runnerName=/, "", r); print $1 " " $2 " " r }' "$R/runner.log" 2> /dev/null | sort -u | paste -sd ',' -)
[ -z "$cut" ] || echo "WARN a restart since this config was installed ($inst UTC) cut a job on [$cut] (log time, runner): find it on GitHub (it ends 'lost communication' after 10 min) and re-run it, unless it already was"
if [ "$MODE" = runscaler ]; then
  echo "POOL RUNSCALER DONE: runscaler v$RSV runs ($HOME/bin/runner and the process, sha256 ${WANT:0:12}), on config.toml with the log-file line"
  if [ "$RSV" = "$PINNED" ]; then
    echo "NEXT the check the next day (README \"runscaler: the release this one pins, and the way back\"). The way back, if it does not serve: its download, then this step with its version (as RS_USER):"
    echo "  mkdir -p ~/build/dl && curl -fsSL -o ~/build/dl/$(basename "$(dl_of "$WAYBACK")") https://github.com/ysya/runscaler/releases/download/v$WAYBACK/runner-linux-amd64.tar.gz"
    echo "  pool-image.sh runscaler $WAYBACK"
  else
    echo "NEXT the way forward again, from Install step 4's download: pool-image.sh runscaler"
  fi
  exit 0
fi
echo "POOL IMAGE DONE ($MODE): $(image_of "$CFG")"
[ "$MODE" = back ] || echo "NEXT READY says nothing about the image (no runner has started from it yet): watch the first job on it, then run pool-image.sh accept (it works) or pool-image.sh back (it does not)"
