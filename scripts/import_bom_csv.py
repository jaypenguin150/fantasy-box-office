"""FALLBACK: load Box Office Mojo grosses from CSV files you upload, instead of fetching them.

Use this if Box Office Mojo blocks the automatic pull. In Excel, save the two Box Office Mojo tabs as CSV and upload
them to the data/manual/ folder on GitHub as:
    data/manual/domestic.csv   (the US year chart)
    data/manual/mexico.csv     (the Mexico year chart)
then run the workflow by hand with "Use the CSV files from data/manual" ticked.

Needed columns (any order, extra columns ignored): Release, Gross, Release Date, Distributor
"""
import csv, datetime, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, load, save, now_iso, norm, money, error, summary
from fetch_bom import check, Fail


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows: raise Fail(f"{os.path.basename(path)} is empty")
    cols = {norm(c): c for c in rows[0]}
    for need in ("release", "gross"):
        if need not in cols: raise Fail(f"{os.path.basename(path)} has no '{need.title()}' column (found: {', '.join(rows[0])})")
    out = []
    for r in rows:
        title = (r[cols["release"]] or "").strip()
        if not title: continue
        raw_date = (r.get(cols.get("release date", ""), "") or "").strip()
        out.append({"title": title, "gross": money(r[cols["gross"]]) if r[cols["gross"]].strip() not in ("-", "") else 0,
                    "releaseDate": pretty_date(raw_date), "distributor": (r.get(cols.get("distributor", ""), "") or "").strip()})
    return out


def pretty_date(t):
    """Excel often exports dates as 6/14/2024 or 2024-06-14; the site wants 'Jun 14'."""
    if t[:3].isalpha(): return t
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%d-%b-%Y"):
        try:
            d = datetime.datetime.strptime(t.split(" ")[0], fmt); return f"{d.strftime('%b')} {d.day}"
        except ValueError: pass
    return t


def main():
    manual = DATA / "manual"
    jobs = [("US", "domestic.csv", "bom_domestic.json", 100), ("Mexico", "mexico.csv", "bom_mexico.json", 30)]
    results = []
    try:
        for label, csvname, fname, minimum in jobs:
            path = manual / csvname
            if not path.exists(): raise Fail(f"data/manual/{csvname} wasn't found. Upload it first.")
            rows = read(path); check(rows, load(fname), label, minimum); results.append((label, fname, rows, csvname))
    except Fail as e:
        error(f"CSV import failed. Data was NOT changed. {e}")
        summary(f"### ❌ CSV import failed\n{e}")
        sys.exit(1)
    stamp = now_iso()
    for label, fname, rows, csvname in results:
        save(fname, {"fetchedAt": stamp, "source": f"uploaded data/manual/{csvname}", "rows": rows})
        print(f"{label}: {len(rows)} movies from {csvname}")
    summary("### ✅ Box office loaded from uploaded CSV files\n" + "\n".join(f"- {l}: {len(r)} movies" for l, _, r, _ in results))


if __name__ == "__main__":
    main()
