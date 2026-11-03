#!/usr/bin/env bash
# 02-d1.sh — D1: RUN_USER's rootless dockerd, its hardening, the `runners` network, the local registry and the runner
# image. Runs AS RUN_USER, never root (linux-docker/README.md; needs this release's linux-docker/ as ~/build, with the
# repository's setup/tls-excluded-spki in ~/build/setup/):
#   ssh RUN_USER@<host> 'bash -s' < linux-docker/setup/02-d1.sh               the FULL run: a fresh host (re-runnable)
#   ssh RUN_USER@<host> 'bash ~/build/setup/02-d1.sh build RUNNER_VERSION'     BUILD: a runner release's image
# THE IMAGE (step 5, both modes): release v<VERSION> of actions/runner, read with setup/runner-release.sh (GitHub's API;
# the tarball's sha256 must be the release asset's digest; every download with the filtered CA bundle and no CA
# folder), built with --no-cache on the base image/Dockerfile pins, from a fresh 0700 context outside ~/build that holds
# image/'s files (the RECIPE) and the checked tarball as runner.tar.gz (not part of the recipe). The runner version is
# then read from the pushed image (pool-image.sh up's own read): it must be VERSION.
# FULL: steps 1-9 with VERSION = the host config's RUNNER_VERSION; step 9 writes the build record, then ~/run/image.ref:
#   this run is image.ref's ONLY writer.
# BUILD VERSION: ONE path for the updater and a person. Step 3's read-only checks, the image (5) and its checks (6 and
#   8), then the build record; never steps 1, 2, 4 or 7, never image.ref. It does NOT read the updater's on/off key:
#   the updater checks its own key before it calls this, and a person's release update must work while it is off.
#   Then, AS RS_USER, `pool-image.sh up VERSION` (never 03-runscaler.sh alone: up checks the image's runner version,
#   keeps the rollback and restarts only with no runner), and after the first job on the new image passes,
#   `pool-image.sh accept` (or `back`).
# THE BUILD RECORD: ~/run/builds/<VERSION>-<RECIPE>, RECIPE = the sha256 of image/'s `sha256sum` lines (`<hash>  <name>`,
#   names in byte order). ONE per (version, recipe): a rebuild replaces it. 0640 in a 0750 folder, so RS_USER (in
#   RUN_USER's group) can read it. Exactly four `key value` lines, in this order: `format 1`, `version N.N.N`, `digest
#   sha256:<64 hex>` (the image's digest in the local registry), `recipe <64 hex>`. Written whole under a temporary name
#   (.new.*), fsynced, then renamed: a reader takes only names of the record's form, and reads each line by its pattern,
#   as hostile (never sourced). A failed check, a version mismatch or a digest mismatch writes no record.
# Exit: 0 done; 1 FAIL or REFUSE (the line says why; nothing a pool runs changed); 2 usage; 75 WAIT (GitHub answered
# 403 or 429, a rate limit: run it again later). No secret here.
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
host_conf 02-d1.sh HOST_IP SSH_PORT RUN_USER RS_USER REGISTRY_PORT RS_HEALTH_PORT IMAGE_NAME RUNNER_VERSION
usage() { echo "usage: 02-d1.sh (no argument: the full run) | 02-d1.sh build RUNNER_VERSION (for example 2.339.0)"; exit 2; }
MODE=full VERSION=$RUNNER_VERSION
case $# in
  0) [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "02-d1.sh: REFUSE the host config's RUNNER_VERSION is not N.N.N: [$VERSION]" >&2; exit 1; } ;;
  2) { [ "$1" = build ] && [[ $2 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; } || usage; MODE=build VERSION=$2 ;;
  *) usage ;;
esac
cd ~
B=$HOME/build; U=$(id -u)
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$U}
export DOCKER_HOST=unix:///run/user/$U/docker.sock
PROFILE=seccomp-userns-min-v29.9.0.json
PROFILE_SHA=c7c39b9127e823304a731edcde7719b4a4de6aa54a5955076432cd64d33a666f
DEFAULT_SHA=785b2429264afba4d594320337cb17f144f3c7d51585f9805eef72e28f4f9334
REGISTRY=registry:3@sha256:ddf754342cfc8acc51a56d5d0ab6af06826461864460636d8bd5c546dab2a7b8
RPORT=${REGISTRY_PORT}   # the local registry, host loopback only
HPORT=${RS_HEALTH_PORT}   # runscaler's health port: recorded in net.env (nothing listens on it before runscaler runs)
TAG=localhost:$RPORT/${IMAGE_NAME}:b$(date -u +%Y%m%dT%H%M%SZ)   # runs go by DIGEST; the tag only names the build
PUBLIC_IP=${HOST_IP}
say() { printf '\n== %s\n' "$*"; }
ok() { echo "OK   $*"; }
die() { echo "FAIL $*"; exit 1; }
wait_() { echo "WAIT $*"; exit 75; }
sha() { [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ] || die "sha256 $1"; }
quad() { [[ $1 =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] && [ "$1" != 0.0.0.0 ]; }
. "$B/setup/runner-release.sh" || die "cannot read $B/setup/runner-release.sh: is this release's linux-docker/ ~/build?"
REC_DIR=$HOME/run/builds
record() {   # the BUILD RECORD (the header says its form): written whole under a temporary name, fsynced, renamed
  local t
  REC=$REC_DIR/$VERSION-$RECIPE
  [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && ${IMAGE#*@} =~ ^sha256:[0-9a-f]{64}$ && $RECIPE =~ ^[0-9a-f]{64}$ ]] || return 1
  install -d -m 750 "$REC_DIR" || return 1
  t=$(mktemp "$REC_DIR/.new.XXXXXX") || return 1
  { printf 'format 1\nversion %s\ndigest %s\nrecipe %s\n' "$VERSION" "${IMAGE#*@}" "$RECIPE" > "$t" && chmod 640 "$t" \
      && dd if=/dev/null of="$t" conv=notrunc,fsync status=none && mv -f "$t" "$REC"; } || { rm -f "$t"; return 1; }
}

if [ "$MODE" = full ]; then   # ---- steps 1 and 2: the FULL run only (BUILD never installs or restarts the daemon)
say "1. rootless dockerd"
systemctl --user is-active --quiet docker || dockerd-rootless-setuptool.sh install
say "2. hardening (daemon.json) + the second socket in ~/run for ${RS_USER}"
sha "$B/config/$PROFILE" "$PROFILE_SHA"; sha "$B/config/seccomp-default-docker-v29.9.0.json" "$DEFAULT_SHA"
install -d -m 700 "$HOME/.config/docker"; install -d -m 750 "$HOME/run"
install -m 644 "$B/config/$PROFILE" "$HOME/.config/docker/$PROFILE"
want=$(printf '{\n  "seccomp-profile": "%s",\n  "no-new-privileges": true,\n  "init": true,\n  "group": "root"\n}' "$HOME/.config/docker/$PROFILE")
dropin=$HOME/.config/systemd/user/docker.service.d/10-liveapp.conf
wantd=$(printf '[Service]\nExecStart=\nExecStart=/usr/bin/dockerd-rootless.sh -H unix://%%t/docker.sock -H unix://%s/run/docker.sock\n' "$HOME")
changed=0
[ "$(cat "$HOME/.config/docker/daemon.json" 2>/dev/null)" = "$want" ] || { printf '%s\n' "$want" > "$HOME/.config/docker/daemon.json"; changed=1; }
[ "$(cat "$dropin" 2>/dev/null)" = "$wantd" ] || { install -d -m 755 "$(dirname "$dropin")"; printf '%s\n' "$wantd" > "$dropin"; changed=1; }
[ "$changed" = 0 ] || { systemctl --user daemon-reload; systemctl --user restart docker; }
for _ in $(seq 1 30); do docker version >/dev/null 2>&1 && break; sleep 1; done
s=$(stat -c '%a %U:%G' "$HOME/run/docker.sock" 2>/dev/null) || die "no socket at ~/run/docker.sock"
[ "$s" = "660 ${RUN_USER}:${RUN_USER}" ] && ok "~/run/docker.sock $s" || die "~/run/docker.sock is [$s], want 660 ${RUN_USER}:${RUN_USER}"
fi   # ---- end of steps 1 and 2
say "3. (a) the daemon names the profile, is rootless, no-new-privileges"
so=$(docker info --format '{{.SecurityOptions}}') || die "docker info does not answer"
case "$so" in *"profile=$HOME/.config/docker/$PROFILE"*) ok "seccomp profile = ours" ;; *) die "seccomp not ours: $so" ;; esac
case "$so" in *rootless*) ok rootless ;; *) die "not rootless: $so" ;; esac
case "$so" in *no-new-privileges*) ok no-new-privileges ;; *) die "no no-new-privileges: $so" ;; esac
if [ "$MODE" = build ]; then   # ---- BUILD: what the push and the checks need, read only (step 4 is the full run's)
say "(read only) the runners network exists and the registry answers: the full run's step 4 made them"
docker network inspect runners >/dev/null 2>&1 || die "no runners network: run the full 02-d1.sh first"
curl -fs "http://127.0.0.1:$RPORT/v2/" >/dev/null || die "the registry does not answer on 127.0.0.1:$RPORT: run the full 02-d1.sh first"
ok "the runners network exists; the registry answers on 127.0.0.1:$RPORT"
else   # ---- step 4: the FULL run only
say "4. the runners network and the registry on the default bridge"
# A plain bridge. ICC cannot be restricted on this host: Docker refuses an enable_icc=false network without the
# br_netfilter module, which a rootless daemon cannot load (measured). Jobs on `runners` can reach each other's open
# ports, as jobs on one classic runner host can. `runners` still keeps jobs off the registry's
# default bridge: that traffic is ROUTED, so Docker's isolation rules apply (step 7 measures it).
docker network inspect runners >/dev/null 2>&1 || docker network create runners >/dev/null || die "cannot create network runners"
[ "$(docker network inspect runners --format '{{.Driver}}')" = bridge ] && ok "runners: a bridge network" || die "runners is not a bridge network"
docker inspect runner-registry >/dev/null 2>&1 || docker run -d --name runner-registry --restart unless-stopped \
  -p 127.0.0.1:$RPORT:5000 -v runner-registry:/var/lib/registry "$REGISTRY" >/dev/null || die "cannot create the registry container"
[ "$(docker inspect -f '{{.State.Running}}' runner-registry)" = true ] || docker start runner-registry >/dev/null || die "cannot start runner-registry"
for _ in $(seq 1 20); do curl -fs "http://127.0.0.1:$RPORT/v2/" >/dev/null && break; sleep 1; done
curl -fs "http://127.0.0.1:$RPORT/v2/" >/dev/null || die "registry does not answer on 127.0.0.1:$RPORT"; ok "registry answers on 127.0.0.1:$RPORT"
fi   # ---- end of step 4
say "5. the runner image of release v$VERSION (fetched and checked, built, pushed, each checked; the digest of THIS build)."
say "   Its record (and, in the full run, image.ref) is written only at the END, after every check below passed on it (r5 B5-4)"
install -d -m 700 "$RR_DIR" || die "cannot make $RR_DIR"
CTX=$(mktemp -d "$RR_DIR/ctx.XXXXXX") || die "cannot make a build context in $RR_DIR"
trap 'rm -rf -- "${CTX:?}"' EXIT
# The RECIPE: image/'s files, each a plain file, copied into the context; the hash is of these copies (the header).
names=$(LC_ALL=C ls -A "$B/image") && [ -n "$names" ] || die "cannot list $B/image"
lines=
while IFS= read -r n; do
  [ -f "$B/image/$n" ] && [ ! -L "$B/image/$n" ] || die "image/$n is not a plain file: the recipe is image/'s plain files only"
  [ "$n" != runner.tar.gz ] || die "image/$n: that name is the checked tarball's in the build context"
  cp "$B/image/$n" "$CTX/$n" || die "cannot copy image/$n into the build context"
  h=$(sha256sum < "$CTX/$n") || die "cannot hash image/$n"
  lines+="${h%% *}  $n"$'\n'
done <<< "$names"
RECIPE=$(printf '%s' "$lines" | sha256sum | cut -d' ' -f1)
[[ $RECIPE =~ ^[0-9a-f]{64}$ ]] || die "cannot hash the recipe"
ok "the recipe: image/ ($(paste -sd' ' - <<< "$names")): sha256 $RECIPE"
rr_release tag "$VERSION" || { [ $? != 75 ] || wait_ "GitHub's rate limit: nothing was built; run it again later"; die "release v$VERSION: nothing was built (the REFUSE line above says why)"; }
rr_tarball "$CTX/runner.tar.gz" || die "release v$VERSION: nothing was built (the REFUSE line above says why)"
iid=$(docker build -q --no-cache -t "$TAG" "$CTX") || die "docker build failed: no record, image.ref NOT changed"
rm -rf -- "${CTX:?}"; trap - EXIT
[ "$(docker inspect -f '{{.Id}}' "$TAG")" = "$iid" ] || die "the tag does not point at the image just built"
docker push -q "$TAG" >/dev/null || die "docker push failed: no record, image.ref NOT changed"
IMAGE=$(docker inspect --format '{{index .RepoDigests 0}}' "$TAG") || die "cannot read the digest of $TAG"
[[ $IMAGE =~ ^localhost:$RPORT/${IMAGE_NAME}@sha256:[0-9a-f]{64}$ ]] || die "unexpected digest reference [$IMAGE]"
# The runner's version, from the image itself, as pool-image.sh up reads it: the one line that is a bare version
# number (two such lines = no match). No network, bounded. Its labels do not carry it (measured).
out=$(docker run --rm --network none --memory 512m --cpus 1 "$IMAGE" ./config.sh --version < /dev/null) \
  || die "could not run $IMAGE to read its runner version: no record"
v=$(grep -xE '[0-9]+\.[0-9]+\.[0-9]+' <<< "$out" || true)
[ "$v" = "$VERSION" ] || die "the runner in $IMAGE is [$v], not $VERSION: no record"
ok "built and pushed $IMAGE, runner $v (no record yet)"
say "6. (b) a container with NO options, as the MAIN process"
out=$(docker run --rm --network runners "$IMAGE" bash -c '
  grep -E "^(Seccomp|NoNewPrivs):" /proc/self/status | tr -s "\t" " "; echo "pid1=$(cat /proc/1/comm) umask=$(umask)"
  python3 -c "import ctypes; l=ctypes.CDLL(None,use_errno=True); r=l.syscall(250,0,-4,0); print(\"keyctl\", \"EPERM\" if r==-1 and ctypes.get_errno()==1 else \"ALLOWED\")"
  sudo -n true 2>/dev/null && echo sudo=YES || echo sudo=refused
  cd / && bwrap --unshare-user --unshare-net --ro-bind / / /bin/true && echo bwrap=ok
  locale -a | grep -qi "^en_US.utf8$" && echo locale=ok; true' 2>&1) || true
echo "$out"
for w in "Seccomp: 2" "NoNewPrivs: 1" "pid1=docker-init" "umask=0022" "keyctl EPERM" "sudo=refused" "bwrap=ok" "locale=ok"; do
  case "$out" in *"$w"*) ok "$w" ;; *) die "missing: $w (no record, image.ref NOT changed)" ;; esac
done
say "6. controls: unconfined lets keyctl through; Docker's default profile stops bwrap"
c1=$(docker run --rm --security-opt seccomp=unconfined "$IMAGE" python3 -c "import ctypes; l=ctypes.CDLL(None,use_errno=True); print('ALLOWED' if l.syscall(250,0,-4,0)>0 else 'EPERM')" 2>&1 || true)
[ "$c1" = ALLOWED ] && ok "control: unconfined -> keyctl ALLOWED" || die "control: unconfined keyctl [$c1] (the EPERM check proves nothing)"
c2=$(docker run --rm --security-opt seccomp="$B/config/seccomp-default-docker-v29.9.0.json" "$IMAGE" bash -c 'cd / && bwrap --unshare-user --ro-bind / / /bin/true' 2>&1 || true)
case "$c2" in *"No permissions to create new namespace"*|*"Operation not permitted"*) ok "control: Docker's default profile stops bwrap" ;; *) die "control: Docker's default profile did not stop bwrap as expected: [$c2]" ;; esac

if [ "$MODE" = full ]; then   # ---- step 7: the FULL run only (it checks the network, not the image, and writes net.env)
say "7. (c) a runners container reaches the internet; not the registry, the host loopback or the gateways' other ports"
# Two gateways. RUNNERS_GW: the `runners` bridge, inside rootlesskit's DETACHED network namespace. NETNS_GW: that
# namespace's default gateway, gvisor-tap-vsock's userspace NAT. With --detach-netns the daemon runs in the HOST's
# namespace, so a `--network host` container sees the HOST's routes (the host's own gateway): the
# namespace is read as its owner, through the child's mount namespace, and checked against rootlesskit's own API.
S=$XDG_RUNTIME_DIR/dockerd-rootless
gw=$(docker network inspect runners -f '{{(index .IPAM.Config 0).Gateway}}') || die "cannot read the runners gateway"
nsgw=$(nsenter -U --preserve-credentials -m -t "$(cat "$S/child_pid")" -- nsenter --net="$S/netns" ip -4 route show default 2>/dev/null | awk '{print $3; exit}' || true)
apidns=$(curl -s -m5 --unix-socket "$S/api.sock" http://rootlesskit/v1/info | python3 -c 'import json,sys; print(json.load(sys.stdin)["networkDriver"]["dns"][0])' 2>/dev/null || true)
hgw=$(ip -4 route show default | awk '{print $3; exit}' || true)
quad "$gw" && ok "runners gateway $gw" || die "runners gateway is not an address: [$gw]"
quad "$nsgw" && ok "D1's namespace gateway $nsgw" || die "namespace gateway is not an address: [$nsgw]"
[ "$nsgw" = "$apidns" ] && ok "control: rootlesskit's API names the same address ($apidns, its DNS)" || die "the namespace route [$nsgw] and rootlesskit's API [$apidns] disagree"
[ "$nsgw" != "$hgw" ] && ok "control: it is not the host's own default gateway ($hgw)" || die "the namespace gateway equals the host's default gateway [$hgw]: the wrong namespace was read"
rip=$(docker inspect -f '{{.NetworkSettings.Networks.bridge.IPAddress}}' runner-registry) || die "cannot read the registry's address"
quad "$rip" || die "registry IP [$rip]"
printf 'RUNNERS_GW=%s\nNETNS_GW=%s\nPUBLIC_IP=%s\nRPORT=%s\nHPORT=%s\n' "$gw" "$nsgw" "$PUBLIC_IP" "$RPORT" "$HPORT" > "$HOME/run/net.env.new" \
  && chmod 644 "$HOME/run/net.env.new" && mv -f "$HOME/run/net.env.new" "$HOME/run/net.env" || die "cannot write ~/run/net.env"
gh=$(docker run --rm --network runners "$IMAGE" curl -s -m10 -o /dev/null -w '%{http_code}' https://github.com || true)
case "$gh" in 2*|3*) ok "a runners container reaches github.com ($gh)" ;; *) die "a runners container cannot reach github.com [$gh]: the network is broken" ;; esac
# A TCP connect is "reached" whatever the port speaks. The CONTROL ($PUBLIC_IP:SSH_PORT) runs FIRST and LAST: a connect to a
# closed port on NETNS_GW is a black-holed dial that holds a slot of the shared NAT for about a minute, and 5 to 10 of
# them stall every new outbound connect (measured; the source bound is 10) — so this tests ONE such port, never a
# sweep. The health port is not tested here (nothing listens on it before runscaler runs): a first job is that proof.
tcp='for hp in "$@"; do if timeout 5 bash -c "exec 3<>/dev/tcp/${hp%:*}/${hp#*:}" 2>/dev/null; then echo "REACHED $hp"; else echo "refused $hp"; fi; done'
out=$(docker run --rm --network runners "$IMAGE" bash -c "$tcp" _ "$PUBLIC_IP:${SSH_PORT}" "$rip:5000" "$gw:$RPORT" "$nsgw:$RPORT" "$PUBLIC_IP:$RPORT" "$PUBLIC_IP:${SSH_PORT}") || die "the reach test did not run"
echo "$out"
for hp in "$rip:5000" "$gw:$RPORT" "$nsgw:$RPORT" "$PUBLIC_IP:$RPORT"; do
  grep -qx "refused $hp" <<<"$out" && ok "refused $hp" || die "a runners container reached $hp"
done
[ "$(grep -cx "REACHED $PUBLIC_IP:${SSH_PORT}" <<<"$out")" = 2 ] && ok "control: the same test reaches $PUBLIC_IP:${SSH_PORT} before AND after" || die "control: $PUBLIC_IP:${SSH_PORT} not reached before and after (the refusals prove nothing)"
dns='import socket, struct, sys
q = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0) + b"\x06github\x03com\x00" + struct.pack(">HH", 1, 1)
s = socket.create_connection((sys.argv[1], 53), 5); s.sendall(struct.pack(">H", len(q)) + q)
n = struct.unpack(">H", s.recv(2))[0]; a = s.recv(n)
print("DNS id=%s rcode=%d answers=%d" % (a[:2] == q[:2], a[3] & 15, struct.unpack(">H", a[6:8])[0]))'
d=$(docker run --rm --network runners "$IMAGE" python3 -c "$dns" "$nsgw" 2>&1 || true)
[[ $d =~ ^DNS\ id=True\ rcode=0\ answers=[1-9] ]] && ok "the one EXPECTED open port: $nsgw:53 answers a TCP DNS query" || die "$nsgw:53 TCP DNS: [$d] (p9b: it answers)"
c3=$(docker run --rm "$IMAGE" curl -s -m5 -o /dev/null -w '%{http_code}' "http://$rip:5000/v2/" || true)
[ "$c3" = 200 ] && ok "control: from the default bridge the registry answers" || die "control: default bridge cannot reach the registry [$c3] (check (c) proves nothing)"
say "7. (c) every TCP port of the runners gateway: nothing answers (r4 B4-11; local to the namespace, no NAT: p9, 9 s)"
scan='import socket, sys
from concurrent.futures import ThreadPoolExecutor
def probe(hp):
    s = socket.socket(); s.settimeout(1.0)
    try: return hp if s.connect_ex(hp) == 0 else None
    finally: s.close()
todo = [(sys.argv[1], p) for p in range(1, 65536)]
with ThreadPoolExecutor(512) as ex: found = [x for x in ex.map(probe, todo) if x]
for h, p in found: print("OPEN %s:%d" % (h, p))
print("SCANNED %d" % len(todo))'
out=$(docker run --rm --network runners "$IMAGE" python3 -c "$scan" "$gw") || die "the port scan did not run"
grep -qx "SCANNED 65535" <<<"$out" || die "the scan did not finish: [$out]"
open=$(grep '^OPEN' <<<"$out" || true)
[ -z "$open" ] && ok "no TCP port 1-65535 answers on $gw" || die "ports that answer on the runners gateway: $(echo $open)"
trap 'docker rm -f liveapp-b2-listen >/dev/null 2>&1 || true' EXIT
docker run -d --rm --name liveapp-b2-listen --network runners "$IMAGE" python3 -m http.server 8000 >/dev/null || die "cannot start the scan's control"
sleep 2; lip=$(docker inspect -f '{{.NetworkSettings.Networks.runners.IPAddress}}' liveapp-b2-listen || true)
ctl=$(docker run --rm --network runners "$IMAGE" python3 -c "$scan" "$lip" 2>&1 || true); docker rm -f liveapp-b2-listen >/dev/null 2>&1 || true
grep -qx "OPEN $lip:8000" <<<"$ctl" && ok "control: the same scanner finds an open port ($lip:8000)" || die "control: the scanner missed $lip:8000 (the scan proves nothing): [$ctl]"
fi   # ---- end of step 7

say "8. (e) container ROOT (= host ${RUN_USER}, what an escape becomes) cannot list another user's home or /root; control: its own"
done_h=" "
for h in /home/* /root; do
  [ -d "$h" ] && [ "$h" != "$HOME" ] || continue
  rc=0; e=$(docker run --rm -u 0 -v "$h:/x" "$IMAGE" ls /x 2>&1) || rc=$?
  if [ "$rc" = 2 ] && [[ $e == *"Permission denied"* ]]; then ok "D1 container root: ls $h -> Permission denied"; else die "escape check $h: rc=$rc [$e]"; fi
  done_h="$done_h$h "
done
[[ $done_h == *" /home/${RS_USER} "* ]] || die "the escape check did not reach /home/${RS_USER} (the PAT's home)"
docker run --rm -u 0 -v "$HOME/run:/x" "$IMAGE" cat /x/net.env >/dev/null && ok "control: D1 container root reads ${RUN_USER}'s own files" || die "control failed (check (e) proves nothing)"

say "9. every check passed on $IMAGE (runner $VERSION): its build record$([ "$MODE" = build ] || echo ', then image.ref')"
record || die "cannot write the build record $REC_DIR/$VERSION-$RECIPE"
ok "build record $REC"
if [ "$MODE" = full ]; then   # ---- image.ref: the FULL run only (its only writer)
printf '%s\n' "$IMAGE" > "$HOME/run/image.ref.new" && chmod 644 "$HOME/run/image.ref.new" && mv -f "$HOME/run/image.ref.new" "$HOME/run/image.ref" \
  || die "cannot write ~/run/image.ref"
[ "$(cat "$HOME/run/image.ref")" = "$IMAGE" ] && ok "image.ref = $IMAGE" || die "image.ref does not hold $IMAGE"
echo; echo "B2 DONE (D1)"
else
echo; echo "BUILD DONE (D1): runner $VERSION, $IMAGE, record $REC"
fi
