#!/bin/bash
# Resumable fetcher for class entry pages
#
# Usage: fetch_entries.sh [listfile]
#   no arg    - re-download all class pages (skips already-fetched; resumable)
#   listfile  - re-fetch exactly the classes listed (one num per line),
#               never skipping; used by refresh_cron.sh (frontier + lookahead)
#
# A page is accepted only if it looks like a real class page (> 50 KB) or a
# legitimate "No entries" page. Pages are written to a temp file and moved
# into place only when accepted, so a failed fetch (dead session cookie,
# network blip) never clobbers the previous good page.
# Exit code: 0 if every page in the list was fetched, 1 otherwise.
cd "$(dirname "$0")"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
mkdir -p entries

if [ -n "$1" ]; then
  python3 -c "
import json, sys
want = [l.strip() for l in open(sys.argv[1]) if l.strip()]
have = {c['num']: c['guid'] for c in json.load(open('classes.json'))}
for num in want:
    if num in have:
        print(num, have[num])
    else:
        print('WARN no guid for class ' + num, file=sys.stderr)
" "$1" > fetchlist.txt
else
  python3 -c "import json; [print(c['num'], c['guid']) for c in json.load(open('classes.json'))]" > fetchlist.txt
fi

curl -s -b jar.txt -c jar.txt -A "$UA" -o /dev/null "https://horseshowsonline.com/ShowDetails?ShowGUID=46c298a5-6bac-44e0-a711-56695c992e12"
ok=0; fail=0; n=0
while read -r num guid; do
  final="entries/$num.html"
  tmp="$final.tmp"
  if [ -z "$1" ] && [ -s "$final" ] && [ $(wc -c < "$final") -gt 50000 ]; then
    ok=$((ok+1)); continue
  fi
  good=0
  for attempt in 1 2 3; do
    touch "$tmp"
    if curl -s -b jar.txt -c jar.txt -A "$UA" --max-time 90 -o "$tmp" "https://horseshowsonline.com/ClassResults.aspx?ClassGUID=$guid"; then
      if [ $(wc -c < "$tmp") -gt 50000 ] || grep -q 'No entries' "$tmp" || grep -qi 'no data' "$tmp"; then
        good=1; break
      fi
    fi
    sleep 2
  done
  if [ $good -eq 1 ]; then
    mv "$tmp" "$final"
    ok=$((ok+1)); echo "OK $num"
  else
    rm -f "$tmp"
    fail=$((fail+1)); echo "FAIL $num"
  fi
  n=$((n+1))
  if [ $((n % 25)) -eq 0 ]; then
    curl -s -b jar.txt -c jar.txt -A "$UA" -o /dev/null "https://horseshowsonline.com/ShowDetails?ShowGUID=46c298a5-6bac-44e0-a711-56695c992e12"
  fi
done < fetchlist.txt
echo "FETCHED ok=$ok failed=$fail"
[ $fail -eq 0 ]
