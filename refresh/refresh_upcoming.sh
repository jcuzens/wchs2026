#!/bin/bash
# 4-hour scratch refresh for the WCHS 2026 schedule page.
#
# Re-fetches the entry pages of every class that is not settled yet (no
# placings posted) so scratches (entries withdrawn before their class,
# shown on the site with a pink strikethrough row) stay current across the
# whole upcoming schedule. refresh_cron.sh (8-minute) keeps only the
# frontier + lookahead fresh; this pass covers the rest.
#
#   cron: 0 */4 * * *  <repo>/refresh/refresh_upcoming.sh
#
# Same lock/log/safety as refresh_cron.sh: a run that overlaps the 8-minute
# job (or another upcoming run) skips. The first run after deploy is the
# one-time "big refresh" of all unsettled classes.
set -u
export PATH=/usr/local/bin:/usr/bin:/bin
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
LOG="$HERE/cron.log"
LOCK="$HERE/cron.lock"
LIST="$HERE/upcominglist.txt"

exec >>"$LOG" 2>&1
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { log "ERROR: $*"; log "=== upcoming refresh aborted ==="; exit 1; }

log "=== upcoming refresh start (pid $$) ==="

# one run at a time, sharing the 8-minute job's lock
exec 9>"$LOCK"
if ! flock -n 9; then
  log "previous run still going, skipping"
  exit 0
fi

cd "$HERE" || die "cannot cd to $HERE"
git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1 || die "not a git repo"

# --- fetch phase
nfiles=$(ls entries/ 2>/dev/null | wc -l)
total=$(python3 -c "import json; print(len(json.load(open('classes.json'))))")
if [ "$nfiles" -lt 50 ]; then
  log "entries/ has $nfiles/$total pages -> full resumable fetch"
  bash fetch_entries.sh || log "WARNING: full fetch had failures (resumable; retries next run)"
  python3 parse_entries.py >/dev/null
else
  python3 select_frontier.py upcoming > "$LIST"
  if [ ! -s "$LIST" ]; then
    log "nothing upcoming (all classes settled); nothing to do"
    log "=== upcoming refresh done ==="
    exit 0
  fi
  log "upcoming: $(tr '\n' ' ' < "$LIST")"
  bash fetch_entries.sh "$LIST" || log "WARNING: upcoming fetch had failures"
  python3 parse_entries.py >/dev/null
fi

# --- safety: refuse to publish a catastrophic data loss
counts=$(python3 - <<'PY'
import json, os, re
new = json.load(open('data.json'))
new_n = sum(len(c['entries']) for c in new)
m = re.search(r'^(?:const|let) DATA = (\{.*\});\s*$',
              open(os.path.join('..', 'index.html')).read(), re.M)
old_n = sum(len(c['e']) for c in json.loads(m.group(1))['classes']) if m else 0
print(new_n, old_n)
PY
)
new_n=${counts%% *}
old_n=${counts##* }
log "entries: $old_n -> $new_n"
if [ "$old_n" -gt 0 ] && [ "$new_n" -lt $((old_n / 2)) ]; then
  die "entry count dropped to $new_n (was $old_n); refusing to publish"
fi

# --- build + publish (asof only changes when the data changed)
python3 build_page.py || die "build failed"
if git -C "$ROOT" diff --quiet HEAD -- index.html payload.json check.json; then
  log "unchanged; nothing to publish"
else
  git -C "$ROOT" add index.html payload.json check.json || die "git add failed"
  git -C "$ROOT" commit -m "Refresh upcoming entries $(date +%F)" || die "git commit failed"
  git -C "$ROOT" push || die "git push failed"
  log "committed and pushed"
fi
log "=== upcoming refresh done ==="
