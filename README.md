# api-explorer

A searchable explorer for the [public-apis](https://github.com/public-apis/public-apis) list of free APIs. Built as a project for learning GitHub: submodules, Actions, Pages, issues and pull requests.

Data comes from the upstream list, included here as a git submodule at `vendor/public-apis/`. This repo records which upstream commit it uses (the "pin"), and a nightly job will move the pin forward.

## Cloning

A submodule is a pointer to another repo, so a plain clone leaves `vendor/public-apis/` empty. Clone with:

```bash
git clone --recurse-submodules https://github.com/graemewal777/api-explorer.git
```

Already cloned without it? Run:

```bash
git submodule update --init
```

## Status

Work is tracked in [docs/learning-log.md](docs/learning-log.md).

## License

MIT. The upstream list is also MIT-licensed.
