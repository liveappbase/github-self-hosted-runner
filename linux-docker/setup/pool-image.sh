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
# ~/build), ONCE: a private copy, parsed by one exact pattern of 02-d1.sh's four lines, never sourced. A record that is
# missing, not a plain file, of another form, version or recipe, or whose digest the local registry does not serve:
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
#   rollback's; DIGEST's image already: `end`, nothing to switch, config.toml.prev kept as it is); START STATE (the
#   unit active and enabled, config.toml installed before its start: else not now); DISK (RUN_USER's filesystem, D1's
#   data and the registry, at least DISK_PCT % free: runscaler's min_free); jq (`jq --version` a core row of
#   ~/build/core/TESTED_JQ); the PINS; then PRE-VALIDATE: `03-runscaler.sh render DIGEST
#   STAGED` (STAGED = ~/.config/runner/config.staged.toml; 03 refuses a rejected digest), up to 3 tries 20 s apart:
#   exit 0 (PASS) ends them, exit 4 (API-ONLY) tries again and after the third counts as PASS, anything else is STOP
#   check failed, nothing installed; then D3: STAGED names DIGEST and differs from config.toml in its runner-image
#   lines alone. (2) THE IDLE PAIR: two /healthz reads 3 s apart, decided by ~/build/core/idle.jq over every set
#   config.toml names and every set the reads list (no state: no set is excused, the updater keeps the 24 h). Not idle:
#   STAGED removed, config.toml unchanged, the journal removed, exit 3. (3) At once: config.toml's sha must still be
#   the window's (else STOP HAND CHANGE) and STAGED's the one 03 printed (else STOP check failed); config.toml is kept
#   as config.toml.prev (the rollback); then THE RENAME and THE RESTART, below, unconditionally (no idle check again).
# back --unattended: the rollback to config.toml.prev, the backup of the switch it undoes. The unit not active and
#   enabled: no restart, `end rollback pending: CI disabled by a person` (the updater tries again). config.toml
#   installed after runscaler started: STOP HAND CHANGE (a pending hand edit). config.toml already the backup (and
#   running, so): done, `running` the process that runs it, no restart. No backup, one that does not name ONE
#   image, one that differs from config.toml in more than its runner-image lines, or one whose image the registry
#   does not serve: STOP ROLLBACK FAILED. PRE-VALIDATE of a copy (STAGED = ~/.config/runner/config.rollback.toml) by
#   the ONE VALIDATE RULE (~/bin/runner-start validate, stdout and stderr, ~/bin/validate-class), up to 3 tries 20 s
#   apart: PASS ends them, API-ONLY after the third counts as PASS, NON-API is STOP ROLLBACK FAILED and UNKNOWN is
#   `end` (no STOP: the updater tries again), both before any restart. No idle wait: then THE RENAME and THE RESTART
#   at once (runscaler's drain lets busy runners finish).
# THE RENAME: `rename-start`, STAGED renamed over config.toml, `renamed` (UTC epoch: the INSTALL TIME, plan D1), then a
#   wait until the clock's second is past it. A config.toml whose sha is not STAGED's now is A HAND CHANGE AFTER THE
#   INSTALL: no restart on it, `hand-change`, STOP HAND CHANGE, and the journal stays OPEN for the updater's RECOVER.
# THE RESTART: `from` (the process it stops), `stopping` (the restart's own epoch), `systemctl --user stop runscaler`
#   (the drain), `stopped` (once no runscaler runs, before and after: the log position ~/.config/runner/runner.log's
#   inode, its size, and the sha256 of the 64 bytes before it, or none), the hand-change check again (a change during
#   the drain: no start, runscaler stays stopped), `starting`, `systemctl --user start runscaler`, then up to 10 min
#   until a process that started after `renamed` runs, with config.toml still the TARGET (else the hand-change STOP):
#   `running`. The updater hands the core facts.restart = {from, to: running, stopped} (core/README.md). A kill
#   anywhere after `rename-start` leaves the journal open, and the old file is never put back: the updater's next pass
#   reads config.toml's sha against `config-sha` and `staged-sha`.
# The journal, line by line (V = N.N.N, H = 64 hex, P = an absolute path, I = an image reference, E = UTC epoch):
#   window ID                   ^window [0-9]{14}-[0-9]+$     (UTC yyyymmddHHMMSS-pid)
#   kind switch|rollback        ^kind (switch|rollback)$
#   version V                   (switch)
#   digest sha256:H             (switch)
#   process PID START | none    runscaler at the window's start (MainPID, ActiveEnterTimestamp)
#   old I                       the image config.toml names (switch) | config.toml.prev names (rollback)
#   config-sha H                config.toml at the window's start
#   staged P                    before STAGED is written
#   validate pre N CLASS        ^validate pre [1-3] (PASS|API-ONLY|NON-API|UNKNOWN)$   (windows/ID.d/validate-pre-N.out)
#   staged-sha H                the validated STAGED: the TARGET
#   target SET=I SET=I          the TARGET's lines, in config order
#   idle idle                   (switch) the idle pair said idle
#   backup P                    (switch) before config.toml is kept as config.toml.prev
#   rename-start E              before the rename
#   renamed E                   after it: the install time
#   [hand-change H|unreadable]  config.toml after the install, not the TARGET: the journal stays open
#   from PID START | none       the process the restart stops
#   stopping E                  before `systemctl --user stop`: the restart's own epoch
#   stopped INODE OFFSET H | none
#   starting E                  before `systemctl --user start`
#   running PID START           the new process, started after `renamed`
#   stop NAME: TEXT             a STOP (check failed | DISK | untested jq | HAND CHANGE | ROLLBACK FAILED)
#   end TEXT                    the window ended with no STOP (the updater tries again later)
#   closed E                    before the journal is renamed to windows/ID
# Exit codes of the unattended modes (the updater's interface; it reads the rest from the journal and the files):
#   0  done: the target runs (a process started after `renamed`); the journal closed
#   1  not done: the closed journal's `stop` or `end` line says why; or the journal is still OPEN (a step after
#      `rename-start` failed or was cut, or a HAND CHANGE AFTER THE INSTALL): the updater's RECOVER ends it; or a
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
PINS="$S03=cd3ce73a6b888e2ea65c0a9f340cbe443aad323595eb11af4cdca3a4372191a2
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
recipe_of() {   # recipe_of DIR: 02-d1.sh's RECIPE of DIR (image/): the sha256 of its plain files' `<sha256>  <name>`
  # lines, names in byte order (02-d1.sh hashes its copies of the same files); rc 1 when DIR holds anything else
  local names n h lines=
  { names=$(LC_ALL=C ls -A "$1") && [ -n "$names" ]; } || return 1
  while IFS= read -r n; do
    { [ -f "$1/$n" ] && [ ! -L "$1/$n" ]; } || return 1
    h=$(sha256sum < "$1/$n") || return 1
    lines+="${h%% *}  $n"$'\n'
  done <<< "$names"
  h=$(printf '%s' "$lines" | sha256sum) || return 1
  [[ ${h%% *} =~ ^[0-9a-f]{64}$ ]] && echo "${h%% *}"
}
record_digest() {   # record_digest VERSION RECIPE: digest = the one RUN_USER's build record of VERSION and RECIPE
  # names. The record is read ONCE (a private copy, then only the copy) and must be exactly 02-d1.sh's four lines; else
  # rc 1 and why = what is wrong (both are set here, not printed: a $(…) would lose why)
  local f=$BUILDS/$1-$2 t size nonul text
  digest=
  local re=$'^format 1\nversion ([0-9]+\\.[0-9]+\\.[0-9]+)\ndigest (sha256:[0-9a-f]{64})\nrecipe ([0-9a-f]{64})\n$'
  why="there is none"
  [ -e "$f" ] || [ -L "$f" ] || return 1
  why="it is not a plain file"
  { [ -f "$f" ] && [ ! -L "$f" ]; } || return 1
  why="it cannot be read"
  t=$(mktemp "$R/.record.XXXXXX") || return 1
  if head -c 1025 -- "$f" > "$t" < /dev/null; then
    size=$(wc -c < "$t"); nonul=$(tr -d '\000' < "$t" | wc -c); text=$(cat -- "$t"; echo .); text=${text%.}
  fi
  rm -f -- "$t"
  [ -n "${size-}" ] || return 1
  why="it is not 02-d1.sh's four lines (format 1, version, digest, recipe)"
  { [ "$size" -le 1024 ] && [ "$size" = "$nonul" ] && [[ $text =~ $re ]]; } || return 1
  why="it names version ${BASH_REMATCH[1]}"
  [ "${BASH_REMATCH[1]}" = "$1" ] || return 1
  why="it names another recipe"
  [ "${BASH_REMATCH[3]}" = "$2" ] || return 1
  digest=${BASH_REMATCH[2]}
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
uhand() {   # SHA WHEN [NOTE]: A HAND CHANGE AFTER THE INSTALL (the header): nothing restarts on that file
  ujs hand-change "$1"
  clean "$CFG changed by hand $2 (sha256 ${1:0:12}…, not the ${TSHA:0:12}… this window validated and installed): nothing restarts on it${3-}. Check the file; to keep it, run RUNNER_START_CONFIG=$CFG ~/bin/runner-start validate, and only when that passes, systemctl --user restart runscaler at idle. The window journal $J stays open: the updater's next pass ends it"
  ujs stop "HAND CHANGE: $REPLY"; echo "STOP HAND CHANGE: $REPLY"; exit 1
}
proc_now() {   # runscaler as systemd reports it, in ONE read: "PID START" (MainPID, ActiveEnterTimestamp) when active, else none
  local o k v s= p= a=
  o=$(systemctl --user show runscaler -p ActiveState -p MainPID -p ActiveEnterTimestamp --timestamp=unix 2> /dev/null < /dev/null) \
    || { echo none; return 0; }
  while IFS='=' read -r k v; do case $k in ActiveState) s=$v ;; MainPID) p=$v ;; ActiveEnterTimestamp) a=${v#@} ;; esac; done <<< "$o"
  if [ "$s" = active ] && [[ $p =~ ^[1-9][0-9]*$ ]] && [[ $a =~ ^[0-9]+$ ]]; then echo "$p $a"; else echo none; fi
}
log_pos() {   # runscaler's log position now: "INODE OFFSET SHA" (inode and size from ONE open; the sha256 of the 64 bytes
  # before OFFSET, or of all of them when fewer), the way the updater's pass captures one; rc 1 when it cannot be read
  python3 -I -c '
import hashlib, os, sys
with open(sys.argv[1], "rb") as f:
    st = os.fstat(f.fileno())
    n = st.st_size
    f.seek(max(0, n - 64))
    b = f.read(min(64, n))
if len(b) != min(64, n):
    sys.exit(1)
print("%d %d %s" % (st.st_ino, n, hashlib.sha256(b).hexdigest()))' "$R/runner.log" 2> /dev/null < /dev/null
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
tested_jq() {   # `jq --version` is a core row of ~/build/core/TESTED_JQ (the core's own list); JQV = what it printed
  JQV=$(jq --version 2> /dev/null < /dev/null) || JQV="no jq"
  [[ $JQV =~ ^jq-[A-Za-z0-9.+-]+$ ]] || return 1
  awk -v v="$JQV" '$1 == v && $2 ~ /(^|,)core(,|$)/ { f = 1 } END { exit !f }' "$CORE/TESTED_JQ" 2> /dev/null
}
uidle() {   # THE IDLE PAIR (the header): 0 idle; 1 not idle; 2 the core could not decide. IDLE_WHY = the core's reason
  local h=$WDIR/idle-healthz.json f=$WDIR/idle-facts.json s=$WDIR/idle-state.json o=$WDIR/idle.json j i
  : > "$h" && : > "$s" || { IDLE_WHY="cannot write $WDIR"; return 2; }
  # shellcheck disable=SC2046
  jq -n -c '{format: 1, sets: $ARGS.positional}' --args $(sets_of "$CFG") > "$f" 2> /dev/null < /dev/null \
    || { IDLE_WHY="cannot write $f"; return 2; }
  for i in 1 2; do
    [ "$i" = 1 ] || sleep 3   # between the reads: the last read is followed by the rename and the restart, at once
    j=$(curl -fs -m 5 "http://127.0.0.1:${RS_HEALTH_PORT}/healthz" < /dev/null) && printf '%s\n' "$j" >> "$h"
  done
  jq -n -L "$CORE/lib" -f "$CORE/idle.jq" --slurpfile state "$s" --slurpfile facts "$f" --slurpfile healthz "$h" \
    --arg now "$(date +%s)" > "$o" 2> "$o.err" < /dev/null || { IDLE_WHY=$(head -n 1 "$o.err"); return 2; }
  IDLE_WHY=$(jq -r '.reason' "$o" 2> /dev/null) || { IDLE_WHY="no reason in $o"; return 2; }
  case $(jq -r '.verdict' "$o" 2> /dev/null) in idle) return 0 ;; not-idle) return 1 ;; *) return 2 ;; esac
}
urename() {   # THE RENAME (the header)
  ujs rename-start "$(date +%s)"
  mv -f -- "$STAGED" "$CFG" || ufail "could not rename $STAGED over $CFG (it is as it was): the window journal $J stays open"
  RENAMED=$(date +%s); ujs renamed "$RENAMED"
}
urestart() {   # THE RESTART (the header): returns when the new process runs; else exit 1, the journal open
  local o p i
  while [ "$(date +%s)" -le "$RENAMED" ]; do sleep 0.2; done   # past the install's second: the start proves it
  sha_of "$CFG"; [ "$REPLY" = "$TSHA" ] || uhand "$REPLY" "after the rename, before the restart"
  ujs from "$(proc_now)"
  ujs stopping "$(date +%s)"
  systemctl --user stop runscaler < /dev/null || ufail "systemctl --user stop runscaler failed (journalctl --user -u runscaler): the window journal $J stays open"
  p=none
  if [ "$(proc_now)" = none ] && o=$(log_pos) && [[ $o =~ ^[0-9]+\ [0-9]+\ [0-9a-f]{64}$ ]] && [ "$(proc_now)" = none ]; then p=$o; fi
  ujs stopped "$p"
  sha_of "$CFG"; [ "$REPLY" = "$TSHA" ] || uhand "$REPLY" "while runscaler drained" ", and runscaler stays stopped"
  ujs starting "$(date +%s)"
  systemctl --user start runscaler < /dev/null || ufail "systemctl --user start runscaler failed (journalctl --user -u runscaler): the window journal $J stays open"
  for i in $(seq 1 120); do   # up to 10 min of the clock
    o=$(proc_now)
    if [ "$o" != none ] && [ "${o#* }" -gt "$RENAMED" ]; then
      # the file it read must still be the TARGET: a change around the start leaves no way to name what it runs
      sha_of "$CFG"; [ "$REPLY" = "$TSHA" ] || uhand "$REPLY" "around runscaler's start" ", and the runscaler that started meanwhile may run either file"
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
  if [ "$MODE" = up ]; then STAGED=$R/config.staged.toml; else STAGED=$R/config.rollback.toml; fi
  ujs window "$WID"
  if [ "$MODE" = up ]; then ujs kind switch; ujs version "$VERSION"; ujs digest "$DIGEST"; un_up; else ujs kind rollback; un_back; fi
}
un_up() {
  local cur new n rc cls out f p
  ujs process "$(proc_now)"
  cur=$(image_of "$CFG") || ustop "check failed" "config.toml does not name ONE runner image for both sets ($SETS): read $CFG"
  ujs old "$cur"
  sha_of "$CFG"; CSHA=$REPLY; ujs config-sha "$CSHA"
  new=localhost:${REGISTRY_PORT}/${IMAGE_NAME}@$DIGEST
  [ "$cur" != "$new" ] || uend "config.toml already runs $new: there is nothing to switch, and its rollback ($KEEPP) stays as it is"
  pulls "$cur"; case $? in
    0) ;;
    1) ustop "check failed" "the registry does not serve $cur, the image the pool runs now: its rollback could not start a runner" ;;
    *) ustop "check failed" "the registry ($REG) does not answer, so it cannot be checked that it still serves $cur, the image the pool runs now (the rollback's)" ;;
  esac
  { [ "$(systemctl --user is-active runscaler 2> /dev/null)" = active ] && [ "$(systemctl --user is-enabled runscaler 2> /dev/null)" = enabled ]; } \
    || unot "START STATE: runscaler is not active and enabled"
  started_after || unot "START STATE: config.toml was installed after runscaler started, so it is not proven to be the config that runs"
  disk_ok || ustop DISK "$DISK_WHY"
  tested_jq || ustop "untested jq" "jq here prints [$JQV], which is no core row of $CORE/TESTED_JQ: the decision core is not tested with it. Run tests/core with it (JQ=$(command -v jq) python3 -I -B -m unittest discover -s tests/core -t .), and release its row"
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
  # at once (the header, step 3)
  sha_of "$CFG"; [ "$REPLY" = "$CSHA" ] || ustop "HAND CHANGE" "config.toml changed during the window (sha256 ${REPLY:0:12}…, the window's ${CSHA:0:12}…): nothing was renamed or restarted. Check it; a hand change belongs outside the updater's windows"
  sha_of "$STAGED"; [ "$REPLY" = "$TSHA" ] || ustop "check failed" "$STAGED is not the file 03 validated (sha256 ${REPLY:0:12}…, 03 printed ${TSHA:0:12}…): nothing was renamed"
  ujs backup "$KEEPP"
  put "$CFG" "$KEEPP"
  urename
  urestart
  udone
}
un_back() {
  local old n rc cls out f
  ujs process "$(proc_now)"
  { [ -f "$KEEPP" ] && [ ! -L "$KEEPP" ]; } || ustop "ROLLBACK FAILED" "there is no rollback config $KEEPP (the backup of the switch to undo): nothing to go back to. Read $CFG and the closed window journals in $WINDOWS"
  old=$(image_of "$KEEPP") || ustop "ROLLBACK FAILED" "$KEEPP does not name ONE runner image for both sets: read it"
  ujs old "$old"
  sha_of "$CFG"; CSHA=$REPLY; ujs config-sha "$CSHA"
  { [ "$(systemctl --user is-active runscaler 2> /dev/null)" = active ] && [ "$(systemctl --user is-enabled runscaler 2> /dev/null)" = enabled ]; } \
    || uend "rollback pending: CI disabled by a person (runscaler is not active and enabled): nothing restarts"
  started_after || ustop "HAND CHANGE" "config.toml was installed after runscaler started (a hand 03 run?): a pending hand edit, which the rollback would replace unseen. Check $CFG; restart runscaler at idle once it is the config you want"
  same_but_image "$KEEPP" "$CFG" || ustop "ROLLBACK FAILED" "config.toml differs from the rollback $KEEPP in more than the runner-image lines (sets or numbers changed since the switch): the rollback would undo that too. Compare the two"
  if cmp -s -- "$KEEPP" "$CFG"; then   # it already runs the rollback (started after its install, above): done, no restart
    RUNNING=$(proc_now); ujs running "$RUNNING"; udone
  fi
  pulls "$old"; case $? in
    0) ;;
    1) ustop "ROLLBACK FAILED" "the registry no longer serves the rollback's image $old: a runner of it could not start" ;;
    *) ustop "ROLLBACK FAILED" "the registry ($REG) does not answer, so no runner of either image can start: bring D1's registry back first (02-d1.sh as ${RUN_USER})" ;;
  esac
  ujs staged "$STAGED"
  { cp -- "$KEEPP" "$STAGED.tmp" && chmod 600 "$STAGED.tmp" && mv -f -- "$STAGED.tmp" "$STAGED"; } \
    || { rm -f -- "$STAGED.tmp"; ustop "ROLLBACK FAILED" "could not copy $KEEPP to $STAGED"; }
  sha_of "$STAGED"; TSHA=$REPLY
  sha_of "$KEEPP"; [ "$REPLY" = "$TSHA" ] || ustop "ROLLBACK FAILED" "the copy $STAGED is not $KEEPP"
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
  sha_of "$CFG"; [ "$REPLY" = "$CSHA" ] || ustop "HAND CHANGE" "config.toml changed during the rollback window (sha256 ${REPLY:0:12}…, the window's ${CSHA:0:12}…): nothing was renamed or restarted"
  sha_of "$STAGED"; [ "$REPLY" = "$TSHA" ] || ustop "ROLLBACK FAILED" "$STAGED changed after its validate: nothing was renamed"
  urename
  urestart
  udone
}

[ "$(id -un)" = ${RS_USER} ] || die "run me as ${RS_USER}"
if [ "$UN" = 1 ]; then   # THE UPDATER LOCK first (fd 9: runner-release.sh's rr_lock), then this script's own
  # shellcheck source=runner-release.sh
  . "$B/setup/runner-release.sh" || die "cannot read $B/setup/runner-release.sh (is this release's linux-docker/ ~/build?): nothing changed"
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
  recipe=$(recipe_of "$B/image") || die "$B/image is not this release's plain image/ files, so its recipe cannot be read: nothing changed"
  record_digest "$VERSION" "$recipe" || die "no usable build record of runner $VERSION for this release's image (recipe ${recipe:0:12}…, $BUILDS/$VERSION-$recipe): $why. To make it, $fix; nothing changed"
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
