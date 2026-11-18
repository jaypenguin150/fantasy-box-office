"""Assemble data/data.json (what the website reads) from the files in data/.

Inputs : config.json, picks.json, movies.csv, bom_domestic.json, bom_mexico.json, rt_scores.json
Output : data.json

Safety: a movie's gross is never allowed to drop by more than 2% (or vanish) in one rebuild. If a
refresh would do that, the previous value is kept and a warning is raised, because grosses only
grow, so a drop means the pull was incomplete or garbled.
"""
import csv, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, load, save, norm, money, warning, error, notice, summary

MAX_DROP = 0.98


def die(msg):
    error(msg); sys.exit(1)


def short_names(full_names):
    """'Gabby Porcaro' -> 'Gabby P.'  If two people would collide, use more letters of the last name ('Adam Le.')."""
    def make(n, k):
        parts = n.split()
        return n if len(parts) < 2 else f"{parts[0]} {parts[-1][:k].title()}."
    out, k = {n: make(n, 1) for n in full_names}, 1
    while len(set(out.values())) < len(out) and k < 12:
        k += 1
        seen = {}
        for n, v in out.items(): seen.setdefault(v, []).append(n)
        for v, group in seen.items():
            if len(group) > 1:
                for n in group: out[n] = make(n, k)
    return out


def parse_rt(v):
    """'45', '45%' or '0.45' -> 0.45. Blank -> None."""
    v = str(v or "").strip().rstrip("%")
    if not v: return None
    try: x = float(v)
    except ValueError: die(f"movies.csv: can't read Rotten Tomatoes override '{v}'")
    return x / 100 if x > 1 else x


def month_of(text):
    """'Jun 14' -> 'Jun'. Also copes with '6/14/2024' or '2024-06-14'."""
    import datetime
    t = (text or "").strip()
    if len(t) >= 3 and t[:3].isalpha(): return t[:3].title()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%d-%b-%Y"):
        try: return datetime.datetime.strptime(t.split(" ")[0], fmt).strftime("%b")
        except ValueError: pass
    return ""


def index_bom(snap):
    out = {}
    for r in (snap or {}).get("rows", []):
        k = norm(r["title"])
        if k not in out or r["gross"] > out[k]["gross"]:
            out[k] = r
    return out


def date_of(snap):
    for key in ("fetchedAt", "importedAt"):
        if snap and snap.get(key): return snap[key][:10]
    return ""


def main():
    cfg = load("config.json") or die("data/config.json is missing")
    picks = load("picks.json") or die("data/picks.json is missing")
    dom_snap, mex_snap, rt_snap = load("bom_domestic.json"), load("bom_mexico.json"), load("rt_scores.json", {})
    if not dom_snap: die("data/bom_domestic.json is missing")
    dom, mex = index_bom(dom_snap), index_bom(mex_snap)
    rt_cache = (rt_snap or {}).get("scores", {})
    prev = (load("data.json") or {}).get("movies", {})

    with open(DATA / "movies.csv", encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("movie") or "").strip()]
    movies, kept, unmatched, rt_changes = {}, [], [], []
    for r in rows:
        name = " ".join(r["movie"].split())
        d, m, p = dom.get(norm(name)), mex.get(norm(name)), prev.get(name, {})
        gross_dom, gross_mex = (d["gross"] if d else 0), (m["gross"] if m else 0)
        for label, new, old in (("US", gross_dom, p.get("grossDom", 0)), ("Mexico", gross_mex, p.get("grossMex", 0))):
            if old and new < old * MAX_DROP:
                kept.append(f"{name} ({label}): new ${new:,} vs previous ${old:,}")
                if label == "US": gross_dom = old
                else: gross_mex = old
        if not d and p.get("grossDom", 0) == 0: unmatched.append(name)
        override = parse_rt(r.get("rt_override"))
        rt = override if override is not None else (rt_cache.get(name, {}).get("score") or 0)
        if p and abs((p.get("rt") or 0) - rt) > 1e-9: rt_changes.append(f"{name}: {round((p.get('rt') or 0) * 100)}% → {round(rt * 100)}%")
        movies[name] = {
            "distributor": (d["distributor"] if d else (p.get("distributor") if p.get("grossDom") else "")) or "Not Released Yet",
            "month": (month_of(d["releaseDate"]) if d and d["releaseDate"] else (p.get("month", "") if p.get("grossDom") else "")),
            "grossDom": gross_dom, "grossMex": gross_mex,
            "franchise": str(r.get("franchise", "")).strip() in ("1", "true", "True", "yes", "Yes", "Y", "y"),
            "rt": rt,
        }

    by_norm = {norm(n): n for n in movies}
    style = cfg.get("nameStyle", "full")            # "short" shows 'Gabby P.'; picks.json keeps the full names
    shown = short_names([p["name"] for p in picks["players"]]) if style == "short" else {p["name"]: p["name"] for p in picks["players"]}
    players = []
    for p in picks["players"]:
        out = []
        for k in p["picks"]:
            clean = by_norm.get(norm(k["movie"]))
            if not clean: die(f"{p['name']} picked '{k['movie']}', which isn't listed in data/movies.csv")
            out.append({"pick": k["pick"], "movie": clean, "scoring": bool(k.get("handPicked"))})
        players.append({"name": shown[p["name"]], "employed": p.get("employed", True), "picks": out})

    data = {
        "updated": date_of(dom_snap), "rtUpdated": date_of(rt_snap), "refreshDays": cfg.get("refreshEveryDays", 10),
        "enforce": cfg.get("enforce", {}), "season": cfg["season"], "penalty": cfg["penalty"], "rtThreshold": cfg["rtThreshold"],
        "movies": movies, "players": players,
    }
    before = load("data.json")
    save("data.json", data)

    # ---- report ----
    lines = [f"### Rebuilt data.json", f"- {len(players)} players, {len(movies)} movies; box office as of {data['updated']}, Rotten Tomatoes as of {data['rtUpdated']}"]
    if before:
        moved = sorted(((m["grossDom"] + m["grossMex"]) - (before["movies"].get(n, {}).get("grossDom", 0) + before["movies"].get(n, {}).get("grossMex", 0)), n) for n, m in movies.items())
        moved = [(d, n) for d, n in reversed(moved) if d > 0][:5]
        if moved: lines.append("- Biggest gross changes: " + "; ".join(f"{n} +${d:,}" for d, n in moved))
    if rt_changes: lines.append("- Rotten Tomatoes changes: " + "; ".join(rt_changes))
    if kept:
        for k in kept: warning("Kept previous gross because the new number dropped: " + k)
        lines.append("- ⚠️ Kept previous gross (new number was lower): " + "; ".join(kept))
    if unmatched: lines.append("- Not found on Box Office Mojo (scored $0, treated as unreleased): " + ", ".join(sorted(unmatched)))
    print("\n".join(lines)); summary("\n".join(lines))


if __name__ == "__main__":
    main()
