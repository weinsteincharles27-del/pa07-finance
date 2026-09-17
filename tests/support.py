"""Shared scaffolding. Everything is offline: the one seam into the network is
collect_fec.fetch, which fake_fetch() replaces. Nothing here opens a socket."""
import contextlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
_loaded = {}
if ROOT not in sys.path:            # the modules import each other by plain name
    sys.path.insert(0, ROOT)


def load(name):
    """Import a project module by file, cached, registered under its plain name."""
    if name in _loaded:
        return _loaded[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _loaded[name] = mod
    return mod


def fixture(name):
    return json.load(open(os.path.join(FIX, name)))


def has_fixture(name):
    return os.path.exists(os.path.join(FIX, name))


@contextlib.contextmanager
def sandbox():
    """A temp dir seeded with the frozen sources. Yields (src_dir, work_dir)."""
    d = tempfile.mkdtemp(prefix="pa07fin-")
    try:
        src = os.path.join(d, "sources")
        os.makedirs(src)
        for f in ("fec.json", "fec_history.json", "fec_detail.json", "race.json", "results.json"):
            shutil.copy(os.path.join(FIX, f), src)
        yield src, d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def built(src, work):
    """Build the workbook from a sandbox. Returns (xlsx_path, anchors)."""
    b = load("build_workbook")
    fec = json.load(open(os.path.join(src, "fec.json")))
    hist = json.load(open(os.path.join(src, "fec_history.json")))
    race = json.load(open(os.path.join(src, "race.json")))
    dpath = os.path.join(src, "fec_detail.json")
    det = json.load(open(dpath)) if os.path.exists(dpath) else None
    out = os.path.join(work, "PA07_Campaign_Finance.xlsx")
    anchors = b.build(fec, hist, race, out, det=det)
    return out, anchors


class fake_fetch(object):
    """Replace collect_fec.fetch with canned responses keyed on (path, sorted params)."""

    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def __call__(self, path, **params):
        params.pop("api_key", None)
        self.calls.append((path, dict(params)))
        for (p, match), resp in self.responses:
            if p == path and all(params.get(k) == v for k, v in match.items()):
                return resp
        return {"results": [], "pagination": {"pages": 1}}

    def __enter__(self):
        self.mod = load("collect_fec")
        self.orig = self.mod.fetch
        self.mod.fetch = self
        return self

    def __exit__(self, *a):
        self.mod.fetch = self.orig
