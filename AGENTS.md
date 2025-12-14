# AGENTS.md (repo instructions)

## Project intent

This repository hosts a MkDocs Material site for NILTC, with content exported from WordPress.

Primary UI goal: match the legacy NILTC WordPress look (centered white content with shadow, **black outer gutters**, large banner header).

## Key files

- `mkdocs.yml`: MkDocs configuration (theme + nav).
- `mkdocs/docs/`: Markdown content and images.
- `mkdocs/docs/stylesheets/niltc.css`: All styling overrides live here.
- `mkdocs/docs/assets/`: Banner/favicon/social icons, etc.
- `mkdocs/hooks.py`: MkDocs build hook (generates pages from YAML).
- `data/shows.yml`: Shows source data (schema 2; edit this; pages are generated).
- `python_tools/past_shows.py`: Past shows generator.
- `python_tools/wordpress_to_markdown.py`: WordPress REST API → Markdown export script.
- `requirements.txt`: Python deps for building on GitHub Actions.
- `.github/workflows/pages.yml`: GitHub Pages build/deploy workflow.

## Content exclusions

- Do not include “Members Only” pages/content in MkDocs.

## MkDocs conventions

- Keep left sidebar navigation (no top tabs):
  - Enable: `navigation.sections`, `navigation.expand`
  - Disable: `navigation.tabs`, `navigation.tabs.sticky`
- Keep a grouped/nested `nav:` (e.g. `NILTC`, `Shows`, `Standards`) so the sidebar has section headers.
- Prefer CSS via `extra_css` over template overrides or plugins.

## Styling conventions

- “Sides of the screen” (outside the centered content) should be black.
- The sidebar menu should remain the default/light style (don’t force it black unless requested).
- Any new visual tweaks go into `mkdocs/docs/stylesheets/niltc.css`.

## Generated content

- Past Shows pages are generated at build time from `data/shows.yml` via `mkdocs/hooks.py`.
- Do not hand-edit `mkdocs/docs/past-shows/**/index.md`; edit the YAML and run `mkdocs build -f mkdocs.yml`.

## WordPress export workflow

- Requires `pandoc` on PATH and Python with `requests`.
- On this machine, use Homebrew Python 3.12:
  - `/opt/homebrew/opt/python@3.12/bin/python3.12 python_tools/wordpress_to_markdown.py -b https://niltc.org -o mkdocs/docs`

## Local validation

- Build: `mkdocs build -f mkdocs.yml`
- Serve: `mkdocs serve -f mkdocs.yml`

## GitHub Pages

- Deployment uses GitHub Actions workflow `.github/workflows/pages.yml`.
- GitHub repo settings must have Pages → Source set to “GitHub Actions”.
- If adding MkDocs plugins, update `requirements.txt` so CI can build.

## Repo docs

- High-level overview for humans: `README.md`
- Build/export/deploy details: `DEVELOPMENT.md`

## Python style

- Follow `PYTHON_STYLE.md` (tabs for indentation, argparse patterns, ascii-only).
