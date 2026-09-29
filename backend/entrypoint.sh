#!/bin/sh
# Make the classic link-local metadata address reachable from this
# container: the compose network maps the metadata service to META_IP, and
# this NAT rule redirects locally generated requests to 169.254.169.254.
META_IP="${META_IP:-172.31.0.10}"
if iptables -t nat -C OUTPUT -d 169.254.169.254/32 -p tcp --dport 80 -j DNAT --to-destination "$META_IP:80" 2>/dev/null; then
    :
else
    iptables -t nat -A OUTPUT -d 169.254.169.254/32 -p tcp --dport 80 -j DNAT --to-destination "$META_IP:80" 2>/dev/null \
        && echo "[entrypoint] metadata alias 169.254.169.254 -> $META_IP installed" \
        || echo "[entrypoint] WARNING: could not install the metadata alias (missing NET_ADMIN?)"
fi
exec "$@"
