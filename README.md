# github-self-hosted-runner

Run GitHub Actions jobs on your own hardware, each job in a fresh environment that is deleted after it. Two host types, each with its own install:

| Host | Each job runs in | Install |
|---|---|---|
| **Apple-silicon Mac** | a fresh macOS VM ([Tart](https://github.com/openai/tart)), behind a network wall | [Install](#install), below |
| **Linux server** (Ubuntu, x86_64) | a fresh Docker container from a local runner image, on a rootless Docker daemon | [linux-docker/README.md](linux-docker/README.md) |

On both, [runscaler](https://github.com/ysya/runscaler) takes the jobs from GitHub runner scale sets. The rest of this page is about the Mac host; the Linux server has its own page, [linux-docker/README.md](linux-docker/README.md).

## The Mac host

Turn an Apple-silicon Mac into a GitHub Actions host that runs every job in a **fresh Tart VM behind a network wall**.

- Each job gets a new macOS VM, cloned from a golden image and deleted after the job. At most 2 jobs run at once (Apple allows 2 macOS VMs per Mac).
- [runscaler](https://github.com/ysya/runscaler) takes the jobs from GitHub (one scale set per repository or organization) and starts the VMs with [Tart](https://github.com/openai/tart).
- Every VM starts behind [softnet](https://github.com/openai/softnet): it reaches the internet, but not this Mac, your network, your router, the clipboard or the audio input.
- A root-owned `tart` shim admits a VM start only when a **live proof** of that wall (`wall-check`) matches the installed Tart, softnet and shim.
- You install it from ONE published release, with ONE root step whose exact line is an immutable release asset.

Status: **v0.2.0, pre-release.** The design and its reasons: [docs/design.md](docs/design.md). Day-to-day work: [docs/operations.md](docs/operations.md). What the wall does and does not protect: [SECURITY.md](SECURITY.md).

Licence: [Apache-2.0](LICENSE) for the code in this repository. What it downloads keeps its own licence (below).

## Requirements

- A Mac with Apple silicon, on **macOS 27** (the base image is macOS 27; a guest newer than the host does not boot).
- **A dedicated Mac.** Do not use it for anything else, and keep no other user accounts on it that you do not trust (see [SECURITY.md](SECURITY.md)).
- At least **16 GB of RAM** (install refuses less).
- At least **512 GB internal disk, with at least 250 GiB free**. The sum: the shim's free-disk floor 100 GiB + the base and golden image ≈ 50 GiB + one rebuild generation ≈ 50 GiB + two jobs' growth ≈ 40 GiB.
- IPv4 behind a NAT router. **ONE network only:** turn Wi-Fi off when the Mac is on Ethernet (wall-check stops when two network ports have an address).
- Outbound access to the public DNS resolvers 1.1.1.1 and 8.8.8.8, to OpenDNS, and to `checkip.amazonaws.com`. OpenDNS and checkip.amazonaws.com must report the same public address.
- The runner user is fixed in v0.x: a Standard user named **`ci`** with the home folder **`/Users/ci`**. The root-owned shim names these paths on purpose (it reads no path from the environment).
- The root step makes `/usr/local/bin` owned by root:wheel, mode 755, without ACLs, for good.

## Install

Do the steps in this order. Each step is one System Settings path or one line to run. Every line that starts with `sudo` runs **only in the admin's own session** (Screen Sharing as the admin, or fast user switching at the Mac's screen) — never with `su` or `sudo` from ci's session or ci's SSH.

1. **Users.** Create your own admin account in Setup Assistant (skip Apple Account and iCloud). Then System Settings → Users & Groups → Add User: **Standard**, name `ci`, a long random password (keep it in your password manager).
2. **FileVault off.** System Settings → Privacy & Security → FileVault: Off. Automatic login needs it off. The cost: the token and the VM images are not encrypted at rest.
3. **Automatic login.** System Settings → Users & Groups → Automatically log in as: `ci`. Restart the Mac once. From then on, never log `ci` out (the runner service runs in ci's login session).
4. **Energy.** System Settings → Energy: "Prevent automatic sleeping when the display is off" On, and "Start up automatically after a power failure" On.
5. **Software Update.** System Settings → General → Software Update: install the latest macOS. Then, under Automatic Updates, turn "Install macOS updates" Off and "Install Security Responses and system files" Off. From now on, install macOS updates and security responses only in the idle runbook ([docs/operations.md](docs/operations.md)), never unattended: an unattended restart kills running jobs, and on a new macOS build runscaler does not start again (and runner-enable refuses) until wall-check has run on it.
6. **Remote Login for ci only.** System Settings → General → Sharing → Remote Login: On, "Allow access for: Only these users" → `ci`. Then, in Terminal as `ci`, add your SSH key (replace the key text):
   ```
   mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo 'ssh-ed25519 AAAA…your-key… you@laptop' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
   ```
   Then, still at the Mac, read its host key and write down the `SHA256:…` part:
   ```
   ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
   ```
   At your first `ssh ci@<the Mac>` from your laptop, type `yes` only if the fingerprint ssh shows is the same. Step 15 sends your token over this connection.
7. **Screen Sharing for the admin.** System Settings → General → Sharing → Screen Sharing: On, and allow your admin user. Connect as the admin and choose "Log in as yourself" (not "Ask for permission"). This is the admin's own session for every `sudo` line below. Paste lines into it with Screen Sharing's shared clipboard.
8. **SSH keys only.** In the admin's own session, turn off password logins (the file name must sort before Apple's `100-macos.conf`):
   ```
   printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' | sudo tee /etc/ssh/sshd_config.d/100-mac-runner.conf >/dev/null
   ```
   Check it: `sudo /usr/sbin/sshd -T | grep -E '^(passwordauthentication|kbdinteractiveauthentication) '` must print `no` twice.
9. **Router.** In your router's settings: NAT loopback (hairpin) off, UPnP and NAT-PMP off, administration from the internet off, and no port forwards to this Mac.
10. **Install the release (as ci).** Open the release you chose on GitHub, open its asset `install-line.txt`, and run that one line as `ci` (over SSH or in ci's Terminal). Check the asset first ("Check a release" below). The line downloads the release, checks its sha256, unpacks it into `/Users/ci/mac-runner/` and runs its `install`. At the end, install prints what is still needed (ROOT LINE, WALL-CHECK, NEXT), and UPDATER: the runner-image updater, OFF on a fresh host ("The updater" below).
11. **The root step (in the admin's own session).** Run the one line in the asset `root-line.txt` of the same release. It copies `setup/02-wall.sh` to a root-owned file, runs it only if its sha256 is the release's, and installs softnet, the shim and its config into `/usr/local`. It prints `02-wall: installed …` on success.
12. **The golden image (as ci).** `/Users/ci/bin/golden-build` — it downloads the pinned base image once (≈ 34 GB; ≈ 41 GB on disk), provisions the GitHub runner in a VM behind the wall, and prints `DONE: liveapp-mac-golden-<yyyymmdd>`. The first run takes as long as the download; a rebuild takes a few minutes. Its last step, the eMudhra stage, hardens the image against the 2026-10 eMudhra incident and checks the result; on a failure golden-build stops and makes no image ([docs/design.md](docs/design.md), "The eMudhra stage").
13. **Configure the scale sets (as ci).** Edit `/Users/ci/.config/runner/config.toml` (install made it from [config/config.toml.example](config/config.toml.example) and set `cpu` and `memory` for this Mac). In each `[[scaleset]]`: `url`, `name`, `labels`, `token`, and `runner-image` = the name golden-build printed. Keep or change `disable-update` (what each value does is written beside it). Neither value keeps the runner current: a new runner comes with a release ("Update", step 6), or with the updater ("The updater").

    For an organization scale set, also set `runner-group`: the group decides which repositories can send jobs to this Mac. Without it, the set joins the organization's Default group (by default: every private repository of the organization). To serve fewer, first create a group: Organization → Settings → Actions → Runner groups → New runner group, Repository access "Selected repositories", "Allow public repositories" off (where your GitHub plan allows more groups).
14. **Prove the wall (as ci).** If your router must forward other ports into your network, first list them in `/Users/ci/.config/runner/wall.conf` ([config/wall.conf.example](config/wall.conf.example)) so wall-check probes them too (install created that folder). Then `/Users/ci/bin/wall-check` — it boots a control VM and a walled VM and probes your network from inside. It ends with `PASS: stamp written …` and the shim's `OK wall stamp matches`. Any STOP names what failed (see [docs/operations.md](docs/operations.md)).
15. **The token.** Create a fine-grained personal access token (GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token):
    - Resource owner: the account or organization that owns the repositories (an organization scale set: the organization).
    - A repository scale set: Repository access "Only select repositories" (the repositories you configured), and Repository permissions → **Administration: Read and write**. You need admin access to those repositories.
    - An organization scale set: Organization permissions → **Self-hosted runners: Read and write** and **Administration: Read**. You must be an owner of the organization.
    - Expiration: 90 days. Put the expiry date in your calendar: an expired token leaves jobs queued, and nothing on the Mac warns. Rotate it before then ([docs/operations.md](docs/operations.md), "Token rotation").
    - An organization can require an owner to approve the token. Until it is approved, step 16 fails: check the token's status on GitHub first.

    Put it on the Mac from **your own terminal** (a hidden prompt; the token never appears on screen or in a command line). For `token = "env:RUNNER_TOKEN_OWNER"` the file is `token-owner` (the part after `RUNNER_TOKEN_`, in lower case; letters, digits and `_` only):
    ```
    read -rs "t?GitHub token: " && print -rn -- "$t" | ssh ci@<the Mac> 'umask 077 && cat > /Users/ci/.config/runner/token-owner && chmod 600 /Users/ci/.config/runner/token-owner'; unset t
    ```
16. **Validate (as ci).** `/Users/ci/bin/runner-start validate` must end with all checks passed.
17. **Enable (as ci).** `/Users/ci/bin/runner-enable` — it refuses, with the reason, unless the root files, the stamp, the wall proof, the service and the lock are all right. Then check that runscaler started:
    ```
    curl -s http://127.0.0.1:8080/healthz
    ```
    Within a minute, every scale set must show `"ready":true`. If not, read why:
    ```
    tail /Users/ci/Library/Logs/mac-runner/runner-start.err /Users/ci/Library/Logs/mac-runner/runscaler.log
    ```
18. **The check workflow.** Copy [examples/runner-check.yml](examples/runner-check.yml) into `.github/workflows/` of a repository a scale set serves, put your label in `runs-on`, and commit it to that repository's default branch (GitHub runs a hand-started workflow only from there). Then, from your laptop: `gh workflow run runner-check.yml -R <owner>/<repo> -f host=<the Mac's LAN address> -f router=<your router's address>` (`/Users/ci/bin/wall-check --derive` prints both). It must be green, and its log must show both addresses blocked.

    Then run [examples/emudhra-check.yml](examples/emudhra-check.yml) the same way (its header says how to set it up). It must be green: it is the proof that the saved image holds the eMudhra fix.

**First adopters:** install's fresh-host steps (creating the folders, writing config.toml, the first LaunchAgent load) have run only in review, not on a fresh Mac. Please send us install's full output (it holds no secret).

## Check a release

Copy the two lines only from the assets of the release you chose — never from the release notes and never from the Mac. From your laptop, with `gh`, in an empty folder:

1. Download the two lines and compare them with the release's `SHA256SUMS` (any gh version):
   ```
   gh release download <tag> -R liveappbase/github-self-hosted-runner -p install-line.txt -p root-line.txt -p SHA256SUMS && for f in install-line.txt root-line.txt; do [[ "$(shasum -a 256 < $f)" == "$(awk -v f=$f '$2 == f {print $1}' SHA256SUMS)  -" ]] && echo "$f matches SHA256SUMS" || echo "$f DIFFERS — do not run it"; done
   ```
   This compares the files only with another asset of the same release.
2. Check them against the release's attestation. This needs gh 2.102.0 or newer: `gh --version` shows yours; `brew upgrade gh` updates it. An older gh may not read this repository's attestations, and gh 2.92.0 or older also sends your GitHub token to another host while it checks (GitHub advisory GHSA-8xvp-7hj6-mcj9).
   ```
   gh release verify <tag> -R liveappbase/github-self-hosted-runner
   ```
   ```
   gh release verify-asset <tag> install-line.txt -R liveappbase/github-self-hosted-runner
   ```
   ```
   gh release verify-asset <tag> root-line.txt -R liveappbase/github-self-hosted-runner
   ```
   Each must pass. `verify-asset` binds the file you will paste to the release's attestation.

`root-line.txt` holds the sha256 of `setup/02-wall.sh`; it must equal the `…/setup/02-wall.sh` line of SHA256SUMS. Never use `shasum -c` on a hash list: it picks the algorithm from the length of each hash.

## Update

1. `/Users/ci/bin/runner-updater status` FIRST (a host on a release before 0.2.0 has no such link: go to step 2). When it shows an open window journal, run `/Users/ci/bin/runner-updater pass` before anything else: its RECOVER then sees CI as the window left it, and ends the window. When that pass prints "another run holds the updater lock", a window is RUNNING: wait, and run `status` again until it shows no open window. Never run runner-disable while a run holds the updater lock: it can make a good switch fail and undo it. When the pass says RECOVER cannot read or act on the window record: "An unfinished window the updater cannot end" below.
2. Wait until no job runs. When step 1 ran `status`: just before runner-disable, check again that no run holds the updater lock: `/usr/sbin/lsof /Users/ci/.local/state/runner-updater/lock` prints nothing (while the updater is ON, a window may start just as CI goes idle). When it prints a line, go back to step 1. Then `/Users/ci/bin/runner-disable` (it waits for a running job; a stop kills a running VM — see [SECURITY.md](SECURITY.md)). With CI disabled: when config.toml has no line `log-file = "/Users/ci/.config/runner/runner.log"` above its first table, add it (config/config.toml.example has it; install never edits an existing config): without it runscaler 0.10.0 and later write their log elsewhere, and the updater refuses the config.
3. Run the new release's `install-line.txt` as ci. Read what install prints. It refuses while an updater run holds its lock, or a window record is open (it names the `pass` to run).
4. Only if install prints `ROOT LINE NEEDED`: the new release's `root-line.txt`, in the admin's own session.
5. If install prints `WALL-CHECK needed`: `/Users/ci/bin/wall-check`.
6. If the new release pins another runner or base image than your image was built with: rebuild the image now ([docs/operations.md](docs/operations.md), "Rebuilding the image", steps 2–5), then go to step 8. This is the only dependable way a new runner reaches the jobs. To compare: `/Users/ci/bin/golden-build --print-runner` prints the runner version a build uses now, and `BASE` in `/Users/ci/bin/golden-build` is the base the release pins. Your image's build log, `/Users/ci/Library/Logs/mac-runner/golden-<yyyymmdd>.log` (the date in `runner-image`), printed the line `runner <version>` and `start: … from <base>, …`. While the updater is ON, a runner change is `/Users/ci/bin/runner-updater rebuild mac-golden` after step 7 (it runs the whole window: build, gate, config, enable), never a hand golden-build.
7. `/Users/ci/bin/runner-enable`.
8. If install printed that runscaler was replaced: run the check workflow, and look for the job's VM in `/Users/ci/Library/Logs/mac-runner/admissions.log`.

Run the tools by their absolute paths (`/Users/ci/bin/…`). A rollback to an older release: "The way back to an older release" below.

### The way back to an older release

The one text for every way back (also [docs/operations.md](docs/operations.md)'s). As ci:

1. When the updater is installed: `/Users/ci/bin/runner-updater off`. When it refuses because a window is unfinished: `/Users/ci/bin/runner-updater pass`; when that pass names a cause, fix it and run `off` again; when it says RECOVER cannot read or act on the window record: the hand steps of "An unfinished window the updater cannot end" (CI is then up), and go on with the record left as it is. That works only for a way back to a release WITHOUT the updater (v0.1.0-rc.3): an older 0.2.x install refuses an open record too, so a way back between two 0.2.x releases needs the maintainer's clear first. Write down the 0.2.x folder that is current: `readlink /Users/ci/mac-runner/current`.
2. When the updater's agent is loaded (`launchctl print gui/$(id -u)/sh.liveapp.runner-updater` prints it) and no run holds the updater lock (`/usr/sbin/lsof /Users/ci/.local/state/runner-updater/lock` prints nothing):
   ```
   launchctl bootout gui/$(id -u)/sh.liveapp.runner-updater
   ```
3. When it is there, move its plist out of LaunchAgents (launchd loads that folder again at the next login):
   ```
   mv /Users/ci/Library/LaunchAgents/sh.liveapp.runner-updater.plist /Users/ci/mac-runner/updater-plist.prev
   ```
4. `/Users/ci/bin/runner-disable`; then the older release's install: `/Users/ci/mac-runner/<older VERSION>/install` when that folder holds the release you want, else that release's `install-line.txt` (an rc of the SAME VERSION replaced the folder). THE CONFIG: the copy you made before the change, checked by its sha256, and only when `/Users/ci/Applications/tart.app/Contents/MacOS/tart list` still has each image it names; else the current config. Then `/Users/ci/bin/runner-start validate`, then `/Users/ci/bin/runner-enable`.

- On v0.1.0-rc.3, `runner-enable --check` ENABLES CI (it ignores its arguments): never run it there.
- Do not prune on the older release while a candidate is open (`status` showed one): its golden-prune ignores the protected list.
- After a way back to a release without the link, the weekly watchdog's line for this host fails until 0.2.0 is back: tell the watchdog's owner, or expect its could-not-run ask.
- With an unfinished window record left as it is (step 1), the updater's state stays ON: a later 0.2.x install refuses until the maintainer clears the record.

## The updater

From release 0.2.0 the host carries the runner-image updater, `/Users/ci/bin/runner-updater`. It builds a new golden image when GitHub publishes a new runner, gates it, switches a family's scale sets to it in a window with CI disabled, watches the jobs on it for 72 h, and rolls back when they fail. Every rule: [docs/operations.md](docs/operations.md) ("The updater: status, on, off, pass, protect" and the sections after it).

- It is OFF after a fresh install, and an upgrade keeps it ON or OFF. Install prints `UPDATER` (the first line of `runner-updater status`) and, while it is OFF, a line `NEXT (optional)`.
- Its timer, the LaunchAgent `sh.liveapp.runner-updater` (install loads it), runs `/Users/ci/bin/runner-updater pass --log /Users/ci/Library/Logs/mac-runner/runner-updater.log` every 10 min. While the updater is OFF a pass does nothing, but it still ends an unfinished window. The log has one block per pass, from `=== pass <UTC> pid N` to `=== end rc N <UTC>`; above 1 MiB it is renamed to `runner-updater.log.1`. What a pass could not write there goes to `runner-updater.err` beside it.
- Turn it on, as ci:
  1. Write its families file, `/Users/ci/.config/runner-updater/families` (its folder 0700): one line per family, `FAMILY tart SET [SET ...]`, with every scale set of the family (its `name` in config.toml) on that ONE line. Only `mac-golden` has a builder in this release. For example:
     ```
     mkdir -m 700 -p /Users/ci/.config/runner-updater && print -r -- 'mac-golden tart mac-ci-one mac-ci-two' > /Users/ci/.config/runner-updater/families
     ```
  2. `/Users/ci/bin/runner-updater on` (it refuses a warm pool: a `pool-size` other than 0).
  3. `/Users/ci/bin/runner-updater status` shows ON. The first pass holds `STOP NO BASELINE` until the family has a recipe baseline: run `/Users/ci/bin/runner-updater rebuild mac-golden` once (a full window, with CI disabled while it builds); the accept of the image it builds, after up to 72 h of jobs, writes the baseline.
- `/Users/ci/bin/runner-updater off` turns it off. While it is ON, a runner change is `runner-updater rebuild mac-golden`, never a hand golden-build.

### An unfinished window the updater cannot end

A window journal (the record), `/Users/ci/.local/state/runner-updater/window`, that RECOVER says it cannot read or act on (a bug, or a damaged file), or a state the updater cannot load while that record is open: every pass stops there and acts on nothing, and install and `off` refuse. CI may be down. These hand steps bring CI back on a config chosen from the record. They delete no image and never touch the record. Then the maintainer clears it (below).

Run them as ci, in this order:

1. No run holds the updater lock: `/usr/sbin/lsof /Users/ci/.local/state/runner-updater/lock` prints nothing. When it prints a line, a run holds the lock (a window may be RUNNING, with its record open): wait as "Update" step 1 says, then run `/Users/ci/bin/runner-updater status` again. Go on only when no run holds the lock and `status` still names this section.
2. Leave the record as it is: do not delete, move or edit it. Read it: `cat /Users/ci/.local/state/runner-updater/window`. The steps use its lines `kind` (switch or rollback), `config-sha`, `backup PATH`, `image NAME`, `gate-clone NAME`, `disable-start`, `installed EPOCH SHA …` (the LAST one counts), `state-write …` and `hand-change SHA`.
3. CI ALREADY RIGHT, before any wait. The config's sha: `shasum -a 256 /Users/ci/.config/runner/config.toml`. CI already runs a right file when `/Users/ci/.config/runner/enabled` exists, ONE runscaler runs (`TZ=UTC0 ps -ax -o pid,lstart,args | grep '/Users/ci/bin/runne[r] run'`: its start time in UTC), and EITHER the record has an `installed` line, that runscaler started after its EPOCH (`date -u -r EPOCH`: also UTC) and the config's sha is that line's SHA, OR the record has no `disable-start` line and the config's sha is its `config-sha`. A record with `disable-start` but no `installed` line is never "already right". When CI is already right: do steps 4 and 5 only, then step 9.
4. The window's tools. `ps -ax -o pid,pgid,user,args | grep -E '/Users/ci/mac-runner/[^/]+/bin/golden-(build|emudhra|gat[e])'` lists them. When one runs as ci, wait 5 min and look again. When it still runs, stop THAT process's group (its pgid): `kill -TERM -- -<pgid>`. Only those three tools' groups (their real-run is in their group), never by a name pattern, never runscaler, and never because runner-lock-free says `held` (runscaler holds the runner lock while CI runs).
5. The window's VMs, by EXACT name only: the record's `gate-clone` name, and for a `kind switch` record its second `image` line (a name `gold-<yyyymmdd>`). For each one that `/Users/ci/Applications/tart.app/Contents/MacOS/tart list` shows `running`: `/Users/ci/Applications/tart.app/Contents/MacOS/tart stop <name>`. Never a rollback record's `image` lines, never by a prefix.
6. When `/Users/ci/.config/runner/enabled` exists: `/Users/ci/bin/runner-disable` (it waits for a running job: wait for it). When it is absent and `/Users/ci/bin/runner-lock-free` says `held`, a runscaler still drains: wait until it says `free`, reading it every 10 s for up to 3700 s, and send no signal (do not run runner-disable here):
   ```
   n=0; until [[ $(/Users/ci/bin/runner-lock-free) == free ]] || (( n++ >= 370 )); do sleep 10; done; /Users/ci/bin/runner-lock-free
   ```
   Still `held` at the end: stop here, with CI as it is, and tell the maintainer. Then copy the config as found aside, never over a file, and check the copy (the two shas must be the same):
   ```
   c=/Users/ci/.config/runner/config.toml; f=$c.found.$(date -u +%Y%m%d%H%M%S); cp -n -p $c $f && shasum -a 256 $c $f
   ```
7. THE CHOICES, in this order. Put a choice in place by copy and rename, and check that its sha is the choice's:
   ```
   c=/Users/ci/.config/runner/config.toml; cp -p <the choice> $c.new && mv $c.new $c && shasum -a 256 $c
   ```
   Then validate it, and classify the output with the release's own tool (the updater's one validate rule):
   ```
   /Users/ci/bin/runner-start validate > /Users/ci/validate.out 2>&1; /bin/zsh -f /Users/ci/mac-runner/current/bin/validate-class $? /Users/ci/validate.out
   ```
   `PASS`: go to step 8. `API-ONLY` (GitHub's API did not answer): validate again, 20 s apart, up to 3 times; the third `API-ONLY` counts as a pass. `NON-API` or `UNKNOWN`: the NEXT choice.
   1. The file with the last `installed` line's SHA, when the record is `kind rollback`, or has a `state-write switched` or `state-write rolled` line, or a `hand-change` line whose SHA is that SHA. It is the config itself when the config's sha is that SHA; else it is in the window's work folder, `/Users/ci/.local/state/runner-updater/windows/<the record's window ID>.d/`: the one `config.toml.*` file there whose sha (`shasum -a 256 …/config.toml.*`) is that SHA.
   2. The backup (the record's `backup` path), when its sha is the record's `config-sha`.
   3. The config as found (the copy of step 6).
8. On the first choice that passes: note the time, `date -u`, then `/Users/ci/bin/runner-enable`. It counts only when it prints `runner-enable: enabled`. A refusal is never a reason to try the next choice (runner-enable reads no config): read its text. When it says `the runner lock is not free`, a runscaler still drains: go back to step 6's wait, then runner-enable again. When it says `a VM outside runscaler is running` and each VM it names is one of step 5's (a record VM still runs): step 5, then runner-enable again. Any other text (another VM too): stop here, with the validated choice in place and CI down, and tell the maintainer at once. Then the start check, within 10 min: `/Users/ci/.config/runner/enabled` exists and ONE runscaler runs that started AFTER that time (step 3's `TZ=UTC0 ps` line; both are UTC). launchd may wait up to 300 s before it starts one. When it does not start: `/Users/ci/bin/runner-disable`, then the NEXT choice. CI never starts on a config that did not validate. When every choice fails, CI stays down and the last choice tried is the config left in place: it did not validate, or did not start. Tell the maintainer at once.
9. Tell the maintainer, with the record's text. Until the maintainer clears it, every pass stops at RECOVER and acts on nothing; `off` and install refuse.

A residual: a rollback record whose target never ran goes back on the image R1 rejected (the backup), and its jobs may fail until the maintainer acts.

**The maintainer's clear**, after the hand steps, as ci:

1. When no run holds the updater lock (`/usr/sbin/lsof /Users/ci/.local/state/runner-updater/lock` prints nothing), boot the timer out, so no timer pass runs between the move and `off`:
   ```
   launchctl bootout gui/$(id -u)/sh.liveapp.runner-updater
   ```
2. MOVE the record aside, never delete it (it is kept for diagnosis; no part of the updater reads that folder):
   ```
   mkdir -m 700 -p /Users/ci/.local/state/runner-updater/aside && mv -n /Users/ci/.local/state/runner-updater/window /Users/ci/.local/state/runner-updater/aside/window.$(date -u +%Y%m%d%H%M%S)
   ```
3. At once: `/Users/ci/bin/runner-updater off`, so no pass acts on a state the hand steps did not update (a candidate, a pin, a protected image). When it prints `WAIT` or `REFUSE` (the state), `off` cannot run: leave the agent booted out until the state is fixed.
4. Delete the leftovers the hand steps stopped, each only when no line of config.toml (other than a comment) names it (`grep -n '<name>' /Users/ci/.config/runner/config.toml`): the record's `gate-clone` name; for a `kind switch` record its work VM (the second `image` line) and, when the record has no `gate green 0` line, its output (the third). For each: `/Users/ci/Applications/tart.app/Contents/MacOS/tart delete <name>`. A stopped clone left in place makes every later golden-gate stop.
5. Load the timer again:
   ```
   launchctl bootstrap gui/$(id -u) /Users/ci/Library/LaunchAgents/sh.liveapp.runner-updater.plist
   ```
6. `/Users/ci/bin/runner-updater on` only after you compared, for each family, the candidate `status` shows (or none) with each set's `runner-image` line in config.toml: `status` reads no config, so it cannot show what runs.

After a way back to v0.1.0-rc.3: rc.3's install removed the `/Users/ci/bin/runner-updater` link, and it has no updater agent. Run `off` from the 0.2.x folder you wrote down (`/Users/ci/mac-runner/<VERSION>/bin/runner-updater off`), skip lines 1 and 5, and do line 6 only after the next 0.2.x install.

## Move an existing host onto a release

install never overwrites a file in `/Users/ci/bin` that is not its own link. If the tools are there as files from an earlier hand install, disable the agent, move them (all but `/Users/ci/bin/runner`) to a folder of their own, and keep that folder until the new release has run a green check workflow. [docs/operations.md](docs/operations.md) ("Moving a host onto a release") has the full list and the way back.

## Uninstall

As ci:

1. `/Users/ci/bin/runner-disable`
2. Remove each scale set from GitHub: runscaler never removes one on its own, and jobs that name your label would stay queued. One line per `[[scaleset]]` of config.toml: `<name>` is its `name`, and `RUNNER_TOKEN_OWNER` / `token-owner` are what its `token` names. The token goes in through the environment, never the command line:
   ```
   RUNNER_TOKEN_OWNER="$(</Users/ci/.config/runner/token-owner)" /Users/ci/bin/runner scaleset delete <name> --config /Users/ci/.config/runner/config.toml
   ```
   Its pass: `Deleted runner scale set "<name>" (ID N)`. `No runner scale set named … is registered` is NOT a pass (a wrong token or scope prints it too): check the Runners page of the repository or organization (Settings → Actions → Runners).
3. `launchctl bootout gui/$(id -u)/sh.liveapp.mac-runner` and `rm /Users/ci/Library/LaunchAgents/sh.liveapp.mac-runner.plist`; the updater's timer the same way: `launchctl bootout gui/$(id -u)/sh.liveapp.runner-updater` and `rm /Users/ci/Library/LaunchAgents/sh.liveapp.runner-updater.plist`
4. `/Users/ci/Applications/tart.app/Contents/MacOS/tart list` shows the VMs. Delete every `liveapp-mac-golden-*` and `runner-*` VM it shows: `/Users/ci/Applications/tart.app/Contents/MacOS/tart delete <name>`
5. `rm /Users/ci/.config/runner/token-*`
6. `rm -rf /Users/ci/.tart /Users/ci/mac-runner /Users/ci/Applications/tart.app /Users/ci/bin/runner` (the image cache is ≈ 41 GB), and the updater's state, its families file and its logs: `rm -rf /Users/ci/.local/state/runner-updater /Users/ci/.config/runner-updater /Users/ci/Library/Logs/mac-runner/runner-updater.*` (the state folder holds the updater's history, its closed window journals: keep a copy if you want it)
7. On GitHub: **revoke the token.**

Then, in the admin's own session, two lines (they remove the root files whatever the record says — a softnet that does not match the record is the more suspect case):

```
sudo rm -f /usr/local/bin/softnet
```
```
sudo rm -rf /usr/local/libexec/liveapp-ci
```

## What it downloads, and their licences

Nothing third-party is in this repository. install downloads each tool by digest ([setup/downloads.manifest](setup/downloads.manifest)), and golden-build downloads the GitHub runner by digest:

- **Tart 2.41.1** and **softnet 0.24.1** — Functional Source License 1.1 with an Apache-2.0 future licence (FSL-1.1-ALv2). Running your own CI on your own Macs is fine. Selling hosted macOS runners to others is a competing use under that licence.
- **runscaler 0.9.5** — MIT.
- **GitHub Actions runner 2.338.2** — MIT.
- The base image `ghcr.io/cirruslabs/macos-golden-gate-base`, pinned by digest, holds macOS (Apple's licence: at most two macOS VMs per Apple computer you own or control, for software development and testing, macOS Server, or personal non-commercial use) and software that Cirrus Labs installed in it (Homebrew packages, Rosetta, tart-guest-agent), each under its own licence.
