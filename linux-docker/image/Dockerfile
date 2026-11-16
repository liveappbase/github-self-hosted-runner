# The Linux runner image. Built on the CI host by RUN_USER (02-d1.sh), pushed to the local registry on 127.0.0.1
# (REGISTRY_PORT); runscaler names it by digest. Base: GitHub's runner image by digest (the multi-arch index of
# actions-runner 2.338.2), PINNED: the OS, the runner user and the Docker tools. The RUNNER in the image is the release
# 02-d1.sh fetched and checked (its sha256 = the release asset's digest) and put into the build context as
# runner.tar.gz: install-runner.sh puts it in place of the base's runner. A new runner release changes nothing here.
# Adds what the stock image lacks and the jobs call: bubblewrap (a sandboxed job), the en_US.UTF-8 locale (a test sets
# LC_ALL to it), a classic runner host's tools (build-essential, xz, zstd), and gh.
# gh comes from GitHub's own apt repository (cli.github.com), never Ubuntu's: Ubuntu noble's gh is under most of gh's
# published security advisories. Its key is a file of this recipe, githubcli-archive-key.asc (GitHub CLI's public key as
# keyserver.ubuntu.com serves it under its fingerprint; no key is fetched at build time). The gh RUN dearmors it to the
# ONE keyring apt trusts for that source (its signed-by), checks THAT file with apt-key-pinned.sh (its one primary key
# must be the fingerprint the check names: the pin's one spelling on this host), and only then writes the source and
# runs apt-get update. The gh it installs must be at least the version in gh-floor (gh-floor-ok.sh, the one compare;
# 02-d1.sh step 6 (b) runs it again on the built image): with no gh of that repository for this architecture the build
# fails, it never falls back to Ubuntu's. Every command of that RUN is joined by &&, so a failed step stops the build.
FROM ghcr.io/actions/actions-runner@sha256:759a1d94a15b05941aba5196974ff43fe15b4cbba29b694b35cbc32a1166b232
USER root
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends bubblewrap build-essential xz-utils zstd locales \
 && locale-gen en_US.UTF-8 \
 && rm -rf /var/lib/apt/lists/*
COPY githubcli-archive-key.asc apt-key-pinned.sh gh-floor gh-floor-ok.sh /tmp/gh/
RUN install -d -m 755 /etc/apt/keyrings \
 && install -d -m 700 /tmp/gh/gnupg \
 && gpg --homedir /tmp/gh/gnupg --batch --dearmor -o /etc/apt/keyrings/githubcli-archive-keyring.gpg /tmp/gh/githubcli-archive-key.asc \
 && chmod 644 /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && bash /tmp/gh/apt-key-pinned.sh /etc/apt/keyrings/githubcli-archive-keyring.gpg 7F38BBB59D064DBCB3D84D725612B36462313325 \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gh \
 && bash /tmp/gh/gh-floor-ok.sh /tmp/gh/gh-floor "$(gh --version | sed -n '1s/^gh version \([^ ]*\).*/\1/p')" \
 && rm -rf /var/lib/apt/lists/* /tmp/gh
COPY install-runner.sh runner.tar.gz /tmp/runner/
RUN bash /tmp/runner/install-runner.sh /tmp/runner/runner.tar.gz /home/runner && rm -rf /tmp/runner
USER runner
