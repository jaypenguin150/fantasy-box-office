"""Fetch the Box Office Mojo yearly charts (US and Mexico) and save them to data/.

Two pages, one request each, identified honestly in the User-Agent. Nothing is saved unless BOTH pages
download and pass sanity checks, so a block, outage or layout change leaves the previous data untouched
and fails the run (GitHub then emails you).

Note: Box Office Mojo's conditions of use restrict automated access without written consent.
"""
import os, sys, time, urllib.request, urllib.error
from html.parser import HTMLParser
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, save, now_iso, norm, money, error, notice, warning, summary

BASE = os.environ.get("BOM_BASE", "https://www.boxofficemojo.com").rstrip("/")
REPO = os.environ.get("GITHUB_REPOSITORY", "fantasy-box-office")
UA = os.environ.get("BOM_USER_AGENT", f"FantasyBoxOfficeLeague/1.0 (private league scoreboard; ~1 refresh per 10 days; https://github.com/{REPO})")


class Fail(Exception):
    pass


class TableParser(HTMLParser):
    """Collects every <table> as a list of rows of cell text (handles nesting)."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._stack = [], []

    def handle_starttag(self, tag, attrs):
        s = self._stack
        if tag == "table": s.append({"rows": [], "row": None, "cell": None})
        elif s and tag == "tr": s[-1]["row"] = []
        elif s and tag in ("td", "th") and s[-1]["row"] is not None: s[-1]["cell"] = []

    def handle_data(self, data):
        if self._stack and self._stack[-1]["cell"] is not None: self._stack[-1]["cell"].append(data)

    def handle_endtag(self, tag):
        s = self._stack
        if not s: return
        t = s[-1]
        if tag in ("td", "th") and t["cell"] is not None:
            t["row"].append(" ".join("".join(t["cell"]).split())); t["cell"] = None
        elif tag == "tr" and t["row"] is not None:
            t["rows"].append(t["row"]); t["row"] = None
        elif tag == "table": self.tables.append(s.pop()["rows"])


def parse_chart(html):
    """Return [{title, gross, releaseDate, distributor}] from the yearly chart page."""
    p = TableParser(); p.feed(html)
    best = []
    for rows in p.tables:
        for i, r in enumerate(rows):
            head = [norm(c) for c in r]
            if "release" in head and "gross" in head:
                col = {h: j for j, h in reversed(list(enumerate(head)))}  # first occurrence wins
                out = []
                for row in rows[i + 1:]:
                    if len(row) <= max(col["release"], col["gross"]) or not row[col["release"]]: continue
                    out.append({
                        "title": row[col["release"]],
                        "gross": money(row[col["gross"]]) if row[col["gross"]] not in ("-", "") else 0,
                        "releaseDate": row[col["release date"]] if "release date" in col and col["release date"] < len(row) else "",
                        "distributor": row[col["distributor"]] if "distributor" in col and col["distributor"] < len(row) else "",
                    })
                if len(out) > len(best): best = out
                break
    if not best: raise Fail("couldn't find the chart table on the page (has the layout changed?)")
    return best


def download(url):
    last = None
    for attempt, wait in enumerate((0, 5, 20), 1):
        time.sleep(wait if os.environ.get("BOM_PAUSE", "3") != "0" else 0)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404, 451):
                raise Fail(f"Box Office Mojo refused the request (HTTP {e.code}) for {url}. It may be blocking GitHub's servers.")
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = str(getattr(e, "reason", e))
        print(f"attempt {attempt} failed ({last}); retrying" if attempt < 3 else "")
    raise Fail(f"couldn't download {url} after 3 attempts ({last})")


def check(rows, prev, label, minimum):
    if len(rows) < minimum: raise Fail(f"{label} chart has only {len(rows)} rows (expected at least {minimum}); page looks incomplete")
    if not any(r["gross"] > 1_000_000 for r in rows): raise Fail(f"{label} chart has no sensible grosses; parsing probably failed")
    if prev and prev.get("rows"):
        old = {norm(r["title"]) for r in prev["rows"]}
        kept = len(old & {norm(r["title"]) for r in rows}) / len(old)
        if kept < 0.8: raise Fail(f"{label} chart shares only {kept:.0%} of its titles with the last pull; refusing to overwrite")


def main():
    cfg = load("config.json") or {}
    season = cfg.get("season", 2024)
    pages = [("US", "bom_domestic.json", f"{BASE}/year/{season}/", 100), ("Mexico", "bom_mexico.json", f"{BASE}/year/{season}/?area=MX", 30)]
    results = []
    try:
        for i, (label, fname, url, minimum) in enumerate(pages):
            if i: time.sleep(float(os.environ.get("BOM_PAUSE", "3")))  # be gentle: pause between the two pages
            rows = parse_chart(download(url))
            check(rows, load(fname), label, minimum)
            results.append((label, fname, url, rows))
    except Fail as e:
        error(f"Box Office Mojo pull failed. Data was NOT changed. {e}")
        summary(f"### ❌ Box Office Mojo pull failed\n{e}\n\nNothing was changed. See the README, 'If a refresh fails'.")
        sys.exit(1)
    stamp = now_iso()
    for label, fname, url, rows in results:
        save(fname, {"fetchedAt": stamp, "source": url, "rows": rows})
        print(f"{label}: {len(rows)} movies, top: {rows[0]['title']} ${rows[0]['gross']:,}")
    summary(f"### ✅ Box Office Mojo pulled\n" + "\n".join(f"- {l}: {len(r)} movies" for l, _, _, r in results))


if __name__ == "__main__":
    main()
