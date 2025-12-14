# Development

This file documents how to build, serve, and publish the NILTC MkDocs site.

## Repo layout

- `mkdocs.yml`: MkDocs config (nav/theme).
- `mkdocs/docs/`: site content (Markdown + assets).
- `mkdocs/docs/stylesheets/niltc.css`: all CSS overrides (legacy “black frame” look, sidebar tweaks, etc.).
- `mkdocs/hooks.py`: MkDocs build hook (generates shows-related pages from YAML).
- `data/`: editable data files used to generate pages.
- `python_tools/`: Python utilities (export + generators).
- `.github/workflows/pages.yml`: GitHub Pages deployment via Actions.
- `requirements.txt`: Python deps for CI builds.

## Local development

Install site dependencies:

```bash
python -m pip install -r requirements.txt
```

Serve locally:

```bash
mkdocs serve -f mkdocs.yml
```

Build locally:

```bash
mkdocs build -f mkdocs.yml
```

## Shows pages (generated)

Shows live in `data/shows.yml` (schema 2: `venues` + flat `events` list).

On `mkdocs build` / `mkdocs serve`, `mkdocs/hooks.py` regenerates:

- `mkdocs/docs/upcoming-shows/index.md`
- `mkdocs/docs/past-shows/index.md` (overview; current year)
- `mkdocs/docs/past-shows/<decade>s/index.md` (decade pages; auto-created from data)
- The “See NILTC in person” block inside `mkdocs/docs/index.md` (between `SHOWS_NEXT` markers)

Manual run:

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 python_tools/generate_shows_pages.py
```

Do not hand-edit the generated outputs; edit `data/shows.yml` instead.

## In the News (generated)

In the News is a single list page generated from a URL CSV:

- Input: `data/in_the_news.csv` (one URL per line; optional `title_override` column)
- Canonical store: `data/in_the_news.yml` (schema 1)
- Repair queue: `data/in_the_news_needs_review.csv` (hard fails + non-200 soft fails only)
- Output page: `mkdocs/docs/in-the-news/index.md`

Manual run:

```bash
python3 python_tools/news_enrich.py -i data/in_the_news.csv -y data/in_the_news.yml -r data/in_the_news_needs_review.csv
python3 python_tools/news_render.py -i data/in_the_news.yml -o mkdocs/docs/in-the-news/index.md
```

MkDocs integration:

- `mkdocs/hooks.py` always runs the renderer.
- Enrichment (network calls) only runs when `mkdocs.yml` sets `extra.news_enrich: true`.

Notes:

- The pipeline does not download/store images and does not scrape article body text.
- If an item is a hard failure but a working replacement exists with the same source and title (or same published time), enrichment sets `replaced_by` + `suppress` so the dead duplicate is hidden.

## WordPress -> MkDocs exporter

`python_tools/wordpress_to_markdown.py` exports WordPress pages (and optionally posts) via REST API and converts HTML to Markdown using `pandoc`:

- Fetches pages and optionally posts from `wp-json/wp/v2/pages` and `wp-json/wp/v2/posts`, handling pagination.
- Adds a short randomized sleep before each request to reduce load.
- Converts each item’s `content.rendered` HTML to GitHub-flavored Markdown using Pandoc.
- Writes MkDocs-friendly output paths:
  - Pages: `mkdocs/docs/<site-path>/index.md` (homepage becomes `mkdocs/docs/index.md`)
  - Posts: `mkdocs/docs/posts/<year>/<slug>/<slug>.md`
- Optionally downloads referenced images and relinks them either adjacent to each Markdown file or into a shared assets folder.
- Adds YAML front matter per file with title, type (page or post), WordPress ID, original link, and date.
- Applies a small cleanup pass:
  - Adds a default language tag to code fences that have none
  - Optionally inserts/enforces a single `<!-- more -->` marker for posts
  - Optionally rewrites internal WordPress links to relative MkDocs paths using a link map
- Produces a CSV report listing each exported item and the number of images downloaded.

### Export usage

The exporter requires `pandoc` on your PATH and Python with `requests` installed.

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 python_tools/wordpress_to_markdown.py \
  -b https://niltc.org \
  -o mkdocs/docs
```

## GitHub Pages deployment

This repo publishes via GitHub Actions (see `.github/workflows/pages.yml`).

In GitHub repo settings:

- Settings → Pages → Source: GitHub Actions
