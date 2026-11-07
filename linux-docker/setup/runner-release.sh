#!/usr/bin/env bash
# runner-release.sh — SOURCED, never run: ONE copy of how the Linux host reads an actions/runner release, and of the
# trust every such download uses; ONE copy of a release's image RECIPE and of its BUILD RECORD reader; ONE reader of a
# file that the host's other user owns (rr_read); and ONE CONFIG COMPARE (rr_same_but_image, below). 02-d1.sh
# sources it (`02-d1.sh build VERSION` and its full run), and so do pool-image.sh (its `up`, its `back` and its
# unattended modes), 03-runscaler.sh (inside a window, with no config.toml, and for `real --image-only`) and
# bin/runner-updater (both users: RS_USER's DUE, RUN_USER's build pass), so a person's build and the updater read a
# release, a recipe and a record the same way. It reads no host config. Needs bash 5, GNU coreutils, curl, python3 and
# RR_OPENSSL.
#
#   rr_excluded FILE        the keys the data file excludes, one per line on stdout (or REFUSE)
#   rr_bundle               the filtered CA bundle is current, or is rebuilt: sets RR_BUNDLE and RR_CAPATH
#   rr_curl ARG...          ONE download: rr_bundle first (its lines on stderr), then curl with the trust below
#   rr_release tag VERSION  release v<VERSION>; rr_release latest: the newest release. GitHub's API answer, checked:
#                           sets RR_VERSION, RR_PUBLISHED (epoch seconds), RR_DIGEST (sha256:<64 hex>), RR_URL
#   rr_eligible NOW         rr_release latest, published at least RR_AGE (2 days) before NOW (whole epoch seconds: the
#                           caller's UTC clock): 0, with the RR_ facts above set; younger: 1 and a REFUSE line that
#                           names when it becomes eligible (PLAN D2: "at least 2 days old (latest only)")
#   rr_tarball FILE         downloads RR_URL into FILE, then its sha256 must be RR_DIGEST
#   rr_lock ROLE [-n]       THE UPDATER LOCK (below), held on fd 9 until this process and its children end, after
#                           THE MODES of its folder by ROLE (below; rs or run: the caller's host user); -n (a timer pass
#                           of the updater) only tries it: 75 when another run holds it
#   rr_held                 THE UPDATER'S CHILD (below): this process holds THE UPDATER LOCK on an fd 9 its holder
#                           handed it; it takes, opens and waits for nothing. 0, or 1 and RR_WHY (it prints nothing)
# Each returns 0, or 1 with a REFUSE line on stderr; rr_release and rr_eligible return 75 with a WAIT line on stderr
# when GitHub answers 403 or 429 (a rate limit: try again later); rr_curl returns curl's own exit code, or 126 when its
# rr_bundle refused (the REFUSE line says why). Call each in a condition (`rr_bundle || …`): they test their own
# commands' exit codes, so a bare call under `set -e` would exit at the first such test.
# THE RECIPE AND THE BUILD RECORD (02-d1.sh's header gives their form; PLAN D2 HETZNER: ONE recipe function and ONE
# build-record reader). These three print nothing: 0, or 1 and RR_WHY, for the caller's own line. Call them in the
# caller's shell (a condition, never $(…)), so that what they set stays set:
#   rr_recipe DIR [CTX]     RR_RECIPE = the RECIPE of DIR, an image/ folder: the sha256 of one `<sha256>  <name>` line
#                           per entry, names in byte order; RR_NAMES = the names, one per line. Every entry must be a
#                           plain file (no folder, no symlink), and none may be named runner.tar.gz (the checked
#                           tarball's name in a build context). With CTX (02-d1.sh's build context), each file is copied
#                           into CTX first and the COPY is hashed: what the build reads is what the recipe names
#   rr_record DIR VERSION RECIPE
#                           THE BUILD RECORD of (VERSION, RECIPE): DIR/<VERSION>-<RECIPE>, read ONCE, by rr_read (a
#                           private copy in RR_DIR, then only the copy), exactly 02-d1.sh's four lines, at most 1024
#                           bytes, no NUL byte, never sourced; its version and recipe must be its name's. Sets
#                           RR_RECORD (its path), RR_REC_VERSION, RR_REC_DIGEST and RR_REC_RECIPE. RR_WHY: there is
#                           none; it is not a plain file; it cannot be read; it is not the four lines; it names another
#                           version, or recipe
#   rr_record_of DIR DIGEST the ONE build record in DIR whose digest is DIGEST (the image a config runs: the updater's
#                           BASELINE, PLAN D2 HETZNER). A record is a plain file of DIR named <VERSION>-<RECIPE> that
#                           rr_record reads as that version and recipe; any other file of DIR is none. The same
#                           variables; RR_COUNT = how many records name DIGEST: none, or more than one, is rc 1
# ANOTHER USER'S FILE (PLAN D1: RUN_USER's files are HOSTILE to RS_USER). EVERY read by one host user of a file the
# other one owns is rr_read: RUN_USER's build records (rr_record_read, for rr_record and rr_record_of: RS_USER's DUE and
# pool-image.sh's `up`) and RUN_USER's ~/run/image.ref (03-runscaler.sh with no config.toml, and the README's check of
# a moved host). A type check and then an open are two lookups of the path: RUN_USER can rename a FIFO over the name
# between them, and that open waits for a writer for ever, while the updater lock is held (review r1 of S2b-3b-2,
# measured); a symlink renamed in there is followed. So:
#   rr_read FILE MAX        at most MAX bytes of FILE on stdout, through ONE open (python3: O_NONBLOCK, O_NOFOLLOW)
#                           that never blocks and never follows a symlink; the type is that open's own fstat, a
#                           regular file only: a FIFO (with a writer or none), a symlink, a device or a folder under the
#                           name is none, at once. 0, or 1 and RR_WHY: there is none; it is not a plain file; it cannot
#                           be read
# THE CONFIG COMPARE (runscaler 0.12 bump, slice H2a: the H2 plan's H2-2', R-8): ONE copy of how two runscaler configs
# of this host are compared, read by pool-image.sh (its five callers: a person's up after its 03, the pending-restart
# up, a person's back, the unattended up's D3 and back --unattended's check of its copy) and by 03-runscaler.sh (`real
# DIGEST --image-only`, a person's up: H2-7). COMMENTS ARE NOT CONTENT, so a render whose comment lines changed (03's
# header names the runscaler release) is the same config; a VALUE is content, an inline comment after one too:
#   rr_content FILE         the CONTENT of FILE (PLAN D1, the closing lines'): its lines whose first non-blank character
#                           is not `#` and that are not blank ([[:blank:]]: space and tab), each with its newline, on
#                           stdout; 1 when FILE cannot be read
#   rr_logfile_free TEXT    0 when the config TEXT has NO log-file key, read as runner-start reads a config (TOML,
#                           python3's tomllib; a key bare or quoted, in any case and spacing, at the top level, dotted,
#                           or in any table); 1 when it has one, or a key this cannot read as plain ASCII, or TEXT does
#                           not parse: a log-file key it cannot place is never read as "none"
#   rr_same_but_image A B   0 when config A (the older one: the one that runs, or the kept rollback) and config B (the
#                           newer) are the same less their `runner-image = ` lines, each read ONCE by rr_content; or when
#                           A has no log-file key (rr_logfile_free) and B is A with RR_LOGK, the log-file KEY line 03's
#                           render has, once, right after A's first `log-level = ` line (THE LOG-FILE LINE: so the next
#                           up of a host whose config is older than that line adds it); else 1 (a value, an inline
#                           comment, another log-file value, the line twice or in another place). It prints nothing.
#   RR_LOGK                 that line: `log-file = "$HOME/.config/runner/runner.log"`, the runner.log beside the config
#                           (03's `log-file = "$LOGF"`: on a host, RS_USER's HOME is /home/RS_USER)
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
# THE UPDATER'S CHILD (S2b-3c-1 D-a; PLAN D7 "the unattended modes are the updater's only"): pool-image.sh's unattended
# modes, and 03-runscaler.sh's render inside a window, run only as the child of the lock's holder, and rr_held is that
# test, three conditions: (1) /dev/fd/9 is RR_LOCK (the same file); (2) a FRESH open of RR_LOCK cannot take it (flock -n
# fails: someone holds it); (3) fd 9 can (flock -n 9: this open file description is the holder's, handed down). Without
# (2), a shell that opened the lock on fd 9 and holds nothing would pass: flock -n 9 would TAKE the free lock (measured,
# Opus r2 F9). RESIDUAL, named: a person who takes the lock on fd 9 by hand (`( flock 9; ... ) 9>> RR_LOCK`, the
# flock(1) idiom) passes; the open-window refusal still serializes such a window, and the next pass ends its journal.
# THE MODES (PLAN D1, "Hetzner: one record per user", 11-05): RR_LOCK's folder holds the updater's state, RR_STATE, which
# RS_USER's `status` prints of RUN_USER's (D7), by the same channel as RUN_USER's build records: RUN_USER's group, whose
# only member is RS_USER (01-users.sh checks that). rr_lock sets them, by the ROLE its caller names, BEFORE it opens the
# lock, so every holder of it (both users' updaters, 02-d1.sh in both modes as RUN_USER; pool-image.sh's unattended
# modes take none: they run as RS_USER's updater's child, rr_held) sets the same ones, a lock take that finds the lock
# held too, and a folder left with older modes is set at the next one:
#   run  each folder from the home to RR_LOCK's: one it makes 0710, one that is there gains the group's search (g+x)
#        and keeps every other bit (so others get nothing they did not have; the home itself is 01-users.sh's 0750);
#        RR_LOCK's own folder 0710 each time; RR_STATE 0640
#   rs   one it makes 0700, one that is there is left; RR_LOCK's own folder 0700 each time; RR_STATE 0600 (no channel
#        from RS_USER to RUN_USER)
# and RR_LOCK 0600 for both (it is made so: a lock RS_USER could open, it could hold). Its folders are made 0700 first and
# opened only after the lock and the state have their modes, so nothing in them is the group's before it is set. A
# folder is made with its mode, never the umask's or coreutils' own (install -d made parents 0700 on Ubuntu 26.04 and
# 0755 on 24.04 under umask 077, measured). RR_STATE_MODE names the state's mode for the caller: the updater writes its
# state (by rename) with it, and only under the lock. Everything else there stays private: the updater makes PASSDIR
# 0700 and its files under umask 077; RR_DIR is 0700.
# THE DATA FILE: setup/tls-excluded-spki of the repository (the install line puts it into ~/build/setup/, beside this
# file). Its own header gives the format and the refusals.

RR_API=https://api.github.com/repos/actions/runner
RR_DL=https://github.com/actions/runner/releases/download
RR_SRC=/etc/ssl/certs/ca-certificates.crt
RR_OPENSSL=/usr/bin/openssl
RR_FLOOR=100
RR_AGE=172800   # the seconds a latest release must be old before an updater takes it (2 days: PLAN D2)
RR_DIR=$HOME/.cache/liveapp-ci
RR_LOCK=$HOME/.local/state/runner-updater/lock
RR_STATE=${RR_LOCK%/*}/state.json   # the updater's state (bin/runner-updater's STATE): THE MODES (above)
case ${BASH_SOURCE[0]} in */*) RR_EXCLUDED=${BASH_SOURCE[0]%/*}/tls-excluded-spki ;; *) RR_EXCLUDED=./tls-excluded-spki ;; esac
case $(uname -m) in x86_64) RR_ARCH=x64 ;; aarch64) RR_ARCH=arm64 ;; *) RR_ARCH= ;; esac
RR_BUNDLE= RR_CAPATH= RR_VERSION= RR_PUBLISHED= RR_DIGEST= RR_URL=
RR_RECIPE= RR_NAMES= RR_RECORD= RR_REC_VERSION= RR_REC_DIGEST= RR_REC_RECIPE= RR_COUNT= RR_WHY= RR_STATE_MODE=
RR_LOGK="log-file = \"$HOME/.config/runner/runner.log\""   # THE CONFIG COMPARE (the header)

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

rr_eligible() {   # rr_eligible NOW: the latest release, at least RR_AGE old at NOW (the header)
  local now=${1-} rc
  [[ $now =~ ^(0|[1-9][0-9]*)$ ]] || { rr_no "rr_eligible: NOW is not whole epoch seconds: [$now]"; return 1; }
  rr_release latest; rc=$?
  [ "$rc" = 0 ] || return "$rc"
  [ $((now - RR_PUBLISHED)) -ge "$RR_AGE" ] && return 0
  rr_no "release v$RR_VERSION is younger than 2 days: published $(date -u -d "@$RR_PUBLISHED" '+%Y-%m-%d %H:%M:%S UTC'), eligible from $(date -u -d "@$((RR_PUBLISHED + RR_AGE))" '+%Y-%m-%d %H:%M:%S UTC')"
  return 1
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

rr_recipe() {   # rr_recipe DIR [CTX]: RR_RECIPE and RR_NAMES of an image/ folder (the header); 1 + RR_WHY
  local d=${1-} c=${2-} names n f h lines=
  RR_RECIPE= RR_NAMES= RR_WHY=
  { names=$(LC_ALL=C ls -A -- "$d" 2> /dev/null) && [ -n "$names" ]; } \
    || { RR_WHY="cannot list image/ ($d), or it is empty"; return 1; }
  while IFS= read -r n; do
    { [ -f "$d/$n" ] && [ ! -L "$d/$n" ]; } || { RR_WHY="image/$n is not a plain file: the recipe is image/'s plain files only"; return 1; }
    [ "$n" != runner.tar.gz ] || { RR_WHY="image/$n: that name is the checked tarball's in the build context"; return 1; }
    f=$d/$n
    if [ -n "$c" ]; then
      cp -- "$d/$n" "$c/$n" || { RR_WHY="cannot copy image/$n into the build context"; return 1; }
      f=$c/$n
    fi
    h=$(sha256sum < "$f") || { RR_WHY="cannot hash image/$n"; return 1; }
    lines+="${h%% *}  $n"$'\n'
  done <<< "$names"
  h=$(printf '%s' "$lines" | sha256sum) && h=${h%% *} && [[ $h =~ ^[0-9a-f]{64}$ ]] || { RR_WHY="cannot hash the recipe"; return 1; }
  RR_RECIPE=$h RR_NAMES=$names
}

rr_content() {   # rr_content FILE: its CONTENT on stdout (THE CONFIG COMPARE, the header); 1 when it cannot be read
  grep -v -E '^[[:blank:]]*(#|$)' -- "${1-}" 2> /dev/null || [ $? = 1 ]
}
rr_logfile_free() {   # rr_logfile_free TEXT: 0 the config TEXT has no log-file key (THE CONFIG COMPARE, the header); 1
  # it has one, a key that is not plain ASCII (runner-start's own key rule), or it does not parse
  python3 -I -c '
import re, sys, tomllib
def keys(t):
    if isinstance(t, dict):
        for k, v in t.items():
            yield k
            yield from keys(v)
    elif isinstance(t, list):
        for x in t:
            yield from keys(x)
try:
    c = tomllib.loads(sys.stdin.buffer.read().decode("utf-8"))
except (UnicodeDecodeError, tomllib.TOMLDecodeError):
    sys.exit(1)
sys.exit(1 if any(not re.fullmatch(r"[A-Za-z0-9_-]+", k) or "log-file" in k.lower() for k in keys(c)) else 0)' \
    <<< "${1-}" 2> /dev/null
}
rr_same_but_image() {   # rr_same_but_image A B: THE CONFIG COMPARE (the header): 0 the same but the image, or B is A
  # with THE LOG-FILE LINE added; else 1
  local ca cb na nb
  ca=$(rr_content "${1-}") && cb=$(rr_content "${2-}") || return 1
  na=$(printf '%s\n' "$ca" | grep -v '^runner-image = ') || :
  nb=$(printf '%s\n' "$cb" | grep -v '^runner-image = ') || :
  [ "$na" = "$nb" ] && return 0
  rr_logfile_free "$ca" || return 1
  na=$(printf '%s\n' "$na" | RR_K=$RR_LOGK awk '{ print } /^log-level = / && !n++ { print ENVIRON["RR_K"] }') || return 1
  [ "$na" = "$nb" ]
}

rr_read() {   # rr_read FILE MAX: ANOTHER USER'S FILE (the header), at most MAX bytes of it on stdout; 1 + RR_WHY
  local rc
  RR_WHY="it cannot be read"
  [[ ${2-} =~ ^[1-9][0-9]{0,6}$ ]] || { RR_WHY="rr_read: MAX is not a count: [${2-}]"; return 1; }
  python3 -I -c '
import errno, os, stat, sys
try:
    fd = os.open(sys.argv[1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_NOCTTY | os.O_CLOEXEC)
except OSError as e:
    sys.exit(3 if e.errno == errno.ENOENT else 4 if e.errno == errno.ELOOP else 5)
try:
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        sys.exit(4)
    want, data = int(sys.argv[2]), b""
    while len(data) < want:
        b = os.read(fd, want - len(data))
        if not b:
            break
        data += b
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
except OSError:
    sys.exit(5)
' "${1-}" "$2" < /dev/null
  rc=$?
  case $rc in
    0) RR_WHY= ;;
    3) RR_WHY="there is none" ;;
    4) RR_WHY="it is not a plain file" ;;
    *) RR_WHY="it cannot be read" ;;
  esac
  [ "$rc" = 0 ]
}

rr_record_read() {   # rr_record_read FILE: one build record, read ONCE into a private copy (rr_read: RUN_USER's file),
  # then only the copy (the header: rr_record): RR_REC_VERSION, RR_REC_DIGEST, RR_REC_RECIPE; 1 + RR_WHY
  local f=${1-} t size= nonul text
  local re=$'^format 1\nversion ([0-9]+\\.[0-9]+\\.[0-9]+)\ndigest (sha256:[0-9a-f]{64})\nrecipe ([0-9a-f]{64})\n$'
  RR_REC_VERSION= RR_REC_DIGEST= RR_REC_RECIPE=
  RR_WHY="it cannot be read"
  { install -d -m 700 "$RR_DIR" && t=$(mktemp "$RR_DIR/record.XXXXXX"); } 2> /dev/null || return 1
  if rr_read "$f" 1025 > "$t"; then
    size=$(wc -c < "$t"); nonul=$(tr -d '\000' < "$t" | wc -c); text=$(cat -- "$t"; echo .); text=${text%.}
  fi
  rm -f -- "$t"
  [ -n "$size" ] || { RR_WHY=${RR_WHY:-it cannot be read}; return 1; }
  RR_WHY="it is not 02-d1.sh's four lines (format 1, version, digest, recipe)"
  { [ "$size" -le 1024 ] && [ "$size" = "$nonul" ] && [[ $text =~ $re ]]; } || return 1
  RR_REC_VERSION=${BASH_REMATCH[1]} RR_REC_DIGEST=${BASH_REMATCH[2]} RR_REC_RECIPE=${BASH_REMATCH[3]}
}

rr_record() {   # rr_record DIR VERSION RECIPE: the build record of (VERSION, RECIPE) (the header); 1 + RR_WHY
  RR_RECORD=${1-}/${2-}-${3-}
  rr_record_read "$RR_RECORD" || return 1
  RR_WHY="it names version $RR_REC_VERSION"
  [ "$RR_REC_VERSION" = "${2-}" ] || return 1
  RR_WHY="it names another recipe"
  [ "$RR_REC_RECIPE" = "${3-}" ] || return 1
}

rr_record_of() {   # rr_record_of DIR DIGEST: the ONE build record whose digest is DIGEST (the header); 1 + RR_WHY
  local d=${1-} want=${2-} f n v= rc= rec= names=
  RR_RECORD= RR_REC_VERSION= RR_REC_DIGEST= RR_REC_RECIPE= RR_COUNT=0
  [[ $want =~ ^sha256:[0-9a-f]{64}$ ]] || { RR_WHY="[$want] is no sha256 digest"; return 1; }
  for f in "$d"/*; do
    n=${f##*/}
    [[ $n =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9a-f]{64}$ ]] || continue
    rr_record_read "$f" || continue
    [ "$n" = "$RR_REC_VERSION-$RR_REC_RECIPE" ] && [ "$RR_REC_DIGEST" = "$want" ] || continue
    RR_COUNT=$((RR_COUNT + 1)) rec=$f v=$RR_REC_VERSION rc=$RR_REC_RECIPE
    names+="${names:+, }$n"
  done
  RR_REC_VERSION= RR_REC_DIGEST= RR_REC_RECIPE=
  case $RR_COUNT in
    0) RR_WHY="no build record in $d names $want"; return 1 ;;
    1) RR_RECORD=$rec RR_REC_VERSION=$v RR_REC_DIGEST=$want RR_REC_RECIPE=$rc RR_WHY= ;;
    *) RR_WHY="$RR_COUNT build records in $d name $want ($names)"; return 1 ;;
  esac
}

rr_lock() {   # rr_lock ROLE [-n]: THE UPDATER LOCK (the header), for a command: it waits, and says so first. -n, for
  # a timer pass: it only tries, and returns 75 (no line) when another run holds it. First THE MODES (the header), by ROLE
  local role=${1-} dm sm top=${RR_LOCK%/*} rel d p
  case $role in
    run) dm=710 sm=640 ;;
    rs) dm=700 sm=600 ;;
    *) rr_no "rr_lock: the role is rs or run, not [$role]"; return 1 ;;
  esac
  rel=${top#"$HOME"/} d=$HOME
  IFS=/ read -r -a p <<< "$rel"
  for rel in "${p[@]}"; do    # each folder from the home to RR_LOCK's: one it makes is 0700, never the umask's mode
    d=$d/$rel
    [ -d "$d" ] || mkdir -m 700 -- "$d" 2> /dev/null || [ -d "$d" ] || { rr_no "cannot make $d"; return 1; }
  done
  { [ -e "$RR_LOCK" ] || (umask 077 && : >> "$RR_LOCK"); } && chmod 600 -- "$RR_LOCK" \
    || { rr_no "cannot make the updater lock $RR_LOCK, or set its mode"; return 1; }
  if [ -f "$RR_STATE" ] && [ ! -L "$RR_STATE" ]; then
    chmod "$sm" -- "$RR_STATE" || { rr_no "cannot set the mode of $RR_STATE"; return 1; }
  fi
  d=$HOME
  for rel in "${p[@]}"; do    # then the folders' modes (a parent made above is 0700: g+x gives it 0710), the state and
    d=$d/$rel                 # the lock in them set already
    if [ "$d" = "$top" ]; then chmod "$dm" -- "$d"
    elif [ "$role" = run ]; then chmod g+x -- "$d"
    else continue; fi || { rr_no "cannot set the mode of $d"; return 1; }
  done
  RR_STATE_MODE=$sm
  [ /dev/fd/9 -ef "$RR_LOCK" ] || exec 9>> "$RR_LOCK" || { rr_no "cannot open the updater lock $RR_LOCK"; return 1; }
  flock -n 9 && return 0
  [ "${2-}" != -n ] || return 75
  echo "WAIT another run holds the updater lock $RR_LOCK (a build, or a pass of the updater): waiting for it to end"
  flock 9 || { rr_no "cannot take the updater lock $RR_LOCK"; return 1; }
}

rr_held() {   # rr_held: THE UPDATER'S CHILD (the header): 0, or 1 and RR_WHY; prints nothing, waits for nothing
  local rc
  RR_WHY="fd 9 is not the updater lock $RR_LOCK (no holder handed it down)"
  [ /dev/fd/9 -ef "$RR_LOCK" ] || return 1
  flock -n -E 75 "$RR_LOCK" true 9>&- 2> /dev/null < /dev/null; rc=$?
  case $rc in
    75) ;;
    0) RR_WHY="nobody holds the updater lock $RR_LOCK (a fresh open of it took it at once)"; return 1 ;;
    *) RR_WHY="the updater lock $RR_LOCK cannot be tested by a fresh open (flock exited $rc)"; return 1 ;;
  esac
  RR_WHY="fd 9 is the updater lock, but another run holds it (fd 9 is no holder's)"
  flock -n 9 || return 1
  RR_WHY=
}
