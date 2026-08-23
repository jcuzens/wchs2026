#!/bin/bash
# Resumable fetcher for class entry pages
cd "$(dirname "$0")"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
mkdir -p entries
python3 -c "import json; [print(c['num'], c['guid']) for c in json.load(open('classes.json'))]" > fetchlist.txt
curl -s -b jar.txt -c jar.txt -A "$UA" -o /dev/null "https://horseshowsonline.com/ShowDetails?ShowGUID=46c298a5-6bac-44e0-a711-56695c992e12"
n=0
while read -r num guid; do
  if [ -s "entries/$num.html" ] && [ $(wc -c < "entries/$num.html") -gt 50000 ]; then n=$((n+1)); continue; fi
  ok=0
  for attempt in 1 2 3; do
    curl -s -b jar.txt -c jar.txt -A "$UA" --max-time 90 -o "entries/$num.html" "https://horseshowsonline.com/ClassResults.aspx?ClassGUID=$guid" && ok=1 && break
    sleep 2
  done
  if [ $ok -eq 1 ] && [ $(wc -c < "entries/$num.html") -gt 50000 ]; then
    n=$((n+1)); echo "OK $num"
  else
    echo "FAIL $num"; rm -f "entries/$num.html"
  fi
  if [ $((n % 25)) -eq 0 ]; then
    curl -s -b jar.txt -c jar.txt -A "$UA" -o /dev/null "https://horseshowsonline.com/ShowDetails?ShowGUID=46c298a5-6bac-44e0-a711-56695c992e12"
  fi
done < fetchlist.txt
echo "DONE $n"
