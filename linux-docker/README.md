# linux-docker — a Linux CI host that runs every job in a fresh Docker container

This folder is the Linux half of the repository: a Linux host where [runscaler](https://github.com/ysya/runscaler) takes jobs from GitHub runner scale sets and starts each one in a new container from a local runner image. The Mac product is the rest of the repository ([../README.md](../README.md)).

- Two host users. **RUN_USER** runs a rootless Docker daemon ("D1") and a local image registry, and holds no secret. **RS_USER** runs only runscaler (a systemd user unit) and holds the GitHub token; it reaches D1 through a second socket, as a member of RUN_USER's group. No job reaches a root Docker daemon.
- Jobs run on a `runners` network, with a pinned seccomp profile, no-new-privileges and an init process; `docker.dind` is always false. `runner-start` refuses to start runscaler with a config that would give a job a Docker socket.
- Every value of the host (the users, ports, address, organization, token name, set names and labels) is in ONE host config file, `/etc/liveapp-ci/host.conf`. The scripts hold none of them, and each one refuses to run without that file.

Status: these scripts run one host (Ubuntu 26.04, x86_64, Docker 29.9.0). They moved here unchanged except that the host values left them, and except the build path of `02-d1.sh` (`build VERSION`, "A new runner release" below), which is new and has not yet run on that host. `runner-start` refuses any Docker version other than the one the seccomp profile was cut from (29.9.0).

## Files

| File | Runs as | What it does |
|---|---|---|
| `host.conf.example` | — | Every key of the host config, with placeholder values and what each one is. |
| `setup/01-users.sh` | root | Creates RUN_USER and RS_USER, the group, the ssh keys, the runscaler lock rule and linger. Re-runnable. |
| `setup/01-users-undo.sh` | root | Removes only what 01-users.sh made (its header lists what must happen first). |
| `setup/02-d1.sh` | RUN_USER | With no argument (the full run): the rootless Docker daemon and its hardening, the `runners` network, the local registry, and the runner image of the host config's `RUNNER_VERSION` (built, pushed, checked; then its build record, and its digest goes to `~/run/image.ref`). With `build VERSION`: only the runner image of that release, its checks and its build record. |
| `setup/runner-release.sh` | RUN_USER | Read by 02-d1.sh, never run: how a runner release is read from GitHub, and the trust of every download (below). |
| `setup/03-runscaler.sh` | RS_USER | Installs runscaler (by sha256), `runner-start`, `pool-ready` and the unit; renders, checks and installs the config. Never restarts runscaler. |
| `setup/pool-image.sh` | RS_USER | Puts a new runner image into the pool (`up VERSION`), rolls it back (`back`), or ends the release (`accept`). |
| `bin/runner-start` | RS_USER | The unit's start command: checks the config, D1, the registry and the token files, then starts runscaler. |
| `bin/pool-ready` | RS_USER | Is runscaler serving exactly the named sets, each ready? |
| `image/Dockerfile` | RUN_USER | The runner image: GitHub's runner image by digest (the pinned base), the runner of the release 02-d1.sh fetched, plus bubblewrap, gh, a locale and build tools. |
| `image/install-runner.sh` | (the build) | Run inside the image build: puts the fetched runner in place of the base image's runner. |
| `../setup/tls-excluded-spki` | — | The CA keys no download trusts (the repository's top-level `setup/`; the install puts it into `~/build/setup/`). |
| `config/` | — | The systemd unit and the two seccomp profiles (Docker's default, and the one the jobs run with). |

`setup/pool-image.sh` pins `setup/03-runscaler.sh`, `bin/runner-start`, `bin/pool-ready` and `config/runscaler.service` by sha256 (`PINS`). `tools/release-check` refuses a release in which one of them changed without its pin.

## Install

You need: a dedicated x86_64 Linux host with systemd, root ssh with your key, Docker Engine 29.9.0 with its rootless extras (`dockerd-rootless-setuptool.sh`) and `uidmap`, and `python3` (3.11 or newer), `curl`, `ss`, `nsenter` and `ip` on it. The scripts touch no root Docker daemon and no other user.

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
3. **The files (once as RUN_USER, once as RS_USER).** Each user gets this release's `linux-docker/` as `~/build`, with the repository's `setup/tls-excluded-spki` in `~/build/setup/` (an older `~/build` is moved aside, not deleted). `COPYFILE_DISABLE=1` keeps macOS's tar from adding `._` files, which would become part of the image recipe:
   ```
   COPYFILE_DISABLE=1 tar -C linux-docker -cf - . -C .. setup/tls-excluded-spki | ssh <RUN_USER>@<host> 'rm -rf ~/build.new && mkdir ~/build.new && tar -C ~/build.new -xf - && { [ ! -e ~/build ] || mv ~/build ~/build.prev.$(date -u +%Y%m%dT%H%M%SZ); } && mv ~/build.new ~/build'
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

## A new runner release

A new release of GitHub's runner ([actions/runner](https://github.com/actions/runner/releases)) needs no release of this repository: the image is built for the runner version you name. A release of this repository that changes `image/` or the base image is put in place the same way, after Install step 3 for both users and Install step 4 (pool-image.sh refuses a `~/build` whose pinned files are not its own release's; step 3 moves the old `~/build` aside with runscaler's download in it, and 03 checks that download first).

1. **Build the image (RUN_USER).** It reads the release from GitHub, checks the runner tarball against the release's own sha256 digest, builds the image on the pinned base, runs the image checks of Install step 5 on it, and writes its build record. It must end with `BUILD DONE (D1)`. A line that starts with `WAIT` means GitHub's rate limit: run it again later. It does not look at the updater's on/off setting, so it works with the updater off:
   ```
   ssh <RUN_USER>@<host> 'bash ~/build/setup/02-d1.sh build <runner version>'
   ```
2. **Put it into the pool (RS_USER), at a quiet time** (it waits for the pool to be idle before it restarts runscaler). Coming: in a later release, `up` reads the build record of that version. Until then `up` reads `~/run/image.ref`, which only the full run writes: set `RUNNER_VERSION` in the host config to the new version (Install step 1), run Install step 5 again instead of step 1 here, and then:
   ```
   ssh -o ServerAliveInterval=60 <RS_USER>@<host> 'bash -s -- up <runner version>' < linux-docker/setup/pool-image.sh
   ```
3. After the first job on the new image passed: the same line with `accept`. If jobs fail on it: the same line with `back`.

This release adds the host-config key `RUNNER_VERSION`: on a host installed before it, add that key (the runner version the pool runs now; Install step 1) before you run this release's 02-d1.sh, which refuses a host config without it.

**The build record.** Each build that passed every check writes `~/run/builds/<version>-<recipe>` as RUN_USER (0640, so RS_USER, a member of RUN_USER's group, can read it): exactly four lines, `format 1`, `version <version>`, `digest sha256:<the image's digest in the local registry>`, `recipe <the sha256 of image/'s files>`. There is one record per version and recipe; building the same version again replaces it. It is written under a temporary name and renamed, so a cut-off run leaves no partial record. A failed check, a version mismatch or a digest mismatch writes none. Its reader must read it as untrusted data: each line by its pattern, never sourced.

**The trust of the downloads.** Every download of the build path (GitHub's API and the runner tarball) uses `curl --cacert` with a filtered CA bundle (the system's bundle, without the certificates whose public key `setup/tls-excluded-spki` names) and `--capath` with an empty folder, so curl's built-in CA folder adds nothing back. That file's header gives its format; a file that breaks it, or names no key at all, stops the build before any download.

## A host that already runs these scripts from a hand copy

Until you do this, the host keeps running the files it has. The move installs the host config and this release's files, checks that the pool runs the config and image its records name, and does nothing else: it runs no 03 and restarts nothing. The scripts of this folder refuse to run without the host config, so it comes first:

1. Install step 1 (the host config, with the values the host uses today).
2. Install step 3 for both users, then Install step 4.
3. Check that runscaler runs the installed config.toml, read only. It prints the image config.toml names for both sets and the record that names it too (`image.ref`, or after a `back` the kept config, `config.toml.pre-image`), and checks that runscaler started after config.toml was installed (pool-image.sh's own rule, in whole seconds). It must end with `OK   runscaler started`. A line that starts with `STOP` says what to do: the move stops there; do it, then run this check again:
   ```
   ssh <RS_USER>@<host> 'bash -s' <<'EOF'
   R=~/.config/runner; img() { sed -n 's/^runner-image = "\(.*\)"$/\1/p' "$1" | sort -u; }
   c=$(img $R/config.toml); r=$(cat "/home/$(sed -n 's/^RUN_USER=//p' /etc/liveapp-ci/host.conf)/run/image.ref")
   [ "$(grep -c '^runner-image = ' $R/config.toml)" = 2 ] && [ "$(printf '%s\n' "$c" | grep -c .)" = 1 ] || { echo "STOP config.toml does not name ONE runner image for both sets: read $R/config.toml and find out what changed it"; exit 1; }
   if [ "$c" = "$r" ]; then echo "OK   config.toml names $c for both sets; image.ref names it too"
   elif cmp -s $R/config.toml.pre-image $R/config.toml; then echo "OK   config.toml names $c for both sets; it is the kept config of a back (image.ref still names the rejected $r)"
   else echo "STOP config.toml names $c, image.ref names $r, and config.toml is not the kept config of a back: a build that no up has put into the pool, or a file changed by hand. Put image.ref's image into the pool with this release's up (A new runner release, steps 3 and 4); do not edit image.ref to match config.toml, which would name an image that may never have run; then run this check again"; exit 1; fi
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

Do not run 03-runscaler.sh by hand on the running pool: it installs config.toml again, with a new time, and then the next `pool-image.sh up` (and the `accept` of an open release) refuses until runscaler restarts. The next runner release's `up` runs 03 itself ("A new runner release", step 3): it installs this release's `runner-start`, `pool-ready` and unit, renders config.toml from the host config, and restarts runscaler when the pool is idle. If a value of the host config is not the one the pool runs, that `up` stops with config.toml as it was, and nothing restarts. If a release is still open (its `up` ran, and neither its `accept` nor its `back`), close it first with one of them ("A new runner release", step 4).

## Uninstall

Follow the header of `setup/01-users-undo.sh` (what must happen before it), then as root:

```
ssh root@<host> 'bash -s' < linux-docker/setup/01-users-undo.sh
```
```
ssh root@<host> 'rm -rf /etc/liveapp-ci'
```
