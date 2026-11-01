# linux-docker — a Linux CI host that runs every job in a fresh Docker container

This folder is the Linux half of the repository: a Linux host where [runscaler](https://github.com/ysya/runscaler) takes jobs from GitHub runner scale sets and starts each one in a new container from a local runner image. The Mac product is the rest of the repository ([../README.md](../README.md)).

- Two host users. **RUN_USER** runs a rootless Docker daemon ("D1") and a local image registry, and holds no secret. **RS_USER** runs only runscaler (a systemd user unit) and holds the GitHub token; it reaches D1 through a second socket, as a member of RUN_USER's group. No job reaches a root Docker daemon.
- Jobs run on a `runners` network, with a pinned seccomp profile, no-new-privileges and an init process; `docker.dind` is always false. `runner-start` refuses to start runscaler with a config that would give a job a Docker socket.
- Every value of the host (the users, ports, address, organization, token name, set names and labels) is in ONE host config file, `/etc/liveapp-ci/host.conf`. The scripts hold none of them, and each one refuses to run without that file.

Status: these scripts run one host (Ubuntu 26.04, x86_64, Docker 29.9.0). They moved here unchanged except that the host values left them. `runner-start` refuses any Docker version other than the one the seccomp profile was cut from (29.9.0).

## Files

| File | Runs as | What it does |
|---|---|---|
| `host.conf.example` | — | Every key of the host config, with placeholder values and what each one is. |
| `setup/01-users.sh` | root | Creates RUN_USER and RS_USER, the group, the ssh keys, the runscaler lock rule and linger. Re-runnable. |
| `setup/01-users-undo.sh` | root | Removes only what 01-users.sh made (its header lists what must happen first). |
| `setup/02-d1.sh` | RUN_USER | The rootless Docker daemon and its hardening, the `runners` network, the local registry, and the runner image (built, pushed, checked; then its digest goes to `~/run/image.ref`). |
| `setup/03-runscaler.sh` | RS_USER | Installs runscaler (by sha256), `runner-start`, `pool-ready` and the unit; renders, checks and installs the config. Never restarts runscaler. |
| `setup/pool-image.sh` | RS_USER | Puts a new runner image into the pool (`up VERSION`), rolls it back (`back`), or ends the release (`accept`). |
| `bin/runner-start` | RS_USER | The unit's start command: checks the config, D1, the registry and the token files, then starts runscaler. |
| `bin/pool-ready` | RS_USER | Is runscaler serving exactly the named sets, each ready? |
| `image/Dockerfile` | RUN_USER | The runner image: GitHub's runner image by digest, plus bubblewrap, gh, a locale and build tools. |
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
3. **The files (once as RUN_USER, once as RS_USER).** Each user gets this release's `linux-docker/` as `~/build` (an older `~/build` is moved aside, not deleted):
   ```
   tar -C linux-docker -cf - . | ssh <RUN_USER>@<host> 'rm -rf ~/build.new && mkdir ~/build.new && tar -C ~/build.new -xf - && { [ ! -e ~/build ] || mv ~/build ~/build.prev.$(date -u +%Y%m%dT%H%M%SZ); } && mv ~/build.new ~/build'
   ```
   Then the same line with `<RS_USER>`.
4. **runscaler's download (RS_USER).** 03-runscaler.sh checks its sha256 before it extracts anything:
   ```
   ssh <RS_USER>@<host> 'mkdir -p ~/build/dl && curl -fsSL -o ~/build/dl/runner-linux-amd64.tar.gz https://github.com/ysya/runscaler/releases/download/v0.9.5/runner-linux-amd64.tar.gz'
   ```
5. **D1 and the runner image (RUN_USER).** It must end with `B2 DONE (D1)`:
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

1. A release of this repository puts the new runner image's digest into `image/Dockerfile`. Check it out, then do Install step 3 for both users (pool-image.sh refuses a `~/build` whose pinned files are not its own release's), then Install step 4: step 3 moves the old `~/build` aside with runscaler's download in it, and 03 checks that download first.
2. As RUN_USER, Install step 5 again: it builds and checks the new image, and only then writes its digest to `~/run/image.ref`.
3. As RS_USER, at a quiet time (it waits for the pool to be idle before it restarts runscaler):
   ```
   ssh -o ServerAliveInterval=60 <RS_USER>@<host> 'bash -s -- up <runner version>' < linux-docker/setup/pool-image.sh
   ```
4. After the first job on the new image passed: the same line with `accept`. If jobs fail on it: the same line with `back`.

## A host that already runs these scripts from a hand copy

Until you do this, the host keeps running the files it has. The move installs the host config and this release's files, and nothing else: it runs no 03 and restarts nothing. The scripts of this folder refuse to run without the host config, so it comes first:

1. Install step 1 (the host config, with the values the host uses today).
2. Install step 3 for both users, then Install step 4.
3. Check the host config against the running pool, read only. This release's `pool-ready` takes the health port from the host config; give it the set names from the host config. It must end with `READY`:
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
