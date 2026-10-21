# Learning log

One entry per milestone: what we did, and the GitHub idea it taught.

## M0: repo and submodule

- Created a new public repo instead of forking `public-apis`. Scheduled Actions are disabled by default on forks, and we want a nightly job later.
- `git submodule add --depth 1` pulled in `public-apis` shallow (about 500 KB instead of its full history). `shallow = true` in `.gitmodules` makes later updates shallow too.
- The submodule is a pin: this repo stores one commit hash for `vendor/public-apis`, not the files. Upstream's default branch is `master`, not `main`.
- Gotcha: a plain `git clone` leaves the submodule folder empty. See the README.
