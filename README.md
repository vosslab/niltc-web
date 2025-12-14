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
