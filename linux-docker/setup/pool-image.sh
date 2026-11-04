#!/usr/bin/env bash
# pool-image.sh — a RUNNER RELEASE, the POOL half: AS RS_USER, after `02-d1.sh build VERSION` (as RUN_USER) built the
# runner image of VERSION and wrote its build record. Needs this release's linux-docker/ as ~/build.
#   up:     ssh -o ServerAliveInterval=60 RS_USER@<host> 'bash -s -- up 2.338.2' < linux-docker/setup/pool-image.sh
#   back:   the same line with `back` — the rollback to the image the pool ran before this release's `up`.
#   accept: the same line with `accept` — ends the release once a job passed on the new image: the kept rollback is
#           removed, so the NEXT release's `up` keeps this config. Until then an `up` to another image refuses. It
#           closes the release whose image config.toml RUNS, whatever build records there are by then.
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
# up:   refuses unless pool.env holds the numbers config.toml runs (03 renders from pool.env, so others would go live
#       with the image) and the record's image's runner is VERSION; keeps the rollback; 03 real DIGEST (the same sets and
#       numbers, the record's image: it installs with the pool running and restarts nothing; if it fails, config.toml is
#       unchanged); if config.toml then differs from the rollback in more than the image, the rollback goes back with
#       config.toml's old mtime and nothing restarts. config.toml already on the record's image with a restart pending (a
#       run cut off before its restart, or a bare 03 run) restarts only when the rollback was kept while the running
#       process ran.
# back: puts config.toml.pre-image back with NO 03 (no build, no GitHub), only when the image is ALL it changes and the
#       registry still serves the old digest (runscaler pulls it at every runner start, so a dead registry stops both
#       images alike). `03 real` with no digest renders the image config.toml runs NOW, so a later 03 (a change of the
#       numbers) keeps the old image; only an `up` puts a new one in.
# ONE RUN AT A TIME: a lock in ~/.config/runner. An ssh drop with no pty can leave the old run alive; a new one then
# refuses and names its pid.
# Then, up and back: the restart. restart() re-reads the start time just before it restarts, so it never restarts a
# process that already runs this config.toml. If runscaler already started after config.toml was installed, no
# restart; else wait up to 10 min for both sets to be quiet (no runner, no job), then up to 60 min more for a moment
# with no runner in its idle phase, then restart (SIGTERM = drain: a running job finishes first, up to 70 min) -> READY
# within 10 min -> name any job a restart cut.
# PINS: what 03 runs, and what it installs from ~/build before it validates, by sha256. tools/release-check refuses a
# pinned file that changed without its PIN.
#
# THE UNATTENDED MODES: the runner-image updater's switch and rollback (plan D1, D5, D6). Run from ~/build itself:
#   bash ~/build/setup/pool-image.sh up --unattended VERSION DIGEST   (DIGEST: sha256:<64 hex>, of the build record of
#                                                                     VERSION, which the updater read)
#   bash ~/build/setup/pool-image.sh back --unattended                (also a person's `back` of an updater's switch)
# Each holds THE UPDATER LOCK (runner-release.sh's rr_lock: on fd 9, so a parent that holds it runs this as its child;
# another holder makes it wait, and it says so first) and then this script's own lock (fd 8, -n), and keeps ONE WINDOW
# JOURNAL, ~/.local/state/runner-updater/window: one `KEY VALUE` line per fact, each appended and synced (`dd
# conv=notrunc,fsync`, its exit status checked) BEFORE the step it names; a journal it cannot write stops the window
# before that step. A journal there at the start is an earlier window that did not close: REFUSE, nothing changed. A
# window that ends is CLOSED: its journal is renamed to ~/.local/state/runner-updater/windows/ID, its files (each
# validate's whole output, the /healthz reads) stay in windows/ID.d.
# up --unattended: (1) the window's start and runscaler's process (systemd's MainPID and ActiveEnterTimestamp, one read);
#   FAMILY LINES (config.toml's two sets name ONE image, the old image, which the registry must still serve: the
#   rollback's; DIGEST's image already: nothing to switch, config.toml.prev kept as it is: done, `running`, when a
#   runscaler that started after config.toml's install runs it, else `end`); START STATE (the unit active and enabled,
#   config.toml installed before its start: else not now); DISK (RUN_USER's filesystem, D1's data and the registry, at
#   least DISK_PCT % free: runscaler's min_free); jq (`jq --version` a core row of ~/build/core/TESTED_JQ); the PINS;
#   then PRE-VALIDATE: `03-runscaler.sh render DIGEST STAGED` (STAGED = ~/.config/runner/config.staged.toml; 03
#   refuses a rejected digest), up to 3 tries 20 s apart: exit 0 (PASS) ends them, exit 4 (API-ONLY) tries again and
#   after the third counts as PASS, anything else is STOP check failed, nothing installed; then D3: STAGED names DIGEST
#   and differs from config.toml in its runner-image lines alone. (2) THE IDLE PAIR: two /healthz reads 3 s apart,
#   decided by ~/build/core/idle.jq over every set config.toml names and every set the reads list (no state: no set is
#   excused, the updater keeps the 24 h); a core that fails or answers no idle/not-idle: `end`. Not idle: STAGED
#   removed, config.toml unchanged, the journal removed, exit 3. (3) At once: THE BACKUP to config.toml.prev (the
#   rollback; STAGED must still be the one 03 printed first, else STOP check failed and config.toml.prev stays as it
#   was), then THE RENAME and THE RESTART, below, unconditionally (no idle check again).
# back --unattended: the rollback to config.toml.prev, the backup of the switch it undoes. The unit not active and
#   enabled: no restart, `end rollback pending: CI disabled by a person` (the updater tries again). config.toml
#   installed after runscaler started: STOP HAND CHANGE (a pending hand edit). config.toml already the backup (and
#   running, so): done, `running` the process that runs it, no restart. No backup, one that does not name ONE
#   image, one that differs from config.toml in more than its runner-image lines, or one whose image the registry
#   does not serve: STOP ROLLBACK FAILED. PRE-VALIDATE of a copy (STAGED = ~/.config/runner/config.rollback.toml,
#   its lines checked once it is made) by the ONE VALIDATE RULE (~/bin/runner-start validate, stdout and
#   stderr, ~/bin/validate-class), up to 3 tries 20 s apart: PASS ends them, API-ONLY after the third counts as PASS,
#   NON-API is STOP ROLLBACK FAILED and UNKNOWN is `end` (no STOP: the updater tries again), both before any restart.
#   No idle wait: then THE BACKUP of the config it replaces to windows/ID.d/config.toml.backup (what the updater's
#   RECOVER puts back when the rollback target fails validate: plan D1, RECOVER step 4), THE RENAME and THE RESTART
#   at once (runscaler's drain lets busy runners finish).
# THE ORDER OF CHECK AND STEP: each check of a file comes AFTER the journal line of the step it guards and right before
#   that step, and a copy is checked after it is made. A failed check before `rename-start` closes the journal (STOP);
#   after it, the journal closes only when config.toml is provably the window's own pre-window file (just checked),
#   and else stays OPEN with `hand-change` (A HAND CHANGE: nothing restarts on that file) for the updater's RECOVER.
# THE BACKUP: `backup P`, config.toml copied to P.tmp (0600), the copy's sha checked against `config-sha` (else STOP
#   HAND CHANGE, P as it was), renamed to P.
# THE RENAME: `rename-start`; the INSTALL TIME: STAGED's mtime set by the clock now (`touch -c -m`), so config.toml's
#   mtime second, which started_after reads, is rename-start's or later and renamed's or earlier (never the render or
#   copy time: plan D1); config.toml still `config-sha` (else A HAND CHANGE: nothing renamed) and STAGED still
#   `staged-sha` (else STOP check failed | ROLLBACK FAILED, closed: config.toml is the pre-window file), then STAGED
#   renamed over config.toml at once, `renamed` (UTC epoch: the install time, plan D1), then a wait until the clock's
#   second is past it.
# THE RESTART: `from` (the process it stops), `stopping` (the restart's own epoch), config.toml still the TARGET (else
#   A HAND CHANGE AFTER THE INSTALL: no stop), `systemctl --user stop runscaler` (the drain), `stopped` (once no
#   runscaler runs, before and after: the log position ~/.config/runner/runner.log's inode, its size, and the sha256 of
#   the 64 bytes before it, or none), `starting`, the TARGET again (else no start: runscaler stays stopped),
#   `systemctl --user start runscaler`, then up to 10 min until a process that started after `renamed` runs, with
#   config.toml still the TARGET (else the hand-change STOP): `running`. The updater hands the core facts.restart =
#   {from, to: running, stopped} (core/README.md). A kill anywhere after `rename-start` leaves the journal open, and
#   the old file is never put back: the updater's next pass reads config.toml's sha against `config-sha` and
#   `staged-sha`, and the `backup` file.
# THE RESIDUALS (instants no lock-free design closes, each a few ms): a hand edit of config.toml after the rename's
#   check and before the rename is replaced by it; a runscaler start in a later second than the install time's and
#   before the rename reads as started after the install; a change of config.toml after the start's check and before
#   runner-start reads the file is started on (the check after the start sees it: `hand-change`, the journal open,
#   but that process may run either file).
# The journal, line by line (V = N.N.N, H = 64 hex, P = an absolute path, I = an image reference, E = UTC epoch):
#   window ID                   ^window [0-9]{14}-[0-9]+$     (UTC yyyymmddHHMMSS-pid)
#   kind switch|rollback        ^kind (switch|rollback)$
#   version V                   (switch)
#   digest sha256:H             (switch)
#   process PID START | none    runscaler at the window's start (MainPID, ActiveEnterTimestamp)
#   old I                       the image config.toml names at the window's start (a rollback's target: `target`)
#   config-sha H                config.toml at the window's start
#   staged P                    before STAGED is written
#   validate pre N CLASS        ^validate pre [1-3] (PASS|API-ONLY|NON-API|UNKNOWN)$   (windows/ID.d/validate-pre-N.out)
#   staged-sha H                the validated STAGED: the TARGET
#   target SET=I SET=I          the TARGET's lines, in config order
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
#   starting E                  before `systemctl --user start`
#   running PID START           the new process, started after `renamed` (with no rename: after config.toml's install)
#   stop NAME: TEXT             a STOP (check failed | DISK | untested jq | HAND CHANGE | ROLLBACK FAILED)
#   end TEXT                    the window ended with no STOP (the updater tries again later)
#   closed E                    before the journal is renamed to windows/ID
# Exit codes of the unattended modes (the updater's interface; it reads the rest from the journal and the files):
#   0  done: the target runs (a process started after `renamed`, or with nothing to switch after config.toml's install);
#      the journal closed
#   1  not done: the closed journal's `stop` or `end` line says why; or the journal is still OPEN (a step after
#      `rename-start` failed or was cut, or A HAND CHANGE found after it): the updater's RECOVER ends it; or a
#      REFUSE before any journal (not RS_USER, a lock, an open journal)
#   2  usage
#   3  not now (up): START STATE not met, or not idle; nothing staged, nothing changed, no journal kept
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
MODE=${1-} VERSION= DIGEST= UN=0
usage() { echo "usage: pool-image.sh up RUNNER_VERSION (for example 2.338.2) | back | accept   (a person's)"
  echo "       pool-image.sh up --unattended RUNNER_VERSION DIGEST | back --unattended   (the updater's; DIGEST: sha256:<64 hex>)"; exit 2; }
case $MODE:$# in
  up:2) VERSION=$2 ;;
  up:4) [ "$2" = --unattended ] || usage; UN=1 VERSION=$3 DIGEST=$4; [[ $DIGEST =~ ^sha256:[0-9a-f]{64}$ ]] || usage ;;
  back:1|accept:1) ;;
  back:2) [ "$2" = --unattended ] || usage; UN=1 ;;
  *) usage ;;
esac
[ "$MODE" != up ] || [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || usage
R=$HOME/.config/runner; CFG=$R/config.toml; KEEPC=$R/config.toml.pre-image; POOL=$R/pool.env; LOCK=$R/pool-image.lock
BUILDS=/home/${RUN_USER}/run/builds; REG=http://127.0.0.1:${REGISTRY_PORT}; D1=unix:///home/${RUN_USER}/run/docker.sock; B=$HOME/build
S03=$B/setup/03-runscaler.sh
# The unattended modes' files (the header): the window journal, the closed ones, the rollback, the decision core
STATE=$HOME/.local/state/runner-updater; J=$STATE/window; WINDOWS=$STATE/windows; KEEPP=$R/config.toml.prev; CORE=$B/core
DISK_PCT=10   # runscaler's min_free (plan D5 DISK): the share of D1's filesystem a switch leaves free
# What 03 runs, and what it installs from ~/build before it validates, by sha256 (the header says why).
PINS="$S03=ed63eccdcb4fcb680c562bca55370e59755aeefc92fdd568debf0af4fd4e7a57
$B/bin/runner-start=698d52799fc20feff260fcec82d3aa49f66aa535547368b17d27226941306107
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
same_but_image() {   # same_but_image A B: the two configs differ in their runner-image lines alone
  cmp -s <(grep -v '^runner-image = ' "$1") <(grep -v '^runner-image = ' "$2")
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
  local a; a=$(systemctl --user show runscaler -p ActiveEnterTimestamp --value --timestamp=unix 2> /dev/null); a=${a#@}
  [[ $a =~ ^[0-9]+$ ]] && echo "$a"
}
started_after() {   # runscaler is active and started after config.toml was installed: it runs this config.toml
  local a
  [ "$(systemctl --user is-active runscaler 2> /dev/null)" = active ] && a=$(start_of) && [ "$a" -gt "$(stat -c %Y "$CFG")" ]
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
  if started_after; then ok "runscaler already started after config.toml was installed: no second restart"; return 0; fi
  systemctl --user restart runscaler
}
again() {
  if [ "$MODE" = up ]; then echo "Run pool-image.sh up again once that is fixed, or pool-image.sh back to go back"
  else echo "Run pool-image.sh back again once that is fixed"; fi
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
ufail() { echo "FAIL $*"; exit 1; }   # the window stops here; its journal stays as it is (open)
ujs() { uj "$@" || ufail "the window journal $J could not record '$1': the window stops before that step (the journal stays open)"; }
uclose() {   # KEY TEXT: the window's last word (`stop NAME: TEXT` or `end TEXT`), `closed`, the journal to windows/ID.
  # Only before the rename: STAGED (this window's) is removed first
  rm -f -- "$STAGED"
  clean "$2"; ujs "$1" "$REPLY"; ujs closed "$(date +%s)"
  mv -f -- "$J" "$WINDOWS/$WID" || ufail "could not close the window journal $J (a rename to $WINDOWS/$WID)"
}
ustop() { uclose stop "$1: $2"; echo "STOP $REPLY"; echo "Nothing changed: config.toml as it was, nothing restarted (the journal: $WINDOWS/$WID)"; exit 1; }
uend() { uclose end "$1"; echo "END $REPLY"; echo "Nothing changed (the journal: $WINDOWS/$WID)"; exit 1; }
unot() {   # TEXT: not now: nothing staged, nothing changed, and no journal is kept
  rm -f -- "$STAGED"; rm -f -- "$J"; rm -rf -- "${WDIR:?}"
  echo "POOL IMAGE NOT NOW ($MODE --unattended): $1"; exit 3
}
uhand() {   # SHA WHAT: A HAND CHANGE found after `rename-start` (the header): `hand-change`, the STOP, the journal OPEN
  ujs hand-change "$1"
  clean "$CFG changed by hand $2. This window restarts nothing on that file: check it; to keep it, run RUNNER_START_CONFIG=$CFG ~/bin/runner-start validate, and only when that passes, systemctl --user restart runscaler at idle. The window journal $J stays open: the updater's next pass ends it"
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
    uhand "$REPLY" "after rename-start, before the rename (sha256 ${REPLY:0:12}…, the window's ${CSHA:0:12}…): nothing was renamed, and runscaler runs on as it was"
  fi
  sha_of "$STAGED"
  if [ "$REPLY" != "$TSHA" ]; then   # config.toml is the window's own pre-window file (just checked): the journal closes
    if [ "$MODE" = up ]; then ustop "check failed" "$STAGED is not the file 03 validated (sha256 ${REPLY:0:12}…, 03 printed ${TSHA:0:12}…): nothing was renamed"; fi
    ustop "ROLLBACK FAILED" "$STAGED changed after its validate (sha256 ${REPLY:0:12}…, the validated ${TSHA:0:12}…): nothing was renamed"
  fi
  mv -f -- "$STAGED" "$CFG" || ufail "could not rename $STAGED over $CFG (it is as it was): the window journal $J stays open"
  RENAMED=$(date +%s); ujs renamed "$RENAMED"
}
urestart() {   # THE RESTART (the header): returns when the new process runs; else exit 1, the journal open
  local o p i
  while [ "$(date +%s)" -le "$RENAMED" ]; do sleep 0.2; done   # past the install's second: the start proves it
  ujs from "$(proc_now)"
  ujs stopping "$(date +%s)"
  utarget "after the rename, before the stop" "runscaler was not stopped, and runs on as it was"
  systemctl --user stop runscaler < /dev/null || ufail "systemctl --user stop runscaler failed (journalctl --user -u runscaler): the window journal $J stays open"
  p=none
  if [ "$(proc_now)" = none ] && o=$(log_pos) && [[ $o =~ ^[0-9]+\ [0-9]+\ [0-9a-f]{64}$ ]] && [ "$(proc_now)" = none ]; then p=$o; fi
  ujs stopped "$p"
  ujs starting "$(date +%s)"
  utarget "while runscaler drained, before its start" "runscaler stays stopped"
  systemctl --user start runscaler < /dev/null || ufail "systemctl --user start runscaler failed (journalctl --user -u runscaler): the window journal $J stays open"
  for i in $(seq 1 120); do   # up to 10 min of the clock
    o=$(proc_now)
    if [ "$o" != none ] && [ "${o#* }" -gt "$RENAMED" ]; then
      # the file it read must still be the TARGET: a change around the start leaves no way to name what it runs
      utarget "around runscaler's start" "the runscaler that started meanwhile may run either file"
      RUNNING=$o; ujs running "$o"; return 0
    fi
    sleep 5
  done
  ufail "no runscaler started after the install within 10 min (journalctl --user -u runscaler): the window journal $J stays open"
}
udone() {   # the target runs: `closed`, the journal to windows/ID
  ujs closed "$(date +%s)"
  mv -f -- "$J" "$WINDOWS/$WID" || ufail "the target runs, but the window journal $J could not be closed (a rename to $WINDOWS/$WID)"
  echo "POOL IMAGE DONE ($MODE --unattended): $(image_of "$CFG") (runscaler $RUNNING, started after the install; the journal: $WINDOWS/$WID)"
  exit 0
}
unattended() {   # the window: its journal, then up or back (each ends with exit)
  export LC_ALL=C
  if [ -e "$J" ] || [ -L "$J" ]; then
    die "an open window journal $J: an earlier window did not close (it was cut off), and the updater's next pass (RECOVER) ends it; nothing changed"
  fi
  install -d -m 700 "$WINDOWS" || die "cannot make $WINDOWS: nothing changed"
  WID=$(date -u +%Y%m%d%H%M%S)-$$; WDIR=$WINDOWS/$WID.d
  mkdir -m 700 "$WDIR" || die "cannot make $WDIR: nothing changed"
  # STAGED, and the STOP of a failure that is no hand change: up's `check failed`, back's `ROLLBACK FAILED`
  if [ "$MODE" = up ]; then STAGED=$R/config.staged.toml UFAIL="check failed"; else STAGED=$R/config.rollback.toml UFAIL="ROLLBACK FAILED"; fi
  ujs window "$WID"
  if [ "$MODE" = up ]; then ujs kind switch; ujs version "$VERSION"; ujs digest "$DIGEST"; un_up; else ujs kind rollback; un_back; fi
}
un_up() {
  local cur new n rc cls out f p m
  ujs process "$(proc_now)"
  cur=$(image_of "$CFG") || ustop "check failed" "config.toml does not name ONE runner image for both sets ($SETS): read $CFG"
  ujs old "$cur"
  sha_of "$CFG"; CSHA=$REPLY; ujs config-sha "$CSHA"
  new=localhost:${REGISTRY_PORT}/${IMAGE_NAME}@$DIGEST
  if [ "$cur" = "$new" ]; then   # nothing to switch, and its rollback ($KEEPP) stays as it is: done only if it RUNS
    p=$(proc_now); m=$(stat -c %Y "$CFG" 2> /dev/null)   # ONE read of the process: the one `running` names
    if [ "$p" != none ] && [[ $m =~ ^[0-9]+$ ]] && [ "${p#* }" -gt "$m" ]; then RUNNING=$p; ujs running "$p"; udone; fi
    uend "config.toml already names $new, but no runscaler that started after its install runs it (runscaler: $p): there is nothing to switch, its rollback ($KEEPP) stays as it is, and this mode restarts nothing"
  fi
  pulls "$cur"; case $? in
    0) ;;
    1) ustop "check failed" "the registry does not serve $cur, the image the pool runs now: its rollback could not start a runner" ;;
    *) ustop "check failed" "the registry ($REG) does not answer, so it cannot be checked that it still serves $cur, the image the pool runs now (the rollback's)" ;;
  esac
  { [ "$(systemctl --user is-active runscaler 2> /dev/null)" = active ] && [ "$(systemctl --user is-enabled runscaler 2> /dev/null)" = enabled ]; } \
    || unot "START STATE: runscaler is not active and enabled"
  started_after || unot "START STATE: config.toml was installed after runscaler started, so it is not proven to be the config that runs"
  disk_ok || ustop DISK "$DISK_WHY"
  if ! tested_jq; then
    [ "$JQV" != "no jq" ] || ustop "untested jq" "no jq answers \`jq --version\` here: install one that $CORE/TESTED_JQ lists for core (Ubuntu 26.04's and 24.04's packages are), and the updater switches at its next pass"
    ustop "untested jq" "jq here prints [$JQV], which is no core row of $CORE/TESTED_JQ: the decision core is not tested with it. Run tests/core with it (JQ=$(command -v jq) python3 -I -B -m unittest discover -s tests/core -t .), and release its row"
  fi
  p=$(pins_bad) && ustop "check failed" "$p is not the reviewed copy (sha256 of PINS): this ~/build is not one release's"
  ujs staged "$STAGED"
  for n in 1 2 3; do
    out=$WDIR/validate-pre-$n.out
    bash "$S03" render "$DIGEST" "$STAGED" > "$out" 2>&1 < /dev/null; rc=$?
    cls=$(sed -n 's/^VALIDATE \([A-Z-]*\)$/\1/p' "$out" | tail -n 1)
    [ -z "$cls" ] || ujs validate "pre $n $cls"
    case $rc:$cls in
      0:PASS) break ;;
      4:API-ONLY) [ "$n" = 3 ] && break; sleep 20 ;;
      *) f=$(grep '^FAIL ' "$out" | tail -n 1)
         ustop "check failed" "03-runscaler.sh render, try $n: VALIDATE ${cls:-none} (exit $rc): ${f#FAIL } (its whole output: $out)" ;;
    esac
  done
  TSHA=$(sed -n 's/^03 STAGED (render): .* sha256 \([0-9a-f]\{64\}\)\. Nothing was installed\.$/\1/p' "$out" | tail -n 1)
  [[ $TSHA =~ ^[0-9a-f]{64}$ ]] || ustop "check failed" "03-runscaler.sh render printed no sha256 of $STAGED ($out)"
  ujs staged-sha "$TSHA"
  { [ "$(image_of "$STAGED")" = "$new" ] && same_but_image "$CFG" "$STAGED"; } \
    || ustop "check failed" "03's render differs from config.toml in more than the runner-image lines (pool.env's numbers are not the ones config.toml runs?): an unattended switch changes the runner version only (plan D3). Compare $POOL with $CFG"
  ujs target "$(targets "$STAGED")"
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
  udone
}
un_back() {
  local cur tgt n rc cls out f
  ujs process "$(proc_now)"
  { [ -f "$KEEPP" ] && [ ! -L "$KEEPP" ]; } || ustop "ROLLBACK FAILED" "there is no rollback config $KEEPP (the backup of the switch to undo): nothing to go back to. Read $CFG and the closed window journals in $WINDOWS"
  tgt=$(image_of "$KEEPP") || ustop "ROLLBACK FAILED" "$KEEPP does not name ONE runner image for both sets: read it"
  # `old` is what it is in up: the image config.toml names at the window's start (the target's is in `target`)
  cur=$(image_of "$CFG") || ustop "ROLLBACK FAILED" "config.toml does not name ONE runner image for both sets ($SETS), so it is no config an updater's switch installed: read $CFG"
  ujs old "$cur"
  sha_of "$CFG"; CSHA=$REPLY; ujs config-sha "$CSHA"
  { [ "$(systemctl --user is-active runscaler 2> /dev/null)" = active ] && [ "$(systemctl --user is-enabled runscaler 2> /dev/null)" = enabled ]; } \
    || uend "rollback pending: CI disabled by a person (runscaler is not active and enabled): nothing restarts"
  started_after || ustop "HAND CHANGE" "config.toml was installed after runscaler started (a hand 03 run, or a window cut before its restart): a pending change, which the rollback would replace unseen. Check $CFG; restart runscaler at idle once it is the config you want"
  if cmp -s -- "$KEEPP" "$CFG"; then   # it already runs the rollback (started after its install, above): done, no restart
    RUNNING=$(proc_now); ujs running "$RUNNING"; udone
  fi
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
  same_but_image "$STAGED" "$CFG" || ustop "ROLLBACK FAILED" "config.toml differs from the rollback $KEEPP in more than the runner-image lines (sets or numbers changed since the switch): the rollback would undo that too. Compare the two"
  for n in 1 2 3; do
    out=$WDIR/validate-pre-$n.out rc=0
    RUNNER_START_CONFIG=$STAGED "$HOME/bin/runner-start" validate > "$out" 2>&1 < /dev/null || rc=$?
    cls=$("$HOME/bin/validate-class" "$rc" "$out" 2> /dev/null) || cls=UNKNOWN
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
  ujs target "$(targets "$STAGED")"
  # THE BACKUP of the config this window replaces (the pre-window config: plan D1, RECOVER step 4), then at once THE
  # RENAME (its checks: config.toml and STAGED as validated) and THE RESTART
  ujs backup "$WDIR/config.toml.backup"
  ubackup "$WDIR/config.toml.backup"
  urename
  urestart
  udone
}

[ "$(id -un)" = ${RS_USER} ] || die "run me as ${RS_USER}"
if [ "$UN" = 1 ]; then   # THE UPDATER LOCK first (fd 9: runner-release.sh's rr_lock), then this script's own
  # shellcheck source=runner-release.sh
  . "$B/setup/runner-release.sh" || die "cannot read $B/setup/runner-release.sh (is this release's linux-docker/ ~/build?): nothing changed"
  # the measuring helpers (proc_now, log_pos, tested_jq, healthz_pair): ONE copy, shared with bin/runner-updater
  # shellcheck source=runner-facts.sh
  . "$B/setup/runner-facts.sh" || die "cannot read $B/setup/runner-facts.sh (is this release's linux-docker/ ~/build?): nothing changed"
  rr_lock || die "the updater lock (the REFUSE line above says why): nothing changed"
fi
# fd 8, never 9: an unattended run holds the updater lock on fd 9, which its parent may have handed it
exec 8>> "$LOCK" || die "cannot open the lock $LOCK; nothing changed"
flock -n 8 || die "another pool-image.sh run holds $LOCK: pid $(head -n 1 "$LOCK" 2> /dev/null) took it, and a child it started (a systemctl restart that still drains) holds it until that child ends. An ssh drop can leave such a run alive. Let it end, or stop it, then run this again; nothing changed"
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

if [ "$MODE" = up ]; then
  # Only `up` reads a build record: `back` and `accept` work from what runs and what was kept.
  p=$(pins_bad) && die "$p is not the reviewed copy (sha256): nothing changed"
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
    elif [ "$(systemctl --user is-active runscaler 2> /dev/null)" = active ] && ! started_after; then
      # No rollback yet, so this keeps config.toml as one: it must be the config runscaler RUNS (a bare 03 run
      # installs a config under the running process).
      die "config.toml was installed after runscaler started (03 ran outside pool-image.sh?), so it is not the config the pool runs, and keeping it would be no rollback. Restart runscaler at idle first (docs/runners.md section 3b), then run up again; nothing changed"
    fi
    holds_pool "$CFG" || die "pool.env does not hold the numbers config.toml runs, and 03 renders pool.env's: they would go live with the image. Compare $POOL with $CFG first; nothing changed"
    pulls "$cur" || echo "WARN the registry does not serve the image the pool runs now ($cur): its rollback could not start a runner"
    put "$CFG" "$KEEPC"; ok "kept $KEEPC (the rollback: $cur)"
    m0=$(stat -c %Y "$CFG")
    echo; echo "== 03-runscaler.sh real $digest (the same sets and numbers, the record's image: it installs with the pool running, and restarts nothing)"
    bash "$S03" real "$digest" < /dev/null || die "03 real failed: config.toml was not changed, so the pool keeps $cur. Read 03's FAIL line above"
    [ "$(image_of "$CFG")" = "$new" ] || die "03 said DONE but config.toml does not run $new: read it; to go back run pool-image.sh back"
    if ! same_but_image "$KEEPC" "$CFG"; then
      put "$KEEPC" "$R/config.real.toml"; put "$KEEPC" "$CFG"
      python3 -c 'import os, sys; t = int(sys.argv[2]); os.utime(sys.argv[1], (t, t))' "$CFG" "$m0" || die "config.toml is the old one again, but its mtime is new: do NOT restart; read $R"
      die "03's config differed from the rollback in more than the image (did pool.env change during the run?): config.toml is back as it was, mtime too, and nothing restarted"
    fi
  else
    ok "config.toml already runs the build record's image: 03 is not run again"
    if ! started_after; then   # a restart is pending: allowed only into a config this script installed
      [ -e "$KEEPC" ] || die "config.toml names the build record's image, but no rollback was kept for the config runscaler runs (03 ran outside pool-image.sh?): nothing restarted"
      if [ "$(systemctl --user is-active runscaler 2> /dev/null)" = active ]; then
        a=$(start_of) || die "cannot read runscaler's start time: nothing restarted"
        [ "$(stat -c %Y "$KEEPC")" -ge "$a" ] || die "the rollback $KEEPC is older than the running process, so it is not the config that process runs (03 ran outside pool-image.sh?): nothing restarted"
      fi
      same_but_image "$KEEPC" "$CFG" || die "config.toml differs from the rollback in more than the image: nothing restarted. Compare $KEEPC with $CFG"
    fi
  fi
else
  [ -e "$KEEPC" ] || die "no $KEEPC: there is no open release to roll back (accept removed it, or up never ran); nothing changed"
  old=$(image_of "$KEEPC") || die "$KEEPC does not name ONE runner image for both sets: read it; nothing changed"
  if cmp -s "$KEEPC" "$CFG"; then
    ok "config.toml already is the rollback ($old)"
  else
    same_but_image "$KEEPC" "$CFG" || die "config.toml differs from the rollback in more than the image (sets or numbers changed since up): a rollback would undo that too. Compare $KEEPC with $CFG; nothing changed"
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

echo; echo "== restart"
if started_after; then
  ok "runscaler started after config.toml was installed ($(systemctl --user show runscaler -p ActiveEnterTimestamp --value)): it runs this image, no restart"
elif [ "$(systemctl --user is-active runscaler)" != active ]; then
  restart || die "systemctl --user restart runscaler failed: read journalctl --user -u runscaler. config.toml runs the $MODE image. $(again)"
else
  quiet=0; for _ in $(seq 1 40); do counts quiet && { quiet=1; break; }; sleep 15; done
  if [ "$quiet" = 0 ]; then
    echo "WAIT jobs still run after 10 min: the restart now waits (up to 60 min) for a moment with no runner between jobs, then drains the running ones (up to 70 min; the small lane takes no new job meanwhile)"
    calm=0; for _ in $(seq 1 240); do counts noidle && { calm=1; break; }; sleep 15; done
    [ "$calm" = 1 ] || echo "WAIT no moment without a runner in its idle phase came in 60 min: restarting anyway — a job this cuts is named at the end"
  fi
  restart || die "systemctl --user restart runscaler failed: read journalctl --user -u runscaler. config.toml runs the $MODE image. $(again)"
fi
for _ in $(seq 1 40); do out=$(ready 2>&1) && break; sleep 15; done
printf '%s\n' "$out"
[ "$(systemctl --user is-active runscaler)" = active ] && [ "$(systemctl --user is-enabled runscaler)" = enabled ] || die "runscaler is not active and enabled: read journalctl --user -u runscaler. config.toml runs the $MODE image. $(again)"
ready > /dev/null || die "the pool is not READY 10 min after the restart: read journalctl --user -u runscaler. config.toml runs the $MODE image. $(again)"
# A JOB A RESTART CUT: the OLD process logs it while a busy runner drains (its listener stays up — minutes before the
# restart returns), the NEW one as it starts — either way AFTER this config.toml was installed, which is where the scan
# starts (so a re-run after an ssh drop still finds it). Each name carries its log time: a repeat on a later re-run
# reads as old.
inst=$(date -u -d "@$(stat -c %Y "$CFG")" +'%Y-%m-%d %H:%M:%S')
cut=$(awk -v s="$inst" '($1 " " $2) >= s && /Job started for unknown runner/ { r = $0; sub(/.*runnerName=/, "", r); print $1 " " $2 " " r }' "$R/runner.log" 2> /dev/null | sort -u | paste -sd ',' -)
[ -z "$cut" ] || echo "WARN a restart since this config was installed cut a job on [$cut] (log time, runner): find it on GitHub (it ends 'lost communication' after 10 min) and re-run it, unless it already was"
echo "POOL IMAGE DONE ($MODE): $(image_of "$CFG")"
[ "$MODE" = back ] || echo "NEXT READY says nothing about the image (no runner has started from it yet): watch the first job on it, then run pool-image.sh accept (it works) or pool-image.sh back (it does not)"
