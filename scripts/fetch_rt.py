"""Fetch Rotten Tomatoes Tomatometer scores through the OMDb API and save them to data/rt_scores.json.

Needs a free OMDb key stored as the repository secret OMDB_API_KEY. Without it this step is skipped
with a warning (box office still refreshes).

Lookups use the movie name from movies.csv unless you fill in `omdb_title` or `imdb_id` there. A movie
OMDb can't find, or returns without a Rotten Tomatoes score, keeps its previous score and is listed in the report.
Only movies that appear on the Box Office Mojo chart are looked up.
"""
import csv, json, os, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, load, save, now_iso, norm, error, notice, warning, summary

BASE = os.environ.get("OMDB_BASE", "https://www.omdbapi.com/")
KEY = os.environ.get("OMDB_API_KEY", "").strip()


class Fatal(Exception):
    pass


def omdb(params):
    url = BASE + "?" + urllib.parse.urlencode({**params, "apikey": KEY})
    for attempt, wait in enumerate((0, 3, 10), 1):
        time.sleep(wait if os.environ.get("OMDB_PAUSE", "0.25") != "0" else 0)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "FantasyBoxOfficeLeague/1.0"}), timeout=30) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 401: raise Fatal("OMDb rejected the API key (HTTP 401). Check the OMDB_API_KEY secret, and that you activated the key from the email OMDb sent.")
            if attempt == 3: raise Fatal(f"OMDb returned HTTP {e.code}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            if attempt == 3: raise Fatal(f"couldn't reach OMDb ({getattr(e, 'reason', e)})")
    if body.get("Response") == "False":
        msg = body.get("Error", "")
        if "limit" in msg.lower(): raise Fatal("OMDb's daily request limit was reached; try again tomorrow.")
        if "invalid api key" in msg.lower(): raise Fatal("OMDb says the API key is invalid. Check the OMDB_API_KEY secret.")
        return None
    return body


def tomatometer(body):
    for r in body.get("Ratings", []):
        if r.get("Source") == "Rotten Tomatoes":
            v = r.get("Value", "").strip().rstrip("%")
            if v.isdigit(): return int(v) / 100
    return None


def lookup(row, season):
    """Find the movie on OMDb. Tries the release year, then the year before (late-December releases)."""
    if row.get("imdb_id", "").strip():
        return omdb({"i": row["imdb_id"].strip()})
    title = " ".join((row.get("omdb_title") or row["movie"]).split())
    for year in (season, season - 1):
        body = omdb({"t": title, "y": year, "type": "movie"})
        if body: return body
    return None


def main():
    if not KEY:
        warning("OMDB_API_KEY isn't set, so Rotten Tomatoes scores were not refreshed. See the README to add it.")
        summary("### ⚠️ Rotten Tomatoes skipped\nNo `OMDB_API_KEY` secret found.")
        return
    season = (load("config.json") or {}).get("season", 2024)
    on_chart = {norm(r["title"]) for r in (load("bom_domestic.json") or {}).get("rows", [])}
    with open(DATA / "movies.csv", encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("movie") or "").strip() and norm(r["movie"]) in on_chart]
    snap = load("rt_scores.json") or {"scores": {}}
    scores, changed, problems = snap.setdefault("scores", {}), [], []
    try:
        for row in rows:
            time.sleep(float(os.environ.get("OMDB_PAUSE", "0.25")))
            name = " ".join(row["movie"].split())
            body = lookup(row, season)
            if not body:
                problems.append(f"{name}: not found on OMDb (add `imdb_id` or `omdb_title` in movies.csv)"); continue
            year = "".join(c for c in body.get("Year", "") if c.isdigit())[:4]
            if row.get("imdb_id", "").strip() == "" and (not year or abs(int(year) - season) > 1):
                problems.append(f"{name}: OMDb matched '{body.get('Title')}' ({body.get('Year')}), which doesn't look right; add `imdb_id` in movies.csv"); continue
            score = tomatometer(body)
            if score is None:
                problems.append(f"{name}: no Rotten Tomatoes score on OMDb yet; kept the previous one"); continue
            old = scores.get(name, {}).get("score")
            if old is not None and abs(old - score) > 1e-9: changed.append(f"{name}: {round(old * 100)}% → {round(score * 100)}%")
            scores[name] = {"score": score, "source": "omdb", "checked": now_iso()[:10], "imdbId": body.get("imdbID", ""), "matched": f"{body.get('Title')} ({body.get('Year')})"}
    except Fatal as e:
        error(f"Rotten Tomatoes pull stopped. {e} Scores from this run were not saved.")
        summary(f"### ❌ Rotten Tomatoes pull failed\n{e}")
        sys.exit(1)
    snap["fetchedAt"] = now_iso(); snap.pop("importedAt", None)
    save("rt_scores.json", snap)
    for p in problems: warning(p)
    lines = [f"### ✅ Rotten Tomatoes pulled ({len(rows)} movies checked)"]
    lines.append("- Changed: " + ("; ".join(changed) if changed else "no scores changed"))
    if problems: lines.append("- Needs attention:\n" + "\n".join(f"  - {p}" for p in problems))
    print("\n".join(lines)); summary("\n".join(lines))


if __name__ == "__main__":
    main()
