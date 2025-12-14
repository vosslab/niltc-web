# niltc-web

This repo contains:

- `niltc-mirror-old/`: an HTTrack static mirror used to inspect public URL structure.
- `wordpress-to-markdown.py`: a WordPress REST API exporter that converts content to MkDocs-ready Markdown.
- `mkdocs/docs/`: generated Markdown content and downloaded images.
- `mkdocs.yml`: MkDocs configuration for serving/building the generated docs.

## WordPress -> MkDocs exporter

`wordpress-to-markdown.py`:

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

## Usage

The exporter requires Python with `requests` installed plus `pandoc` available on your PATH.

On this machine, `python3` is 3.14 and does not have `requests`, but Homebrew Python 3.12 does:

```bash
/opt/homebrew/opt/python@3.12/bin/python3.12 wordpress-to-markdown.py \
  -b https://niltc.org \
  -o mkdocs/docs
```

Serve locally with MkDocs:

```bash
mkdocs serve -f mkdocs.yml
```
