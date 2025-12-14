#!/usr/bin/env python3
# Moved from python-tools/ to python_tools/

#============================================
# Standard Library
import argparse
import csv
import os
import random
import re
import subprocess
import time
import urllib.parse

# PIP3 modules
import requests


#============================================
def parse_args() -> argparse.Namespace:
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Export WordPress Pages and Posts via REST API and convert to MkDocs Markdown."
	)

	parser.add_argument(
		'-b', '--base-url',
		dest='base_url',
		required=True,
		help='Base site URL, example: https://niltc.org'
	)
	parser.add_argument(
		'-o', '--out-dir',
		dest='out_dir',
		required=True,
		help='MkDocs docs output directory, example: mkdocs/docs'
	)

	parser.add_argument(
		'-P', '--include-pages',
		dest='include_pages',
		help='Include WordPress pages',
		action='store_true'
	)
	parser.add_argument(
		'-p', '--no-pages',
		dest='include_pages',
		help='Do not include WordPress pages',
		action='store_false'
	)
	parser.set_defaults(include_pages=True)

	parser.add_argument(
		'-T', '--include-posts',
		dest='include_posts',
		help='Include WordPress posts',
		action='store_true'
	)
	parser.add_argument(
		'-t', '--no-posts',
		dest='include_posts',
		help='Do not include WordPress posts',
		action='store_false'
	)
	parser.set_defaults(include_posts=False)

	parser.add_argument(
		'-n', '--per-page',
		dest='per_page',
		type=int,
		default=100,
		help='REST API per_page (WordPress usually max 100)'
	)
	parser.add_argument(
		'-s', '--sleep-max',
		dest='sleep_max',
		type=float,
		default=0.6,
		help='Max random sleep seconds before each HTTP request'
	)

	parser.add_argument(
		'-m', '--media-mode',
		dest='media_mode',
		choices=['adjacent', 'assets', 'none'],
		default='adjacent',
		help='Where to put images: adjacent, assets, or none'
	)
	parser.add_argument(
		'-A', '--assets-dir',
		dest='assets_dir',
		default='assets',
		help='Assets dir inside out-dir when media-mode=assets'
	)

	parser.add_argument(
		'-r', '--rewrite-links',
		dest='rewrite_links',
		help='Rewrite internal WordPress links to relative MkDocs links when possible',
		action='store_true'
	)
	parser.add_argument(
		'-R', '--no-rewrite-links',
		dest='rewrite_links',
		help='Do not rewrite internal links',
		action='store_false'
	)
	parser.set_defaults(rewrite_links=True)

	parser.add_argument(
		'-c', '--code-lang',
		dest='code_lang',
		default='py3',
		help='Language label for code fences that have no language'
	)

	parser.add_argument(
		'--posts-prefix',
		dest='posts_prefix',
		default='posts',
		help='Folder prefix inside out-dir for posts'
	)

	parser.add_argument(
		'--title-strip-regex',
		dest='title_strip_regex',
		default='',
		help='Regex to strip from titles, example: ^Python Friday #\\d+\\s*'
	)

	parser.add_argument(
		'--more-tag-regex',
		dest='more_tag_regex',
		default='',
		help='Regex; matching lines get replaced by <!-- more -->'
	)

	parser.add_argument(
		'--report-csv',
		dest='report_csv',
		default='wp_to_mkdocs_report.csv',
		help='CSV report filename written in current directory'
	)

	args = parser.parse_args()
	return args


#============================================
def sleep_briefly(sleep_max: float) -> None:
	"""
	Sleep for a random short duration.

	Args:
		sleep_max (float): Maximum seconds to sleep.
	"""
	time.sleep(random.random() * sleep_max)


#============================================
def build_headers() -> dict:
	"""
	Build browser-like headers to avoid ModSecurity blocks.

	Returns:
		dict: HTTP headers.
	"""
	ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
	ua += "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
	headers = {
		'User-Agent': ua,
		'Accept': 'application/json,text/html;q=0.9,*/*;q=0.8',
		'Accept-Language': 'en-US,en;q=0.9',
	}
	return headers


#============================================
def ensure_dir(dir_path: str) -> None:
	"""
	Create a directory if it does not exist.

	Args:
		dir_path (str): Directory path.
	"""
	os.makedirs(dir_path, exist_ok=True)


#============================================
def sanitize_title(title_html: str) -> str:
	"""
	Remove HTML tags and collapse whitespace.

	Args:
		title_html (str): Title in HTML.

	Returns:
		str: Plain title.
	"""
	title_text = re.sub(r'<[^>]+>', '', title_html)
	title_text = re.sub(r'\s+', ' ', title_text).strip()
	return title_text


#============================================
def strip_title(title: str, strip_regex: str) -> str:
	"""
	Strip a regex from the title.

	Args:
		title (str): Title.
		strip_regex (str): Regex to strip.

	Returns:
		str: Title.
	"""
	if not strip_regex:
		return title
	title = re.sub(strip_regex, '', title).strip()
	return title


#============================================
def site_path_from_link(link: str) -> str:
	"""
	Convert a site link into a normalized site path.

	Args:
		link (str): Absolute URL.

	Returns:
		str: Path without leading and trailing slashes.
	"""
	path = urllib.parse.urlparse(link).path
	path = path.strip('/')
	return path


#============================================
def build_page_output_path(out_dir: str, link: str) -> str:
	"""
	Build a MkDocs-friendly output path for a WordPress page.

	Args:
		out_dir (str): MkDocs docs dir.
		link (str): WordPress page link.

	Returns:
		str: Output Markdown path.
	"""
	site_path = site_path_from_link(link)
	if not site_path:
		return os.path.join(out_dir, 'index.md')
	return os.path.join(out_dir, site_path, 'index.md')


#============================================
def parse_year_from_date(date_str: str) -> str:
	"""
	Parse year from a WordPress date string.

	Args:
		date_str (str): Date string like 2022-06-21T17:36:16

	Returns:
		str: Year, or 'unknown' if not parseable.
	"""
	if not date_str:
		return 'unknown'
	m = re.match(r'^(?P<year>\d{4})-', date_str)
	if not m:
		return 'unknown'
	return m.group('year')


#============================================
def build_post_output_path(out_dir: str, posts_prefix: str, year: str, slug: str) -> str:
	"""
	Build an output path for a WordPress post.

	Args:
		out_dir (str): MkDocs docs dir.
		posts_prefix (str): Posts prefix folder.
		year (str): Year.
		slug (str): Post slug.

	Returns:
		str: Output Markdown path.
	"""
	return os.path.join(out_dir, posts_prefix, year, slug, slug + '.md')


#============================================
def is_image_url(url: str) -> bool:
	"""
	Check whether a URL likely points to an image.

	Args:
		url (str): URL.

	Returns:
		bool: True if URL looks like an image.
	"""
	u = url.lower()
	if u.endswith('.png'):
		return True
	if u.endswith('.jpg'):
		return True
	if u.endswith('.jpeg'):
		return True
	if u.endswith('.gif'):
		return True
	if u.endswith('.webp'):
		return True
	return False


#============================================
def find_image_urls_in_html(html: str) -> list:
	"""
	Find image URLs in HTML.

	Args:
		html (str): HTML.

	Returns:
		list: Image URLs.
	"""
	urls = []
	for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
		urls.append(m.group(1))

	for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
		href = m.group(1)
		if is_image_url(href):
			urls.append(href)

	unique_urls = []
	seen = set()
	for u in urls:
		if u in seen:
			continue
		seen.add(u)
		unique_urls.append(u)

	return unique_urls


#============================================
def sanitize_filename(filename: str) -> str:
	"""
	Sanitize filename to ASCII-safe characters.

	Args:
		filename (str): Filename.

	Returns:
		str: Sanitized filename.
	"""
	filename = filename.strip()
	if not filename:
		return 'asset'

	filename = filename.encode('ascii', errors='ignore').decode('ascii')
	filename = re.sub(r'[^A-Za-z0-9._-]+', '-', filename).strip('-')
	if not filename:
		return 'asset'
	return filename


#============================================
def choose_asset_filename(asset_url: str) -> str:
	"""
	Choose a local filename for an asset URL.

	Args:
		asset_url (str): Asset URL.

	Returns:
		str: Local filename.
	"""
	path = urllib.parse.urlparse(asset_url).path
	name = os.path.basename(path)
	name = urllib.parse.unquote(name)
	name = sanitize_filename(name)
	if not name or name == 'asset':
		name += '.bin'
	return name


#============================================
def download_asset(
	session: requests.Session,
	asset_url: str,
	out_assets_dir: str,
	sleep_max: float
) -> str:
	"""
	Download an asset and return the local filename.

	Args:
		session (requests.Session): HTTP session.
		asset_url (str): Asset URL.
		out_assets_dir (str): Assets directory.
		sleep_max (float): Max sleep before request.

	Returns:
		str: Local filename.

	Raises:
		RuntimeError: If download fails.
	"""
	ensure_dir(out_assets_dir)

	filename = choose_asset_filename(asset_url)
	out_path = os.path.join(out_assets_dir, filename)
	if os.path.exists(out_path):
		return filename

	sleep_briefly(sleep_max)
	resp = session.get(asset_url, stream=True, timeout=30)
	if resp.status_code != 200:
		raise RuntimeError('Asset download failed ' + str(resp.status_code) + ': ' + asset_url)

	with open(out_path, 'wb') as f:
		for chunk in resp.iter_content(chunk_size=1024 * 64):
			if not chunk:
				continue
			f.write(chunk)

	return filename


#============================================
def relink_images_in_html(
	session: requests.Session,
	html: str,
	base_url: str,
	out_md_path: str,
	out_dir: str,
	assets_dir: str,
	media_mode: str,
	sleep_max: float
) -> tuple:
	"""
	Download images referenced in HTML and relink.

	Args:
		session (requests.Session): HTTP session.
		html (str): HTML.
		base_url (str): Base site URL.
		out_md_path (str): Output Markdown path for this item.
		out_dir (str): MkDocs docs dir.
		assets_dir (str): Assets dir name inside out_dir.
		media_mode (str): adjacent, assets, none.
		sleep_max (float): Max sleep.

	Returns:
		tuple: (updated_html, downloaded_files)
	"""
	if media_mode == 'none':
		return html, []

	base_url = base_url.rstrip('/') + '/'
	image_urls = find_image_urls_in_html(html)
	downloaded = []

	if media_mode == 'adjacent':
		target_dir = os.path.dirname(out_md_path)
	else:
		target_dir = os.path.join(out_dir, assets_dir)

	for u in image_urls:
		abs_url = urllib.parse.urljoin(base_url, u)
		if not is_image_url(abs_url):
			continue

		local_name = download_asset(session, abs_url, target_dir, sleep_max)
		downloaded.append(local_name)

		if media_mode == 'adjacent':
			new_ref = local_name
		else:
			new_ref = assets_dir.rstrip('/') + '/' + local_name
			new_ref = new_ref.replace('\\', '/')

		html = html.replace('src="' + u + '"', 'src="' + new_ref + '"')
		html = html.replace("src='" + u + "'", "src='" + new_ref + "'")
		html = html.replace('href="' + u + '"', 'href="' + new_ref + '"')
		html = html.replace("href='" + u + "'", "href='" + new_ref + "'")

		html = html.replace('src="' + abs_url + '"', 'src="' + new_ref + '"')
		html = html.replace("src='" + abs_url + "'", "src='" + new_ref + "'")
		html = html.replace('href="' + abs_url + '"', 'href="' + new_ref + '"')
		html = html.replace("href='" + abs_url + "'", "href='" + new_ref + "'")

	return html, downloaded

#============================================
def strip_embeds_from_html(html: str) -> str:
	"""
	Remove common embed tags that cause network fetches during conversion.

	Args:
		html (str): HTML.

	Returns:
		str: Cleaned HTML.
	"""
	html = re.sub(
		r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>',
		'',
		html,
		flags=re.IGNORECASE
	)
	html = re.sub(
		r'<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>',
		'',
		html,
		flags=re.IGNORECASE
	)
	html = re.sub(
		r'<blockquote\b[^>]*class=["\'][^"\']*(wp-embedded-content|fb-post)[^"\']*["\'][^>]*>.*?<\/blockquote>',
		'',
		html,
		flags=re.IGNORECASE | re.DOTALL
	)
	return html

#============================================
def pandoc_html_to_md(html: str) -> str:
	"""
	Convert HTML to GitHub-flavored Markdown using pandoc.

	Args:
		html (str): HTML fragment.

	Returns:
		str: Markdown.
	"""
	cmd = [
		'pandoc',
		'--sandbox',
		'--fail-if-warnings=false',
		'-f', 'html',
		'-t', 'gfm',
		'--wrap=preserve',
	]
	md = subprocess.check_output(cmd, input=html, text=True)
	md = md.strip() + "\n"
	return md


#============================================
def add_front_matter(
	md: str,
	title: str,
	wp_link: str,
	wp_id: int,
	date_str: str,
	item_type: str
) -> str:
	"""
	Add YAML front matter to Markdown.

	Args:
		md (str): Markdown body.
		title (str): Title.
		wp_link (str): WordPress link.
		wp_id (int): WordPress ID.
		date_str (str): Date string from WordPress.
		item_type (str): page or post.

	Returns:
		str: Markdown with YAML front matter.
	"""
	lines = []
	lines.append('---')
	lines.append('title: "' + title.replace('"', '') + '"')
	lines.append('type: "' + item_type + '"')
	lines.append('wp_id: ' + str(wp_id))
	lines.append('wp_link: "' + wp_link + '"')
	if date_str:
		lines.append('date: "' + date_str + '"')
	lines.append('---')
	lines.append('')
	lines.append(md.rstrip())
	lines.append('')
	return "\n".join(lines)


#============================================
def apply_more_tag(md: str, more_tag_regex: str) -> str:
	"""
	Replace matching lines with <!-- more -->.

	Args:
		md (str): Markdown.
		more_tag_regex (str): Regex.

	Returns:
		str: Markdown.
	"""
	if not more_tag_regex:
		return md

	out = []
	pat = re.compile(more_tag_regex)
	for line in md.splitlines():
		if pat.search(line):
			out.append('<!-- more -->')
			continue
		out.append(line)

	return "\n".join(out) + "\n"


#============================================
def ensure_more_tag_once(md: str) -> str:
	"""
	Ensure there is one <!-- more --> tag, best-effort.

	Args:
		md (str): Markdown.

	Returns:
		str: Markdown.
	"""
	if '<!-- more -->' in md:
		return md

	lines = md.splitlines()
	out = []
	inserted = False

	for line in lines:
		if not inserted and line.startswith('## '):
			out.append('<!-- more -->')
			out.append('')
			inserted = True
		out.append(line)

	if not inserted:
		out.append('')
		out.append('<!-- more -->')

	return "\n".join(out) + "\n"


#============================================
def add_code_fence_language(md: str, code_lang: str) -> str:
	"""
	Add language tag to code fences that have none.

	Args:
		md (str): Markdown.
		code_lang (str): Language tag.

	Returns:
		str: Markdown.
	"""
	out = []
	in_code = False
	for line in md.splitlines():
		if line.startswith('```'):
			if line.strip() == '```':
				if not in_code:
					out.append('``` ' + code_lang)
					in_code = True
					continue
				out.append('```')
				in_code = False
				continue

			out.append(line)
			if not in_code:
				in_code = True
			else:
				in_code = False
			continue

		out.append(line)

	return "\n".join(out) + "\n"


#============================================
def build_link_map(items: list, out_dir: str, posts_prefix: str) -> dict:
	"""
	Build a map from WordPress link to output relpath.

	Args:
		items (list): Items with type, link, date, slug.
		out_dir (str): MkDocs docs dir.
		posts_prefix (str): Posts prefix.

	Returns:
		dict: Map of wp_link -> relpath from out_dir.
	"""
	link_map = {}
	for it in items:
		if it['type'] == 'page':
			out_path = build_page_output_path(out_dir, it['link'])
		else:
			year = parse_year_from_date(it.get('date', ''))
			out_path = build_post_output_path(out_dir, posts_prefix, year, it.get('slug', 'post'))

		rel = os.path.relpath(out_path, out_dir)
		rel = rel.replace('\\', '/')
		link_map[it['link'].rstrip('/')] = rel
		link_map[it['link'].rstrip('/') + '/'] = rel

	return link_map


#============================================
def rewrite_md_links_to_relative(md: str, current_out_path: str, out_dir: str, link_map: dict) -> str:
	"""
	Rewrite Markdown links that match the WordPress link map to relative paths.

	Args:
		md (str): Markdown.
		current_out_path (str): Current output md path.
		out_dir (str): MkDocs docs dir.
		link_map (dict): Map of wp_link -> relpath.

	Returns:
		str: Updated Markdown.
	"""
	current_dir = os.path.dirname(current_out_path)

	def repl(m: re.Match) -> str:
		text = m.group(1)
		url = m.group(2)

		key = url.rstrip('/')
		if key not in link_map:
			return m.group(0)

		target_rel_from_out = link_map[key]
		target_abs = os.path.join(out_dir, target_rel_from_out)
		rel_from_current = os.path.relpath(target_abs, current_dir)
		rel_from_current = rel_from_current.replace('\\', '/')
		return '[' + text + '](' + rel_from_current + ')'

	pat = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
	md = pat.sub(repl, md)
	return md


#============================================
def request_json(
	session: requests.Session,
	url: str,
	sleep_max: float
) -> tuple:
	"""
	Request JSON and return parsed JSON and headers.

	Args:
		session (requests.Session): HTTP session.
		url (str): URL.
		sleep_max (float): Max sleep.

	Returns:
		tuple: (json_obj, headers)

	Raises:
		RuntimeError: If HTTP status is not 200.
	"""
	sleep_briefly(sleep_max)
	resp = session.get(url, timeout=30)
	if resp.status_code != 200:
		raise RuntimeError('HTTP failed ' + str(resp.status_code) + ': ' + url)
	return resp.json(), resp.headers


#============================================
def fetch_items(
	session: requests.Session,
	base_url: str,
	endpoint: str,
	per_page: int,
	sleep_max: float
) -> list:
	"""
	Fetch all items from a WordPress REST endpoint with pagination.

	Args:
		session (requests.Session): HTTP session.
		base_url (str): Base URL.
		endpoint (str): REST endpoint, example: pages or posts.
		per_page (int): Items per page.
		sleep_max (float): Max sleep.

	Returns:
		list: Items.
	"""
	base_url = base_url.rstrip('/')
	page = 1
	total_pages = 1
	all_items = []

	while page <= total_pages:
		url = base_url + '/wp-json/wp/v2/' + endpoint
		url += '?status=publish'
		url += '&per_page=' + str(per_page)
		url += '&page=' + str(page)
		url += '&_fields=id,slug,link,title,content,date'

		obj, headers = request_json(session, url, sleep_max)

		if 'X-WP-TotalPages' in headers:
			total_pages = int(headers['X-WP-TotalPages'])

		for it in obj:
			item = {
				'id': int(it.get('id', 0)),
				'slug': it.get('slug', ''),
				'link': it.get('link', ''),
				'date': it.get('date', ''),
				'title_html': it.get('title', {}).get('rendered', ''),
				'content_html': it.get('content', {}).get('rendered', ''),
			}
			all_items.append(item)

		page += 1

	return all_items


#============================================
def write_report_csv(report_csv: str, rows: list) -> None:
	"""
	Write a CSV report.

	Args:
		report_csv (str): Output CSV path.
		rows (list): Report rows.
	"""
	with open(report_csv, 'w', newline='', encoding='utf-8') as f:
		w = csv.writer(f)
		w.writerow(['type', 'wp_id', 'slug', 'wp_link', 'out_path', 'images_downloaded'])
		for r in rows:
			w.writerow(r)


#============================================
def convert_one_item(
	session: requests.Session,
	base_url: str,
	out_dir: str,
	assets_dir: str,
	media_mode: str,
	sleep_max: float,
	rewrite_links: bool,
	code_lang: str,
	title_strip_regex: str,
	more_tag_regex: str,
	item_type: str,
	wp_id: int,
	slug: str,
	wp_link: str,
	date_str: str,
	title_html: str,
	content_html: str,
	link_map: dict,
	out_path: str
) -> tuple:
	"""
	Convert one WordPress item to Markdown and write it.

	Args:
		session (requests.Session): HTTP session.
		base_url (str): Base URL.
		out_dir (str): MkDocs docs dir.
		assets_dir (str): Assets dir.
		media_mode (str): adjacent, assets, none.
		sleep_max (float): Max sleep.
		rewrite_links (bool): Rewrite internal links.
		code_lang (str): Code fence language.
		title_strip_regex (str): Regex to strip from title.
		more_tag_regex (str): Regex for <!-- more --> replacement.
		item_type (str): page or post.
		wp_id (int): WordPress id.
		slug (str): Slug.
		wp_link (str): Link.
		date_str (str): Date.
		title_html (str): Title HTML.
		content_html (str): Content HTML.
		link_map (dict): Map of wp_link -> relpath.
		out_path (str): Output path.

	Returns:
		tuple: (out_path, images_downloaded_count)
	"""
	title = sanitize_title(title_html)
	title = strip_title(title, title_strip_regex)

	ensure_dir(os.path.dirname(out_path))

	html, downloaded = relink_images_in_html(
		session=session,
		html=content_html,
		base_url=base_url,
		out_md_path=out_path,
		out_dir=out_dir,
		assets_dir=assets_dir,
		media_mode=media_mode,
		sleep_max=sleep_max
	)

	html = strip_embeds_from_html(html)
	md = pandoc_html_to_md(html)
	md = add_code_fence_language(md, code_lang)
	md = apply_more_tag(md, more_tag_regex)

	if item_type == 'post':
		md = ensure_more_tag_once(md)

	if rewrite_links:
		md = rewrite_md_links_to_relative(md, out_path, out_dir, link_map)

	md = add_front_matter(
		md=md,
		title=title,
		wp_link=wp_link,
		wp_id=wp_id,
		date_str=date_str,
		item_type=item_type
	)

	with open(out_path, 'w', encoding='utf-8') as f:
		f.write(md)

	return out_path, len(downloaded)


#============================================
def main() -> None:
	"""
	Main entry point.

	Raises:
		RuntimeError: For fetch or conversion failures.
	"""
	args = parse_args()

	out_dir = args.out_dir
	ensure_dir(out_dir)

	session = requests.Session()
	session.headers.update(build_headers())

	items = []

	if args.include_pages:
		pages = fetch_items(
			session=session,
			base_url=args.base_url,
			endpoint='pages',
			per_page=args.per_page,
			sleep_max=args.sleep_max
		)
		for p in pages:
			p['type'] = 'page'
			items.append(p)

	if args.include_posts:
		posts = fetch_items(
			session=session,
			base_url=args.base_url,
			endpoint='posts',
			per_page=args.per_page,
			sleep_max=args.sleep_max
		)
		for p in posts:
			p['type'] = 'post'
			items.append(p)

	if not items:
		raise RuntimeError('No items to convert. Enable pages and or posts.')

	link_map = build_link_map(items, out_dir, args.posts_prefix)

	report_rows = []

	for it in items:
		if it['type'] == 'page':
			out_path = build_page_output_path(out_dir, it['link'])
		else:
			year = parse_year_from_date(it.get('date', ''))
			out_path = build_post_output_path(out_dir, args.posts_prefix, year, it.get('slug', 'post'))

		out_path, img_count = convert_one_item(
			session=session,
			base_url=args.base_url,
			out_dir=out_dir,
			assets_dir=args.assets_dir,
			media_mode=args.media_mode,
			sleep_max=args.sleep_max,
			rewrite_links=args.rewrite_links,
			code_lang=args.code_lang,
			title_strip_regex=args.title_strip_regex,
			more_tag_regex=args.more_tag_regex,
			item_type=it['type'],
			wp_id=it['id'],
			slug=it.get('slug', ''),
			wp_link=it.get('link', ''),
			date_str=it.get('date', ''),
			title_html=it.get('title_html', ''),
			content_html=it.get('content_html', ''),
			link_map=link_map,
			out_path=out_path
		)

		report_rows.append([
			it['type'],
			str(it['id']),
			it.get('slug', ''),
			it.get('link', ''),
			out_path,
			str(img_count),
		])

	write_report_csv(args.report_csv, report_rows)


#============================================
def _assert_sanitize_filename() -> None:
	"""
	Simple assertion test for sanitize_filename().

	Returns:
		None
	"""
	result = sanitize_filename("JoHN  file 01.png")
	assert result == "JoHN-file-01.png"


#============================================
if __name__ == '__main__':
	_assert_sanitize_filename()
	main()
