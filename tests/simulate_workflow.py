"""Dry-run of .github/workflows/refresh.yml: same scripts, same shell commands, a local fake 'GitHub' remote.
    python3 tests/simulate_workflow.py"""
import json, os, re, shutil, subprocess, sys, tempfile, threading
from http.server import ThreadingHTTPServer
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_pipeline as T

ROOT = T.ROOT
tmp = tempfile.mkdtemp()
remote, work = os.path.join(tmp, "remote.git"), os.path.join(tmp, "work")
sh = lambda cmd, cwd=None, env=None: subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True, text=True)
sh(f"git init -q --bare {remote}")
shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
for c in ("git init -q -b main", "git add -A", 'git -c user.name=t -c user.email=t@t commit -qm seed', f"git remote add origin {remote}", "git push -q -u origin main"):
    assert sh(c, work).returncode == 0, c

srv = ThreadingHTTPServer(("127.0.0.1", 0), T.Mock); threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}"
with open(os.path.join(work, "data", "bom_domestic.json")) as f: dom = json.load(f)["rows"]
with open(os.path.join(work, "data", "bom_mexico.json")) as f: mex = json.load(f)["rows"]
T.Mock.state = {"pages": {"dom": T.chart_html([dict(r, gross=r["gross"] + 1_500_000) for r in dom]), "mex": T.chart_html(mex)},
                "omdb": {("wicked", "2024"): T.omdb_record("Wicked", 2024, 35)}, "omdb_by_id": {}}

# the workflow's shell step, copied verbatim from the YAML
yml = open(os.path.join(work, ".github/workflows/refresh.yml")).read()
save_script = re.search(r"- name: Save changes.*?run: \|\n(.*?)\n\n      - name", yml, re.S).group(1)
save_script = "\n".join(l[10:] for l in save_script.splitlines())


def run_workflow(event, **inputs):
    out = os.path.join(tmp, "gh_output.txt"); open(out, "w").close()
    base = {**os.environ, "GITHUB_OUTPUT": out, "BOM_BASE": url, "OMDB_BASE": url + "/", "BOM_PAUSE": "0", "OMDB_PAUSE": "0", "OMDB_API_KEY": "k"}
    env = {**base, "EVENT_NAME": event, **{k.upper(): str(v).lower() for k, v in inputs.items()}}
    py = lambda s, e=env: sh(f"{sys.executable} scripts/{s}", work, e)
    print(py("due.py").stdout.strip().replace("\n", " | "))
    o = dict(l.split("=") for l in open(out).read().split())
    if o["bom"] == "true": print(" fetch_bom:", "ok" if py("fetch_bom.py").returncode == 0 else "FAILED")
    if o["rt"] == "true": print(" fetch_rt :", "ok" if py("fetch_rt.py").returncode == 0 else "FAILED")
    if o["bom"] == "true" or o["rt"] == "true" or event == "push":
        print(" build    :", "ok" if py("build_data.py").returncode == 0 else "FAILED")
        r = sh(save_script, work, env); print(" save     :", (r.stdout + r.stderr).strip().splitlines()[-1])


print("--- run 1: scheduled, data never fetched ---"); run_workflow("schedule")
print("--- run 2: scheduled again right away (gate should skip) ---"); run_workflow("schedule")
print("--- run 3: manual button, RT only ---"); T.Mock.state["omdb"][("wicked", "2024")] = T.omdb_record("Wicked", 2024, 36)
run_workflow("workflow_dispatch", refresh_bom=False, refresh_rt=True, use_csv=False)
print("--- run 4: someone edits a sequel flag in movies.csv (push trigger) ---")
p = os.path.join(work, "data", "movies.csv"); txt = open(p).read()
open(p, "w").write(txt.replace("Wicked,0,", "Wicked,1,", 1)); sh('git -c user.name=t -c user.email=t@t commit -qam "edit flag" && git push -q', work)
run_workflow("push")
log = sh("git log main --oneline", remote).stdout.strip(); print("--- commits on the fake GitHub remote ---\n" + log)
d = json.loads(sh("git show main:data/data.json", remote).stdout)
print("remote data.json: Wicked franchise =", d["movies"]["Wicked"]["franchise"], "| Wicked rt =", d["movies"]["Wicked"]["rt"], "| Inside Out 2 gross =", f'{d["movies"]["Inside Out 2"]["grossDom"]:,}', "| updated =", d["updated"], "| rtUpdated =", d["rtUpdated"])
srv.shutdown(); shutil.rmtree(tmp)
