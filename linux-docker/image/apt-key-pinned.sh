#!/usr/bin/env bash
# apt-key-pinned.sh FILE PIN — run by image/Dockerfile as root, at build time (never on the host), on the keyring apt
# will trust for GitHub's gh repository: the file the source's signed-by names. Exit 0 only when the primary keys of
# FILE are PIN alone: gpg --show-keys --with-colons, each `pub` record's own `fpr` (a subkey's fpr follows its `sub`,
# and is no primary key); else exit 1, naming the fingerprints it saw (none: gpg could not read FILE). PIN is 40
# upper-case hex digits; a usage error exits 2. It reads FILE with a gpg home of its own, which it removes.
# THE RULE is the Studio's (bin/linux-image-build's key_pinned: the primaries' fingerprints, joined by one space, must
# be PIN): this is its second copy, in another runtime (a Docker build), and tests/hetzner/test_gh_image.py pins the
# two to agree on the same fixtures. No secret here.
set -uo pipefail
me=apt-key-pinned.sh
[ $# = 2 ] && [[ $2 =~ ^[0-9A-F]{40}$ ]] || { echo "$me: usage: $me FILE PIN (PIN: 40 upper-case hex digits)" >&2; exit 2; }
h=$(mktemp -d) || { echo "$me: FAIL cannot make a gpg home" >&2; exit 1; }
trap 'rm -rf -- "${h:?}"' EXIT
fpr=$(gpg --homedir "$h" --batch --show-keys --with-colons -- "$1" 2> /dev/null \
  | awk -F: '$1 == "pub" {p = 1; next} $1 == "fpr" && p {printf "%s%s", s, $10; s = " "; p = 0}')
[ "$fpr" = "$2" ] || { echo "$me: FAIL $1: its primary keys are [$fpr], want $2 alone" >&2; exit 1; }
echo "$me: OK $1: its one primary key is $2"
