#!/bin/sh
set -eu
case "${RENEWED_LINEAGE:-}" in
  /etc/letsencrypt/live/sm.briconbric.com|/etc/letsencrypt/live/smapp.briconbric.com)
    /usr/sbin/nginx -t
    /bin/systemctl reload nginx
    ;;
esac
