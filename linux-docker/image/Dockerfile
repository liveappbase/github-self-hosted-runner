# The Linux runner image. Built on the CI host by RUN_USER (02-d1.sh), pushed to the local registry on 127.0.0.1
# (REGISTRY_PORT); runscaler names it by digest. Base: GitHub's runner image by digest (the multi-arch index of
# actions-runner 2.338.2), PINNED: the OS, the runner user and the Docker tools. The RUNNER in the image is the release
# 02-d1.sh fetched and checked (its sha256 = the release asset's digest) and put into the build context as
# runner.tar.gz: install-runner.sh puts it in place of the base's runner. A new runner release changes nothing here.
# Adds what the stock image lacks and the jobs call: bubblewrap + gh (a sandboxed job), the en_US.UTF-8 locale (a test
# sets LC_ALL to it), and a classic runner host's tools (build-essential, xz, zstd).
FROM ghcr.io/actions/actions-runner@sha256:759a1d94a15b05941aba5196974ff43fe15b4cbba29b694b35cbc32a1166b232
USER root
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends bubblewrap gh build-essential xz-utils zstd locales \
 && locale-gen en_US.UTF-8 \
 && rm -rf /var/lib/apt/lists/*
COPY install-runner.sh runner.tar.gz /tmp/runner/
RUN bash /tmp/runner/install-runner.sh /tmp/runner/runner.tar.gz /home/runner && rm -rf /tmp/runner
USER runner
