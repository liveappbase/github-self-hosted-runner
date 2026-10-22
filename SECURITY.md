# Security

## Report a vulnerability

Use GitHub's private vulnerability reporting for this repository (Security → Report a vulnerability). Do not open a public issue for a security problem.

## The model in one paragraph

**Job code is untrusted.** A job runs as the admin user of a fresh macOS VM, which is deleted after the job. The network wall keeps that VM away from this Mac and your network. The wall protects the host **from jobs**. It does not protect the host from a compromised `ci` user: `ci` can run Tart without the shim and can write the wall stamp itself. The stamp guards against accidents, not against `ci`.

## What the wall blocks

Every VM that runscaler starts goes through the root-owned shim, which starts Tart with softnet and these flags: `--net-softnet-block=@host,224.0.0.0/4 --no-clipboard --no-audio`. softnet passes every packet of the VM through its own code and decides by destination.

- **This Mac:** every address of the host (SSH and Screen Sharing included).
- **Your network:** every private destination (your LAN, your router's LAN address). softnet admits only global addresses and the VM's own gateway; that gateway is the host, and `@host` blocks it.
- **mDNS:** multicast is blocked. An mDNS answer for the host's name can still reach a VM — it is the host's address on that VM's own private bridge — and that address is blocked like every other host address.
- **The clipboard and the audio input:** the VM gets neither device.
- IPv6 and other packet types from the VM are dropped.

`wall-check` proves, from inside a VM with the production flags, before any job runs, that these are NOT reachable: every IPv4 address of the host on 22 and 5900; the router, by each method a plain-NAT control VM used to reach it (ping, or TCP 53, 80 or 443); the VM's own gateway on 22 and 5900; every mDNS answer for the host's name; and a list of TCP ports on your public address (below). It also proves that github.com IS reachable. The control VM must first reach the host's LAN address (on 22 or 5900) and the router, so that "not reached" means something.

wall-check does not probe the rest. The IPv6 drop is softnet's code, multicast is the block list, and the missing clipboard and audio are the shim's flags: read in the code, not probed. The shim admits a VM only while the stamp of that proof matches the installed Tart, softnet and shim.

## What the wall does NOT block

- **The internet.** A job can send out anything it can read. It uses your public IP address: a service that allows that address trusts every job.
- **Your public IP address (the hairpin).** softnet admits global addresses, and your own public address is one. A job that connects to your public address reaches whatever your router answers or forwards there. **Only your router stops this:** turn off NAT loopback, UPnP and NAT-PMP, and administration from the internet, and forward no port to this Mac. wall-check probes your public address on a LIST of TCP ports (22 23 53 80 443 5900 7547 8080 8443 and the forwards you declare in `wall.conf`). It does not probe every port, and it does not probe UDP.
- **UPnP / NAT-PMP on your router.** A job could ask your router to open a port. Turn both off.
- **A compromised `ci` user** (above).

## Accounts and secrets on the host

- **softnet is setuid root and every local user can run it.** Keep no other untrusted user accounts on this Mac.
- **The token** (a fine-grained personal access token). A repository token (Administration: Read and write) can delete those repositories, add deploy keys and register a runner that receives their jobs and those jobs' secrets. An organization token (Self-hosted runners: Read and write, Administration: Read) can register runners and change runner groups for the whole organization, so a stolen one can take every job that names your label, with its secrets. `ci`, and anyone with ci's SSH key, holds that power. Use a 90-day expiry; revoke it on GitHub when you uninstall. VMs never receive the token: only runscaler reads it, and the shim starts Tart with an empty environment.
- FileVault is off (automatic login needs it): the token and the VM images are not encrypted at rest.
- Every `sudo` line runs only in the admin's own session — never with `su` or `sudo` from ci's session or ci's SSH, which `ci` controls.

## The trust chain of a release

- The trust root is **the named human maintainers** of this repository. No bot user and no GitHub App has write access.
- A release is immutable: its tag and its four assets (`…tar.gz`, `install-line.txt`, `root-line.txt`, `SHA256SUMS`) cannot change after publishing. Copy the two lines **only from the assets of the release you chose** — never from the release notes and never from the Mac. The README's "Check a release" compares them with `SHA256SUMS` and, with gh 2.81.0 or newer, checks them against the release's attestation (`gh release verify`, `gh release verify-asset`).
- The root line checks the sha256 of its own root-owned copy of `02-wall.sh` before it runs it. A compromised `ci` can change the staged files in ci's home; the root line then refuses, and nothing runs as root.

## Which repositories to serve

Private repositories are recommended. If a scale set serves a public repository, set "Require approval for all outside collaborators" for fork pull requests: otherwise anyone can run code on your Mac by opening a pull request. For an organization scale set, the runner group's repository access decides which repositories can run jobs here, not config.toml: keep "Allow public repositories" off for that group. This repository itself has no runner: its own check runs on GitHub-hosted runners.

## runscaler's limits (named, not patched)

- **Stopping kills running jobs.** `runner-disable` (and any stop of runscaler) drains, and the drain kills the VMs still running at its end. Stop only when the Mac is idle, and re-run a job the stop killed.
- **Shared fate.** One runscaler process serves every scale set: an error in one stops all of them, with their running VMs.
- **A refused VM start** (a stale stamp, low disk) leaves the job queued and leaves one never-connecting `runner-*` registration on GitHub per attempt (about one every 2 minutes). GitHub removes them after a day.
- A failed `[tart] dns` setting only warns; the image's own DNS is a second layer.

## Uninstall

The README's "Uninstall" removes the scale sets from GitHub, the service, the images, the tools, the token file and the root files, and tells you to revoke the token on GitHub.
