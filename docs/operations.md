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

The runner-image updater is not complete yet: this release takes no action on what it finds. Run each command as ci: `/Users/ci/mac-runner/current/bin/runner-updater COMMAND` (install does not link it yet). It sets its own PATH, so it runs the same from a timer, a terminal or a non-interactive ssh.

- Its state is `/Users/ci/.local/state/runner-updater/state.json`: ON or OFF, each family's candidate, its previous image, the date until which `back` restores that image, its rejected versions, its recipe baseline and the STOPs it holds, the runner version of each image it built, and the decision core's own state. A fresh install has no state file: the updater is OFF.
- `status` prints ON or OFF, each family (its candidate or "no candidate", that date, its rejected versions), the core's STOP lines with their next step, and each STOP's properties (`known false` for a STOP this release does not know). It takes no lock and writes nothing, so it runs while a pass runs, and it never prints half of a state.
- `on` turns the updater on. `off` turns it off, then removes every host pin in `/Users/ci/.local/state/runner-updater/pin/`, so a golden-build by hand uses the release's runner version. It writes each removal to `/Users/ci/.local/state/runner-updater/actions` first; when it cannot write that line, it stops and the pin stays (run `off` again). `off` refuses while a window is open (`/Users/ci/.local/state/runner-updater/window` exists): it never leaves a window half done.
- `pass` is what the timer runs (the timer comes in a later release). When another run holds the updater lock, or the updater is OFF, it ends at once. When ON, it reads what report reads, asks the core, keeps the core's state, rewrites the protected list, and prints what it would do ("would roll back FAMILY", "would accept FAMILY"). It does none of it.
- After that, `pass` prints for each family of the families file the runner release it would switch to (`would switch FAMILY to V`), or why not: an open candidate; `STOP NO BASELINE` (the family has no recipe baseline yet: `rebuild FAMILY` sets it, in a later release); `STOP recipe changed` (a builder file, `setup/emudhra.node-diff`, `setup/tls-excluded-spki` or the base image pin changed since the baseline: `rebuild FAMILY`); `WAIT` (GitHub answered 403 or 429, a rate limit: the next pass asks again); a rejected version; a version that is not newer than the family's, or not 2 days old yet; a release that fails its checks. Only `mac-golden` has a recipe in this release, and the family's current version is the one the updater recorded for its image. It switches nothing. A family held for a reason on the host asks GitHub nothing.
- The release checks (GitHub's latest release, read at most once per pass): its tag is `vN.N.N`, it is at least 2 days old, it is not rejected for the family, and the sha256 of its `actions-runner-osx-arm64-N.N.N.tar.gz` equals the asset's digest. It downloads that tarball to check it, removes the download, and keeps only the record of what it checked (`/Users/ci/.local/state/runner-updater/release/verified`), so the next pass does not download it again.
- Every download of the updater uses a filtered CA bundle, `/Users/ci/.local/state/runner-updater/release/bundle.pem`: `/etc/ssl/cert.pem` less every certificate whose key `setup/tls-excluded-spki` names. It is rebuilt when its source, that file or the filter changes; when fewer than 100 certificates would be left, or the file breaks its format, the pass prints a STOP and downloads nothing. curl runs with `OPENSSL_X509_TEA_DISABLE=1`: without it, Apple's curl falls back to the keychain and the bundle excludes nothing.
- `protect` writes the protected list, `/Users/ci/.local/state/runner-updater/protected`, from the state: each family's candidate images, its previous image until 7 days after an accept, and each image an open window names. golden-prune never prints a name in that list. If the list is lost or damaged, do not create it empty: run `protect` (a pass also writes it while the updater is ON). If the state file is lost but the list still names images, every command refuses (exit 1): a fresh state would drop what the list keeps. Put the state back; or, when no image in the list must be kept, move the list aside and run the command again.
- A state file the updater does not read stays as it is: a state of another format gives `WAIT` (exit 4), a damaged one `REFUSE` (exit 1). Look at the file before you change it.
- A state with a member this release does not read (a later release wrote it) also gives `WAIT` (exit 4), for every command, `status` too: the line names each such member. That member may name an image to keep or hold a STOP, so this release changes nothing. Install the release that wrote it again.
- When ci cannot search `/Users/ci/.local/state/runner-updater` or a folder above it, every command refuses (exit 1): the files in it would look absent, and a lost state must not read as a fresh, OFF one. `off` also stops when it cannot read and search the pin folder: the pins stay. Look at the folder's mode, then run the command again.
- The updater refuses a `config.toml` with a top-level `log-file`, or a `log-format` other than `"text"`: the core reads only runscaler's own `runner.log` beside the config, in the text format.
- It also refuses a warm pool for a set of a family: a `pool-size` other than 0 in the `[tart]` table, or a `pool-size` key anywhere else (it reads only the one in `[tart]`). The text `pool-size` in a value, such as a URL, or in a comment is no key. Its rules for a Tart set assume no warm pool, as `config/config.toml.example` sets it. `on` refuses it, and a pass or a report then has no facts.

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

1. On the maintainer's machine, in the repository: `tools/release-check --private-list <your private list>` must be GREEN (the repository's own CI runs only the generic rules; the private list never leaves the maintainer's machine), and the unit tests must pass: `JQ=/usr/bin/jq python3 -I -m unittest discover -s tests -t .` (`JQ=/usr/bin/jq`: the tests run the jq that `JQ` names, else the first `jq` on PATH, and only a row of `core/TESTED_JQ` is a pass; on macOS that row is `/usr/bin/jq`, jq-1.7.1-apple, while a Homebrew jq first on PATH is no row and the tests fail on it). Both are required before every tag, also when the hosted CI did not run. The cells of `tests/hetzner` (the scripts of `linux-docker/`) run those scripts as root, so they run only in a container: the ubuntu rows of the CI's jq-linux job run them, and on the Mac they skip. To check them locally before you push, run them in a throwaway container with no network and the repository mounted read-only (the line is RUN_LINE in `tests/hetzner/support.py`). A maintainer who runs a Linux host of `linux-docker/` puts that host's values in the list too: every value of its host config (its address, user names, set names, labels, runner groups, image name and token names), and its host name. Leave out only the port numbers (a bare number would match unrelated numbers) and a value that is public anyway, such as the organization URL of this repository's own owner.
2. `git tag -a v<VERSION>-rc.<N> -m "<VERSION> rc <N>"` (or `v<VERSION>` for the final release, on the same commit as its last rc). Do not push it yet.
3. `tools/release-check --build v<VERSION>-rc.<N> --private-list <your private list>` on that LOCAL tag. It also runs the decision core's and the watchdog's tests with every jq of `core/TESTED_JQ` this Mac has (`/usr/bin/jq`), and reads with `gh` that the commit's CI jobs `jq <version> (<image>)` passed for the other rows: so the commit must already be on GitHub (its pull request) with those jobs green, and a row it cannot run or read is RED. It also checks the tag's tagger line and message, then builds the tarball, `install-line.txt`, `root-line.txt` and `SHA256SUMS` into one folder and prints their hashes. If it is RED, nothing is built: delete the local tag (`git tag -d v<VERSION>-rc.<N>`), fix the cause, and tag again.
4. Only then push the tag: `git push origin v<VERSION>-rc.<N>`.
5. Create the GitHub release (a pre-release for an rc) with immutable releases on and exactly those four files as assets. The notes only point to the assets.
6. Before announcing: download all four assets (`gh release download <tag> -R liveappbase/mac-github-self-hosted-runner`) into an empty folder and compare each with the built file (`cmp`), and run `gh release verify <tag> -R liveappbase/mac-github-self-hosted-runner` and `gh release verify-asset <tag> <file> -R liveappbase/mac-github-self-hosted-runner` for each of the four, with gh 2.102.0 or newer. gh 2.81.0 does not read this repository's attestations ("no attestations"), and gh 2.92.0 or older sends the GitHub token to another host during a verify (advisory GHSA-8xvp-7hj6-mcj9): never run an older one, also not from a temporary folder.
7. Install the release on a host you run (an rc first) before the final tag is made.
