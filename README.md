# api-explorer

A searchable explorer for the [public-apis](https://github.com/public-apis/public-apis) list of free APIs. **Live site: https://graemewal777.github.io/api-explorer/** Built as a project for learning GitHub: submodules, Actions, Pages, issues and pull requests.

Data comes from the upstream list, included here as a git submodule at `vendor/public-apis/`. This repo records which upstream commit it uses (the "pin"), and a nightly GitHub Actions job (03:17 UTC) moves the pin forward, rebuilds and redeploys the site.

## Cloning

A submodule is a pointer to another repo, so a plain clone leaves `vendor/public-apis/` empty. Clone with:

```bash
git clone --recurse-submodules https://github.com/graemewal777/api-explorer.git
```

Already cloned without it? Run:

```bash
git submodule update --init
```

## Run it locally

```bash
python3 scripts/build.py                      # reads the submodule, writes site/apis.json
cd site && python3 -m http.server 8765        # then open http://127.0.0.1:8765/
```

## Link health check

A nightly workflow (`.github/workflows/health.yml`, 02:47 UTC) probes every API URL and records which ones fail in `data/health.json`. A link is flagged "possibly dead" after three failed runs in a row. Reachable-but-bot-blocking sites (403, Cloudflare challenges) are never counted as failures.

```bash
python3 scripts/healthcheck.py --dry-run --limit 50    # try it locally on 50 URLs; writes nothing
```

Local runs are only indicative: a resolver or filter on your machine can flag healthy sites. The nightly run on GitHub's runner is the one the site uses.

## Tests

```bash
python3 -m unittest discover -s tests         # parser
node --test tests/filter.test.js              # search and filters
```

## Status

Work is tracked in [docs/learning-log.md](docs/learning-log.md).

## License

MIT. The upstream list is also MIT-licensed.
