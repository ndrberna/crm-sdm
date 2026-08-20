#!/usr/bin/env python3
"""
run_cqs.py — executes competency questions and verifies expected results.

Rationale
---------
Provides continuous integration testing for Competency Questions (CQs):
- Executes formal SPARQL queries for each CQ.
- Asserts expected row counts to verify result correctness.
- Programmatically flags regressions caused by schema or data changes.


.rq File Format
--------------------
The PREFIX prologues at the top apply to all queries. Each block is
introduced by:

    #### CQn  question text
    #### EXPECT <number of expected rows>

Usage
---
    pip install rdflib
    python3 scripts/run_cqs.py
    python3 scripts/run_cqs.py --show CQ3     # also prints the result rows
"""

from __future__ import annotations

import argparse
import re
import sys

import rdflib


def split_queries(text: str):
    """Returns (prologue, [(name, question, expected, query)])."""
    lines = text.splitlines()
    first = next((i for i, l in enumerate(lines) if l.startswith("#### CQ")), len(lines))
    prologue = "\n".join(l for l in lines[:first] if l.strip().startswith("PREFIX"))

    blocks, cur = [], None
    for line in lines[first:]:
        m = re.match(r"^####\s+(CQ\d+)\s*(.*)$", line)
        if m:
            if cur:
                blocks.append(cur)
            cur = {"name": m.group(1), "question": m.group(2).strip(),
                   "expect": None, "body": []}
            continue
        if cur is None:
            continue
        m = re.match(r"^####\s+EXPECT\s+(\d+)", line)
        if m:
            cur["expect"] = int(m.group(1))
            continue
        if line.startswith("####"):
            cur["question"] += " " + line.lstrip("# ").strip()
            continue
        cur["body"].append(line)
    if cur:
        blocks.append(cur)
    for b in blocks:
        b["query"] = prologue + "\n" + "\n".join(b["body"]).strip()
    return prologue, blocks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kg", default="../kg/crm-sdm-kg.ttl")
    ap.add_argument("--cqs", default="../validation/competency-questions.rq")
    ap.add_argument("--show", default=None, metavar="CQn",
                    help="print rows returned by the specified CQ")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    g = rdflib.Graph()
    g.parse(args.kg, format="turtle")
    print(f"Graph: {len(g)} triples\n")

    _, blocks = split_queries(open(args.cqs, encoding="utf-8").read())
    failures = 0
    for b in blocks:
        try:
            rows = list(g.query(b["query"]))
        except Exception as e:
            print(f"  ERROR  {b['name']}: {str(e)[:90]}")
            failures += 1
            continue
        n, exp = len(rows), b["expect"]
        ok = exp is None or n == exp
        status = "OK   " if ok else "FAIL "
        failures += not ok
        print(f"  {status} {b['name']}  {n:>4} rows"
              + ("" if exp is None else f"  (expected {exp})"))
        print(f"        {b['question'][:96]}")
        if args.show and args.show.upper() == b["name"]:
            cols = [str(v) for v in rows[0].labels] if rows else []
            print("        " + " | ".join(cols))
            for r in rows[:args.limit]:
                print("        " + " | ".join(
                    (str(x).rsplit('#', 1)[-1] if x is not None else "-")[:26] for x in r))

    print()
    if failures:
        sys.exit(f"{failures} competency question(s) failed.")
    print(f"All {len(blocks)} competency questions answered as expected.")


if __name__ == "__main__":
    main()