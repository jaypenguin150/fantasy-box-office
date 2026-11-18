"""ONE-TIME SEED: copy the picks, flags and box office tabs out of the original workbook into data/.

    pip install openpyxl
    python scripts/import_from_workbook.py Fantasy_Box_Office_2024.xlsx 2026-11-17

After this the workbook is no longer needed: the scheduled refresh keeps the data files up to date.
Emails, offices and roles from the form are deliberately NOT copied.
"""
import csv, json, re, sys
from openpyxl import load_workbook
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import DATA, save, money

src = sys.argv[1]
imported = sys.argv[2] if len(sys.argv) > 2 else __import__("datetime").date.today().isoformat()
wb = load_workbook(src, data_only=True)
DATA.mkdir(parents=True, exist_ok=True)

def bom_rows(sheet):
    rows = []
    for r in wb[sheet].iter_rows(min_row=2, values_only=True):
        if r[1]:
            rows.append({"title": str(r[1]).strip(), "gross": money(r[5]), "releaseDate": str(r[8] or ""), "distributor": r[9] or ""})
    return rows

for name, sheet, url in [("bom_domestic.json", "2024 Movie Data BOM DOM", "https://www.boxofficemojo.com/year/2024/"),
                         ("bom_mexico.json", "2024 Movie Data BOM MEX", "https://www.boxofficemojo.com/year/2024/?area=MX")]:
    save(name, {"fetchedAt": None, "importedAt": imported, "source": url, "rows": bom_rows(sheet)})

inp, eng = wb["Inputs"], wb["Engine"]
movies, rt = [], {}
for r in range(6, 200):
    n = inp.cell(r, 1).value
    if not n: continue
    n = str(n).strip()
    movies.append({"movie": n, "franchise": 1 if inp.cell(r, 7).value else 0, "rt_override": "", "omdb_title": "", "imdb_id": ""})
    rt[n] = {"score": inp.cell(r, 8).value or 0, "source": "workbook", "checked": None}
movies.sort(key=lambda m: m["movie"].lower())
with open(DATA / "movies.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["movie", "franchise", "rt_override", "omdb_title", "imdb_id"], lineterminator="\n"); w.writeheader(); w.writerows(movies)
save("rt_scores.json", {"fetchedAt": None, "importedAt": imported, "scores": rt})

employed = {inp.cell(r, 14).value: bool(inp.cell(r, 15).value) for r in range(6, 60) if inp.cell(r, 14).value}
players = {}
for r in range(6, 402):
    p = eng.cell(r, 21).value
    if p in (None, 0, ""): continue
    players.setdefault(p, []).append({"pick": str(eng.cell(r, 23).value).strip(), "movie": eng.cell(r, 24).value, "handPicked": bool(eng.cell(r, 30).value)})
save("picks.json", {"players": [{"name": n, "employed": employed.get(n, True), "picks": pk} for n, pk in sorted(players.items())]})

old = None
try: old = json.load(open(DATA / "data.json"))
except (OSError, ValueError): pass
save("config.json", {
    "season": 2024, "refreshEveryDays": 10, "penalty": 75_000_000, "rtThreshold": eng["AB3"].value,
    "enforce": (old or {}).get("enforce", {"sequels": True, "summer": True, "distributor": True}),
})
print(f"seeded: {len(players)} players, {len(movies)} movies, {sum(len(bom_rows(s)) for s in ['2024 Movie Data BOM DOM'])} domestic rows")
