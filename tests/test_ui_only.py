#!/usr/bin/env python3
"""Verify `build_page.py --ui-only` preserves the embedded payload (incl. asof)
and is idempotent. Run after building: python3 refresh/build_page.py"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = os.path.join(ROOT, "index.html")
BUILDER = os.path.join(ROOT, "refresh", "build_page.py")

def payload_of(p):
    s = open(p).read()
    m = re.search(r"^const DATA = (\{.*\});\s*$", s, re.M)
    assert m, "payload not found in " + p
    return m.group(1)

fails = []
def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  [" + extra + "]") if extra else ""))
    if not cond:
        fails.append(name)

p_before = payload_of(IDX)
subprocess.run([sys.executable, BUILDER, "--ui-only"], check=True)
check("payload preserved across --ui-only rebuild", payload_of(IDX) == p_before)
check("template applied (updatedLine present)", 'id="updatedLine"' in open(IDX).read())
first = open(IDX).read()
subprocess.run([sys.executable, BUILDER, "--ui-only"], check=True)
check("idempotent (second --ui-only run byte-identical)", open(IDX).read() == first)

print("\n" + ("ALL PASS" if not fails else str(len(fails)) + " FAILURES: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
