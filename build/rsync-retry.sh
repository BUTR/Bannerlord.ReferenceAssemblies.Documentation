#!/usr/bin/env bash
# rsync, retried while the deploy target is busy.
#
# The deploy key is confined by rrsync (rsync 3.2.4+), which takes a per-user
# lock and refuses a second concurrent session with
#   "Another instance of rrsync is already accessing this directory."
# rsync then dies with exit code 12 before sending anything. Parallel backfill
# jobs finish their builds within seconds of each other and collide on that
# lock, so a refused upload is retried with a jittered wait. Any other failure
# is returned as-is, on the first attempt.
#
# Usage: rsync-retry.sh <rsync arguments...>
set -u

max=${RSYNC_RETRY_MAX:-30}
attempt=1
while :; do
    out=$(rsync "$@" 2>&1)
    rc=$?
    if [ "$rc" -eq 0 ]; then
        [ -n "$out" ] && printf '%s\n' "$out"
        exit 0
    fi
    printf '%s\n' "$out" >&2
    if [ "$rc" -ne 12 ] || ! grep -q 'Another instance of rrsync' <<<"$out" || [ "$attempt" -ge "$max" ]; then
        exit "$rc"
    fi
    wait=$((15 + RANDOM % 16))
    echo "deploy target busy (attempt $attempt/$max); retrying in ${wait}s"
    sleep "$wait"
    attempt=$((attempt + 1))
done
