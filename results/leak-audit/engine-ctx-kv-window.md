# Leak audit: engine-ctx-kv-window

Run on the agent environment after provisioning. 2026-10-02T06:15:00Z · commit de52cb81fad4+dirty · runtime:dev c9982c1f28b5, harness:dev 29acec6db031, runtime-cuda:dev ?, serve:dev 740005ccc263 · AMD Ryzen 7 8745HS w/ Radeon 780M Graphics (dev-host); task sha256:c66e877accb21d2bd33a525916c1bbfb227b3c5f2ab332a282c80aa3f42161a3.

## container `main`

```
## whoami: root on b3dc2b72480a
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
LISTEN 0      4096      127.0.0.11:39731      0.0.0.0:*          
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /ops ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1 -> localhost
172.19.0.4 -> b3dc2b72480a
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.4	b3dc2b72480a
### scheduler: reservations and partitions
### object store response headers
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
341: CUDA_DEVICE_ORDER=PCI_BUS_ID
341: NVIDIA_DRIVER_CAPABILITIES=compute,utility
341: NVIDIA_VISIBLE_DEVICES=void
544: CUDA_DEVICE_ORDER=PCI_BUS_ID
544: NVIDIA_DRIVER_CAPABILITIES=compute,utility
544: NVIDIA_VISIBLE_DEVICES=void
545: CUDA_DEVICE_ORDER=PCI_BUS_ID
545: NVIDIA_DRIVER_CAPABILITIES=compute,utility
545: NVIDIA_VISIBLE_DEVICES=void
### docker sockets / credentials
### logs
drwxr-xr-x 1 root  root    4096 Aug  9 21:46 .
drwxr-xr-x 1 root  root    4096 May 25 20:18 ..
lrwxrwxrwx 1 root  root      39 Aug  9 21:35 README -> ../../usr/share/doc/systemd/README.logs
drwx------ 1 munge munge   4096 Oct  2 06:15 munge
drwx------ 2 root  root    4096 Aug  9 21:35 private
drwxr-xr-x 1 slurm slurm   4096 Aug  9 21:46 slurm
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/etc/platform:
total 24
drwxr-xr-x 1 root root 4096 Oct  2 06:15 .
drwxr-xr-x 1 root root 4096 Oct  2 06:15 ..
-rw-r--r-- 1 root root  119 Jun  2 16:40 job.env
-rw-r--r-- 1 root root   10 Oct  1 21:56 node-metrics.conf
-rw-r--r-- 1 root root   25 Oct  1 21:56 objstore.conf

/opt:
total 20
drwxr-xr-x 1 root root 4096 Oct  1 21:56 .
drwxr-xr-x 1 root root 4096 Oct  2 06:15 ..
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
drwxr-xr-x 1 root  root  4096 Oct  2 06:15 ..
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
bash: line 10: /proc/23/environ: Permission denied
bash: line 26: /proc/23/environ: Permission denied
sed: -e expression #1, char 16: unterminated `s' command
sed: -e expression #1, char 16: unterminated `s' command
bash: line 30: /proc/23/environ: Permission denied
```

## container `engine`

```
## whoami: root on engine
### files mentioning task/harness terms (outside /ops, /proc, /sys, /usr/lib*, /usr/share, python site-packages)
/usr/local/bin/engine-supervisor
### environment variables of all processes (names only, non-standard)
LLAMA_ARG_HOST
### processes
root     /app/llama-server -m /models/model.gguf --host 0.0.0.0 --port 8080 --metrics --slots --parallel 16 --threads 2 --ctx-size 131072 --batch-size 2048 --ubatch-size 512
root     /bin/bash /usr/local/bin/engine-supervisor
root     head -40
root     sort -u
### listening sockets
### mounts (non-overlay, non-proc; tmpfs only beyond the container defaults)
shm /dev/shm tmpfs rw,nosuid,nodev,noexec,relatime,size=65536k,inode64 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /ops ext4 ro,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /shared ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/resolv.conf ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hostname ext4 rw,relatime 0 0
/dev/mapper/ubuntu--vg-ubuntu--lv /etc/hosts ext4 rw,relatime 0 0
### names: reverse lookups of every interface address, and the hosts file
127.0.0.1	localhost
::1	localhost ip6-localhost ip6-loopback
fe00::	ip6-localnet
ff00::	ip6-mcastprefix
ff02::1	ip6-allnodes
ff02::2	ip6-allrouters
172.19.0.2	engine
### scheduler: reservations and partitions
### object store response headers
### environment of non-job processes not started by a login (names only)
### GPUs: device files here (only the GPU node may have them), site GPU and NCCL config, GPU variables

-- /etc/profile.d/01-locale-fix.sh (2024-04-22 13:04:27)
# Make sure the locale variables are set to valid values.
eval $(/usr/bin/locale-check C.UTF-8)
### docker sockets / credentials
### logs
drwxr-xr-x 1 root root              4096 Oct  1 04:38 .
drwxr-xr-x 1 root root              4096 Sep 11 02:10 ..
lrwxrwxrwx 1 root root                39 Oct  1 04:37 README -> ../../usr/share/doc/systemd/README.logs
-rw-r--r-- 1 root root              5796 Oct  1 04:38 alternatives.log
drwxr-xr-x 1 root root              4096 Oct  1 04:37 apt
-rw-r--r-- 1 root root             61229 Sep 11 02:03 bootstrap.log
-rw-r--r-- 1 root root            344151 Oct  1 04:38 dpkg.log
-rw-r--r-- 1 root root                 0 Sep 11 02:03 faillog
-rw-r--r-- 1 root root               605 Oct  1 04:38 fontconfig.log
drwxr-sr-x 2 root systemd-journal   4096 Oct  1 04:37 journal
### /opt /usr/local/bin /usr/local/libexec /etc/platform /root
/opt:
total 8
drwxr-xr-x 2 root root 4096 Sep 11 02:03 .
drwxr-xr-x 1 root root 4096 Oct  2 06:15 ..

/root:
total 20
drwx------ 1 root root 4096 Oct  1 04:37 .
drwxr-xr-x 1 root root 4096 Oct  2 06:15 ..
-rw-r--r-- 1 root root 3106 Apr 22  2024 .bashrc
-rw-r--r-- 1 root root  161 Apr 22  2024 .profile
drwx------ 2 root root 4096 Oct  1 04:37 .ssh

/usr/local/bin:
total 12
drwxr-xr-x 1 root root 4096 Oct  1 18:44 .
drwxr-xr-x 1 root root 4096 Sep 11 02:03 ..
-rwxr-xr-x 1 root root 3714 Oct  1 18:32 engine-supervisor
bash: line 10: /proc/10944/environ: No such file or directory
sed: -e expression #1, char 18: unterminated `s' command
sed: -e expression #1, char 18: unterminated `s' command
```

## container `provision`

```
Error response from daemon: container 424157504d71c188cd3526c75c7cd810ab752379906dd67b619e4bbc7437ccc0 is not running
```

