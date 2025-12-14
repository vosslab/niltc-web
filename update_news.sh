#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DO_SNAPSHOTS=1
DO_ENRICH=1
DO_RENDER=1
DO_BUILD=1

VERBOSE=0

usage() {
	cat <<'EOF'
Usage: ./update_news.sh [options]

Runs the full In the News update pipeline:
  1) Extract head-cache from full HTML snapshots (snapshots/news_full/*.html)
  2) Enrich data/in_the_news.yml from data/in_the_news.csv (network + head-cache)
  3) Render mkdocs/docs/in-the-news/index.md
  4) mkdocs build -f mkdocs.yml

Options:
  --no-snapshots   Skip snapshot extraction
  --no-enrich      Skip enrichment (still renders from existing YAML)
  --no-render      Skip rendering
  --no-build       Skip mkdocs build
  -v, --verbose    Verbose output
  -h, --help       Show this help

Env overrides:
  PY_ENRICH        Python to use for enrichment (default: python3.12 if available)
  NEWS_SLEEP_MAX   Max random sleep seconds before requests (default: 1.0)
  NEWS_TIMEOUT     Request timeout seconds (default: 20.0)
  NEWS_MAX         Optional max URLs to process (default: unset)
EOF
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--no-snapshots) DO_SNAPSHOTS=0; shift ;;
		--no-enrich) DO_ENRICH=0; shift ;;
		--no-render) DO_RENDER=0; shift ;;
		--no-build) DO_BUILD=0; shift ;;
		-v|--verbose) VERBOSE=1; shift ;;
		-h|--help) usage; exit 0 ;;
		*) echo "Unknown option: $1" >&2; usage; exit 2 ;;
	esac
done

PY_ENRICH_BIN="${PY_ENRICH:-}"
if [[ -z "${PY_ENRICH_BIN}" ]]; then
	if [[ -x "/opt/homebrew/opt/python@3.12/bin/python3.12" ]]; then
		PY_ENRICH_BIN="/opt/homebrew/opt/python@3.12/bin/python3.12"
	else
		PY_ENRICH_BIN="python3"
	fi
fi

NEWS_SLEEP_MAX="${NEWS_SLEEP_MAX:-1.0}"
NEWS_TIMEOUT="${NEWS_TIMEOUT:-20.0}"
NEWS_MAX="${NEWS_MAX:-}"

extra_args=()
if [[ "${VERBOSE}" -eq 1 ]]; then
	extra_args+=("-v")
fi
if [[ -n "${NEWS_MAX}" ]]; then
	extra_args+=("-n" "${NEWS_MAX}")
fi

echo "[news] repo: ${ROOT}"

if [[ "${DO_SNAPSHOTS}" -eq 1 ]]; then
	echo "[news] 1/4 snapshot -> head cache"
	python3 "${ROOT}/python_tools/news_snapshot_extract.py" ${VERBOSE:+-v}
fi

if [[ "${DO_ENRICH}" -eq 1 ]]; then
	echo "[news] 2/4 enrich YAML"
	"${PY_ENRICH_BIN}" "${ROOT}/python_tools/news_enrich.py" \
		-i "${ROOT}/data/in_the_news.csv" \
		-y "${ROOT}/data/in_the_news.yml" \
		-r "${ROOT}/data/in_the_news_needs_review.csv" \
		-q "${ROOT}/data/in_the_news_needs_snapshot.csv" \
		--head-cache-dir "${ROOT}/cache/news_head" \
		-s "${NEWS_SLEEP_MAX}" \
		-t "${NEWS_TIMEOUT}" \
		"${extra_args[@]}"
fi

if [[ "${DO_RENDER}" -eq 1 ]]; then
	echo "[news] 3/4 render MkDocs page"
	python3 "${ROOT}/python_tools/news_render.py" \
		-i "${ROOT}/data/in_the_news.yml" \
		-o "${ROOT}/mkdocs/docs/in-the-news/index.md"
fi

if [[ "${DO_BUILD}" -eq 1 ]]; then
	echo "[news] 4/4 mkdocs build"
	mkdocs build -f "${ROOT}/mkdocs.yml"
fi

echo "[news] done"

