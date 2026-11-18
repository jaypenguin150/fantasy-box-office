"""Run with:  python3 tests/test_pipeline.py
Runs the real scripts against mock Box Office Mojo / OMDb servers (no internet needed)."""
import datetime, json, os, shutil, subprocess, sys, tempfile, threading, unittest, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)


def chart_html(rows, headers=("Rank", "Release", "Genre", "Budget", "Running Time", "Gross", "Theaters", "Total Gross", "Release Date", "Distributor", "Estimated")):
    """Mimic the shape of a Box Office Mojo yearly chart: nested links, stray whitespace, dash placeholders."""
    h = "".join(f"<th>{c}</th>" for c in headers)
    body = ""
    for i, r in enumerate(rows, 1):
        body += (f'<tr><td class="a-text-right">{i}</td><td class="a-text-left mojo-field-type-release"><a class="a-link-normal" href="/release/rl{i}/">{r["title"]}</a></td>'
                 f'<td>-</td><td>-</td><td>-</td><td class="a-text-right mojo-field-type-money">${r["gross"]:,}</td><td>4,000</td><td>${r["gross"]:,}</td>'
                 f'<td class="a-text-left">\n  {r["releaseDate"]}\n </td><td><a href="/studio/x/">{r["distributor"]}</a></td><td>false</td></tr>')
    return f"<html><body><div><table class='nav'><tr><td>menu</td></tr></table><table class='a-bordered'><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div></body></html>"


class Mock(BaseHTTPRequestHandler):
    state = {}

    def log_message(self, *a): pass

    def _send(self, code, body, ctype="text/html"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body.encode())

    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query); st = Mock.state
        if u.path.startswith("/year/"):
            if st.get("bom_status", 200) != 200: return self._send(st["bom_status"], "nope")
            key = "mex" if q.get("area") == ["MX"] else "dom"
            return self._send(200, st["pages"][key])
        if u.path == "/":  # OMDb
            if st.get("omdb_mode") == "badkey": return self._send(200, json.dumps({"Response": "False", "Error": "Invalid API key!"}), "application/json")
            if st.get("omdb_mode") == "limit": return self._send(200, json.dumps({"Response": "False", "Error": "Request limit reached!"}), "application/json")
            if "i" in q:
                hit = st["omdb_by_id"].get(q["i"][0])
            else:
                hit = st["omdb"].get((q["t"][0].lower(), q.get("y", [""])[0]))
            return self._send(200, json.dumps(hit or {"Response": "False", "Error": "Movie not found!"}), "application/json")
        self._send(404, "")


def omdb_record(title, year, rt, imdb="tt0000001"):
    r = {"Title": title, "Year": str(year), "imdbID": imdb, "Response": "True", "Ratings": [{"Source": "Internet Movie Database", "Value": "7.0/10"}]}
    if rt is not None: r["Ratings"].append({"Source": "Rotten Tomatoes", "Value": f"{rt}%"})
    return r


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls): cls.server.shutdown()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        shutil.copytree(os.path.join(ROOT, "data"), self.data)
        self.dom, self.mex = self.j("bom_domestic.json")["rows"], self.j("bom_mexico.json")["rows"]
        Mock.state = {"pages": {"dom": chart_html(self.dom), "mex": chart_html(self.mex)}, "omdb": {}, "omdb_by_id": {}}

    def tearDown(self): shutil.rmtree(self.tmp)

    def run_script(self, name, **env):
        e = {**os.environ, "FBO_DATA_DIR": self.data, "BOM_BASE": self.url, "OMDB_BASE": self.url + "/", "BOM_PAUSE": "0", "OMDB_PAUSE": "0", "OMDB_API_KEY": "testkey", **env}
        e = {k: v for k, v in e.items() if v is not None}
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, name)], env=e, capture_output=True, text=True)

    def snapshot(self):
        out = {}
        for dirpath, _, files in os.walk(self.data):
            for f in sorted(files):
                path = os.path.join(dirpath, f)
                with open(path, "rb") as fh: out[os.path.relpath(path, self.data)] = fh.read()
        return out

    def j(self, name):
        with open(os.path.join(self.data, name)) as f: return json.load(f)

    def put(self, name, obj):
        with open(os.path.join(self.data, name), "w") as f: json.dump(obj, f)

    def edit_movies_csv(self, fn):
        import csv
        p = os.path.join(self.data, "movies.csv")
        with open(p, newline="") as f: rows = list(csv.DictReader(f))
        for r in rows: fn(r)
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(rows)


class TestBom(Base):
    def test_parser_reads_realistic_markup(self):
        import fetch_bom
        rows = fetch_bom.parse_chart(chart_html(self.dom))
        self.assertEqual(len(rows), len(self.dom))
        self.assertEqual(rows[0], self.dom[0])
        self.assertEqual(rows[2]["releaseDate"], self.dom[2]["releaseDate"])  # whitespace around the date is cleaned

    def test_success_updates_both_files(self):
        bumped = [dict(r, gross=r["gross"] + 1_000_000) for r in self.dom]
        Mock.state["pages"]["dom"] = chart_html(bumped)
        r = self.run_script("fetch_bom.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        d = self.j("bom_domestic.json")
        self.assertIsNotNone(d["fetchedAt"]); self.assertEqual(d["rows"][0]["gross"], self.dom[0]["gross"] + 1_000_000)
        self.assertEqual(len(self.j("bom_mexico.json")["rows"]), len(self.mex))

    def test_blocked_leaves_data_untouched(self):
        before = self.snapshot(); Mock.state["bom_status"] = 403
        r = self.run_script("fetch_bom.py")
        self.assertEqual(r.returncode, 1); self.assertIn("refused", r.stdout)
        self.assertEqual(before, self.snapshot())

    def test_layout_change_leaves_data_untouched(self):
        before = self.snapshot(); Mock.state["pages"]["dom"] = "<html><body><div>redesigned page</div></body></html>"
        r = self.run_script("fetch_bom.py")
        self.assertEqual(r.returncode, 1); self.assertEqual(before, self.snapshot())

    def test_truncated_page_rejected(self):
        before = self.snapshot(); Mock.state["pages"]["dom"] = chart_html(self.dom[:20])
        r = self.run_script("fetch_bom.py")
        self.assertEqual(r.returncode, 1); self.assertIn("incomplete", r.stdout); self.assertEqual(before, self.snapshot())

    def test_second_page_failure_saves_nothing(self):
        before = self.snapshot(); Mock.state["pages"]["mex"] = chart_html(self.mex[:5])
        r = self.run_script("fetch_bom.py")
        self.assertEqual(r.returncode, 1); self.assertEqual(before, self.snapshot())  # US page was fine but nothing saved


class TestCsvFallback(Base):
    def write_csv(self, name, rows, header="Rank,Release,Genre,Budget,Running Time,Gross,Theaters,Total Gross,Release Date,Distributor,Estimated"):
        os.makedirs(os.path.join(self.data, "manual"), exist_ok=True)
        with open(os.path.join(self.data, "manual", name), "w", encoding="utf-8-sig", newline="") as f:
            f.write(header + "\n")
            for i, r in enumerate(rows, 1):
                f.write(f'{i},"{r["title"]}",-,-,-,"${r["gross"]:,}",4000,"${r["gross"]:,}",{r["date"]},"{r["distributor"]}",false\n')

    def test_import_normalises_excel_dates_and_updates(self):
        conv = lambda rows: [dict(title=r["title"], gross=r["gross"] + 3_000_000, date="6/14/2024", distributor=r["distributor"]) for r in rows]
        self.write_csv("domestic.csv", conv(self.dom)); self.write_csv("mexico.csv", conv(self.mex))
        r = self.run_script("import_bom_csv.py"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        d = self.j("bom_domestic.json"); self.assertEqual(d["rows"][0]["releaseDate"], "Jun 14")
        self.assertEqual(d["rows"][0]["gross"], self.dom[0]["gross"] + 3_000_000); self.assertIn("uploaded", d["source"])
        self.assertEqual(self.run_script("build_data.py").returncode, 0)
        self.assertEqual(self.j("data.json")["movies"]["Wicked"]["month"], "Jun")

    def test_missing_files_fail_cleanly(self):
        before = self.snapshot(); r = self.run_script("import_bom_csv.py")
        self.assertEqual(r.returncode, 1); self.assertIn("wasn't found", r.stdout); self.assertEqual(before, self.snapshot())

    def test_wrong_columns_rejected(self):
        self.write_csv("domestic.csv", [], header="Foo,Bar"); self.write_csv("mexico.csv", [], header="Foo,Bar")
        before = self.snapshot(); r = self.run_script("import_bom_csv.py")
        self.assertEqual(r.returncode, 1); self.assertEqual(before, self.snapshot())


class TestRt(Base):
    def setUp(self):
        super().setUp()
        s = Mock.state["omdb"]
        s[("deadpool & wolverine", "2024")] = omdb_record("Deadpool & Wolverine", 2024, 78, "tt6263850")
        s[("anyone but you", "2023")] = omdb_record("Anyone But You", 2023, 56, "tt26047818")   # found only via the year before
        s[("mean girls", "2024")] = omdb_record("Mean Girls", 2004, 84)                         # wrong film: 2004 original
        s[("wicked", "2024")] = omdb_record("Wicked", 2024, None)                               # no RT score yet
        s[("inside out 2", "2024")] = omdb_record("Inside Out 2", 2024, 91)                      # unchanged

    def test_scores_updated_and_edge_cases(self):
        before = self.j("rt_scores.json")["scores"]
        r = self.run_script("fetch_rt.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sc = self.j("rt_scores.json"); s = sc["scores"]
        self.assertEqual(s["Deadpool & Wolverine"]["score"], 0.78); self.assertEqual(s["Deadpool & Wolverine"]["source"], "omdb")
        self.assertEqual(s["Anyone But You"]["score"], 0.56)                               # year-1 fallback worked
        self.assertEqual(s["Mean Girls"]["score"], before["Mean Girls"]["score"])           # wrong-year match rejected
        self.assertEqual(s["Wicked"]["score"], before["Wicked"]["score"])                   # missing RT keeps old value
        self.assertIsNotNone(sc["fetchedAt"]); self.assertIn("doesn't look right", r.stdout)
        self.assertIn("Deadpool & Wolverine:", r.stdout)                                    # change listed in report

    def test_unreleased_movies_not_looked_up(self):
        Mock.state["omdb"][("luca", "2024")] = omdb_record("Luca", 2024, 99)
        self.run_script("fetch_rt.py")
        self.assertNotEqual(self.j("rt_scores.json")["scores"]["Luca"]["source"], "omdb")  # not on the BOM chart, so skipped

    def test_imdb_id_override(self):
        def setid(r):
            if r["movie"] == "Wicked": r["imdb_id"] = "tt1262426"
        self.edit_movies_csv(setid)
        Mock.state["omdb"].pop(("wicked", "2024"), None)                  # title search would find nothing...
        Mock.state["omdb_by_id"]["tt1262426"] = omdb_record("Wicked", 2024, 77, "tt1262426")   # ...but the id works
        self.run_script("fetch_rt.py")
        self.assertEqual(self.j("rt_scores.json")["scores"]["Wicked"]["score"], 0.77)

    def test_missing_key_skips_quietly(self):
        before = self.snapshot(); r = self.run_script("fetch_rt.py", OMDB_API_KEY="")
        self.assertEqual(r.returncode, 0); self.assertIn("OMDB_API_KEY", r.stdout); self.assertEqual(before, self.snapshot())

    def test_bad_key_fails_without_saving(self):
        before = self.snapshot(); Mock.state["omdb_mode"] = "badkey"; r = self.run_script("fetch_rt.py")
        self.assertEqual(r.returncode, 1); self.assertIn("key", r.stdout.lower()); self.assertEqual(before, self.snapshot())

    def test_rate_limit_fails_without_saving(self):
        before = self.snapshot(); Mock.state["omdb_mode"] = "limit"; r = self.run_script("fetch_rt.py")
        self.assertEqual(r.returncode, 1); self.assertIn("limit", r.stdout.lower()); self.assertEqual(before, self.snapshot())


class TestDue(Base):
    def due(self, **env):
        out = os.path.join(self.tmp, "out.txt")
        with open(out, "w"): pass
        r = self.run_script("due.py", GITHUB_OUTPUT=out, **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out) as f: got = dict(l.split("=") for l in f.read().split())
        got.pop("csv", None); return got

    def stamp(self, name, days_ago):
        d = self.j(name); d["fetchedAt"] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)).isoformat()
        self.put(name, d)

    def test_never_fetched_is_due(self): self.assertEqual(self.due(EVENT_NAME="schedule"), {"bom": "true", "rt": "true"})

    def test_ten_day_gate(self):
        for n in ("bom_domestic.json", "rt_scores.json"): self.stamp(n, 3)
        self.assertEqual(self.due(EVENT_NAME="schedule"), {"bom": "false", "rt": "false"})
        self.stamp("bom_domestic.json", 9.9)  # within the few-hours slack
        self.assertEqual(self.due(EVENT_NAME="schedule")["bom"], "true")
        self.stamp("bom_domestic.json", 11); self.stamp("rt_scores.json", 10.2)
        self.assertEqual(self.due(EVENT_NAME="schedule"), {"bom": "true", "rt": "true"})

    def test_manual_button_ignores_gate_and_respects_checkboxes(self):
        for n in ("bom_domestic.json", "rt_scores.json"): self.stamp(n, 0.1)
        self.assertEqual(self.due(EVENT_NAME="workflow_dispatch", REFRESH_BOM="true", REFRESH_RT="true"), {"bom": "true", "rt": "true"})
        self.assertEqual(self.due(EVENT_NAME="workflow_dispatch", REFRESH_BOM="false", REFRESH_RT="true"), {"bom": "false", "rt": "true"})


class TestBuild(Base):
    def _committed(self):
        with open(os.path.join(ROOT, "data", "data.json")) as f: return json.load(f)

    def build(self):
        r = self.run_script("build_data.py"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr); return r

    def test_rebuild_matches_committed_data(self):
        self.build(); a, b = self.j("data.json"), self._committed()
        self.assertEqual(a["movies"], b["movies"]); self.assertEqual(a["players"], b["players"])

    def test_gross_drop_is_ignored_but_increase_accepted(self):
        d = self.j("bom_domestic.json")
        d["rows"][0]["gross"] = int(d["rows"][0]["gross"] * 0.5); d["rows"][1]["gross"] += 5_000_000
        self.put("bom_domestic.json", d)
        prev = self.j("data.json")["movies"]; r = self.build(); now = self.j("data.json")["movies"]
        t0, t1 = d["rows"][0]["title"], d["rows"][1]["title"]
        self.assertEqual(now[t0]["grossDom"], prev[t0]["grossDom"]); self.assertIn("Kept previous gross", r.stdout)
        self.assertEqual(now[t1]["grossDom"], prev[t1]["grossDom"] + 5_000_000)

    def test_missing_movie_keeps_previous_gross(self):
        d = self.j("bom_domestic.json"); gone = d["rows"][0]["title"]; d["rows"] = d["rows"][1:]
        self.put("bom_domestic.json", d)
        prev = self.j("data.json")["movies"][gone]["grossDom"]; self.build()
        self.assertEqual(self.j("data.json")["movies"][gone]["grossDom"], prev)

    def test_rt_override_beats_fetched_score(self):
        def setov(r):
            if r["movie"] == "Wicked": r["rt_override"] = "40%"
        self.edit_movies_csv(setov)
        self.build(); self.assertEqual(self.j("data.json")["movies"]["Wicked"]["rt"], 0.4)

    def test_unknown_pick_fails_loudly(self):
        pk = self.j("picks.json"); pk["players"][0]["picks"][0]["movie"] = "Not A Real Movie"
        self.put("picks.json", pk)
        r = self.run_script("build_data.py"); self.assertEqual(r.returncode, 1); self.assertIn("Not A Real Movie", r.stdout)


class TestEndToEnd(Base):
    def test_full_refresh(self):
        Mock.state["pages"]["dom"] = chart_html([dict(r, gross=r["gross"] + 2_000_000) for r in self.dom])
        Mock.state["omdb"][("wicked", "2024")] = omdb_record("Wicked", 2024, 30)  # drops to the penalty zone
        for step in ("fetch_bom.py", "fetch_rt.py", "build_data.py"):
            r = self.run_script(step); self.assertEqual(r.returncode, 0, step + r.stdout + r.stderr)
        d = self.j("data.json")
        self.assertEqual(d["movies"]["Wicked"]["rt"], 0.30)
        self.assertEqual(d["updated"], datetime.datetime.now(datetime.timezone.utc).date().isoformat())
        # and the website's scoring engine accepts the rebuilt file
        out = subprocess.run(["node", "-e", f'const {{evaluate}}=require("{ROOT}/scoring.js");const r=evaluate(require("{self.data}/data.json"));console.log(r.players.length, r.players.every(p=>Number.isFinite(p.adjusted)))'], capture_output=True, text=True)
        self.assertEqual(out.stdout.split(), ["21", "true"], out.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
