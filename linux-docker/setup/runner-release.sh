#!/usr/bin/env bash
# runner-release.sh — SOURCED, never run: ONE copy of how the Linux host reads an actions/runner release, and of the
# trust every such download uses. 02-d1.sh sources it (`02-d1.sh build VERSION` and its full run); the updater's
# latest-release check sources it too, so a person's build and the updater read a release the same way. It reads no
# host config. Needs bash 5, GNU coreutils, curl, python3 and RR_OPENSSL.
#
#   rr_excluded FILE        the keys the data file excludes, one per line on stdout (or REFUSE)
#   rr_bundle               the filtered CA bundle is current, or is rebuilt: sets RR_BUNDLE and RR_CAPATH
#   rr_curl ARG...          ONE download: rr_bundle first (its lines on stderr), then curl with the trust below
#   rr_release tag VERSION  release v<VERSION>; rr_release latest: the newest release. GitHub's API answer, checked:
#                           sets RR_VERSION, RR_PUBLISHED (epoch seconds), RR_DIGEST (sha256:<64 hex>), RR_URL
#   rr_tarball FILE         downloads RR_URL into FILE, then its sha256 must be RR_DIGEST
#   rr_lock                 THE UPDATER LOCK (below), held on fd 9 until this process and its children end;
#                           rr_lock -n (a timer pass of the updater) only tries it: 75 when another run holds it
# Each returns 0, or 1 with a REFUSE line on stderr; rr_release returns 75 with a WAIT line on stderr when GitHub
# answers 403 or 429 (a rate limit: try again later); rr_curl returns curl's own exit code, or 126 when its rr_bundle
# refused (the REFUSE line says why). Call each in a condition (`rr_bundle || …`): they test their own commands' exit
# codes, so a bare call under `set -e` would exit at the first such test.
#
# TRUST (plan D2): every download is rr_curl, curl with ~/.curlrc ignored (-q first), https only (redirects too), TLS
# 1.2 or newer, OPENSSL_X509_TEA_DISABLE=1, --cacert RR_BUNDLE and --capath RR_CAPATH, an EMPTY folder. That folder
# matters: Ubuntu's curl keeps its built-in CA folder (the system's hashed certificate links) beside a --cacert, so
# with --cacert alone an excluded root is still trusted. Measured 2026-11-02 (Ubuntu 24.04 curl 8.5.0, 26.04 curl
# 8.18.0): a --cacert holding one root that does not anchor GitHub's API still got its HTTP 200; with an empty
# --capath added, curl exit 60.
# THE FILTERED BUNDLE: RR_SRC (the system's bundle) less every certificate whose key RR_EXCLUDED names; the key is the
# SHA-256 of the DER SubjectPublicKeyInfo (RR_OPENSSL x509 -pubkey, then pkey -pubin -outform DER: homebrew-core's
# reading). At least RR_FLOOR certificates kept, else REFUSE. A certificate openssl cannot read: REFUSE (never kept,
# never silently dropped). The bundle lives in RR_DIR/tls (0700) with a stamp naming the sha256 of the source and of
# the data file, RR_OPENSSL's version, the sha256 of the filter's own code (rr_sha, rr_excluded and rr_bundle as this
# bash holds them: what runs, not the file, which a new release may replace mid-run), RR_FLOOR, and the bundle's own
# sha256; any of them changed (the bundle edited too), and the bundle is rebuilt. EVERY download runs that check first
# (rr_curl), so an input that changes between two downloads (a key added to the data file after the release was read)
# holds for the next one, and a bundle that ~/.cache kept from another release of this file is rebuilt. EACH INPUT IS
# READ ONCE: the source and the data file are copied into a private folder first, and the stamp's hashes, the parse
# and the filter all read those copies. Two reads of a path would let a file replaced between them (Install step 3
# moves a new ~/build into place) leave a bundle made from one version under a stamp of the other, which every later
# check calls current. RR_OPENSSL, measured on the Linux host 2026-11-02: OpenSSL 3.5.5.
# THE UPDATER LOCK (plan D1): ONE per host user, RR_LOCK, named here once so that 02-d1.sh and the updater (which
# sources this file too) take the same one. Held for a run's whole length: a second run waits for it (rr_lock, for a
# command: a WAIT line names the lock first); a timer pass of the updater only tries it (rr_lock -n) and exits instead.
# flock(2) ties the lock to the OPEN FILE, so a child that inherits fd 9 shares its parent's lock: when fd 9 already
# is RR_LOCK, rr_lock takes it there (at once, if the parent holds it), and so a holder can run 02-d1.sh as its child.
# A new open of RR_LOCK would be another holder, and that child would wait for its own parent.
# THE DATA FILE: setup/tls-excluded-spki of the repository (the install line puts it into ~/build/setup/, beside this
# file). Its own header gives the format and the refusals.

RR_API=https://api.github.com/repos/actions/runner
RR_DL=https://github.com/actions/runner/releases/download
RR_SRC=/etc/ssl/certs/ca-certificates.crt
RR_OPENSSL=/usr/bin/openssl
RR_FLOOR=100
RR_DIR=$HOME/.cache/liveapp-ci
RR_LOCK=$HOME/.local/state/runner-updater/lock
case ${BASH_SOURCE[0]} in */*) RR_EXCLUDED=${BASH_SOURCE[0]%/*}/tls-excluded-spki ;; *) RR_EXCLUDED=./tls-excluded-spki ;; esac
case $(uname -m) in x86_64) RR_ARCH=x64 ;; aarch64) RR_ARCH=arm64 ;; *) RR_ARCH= ;; esac
RR_BUNDLE= RR_CAPATH= RR_VERSION= RR_PUBLISHED= RR_DIGEST= RR_URL=

rr_no() { echo "runner-release: REFUSE $*" >&2; }
rr_sha() {   # rr_sha FILE: its sha256, 64 hex, or rc 1
  local s
  s=$(sha256sum < "$1") || return 1
  s=${s%% *}
  [[ $s =~ ^[0-9a-f]{64}$ ]] || return 1
  printf '%s' "$s"
}

rr_excluded() {   # rr_excluded FILE [NAME]: every hash, once all lines passed; one bad line REFUSES the whole file.
  # NAME (default FILE) is the name the REFUSE lines give it: rr_bundle reads its own copy of RR_EXCLUDED.
  local f=${1-} l h out= n=0
  local nm=${2:-$f}
  { [ -f "$f" ] && [ -r "$f" ]; } || { rr_no "cannot read the excluded keys [$nm]"; return 1; }
  if LC_ALL=C grep -q $'\r' -- "$f"; then rr_no "$nm holds a CR byte"; return 1; fi
  while IFS= read -r l || [ -n "$l" ]; do
    case $l in ''|'#'*) continue ;; esac
    h=${l%% *}
    [[ $h =~ ^[0-9a-f]{64}$ ]] || { rr_no "$nm: a data line whose first field is not 64 lowercase hex"; return 1; }
    case $out in *"$h"*) rr_no "$nm names the key $h twice"; return 1 ;; esac
    out+=$h$'\n'
    n=$((n + 1))
  done < "$f"
  [ "$n" -gt 0 ] || { rr_no "$nm has no data line: an empty list is refused, never read as nothing to exclude"; return 1; }
  printf '%s' "$out"
}

rr_bundle() {
  local d=$RR_DIR/tls ex ov src exs fc want b t l pem= in=0 kept=0 dropped=0 h
  RR_BUNDLE= RR_CAPATH=
  [ -x "$RR_OPENSSL" ] || { rr_no "no $RR_OPENSSL"; return 1; }
  { ov=$("$RR_OPENSSL" version < /dev/null) && [ -n "$ov" ]; } || { rr_no "$RR_OPENSSL version does not answer"; return 1; }
  [[ $RR_FLOOR =~ ^[1-9][0-9]*$ ]] || { rr_no "RR_FLOOR is not a count: [$RR_FLOOR]"; return 1; }
  install -d -m 700 "$RR_DIR" "$d" "$d/capath" || { rr_no "cannot make $d"; return 1; }
  [ -z "$(ls -A "$d/capath")" ] || { rr_no "$d/capath, curl's CA folder, must be empty: something put a file there"; return 1; }
  t=$(mktemp -d "$d/.new.XXXXXX") || { rr_no "cannot make a folder in $d"; return 1; }
  # EACH INPUT READ ONCE (the header): the data file and the source are copied into $t first, and everything below
  # (the stamp's hashes, the parse, the filter) reads those copies, never the paths again
  { [ -f "$RR_EXCLUDED" ] && [ -r "$RR_EXCLUDED" ] && cat -- "$RR_EXCLUDED" > "$t/excluded"; } \
    || { rm -rf -- "$t"; rr_no "cannot read the excluded keys [$RR_EXCLUDED]"; return 1; }
  cat -- "$RR_SRC" > "$t/source" || { rm -rf -- "$t"; rr_no "cannot read the CA bundle $RR_SRC"; return 1; }
  src=$(rr_sha "$t/source") || { rm -rf -- "$t"; rr_no "cannot read the CA bundle $RR_SRC"; return 1; }
  exs=$(rr_sha "$t/excluded") || { rm -rf -- "$t"; rr_no "cannot hash $RR_EXCLUDED"; return 1; }
  fc=$(declare -f rr_sha rr_excluded rr_bundle | sha256sum) && fc=${fc%% *} && [[ $fc =~ ^[0-9a-f]{64}$ ]] \
    || { rm -rf -- "$t"; rr_no "cannot hash the filter's own code"; return 1; }
  ex=$(rr_excluded "$t/excluded" "$RR_EXCLUDED") || { rm -rf -- "$t"; return 1; }
  want="source $src"$'\n'"excluded $exs"$'\n'"openssl $ov"$'\n'"filter $fc"$'\n'"floor $RR_FLOOR"
  if [ -f "$d/bundle.pem" ] && [ -f "$d/stamp" ] && b=$(rr_sha "$d/bundle.pem") \
     && [ "$(cat "$d/stamp")" = "$want"$'\n'"bundle $b" ]; then
    rm -rf -- "$t"
    RR_BUNDLE=$d/bundle.pem RR_CAPATH=$d/capath
    echo "OK   the filtered CA bundle is current ($RR_BUNDLE)"
    return 0
  fi
  : > "$t/bundle.pem" || { rm -rf -- "$t"; rr_no "cannot write in $t"; return 1; }
  while IFS= read -r l || [ -n "$l" ]; do
    if [ "$in" = 1 ]; then
      pem+=$l$'\n'
      [ "$l" = '-----END CERTIFICATE-----' ] || continue
      in=0
      if ! printf '%s' "$pem" > "$t/c.pem" \
         || ! "$RR_OPENSSL" x509 -in "$t/c.pem" -noout -pubkey -out "$t/p.pem" < /dev/null 2> /dev/null \
         || ! "$RR_OPENSSL" pkey -pubin -in "$t/p.pem" -outform DER -out "$t/k.der" < /dev/null 2> /dev/null \
         || [ ! -s "$t/k.der" ] || ! h=$(rr_sha "$t/k.der"); then
        rm -rf -- "$t"; rr_no "$RR_SRC holds a certificate whose key $RR_OPENSSL cannot read: no bundle"; return 1
      fi
      rm -f -- "$t/p.pem" "$t/k.der"
      case $'\n'$ex$'\n' in
        *$'\n'$h$'\n'*) dropped=$((dropped + 1)) ;;
        *) printf '%s' "$pem" >> "$t/bundle.pem" || { rm -rf -- "$t"; rr_no "cannot write in $t"; return 1; }
           kept=$((kept + 1)) ;;
      esac
    elif [ "$l" = '-----BEGIN CERTIFICATE-----' ]; then
      in=1 pem=$l$'\n'
    fi
  done < "$t/source"
  [ "$in" = 0 ] || { rm -rf -- "$t"; rr_no "$RR_SRC ends inside a certificate: no bundle"; return 1; }
  [ "$kept" -ge "$RR_FLOOR" ] || { rm -rf -- "$t"; rr_no "only $kept certificates of $RR_SRC kept ($dropped excluded), want $RR_FLOOR or more: no bundle"; return 1; }
  { b=$(rr_sha "$t/bundle.pem") && printf '%s\nbundle %s\n' "$want" "$b" > "$t/stamp" \
      && mv -f -- "$t/bundle.pem" "$d/bundle.pem" && mv -f -- "$t/stamp" "$d/stamp"; } \
    || { rm -rf -- "$t"; rr_no "cannot install the bundle in $d"; return 1; }
  rm -rf -- "$t"
  RR_BUNDLE=$d/bundle.pem RR_CAPATH=$d/capath
  echo "OK   the filtered CA bundle: $kept certificates of $RR_SRC kept, $dropped dropped by their excluded keys ($RR_BUNDLE)"
}

rr_curl() {   # rr_curl ARG...: ONE download of this path: the bundle check first (its lines on stderr, so that the
  # caller's stdout is curl's alone), then curl with the trust above. Exit: curl's, or 126 when the check refused.
  rr_bundle >&2 || return 126
  OPENSSL_X509_TEA_DISABLE=1 curl -q --proto =https --proto-redir =https --tlsv1.2 --cacert "$RR_BUNDLE" \
    --capath "$RR_CAPATH" -sS "$@" < /dev/null
}

rr_release() {
  local kind=${1-} v=${2-} url j code rc facts re
  RR_VERSION= RR_PUBLISHED= RR_DIGEST= RR_URL=
  case $kind:$# in
    tag:2) [[ $v =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { rr_no "not a runner version: [$v]"; return 1; }
           url=$RR_API/releases/tags/v$v ;;
    latest:1) url=$RR_API/releases/latest ;;
    *) rr_no "usage: rr_release tag VERSION | rr_release latest"; return 1 ;;
  esac
  [ -n "$RR_ARCH" ] || { rr_no "no runner build for this machine ($(uname -m))"; return 1; }
  install -d -m 700 "$RR_DIR" || { rr_no "cannot make $RR_DIR"; return 1; }
  j=$(mktemp "$RR_DIR/release.XXXXXX") || { rr_no "cannot make a file in $RR_DIR"; return 1; }
  code=$(rr_curl --max-time 60 -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2022-11-28' \
           -o "$j" -w '%{http_code}' "$url") || { rc=$?; rm -f -- "$j"
    [ "$rc" = 126 ] || rr_no "GitHub's API did not answer $url (curl exit $rc)"; return 1; }
  case $code in
    200) ;;
    403|429) rm -f -- "$j"; echo "runner-release: WAIT GitHub answered $code (a rate limit) for $url" >&2; return 75 ;;
    *) rm -f -- "$j"; rr_no "GitHub answered $code for $url"; return 1 ;;
  esac
  facts=$(python3 -I - "$j" "$kind" "$v" "$RR_ARCH" "$RR_DL" <<'PY'
import calendar, json, re, sys, time
path, kind, want, arch, dl = sys.argv[1:6]


def no(why):
    print(why)
    sys.exit(1)


try:
    with open(path, 'rb') as f:
        r = json.loads(f.read().decode('utf-8'))
except (OSError, ValueError):
    no('the answer is not JSON')
if not isinstance(r, dict):
    no('the answer is not a JSON object')
tag = r.get('tag_name')
m = re.fullmatch(r'v([0-9]+\.[0-9]+\.[0-9]+)', tag) if isinstance(tag, str) else None
if not m:
    no('its tag %s is not v<N.N.N>' % repr(tag)[:80])
v = m.group(1)
if kind == 'tag' and v != want:
    no('the answer is release v%s, not v%s' % (v, want))
name = 'actions-runner-linux-%s-%s.tar.gz' % (arch, v)
a = [x for x in (r.get('assets') or []) if isinstance(x, dict) and x.get('name') == name]
if len(a) != 1:
    no('release v%s has %d assets named %s, want 1' % (v, len(a), name))
d = a[0].get('digest')
if not (isinstance(d, str) and re.fullmatch(r'sha256:[0-9a-f]{64}', d)):
    no('the asset %s has no sha256 digest' % name)
u = a[0].get('browser_download_url')
if u != '%s/v%s/%s' % (dl, v, name):
    no('the asset %s is not downloaded from its release\'s own address' % name)
p = r.get('published_at')
if not (isinstance(p, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', p)):
    no('release v%s has no published_at time' % v)
print('version %s\npublished %d\ndigest %s\nurl %s' % (v, calendar.timegm(time.strptime(p, '%Y-%m-%dT%H:%M:%SZ')), d, u))
PY
)
  rc=$?
  rm -f -- "$j"
  [ "$rc" = 0 ] || { rr_no "$url: ${facts:-the answer could not be read}"; return 1; }
  re=$'^version ([0-9]+\\.[0-9]+\\.[0-9]+)\npublished ([0-9]+)\ndigest (sha256:[0-9a-f]{64})\nurl (https://[^[:space:]]+)$'
  [[ $facts =~ $re ]] || { rr_no "$url: the answer's facts are not of their form"; return 1; }
  RR_VERSION=${BASH_REMATCH[1]} RR_PUBLISHED=${BASH_REMATCH[2]} RR_DIGEST=${BASH_REMATCH[3]} RR_URL=${BASH_REMATCH[4]}
  echo "OK   release v$RR_VERSION ($RR_ARCH): $RR_DIGEST"
}

rr_tarball() {   # rr_tarball FILE: after rr_release; a FILE that fails the digest check is removed
  local f=${1-} s rc
  { [ -n "$f" ] && [ -n "$RR_URL" ] && [[ $RR_DIGEST =~ ^sha256:[0-9a-f]{64}$ ]]; } \
    || { rr_no "usage: rr_tarball FILE, after rr_release"; return 1; }
  rr_curl -fL --max-redirs 5 --max-time 900 --max-filesize 2147483648 -o "$f" "$RR_URL" \
    || { rc=$?; rm -f -- "$f"; [ "$rc" = 126 ] || rr_no "the download of $RR_URL failed (curl exit $rc)"; return 1; }
  s=$(rr_sha "$f") || { rm -f -- "$f"; rr_no "cannot hash $f"; return 1; }
  [ "sha256:$s" = "$RR_DIGEST" ] || { rm -f -- "$f"; rr_no "$RR_URL: its sha256 is $s, not the release asset's digest $RR_DIGEST"; return 1; }
  echo "OK   $RR_URL: its sha256 is the release asset's digest"
}

rr_lock() {   # rr_lock: THE UPDATER LOCK (the header), for a command: it waits, and says so first. rr_lock -n, for
  # a timer pass: it only tries, and returns 75 (no line) when another run holds it
  install -d -m 700 "${RR_LOCK%/*}" || { rr_no "cannot make ${RR_LOCK%/*}"; return 1; }
  [ /dev/fd/9 -ef "$RR_LOCK" ] || exec 9>> "$RR_LOCK" || { rr_no "cannot open the updater lock $RR_LOCK"; return 1; }
  flock -n 9 && return 0
  [ "${1-}" != -n ] || return 75
  echo "WAIT another run holds the updater lock $RR_LOCK (a build, or a pass of the updater): waiting for it to end"
  flock 9 || { rr_no "cannot take the updater lock $RR_LOCK"; return 1; }
}
