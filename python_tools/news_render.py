#!/usr/bin/env python3

# Standard Library
import html
import os
import urllib.parse
import re
import datetime
import argparse

# PIP3 modules
import yaml


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
def sanitize_source_slug(text: str) -> str:
	"""
	Sanitize a source name/domain into a stable css class slug.

	Rules:
	- lowercase
	- remove non-alphanumerics
	- collapse whitespace to nothing (covered by removal)

	Args:
		text (str): Source or domain.

	Returns:
		str: Slug.
	"""
	text = str(text or '').strip().lower()
	text = re.sub(r'[^a-z0-9]+', '', text)
	return text


#============================================
def source_shortname(source: str, domain: str) -> str:
	"""
	Get a short, stable class suffix for a known source.

	Args:
		source (str): Display source name.
		domain (str): Domain fallback.

	Returns:
		str: Shortname slug.
	"""
	key = sanitize_source_slug(source)

	known = {
		'chicagotribune': 'tribune',
		'dailyherald': 'dailyherald',
		'omahaworldherald': 'omahaworldherald',
		'ketv': 'ketv',
		'dailynonpareil': 'dailynonpareil',
		'kanecountychronicle': 'kanecountychronicle',
	}

	if key in known:
		return known[key]

	d = sanitize_source_slug(domain)
	if d.endswith('chicagotribunecom'):
		return 'tribune'
	if d.endswith('dailyheraldcom'):
		return 'dailyherald'
	if d.endswith('omahacom'):
		return 'omahaworldherald'
	if d.endswith('ketvcom'):
		return 'ketv'

	return key or d or 'unknown'


#============================================
def date_from_url(url: str) -> str:
	"""
	Best-effort YYYY-MM-DD extraction from URL path.

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

	return ' '.join(out_words).strip()


#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed arguments.
	"""
	parser = argparse.ArgumentParser(description='Render MkDocs In the News page from YAML')

	parser.add_argument(
		'-i', '--input', dest='input_yaml', required=False, type=str,
		default='data/in_the_news.yml',
		help='Input YAML file (default: data/in_the_news.yml)',
	)
	parser.add_argument(
		'-o', '--output', dest='output_md', required=False, type=str,
		default='mkdocs/docs/in-the-news/index.md',
		help='Output Markdown file (default: mkdocs/docs/in-the-news/index.md)',
	)

	args = parser.parse_args()
	return args


#============================================
def write_text_file_if_changed(path: str, content: str):
	"""
	Write a text file only if content changed.

	Args:
		path (str): File path.
		content (str): New content.
	"""
	parent_dir = os.path.dirname(path)
	if parent_dir:
		os.makedirs(parent_dir, exist_ok=True)

	if os.path.exists(path):
		with open(path, 'r', encoding='utf-8') as f:
			existing = f.read()
		if existing == content:
			return

	with open(path, 'w', encoding='utf-8') as f:
		f.write(content)


#============================================
def parse_time_for_sort(time_text: str):
	"""
	Parse ISO-ish time for sorting.

	Args:
		time_text (str): Time string.

	Returns:
		datetime.datetime|None: Parsed datetime or None.
	"""
	time_text = str(time_text or '').strip()
	if not time_text:
		return None

	# Support Z suffix
	if time_text.endswith('Z'):
		time_text = time_text[:-1] + '+00:00'

	try:
		dt = datetime.datetime.fromisoformat(time_text)
	except Exception:
		return None

	# Normalize so we never compare naive vs aware datetimes.
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=datetime.timezone.utc)
	else:
		dt = dt.astimezone(datetime.timezone.utc)

	return dt


#============================================
def pick_display_date(item: dict) -> str:
	"""
	Pick a YYYY-MM-DD date for display.

	Args:
		item (dict): News item.

	Returns:
		str: Date string or ''.
	"""
	published_time = str(item.get('published_time', '') or '').strip()
	if re.match(r'^\d{4}-\d{2}-\d{2}', published_time):
		return published_time[:10]

	last_checked = str(item.get('last_checked', '') or '').strip()
	if re.match(r'^\d{4}-\d{2}-\d{2}$', last_checked):
		return last_checked

	return ''


#============================================
def read_yaml_file(yaml_path: str) -> dict:
	"""
	Read YAML file.

	Args:
		yaml_path (str): YAML path.

	Returns:
		dict: Parsed YAML.
	"""
	with open(yaml_path, 'r', encoding='utf-8') as f:
		data = yaml.safe_load(f)
	return data


#============================================
def render_in_the_news_page(data: dict) -> str:
	"""
	Render the In the News Markdown page from YAML data.

	Args:
		data (dict): YAML dict.

	Returns:
		str: Markdown content.
	"""
	stories = []
	if isinstance(data, dict) and isinstance(data.get('stories', None), list):
		stories = data.get('stories', [])
	elif isinstance(data, dict):
		# Backward-compatible: older schema wrapped items in a dict.
		raw_items = data.get('items', [])
		if isinstance(raw_items, list):
			for item in raw_items:
				if not isinstance(item, dict):
					continue
				title = str(item.get('title', '') or '').strip()
				published_time = str(item.get('published_time', '') or '').strip()
				published_date = published_time[:10] if re.match(r'^\d{4}-\d{2}-\d{2}', published_time) else ''
				urls = []
				for u in [item.get('canonical_url', ''), item.get('final_url', ''), item.get('url', '')]:
					u = str(u or '').strip()
					if u and u not in urls:
						urls.append(u)

				stories.append({
					'id': str(item.get('id', '') or '').strip(),
					'source': str(item.get('source', '') or '').strip(),
					'published_date': published_date,
					'title': title,
					'author': str(item.get('author', '') or '').strip() or None,
					'teaser': str(item.get('teaser', '') or '').strip() or None,
					'urls': urls,
				})
	elif isinstance(data, list):
		# Backward-compatible: intermediate list schema.
		stories = data

	def sort_key(story: dict):
		d = str(story.get('published_date', '') or '').strip()
		t = str(story.get('title', '') or '').strip()
		return d, t

	stories_sorted = [s for s in stories if isinstance(s, dict)]
	# Only render stories that have BOTH published_date and title.
	stories_sorted = [
		s for s in stories_sorted
		if re.match(r'^\d{4}-\d{2}-\d{2}$', str(s.get('published_date', '') or '').strip())
		and str(s.get('title', '') or '').strip()
	]
	stories_sorted = sorted(stories_sorted, key=sort_key, reverse=True)

	out = ''
	out += '---\n'
	out += 'title: \"In the News\"\n'
	out += 'type: \"page\"\n'
	out += 'wp_id: 866\n'
	out += 'wp_link: \"https://niltc.org/in-the-news\"\n'
	out += 'date: \"2017-02-17T02:18:11\"\n'
	out += '---\n'
	out += '\n'
	out += '<!-- Generated from data/in_the_news.yml (built from data/in_the_news.csv). Edit the CSV and run enrichment. -->\n'
	out += '\n'
	out += '# In the News\n'
	out += '\n'
	out += 'Articles from around the web covering NILTC.\n'
	out += '\n'

	if not stories_sorted:
		out += '_No articles listed yet._\n'
		return out

	out += '<div class=\"news-list\">' + '\n'
	out += '\n'

	for story in stories_sorted:
		if bool(story.get('suppress', False)):
			continue

		source = str(story.get('source', '') or '').strip()
		date_str = str(story.get('published_date', '') or '').strip()
		title = str(story.get('title', '') or '').strip()
		author = str(story.get('author', '') or '').strip()
		teaser = str(story.get('teaser', '') or '').strip()

		urls = story.get('urls', [])
		if not isinstance(urls, list):
			urls = []
		url_to_use = ''
		for u in urls:
			u = str(u or '').strip()
			if u:
				url_to_use = u
				break
		if not url_to_use:
			continue

		domain = urllib.parse.urlparse(url_to_use).netloc
		if not source:
			source = domain

		if looks_like_html(author):
			author = ''
		if looks_like_html(teaser):
			teaser = ''

		source_slug = source_shortname(source, domain)

		title_html = html.escape(title)
		source_html = html.escape(source)
		date_html = html.escape(date_str)
		author_html = html.escape(author) if author else ''
		teaser_html = html.escape(teaser) if teaser else ''
		url_html = html.escape(url_to_use, quote=True)

		out += f'<div class=\"news-item news-src-{source_slug}\">' + '\n'
		out += '\t<div class=\"news-meta\">'
		out += f'<span class=\"news-source news-source--{source_slug}\">{source_html}</span>'
		out += f'<span class=\"news-date\">{date_html}</span>'
		out += '</div>' + '\n'
		out += f'\t<div class=\"news-title\"><a href=\"{url_html}\" target=\"_blank\" rel=\"noopener\">{title_html}</a></div>' + '\n'

		if author_html or teaser_html:
			out += '\t<div class=\"news-extra\">' + '\n'
			if author_html:
				out += f'\t\t<div class=\"news-author\">{author_html}</div>' + '\n'
			if teaser_html:
				out += f'\t\t<div class=\"news-teaser\">{teaser_html}</div>' + '\n'
			out += '\t</div>' + '\n'

		out += '</div>' + '\n'
		out += '\n'

	out += '</div>' + '\n'
	out += '\n'
	return out


#============================================
def main():
	"""
	Main entry point.
	"""
	args = parse_args()
	data = read_yaml_file(args.input_yaml)
	content = render_in_the_news_page(data)
	write_text_file_if_changed(args.output_md, content)


if __name__ == '__main__':
	main()
