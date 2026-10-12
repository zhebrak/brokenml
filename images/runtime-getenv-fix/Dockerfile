# The study's runtime image with one Slurm fix, for re-grading the trials a platform defect left without a verdict
# (docs/preregistration.md, deviation ag). In the study's image, `sbatch --export=NONE` or `--export=<list>` (both turn
# on --get-user-env) makes slurmd load the user's environment through clone(CLONE_NEWPID|CLONE_NEWNS); an unprivileged
# node container may not create those namespaces (EPERM), so slurmd exits ("fatal: clone: Operation not permitted")
# and takes its node down. Slurm 26.05.2 is rebuilt here exactly as the base image builds it (giovtorres/
# slurm-docker-cluster 3.0.0, stage "builder": same base, packages, rpmmacros and `rpmbuild -ta`) with one patch,
# slurm-getenv-fork-fallback.patch: on that failure slurmd falls back to fork, Slurm's own path when namespaces are
# disabled. The RPM release becomes 1.ocb1.el9 and /opt/ocb/VERSION a new source hash (the base's is kept in
# /opt/ocb/VERSION.base) and /opt/ocb/BUILD the package-list hash over the patched packages, so the build shows in
# `rpm -q slurm` and in every grading's diagnostics (runtime_build, node_build); nothing else changes. Build: docker build -t bench/runtime:getenvfix1 images/runtime-getenv-fix
ARG RUNTIME_IMAGE=bench/runtime:dev
ARG BASE_VERSION=8631a20f3ea56bdc

FROM rockylinux/rockylinux:9 AS builder
RUN set -ex \
    && dnf makecache \
    && dnf -y install dnf-plugins-core epel-release \
    && dnf config-manager --set-enabled crb \
    && dnf makecache \
    && dnf -y install --nobest --exclude='*.i686' autoconf automake bzip2 freeipmi-devel dbus-devel gcc gcc-c++ git \
       gtk2-devel hdf5-devel http-parser-devel hwloc-devel json-c-devel libcurl-devel libyaml-devel lua-devel lz4-devel \
       make man2html mariadb-devel munge munge-devel ncurses-devel numactl-devel openssl-devel pam-devel perl python3.12 \
       python3.12-devel readline-devel rpm-build rpmdevtools rrdtool-devel wget libjwt libjwt-devel \
    && dnf clean all \
    && rm -rf /var/cache/dnf \
    && rpmdev-setuptree
COPY slurm.rpmmacros /root/.rpmmacros
COPY slurm-getenv-fork-fallback.patch /root/
RUN set -ex \
    && wget -q -O /root/slurm-26.05.2.tar.bz2 https://download.schedmd.com/slurm/slurm-26.05.2.tar.bz2 \
    && echo "01151f233dde64d95cc4ca96931aea3d4a2cad372ed9ad86a8b9f6b674600c3b  /root/slurm-26.05.2.tar.bz2" | sha256sum -c - \
    && cd /root \
    && tar xjf slurm-26.05.2.tar.bz2 \
    && patch -p1 -d slurm-26.05.2 < slurm-getenv-fork-fallback.patch \
    && tar cjf /root/rpmbuild/SOURCES/slurm-26.05.2.tar.bz2 slurm-26.05.2 \
    && rpmbuild -ta --define 'extraver .ocb1' /root/rpmbuild/SOURCES/slurm-26.05.2.tar.bz2 \
    && ls -lh /root/rpmbuild/RPMS/x86_64/

FROM ${RUNTIME_IMAGE}
ARG BASE_VERSION
COPY --from=builder /root/rpmbuild/RPMS/x86_64/ /tmp/rpms/
COPY slurm-getenv-fork-fallback.patch /tmp/rpms/
RUN set -ex \
    && test "$(cat /opt/ocb/VERSION)" = "${BASE_VERSION}" \
    && cd /tmp/rpms \
    && rpm -Uvh slurm-[0-9]*.rpm slurm-perlapi-*.rpm slurm-slurmctld-*.rpm slurm-slurmd-*.rpm slurm-slurmdbd-*.rpm \
       slurm-slurmrestd-*.rpm slurm-contribs-*.rpm slurm-devel-*.rpm \
    && rpm -q slurm slurm-slurmd | grep -c ocb1 | grep -qx 2 \
    && cp /opt/ocb/VERSION /opt/ocb/VERSION.base \
    && printf '%s+%s' "${BASE_VERSION}" "$(sha256sum slurm-getenv-fork-fallback.patch | cut -c1-64)" | sha256sum \
       | cut -c1-16 > /opt/ocb/VERSION \
    && cd / \
    && rm -rf /tmp/rpms
# The build ID the verifier records (runtime_build, node_build): the same recipe as images/runtime/Dockerfile, now over
# the patched packages, so every grading on this image names it; the study image's ID stays in BUILD.base.
RUN set -eo pipefail; cp /opt/ocb/BUILD /opt/ocb/BUILD.base && cp /opt/ocb/BUILD.txt /opt/ocb/BUILD.txt.base \
    && { rpm -qa | sort; uv pip freeze --system --python /usr/bin/python3.12; } > /opt/ocb/BUILD.txt \
    && sha256sum /opt/ocb/BUILD.txt | cut -c1-16 > /opt/ocb/BUILD \
    && ! cmp -s /opt/ocb/BUILD /opt/ocb/BUILD.base
