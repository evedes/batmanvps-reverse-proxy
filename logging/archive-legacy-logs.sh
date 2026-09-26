#!/bin/sh
# Preserve only Kinfolio's old file logs before the container is replaced.
set -eu
umask 077
archive_dir=
for name in getkinfolio.access.log getkinfolio.error.log getkinfolio-staging.access.log getkinfolio-staging.error.log; do
  if docker exec nginx-reverseproxy test -f "/var/log/nginx/$name" 2>/dev/null; then
    if [ -z "$archive_dir" ]; then
      archive_root="$HOME/.local/state/kinfolio-legacy-proxy-logs"
      mkdir -p "$archive_root"
      chmod 700 "$archive_root"
      archive_dir=$(mktemp -d "$archive_root/snapshot-XXXXXXXX")
    fi
    docker cp "nginx-reverseproxy:/var/log/nginx/$name" "$archive_dir/$name"
    chmod 600 "$archive_dir/$name"
  fi
done
if [ -n "$archive_dir" ]; then
  printf 'Legacy Kinfolio logs preserved with restricted permissions in %s\n' "$archive_dir"
fi
