# Leak audit: wrong-nic-one-node

Run on the agent environment after provisioning. 2026-10-02T06:26:12Z · commit de52cb81fad4+dirty · runtime:dev c9982c1f28b5, harness:dev 29acec6db031, runtime-cuda:dev ?, serve:dev 740005ccc263 · AMD Ryzen 7 8745HS w/ Radeon 780M Graphics (dev-host); task sha256:6dc7094b39319aa8701c5803680e14ca930ba74822740316ff2a34db6769602c.

## container `main`

```
## whoami: root on 5165aad12980
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
LISTEN 0      4096      127.0.0.11:46481      0.0.0.0:*          
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
172.20.0.5 -> 5165aad12980
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.20.0.5	5165aad12980
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:31:28 GMT
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
17: CUDA_DEVICE_ORDER=PCI_BUS_ID
17: NVIDIA_DRIVER_CAPABILITIES=compute,utility
17: NVIDIA_VISIBLE_DEVICES=void
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
658: CUDA_DEVICE_ORDER=PCI_BUS_ID
658: NVIDIA_DRIVER_CAPABILITIES=compute,utility
658: NVIDIA_VISIBLE_DEVICES=void
851: CUDA_DEVICE_ORDER=PCI_BUS_ID
851: NVIDIA_DRIVER_CAPABILITIES=compute,utility
851: NVIDIA_VISIBLE_DEVICES=void
852: CUDA_DEVICE_ORDER=PCI_BUS_ID
852: NVIDIA_DRIVER_CAPABILITIES=compute,utility
852: NVIDIA_VISIBLE_DEVICES=void
853: CUDA_DEVICE_ORDER=PCI_BUS_ID
853: NVIDIA_DRIVER_CAPABILITIES=compute,utility
853: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:26 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Aug  9 21:46 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 24
drwxr-xr-x 1 root root 4096 Oct  2 06:26 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Oct  1 21:56 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 20
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
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
drwxr-xr-x 1 root  root  4096 Oct  2 06:26 ..
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
LISTEN 0      4096         0.0.0.0:6817       0.0.0.0:*                                
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=36,fd=7))
LISTEN 0      4096      127.0.0.11:40187      0.0.0.0:*                                
LISTEN 0      128             [::]:22            [::]:*    users:(("sshd",pid=36,fd=8))
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.20.0.2 -> slurmctld
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.20.0.2	slurmctld
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:31:29 GMT
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
325: CUDA_DEVICE_ORDER=PCI_BUS_ID
325: NVIDIA_DRIVER_CAPABILITIES=compute,utility
325: NVIDIA_VISIBLE_DEVICES=void
559: CUDA_DEVICE_ORDER=PCI_BUS_ID
559: NVIDIA_DRIVER_CAPABILITIES=compute,utility
559: NVIDIA_VISIBLE_DEVICES=void
560: CUDA_DEVICE_ORDER=PCI_BUS_ID
560: NVIDIA_DRIVER_CAPABILITIES=compute,utility
560: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:26 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Oct  2 06:26 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 24
drwxr-xr-x 1 root root 4096 Oct  2 06:26 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Oct  1 21:56 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 20
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
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
drwxr-xr-x 1 root  root  4096 Oct  2 06:26 ..
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
Error response from daemon: container 79935145bc9a6f0e58fb3eb6551ebdab038e58ade778dee10447cb67c358386b is not running
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
svc-tra+ /usr/bin/python3.12 -u /ops/src/train.py --config /ops/jobs/train/train.yaml
svc-tra+ /usr/bin/python3.12 /usr/local/bin/torchrun --nnodes=2 --nproc-per-node=2 --rdzv-backend=c10d --rdzv-endpoint=c1:29500 --rdzv-id=1 /ops/src/train.py --config /ops/jobs/train/train.yaml
svc-tra+ srun torchrun --nnodes=2 --nproc-per-node=2 --rdzv-backend=c10d --rdzv-endpoint=c1:29500 --rdzv-id=1 /ops/src/train.py --config /ops/jobs/train/train.yaml
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                                             
LISTEN 0      128          0.0.0.0:9100       0.0.0.0:*    users:(("python3",pid=42,fd=3))                    
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=43,fd=7))                       
LISTEN 0      4096      127.0.0.11:36887      0.0.0.0:*                                                       
LISTEN 0      4096         0.0.0.0:36873      0.0.0.0:*    users:(("srun",pid=101,fd=14))                     
LISTEN 0      4096         0.0.0.0:37553      0.0.0.0:*    users:(("srun",pid=101,fd=10))                     
LISTEN 0      4096         0.0.0.0:38549      0.0.0.0:*    users:(("srun",pid=106,fd=9),("srun",pid=101,fd=9))
LISTEN 0      4096         0.0.0.0:6818       0.0.0.0:*    users:(("slurmd",pid=1,fd=10))                     
LISTEN 0      4096      172.19.0.2:45757      0.0.0.0:*    users:(("python3.12",pid=132,fd=7))                
LISTEN 0      4096      172.19.0.2:46825      0.0.0.0:*    users:(("python3.12",pid=133,fd=7))                
LISTEN 0      4096               *:44565            *:*    users:(("pt_elastic",pid=121,fd=19))               
LISTEN 0      4096               *:29500            *:*    users:(("pt_elastic",pid=121,fd=10))               
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
172.20.0.7 -> c1
172.19.0.2 -> c1
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.20.0.7	c1
172.19.0.2	c1
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:31:29 GMT
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
17: CUDA_DEVICE_ORDER=PCI_BUS_ID
17: NVIDIA_DRIVER_CAPABILITIES=compute,utility
17: NVIDIA_VISIBLE_DEVICES=void
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
629: CUDA_DEVICE_ORDER=PCI_BUS_ID
629: NVIDIA_DRIVER_CAPABILITIES=compute,utility
629: NVIDIA_VISIBLE_DEVICES=void
897: CUDA_DEVICE_ORDER=PCI_BUS_ID
897: NVIDIA_DRIVER_CAPABILITIES=compute,utility
897: NVIDIA_VISIBLE_DEVICES=void
898: CUDA_DEVICE_ORDER=PCI_BUS_ID
898: NVIDIA_DRIVER_CAPABILITIES=compute,utility
898: NVIDIA_VISIBLE_DEVICES=void
899: CUDA_DEVICE_ORDER=PCI_BUS_ID
899: NVIDIA_DRIVER_CAPABILITIES=compute,utility
899: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:26 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Oct  2 06:26 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 24
drwxr-xr-x 1 root root 4096 Oct  2 06:26 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Oct  1 21:56 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 20
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
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
drwxr-xr-x 1 root  root  4096 Oct  2 06:26 ..
-rw-r--r-- 1 root  root    18 May 25 20:19 .bash_logout
-rw-r--r-- 1 root  root   141 May 25 20:19 .bash_profile
-rw-r--r-- 1 root  root   429 May 25 20:19 .bashrc
-rw-r--r-- 1 root  root   100 May 25 20:1
```

## container `c2`

```
## whoami: root on c2
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
metrics  python3 /usr/local/libexec/node-metrics
munge    /usr/sbin/munged
root     /usr/bin/coreutils --coreutils-prog-shebang=cut /usr/bin/cut -c1-200
root     /usr/bin/coreutils --coreutils-prog-shebang=head /usr/bin/head -40
root     /usr/bin/coreutils --coreutils-prog-shebang=sort /usr/bin/sort -u
root     /usr/sbin/slurmd -D -N c2
root     [slurmstepd] <defunct>
root     sshd: /usr/sbin/sshd [listener] 0 of 10-100 startups
### listening sockets
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                         
LISTEN 0      4096      127.0.0.11:34793      0.0.0.0:*                                   
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=42,fd=7))   
LISTEN 0      4096         0.0.0.0:6818       0.0.0.0:*    users:(("slurmd",pid=1,fd=10)) 
LISTEN 0      128          0.0.0.0:9100       0.0.0.0:*    users:(("python3",pid=41,fd=3))
LISTEN 0      128             [::]:22            [::]:*    users:(("sshd",pid=42,fd=8))   
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
172.20.0.3 -> c2
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.20.0.3	c2
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:31:30 GMT
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
17: CUDA_DEVICE_ORDER=PCI_BUS_ID
17: NVIDIA_DRIVER_CAPABILITIES=compute,utility
17: NVIDIA_VISIBLE_DEVICES=void
1: CUDA_DEVICE_ORDER=PCI_BUS_ID
1: NVIDIA_DRIVER_CAPABILITIES=compute,utility
1: NVIDIA_VISIBLE_DEVICES=void
594: CUDA_DEVICE_ORDER=PCI_BUS_ID
594: NVIDIA_DRIVER_CAPABILITIES=compute,utility
594: NVIDIA_VISIBLE_DEVICES=void
830: CUDA_DEVICE_ORDER=PCI_BUS_ID
830: NVIDIA_DRIVER_CAPABILITIES=compute,utility
830: NVIDIA_VISIBLE_DEVICES=void
831: CUDA_DEVICE_ORDER=PCI_BUS_ID
831: NVIDIA_DRIVER_CAPABILITIES=compute,utility
831: NVIDIA_VISIBLE_DEVICES=void
832: CUDA_DEVICE_ORDER=PCI_BUS_ID
832: NVIDIA_DRIVER_CAPABILITIES=compute,utility
832: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:26 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Oct  2 06:26 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 24
drwxr-xr-x 1 root root 4096 Oct  2 06:26 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Oct  1 21:56 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 20
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
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
drwxr-xr-x 1 root  root  4096 Oct  2 06:26 ..
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
bash: line 10: /proc/81/environ: No such process
sed: -e expression #1, char 16: unterminated `s' command
sed: -e expression #1, char 16: unterminated `s' command
bash: line 26: /proc/81/environ: No such process
bash: line 30: /proc/81/environ: No such process
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
LISTEN 0      4096      127.0.0.11:45841      0.0.0.0:*                                  
LISTEN 0      5            0.0.0.0:8000       0.0.0.0:*    users:(("python3",pid=1,fd=3))
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 ro,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.20.0.4 -> objstore
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.20.0.4	objstore
### scheduler: reservations and partitions
No reservations in the system
PartitionName=main
   MaxNodes=UNLIMITED MaxTime=00:15:00 MinNodes=0 LLN=NO MaxCPUsPerNode=UNLIMITED MaxCPUsPerSocket=UNLIMITED
   State=UP TotalCPUs=4 TotalNodes=2 SelectTypeParameters=NONE
### object store response headers
HTTP/1.1 501 Not Implemented
Server: objstore 
Date: Fri, 02 Oct 2026 06:31:30 GMT
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
229: CUDA_DEVICE_ORDER=PCI_BUS_ID
229: NVIDIA_DRIVER_CAPABILITIES=compute,utility
229: NVIDIA_VISIBLE_DEVICES=void
230: CUDA_DEVICE_ORDER=PCI_BUS_ID
230: NVIDIA_DRIVER_CAPABILITIES=compute,utility
230: NVIDIA_VISIBLE_DEVICES=void
231: CUDA_DEVICE_ORDER=PCI_BUS_ID
231: NVIDIA_DRIVER_CAPABILITIES=compute,utility
231: NVIDIA_VISIBLE_DEVICES=void
26: CUDA_DEVICE_ORDER=PCI_BUS_ID
26: NVIDIA_DRIVER_CAPABILITIES=compute,utility
26: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:26 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 2 slurm slurm   4096 Aug  9 21:46 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 16
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
-rw-r--r-- 1 root root   10 Oct  1 21:56 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 24
drwxr-xr-x 1 root root 4096 Oct  1 21:57 .
drwxr-xr-x 1 root root 4096 Oct  2 06:26 ..
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
drwxr-xr-x 1 root  root  4096 Oct  2 06:26 ..
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

