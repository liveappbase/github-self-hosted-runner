#!/usr/bin/env bash
# 03-runscaler.sh — runscaler as RS_USER: the binary (both checksums), runner-start, pool-ready, validate-class, the user
# unit, and ONE named config. Runs AS RS_USER, never root (linux-docker/README.md; needs this release's linux-docker/ as
# ~/build):
#   ssh RS_USER@<host> 'bash -s -- MODE' < linux-docker/setup/03-runscaler.sh
# The set names, groups and labels are the host config's (host.conf.example):
#   MODE real [DIGEST] two sets: MAIN_SET    (group GROUP, labels self-hosted + MAIN_LABEL) and the small lane
#                      SMALL_SET             (same group, labels self-hosted + SMALL_LABEL, 1 runner, its own
#                      cpu/memory: SMALL_CPU/SMALL_MEMORY)
#   MODE render DIGEST STAGED   real's sets, for an image switch of the updater (below); it installs nothing
# (The one-off modes `probe` and `c1` of the first install are cut, with the five host-config keys only they read.)
# THE IMAGE: DIGEST (sha256:<64 hex>) is an image of the local registry. With none, the image the installed config.toml
# RUNS NOW (image_of, pool-image.sh's own function), so a `03 real` after a change of pool.env's numbers, or after a
# release that changes an installed file, keeps the running image; RUN_USER's ~/run/image.ref (the full 02-d1.sh run's)
# is read only when there is no config.toml (a fresh host). A REJECTED image is refused in every mode, before anything.
# REJECTED: ~/.local/state/runner-updater/rejected (the folder of the updater lock, runner-release.sh's RR_LOCK), which
# the updater writes: one `sha256:<64 hex>` per line. No file, or an empty one, rejects nothing; any other content (a
# blank line, a CR, other text, not a regular file) REFUSES: a list that cannot be read is never read as "none".
# real: it installs the files above from ~/build, renders ~/.config/runner/config.real.new.toml (a .toml NAME:
# runscaler takes the config type from the extension) and runs the refusal controls on throwaway copies. Only when
# the token is in does it validate the render with runscaler's own strict `validate` and THEN install it as
# config.real.toml and config.toml. No token: no CONFIG is installed ("03 STOPPED", exit 3; the binary, runner-start,
# pool-ready, validate-class and the unit are). A validate that is not PASS: config.toml is not touched. It does not
# start or restart runscaler (a running pool is fine: validate takes no lock). A config that registers a NEW set is
# rendered only with the unit stopped (a crash restart must not register it before the operator's go).
# render DIGEST STAGED: renders real's sets with that image into STAGED (a .toml file in ~/.config/runner, other than
# config.toml and config.real.toml) and validates it. It INSTALLS NOTHING and runs none of real's refusal controls: it
# refuses when a file real installs is not, as installed, the one this release pins (each one's PIN is read from ONE
# copy, the PINS of ~/build/setup/pool-image.sh; runscaler's binary is BIN_SHA), when the render's sets are not
# config.toml's (an image switch never changes them), and with no token. Exit: 0 PASS (STAGED is the validated render);
# 4 API-ONLY (STAGED kept: the window's tries decide, plan D5); 1 anything else, with NOTHING staged (a STAGED from
# before is removed too, also when the host config refuses: the cleanup is set before it is read); 2 usage.
# THE VALIDATE: `runner-start validate`, its stdout AND stderr (runner-start refuses on stderr), is classified by the ONE
# VALIDATE RULE (~/bin/validate-class): it prints the whole output, then `VALIDATE <class>`. real installs only on PASS.
# NUMBERS: ~/.config/runner/pool.env (0600; CONCURRENT CPU MEMORY MAX SMALL_CPU SMALL_MEMORY, whole numbers), written
# once the pool's size is measured. real and render REFUSE without it. An env var of the same name that disagrees with
# what is used is refused: change the record, not the call.
# THE ARGUMENTS, and the cleanup, come before the host config (and so before `set -e`): a usage error changes nothing,
# and from here on nothing is staged unless this run stages it: at any exit but a render's PASS or API-ONLY, STAGED (one
# from before too) is removed, also when the host config refuses.
R=$HOME/.config/runner
usage() { echo "usage: 03-runscaler.sh real [DIGEST] | render DIGEST STAGED (DIGEST: sha256:<64 hex>; STAGED: a .toml file in $R, not config.toml or config.MODE.toml)"; exit 2; }
MODE=${1-} DIGEST= STAGED=
case $MODE:$# in
  real:1) ;;
  real:2) DIGEST=$2 ;;
  render:3) DIGEST=$2 STAGED=$3
    case ${STAGED##*/} in config.toml|config.probe.toml|config.real.toml|config.c1.toml) usage ;; esac
    [[ ${STAGED%/*} == "$R" && ${STAGED##*/} =~ ^[A-Za-z0-9][A-Za-z0-9._-]*\.toml$ ]] || usage ;;
  *) usage ;;
esac
[ -z "$DIGEST" ] || [[ $DIGEST =~ ^sha256:[0-9a-f]{64}$ ]] || usage
tmp=$(mktemp -d) || exit 1
kept=0
trap 'rm -rf "${tmp:?}"; [ -z "$STAGED" ] || [ "$kept" = 1 ] || rm -f -- "$STAGED"' EXIT
set -euo pipefail
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
host_conf 03-runscaler.sh RUN_USER RS_USER REGISTRY_PORT RS_HEALTH_PORT IMAGE_NAME ORG_URL TOKEN_ENV TOKEN_FILE GROUP MAIN_SET MAIN_LABEL SMALL_SET SMALL_LABEL
cd ~
B=$HOME/build; POOL=$R/pool.env
D1=unix:///home/${RUN_USER}/run/docker.sock
TGZ_SHA=f0e024d181954fb6d29d254b43907152be0f5fa8f91b3e054e9e199be29ec25f
BIN_SHA=d9d1e5779ad5c7220dddcba1a2464f50f680f9d8102f784da63f15a052523948
KEYS="CONCURRENT CPU MEMORY MAX SMALL_CPU SMALL_MEMORY"
PIMG=$B/setup/pool-image.sh   # its PINS are the ONE copy of the pins: render compares the installed files with them
REJECTED=$HOME/.local/state/runner-updater/rejected
IMGRE='^localhost:'"${REGISTRY_PORT}"'/'"${IMAGE_NAME}"'@sha256:[0-9a-f]{64}$'   # the image reference a config names
# What real installs from ~/build: SOURCE (in ~/build) DEST (in $HOME) MODE. render compares each DEST with SOURCE's PIN.
INSTALLS="bin/runner-start bin/runner-start 755
bin/pool-ready bin/pool-ready 755
bin/validate-class bin/validate-class 755
config/runscaler.service .config/systemd/user/runscaler.service 644"
say() { printf '\n== %s\n' "$*"; }
ok() { echo "OK   $*"; }
die() { echo "FAIL $*"; exit 1; }
sha() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || die "sha256 $1"; }
image_of() {   # image_of FILE: the ONE runner-image both sets name; empty (and rc 1) when the sets disagree or name none
  local imgs; imgs=$(sed -n 's/^runner-image = "\(.*\)"$/\1/p' "$1" 2> /dev/null | sort -u)
  [ "$(grep -c '^runner-image = ' "$1" 2> /dev/null)" = 2 ] && [ "$(printf '%s\n' "$imgs" | grep -c .)" = 1 ] \
    && [[ $imgs =~ $IMGRE ]] && echo "$imgs"
}
rejected() {   # rejected DIGEST: 0 = REJECTED lists it; 1 = it does not (no file, or an empty one). Any other content
  # REFUSES here (the header). The file is read ONCE, into a private copy.
  local n rc=0
  [ -e "$REJECTED" ] || [ -L "$REJECTED" ] || return 1
  { [ -f "$REJECTED" ] && [ -r "$REJECTED" ] && cat -- "$REJECTED" > "$tmp/rejected"; } \
    || die "cannot read the rejected digests $REJECTED (not a readable file): nothing changed"
  n=$(LC_ALL=C grep -c -v -x -E 'sha256:[0-9a-f]{64}' "$tmp/rejected") || rc=$?
  case $rc in
    0) die "$REJECTED holds $n line(s) that are not sha256:<64 hex>: the rejected digests cannot be read, and are never read as none; nothing changed" ;;
    1) ;;
    *) die "cannot read the rejected digests $REJECTED: nothing changed" ;;
  esac
  rc=0; n=$(LC_ALL=C grep -c -x -F -- "$1" "$tmp/rejected") || rc=$?
  case $rc in 0) return 0 ;; 1) return 1 ;; *) die "cannot read the rejected digests $REJECTED: nothing changed" ;; esac
}
read_pins() {   # the PINS block of pool-image.sh, as data: one "PATH HEX" line per `$B/PATH=HEX` line (its `$S03=HEX`
  # line pins this file); rc 1 when the block is absent, unclosed, or holds a line of another shape
  local l inb=0 end=0 out= re_b='^\$B/([A-Za-z0-9._/-]+)=([0-9a-f]{64})$' re_s='^\$S03=[0-9a-f]{64}$'
  { [ -f "$PIMG" ] && [ -r "$PIMG" ]; } || return 1
  while IFS= read -r l || [ -n "$l" ]; do
    if [ "$inb" = 0 ]; then [[ $l == 'PINS="'* ]] || continue; inb=1 l=${l#PINS=\"}; fi
    [[ $l != *\" ]] || { end=1; l=${l%\"}; }
    if [[ $l =~ $re_b ]]; then out+="${BASH_REMATCH[1]} ${BASH_REMATCH[2]}"$'\n'
    elif ! [[ $l =~ $re_s ]]; then return 1; fi
    [ "$end" = 0 ] || break
  done < "$PIMG"
  { [ "$end" = 1 ] && [ -n "$out" ]; } || return 1
  printf '%s' "$out"
}
say "the numbers"
[ -e "$POOL" ] || die "no $POOL: B4's numbers are not recorded, so '$MODE' is not rendered (plan §4 B4)"
[ "$(stat -c '%a %U' "$POOL")" = "600 $(id -un)" ] || die "$POOL is not 0600 and owned by $(id -un)"
seen=" "
while IFS= read -r line || [ -n "$line" ]; do
  case $line in ''|'#'*) continue ;; esac
  [[ $line =~ ^(CONCURRENT|CPU|MEMORY|MAX|SMALL_CPU|SMALL_MEMORY)=([1-9][0-9]*)$ ]] || die "$POOL: want KEY=whole number for $KEYS, got [$line]"
  k=${BASH_REMATCH[1]}; [[ $seen != *" $k "* ]] || die "$POOL names $k twice"
  printf -v "N_$k" %s "${BASH_REMATCH[2]}"; seen="$seen$k "
done < "$POOL"
for k in $KEYS; do [[ $seen == *" $k "* ]] || die "$POOL lacks $k"; done
src="$POOL (B4's record)"
for k in $KEYS; do
  n=N_$k; e=${!k:-}; [ -z "$e" ] || [ "$e" = "${!n}" ] || die "env $k=$e disagrees with $src ($k=${!n}): change the record, not the call"
done
# THE SMALL LANE: short jobs get a set of their own,
# SMALL_SET, so a finisher never waits behind a long job. `concurrent` is process-wide, so it is MAX (the big set)
# + 1 (the small set's one runner): then the small lane always has its slot, and the big set never takes it.
[ "$N_CONCURRENT" = "$((N_MAX + 1))" ] || die "$src: CONCURRENT=$N_CONCURRENT must be MAX + 1 = $((N_MAX + 1)) (one slot for the small lane)"
ok "concurrent=$N_CONCURRENT cpu=$N_CPU memory=$N_MEMORY max-runners=$N_MAX small-lane cpu=$N_SMALL_CPU memory=$N_SMALL_MEMORY from $src"

say "(d) ${RS_USER} reaches D1 through the shared socket; the image"
v=$(docker -H "$D1" version --format '{{.Server.Version}}' 2>&1) && ok "D1 answers ${RS_USER}: Docker $v" || die "D1 refuses ${RS_USER}: $v"
if [ -n "$DIGEST" ]; then
  IMAGE=localhost:${REGISTRY_PORT}/${IMAGE_NAME}@$DIGEST; from="the argument"
elif [ -e "$R/config.toml" ] || [ -L "$R/config.toml" ]; then
  IMAGE=$(image_of "$R/config.toml") || die "config.toml does not name ONE runner image for both sets, so there is no image it runs now to render: read $R/config.toml, or name the image (DIGEST); nothing changed"
  from="the image config.toml runs now"
else
  IMAGE=$(cat /home/${RUN_USER}/run/image.ref) || die "no config.toml and no image.ref from B2"
  from="image.ref: there is no config.toml yet"
fi
[[ $IMAGE =~ $IMGRE ]] && ok "image $IMAGE ($from)" || die "the image is not one strict digest reference: [$IMAGE]"
if rejected "${IMAGE#*@}"; then die "the image $IMAGE is rejected (listed in $REJECTED): nothing changed"; fi
ok "not a rejected image"

if [ "$MODE" = render ]; then
  say "render installs nothing: the installed files must be the ones this release pins (pool-image.sh's PINS; runscaler by BIN_SHA)"
  pins=$(read_pins) || die "$PIMG: no PINS block of \$S03=HEX and \$B/PATH=HEX lines, so the pins cannot be read; nothing staged"
  while read -r s d m; do
    pin=
    while read -r p h; do [ "$p" != "$s" ] || pin=$h; done <<< "$pins"
    [ -n "$pin" ] || die "$PIMG's PINS name no $s, which real installs: nothing staged"
    got=$(sha256sum < "$HOME/$d" 2> /dev/null) || got=
    [ "${got%% *}" = "$pin" ] || die "$HOME/$d is not the $s this release pins (pool-image.sh's PINS): install this release first (pool-image.sh up, or 03 real); nothing staged"
  done <<< "$INSTALLS"
  got=$(sha256sum < "$HOME/bin/runner" 2> /dev/null) || got=
  [ "${got%% *}" = "$BIN_SHA" ] || die "$HOME/bin/runner is not the runscaler this release pins (BIN_SHA): nothing staged"
  ok "runscaler, $(while read -r s d m; do printf '%s ' "${d##*/}"; done <<< "$INSTALLS")are the pinned ones"
else
  say "runscaler v0.9.5, runner-start, pool-ready, validate-class, the unit"
  sha "$B/dl/runner-linux-amd64.tar.gz" "$TGZ_SHA"
  install -d -m 700 "$HOME/bin" "$R"; install -d -m 755 "$HOME/.config/systemd/user"
  tar -xzf "$B/dl/runner-linux-amd64.tar.gz" -C "$tmp" runner; sha "$tmp/runner" "$BIN_SHA"
  install -m 755 "$tmp/runner" "$HOME/bin/runner"
  while read -r s d m; do install -m "$m" "$B/$s" "$HOME/$d"; done <<< "$INSTALLS"
  systemctl --user daemon-reload
  ver=$("$HOME/bin/runner" version 2>&1) || die "runner version: $ver"; ok "${ver%%$'\n'*}"
fi

umask 077
NEW=$R/config.$MODE.new.toml; [ "$MODE" != render ] || NEW=$STAGED
say "render ${NEW##*/}"
header() { cat <<T
# runscaler v0.9.5 config, MODE real, rendered by 03-runscaler.sh. 0600.
# Numbers from $src.
log-level = "info"
concurrent = $N_CONCURRENT
health-address = "127.0.0.1"
health-port = ${RS_HEALTH_PORT}
drain-timeout = "70m"
provider = "docker"
# disable-update: the default (true), as on the Mac. Rebuild the image within 30 days of each runner release (§9 R4).

[docker]
socket = "/home/${RUN_USER}/run/docker.sock"
dind = false
network = "runners"
cpu = $N_CPU
memory = $N_MEMORY
pids-limit = 8192
T
}
set_() { cat <<T

[[scaleset]]
url = "${ORG_URL}"
name = "$1"
token = "env:${TOKEN_ENV}"
runner-group = "$2"
labels = $3
max-runners = $4
runner-image = "$IMAGE"
T
}
small() { set_ ${SMALL_SET} ${GROUP} '["self-hosted", "'"${SMALL_LABEL}"'"]' 1; cat <<T

[scaleset.docker]
cpu = $N_SMALL_CPU
memory = $N_SMALL_MEMORY
T
}
render() {   # $1 = yes: with the small lane (the real render); no: without it (the controls' base, below)
  header
  set_ ${MAIN_SET} ${GROUP} '["self-hosted", "'"${MAIN_LABEL}"'"]' "$N_MAX"; [ "$1" = no ] || small
}
render yes > "$NEW"
first=$(grep -m1 -E '^name = ' "$NEW" | cut -d'"' -f2)
sets_of() { grep -E '^name = ' "$1" 2>/dev/null | cut -d'"' -f2 | sort | paste -sd' ' -; }
ok "rendered $NEW (sets: $(sets_of "$NEW"))"
if [ "$MODE" = render ]; then
  [ "$(sets_of "$R/config.toml")" = "$(sets_of "$NEW")" ] || die "the render's sets [$(sets_of "$NEW")] are not config.toml's [$(sets_of "$R/config.toml")]: an image switch never changes the sets; nothing staged"
  ok "the same sets as config.toml"
else
# A render that changes the SET LIST installs only with the unit inactive (or failed) AND disabled: `activating`
# (auto-restart between retries) would register it at the next retry, and an enabled unit at the next boot — both
# without the operator's go. The same set list (a rebuild) installs in any state.
st=$(systemctl --user is-active runscaler 2>/dev/null || true); en=$(systemctl --user is-enabled runscaler 2>/dev/null || true)
if [ "$(sets_of "$R/config.toml")" = "$(sets_of "$NEW")" ]; then
  ok "the same sets as the installed config: installing this render changes no registration (unit $st, $en)"
else
  case $st in inactive|failed) ;; *) die "this render changes the sets [$(sets_of "$R/config.toml")] -> [$(sets_of "$NEW")] and the unit is $st: at idle, systemctl --user disable --now runscaler first" ;; esac
  [ "$en" = disabled ] || die "this render changes the sets and the unit is $en: a boot would register them; systemctl --user disable --now runscaler first"
  ok "the unit is $st and $en: the new sets register only at the [OUTWARD] enable --now"
fi

say "controls: runner-start refuses each bad config (throwaway copies of the render; they hold with a token present)"
t2=$tmp/c.toml
# The controls below APPEND tables, which TOML gives to the LAST [[scaleset]]. The small lane is last and has its own
# [scaleset.docker], so a second one would not parse and every control would refuse for that reason instead
# (measured). They run on the render WITHOUT the small lane (CB); the small lane's own table has controls after them.
CB=$tmp/base.toml; render no > "$CB"
refuses() { local want=$1; out=$(RUNNER_START_CONFIG=$t2 "$HOME/bin/runner-start" validate 2>&1 || true)
  case $out in *"$want"*) ok "refused: $want" ;; *) die "runner-start did not refuse ($want): $out" ;; esac; }
add() { cp "$CB" "$t2"; printf '%b' "$1" >> "$t2"; }   # appended tables belong to the LAST [[scaleset]]
sed 's/'"${TOKEN_ENV}"'/RUNNER_TOKEN_NOFILE/' "$CB" > "$t2"; refuses "token file missing or empty: $R/token-nofile"
sed 's/^dind = false$/dind = true/' "$CB" > "$t2"; refuses "docker.dind resolves to True"
add '\n[scaleset.docker]\ndind = "true"\n'; refuses "docker.dind resolves to 'true'"
add "\n[scaleset.docker]\ndind = 'true'\n"; refuses "docker.dind resolves to 'true'"
add '\n[scaleset.docker]\ndind = 1\n'; refuses "docker.dind resolves to 1"
add '\n[scaleset.docker]\nDinD = true\n'; refuses "docker.dind resolves to True"
add '\n[scaleset.docker]\n"dind" = true\n'; refuses "docker.dind resolves to True"
add '\n[[scaleset]]\nname = "x"\ntoken = "env:'"${TOKEN_ENV}"'"\ndocker.dind = true\n'; refuses "'x': docker.dind resolves to True"
# no dind under [docker], false in ONE set only -> the other set resolves the builtin true
{ sed '/^dind = false$/d' "$CB"; printf '\n[[scaleset]]\nname = "y"\ntoken = "env:'"${TOKEN_ENV}"'"\n\n[scaleset.docker]\ndind = false\n'; } > "$t2"
refuses "scaleset[0] '$first': docker.dind resolves to True"
add '\n[scaleset.docker]\ndind = false\nDIND = false\n'; refuses "spelled twice"
add "\n[scaleset.docker]\nsocket = \"/run/user/$(id -u)/docker.sock\"\n"; refuses "docker.socket resolves to"
# keys viper resolves differently from a TOML parser, and keys the render never writes
top() { awk -v line="$1" '{print} /^provider = "docker"$/{print line}' "$CB" > "$t2"; }   # a TOP-LEVEL key
top '"docker.dind" = true'; refuses "'docker.dind' is not a plain ASCII key"
top '"docker.socket" = "/var/run/docker.sock"'; refuses "'docker.socket' is not a plain ASCII key"
add '\n[scaleset.docker]\n"dİnd" = true\n'; refuses "'dİnd' is not a plain ASCII key"
add '\n[scaleset.docker]\nshared-volume = "/s"\n'; refuses "docker.shared-volume is not one the render writes"
add '\n[scaleset.docker]\ncache-volumes = ["a:/b"]\n'; refuses "docker.cache-volumes is not one the render writes"
cp "$NEW" "$tmp/c.toml.new"; out=$(RUNNER_START_CONFIG=$tmp/c.toml.new "$HOME/bin/runner-start" validate 2>&1 || true)
case $out in *"must end in .toml"*) ok "refused: a config name that does not end in .toml" ;; *) die "runner-start did not refuse a .toml.new name: $out" ;; esac
# the small lane's OWN [scaleset.docker]: the real render ends inside it, so a line appended lands there
{ cat "$NEW"; printf 'dind = true\n'; } > "$t2"; refuses "scaleset[1] '${SMALL_SET}': docker.dind resolves to True"
{ cat "$NEW"; printf 'shared-volume = "/s"\n'; } > "$t2"; refuses "scaleset[1].docker.shared-volume is not one the render writes"
fi   # ---- end of real's set check and controls

if [ ! -s "$R/${TOKEN_FILE}" ]; then
  [ "$MODE" != render ] || die "no token ($R/${TOKEN_FILE}), so the render cannot be validated: nothing staged"
  echo; echo "03 STOPPED ($MODE): no token yet, so the render is NOT validated and NOT installed (config.toml unchanged)."
  echo "Put the token in (plan §4 B3), then run 03 $MODE again."; exit 3
fi
classify() {   # classify FILE: runner-start validate of FILE, its stdout AND stderr into $tmp/validate.out (a REFUSE line
  # is on stderr); prints the ONE VALIDATE RULE's class
  local rc=0
  RUNNER_START_CONFIG=$1 "$HOME/bin/runner-start" validate > "$tmp/validate.out" 2>&1 < /dev/null || rc=$?
  "$HOME/bin/validate-class" "$rc" "$tmp/validate.out"
}
if [ "$MODE" != render ]; then
say "runscaler's own strict validate: its control first, then the render"
# The control must pass runner-start's guard (an unknown KEY no longer does) and fail runscaler's own check:
# log-level must be debug/info/warn/error (config.go ValidateGlobal), checked before any Docker or GitHub call.
sed 's/^log-level = "info"$/log-level = "liveapp-bogus"/' "$NEW" > "$t2"
cls=$(classify "$t2") || die "validate-class could not classify the control's validate"
out=$(cat "$tmp/validate.out")
[ "$cls" = NON-API ] || die "control: validate of log-level = liveapp-bogus is $cls, not NON-API (its pass proves nothing): $out"
case $out in *"log-level must be"*) ok "control: runscaler's validate refuses a bad log-level (NON-API)" ;; *) die "control: validate failed for another reason: ${out:0:400}" ;; esac
else
say "runscaler's own strict validate of the render"
fi
cls=$(classify "$NEW") || die "validate-class could not classify the validate: nothing changed"
echo "-- runner-start validate $NEW (stdout and stderr):"
cat "$tmp/validate.out"
echo "VALIDATE $cls"
if [ "$MODE" = render ]; then
  case $cls in
    PASS) kept=1; echo; echo "03 STAGED (render): $STAGED names $IMAGE, validate PASS, sha256 $(sha256sum < "$STAGED" | cut -c1-64). Nothing was installed."; exit 0 ;;
    API-ONLY) kept=1; echo; echo "03 STAGED (render): $STAGED names $IMAGE, validate API-ONLY (only the GitHub API part failed: the caller's tries decide), sha256 $(sha256sum < "$STAGED" | cut -c1-64). Nothing was installed."; exit 4 ;;
    *) die "validate $cls: nothing staged" ;;
  esac
fi
[ "$cls" = PASS ] || die "validate $cls, config.toml NOT changed"
vsha=$(sha256sum < "$NEW")
ok "validate passed: $NEW"
before=$( (sha256sum "$R/config.toml" 2>/dev/null || echo none) | cut -c1-12)
mv -f "$NEW" "$R/config.$MODE.toml"
cp -f "$R/config.$MODE.toml" "$R/config.toml.tmp"
[ "$(sha256sum < "$R/config.toml.tmp")" = "$vsha" ] || die "the copy is not the file that was validated: config.toml NOT changed"
mv -f "$R/config.toml.tmp" "$R/config.toml"
ok "installed: config.toml = config.$MODE.toml (sha256 $before -> $(sha256sum "$R/config.toml" | cut -c1-12))"
echo; echo "03 DONE ($MODE) — the unit was NOT restarted: restart it yourself, at idle"
