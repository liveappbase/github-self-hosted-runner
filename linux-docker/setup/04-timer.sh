#!/usr/bin/env bash
# 04-timer.sh — the updater's TIMER, as EACH host user, RS_USER and RUN_USER (linux-docker/README.md, Install step 11):
#   ssh RS_USER@<host> 'bash ~/build/setup/04-timer.sh'       then the same line as RUN_USER
# It installs this release's config/runner-updater.service and config/runner-updater.timer (~/build/config/: the SAME
# two files for both users) as ~/.config/systemd/user/runner-updater.service and .timer, each 0644, then runs
# `systemctl --user daemon-reload`, then `systemctl --user enable --now runner-updater.timer`, and checks that the timer
# is enabled and active. From then on the user manager runs ~/bin/runner-updater pass every 10 minutes (the timer
# file's header says when, and why). It changes nothing of the updater itself: a fresh install is OFF for both users
# (PLAN D11), and a pass while OFF ends at once with exit 0, so the timer starts nothing until `runner-updater on`.
# IDEMPOTENT AND CONVERGING: a file there that is already this release's (a plain file, its bytes, mode 0644) is left
# as it is, not written again; any other (an older release's, one changed by hand, another mode, a symlink) is
# replaced by rename. The two systemctl calls run on every run, in that order: a run cut after a write is finished by
# the next. A release that changes either file needs this step again, as each user (after Install step 3).
# LINGER, read only: a user manager runs after the user's last logout, and so fires its timers, only with linger.
# This script never changes it (01-users.sh, as root, owns linger, Install step 2): `loginctl show-user USER -p
# Linger --value` must answer exactly `yes`, else REFUSE with the root line, and nothing is written. It refuses too,
# with nothing written, as a user other than RS_USER and RUN_USER, and when ~/bin/runner-updater (Install step 10's
# link, the timer's ExecStart) is not there.
# Ends with `04 DONE (USER)`. Exit: 0 done; 1 REFUSE or FAIL (the line says why).
# Stop the timer: `systemctl --user disable --now runner-updater.timer` (or keep it and run `runner-updater off`).
set -uo pipefail
umask 022
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
host_conf 04-timer.sh RS_USER RUN_USER
ok() { echo "OK   $*"; }
refuse() { echo "04-timer.sh: REFUSE $*"; exit 1; }
fail() { echo "FAIL $*"; exit 1; }
ME=$(id -un)
B=$HOME/build
U=$HOME/.config/systemd/user
NAMES="runner-updater.service runner-updater.timer"
echo "== the updater's timer, as $ME"
[ "$ME" = "${RS_USER}" ] || [ "$ME" = "${RUN_USER}" ] \
  || refuse "run me as ${RS_USER} or ${RUN_USER} (the updater's two users), not as $ME: nothing was written"
for n in $NAMES; do
  { [ -f "$B/config/$n" ] && [ ! -L "$B/config/$n" ]; } \
    || refuse "$B/config/$n is not a plain file: is this release's linux-docker/ ~/build (Install step 3)? Nothing was written"
done
[ -x "$HOME/bin/runner-updater" ] \
  || refuse "$HOME/bin/runner-updater is not there: the timer runs it (ExecStart=%h/bin/runner-updater pass). Do Install step 10 first, then this step again. Nothing was written"
# linger, read only (the header)
l=$(loginctl show-user "$ME" -p Linger --value 2>&1 < /dev/null)
[ "$l" = yes ] || refuse "$ME has no linger (loginctl show-user $ME -p Linger --value: [${l//[[:cntrl:]]/ }]): without it, $ME's user manager, and so its timer, stops at $ME's last logout. Linger is root's to give: from your checkout, run Install step 2 again (it gives both users linger, and changes nothing else that is in place): ssh root@<host> 'bash -s' < linux-docker/setup/01-users.sh, then this step again. Nothing was written"
ok "$ME has linger: its user manager runs from boot, with no login"
# the two files: this release's, or replaced by rename
[ -d "$U" ] || install -d -m 755 "$U" || fail "cannot make $U"
for n in $NAMES; do
  if [ -f "$U/$n" ] && [ ! -L "$U/$n" ] && [ "$(stat -c %a "$U/$n")" = 644 ] && cmp -s -- "$B/config/$n" "$U/$n"; then
    ok "$U/$n is this release's: left as it is"
  else
    { install -m 644 -- "$B/config/$n" "$U/.$n.new" && mv -f -- "$U/.$n.new" "$U/$n"; } \
      || { rm -f -- "$U/.$n.new"; fail "cannot install $U/$n"; }
    ok "installed $U/$n (0644)"
  fi
done
systemctl --user daemon-reload || fail "systemctl --user daemon-reload"
systemctl --user enable --now runner-updater.timer || fail "systemctl --user enable --now runner-updater.timer"
a=$(systemctl --user is-active runner-updater.timer 2>&1)
e=$(systemctl --user is-enabled runner-updater.timer 2>&1)
{ [ "$a" = active ] && [ "$e" = enabled ]; } || fail "runner-updater.timer is [$a] and [$e], not active and enabled"
ok "runner-updater.timer is enabled and active: ~/bin/runner-updater pass every 10 minutes (systemctl --user list-timers runner-updater.timer; its passes: journalctl --user -u runner-updater)"
echo "04 DONE ($ME)"
