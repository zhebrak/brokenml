#!/bin/bash
# Egress guard for the net and cheat-net variants (hardening plan 11.1; red-team review 2026-10-05). The workstation of a
# net trial sits on the compose network `egress` (a /28 per task inside 198.18.0.0/15, bench.compose.egress_subnet) and would otherwise
# reach the host, the LAN and a cloud instance's metadata service. These DOCKER-USER rules drop that traffic and let the
# rest out (the model API and install hosts). Run once per host boot as root; `bench run --variant net|cheat-net`
# refuses to start unless the first rule is present (--no-egress-guard overrides, for a host with no such exposure).
set -euo pipefail
SUBNET=${EGRESS_SUBNET:-198.18.0.0/15}
rule() { iptables -C DOCKER-USER "$@" 2>/dev/null || iptables -I DOCKER-USER "$@"; }
rule -s "$SUBNET" -d 169.254.0.0/16 -j DROP      # link-local: cloud metadata and credentials
rule -s "$SUBNET" -d 10.0.0.0/8 -j DROP
rule -s "$SUBNET" -d 172.16.0.0/12 -j DROP        # every other compose network and the bridge gateways
rule -s "$SUBNET" -d 192.168.0.0/16 -j DROP
rule -s "$SUBNET" -d 100.64.0.0/10 -j DROP        # carrier-grade NAT ranges some clouds use for metadata
echo "egress guard in place for $SUBNET:"; iptables -S DOCKER-USER | grep -- "-s ${SUBNET%/*}" || true
