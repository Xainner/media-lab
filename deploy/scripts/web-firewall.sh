#!/usr/bin/env bash
# Dedicated INPUT rule only; no global UFW enable/prune or changes to other ports.
set -euo pipefail
# MEDIA_LAB_PROXY_IP (the reverse proxy) and MEDIA_LAB_PORT come from /etc/media-lab/media-lab.env.
CONF="${MEDIA_LAB_CONF:-/etc/media-lab/media-lab.env}"
# shellcheck source=/dev/null
[[ -f $CONF ]] && . "$CONF"
PROXY="${MEDIA_LAB_PROXY_IP:?set MEDIA_LAB_PROXY_IP in $CONF}"
RULE=(-p tcp --dport "${MEDIA_LAB_PORT:-8390}" '!' -s "$PROXY" '!' -i lo -m comment --comment media-lab-web-proxy-only -j REJECT --reject-with tcp-reset)
case "${1:-status}" in
  apply) iptables -C INPUT "${RULE[@]}" 2>/dev/null || iptables -I INPUT 1 "${RULE[@]}" ;;
  status) iptables -C INPUT "${RULE[@]}" ;;
  remove) while iptables -C INPUT "${RULE[@]}" 2>/dev/null; do iptables -D INPUT "${RULE[@]}"; done ;;
  *) exit 2 ;;
esac
