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

### H1: state, runner, canary guard and CLI

- Added to `scripts/healthcheck.py`: `update_state` (failure counter per URL, capped at 5, `first_failed` kept, cleared by `ok` or `blocked`), `load_state` and `save_state` (sorted, deterministic, written via a temp file), `interleave_by_host`, `run` (25 workers, one request at a time per host with 0.5s spacing), `canaries_ok`, and a CLI (`python3 scripts/healthcheck.py`, flags `--dry-run`, `--limit`, `--state`, `--workers`, `--spacing`, `--min-urls`).
- Three failure modes the tests pin down on purpose:
  - A **damaged state file stops the run** (loaded before any probing, so it fails in seconds). Silently starting over would reset every counter.
  - The **canary guard** probes 5 near-certain-to-be-up sites; two failures abort the run and leave the state file byte-for-byte untouched.
  - **Partial runs are safe**: a URL that was not probed keeps its old entry, `--limit` never writes state, and the CLI refuses to run when the README yields fewer than 1,000 URLs (otherwise a format change upstream would prune the whole state).
- 25 new tests (58 Python tests in total, plus 12 in JavaScript). Because they passed first time I checked them by breaking ten behaviours on purpose. Nine were caught at once; one survived and showed a real gap: the "state untouched" test seeded the file in the exact format the code writes, so a rewrite looked identical. It now seeds a different format, and all ten are caught.

**Real run, from this Mac, all 2,165 URLs:** 295 seconds. 1,848 ok (85.4%), 99 blocked (4.6%), **218 failing (10.1%)**: dns 68, gone 57, timeout 32, error 26, tls 19, refused 12, network 4. The 80-URL sample had suggested 4 to 6%; 80 was too small a sample to trust that number.

What the follow-up checks showed (all read-only):

| Check | Result |
|---|---|
| Re-probe the 218 about 10 minutes later | 215 failed again, 214 of them in the same class. Only 3 recovered: `*.docs.apiary.io` pages flapping between error and ok. Failures are overwhelmingly persistent, not flaky. |
| DNS failures against Cloudflare (1.1.1.1) and Google (8.8.8.8) resolvers | 63 of 66 hosts unresolvable on all three resolvers (real). **3 resolve elsewhere**: `disqus.com`, `developer.foursquare.com`, `verifier.meetchopra.com`. Those are false positives from this machine's own DNS. |
| tls failures | curl exits 60 (certificate not trusted) and 35 (handshake). Real certificate problems on small sites, which a browser would also warn about. |

Takeaways:
- **Local runs are only indicative.** A resolver, filter or geo-block on this machine can flag healthy sites. The run that counts is the one on GitHub's runner (H3), and the accuracy audit (H4) should use that output.
- The 3-in-a-row rule mostly guards against flappers like apiary. Persistent failures reach "dead" on night three either way.
- For H2: badge wording should follow the error class ("may be gone" for dns, gone and refused; "certificate problem" for tls; "not responding" for timeout and error), not one generic label.
- Runtime is about 5 minutes, comfortably inside a nightly job.

### H2: build integration and the site badge

- `scripts/build.py` now reads `data/health.json` (`--health` to override) and flags each API whose URL is in the failing list: `health` is `"failing"` below `DEAD_AFTER` (3) failed runs in a row and `"dead"` at or above it, plus `health_error` and `health_since`. `apis.json` also gets a top-level `health_checked` date. The threshold is a constant, not stored in the data, so changing it needs no migration. A missing health file means no flags (no checks have run yet); a **damaged one fails the build loudly** instead of quietly dropping every flag.
- `healthcheck.py` used to import `build.py` at the top and `build.py` now needs `healthcheck`'s state loader. Importing each other would be a circle, so `healthcheck.main()` imports `build` inside the function, the only place it needs it.
- Site: a "Hide possibly-dead links" checkbox (off by default, as agreed; URL hash `hidedead=1`, so a filtered view is shareable) that hides **dead** links only. A link that merely failed its latest check keeps showing with a quiet "Failed latest check" badge. Badge wording follows what failed: "May be gone" (dns, gone, refused), "Certificate problem" (tls), "Not responding" (timeout, error, network), with a tooltip saying since when and why. The footer says when links were last checked and how many are possibly dead. Red badge colours exist for light and dark mode.
- Tests first: 10 Python and 8 JavaScript (68 Python and 20 JavaScript in total). Two mistakes of mine along the way:
  - The "damaged health file fails loudly" test passed **before** the feature existed, because argparse rejecting the unknown `--health` flag also raises `SystemExit`. A test that is green by accident proves nothing, so it now requires the actual error message to mention health.
  - The build-level tests tripped the real-data sanity guard because the tiny fixture has a deliberately malformed row (1 of 11, over the 1% limit). Those tests now relax the limits explicitly.
- Eleven deliberate code breaks (threshold off by one, everything flagged dead, error class dropped, input mutated, `hideDead` also hiding "failing", wording lost, and so on) were all caught.
- **Checked in a real browser** against a fixture built from the real H1 run (the same 218 failing URLs, with failure counts adjusted so some are dead, some tls, some merely failing): 185 dead and 33 failing flagged. Counts were compared with an independent Python computation: hide-dead on shows 1,984 of 2,169 (expected 1,984) and leaves no dead badge; all 33 "failed latest check" badges stay visible while hiding; wording counts match the classes exactly (May be gone 137 = dns 68 + gone 57 + refused 12; Certificate problem 19; Not responding 29 = timeout 19 + error 10); the deep link `#q=api&hidedead=1&nokey=1` restored all controls and showed 175 (expected 175); no console errors; badges readable in light and dark mode.
- The browser pane had closed partway through and refused a navigation; reopening it with a proper start call fixed that.
- **The live site is unchanged for now:** there is no `data/health.json` in the repo yet, so the live build has no flags and no footer line. The first real data arrives with the workflow in H3.
