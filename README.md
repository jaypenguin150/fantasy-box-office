# Fantasy Box Office 2024

A scoreboard website that refreshes itself. Box office grosses come from Box Office Mojo, Rotten Tomatoes scores come from OMDb, and the site rebuilds its numbers in your browser from plain files in this repo.

## How it works

```
every 10 days (or when you press the button)
   Box Office Mojo  ->  data/bom_domestic.json, data/bom_mexico.json
   OMDb             ->  data/rt_scores.json
   + data/picks.json (who picked what) + data/movies.csv (sequel flags, overrides)
   ->  scripts/build_data.py  ->  data/data.json  ->  the website (index.html)
```

A GitHub "Action" (`.github/workflows/refresh.yml`) runs once a day, but only refreshes when the data is 10 days old. You can also run it yourself at any time.

## One-time setup

**1. Upload the files.** Upload everything in this folder to your repository (Add file → Upload files). Files with the same name are replaced.

The workflow file lives in a hidden folder (`.github/workflows/`), which is easy to miss when dragging files. The safest way is to create it directly on GitHub: **Add file → Create new file**, type `.github/workflows/refresh.yml` as the name (typing the slashes creates the folders), paste in the contents of `refresh.yml` from this download, and click **Commit changes**.

**2. Get a free OMDb key.** Go to https://www.omdbapi.com/apikey.aspx, choose the free tier, enter your email, and click the activation link in the email they send. (The free key allows 1,000 lookups a day; this uses about 50 per refresh.)

**3. Save the key in GitHub.** In your repository: **Settings → Secrets and variables → Actions → New repository secret**. Name it exactly `OMDB_API_KEY` and paste the key as the value. The key is hidden after you save it and is never shown in logs.

**4. Check the permissions.** **Settings → Actions → General → Workflow permissions**: choose **Read and write permissions** and save. (Needed so the job can save the refreshed files. Your organization may already allow this.)

**5. Run it once.** Open the **Actions** tab → **Refresh data** (left side) → **Run workflow** → **Run workflow**. It takes about a minute. A green check means success; open the run to see a summary of what changed.

## Day to day

- **Nothing to do.** It refreshes itself every 10 days. If anything fails, GitHub emails the repository owner.
- **Refresh now:** Actions → Refresh data → Run workflow. You get three tick boxes:
  - *Refresh Box Office Mojo grosses* (on by default)
  - *Refresh Rotten Tomatoes scores* (on by default)
  - *Box Office Mojo is blocked: use the CSV files from data/manual* (off; see below)
- **See what happened:** click the run, then click **Summary**. It lists biggest gross changes, Rotten Tomatoes changes, and anything needing attention.

## Editing the data

Edit files right on GitHub: open the file, click the pencil icon, make the change, click **Commit changes**. Editing `movies.csv`, `picks.json` or `config.json` rebuilds the site data automatically within a minute.

**`data/movies.csv`** has one row per movie:

| column | what it does |
|---|---|
| `movie` | the clean name; must match Box Office Mojo's title (capitalization and extra spaces don't matter) |
| `franchise` | `1` if you count it as a sequel/franchise movie, otherwise `0` |
| `rt_override` | optional. A score like `45` or `45%` here beats whatever OMDb says |
| `omdb_title` | optional. Use if OMDb knows the movie under a different title |
| `imdb_id` | optional. Looks the movie up by IMDb ID (like `tt1262426`) instead of by title; the most reliable fix when a movie is mismatched |

**`data/config.json`**: the season, the $75M penalty, the 45% Rotten Tomatoes cutoff, how many days between refreshes (`refreshEveryDays`), and the rule switches (`enforce`).

Rotten Tomatoes problems show up as yellow warnings in the run (for example "not found on OMDb" or "matched the wrong year"). Fix them by adding an `imdb_id` or `rt_override` in `movies.csv`.

## If a refresh fails

The failed step stops without changing anything, so the site keeps showing the last good data.

- **"Box Office Mojo refused the request (HTTP 403)"**: Box Office Mojo is blocking GitHub's servers. Use the manual fallback: in Excel, save your two Box Office Mojo tabs (US and Mexico) as CSV files. Upload them to the `data/manual/` folder as `domestic.csv` and `mexico.csv`. Then run the workflow with only the CSV box ticked (untick the Rotten Tomatoes box if you like). They need the columns `Release`, `Gross`, `Release Date`, `Distributor`.
- **"couldn't find the chart table"**: Box Office Mojo changed its page layout. Use the CSV fallback and let whoever maintains this know.
- **"incomplete" / "shares only X% of its titles"**: the page that came back looked wrong. The safety checks refused it. Try again later.
- **OMDb "invalid API key"**: re-check the `OMDB_API_KEY` secret and that you clicked the activation link in the OMDb email.
- **OMDb "limit reached"**: try again tomorrow.
- **The site doesn't show new numbers**: wait a couple of minutes (GitHub Pages republishes after each save), then hard-refresh the page.
- **The daily check stopped running**: GitHub pauses scheduled jobs in repositories with no activity for 60 days. Go to the Actions tab and click **Enable workflow**.

## Safety checks built in

- Nothing is saved unless both Box Office Mojo pages download and look sane (enough rows, real numbers, mostly the same titles as last time).
- A movie's gross can never drop by more than 2% in a refresh (grosses only grow). If it would, the previous number is kept and a warning is shown.
- A Rotten Tomatoes lookup that matches the wrong year, or returns no score, keeps the previous score.

## About the Box Office Mojo pull

Box Office Mojo's conditions of use restrict automated access without written consent. This repo requests two pages once every 10 days and identifies itself honestly in the request. If you want explicit permission, IMDb's licensing team is at imdb-licensing@imdb.com. You can also stop the automatic pull at any time by using only the CSV fallback.

## Rules and scoring

- Mexico is always included: a movie scores its US plus Mexico gross for the calendar year.
- Each player's scoring movies are the highest-revenue **legal** set from their 12 greenlit movies: at most 5 released May–September, at most 6 sequels/franchise movies, at least 3 distributors, fewer than 5 from one distributor. If no legal 9 exists, the best legal 8 is used, then 7, and so on.
- A movie with a Rotten Tomatoes score of 45% or lower loses $75M (never below $0).
- Players who aren't employed are left out of the prize standing.

The original workbook never enforced the sequel cap, left September out of the summer cap, never added Mexico, and `Engine!F6` summed unpenalised gross. This site fixes all four.

## Testing (optional)

```
python3 tests/test_pipeline.py       # runs the refresh scripts against mock Box Office Mojo / OMDb servers
python3 tests/simulate_workflow.py   # dry-runs the whole GitHub workflow against a fake remote
node tests/verify.js                 # proves the scoring matches the original workbook
```

`scripts/import_from_workbook.py` was the one-time import from the original Excel file; you don't need it again.
