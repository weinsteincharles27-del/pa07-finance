"""changed.py and the weekly history rule."""
import datetime
import json
import os
import subprocess
import tempfile
import shutil

import support


def repo_with(files):
    """A throwaway git repo with `files` committed, returning its path."""
    d = tempfile.mkdtemp(prefix="pa07chg-")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True)
    for rel, obj in files.items():
        os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
        json.dump(obj, open(os.path.join(d, rel), "w"))
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed"], cwd=d, check=True)
    return d


def run_changed(d):
    mod = support.load("changed")
    orig = mod.ROOT
    mod.ROOT = d
    try:
        return mod.main()
    finally:
        mod.ROOT = orig


def test_timestamp_only_change_is_discarded():
    d = repo_with({"sources/fec.json": {"retrieved_utc": "2026-01-01T00:00:00Z", "x": 1}})
    try:
        json.dump({"retrieved_utc": "2026-02-02T00:00:00Z", "x": 1}, open(os.path.join(d, "sources/fec.json"), "w"))
        assert run_changed(d) == 1
        # and the working tree was restored to the committed version
        assert json.load(open(os.path.join(d, "sources/fec.json")))["retrieved_utc"] == "2026-01-01T00:00:00Z"
    finally:
        shutil.rmtree(d)


def test_real_change_is_kept():
    d = repo_with({"sources/fec.json": {"retrieved_utc": "2026-01-01T00:00:00Z", "x": 1}})
    try:
        json.dump({"retrieved_utc": "2026-02-02T00:00:00Z", "x": 2}, open(os.path.join(d, "sources/fec.json"), "w"))
        assert run_changed(d) == 0
        assert json.load(open(os.path.join(d, "sources/fec.json")))["x"] == 2
    finally:
        shutil.rmtree(d)


def test_nested_timestamps_and_days_to_election_are_ignored():
    m = {"generated_utc": "a", "race": {"days_to_election": 47, "election": "2026-11-03"}, "files": {"x": 1}}
    d = repo_with({"site/data/manifest.json": m})
    try:
        m2 = {"generated_utc": "b", "race": {"days_to_election": 46, "election": "2026-11-03"}, "files": {"x": 2}}
        json.dump(m2, open(os.path.join(d, "site/data/manifest.json"), "w"))
        assert run_changed(d) == 1
    finally:
        shutil.rmtree(d)


def test_history_refetched_only_when_stale():
    mod = support.load("collect_fec")
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "h.json")
        now = datetime.datetime(2026, 9, 17, tzinfo=datetime.timezone.utc)
        assert mod.history_is_fresh(p, now) is False                       # missing
        json.dump({"retrieved_utc": "2026-09-15T00:00:00Z"}, open(p, "w"))
        assert mod.history_is_fresh(p, now) is True                        # 2 days old
        json.dump({"retrieved_utc": "2026-09-01T00:00:00Z"}, open(p, "w"))
        assert mod.history_is_fresh(p, now) is False                       # 16 days old
        json.dump({"nope": 1}, open(p, "w"))
        assert mod.history_is_fresh(p, now) is False                       # unreadable stamp
    finally:
        shutil.rmtree(d)
