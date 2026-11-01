#!/usr/bin/env bash
# 01-users-undo.sh — removes ONLY what 01-users.sh made (users that carry its marker, the lock rule). As root:
#   ssh root@<host> 'bash -s' < linux-docker/setup/01-users-undo.sh
# BEFORE it, in this order: move every repository's jobs to another runner first; as RS_USER
# `systemctl --user disable --now runscaler` (runscaler holds its lock while it runs, and a delete is refused then);
# `runner-start delete NAME` for each set ("Deleted …", a second run "No runner scale set named …") — with the config
# that NAMES each set, only for a config file that exists (a missing one is a named skip), and ANY other answer stops
# the undo here; remove the token file; revoke the token on GitHub; as RUN_USER `systemctl --user disable --now docker`
# (D1 and the registry).
# PRE-FLIGHT, which changes nothing — it REFUSES (exit 1) while, for a marked user: runscaler or docker is active in its
# user manager; it has a process other than that manager (systemd, (sd-pam), dbus-daemon); a process runs in its
# subuid range (a container); or a token file exists under ~RS_USER/.config/runner (the scale sets may still be
# registered). A user without the marker is never touched. Then RS_USER FIRST (the only member of group RUN_USER), then
# RUN_USER; the FIRST failure stops it (exit 1, no DONE line). The lock rule and /tmp/runner.lock go only once RS_USER
# does not exist. The host config stays (root removes /etc/liveapp-ci by hand: linux-docker/README.md).
set -uo pipefail
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
host_conf 01-users-undo.sh RUN_USER RS_USER
cd / || exit 1
MARK=/var/lib/liveapp-ci
refuse() { echo "REFUSE $*"; echo "R1-UNDO REFUSED: nothing was changed"; exit 1; }
die() { echo "FAIL $*"; echo "R1-UNDO STOPPED at this step: the steps above it are done, nothing after it"; exit 1; }
ok() { echo "OK   $*"; }

users=""; for u in ${RS_USER} ${RUN_USER}; do [ -e "$MARK/r1-created-$u" ] && users="$users $u"; done
[ -n "$users" ] || refuse "no user carries R1's marker in $MARK"
for u in $users; do
  id "$u" >/dev/null 2>&1 || continue
  for unit in runscaler docker; do
    st=$(systemctl --user -M "$u@" is-active "$unit" 2>/dev/null)
    case $st in active|activating|deactivating|reloading|refreshing) refuse "$u: $unit is $st (stop it first)" ;; esac
  done
  p=$(ps -u "$u" -o pid=,comm= | awk '$2 != "systemd" && $2 != "(sd-pam)" && $2 != "dbus-daemon"' | head -5)   # the user manager's own processes
  [ -z "$p" ] || refuse "$u has processes: $(echo $p)"
  for f in subuid subgid; do
    r=$(grep "^$u:" "/etc/$f" | head -1 | cut -d: -f2-)
    [ -n "$r" ] || continue
    s=${r%%:*}; n=${r#*:}
    col=uid; [ "$f" = subgid ] && col=gid
    q=$(ps -eo "$col=,pid=,comm=" | awk -v s="$s" -v e="$((s + n - 1))" '$1 >= s && $1 <= e' | head -5)
    [ -z "$q" ] || refuse "$u: processes in its $f range $s-$((s + n - 1)) (a container?): $(echo $q)"
  done
done
t=$(ls /home/${RS_USER}/.config/runner/token-* 2>/dev/null)
[ -z "$t" ] || refuse "a token file exists ($t): delete the scale sets first, then the token (plan §3 R1-UNDO)"
ok "pre-flight: nothing of$users runs, no token file"

for u in ${RS_USER} ${RUN_USER}; do
  [ -e "$MARK/r1-created-$u" ] || { echo "skip $u: no R1 marker"; continue; }
  if id "$u" >/dev/null 2>&1; then
    loginctl disable-linger "$u" || die "loginctl disable-linger $u"
    loginctl terminate-user "$u" 2>/dev/null
    for _ in $(seq 1 30); do pgrep -u "$u" >/dev/null || break; sleep 1; done
    pgrep -u "$u" >/dev/null && die "$u still has processes after 30 s: $(pgrep -u "$u" | paste -sd' ' -)"
    userdel -r "$u" 2>&1 | grep -v 'mail spool'
    id "$u" >/dev/null 2>&1 && die "userdel $u"
    [ ! -e "/home/$u" ] || die "userdel $u left /home/$u"
  fi
  getent group "$u" >/dev/null && die "group $u still exists after userdel (a member left in it?): $(getent group "$u")"
  sed -i "/^$u:/d" /etc/subuid /etc/subgid || die "removing $u from /etc/subuid and /etc/subgid"
  rm -f "$MARK/r1-created-$u" || die "removing the marker of $u"
  ok "removed $u"
done
# the lock rule names RS_USER: it goes whenever RS_USER is gone (also after an R1 that never made RS_USER)
if ! id ${RS_USER} >/dev/null 2>&1; then
  rm -f /etc/tmpfiles.d/liveapp-runner-lock.conf /tmp/runner.lock || die "removing the lock rule and /tmp/runner.lock"
  ok "removed the lock rule and /tmp/runner.lock"
fi
rmdir "$MARK" 2>/dev/null
echo "R1-UNDO DONE"
