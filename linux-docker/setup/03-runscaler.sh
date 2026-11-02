#!/usr/bin/env bash
# 03-runscaler.sh — runscaler as RS_USER: the binary (both checksums), runner-start, pool-ready, the user unit, and ONE
# named config. Runs AS RS_USER, never root (linux-docker/README.md; needs this release's linux-docker/ as ~/build):
#   ssh RS_USER@<host> 'bash -s -- MODE' < linux-docker/setup/03-runscaler.sh
# The set names, groups and labels are the host config's (host.conf.example):
#   MODE probe  one set: PROBE_SET           (group GROUP, labels self-hosted + PROBE_LABEL)
#   MODE real   two sets: MAIN_SET           (group GROUP, labels self-hosted + MAIN_LABEL) and the small lane
#               SMALL_SET                    (same group, labels self-hosted + SMALL_LABEL, 1 runner, its own
#               cpu/memory: SMALL_CPU/SMALL_MEMORY)
#   MODE c1     MAIN_SET + C1_SET            (group C1_GROUP, label C1_LABEL only, 1 runner, the real set's cpu)
# It renders ~/.config/runner/config.MODE.new.toml (a .toml NAME: runscaler takes the config type from the extension)
# and runs the refusal controls on throwaway copies. Only when the token is in does it validate the render with
# runscaler's own strict `validate` and THEN install it as config.MODE.toml and config.toml. No token: no CONFIG is
# installed ("03 STOPPED", exit 3; the binary, runner-start, pool-ready and the unit are). A failed validate:
# config.toml is not touched. It does not start or restart runscaler (a running pool is fine: validate takes no lock). A
# config that registers a NEW set is rendered only with the unit stopped (a crash restart must not register it before
# the operator's go).
# NUMBERS: ~/.config/runner/pool.env (0600; CONCURRENT CPU MEMORY MAX SMALL_CPU SMALL_MEMORY, whole numbers), written
# once the pool's size is measured. real and c1 REFUSE without it; probe without it uses the start values 3/4/4096/3
# and says so. An env var of the same name that disagrees with what is used is refused: change the record, not the call.
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
host_conf 03-runscaler.sh RUN_USER RS_USER REGISTRY_PORT RS_HEALTH_PORT IMAGE_NAME ORG_URL TOKEN_ENV TOKEN_FILE GROUP MAIN_SET MAIN_LABEL SMALL_SET SMALL_LABEL PROBE_SET PROBE_LABEL C1_SET C1_GROUP C1_LABEL
cd ~
B=$HOME/build; R=$HOME/.config/runner; POOL=$R/pool.env
MODE=${1-}; case $MODE in probe|real|c1) ;; *) echo "usage: 03-runscaler.sh probe|real|c1"; exit 2 ;; esac
D1=unix:///home/${RUN_USER}/run/docker.sock
TGZ_SHA=f0e024d181954fb6d29d254b43907152be0f5fa8f91b3e054e9e199be29ec25f
BIN_SHA=d9d1e5779ad5c7220dddcba1a2464f50f680f9d8102f784da63f15a052523948
KEYS="CONCURRENT CPU MEMORY MAX SMALL_CPU SMALL_MEMORY"
say() { printf '\n== %s\n' "$*"; }
ok() { echo "OK   $*"; }
die() { echo "FAIL $*"; exit 1; }
sha() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || die "sha256 $1"; }

say "the numbers"
N_CONCURRENT=3 N_CPU=4 N_MEMORY=4096 N_MAX=3 N_SMALL_CPU=2 N_SMALL_MEMORY=2048
if [ -e "$POOL" ]; then
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
else
  [ "$MODE" = probe ] || die "no $POOL: B4's numbers are not recorded, so '$MODE' is not rendered (plan §4 B4)"
  src="the START values (no $POOL yet: B4 has not run; the probe set only proves the route)"
fi
for k in $KEYS; do
  n=N_$k; e=${!k:-}; [ -z "$e" ] || [ "$e" = "${!n}" ] || die "env $k=$e disagrees with $src ($k=${!n}): change the record, not the call"
done
# THE SMALL LANE: short jobs get a set of their own,
# SMALL_SET, so a finisher never waits behind a long job. `concurrent` is process-wide, so it is MAX (the big set)
# + 1 (the small set's one runner): then the small lane always has its slot, and the big set never takes it.
[ "$MODE" = probe ] || [ "$N_CONCURRENT" = "$((N_MAX + 1))" ] || die "$src: CONCURRENT=$N_CONCURRENT must be MAX + 1 = $((N_MAX + 1)) (one slot for the small lane)"
ok "concurrent=$N_CONCURRENT cpu=$N_CPU memory=$N_MEMORY max-runners=$N_MAX small-lane cpu=$N_SMALL_CPU memory=$N_SMALL_MEMORY from $src"

say "(d) ${RS_USER} reaches D1 through the shared socket; the image reference"
v=$(docker -H "$D1" version --format '{{.Server.Version}}' 2>&1) && ok "D1 answers ${RS_USER}: Docker $v" || die "D1 refuses ${RS_USER}: $v"
IMAGE=$(cat /home/${RUN_USER}/run/image.ref) || die "no image.ref from B2"
[[ $IMAGE =~ ^localhost:${REGISTRY_PORT}/${IMAGE_NAME}@sha256:[0-9a-f]{64}$ ]] && ok "image $IMAGE" || die "image.ref is not one strict digest reference: [$IMAGE]"
say "runscaler v0.9.5, runner-start, pool-ready, the unit"
sha "$B/dl/runner-linux-amd64.tar.gz" "$TGZ_SHA"
install -d -m 700 "$HOME/bin" "$R"; install -d -m 755 "$HOME/.config/systemd/user"
tmp=$(mktemp -d); trap 'rm -rf "${tmp:?}"' EXIT
tar -xzf "$B/dl/runner-linux-amd64.tar.gz" -C "$tmp" runner; sha "$tmp/runner" "$BIN_SHA"
install -m 755 "$tmp/runner" "$HOME/bin/runner"
install -m 755 "$B/bin/runner-start" "$HOME/bin/runner-start"
install -m 755 "$B/bin/pool-ready" "$HOME/bin/pool-ready"
install -m 644 "$B/config/runscaler.service" "$HOME/.config/systemd/user/runscaler.service"
systemctl --user daemon-reload
ver=$("$HOME/bin/runner" version 2>&1) || die "runner version: $ver"; ok "${ver%%$'\n'*}"

say "render config.$MODE.new.toml"
header() { cat <<T
# runscaler v0.9.5 config, MODE $MODE, rendered by 03-runscaler.sh. 0600.
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
umask 077
NEW=$R/config.$MODE.new.toml
render() {   # $1 = yes: with the small lane (the real render); no: without it (the controls' base, below)
  header
  case $MODE in
    probe) set_ ${PROBE_SET} ${GROUP} '["self-hosted", "'"${PROBE_LABEL}"'"]' "$N_MAX" ;;
    real)  set_ ${MAIN_SET} ${GROUP} '["self-hosted", "'"${MAIN_LABEL}"'"]' "$N_MAX"; [ "$1" = no ] || small ;;
    c1)    set_ ${MAIN_SET} ${GROUP} '["self-hosted", "'"${MAIN_LABEL}"'"]' "$N_MAX"
           set_ ${C1_SET} ${C1_GROUP} '["'"${C1_LABEL}"'"]' 1 ;;
  esac
}
render yes > "$NEW"
first=$(grep -m1 -E '^name = ' "$NEW" | cut -d'"' -f2)
sets_of() { grep -E '^name = ' "$1" 2>/dev/null | cut -d'"' -f2 | sort | paste -sd' ' -; }
ok "rendered $NEW (sets: $(sets_of "$NEW"))"
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
if [ "$MODE" = real ]; then   # the small lane's OWN [scaleset.docker]: the real render ends inside it, so a line appended lands there
  { cat "$NEW"; printf 'dind = true\n'; } > "$t2"; refuses "scaleset[1] '${SMALL_SET}': docker.dind resolves to True"
  { cat "$NEW"; printf 'shared-volume = "/s"\n'; } > "$t2"; refuses "scaleset[1].docker.shared-volume is not one the render writes"
fi

if [ ! -s "$R/${TOKEN_FILE}" ]; then
  echo; echo "03 STOPPED ($MODE): no token yet, so the render is NOT validated and NOT installed (config.toml unchanged)."
  echo "Put the token in (plan §4 B3), then run 03 $MODE again."; exit 3
fi
say "runscaler's own strict validate: its control first, then the render"
# The control must pass runner-start's guard (an unknown KEY no longer does) and fail runscaler's own check:
# log-level must be debug/info/warn/error (config.go ValidateGlobal), checked before any Docker or GitHub call.
sed 's/^log-level = "info"$/log-level = "liveapp-bogus"/' "$NEW" > "$t2"
if out=$(RUNNER_START_CONFIG=$t2 "$HOME/bin/runner-start" validate 2>&1); then
  die "control: validate PASSED log-level = liveapp-bogus (its pass proves nothing): $out"
fi
case $out in *"log-level must be"*) ok "control: runscaler's validate refuses a bad log-level" ;; *) die "control: validate failed for another reason: ${out:0:400}" ;; esac
out=$(RUNNER_START_CONFIG=$NEW "$HOME/bin/runner-start" validate 2>&1) || die "validate failed, config.toml NOT changed: $out"
vsha=$(sha256sum < "$NEW")
case $out in *"All checks passed."*) ok "validate passed: $NEW" ;; *) die "validate exited 0 without 'All checks passed.', config.toml NOT changed: $out" ;; esac
before=$( (sha256sum "$R/config.toml" 2>/dev/null || echo none) | cut -c1-12)
mv -f "$NEW" "$R/config.$MODE.toml"
cp -f "$R/config.$MODE.toml" "$R/config.toml.tmp"
[ "$(sha256sum < "$R/config.toml.tmp")" = "$vsha" ] || die "the copy is not the file that was validated: config.toml NOT changed"
mv -f "$R/config.toml.tmp" "$R/config.toml"
ok "installed: config.toml = config.$MODE.toml (sha256 $before -> $(sha256sum "$R/config.toml" | cut -c1-12))"
echo; echo "03 DONE ($MODE) — the unit was NOT restarted: restart it yourself, at idle"
