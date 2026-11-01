#!/usr/bin/env bash
# pool-image.sh — a RUNNER RELEASE, the POOL half: AS RS_USER, after 02-d1.sh (as RUN_USER) built the new runner image
# and wrote its digest to /home/RUN_USER/run/image.ref. Needs this release's linux-docker/ as ~/build.
#   up:     ssh -o ServerAliveInterval=60 RS_USER@<host> 'bash -s -- up 2.338.2' < linux-docker/setup/pool-image.sh
#   back:   the same line with `back` — the rollback to the image the pool ran before this release's `up`.
#   accept: the same line with `accept` — ends the release once a job passed on the new image: the kept rollback is
#           removed, so the NEXT release's `up` keeps this config. Until then an `up` to another image refuses. It
#           closes the release whose image config.toml RUNS, whatever image.ref says by then (a rebuild or the next
#           release's 02 may have moved it).
# THE ROLLBACK FILE (config.toml.pre-image) belongs to ONE release: `up` writes it only when it is absent or names the
# image config.toml runs now (image.ref moves, so "differs from image.ref" would keep an unproven config).
# up:   refuses unless pool.env holds the numbers config.toml runs (03 renders from pool.env, so others would go live
#       with the image) and the new image's runner is RUNNER_VERSION; keeps the rollback; 03 real (the same sets and
#       numbers, the new image: it installs with the pool running and restarts nothing; if it fails, config.toml is
#       unchanged); if config.toml then differs from the rollback in more than the image, the rollback goes back with
#       config.toml's old mtime and nothing restarts. config.toml already on image.ref with a restart pending (a run cut
#       off before its restart, or a bare 03 run) restarts only when the rollback was kept while the running process ran.
# back: puts config.toml.pre-image back with NO 03 (no build, no GitHub), only when the image is ALL it changes and the
#       registry still serves the old digest (runscaler pulls it at every runner start, so a dead registry stops both
#       images alike). image.ref keeps the new digest, so a later 03 renders it again: fix the image (or put the old
#       Dockerfile back and run 02-d1.sh) first.
# ONE RUN AT A TIME: a lock in ~/.config/runner. An ssh drop with no pty can leave the old run alive; a new one then
# refuses and names its pid.
# Then, up and back: the restart. restart() re-reads the start time just before it restarts, so it never restarts a
# process that already runs this config.toml. If runscaler already started after config.toml was installed, no
# restart; else wait up to 10 min for both sets to be quiet (no runner, no job), then up to 60 min more for a moment
# with no runner in its idle phase, then restart (SIGTERM = drain: a running job finishes first, up to 70 min) -> READY
# within 10 min -> name any job a restart cut.
# PINS: what 03 runs, and what it installs from ~/build before it validates, by sha256. tools/release-check refuses a
# pinned file that changed without its PIN.
set -uo pipefail
# THE HOST CONFIG: every value of this host (users, ports, addresses, names) is in HOST_CONF, root's file, never in
# this script; linux-docker/host.conf.example names each key. Absent, not root's, writable by another user, a line that
# is not KEY=value, a key twice or a key missing: REFUSE on stderr, exit 1, before anything else runs.
HOST_CONF=/etc/liveapp-ci/host.conf
host_conf() {   # host_conf SCRIPT KEY...: each named KEY's line in HOST_CONF sets that variable
  local me=$1 l k o seen=" "; shift
  o=$(stat -c '%a %U' "$HOST_CONF" 2>/dev/null) || { echo "$me: REFUSE no host config $HOST_CONF (linux-docker/README.md)" >&2; exit 1; }
  [[ $o =~ ^[0-7][0145][0145]\ root$ ]] || { echo "$me: REFUSE $HOST_CONF must be root's and writable by root only: [$o]" >&2; exit 1; }
  while IFS= read -r l || [ -n "$l" ]; do
    case $l in ''|'#'*) continue ;; esac
    [[ $l =~ ^([A-Z][A-Z0-9_]*)=([A-Za-z0-9][A-Za-z0-9._:/-]*)$ ]] || { echo "$me: REFUSE $HOST_CONF: want KEY=value, got [$l]" >&2; exit 1; }
    k=${BASH_REMATCH[1]}; [[ " $* " == *" $k "* ]] || continue
    [[ $seen != *" $k "* ]] || { echo "$me: REFUSE $HOST_CONF names $k twice" >&2; exit 1; }
    printf -v "$k" %s "${BASH_REMATCH[2]}"; seen="$seen$k "
  done < "$HOST_CONF"
  for k in "$@"; do [[ $seen == *" $k "* ]] || { echo "$me: REFUSE $HOST_CONF lacks $k (linux-docker/host.conf.example)" >&2; exit 1; }; done
}
host_conf pool-image.sh RUN_USER RS_USER REGISTRY_PORT RS_HEALTH_PORT IMAGE_NAME MAIN_SET SMALL_SET
MODE=${1-}; VERSION=${2-}
usage() { echo "usage: pool-image.sh up RUNNER_VERSION (for example 2.338.2) | back | accept"; exit 2; }
case $MODE in
  up) [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || usage ;;
  back|accept) [ -z "$VERSION" ] || usage ;;
  *) usage ;;
esac
R=$HOME/.config/runner; CFG=$R/config.toml; KEEPC=$R/config.toml.pre-image; POOL=$R/pool.env; LOCK=$R/pool-image.lock
REF=/home/${RUN_USER}/run/image.ref; REG=http://127.0.0.1:${REGISTRY_PORT}; D1=unix:///home/${RUN_USER}/run/docker.sock; B=$HOME/build
S03=$B/setup/03-runscaler.sh
# What 03 runs, and what it installs from ~/build before it validates, by sha256 (the header says why).
PINS="$S03=6d3edcbc5be39df84d1547b973df79ff332a39ac894d6c3f94928cc7506a27b4
$B/bin/runner-start=93a6651fb810dd1906e876ab8124a8e07f9e92405bded6a1e77cfc34b7b65864
$B/bin/pool-ready=8c07e682d7c94a1ee102f6b6f6372b24ce967cf37294227a12889be0d0768947
$B/config/runscaler.service=b84e46b1b9d4391258a6a6161b55f6c96fe625aec4eec8251c0f8dd562c530be"
SETS="${MAIN_SET} ${SMALL_SET}"
IMGRE='^localhost:'"${REGISTRY_PORT}"'/'"${IMAGE_NAME}"'@sha256:[0-9a-f]{64}$'   # 03's own rule for image.ref
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

[ "$(id -un)" = ${RS_USER} ] || die "run me as ${RS_USER}"
exec 9>> "$LOCK" || die "cannot open the lock $LOCK; nothing changed"
flock -n 9 || die "another pool-image.sh run holds $LOCK: pid $(head -n 1 "$LOCK" 2> /dev/null) took it, and a child it started (a systemctl restart that still drains) holds it until that child ends. An ssh drop can leave such a run alive. Let it end, or stop it, then run this again; nothing changed"
printf '%s\n' "$$" > "$LOCK"
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
  # Only `up` reads image.ref: `back` and `accept` work from what runs and what was kept.
  new=$(cat "$REF" 2> /dev/null) || die "no $REF: run 02-d1.sh as ${RUN_USER} first; nothing changed"
  [[ $new =~ $IMGRE ]] || die "$REF is not one strict digest reference: [$new]; nothing changed"
  while IFS= read -r p; do
    [ "$(sha256sum "${p%=*}" 2> /dev/null | cut -d' ' -f1)" = "${p##*=}" ] || die "${p%=*} is not the reviewed copy (sha256): nothing changed"
  done <<< "$PINS"
  pulls "$new"; case $? in 0) ;; 1) die "the registry does not hold $new (the image runscaler would pull): nothing changed" ;; *) die "the registry ($REG) does not answer: nothing changed" ;; esac
  # The runner's version, from the image itself: its labels do not carry it (measured). No network, bounded. Every
  # child here reads /dev/null: the script itself arrives on stdin (`bash -s`), and a child that reads it eats the rest.
  # The image sets ACTIONS_RUNNER_PRINT_LOG_TO_STDOUT=1, so the runner's log comes too: the version is the one line
  # that is a bare version number (two such lines = no match = refused).
  out=$(DOCKER_HOST=$D1 docker run --rm --network none --memory 512m --cpus 1 "$new" ./config.sh --version < /dev/null) \
    || die "could not run $new to read its runner version (its error is above): nothing changed"
  v=$(grep -xE '[0-9]+\.[0-9]+\.[0-9]+' <<< "$out")
  [ "$v" = "$VERSION" ] || die "the runner in $new is [$v], not $VERSION: 02-d1.sh built from another Dockerfile? nothing changed"
  ok "image.ref: $new (the registry serves it; runner $v)"
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
    echo; echo "== 03-runscaler.sh real (the same sets and numbers, the new image: it installs with the pool running, and restarts nothing)"
    bash "$S03" real < /dev/null || die "03 real failed: config.toml was not changed, so the pool keeps $cur. Read 03's FAIL line above"
    [ "$(image_of "$CFG")" = "$new" ] || die "03 said DONE but config.toml does not run $new: read it; to go back run pool-image.sh back"
    if ! same_but_image "$KEEPC" "$CFG"; then
      put "$KEEPC" "$R/config.real.toml"; put "$KEEPC" "$CFG"
      python3 -c 'import os, sys; t = int(sys.argv[2]); os.utime(sys.argv[1], (t, t))' "$CFG" "$m0" || die "config.toml is the old one again, but its mtime is new: do NOT restart; read $R"
      die "03's config differed from the rollback in more than the image (did pool.env change during the run?): config.toml is back as it was, mtime too, and nothing restarted"
    fi
  else
    ok "config.toml already runs image.ref: 03 is not run again"
    if ! started_after; then   # a restart is pending: allowed only into a config this script installed
      [ -e "$KEEPC" ] || die "config.toml names image.ref, but no rollback was kept for the config runscaler runs (03 ran outside pool-image.sh?): nothing restarted"
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
    echo "NOTE image.ref still names $(cat "$REF" 2> /dev/null): a later 03 real renders that image again"
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
