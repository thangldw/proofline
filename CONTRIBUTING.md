# Contributing

Proofline accepts focused issues and pull requests for the current roadmap. Do not include private
sources, database files, credentials, prompts, model payloads, or pilot data in reports.

## Development

```bash
git clone https://github.com/thangldw/proofline.git
cd proofline
make setup
make test
make check
```

Keep changes small, add regression tests, use migrations for schema changes, preserve exact
provenance, and document user-visible behavior. A mock or synthetic fixture must be clearly marked
and must not be presented as real quality evidence.

Documentation diagrams follow [`docs/visual-language.md`](docs/visual-language.md). Product and
landing surfaces use system fonts only; a contribution must not add remote font calls or bundled
font files without an explicit size and offline-mode decision.

Before opening a pull request, describe the behavior, failure modes, data/migration impact, tests
run, and any remaining limitations. Security reports belong in the private channel documented in
[SECURITY.md](SECURITY.md).
