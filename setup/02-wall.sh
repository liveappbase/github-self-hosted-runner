#!/bin/zsh -f
# 02-wall.sh — install the network wall's root-owned files. The ADMIN runs it in the admin's own session with the ONE
# line root-line.txt of the release (setup/02-wall.run-line, rendered by tools/release-check --build with the sha256 of
# this file as released): that line copies this script
# to a root-owned file (mode 0600) in /private/tmp, runs that copy only if its sha256 is the one sent, with
# `/bin/zsh -f` (no startup file of the caller's HOME runs as root), and removes it even on Ctrl-C. This file lives in
# ci's home (/Users/ci/mac-runner/<VERSION>/setup/), so the sha256 is what ties the run to the release.
# Design: docs/design.md ("The root files"). v0.x keeps the four literals below: the root files never change in v0.x.
# What it does, in this order. It changes NOTHING until every check passed:
#   1. It stops unless it runs as root, and unless /usr/local (above both folders it owns) is root:wheel, mode 755,
#      with no ACL — wall-files-check requires that too, and this script does not change it.
#   2. It copies the staged shim and softnet into a folder only root can open, and compares each COPY's SHA-256 with
#      the literal below (so the file it checks is the file it installs). softnet 0.24.1 is not code-signed: its hash
#      is its identity; it is the binary from softnet.tar.gz, whose digest the download step checked (below).
#   3. It writes shim.conf (the free-disk floor) from the text below and compares its SHA-256 with the literal.
#   4. It creates /usr/local/bin, /usr/local/libexec and /usr/local/libexec/liveapp-ci when absent. Each of them —
#      also one that already existed, such as /usr/local/bin — is then set to root:wheel, mode 755, with no ACL.
#      It stops if any is a symlink or not a directory, or if a file it would replace is not a plain file.
#   5. It installs softnet (root:wheel 4755), the shim (root:wheel 755) and shim.conf (root:wheel 644), each by a
#      rename, so a reader sees the old file or the new one, never half of one. No file can carry an ACL: its folder
#      has none by then (step 4), and a copy without -p does not carry one.
#   6. LAST, it writes the record install.digests (root:wheel 644). This script is the record's only writer; until
#      it is written, wall-files-check says FILES red, so a stopped run fails closed.
# Running it again with the same files leaves everything the same. Every stop: "02-wall: REFUSE <reason>", exit 1.
# The constants below are the named inputs; tools/release-check pins STAGE_SHIM to VERSION and the four literals.
WANT_UID=0
OWNER=root:wheel
STAGE_SHIM=/Users/ci/mac-runner/0.1.0/bin/tart-shim
STAGE_SOFTNET=/Users/ci/mac-runner/downloads/softnet-0.24.1/softnet
BINDIR=/usr/local/bin
LIBDIR=/usr/local/libexec/liveapp-ci
SHIM_SHA=2289161838f8aae4d2e2c765031323270cc8abf462eaf2e21f13276c57bd580f
CONF_SHA=dbe64c3daa692d33b3a1998749ed2e038a25cfaeb8ffe9f69b32024a05c5fdaa
SOFTNET_SHA=e5e35d61a6dd7e35a3134732e766c897b7cb6f097080ff00e1e75adeab0471c7
SOFTNET_TARBALL_SHA=8ff8ff099c2b5ac1b1128e7999c4a730ac85f486c8a4cb0239eb98432859a0f7
CP=/bin/cp
TMPROOT=/private/tmp

set -u
umask 022
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
refuse() { print -u2 -r -- "02-wall: REFUSE $*"; exit 1 }
sha() { local out; out=$(/usr/bin/env -i PATH=$PATH /usr/bin/shasum -a 256 $1) || return 1; print -r -- ${out[1,64]} }

# 1. root
[[ $(id -u) == $WANT_UID ]] || refuse "must run as root (uid $WANT_UID): run it only through root-line.txt of the release, in the admin's own session"

# 2. copies into a root-only folder, then the checks on those copies
for d in ${BINDIR:h} ${LIBDIR:h:h}; do   # /usr/local, both ways up
  [[ -d $d && ! -L $d && "$(stat -f '%Su:%Sg %Sp' $d)" == "$OWNER drwxr-xr-x" && $(ls -lde $d | wc -l) -eq 1 ]] \
    || refuse "not OWNER with mode drwxr-xr-x and no ACL: $d"
done
work=$(mktemp -d $TMPROOT/liveapp-02wall.XXXXXX) || refuse "mktemp failed"
tmps=()   # every .NAME.new this run creates beside a destination
trap 'rm -rf -- "$work"; rm -f -- "${tmps[@]}"' EXIT
trap 'exit 130' INT TERM HUP   # so the EXIT trap runs on Ctrl-C too
chmod 700 $work
[[ -f $STAGE_SHIM && ! -L $STAGE_SHIM && -r $STAGE_SHIM ]] || refuse "staged shim absent or unreadable: $STAGE_SHIM"
[[ -f $STAGE_SOFTNET && ! -L $STAGE_SOFTNET && -r $STAGE_SOFTNET ]] || refuse "staged softnet absent or unreadable: $STAGE_SOFTNET"
$CP -X $STAGE_SHIM $work/tart || refuse "copy of the staged shim failed"
$CP -X $STAGE_SOFTNET $work/softnet || refuse "copy of the staged softnet failed"
[[ $(sha $work/tart) == $SHIM_SHA ]] || refuse "staged shim sha256 differs from the literal: $STAGE_SHIM"
[[ $(sha $work/softnet) == $SOFTNET_SHA ]] || refuse "staged softnet sha256 differs from the literal: $STAGE_SOFTNET"

# 3. shim.conf from this text
print -rl -- "# liveapp-ci shim: free-disk floor. The shim refuses a VM start while the volume that holds Tart's VMs" \
  "# (TART_HOME, else /Users/ci/.tart) has less free space than this (GiB). Written by 02-wall.sh; edit it there." \
  "floor-gib 100" > $work/shim.conf
[[ $(sha $work/shim.conf) == $CONF_SHA ]] || refuse "shim.conf sha256 differs from the literal"
print -rl -- "shim $SHIM_SHA" "shim.conf $CONF_SHA" "softnet $SOFTNET_SHA" "softnet-tarball $SOFTNET_TARBALL_SHA" \
  > $work/install.digests

# 4. the two directories (and libexec above LIBDIR); a destination already there must be a plain file
for d in $BINDIR ${LIBDIR:h} $LIBDIR; do
  if [[ -e $d || -L $d ]]; then
    [[ -d $d && ! -L $d ]] || refuse "not a real directory: $d"
  fi
done
for f in $BINDIR/softnet $LIBDIR/tart $LIBDIR/shim.conf $LIBDIR/install.digests; do
  if [[ -e $f || -L $f ]]; then
    [[ -f $f && ! -L $f ]] || refuse "not a regular file: $f"
  fi
done
for d in $BINDIR ${LIBDIR:h} $LIBDIR; do
  [[ -d $d ]] || mkdir $d || refuse "mkdir failed: $d"
  chown $OWNER $d && chmod 755 $d && chmod -N $d || refuse "chown/chmod failed: $d"
done

# 5 + 6. each file by a rename; the record last
put() { # put SOURCE DEST MODE
  local tmp=${2:h}/.${2:t}.new
  tmps+=($tmp)
  rm -f $tmp && $CP -X $1 $tmp && chown $OWNER $tmp && chmod $3 $tmp && mv -f $tmp $2 \
    || { rm -f $tmp; refuse "install failed: $2" }
}
put $work/softnet $BINDIR/softnet 4755
put $work/tart $LIBDIR/tart 755
put $work/shim.conf $LIBDIR/shim.conf 644
put $work/install.digests $LIBDIR/install.digests 644
print -r -- "02-wall: installed softnet, the shim and shim.conf; record written: $LIBDIR/install.digests"
