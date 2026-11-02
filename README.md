# mac-github-self-hosted-runner

Turn an Apple-silicon Mac into a GitHub Actions host that runs every job in a **fresh Tart VM behind a network wall**.

- Each job gets a new macOS VM, cloned from a golden image and deleted after the job. At most 2 jobs run at once (Apple allows 2 macOS VMs per Mac).
- [runscaler](https://github.com/ysya/runscaler) takes the jobs from GitHub (one scale set per repository or organization) and starts the VMs with [Tart](https://github.com/openai/tart).
- Every VM starts behind [softnet](https://github.com/openai/softnet): it reaches the internet, but not this Mac, your network, your router, the clipboard or the audio input.
- A root-owned `tart` shim admits a VM start only when a **live proof** of that wall (`wall-check`) matches the installed Tart, softnet and shim.
- You install it from ONE published release, with ONE root step whose exact line is an immutable release asset.

Status: **v0.1.0, pre-release.** The design and its reasons: [docs/design.md](docs/design.md). Day-to-day work: [docs/operations.md](docs/operations.md). What the wall does and does not protect: [SECURITY.md](SECURITY.md).

A Linux host that runs each job in a fresh Docker container has its own folder and install: [linux-docker/README.md](linux-docker/README.md).

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
10. **Install the release (as ci).** Open the release you chose on GitHub, open its asset `install-line.txt`, and run that one line as `ci` (over SSH or in ci's Terminal). Check the asset first ("Check a release" below). The line downloads the release, checks its sha256, unpacks it into `/Users/ci/mac-runner/` and runs its `install`. At the end, install prints what is still needed (ROOT LINE, WALL-CHECK, NEXT).
11. **The root step (in the admin's own session).** Run the one line in the asset `root-line.txt` of the same release. It copies `setup/02-wall.sh` to a root-owned file, runs it only if its sha256 is the release's, and installs softnet, the shim and its config into `/usr/local`. It prints `02-wall: installed …` on success.
12. **The golden image (as ci).** `/Users/ci/bin/golden-build` — it downloads the pinned base image once (≈ 34 GB; ≈ 41 GB on disk), provisions the GitHub runner in a VM behind the wall, and prints `DONE: liveapp-mac-golden-<yyyymmdd>`. The first run takes as long as the download; a rebuild takes a few minutes. Its last step, the eMudhra stage, hardens the image against the 2026-10 eMudhra incident and checks the result; on a failure golden-build stops and makes no image ([docs/design.md](docs/design.md), "The eMudhra stage").
13. **Configure the scale sets (as ci).** Edit `/Users/ci/.config/runner/config.toml` (install made it from [config/config.toml.example](config/config.toml.example) and set `cpu` and `memory` for this Mac). In each `[[scaleset]]`: `url`, `name`, `labels`, `token`, and `runner-image` = the name golden-build printed. Keep or change `disable-update` (what each value does is written beside it). Neither value keeps the runner current: a new runner comes with a release ("Update", step 5).

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
   gh release download <tag> -R liveappbase/mac-github-self-hosted-runner -p install-line.txt -p root-line.txt -p SHA256SUMS && for f in install-line.txt root-line.txt; do [[ "$(shasum -a 256 < $f)" == "$(awk -v f=$f '$2 == f {print $1}' SHA256SUMS)  -" ]] && echo "$f matches SHA256SUMS" || echo "$f DIFFERS — do not run it"; done
   ```
   This compares the files only with another asset of the same release.
2. Check them against the release's attestation. This needs gh 2.102.0 or newer: `gh --version` shows yours; `brew upgrade gh` updates it. An older gh may not read this repository's attestations, and gh 2.92.0 or older also sends your GitHub token to another host while it checks (GitHub advisory GHSA-8xvp-7hj6-mcj9).
   ```
   gh release verify <tag> -R liveappbase/mac-github-self-hosted-runner
   ```
   ```
   gh release verify-asset <tag> install-line.txt -R liveappbase/mac-github-self-hosted-runner
   ```
   ```
   gh release verify-asset <tag> root-line.txt -R liveappbase/mac-github-self-hosted-runner
   ```
   Each must pass. `verify-asset` binds the file you will paste to the release's attestation.

`root-line.txt` holds the sha256 of `setup/02-wall.sh`; it must equal the `…/setup/02-wall.sh` line of SHA256SUMS. Never use `shasum -c` on a hash list: it picks the algorithm from the length of each hash.

## Update

1. Wait until no job runs, then `/Users/ci/bin/runner-disable` (it waits for a running job; a stop kills a running VM — see [SECURITY.md](SECURITY.md)).
2. Run the new release's `install-line.txt` as ci. Read what install prints.
3. Only if install prints `ROOT LINE NEEDED`: the new release's `root-line.txt`, in the admin's own session.
4. If install prints `WALL-CHECK needed`: `/Users/ci/bin/wall-check`.
5. If the new release pins another runner or base image than your image was built with: rebuild the image now ([docs/operations.md](docs/operations.md), "Rebuilding the image", steps 2–5), then go to step 7. This is the only dependable way a new runner reaches the jobs. To compare: `/Users/ci/bin/golden-build --print-runner` prints the runner version a build uses now, and `BASE` in `/Users/ci/bin/golden-build` is the base the release pins. Your image's build log, `/Users/ci/Library/Logs/mac-runner/golden-<yyyymmdd>.log` (the date in `runner-image`), printed the line `runner <version>` and `start: … from <base>, …`.
6. `/Users/ci/bin/runner-enable`.
7. If install printed that runscaler was replaced: run the check workflow, and look for the job's VM in `/Users/ci/Library/Logs/mac-runner/admissions.log`.

Run the tools by their absolute paths (`/Users/ci/bin/…`). A rollback is the same steps with the older release's lines.

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
3. `launchctl bootout gui/$(id -u)/sh.liveapp.mac-runner` and `rm /Users/ci/Library/LaunchAgents/sh.liveapp.mac-runner.plist`
4. `/Users/ci/Applications/tart.app/Contents/MacOS/tart list` shows the VMs. Delete every `liveapp-mac-golden-*` and `runner-*` VM it shows: `/Users/ci/Applications/tart.app/Contents/MacOS/tart delete <name>`
5. `rm /Users/ci/.config/runner/token-*`
6. `rm -rf /Users/ci/.tart /Users/ci/mac-runner /Users/ci/Applications/tart.app /Users/ci/bin/runner` (the image cache is ≈ 41 GB)
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
