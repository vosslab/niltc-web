#!/usr/bin/env python3

# Standard Library
import os
import html
import datetime
import argparse

# PIP3 modules
import yaml


#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed arguments.
	"""
	parser = argparse.ArgumentParser(description="Generate Past Shows pages from YAML")

	parser.add_argument(
		'-i', '--input', dest='input_file', required=False, type=str,
		default='data/past_shows.yml',
		help='Input YAML file (default: data/past_shows.yml)',
	)
	parser.add_argument(
		'-d', '--docs-dir', dest='docs_dir', required=False, type=str,
		default='mkdocs/docs',
		help='MkDocs docs dir (default: mkdocs/docs)',
	)
	parser.add_argument(
		'-y', '--year', dest='current_year', required=False, type=int,
		default=None,
		help='Override current year for overview page',
	)

	parser.add_argument(
		'-n', '--dry-run', dest='dry_run', help='Do not write files', action='store_true'
	)
	parser.add_argument(
		'-w', '--write', dest='dry_run', help='Write files (default)', action='store_false'
	)
	parser.set_defaults(dry_run=False)

	args = parser.parse_args()
	return args


#============================================
def read_yaml_file(yaml_path: str) -> dict:
	"""
	Read the past shows YAML data file.

	Args:
		yaml_path (str): YAML file path.

	Returns:
		dict: Parsed YAML content.
	"""
	with open(yaml_path, 'r', encoding='utf-8') as f:
		data = yaml.safe_load(f)
	return data


#============================================
def normalize_url(url: str) -> str:
	"""
	Normalize URL strings (mainly HTML entity unescaping).

	Args:
		url (str): URL string.

	Returns:
		str: Normalized URL.
	"""
	url = url.strip()
	url = html.unescape(url)
	return url


#============================================
def normalize_shows_by_year(raw: dict) -> dict:
	"""
	Normalize and validate shows_by_year content.

	Args:
		raw (dict): Raw YAML dict.

	Returns:
		dict: Normalized shows_by_year where keys are int and values are list of rows.
	"""
	if raw is None:
		raise ValueError('YAML file is empty')
	if 'shows_by_year' not in raw:
		raise ValueError('Missing required key: shows_by_year')

	shows_by_year_raw = raw['shows_by_year']
	if not isinstance(shows_by_year_raw, dict):
		raise ValueError('shows_by_year must be a dict')

	shows_by_year: dict = {}
	for year_key in shows_by_year_raw:
		year_int = int(year_key)
		rows_raw = shows_by_year_raw[year_key]
		if rows_raw is None:
			rows_raw = []
		if not isinstance(rows_raw, list):
			raise ValueError(f'shows_by_year[{year_key}] must be a list')

		rows = []
		for row in rows_raw:
			if not isinstance(row, dict):
				raise ValueError(f'Each row in shows_by_year[{year_key}] must be a dict')

			date_str = str(row.get('date', '')).strip()
			show_str = str(row.get('show', '')).strip()
			pictures_raw = row.get('pictures', [])
			if pictures_raw is None:
				pictures_raw = []
			if not isinstance(pictures_raw, list):
				raise ValueError(f'Row pictures must be a list (year {year_key}, show {show_str})')

			pictures = []
			for pic in pictures_raw:
				if not isinstance(pic, dict):
					continue
				text_str = str(pic.get('text', 'Link')).strip() or 'Link'
				url_str = str(pic.get('url', '')).strip()
				if not url_str:
					continue
				url_str = normalize_url(url_str)
				pictures.append({'text': text_str, 'url': url_str})

			rows.append({'date': date_str, 'show': show_str, 'pictures': pictures})

		shows_by_year[year_int] = rows

	return shows_by_year


#============================================
def decade_start_for_year(year: int) -> int:
	"""
	Get the decade start year for a given year.

	Args:
		year (int): Year.

	Returns:
		int: Decade start year (e.g., 2010 for 2017).
	"""
	decade_start = (year // 10) * 10
	return decade_start


#============================================
def group_years_by_decade(shows_by_year: dict) -> dict:
	"""
	Group years into decades.

	Args:
		shows_by_year (dict): Mapping of year to list of rows.

	Returns:
		dict: Mapping of decade start year to list of years.
	"""
	decades: dict = {}
	for year in shows_by_year:
		decade_start = decade_start_for_year(year)
		if decade_start not in decades:
			decades[decade_start] = []
		decades[decade_start].append(year)

	for decade_start in decades:
		decades[decade_start] = sorted(decades[decade_start], reverse=True)

	return decades


#============================================
def pictures_cell_markdown(pictures: list) -> str:
	"""
	Render pictures cell markdown from a list of pictures.

	Args:
		pictures (list): List of dicts with keys 'text' and 'url'.

	Returns:
		str: Markdown for the pictures cell.
	"""
	if not pictures:
		return ''

	parts = []
	for pic in pictures:
		text_str = str(pic.get('text', 'Link')).strip() or 'Link'
		url_str = str(pic.get('url', '')).strip()
		if not url_str:
			continue
		parts.append(f'[{text_str}]({url_str})')

	cell = ' '.join(parts)
	return cell


#============================================
def render_year_table(rows: list) -> str:
	"""
	Render a Markdown table for a list of show rows.

	Args:
		rows (list): List of row dicts (date/show/pictures).

	Returns:
		str: Markdown table.
	"""
	out_lines = []
	out_lines.append('| Date | Show | Pictures |')
	out_lines.append('| --- | --- | --- |')

	for row in rows:
		date_str = str(row.get('date', '')).strip()
		show_str = str(row.get('show', '')).strip()
		pics_md = pictures_cell_markdown(row.get('pictures', []))
		out_lines.append(f'| {date_str} | {show_str} | {pics_md} |')

	out = '\n'.join(out_lines) + '\n'
	return out


#============================================
def render_year_section(year: int, rows: list) -> str:
	"""
	Render a year section with heading + table.

	Args:
		year (int): Year.
		rows (list): List of show rows.

	Returns:
		str: Markdown for the section.
	"""
	out = ''
	out += f'## {year}\n\n'
	if not rows:
		out += '_No shows recorded._\n'
		return out

	out += render_year_table(rows)
	return out


#============================================
def ensure_dir(path: str):
	"""
	Ensure a directory exists.

	Args:
		path (str): Directory path.
	"""
	os.makedirs(path, exist_ok=True)


#============================================
def write_text_file(path: str, content: str, dry_run: bool):
	"""
	Write a text file to disk.

	Args:
		path (str): File path.
		content (str): File content.
		dry_run (bool): If True, do not write.
	"""
	parent_dir = os.path.dirname(path)
	if parent_dir:
		ensure_dir(parent_dir)

	if dry_run:
		return

	if os.path.exists(path):
		with open(path, 'r', encoding='utf-8') as f:
			existing = f.read()
		if existing == content:
			return

	with open(path, 'w', encoding='utf-8') as f:
		f.write(content)


#============================================
def overview_front_matter() -> str:
	"""
	Get front matter for the Past Shows overview page.

	Returns:
		str: YAML front matter.
	"""
	out = ''
	out += '---\n'
	out += 'title: \"Past Shows\"\n'
	out += 'type: \"page\"\n'
	out += 'wp_id: 158\n'
	out += 'wp_link: \"https://niltc.org/past-shows\"\n'
	out += 'date: \"2011-01-17T03:19:24\"\n'
	out += '---\n'
	out += '\n'
	return out


#============================================
def decade_page_front_matter(decade_start: int) -> str:
	"""
	Get front matter for a decade page.

	Args:
		decade_start (int): Decade start year (e.g., 2010).

	Returns:
		str: YAML front matter.
	"""
	out = ''
	out += '---\n'
	out += f'title: \"Past Shows ({decade_start}s)\"\n'
	out += '---\n'
	out += '\n'
	return out


#============================================
def generate_past_shows_pages(input_yaml: str, docs_dir: str, current_year: int, dry_run: bool):
	"""
	Generate Past Shows pages into mkdocs/docs/past-shows/.

	Args:
		input_yaml (str): Input YAML data file path.
		docs_dir (str): MkDocs docs directory.
		current_year (int): Current year to show on the overview page.
		dry_run (bool): If True, do not write files.
	"""
	raw = read_yaml_file(input_yaml)
	shows_by_year = normalize_shows_by_year(raw)

	decades = group_years_by_decade(shows_by_year)
	decade_starts = sorted(decades.keys(), reverse=True)

	past_shows_dir = os.path.join(docs_dir, 'past-shows')

	# Overview page: current year + decade links
	overview_md = overview_front_matter()
	overview_md += '<!-- Generated from data/past_shows.yml. Edit that file instead. -->\n\n'

	overview_md += render_year_section(current_year, shows_by_year.get(current_year, []))
	overview_md += '\n'
	overview_md += '## Browse by decade\n\n'
	for decade_start in decade_starts:
		decade_slug = f'{decade_start}s'
		overview_md += f'- [{decade_start}s]({decade_slug}/index.md)\n'

	overview_path = os.path.join(past_shows_dir, 'index.md')
	write_text_file(overview_path, overview_md, dry_run)

	# Decade pages
	for decade_start in decade_starts:
		decade_slug = f'{decade_start}s'
		decade_dir = os.path.join(past_shows_dir, decade_slug)
		decade_path = os.path.join(decade_dir, 'index.md')

		decade_md = decade_page_front_matter(decade_start)
		decade_md += '<!-- Generated from data/past_shows.yml. Edit that file instead. -->\n\n'

		for year in decades[decade_start]:
			decade_md += render_year_section(year, shows_by_year.get(year, []))
			decade_md += '\n'

		write_text_file(decade_path, decade_md, dry_run)


#============================================
def main():
	"""
	Main entrypoint.
	"""
	args = parse_args()

	if args.current_year is None:
		args.current_year = datetime.date.today().year

	generate_past_shows_pages(
		input_yaml=args.input_file,
		docs_dir=args.docs_dir,
		current_year=args.current_year,
		dry_run=args.dry_run,
	)


if __name__ == '__main__':
	main()
