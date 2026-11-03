#!/usr/bin/env bash
# install-runner.sh TARBALL HOME — run by image/Dockerfile as root, at build time (never on the host): puts the runner
# release in TARBALL (02-d1.sh checked its sha256 against the release asset's digest) into HOME, in place of the base
# image's runner.
# The tarball's top level must be bin/, externals/ and plain files (config.sh, run.sh, …). Any other shape (another
# folder, a dotfile, a link, no bin/ or no externals/) is REFUSED, HOME unchanged. Then HOME's bin/, externals/ and each
# of the TARBALL's root files are removed, the tarball's are moved in, and they get the owner of the base's bin/ (the
# base gives its runner to the runner user). The rest of HOME stays: the runner user's dotfiles, the base's other
# folders, and a root file the tarball does not have.
set -euo pipefail
no() { echo "install-runner.sh: REFUSE $*" >&2; exit 1; }
[ $# = 2 ] || no "usage: install-runner.sh TARBALL HOME"
tgz=$1 home=$2
[ -f "$tgz" ] || no "no tarball $tgz"
{ [ -d "$home/bin" ] && [ ! -L "$home/bin" ]; } || no "$home/bin is not the base image's runner folder"
own=$(stat -c %u:%g "$home/bin")
st=$(mktemp -d "$home/.install-runner.XXXXXX")
trap 'rm -rf -- "$st"' EXIT
tar -xzf "$tgz" -C "$st" --no-same-owner || no "cannot unpack $tgz"
roots=()
for p in "$st"/* "$st"/.[!.]* "$st"/..?*; do
  [ -e "$p" ] || [ -L "$p" ] || continue
  n=${p##*/}
  case $n in
    bin|externals) { [ -d "$p" ] && [ ! -L "$p" ]; } || no "the tarball's $n is not a folder" ;;
    .*) no "the tarball has a dotfile at its top level: $n" ;;
    *) { [ -f "$p" ] && [ ! -L "$p" ]; } || no "the tarball's top-level $n is not a plain file (only bin/ and externals/ may be folders)"
       roots+=("$n") ;;
  esac
done
{ [ -d "$st/bin" ] && [ -d "$st/externals" ]; } || no "the tarball has no bin/ or no externals/"
rm -rf -- "$home/bin" "$home/externals"
for n in "${roots[@]}"; do rm -rf -- "${home:?}/$n"; done
mv -- "$st/bin" "$st/externals" "$home/"
for n in "${roots[@]}"; do mv -- "$st/$n" "$home/$n"; done
chown -R "$own" "$home/bin" "$home/externals"
for n in "${roots[@]}"; do chown "$own" "$home/$n"; done
echo "install-runner.sh: the runner of $tgz is in $home (bin/, externals/ and ${#roots[@]} root files, owner $own)"
