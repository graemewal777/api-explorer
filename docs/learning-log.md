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
