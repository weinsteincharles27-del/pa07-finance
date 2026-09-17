#!/usr/bin/env python3
"""Did anything the refresh job owns change, other than a timestamp?

Every run stamps retrieved_utc and generated_utc, so a plain `git diff` is
never empty and a five-minute schedule would commit 288 times a day saying
nothing. This compares each owned JSON file to the committed version with
those keys removed. If none differ, the working-tree changes are discarded
(including the workbook, which only re-embeds the same timestamps) and the
job commits nothing.

    python3 changed.py        # exit 0 = something changed, 1 = nothing did
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OWNED_JSON = ["sources/fec.json", "sources/fec_history.json", "sources/fec_detail.json",
              "site/data/manifest.json", "site/data/detail.json", "site/data/candidates.json", "site/data/outside.json",
              "site/data/history.json", "site/data/caveats.json"]
OWNED_ALL = OWNED_JSON + ["site/PA07_Campaign_Finance.xlsx"]
# Keys that move on every run without meaning anything moved: stamps, the
# countdown, and byte counts (openpyxl's zip output is not byte-stable, so the
# workbook's size wobbles by a byte between identical builds).
VOLATILE = {"retrieved_utc", "generated_utc", "days_to_election", "files", "bytes"}


def strip(obj):
    """Drop the volatile keys, recursively."""
    if isinstance(obj, dict):
        return {k: strip(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [strip(v) for v in obj]
    return obj


def committed(rel):
    try:
        out = subprocess.run(["git", "show", "HEAD:" + rel], cwd=ROOT, capture_output=True, check=True)
        return json.loads(out.stdout.decode("utf-8"))
    except (subprocess.CalledProcessError, ValueError):
        return None                                   # new file, or not in git yet


def differs(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return False
    now = json.load(open(path))
    was = committed(rel)
    return was is None or strip(now) != strip(was)


def main():
    changed = [rel for rel in OWNED_JSON if differs(rel)]
    if changed:
        print("changed: " + ", ".join(changed))
        return 0
    print("nothing but timestamps changed; discarding")
    # `git checkout -- a b c` refuses the whole list if any path is untracked,
    # so restore only the owned files git actually knows about.
    tracked = subprocess.run(["git", "ls-files", "--"] + OWNED_ALL, cwd=ROOT,
                             capture_output=True, text=True).stdout.split()
    if tracked:
        subprocess.run(["git", "checkout", "--"] + tracked, cwd=ROOT, check=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
