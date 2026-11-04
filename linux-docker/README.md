# linux-docker — a Linux CI host that runs every job in a fresh Docker container

This folder is the Linux half of the repository: a Linux host where [runscaler](https://github.com/ysya/runscaler) takes jobs from GitHub runner scale sets and starts each one in a new container from a local runner image. The Mac product is the rest of the repository ([../README.md](../README.md)).

- Two host users. **RUN_USER** runs a rootless Docker daemon ("D1") and a local image registry, and holds no secret. **RS_USER** runs only runscaler (a systemd user unit) and holds the GitHub token; it reaches D1 through a second socket, as a member of RUN_USER's group. No job reaches a root Docker daemon.
- Jobs run on a `runners` network, with a pinned seccomp profile, no-new-privileges and an init process; `docker.dind` is always false. `runner-start` refuses to start runscaler with a config that would give a job a Docker socket.
- Every value of the host (the users, ports, address, organization, token name, set names and labels) is in ONE host config file, `/etc/liveapp-ci/host.conf`. The scripts hold none of them, and each one refuses to run without that file.

Status: these scripts run one host (Ubuntu 26.04, x86_64, Docker 29.9.0). They moved here unchanged except that the host values left them, and except the release path (`02-d1.sh build VERSION`, then `pool-image.sh up VERSION` from its build record: "A new runner release" below), `03-runscaler.sh render`, `pool-image.sh`'s unattended modes ("The updater's switch and rollback" below), and the updater's `bin/runner-updater` ("The updater: status, on, off, pass" below), which are new and have not yet run on that host. `runner-start` refuses any Docker version other than the one the seccomp profile was cut from (29.9.0).

## Files

| File | Runs as | What it does |
|---|---|---|
| `host.conf.example` | — | Every key of the host config, with placeholder values and what each one is. |
| `setup/01-users.sh` | root | Creates RUN_USER and RS_USER, the group, the ssh keys, the runscaler lock rule and linger. Re-runnable. |
| `setup/01-users-undo.sh` | root | Removes only what 01-users.sh made (its header lists what must happen first). |
| `setup/02-d1.sh` | RUN_USER | With no argument (the full run): the rootless Docker daemon and its hardening, the `runners` network, the local registry, and the runner image of the host config's `RUNNER_VERSION` (built, pushed, checked; then its build record, and its digest goes to `~/run/image.ref`). With `build VERSION`: only the runner image of that release, its checks and its build record. |
| `setup/runner-release.sh` | RUN_USER, RS_USER | Read by 02-d1.sh and by pool-image.sh's unattended modes, never run: how a runner release is read from GitHub, the trust of every download (below), and the updater lock. |
| `setup/03-runscaler.sh` | RS_USER | Installs runscaler (by sha256), `runner-start`, `pool-ready`, `validate-class` and the unit; renders, checks and installs the config (`real`, with the image config.toml runs unless it is given one). Never restarts runscaler. `render` (the updater's) renders and validates a config into a file of its own and installs nothing. |
| `setup/runner-facts.sh` | RS_USER | Read by pool-image.sh's unattended modes and by `bin/runner-updater`, never run: the one copy of what the updater measures (runscaler's process as systemd reports it, its log position and the log text since the last pass, the config's sets and images, the jq check, the two `/healthz` reads). |
| `setup/pool-image.sh` | RS_USER | Puts the image of a runner release's build record into the pool (`up VERSION`), rolls it back (`back`), or ends the release (`accept`). The updater's own switch and rollback are its unattended modes (`up --unattended`, `back --unattended`: "The updater's switch and rollback", below). |
| `bin/runner-updater` | RS_USER | The runner-image updater: `status`, `on`, `off`, and `pass`, which measures, asks the decision core and prints what it would do, and takes no action in this release ("The updater: status, on, off, pass" below). Install step 10 links it into `~/bin`. |
| `bin/runner-start` | RS_USER | The unit's start command: checks the config, D1, the registry and the token files, then starts runscaler. |
| `bin/validate-class` | RS_USER | The class of one `runner-start validate` result (PASS, API-ONLY, NON-API or UNKNOWN): the same rule as the Mac's `bin/validate-class`. |
| `bin/pool-ready` | RS_USER | Is runscaler serving exactly the named sets, each ready? |
| `image/Dockerfile` | RUN_USER | The runner image: GitHub's runner image by digest (the pinned base), the runner of the release 02-d1.sh fetched, plus bubblewrap, gh, a locale and build tools. |
| `image/install-runner.sh` | (the build) | Run inside the image build: puts the fetched runner in place of the base image's runner. |
| `../setup/tls-excluded-spki` | — | The CA keys no download trusts (the repository's top-level `setup/`; the install puts it into `~/build/setup/`). |
| `../core/` | RS_USER | The updater's decision core, the same files as the Mac's (the repository's top-level `core/`; the install puts it into `~/build/core/`): the unattended switch asks its `idle.jq` whether the pool is idle, under a jq that `core/TESTED_JQ` lists. |
| `config/` | — | The systemd unit and the two seccomp profiles (Docker's default, and the one the jobs run with). |

`setup/pool-image.sh` pins `setup/03-runscaler.sh`, `bin/runner-start`, `bin/pool-ready`, `bin/validate-class` and `config/runscaler.service` by sha256 (`PINS`); `03-runscaler.sh render` reads the same pins. `tools/release-check` refuses a release in which one of them changed without its pin.

## Install

You need: a dedicated x86_64 Linux host with systemd, root ssh with your key, Docker Engine 29.9.0 with its rootless extras (`dockerd-rootless-setuptool.sh`) and `uidmap`, and `python3` (3.11 or newer), `curl`, `jq`, `ss`, `nsenter` and `ip` on it. The jq must be a version that `core/TESTED_JQ` lists for `core` (the `jq` package of Ubuntu 26.04 and of 24.04 is one): the updater's switch stops under any other. The scripts touch no root Docker daemon and no other user.

Run every line below from your laptop, in a checkout of the release you chose (replace `<host>`, `<version>` and the user names with yours):

```
git clone --branch v<version> --depth 1 https://github.com/liveappbase/mac-github-self-hosted-runner && cd mac-github-self-hosted-runner
```

1. **The host config (root).** Copy `linux-docker/host.conf.example` to `host.conf`, set every value (each key's comment says what it is), then install it as root's file:
   ```
   ssh root@<host> 'install -d -m 755 /etc/liveapp-ci && umask 022 && cat > /etc/liveapp-ci/host.conf.new && chmod 644 /etc/liveapp-ci/host.conf.new && mv /etc/liveapp-ci/host.conf.new /etc/liveapp-ci/host.conf' < host.conf
   ```
2. **The users (root).** It copies root's `authorized_keys` to both users, so the lines below can ssh as them. It must end with `R1 DONE`:
   ```
   ssh root@<host> 'bash -s' < linux-docker/setup/01-users.sh
   ```
3. **The files (once as RUN_USER, once as RS_USER).** Each user gets this release's `linux-docker/` as `~/build`, with the repository's `setup/tls-excluded-spki` in `~/build/setup/` and its `core/` as `~/build/core/` (an older `~/build` is moved aside, not deleted). `COPYFILE_DISABLE=1` keeps macOS's tar from adding `._` files, which would become part of the image recipe:
   ```
   COPYFILE_DISABLE=1 tar -C linux-docker -cf - . -C .. setup/tls-excluded-spki core | ssh <RUN_USER>@<host> 'rm -rf ~/build.new && mkdir ~/build.new && tar -C ~/build.new -xf - && { [ ! -e ~/build ] || mv ~/build ~/build.prev.$(date -u +%Y%m%dT%H%M%SZ); } && mv ~/build.new ~/build'
   ```
   Then the same line with `<RS_USER>`.
4. **runscaler's download (RS_USER).** 03-runscaler.sh checks its sha256 before it extracts anything:
   ```
   ssh <RS_USER>@<host> 'mkdir -p ~/build/dl && curl -fsSL -o ~/build/dl/runner-linux-amd64.tar.gz https://github.com/ysya/runscaler/releases/download/v0.9.5/runner-linux-amd64.tar.gz'
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
9. **runscaler (RS_USER).** It must end with `03 DONE (real)`:
   ```
   ssh <RS_USER>@<host> 'bash -s -- real' < linux-docker/setup/03-runscaler.sh
   ```
   Then start it, and check that both sets are ready (within a minute):
   ```
   ssh <RS_USER>@<host> 'systemctl --user enable --now runscaler && sleep 60 && ~/bin/pool-ready <MAIN_SET> <SMALL_SET>'
   ```
10. **The updater (RS_USER).** It links `~/bin/runner-updater` to the copy in `~/build`, so after a release's step 3 it runs that release's files. A fresh install is OFF ("The updater: status, on, off, pass" below):
   ```
   ssh <RS_USER>@<host> 'install -d -m 700 ~/bin && ln -sfn ~/build/bin/runner-updater ~/bin/runner-updater'
   ```

## A new runner release

A new release of GitHub's runner ([actions/runner](https://github.com/actions/runner/releases)) needs no release of this repository: the image is built for the runner version you name. A release of this repository that changes `image/` or the base image is put in place the same way, after Install step 3 for both users and Install step 4 (pool-image.sh refuses a `~/build` whose pinned files are not its own release's; step 3 moves the old `~/build` aside with runscaler's download in it, and 03 checks that download first). A host that has no `~/bin/runner-updater` yet (installed before the updater came) also needs Install step 10, once: its link then follows each later release's `~/build`.

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

**The build record.** Each build that passed every check writes `~/run/builds/<version>-<recipe>` as RUN_USER (0640, so RS_USER, a member of RUN_USER's group, can read it): exactly four lines, `format 1`, `version <version>`, `digest sha256:<the image's digest in the local registry>`, `recipe <the sha256 of image/'s files>`. There is one record per version and recipe; building the same version again replaces it. It is written under a temporary name and renamed, so a cut-off run leaves no partial record. A failed check, a version mismatch or a digest mismatch writes none. `pool-image.sh up <version>` reads the record of its own release's recipe, as untrusted data: once, each line by its pattern, never sourced.

**The trust of the downloads.** Every download of the build path (GitHub's API and the runner tarball) uses `curl --cacert` with a filtered CA bundle (the system's bundle, without the certificates whose public key `setup/tls-excluded-spki` names) and `--capath` with an empty folder, so curl's built-in CA folder adds nothing back. That file's header gives its format; a file that breaks it, or names no key at all, stops the build before any download.

## The updater's switch and rollback

The runner-image updater (not yet on this host: its timer comes in a later release) switches the pool to a new runner release, and rolls it back, with `pool-image.sh`'s two unattended modes. Both run as RS_USER from `~/build` itself (`bash ~/build/setup/pool-image.sh …`), hold the updater lock, and keep a journal: `~/.local/state/runner-updater/window`, one line per step, each written to disk before the step it names. When a window ends, its journal moves to `~/.local/state/runner-updater/windows/<id>`, and the full output of each validate and the two `/healthz` reads stay in `windows/<id>.d/`.

- `up --unattended <version> <digest>` checks what runs (both sets name one image, the registry still serves it, runscaler started after `config.toml` was installed, 10% of the disk free, a tested jq), renders and validates the new config into `~/.config/runner/config.staged.toml` (up to three tries, 20 s apart), and checks that it differs from `config.toml` in the image lines alone. Then it reads `/healthz` twice, 3 s apart; if any set is busy it removes the staged file, changes nothing and exits 3. If all are idle, it keeps `config.toml` as `config.toml.prev` (`backup`: a copy, checked against the config the window started with), renames the staged file over `config.toml` (`rename-start`, then `renamed` with the time; `config.toml` gets the time of the rename), waits for the next second, and restarts runscaler: it stops it (`stopping`), notes where the log ends once the old process has exited (`stopped`), starts it (`starting`), and waits until a process that started after the rename runs (`running`). Exit 0: the new image runs. If `config.toml` already names that image, nothing is switched: exit 0 when a runscaler that started after it was installed runs it, else exit 1 (`end`).
- `back --unattended` puts `config.toml.prev` back the same way, after it validated a copy of it, with no wait for idle: runscaler's restart lets busy runners finish their jobs first. Before the rename it keeps the config it replaces as `windows/<id>.d/config.toml.backup` (`backup`), the config the updater puts back if the rollback cannot run.

Each check of a file comes right before the step it guards, after that step's journal line. If `config.toml` changes by hand during a window, the window renames nothing over it and restarts nothing on it (but for a few milliseconds between a check and its step, which the header of `setup/pool-image.sh` names).

What a person reads in a journal: the last line says how the window ended. `closed` after `running`: done. `stop <name>: <text>` then `closed`: a STOP, and the text says what to do. `end <text>` then `closed`: nothing changed, and the updater tries again later. A journal still at `window` (not moved to `windows/`) did not end: the run was cut off, or `config.toml` was changed by hand once the rename had begun (`hand-change`, then `stop HAND CHANGE`). Then nothing restarts on that file, and the updater's next pass ends the journal. To keep such a file, check it with `RUNNER_START_CONFIG=~/.config/runner/config.toml ~/bin/runner-start validate`, and restart runscaler at idle only when that passes.

A person rolls back an updater's switch with the same mode, as RS_USER. It refuses while a journal is open, and it does nothing (exit 1, `end rollback pending`) while runscaler is stopped or disabled:
```
ssh <RS_USER>@<host> 'bash ~/build/setup/pool-image.sh back --unattended'
```

## The updater: status, on, off, pass

The runner-image updater runs as RS_USER: `~/bin/runner-updater` (Install step 10). In this release it only looks: a pass measures, asks the decision core (`~/build/core/`) and prints what it would do, and it starts, stops, switches and edits nothing. It sets its own `PATH`, so it runs the same from a terminal, a timer (a later release) or a non-interactive ssh. Its state is `~/.local/state/runner-updater/state.json`: ON or OFF, the family `hz-docker` (both sets of this host) with its candidate (the runner version it switched to and is observing), its previous image, the date until which `back` restores that image, its rejected versions and the STOPs it holds, and the decision core's own state. A fresh install has no state file: the updater is OFF.

- `status` prints ON or OFF, the family's candidate, back date and rejected versions, an open window journal, and the core's lines: each STOP with its next step, and the evidence it has. It takes no lock and writes nothing, so it runs at any time:
  ```
  ssh <RS_USER>@<host> '~/bin/runner-updater status'
  ```
- `runner-updater on` turns the updater on; `runner-updater off` turns it off. `off` refuses while a window journal is open (`~/.local/state/runner-updater/window`): it never leaves a window half done. Both wait while another run holds the updater lock (`~/.local/state/runner-updater/lock`), and say so:
  ```
  ssh <RS_USER>@<host> '~/bin/runner-updater on'
  ```
- `runner-updater pass` is what the timer will run. When another run holds the updater lock, or the updater is OFF, it ends at once. When a window journal is open, it prints `STOP RECOVER needed (S2b-3c)` and does nothing more: a later release's RECOVER ends that window, so do not delete the journal. When ON, it reads runscaler's process (from systemd), where runscaler's log ends and what it wrote since the last pass, the config runscaler runs and when it was installed, and two `/healthz` reads; it asks the core (idle, R1, KEEP, the STOP lines), keeps the core's state, and prints what it would do: `would roll back hz-docker`, `would accept hz-docker`, `would hold hz-docker: STOP …`, and whether it would switch now. Each pass's files are in `~/.local/state/runner-updater/pass/`.
- Under a jq that `core/TESTED_JQ` does not list for `core`, `status` and a pass that is ON print `STOP untested jq` (exit 3) and the line that runs the core's tests with it. A state file of another format, or with an entry this release does not read (a newer release wrote it), makes every command print `WAIT` (exit 4) and change nothing; one it cannot read is `REFUSE` (exit 1), and it is left as it is. A pass whose decision core waits (the core's own state, kept in the state file, is of a format it does not read) prints `WAIT` (exit 4) too, and changes nothing.
- A pass has no facts (`REFUSE no facts`, exit 1) when config.toml's lines would mislead the core, among them a top-level `log-level` other than `"info"` (what 03-runscaler.sh renders) or `"debug"`: at `warn` or `error` runscaler logs no finished job, so a quiet log would look like a healthy one.
- The weekly runner watchdog (`watchdog/run`) asks the owner to run `<its --hz line> runner-updater status`, by the bare name. An ssh command has no `~/bin` on its PATH, so the `--hz` line must put RS_USER's `~/bin` on it, in this shape:
  ```
  --hz 'ssh <RS_USER>@<host> PATH=/home/<RS_USER>/bin:/usr/local/bin:/usr/bin:/bin'
  ```

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

Then install this release's files as for every release ("A new runner release", its first paragraph), and do Install step 10 once: this release adds the updater, `~/bin/runner-updater`.

## A host that already runs these scripts from a hand copy

Until you do this, the host keeps running the files it has. The move installs the host config and this release's files, checks that the pool runs the config and image its records name, and does nothing else: it runs no 03 and restarts nothing. The scripts of this folder refuse to run without the host config, so it comes first:

1. Install step 1 (the host config, with the values the host uses today). Its `RUNNER_VERSION` is the runner version the pool runs now: "Upgrading from a release before this one", step 1, reads it.
2. Install step 3 for both users, then Install step 4, then Install step 10 (the updater's link: a fresh updater is OFF and starts nothing).
3. Check that runscaler runs the installed config.toml, read only. It prints the image config.toml names for both sets and the record that names it too (`image.ref`, or after a `back` the kept config, `config.toml.pre-image`), and checks that runscaler started after config.toml was installed (pool-image.sh's own rule, in whole seconds). It must end with `OK   runscaler started`. A line that starts with `STOP` says what to do: the move stops there; do it, then run this check again:
   ```
   ssh <RS_USER>@<host> 'bash -s' <<'EOF'
   R=~/.config/runner; img() { sed -n 's/^runner-image = "\(.*\)"$/\1/p' "$1" | sort -u; }
   c=$(img $R/config.toml); r=$(cat "/home/$(sed -n 's/^RUN_USER=//p' /etc/liveapp-ci/host.conf)/run/image.ref")
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

Do not run 03-runscaler.sh by hand on the running pool: it installs config.toml again, with a new time, and then the next `pool-image.sh up` (and the `accept` of an open release) refuses until runscaler restarts. The next runner release's `up` runs 03 itself ("A new runner release", step 2): it installs this release's `runner-start`, `pool-ready`, `validate-class` and unit, renders config.toml from the host config, and restarts runscaler when the pool is idle. If a value of the host config is not the one the pool runs, that `up` stops with config.toml as it was, and nothing restarts. If a release is still open (its `up` ran, and neither its `accept` nor its `back`), close it first with one of them ("A new runner release", step 3: `accept` or `back`).

## Uninstall

Follow the header of `setup/01-users-undo.sh` (what must happen before it), then as root:

```
ssh root@<host> 'bash -s' < linux-docker/setup/01-users-undo.sh
```
```
ssh root@<host> 'rm -rf /etc/liveapp-ci'
```
