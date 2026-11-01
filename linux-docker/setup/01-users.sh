#!/usr/bin/env bash
# 01-users.sh — the ROOT step of the Linux Docker CI host: its two users. As root (linux-docker/README.md):
#   ssh root@<host> 'bash -s' < linux-docker/setup/01-users.sh
# Undo: 01-users-undo.sh. The two users (their names are the host config's RUN_USER and RS_USER):
#   RS_USER   runs ONLY runscaler (a systemd user unit) and holds the token. No daemon. In group RUN_USER (D1's socket).
#   RUN_USER  runs the rootless dockerd D1 (runner containers + the local registry). Holds no secret.
# RE-RUNNABLE TO COMPLETION: the marker $MARK/r1-created-<user> is written BEFORE useradd, once `id` says the user is
# absent, so a useradd that fails half-way still leaves a MARKED user. Every run finishes the set-up of every MARKED user
# that exists (home, group, keys, linger); a run cut off anywhere is finished by the next run. A failed useradd stops the
# creation of further users (RS_USER needs RUN_USER's group). A user that exists WITHOUT a marker was not made here: this
# step stops there, and changes it never.
# ROOT NEVER WRITES INSIDE A USER'S HOME: the ssh keys (root's own authorized_keys) are written AS the user (runuser),
# and a `.ssh` that is a symlink is a FAIL with nothing written.
# ORDER: users, group, keys, lock rule, linger LAST (a user manager keeps the groups it started with), and RS_USER gets
# linger only once it has group RUN_USER.
# Ends with CHECK lines; exit 1 when any check fails. Touches no unmarked user, no service, sshd or Docker setting.
# KNOWN LIMIT (kept as it runs on the first host): the group check compares the SORTED group list of RS_USER with
# "RS_USER RUN_USER", so it passes only when RS_USER sorts before RUN_USER (host.conf.example's names do).
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
host_conf 01-users.sh RUN_USER RS_USER
cd / || exit 1
fail=0
ok()  { echo "OK   $*"; }
bad() { echo "FAIL $*"; fail=1; }
MARK=/var/lib/liveapp-ci
TMPFILES=/etc/tmpfiles.d/liveapp-runner-lock.conf
install -d -m 0755 -o root -g root "$MARK"
has_run_group() { [[ " $(id -nG ${RS_USER} 2>/dev/null) " == *" ${RUN_USER} "* ]]; }

# 1. create (RUN_USER first, so its group exists for RS_USER); the marker BEFORE each useradd
for u in ${RUN_USER} ${RS_USER}; do
  if id "$u" >/dev/null 2>&1; then
    [ -e "$MARK/r1-created-$u" ] || { bad "$u exists and was not made by R1: no further user is made"; break; }
    echo "note $u was made by R1: finishing its set-up"; continue
  fi
  touch "$MARK/r1-created-$u" || { bad "cannot write $MARK/r1-created-$u: no user made"; break; }
  useradd -m -s /bin/bash "$u" || { bad "useradd $u failed: no further user is made (fix the cause, then run R1 again)"; break; }
done
marked=""; for u in ${RUN_USER} ${RS_USER}; do [ -e "$MARK/r1-created-$u" ] && id "$u" >/dev/null 2>&1 && marked="$marked $u"; done

# 2. finish the set-up of every MARKED user (each step idempotent)
for u in $marked; do
  h=/home/$u
  [ -e "$h" ] || mkhomedir_helper "$u" 0027 || bad "$u has no home and mkhomedir_helper failed"
  if [ -L "$h" ] || [ ! -d "$h" ]; then bad "$u: $h is not a plain directory"; continue; fi
  chmod 0750 "$h"
  if runuser -u "$u" -- test -e "$h/.ssh/authorized_keys"; then :
  elif runuser -u "$u" -- test -L "$h/.ssh"; then bad "$u: $h/.ssh is a symlink: no key written"
  else runuser -u "$u" -- sh -c 'umask 077 && mkdir -p "$1/.ssh" && cat > "$1/.ssh/authorized_keys"' _ "$h" < /root/.ssh/authorized_keys \
    || bad "$u: writing $h/.ssh/authorized_keys as $u"
  fi
done
case " $marked " in *" ${RS_USER} "*) has_run_group || usermod -aG ${RUN_USER} ${RS_USER} || bad "usermod -aG ${RUN_USER} ${RS_USER}" ;; esac

# 3. runscaler's lock file exists from boot, owned by RS_USER (fs.protected_regular=2: a /tmp/runner.lock another user
#    made first would refuse runscaler's O_CREAT open for good). runscaler itself sets it to 0666 when it starts.
#    Only once RS_USER exists (a rule naming an absent user would outlive an undo).
case " $marked " in
  *" ${RS_USER} "*)
    # `x`: never AGED away by the host's `q /tmp … 10d` clean while a long-running runscaler holds it (systemd 259
    # accepts f + x on one path: measured by a dry run)
    [ -e "$TMPFILES" ] || printf '# runscaler lock (plan PLAN-2026-10-21-linux-runscaler §2.3): exists from boot, owned by '"${RS_USER}"', never aged\nf /tmp/runner.lock 0600 '"${RS_USER}"' '"${RS_USER}"' -\nx /tmp/runner.lock\n' > "$TMPFILES"
    systemd-tmpfiles --create "$TMPFILES" || bad "systemd-tmpfiles --create $TMPFILES" ;;
  *) bad "${RS_USER} does not exist: no lock rule written" ;;
esac

# 4. linger LAST, for every marked user; RS_USER only once it has group RUN_USER
for u in $marked; do
  if [ "$u" = ${RS_USER} ] && ! has_run_group; then bad "${RS_USER} lacks group ${RUN_USER}: no linger (its user manager would start without the group)"; continue; fi
  loginctl enable-linger "$u" || bad "loginctl enable-linger $u"
done

# CHECKS
want_groups() { [ "$(id -nG "$1" 2>/dev/null | tr ' ' '\n' | sort | paste -sd' ' -)" = "$2" ]; }
want_groups ${RS_USER} "${RS_USER} ${RUN_USER}" && ok "${RS_USER} groups = ${RS_USER} ${RUN_USER}" || bad "${RS_USER} groups = [$(id -nG ${RS_USER} 2>&1)]"
want_groups ${RUN_USER} "${RUN_USER}" && ok "${RUN_USER} groups = ${RUN_USER}" || bad "${RUN_USER} groups = [$(id -nG ${RUN_USER} 2>&1)]"
m=$(getent group ${RUN_USER} | cut -d: -f4); [ "$m" = ${RS_USER} ] && ok "group ${RUN_USER} members = ${RS_USER} (D1 socket's access list)" || bad "group ${RUN_USER} members = [$m]"
rootsock=absent; [ -S /var/run/docker.sock ] && rootsock=present
units=$(systemctl is-active docker.service docker.socket 2>/dev/null | paste -sd' ' -)
for u in ${RS_USER} ${RUN_USER}; do
  [ -e "$MARK/r1-created-$u" ] && ok "$u made by R1" || bad "$u was not made by R1 (an existing user of that name)"
  [ -e "/var/lib/systemd/linger/$u" ] && ok "$u linger" || bad "$u linger"
  for f in subuid subgid; do grep -q "^$u:" "/etc/$f" && ok "$u $f $(grep "^$u:" "/etc/$f" | cut -d: -f2-)" || bad "$u $f"; done
  m=$(stat -c '%a %U:%G' "/home/$u" 2>&1); [ "$m" = "750 $u:$u" ] && ok "$u home $m" || bad "$u home $m"
  k=$(stat -c '%a %U' "/home/$u/.ssh/authorized_keys" 2>/dev/null); [ "$k" = "600 $u" ] && ok "$u authorized_keys $k" || bad "$u authorized_keys [$k]"
  uid=$(id -u "$u" 2>/dev/null); act=""
  for _ in 1 2 3 4 5 6 7 8 9 10; do act=$(systemctl is-active "user@$uid.service"); [ "$act" = active ] && break; sleep 1; done
  [ "$act" = active ] && ok "$u user manager active" || bad "$u user manager [$act]"
  out=$(sudo -u "$u" docker -H unix:///var/run/docker.sock info 2>&1); rc=$?
  if [ "$rc" = 0 ]; then bad "$u REACHES the root docker daemon"
  elif [ "$rootsock" = absent ] && [ "$units" = "inactive inactive" ]; then ok "$u: no root docker daemon on this host"
  else case "$out" in *"permission denied"*) ok "$u refused by the root docker daemon (permission denied)" ;; *) bad "$u root daemon: rc=$rc units=[$units] [${out:0:100}]" ;; esac
  fi
done
# RS_USER's user manager runs WITH group RUN_USER (else runscaler cannot reach D1's socket)
gid=$(getent group ${RUN_USER} | cut -d: -f3)
pid=$(systemctl show -p MainPID --value "user@$(id -u ${RS_USER} 2>/dev/null).service" 2>/dev/null)
grps=$(grep -E "^Groups:" "/proc/$pid/status" 2>/dev/null)
if [ -n "$gid" ]; then
  case " ${grps#Groups:} " in *[[:space:]]"$gid"[[:space:]]*) ok "${RS_USER} user manager has group ${RUN_USER} ($gid)" ;; *) bad "${RS_USER} user manager lacks group ${RUN_USER} ($gid): [$grps]" ;; esac
else bad "no group ${RUN_USER}"; fi
# subuid and subgid ranges do not overlap (all users; a range inside a larger earlier one counts)
for f in subuid subgid; do
  ov=$(awk -F: '{print $2, $2+$3-1, $1}' "/etc/$f" | sort -n | awk 'NR>1 && $1<=me {print "overlap: " mn " and " $3} $2>me {me=$2; mn=$3} NR==1 {me=$2; mn=$3}')
  [ -z "$ov" ] && ok "$f ranges do not overlap" || bad "$f $ov"
done
# the lock file: owned by RS_USER; 0600 from tmpfiles, 0666 once runscaler has started (its own chmod)
grep -qx 'x /tmp/runner.lock' "$TMPFILES" 2>/dev/null && ok "$TMPFILES excludes /tmp/runner.lock from /tmp's aging" || bad "$TMPFILES lacks 'x /tmp/runner.lock'"
l=$(stat -c '%a %U:%G' /tmp/runner.lock 2>/dev/null)
case $l in "600 ${RS_USER}:${RS_USER}"|"666 ${RS_USER}:${RS_USER}") ok "/tmp/runner.lock $l" ;; *) bad "/tmp/runner.lock [$l]" ;; esac
if [ "$(systemctl --user -M ${RS_USER}@ is-active runscaler 2>/dev/null)" = active ]; then
  # the pool runs: the lock's holder (from /proc/locks, as runner-start reads it) must be runscaler itself
  main=$(systemctl --user -M ${RS_USER}@ show -p MainPID --value runscaler 2>/dev/null)
  s=$(stat -c '%d %i' /tmp/runner.lock 2>/dev/null); d=${s% *}; ino=${s#* }; holder=""
  [ -n "$s" ] && holder=$(awk -v k="$(printf '%02x:%02x:%s' $(( (d >> 8) & 0xfff )) $(( (d & 0xff) | ((d >> 12) & 0xfff00) )) "$ino")" '$2 == "FLOCK" && $6 == k {print $5; exit}' /proc/locks)
  [ -n "$holder" ] && [ "$holder" = "$main" ] && ok "/tmp/runner.lock is held by the running runscaler (pid $main)" || bad "/tmp/runner.lock holder [$holder] is not runscaler's main pid [$main]"
else
  sudo -u ${RS_USER} flock -n /tmp/runner.lock true && ok "${RS_USER} can take /tmp/runner.lock (runscaler can start)" || bad "${RS_USER} cannot take /tmp/runner.lock"
fi
[ "$fail" = 0 ] && echo "R1 DONE" || { echo "R1 HAS FAILURES: read each FAIL line. A re-run finishes a run that was cut off; it does not change a user R1 did not make, or a subuid range."; exit 1; }
