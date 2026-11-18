#!/usr/bin/env bash
# install-release.sh TAG SHA256 UNPACK [--same] [--older] [--anyway] — a release of this repository, installed by ITS
# OWN install line (W4: one verified install line per release; the W4 plan's r3 MODEL X-1..X-5 and FINAL FOLD
# Y-1..Y-9). Never run by hand: a release's linux-install-line.txt (setup/install-release.run-line, rendered by the
# release build with the release's tarball URL, its sha256, VERSION and tag) downloads the tarball, checks its sha256,
# unpacks it into a fresh UNPACK folder of the user's home (plain files and folders only, 0755/0644), and execs THIS
# file of that unpacked tree with TAG, the sha256 and UNPACK, then its own arguments (`ssh <user>@<host> 'bash -s --
# --older' < linux-install-line.txt`, linux-docker/README.md "A release of this repository, by its install line").
# It does today's documented person's steps for ONE user, checked first, and nothing new (X-1):
#   Install step 3 (linux-docker/ as ~/build, with setup/tls-excluded-spki in ~/build/setup/ and core/ as
#   ~/build/core/; the old ~/build moved to ~/build.prev.<UTC>), and as RS_USER Install step 4 (the way back's
#   runscaler download kept, the pinned one downloaded) and step 3's end (`runner-updater pass` and `status`).
# THE ORDER, nothing changes until all is checked (X-2, Y-7): the role; THE INSTALL LOCK; the heal; the identity; as
#   RS_USER, RUN_USER's identity; the host-config keys; the new tree staged and, as RS_USER, its downloads; then THE
#   SWITCH. Any refusal before the switch: the old ~/build untouched, the staging removed, `REFUSE <tag>: ...`, exit 1.
# THE ROLE (X-1): the user it runs as must be the host config's RUN_USER or RS_USER (never root; the line refuses root
#   before it downloads anything).
# THE INSTALL LOCK (Y-1): ~/.local/state/runner-updater/install.lock, flock -n on fd 7, taken FIRST and held to the
#   end (no child inherits it): held -> `REFUSE <tag>: another install runs`, nothing changed. So one user's two runs of
#   a line (an ssh drop, then a retry while the first still downloads) never share a staging folder.
# THE HEAL (X-3): a cut between the switch's two renames leaves no ~/build and the old tree as the newest
#   ~/build.prev.*: the run moves that one back first (under the updater lock too) and says HEALED. Then every
#   ~/build.new.* (the staging of a cut run; only an install makes one) is removed.
# THE IDENTITY (X-5, Y-9; ONE order: runner-release.sh's rr_tag_cmp, ONE reader: rr_release_record): ~/build/.release
#   (`tag <TAG>`, `sha256 <hex>`) absent = a tree installed before W4, unknown: any release goes in. The same tag and
#   sha256: `DONE <tag>: already installed`, exit 0, nothing changed, unless --same (a fresh copy). The same tag with
#   another sha256: --same. An older tag: --older (the way back, on purpose: X-8). As RS_USER, RUN_USER's
#   ~/build/.release (rr_read: RUN_USER's file) must name this tag and sha256: RUN_USER first, always.
# THE HOST-CONFIG KEYS (Y-7): each key of the release's linux-docker/host.conf.example must be in HOST_CONF exactly
#   once, else `REFUSE <tag> needs root's step first`, before any change (README Install step 1).
# THE STAGING (Y-1, Y-9 F9): a unique `mktemp -d ~/build.new.XXXXXXXX` (0755), the tree of Install step 3 copied in
#   from UNPACK, and its .release written BEFORE the switch (the rename carries it). As RS_USER (Y-3), into it before
#   the switch: the way back's runscaler download (the release's 03-runscaler.sh WAYBACK and WAYBACK_TGZ_SHA, read as
#   data), found BY ITS SHA256 under any name among the plain files of ~/build/dl/ and of every ~/build.prev.*/dl/,
#   newest first, and copied in under the release's name for it (03's dl_of): KEPT; none: NOT KEPT and a NEXT line,
#   never a refusal (today's step 4); then the pinned download (PINNED, TGZ_SHA), REQUIRED: a failure refuses.
# THE SWITCH (X-3): under the user's updater lock (runner-release.sh's rr_lock -n, fd 9) and, as RS_USER, then
#   pool-image.sh's lock (fd 8), each held -> REFUSE: as RS_USER a window journal there REFUSES unless --anyway
#   (README Install step 3's "install this release's files anyway"); then `mv ~/build ~/build.prev.<UTC>` and `mv
#   STAGING ~/build`, back to back. Only the newest 3 ~/build.prev.* are kept. Then both locks are released.
# AFTER THE SWITCH (X-4, Y-5, Y-6), checked and named, never run: each user's installed timer units (Install step
#   11); as RS_USER, the installed files 03-runscaler.sh installs (its INSTALLS: Install step 9), and runscaler's
#   installed binary against the release's BIN_SHA (the runscaler step, a person's). What is not installed yet (a
#   host before those steps) is no NEXT line: those steps install it. As RS_USER, with the updater installed (~/bin/runner-updater,
#   Install step 10), its `pass` and `status` run once the locks are released (step 3's end): a pass whose exit code
#   is not 0, that WAITs or found the updater lock held, or a status that still shows a window journal ->
#   `DONE <tag>: the files are installed, but the pass says: <its line>`, exit 3.
# Prints its steps (OK, KEPT, NOT KEPT, HEALED), then one final line: `DONE <tag>: nothing else to do`, or `DONE <tag>`
# and a `NEXT as <user>: ...` line per outstanding step, or `REFUSE ...`. Exit: 0 DONE; 1 REFUSE; 2 usage; 3 DONE with
# the pass's line. It reads the user's own PATH (the line's), and every curl starts with -q (no ~/.curlrc).
set -uo pipefail
umask 022
TAG=${1-} SHA=${2-} UNPACK=${3-}
usage() { echo "install-release.sh: usage: install-release.sh TAG SHA256 UNPACK [--same] [--older] [--anyway] (run by a release's linux-install-line.txt, never by hand)"; exit 2; }
[ "$#" -ge 3 ] || usage
shift 3
SAME= OLDER= ANYWAY=
for a in "$@"; do
  case $a in --same) SAME=1 ;; --older) OLDER=1 ;; --anyway) ANYWAY=1 ;; *) usage ;; esac
done
[[ $SHA =~ ^[0-9a-f]{64}$ ]] || usage
SELF=${BASH_SOURCE[0]}
S=${SELF%/*}                     # this release's linux-docker/setup/, in UNPACK
REL=${S%/linux-docker/setup}     # UNPACK/<VERSION>
STAGE= SWITCHED=
cleanup() {
  [ -z "$STAGE" ] || [ -n "$SWITCHED" ] || rm -rf -- "$STAGE"
  case $UNPACK in "$HOME"/.release-unpack.????????) rm -rf -- "$UNPACK" ;; esac
}
trap cleanup EXIT
say() { echo "$*"; }
refuse() { echo "REFUSE $TAG: $*"; exit 1; }
{ [ "${REL%/*}" = "$UNPACK" ] && [[ $UNPACK == "$HOME"/.release-unpack.???????? ]] && [ -d "$REL/core" ] \
    && [ -f "$REL/setup/tls-excluded-spki" ] && [ -d "$REL/linux-docker" ]; } \
  || { UNPACK=; refuse "this file is not the install-release.sh of a tree the line unpacked into ~/.release-unpack.*: nothing changed"; }
# shellcheck source=runner-release.sh
. "$S/runner-release.sh" || refuse "cannot read $S/runner-release.sh: nothing changed"
rr_tag_cmp "$TAG" "$TAG" || refuse "$RR_WHY: nothing changed"

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
host_conf install-release.sh RS_USER RUN_USER
ME=$(id -un)
if [ "$ME" = "${RS_USER}" ]; then ROLE=rs
elif [ "$ME" = "${RUN_USER}" ]; then ROLE=run
else refuse "run this line as ${RUN_USER} or ${RS_USER} (the host config's RUN_USER and RS_USER), not as $ME: nothing changed"; fi
B=$HOME/build
SD=${RR_LOCK%/*}
WINDOW=$SD/window
POOLLOCK=$HOME/.config/runner/pool-image.lock
NEXT=()

# THE INSTALL LOCK (the header): the folders made as rr_lock makes them (0700; rr_lock sets their modes at its take)
d=$HOME
for p in .local .local/state .local/state/runner-updater; do
  d=$HOME/$p
  [ -d "$d" ] || mkdir -m 700 -- "$d" 2> /dev/null || [ -d "$d" ] || refuse "cannot make $d: nothing changed"
done
ILOCK=$SD/install.lock
exec 7>> "$ILOCK" || refuse "cannot open $ILOCK: nothing changed"
flock -n 7 || refuse "another install runs (it holds $ILOCK): nothing changed"

locks() {   # the updater lock (fd 9), then, as RS_USER, pool-image.sh's (fd 8): each held -> REFUSE
  rr_lock "$ROLE" -n > /dev/null
  case $? in
    0) ;;
    75) refuse "the updater runs now (it holds $RR_LOCK): nothing changed; run this line again when its pass ends" ;;
    *) refuse "cannot take the updater lock $RR_LOCK: nothing changed" ;;
  esac
  if [ "$ROLE" = rs ] && [ -d "${POOLLOCK%/*}" ]; then
    exec 8>> "$POOLLOCK" || refuse "cannot open $POOLLOCK: nothing changed"
    flock -n 8 || refuse "a pool-image.sh run holds $POOLLOCK: nothing changed; run this line again when it ends"
  fi
}
unlock() { exec 8>&- 9>&-; }
prevs() { ls -1d "$HOME"/build.prev.* 2> /dev/null | LC_ALL=C sort -r; }   # newest first

# THE HEAL (the header)
if [ ! -e "$B" ] && [ ! -L "$B" ]; then
  p=$(prevs | head -n 1)
  if [ -n "$p" ]; then
    locks
    mv -T -- "$p" "$B" || refuse "cannot move $p back to ~/build"
    unlock
    say "HEALED: ~/build was missing (a cut between the two renames of an install): moved ~/${p##*/} back to ~/build"
  fi
fi
for p in "$HOME"/build.new.*; do
  [ -e "$p" ] || [ -L "$p" ] || continue
  rm -rf -- "$p" && say "OK   removed ~/${p##*/}, the staging of a run that was cut"
done

# THE IDENTITY (the header)
if [ -e "$B/.release" ] || [ -L "$B/.release" ]; then
  rr_release_record "$B/.release" || refuse "~/build/.release cannot be read ($RR_WHY): nothing changed"
  rr_tag_cmp "$TAG" "$RR_REL_TAG" || refuse "$RR_WHY: nothing changed"
  case $RR_CMP in
    0) if [ "$RR_REL_SHA" = "$SHA" ]; then
         [ -n "$SAME" ] || { echo "DONE $TAG: already installed (~/build/.release names it, sha256 $SHA): nothing changed; --same installs it again"; exit 0; }
       else
         [ -n "$SAME" ] || refuse "~/build runs $TAG of another sha256 (${RR_REL_SHA:0:12}): nothing changed; --same installs this one"
       fi ;;
    -1) [ -n "$OLDER" ] || refuse "~/build runs $RR_REL_TAG, newer than $TAG: nothing changed; to go back to $TAG on purpose, run this line with --older" ;;
  esac
fi
if [ "$ROLE" = rs ] && [ "${RUN_USER}" != "${RS_USER}" ]; then
  if ! rr_release_record "/home/${RUN_USER}/build/.release"; then
    refuse "run this line as ${RUN_USER} first (its ~/build/.release: $RR_WHY): nothing changed"
  fi
  [ "$RR_REL_TAG" = "$TAG" ] && [ "$RR_REL_SHA" = "$SHA" ] \
    || refuse "run this line as ${RUN_USER} first (its ~/build/.release names $RR_REL_TAG, sha256 ${RR_REL_SHA:0:12}): nothing changed"
fi

# THE HOST-CONFIG KEYS (the header)
while IFS= read -r k; do
  [ "$(grep -c "^$k=" "$HOST_CONF")" = 1 ] \
    || { echo "REFUSE $TAG needs root's step first: $HOST_CONF lacks $k, or holds it more than once (README Install step 1): nothing changed"; exit 1; }
done < <(sed -n 's/^\([A-Z][A-Z0-9_]*\)=.*/\1/p' "$REL/linux-docker/host.conf.example")

# THE STAGING (the header)
STAGE=$(mktemp -d "$HOME/build.new.XXXXXXXX") || refuse "cannot make a staging folder in $HOME: nothing changed"
{ chmod 755 -- "$STAGE" && cp -a -- "$REL/linux-docker/." "$STAGE/" && mkdir -p -- "$STAGE/setup" \
    && cp -a -- "$REL/setup/tls-excluded-spki" "$STAGE/setup/" && cp -a -- "$REL/core" "$STAGE/core" \
    && printf 'tag %s\nsha256 %s\n' "$TAG" "$SHA" > "$STAGE/.release"; } \
  || refuse "cannot copy the release's tree into ${STAGE/#$HOME/\~}: nothing changed"
S03=$STAGE/setup/03-runscaler.sh
pin() { sed -n "s/^$1=\\($2\\)\$/\\1/p" "$S03"; }   # a pin of this release's 03-runscaler.sh, as data
PINNED=$(pin PINNED '[0-9.]*') TGZ_SHA=$(pin TGZ_SHA '[0-9a-f]\{64\}') BIN_SHA=$(pin BIN_SHA '[0-9a-f]\{64\}')
WAYBACK=$(pin WAYBACK '[0-9.]*') WAYBACK_TGZ_SHA=$(pin WAYBACK_TGZ_SHA '[0-9a-f]\{64\}')
if [ "$ROLE" = rs ]; then
  [[ $PINNED =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && $WAYBACK =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && -n $TGZ_SHA && -n $WAYBACK_TGZ_SHA ]] \
    || refuse "its 03-runscaler.sh holds no PINNED, TGZ_SHA, WAYBACK and WAYBACK_TGZ_SHA lines: nothing changed"
  mkdir -p -- "$STAGE/dl" || refuse "cannot make the staging's dl/: nothing changed"
  k=
  for f in "$B/dl" $(prevs | sed 's|$|/dl|'); do
    for g in "$f"/*; do
      [ -f "$g" ] && [ ! -L "$g" ] || continue
      [ "$(sha256sum < "$g" | cut -d ' ' -f 1)" = "$WAYBACK_TGZ_SHA" ] && { k=$g; break 2; }
    done
  done
  w=$STAGE/dl/runner-v$WAYBACK-linux-amd64.tar.gz
  if [ -n "$k" ] && cp -- "$k" "$w" && [ "$(sha256sum < "$w" | cut -d ' ' -f 1)" = "$WAYBACK_TGZ_SHA" ]; then
    say "KEPT $k as ~/build/dl/${w##*/}"
  else
    rm -f -- "$w"
    say "NOT KEPT: no runscaler v$WAYBACK download (none has the way back's sha256, WAYBACK_TGZ_SHA) in ~/build/dl or ~/build.prev.*/dl"
    NEXT+=("the way back's runscaler v$WAYBACK download is NOT KEPT: the README's \"runscaler: the release this one pins, and the way back\" downloads it, when you take the way back")
  fi
  p=$STAGE/dl/runner-linux-amd64.tar.gz
  { curl -q -fsSL --proto =https --proto-redir =https --tlsv1.2 --max-redirs 5 --max-time 900 -o "$p" \
      "https://github.com/ysya/runscaler/releases/download/v$PINNED/runner-linux-amd64.tar.gz" < /dev/null \
      && [ "$(sha256sum < "$p" | cut -d ' ' -f 1)" = "$TGZ_SHA" ]; } \
    || refuse "the download of runscaler v$PINNED failed, or its sha256 is not 03-runscaler.sh's TGZ_SHA: nothing changed"
  say "OK   runscaler v$PINNED downloaded, its sha256 03-runscaler.sh's TGZ_SHA (~/build/dl/runner-linux-amd64.tar.gz)"
fi

# THE SWITCH (the header)
locks
if [ "$ROLE" = rs ] && { [ -e "$WINDOW" ] || [ -L "$WINDOW" ]; } && [ -z "$ANYWAY" ]; then
  refuse "a window journal is there ($WINDOW): nothing changed. Run ~/bin/runner-updater pass, then status, until status shows no window journal line, then this line again; an updater too old to end it (STOP RECOVER needed): this line with --anyway"
fi
pv=
if [ -e "$B" ] || [ -L "$B" ]; then
  pv=$HOME/build.prev.$(date -u +%Y%m%dT%H%M%SZ)
  n=1
  while [ -e "$pv" ] || [ -L "$pv" ]; do pv=$HOME/build.prev.$(date -u +%Y%m%dT%H%M%SZ)-$n; n=$((n + 1)); done
  mv -T -- "$B" "$pv" || refuse "cannot move ~/build aside: nothing changed"
fi
mv -T -- "$STAGE" "$B" || { [ -z "$pv" ] || mv -T -- "$pv" "$B"; refuse "cannot move the staging to ~/build: nothing changed"; }
SWITCHED=1
unlock
say "OK   switched: ~/build is $TAG${pv:+ (the release before: ~/${pv##*/})}"
prevs | tail -n +4 | while IFS= read -r p; do rm -rf -- "$p" && say "OK   removed ~/${p##*/} (only the newest 3 are kept)"; done

# AFTER THE SWITCH (the header)
for n in runner-updater.service runner-updater.timer; do
  u=$HOME/.config/systemd/user/$n
  if { [ -e "$u" ] || [ -L "$u" ]; } && ! cmp -s -- "$B/config/$n" "$u"; then
    NEXT+=("the updater's timer units are not this release's: bash ~/build/setup/04-timer.sh (README Install step 11)")
    break
  fi
done
if [ "$ROLE" = rs ]; then
  differ=()
  while read -r s dst m; do
    [ -n "$s" ] || continue
    { [ -e "$HOME/$dst" ] || [ -L "$HOME/$dst" ]; } || continue    # not installed yet: Install step 9's
    cmp -s -- "$B/$s" "$HOME/$dst" || differ+=("$dst")
  done < <(sed -n '/^INSTALLS="/,/"$/{s/^INSTALLS="//;s/"$//;p;}' "$B/setup/03-runscaler.sh")
  if [ "${#differ[@]}" = 1 ]; then
    NEXT+=("${differ[0]} is not this release's: the next pool-image.sh up installs it (or 03-runscaler.sh real: README Install step 9)")
  elif [ "${#differ[@]}" -gt 1 ]; then
    NEXT+=("$(IFS=,; echo "${differ[*]}" | sed 's/,/, /g') are not this release's: the next pool-image.sh up installs them (or 03-runscaler.sh real: README Install step 9)")
  fi
  rb=$(sha256sum < "$HOME/bin/runner" 2> /dev/null | cut -d ' ' -f 1)
  if [ -n "$rb" ] && [ "$rb" != "$BIN_SHA" ]; then
    NEXT+=("this release pins runscaler v$PINNED, and another one runs: the runscaler step, a person's, at a quiet time (README \"runscaler: the release this one pins, and the way back\")")
  fi
fi
said=
if [ "$ROLE" = rs ] && { [ -e "$HOME/bin/runner-updater" ] || [ -L "$HOME/bin/runner-updater" ]; }; then
  out=$("$B/bin/runner-updater" pass < /dev/null 7>&- 2>&1); rc=$?
  printf '%s\n' "$out"
  l=$(printf '%s\n' "$out" | grep -v '^$' | tail -n 1)
  if [ "$rc" != 0 ] || [[ $l == "runner-updater: WAIT"* || $l == *"another run holds the updater lock"* ]]; then said=$l; fi
  out=$("$B/bin/runner-updater" status < /dev/null 7>&- 2>&1)
  printf '%s\n' "$out"
  [ -n "$said" ] || said=$(printf '%s\n' "$out" | grep -m 1 'status: a window journal is')
fi
if [ -n "$said" ]; then
  echo "DONE $TAG: the files are installed, but the pass says: $said (README Install step 3; \"An unfinished window the updater cannot end\")"
elif [ "${#NEXT[@]}" = 0 ]; then
  echo "DONE $TAG: nothing else to do"
else
  echo "DONE $TAG"
fi
for n in "${NEXT[@]}"; do echo "NEXT as $ME: $n"; done
[ -z "$said" ] || exit 3
exit 0
