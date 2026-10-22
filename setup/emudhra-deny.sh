#!/bin/zsh -f
# emudhra-deny.sh — deny, in this Mac's ADMIN trust settings, every anchor of Apple's whose public key is one of the
# three that homebrew-core a2ee7ae08c6 excludes (the eMudhra incident: its intermediate keys were compromised). The
# deny reaches every client of Apple's Security framework on this host: runscaler (Go), Tart and nscurl (URLSession),
# Swift. It does NOT reach /usr/bin/curl: its LibreSSL asks Apple only when its own bundle (/etc/ssl/cert.pem, which
# stays unfiltered on the host) fails. Design and the before/after checks: docs/operations.md ("The host eMudhra
# deny"). This is this fleet's hand step, NOT an adopter step of v0.1, and no release asset holds its line.
# The ADMIN runs it in the admin's own session with ONE line that setup/render-run-line renders from a copy you
# reviewed, with the UNCHANGED template setup/02-wall.run-line: that line copies this file to a root-owned 0600 file,
# runs it with /bin/zsh -f only if its sha256 is the reviewed copy's, and removes it, even on Ctrl-C. macOS may ask for
# an administrator's name and password once per certificate it changes. Its rollback is setup/emudhra-undeny.sh.
# It reads NOTHING from ci's home: the certificates come from Apple's anchor set (the three sources below), chosen by
# the SPKI SHA-256 literals in this file; its scratch is its own mktemp -d (0700). Base-macOS tools only (/usr/bin/openssl
# is LibreSSL; there is no timeout tool on a stock Mac).
# In this order; it changes nothing before step 4:
#   1. It stops unless it runs as root.
#   2. It reads the three sources and prints each one's counts. A certificate LibreSSL cannot parse (Apple's ML-DSA
#      anchors) is printed "cannot parse", never a refusal. It refuses when the keychain or Anchors/ is below its floor.
#   3. It prints every certificate with an excluded key: its name, SPKI, SHA-1, SHA-256 and the sources that hold it.
#      It refuses when there is none (the store changed: report it).
#   4. For each one that is not denied yet: security add-trusted-cert -d -r deny -k /Library/Keychains/System.keychain
#      (-k also adds a copy of it to System.keychain; without a trust setting that copy is inert). One already denied
#      is skipped, so a re-run asks for no password.
#   5. It checks its own result: the admin trust settings (trust-settings-export -d) hold a deny (result 3, for every
#      policy) for each one, and verify-cert -p basic -L exits non-zero for each one and 0 for the three control roots.
# It prints "denied", "already denied" or "FAILED" per certificate. Exit 0: each excluded anchor is denied and each
# control root is trusted. Exit 1: "emudhra-deny: REFUSE <reason>" (nothing changed), or a FAILED line (a partial
# result: keep the session open, run the undeny line, report). Exit 130, interrupted (Ctrl-C), with one line on stderr:
# before step 4 "interrupted: nothing changed"; from step 4 on "INTERRUPTED …: the result is not checked" (run the
# deny line again, which skips what is denied, or the undeny line).
WANT_UID=0
# homebrew-core a2ee7ae08c6, ca-certificates.rb, EXCLUDED_SPKI_HASHES. Its source line:
# "Exclude AAA Certificate Services and the emSign G3 roots by their public keys."
EXCLUDED_SPKI=(
  bd153ed7b0434f6886b17bce8bbe84ed340c7132d702a8f4fa318f756ecbd6f3  # AAA Certificate Services
  c619e4780ed8e0abeda24ad732567de4383a7ea941338f6d1a7d1b49ac792fe9  # emSign Root TLS CA - G3
  8d417db2dd8bf5e3084d1e3f196d583849d81bdd4c00c70b9d39369e96b8c782  # emSign ECC Root CA - G3
)
# The control roots (never denied; verify-cert must stay 0), by the SHA-256 of the certificate in KC
CONTROL_ROOTS=(
  e793c9b02fd8aa13e21c31228accb08119643b749c898964b1746d46c3d4cbd2  # USERTrust RSA Certification Authority
  4ff460d54b9c86dabfbcfc5712e0400d2bed3fbc4d4fbdaa86e06adcd2a9ad7a  # USERTrust ECC Certification Authority
  96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6  # ISRG Root X1
)
KC=/System/Library/Keychains/SystemRootCertificates.keychain
ANCHORS=/System/Library/Security/Certificates.bundle/Contents/Resources/Anchors
ASSET_ROOTS=(/System/Library/AssetsV2/com_apple_MobileAsset_PKITrustStore /private/var/run/com.apple.security.cryptexd/mnt /System/Volumes/Preboot/Cryptexes)
KC_FLOOR=100
ANCHORS_FLOOR=200
OSSL=/usr/bin/openssl
SEC=/usr/bin/security
PLUTIL=/usr/bin/plutil

set -u
umask 077
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export LC_ALL=C
TAB=$'\t'
refuse() { print -u2 -r -- "emudhra-deny: REFUSE $*"; exit 1 }
say() { print -r -- "emudhra-deny: $*" }

# 1. root
[[ $(/usr/bin/id -u) == $WANT_UID ]] || refuse "must run as root: only through the rendered line, in the admin's own session"
w=$(/usr/bin/mktemp -d /private/tmp/emudhra-deny.XXXXXX) || refuse "mktemp failed"
trap '/bin/rm -rf -- "${w:?}"' EXIT
changing=0   # 1 from step 4 on: an interrupt then leaves a result that no step checked
interrupted() {
  if (( changing )); then
    print -u2 -r -- "emudhra-deny: INTERRUPTED while writing the denies: the result is not checked." \
      "Run the deny line again (it skips what is already denied), or run the undeny line."
  else
    print -u2 -r -- "emudhra-deny: interrupted: nothing changed"
  fi
  exit 130
}
trap interrupted INT TERM HUP
/bin/chmod 700 $w || refuse "chmod of $w failed"

certinfo() { # FILE FORM -> REPLY = "SPKI<TAB>SHA256<TAB>SUBJECT"; return 1 when LibreSSL cannot parse the certificate
  # or hash its key (never the hash of empty input). The SPKI pipeline is homebrew-core's.
  local out l sub= fp=
  out=$($OSSL x509 -inform $2 -in $1 -noout -subject -fingerprint -sha256 2>/dev/null) || return 1
  for l in ${(f)out}; do
    case $l in
      (subject=*) sub=${${l#subject=}# } ;;
      (*Fingerprint=*) fp=${(L)${${l#*=}//:/}} ;;
    esac
  done
  [[ $fp =~ '^[0-9a-f]{64}$' ]] || return 1
  /bin/rm -f $w/pub $w/der
  $OSSL x509 -inform $2 -in $1 -noout -pubkey > $w/pub 2>/dev/null || return 1
  $OSSL pkey -pubin -in $w/pub -outform der -out $w/der 2>/dev/null && [[ -s $w/der ]] || return 1
  out=$($OSSL dgst -sha256 -r $w/der 2>/dev/null) && [[ ${out[1,64]} =~ '^[0-9a-f]{64}$' ]] || return 1
  REPLY=${out[1,64]}$TAB$fp$TAB$sub
}
read_source() { # LABEL FORM FILE… -> $w/LABEL.tsv "SPKI<TAB>SHA256<TAB>SUBJECT<TAB>FILE"; n_read, n_hashed; prints
  # "cannot parse" lines
  local label=$1 form=$2 f; shift 2
  : > $w/$label.tsv
  n_read=0 n_hashed=0
  for f in "$@"; do
    n_read=$(( n_read + 1 ))
    if certinfo $f $form; then print -r -- "$REPLY$TAB$f" >> $w/$label.tsv; n_hashed=$(( n_hashed + 1 ))
    else say "  cannot parse: $f"; fi
  done
}
read_keychain() { # LABEL KEYCHAIN -> its certificates, split into $w/LABEL/c0001.pem …, then read_source
  /bin/mkdir -p $w/$1 || refuse "mkdir failed"
  $SEC find-certificate -a -p $2 > $w/$1.pem 2>/dev/null || return 1
  /usr/bin/awk -v d=$w/$1 '/-----BEGIN CERTIFICATE-----/ {n++; f=sprintf("%s/c%04d.pem", d, n); p=1} p {print > f}
    /-----END CERTIFICATE-----/ {if (p) close(f); p=0}' $w/$1.pem || return 1
  read_source $1 pem $w/$1/c*.pem(N)
}

# 2. the three sources of Apple's anchor set
sources=()
read_keychain kc $KC || refuse "cannot read $KC"
say "$KC: $n_read certificates, $n_hashed hashed"
(( n_hashed >= KC_FLOOR )) || refuse "$KC: $n_hashed hashed, below the floor $KC_FLOOR: the store looks wrong; nothing changed"
sources+=(kc)
read_source anchors der $ANCHORS/*.cer(N)
say "$ANCHORS: $n_read certificates, $n_hashed hashed"
(( n_hashed >= ANCHORS_FLOOR )) || refuse "$ANCHORS: $n_hashed hashed, below the floor $ANCHORS_FLOOR: the store looks wrong; nothing changed"
sources+=(anchors)
n=0
for a in ${(f)"$(for r in $ASSET_ROOTS; do [[ -d $r ]] && /usr/bin/find $r -name SystemRootCertificates.keychain -type f 2>/dev/null; done)"}; do
  n=$(( n + 1 ))
  read_keychain asset$n $a || refuse "cannot read the trust-store asset $a"
  v=$($PLUTIL -extract VersionNumber raw -o - ${a:h}/AssetVersion.plist 2>/dev/null)
  say "$a (version ${v:-unknown}): $n_read certificates, $n_hashed hashed"
  (( n_read > 0 )) || refuse "the trust-store asset $a holds no certificate: nothing changed"
  sources+=(asset$n)
done
(( n )) || say "PKITrustStore asset: none"

# 3. the certificates with an excluded key: the union of the sources, one per certificate
typeset -A src file sub spk
for s in $sources; do
  for l in ${(f)"$(<$w/$s.tsv)"}; do
    q=("${(@ps:\t:)l}")   # SPKI SHA256 SUBJECT FILE
    (( ${EXCLUDED_SPKI[(Ie)$q[1]]} )) || continue
    if (( ${+src[$q[2]]} )); then src[$q[2]]+=" $s"
    else src[$q[2]]=$s; file[$q[2]]=$q[4]; sub[$q[2]]=$q[3]; spk[$q[2]]=$q[1]; fi
  done
done
(( ${#src} )) || refuse "found no anchor with an excluded key in Apple's anchor set: the store changed — report it; nothing changed"
typeset -A sha1 pem
for h in ${(ko)src}; do
  form=pem; [[ $src[$h] == anchors* ]] && form=der
  pem[$h]=$w/deny-$h.pem
  $OSSL x509 -inform $form -in $file[$h] -outform pem -out $pem[$h] 2>/dev/null || refuse "cannot convert $file[$h]"
  o=$($OSSL x509 -in $pem[$h] -noout -fingerprint -sha1 2>/dev/null) || refuse "cannot read the SHA-1 of $file[$h]"
  sha1[$h]=${(U)${${o#*=}//:/}}
  say "excluded: $sub[$h]"
  say "  SPKI $spk[$h], SHA-1 $sha1[$h], SHA-256 $h; in: $src[$h]"
done

ts_export() { # -> $w/ts.plist (absent when the admin domain holds no trust settings); return 1 when unreadable
  local out
  /bin/rm -f $w/ts.plist
  out=$($SEC trust-settings-export -d $w/ts.plist 2>&1) && return 0
  /bin/rm -f $w/ts.plist
  [[ $out == *'No Trust Settings'* ]] && return 0
  REPLY=${out%%$'\n'*}; return 1
}
deny_state() { # SHA1 -> REPLY: "deny" (every admin entry of the certificate is result 3, and one applies to every
  # policy or to SSL) | "none" (no entry) | "other: …"
  local f=$w/ts.plist k key= i r pn n=0 ssl=0 bad=
  [[ -f $f ]] || { REPLY=none; return }
  for k in ${(f)"$($PLUTIL -p $f | /usr/bin/grep -oE '"[0-9A-Fa-f]{40}" =>' | /usr/bin/tr -d '" =>')"}; do
    [[ ${(U)k} == ${(U)1} ]] && key=$k
  done
  [[ -n $key ]] || { REPLY=none; return }
  for (( i = 0; i < 64; i++ )); do
    $PLUTIL -extract trustList.$key.trustSettings.$i xml1 -o - $f > /dev/null 2>&1 || break
    n=$(( n + 1 ))
    r=$($PLUTIL -extract trustList.$key.trustSettings.$i.kSecTrustSettingsResult raw -o - $f 2>/dev/null) || r=1
    if $PLUTIL -extract trustList.$key.trustSettings.$i.kSecTrustSettingsPolicy xml1 -o - $f > /dev/null 2>&1; then
      pn=$($PLUTIL -extract trustList.$key.trustSettings.$i.kSecTrustSettingsPolicyName raw -o - $f 2>/dev/null)
      [[ $r == 3 && ${(L)pn} == *ssl* ]] && ssl=1
    else
      [[ $r == 3 ]] && ssl=1
    fi
    [[ $r == 3 ]] || bad+=" entry $i has result $r;"
  done
  if (( n == 0 )); then REPLY="other: an entry without a trust setting (that means: trusted as a root)"
  elif [[ -n $bad ]]; then REPLY="other:$bad"
  elif (( ! ssl )); then REPLY="other: every deny names a policy that is not SSL"
  else REPLY=deny; fi
}
vc() { # PEM -> REPLY = verify-cert's "Verify Result" line, else its last line; returns its exit status
  local out rc; local -a ls m
  out=$($SEC verify-cert -c $1 -p basic -L 2>&1); rc=$?
  ls=(${(f)out}); m=(${(M)ls:#*Verify Result*}); REPLY=${m[1]:-${ls[-1]-}}
  return $rc
}

# 4. the deny, for each one not denied yet
ts_export || refuse "cannot read the admin trust settings ($REPLY): nothing changed"
typeset -A was
changing=1
for h in ${(ko)src}; do
  deny_state $sha1[$h]; was[$h]=$REPLY
  if [[ $REPLY == deny ]]; then say "$sub[$h]: already denied"; continue; fi
  say "$sub[$h]: writing the deny (macOS may ask for an administrator's name and password)"
  out=$($SEC add-trusted-cert -d -r deny -k /Library/Keychains/System.keychain $pem[$h] 2>&1); rc=$?
  (( rc == 0 )) || say "$sub[$h]: security add-trusted-cert exited $rc: ${out%%$'\n'*}"
done

# 5. its own result
failed=0
ts_export || { say "FAILED: cannot read the admin trust settings after the deny ($REPLY)"; failed=1 }
for h in ${(ko)src}; do
  deny_state $sha1[$h]; st=$REPLY
  vc $pem[$h]; rc=$?
  if [[ $st == deny ]] && (( rc != 0 )); then
    if [[ $was[$h] == deny ]]; then say "already denied: $sub[$h] (SHA-1 $sha1[$h]); verify-cert exits $rc: $REPLY"
    else say "denied: $sub[$h] (SHA-1 $sha1[$h]); verify-cert exits $rc: $REPLY"; fi
  else
    say "FAILED: $sub[$h] (SHA-1 $sha1[$h]): admin trust setting '$st'; verify-cert exits $rc: $REPLY"; failed=1
  fi
done
typeset -A ctl
for l in ${(f)"$(<$w/kc.tsv)"}; do
  q=("${(@ps:\t:)l}")
  (( ${CONTROL_ROOTS[(Ie)$q[2]]} )) && ctl[$q[2]]=$q[4]
done
for h in $CONTROL_ROOTS; do
  if (( ! ${+ctl[$h]} )); then say "FAILED: control root $h is not in $KC: the result has no control"; failed=1; continue; fi
  vc $ctl[$h]; rc=$?; why=$REPLY   # verify-cert's own line, before certinfo sets REPLY
  n=$h; certinfo $ctl[$h] pem && n=${REPLY##*$TAB}
  if (( rc == 0 )); then say "control trusted: $n; verify-cert exits 0"
  else say "FAILED: control $n: verify-cert exits $rc: $why (a control root must stay trusted)"; failed=1; fi
done
(( failed )) && { say "FAILED: a partial or wrong result (above). Keep this session open and run the undeny line."; exit 1 }
say "done: every excluded anchor is denied in the admin trust settings; every control root is trusted"
exit 0
