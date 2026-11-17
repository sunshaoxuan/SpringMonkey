#!/bin/sh
set -eu
# Only the new FRP dashboard TCP listener is restricted. Existing rules stay.
for firewall in iptables ip6tables; do
    command -v "$firewall" >/dev/null
    "$firewall" -C INPUT ! -i lo -p tcp --dport 19119 -m comment --comment hermes-dashboard-loopback -j DROP 2>/dev/null ||
        "$firewall" -I INPUT 1 ! -i lo -p tcp --dport 19119 -m comment --comment hermes-dashboard-loopback -j DROP
done
