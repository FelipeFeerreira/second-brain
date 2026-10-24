# Second Brain

A local-first knowledge manager that stores notes as **Markdown files with YAML front matter**. It combines linked notes with structured book and game collections, without a hosted database or account requirement.

**Stack:** Python 3.10+ · Flask · PyYAML · Markdown · browser-based UI

| | |
|:--|:--|
| **Live demo** | Local app — no hosted demo |
| **Screenshots** | Pending — no screenshots yet |
| **Stack** | Python · Flask · PyYAML · Markdown |
| **License** | MIT — [LICENSE](LICENSE) |

## Features

- Create and edit notes and ideas, with `[[wikilinks]]`, backlinks and tags.
- Search titles and note bodies; filter structured book and game collections.
- Explore relationships through a visual knowledge graph.
- Keep readable files that can also be opened in other Markdown editors.
- Choose a local vault directory, including a directory synchronized by your own file-sync tool.

## Run locally

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**. An empty `vault/` is created locally. To use another folder, run `python app.py --vault /path/to/notes`. No personal notes or local configuration are included in this repository.

## Architecture

`core.py` parses Markdown and maintains an in-memory index of notes, links and tags. `app.py` exposes the Flask API and serves the interface from `static/` and `templates/`. Markdown files remain the source of truth.

## Scope and verification

This is a personal, single-user local application. It has no multi-user authentication or hardened public hosting setup; keep the default loopback binding and use trusted local notes. File synchronization is external to the application and does not resolve concurrent edits automatically. See [verification notes](docs/PORTFOLIO_VALIDATION.md).

---

## What I would do next

- Add tests for the Markdown/index layer and a sample vault that ships with the repo.
- Add a one-command packaging path so Windows users do not need a venv.
- Document a conflict strategy for folders synced by external tools.

## License

MIT - see [LICENSE](LICENSE). You may use, modify and redistribute this code with attribution.
