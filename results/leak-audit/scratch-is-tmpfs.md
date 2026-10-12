# Leak audit: scratch-is-tmpfs

Run on the agent environment after provisioning. 2026-10-04T07:22:39Z · commit 1bb6f4c05b48+dirty · runtime:dev 63f483811ac7, harness:dev 033924f733c4, runtime-cuda:dev ?, serve:dev 3c4a8c813af3 · AMD Ryzen 7 8745HS w/ Radeon 780M Graphics (dev-host); task sha256:496cd5086e567761a071eac344d290bb81800474faab8f93c6ba5133f128802f.

## container `main`

```
## whoami: root on 96e8b5a45c6d
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
/opt/ocb/ocb/metrics.py
/opt/ocb/ocb/frdump.py
### environment variables of all processes (names only, non-standard)
GIT_PAGER
NVIDIA_DRIVER_CAPABILITIES
NVIDIA_VISIBLE_DEVICES
PAGER
SYSTEMD_PAGER
### processes
munge    /usr/sbin/munged
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -150
root     /usr/bin/coreutils --coreutils-prog-shebang=sleep /usr/bin/sleep infinity
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess
LISTEN 0      4096      127.0.0.11:35409      0.0.0.0:*          
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /ops ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /run/cluster-keys ext4 ro,relatime 0 0
tmpfs /shared/ckpt tmpfs rw,relatime,size=524288k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.6 -> 96e8b5a45c6d
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.6	96e8b5a45c6d
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Sun, 04 Oct 2026 07:23:15 GMT
Content-Type: application/xml
Content-Length: 168

### environment of non-job processes not started by a login (names only)
### GPUs: device files here (only the GPU node may have them), site GPU and NCCL config, GPU variables

-- /etc/profile.d/bash_completion.sh (2024-04-30 11:43:58)
# shellcheck shell=sh disable=SC1091,SC2039,SC2166
# Check for interactive bash and that we haven't already been sourced.
if [ "x${BASH_VERSION-}" != x -a "x${PS1-}" != x -a "x${BASH_COMPLETION_VERSINFO-}" = x ]; then

    # Check for recent enough version of bash.
-- /etc/profile.d/colorgrep.csh (2022-05-16 14:43:06)

# color-grep initialization

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) then
-- /etc/profile.d/colorgrep.sh (2022-05-16 14:43:06)
# color-grep initialization

/usr/libexec/grepconf.sh -c || return

alias grep='grep --color=auto' 2>/dev/null
-- /etc/profile.d/colorxzgrep.csh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
alias xzgrep 'xzgrep --color=auto'
alias xzfgrep 'xzfgrep --color=auto'
alias xzegrep 'xzegrep --color=auto'
-- /etc/profile.d/colorxzgrep.sh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c || return
alias xzgrep='xzgrep --color=auto' 2>/dev/null
alias xzegrep='xzegrep --color=auto' 2>/dev/null
alias xzfgrep='xzfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/colorzgrep.csh (2022-10-30 00:14:30)
test -f /usr/libexec/grepconf.sh
if ( $status == 1 ) exit

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
-- /etc/profile.d/colorzgrep.sh (2022-10-30 00:14:30)
[ -f /usr/libexec/grepconf.sh ] || return

/usr/libexec/grepconf.sh -c || return
alias zgrep='zgrep --color=auto' 2>/dev/null
alias zfgrep='zfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/csh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, is sourced from /etc/csh.login
-- /etc/profile.d/debuginfod.csh (2026-01-03 09:13:11)
# $HOME/.login* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/debuginfod.sh (2026-01-03 09:13:11)
# $HOME/.profile* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/flatpak.sh (2024-04-17 17:19:24)
if command -v flatpak > /dev/null; then
    # set XDG_DATA_DIRS to include Flatpak installations

    new_dirs=$(
        (
-- /etc/profile.d/gawk.csh (2019-08-28 18:54:14)
alias gawkpath_default 'unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`'

alias gawkpath_prepend 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "\!*"":$AWKPATH"'

alias gawkpath_append 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "$AWKPATH"":\!*"'
-- /etc/profile.d/gawk.sh (2019-08-28 18:54:14)
gawkpath_default () {
	unset AWKPATH
	export AWKPATH=`gawk 'BEGIN {print ENVIRON["AWKPATH"]}'`
}

-- /etc/profile.d/lang.csh (2020-06-23 06:11:43)
# /etc/profile.d/lang.csh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/lang.sh (2020-06-23 06:11:43)
# /etc/profile.d/lang.sh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/less.csh (2025-11-03 06:42:30)
# less initialization script (csh)

# All less.*sh files should have the same semantics!

# In case you are curious, the test for non-emptiness is not as easy as in
-- /etc/profile.d/less.sh (2025-11-03 06:42:30)
# less initialization script (sh)

# All less.*sh files should have the same semantics!

if [ -z "$LESSOPEN" ] && [ -x /usr/bin/lesspipe.sh ]; then
-- /etc/profile.d/lmod.sh (2026-08-09 21:35:12)
source /usr/local/lmod/lmod/init/bash
export SPACK_ROOT=/usr/local/spack
export MODULEPATH="/opt/spack/modules/linux-rocky9-x86_64/Core:/opt/modulefiles"
source /usr/local/spack/share/spack/setup-env.sh
-- /etc/profile.d/sh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, it is sourced from /etc/profile
-- /etc/profile.d/which2.csh (2025-08-05 18:59:17)
# Initialization script for csh

# alias which 'alias | /usr/bin/which --tty-only --read-alias --show-dot --show-tilde'
-- /etc/profile.d/which2.sh (2025-08-05 18:59:18)
# shellcheck shell=sh
# Initialization script for bash, sh, mksh and ksh

if [ -r /proc/$$/exe ]; then
    SHELLNAME=$(basename $(readlink /proc/$$/exe))
115: CUDA_DEVICE_ORDER=PCI_BUS_ID
115: NVIDIA_DRIVER_CAPABILITIES=compute,utility
115: NVIDIA_VISIBLE_DEVICES=void
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
322: CUDA_DEVICE_ORDER=PCI_BUS_ID
322: NVIDIA_DRIVER_CAPABILITIES=compute,utility
322: NVIDIA_VISIBLE_DEVICES=void
323: CUDA_DEVICE_ORDER=PCI_BUS_ID
323: NVIDIA_DRIVER_CAPABILITIES=compute,utility
323: NVIDIA_VISIBLE_DEVICES=void
44: CUDA_DEVICE_ORDER=PCI_BUS_ID
44: NVIDIA_DRIVER_CAPABILITIES=compute,utility
44: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  4 07:22 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Aug  9 21:46 slurm
### ls /opt
total 20
drwxr-xr-x 1 root root 4096 Oct  4 07:20 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack
### ls /opt/modulefiles
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
### ls /opt/ocb
total 44
drwxr-xr-x 1 root root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ..
-rw-r--r-- 1 root root    17 Oct  4 07:20 BUILD
-rw-r--r-- 1 root root 24491 Oct  4 07:20 BUILD.txt
-rw-r--r-- 1 root root    17 Oct  4 07:20 VERSION
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ocb
### ls /opt/spack
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules
### ls /usr/local/bin
total 64636
drwxr-xr-x 1 root root     4096 Oct  4 07:20 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
-rwxr-xr-x 1 root root      302 Oct  1 21:56 f2py
-rwxr-xr-x 1 root root  1936948 Aug  9 21:33 gosu
-rwxr-xr-x 1 root root      291 Oct  1 21:56 isympy
-rwxr-xr-x 1 root root      302 Oct  1 21:56 numpy-config
-rwxr-xr-x 1 root root       39 Oct  4 07:20 ocb
-rwxr-xr-x 1 root root     2514 Oct  2 19:49 ocb-entrypoint.sh
-rwxr-xr-x 1 root root  8079336 Oct  1 21:56 py-spy
-rwxr-xr-x 1 root root      307 Oct  1 21:56 py.test
-rwxr-xr-x 1 root root      301 Oct  1 21:56 pygmentize
-rwxr-xr-x 1 root root      307 Oct  1 21:56 pytest
-rwxr-xr-x 1 root root      327 Oct  1 21:56 torchfrtrace
-rwxr-xr-x 1 root root      306 Oct  1 21:56 torchrun
-rwxr-xr-x 1 root root 56101408 Sep 29 18:43 uv
### ls /usr/local/libexec
total 36
drwxr-xr-x 1 root root 4096 Oct  4 07:22 .
drwxr-xr-x 1 root root 4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root 1449 Oct  1 23:13 gpu-ballast
-rwxr-xr-x 1 root root 2844 Oct  1 23:13 node-metrics
-rwxr-xr-x 1 root root 1684 Oct  4 07:20 ocb-healthcheck
-rwxr-xr-x 1 root root 1358 Oct  2 19:49 ocb-install-keys
-rwxr-xr-x 1 root root  749 Oct  2 19:19 ocb-keys
-rwxr-xr-x 1 root root 1230 Oct  4 07:20 ocb-taskprolog
### ls /etc/platform
total 28
drwxr-xr-x 1 root root 4096 Oct  4 07:22 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Jun  2 16:40 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  4 07:20 objstore.conf
### ls /root
total 48
dr-xr-x--- 1 root  root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root  root  4096 Oct  4 07:22 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
drwxr-xr-x 3 root  root  4096 Oct  4 07:20 .cache
-rw-r--r-- 1 root  root   100 May 25 20:19 .cshrc
drwx------ 1 root  root  4096 Oct  4 07:22 .ssh
-rw-r--r-- 1 root  root   129 May 25 20:19 .tcshrc
-rw------- 1 root  root   532 Aug  9 21:35 .viminfo
drw------- 3 slurm slurm 4096 Aug  9 21:31 examples
### site configuration files
-- /etc/platform/job.env (119 bytes, 2026-06-02 16:40:00.000000000)
# Site job environment (platform team), applied to every job task before /ops/cluster/nodes/<node>.env.
LC_ALL=C.UTF-8
-- /etc/platform/node-metrics.conf (10 bytes, 2026-06-02 16:40:00.000000000 )
port=9100
-- /etc/platform/objstore.conf (25 bytes, 2026-10-04 07:20:04.000000000 )
url=http://objstore:8000
### task id: places the agent reads, grepped for scratch-is-tmpfs
### task id hits: 0
sed: -e expression #1, char 16: 
```

## container `slurmctld`

```
## whoami: root on slurmctld
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
/opt/ocb/ocb/metrics.py
/opt/ocb/ocb/frdump.py
### environment variables of all processes (names only, non-standard)

/sshd [listener] 0 of 10-100 startups
GIT_PAGER
NVIDIA_DRIVER_CAPABILITIES
NVIDIA_VISIBLE_DEVICES
PAGER
SYSTEMD_PAGER
d
### processes
munge    /usr/sbin/munged
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -150
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
root     sshd: /usr/sbin/sshd [listener] 0 of 10-100 startups
slurm    /usr/sbin/slurmctld -D -i
slurm    slurmctld: slurmscriptd
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                      
LISTEN 0      4096         0.0.0.0:6817       0.0.0.0:*                                
LISTEN 0      4096      127.0.0.11:36013      0.0.0.0:*                                
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=42,fd=7))
LISTEN 0      128             [::]:22            [::]:*    users:(("sshd",pid=42,fd=8))
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /run/cluster-keys ext4 ro,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.5 -> slurmctld
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.5	slurmctld
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Sun, 04 Oct 2026 07:23:15 GMT
Content-Type: application/xml
Content-Length: 168

### environment of non-job processes not started by a login (names only)
### GPUs: device files here (only the GPU node may have them), site GPU and NCCL config, GPU variables

-- /etc/profile.d/bash_completion.sh (2024-04-30 11:43:58)
# shellcheck shell=sh disable=SC1091,SC2039,SC2166
# Check for interactive bash and that we haven't already been sourced.
if [ "x${BASH_VERSION-}" != x -a "x${PS1-}" != x -a "x${BASH_COMPLETION_VERSINFO-}" = x ]; then

    # Check for recent enough version of bash.
-- /etc/profile.d/colorgrep.csh (2022-05-16 14:43:06)

# color-grep initialization

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) then
-- /etc/profile.d/colorgrep.sh (2022-05-16 14:43:06)
# color-grep initialization

/usr/libexec/grepconf.sh -c || return

alias grep='grep --color=auto' 2>/dev/null
-- /etc/profile.d/colorxzgrep.csh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
alias xzgrep 'xzgrep --color=auto'
alias xzfgrep 'xzfgrep --color=auto'
alias xzegrep 'xzegrep --color=auto'
-- /etc/profile.d/colorxzgrep.sh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c || return
alias xzgrep='xzgrep --color=auto' 2>/dev/null
alias xzegrep='xzegrep --color=auto' 2>/dev/null
alias xzfgrep='xzfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/colorzgrep.csh (2022-10-30 00:14:30)
test -f /usr/libexec/grepconf.sh
if ( $status == 1 ) exit

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
-- /etc/profile.d/colorzgrep.sh (2022-10-30 00:14:30)
[ -f /usr/libexec/grepconf.sh ] || return

/usr/libexec/grepconf.sh -c || return
alias zgrep='zgrep --color=auto' 2>/dev/null
alias zfgrep='zfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/csh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, is sourced from /etc/csh.login
-- /etc/profile.d/debuginfod.csh (2026-01-03 09:13:11)
# $HOME/.login* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/debuginfod.sh (2026-01-03 09:13:11)
# $HOME/.profile* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/flatpak.sh (2024-04-17 17:19:24)
if command -v flatpak > /dev/null; then
    # set XDG_DATA_DIRS to include Flatpak installations

    new_dirs=$(
        (
-- /etc/profile.d/gawk.csh (2019-08-28 18:54:14)
alias gawkpath_default 'unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`'

alias gawkpath_prepend 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "\!*"":$AWKPATH"'

alias gawkpath_append 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "$AWKPATH"":\!*"'
-- /etc/profile.d/gawk.sh (2019-08-28 18:54:14)
gawkpath_default () {
	unset AWKPATH
	export AWKPATH=`gawk 'BEGIN {print ENVIRON["AWKPATH"]}'`
}

-- /etc/profile.d/lang.csh (2020-06-23 06:11:43)
# /etc/profile.d/lang.csh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/lang.sh (2020-06-23 06:11:43)
# /etc/profile.d/lang.sh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/less.csh (2025-11-03 06:42:30)
# less initialization script (csh)

# All less.*sh files should have the same semantics!

# In case you are curious, the test for non-emptiness is not as easy as in
-- /etc/profile.d/less.sh (2025-11-03 06:42:30)
# less initialization script (sh)

# All less.*sh files should have the same semantics!

if [ -z "$LESSOPEN" ] && [ -x /usr/bin/lesspipe.sh ]; then
-- /etc/profile.d/lmod.sh (2026-08-09 21:35:12)
source /usr/local/lmod/lmod/init/bash
export SPACK_ROOT=/usr/local/spack
export MODULEPATH="/opt/spack/modules/linux-rocky9-x86_64/Core:/opt/modulefiles"
source /usr/local/spack/share/spack/setup-env.sh
-- /etc/profile.d/sh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, it is sourced from /etc/profile
-- /etc/profile.d/which2.csh (2025-08-05 18:59:17)
# Initialization script for csh

# alias which 'alias | /usr/bin/which --tty-only --read-alias --show-dot --show-tilde'
-- /etc/profile.d/which2.sh (2025-08-05 18:59:18)
# shellcheck shell=sh
# Initialization script for bash, sh, mksh and ksh

if [ -r /proc/$$/exe ]; then
    SHELLNAME=$(basename $(readlink /proc/$$/exe))
153: CUDA_DEVICE_ORDER=PCI_BUS_ID
153: NVIDIA_DRIVER_CAPABILITIES=compute,utility
153: NVIDIA_VISIBLE_DEVICES=void
377: CUDA_DEVICE_ORDER=PCI_BUS_ID
377: NVIDIA_DRIVER_CAPABILITIES=compute,utility
377: NVIDIA_VISIBLE_DEVICES=void
378: CUDA_DEVICE_ORDER=PCI_BUS_ID
378: NVIDIA_DRIVER_CAPABILITIES=compute,utility
378: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  4 07:22 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Oct  4 07:22 slurm
### ls /opt
total 20
drwxr-xr-x 1 root root 4096 Oct  4 07:20 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack
### ls /opt/modulefiles
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
### ls /opt/ocb
total 44
drwxr-xr-x 1 root root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ..
-rw-r--r-- 1 root root    17 Oct  4 07:20 BUILD
-rw-r--r-- 1 root root 24491 Oct  4 07:20 BUILD.txt
-rw-r--r-- 1 root root    17 Oct  4 07:20 VERSION
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ocb
### ls /opt/spack
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules
### ls /usr/local/bin
total 64636
drwxr-xr-x 1 root root     4096 Oct  4 07:20 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
-rwxr-xr-x 1 root root      302 Oct  1 21:56 f2py
-rwxr-xr-x 1 root root  1936948 Aug  9 21:33 gosu
-rwxr-xr-x 1 root root      291 Oct  1 21:56 isympy
-rwxr-xr-x 1 root root      302 Oct  1 21:56 numpy-config
-rwxr-xr-x 1 root root       39 Oct  4 07:20 ocb
-rwxr-xr-x 1 root root     2514 Oct  2 19:49 ocb-entrypoint.sh
-rwxr-xr-x 1 root root  8079336 Oct  1 21:56 py-spy
-rwxr-xr-x 1 root root      307 Oct  1 21:56 py.test
-rwxr-xr-x 1 root root      301 Oct  1 21:56 pygmentize
-rwxr-xr-x 1 root root      307 Oct  1 21:56 pytest
-rwxr-xr-x 1 root root      327 Oct  1 21:56 torchfrtrace
-rwxr-xr-x 1 root root      306 Oct  1 21:56 torchrun
-rwxr-xr-x 1 root root 56101408 Sep 29 18:43 uv
### ls /usr/local/libexec
total 36
drwxr-xr-x 1 root root 4096 Oct  4 07:22 .
drwxr-xr-x 1 root root 4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root 1449 Oct  1 23:13 gpu-ballast
-rwxr-xr-x 1 root root 2844 Oct  1 23:13 node-metrics
-rwxr-xr-x 1 root root 1684 Oct  4 07:20 ocb-healthcheck
-rwxr-xr-x 1 root root 1358 Oct  2 19:49 ocb-install-keys
-rwxr-xr-x 1 root root  749 Oct  2 19:19 ocb-keys
-rwxr-xr-x 1 root root 1230 Oct  4 07:20 ocb-taskprolog
### ls /etc/platform
total 28
drwxr-xr-x 1 root root 4096 Oct  4 07:22 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Jun  2 16:40 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  4 07:20 objstore.conf
### ls /root
total 48
dr-xr-x--- 1 root  root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root  root  4096 Oct  4 07:22 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
drwxr-xr-x 3 root  root  4096 Oct  4 07:20 .cache
-rw-r--r-- 1 root  root   100 May 25 20:19 .cshrc
drwx------ 1 root  root  4096 Oct  4 07:22 .ssh
-rw-r--r-- 1 root  root   129 May 25 20:19 .tcshrc
-rw------- 1 root  root   532 Aug  9 21:35 .viminfo
drw------- 3 slurm slurm 4096 Aug  9 21:31 examples
### site configuration files
-- /etc/platform/job.env (119 bytes, 2026-06-02 16:40:00.000000000)
# Site job environment (platform team), applied to every job task before /ops/cluster/nodes/<node>.env.
LC_ALL=C.UTF-8
-- /etc/platform/node-metrics.conf (10 bytes, 2026-06-02 16:40:00.000000000 )
port=9100
-- /etc/platform/objstore.conf (25 bytes, 2026-10-04 07:20:04.000000000 )
url=http://objstore:8000
### task id: places the agent reads, grepped for scratch-is-tmpfs
### task
```

## container `provision`

```
Error response from daemon: container 6c713935c1306d4338c0d5598a37de8420fc00a163bbc968dc3dc328e10787d7 is not running
```

## container `c1`

```
## whoami: root on c1
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
/opt/ocb/ocb/metrics.py
/opt/ocb/ocb/frdump.py
### environment variables of all processes (names only, non-standard)

/sshd [listener] 0 of 10-100 startups
GIT_PAGER
NVIDIA_DRIVER_CAPABILITIES
NVIDIA_VISIBLE_DEVICES
PAGER
SYSTEMD_PAGER
v
### processes
metrics  python3 /usr/local/libexec/node-metrics
munge    /usr/sbin/munged
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -150
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
root     /usr/sbin/slurmd -D -N c1
root     [slurmstepd] <defunct>
root     sshd: /usr/sbin/sshd [listener] 0 of 10-100 startups
svc-tra+ [srun] <defunct>
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                         
LISTEN 0      128          0.0.0.0:9100       0.0.0.0:*    users:(("python3",pid=47,fd=3))
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=48,fd=7))   
LISTEN 0      4096      127.0.0.11:44923      0.0.0.0:*                                   
LISTEN 0      4096         0.0.0.0:6818       0.0.0.0:*    users:(("slurmd",pid=1,fd=10)) 
LISTEN 0      128             [::]:22            [::]:*    users:(("sshd",pid=48,fd=8))   
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
tmpfs /scratch tmpfs rw,nosuid,nodev,noexec,relatime,size=4194304k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /ops ext4 ro,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /run/cluster-keys ext4 ro,relatime 0 0
tmpfs /shared/ckpt tmpfs rw,relatime,size=524288k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.3 -> c1
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.3	c1
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Sun, 04 Oct 2026 07:23:16 GMT
Content-Type: application/xml
Content-Length: 168

### environment of non-job processes not started by a login (names only)
### GPUs: device files here (only the GPU node may have them), site GPU and NCCL config, GPU variables

-- /etc/profile.d/bash_completion.sh (2024-04-30 11:43:58)
# shellcheck shell=sh disable=SC1091,SC2039,SC2166
# Check for interactive bash and that we haven't already been sourced.
if [ "x${BASH_VERSION-}" != x -a "x${PS1-}" != x -a "x${BASH_COMPLETION_VERSINFO-}" = x ]; then

    # Check for recent enough version of bash.
-- /etc/profile.d/colorgrep.csh (2022-05-16 14:43:06)

# color-grep initialization

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) then
-- /etc/profile.d/colorgrep.sh (2022-05-16 14:43:06)
# color-grep initialization

/usr/libexec/grepconf.sh -c || return

alias grep='grep --color=auto' 2>/dev/null
-- /etc/profile.d/colorxzgrep.csh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
alias xzgrep 'xzgrep --color=auto'
alias xzfgrep 'xzfgrep --color=auto'
alias xzegrep 'xzegrep --color=auto'
-- /etc/profile.d/colorxzgrep.sh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c || return
alias xzgrep='xzgrep --color=auto' 2>/dev/null
alias xzegrep='xzegrep --color=auto' 2>/dev/null
alias xzfgrep='xzfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/colorzgrep.csh (2022-10-30 00:14:30)
test -f /usr/libexec/grepconf.sh
if ( $status == 1 ) exit

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
-- /etc/profile.d/colorzgrep.sh (2022-10-30 00:14:30)
[ -f /usr/libexec/grepconf.sh ] || return

/usr/libexec/grepconf.sh -c || return
alias zgrep='zgrep --color=auto' 2>/dev/null
alias zfgrep='zfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/csh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, is sourced from /etc/csh.login
-- /etc/profile.d/debuginfod.csh (2026-01-03 09:13:11)
# $HOME/.login* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/debuginfod.sh (2026-01-03 09:13:11)
# $HOME/.profile* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/flatpak.sh (2024-04-17 17:19:24)
if command -v flatpak > /dev/null; then
    # set XDG_DATA_DIRS to include Flatpak installations

    new_dirs=$(
        (
-- /etc/profile.d/gawk.csh (2019-08-28 18:54:14)
alias gawkpath_default 'unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`'

alias gawkpath_prepend 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "\!*"":$AWKPATH"'

alias gawkpath_append 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "$AWKPATH"":\!*"'
-- /etc/profile.d/gawk.sh (2019-08-28 18:54:14)
gawkpath_default () {
	unset AWKPATH
	export AWKPATH=`gawk 'BEGIN {print ENVIRON["AWKPATH"]}'`
}

-- /etc/profile.d/lang.csh (2020-06-23 06:11:43)
# /etc/profile.d/lang.csh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/lang.sh (2020-06-23 06:11:43)
# /etc/profile.d/lang.sh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/less.csh (2025-11-03 06:42:30)
# less initialization script (csh)

# All less.*sh files should have the same semantics!

# In case you are curious, the test for non-emptiness is not as easy as in
-- /etc/profile.d/less.sh (2025-11-03 06:42:30)
# less initialization script (sh)

# All less.*sh files should have the same semantics!

if [ -z "$LESSOPEN" ] && [ -x /usr/bin/lesspipe.sh ]; then
-- /etc/profile.d/lmod.sh (2026-08-09 21:35:12)
source /usr/local/lmod/lmod/init/bash
export SPACK_ROOT=/usr/local/spack
export MODULEPATH="/opt/spack/modules/linux-rocky9-x86_64/Core:/opt/modulefiles"
source /usr/local/spack/share/spack/setup-env.sh
-- /etc/profile.d/sh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, it is sourced from /etc/profile
-- /etc/profile.d/which2.csh (2025-08-05 18:59:17)
# Initialization script for csh

# alias which 'alias | /usr/bin/which --tty-only --read-alias --show-dot --show-tilde'
-- /etc/profile.d/which2.sh (2025-08-05 18:59:18)
# shellcheck shell=sh
# Initialization script for bash, sh, mksh and ksh

if [ -r /proc/$$/exe ]; then
    SHELLNAME=$(basename $(readlink /proc/$$/exe))
186: CUDA_DEVICE_ORDER=PCI_BUS_ID
186: NVIDIA_DRIVER_CAPABILITIES=compute,utility
186: NVIDIA_VISIBLE_DEVICES=void
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
36: CUDA_DEVICE_ORDER=PCI_BUS_ID
36: NVIDIA_DRIVER_CAPABILITIES=compute,utility
36: NVIDIA_VISIBLE_DEVICES=void
441: CUDA_DEVICE_ORDER=PCI_BUS_ID
441: NVIDIA_DRIVER_CAPABILITIES=compute,utility
441: NVIDIA_VISIBLE_DEVICES=void
442: CUDA_DEVICE_ORDER=PCI_BUS_ID
442: NVIDIA_DRIVER_CAPABILITIES=compute,utility
442: NVIDIA_VISIBLE_DEVICES=void
443: CUDA_DEVICE_ORDER=PCI_BUS_ID
443: NVIDIA_DRIVER_CAPABILITIES=compute,utility
443: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  4 07:22 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Oct  4 07:22 slurm
### ls /opt
total 20
drwxr-xr-x 1 root root 4096 Oct  4 07:20 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack
### ls /opt/modulefiles
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
### ls /opt/ocb
total 44
drwxr-xr-x 1 root root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ..
-rw-r--r-- 1 root root    17 Oct  4 07:20 BUILD
-rw-r--r-- 1 root root 24491 Oct  4 07:20 BUILD.txt
-rw-r--r-- 1 root root    17 Oct  4 07:20 VERSION
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ocb
### ls /opt/spack
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules
### ls /usr/local/bin
total 64636
drwxr-xr-x 1 root root     4096 Oct  4 07:20 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
-rwxr-xr-x 1 root root      302 Oct  1 21:56 f2py
-rwxr-xr-x 1 root root  1936948 Aug  9 21:33 gosu
-rwxr-xr-x 1 root root      291 Oct  1 21:56 isympy
-rwxr-xr-x 1 root root      302 Oct  1 21:56 numpy-config
-rwxr-xr-x 1 root root       39 Oct  4 07:20 ocb
-rwxr-xr-x 1 root root     2514 Oct  2 19:49 ocb-entrypoint.sh
-rwxr-xr-x 1 root root  8079336 Oct  1 21:56 py-spy
-rwxr-xr-x 1 root root      307 Oct  1 21:56 py.test
-rwxr-xr-x 1 root root      301 Oct  1 21:56 pygmentize
-rwxr-xr-x 1 root root      307 Oct  1 21:56 pytest
-rwxr-xr-x 1 root root      327 Oct  1 21:56 torchfrtrace
-rwxr-xr-x 1 root root      306 Oct  1 21:56 torchrun
-rwxr-xr-x 1 root root 56101408 Sep 29 18:43 uv
### ls /usr/local/libexec
total 36
drwxr-xr-x 1 root root 4096 Oct  4 07:22 .
drwxr-xr-x 1 root root 4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root 1449 Oct  1 23:13 gpu-ballast
-rwxr-xr-x 1 root root 2844 Oct  1 23:13 node-metrics
-rwxr-xr-x 1 root root 1684 Oct  4 07:20 ocb-healthcheck
-rwxr-xr-x 1 root root 1358 Oct  2 19:49 ocb-install-keys
-rwxr-xr-x 1 root root  749 Oct  2 19:19 ocb-keys
-rwxr-xr-x 1 root root 1230 Oct  4 07:20 ocb-taskprolog
### ls /etc/platform
total 28
drwxr-xr-x 1 root root 4096 Oct  4 07:22 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Jun  2 16:40 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  4 07:20 objstore.conf
### ls /root
total 48
dr-xr-x--- 1 root  root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root  root  4096 Oct  4 07:22 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
drwxr-xr-x 3 root  root  4096 Oct  4 07:20 .cache
-rw-r--r-- 1 root  root   100 May 
```

## container `c2`

```
## whoami: root on c2
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
/opt/ocb/ocb/metrics.py
/opt/ocb/ocb/frdump.py
### environment variables of all processes (names only, non-standard)

/sshd [listener] 0 of 10-100 startups
GIT_PAGER
NVIDIA_DRIVER_CAPABILITIES
NVIDIA_VISIBLE_DEVICES
PAGER
SYSTEMD_PAGER
v
### processes
metrics  python3 /usr/local/libexec/node-metrics
munge    /usr/sbin/munged
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -150
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
root     /usr/sbin/slurmd -D -N c2
root     [slurmstepd] <defunct>
root     sshd: /usr/sbin/sshd [listener] 0 of 10-100 startups
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                         
LISTEN 0      4096         0.0.0.0:6818       0.0.0.0:*    users:(("slurmd",pid=1,fd=10)) 
LISTEN 0      4096      127.0.0.11:33431      0.0.0.0:*                                   
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=49,fd=7))   
LISTEN 0      128          0.0.0.0:9100       0.0.0.0:*    users:(("python3",pid=48,fd=3))
LISTEN 0      128             [::]:22            [::]:*    users:(("sshd",pid=49,fd=8))   
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /ops ext4 ro,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /run/cluster-keys ext4 ro,relatime 0 0
tmpfs /shared/ckpt tmpfs rw,relatime,size=524288k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.7 -> c2
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.7	c2
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Sun, 04 Oct 2026 07:23:17 GMT
Content-Type: application/xml
Content-Length: 168

### environment of non-job processes not started by a login (names only)
### GPUs: device files here (only the GPU node may have them), site GPU and NCCL config, GPU variables

-- /etc/profile.d/bash_completion.sh (2024-04-30 11:43:58)
# shellcheck shell=sh disable=SC1091,SC2039,SC2166
# Check for interactive bash and that we haven't already been sourced.
if [ "x${BASH_VERSION-}" != x -a "x${PS1-}" != x -a "x${BASH_COMPLETION_VERSINFO-}" = x ]; then

    # Check for recent enough version of bash.
-- /etc/profile.d/colorgrep.csh (2022-05-16 14:43:06)

# color-grep initialization

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) then
-- /etc/profile.d/colorgrep.sh (2022-05-16 14:43:06)
# color-grep initialization

/usr/libexec/grepconf.sh -c || return

alias grep='grep --color=auto' 2>/dev/null
-- /etc/profile.d/colorxzgrep.csh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
alias xzgrep 'xzgrep --color=auto'
alias xzfgrep 'xzfgrep --color=auto'
alias xzegrep 'xzegrep --color=auto'
-- /etc/profile.d/colorxzgrep.sh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c || return
alias xzgrep='xzgrep --color=auto' 2>/dev/null
alias xzegrep='xzegrep --color=auto' 2>/dev/null
alias xzfgrep='xzfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/colorzgrep.csh (2022-10-30 00:14:30)
test -f /usr/libexec/grepconf.sh
if ( $status == 1 ) exit

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
-- /etc/profile.d/colorzgrep.sh (2022-10-30 00:14:30)
[ -f /usr/libexec/grepconf.sh ] || return

/usr/libexec/grepconf.sh -c || return
alias zgrep='zgrep --color=auto' 2>/dev/null
alias zfgrep='zfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/csh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, is sourced from /etc/csh.login
-- /etc/profile.d/debuginfod.csh (2026-01-03 09:13:11)
# $HOME/.login* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/debuginfod.sh (2026-01-03 09:13:11)
# $HOME/.profile* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/flatpak.sh (2024-04-17 17:19:24)
if command -v flatpak > /dev/null; then
    # set XDG_DATA_DIRS to include Flatpak installations

    new_dirs=$(
        (
-- /etc/profile.d/gawk.csh (2019-08-28 18:54:14)
alias gawkpath_default 'unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`'

alias gawkpath_prepend 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "\!*"":$AWKPATH"'

alias gawkpath_append 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "$AWKPATH"":\!*"'
-- /etc/profile.d/gawk.sh (2019-08-28 18:54:14)
gawkpath_default () {
	unset AWKPATH
	export AWKPATH=`gawk 'BEGIN {print ENVIRON["AWKPATH"]}'`
}

-- /etc/profile.d/lang.csh (2020-06-23 06:11:43)
# /etc/profile.d/lang.csh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/lang.sh (2020-06-23 06:11:43)
# /etc/profile.d/lang.sh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/less.csh (2025-11-03 06:42:30)
# less initialization script (csh)

# All less.*sh files should have the same semantics!

# In case you are curious, the test for non-emptiness is not as easy as in
-- /etc/profile.d/less.sh (2025-11-03 06:42:30)
# less initialization script (sh)

# All less.*sh files should have the same semantics!

if [ -z "$LESSOPEN" ] && [ -x /usr/bin/lesspipe.sh ]; then
-- /etc/profile.d/lmod.sh (2026-08-09 21:35:12)
source /usr/local/lmod/lmod/init/bash
export SPACK_ROOT=/usr/local/spack
export MODULEPATH="/opt/spack/modules/linux-rocky9-x86_64/Core:/opt/modulefiles"
source /usr/local/spack/share/spack/setup-env.sh
-- /etc/profile.d/sh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, it is sourced from /etc/profile
-- /etc/profile.d/which2.csh (2025-08-05 18:59:17)
# Initialization script for csh

# alias which 'alias | /usr/bin/which --tty-only --read-alias --show-dot --show-tilde'
-- /etc/profile.d/which2.sh (2025-08-05 18:59:18)
# shellcheck shell=sh
# Initialization script for bash, sh, mksh and ksh

if [ -r /proc/$$/exe ]; then
    SHELLNAME=$(basename $(readlink /proc/$$/exe))
154: CUDA_DEVICE_ORDER=PCI_BUS_ID
154: NVIDIA_DRIVER_CAPABILITIES=compute,utility
154: NVIDIA_VISIBLE_DEVICES=void
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
37: CUDA_DEVICE_ORDER=PCI_BUS_ID
37: NVIDIA_DRIVER_CAPABILITIES=compute,utility
37: NVIDIA_VISIBLE_DEVICES=void
406: CUDA_DEVICE_ORDER=PCI_BUS_ID
406: NVIDIA_DRIVER_CAPABILITIES=compute,utility
406: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  4 07:22 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Oct  4 07:22 slurm
### ls /opt
total 20
drwxr-xr-x 1 root root 4096 Oct  4 07:20 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack
### ls /opt/modulefiles
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
### ls /opt/ocb
total 44
drwxr-xr-x 1 root root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ..
-rw-r--r-- 1 root root    17 Oct  4 07:20 BUILD
-rw-r--r-- 1 root root 24491 Oct  4 07:20 BUILD.txt
-rw-r--r-- 1 root root    17 Oct  4 07:20 VERSION
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ocb
### ls /opt/spack
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules
### ls /usr/local/bin
total 64636
drwxr-xr-x 1 root root     4096 Oct  4 07:20 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
-rwxr-xr-x 1 root root      302 Oct  1 21:56 f2py
-rwxr-xr-x 1 root root  1936948 Aug  9 21:33 gosu
-rwxr-xr-x 1 root root      291 Oct  1 21:56 isympy
-rwxr-xr-x 1 root root      302 Oct  1 21:56 numpy-config
-rwxr-xr-x 1 root root       39 Oct  4 07:20 ocb
-rwxr-xr-x 1 root root     2514 Oct  2 19:49 ocb-entrypoint.sh
-rwxr-xr-x 1 root root  8079336 Oct  1 21:56 py-spy
-rwxr-xr-x 1 root root      307 Oct  1 21:56 py.test
-rwxr-xr-x 1 root root      301 Oct  1 21:56 pygmentize
-rwxr-xr-x 1 root root      307 Oct  1 21:56 pytest
-rwxr-xr-x 1 root root      327 Oct  1 21:56 torchfrtrace
-rwxr-xr-x 1 root root      306 Oct  1 21:56 torchrun
-rwxr-xr-x 1 root root 56101408 Sep 29 18:43 uv
### ls /usr/local/libexec
total 36
drwxr-xr-x 1 root root 4096 Oct  4 07:22 .
drwxr-xr-x 1 root root 4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root 1449 Oct  1 23:13 gpu-ballast
-rwxr-xr-x 1 root root 2844 Oct  1 23:13 node-metrics
-rwxr-xr-x 1 root root 1684 Oct  4 07:20 ocb-healthcheck
-rwxr-xr-x 1 root root 1358 Oct  2 19:49 ocb-install-keys
-rwxr-xr-x 1 root root  749 Oct  2 19:19 ocb-keys
-rwxr-xr-x 1 root root 1230 Oct  4 07:20 ocb-taskprolog
### ls /etc/platform
total 28
drwxr-xr-x 1 root root 4096 Oct  4 07:22 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Jun  2 16:40 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  4 07:20 objstore.conf
### ls /root
total 48
dr-xr-x--- 1 root  root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root  root  4096 Oct  4 07:22 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
drwxr-xr-x 3 root  root  4096 Oct  4 07:20 .cache
-rw-r--r-- 1 root  root   100 May 25 20:19 .cshrc
drwx------ 1 root  root  4096 Oct  4 07:22 .ssh
-rw-r--r-- 1 root  root   129 May 25 20:19 .tcshrc
-rw------- 1 root  root   532 Aug  9 21:35 .viminfo
drw------- 3 slurm slurm 4096 Aug  9 21:31 examples
### site configuration files
-- /etc/platform/job.env (119 bytes, 2026-06-02 16:40:00.000000000)
# Site job environm
```

## container `objstore`

```
## whoami: root on objstore
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
/opt/harness/harness/provision.py
/opt/harness/harness/corpus.py
/opt/harness/harness/config.py
/opt/harness/harness/__init__.py
/opt/harness/harness/teacher.py
/opt/harness/harness/store.py
/opt/harness/harness/cluster.py
/opt/harness/harness/verify/report.py
/opt/harness/harness/verify/gpus.py
/opt/harness/harness/verify/policy.py
/opt/harness/harness/verify/evaluate.py
/opt/harness/harness/verify/run.py
/opt/harness/harness/verify/__main__.py
/opt/ocb/ocb/metrics.py
/opt/ocb/ocb/frdump.py
/usr/local/libexec/ocb-hwsetup.sh
### environment variables of all processes (names only, non-standard)
GIT_PAGER
NVIDIA_DRIVER_CAPABILITIES
NVIDIA_VISIBLE_DEVICES
PAGER
SYSTEMD_PAGER
### processes
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -150
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
root     python3 -m harness.objstore
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                        
LISTEN 0      5            0.0.0.0:8000       0.0.0.0:*    users:(("python3",pid=1,fd=3))
LISTEN 0      4096      127.0.0.11:33707      0.0.0.0:*                                  
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 ro,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.2 -> objstore
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.2	objstore
### scheduler: reservations and partitions
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Sun, 04 Oct 2026 07:23:21 GMT
Content-Type: application/xml
Content-Length: 168

### environment of non-job processes not started by a login (names only)
### GPUs: device files here (only the GPU node may have them), site GPU and NCCL config, GPU variables

-- /etc/profile.d/bash_completion.sh (2024-04-30 11:43:58)
# shellcheck shell=sh disable=SC1091,SC2039,SC2166
# Check for interactive bash and that we haven't already been sourced.
if [ "x${BASH_VERSION-}" != x -a "x${PS1-}" != x -a "x${BASH_COMPLETION_VERSINFO-}" = x ]; then

    # Check for recent enough version of bash.
-- /etc/profile.d/colorgrep.csh (2022-05-16 14:43:06)

# color-grep initialization

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) then
-- /etc/profile.d/colorgrep.sh (2022-05-16 14:43:06)
# color-grep initialization

/usr/libexec/grepconf.sh -c || return

alias grep='grep --color=auto' 2>/dev/null
-- /etc/profile.d/colorxzgrep.csh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
alias xzgrep 'xzgrep --color=auto'
alias xzfgrep 'xzfgrep --color=auto'
alias xzegrep 'xzegrep --color=auto'
-- /etc/profile.d/colorxzgrep.sh (2022-06-15 04:55:38)
/usr/libexec/grepconf.sh -c || return
alias xzgrep='xzgrep --color=auto' 2>/dev/null
alias xzegrep='xzegrep --color=auto' 2>/dev/null
alias xzfgrep='xzfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/colorzgrep.csh (2022-10-30 00:14:30)
test -f /usr/libexec/grepconf.sh
if ( $status == 1 ) exit

/usr/libexec/grepconf.sh -c
if ( $status == 1 ) exit
-- /etc/profile.d/colorzgrep.sh (2022-10-30 00:14:30)
[ -f /usr/libexec/grepconf.sh ] || return

/usr/libexec/grepconf.sh -c || return
alias zgrep='zgrep --color=auto' 2>/dev/null
alias zfgrep='zfgrep --color=auto' 2>/dev/null
-- /etc/profile.d/csh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, is sourced from /etc/csh.login
-- /etc/profile.d/debuginfod.csh (2026-01-03 09:13:11)
# $HOME/.login* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/debuginfod.sh (2026-01-03 09:13:11)
# $HOME/.profile* or similar files may first set $DEBUGINFOD_URLS.
# If $DEBUGINFOD_URLS is not set there, we set it from system *.url files.
# $HOME/.*rc or similar files may then amend $DEBUGINFOD_URLS.
# See also [man debuginfod-client-config] for other environment variables
# such as $DEBUGINFOD_MAXSIZE, $DEBUGINFOD_MAXTIME, $DEBUGINFOD_PROGRESS.
-- /etc/profile.d/flatpak.sh (2024-04-17 17:19:24)
if command -v flatpak > /dev/null; then
    # set XDG_DATA_DIRS to include Flatpak installations

    new_dirs=$(
        (
-- /etc/profile.d/gawk.csh (2019-08-28 18:54:14)
alias gawkpath_default 'unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`'

alias gawkpath_prepend 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "\!*"":$AWKPATH"'

alias gawkpath_append 'if (! $?AWKPATH) setenv AWKPATH ""; if ($AWKPATH == "") then; unsetenv AWKPATH; setenv AWKPATH `gawk -v x=AWKPATH "BEGIN {print ENVIRON[x]}"`; endif; setenv AWKPATH "$AWKPATH"":\!*"'
-- /etc/profile.d/gawk.sh (2019-08-28 18:54:14)
gawkpath_default () {
	unset AWKPATH
	export AWKPATH=`gawk 'BEGIN {print ENVIRON["AWKPATH"]}'`
}

-- /etc/profile.d/lang.csh (2020-06-23 06:11:43)
# /etc/profile.d/lang.csh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/lang.sh (2020-06-23 06:11:43)
# /etc/profile.d/lang.sh - exports environment variables, and provides fallback
#                          for CJK languages that can't be displayed in console.
#                          Resets the locale if unavailable.

unset LANG_backup
-- /etc/profile.d/less.csh (2025-11-03 06:42:30)
# less initialization script (csh)

# All less.*sh files should have the same semantics!

# In case you are curious, the test for non-emptiness is not as easy as in
-- /etc/profile.d/less.sh (2025-11-03 06:42:30)
# less initialization script (sh)

# All less.*sh files should have the same semantics!

if [ -z "$LESSOPEN" ] && [ -x /usr/bin/lesspipe.sh ]; then
-- /etc/profile.d/lmod.sh (2026-08-09 21:35:12)
source /usr/local/lmod/lmod/init/bash
export SPACK_ROOT=/usr/local/spack
export MODULEPATH="/opt/spack/modules/linux-rocky9-x86_64/Core:/opt/modulefiles"
source /usr/local/spack/share/spack/setup-env.sh
-- /etc/profile.d/sh.local (2024-04-07 20:15:49)
#Add any required envvar overrides to this file, it is sourced from /etc/profile
-- /etc/profile.d/which2.csh (2025-08-05 18:59:17)
# Initialization script for csh

# alias which 'alias | /usr/bin/which --tty-only --read-alias --show-dot --show-tilde'
-- /etc/profile.d/which2.sh (2025-08-05 18:59:18)
# shellcheck shell=sh
# Initialization script for bash, sh, mksh and ksh

if [ -r /proc/$$/exe ]; then
    SHELLNAME=$(basename $(readlink /proc/$$/exe))
16: CUDA_DEVICE_ORDER=PCI_BUS_ID
16: NVIDIA_DRIVER_CAPABILITIES=compute,utility
16: NVIDIA_VISIBLE_DEVICES=void
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
203: CUDA_DEVICE_ORDER=PCI_BUS_ID
203: NVIDIA_DRIVER_CAPABILITIES=compute,utility
203: NVIDIA_VISIBLE_DEVICES=void
204: CUDA_DEVICE_ORDER=PCI_BUS_ID
204: NVIDIA_DRIVER_CAPABILITIES=compute,utility
204: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 2 munge munge   4096 Feb 16  2026 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 2 slurm slurm   4096 Aug  9 21:46 slurm
### ls /opt
total 24
drwxr-xr-x 1 root root 4096 Oct  4 07:20 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
drwxr-xr-x 1 root root 4096 Oct  4 07:20 harness
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack
### ls /opt/harness
total 48
drwxr-xr-x 1 root root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ..
-rw-r--r-- 1 root root    17 Oct  4 07:20 BUILD
-rw-r--r-- 1 root root 24578 Oct  4 07:20 BUILD.txt
-rw-r--r-- 1 root root    17 Oct  4 07:20 VERSION
drwxr-xr-x 1 root root  4096 Oct  4 07:20 harness
### ls /opt/modulefiles
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
### ls /opt/ocb
total 44
drwxr-xr-x 1 root root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ..
-rw-r--r-- 1 root root    17 Oct  4 07:20 BUILD
-rw-r--r-- 1 root root 24491 Oct  4 07:20 BUILD.txt
-rw-r--r-- 1 root root    17 Oct  4 07:20 VERSION
drwxr-xr-x 1 root root  4096 Oct  4 07:20 ocb
### ls /opt/spack
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  4 07:20 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules
### ls /usr/local/bin
total 64636
drwxr-xr-x 1 root root     4096 Oct  4 07:20 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
-rwxr-xr-x 1 root root      302 Oct  1 21:56 f2py
-rwxr-xr-x 1 root root  1936948 Aug  9 21:33 gosu
-rwxr-xr-x 1 root root      601 Oct  2 19:49 harness-entrypoint.sh
-rwxr-xr-x 1 root root      291 Oct  1 21:56 isympy
-rwxr-xr-x 1 root root      302 Oct  1 21:56 numpy-config
-rwxr-xr-x 1 root root       39 Oct  4 07:20 ocb
-rwxr-xr-x 1 root root     2514 Oct  2 19:49 ocb-entrypoint.sh
-rwxr-xr-x 1 root root  8079336 Oct  1 21:56 py-spy
-rwxr-xr-x 1 root root      307 Oct  1 21:56 py.test
-rwxr-xr-x 1 root root      301 Oct  1 21:56 pygmentize
-rwxr-xr-x 1 root root      307 Oct  1 21:56 pytest
-rwxr-xr-x 1 root root      327 Oct  1 21:56 torchfrtrace
-rwxr-xr-x 1 root root      306 Oct  1 21:56 torchrun
-rwxr-xr-x 1 root root 56101408 Sep 29 18:43 uv
### ls /usr/local/libexec
total 40
drwxr-xr-x 1 root root 4096 Oct  4 07:20 .
drwxr-xr-x 1 root root 4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root 1449 Oct  1 23:13 gpu-ballast
-rwxr-xr-x 1 root root 2844 Oct  1 23:13 node-metrics
-rwxr-xr-x 1 root root 1684 Oct  4 07:20 ocb-healthcheck
-rwxr-xr-x 1 root root 4958 Oct  2 13:12 ocb-hwsetup.sh
-rwxr-xr-x 1 root root 1358 Oct  2 19:49 ocb-install-keys
-rwxr-xr-x 1 root root  749 Oct  2 19:19 ocb-keys
-rwxr-xr-x 1 root root 1230 Oct  4 07:20 ocb-taskprolog
### ls /etc/platform
total 20
drwxr-xr-x 1 root root 4096 Oct  4 07:20 .
drwxr-xr-x 1 root root 4096 Oct  4 07:22 ..
-rw-r--r-- 1 root root   10 Oct  4 07:20 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  4 07:20 objstore.conf
### ls /root
total 44
dr-xr-x--- 1 root  root  4096 Oct  4 07:20 .
drwxr-xr-x 1 root  root  4096 Oct  4 07:22 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
drwxr-xr-x 3 root  root  4096 Oct  4 07:20 .cache
-rw-r--r-- 1 root  root   100 May 25 20:19 .cshrc
drwx------ 1 root  root  4096 Oct  2 19:10 .ssh
-rw-r--r-- 1 root  root   129 May 25 20:19 .tcshrc
-rw------- 1 root  root   532 Aug  9 21:35 .viminfo
drw------- 3 slurm slurm 4096 Aug  9 21:31 examples
### site configuration files
-- /etc/platform/node-metrics.conf (10 bytes
```

## container `keys`

```
Error response from daemon: container 7cab24e409c2940aa4fcfcd9a9ba0295e8af17afc16f3e75389929a3e0e101bd is not running
```

