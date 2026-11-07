# linux-docker — a Linux CI host that runs every job in a fresh Docker container

This folder is the repository's Linux host type: a Linux server where [runscaler](https://github.com/ysya/runscaler) takes jobs from GitHub runner scale sets and starts each one in a new container from a local runner image. The other host type, an Apple-silicon Mac, is the rest of the repository ([../README.md](../README.md)).

- Two host users. **RUN_USER** runs a rootless Docker daemon ("D1") and a local image registry, and holds no secret. **RS_USER** runs only runscaler (a systemd user unit) and holds the GitHub token; it reaches D1 through a second socket, as a member of RUN_USER's group. No job reaches a root Docker daemon.
- Jobs run on a `runners` network, with a pinned seccomp profile, no-new-privileges and an init process; `docker.dind` is always false. `runner-start` refuses to start runscaler with a config that would give a job a Docker socket.
- Every value of the host (the users, ports, address, organization, token name, set names and labels) is in ONE host config file, `/etc/liveapp-ci/host.conf`. The scripts hold none of them, and each one refuses to run without that file.

Status: these scripts run one host (Ubuntu 26.04, x86_64, Docker 29.9.0). They moved here unchanged except that the host values left them, and except the release path (`02-d1.sh build VERSION`, then `pool-image.sh up VERSION` from its build record: "A new runner release" below), `03-runscaler.sh render`, `pool-image.sh`'s unattended modes ("The updater's switch and rollback" below), and the updater's `bin/runner-updater` with its timer (`setup/04-timer.sh`: "The updater: status, on, off, pass, build" below), which are new and have not yet run on that host. `runner-start` refuses any Docker version other than the one the seccomp profile was cut from (29.9.0).

## Files

| File | Runs as | What it does |
|---|---|---|
| `host.conf.example` | — | Every key of the host config, with placeholder values and what each one is. |
| `setup/01-users.sh` | root | Creates RUN_USER and RS_USER, the group, the ssh keys, the runscaler lock rule and linger. Re-runnable. |
| `setup/01-users-undo.sh` | root | Removes only what 01-users.sh made (its header lists what must happen first). |
| `setup/02-d1.sh` | RUN_USER | With no argument (the full run): the rootless Docker daemon and its hardening, the `runners` network, the local registry, and the runner image of the host config's `RUNNER_VERSION` (built, pushed, checked; then its build record, and its digest goes to `~/run/image.ref`). With `build VERSION`: only the runner image of that release, its checks and its build record. |
| `setup/runner-release.sh` | RUN_USER, RS_USER | Read by 02-d1.sh, by 03-runscaler.sh, by pool-image.sh (`up`, `back` and its unattended modes) and by `bin/runner-updater` (both users), never run: how a runner release is read from GitHub and when the latest one is old enough (2 days), the trust of every download (below), the one copy of the image recipe and of the build record reader, the one reader of a file the host's other user owns (`rr_read`: RUN_USER's files are read as hostile), the one compare of two runscaler configs (`rr_same_but_image`: its comment lines are not part of a config), and the updater lock. |
| `setup/03-runscaler.sh` | RS_USER | Installs `runner-start`, `pool-ready`, `validate-class` and the unit, and runscaler (by sha256) on a fresh host only; renders, checks and installs the config (`real`, with the image config.toml runs unless it is given one). Never restarts runscaler, and never replaces one that is there. `render` (the updater's) renders and validates a config into a file of its own and installs nothing. |
| `setup/runner-facts.sh` | RS_USER, RUN_USER | Read by pool-image.sh's unattended modes and by `bin/runner-updater` (both users), never run: the one copy of what the updater measures (runscaler's process as systemd reports it, its log position and the log text since the last pass, the config's sets and images, the jq check, the two `/healthz` reads). |
| `setup/pool-image.sh` | RS_USER | Puts the image of a runner release's build record into the pool (`up VERSION`), rolls it back (`back`), or ends the release (`accept`). `runscaler` changes runscaler itself: the release this one pins, or the way back ("runscaler: the release this one pins, and the way back", below). The updater's own switch, rollback and recovery are its unattended modes (`up --unattended`, `back --unattended`, `recover --unattended`: the updater's only, "The updater's switch and rollback", below). |
| `setup/04-timer.sh` | RS_USER, RUN_USER | The updater's timer (Install step 11): installs `config/runner-updater.service` and `config/runner-updater.timer` as the user's own systemd units and starts the timer, which runs `runner-updater pass` every 10 minutes. It reads the user's linger and never changes it. |
| `bin/runner-updater` | RS_USER, RUN_USER | The runner-image updater, one program for both users. As RS_USER: `status`, `on`, `off`, `pass`, which ends a window a cut left, measures, asks the decision core, rolls the pool back on R1's verdict, and prints what else it would do and which runner release it would switch to (it switches nothing in this release), and `back hz-docker`, a person's rollback. As RUN_USER: `status`, `on`, `off`, `pass`, which builds the image of the latest runner release that is old enough, and `build VERSION` ("The updater: status, on, off, pass, build" below). Install step 10 links it into `~/bin` of both users; Install step 11 starts its timer. |
| `bin/runner-start` | RS_USER | The unit's start command: checks the config, D1, the registry and the token files, then starts runscaler. |
| `bin/validate-class` | RS_USER | The class of one `runner-start validate` result (PASS, API-ONLY, NON-API or UNKNOWN): the same rule as the Mac's `bin/validate-class`. |
| `bin/pool-ready` | RS_USER | Is runscaler serving exactly the named sets, each ready? |
| `image/Dockerfile` | RUN_USER | The runner image: GitHub's runner image by digest (the pinned base), the runner of the release 02-d1.sh fetched, plus bubblewrap, gh, a locale and build tools. |
| `image/install-runner.sh` | (the build) | Run inside the image build: puts the fetched runner in place of the base image's runner. |
| `../setup/tls-excluded-spki` | — | The CA keys no download trusts (the repository's top-level `setup/`; the install puts it into `~/build/setup/`). |
| `../core/` | RS_USER | The updater's decision core, the same files as the Mac's (the repository's top-level `core/`; the install puts it into `~/build/core/`): the unattended switch asks its `idle.jq` whether the pool is idle, under a jq that `core/TESTED_JQ` lists. |
| `config/` | — | runscaler's systemd unit, the updater's two (`runner-updater.service`, one pass, and `runner-updater.timer`, every 10 minutes: the same files for both users), and the two seccomp profiles (Docker's default, and the one the jobs run with). |

`setup/pool-image.sh` pins `setup/03-runscaler.sh`, `bin/runner-start`, `bin/pool-ready`, `bin/validate-class` and `config/runscaler.service` by sha256 (`PINS`); `03-runscaler.sh render` reads the same pins. `tools/release-check` refuses a release in which one of them changed without its pin.

## Install

You need: a dedicated x86_64 Linux host with systemd, root ssh with your key, Docker Engine 29.9.0 with its rootless extras (`dockerd-rootless-setuptool.sh`) and `uidmap`, and `python3` (3.11 or newer), `curl`, `jq`, `ss`, `nsenter` and `ip` on it. The jq must be a version that `core/TESTED_JQ` lists for `core` (the `jq` package of Ubuntu 26.04 and of 24.04 is one): the updater's switch stops under any other. The scripts touch no root Docker daemon and no other user.

Run every line below from your laptop, in a checkout of the release you chose (replace `<host>`, `<version>` and the user names with yours):

```
git clone --branch v<version> --depth 1 https://github.com/liveappbase/github-self-hosted-runner && cd github-self-hosted-runner
```

1. **The host config (root).** Copy `linux-docker/host.conf.example` to `host.conf`, set every value (each key's comment says what it is), then install it as root's file:
   ```
   ssh root@<host> 'install -d -m 755 /etc/liveapp-ci && umask 022 && cat > /etc/liveapp-ci/host.conf.new && chmod 644 /etc/liveapp-ci/host.conf.new && mv /etc/liveapp-ci/host.conf.new /etc/liveapp-ci/host.conf' < host.conf
   ```
2. **The users (root).** It copies root's `authorized_keys` to both users, so the lines below can ssh as them. It must end with `R1 DONE`:
   ```
   ssh root@<host> 'bash -s' < linux-docker/setup/01-users.sh
   ```
3. **The files (once as RUN_USER, once as RS_USER).** On a host where the updater is installed (Install step 10), first see what RS_USER's updater holds, as RS_USER:
   ```
   ssh <RS_USER>@<host> '~/bin/runner-updater status'
   ```
   With no `window journal` line, go on. With one, end it first: run `~/bin/runner-updater pass` as RS_USER (ON or OFF, a pass ends a window a cut left before anything else), and `status` again, until it shows none (an open journal that stays has a line that says why, and "An unfinished window the updater cannot end", below, is for the one no run ends). An updater too old to end it (its `status` or `pass` prints `STOP RECOVER needed`) cannot: install this release's files anyway (below), and end it with this release's updater right after them. Then each user gets this release's `linux-docker/` as `~/build`, with the repository's `setup/tls-excluded-spki` in `~/build/setup/` and its `core/` as `~/build/core/` (an older `~/build` is moved aside, not deleted). `COPYFILE_DISABLE=1` keeps macOS's tar from adding `._` files, which would become part of the image recipe:
   ```
   COPYFILE_DISABLE=1 tar -C linux-docker -cf - . -C .. setup/tls-excluded-spki core | ssh <RUN_USER>@<host> 'rm -rf ~/build.new && mkdir ~/build.new && tar -C ~/build.new -xf - && { [ ! -e ~/build ] || mv ~/build ~/build.prev.$(date -u +%Y%m%dT%H%M%SZ); } && mv ~/build.new ~/build'
   ```
   Then the same line with `<RS_USER>`. Then, on a host where the updater is installed, run this release's updater as RS_USER (`~/bin/runner-updater` now runs the copy in `~/build`): `status`, and with a `window journal` line (one an older updater could not end), `pass` (it ends a window a cut left before anything else) and `status` again, until it shows none. Go on with step 4 only once `status` shows no `window journal` line: `03-runscaler.sh real` (step 9) refuses while a window journal is there. One this release's updater cannot end either (its line names it): "An unfinished window the updater cannot end", below:
   ```
   ssh <RS_USER>@<host> '~/bin/runner-updater pass; ~/bin/runner-updater status'
   ```
4. **runscaler's download (RS_USER).** runscaler v0.12.0, the release this one pins. On a fresh host (no `~/bin/runner` yet) 03-runscaler.sh installs it, and checks its sha256 before it extracts anything. A host that runs runscaler already keeps the one it has: only `pool-image.sh runscaler` changes it, from this download ("runscaler: the release this one pins, and the way back", below):
   ```
   ssh <RS_USER>@<host> 'mkdir -p ~/build/dl && curl -fsSL -o ~/build/dl/runner-linux-amd64.tar.gz https://github.com/ysya/runscaler/releases/download/v0.12.0/runner-linux-amd64.tar.gz'
   ```
5. **D1 and the runner image (RUN_USER).** It builds the runner version the host config's `RUNNER_VERSION` names, the way "A new runner release" below does, and writes its digest to `~/run/image.ref` (nothing else writes that file). It must end with `B2 DONE (D1)`:
   ```
   ssh <RUN_USER>@<host> 'bash -s' < linux-docker/setup/02-d1.sh
   ```
6. **The pool's numbers (RS_USER).** `CONCURRENT` must be `MAX + 1` (one slot for the small lane). Size them for your host:
   ```
   ssh <RS_USER>@<host> 'install -d -m 700 ~/.config/runner && umask 077 && printf "CONCURRENT=3\nCPU=4\nMEMORY=4096\nMAX=2\nSMALL_CPU=2\nSMALL_MEMORY=2048\n" > ~/.config/runner/pool.env'
   ```
7. **The runner group (on GitHub).** The sets join the runner group the host config's `GROUP` names, and runscaler refuses a set whose group does not exist. The group decides which repositories can send jobs to this host. Create it: Organization → Settings → Actions → Runner groups → New runner group, named as `GROUP`, Repository access "Selected repositories" (pick them), "Allow public repositories" off (where your GitHub plan allows more groups; else set `GROUP` to `Default`). Or with gh, as an organization owner (`<ORG>` is the organization of `ORG_URL`), then pick its repositories on that page:
   ```
   gh api -X POST orgs/<ORG>/actions/runner-groups -f name=<GROUP> -f visibility=selected -F allows_public_repositories=false
   ```
   For a repository URL there is no group to create: `GROUP` must be `Default`.
8. **The token (RS_USER).** Create it as the Mac README says ([../README.md](../README.md), Install step 15). Put it into the file the host config's `TOKEN_FILE` names, from a hidden prompt:
   ```
   read -rs "t?GitHub token: " && print -rn -- "$t" | ssh <RS_USER>@<host> 'umask 077 && cat > ~/.config/runner/<TOKEN_FILE>'; unset t
   ```
9. **runscaler (RS_USER).** On a fresh host, one with no `~/bin/runner`, it installs runscaler v0.12.0 from step 4's download: its sha256 checked, into `~/bin/runner.new`, then renamed over `~/bin/runner`. On a host with one, it keeps it as it is and checks the config with it: runscaler v0.12.0, or v0.9.5 (the way back, and the runscaler of a host installed before this release). Any other runscaler there, and it stops before it changes anything, naming `pool-image.sh runscaler`, the one step that changes runscaler ("runscaler: the release this one pins, and the way back", below). The config it renders names runscaler's log with a top-level `log-file` line: `runner.log` in RS_USER's `~/.config/runner`, the file the updater and `pool-image.sh` read (without that line, runscaler v0.10 and later write their log elsewhere). `runner-start` refuses a config whose `log-file` is another file or is inside a table, and a config with no `log-file` line on any runscaler but v0.9.5 (the one release that then writes `runner.log` beside the config). It must end with `03 DONE (real)`:
   ```
   ssh <RS_USER>@<host> 'bash -s -- real' < linux-docker/setup/03-runscaler.sh
   ```
   Then start it, and check that both sets are ready (within a minute):
   ```
   ssh <RS_USER>@<host> 'systemctl --user enable --now runscaler && sleep 60 && ~/bin/pool-ready <MAIN_SET> <SMALL_SET>'
   ```
10. **The updater (RS_USER and RUN_USER).** It links `~/bin/runner-updater` to the copy in `~/build`, so after a release's step 3 it runs that release's files. A fresh install is OFF for both users ("The updater: status, on, off, pass, build" below):
   ```
   ssh <RS_USER>@<host> 'install -d -m 700 ~/bin && ln -sfn ~/build/bin/runner-updater ~/bin/runner-updater'
   ```
   Then the same line with `<RUN_USER>`.
11. **The updater's timer (RS_USER and RUN_USER).** It installs the updater's two systemd user units (`runner-updater.service` and `runner-updater.timer`, the same files for both users) into `~/.config/systemd/user/` and starts the timer: from then on each user's updater runs `runner-updater pass` every 10 minutes: the first time at once when the host has been up for 10 minutes, else 10 minutes after a boot. A fresh updater is OFF, and a pass while OFF only ends a window journal a cut left and holds or clears `STOP POOL DOWN` ("The updater", below), so it measures and rolls back nothing until `runner-updater on`. It needs the user's linger, which Install step 2 gives (it only reads it, and refuses without it), and step 10's link. It must end with `04 DONE (<user>)`; run it again after a release that changes `config/runner-updater.service` or `config/runner-updater.timer`:
   ```
   ssh <RS_USER>@<host> 'bash ~/build/setup/04-timer.sh'
   ```
   Then the same line with `<RUN_USER>`.

## A new runner release

A new release of GitHub's runner ([actions/runner](https://github.com/actions/runner/releases)) needs no release of this repository: the image is built for the runner version you name. A release of this repository that changes `image/` or the base image is put in place the same way, after Install step 3 for both users and Install step 4 (pool-image.sh refuses a `~/build` whose pinned files are not its own release's; step 3 moves the old `~/build` aside with runscaler's download in it, and step 4 puts this release's in: 03 installs it on a fresh host only, and never replaces a runscaler that is there; `pool-image.sh runscaler` does: "runscaler: the release this one pins, and the way back", below). A user that has no `~/bin/runner-updater` yet (RS_USER on a host installed before the updater came; RUN_USER on one installed before this release) also needs Install step 10, once: its link then follows each later release's `~/build`. A user whose updater has no timer yet (a host installed before this release) needs Install step 11, once, and again after a release that changes the timer's files (`config/runner-updater.*`). RUN_USER's updater builds the image of the latest runner release that is 2 days old by itself when it is ON (`runner-updater pass`, "The updater" below), the same way as step 1: its build record is then already there.

1. **Build the image (RUN_USER).** It reads the release from GitHub, checks the runner tarball against the release's own sha256 digest, builds the image on the pinned base, runs the image checks of Install step 5 on it, and writes its build record. It must end with `BUILD DONE (D1)`. A line that starts with `WAIT` says what it waits for: GitHub's rate limit ends the run (run it again later); the updater lock, held by another build or by the updater, holds it until that run ends, and then it goes on. It does not look at the updater's on/off setting, so it works with the updater off:
   ```
   ssh <RUN_USER>@<host> 'bash ~/build/setup/02-d1.sh build <runner version>'
   ```
2. **Put it into the pool (RS_USER), at a quiet time** (it waits for the pool to be idle before it restarts runscaler). It reads the build record step 1 wrote for that version (the one of this release's image recipe), checks that the local registry serves its image and that the image's runner is that version, keeps the config the pool runs as the rollback, and puts the record's image in. With no such record it changes nothing and prints step 1's line:
   ```
   ssh -o ServerAliveInterval=60 <RS_USER>@<host> 'bash -s -- up <runner version>' < linux-docker/setup/pool-image.sh
   ```
3. After the first job on the new image passed: the same line with `accept`. If jobs fail on it: the same line with `back`.

A host installed from a release before this one: do "Upgrading from a release before this one" (below) first.

**The build record.** Each build that passed every check writes `~/run/builds/<version>-<recipe>` as RUN_USER (0640, so RS_USER, a member of RUN_USER's group, can read it): exactly four lines, `format 1`, `version <version>`, `digest sha256:<the image's digest in the local registry>`, `recipe <the sha256 of image/'s files>`. There is one record per version and recipe; building the same version again replaces it. It is written under a temporary name and renamed, so a cut-off run leaves no partial record. A failed check, a version mismatch or a digest mismatch writes none. `pool-image.sh up <version>` reads the record of its own release's recipe, as untrusted data: once, each line by its pattern, never sourced. RS_USER's updater reads records the same way: the one whose digest is the image the pool runs is that image's record (its runner version and recipe), and the one of a new release and this release's recipe tells it RUN_USER has built that release.

**The trust of the downloads.** Every download of the build path (GitHub's API and the runner tarball) uses `curl --cacert` with a filtered CA bundle (the system's bundle, without the certificates whose public key `setup/tls-excluded-spki` names) and `--capath` with an empty folder, so curl's built-in CA folder adds nothing back. That file's header gives its format; a file that breaks it, or names no key at all, stops the build before any download.

## runscaler: the release this one pins, and the way back

This release pins runscaler v0.12.0, and v0.9.5 (the runscaler of a host installed before it) is the way back. Install step 9 installs v0.12.0 on a fresh host only. On a host that runs runscaler, `pool-image.sh runscaler` is the one step that changes it, as RS_USER, in this order:

1. Install step 3 for both users (this release's files), then Install step 4 (the v0.12.0 download).
2. The step, at a quiet time. It must end with `POOL RUNSCALER DONE`:
   ```
   ssh -o ServerAliveInterval=60 <RS_USER>@<host> 'bash -s -- runscaler' < linux-docker/setup/pool-image.sh
   ```
3. The next day, read what runscaler wrote since the step: `journalctl --user -u runscaler` and `~/.config/runner/runner.log`.

What the step does, in order:

- It checks first, and changes nothing when a check fails; its line says what to do. The checks: this release's files (Install step 3); the version (v0.12.0, or v0.9.5); no window journal of the updater (`~/bin/runner-updater pass`, then `status`); no open image release (an `up` with neither its `accept` nor its `back`: accept or back first); runscaler's unit enabled (else `systemctl --user enable --now runscaler` first); that version's download, by its sha256. The kept config of a release a `back` closed is config.toml itself: the step removes it, and says so.
- If runscaler already runs that version on config.toml, and config.toml has the `log-file` line, it says `DONE ALREADY`, restarts nothing, and goes on to the checks after the restart (below).
- Else 03-runscaler.sh renders config.toml again, with the image it runs, and compares the two before it installs anything: they may differ only in comment lines and in the `log-file` line ("The log-file line", below). Any other difference (a value of the host config or of pool.env that is not the one the pool runs) stops it before it installs anything (its render stays as `~/.config/runner/config.real.new.toml`, to compare). Then it installs this release's `runner-start`, `pool-ready`, `validate-class` and unit, puts that version's runscaler into `~/bin/runner.new` (its sha256 checked), and checks the config with it (`runner-start validate --staged`). Only when that passes does it install config.toml first, and then renames `~/bin/runner.new` over `~/bin/runner`.
- Then it restarts runscaler at idle, as `up` does (a unit that is down it starts at once), waits for READY, checks that the process that runs is that version's runscaler, and names any job a restart cut.

Also, a config.toml that a bare `03-runscaler.sh real` installed and runscaler has not started yet goes live with this restart, when it is what the step renders, byte for byte; any other config.toml that runscaler has not started yet stops the step before it installs anything. A step cut off (an ssh drop) leaves runscaler and config.toml a pair that starts: run the same line again to finish it.

The step keeps no copy of the runscaler it replaces and has no `accept` or `back`: the way back is the step itself. If v0.12.0 does not serve (also when its unit no longer starts), download v0.9.5, then run the step with its version:
```
ssh <RS_USER>@<host> 'mkdir -p ~/build/dl && curl -fsSL -o ~/build/dl/runner-v0.9.5-linux-amd64.tar.gz https://github.com/ysya/runscaler/releases/download/v0.9.5/runner-linux-amd64.tar.gz'
```
```
ssh -o ServerAliveInterval=60 <RS_USER>@<host> 'bash -s -- runscaler 0.9.5' < linux-docker/setup/pool-image.sh
```
The way forward again is the step with no version (Install step 4's download stays in `~/build/dl`).

v0.12.0 logs a WARN at each start, `Service definition predates this runner's template …`, with a `fix=… migrate --user` line: that is expected. Never run its `fix=… migrate --user` (it migrates a unit of that name from before a rename, and this host's unit is the one 03-runscaler.sh installs), and never `runner update`.

The updater after the step: a pass, ON or OFF, finds no candidate and rolls nothing back (this release's updater switches nothing). A pass that runs while the step's restart drains holds `STOP POOL DOWN` (no runscaler runs then), and the next pass clears it once runscaler runs.

## The updater's switch and rollback

The runner-image updater switches the pool to a new runner release and rolls it back with `pool-image.sh`'s two unattended window modes, and ends a window that a cut left with its third, `recover --unattended` (RECOVER). Its switch comes in a later release: this release's updater switches nothing, and it rolls back (R1's verdict in a pass, and a person's `runner-updater back hz-docker`: "The rollback, and what status shows of it", below). The three modes are the updater's only: each runs as RS_USER from `~/build` itself, as the child of `runner-updater`, which hands it the updater lock; run by hand, it refuses and changes nothing. A window keeps a journal: `~/.local/state/runner-updater/window`, one line per step, each written to disk before the step it names. When a window ends, its journal stays at `window` with the closing lines (`installed` says what `config.toml` is then, and the last line is `closed`), until the updater's next run (a pass, `on`, `off` or `back`) applies it to the updater's state and moves it to `~/.local/state/runner-updater/windows/<id>`. The full output of each validate and the `/healthz` reads stay in `windows/<id>.d/`.

- `up --unattended <version> <digest>` checks what runs (both sets name one image, the registry still serves it, runscaler started after `config.toml` was installed, 10% of the disk free, a tested jq), renders and validates the new config into `~/.config/runner/config.staged.toml` (up to three tries, 20 s apart), and checks that it differs from `config.toml` in the image lines alone (its comment lines aside, and, when `config.toml` has no `log-file` line, the line that adds it: "The log-file line", below). Then it reads `/healthz` twice, 3 s apart; if any set is busy it removes the staged file, changes nothing and exits 3. If all are idle, it keeps `config.toml` as `config.toml.prev` (`backup`: a copy, checked against the config the window started with), renames the staged file over `config.toml` (`rename-start`, then `renamed` with the time; `config.toml` gets the time of the rename), waits for the next second, and restarts runscaler: it stops it (`stopping`), notes where the log ends once the old process has exited (`stopped`), starts it (`starting`), and waits until a process that started after the rename runs (`running`). Exit 0: the new image runs. If `config.toml` already names that image, nothing is switched: exit 0 when a runscaler that started after it was installed runs it, else exit 1 (`end`).
- `back --unattended` puts `config.toml.prev` back the same way, after it validated a copy of it, with no wait for idle: runscaler's restart lets busy runners finish their jobs first. Its first lines say why it rolls back and what it may reject (`why`: R1's verdict, R1's connect-only one, or a person's back; `verdict`, the sha of R1's verdict it keeps in `windows/<id>.d/verdict.json`; `old-version`, the version it leaves; `target-version`, the version it restores). Before the rename it keeps the config it replaces as `windows/<id>.d/config.toml.backup` (`backup`), the config RECOVER puts back if the rollback cannot run.
- `recover --unattended` (RECOVER) ends a journal that a cut left at `window` with no `closed` line: from the journal and the file `config.toml` is now, it finishes or undoes the window's step (it may start or restart runscaler, or put a rollback's backup back), and closes the journal. The updater runs it first in every run that takes the lock.

Each check of a file comes right before the step it guards, after that step's journal line. If `config.toml` changes by hand during a window, the window renames nothing over it and restarts nothing on it (but for a few milliseconds between a check and its step, which the header of `setup/pool-image.sh` names).

What a person reads in a journal: the last lines say how the window ended. `running`, then the closing lines: done. `stop <name>: <text>`, then the closing lines: a STOP, and the text says what to do. `end <text>`, then the closing lines: nothing changed, and the updater tries again later. A journal at `window` whose last line is `closed` waits for the updater's next run, which applies it and moves it to `windows/` (`runner-updater status` says so). A journal at `window` with no `closed` line did not end: the run was cut off, or `config.toml` was changed by hand once the rename had begun (`hand-change`, then `stop HAND CHANGE`). Then nothing restarts on that file, and the updater's next run ends the journal (RECOVER), or says why it cannot ("An unfinished window the updater cannot end", below). To keep such a file, check it with `RUNNER_START_CONFIG=~/.config/runner/config.toml ~/bin/runner-start validate`, and restart runscaler at idle only when that passes.

A person rolls back an updater's switch with `runner-updater back hz-docker` (below), never with `pool-image.sh back --unattended` by hand (that refuses).

## The updater: status, on, off, pass, build

The runner-image updater is one program for both users, `~/bin/runner-updater` (Install step 10), and the user it runs as decides what it does. In this release it switches nothing. As RS_USER a pass first ends a window journal a cut left (RECOVER), applies a closed one to its state, and holds or clears `STOP POOL DOWN` (runscaler's unit enabled means CI is on, so an enabled unit with no runscaler that runs is CI down: "The rollback, and what status shows of it", below); then it measures, asks the decision core (`~/build/core/`), rolls the pool back on R1's verdict (one window), and prints what else it would do and which runner release it would switch to. As RUN_USER a pass builds the image of that release, which a later release's switch needs. Its timer (Install step 11) runs `runner-updater pass` every 10 minutes for each user, and a pass also runs when you run it. It sets its own `PATH`, so it runs the same from its timer, a terminal or a non-interactive ssh. Each user has its own state, `~/.local/state/runner-updater/state.json`, and its own updater lock. RS_USER's: ON or OFF, the family `hz-docker` (both sets of this host) with its candidate (the runner version it switched to and is observing), its previous image, the date until which `back` restores that image, its rejected versions and the STOPs it holds, when R1's rollback was first due and how many connect-only rollbacks of each version there were, the last window journal it applied, and the decision core's own state; beside it, `~/.local/state/runner-updater/rejected` lists the image digest of each rejected version (03-runscaler.sh refuses those images). RUN_USER's: ON or OFF, and the STOPs of its builds. A fresh install has no state file: the updater is OFF, for each user.

- `status` prints ON or OFF; as RS_USER also the family's candidate, back date and rejected versions, and a window journal at `window`: open (with its last STOP, and whether a runscaler runs), closed and not applied, or applied and not archived (one no run of the updater can end names "An unfinished window the updater cannot end", below); then the core's lines: each STOP with its next step, and the evidence it has (none of a family with no candidate: a departed candidate's evidence is no current work); a `STOP ROLLED BACK` whose copy of R1's verdict cannot be read gets a line that says R1's failures are not readable. As RS_USER it then prints RUN_USER's record, after all of its own lines, also when they end early (a `WAIT` or `REFUSE` about its own state, or `STOP core could not decide`): each line starting `runner-updater: as <RUN_USER>:` ON or OFF, and each STOP of RUN_USER's builds with its next step, as RUN_USER (`runner-updater build <version>`). It reads RUN_USER's state file as untrusted data (one read that never waits and never follows a symlink, never run), and shows it only in the form RUN_USER's own updater writes (a `check failed` of a build, with a version number of 1 to 9 digits in each part and a short plain text). Each such line names the STOP, its version and its next step, never its text: in place of its cause it says that RUN_USER's own `runner-updater status` shows it (that text is RUN_USER's, and could read as an instruction); anything else, a file it cannot read, or one of another format, is one line that says why, with RUN_USER's own `runner-updater status` as the way to read it. RS_USER can read that file because RUN_USER's updater keeps it readable by RUN_USER's group (RS_USER is its only member), as the build records are: the file 0640, and its folders open to the group for search only; RS_USER's own state stays private. Under an untested jq it reads no record (its `STOP untested jq` line says so). Nothing of RUN_USER's record changes its exit code: that stays RS_USER's own (the watchdog reads only the lines). It takes no lock and writes nothing, so it runs at any time:
  ```
  ssh <RS_USER>@<host> '~/bin/runner-updater status'
  ```
- `runner-updater on` turns the updater on; `runner-updater off` turns it off. Each user has its own: RUN_USER's builds nothing while it is OFF. As RS_USER both first end a window journal a cut left and apply a closed one (as a pass does); `off` refuses while a journal stays at `window` after that (`~/.local/state/runner-updater/window`): it never leaves a window half done, and its line says whether that run changed something. `off` also stops the clock of a pending rollback (time while OFF never counts against its 2 hours). Both wait while another run holds the updater lock (`~/.local/state/runner-updater/lock`), and say so:
  ```
  ssh <RS_USER>@<host> '~/bin/runner-updater on'
  ```
- The timer (Install step 11) runs `runner-updater pass` every 10 minutes, as each user: the first time at once when the host has been up for 10 minutes, else 10 minutes after a boot. While the updater is OFF, that pass only ends a window journal a cut left, applies a closed one and holds or clears `STOP POOL DOWN` (exit 0, or 1 while a journal stays), and the updater itself asks the core and GitHub nothing (RECOVER may validate a config and start runscaler, which both reach GitHub); while it is ON, it does what `pass` does (below). Each user's timer is its own. See when it ran and when it runs next, and what each pass printed:
  ```
  ssh <RS_USER>@<host> 'systemctl --user list-timers runner-updater.timer; journalctl --user -u runner-updater -n 50 --no-pager'
  ```
  To stop the passes, run `runner-updater off` (the timer stays, and each pass then does only what a pass while OFF does), or stop the timer itself (a pass that runs then still ends as it would):
  ```
  ssh <RS_USER>@<host> 'systemctl --user disable --now runner-updater.timer'
  ```
  Install step 11 starts it again. A pass that runs longer than 2 hours (a build, or a window's drain and start) is stopped by systemd: a build stopped so holds no STOP (below), and the next pass builds it again; a window stopped so leaves its journal open, and the next pass ends it. systemd sends SIGTERM first; what is still running at its `TimeoutStopSec` (the manager's default: the unit names none) gets SIGKILL, which no trap sees: then there is no CUT line, the build context may stay in `~/.cache/liveapp-ci`, the updater lock is free once every holder has exited, and the state file is still valid (it is only ever replaced by a rename).
- `runner-updater pass` is what the timer runs. When another run holds the updater lock, it ends at once. As RS_USER it first runs RECOVER on a window journal a cut left and applies a closed one, then holds or clears `STOP POOL DOWN`; a journal that stays at `window` is its STOP line (exit 1) and nothing more (do not delete the journal: "An unfinished window the updater cannot end", below, when no run ends it). While the updater is OFF the pass ends there: the updater itself asks the core and GitHub nothing (RECOVER, before it, may validate a config and start runscaler, which both reach GitHub). When ON, it reads runscaler's process (from systemd), where runscaler's log ends and what it wrote since the last pass, the config runscaler runs and when it was installed, and two `/healthz` reads; it asks the core (idle, R1, KEEP, the STOP lines), keeps the core's state, prints what it would do of KEEP's (`would accept hz-docker`, `would hold hz-docker: STOP …`), and rolls the pool back on R1's verdict (`R1's rollback is due for hz-docker`: "The rollback, and what status shows of it", below). Then one line for the family (`hz-docker is not due: a window ran in this pass` after a rollback window: the next pass decides): `would switch hz-docker to <version>` when GitHub's latest runner release is at least 2 days old, newer than the runner of the image the pool runs, not rejected, held by no STOP, and RUN_USER has built it for this release's image; else `hz-docker is not due:` and the first reason, in this order: an open candidate, a STOP, this release's image recipe, `STOP NO BASELINE` (no build record of RUN_USER names the image the pool runs: "A new runner release" puts one in), `STOP recipe changed` (this release's `image/` is not the one that image was built from), GitHub's rate limit (`WAIT`), a release under 2 days old, a STOP of that release, rejected, not newer, or `it waits for RUN_USER's build`. It asks GitHub only when nothing on the host holds the family, and downloads nothing. Each pass's files are in `~/.local/state/runner-updater/pass/`.
- `runner-updater pass` as RUN_USER is the build pass. When ON, it reads GitHub's latest runner release, and when that is at least 2 days old and has no build record yet for this release's image, it builds it the way "A new runner release" step 1 does (02-d1.sh, under the same updater lock) and prints `built runner <version>`. GitHub's rate limit is a `WAIT`: a later pass tries again. A build cut by a signal (an ssh drop, a reboot, or a stop of the timer's pass by systemd, at its 2 hour bound too: 02-d1.sh ends by SIGHUP, SIGPIPE or SIGTERM) prints `CUT` and holds no STOP: the next pass builds it again; a stop that comes before 02-d1.sh starts prints `CUT` with "no build started"; a stop that reaches the updater while 02-d1.sh runs is a `CUT` too, whatever 02-d1.sh then exits with (but a build that passed: `built runner`). When systemd's SIGKILL follows its SIGTERM (the timer bullet above), there is no `CUT` line, and still no STOP. A build that hangs each time is cut every 2 hours and tried again, with no STOP: its `CUT` lines are in RUN_USER's `journalctl --user -u runner-updater`. A build that fails holds `STOP check failed (runner <version>)` with the line that says why (02-d1.sh's REFUSE line, else its FAIL line), and no later pass builds that version again (a newer release is built as usual; a release whose version has a part of 10 digits or more is not built: `no build`). RS_USER's `status` names that STOP; its cause is in RUN_USER's own `runner-updater status`. Once the cause is fixed, retry it as RUN_USER; `build` works while the updater is OFF, waits for the updater lock, and clears that STOP when the build passes; a `build` that fails prints why and holds no STOP (one that is there stays). A pass also clears that STOP when it finds the version's build record (a build by "A new runner release" step 1):
  ```
  ssh <RUN_USER>@<host> '~/bin/runner-updater build <runner version>'
  ```
- `runner-updater back hz-docker` (RS_USER) is a person's rollback: while the updater is ON, with a candidate (before an accept) or before its back date, it rolls the pool back to the previous image at once (one window, with no wait for idle: runscaler's restart lets busy runners finish their jobs). Like a pass, it first ends a window journal a cut left (RECOVER) and applies a closed one, and after that and its own window it holds or clears `STOP POOL DOWN`. It refuses while the updater is OFF, with nothing to go back to, and while runscaler's unit is disabled (`rollback pending: CI disabled by a person`: `systemctl --user enable --now runscaler` first), and its line says whether that run changed something (what its RECOVER did stays). It rejects the version it leaves only when that is newer than the one it restores, and holds no `STOP ROLLED BACK`. Exit 0 rolled back; 5 pending (the window ended with no STOP, as when its validate was UNKNOWN: run it again later; the line says whether that run changed something); 1 a STOP or a REFUSE:
  ```
  ssh <RS_USER>@<host> '~/bin/runner-updater back hz-docker'
  ```
- Under a jq that `core/TESTED_JQ` does not list for `core`, `status` and a pass that is ON (of either user) print `STOP untested jq` (exit 3) and the line that runs the core's tests with it. A state file of another format, or with an entry this release does not read (a newer release wrote it), makes every command print `WAIT` (exit 4) and change nothing; one it cannot read is `REFUSE` (exit 1), and it is left as it is. A pass or `status` whose decision core waits (the core's own state, kept in the state file, is of a format it does not read) prints `WAIT` (exit 4) too, `status` after its lines: `status` writes nothing, and a pass keeps the core's own state as it was, while what it did before it asked the core (RECOVER, the apply step, `STOP POOL DOWN`) stays. An answer of the core that is not one of its own is `STOP core could not decide` (exit 1).
- A pass has no facts (`REFUSE no facts`, exit 1) when config.toml's lines would mislead the core, among them a top-level `log-level` other than `"info"` (what 03-runscaler.sh renders) or `"debug"`: at `warn` or `error` runscaler logs no finished job, so a quiet log would look like a healthy one.
- The weekly runner watchdog (`watchdog/run`) asks the owner to run `<its --hz line> runner-updater status`, by the bare name. An ssh command has no `~/bin` on its PATH, so the `--hz` line must put RS_USER's `~/bin` on it, in this shape:
  ```
  --hz 'ssh <RS_USER>@<host> PATH=/home/<RS_USER>/bin:/usr/local/bin:/usr/bin:/bin'
  ```

## The rollback, and what status shows of it

R1 (core/README.md: three counted failures on one set with no proof of life between them) says the candidate must be rolled back. The next pass while the updater is ON does it: one rollback window to the previous image (`config.toml.prev`, the backup its switch kept), with no wait for idle, and `status` then shows no candidate, the version among the rejected ones (its image's digest in `~/.local/state/runner-updater/rejected`, so `03-runscaler.sh` refuses that image in every mode), and `STOP ROLLED BACK (runner <version>)` with R1's counted failures (or a line that says R1's failures are not readable, when the copy of R1's verdict the window kept is not the one its journal names). The window's own lines are in its journal, `~/.local/state/runner-updater/windows/<id>`.

- A verdict whose failures are all connection failures (connect-class only) rejects nothing the first time: its `STOP ROLLED BACK` says one retry after 1 hour comes first, and a pass removes that STOP 1 hour after the rollback; a second such rollback of the same version rejects it.
- The pass starts no rollback window, and its line says why, while: runscaler's unit is disabled (`rollback pending: CI disabled by a person`: R1's verdict stays, and the rollback runs once a person enables the unit, `systemctl --user enable --now runscaler`); `config.toml` does not name the candidate's image (`STOP HAND CHANGE`, a pending hand edit: the rollback would replace that file unseen; put the candidate's config back, and the next pass tries again); `config.toml.prev` is not the image the switch kept (`STOP ROLLBACK FAILED`); its RECOVER started runscaler in the same pass (one restart per pass: the next pass starts it); or `STOP ROLLBACK FAILED` is held.
- A rollback that cannot run now (its validate UNKNOWN: `rollback pending`) is tried again each pass while R1's verdict stands, for 2 hours from the first pass that could start a try (time while runscaler's unit is disabled, a hand edit is pending, or the updater is OFF does not count); after that, `STOP ROLLBACK FAILED`, and no more tries. Check the pool (its journal, runscaler's `journalctl --user -u runscaler`), then roll back by hand with `runner-updater back hz-docker` once it can run, or keep the pool as it is.
- `STOP POOL DOWN`: runscaler's unit is enabled, and no runscaler runs (its `/healthz` answers for every set on two reads 3 s apart, the same process): CI is down. Each pass holds it while that is so, and clears it once a runscaler runs, or once the unit is disabled (CI off on purpose). `STOP CI DISABLED`: a window found the unit disabled; a pass clears it once the unit is enabled and a runscaler that started after `config.toml` was installed runs (so a rollback that a `systemctl --user disable` without `--now` left with the old runscaler running keeps it until runscaler restarts on the rollback's config).
- `STOP ROLLED BACK` and `STOP HAND CHANGE` name `runner-updater retry` and `runner-updater rebuild` as their next step: those commands come in a later release. Until then such a STOP holds the family's next release (`status` says which), and this release switches nothing anyway.

## An unfinished window the updater cannot end

Every run of the updater stops on a window journal it cannot end, and says so with this section's name (as does `status`): RECOVER cannot read or act on it (`STOP RECOVER cannot end the window journal`: a journal that is not a readable plain file, no `window` first line (a journal whose only line was cut has none), a line that is not `KEY VALUE` or that no pattern of `setup/pool-image.sh`'s header reads, a `backup` line with no `kind`, `config-sha`, `staged`, `staged-sha` or `target` line before it, a `backup` line that is not its kind's backup, or a window folder it cannot make); the updater's apply step cannot read a closed one (`STOP the window journal ... is closed, but the apply step cannot read it`: a journal that is not a readable plain file, no `window` first line, a line that is not `KEY VALUE`, a STOP name the window's grammar has not, a `kind`, `why`, `target` or `old` line of another shape, an `installed` line of another shape, a CLASS its kind has not, a line it needs missing (a switch's `version`), a journal of an earlier release with no line that says what it installed, or one jq cannot read); or it cannot archive one (`windows/<id>` is there already). CI may be down meanwhile. As RS_USER:

1. Stop the timer, so that no pass runs meanwhile:
   ```
   ssh <RS_USER>@<host> 'systemctl --user disable --now runner-updater.timer'
   ```
2. Read the record: `~/.local/state/runner-updater/window` (its STOP line says what is wrong) and the files of `~/.local/state/runner-updater/windows/<id>.d/`.
3. Bring CI back by hand: put in place the config the record's own lines name (the TARGET its `target` lines name, or the `backup` it kept: `config.toml.prev` of a switch, `windows/<id>.d/config.toml.backup` of a rollback), check it with `RUNNER_START_CONFIG=~/.config/runner/config.toml ~/bin/runner-start validate`, and only when that passes, `systemctl --user restart runscaler`.
4. Move the record aside, never delete it:
   ```
   ssh <RS_USER>@<host> 'mkdir -p ~/.local/state/runner-updater/aside && mv ~/.local/state/runner-updater/window ~/.local/state/runner-updater/aside/window.$(date -u +%Y%m%dT%H%M%SZ)'
   ```
5. `~/bin/runner-updater off`, then Install step 11 again (the timer).
6. `~/bin/runner-updater on` only once `~/bin/runner-updater status` shows what runs.

A closed journal whose rejection cannot be written (`STOP the window journal ... is closed, but its rejection cannot be written`: `~/.local/state/runner-updater/rejected` is not a readable file of one `sha256:<64 hex>` per line, which 03-runscaler.sh also refuses) is not moved aside: fix that file by hand (each line one such digest), and the next run applies the journal.

## Upgrading from a release before this one

This release adds the host-config key `RUNNER_VERSION`: the runner version a full 02-d1.sh run builds. This release's 02-d1.sh refuses to run without it, with `02-d1.sh: REFUSE /etc/liveapp-ci/host.conf lacks RUNNER_VERSION`, before it changes anything. Set it to the runner version the pool runs now, before you run a script of this release. The lines below change that one key in the host config installed on the host; every other line stays as it is. (This release no longer reads `PROBE_SET`, `PROBE_LABEL`, `C1_SET`, `C1_GROUP` and `C1_LABEL`: 03-runscaler.sh's one-off modes `probe` and `c1` are gone. Their lines may stay in the host config.)

1. Read that version (as RS_USER). It starts the image that config.toml names, with no network, and prints its runner's version, as `pool-image.sh up` reads it. It must print exactly one version; if it prints none or two, stop: config.toml does not name one image for both sets.
   ```
   ssh <RS_USER>@<host> 'sed -n "s/^runner-image = \"\(.*\)\"$/\1/p" ~/.config/runner/config.toml | sort -u | while read -r i; do DOCKER_HOST=unix:///home/<RUN_USER>/run/docker.sock docker run --rm --network none --memory 512m --cpus 1 "$i" ./config.sh --version < /dev/null | grep -xE "[0-9]+\.[0-9]+\.[0-9]+"; done'
   ```
2. Set it in the installed host config (root). Put what step 1 printed in place of `<version>`, at the start of the line: that is the only place you edit. The line refuses a version that is not three numbers joined by dots (N.N.N, with no space), and then writes nothing. Else it keeps every other line, puts `RUNNER_VERSION=<version>` in place of a `RUNNER_VERSION` line it may have, and keeps the file as it was before as `host.conf.prev`:
   ```
   ssh root@<host> 'v="<version>"; f=/etc/liveapp-ci/host.conf; ok=; case $v in *[!0-9.]*|.*|*.|*..*|*.*.*.*) ;; *.*.*) ok=1 ;; esac; [ "$ok" = 1 ] || { printf "REFUSE [%s] is not a runner version N.N.N: nothing was written\n" "$v"; exit 1; }; cp -p "$f" "$f.prev" || exit 1; grep -v "^RUNNER_VERSION=" "$f.prev" > "$f.new"; [ $? -le 1 ] || exit 1; printf "RUNNER_VERSION=%s\n" "$v" >> "$f.new" && chmod 644 "$f.new" && mv "$f.new" "$f" && echo "OK $f: RUNNER_VERSION=$v (the file before: $f.prev)"'
   ```
3. Check it against this release, from your checkout: the installed host config must hold each key of `linux-docker/host.conf.example` once (they are the keys this release's scripts read), and its `RUNNER_VERSION` must be N.N.N. It must print the one line `RUNNER_VERSION=<version>` and nothing else. A line that starts with `WANT` says what is wrong; `host.conf.prev` is the file before step 2:
   ```
   sed -n 's/^\([A-Z][A-Z0-9_]*\)=.*/\1/p' linux-docker/host.conf.example | ssh <RUN_USER>@<host> 'f=/etc/liveapp-ci/host.conf; n=0; while read -r k; do c=$(grep -c "^$k=" "$f"); [ "$c" = 1 ] || { echo "WANT one $k line in $f, found $c"; n=1; }; done; grep -xE "RUNNER_VERSION=[0-9]+\.[0-9]+\.[0-9]+" "$f" || { echo "WANT RUNNER_VERSION=N.N.N in $f, found [$(grep "^RUNNER_VERSION=" "$f")]"; n=1; }; [ "$n" = 0 ]'
   ```
   - `WANT one KEY line in …, found 0`: the installed file lacks KEY, so each script that reads KEY refuses to run. As root, add the line `KEY=value` to it with your host's value (`host.conf.example` says what KEY is), then run this check again.
   - `WANT one KEY line in …, found 2` (or more): every script refuses a host config that names a key twice. As root, keep the one line with your host's value, remove the others, then run this check again.
   - `WANT RUNNER_VERSION=N.N.N in …, found […]`: run step 2 again with the version step 1 printed, then this check.

Then install this release's files as for every release ("A new runner release", its first paragraph), and do Install step 10 once, for both users: this release adds the updater, `~/bin/runner-updater`. Then do Install step 11 once, for both users: this release adds its timer (while the updater is OFF, a pass only ends a window journal a cut left and holds or clears `STOP POOL DOWN`).

This release's `03-runscaler.sh real` also renders a new line into config.toml, `log-file` (Install step 9), which the config.toml of a host installed before it does not have. It needs no step of its own: `pool-image.sh runscaler`, which this release asks for ("runscaler: the release this one pins, and the way back", above), or the next `pool-image.sh up`, puts it in ("The log-file line", below).

## The log-file line

From this release, `03-runscaler.sh real` renders a top-level `log-file` line into config.toml, with a comment line above it: the `runner.log` in RS_USER's `~/.config/runner`, the file the updater and `pool-image.sh` read. Without that line, runscaler v0.10 and later write their log elsewhere, and the old `runner.log` stays as it is: the updater would read that quiet file as a healthy log.

A host installed before this release runs a config.toml without the line, and it runs on unchanged: this release's `runner-start` starts a config with no `log-file` line on runscaler v0.9.5 (the runscaler such a host runs, and the way back from v0.12.0; it then writes `runner.log` beside the config, the same file), and refuses it on any other runscaler. Do not add the line by hand, and do not run 03-runscaler.sh by hand for it. `pool-image.sh runscaler` ("runscaler: the release this one pins, and the way back", above), the next `pool-image.sh up` to another image ("A new runner release", step 2), or in a later release the updater's switch, adds it: that `up` accepts a render that differs from the config the pool runs in the image, in its comment lines (a comment line is not part of the config: the first line names the runscaler release) and in the `log-file` line alone, once, right after `log-level`, and only when that config has no `log-file` key. It keeps all of its checks (pool.env's numbers must be the ones the pool runs, else `up` itself stops before it runs 03; every other value of the host config too, else 03 stops before it installs config.real.toml or config.toml, with config.toml as it was, and nothing restarts; by then 03 has installed this release's `runner-start`, `pool-ready`, `validate-class` and unit, each of which starts with either runscaler), and it restarts runscaler when the pool is idle. A `back` to the config it kept, which has no `log-file` line, is accepted too while runscaler v0.9.5 runs (the way back): it runs that config as before, and the next `up` adds the line again. On any other runscaler, `back` refuses it before it changes anything: `runner-start` would refuse that config at the restart, and CI would be down.

## A host that already runs these scripts from a hand copy

Until you do this, the host keeps running the files it has. The move installs the host config and this release's files, checks that the pool runs the config and image its records name, and does nothing else: it runs no 03 and restarts nothing. The scripts of this folder refuse to run without the host config, so it comes first:

1. Install step 1 (the host config, with the values the host uses today). Its `RUNNER_VERSION` is the runner version the pool runs now: "Upgrading from a release before this one", step 1, reads it.
2. Install step 3 for both users, then Install step 4, then Install step 10 (the updater's link: a fresh updater is OFF), then Install step 11 (its timer: a pass while OFF only ends a window journal a cut left, which a host moved from a hand copy has none of, and holds or clears `STOP POOL DOWN`).
3. Check that runscaler runs the installed config.toml, read only. It prints the image config.toml names for both sets and the record that names it too (`image.ref`, or after a `back` the kept config, `config.toml.pre-image`), and checks that runscaler started after config.toml was installed (pool-image.sh's own rule, in whole seconds). It must end with `OK   runscaler started`. A line that starts with `STOP` says what to do: the move stops there; do it, then run this check again:
   ```
   ssh <RS_USER>@<host> 'bash -s' <<'EOF'
   R=~/.config/runner; img() { sed -n 's/^runner-image = "\(.*\)"$/\1/p' "$1" | sort -u; }
   c=$(img $R/config.toml); r=$(. ~/build/setup/runner-release.sh && rr_read "/home/$(sed -n 's/^RUN_USER=//p' /etc/liveapp-ci/host.conf)/run/image.ref" 1024) || { echo "STOP RUN_USER's ~/run/image.ref is not a plain file (a FIFO, a symlink or a folder is none) or cannot be read: as RUN_USER, look at it (ls -l ~/run/image.ref), then run this check again"; exit 1; }
   [ "$(grep -c '^runner-image = ' $R/config.toml)" = 2 ] && [ "$(printf '%s\n' "$c" | grep -c .)" = 1 ] || { echo "STOP config.toml does not name ONE runner image for both sets: read $R/config.toml and find out what changed it"; exit 1; }
   if [ "$c" = "$r" ]; then echo "OK   config.toml names $c for both sets; image.ref names it too"
   elif cmp -s $R/config.toml.pre-image $R/config.toml; then echo "OK   config.toml names $c for both sets; it is the kept config of a back (image.ref still names the rejected $r)"
   else echo "STOP config.toml names $c, image.ref names $r, and config.toml is not the kept config of a back: a build that no up has put into the pool, or a file changed by hand. Put a runner release into the pool with this release's steps (A new runner release, steps 1 and 2), then accept or back (its step 3); do not edit image.ref to match config.toml, which would name an image that may never have run; then run this check again"; exit 1; fi
   a=$(systemctl --user show runscaler -p ActiveEnterTimestamp --value --timestamp=unix); a=${a#@}; m=$(stat -c %Y $R/config.toml)
   [ "$(systemctl --user is-active runscaler)" = active ] && [[ $a =~ ^[0-9]+$ ]] || { echo "STOP runscaler is not active: read journalctl --user -u runscaler"; exit 1; }
   [ "$a" -gt "$m" ] || { echo "STOP config.toml was installed at $m, after runscaler started at $a: runscaler does not run this file. Restart it when no job runs (systemctl --user restart runscaler), then run this check again"; exit 1; }
   echo "OK   runscaler started at $a, after config.toml was installed at $m: it runs this config.toml"
   EOF
   ```
4. Check the host config against the running pool, read only. This release's `pool-ready` takes the health port from the host config; give it the set names from the host config. It must end with `READY`:
   ```
   ssh <RS_USER>@<host> 'bash ~/build/bin/pool-ready <MAIN_SET> <SMALL_SET>'
   ```

Do not run 03-runscaler.sh by hand on the running pool: it installs config.toml again, with a new time, and then the next `pool-image.sh up` (and the `accept` of an open release) refuses until runscaler restarts. The next runner release's `up` runs 03 itself ("A new runner release", step 2): it installs this release's `runner-start`, `pool-ready`, `validate-class` and unit, renders config.toml from the host config (with the `log-file` line the move's config.toml has not: "The log-file line", above), and restarts runscaler when the pool is idle. If a value of the host config is not the one the pool runs, that `up` stops with config.toml as it was, and nothing restarts. If a release is still open (its `up` ran, and neither its `accept` nor its `back`), close it first with one of them ("A new runner release", step 3: `accept` or `back`).

## Uninstall

Follow the header of `setup/01-users-undo.sh` (what must happen before it), then as root:

```
ssh root@<host> 'bash -s' < linux-docker/setup/01-users-undo.sh
```
```
ssh root@<host> 'rm -rf /etc/liveapp-ci'
```
