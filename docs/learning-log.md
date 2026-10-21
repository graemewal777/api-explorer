# Learning log

One entry per milestone: what we did, and the GitHub idea it taught.

## M0: repo and submodule

- Created a new public repo instead of forking `public-apis`. Scheduled Actions are disabled by default on forks, and we want a nightly job later.
- `git submodule add --depth 1` pulled in `public-apis` shallow (about 500 KB instead of its full history). `shallow = true` in `.gitmodules` makes later updates shallow too.
- The submodule is a pin: this repo stores one commit hash for `vendor/public-apis`, not the files. Upstream's default branch is `master`, not `main`.
- Gotcha: a plain `git clone` leaves the submodule folder empty. See the README.

## M1: parser

- Built `scripts/build.py` (Python standard library only) and 15 tests in `tests/`. Run them with `python3 -m unittest discover -s tests`.
- Wrote the tests first, watched them fail, then made them pass (red, then green).
- **The plan assumed one table format. The real README has three.** The standard category tables start at `### Animals`; the preamble also holds a 3-column promo table and an MCP-server table with other columns. The parser reads a table only when its header is exactly `API | Description | Auth | HTTPS | CORS`, and skips the rest.
- **The sanity guard caught a real problem on its first run on real data**: 106 rows failed (over 1%) and the build stopped. 104 had an extra empty trailing cell, one had two, and one (MapQuest) had no closing `|` and a stray fifth value. The fix tolerates trailing empties and counts non-empty extras as "ragged" (2 today) instead of dropping them.
- Cross-check: parser says 2,169 APIs in 51 categories; an independent `awk` count of rows inside standard tables also says 2,169. The other 33 rows of the README's 2,202 are the promo and MCP tables.
- Two APIs (TasteDive, Open-Meteo) appear in two categories upstream, so they appear twice here on purpose.
- Output: `site/apis.json`, gitignored because the nightly job regenerates it.

## M2: the site

- Plain HTML, CSS and JavaScript in `site/`, no framework and no build step. `site/filter.js` holds the pure logic (search, filters, URL hash) and `site/app.js` does the DOM work. Keeping them apart lets the logic run in Node tests as well as the browser.
- Filters: search text (every word must match name, description or category), category, "No API key needed", "HTTPS only", and "Works from a browser (CORS)". Filter state lives in the URL hash, so a filtered view is a shareable link, for example `#q=bitcoin&nokey=1`.
- Run the JS tests with `node --test tests/filter.test.js` (12 tests). `node --test tests/` fails on Node 24: it treats the folder as a file.
- Sanity-checked the tests by breaking the HTTPS filter on purpose: one test failed, then the original file went back.
- Checked in a real browser against counts computed separately in Python: search "weather" gives 56, Weather plus all three toggles gives 13, the three toggles alone give 516, and the deep link `#q=bitcoin&nokey=1` gives 12. All matched.
- Safety: the data comes from a list anyone can edit upstream, so cards are built with `textContent` (never `innerHTML`) and links only use `http(s)` URLs with `rel="noopener noreferrer"`.
- To view it locally: `python3 scripts/build.py`, then `cd site && python3 -m http.server 8765` and open http://127.0.0.1:8765/. The page needs `site/apis.json`, which is generated and gitignored.

## M3: Pages deploy workflow

- `.github/workflows/deploy.yml` runs on every push to `main`, and from the "Run workflow" button (`workflow_dispatch`). The nightly schedule comes in M4.
- Two jobs. `build` checks out with `submodules: true`, runs both test suites, runs `scripts/build.py`, and uploads `site/` as the Pages artifact. `deploy` only runs if `build` passed, so a failing test blocks the deploy.
- Permissions are the minimum: `contents: read`, `pages: write`, `id-token: write`. The deploy job uses a `github-pages` environment, which is where the live URL is reported.
- `concurrency: pages` with `cancel-in-progress: false` stops two deploys running at once without killing one already in progress.
- Looked up the current releases of each action instead of guessing: `checkout` v7, `configure-pages` v6, `upload-pages-artifact` v5, `deploy-pages` v5. Tags like `@v7` follow the newest v7; pinning to a full commit hash is stricter but needs manual updates.
- Pages must be switched on once in the repo settings with the source set to "GitHub Actions" (not "Deploy from a branch"). Before that, the deploy job has nowhere to publish, so enabling it comes before merging this workflow.
- **Result (live):** Pages enabled with source "GitHub Actions"; merging the PR started the first deploy automatically and it passed in about 20 seconds. Live site: https://graemewal777.github.io/api-explorer/. The live `apis.json` matched the local build (2,169 APIs at upstream commit `339ab55`), a four-filter deep link gave 16 results (independent count: 16), and the console was clean.
- The first run warned that `ubuntu-latest` is migrating to Ubuntu 26 from October 19, 2026. M4 pins Python and Node explicitly so a runner image change can't silently break the build.

## M4: nightly sync

- The workflow now also runs on a schedule (`17 3 * * *`, 03:17 UTC daily; an off-the-hour minute avoids the busiest queue times) and from the manual button. Scheduled runs use the default branch only.
- `scripts/bump-submodule.sh` moves the `vendor/public-apis` pin to upstream's latest commit and commits it as `github-actions[bot]`, with a compare link in the message. It does nothing if the pin is current, and it never pushes. Keeping it as a script (not inline YAML) meant I could test it on this machine first: no-op case, real bump from an old pin, bot commit, and a clean second run all behaved.
- `.gitmodules` now says `branch = master`, so `git submodule update --remote` follows upstream's default branch on purpose, not by default.
- The bump step runs only for scheduled or manual runs **and** only on `refs/heads/main`. Without the branch guard, a manual run from a feature branch would push that branch's commits to `main`.
- The bump is pushed with the default `GITHUB_TOKEN`. Pushes made that way do **not** start other workflow runs, which is why bump and deploy live in one workflow: the same run goes on to build and deploy the bumped tree.
- Permissions are per job: `build` gets `contents: write` and `pages: write`; `deploy` gets `pages: write` and `id-token: write`. Everything else is read-only.
- Still to watch: scheduled workflows in public repos are disabled after 60 days without repo activity. Upstream changes most days, so bumps should keep the repo active, but it is unconfirmed. Check the Actions tab now and then.

### M4 proof (run 2026-10-21)

Tested the bump path end to end on GitHub, not just locally:

| Step | Live site | Evidence |
|---|---|---|
| Baseline | 2,169 APIs at upstream `339ab55` | First run of the new workflow, pushed to `main`, passed |
| Pin to old commit (PR #6) | **1,954 APIs at `87ae94a`** (2026-09-30) | Merged, deploy passed, live `apis.json` showed 1,954 |
| Manual "Run workflow" on `main` | Bump step logged `bumped public-apis 87ae94a -> 339ab55` | Bot pushed `287c700` to `main`, same run built and deployed |
| After | **2,169 APIs at `339ab55`** | Live `apis.json` matched upstream's latest commit |

- The bot commit (`github-actions[bot]`, "Bump public-apis to 339ab55") sits in `main`'s history with the compare link in its body.
- **Confirmed:** no workflow run exists for the bot's commit. A push made with `GITHUB_TOKEN` does not start another run, so the single-workflow design was necessary, not just tidy.
- The schedule is registered and the workflow is `active`. The first scheduled run is due at 03:17 UTC the next day, which is still to be confirmed. Scheduled runs only fire from the default branch, and GitHub can delay them under load.
- Upstream got 265 new APIs and lost 50 in the three weeks between the two commits, so the pin goes stale quickly without this job.

## Link health check

Plan: nightly job that probes every API URL, remembers failures across nights, and flags links that keep failing. Milestones H0 to H4; each is a branch and a PR.

### H0: the probe engine

- `scripts/healthcheck.py` (`classify` and `probe`) and `tests/test_healthcheck.py` (18 tests, run against a local test server that plays every kind of misbehaving site: 404, 410, 500, 403, HEAD-rejected-but-GET-works, redirects, a redirect loop, a slow endpoint, a flaky endpoint, Cloudflare challenge pages, a closed port, an unresolvable host).
- **Why curl, not Python.** A first sample with Python's `urllib` on this Mac flagged 35 of 40 healthy sites (including github.com) as broken: that Python build has no certificate bundle. A health checker's biggest risk is false positives caused by its own environment. `curl` uses the system certificates. The canary guard planned for H1 covers the same risk at run time.
- **Classes.** `ok`; `blocked` (reachable but refuses bots: any 4xx other than 404 and 410, plus 999 and Cloudflare challenge pages) which is **not** a failure; failures are `gone` (404, 410), `error` (5xx), `dns`, `refused`, `timeout`, `tls`, `network`. Cloudflare's 52x "origin is down" codes stay real failures, only its 403 and 503 challenges count as blocked.
- Probe order: HEAD, then GET if HEAD is not ok (15 of 80 sampled URLs needed the GET). One retry after 2 seconds on any failure.
- **Safety.** URLs come from a list anyone can edit. `curl` is restricted to http and https (`--proto`, `--proto-redir`) so `file://` and friends are never fetched, and `--` before the URL stops a URL such as `--version` being read as an option. A missing `curl` raises an error instead of marking every link dead.
- **Mutation checks found redundant code.** Removing `403` from my explicit bot-block list broke no test, because the catch-all "other 4xx means blocked" rule already covered it. I deleted the dead list and kept the rule that does the work; after that, every rule I mutated made a test fail. I also corrected one test of my own: a bare `--version` is a hostname that fails DNS (`dns`), not a `network` error, and `dns` is the result that proves the `--` guard works.
- **Real-world check.** `probe()` over the same 80 real URLs as my earlier hand calibration (same random seed) gave 68 ok, 7 blocked, 2 timeouts, 2 gone, 1 DNS failure: identical. The same two sites still time out after a retry, which is why a link must fail three runs in a row before the site calls it dead.
- Run the tests with `python3 -m unittest discover -s tests`.
