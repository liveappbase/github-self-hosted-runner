# Operations

Every command runs as `ci` (over SSH or in ci's Terminal) unless it says otherwise. Run the tools by their absolute paths. The reasons behind each step are in [design.md](design.md).

## Planned maintenance (the idle runbook)

A stop kills the jobs still running at its end ([../SECURITY.md](../SECURITY.md)), so stop only an idle host:

1. Check that the host is idle: `curl -s http://127.0.0.1:8080/healthz` shows `in_use` 0 on two reads 30 seconds apart, and no job for the host's label is queued on GitHub.
2. `/Users/ci/bin/runner-disable` — it waits until runscaler has stopped and the lock is free. While the flag is absent, a restart cannot start runscaler again.
3. Do the work (a macOS update or security response, an update of this repository, an image rebuild, a token rotation, …). Restart the Mac if the work needs it (Apple menu → Restart, in the admin's Screen Sharing session; never log `ci` out).
4. `/Users/ci/bin/wall-files-check` — `FILES red` is a STOP: find why before anything else (an update of the root files needs the release's root line). `STAMP stale` means `/Users/ci/bin/wall-check` must run.
   After a macOS update or security response, run `/Users/ci/bin/wall-check` even when it says `STAMP current`: the stamp records the macOS build it was proven on, and runner-enable refuses until a wall-check on the new build has passed.
5. `/Users/ci/bin/runner-enable`. A job that GitHub gave the host in the gap died; re-run it.

Never run `runner doctor --fix` or a second `runner run` while the agent is enabled.

## Rebuilding the image

When: the host moved onto a release that pins a new runner or base image (README, "Update", step 5). With either `disable-update` value, the runner in the image does not keep itself current ([../config/config.toml.example](../config/config.toml.example)), so this rebuild is the only dependable way a new runner reaches the jobs.

- Is the image behind? Compare a job log's `Current runner version` with the newest release of actions/runner.
- The deadline: `gh api repos/<owner>/<repo>/actions/runners/deprecations/<version>` prints `runtime_deprecates_at`.
- After that date, by runscaler 0.10.0's README (not measured here): a runner on that version is refused on its first poll with `Runner version vX.Y.Z is deprecated and cannot receive messages` and exits, and the jobs stay queued. On Tart, runscaler's start-up check logs the refusal in `/Users/ci/Library/Logs/mac-runner/runscaler.log`, not in a job. Queued jobs mean a retired runner only when that line is there; "Outage recovery" lists the other causes.
- What to do: before the deadline, move the host onto a release that pins a newer runner (README, "Update"). If no release pins one yet, ask for one in this repository's issues.

1. The idle runbook steps 1–2.
2. `/Users/ci/bin/golden-build` — prints `DONE: liveapp-mac-golden-<yyyymmdd>`. Its output is also kept in `/Users/ci/Library/Logs/mac-runner/golden-<yyyymmdd>.log`. The date is today's, read once at the start, so a build across midnight keeps one date for every name; `--date YYYYMMDD` (a real date) names another day. Its start line names the runner version and where it comes from. Its last step is the eMudhra stage ([design.md](design.md), "The eMudhra stage"): it prints a verdict table and a census, and ends with `golden-emudhra: GREEN` or `RED`. On RED, golden-build stops and makes no image: read the `FAIL` lines. After a new runner version or base image, `node-diff-compare: FAIL a new entry` means the release needs a new `setup/emudhra.node-diff`: make it from the `NODE-DIFF` lines of a run where the fix ran, and have it reviewed. A `NODE-DIFF-LOST` line is not a failure by itself: the root is no longer in the difference. Either the runner's Node dropped it (no new file is needed), or the Homebrew bundle holds it again. For an excluded root (emSign ECC Root CA - G3 today), read the census's bundle `FAIL` line first: that check still ends the stage RED. A `node-diff-compare: FAIL` for a block with no DONE line or no END line means a Node in the guest could not compute its difference: read the census `FAIL` line above it.
   - The runner version: the release literal (`RUNNER_VERSION` in golden-build), unless the host pin `/Users/ci/.local/state/runner-updater/pin/mac-golden` exists. The updater writes that pin; a person normally never does. A pin wins over the literal. A pin that is not a regular file of exactly one line `VERSION SHA256` stops golden-build before it starts: it never falls back to the literal. So does a folder on the pin's path that ci cannot search: a pin behind it would look absent.
   - `/Users/ci/bin/golden-build --print-runner` prints `host pin V (release literal L)` or `release literal L (no host pin)`, and does nothing else: no lock, no Tart, and it runs while the agent is enabled.
3. `/Users/ci/bin/golden-gate liveapp-mac-golden-<yyyymmdd>`, right after golden-build and BEFORE the configuration names the image, so a RED or STOP needs no revert. It is the host-side check of the SAVED image (golden-build's census read the build VM while it ran, before `tart stop`). It clones the image to an `s1-gate-*` VM, runs the eMudhra gate in it, deletes the clone, and must end `golden-gate: GREEN <image>`. On RED (the image fails the gate) or STOP (the image was not checked): `/Users/ci/bin/runner-enable` on the unchanged configuration, and report with the `FAIL` and `STOP` lines. A STOP for a leftover `s1-gate-*` prints the exact lines to stop its VM and then delete it: run them, then golden-gate again ([design.md](design.md), "The gate on a saved image").
4. Put that name as `runner-image` in every `[[scaleset]]` of `/Users/ci/.config/runner/config.toml`, then `/Users/ci/bin/runner-start validate`. (`runner-start validate CONFIG` runs the same checks on another file, by its absolute path; the updater uses it for a temporary copy.)
   Then `/Users/ci/bin/runner-enable`, then run the check workflow and [../examples/emudhra-check.yml](../examples/emudhra-check.yml) at once. emudhra-check stays the job-level proof: its gate runs in a job's own VM from the new image (a deny (result 3) and `verify-cert` non-zero for each excluded anchor, and `verify-cert` 0 for the control roots). Keep the new image only if both are green; else point the config back to the previous image (idle runbook again) and report.
   The window: runner-enable comes first, so jobs already queued for the label can run on the new image before emudhra-check has run. This is accepted because golden-gate checked the saved image before the configuration named it, and the census passed on the build VM. Keep the window short: start the check right after runner-enable.
5. Free the disk: `/Users/ci/bin/golden-prune <configured image> $(/Users/ci/Applications/tart.app/Contents/MacOS/tart list --source local -q)` prints the images that may go (all but the configured one and the newest other generation); delete exactly those with `/Users/ci/Applications/tart.app/Contents/MacOS/tart delete <name>`. On a host with the updater (the folder `/Users/ci/.local/state/runner-updater` exists), golden-prune also never prints an image in the updater's protected list, `/Users/ci/.local/state/runner-updater/protected`, and refuses when that list is missing, unreadable, not a regular file, or holds a line that is not an image name. It also refuses when a folder on the list's path (that folder or one above it) exists but ci cannot search it: the list would look absent, as on a host with no updater.

The pinned base image could one day leave its registry; a release then pins another one.

## The host eMudhra deny (this fleet's hand step)

This is NOT an adopter step in v0.1. The README promises ONE root step, and [../SECURITY.md](../SECURITY.md) says a root line comes only from a release's assets; no asset holds this line. This fleet does it by hand, from a copy the maintainer reviewed. A published asset may come in a later release if adopters need it.

What it does: `setup/emudhra-deny.sh` writes a deny into the host's admin trust settings for each of Apple's anchors whose key homebrew-core excludes ([design.md](design.md), "The eMudhra stage"). That reaches every client of Apple's Security framework on the host: runscaler's Go TLS, Tart's and nscurl's URLSession. It does NOT reach the host's `/usr/bin/curl`: its LibreSSL asks Apple only when its own bundle fails, and the host's `/etc/ssl/cert.pem` stays unfiltered, so curl trusts both test paths before and after (measured: HTTP 200 on the AAA path where nscurl gets -1202). That is accepted because every host use of curl is pinned or cross-checked: `fetch.sh` and the install line check a sha256, and wall-check compares checkip with OpenDNS. A new host use of curl that relies on TLS trust needs its own decision.

1. Have both scripts reviewed: `setup/emudhra-deny.sh` and its rollback `setup/emudhra-undeny.sh`. Each reads nothing from ci's home and checks its own result.
2. Stage them as ci. On a host installed from a release they are already in `/Users/ci/mac-runner/<VERSION>/setup/`: render from the same bytes (the files as unpacked from that tag's tarball), or the line refuses. On a host staged by hand: `/Users/ci/setup/emudhra-deny.sh` and `/Users/ci/setup/emudhra-undeny.sh`.
3. On the maintainer's machine, render BOTH lines before the run, from the reviewed copies (repeat with `emudhra-undeny.sh`):
   ```
   setup/render-run-line setup/02-wall.run-line setup/emudhra-deny.sh /Users/ci/mac-runner/<VERSION>/setup/emudhra-deny.sh
   ```
   The template is the unchanged `setup/02-wall.run-line`: the line copies the staged file to a root-owned file, runs it only if its sha256 is the reviewed copy's, and removes it.
   Each line is about 600 characters. If your terminal breaks a line when you copy it, paste it as a block of several lines instead: keep every character, and break it only right after a `;` inside the single quotes (a line break there ends a command just as `;` does; the maintainer tested this). Never break it inside a word, a path or the hash.
4. Before, as ci: the rows below, written down.
5. In the admin's OWN GUI session: the deny line. That session is Screen Sharing connected as the admin with "Log in as yourself", or the admin's own desktop at the Mac. Never run it with `su -l <admin>` (or `sudo`) in a Terminal of ci's session: macOS cannot show its password dialog there, and the deny fails with `SecTrustSettingsSetTrustSettings: The authorization was denied since no user interaction was possible.` (measured on the mini; the self-check then prints `FAILED`, and nothing was changed). macOS asks for an administrator's name and password once per certificate. It prints each certificate's name and SPKI, then `denied` or `already denied` for each, and ends with `done: …`. A `FAILED` line: keep the session open, run the undeny line, report. If you stop it with Ctrl-C (for example at a password dialog that does not show), it prints whether anything changed: after `INTERRUPTED`, run the deny line again (it skips what is denied) or the undeny line.
6. After, as ci: the same rows. Stay in the admin's session until they pass.
7. Restart runscaler in the idle runbook (`runner-disable`, then `runner-enable`), and check that `curl -s http://127.0.0.1:8080/healthz` shows every scale set ready. On a fresh host, where runscaler has no configuration yet, the validate row and the check workflow wait for the first `runner-start validate`: keep the undeny line ready until they pass, and read a TLS error there as the deny first.

| Check, as ci (read-only) | Before | After |
|---|---|---|
| `verify-cert` of each excluded root (AAA Certificate Services, emSign ECC Root CA - G3 on macOS 27) | 0 | non-zero |
| `verify-cert` of each control root (USERTrust RSA, USERTrust ECC, ISRG Root X1) | 0 | 0 |
| admin deny entries (`trust-settings-export -d`, result 3) | 0 | one per excluded root |
| nscurl, the emSign test path | trusted | `Code=-1202` with `-9807` |
| nscurl, `https://github.com/` | trusted | trusted |
| nscurl, `https://ghcr.io/v2/` (Tart's pulls; any HTTP answer) | trusted | trusted |
| `/Users/ci/bin/runner-start validate` (Go, through Apple's verifier) | all checks passed | all checks passed |
| host `/usr/bin/curl`, the emSign test path (a named gap) | HTTP 200 | HTTP 200 |

The rows, each one line, as ci. verify-cert:

```
for n in "AAA Certificate Services" "emSign ECC Root CA - G3" "USERTrust RSA Certification Authority" "USERTrust ECC Certification Authority" "ISRG Root X1"; do if /usr/bin/security find-certificate -c "$n" -p /System/Library/Keychains/SystemRootCertificates.keychain > /tmp/emudhra-root.pem 2>/dev/null; then /usr/bin/security verify-cert -c /tmp/emudhra-root.pem -p basic -L > /dev/null 2>&1; echo "$n: verify-cert $?"; else echo "$n: not in Apple's store"; fi; done; rm -f /tmp/emudhra-root.pem
```

The admin deny entries (no output from export and a count of 0 both mean none):

```
rm -f /tmp/emudhra-ts.plist; /usr/bin/security trust-settings-export -d /tmp/emudhra-ts.plist; /usr/bin/plutil -p /tmp/emudhra-ts.plist 2>/dev/null | grep -c '"kSecTrustSettingsResult" => 3'; rm -f /tmp/emudhra-ts.plist
```

nscurl (it exits 0 on every failure, so read its output: nothing after the colon = trusted; a gone test host makes that row "not measured", never a pass):

```
for u in https://dv-g3b-emudhra.we-have-a-problem.com/ https://github.com/ https://ghcr.io/v2/; do echo "$u: $(/usr/bin/nscurl -o /dev/null $u 2>&1 | grep -oE 'Load failed|Code=-?[0-9]+|-98[0-9][0-9]' | sort -u | tr '\n' ' ')"; done
```

The named gap:

```
/usr/bin/curl -s -o /dev/null -w '%{http_code}\n' https://dv-g3b-emudhra.we-have-a-problem.com/
```

**Rollback:** the rendered undeny line, in the admin's own GUI session (as in step 5, never through `su` in ci's session). It finds the certificates by the same keys, also in System.keychain (so it works after Apple drops a root), removes each admin trust setting, and checks its own result. Its pass: it ends with `done: no admin trust setting is left …`, the verify-cert row of the excluded roots reads 0 again, and the nscurl emSign row reads trusted again. The copies the deny's `-k` put into System.keychain stay; without a trust setting they are inert.

## Token rotation

In the idle window (steps 1–2 of the idle runbook): put the new token on the Mac with the same hidden-prompt line as in the README (step 15), then `/Users/ci/bin/runner-start validate`, then `/Users/ci/bin/runner-enable`. Revoke the old token on GitHub.

## After runscaler changed

When install printed that runscaler was replaced (a release with a new runscaler, or a rollback across one; a re-run after a failed install prints it again, until an install completes): after `runner-enable`, run the check workflow, and check that the VM of that job has an admission line in `/Users/ci/Library/Logs/mac-runner/admissions.log` (`grep runner- /Users/ci/Library/Logs/mac-runner/admissions.log | tail -3`). A job that ran without an admission line did not start through the shim: disable the agent and find out why.

## When the shim refuses

The shim's refusals appear in runscaler's log (`/Users/ci/Library/Logs/mac-runner/runscaler.log`) and in runner-enable's output, as `liveapp-ci-shim: REFUSE <reason>`. A refused VM start leaves its job queued. The shim is frozen in v0.x, so some of its texts are older than this repository: where a refusal says **`run n1-driver`**, run **`/Users/ci/bin/wall-check`**. The shim's header also names a plan file and test cells that were never published; its design is in [design.md](design.md), and its rules are checked live by wall-check's shim probes and by `--liveapp-check`.

| The shim says | What to do |
|---|---|
| `REAL changed since the wall stamp: run n1-driver` | Tart changed (an update): idle runbook, then `/Users/ci/bin/wall-check`. |
| `SOFTNET changed since the wall stamp: run n1-driver` | softnet changed: `wall-files-check` must say `FILES green` (else the release's root line), then `/Users/ci/bin/wall-check`. |
| `the shim changed since the wall stamp: run n1-driver` | The shim was reinstalled with other bytes: `wall-files-check`, then `/Users/ci/bin/wall-check`. |
| `wall stamp absent, empty or unreadable: …` | No valid proof (a failed wall-check deletes the stamp): `/Users/ci/bin/wall-check`. |
| `wall stamp line not understood`, `… field repeated`, `… field missing` | The stamp was changed by hand: `/Users/ci/bin/wall-check`. |
| `free disk below the floor: N GiB < 100 GiB` | Free disk where Tart keeps its VMs: prune old images ("Rebuilding the image", step 5), `tart prune`, old logs. No wall-check needed. |
| `conf absent or unreadable`, `conf line not understood`, `conf floor-gib repeated`, `conf has no floor-gib line` | The root files are damaged: `wall-files-check`, then the release's root line, then `/Users/ci/bin/wall-check`. |
| `hashed file absent or unreadable: <file>` | Tart or softnet is missing: the install line (Tart), or the root line (softnet). Then `/Users/ci/bin/wall-check`. |
| `run admits only: run runner-<8 hex> --no-graphics` | Something other than runscaler tried to start a VM through the shim. wall-check's shim probes cause this on purpose; anything else is to investigate. |
| `not a Tart subcommand this shim passes: '<x>'` | Only runscaler's subcommands pass the shim. For maintenance work (for example `tart export`), call Tart directly (`/Users/ci/Applications/tart.app/Contents/MacOS/tart`) with the agent disabled and nothing else running. |
| `tart set <vm> --random-mac failed` | Tart could not change the new VM: read runscaler's log for Tart's own error. |
| `cannot append the admission line to …` | The log folder is missing or not writable: run the install line again (it creates `/Users/ci/Library/Logs/mac-runner`, 0700). |
| `TART_HOME must be an absolute path` | Fix the environment that runs Tart (runscaler's configuration). |
| `df failed`, `df output not understood`, `shasum failed`, `date failed` | A system tool failed or changed its output: report it. |

## When wall-check stops

wall-check names what failed. The most common STOPs:

- `the agent is enabled` — `/Users/ci/bin/runner-disable` first. `the runner lock is held` — runscaler, an install, golden-build, golden-gate or another wall-check runs.
- `turn Wi-Fi off (or unplug Ethernet): one network only` — two network ports have an address.
- `default route is not a hardware port (a VPN?)` — turn the VPN off on this Mac.
- `the wall does not cover a public address on the host` — this Mac has a global address; it must sit behind a NAT router.
- `host-side mDNS control: …` — the Mac does not resolve its own `.local` name; check System Settings → General → Sharing → Local hostname.
- `the home's public IPv4 is not confirmed by two sources` — outbound DNS to OpenDNS or HTTPS to checkip.amazonaws.com is blocked, or they disagree (a VPN, a proxy).
- `no control port: turn on Remote Login or Screen Sharing` — the control VM must reach this Mac on 22 or 5900, else a "blocked" proves nothing.
- `the walled VM reached …` — **the wall does not hold.** The stamp is deleted, so the shim refuses every job. Keep the agent disabled and find out why before anything else.
- `… does not parse` (wall.conf) — fix `/Users/ci/.config/runner/wall.conf` (one line `forwards = PORT, PORT, …`).

`/Users/ci/bin/wall-check --derive` prints every derived value and its source without booting anything; run it first when a STOP is about the network.

## Outage recovery

Read the state first: does `/Users/ci/.config/runner/enabled` exist; is runscaler running (`/Users/ci/bin/runner-lock-free`); `tart list` (every running VM by name); the end of `runscaler.log`; the shim's refusals and `admissions.log`; `wall-files-check`; `/usr/local/libexec/liveapp-ci/tart --liveapp-check`.

- No VM runs: fix the fault, then `/Users/ci/bin/runner-enable` (or, if runscaler hangs with the flag present, stop it with `/Users/ci/bin/runner-disable` and enable again). Queued jobs never block recovery.
- VMs run: wait for them, or decide to stop them (their jobs fail). A running VM whose name is not `runner-<8 hex>` is stopped and deleted first.
- Then re-run every job the outage killed (`gh run rerun --failed <run>`).

**A new macOS build while the agent was enabled** (an update or security response that ran anyway, for example with the README's step 5 left On): at runscaler's next start (after the restart), runner-start refuses, and runscaler does not run. What you see:

- `runner-start: REFUSE the wall was proven on macOS build …; this Mac runs …` in `/Users/ci/Library/Logs/mac-runner/runner-start.err`, a new line every 300 s (launchd tries again at that interval while the flag exists).
- Jobs for the label stay queued.

Then do the idle runbook: `/Users/ci/bin/runner-disable`, `/Users/ci/bin/wall-check`, `/Users/ci/bin/runner-enable`. A runscaler that is still running (no restart after the change) is not stopped by this check; it is caught at its next start.

What ends QUEUED (a monitor that watches queue age sees it): a retired runner, an expired token, a crash loop before any VM starts, a stale or deleted stamp, a stamp from another macOS build, low disk, a refused VM, the Mac off. What ends FAILED (a job that had a runner is killed): a runscaler crash, a power cut, an unattended restart, a stop.

## Disk

The growers are bounded: runscaler's log and runner-start's log (10 MB each, cut when runscaler starts), runscaler's own `runner.log` beside `config.toml` (runscaler renames it to `runner.log.1` at 10 MiB and starts a new one; it keeps one backup), Tart's image cache (`cache-budget` in config.toml), the golden images (the configured one and the newest other generation), and the jobs' VMs (deleted after each job). golden-build's two logs per build (`golden-<yyyymmdd>.log` and `golden-<yyyymmdd>-vm.log`) and golden-gate's two logs per run (`s1-gate-<yyyymmddHHMMSS>-vm.log` and `s1-gate-<yyyymmddHHMMSS>-gate.log`) are small and are not removed: delete old ones by hand. The shim refuses a VM start below 100 GiB free; golden-build refuses below 200 GiB free. Both leave jobs queued.

## The updater: status, on, off, pass, protect

The runner-image updater is not complete yet: a pass takes no action on what it finds but RECOVER (below), and only `rebuild` and `switch-now` (below) start a change of CI. Run each command as ci: `/Users/ci/mac-runner/current/bin/runner-updater COMMAND` (install does not link it yet). It sets its own PATH, so it runs the same from a timer, a terminal or a non-interactive ssh.

- Its state is `/Users/ci/.local/state/runner-updater/state.json`: ON or OFF, each family's candidate, its previous image, the date until which `back` restores that image, its rejected versions, its recipe baseline and the STOPs it holds, the runner version of each image it built, and the decision core's own state. A fresh install has no state file: the updater is OFF.
- `status` prints ON or OFF, each family (its candidate or "no candidate", that date, its rejected versions), the host pin of each family with a builder (`host pin VERSION`, or `none`: a hand golden-build then uses the release literal), an open window journal, the core's STOP lines with their next step, and each STOP's properties (`known false` for a STOP this release does not know). It takes no lock and writes nothing, so it runs while a pass runs, and it never prints half of a state.
- `on` turns the updater on. `off` turns it off, then removes every host pin in `/Users/ci/.local/state/runner-updater/pin/`, so a golden-build by hand uses the release's runner version. It writes each removal to `/Users/ci/.local/state/runner-updater/actions` first; when it cannot write that line, it stops and the pin stays (run `off` again). `off` runs RECOVER first when a window journal is open (`/Users/ci/.local/state/runner-updater/window`), and refuses only when the journal stays open: it never leaves a window half done.
- `pass` is what the timer runs (the timer comes in a later release). When another run holds the updater lock, or the updater is OFF, it ends at once. When a window journal is open (`/Users/ci/.local/state/runner-updater/window`), it runs RECOVER first (below), even while the updater is OFF; a pass whose RECOVER holds a STOP exits 1. When ON, it reads what report reads, asks the core, keeps the core's state, rewrites the protected list, and prints what it would do ("would roll back FAMILY", "would accept FAMILY"). It does none of it.
- After that, `pass` prints for each family of the families file the runner release it would switch to (`would switch FAMILY to V`), or why not: an open candidate; a STOP the family holds (the line names the STOP and its version; `status` gives its next step): every STOP holds it, except that a newer release proceeds alone past `check failed`, `ROLLED BACK` and `PINNED RUNNER RETIRED` of an older version; `STOP NO BASELINE` (the family has no recipe baseline yet: `rebuild FAMILY` sets it, in a later release); `STOP recipe changed` (a builder file, `setup/emudhra.node-diff`, `setup/tls-excluded-spki` or the base image pin changed since the baseline: `rebuild FAMILY`); `WAIT` (GitHub answered 403 or 429, a rate limit: the next pass asks again); a rejected version; a version that is not newer than the family's, or not 2 days old yet; a release that fails its checks. Only `mac-golden` has a recipe in this release, and the family's current version is the one the updater recorded for its image. It switches nothing. A family held for a reason on the host asks GitHub nothing.
- The release checks (GitHub's latest release, read at most once per pass): its tag is `vN.N.N`, it is at least 2 days old, it is not rejected for the family, and the sha256 of its `actions-runner-osx-arm64-N.N.N.tar.gz` equals the asset's digest. It downloads that tarball to check it, removes the download, and keeps only the record of what it checked (`/Users/ci/.local/state/runner-updater/release/verified`), so the next pass does not download it again.
- Every download of the updater uses a filtered CA bundle, `/Users/ci/.local/state/runner-updater/release/bundle.pem`: `/etc/ssl/cert.pem` less every certificate whose key `setup/tls-excluded-spki` names. It is rebuilt when its source, that file or the filter changes; when fewer than 100 certificates would be left, or the file breaks its format, the pass prints a STOP and downloads nothing. curl runs with `OPENSSL_X509_TEA_DISABLE=1`: without it, Apple's curl falls back to the keychain and the bundle excludes nothing.
- `protect` writes the protected list, `/Users/ci/.local/state/runner-updater/protected`, from the state: each family's candidate images, its previous image until 7 days after an accept, and each image an open window names. golden-prune never prints a name in that list. If the list is lost or damaged, do not create it empty: run `protect` (a pass also writes it while the updater is ON). If the state file is lost but the list still names images, every command refuses (exit 1): a fresh state would drop what the list keeps. Put the state back; or, when no image in the list must be kept, move the list aside and run the command again.
- A state file the updater does not read stays as it is: a state of another format gives `WAIT` (exit 4), a damaged one `REFUSE` (exit 1). Look at the file before you change it.
- A state with a member this release does not read (a later release wrote it) also gives `WAIT` (exit 4), for every command, `status` too: the line names each such member. That member may name an image to keep or hold a STOP, so this release changes nothing. Install the release that wrote it again.
- When ci cannot search `/Users/ci/.local/state/runner-updater` or a folder above it, every command refuses (exit 1): the files in it would look absent, and a lost state must not read as a fresh, OFF one. `off` also stops when it cannot read and search the pin folder: the pins stay. Look at the folder's mode, then run the command again.
- The updater refuses a `config.toml` with a top-level `log-file`, or a `log-format` other than `"text"`: the core reads only runscaler's own `runner.log` beside the config, in the text format.
- It also refuses a warm pool for a set of a family: a `pool-size` other than 0 in the `[tart]` table, or a `pool-size` key anywhere else (it reads only the one in `[tart]`). The text `pool-size` in a value, such as a URL, or in a comment is no key. Its rules for a Tart set assume no warm pool, as `config/config.toml.example` sets it. `on` refuses it, and a pass or a report then has no facts.

## The switch window: rebuild and switch-now

`runner-updater rebuild FAMILY` and `runner-updater switch-now FAMILY`, as ci, each run ONE switch window: the family's sets go from the image they run (the old image) to a new image its builder makes. Only `mac-golden` has a builder in this release (golden-build); for another family the command says "no builder wired". Both run only while the updater is ON, and wait for the updater lock.

- `rebuild FAMILY` builds the family's CURRENT runner version again: the version of the old image (the updater's record of it, else the version golden-build's log printed for it). It refuses when it cannot tell that version, or knows no sha256 for it (the host pin's or the release literal's). It is the rehearsal of a switch, and the way to answer HAND CHANGE.
- `switch-now FAMILY` is the same window with no idle wait, and it says so: runner-disable then drains every set at once, and a drain stops the jobs still running at its end. Its release is the one the family's `NO IDLE` STOP holds, else the current version, as `rebuild`.

Before it disables CI, the window checks, and on any failure changes nothing (no runner-disable, no drain): the family's sets name one image, that image is on the host, today's output does not exist yet (golden-build makes one image a day), the host pin is absent or one line; CI is enabled, runscaler runs and started after the config was installed, and the family's sets are ready; the free disk is at least golden-build's floor (200 GiB) plus the old image's size; `runner-enable --check` passes; the current config validates (`runner-start validate` on a copy). Then it notes which runscaler it will stop. Last comes the idle pair (rebuild only): two `/healthz` reads, 3 s apart, every set idle; after it, nothing but runner-disable touches the host. CI disabled, runscaler not running or a set not idle: "not now", exit 5, nothing changed; run it again later, or `switch-now`.
A STOP before runner-disable replaces only an earlier STOP of the same name: a `POOL DOWN` (CI is down) or a `NO IDLE` (and the release `switch-now` runs) stays until a window ends it.

The window, each step written to its journal first: runner-disable; the host pin `/Users/ci/.local/state/runner-updater/pin/FAMILY` set to the version; `golden-build --date <today, UTC>`; `golden-gate` on the new image; `runner-enable --check`; the new config validated as a copy; then, under the runner lock, the config compared with the copy the window started from and, when it is the same, the family's `runner-image` lines set to the new image (nothing else changes) and `runner-start validate`; when the clock's second is past the config's modification time, `runner-enable`; then it waits up to 10 min for runscaler to start on the new config. The window then closes: the family's new image is its candidate (`status` shows it), the old image its `previous`, and both stay in the protected list. The window also notes where runscaler's log stood when the old runscaler had stopped, so the next pass reads the restart as the updater's own and not as a gap in the evidence.

A failure after runner-disable (the build, the gate, a check, a validate) is `STOP check failed`: the config goes back to the copy the window started from (when the window had changed it), CI is enabled on it, and the window closes. CI is never enabled on a config that just failed validate. When the gate did not pass the new image, the window deletes it (and its work VM) before it closes, unless a config line names it: `golden-prune` would otherwise keep it as the way back. A config that changed during the window (a hand edit) is not edited: `STOP HAND CHANGE`. CI is enabled on the file as found only when a copy of it validates (`runner-start validate`); when it does not, CI stays down and the window journal stays open: check the file, then run `/Users/ci/bin/runner-enable` (the next run validates it again first). Run `rebuild FAMILY` when the edit is done. A hand edit made in the second between the window's last check and runscaler's start cannot be stopped before the start; the window or the next run sees it after.
A hand edit after the window installed its new config (while it validates it, or before runner-enable) is also `STOP HAND CHANGE`, but CI stays down: the window does not put anything over your file and does not enable CI on a file it did not validate. Check the file, then run `/Users/ci/bin/runner-enable`. The window journal stays open (below).
A config whose modification time is more than 10 s ahead of the clock (clock skew, or a `touch` by hand) cannot be proven read: `STOP check failed`, the file as found is kept in the window's folder (`config.toml.found`), the config the window started from goes back, and CI is enabled on it. When runner-enable refuses, or runscaler does not start in 10 min, the window disables CI once, puts the old config back and enables again; when that fails too, it is `STOP POOL DOWN`, CI stays down on the host, and the line names what to run by hand. Free disk below the floor is `STOP DISK`: free disk, then run the window again. The host pin, when the window closes, names the runner version of the image the config runs; when that version is not known, the pin is removed and `status` says `none`.

Its files: the open journal `/Users/ci/.local/state/runner-updater/window`; each closed one, and each window's folder (the copy of the config it started from, the validate outputs, the build's and the gate's output), in `/Users/ci/.local/state/runner-updater/windows/`. An interrupted window (a kill, a crash, a restart) leaves its journal open: the next run ends it with RECOVER (below). Do not delete the journal: RECOVER reads it.

## RECOVER: an interrupted window

A window journal that is open while no run holds the updater lock belongs to a window that was interrupted. `pass`, `rebuild`, `switch-now`, `back`, `retry`, `on` and `off` end it first, with RECOVER; `status` only names it, and `report` takes no action. RECOVER reads only the journal (each line by a fixed pattern) and the host: CI's flag, the running runscaler, the config, the open files, Tart's list and the runner lock. It needs no tested jq (an untested jq stops new work only); jq only reads and writes the state.

- CI enabled, and the window disabled nothing: the journal closes, no STOP.
- CI disabled, and the journal ends just before the window's `runner-disable` step (a power loss can lose the journal's last line, and that line may have been it): RECOVER takes it that the window disabled CI and brings it back on the config the window started from (below). A journal that ends earlier shows that the window disabled nothing: CI was disabled by a person, and RECOVER leaves it so (the journal closes, no STOP).
- CI enabled after the window enabled it: the journal closes when runscaler runs the window's last target config. When the config is another file (other lines for the family, or any other change), a person's config runs: `STOP HAND CHANGE`, and CI stays as it is. When runscaler does not start in 10 min, RECOVER disables CI once and goes on below.
- CI enabled by a person after the window disabled it: `STOP HAND CHANGE`; RECOVER changes nothing.
- CI disabled: RECOVER waits until no process of ci has a tool of the window open (golden-build, golden-emudhra, golden-gate, real-run, by their file identity, as `lsof` lists every open file), no `gold-*`, `n1-*` or `s1-*` VM runs, and the runner lock is free. It waits at most 75 min from its first wait; then `STOP CI DISABLED`, the journal stays open, and each pass checks again. Find what still runs (`lsof`, `tart list`); RECOVER goes on by itself when it ends.
- Then it deletes the window's new image and work VM unless the gate passed them, and only when no config line names them, each written to the journal first.
- The config: the window's edit goes back to the copy the window started from; the copy itself stays; another file is a person's and stays as found. RECOVER enables CI on a person's file only when it validates first; when it does not, `STOP HAND CHANGE`, CI stays down and the journal stays open: check the file, then run `/Users/ci/bin/runner-enable`, or fix it and let the next pass validate it again.
- It writes its own target (the config's sha and the family's lines) to the journal, runs `runner-enable`, and waits up to 10 min for runscaler to start on it. A failure there happens at most once per journal: the second is `STOP POOL DOWN`, with no more runner-disable.
- A window it ends that had not switched holds `STOP check failed` (it was interrupted), unless it already held another STOP; `retry FAMILY` clears it. A window that had switched (its new image runs) keeps its candidate.
- A rollback window it ends: when the window had already decided to put the config back (the validate of the rollback's lines failed, or `ROLLBACK FAILED`), RECOVER puts it back and does not validate those lines again; CI goes on the config the window started from. Its `ROLLED BACK` keeps the counted failures.

RECOVER needs a jq that runs: the state is read with jq before RECOVER starts, so a jq that cannot run at all stops RECOVER too (CI stays as the interruption left it).

## Rollback: back and retry

`runner-updater back FAMILY`, as ci, runs ONE rollback window: the family's sets go back from the image they run to the family's previous image (the image they ran before the updater's last switch). It runs while the updater is ON, before an accept (the family has a candidate: the rehearsal), or after it until 7 days after the accept (`status` shows the date: "back until ..."); else it refuses and changes nothing.

- There is no idle wait: runner-disable drains every set at once, and a drain stops the jobs still running at its end. Before it disables CI, it checks that the family's sets name the candidate's image (else `STOP HAND CHANGE`: a hand edit is pending), that `runner-enable --check` passes, and that the config with the previous image validates (`runner-start validate` on a copy). A failed validate is `STOP ROLLBACK FAILED` with no runner-disable; a validate whose result it cannot read is "rollback pending" (exit 5): run it again.
- With CI disabled by a person (no `/Users/ci/.config/runner/enabled`), nothing restarts: "rollback pending: CI disabled by a person" (exit 5).
- After runner-disable, under the runner lock, it sets the family's `runner-image` lines to the previous image, validates the config, and enables CI. When that validate fails, the config it started from goes back, CI is enabled on it, and it is `STOP ROLLBACK FAILED`: CI is never enabled on lines that just failed validate. A config a person changed during the window is not edited (`STOP HAND CHANGE`), and gets CI only when a copy of it validates, as in the switch window.
- When the previous image runs, the family has no candidate and no previous image any more, the host pin names the previous image's runner version (with the sha the pin had for it before, from the family's closed window journals), and the image it left is deleted when the updater built or adopted it and no config line names it (an image you made by hand stays), written to `/Users/ci/.local/state/runner-updater/actions` first. `back` rejects the version it left only when that version is newer than the previous image's: the updater does not switch to it again until `retry FAMILY`.
- The updater's own rollback (a later release starts it on an R1 verdict) is the same window. It rejects the version it left and holds `STOP ROLLED BACK` with the counted failures; when every counted failure was a connect failure, the first rollback does not reject the version (one retry after 1 h comes first), and the second does. A rollback that cannot start (runner-disable timed out, or a validate it cannot read, before or after the edit) is tried again on each pass for 2 h from the verdict's start; after that, the next try is `STOP ROLLBACK FAILED` and runs no runner-disable. While `ROLLBACK FAILED` holds, no automatic rollback starts for that family. Every `ROLLBACK FAILED` names `runner-updater retry FAMILY` as its next step, whatever step raised it.

`runner-updater retry FAMILY`, as ci, clears the family's rejected versions and every STOP of the family whose line in `status` says `runner-updater retry FAMILY`: `check failed`, `ROLLED BACK`, `JOBS FAIL ON THE NEW IMAGE`, `NO EVIDENCE` and `ROLLBACK FAILED`. A STOP whose line names another step (`HAND CHANGE`: `rebuild`; `NO IDLE`: `switch-now`; `POOL DOWN`, `DISK`: a step by hand) stays, and so does every STOP of another family. A version a `PINNED RUNNER RETIRED` STOP holds stays rejected. `retry` starts nothing: the next pass may go on. It also runs while the updater is OFF.

## The updater's report mode (no action)

`/Users/ci/mac-runner/current/bin/runner-updater report`, as ci, only looks. It makes one pass and prints what the updater's decision core (`core/`) says about it. It stops, starts, edits, pins, deletes and enables nothing.

What it reads:

- the runscaler process (its process id and start time, from `ps`), before and after it notes how far runscaler's own log, `/Users/ci/.config/runner/runner.log`, has come;
- the text that log gained since the last report (it follows one rotation to `runner.log.1`; after more, it says the text is not continuous, and the core counts that as a gap in its evidence);
- `/Users/ci/.config/runner/config.toml`: its modification time (mtime), each scale set's name and its `runner-image` line, and the health address and port;
- the families file `/Users/ci/.config/runner-updater/families`, one line per family: `FAMILY tart SET [SET ...]` (no file: no family);
- two `/healthz` reads, 3 s apart.

It prints each decision (idle, the log pass, keep, status) and then the status lines. `report --observe FAMILY` takes that family's current images as the ones under observation, from that pass on, until `report --observe-clear FAMILY`: the log pass then counts their failures as the updater will. Nothing acts on what it prints.

Its state is in `/Users/ci/.local/state/runner-updater/report/`, never in the updater's own state: `state.json` (the core's state, written only when all four decisions were made), `observe.json`, and `pass/` (the last pass's facts, log text, `/healthz` reads and each decision). A second report waits for the first (the updater lock, `/Users/ci/.local/state/runner-updater/lock`). It refuses to run the core under a jq that `core/TESTED_JQ` does not list (`STOP untested jq`, exit 3), and it prints a `REFUSE` line, and runs nothing more, when it cannot read a fact. On a host where `/Users/ci/.local/state/runner-updater` does not exist yet, it creates it with an empty protected list, in one step, so golden-prune keeps printing what it printed before, also when report is stopped part way. A report killed while it creates the folder can leave a folder `/Users/ci/.local/state/runner-updater.new.<8 characters>` beside it: nothing reads it, and you can remove it. When the folder exists but has no protected list, report refuses and tells you to run `runner-updater protect`, which writes the list from the updater's state: an empty list in place of a lost one would let golden-prune print an image the updater keeps.

## Moving a host onto a release

For a host whose tools were installed by hand into `/Users/ci/bin` (files, not links): install refuses to overwrite them, on purpose.

1. The idle runbook steps 1–2. Note which tools are in `/Users/ci/bin`.
2. Move every tool except `runner` (runscaler) to a folder of its own, for example `/Users/ci/bin.pre-repo/` (move, do not delete). Write down the way back before going on: remove the new links in `/Users/ci/bin`, move the old tools back, put back the old plist from `/Users/ci/mac-runner/plist.prev` if install replaced it (`launchctl bootout` + `launchctl bootstrap gui/$(id -u) <plist>`), run the OLD wall-check, then `runner-enable`.
3. Run the release's install line. If install stops, take the way back and report.
4. Run the root line if install says NEEDED (in the admin's own session; it changes nothing until every check passed).
5. `/Users/ci/bin/wall-check` (the release's). If it stops: the way back.
6. `/Users/ci/bin/runner-enable`, then the check workflow. If it fails: `runner-disable`, the way back.
7. Only then remove the old tools' folder and `/Users/ci/mac-runner/plist.prev`, with their literal paths, after checking that no plist, config or link names them.

## Releasing (maintainers)

A release is never changed after publishing: a fix is a new version.

1. On the maintainer's machine, in the repository: `tools/release-check --private-list <your private list>` must be GREEN (the repository's own CI runs only the generic rules; the private list never leaves the maintainer's machine), and the unit tests must pass with the plain line: `JQ=/usr/bin/jq python3 -I -m unittest discover -s tests -t .` (the reference: one process, one test after the other). (`JQ=/usr/bin/jq`: the tests run the jq that `JQ` names, else the first `jq` on PATH, and only a row of `core/TESTED_JQ` is a pass; on macOS that row is `/usr/bin/jq`, jq-1.7.1-apple, while a Homebrew jq first on PATH is no row and the tests fail on it). The release-check line and the plain test line are both required before every tag, also when the hosted CI did not run. `JQ=/usr/bin/jq python3 -I tools/run-tests` runs the same tests in parallel (one unittest process per test module, as many at a time as the Mac has CPUs): the hosted CI runs it, and it is a fast check while you work. It does not replace the plain line: each module gets a fresh process, so a test that fails only after another module ran in the same process (an env var, the cwd or a module global that it left changed) is red only in the plain line. The cells of `tests/hetzner` (the scripts of `linux-docker/`) run those scripts as root, so they run only in a container: the ubuntu rows of the CI's jq-linux job run them, and on the Mac they skip. To check them locally before you push, run them in a throwaway container with no network and the repository mounted read-only (the line is RUN_LINE in `tests/hetzner/support.py`). A maintainer who runs a Linux host of `linux-docker/` puts that host's values in the list too: every value of its host config (its address, user names, set names, labels, runner groups, image name and token names), and its host name. Leave out only the port numbers (a bare number would match unrelated numbers) and a value that is public anyway, such as the organization URL of this repository's own owner.
2. `git tag -a v<VERSION>-rc.<N> -m "<VERSION> rc <N>"` (or `v<VERSION>` for the final release, on the same commit as its last rc). Do not push it yet.
3. `tools/release-check --build v<VERSION>-rc.<N> --private-list <your private list>` on that LOCAL tag. It also runs the decision core's and the watchdog's tests with every jq of `core/TESTED_JQ` this Mac has (`/usr/bin/jq`), and reads with `gh` that the commit's CI jobs `jq <version> (<image>)` passed for the other rows: so the commit must already be on GitHub (its pull request) with those jobs green, and a row it cannot run or read is RED. It also checks the tag's tagger line and message, then builds the tarball, `install-line.txt`, `root-line.txt` and `SHA256SUMS` into one folder and prints their hashes. If it is RED, nothing is built: delete the local tag (`git tag -d v<VERSION>-rc.<N>`), fix the cause, and tag again.
4. Only then push the tag: `git push origin v<VERSION>-rc.<N>`.
5. Create the GitHub release (a pre-release for an rc) with immutable releases on and exactly those four files as assets. The notes only point to the assets.
6. Before announcing: download all four assets (`gh release download <tag> -R liveappbase/mac-github-self-hosted-runner`) into an empty folder and compare each with the built file (`cmp`), and run `gh release verify <tag> -R liveappbase/mac-github-self-hosted-runner` and `gh release verify-asset <tag> <file> -R liveappbase/mac-github-self-hosted-runner` for each of the four, with gh 2.102.0 or newer. gh 2.81.0 does not read this repository's attestations ("no attestations"), and gh 2.92.0 or older sends the GitHub token to another host during a verify (advisory GHSA-8xvp-7hj6-mcj9): never run an older one, also not from a temporary folder.
7. Install the release on a host you run (an rc first) before the final tag is made.
