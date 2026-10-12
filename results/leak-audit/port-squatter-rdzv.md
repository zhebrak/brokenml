# Leak audit: port-squatter-rdzv

Run on the agent environment after provisioning. 2026-10-02T06:24:08Z · commit de52cb81fad4+dirty · runtime:dev c9982c1f28b5, harness:dev 29acec6db031, runtime-cuda:dev ?, serve:dev 740005ccc263 · AMD Ryzen 7 8745HS w/ Radeon 780M Graphics (dev-host); task sha256:dc1351b298d2e03e2d060b4bad82b687f535a6d49fddced328671902fa7c6b93.

## container `main`

```
## whoami: root on 22d2292af5fa
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
### environment variables of all processes (names only, non-standard)
GIT_PAGER
NVIDIA_DRIVER_CAPABILITIES
NVIDIA_VISIBLE_DEVICES
PAGER
SYSTEMD_PAGER
### processes
munge    /usr/sbin/munged
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -40
root     /usr/bin/coreutils --coreutils-prog-shebang=sleep /usr/bin/sleep infinity
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess
LISTEN 0      4096      127.0.0.11:34821      0.0.0.0:*          
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /ops ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
tmpfs /shared/ckpt tmpfs rw,relatime,size=524288k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.6 -> 22d2292af5fa
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.6	22d2292af5fa
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:25:59 GMT
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
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
23: CUDA_DEVICE_ORDER=PCI_BUS_ID
23: NVIDIA_DRIVER_CAPABILITIES=compute,utility
23: NVIDIA_VISIBLE_DEVICES=void
255: CUDA_DEVICE_ORDER=PCI_BUS_ID
255: NVIDIA_DRIVER_CAPABILITIES=compute,utility
255: NVIDIA_VISIBLE_DEVICES=void
457: CUDA_DEVICE_ORDER=PCI_BUS_ID
457: NVIDIA_DRIVER_CAPABILITIES=compute,utility
457: NVIDIA_VISIBLE_DEVICES=void
458: CUDA_DEVICE_ORDER=PCI_BUS_ID
458: NVIDIA_DRIVER_CAPABILITIES=compute,utility
458: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:24 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Aug  9 21:46 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 24
drwxr-xr-x 1 root root 4096 Oct  2 06:24 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Oct  1 21:56 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 20
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack

/opt/modulefiles:
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..

/opt/ocb:
total 16
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..
-rw-r--r-- 1 root root   17 Oct  1 21:56 VERSION
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb

/opt/spack:
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules

/root:
total 40
dr-xr-x--- 1 root  root  4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root  4096 Oct  2 06:24 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
-rw-r--r-- 1 root  root   100 May 25 20:19 .cshrc
drwx------ 1 root  root  4096 Oct  1 21:56 .ssh
-rw-r--r-- 1 root  root   129 May 25 20:19 .tcshrc
-rw------- 1 root  root   532 Aug  9 21:35 .viminfo
drw------- 3 slurm slurm 4096 Aug  9 21:31 examples

/usr/local/bin:
total 64636
drwxr-xr-x 1 root root     4096 Oct  1 21:56 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
-rwxr-xr-x 1 root root      302 Oct  1 21:56 f2py
-rwxr-xr-x 1 root root  1936948 Aug  9 21:33 gosu
-rwxr-xr-x 1 root root      291 Oct  1 21:56 isympy
-rwxr-xr-x 1 root root      302 Oct  1 21:56 numpy-config
-rwxr-xr-x 1 root root       39 Oct  1 21:56 ocb
-rwxr-xr-x 1 root root     2181 Oct  1 21:02 ocb-entrypoint.sh
-rwxr-xr-x 1 root root  8079336 Oct  1 21:56 py-spy
sed: -e expression #1, char 16: unterminated `s' command
sed: -e expression #1, char 16: unterminated `s' command
```

## container `slurmctld`

```
## whoami: root on slurmctld
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
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
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -40
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
root     sshd: /usr/sbin/sshd [listener] 0 of 10-100 startups
slurm    /usr/sbin/slurmctld -D -i
slurm    slurmctld: slurmscriptd
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                      
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=36,fd=7))
LISTEN 0      4096         0.0.0.0:6817       0.0.0.0:*                                
LISTEN 0      4096      127.0.0.11:43387      0.0.0.0:*                                
LISTEN 0      128             [::]:22            [::]:*    users:(("sshd",pid=36,fd=8))
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.2 -> slurmctld
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.2	slurmctld
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:26:00 GMT
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
187: CUDA_DEVICE_ORDER=PCI_BUS_ID
187: NVIDIA_DRIVER_CAPABILITIES=compute,utility
187: NVIDIA_VISIBLE_DEVICES=void
411: CUDA_DEVICE_ORDER=PCI_BUS_ID
411: NVIDIA_DRIVER_CAPABILITIES=compute,utility
411: NVIDIA_VISIBLE_DEVICES=void
412: CUDA_DEVICE_ORDER=PCI_BUS_ID
412: NVIDIA_DRIVER_CAPABILITIES=compute,utility
412: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:24 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Oct  2 06:24 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 24
drwxr-xr-x 1 root root 4096 Oct  2 06:24 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Oct  1 21:56 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 20
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack

/opt/modulefiles:
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..

/opt/ocb:
total 16
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..
-rw-r--r-- 1 root root   17 Oct  1 21:56 VERSION
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb

/opt/spack:
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules

/root:
total 40
dr-xr-x--- 1 root  root  4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root  4096 Oct  2 06:24 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
-rw-r--r-- 1 root  root   100 May 25 20:19 .cshrc
drwx------ 1 root  root  4096 Oct  1 21:56 .ssh
-rw-r--r-- 1 root  root   129 May 25 20:19 .tcshrc
-rw------- 1 root  root   532 Aug  9 21:35 .viminfo
drw------- 3 slurm slurm 4096 Aug  9 21:31 examples

/usr/local/bin:
total 64636
drwxr-xr-x 1 root root     4096 Oct  1 21:56 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
-rwxr-xr-x 1 root root      302 Oct  1 21:56 f2py
-rwxr-xr-x 1 root root  1936948 Aug  9 21:33 gosu
-rwxr-xr-x 1 root root      291 Oct  1 21:56 isympy
-rwxr-xr-x 1 root root      302 Oct  1 21:56 numpy-config
-rwxr-xr-x 1 root root       39 Oct  1 21:56 ocb
-rwxr-xr-x 1 root root     2181 Oct  1 21:02 ocb-entrypoint.sh
-rwxr-xr-x 1 root root  8079336 Oct  1 21:56 py-spy
bash: line 10: /proc/1/environ: Permission denied
bash: line 10: /proc/17/environ: Permission denied
bash: line 10: /proc/77/environ: Permission denied
bash: line 26: /proc/1/environ: Permission denied
bash: line 26: /proc/17/environ: Permission denied
sed: -e expression #1, char 16: unterminated `s' command
sed: -e expression #1, char 16: unterminated `s' command
bash: line 26: /proc/77/environ: Permission denied
bash: line 30: /proc/1/environ: Permission denied
bash: line 30: /proc/17/environ: Permission denied
bash: line 30: /proc/77/environ: Permission denied
```

## container `provision`

```
Error response from daemon: container 3baa48c8f67564a4777a64e674fd42ce2766782b2bd95b9560cc53e213c14b0a is not running
```

## container `c1`

```
## whoami: root on c1
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
### environment variables of all processes (names only, non-standard)

/sshd [listener] 0 of 10-100 startups
ENVIRONMENT
GIT_PAGER
HYDRA_BOOTSTRAP
HYDRA_LAUNCHER_EXTRA_ARGS
I_MPI_HYDRA_BOOTSTRAP
I_MPI_HYDRA_BOOTSTRAP_EXEC_EXTRA_ARGS
LOG_LEVEL
METRICS_PUSH_URL
NODE_RACK
NVIDIA_DRIVER_CAPABILITIES
NVIDIA_VISIBLE_DEVICES
OCB_METRICS_PORT
OMPI_MCA_plm_slurm_args
PAGER
PRTE_MCA_plm_slurm_args
PYTHONHASHSEED
REPORT_THROUGHPUT
SCRATCH_DIR
SLURMD_DEBUG
SRUN_DEBUG
SYSTEMD_PAGER
TMPDIR
TZ
d
n
### processes
metrics  python3 /usr/local/libexec/node-metrics
munge    /usr/sbin/munged
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -40
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
root     /usr/sbin/slurmd -D -N c1
root     slurmstepd: [1.0]
root     slurmstepd: [1.batch]
root     sshd: /usr/sbin/sshd [listener] 0 of 10-100 startups
svc-tra+ /bin/bash /var/spool/slurm/job00001/slurm_script
svc-tra+ /usr/bin/python3.12 /usr/local/bin/torchrun --nnodes=2 --nproc-per-node=2 --rdzv-backend=c10d --rdzv-endpoint=c1:29500 --rdzv-id=1 /ops/src/train.py --config /ops/jobs/train/train.yaml
svc-tra+ srun torchrun --nnodes=2 --nproc-per-node=2 --rdzv-backend=c10d --rdzv-endpoint=c1:29500 --rdzv-id=1 /ops/src/train.py --config /ops/jobs/train/train.yaml
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                                             
LISTEN 0      128          0.0.0.0:29500      0.0.0.0:*    users:(("python3",pid=42,fd=3))                    
LISTEN 0      4096         0.0.0.0:43899      0.0.0.0:*    users:(("srun",pid=106,fd=9),("srun",pid=101,fd=9))
LISTEN 0      4096         0.0.0.0:43339      0.0.0.0:*    users:(("srun",pid=101,fd=14))                     
LISTEN 0      4096      127.0.0.11:37053      0.0.0.0:*                                                       
LISTEN 0      4096         0.0.0.0:6818       0.0.0.0:*    users:(("slurmd",pid=1,fd=10))                     
LISTEN 0      4096         0.0.0.0:33427      0.0.0.0:*    users:(("srun",pid=101,fd=10))                     
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=43,fd=7))                       
LISTEN 0      128             [::]:22            [::]:*    users:(("sshd",pid=43,fd=8))                       
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /ops ext4 ro,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
tmpfs /shared/ckpt tmpfs rw,relatime,size=524288k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.7 -> c1
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.7	c1
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:26:00 GMT
Content-Type: application/xml
Content-Length: 168

### environment of non-job processes not started by a login (names only)
17 /usr/sbin/munged : OCB_METRICS_PORT
458 /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/so: OCB_METRICS_PORT
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
17: CUDA_DEVICE_ORDER=PCI_BUS_ID
17: NVIDIA_DRIVER_CAPABILITIES=compute,utility
17: NVIDIA_VISIBLE_DEVICES=void
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
385: CUDA_DEVICE_ORDER=PCI_BUS_ID
385: NVIDIA_DRIVER_CAPABILITIES=compute,utility
385: NVIDIA_VISIBLE_DEVICES=void
654: CUDA_DEVICE_ORDER=PCI_BUS_ID
654: NVIDIA_DRIVER_CAPABILITIES=compute,utility
654: NVIDIA_VISIBLE_DEVICES=void
655: CUDA_DEVICE_ORDER=PCI_BUS_ID
655: NVIDIA_DRIVER_CAPABILITIES=compute,utility
655: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:24 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Oct  2 06:24 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 28
drwxr-xr-x 1 root root 4096 Oct  2 06:24 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   11 Oct  2 06:24 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 20
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack

/opt/modulefiles:
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..

/opt/ocb:
total 16
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..
-rw-r--r-- 1 root root   17 Oct  1 21:56 VERSION
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb

/opt/spack:
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules

/root:
total 40
dr-xr-x--- 1 root  root  4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root  4096 Oct  2 06:24 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
-rw-r--r-- 1 root  root   100 May 25 20:19 .cshrc
drwx------ 1 root  root  4096 Oct  1 21:56 .ssh
-rw-r--r-- 1 root  root   129 May 25 20:19 .tcshrc
-rw------- 1 root  root   532 Aug  9 21:35 .viminfo
drw------- 3 slurm slurm 4096 Aug  9 21:31 examples

/usr/local/bin:
total 64636
drwxr-xr-x 1 root root     4096 Oct  1 21:56 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
-rwxr-xr-x 1 root root      302 Oct  1 21:56 f2py
-rwxr-xr-x 1 root root  193694
```

## container `c2`

```
## whoami: root on c2
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
### environment variables of all processes (names only, non-standard)

/sshd [listener] 0 of 10-100 startups
ENVIRONMENT
GIT_PAGER
HYDRA_BOOTSTRAP
HYDRA_LAUNCHER_EXTRA_ARGS
I_MPI_HYDRA_BOOTSTRAP
I_MPI_HYDRA_BOOTSTRAP_EXEC_EXTRA_ARGS
LOG_LEVEL
METRICS_PUSH_URL
NODE_RACK
NVIDIA_DRIVER_CAPABILITIES
NVIDIA_VISIBLE_DEVICES
OCB_METRICS_PORT
OMPI_MCA_plm_slurm_args
PAGER
PRTE_MCA_plm_slurm_args
PYTHONHASHSEED
REPORT_THROUGHPUT
SCRATCH_DIR
SLURMD_DEBUG
SRUN_DEBUG
SYSTEMD_PAGER
TMPDIR
TZ
d
n
### processes
metrics  python3 /usr/local/libexec/node-metrics
munge    /usr/sbin/munged
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -40
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
root     /usr/sbin/slurmd -D -N c2
root     slurmstepd: [1.0]
root     sshd: /usr/sbin/sshd [listener] 0 of 10-100 startups
svc-tra+ /usr/bin/python3.12 /usr/local/bin/torchrun --nnodes=2 --nproc-per-node=2 --rdzv-backend=c10d --rdzv-endpoint=c1:29500 --rdzv-id=1 /ops/src/train.py --config /ops/jobs/train/train.yaml
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                         
LISTEN 0      128          0.0.0.0:29500      0.0.0.0:*    users:(("python3",pid=42,fd=3))
LISTEN 0      4096      127.0.0.11:42161      0.0.0.0:*                                   
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=43,fd=7))   
LISTEN 0      4096         0.0.0.0:6818       0.0.0.0:*    users:(("slurmd",pid=1,fd=10)) 
LISTEN 0      128             [::]:22            [::]:*    users:(("sshd",pid=43,fd=8))   
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /ops ext4 ro,relatime 0 0
tmpfs /shared/ckpt tmpfs rw,relatime,size=524288k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.3 -> c2
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.3	c2
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:26:01 GMT
Content-Type: application/xml
Content-Length: 168

### environment of non-job processes not started by a login (names only)
17 /usr/sbin/munged : OCB_METRICS_PORT
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
17: CUDA_DEVICE_ORDER=PCI_BUS_ID
17: NVIDIA_DRIVER_CAPABILITIES=compute,utility
17: NVIDIA_VISIBLE_DEVICES=void
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
353: CUDA_DEVICE_ORDER=PCI_BUS_ID
353: NVIDIA_DRIVER_CAPABILITIES=compute,utility
353: NVIDIA_VISIBLE_DEVICES=void
592: CUDA_DEVICE_ORDER=PCI_BUS_ID
592: NVIDIA_DRIVER_CAPABILITIES=compute,utility
592: NVIDIA_VISIBLE_DEVICES=void
593: CUDA_DEVICE_ORDER=PCI_BUS_ID
593: NVIDIA_DRIVER_CAPABILITIES=compute,utility
593: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:24 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Oct  2 06:24 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 28
drwxr-xr-x 1 root root 4096 Oct  2 06:24 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   11 Oct  2 06:24 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 20
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack

/opt/modulefiles:
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..

/opt/ocb:
total 16
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..
-rw-r--r-- 1 root root   17 Oct  1 21:56 VERSION
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb

/opt/spack:
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules

/root:
total 40
dr-xr-x--- 1 root  root  4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root  4096 Oct  2 06:24 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
-rw-r--r-- 1 root  root   100 May 25 20:19 .cshrc
drwx------ 1 root  root  4096 Oct  1 21:56 .ssh
-rw-r--r-- 1 root  root   129 May 25 20:19 .tcshrc
-rw------- 1 root  root   532 Aug  9 21:35 .viminfo
drw------- 3 slurm slurm 4096 Aug  9 21:31 examples

/usr/local/bin:
total 64636
drwxr-xr-x 1 root root     4096 Oct  1 21:56 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
-rwxr-xr-x 1 root root      302 Oct  1 21:56 f2py
-rwxr-xr-x 1 root root  1936948 Aug  9 21:33 gosu
-rwxr-xr-x 1 root root      291 Oct  1 21:56 isympy
-rwxr-xr-x 1 root root      302 Oct  1 21:56 numpy-config
-rwxr-xr-x 1 root root       39 Oct  1 21:56 ocb
-rwxr-xr-x 1 root root     2181 Oct  1 21:02 ocb-entrypoint.sh
-rwxr-xr-x 1 root root  8079336 Oct  1 21:56 py-spy
sed: -e expression #1, char 16: unterminated `s' command
sed: -e expression #1, char 16: unterminated `s' command
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
/usr/local/libexec/ocb-hwsetup.sh
### environment variables of all processes (names only, non-standard)
GIT_PAGER
NVIDIA_DRIVER_CAPABILITIES
NVIDIA_VISIBLE_DEVICES
PAGER
SYSTEMD_PAGER
### processes
munge    /usr/sbin/munged
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -40
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
root     python3 -m harness.objstore
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                        
LISTEN 0      5            0.0.0.0:8000       0.0.0.0:*    users:(("python3",pid=1,fd=3))
LISTEN 0      4096      127.0.0.11:33175      0.0.0.0:*                                  
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 ro,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.4 -> objstore
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.4	objstore
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:26:01 GMT
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
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
219: CUDA_DEVICE_ORDER=PCI_BUS_ID
219: NVIDIA_DRIVER_CAPABILITIES=compute,utility
219: NVIDIA_VISIBLE_DEVICES=void
220: CUDA_DEVICE_ORDER=PCI_BUS_ID
220: NVIDIA_DRIVER_CAPABILITIES=compute,utility
220: NVIDIA_VISIBLE_DEVICES=void
26: CUDA_DEVICE_ORDER=PCI_BUS_ID
26: NVIDIA_DRIVER_CAPABILITIES=compute,utility
26: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:24 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 2 slurm slurm   4096 Aug  9 21:46 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 16
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
-rw-r--r-- 1 root root   10 Oct  1 21:56 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 24
drwxr-xr-x 1 root root 4096 Oct  1 21:57 .
drwxr-xr-x 1 root root 4096 Oct  2 06:24 ..
drwxr-xr-x 1 root root 4096 Oct  1 21:57 harness
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modulefiles
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb
drwxr-xr-x 3 root root 4096 Aug  9 21:35 spack

/opt/harness:
total 16
drwxr-xr-x 1 root root 4096 Oct  1 21:57 .
drwxr-xr-x 1 root root 4096 Oct  1 21:57 ..
-rw-r--r-- 1 root root   17 Oct  1 21:57 VERSION
drwxr-xr-x 1 root root 4096 Oct  1 21:57 harness

/opt/modulefiles:
total 8
drwxr-xr-x 2 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:57 ..

/opt/ocb:
total 16
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  1 21:57 ..
-rw-r--r-- 1 root root   17 Oct  1 21:56 VERSION
drwxr-xr-x 1 root root 4096 Oct  1 21:56 ocb

/opt/spack:
total 12
drwxr-xr-x 3 root root 4096 Aug  9 21:35 .
drwxr-xr-x 1 root root 4096 Oct  1 21:57 ..
drwxr-xr-x 2 root root 4096 Aug  9 21:35 modules

/root:
total 40
dr-xr-x--- 1 root  root  4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root  4096 Oct  2 06:24 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
-rw-r--r-- 1 root  root   100 May 25 20:19 .cshrc
drwx------ 1 root  root  4096 Oct  1 21:56 .ssh
-rw-r--r-- 1 root  root   129 May 25 20:19 .tcshrc
-rw------- 1 root  root   532 Aug  9 21:35 .viminfo
drw------- 3 slurm slurm 4096 Aug  9 21:31 examples

/usr/local/bin:
total 64636
drwxr-xr-x 1 root root     4096 Oct  1 21:57 .
drwxr-xr-x 1 root root     4096 Aug  9 21:35 ..
-rwxr-xr-x 1 root root      303 Oct  1 21:56 asciinema
-rwxr-xr-x 1 root root     6995 Aug  9 21:31 docker-entrypoint.sh
bash: line 10: /proc/15/environ: Permission denied
bash: line 26: /proc/15/environ: Permission denied
sed: -e expression #1, char 15: unterminated `s' command
sed: -e expression #1, char 15: unterminated `s' command
bash: line 30: /proc/15/environ: Permission denied
```

