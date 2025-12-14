# AGENTS.md (repo instructions)

## Project intent

This repository hosts a MkDocs Material site for NILTC, with content exported from WordPress.

Primary UI goal: match the legacy NILTC WordPress look (centered white content with shadow, **black outer gutters**, large banner header).

## Key files (expected)

- `mkdocs.yml`: MkDocs configuration (theme + nav).
- `mkdocs/docs/`: Markdown content and images.
- `mkdocs/docs/stylesheets/niltc.css`: All styling overrides live here.
- `mkdocs/docs/assets/`: Banner/favicon/social icons, etc.
- `wordpress-to-markdown.py`: WordPress REST API → Markdown export script.
- `niltc-mirror-old/`: HTTrack mirror (reference only).

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

## WordPress export workflow

- Requires `pandoc` on PATH and Python with `requests`.
- On this machine, use Homebrew Python 3.12:
  - `/opt/homebrew/opt/python@3.12/bin/python3.12 wordpress-to-markdown.py -b https://niltc.org -o mkdocs/docs`

## Local validation

- Build: `mkdocs build -f mkdocs.yml`
- Serve: `mkdocs serve -f mkdocs.yml`

## Python style

- Follow `PYTHON_STYLE.md` (tabs for indentation, argparse patterns, ascii-only).
