"""Export the Fantasy Box Office workbook to data/data.json for the static site.

Usage: python scripts/build_data.py path/to/Fantasy_Box_Office_2024.xlsx [out.json] [YYYY-MM-DD]

Emails, offices and roles are deliberately NOT exported.
"""
import json, sys, re, datetime
from openpyxl import load_workbook

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else "data/data.json"
updated = sys.argv[3] if len(sys.argv) > 3 else datetime.date.today().isoformat()  # YYYY-MM-DD shown on the site
wb = load_workbook(src, data_only=True)

def money(v):
    if v in (None, "", "-"): return 0
    if isinstance(v, (int, float)): return int(v)
    return int(re.sub(r"[^\d]", "", str(v)) or 0)

def bom(sheet):
    d = {}
    for r in wb[sheet].iter_rows(min_row=2, values_only=True):
        if r[1]:
            d[str(r[1]).strip().lower()] = dict(  # lowercase: Excel XLOOKUP is case-insensitive
                gross=money(r[5]), month=str(r[8] or "")[:3], dist=r[9] or "")
    return d
dom, mex = bom("2024 Movie Data BOM DOM"), bom("2024 Movie Data BOM MEX")

inp = wb["Inputs"]
movies = {}
for r in range(6, 200):
    name = inp.cell(r, 1).value
    if not name: continue
    name = str(name).strip()
    d = dom.get(name.lower())
    movies[name] = dict(
        distributor=d["dist"] if d else "Not Released Yet",
        month=d["month"] if d else "",
        grossDom=d["gross"] if d else 0,
        grossMex=mex.get(name.lower(), {}).get("gross", 0),
        franchise=bool(inp.cell(r, 7).value),
        rt=inp.cell(r, 8).value or 0,
    )

employed = {inp.cell(r, 14).value: bool(inp.cell(r, 15).value) for r in range(6, 60) if inp.cell(r, 14).value}

eng = wb["Engine"]
players = {}
for r in range(6, 402):
    p = eng.cell(r, 21).value
    if p in (None, 0, ""): continue
    players.setdefault(p, []).append(dict(
        pick=str(eng.cell(r, 23).value).strip(), movie=eng.cell(r, 24).value, scoring=bool(eng.cell(r, 30).value)))

# Rule switches live in data.json so the commissioner can edit them; rebuilds keep whatever is already there.
enforce = dict(sequels=True, summer=True, distributor=True)
try: enforce.update({k: v for k, v in json.load(open(out)).get("enforce", {}).items() if k in enforce})
except (OSError, ValueError): pass

data = dict(
    updated=updated,
    enforce=enforce,
    season=2024, penalty=75_000_000, rtThreshold=eng["AB3"].value, movies=movies,
    players=[dict(name=n, employed=employed.get(n, True), picks=pk) for n, pk in sorted(players.items())],
)
json.dump(data, open(out, "w"), indent=1, ensure_ascii=False)
print(f"{len(data['players'])} players, {len(movies)} movies -> {out}")
