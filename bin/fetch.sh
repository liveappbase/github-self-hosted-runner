#!/bin/zsh -f
# fetch.sh [--replace] MANIFEST — download pinned tarballs, verify each SHA-256 BEFORE anything is extracted, and
# install one member of each. Design: docs/design.md ("Downloads"). install runs it with --replace.
#
# Manifest line:  KIND URL SHA256 MEMBER DEST     (KIND = file | dir; blank lines and '#' lines are ignored)
# - Stops at the FIRST refusal (exit 1). Every refusal prints "REFUSE <reason>: …" on stderr.
# - Idempotent: a DEST that already holds the same content prints "OK already installed".
# - A DEST with different content is REFUSED and left untouched — unless --replace: then it is REPLACED, and a folder
#   is never moved onto an existing one: DEST -> DEST.prev.<pid>, the new member -> DEST, read back (its digest must
#   be the new one), then DEST.prev.<pid> is removed. install uses --replace only while the agent is disabled and it
#   holds the runner lock; a crash can leave DEST.prev.<pid> (or no DEST), which the next install handles.
# - On success prints "INSTALLED <dest> sha256 <member's own sha256>" (a dir member: a tree digest), or "REPLACED
#   <dest> sha256 <new> (was <old>)". softnet's binary sha256 is 02-wall.sh's SOFTNET_SHA literal.
set -u
export LC_ALL=C
SHASUM=/usr/bin/shasum
DEST_ROOT=/Users/ci     # every DEST is under it; a replaced DEST's aside is removed only under it

refuse() { print -u2 -r -- "REFUSE $*"; exit 1; }
sum256() { $SHASUM -a 256 "$1" | /usr/bin/awk '{print $1}'; }
treesum() { # digest of a directory tree: every file's relative path + sha256, sorted
  (cd "$1" && /usr/bin/find . -type f | LC_ALL=C /usr/bin/sort | while IFS= read -r f; do print -r -- "$f $(sum256 "$f")"; done) \
    | $SHASUM -a 256 | /usr/bin/awk '{print $1}'
}
digest() { if [[ $1 == file ]]; then sum256 "$2"; else treesum "$2"; fi }   # digest KIND PATH

replace=0
if [[ ${1-} == --replace ]]; then replace=1; shift; fi
manifest=${1:-}
(( $# == 1 )) && [[ -n $manifest && -r $manifest ]] || refuse "malformed call: usage fetch.sh [--replace] MANIFEST (a readable file)"
work=$(/usr/bin/mktemp -d -t liveapp-fetch) || refuse "tmp: mktemp failed"
trap '/bin/rm -rf -- "${work:?}"' EXIT

n=0
while IFS= read -r line || [[ -n $line ]]; do
  n=$((n+1))
  [[ -z ${line//[[:space:]]/} || $line == \#* ]] && continue
  f=(${=line})
  (( ${#f} == 5 )) || refuse "malformed line $n: expected KIND URL SHA256 MEMBER DEST"
  kind=$f[1] url=$f[2] want=$f[3] member=$f[4] dest=$f[5]
  [[ $kind == file || $kind == dir ]] || refuse "malformed line $n: KIND must be file or dir"
  [[ $want =~ '^[0-9a-f]{64}$' ]] || refuse "malformed line $n: SHA256 must be 64 lowercase hex digits"
  [[ $dest == $DEST_ROOT/?* && $dest != *..* ]] || refuse "malformed line $n: DEST must be an absolute path under $DEST_ROOT/"
  [[ $member =~ '^[A-Za-z0-9_][A-Za-z0-9._-]*$' ]] || refuse "malformed line $n: MEMBER must be a plain name"

  tgz=$work/$n.tgz
  /usr/bin/curl -fsSL --max-time 600 -o "$tgz" "$url" 2>/dev/null || refuse "download failed: $url"
  got=$(sum256 "$tgz")
  [[ $got == "$want" ]] || refuse "digest mismatch for $url: got $got, want $want (nothing extracted)"

  x=$work/$n.x
  /bin/mkdir "$x" || refuse "tmp: mkdir failed"
  /usr/bin/tar -xzf "$tgz" -C "$x" "$member" 2>/dev/null && [[ -e $x/$member ]] || refuse "member $member not in $url"
  if [[ $kind == file ]]; then
    [[ -f $x/$member ]] || refuse "member $member is not a file"
  else
    [[ -d $x/$member ]] || refuse "member $member is not a directory"
  fi
  new=$(digest $kind "$x/$member")

  if [[ -e $dest || -L $dest ]]; then
    old=$(digest $kind "$dest")
    if [[ $old == "$new" ]]; then
      print -r -- "OK already installed $dest sha256 $new"
      continue
    fi
    (( replace )) || refuse "$dest exists and differs (installed $old, new $new)"
    aside=$dest.prev.$$
    /bin/mv "$dest" "$aside" || refuse "replace: cannot move $dest aside"
    /bin/mv "$x/$member" "$dest" || refuse "replace: cannot move the new $member to $dest (the old one is $aside)"
    [[ $(digest $kind "$dest") == "$new" ]] || refuse "replace: $dest does not read back as $new (the old one is $aside)"
    if [[ $aside == $DEST_ROOT/?*.prev.<-> ]]; then /bin/rm -rf -- "${aside:?}"; fi
    print -r -- "REPLACED $dest sha256 $new (was $old)"
  else
    /bin/mkdir -p "${dest:h}" || refuse "install: mkdir ${dest:h} failed"
    /bin/mv "$x/$member" "$dest" || refuse "install: mv to $dest failed"
    print -r -- "INSTALLED $dest sha256 $new"
  fi
done < "$manifest"
exit 0
