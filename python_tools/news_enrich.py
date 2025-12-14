#!/usr/bin/env python3

# Standard Library
import csv
import html
import html.parser
import json
import os
import re
import time
import random
import datetime
import argparse
import urllib.parse
import hashlib

# PIP3 modules
import requests
import yaml

SESSION = requests.Session()
SESSION.headers.update({
	'User-Agent': (
		'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
		'AppleWebKit/537.36 (KHTML, like Gecko) '
		'Chrome/120.0.0.0 Safari/537.36'
	),
	'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
	'Accept-Language': 'en-US,en;q=0.9',
	# Avoid advertising brotli unless we know we can decode it everywhere.
	'Accept-Encoding': 'gzip, deflate',
	'Connection': 'keep-alive',
	'Upgrade-Insecure-Requests': '1',
})

HEAD_CACHE_DIR_DEFAULT = os.path.join('cache', 'news_head')


#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed arguments.
	"""
	parser = argparse.ArgumentParser(
		description='Enrich/validate In the News URLs and update data/in_the_news.yml',
	)

	parser.add_argument(
		'-i', '--input', dest='input_csv', required=False, type=str,
		default='data/in_the_news.csv',
		help='Input CSV file (default: data/in_the_news.csv)',
	)
	parser.add_argument(
		'-y', '--yaml', dest='output_yaml', required=False, type=str,
		default='data/in_the_news.yml',
		help='Output YAML file (default: data/in_the_news.yml)',
	)
	parser.add_argument(
		'-r', '--review', dest='review_csv', required=False, type=str,
		default='data/in_the_news_needs_review.csv',
		help='Review CSV file (default: data/in_the_news_needs_review.csv)',
	)
	parser.add_argument(
		'-q', '--snapshot-queue', dest='snapshot_csv', required=False, type=str,
		default='data/in_the_news_needs_snapshot.csv',
		help='Blocked URL queue CSV (default: data/in_the_news_needs_snapshot.csv)',
	)
	parser.add_argument(
		'--head-cache-dir', dest='head_cache_dir', required=False, type=str,
		default=HEAD_CACHE_DIR_DEFAULT,
		help='Local head cache directory (default: cache/news_head)',
	)
	parser.add_argument(
		'-s', '--sleep-max', dest='sleep_max', required=False, type=float,
		default=1.0,
		help='Max random sleep (seconds) before each request (default: 1.0)',
	)
	parser.add_argument(
		'-t', '--timeout', dest='timeout', required=False, type=float,
		default=20.0,
		help='Request timeout (seconds) (default: 20.0)',
	)
	parser.add_argument(
		'-n', '--max', dest='max_items', required=False, type=int,
		default=None,
		help='Optional max items (for testing)',
	)
	parser.add_argument(
		'-v', '--verbose', dest='verbose', required=False,
		action='store_true',
		help='Print per-URL progress and extracted fields',
	)

	args = parser.parse_args()
	return args


#============================================
def normalize_text(text: str) -> str:
	"""
	Normalize extracted text: unescape entities, collapse whitespace, strip.

	Args:
		text (str): Input text.

	Returns:
		str: Normalized text.
	"""
	text = str(text or '')
	text = html.unescape(text)
	text = text.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
	text = re.sub(r'\s+', ' ', text)
	text = text.strip()
	return text


#============================================
def looks_like_html(text: str) -> bool:
	"""
	Detect obvious HTML fragments in extracted fields.

	Args:
		text (str): Candidate text.

	Returns:
		bool: True if it looks like HTML.
	"""
	text = str(text or '')
	if '<' not in text or '>' not in text:
		return False

	lower = text.lower()
	if '<meta' in lower or '<html' in lower or '<head' in lower or '<title' in lower:
		return True

	return False


#============================================
def safe_ascii(text: str) -> str:
	"""
	Best-effort ASCII-only string (drops non-ascii).

	Args:
		text (str): Input text.

	Returns:
		str: ASCII-only string.
	"""
	text = str(text or '')
	out = text.encode('ascii', errors='ignore').decode('ascii', errors='ignore')
	return out


#============================================
def slugify(text: str) -> str:
	"""
	Make a URL-ish slug from text (lowercase, a-z0-9 and hyphens).

	Args:
		text (str): Input text.

	Returns:
		str: Slug.
	"""
	text = safe_ascii(normalize_text(text)).lower()
	text = re.sub(r'[^a-z0-9]+', '-', text)
	text = text.strip('-')
	text = re.sub(r'-{2,}', '-', text)
	return text


#============================================
def keyify_source(source: str) -> str:
	"""
	Make a deterministic source key (lowercase, alnum only).

	Args:
		source (str): Source/publisher name.

	Returns:
		str: Key (e.g., "Daily Herald" -> "dailyherald").
	"""
	source = safe_ascii(normalize_text(source)).lower()
	source = re.sub(r'[^a-z0-9]+', '', source)
	return source


#============================================
def domain_key(domain: str) -> str:
	"""
	Derive a reasonable key from a domain.

	Args:
		domain (str): Domain (netloc).

	Returns:
		str: Domain key (usually second-level domain).
	"""
	domain = str(domain or '').strip().lower()
	domain = domain.split(':')[0]
	labels = [p for p in domain.split('.') if p]
	if len(labels) >= 2:
		return labels[-2]
	if labels:
		return labels[0]
	return ''


#============================================
def date_from_time_text(time_text: str) -> str:
	"""
	Get YYYY-MM-DD from an ISO-ish datetime string.

	Args:
		time_text (str): Datetime string.

	Returns:
		str: Date in YYYY-MM-DD or ''.
	"""
	time_text = str(time_text or '').strip()
	if len(time_text) < 10:
		return ''
	date_part = time_text[:10]
	if re.match(r'^\d{4}-\d{2}-\d{2}$', date_part):
		return date_part
	return ''


#============================================
def date_from_url(url: str) -> str:
	"""
	Best-effort YYYY-MM-DD extraction from URL path.

	Supported patterns:
	- /YYYYMMDD/
	- /YYYY/MM/DD/

	Args:
		url (str): URL.

	Returns:
		str: YYYY-MM-DD or ''.
	"""
	try:
		path = urllib.parse.urlparse(str(url or '')).path or ''
	except Exception:
		path = str(url or '')

	match = re.search(r'/(20\d{2})(\d{2})(\d{2})(?:/|$)', path)
	if match:
		return match.group(1) + '-' + match.group(2) + '-' + match.group(3)

	match = re.search(r'/(20\d{2})/(\d{2})/(\d{2})(?:/|$)', path)
	if match:
		return match.group(1) + '-' + match.group(2) + '-' + match.group(3)

	return ''


#============================================
def title_from_url(url: str) -> str:
	"""
	Derive a readable title from the URL slug.

	Args:
		url (str): URL.

	Returns:
		str: Title or ''.
	"""
	try:
		path = urllib.parse.urlparse(str(url or '')).path or ''
	except Exception:
		path = str(url or '')

	path = path.strip('/')
	if not path:
		return ''

	parts = [p for p in path.split('/') if p]
	if not parts:
		return ''

	slug = parts[-1]
	slug = urllib.parse.unquote(slug)
	slug = slug.split('?')[0].split('#')[0]

	if slug.lower().endswith('.html') or slug.lower().endswith('.htm'):
		slug = slug.rsplit('.', 1)[0]

	if not slug or re.match(r'^\d+$', slug):
		return ''

	slug = slug.replace('_', '-')
	raw_words = [w for w in slug.split('-') if w]
	if not raw_words:
		return ''

	small = set(['a', 'an', 'the', 'and', 'or', 'but', 'to', 'of', 'in', 'on', 'at', 'for', 'with', 'by'])
	out_words = []
	for i, w in enumerate(raw_words):
		w_clean = re.sub(r'[^A-Za-z0-9]+', '', w)
		if not w_clean:
			continue

		lower = w_clean.lower()
		if lower == 'lego':
			out_words.append('LEGO')
			continue
		if lower == 'niltc':
			out_words.append('NILTC')
			continue

		if w_clean.isupper() and len(w_clean) <= 5:
			out_words.append(w_clean)
			continue

		if i != 0 and lower in small:
			out_words.append(lower)
			continue

		out_words.append(lower[:1].upper() + lower[1:])

	title = ' '.join(out_words)
	title = normalize_text(title)
	return title


#============================================
def teaser_truncate(description: str, max_words: int = 12) -> str:
	"""
	Truncate a description to up to max_words words plus ellipsis.

	Args:
		description (str): Description text.
		max_words (int): Max number of words.

	Returns:
		str: Teaser.
	"""
	description = normalize_text(description)
	if not description:
		return ''

	words = description.split(' ')
	if len(words) <= max_words:
		return description

	out = ' '.join(words[:max_words]) + '...'
	return out


#============================================
def normalize_url(url: str) -> str:
	"""
	Normalize URL strings (mainly HTML entity unescaping + strip).

	Args:
		url (str): URL string.

	Returns:
		str: Normalized URL.
	"""
	url = normalize_text(url)
	return url


#============================================
def parse_canonical_url(html_text: str, base_url: str) -> str:
	"""
	Extract a canonical URL from HTML.

	Priority:
	- <link rel="canonical" href="...">
	- meta property="og:url"

	Args:
		html_text (str): HTML text.
		base_url (str): Base URL for resolving relative links.

	Returns:
		str: Canonical URL or ''.
	"""
	html_text = str(html_text or '')
	base_url = str(base_url or '').strip()

	parsed = parse_head_data(html_text)
	href = normalize_url(parsed.get('canonical_url', '') or '')
	if href:
		return urllib.parse.urljoin(base_url, href)

	og_url = normalize_url((parsed.get('meta_property', {}) or {}).get('og:url', '') or '')
	if og_url:
		return urllib.parse.urljoin(base_url, og_url)

	return ''


#============================================
class _HeadParser(html.parser.HTMLParser):
	"""
	Simple HTML head parser for meta/link/title.
	"""

	def __init__(self):
		super().__init__()
		self.meta_name = {}
		self.meta_property = {}
		self.canonical_url = ''
		self._in_title = False
		self._title_parts = []

	def handle_starttag(self, tag, attrs):
		tag = str(tag or '').lower()
		attrs_dict = {}
		for k, v in (attrs or []):
			if not k:
				continue
			attrs_dict[str(k).lower()] = str(v or '')

		if tag == 'meta':
			content = normalize_text(attrs_dict.get('content', '') or '')
			if not content:
				return
			name = normalize_text(attrs_dict.get('name', '') or '').lower()
			prop = normalize_text(attrs_dict.get('property', '') or '').lower()
			if name:
				self.meta_name[name] = content
			if prop:
				self.meta_property[prop] = content
			return

		if tag == 'link':
			rel = normalize_text(attrs_dict.get('rel', '') or '').lower()
			href = normalize_text(attrs_dict.get('href', '') or '')
			if rel == 'canonical' and href:
				self.canonical_url = href
			return

		if tag == 'title':
			self._in_title = True
			return

	def handle_endtag(self, tag):
		tag = str(tag or '').lower()
		if tag == 'title':
			self._in_title = False

	def handle_data(self, data):
		if not self._in_title:
			return
		data = normalize_text(data)
		if data:
			self._title_parts.append(data)

	def get_title(self) -> str:
		out = ' '.join(self._title_parts)
		out = normalize_text(out)
		return out


#============================================
def parse_head_data(html_text: str) -> dict:
	"""
	Parse head metadata using stdlib HTMLParser.

	Args:
		html_text (str): HTML text.

	Returns:
		dict: {'meta_name':{}, 'meta_property':{}, 'canonical_url':'', 'title':''}
	"""
	parser = _HeadParser()
	parser.feed(str(html_text or ''))
	out = {
		'meta_name': parser.meta_name,
		'meta_property': parser.meta_property,
		'canonical_url': normalize_text(parser.canonical_url),
		'title': parser.get_title(),
	}
	return out


#============================================
def sha1_12(text: str) -> str:
	"""
	Get a short SHA1 prefix for stable cache filenames.

	Args:
		text (str): Input text.

	Returns:
		str: First 12 hex chars of SHA1.
	"""
	text = str(text or '')
	h = hashlib.sha1(text.encode('utf-8', errors='ignore')).hexdigest()
	return h[:12]


#============================================
def head_cache_path_for_url(url: str, cache_dir: str = HEAD_CACHE_DIR_DEFAULT) -> str:
	"""
	Get deterministic head cache path for a URL.

	Args:
		url (str): URL.
		cache_dir (str): Cache directory.

	Returns:
		str: Cache file path.
	"""
	url = normalize_url(url)
	cache_dir = str(cache_dir or '').strip() or HEAD_CACHE_DIR_DEFAULT
	name = sha1_12(url) + '.head.html'
	return os.path.join(cache_dir, name)


#============================================
def extract_best_url_from_html_head(html_text: str, base_url: str) -> str:
	"""
	Extract a "best URL" from an HTML document head.

	Priority:
	1) <link rel="canonical">
	2) meta property="og:url"
	3) meta name="twitter:url"
	4) JSON-LD mainEntityOfPage.@id or url
	"""
	html_text = str(html_text or '')
	base_url = normalize_url(base_url)

	parsed = parse_head_data(html_text)
	meta_name = parsed.get('meta_name', {}) or {}
	meta_property = parsed.get('meta_property', {}) or {}

	canonical = normalize_url(parsed.get('canonical_url', '') or '')
	if canonical:
		canonical = urllib.parse.urljoin(base_url, canonical)

	og_url = normalize_url(meta_property.get('og:url', '') or '')
	if og_url:
		og_url = urllib.parse.urljoin(base_url, og_url)

	twitter_url = normalize_url(meta_name.get('twitter:url', '') or '')
	if twitter_url:
		twitter_url = urllib.parse.urljoin(base_url, twitter_url)

	jsonld_url = ''
	for jsonld_value in extract_json_ld_objects(html_text):
		candidates = []
		if isinstance(jsonld_value, dict):
			candidates.append(jsonld_value)
		elif isinstance(jsonld_value, list):
			for it in jsonld_value:
				if isinstance(it, dict):
					candidates.append(it)

		for obj in candidates:
			me = obj.get('mainEntityOfPage')
			if isinstance(me, dict) and isinstance(me.get('@id'), str):
				jsonld_url = normalize_url(me.get('@id') or '')
				break
			if isinstance(obj.get('url'), str):
				jsonld_url = normalize_url(obj.get('url') or '')
				break
		if jsonld_url:
			break
	if jsonld_url:
		jsonld_url = urllib.parse.urljoin(base_url, jsonld_url)

	for u in [canonical, og_url, twitter_url, jsonld_url]:
		u = normalize_url(u)
		if not u:
			continue
		if u.startswith('//'):
			u = 'https:' + u
		if u.startswith('http'):
			return u

	return ''


#============================================
def _json_sanitize_no_images(value):
	"""
	Remove image-like fields from JSON-LD objects (recursive).

	Args:
		value: JSON-compatible value.

	Returns:
		Sanitized value.
	"""
	if isinstance(value, list):
		return [_json_sanitize_no_images(v) for v in value]

	if isinstance(value, dict):
		drop = set(['image', 'thumbnail', 'thumbnailurl', 'thumbnailUrl', 'logo'])
		out = {}
		for k, v in value.items():
			ks = str(k or '')
			k_lower = ks.lower()
			if k_lower in drop:
				continue
			out[k] = _json_sanitize_no_images(v)
		return out

	return value


#============================================
def _is_image_meta(attrs: dict) -> bool:
	"""
	Detect meta tags that reference images (to exclude from cache).
	"""
	name = normalize_text(attrs.get('name', '') or '').lower()
	prop = normalize_text(attrs.get('property', '') or '').lower()
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
	"""
	Detect link tags that reference icons/images (to exclude from cache).
	"""
	rel = normalize_text(attrs.get('rel', '') or '').lower()
	as_attr = normalize_text(attrs.get('as', '') or '').lower()

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
class _HeadCacheCollector(html.parser.HTMLParser):
	"""
	Collect title/meta/link and JSON-LD scripts for a compact head cache.
	"""

	def __init__(self):
		super().__init__()
		self._in_title = False
		self._title_parts = []
		self._in_jsonld = False
		self._jsonld_parts = []

		self.meta_tags = []
		self.link_tags = []
		self.jsonld_scripts = []

	def handle_starttag(self, tag, attrs):
		tag = str(tag or '').lower()
		attrs_dict = {}
		for k, v in (attrs or []):
			if not k:
				continue
			attrs_dict[str(k).lower()] = str(v or '')

		if tag == 'title':
			self._in_title = True
			return

		if tag == 'meta':
			if not _is_image_meta(attrs_dict):
				self.meta_tags.append(attrs_dict)
			return

		if tag == 'link':
			if not _is_image_link(attrs_dict):
				self.link_tags.append(attrs_dict)
			return

		if tag == 'script':
			type_attr = normalize_text(attrs_dict.get('type', '') or '').lower()
			if type_attr == 'application/ld+json':
				self._in_jsonld = True
				self._jsonld_parts = []

	def handle_endtag(self, tag):
		tag = str(tag or '').lower()
		if tag == 'title':
			self._in_title = False
			return

		if tag == 'script' and self._in_jsonld:
			raw = ''.join(self._jsonld_parts)
			raw = raw.strip()
			self._in_jsonld = False
			self._jsonld_parts = []
			if raw:
				self.jsonld_scripts.append(raw)

	def handle_data(self, data):
		if self._in_title:
			data = normalize_text(data)
			if data:
				self._title_parts.append(data)
			return

		if self._in_jsonld:
			self._jsonld_parts.append(str(data or ''))

	def title_text(self) -> str:
		return normalize_text(' '.join(self._title_parts))


#============================================
def build_head_cache_html(full_html: str) -> str:
	"""
	Build a minimal HTML document containing only the head metadata we care about.

	Includes:
	- <title>
	- all <meta ...> (excluding image-related)
	- all <link ...> (excluding icons/images)
	- all <script type="application/ld+json"> (sanitized to remove image fields)
	"""
	parser = _HeadCacheCollector()
	parser.feed(str(full_html or ''))

	lines = []
	lines.append('<!doctype html>')
	lines.append('<html>')
	lines.append('<head>')

	title = parser.title_text()
	if title:
		lines.append('<title>' + html.escape(title) + '</title>')

	def emit_tag(tag: str, attrs: dict):
		parts = [tag]
		for k in sorted(attrs.keys()):
			v = str(attrs.get(k, '') or '')
			if v == '':
				continue
			parts.append(f'{k}=\"{html.escape(v, quote=True)}\"')
		return '<' + ' '.join(parts) + '>'

	for attrs in parser.meta_tags:
		lines.append(emit_tag('meta', attrs))

	for attrs in parser.link_tags:
		lines.append(emit_tag('link', attrs))

	for raw in parser.jsonld_scripts:
		# Prefer safe JSON-LD (no image fields). If invalid JSON, omit from cache.
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
def read_text_file(path: str) -> str:
	"""
	Read a UTF-8 text file (best-effort).
	"""
	with open(path, 'r', encoding='utf-8', errors='ignore') as f:
		return f.read()


#============================================
def read_csv_rows(csv_path: str) -> list:
	"""
	Read input CSV rows.

	Args:
		csv_path (str): CSV file path.

	Returns:
		list: List of dict rows.
	"""
	with open(csv_path, 'r', encoding='utf-8', newline='') as f:
		reader = csv.DictReader(f)
		rows = []
		for row in reader:
			if not isinstance(row, dict):
				continue
			rows.append(row)
	return rows


#============================================
def iso_utc_now() -> str:
	"""
	Get a stable UTC timestamp for YAML/CSV fields.

	Returns:
		str: ISO 8601 UTC timestamp like 2025-12-14T15:59:55Z
	"""
	now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
	return now.isoformat().replace('+00:00', 'Z')


#============================================
def make_id_from_url(url: str) -> str:
	"""
	Deterministic id from URL: domain_key + date + slug.

	Args:
		url (str): URL.

	Returns:
		str: Deterministic id.
	"""
	url = normalize_text(url)
	parsed = urllib.parse.urlparse(url)
	domain = parsed.netloc
	dkey = domain_key(domain) or 'unknown'

	date_part = date_from_url(url)
	if not date_part:
		date_part = 'unknown-date'

	last = parsed.path.strip('/').split('/')[-1] if parsed.path else ''
	last = urllib.parse.unquote(last)
	if last.lower().endswith('.html') or last.lower().endswith('.htm'):
		last = last.rsplit('.', 1)[0]
	slug = slugify(last) or 'untitled'

	return f'{dkey}-{date_part}-{slug}'


#============================================
def snapshot_path_for(domain: str, item_id: str) -> str:
	"""
	Deterministic snapshot path for an item.

	Args:
		domain (str): Domain/netloc.
		item_id (str): Item id.

	Returns:
		str: Snapshot path.
	"""
	domain = str(domain or '').strip().lower() or 'unknown'
	item_id = str(item_id or '').strip() or 'unknown'
	return os.path.join('snapshots', domain, item_id + '.html')


#============================================
def read_yaml_or_default(yaml_path: str) -> list:
	"""
	Read YAML file or return an empty list.

	Args:
		yaml_path (str): YAML file path.

	Returns:
		list: Parsed YAML list of records.
	"""
	if not os.path.exists(yaml_path):
		return []

	with open(yaml_path, 'r', encoding='utf-8') as f:
		data = yaml.safe_load(f)

	if data is None:
		return []

	# New schema: top-level list of records.
	if isinstance(data, list):
		return data

	# Backward-compatible: schema 1 dict with items.
	if isinstance(data, dict) and isinstance(data.get('items', None), list):
		out = []
		for old in data.get('items', []):
			if not isinstance(old, dict):
				continue
			url = normalize_text(old.get('url', '') or '')
			if not url:
				continue
			final_url = normalize_text(old.get('final_url', '') or url)
			domain = urllib.parse.urlparse(final_url).netloc
			item_id = make_id_from_url(url)
			source = normalize_text(old.get('source', '') or '') or domain_to_source(domain) or domain

			last_checked = normalize_text(old.get('last_checked', '') or '')
			checked_at = ''
			if re.match(r'^\d{4}-\d{2}-\d{2}$', last_checked):
				checked_at = last_checked + 'T00:00:00Z'

			status_code = int(old.get('status_code', 0) or 0)
			reachable = bool(status_code == 200)

			title = normalize_text(old.get('title', '') or '') or None
			published_time = normalize_text(old.get('published_time', '') or '') or None
			author = normalize_text(old.get('author', '') or '') or None
			teaser = normalize_text(old.get('teaser', '') or '') or None
			canonical_url = normalize_text(old.get('canonical_url', '') or '') or None

			metadata_source = 'none'
			if title or published_time:
				metadata_source = 'live'

			out.append({
				'id': item_id,
				'url': url,
				'source': source,
				'network': {
					'checked_at': checked_at or '',
					'status_code': status_code or None,
					'final_url': final_url,
					'content_type': '',
					'response_bytes': None,
					'redirect_chain': [],
					'reachable': reachable,
					'blocked': False,
					'blocked_reason': '',
				},
				'extracted': {
					'metadata_source': metadata_source,
					'title': title,
					'published_time': published_time,
					'author': author,
					'teaser': teaser,
					'canonical_url': canonical_url,
				},
			})
		return out

	raise ValueError('Unexpected YAML format for in_the_news.yml')


#============================================
def order_story_fields(story: dict) -> dict:
	"""
	Order story keys for stable YAML diffs.
	"""
	keys = [
		'id',
		'fingerprint',
		'source',
		'published_date',
		'title',
		'author',
		'teaser',
		'primary_url',
		'urls',
	]
	out = {}
	for k in keys:
		if k in story:
			out[k] = story.get(k)
	for k in story.keys():
		if k in out:
			continue
		out[k] = story.get(k)
	return out


#============================================
def order_pending_fields(pending: dict) -> dict:
	"""
	Order pending keys for stable YAML diffs.
	"""
	keys = [
		'url',
		'source',
		'cache_path',
		'last_checked',
		'reason',
	]
	out = {}
	for k in keys:
		if k in pending:
			out[k] = pending.get(k)
	for k in pending.keys():
		if k in out:
			continue
		out[k] = pending.get(k)
	return out


#============================================
def read_news_store(yaml_path: str) -> dict:
	"""
	Read canonical in-the-news YAML store.

	New schema:
		schema: 1
		stories: [ ... ]
		pending: [ ... ]

	Backward-compatible:
	- schema 1 dict with items (old pipeline)
	"""
	if not os.path.exists(yaml_path):
		return {'schema': 1, 'stories': [], 'pending': []}

	with open(yaml_path, 'r', encoding='utf-8') as f:
		data = yaml.safe_load(f)

	if data is None:
		return {'schema': 1, 'stories': [], 'pending': []}

	if isinstance(data, dict) and isinstance(data.get('stories', None), list):
		out = {'schema': int(data.get('schema', 1) or 1), 'stories': data.get('stories', []), 'pending': data.get('pending', []) or []}
		if not isinstance(out.get('pending', None), list):
			out['pending'] = []
		return out

	# Convert legacy schema 1: {schema:1, items:[...]}
	if isinstance(data, dict) and isinstance(data.get('items', None), list):
		provisional = []

		for old in data.get('items', []):
			if not isinstance(old, dict):
				continue

			urls = []
			for u in [old.get('url', ''), old.get('final_url', ''), old.get('canonical_url', '')]:
				u = normalize_url(u)
				if u and u not in urls:
					urls.append(u)

			source = normalize_text(old.get('source', '') or '')
			if not source:
				d = urllib.parse.urlparse(urls[0]).netloc if urls else ''
				source = domain_to_source(d) or d

			title = normalize_text(old.get('title', '') or '')
			published_time = normalize_text(old.get('published_time', '') or '')
			published_date = date_from_time_text(published_time) or date_from_url(urls[0] if urls else '')

			author = normalize_text(old.get('author', '') or '') or None
			teaser = normalize_text(old.get('teaser', '') or '') or None

			if not title or not published_date:
				continue

			provisional.append({
				'source': source,
				'published_date': published_date,
				'title': title,
				'author': author,
				'teaser': teaser,
				'urls': urls,
			})

		# Deterministic id assignment: per date, in (date,title,source) order.
		provisional = sorted(provisional, key=lambda s: (s.get('published_date', ''), s.get('title', ''), s.get('source', '')))
		used_ids = set()
		stories = []
		for s in provisional:
			sid = allocate_story_id(s.get('published_date', ''), used_ids)
			out = dict(s)
			out['id'] = sid
			stories.append(out)

		return {'schema': 1, 'stories': stories, 'pending': []}

	# If this was the intermediate list schema, leave empty rather than failing.
	if isinstance(data, list):
		return {'schema': 1, 'stories': [], 'pending': []}

	raise ValueError('Unexpected YAML format for in_the_news.yml')


#============================================
def _suffix_sequence():
	"""
	Yield suffixes: a..z, aa..az, ba..bz, ...
	"""
	letters = 'abcdefghijklmnopqrstuvwxyz'
	for a in letters:
		yield a
	for a in letters:
		for b in letters:
			yield a + b


#============================================
def allocate_story_id(published_date: str, used_ids: set) -> str:
	"""
	Allocate the next available YYYYMMDD suffix id.
	"""
	date_key = str(published_date or '').replace('-', '')
	if not re.match(r'^\d{8}$', date_key):
		date_key = '00000000'

	for suffix in _suffix_sequence():
		cand = date_key + suffix
		if cand in used_ids:
			continue
		used_ids.add(cand)
		return cand

	# Extremely unlikely to run out in practice.
	raise RuntimeError('Unable to allocate story id (too many for one date)')


#============================================
def normalize_fingerprint_text(text: str) -> str:
	"""
	Normalize text for story fingerprinting.

	Rules:
	- lowercase
	- replace unicode dashes with "-"
	- treat dashes as whitespace
	- remove punctuation (keep alphanumerics + spaces)
	- collapse whitespace
	"""
	text = normalize_text(text).lower()

	# Normalize unicode dashes to a hyphen, then treat hyphens as word separators.
	for ch in ['\u2010', '\u2011', '\u2012', '\u2013', '\u2014', '\u2015', '\u2212']:
		text = text.replace(ch, '-')
	text = text.replace('-', ' ')

	# Remove punctuation; keep only a-z0-9 and spaces.
	text = re.sub(r'[^a-z0-9 ]+', ' ', text)
	text = re.sub(r'\s+', ' ', text).strip()
	return text


#============================================
def make_story_fingerprint(published_date: str, source: str, title: str) -> str:
	"""
	Make a stable fingerprint used to dedupe stories.
	"""
	published_date = normalize_text(published_date)
	return published_date + '|' + normalize_fingerprint_text(source) + '|' + normalize_fingerprint_text(title)


#============================================
def primary_url_score(url: str, head_url: str, final_url: str, input_url: str) -> int:
	"""
	Score a URL for story.primary_url selection.

	Priority:
	1) head-derived canonical/og/twitter/url (https only)
	2) final_url after redirects
	3) original input url
	"""
	url_n = normalize_url(url)
	head_n = normalize_url(head_url)
	final_n = normalize_url(final_url)
	input_n = normalize_url(input_url)

	if url_n and head_n and url_n == head_n and url_n.startswith('https://'):
		return 30
	if url_n and final_n and url_n == final_n:
		return 20
	if url_n and input_n and url_n == input_n:
		return 10
	if url_n.startswith('https://'):
		return 15
	return 5


#============================================
def normalize_dedup_key(source: str, published_date: str, title: str) -> str:
	"""
	Backward-compatible alias for older code paths.
	"""
	return make_story_fingerprint(published_date, source, title)


#============================================
def write_text_file_if_changed(path: str, content: str) -> bool:
	"""
	Write a text file only if content changed.

	Args:
		path (str): File path.
		content (str): New file content.

	Returns:
		bool: True if file was written/updated.
	"""
	parent_dir = os.path.dirname(path)
	if parent_dir:
		os.makedirs(parent_dir, exist_ok=True)

	if os.path.exists(path):
		with open(path, 'r', encoding='utf-8') as f:
			existing = f.read()
		if existing == content:
			return False

	with open(path, 'w', encoding='utf-8') as f:
		f.write(content)
	return True


#============================================
def yaml_dump(data) -> str:
	"""
	Dump YAML with stable formatting.

	Args:
		data (dict): YAML dict.

	Returns:
		str: YAML text.
	"""
	out = yaml.safe_dump(
		data,
		sort_keys=False,
		default_flow_style=False,
		width=100,
		allow_unicode=True,
	)
	return out


#============================================
def extract_json_ld_objects(html_text: str) -> list:
	"""
	Extract JSON-LD objects from script tags.

	Args:
		html_text (str): HTML text.

	Returns:
		list: List of parsed JSON values (dicts/lists).
	"""
	html_text = str(html_text or '')
	pattern = r'<script[^>]+type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>'
	matches = re.findall(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)

	out = []
	for raw in matches:
		raw = raw.strip()
		if not raw:
			continue
		try:
			parsed = json.loads(raw)
		except Exception:
			continue
		out.append(parsed)

	return out


#============================================
def jsonld_pick_article(jsonld_value):
	"""
	Pick the first NewsArticle/Article object from JSON-LD.

	Args:
		jsonld_value: Parsed JSON-LD value (dict/list).

	Returns:
		dict: Article-like object or {}.
	"""
	candidates = []

	if isinstance(jsonld_value, dict):
		candidates.append(jsonld_value)
	elif isinstance(jsonld_value, list):
		for item in jsonld_value:
			if isinstance(item, dict):
				candidates.append(item)

	for obj in candidates:
		type_val = obj.get('@type')
		types = []
		if isinstance(type_val, str):
			types = [type_val]
		elif isinstance(type_val, list):
			types = [str(t) for t in type_val if t]

		types_lower = [str(t).lower() for t in types]
		if 'newsarticle' in types_lower or 'article' in types_lower:
			return obj

	return {}


#============================================
def extract_meta_content(html_text: str, attr_name: str, attr_value: str) -> str:
	"""
	Extract a meta tag content attribute by name/property.

	Args:
		html_text (str): HTML text.
		attr_name (str): 'name' or 'property'.
		attr_value (str): Attribute value.

	Returns:
		str: Meta content or ''.
	"""
	html_text = str(html_text or '')
	attr_name = str(attr_name or '').strip().lower()
	attr_value = str(attr_value or '').strip()

	# This is intentionally simple and regex-based (no full HTML parsing).
	pattern = (
		r'<meta[^>]+'
		+ attr_name
		+ r'=[\"\']'
		+ re.escape(attr_value)
		+ r'[\"\'][^>]*content=[\"\'](.*?)[\"\'][^>]*>'
	)
	match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
	if not match:
		pattern2 = (
			r'<meta[^>]+content=[\"\'](.*?)[\"\'][^>]*'
			+ attr_name
			+ r'=[\"\']'
			+ re.escape(attr_value)
			+ r'[\"\'][^>]*>'
		)
		match = re.search(pattern2, html_text, flags=re.IGNORECASE | re.DOTALL)

	if not match:
		return ''

	return normalize_text(match.group(1))


#============================================
def extract_html_title(html_text: str) -> str:
	"""
	Extract HTML <title>.

	Args:
		html_text (str): HTML text.

	Returns:
		str: Title or ''.
	"""
	match = re.search(r'<title[^>]*>(.*?)</title>', str(html_text or ''), flags=re.IGNORECASE | re.DOTALL)
	if not match:
		return ''
	return normalize_text(match.group(1))


#============================================
def strip_tags(text: str) -> str:
	"""
	Remove HTML tags (best-effort).

	Args:
		text (str): HTML snippet.

	Returns:
		str: Plain-ish text.
	"""
	text = str(text or '')
	text = re.sub(r'<script.*?</script>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
	text = re.sub(r'<style.*?</style>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
	text = re.sub(r'<[^>]+>', ' ', text)
	text = normalize_text(text)
	return text


#============================================
def extract_byline_fallback(html_text: str) -> str:
	"""
	Very simple byline fallback: find "By <Name>" near top of doc.

	Args:
		html_text (str): HTML text.

	Returns:
		str: Author name or ''.
	"""
	snippet = str(html_text or '')[:8000]
	plain = strip_tags(snippet)

	match = re.search(
		r'\bBy\s+([A-Z][A-Za-z\.\'\-]+(?:\s+[A-Z][A-Za-z\.\'\-]+){0,4})\b',
		plain,
		flags=re.IGNORECASE,
	)
	if not match:
		return ''

	name = normalize_text(match.group(1))
	if not name:
		return ''
	if len(name) > 60:
		return ''
	return name


#============================================
def extract_metadata(html_text: str) -> dict:
	"""
	Extract metadata from HTML using JSON-LD, then meta tags, then HTML fallbacks.

	Args:
		html_text (str): HTML text.

	Returns:
		dict: Metadata fields (title, author, published_time, modified_time, source, teaser).
	"""
	meta = {
		'title': '',
		'author': '',
		'published_time': '',
		'modified_time': '',
		'source': '',
		'teaser': '',
	}

	# 1) JSON-LD (preferred)
	jsonld_values = extract_json_ld_objects(html_text)
	for jsonld_value in jsonld_values:
		obj = jsonld_pick_article(jsonld_value)
		if not obj:
			continue

		meta['title'] = normalize_text(obj.get('headline', '') or '')
		meta['published_time'] = normalize_text(obj.get('datePublished', '') or '')
		meta['modified_time'] = normalize_text(obj.get('dateModified', '') or '')

		author = obj.get('author')
		if isinstance(author, dict):
			meta['author'] = normalize_text(author.get('name', '') or '')
		elif isinstance(author, list) and author:
			first = author[0]
			if isinstance(first, dict):
				meta['author'] = normalize_text(first.get('name', '') or '')
			else:
				meta['author'] = normalize_text(first)
		elif isinstance(author, str):
			meta['author'] = normalize_text(author)

		publisher = obj.get('publisher', {})
		if isinstance(publisher, dict):
			meta['source'] = normalize_text(publisher.get('name', '') or '')

		description = normalize_text(obj.get('description', '') or '')
		meta['teaser'] = teaser_truncate(description)

		# Found an article object; stop.
		break

	parsed = parse_head_data(html_text)
	meta_name = parsed.get('meta_name', {}) or {}
	meta_property = parsed.get('meta_property', {}) or {}

	# 2) Meta tags (Open Graph / article)
	if not meta['author']:
		meta['author'] = normalize_text(meta_name.get('author', '') or '')
	if not meta['author']:
		meta['author'] = normalize_text(meta_name.get('sailthru.author', '') or '')
	if not meta['published_time']:
		meta['published_time'] = normalize_text(meta_property.get('article:published_time', '') or '')
	if not meta['published_time']:
		meta['published_time'] = normalize_text(meta_name.get('parsely-pub-date', '') or '')
	if not meta['published_time']:
		meta['published_time'] = normalize_text(meta_name.get('sailthru.date', '') or '')
	if not meta['modified_time']:
		meta['modified_time'] = normalize_text(meta_property.get('article:modified_time', '') or '')
	if not meta['title']:
		meta['title'] = normalize_text(meta_property.get('og:title', '') or '')
	if not meta['source']:
		meta['source'] = normalize_text(meta_property.get('og:site_name', '') or '')
	if not meta['teaser']:
		meta['teaser'] = teaser_truncate(meta_property.get('og:description', '') or '')

	# 3) HTML fallback
	if not meta['title']:
		meta['title'] = normalize_text(parsed.get('title', '') or '') or extract_html_title(html_text)
	if not meta['author']:
		meta['author'] = extract_byline_fallback(html_text)

	return meta


#============================================
def domain_to_source(domain: str) -> str:
	"""
	Domain fallback map for source.

	Args:
		domain (str): Domain (netloc).

	Returns:
		str: Source name or ''.
	"""
	d = str(domain or '').lower()
	d = d.split(':')[0]
	if d.endswith('dailyherald.com'):
		return 'Daily Herald'
	if d.endswith('chicagotribune.com'):
		return 'Chicago Tribune'
	if d.endswith('omaha.com'):
		return 'Omaha World-Herald'
	if d.endswith('ketv.com'):
		return 'KETV'
	if d.endswith('nonpareilonline.com'):
		return 'Daily Nonpareil'
	if d.endswith('kcchronicle.com'):
		return 'Kane County Chronicle'
	return ''


#============================================
def make_item_id(source: str, domain: str, published_time: str, title: str, url: str) -> str:
	"""
	Make deterministic id: {source_or_domain}-{published_date}-{slug}.

	Args:
		source (str): Source name.
		domain (str): Domain.
		published_time (str): Published datetime text.
		title (str): Title text.
		url (str): Original URL.

	Returns:
		str: Deterministic id.
	"""
	date_part = date_from_time_text(published_time)
	if not date_part:
		date_part = 'unknown-date'

	source_key = keyify_source(source)
	if not source_key:
		source_key = domain_key(domain)

	slug = slugify(title)
	if not slug:
		# Fallback to URL path last segment.
		path = urllib.parse.urlparse(url).path
		path = path.strip('/').split('/')[-1] if path else ''
		slug = slugify(path)
	if not slug:
		slug = 'untitled'

	out = f'{source_key}-{date_part}-{slug}'
	return out


#============================================
def merge_notes(existing_notes: str, new_note: str) -> str:
	"""
	Preserve manual notes; append new auto notes if needed.

	Args:
		existing_notes (str): Existing notes.
		new_note (str): New note (auto).

	Returns:
		str: Merged notes.
	"""
	existing_notes = normalize_text(existing_notes)
	new_note = normalize_text(new_note)

	if not existing_notes:
		return new_note
	if not new_note:
		return existing_notes
	if new_note.lower() in existing_notes.lower():
		return existing_notes

	out = existing_notes + '; ' + new_note
	return out


#============================================
def remove_note_token(notes: str, token: str) -> str:
	"""
	Remove a single token from a semicolon-separated notes field.

	Args:
		notes (str): Notes string.
		token (str): Token to remove (case-insensitive).

	Returns:
		str: Notes with token removed.
	"""
	notes = normalize_text(notes)
	token = normalize_text(token).lower()
	if not notes or not token:
		return notes

	parts = [p.strip() for p in notes.split(';') if p.strip()]
	kept = []
	for part in parts:
		if part.lower() == token:
			continue
		kept.append(part)

	out = '; '.join(kept)
	return out


#============================================
def is_chicago_tribune(domain: str) -> bool:
	"""
	Check if a domain is Chicago Tribune.

	Args:
		domain (str): Domain.

	Returns:
		bool: True if Chicago Tribune.
	"""
	domain = str(domain or '').lower()
	return domain.endswith('chicagotribune.com')


#============================================
def is_html_content_type(content_type: str) -> bool:
	"""
	Check if a Content-Type header suggests HTML.

	Args:
		content_type (str): Content-Type header.

	Returns:
		bool: True if likely HTML.
	"""
	content_type = str(content_type or '').lower().strip()
	if not content_type:
		return True
	if 'text/html' in content_type:
		return True
	if 'application/xhtml+xml' in content_type:
		return True
	return False


#============================================
def detect_block_markers(html_text: str) -> list:
	"""
	Detect obvious bot-block/captcha/access-denied markers in HTML.

	Args:
		html_text (str): HTML text.

	Returns:
		list: List of marker tokens.
	"""
	lower = str(html_text or '').lower()
	markers = []

	tests = [
		('enable_javascript', 'enable javascript'),
		('captcha', 'captcha'),
		('access_denied', 'access denied'),
		('incident_id', 'incident id'),
		('incapsula', 'incapsula'),
		('imperva', 'imperva'),
		('bot_check', 'are you a robot'),
		('cloudflare', 'cf-browser-verification'),
	]
	for token, needle in tests:
		if needle in lower:
			markers.append(token)

	return markers


#============================================
def title_preview(html_text: str) -> str:
	"""
	Get a short preview of the HTML title tag.

	Args:
		html_text (str): HTML text.

	Returns:
		str: Title preview (first 200 chars) or ''.
	"""
	title = extract_html_title(html_text)
	title = normalize_text(title)
	if not title:
		return ''
	return title[:200]


#============================================
def html_preview_if_no_title(html_text: str) -> str:
	"""
	Get a short sanitized HTML preview when title is missing.

	Args:
		html_text (str): HTML text.

	Returns:
		str: Preview (first 200 chars) or ''.
	"""
	snippet = str(html_text or '')[:4000]
	plain = strip_tags(snippet)
	plain = safe_ascii(plain)
	plain = normalize_text(plain)
	return plain[:200]


#============================================
def fetch(url: str, timeout: float, referer: str = '') -> requests.Response:
	"""
	Fetch a URL using the global browser-like session.

	Args:
		url (str): URL.
		timeout (float): Timeout seconds.
		referer (str): Optional referer.

	Returns:
		requests.Response: Response.
	"""
	headers = {}
	if referer:
		headers['Referer'] = referer
	return SESSION.get(url, timeout=timeout, allow_redirects=True, headers=headers)


#============================================
def fetch_url(url: str, timeout: float, sleep_max: float, referer: str = '') -> tuple:
	"""
	Fetch a URL with polite random sleep and redirects enabled.

	Args:
		url (str): URL.
		timeout (float): Timeout seconds.
		sleep_max (float): Max sleep seconds.
		referer (str): Optional referer.

	Returns:
		tuple: (status_code:int, final_url:str, content_type:str, body_bytes:int, redirect_chain:list, html_text:str, notes:str)
	"""
	if sleep_max and sleep_max > 0:
		time.sleep(random.random() * sleep_max)

	try:
		resp = fetch(url=url, timeout=timeout, referer=referer)
	except requests.exceptions.TooManyRedirects:
		return (0, url, '', 0, [], '', 'redirect_loop')
	except requests.exceptions.Timeout:
		return (0, url, '', 0, [], '', 'timeout')
	except requests.exceptions.RequestException:
		return (0, url, '', 0, [], '', 'request_error')

	status_code = int(resp.status_code or 0)
	final_url = str(resp.url or url)
	content_type = str(resp.headers.get('Content-Type', '') or '')
	content_type = content_type.split(';')[0].strip().lower()
	redirect_chain = []
	try:
		redirect_chain = [str(r.url or '') for r in (resp.history or []) if str(r.url or '')]
	except Exception:
		redirect_chain = []

	notes = ''
	if status_code == 404:
		notes = '404'
	elif status_code == 410:
		notes = '410'
	elif status_code == 403:
		notes = 'blocked'
	elif status_code == 429:
		notes = 'rate_limited'
	elif status_code >= 500:
		notes = 'server_error'

	text = ''
	body_bytes = 0
	if status_code == 200:
		try:
			body_bytes = int(len(resp.content or b''))
		except Exception:
			body_bytes = 0
		text = resp.text or ''

	return (status_code, final_url, content_type, body_bytes, redirect_chain, text, notes)


#============================================
def format_review_csv(rows: list) -> str:
	"""
	Format review CSV content.

	Args:
		rows (list): List of row dicts.

	Returns:
		str: CSV text.
	"""
	fieldnames = ['id', 'url', 'final_url', 'status_code', 'checked_at', 'title_guess', 'notes']
	out_lines = []

	# Manual CSV writing for stable output and to avoid platform newline differences.
	out_lines.append(','.join(fieldnames))
	for row in rows:
		values = []
		for k in fieldnames:
			v = str(row.get(k, '') or '')
			# Simple CSV escaping
			if ',' in v or '"' in v or '\n' in v:
				v = '"' + v.replace('"', '""') + '"'
			values.append(v)
		out_lines.append(','.join(values))

	out = '\n'.join(out_lines) + '\n'
	return out


#============================================
def order_network_fields(network: dict) -> dict:
	"""
	Order network sub-dict keys for stable YAML diffs.

	Args:
		network (dict): Network dict.

	Returns:
		dict: Ordered network dict.
	"""
	keys = [
		'checked_at',
		'status_code',
		'final_url',
		'content_type',
		'response_bytes',
		'redirect_chain',
		'reachable',
		'blocked',
		'blocked_reason',
		'error',
	]

	out = {}
	for k in keys:
		if k in network:
			out[k] = network.get(k)

	for k in network.keys():
		if k in out:
			continue
		out[k] = network.get(k)

	return out


#============================================
def order_extracted_fields(extracted: dict) -> dict:
	"""
	Order extracted sub-dict keys for stable YAML diffs.

	Args:
		extracted (dict): Extracted dict.

	Returns:
		dict: Ordered extracted dict.
	"""
	keys = [
		'metadata_source',
		'title',
		'published_time',
		'author',
		'teaser',
		'canonical_url',
	]

	out = {}
	for k in keys:
		if k in extracted:
			out[k] = extracted.get(k)

	for k in extracted.keys():
		if k in out:
			continue
		out[k] = extracted.get(k)

	return out


#============================================
def order_item_fields(item: dict) -> dict:
	"""
	Keep item dict keys in a predictable order (new canonical schema).

	Args:
		item (dict): Item dict.

	Returns:
		dict: Ordered dict.
	"""
	keys = [
		'id',
		'url',
		'source',
		'snapshot_path',
		'network',
		'extracted',
		'warnings',
		'notes',
		'replaced_by',
		'suppress',
	]

	out = {}
	for k in keys:
		if k not in item:
			continue
		if k == 'network' and isinstance(item.get('network', None), dict):
			out[k] = order_network_fields(item.get('network', {}) or {})
		elif k == 'extracted' and isinstance(item.get('extracted', None), dict):
			out[k] = order_extracted_fields(item.get('extracted', {}) or {})
		else:
			out[k] = item.get(k)

	# Preserve any extra keys (manual fields) at the end.
	for k in item.keys():
		if k in out:
			continue
		out[k] = item.get(k)

	return out


#============================================
def format_snapshot_queue_csv(rows: list) -> str:
	"""
	Format snapshot queue CSV content.

	Args:
		rows (list): List of row dicts.

	Returns:
		str: CSV text.
	"""
	fieldnames = ['url', 'cache_path', 'source', 'reason']
	out_lines = []

	out_lines.append(','.join(fieldnames))
	for row in rows:
		values = []
		for k in fieldnames:
			v = str(row.get(k, '') or '')
			if ',' in v or '"' in v or '\n' in v:
				v = '"' + v.replace('"', '""') + '"'
			values.append(v)
		out_lines.append(','.join(values))

	out = '\n'.join(out_lines) + '\n'
	return out


#============================================
def _network_equivalent(a: dict, b: dict) -> bool:
	"""
	Compare two network dicts ignoring checked_at.

	Args:
		a (dict): Network dict.
		b (dict): Network dict.

	Returns:
		bool: True if equivalent (excluding checked_at).
	"""
	if not isinstance(a, dict) or not isinstance(b, dict):
		return False

	keys = [
		'status_code',
		'final_url',
		'content_type',
		'response_bytes',
		'redirect_chain',
		'reachable',
		'blocked',
		'blocked_reason',
		'error',
	]
	for k in keys:
		if a.get(k) != b.get(k):
			return False
	return True


#============================================
def _extracted_equivalent(a: dict, b: dict) -> bool:
	"""
	Compare two extracted dicts.

	Args:
		a (dict): Extracted dict.
		b (dict): Extracted dict.

	Returns:
		bool: True if equivalent.
	"""
	if not isinstance(a, dict) or not isinstance(b, dict):
		return False

	keys = [
		'metadata_source',
		'title',
		'published_time',
		'author',
		'teaser',
		'canonical_url',
	]
	for k in keys:
		if a.get(k) != b.get(k):
			return False
	return True


#============================================
def _enrich_news_legacy(
	input_csv: str,
	output_yaml: str,
	review_csv: str,
	sleep_max: float,
	timeout: float,
	max_items=None,
	verbose: bool = False,
):
	"""
	Enrich/validate all In the News URLs from CSV and update YAML + review CSV.

	Args:
		input_csv (str): Input CSV path.
		output_yaml (str): Output YAML path.
		review_csv (str): Review CSV path.
		sleep_max (float): Max random sleep per request.
		timeout (float): Request timeout.
		max_items: Optional max items.
		verbose (bool): If True, print progress and extracted fields.
	"""
	rows = read_csv_rows(input_csv)
	if max_items is not None:
		rows = rows[:max_items]

	# Keep only rows with a URL for progress counts.
	work_rows = []
	input_urls = set()
	for row in rows:
		url = normalize_text(row.get('url', '') or '')
		if not url:
			continue
		work_rows.append(row)
		input_urls.add(url)

	data = read_yaml_or_default(output_yaml)
	items = data.get('items', [])

	by_url = {}
	for item in items:
		if not isinstance(item, dict):
			continue
		u = normalize_text(item.get('url', '') or '')
		if u:
			by_url[u] = item

	today_str = datetime.date.today().isoformat()

	ok_count = 0

	total = len(work_rows)
	for idx, row in enumerate(work_rows, start=1):
		url = normalize_text(row.get('url', '') or '')

		title_override = normalize_text(row.get('title_override', '') or '')

		item = by_url.get(url)
		if item is None:
			item = {'url': url}
			items.append(item)
			by_url[url] = item

		status_code, final_url, content_type, body_bytes, html_text, fetch_note = fetch_url(
			url=url,
			timeout=timeout,
			sleep_max=sleep_max,
			referer='',
		)

		# Legacy migration: "redirected" used to live in notes.
		item['notes'] = remove_note_token(item.get('notes', ''), 'redirected')

		title_tag_preview = ''
		if status_code == 200 and is_html_content_type(content_type):
			title_tag_preview = title_preview(html_text)

			if verbose:
				print(f'[{idx}/{total}] {url}')
				print(f'  final_url: {final_url}')
				print(f'  status: {status_code}')
				print(f'  content_type: {content_type}')
			if title_tag_preview:
				print(f'  title_tag: {safe_ascii(title_tag_preview)[:200]}')
			else:
				print('  title_tag: None')
				preview = html_preview_if_no_title(html_text)
				if preview:
					print(f'  html_preview: {preview}')

		final_domain = ''
		canonical_url = ''
		warnings = []
		meta = {'title': '', 'author': '', 'published_time': '', 'modified_time': '', 'source': '', 'teaser': ''}

		# Detect "junk 200" responses and treat as blocked/soft fail (before parsing).
		non_html = False
		body_too_small = False
		block_markers = []
		if status_code == 200:
			if not is_html_content_type(content_type):
				non_html = True
			if int(body_bytes or 0) > 0 and int(body_bytes or 0) < 5120:
				body_too_small = True
			block_markers = detect_block_markers(html_text)

		# Only parse metadata when the response looks like real HTML content.
		if status_code == 200 and (not non_html) and (not body_too_small) and (not block_markers):
			meta = extract_metadata(html_text)

		title = title_override if title_override else meta.get('title', '')
		title = normalize_text(title)
		if not title:
			existing_title = normalize_text(item.get('title', '') or '')
			if looks_like_html(existing_title):
				existing_title = ''
			title = existing_title
		if looks_like_html(title):
			title = ''

		source = ''
		author = ''
		published_time = ''
		modified_time = ''
		teaser = ''

		# Classify hard vs soft failures.
		hard_fail_reason = ''
		soft_fail_reasons = []
		if status_code == 200 and non_html:
			hard_fail_reason = 'non_html_content'
		if status_code in (404, 410):
			hard_fail_reason = fetch_note or str(status_code)
		elif fetch_note in ('timeout', 'request_error', 'redirect_loop'):
			hard_fail_reason = fetch_note
		elif status_code in (403, 429):
			soft_fail_reasons.append(fetch_note or str(status_code))
		elif status_code >= 500:
			soft_fail_reasons.append(fetch_note or 'server_error')

		if status_code == 200 and body_too_small:
			soft_fail_reasons.append('body_too_small')
		for token in block_markers:
			soft_fail_reasons.append('blocked_' + str(token))

		# Retry once with a referer if the response is 200 HTML but title is missing.
		if status_code == 200 and (not non_html) and (not body_too_small) and (not title) and (not block_markers):
			status_code2, final_url2, content_type2, body_bytes2, html_text2, fetch_note2 = fetch_url(
				url=url,
				timeout=timeout,
				sleep_max=sleep_max,
				referer='https://www.google.com/',
			)
			if status_code2 == 200 and is_html_content_type(content_type2) and int(body_bytes2 or 0) >= 5120:
				block_markers2 = detect_block_markers(html_text2)
				if not block_markers2:
					meta2 = extract_metadata(html_text2)
					title2 = normalize_text(meta2.get('title', '') or '')
					if title2 and not looks_like_html(title2):
						if verbose:
							print('  retry: ok (referer google)')
						meta = meta2
						title = title2
						status_code = status_code2
						final_url = final_url2
						content_type = content_type2
						body_bytes = body_bytes2
						html_text = html_text2
						fetch_note = fetch_note2
						non_html = False
						body_too_small = False
						block_markers = []

		# Final URL/domain/canonical/warnings after optional retry.
		final_domain = urllib.parse.urlparse(final_url).netloc
		if status_code == 200 and is_html_content_type(content_type):
			canonical_url = parse_canonical_url(html_text, final_url)
		if final_url and final_url != url:
			warnings.append('redirected')
		if canonical_url and canonical_url != url:
			warnings.append('canonical_changed')
		if status_code == 200:
			lower = str(html_text or '').lower()
			if 'paywall' in lower or 'subscribe to continue' in lower:
				warnings.append('paywall_possible')

		# Now that final_domain is known, derive the rest of the fields.
		source = normalize_text(meta.get('source', '') or '')
		if looks_like_html(source):
			source = ''
		if not source:
			source = domain_to_source(final_domain)
		if not source:
			existing_source = normalize_text(item.get('source', '') or '')
			if looks_like_html(existing_source):
				existing_source = ''
			source = existing_source

		author = normalize_text(meta.get('author', '') or '')
		if looks_like_html(author):
			author = ''
		if not author:
			existing_author = normalize_text(item.get('author', '') or '')
			if looks_like_html(existing_author):
				existing_author = ''
			author = existing_author

			published_time = normalize_text(meta.get('published_time', '') or '') or normalize_text(item.get('published_time', '') or '')
			modified_time = normalize_text(meta.get('modified_time', '') or '') or normalize_text(item.get('modified_time', '') or '')
			teaser = normalize_text(meta.get('teaser', '') or '') or normalize_text(item.get('teaser', '') or '')
			if looks_like_html(teaser):
				teaser = ''

			# If the response looks blocked for scripts, fall back to URL-derived date/title and skip author/teaser.
			blocked_for_script = bool(status_code == 200 and is_html_content_type(content_type) and (body_too_small or block_markers))
			if status_code == 200 and is_html_content_type(content_type):
				derived_date = date_from_url(final_url or url)
				derived_title = title_from_url(final_url or url)

				if not title and derived_title:
					title = derived_title
					warnings.append('title_from_url')

				if not published_time and derived_date:
					published_time = derived_date + 'T00:00:00'
					warnings.append('date_from_url')

			# Mark that we are rendering a minimal, URL-derived block due to likely bot management.
			if blocked_for_script:
				warnings.append('blocked_fallback')
				author = ''
				teaser = ''

			if status_code == 200 and not title:
				soft_fail_reasons.append('no_title')

			if status_code == 200 and not published_time:
				soft_fail_reasons.append('no_published_time')

		if hard_fail_reason:
			status = 'hard_fail'
		elif soft_fail_reasons:
			status = 'soft_fail'
		else:
			status = 'ok'

			is_ok = bool(status_code == 200 and title and published_time and status == 'ok')
			if is_ok:
				ok_count += 1

			# If we cannot determine title or published_time, hide from rendering and keep for review.
			if (not title) or (not published_time):
				item['suppress'] = True
			else:
				if item.get('suppress'):
					item.pop('suppress', None)

		# Notes are for failures, not warnings like canonical changes.
		if status == 'hard_fail':
			item['notes'] = merge_notes(item.get('notes', ''), hard_fail_reason)
		elif status == 'soft_fail':
			reason_text = ';'.join([r for r in soft_fail_reasons if r])
			item['notes'] = merge_notes(item.get('notes', ''), reason_text)

		item['final_url'] = final_url
		item['canonical_url'] = canonical_url
		item['domain'] = final_domain
		item['source'] = source
		item['title'] = title
		item['author'] = author
		item['published_time'] = published_time
		item['modified_time'] = modified_time
		item['teaser'] = teaser_truncate(teaser) if teaser else ''
		item['status_code'] = int(status_code or 0)
		item['is_ok'] = bool(is_ok)
		item['status'] = status
		item['warnings'] = warnings
		item['last_checked'] = today_str

		item['id'] = make_item_id(
			source=source,
			domain=final_domain,
			published_time=published_time,
			title=title,
			url=url,
		)

		if verbose:
			title_print = safe_ascii(title)
			source_print = safe_ascii(source)
			author_print = safe_ascii(author)
			teaser_print = safe_ascii(item.get('teaser', '') or '')
			notes_print = safe_ascii(item.get('notes', '') or '')
			warnings_print = ','.join([safe_ascii(w) for w in warnings if w])
			status_print = safe_ascii(status)
			print(f'  is_ok: {is_ok}')
			if status_print:
				print(f'  status: {status_print}')
			if warnings_print:
				print(f'  warnings: {warnings_print}')
			if source_print:
				print(f'  source: {source_print}')
			if author_print:
				print(f'  author: {author_print}')
			if published_time:
				print(f'  published_time: {published_time}')
			if title_print:
				print(f'  title: {title_print}')
			if teaser_print:
				print(f'  teaser: {teaser_print}')
			if notes_print:
				print(f'  notes: {notes_print}')
			if canonical_url:
				print(f'  canonical_url: {canonical_url}')

	# Replacement handling for dead links:
	# If a URL is hard fail but another entry exists with same source+title (or source+published_time),
	# mark it as replaced and suppress it from rendering and review queue.
	for item in items:
		if not isinstance(item, dict):
			continue
		if normalize_text(item.get('url', '') or '') not in input_urls:
			continue
		if str(item.get('status', '') or '') != 'hard_fail':
			continue

		item_source = normalize_text(item.get('source', '') or '').lower()
		item_title = normalize_text(item.get('title', '') or '').lower()
		item_published = normalize_text(item.get('published_time', '') or '')

		best = None
		best_score = -1
		for cand in items:
			if not isinstance(cand, dict):
				continue
			if cand is item:
				continue
			if str(cand.get('status', '') or '') == 'hard_fail':
				continue
			if not cand.get('id'):
				continue
			cand_source = normalize_text(cand.get('source', '') or '').lower()
			if not item_source or not cand_source or cand_source != item_source:
				continue

			cand_title = normalize_text(cand.get('title', '') or '').lower()
			cand_published = normalize_text(cand.get('published_time', '') or '')

			match_title = bool(item_title and cand_title and cand_title == item_title)
			match_published = bool(item_published and cand_published and cand_published == item_published)
			if not (match_title or match_published):
				continue

			# Prefer exact title matches, then published_time matches.
			score = 0
			if match_published:
				score += 10
			if match_title:
				score += 20

			# Prefer candidates that are currently OK.
			cand_code = int(cand.get('status_code', 0) or 0)
			cand_status = str(cand.get('status', '') or '').strip()
			if cand_code == 200 and cand_status == 'ok':
				score += 5

			if score > best_score:
				best = cand
				best_score = score

		if best:
			item['replaced_by'] = str(best.get('id', '') or '').strip()
			item['suppress'] = True
		else:
			# If there is no replacement anymore, unsuppress so it can be rendered/queued.
			if item.get('suppress') and item.get('replaced_by'):
				item.pop('replaced_by', None)
				item.pop('suppress', None)

	# Build review queue after replacements are applied.
	review_rows = []
	review_count = 0
	for item in items:
		if not isinstance(item, dict):
			continue
		url = normalize_text(item.get('url', '') or '')
		if url not in input_urls:
			continue

		status = str(item.get('status', '') or '').strip()
		status_code = int(item.get('status_code', 0) or 0)
		replaced_by = str(item.get('replaced_by', '') or '').strip()

		queue = False
		if status == 'hard_fail':
			if not replaced_by:
				queue = True
			elif status == 'soft_fail':
				queue = True

		if not queue:
			continue

		review_count += 1
		review_rows.append({
			'url': url,
			'final_url': str(item.get('final_url', '') or ''),
			'status_code': str(status_code),
			'last_checked': str(item.get('last_checked', '') or ''),
			'title_guess': str(item.get('title', '') or ''),
			'notes': normalize_text(item.get('notes', '') or ''),
		})

	# Reorder items for stable YAML diffs
	ordered_items = []
	for item in items:
		if not isinstance(item, dict):
			continue
		ordered_items.append(order_item_fields(item))

	data_out = {
		'schema': 1,
		'items': ordered_items,
	}

	yaml_text = yaml_dump(data_out)
	wrote_yaml = write_text_file_if_changed(output_yaml, yaml_text)

	review_text = format_review_csv(review_rows)
	wrote_review = write_text_file_if_changed(review_csv, review_text)

	if verbose:
		print(f'Processed: {total}')
		print(f'OK: {ok_count}')
		print(f'Needs review: {review_count}')
		print(f'Wrote YAML: {wrote_yaml}')
		print(f'Wrote review CSV: {wrote_review}')


#============================================
def enrich_news(
	input_csv: str,
	output_yaml: str,
	review_csv: str,
	sleep_max: float,
	timeout: float,
	max_items=None,
	verbose: bool = False,
	snapshot_csv: str = 'data/in_the_news_needs_snapshot.csv',
	head_cache_dir: str = HEAD_CACHE_DIR_DEFAULT,
):
	"""
	Enrich the In the News dataset.

	- Input CSV stays clean (URLs only).
	- Canonical YAML stores one record per story, with multiple URLs.
	- Uses a local head cache for metadata extraction when blocked.
	"""
	store = read_news_store(output_yaml)
	stories = store.get('stories', []) if isinstance(store.get('stories', None), list) else []
	pending = store.get('pending', []) if isinstance(store.get('pending', None), list) else []

	stories_by_fingerprint = {}
	used_ids = set()
	for s in [x for x in stories if isinstance(x, dict)]:
		# Compute fingerprint for existing stories (if missing).
		published_date = str(s.get('published_date', '') or '').strip()
		title = str(s.get('title', '') or '').strip()
		source = str(s.get('source', '') or '').strip()
		fp = str(s.get('fingerprint', '') or '').strip()
		if (not fp) and published_date and title and source:
			fp = make_story_fingerprint(published_date, source, title)
			s['fingerprint'] = fp

		# Ensure primary_url exists for existing stories when possible.
		if not normalize_url(s.get('primary_url', '') or ''):
			urls_list = s.get('urls', [])
			if isinstance(urls_list, list):
				for u in urls_list:
					u = normalize_url(u)
					if u:
						s['primary_url'] = u
						break

		if not isinstance(s, dict):
			continue
		sid = str(s.get('id', '') or '').strip()
		if sid:
			used_ids.add(sid)

		# De-duplicate any existing YAML duplicates by fingerprint.
		fp = str(s.get('fingerprint', '') or '').strip()
		if not fp:
			continue
		existing = stories_by_fingerprint.get(fp)
		if existing is None:
			stories_by_fingerprint[fp] = s
			continue

		# Merge URLs; only fill missing fields to avoid churn.
		ex_urls = existing.get('urls', [])
		if not isinstance(ex_urls, list):
			ex_urls = []
		s_urls = s.get('urls', [])
		if not isinstance(s_urls, list):
			s_urls = []
		for u in s_urls:
			u = normalize_url(u)
			if not u:
				continue
			if u not in ex_urls:
				ex_urls.append(u)
		existing['urls'] = ex_urls

		for k in ['source', 'published_date', 'title', 'author', 'teaser', 'primary_url']:
			if (not existing.get(k, None)) and s.get(k, None):
				existing[k] = s.get(k, None)

		# Prefer keeping an existing id; never overwrite a non-empty id.
		if (not existing.get('id', None)) and s.get('id', None):
			existing['id'] = s.get('id', None)

	pending_by_url = {}
	for p in pending:
		if not isinstance(p, dict):
			continue
		u = normalize_url(p.get('url', '') or '')
		if u:
			pending_by_url[u] = p

	rows = read_csv_rows(input_csv)
	urls = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		url = normalize_url(row.get('url', '') or '')
		if not url:
			continue
		if url not in urls:
			urls.append(url)

	if max_items is not None:
		urls = urls[:max_items]

	review_rows = []
	snapshot_rows = []

	repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(output_yaml)), os.pardir))

	total = len(urls)
	for idx, url in enumerate(urls, start=1):
		if verbose:
			print(f'[{idx}/{total}] {url}')

		status_code, final_url, content_type, body_bytes, redirect_chain, html_text, fetch_note = fetch_url(
			url=url,
			timeout=timeout,
			sleep_max=sleep_max,
			referer='',
		)

		if verbose:
			print(f'  status_code: {status_code}')
			print(f'  final_url: {final_url}')
			print(f'  content_type: {content_type}')
			print(f'  response_bytes: {body_bytes}')
			if redirect_chain:
				print(f'  redirect_chain: {len(redirect_chain)}')
			if fetch_note:
				print(f'  fetch_note: {fetch_note}')

		is_html = bool(status_code == 200 and is_html_content_type(content_type))
		snippet = str(html_text or '')[:2048]
		markers = detect_block_markers(snippet) if is_html else []
		body_too_small = False
		try:
			body_too_small = is_html and (int(body_bytes or 0) > 0) and (int(body_bytes or 0) < 5120)
		except Exception:
			body_too_small = False

		blocked = bool(is_html and (body_too_small or markers))
		blocked_reason = ''
		if blocked:
			reasons = []
			for token in markers:
				reasons.append(str(token))
			if body_too_small:
				reasons.append('body_too_small')
			blocked_reason = ';'.join([r for r in reasons if r])

		base_url = str(final_url or url)
		best_url_for_cache = ''
		if is_html:
			best_url_for_cache = extract_best_url_from_html_head(html_text, base_url)
		if not best_url_for_cache:
			best_url_for_cache = url

		cache_candidates = []
		for u in [best_url_for_cache, base_url, url]:
			u = normalize_url(u)
			if not u:
				continue
			cache_candidates.append(head_cache_path_for_url(u, head_cache_dir))
			if u.startswith('http://'):
				cache_candidates.append(head_cache_path_for_url('https://' + u[len('http://'):], head_cache_dir))

		cache_abs_candidates = []
		seen_paths = set()
		for p in cache_candidates:
			if not p:
				continue
			abs_p = p if os.path.isabs(p) else os.path.join(repo_root, p)
			if abs_p in seen_paths:
				continue
			seen_paths.add(abs_p)
			cache_abs_candidates.append((p, abs_p))

		cache_path = cache_abs_candidates[0][0] if cache_abs_candidates else head_cache_path_for_url(url, head_cache_dir)
		cache_abs = cache_abs_candidates[0][1] if cache_abs_candidates else (cache_path if os.path.isabs(cache_path) else os.path.join(repo_root, cache_path))

		if verbose:
			print(f'  cache: {cache_path}')
			if best_url_for_cache and normalize_url(best_url_for_cache) != normalize_url(url):
				print(f'  cache_key_url: {best_url_for_cache}')

		head_html = ''
		if is_html and (not blocked):
			head_html = build_head_cache_html(html_text)
			# Write/update cache only if the extracted head changes.
			write_text_file_if_changed(cache_abs, head_html)

		# Fall back to head cache for blocked/non-HTML fetches.
		if not head_html:
			for _, abs_p in cache_abs_candidates:
				if os.path.exists(abs_p):
					head_html = read_text_file(abs_p)
					cache_abs = abs_p
					break

		# If blocked and no cache exists, queue for snapshot and keep as pending only.
		if blocked and (not os.path.exists(cache_abs)):
			source_guess = domain_to_source(urllib.parse.urlparse(final_url or url).netloc) or urllib.parse.urlparse(final_url or url).netloc
			last_checked = iso_utc_now()
			pending_by_url[url] = {
				'url': url,
				'source': source_guess,
				'cache_path': cache_path,
				'last_checked': last_checked,
				'reason': 'blocked' + (':' + blocked_reason if blocked_reason else ''),
			}
			snapshot_rows.append({
				'url': url,
				'cache_path': cache_path,
				'source': source_guess,
				'reason': blocked_reason or 'blocked',
			})

			if verbose:
				print('  blocked: true (no cache)')
			continue

		# If fetch failed and no cache exists, keep pending and (optionally) review.
		if (not head_html) and (status_code != 200):
			source_guess = domain_to_source(urllib.parse.urlparse(final_url or url).netloc) or urllib.parse.urlparse(final_url or url).netloc
			last_checked = iso_utc_now()
			pending_by_url[url] = {
				'url': url,
				'source': source_guess,
				'cache_path': cache_path,
				'last_checked': last_checked,
				'reason': fetch_note or str(status_code or 0),
			}

			review_rows.append({
				'id': '',
				'url': url,
				'final_url': str(final_url or ''),
				'status_code': str(status_code or ''),
				'checked_at': last_checked,
				'title_guess': '',
				'notes': fetch_note or str(status_code or 0),
			})

			if verbose:
				print('  head: none (no cache)')
			continue

		meta = extract_metadata(head_html)
		source = normalize_text(meta.get('source', '') or '')
		if not source:
			source = domain_to_source(urllib.parse.urlparse(final_url or url).netloc) or urllib.parse.urlparse(final_url or url).netloc

		title = normalize_text(meta.get('title', '') or '')
		author = normalize_text(meta.get('author', '') or '') or None
		published_time = normalize_text(meta.get('published_time', '') or '')
		published_date = date_from_time_text(published_time)
		if not published_date:
			# URL date fallback only if no metadata date.
			published_date = date_from_url(final_url or url)

		teaser = normalize_text(meta.get('teaser', '') or '')
		teaser = teaser_truncate(teaser) if teaser else None

		if verbose:
			print(f'  source: {safe_ascii(source)}')
			print(f'  published_date: {published_date}')
			print(f'  title: {safe_ascii(title)[:200] if title else ""}')
			if author:
				print(f'  author: {safe_ascii(author)}')
			if teaser:
				print(f'  teaser: {safe_ascii(teaser)}')

		if not title or not published_date:
			last_checked = iso_utc_now()
			reason = 'missing_title' if not title else 'missing_published_date'
			pending_by_url[url] = {
				'url': url,
				'source': source,
				'cache_path': cache_path,
				'last_checked': last_checked,
				'reason': reason,
			}
			review_rows.append({
				'id': '',
				'url': url,
				'final_url': str(final_url or ''),
				'status_code': str(status_code or ''),
				'checked_at': last_checked,
				'title_guess': title or '',
				'notes': reason,
			})
			continue

		fingerprint = make_story_fingerprint(published_date, source, title)
		story = stories_by_fingerprint.get(fingerprint)

		head_best_url = ''
		try:
			head_best_url = extract_best_url_from_html_head(head_html, base_url)
		except Exception:
			head_best_url = ''

		primary_candidate = ''
		for cand in [head_best_url, final_url, url]:
			cand = normalize_url(cand)
			if not cand:
				continue
			if cand == normalize_url(head_best_url) and (not cand.startswith('https://')):
				continue
			primary_candidate = cand
			break

		if story is None:
			story = {
				'id': '',
				'fingerprint': fingerprint,
				'source': source,
				'published_date': published_date,
				'title': title,
				'author': author,
				'teaser': teaser,
				'primary_url': primary_candidate or None,
				'urls': [],
			}
			stories.append(story)
			stories_by_fingerprint[fingerprint] = story

			urls_list = []
			for u in [url, final_url, head_best_url, story.get('primary_url', '')]:
				u = normalize_url(u)
				if not u:
					continue
				if u not in urls_list:
					urls_list.append(u)
			story['urls'] = urls_list
		else:
			if str(story.get('fingerprint', '') or '').strip() == '':
				story['fingerprint'] = fingerprint
			if str(story.get('source', '') or '').strip() == '':
				story['source'] = source
			if str(story.get('published_date', '') or '').strip() == '':
				story['published_date'] = published_date
			if str(story.get('title', '') or '').strip() == '':
				story['title'] = title

			if (not story.get('author', None)) and author:
				story['author'] = author
			if (not story.get('teaser', None)) and teaser:
				story['teaser'] = teaser

			existing_primary = normalize_url(story.get('primary_url', '') or '')
			if (not existing_primary) and primary_candidate:
				story['primary_url'] = primary_candidate
			elif existing_primary and primary_candidate:
				ex_score = primary_url_score(existing_primary, head_best_url, final_url, url)
				new_score = primary_url_score(primary_candidate, head_best_url, final_url, url)
				if new_score > ex_score:
					story['primary_url'] = primary_candidate

			urls_list = story.get('urls', [])
			if not isinstance(urls_list, list):
				urls_list = []

			for u in [url, final_url, head_best_url, story.get('primary_url', '')]:
				u = normalize_url(u)
				if not u:
					continue
				if u not in urls_list:
					urls_list.append(u)
			story['urls'] = urls_list

		# If this URL was pending, clear it now that it's part of a story.
		if url in pending_by_url:
			pending_by_url.pop(url, None)

		# Optional review output for non-200 fetches even if cache provides metadata.
		if status_code != 200:
			review_rows.append({
				'id': str(story.get('id', '') or ''),
				'url': url,
				'final_url': str(final_url or ''),
				'status_code': str(status_code or ''),
				'checked_at': iso_utc_now(),
				'title_guess': title,
				'notes': fetch_note or str(status_code or 0),
			})

	# Finalize: ensure stories are unique by fingerprint and assign stable ids for new fingerprints.
	stories_unique = []
	for fp, s in stories_by_fingerprint.items():
		if not isinstance(s, dict):
			continue
		# Keep fingerprint on every story.
		if (not str(s.get('fingerprint', '') or '').strip()) and fp:
			s['fingerprint'] = fp
		stories_unique.append(s)

	# Assign ids only for new stories (do not reshuffle existing ids).
	new_by_date = {}
	for s in stories_unique:
		sid = str(s.get('id', '') or '').strip()
		if sid:
			continue
		published_date = str(s.get('published_date', '') or '').strip()
		if not re.match(r'^\d{4}-\d{2}-\d{2}$', published_date):
			continue
		new_by_date.setdefault(published_date, []).append(s)

	for published_date in sorted(new_by_date.keys()):
		new_stories = new_by_date.get(published_date, [])
		new_stories = sorted(
			new_stories,
			key=lambda x: (
				normalize_fingerprint_text(str(x.get('title', '') or '')),
				normalize_fingerprint_text(str(x.get('source', '') or '')),
				str(x.get('fingerprint', '') or ''),
			),
		)
		for s in new_stories:
			s['id'] = allocate_story_id(published_date, used_ids)

	stories = stories_unique

	# Canonicalize output ordering.
	stories_out = []
	for s in sorted([x for x in stories if isinstance(x, dict)], key=lambda x: (str(x.get('published_date', '') or ''), str(x.get('title', '') or ''))):
		# Ensure urls list is stable and unique.
		urls_list = s.get('urls', [])
		if isinstance(urls_list, list):
			seen = set()
			clean = []
			for u in urls_list:
				u = normalize_url(u)
				if not u:
					continue
				if u in seen:
					continue
				seen.add(u)
				clean.append(u)
			s['urls'] = clean
		stories_out.append(order_story_fields(s))

	pending_out = []
	for p in sorted([x for x in pending_by_url.values() if isinstance(x, dict)], key=lambda x: str(x.get('url', '') or '')):
		pending_out.append(order_pending_fields(p))

	store_out = {
		'schema': 1,
		'stories': stories_out,
		'pending': pending_out,
	}

	yaml_text = yaml_dump(store_out)
	wrote_yaml = write_text_file_if_changed(output_yaml, yaml_text)

	wrote_review = False
	wrote_snapshot = False
	if len(urls) > 0:
		review_text = format_review_csv(review_rows)
		wrote_review = write_text_file_if_changed(review_csv, review_text)

		snapshot_text = format_snapshot_queue_csv(snapshot_rows)
		wrote_snapshot = write_text_file_if_changed(snapshot_csv, snapshot_text)

	if verbose:
		print(f'Processed: {len(urls)}')
		print(f'Stories: {len(stories_out)}')
		print(f'Pending: {len(pending_out)}')
		print(f'Needs snapshot: {len(snapshot_rows)}')
		print(f'Needs review: {len(review_rows)}')
		print(f'Wrote YAML: {wrote_yaml}')
		print(f'Wrote needs_snapshot CSV: {wrote_snapshot}')
		print(f'Wrote needs_review CSV: {wrote_review}')


#============================================
def main():
	"""
	Main entry point.
	"""
	args = parse_args()
	enrich_news(
		input_csv=args.input_csv,
		output_yaml=args.output_yaml,
		review_csv=args.review_csv,
		snapshot_csv=args.snapshot_csv,
		head_cache_dir=args.head_cache_dir,
		sleep_max=args.sleep_max,
		timeout=args.timeout,
		max_items=args.max_items,
		verbose=bool(args.verbose),
	)


if __name__ == '__main__':
	assert parse_canonical_url('<link rel=\"canonical\" href=\"/x\">', 'https://example.com/a') == 'https://example.com/x'
	assert date_from_url('https://www.dailyherald.com/20251213/news/lego-lovers/') == '2025-12-13'
	assert date_from_url('https://www.chicagotribune.com/2025/03/24/for-lego-fans/') == '2025-03-24'
	assert title_from_url('https://example.com/news/lego-lovers-check-out-train-displays/') == 'LEGO Lovers Check Out Train Displays'
	assert teaser_truncate('Children of all ages were captivated by the creations on display today.', 12) == 'Children of all ages were captivated by the creations on display today.'
	assert teaser_truncate('One two three four five six seven eight nine ten eleven twelve thirteen.', 12) == 'One two three four five six seven eight nine ten eleven twelve...'
	main()
