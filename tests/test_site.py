"""Static checks on the page. There is no JS runtime here, so this checks
what can be checked by reading the files."""
import os
import re

import support

SITE = os.path.join(support.ROOT, "site")


def read(rel):
    return open(os.path.join(SITE, rel), encoding="utf-8").read()


def test_index_references_only_files_that_exist():
    html = read("index.html")
    for src in re.findall(r'src="([^"]+)"', html) + re.findall(r'href="(assets/[^"]+)"', html):
        assert os.path.exists(os.path.join(SITE, src)), src


def test_every_data_file_app_js_fetches_is_exported():
    js = read("assets/app.js")
    fetched = set(re.findall(r'get\("data/([a-z]+\.json)"\)', js))
    e = support.load("export_site")
    with support.sandbox() as (src, work):
        site = os.path.join(work, "site")
        e.run(src, site, None)
        written = set(os.listdir(os.path.join(site, "data")))
    assert fetched <= written, fetched - written


def test_no_em_dashes_in_page_copy():
    for rel in ("index.html", "assets/app.js", "assets/finance.js", "assets/app.css"):
        assert chr(0x2014) not in read(rel), rel


def test_no_standings_language_in_page_copy():
    """Colour encodes party and nothing else; no side is called ahead."""
    js = read("assets/finance.js")
    body = re.sub(r"/\*.*?\*/", "", js, flags=re.S)          # strip comments
    for w in ("advantage", "leads", "trailing", "outraised", "outspent", "winning", "losing"):
        assert not re.search(r"\b" + w + r"\b", body, re.I), w


def test_chart_library_exposes_the_kinds_the_page_uses():
    chart = read("assets/chart.js")
    fin = read("assets/finance.js")
    for kind in re.findall(r"\bC\.(groups|stacked|hbars|bars|line)\(", fin):
        assert ("%s: %s" % (kind, kind)) in chart, kind
