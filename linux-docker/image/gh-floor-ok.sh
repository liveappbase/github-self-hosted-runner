#!/usr/bin/env bash
# gh-floor-ok.sh FLOOR_FILE VERSION — THE gh FLOOR's one compare: exit 0 when VERSION is at or above the floor that
# FLOOR_FILE holds, compared field by field as numbers (2.45.0 is below 2.102.0); else 1, naming both. Read by
# image/Dockerfile (the gh it installed, at build time) and by 02-d1.sh step 6 (b) (the gh=<version> the built image
# printed), each from the recipe the build hashed (the build context's copy of image/). FLOOR_FILE (image/gh-floor)
# must be exactly ONE line N.N.N: digits and dots, no `v`, no CR, no other line, no NUL (its newline may be missing);
# one of any other form, or one it cannot read, fails closed (exit 1). VERSION must be N.N.N too. Each number is 1 to 9
# digits. A usage error exits 2. Why a floor: the gh of Ubuntu noble (2.45.0) is under most of gh's published security
# advisories; every one published is fixed at or below the floor.
set -uo pipefail
LC_ALL=C
me=gh-floor-ok.sh
[ $# = 2 ] || { echo "$me: usage: $me FLOOR_FILE VERSION" >&2; exit 2; }
n='[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}'
fail() { echo "$me: FAIL $*" >&2; exit 1; }
{ exec 3< "$1"; } 2> /dev/null || fail "cannot read the floor file $1"
if IFS= read -r -d '' f <&3; then fail "the floor file $1 holds a NUL byte: want one line N.N.N"; fi
re="^($n)"$'\n'"?\$"
[[ $f =~ $re ]] || fail "the floor file $1 is not one line N.N.N: [$(printf '%q' "$f")]"
floor=${BASH_REMATCH[1]}
[[ $2 =~ ^$n$ ]] || fail "the gh version [$2] is not N.N.N (the floor [$floor], $1)"
IFS=. read -r a1 a2 a3 <<< "$2"
IFS=. read -r b1 b2 b3 <<< "$floor"
for i in 1 2 3; do
  a=a$i b=b$i
  (( 10#${!a} == 10#${!b} )) && continue
  (( 10#${!a} > 10#${!b} )) && break
  fail "gh [$2] is below the floor [$floor] ($1)"
done
echo "$me: OK gh [$2] is at or above the floor [$floor] ($1)"
