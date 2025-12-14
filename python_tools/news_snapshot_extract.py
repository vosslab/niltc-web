#!/usr/bin/env python3

# Standard Library
import argparse
import csv
import hashlib
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
import html as html_lib


HEAD_CACHE_DIR_DEFAULT = os.path.join('cache', 'news_head')
SNAPSHOT_DIR_DEFAULT = os.path.join('snapshots', 'news_full')
INDEX_CSV_DEFAULT = os.path.join('snapshots', 'news_full', 'index.csv')


#============================================
def parse_args():
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description='Extract head metadata from full HTML snapshots into cache/news_head/*.head.html',
	)

	parser.add_argument(
		'-i', '--input-dir', dest='input_dir', required=False, type=str,
		default=SNAPSHOT_DIR_DEFAULT,
		help='Input directory of full HTML snapshots (default: snapshots/news_full)',
	)
	parser.add_argument(
		'-c', '--cache-dir', dest='cache_dir', required=False, type=str,
		default=HEAD_CACHE_DIR_DEFAULT,
		help='Output head cache directory (default: cache/news_head)',
	)
	parser.add_argument(
		'--index', dest='index_csv', required=False, type=str,
		default=INDEX_CSV_DEFAULT,
		help='Index CSV output (default: snapshots/news_full/index.csv)',
	)
	parser.add_argument(
		'-n', '--max', dest='max_files', required=False, type=int,
		default=None,
		help='Optional max files (for testing)',
	)
	parser.add_argument(
		'--dry-run', dest='dry_run', required=False,
		action='store_true',
		help='Do not write cache files (still writes index CSV)',
	)
	parser.add_argument(
		'-v', '--verbose', dest='verbose', required=False,
		action='store_true',
		help='Print per-file progress',
	)

	return parser.parse_args()


#============================================
def sha12(text: str) -> str:
	"""
	Get a short SHA1 prefix for stable cache filenames.
	"""
	text = str(text or '')
	return hashlib.sha1(text.encode('utf-8', errors='ignore')).hexdigest()[:12]


#============================================
def normalize_url(url: str) -> str:
	"""
	Normalize a URL string (strip, unescape entities).
	"""
	url = str(url or '').strip()
	url = html_lib.unescape(url)
	return url.strip()


#============================================
def write_text_file_if_changed(path: str, content: str) -> bool:
	"""
	Write text file only if content changed.
	"""
	parent = os.path.dirname(path)
	if parent:
		os.makedirs(parent, exist_ok=True)

	if os.path.exists(path):
		with open(path, 'r', encoding='utf-8', errors='ignore') as f:
			existing = f.read()
		if existing == content:
			return False

	with open(path, 'w', encoding='utf-8') as f:
		f.write(content)
	return True


#============================================
def _json_sanitize_no_images(value):
	"""
	Remove image-like fields from JSON-LD objects (recursive).
	"""
	if isinstance(value, list):
		return [_json_sanitize_no_images(v) for v in value]

	if isinstance(value, dict):
		drop = set(['image', 'thumbnail', 'thumbnailurl', 'thumbnailUrl', 'logo'])
		out = {}
		for k, v in value.items():
			ks = str(k or '')
			if ks.lower() in drop:
				continue
			out[k] = _json_sanitize_no_images(v)
		return out

	return value


#============================================
def _is_image_meta(attrs: dict) -> bool:
	name = str(attrs.get('name', '') or '').strip().lower()
	prop = str(attrs.get('property', '') or '').strip().lower()
	key = prop or name
	if key.startswith('og:image'):
		return True
	if key.startswith('twitter:image'):
		return True
	if key in ('image', 'thumbnail', 'thumbnailurl'):
		return True
	return False


#============================================
def _is_image_link(attrs: dict) -> bool:
	rel = str(attrs.get('rel', '') or '').strip().lower()
	as_attr = str(attrs.get('as', '') or '').strip().lower()
	if as_attr == 'image':
		return True
	if 'icon' in rel:
		return True
	if 'apple-touch-icon' in rel:
		return True
	if 'mask-icon' in rel:
		return True
	return False


#============================================
class HeadMetaParser(HTMLParser):
	"""
	Parse <head> for canonical/og/twitter URLs and collect head elements.
	"""

	def __init__(self):
		super().__init__()
		self.in_head = False
		self.in_title = False
		self.in_ldjson = False

		self.title_parts = []
		self.meta_tags = []
		self.link_tags = []
		self.ldjson_blobs = []
		self._ldjson_parts = []

		self.canonical = None
		self.og_url = None
		self.twitter_url = None

	def handle_starttag(self, tag, attrs):
		tag = str(tag or '').lower()
		attrs_dict = {}
		for k, v in (attrs or []):
			if not k:
				continue
			attrs_dict[str(k).lower()] = str(v or '')

		if tag == 'head':
			self.in_head = True
			return

		if not self.in_head:
			return

		if tag == 'title':
			self.in_title = True
			return

		if tag == 'link':
			if not _is_image_link(attrs_dict):
				self.link_tags.append(attrs_dict)
			rel = str(attrs_dict.get('rel', '') or '').strip().lower()
			href = attrs_dict.get('href')
			if rel == 'canonical' and href:
				if self.canonical is None:
					self.canonical = href
			return

		if tag == 'meta':
			if not _is_image_meta(attrs_dict):
				self.meta_tags.append(attrs_dict)
			prop = str(attrs_dict.get('property', '') or '').strip()
			name = str(attrs_dict.get('name', '') or '').strip()
			content = attrs_dict.get('content')
			if prop == 'og:url' and content:
				if self.og_url is None:
					self.og_url = content
			if name.lower() == 'twitter:url' and content:
				if self.twitter_url is None:
					self.twitter_url = content
			return

		if tag == 'script':
			type_attr = str(attrs_dict.get('type', '') or '').strip().lower()
			if type_attr == 'application/ld+json':
				self.in_ldjson = True
				self._ldjson_parts = []
			return

	def handle_endtag(self, tag):
		tag = str(tag or '').lower()
		if tag == 'head':
			self.in_head = False
			return
		if not self.in_head:
			return
		if tag == 'title':
			self.in_title = False
			return
		if tag == 'script' and self.in_ldjson:
			raw = ''.join(self._ldjson_parts).strip()
			self.in_ldjson = False
			self._ldjson_parts = []
			if raw:
				self.ldjson_blobs.append(raw)

	def handle_data(self, data):
		if not self.in_head:
			return
		if self.in_title:
			text = str(data or '')
			text = re.sub(r'\s+', ' ', text).strip()
			if text:
				self.title_parts.append(text)
			return
		if self.in_ldjson:
			self._ldjson_parts.append(str(data or ''))

	def title_text(self) -> str:
		return re.sub(r'\s+', ' ', ' '.join(self.title_parts)).strip()


#============================================
def extract_url_from_ldjson(blobs: list) -> str:
	"""
	Try to extract a URL from JSON-LD mainEntityOfPage.@id or url.
	"""
	for blob in blobs:
		blob = str(blob or '').strip()
		if not blob:
			continue
		try:
			obj = json.loads(blob)
		except Exception:
			continue

		candidates = []
		if isinstance(obj, dict):
			candidates.append(obj)
		elif isinstance(obj, list):
			for x in obj:
				if isinstance(x, dict):
					candidates.append(x)

		for d in candidates:
			me = d.get('mainEntityOfPage')
			if isinstance(me, dict) and isinstance(me.get('@id'), str):
				return str(me.get('@id') or '').strip()
			if isinstance(d.get('url'), str):
				return str(d.get('url') or '').strip()

	return ''


#============================================
def extract_best_url(html_text: str) -> str:
	"""
	Extract best URL using priority:
	1) link rel=canonical
	2) meta property=og:url
	3) meta name=twitter:url
	4) JSON-LD mainEntityOfPage.@id or url
	"""
	parser = HeadMetaParser()
	parser.feed(str(html_text or ''))

	candidates = [
		parser.canonical,
		parser.og_url,
		parser.twitter_url,
		extract_url_from_ldjson(parser.ldjson_blobs),
	]

	for u in candidates:
		u = normalize_url(u)
		if not u:
			continue
		if u.startswith('//'):
			u = 'https:' + u
		if u.startswith('http'):
			return u

	return ''


#============================================
def build_head_cache_html(full_html: str) -> str:
	"""
	Build a minimal HTML document with just head metadata.
	"""
	parser = HeadMetaParser()
	parser.feed(str(full_html or ''))

	lines = []
	lines.append('<!doctype html>')
	lines.append('<html>')
	lines.append('<head>')

	title = parser.title_text()
	if title:
		lines.append('<title>' + html_lib.escape(title) + '</title>')

	def emit_tag(tag: str, attrs: dict):
		parts = [tag]
		for k in sorted(attrs.keys()):
			v = str(attrs.get(k, '') or '')
			if v == '':
				continue
			parts.append(f'{k}=\"{html_lib.escape(v, quote=True)}\"')
		return '<' + ' '.join(parts) + '>'

	for attrs in parser.meta_tags:
		lines.append(emit_tag('meta', attrs))

	for attrs in parser.link_tags:
		lines.append(emit_tag('link', attrs))

	for raw in parser.ldjson_blobs:
		try:
			obj = json.loads(raw)
		except Exception:
			continue
		obj = _json_sanitize_no_images(obj)
		raw_out = json.dumps(obj, ensure_ascii=False, indent=2)
		lines.append('<script type=\"application/ld+json\">')
		lines.append(raw_out)
		lines.append('</script>')

	lines.append('</head>')
	lines.append('</html>')
	return '\n'.join(lines) + '\n'


#============================================
def process_file(path: Path, cache_dir: Path, dry_run: bool = False):
	"""
	Process one snapshot file and write head cache.
	"""
	try:
		html_text = path.read_text(encoding='utf-8', errors='ignore')
	except Exception:
		return False, '', '', 'read_error'

	url = extract_best_url(html_text)
	if not url:
		return False, '', '', 'no_url_in_head'

	head_doc = build_head_cache_html(html_text)
	if not head_doc or '<head' not in head_doc.lower():
		return False, url, '', 'no_head_doc'

	key = sha12(url)
	out_path = cache_dir / (key + '.head.html')

	if not dry_run:
		write_text_file_if_changed(str(out_path), head_doc)

	return True, url, str(out_path), ''


#============================================
def main():
	args = parse_args()

	input_dir = Path(args.input_dir)
	cache_dir = Path(args.cache_dir)
	index_csv = Path(args.index_csv)

	files = sorted(input_dir.glob('*.html')) if input_dir.exists() else []
	if args.max_files is not None:
		files = files[:args.max_files]

	rows = []
	rows.append(['file', 'extracted_url', 'cache_path', 'ok', 'note'])

	for p in files:
		ok, extracted_url, cache_path, note = process_file(
			path=p,
			cache_dir=cache_dir,
			dry_run=bool(args.dry_run),
		)

		if args.verbose:
			print(str(p))
			print(f'  ok: {ok}')
			if extracted_url:
				print(f'  url: {extracted_url}')
			if cache_path:
				print(f'  cache_path: {cache_path}')
			if note:
				print(f'  note: {note}')

		rows.append([str(p), extracted_url, cache_path, 'true' if ok else 'false', note])

	index_csv.parent.mkdir(parents=True, exist_ok=True)
	with index_csv.open('w', encoding='utf-8', newline='') as f:
		w = csv.writer(f)
		w.writerows(rows)

	if args.verbose:
		print(f'Wrote index: {index_csv}')


if __name__ == '__main__':
	main()

