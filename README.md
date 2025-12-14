# NILTC website

This repository contains the source content for the NILTC website, built with MkDocs Material.

NILTC is a train club (and more) that builds and displays at public shows and events in the Chicagoland area.

## What’s here

- Public-facing pages like **Upcoming Shows**, **Past Shows**, **Standards**, photos/videos, FAQs, and club info.
- A visual style that aims to match the legacy NILTC WordPress look (black outer gutters + centered white content).

## Updating content

- Most pages live in `mkdocs/docs/` as `index.md` files.
- Common pages to edit:
  - Home: `mkdocs/docs/index.md`
  - Standards: `mkdocs/docs/standards/index.md`
  - FAQs: `mkdocs/docs/faqs/index.md`
- **Shows data** lives in `data/shows.yml` (edit the YAML; pages are generated at build time).

## In the News (automated)

This repo maintains a single **In the News** list page generated from a simple URL CSV.

- Add links by editing `data/in_the_news.csv` (one URL per row; `url` column only).
- Canonical data is stored in `data/in_the_news.yml` (one record per story; each story can have multiple URLs).
- URLs that are reachable-but-blocked (Incapsula/incident pages) are queued in `data/in_the_news_needs_snapshot.csv` for a local head cache.
- Hard failures can be inspected in `data/in_the_news_needs_review.csv`.

Manual runs:

```bash
python3.12 python_tools/news_enrich.py -i data/in_the_news.csv -y data/in_the_news.yml -r data/in_the_news_needs_review.csv -q data/in_the_news_needs_snapshot.csv
python3 python_tools/news_render.py -i data/in_the_news.yml -o mkdocs/docs/in-the-news/index.md
```

One-shot helper:

```bash
./update_news.sh
```

Notes:

- The site page `mkdocs/docs/in-the-news/index.md` is generated from `data/in_the_news.yml`.
- MkDocs builds only run enrichment if `mkdocs.yml` has `extra.news_enrich: true` (default is false to avoid network calls during local dev).
- Do not download/store publisher images; the pipeline does not scrape article body text.
- The head cache lives at `cache/news_head/` and is ignored by git. It stores only `<title>`, `<meta>`, `<link>`, and JSON-LD (no images, no body HTML).
- If `data/in_the_news_needs_snapshot.csv` has rows, save full HTML snapshots to `snapshots/news_full/` (any filenames), run `python3 python_tools/news_snapshot_extract.py`, then re-run `python3.12 python_tools/news_enrich.py`.
- The renderer only shows stories that have **both** `published_date` and `title`.

Generated from `data/shows.yml` (do not hand-edit these outputs):

- `mkdocs/docs/upcoming-shows/index.md`
- `mkdocs/docs/past-shows/index.md`
- `mkdocs/docs/past-shows/<decade>s/index.md`
- The “See NILTC in person” block inside `mkdocs/docs/index.md` (between `SHOWS_NEXT` markers)

Example (schema 2):

```yaml
schema: 2

venues:
  ahml:
    name: Arlington Heights Memorial Library
    address: 500 N. Dunton Ave.
    city: Arlington Heights
    state: IL
    postal_code: "60004"
    website: "https://www.ahml.info/"

events:
  - id: 2025-12-ahml
    venue: ahml
    start_date: "2025-12-13"
    end_date: "2025-12-14"
    status: confirmed
```

## Development / publishing

Build/serve instructions, the WordPress export tool, and GitHub Pages deployment are documented in `DEVELOPMENT.md`.
