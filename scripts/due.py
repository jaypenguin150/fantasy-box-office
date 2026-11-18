"""Decide which refreshes should run. Writes `bom=true|false` and `rt=true|false` for the workflow.

Scheduled runs happen daily but only refresh when the data is at least `refreshEveryDays` (default 10) old.
Manual runs ("Run workflow" button) always refresh whatever the checkboxes ask for.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, age_days, set_output

cfg = load("config.json", {})
days = cfg.get("refreshEveryDays", 10)


def due(snapshot):
    if not snapshot or not snapshot.get("fetchedAt"):
        return True
    return age_days(snapshot["fetchedAt"]) >= days - 0.25  # a few hours of slack so the daily check lands on day 10


if os.environ.get("EVENT_NAME") == "workflow_dispatch":
    bom = os.environ.get("REFRESH_BOM", "true") == "true"
    rt = os.environ.get("REFRESH_RT", "true") == "true"
    print("Manual run: refreshing what was ticked.")
    set_output("csv", str(os.environ.get("USE_CSV", "false") == "true").lower())
elif os.environ.get("EVENT_NAME") == "push":
    bom = rt = False
    print("Data files were edited: rebuilding data.json only (no web requests).")
    set_output("csv", "false")
else:
    bom, rt = due(load("bom_domestic.json")), due(load("rt_scores.json"))
    print(f"Scheduled check (refresh every {days} days).")
    set_output("csv", "false")
set_output("bom", str(bom).lower())
set_output("rt", str(rt).lower())
if not (bom or rt) and os.environ.get("EVENT_NAME") != "push":
    print("Nothing is due yet.")
