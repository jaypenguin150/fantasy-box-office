"""Small helpers shared by the refresh scripts. Standard library only."""
import datetime, json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = pathlib.Path(os.environ.get("FBO_DATA_DIR", ROOT / "data"))


def load(name, default=None):
    p = DATA / name
    if not p.exists():
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = DATA / (name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, DATA / name)  # atomic: a crash never leaves a half-written file


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def age_days(iso):
    t = datetime.datetime.fromisoformat(iso)
    return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 86400


def norm(s):
    """Case- and whitespace-insensitive key (Excel's XLOOKUP matched this way too)."""
    return " ".join(str(s).split()).lower()


def money(v):
    s = "".join(ch for ch in str(v) if ch.isdigit())
    return int(s) if s else 0


# GitHub Actions shows these lines as coloured annotations on the run page.
def notice(msg): print(f"::notice::{msg}")
def warning(msg): print(f"::warning::{msg}")
def error(msg): print(f"::error::{msg}")


def summary(md):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(md + "\n")


def set_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    line = f"{name}={value}"
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    print(line)
