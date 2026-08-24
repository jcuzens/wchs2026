#!/bin/bash
# Cron refresh for the WCHS 2026 schedule page.
#
# Every run: re-fetch the results frontier (classes from the last one with
# placings, until the first whose results are not posted yet), plus a
# lookahead of upcoming classes to keep entry lists fresh; rebuild
# index.html; commit and push only when the data actually changed.
#
#   cron: */8 * * * *  <repo>/refresh/refresh_cron.sh
#
# All output goes to refresh/cron.log. Only index.html is ever committed;
# the git-ignored intermediates (entries/, data.json, jar.txt) stay local.
set -u
export PATH=/usr/local/bin:/usr/bin:/bin
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
LOG="$HERE/cron.log"
LOCK="$HERE/cron.lock"
LIST="$HERE/refreshlist.txt"
LOOKAHEAD=8    # schedule classes past the frontier whose entry lists to keep fresh
MAX_STEPS=220  # safety bound on frontier loop iterations (whole show = 218 classes)

exec >>"$LOG" 2>&1
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { log "ERROR: $*"; log "=== refresh aborted ==="; exit 1; }

log "=== refresh start (pid $$) ==="

# one run at a time; a still-running previous run wins, this one skips
exec 9>"$LOCK"
if ! flock -n 9; then
  log "previous run still going, skipping"
  exit 0
fi

cd "$HERE" || die "cannot cd to $HERE"
git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1 || die "not a git repo"
if [ -n "$(git -C "$ROOT" status --porcelain -- index.html)" ]; then
  log "WARNING: index.html has uncommitted local changes; rebuild will overwrite them"
fi

# --- fetch phase
nfiles=$(ls entries/ 2>/dev/null | wc -l)
total=$(python3 -c "import json; print(len(json.load(open('classes.json'))))")
if [ "$nfiles" -lt 50 ]; then
  log "entries/ has $nfiles/$total pages -> full resumable fetch"
  bash fetch_entries.sh || log "WARNING: full fetch had failures (resumable; retries next run)"
  python3 parse_entries.py >/dev/null
else
  log "entries/ has $nfiles/$total pages -> frontier mode"
  python3 parse_entries.py >/dev/null
  steps=0
  while :; do
    steps=$((steps+1))
    [ "$steps" -gt "$MAX_STEPS" ] && die "frontier loop exceeded $MAX_STEPS steps (stuck?)"
    f=$(python3 select_frontier.py frontier)
    [ -z "$f" ] && { log "frontier exhausted (all classes settled)"; break; }
    log "frontier: class $f"
    python3 select_frontier.py frontier-nums > "$LIST"
    bash fetch_entries.sh "$LIST"
    rc=$?
    python3 parse_entries.py >/dev/null
    if python3 select_frontier.py settled "$f"; then
      log "class $f settled"
    else
      [ "$rc" -ne 0 ] && log "WARNING: fetch failed for class $f; will retry next run"
      log "no more results ready (stopped at class $f)"
      break
    fi
  done
  # lookahead: keep entry lists fresh for the classes right after the frontier
  python3 select_frontier.py lookahead "$LOOKAHEAD" > "$LIST"
  if [ -s "$LIST" ]; then
    log "lookahead: $(tr '\n' ' ' < "$LIST")"
    bash fetch_entries.sh "$LIST" || log "WARNING: lookahead fetch had failures"
    python3 parse_entries.py >/dev/null
  fi
fi

# --- safety: refuse to publish a catastrophic data loss
counts=$(python3 - <<'PY'
import json, os, re
new = json.load(open('data.json'))
new_n = sum(len(c['entries']) for c in new)
m = re.search(r'^const DATA = (\{.*\});\s*$',
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
if git -C "$ROOT" diff --quiet HEAD -- index.html; then
  log "index.html unchanged; nothing to publish"
else
  git -C "$ROOT" add index.html || die "git add failed"
  git -C "$ROOT" commit -m "Refresh entries $(date +%F)" || die "git commit failed"
  git -C "$ROOT" push || die "git push failed"
  log "committed and pushed"
fi
log "=== refresh done ==="
