# NILTC website

This repository contains the source content for the Northern Illinois LEGO Train Club (NILTC) website, built with MkDocs Material.

NILTC is a LEGO train club (and more) that builds and displays at public shows and events in the Chicagoland area.

## What’s here

- Public-facing pages like **Upcoming Shows**, **Past Shows**, **Standards**, photos/videos, FAQs, and club info.
- A visual style that aims to match the legacy NILTC WordPress look (black outer gutters + centered white content).

## Updating content

- Most pages live in `mkdocs/docs/` as `index.md` files.
- Common pages to edit:
  - Home: `mkdocs/docs/index.md`
  - Upcoming shows: `mkdocs/docs/upcoming-shows/index.md`
  - Standards: `mkdocs/docs/standards/index.md`
  - FAQs: `mkdocs/docs/faqs/index.md`
- **Past Shows** is generated from `data/past_shows.yml` (edit the YAML; don’t hand-edit the generated `mkdocs/docs/past-shows/**/index.md` files).

## Development / publishing

Build/serve instructions, the WordPress export tool, and GitHub Pages deployment are documented in `DEVELOPMENT.md`.
