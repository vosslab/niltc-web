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
	parser = argparse.ArgumentParser(description="Generate Past Shows pages from data/shows.yml")

	parser.add_argument(
		'-i', '--input', dest='input_file', required=False, type=str,
		default='data/shows.yml',
		help='Input YAML file (default: data/shows.yml)',
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
	Read a YAML file.

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
def parse_iso_date(date_text: str) -> datetime.date:
	"""
	Parse ISO YYYY-MM-DD date string.

	Args:
		date_text (str): Date string.

	Returns:
		datetime.date: Parsed date.
	"""
	date_text = str(date_text).strip()
	return datetime.date.fromisoformat(date_text)


#============================================
def normalize_pictures(pictures_raw) -> list:
	"""
	Normalize pictures into a list of {url: ...} dicts.

	Allowed inputs:
	- list[str] of URLs
	- list[dict] containing url keys

	Args:
		pictures_raw: Raw pictures value from YAML.

	Returns:
		list: List of dicts with key 'url'.
	"""
	if not pictures_raw:
		return []

	if not isinstance(pictures_raw, list):
		raise ValueError('pictures must be a list')

	out = []
	for item in pictures_raw:
		if isinstance(item, str):
			url_str = normalize_url(item)
			if url_str:
				out.append({'url': url_str})
			continue
		if isinstance(item, dict):
			url_str = normalize_url(str(item.get('url', '') or ''))
			if url_str:
				out.append({'url': url_str})
			continue
	return out


#============================================
def classify_event(start_date: datetime.date, end_date: datetime.date, today: datetime.date) -> str:
	"""
	Classify an event by date.

	Args:
		start_date (datetime.date): Start date.
		end_date (datetime.date): End date.
		today (datetime.date): Today's date.

	Returns:
		str: One of 'past', 'current', 'upcoming'.
	"""
	if end_date < today:
		return 'past'
	if start_date <= today <= end_date:
		return 'current'
	return 'upcoming'


#============================================
def normalize_schema2(raw: dict) -> tuple:
	"""
	Normalize schema: 2 show data.

	Args:
		raw (dict): Raw YAML dict.

	Returns:
		tuple: (venues, events)
	"""
	if raw is None:
		raise ValueError('YAML file is empty')
	if int(raw.get('schema', 0) or 0) != 2:
		raise ValueError('Expected schema: 2')

	venues_raw = raw.get('venues', {})
	if not isinstance(venues_raw, dict):
		raise ValueError('venues must be a dict')

	venues = {}
	for venue_id, venue in venues_raw.items():
		if not isinstance(venue_id, str) or not venue_id:
			continue
		if not isinstance(venue, dict):
			continue
		venues[venue_id] = {
			'name': str(venue.get('name', '')).strip(),
			'address': str(venue.get('address', '')).strip(),
			'city': str(venue.get('city', '')).strip(),
			'state': str(venue.get('state', '')).strip(),
			'postal_code': str(venue.get('postal_code', '')).strip(),
			'website': str(venue.get('website', '')).strip(),
		}

	events_raw = raw.get('events', [])
	if not isinstance(events_raw, list):
		raise ValueError('events must be a list')

	events = []
	for event in events_raw:
		if not isinstance(event, dict):
			continue

		event_id = str(event.get('id', '')).strip()
		venue_id = str(event.get('venue', '')).strip()
		status = str(event.get('status', '')).strip()
		start_date = parse_iso_date(event.get('start_date', ''))
		end_date = parse_iso_date(event.get('end_date', ''))

		if end_date < start_date:
			raise ValueError(f'Event end_date before start_date: {event_id}')
		if status != 'confirmed':
			continue
		if not event_id:
			continue
		if venue_id not in venues:
			raise ValueError(f'Event references unknown venue: {event_id} -> {venue_id}')

		pictures = normalize_pictures(event.get('pictures'))

		events.append({
			'id': event_id,
			'venue': venue_id,
			'start_date': start_date,
			'end_date': end_date,
			'status': status,
			'pictures': pictures,
		})

	return (venues, events)


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
def ordinal_suffix(day: int) -> str:
	"""
	Get English ordinal suffix for a day number.

	Args:
		day (int): Day number.

	Returns:
		str: Suffix (st/nd/rd/th).
	"""
	if 11 <= (day % 100) <= 13:
		return 'th'
	last = day % 10
	if last == 1:
		return 'st'
	if last == 2:
		return 'nd'
	if last == 3:
		return 'rd'
	return 'th'


#============================================
def format_date_range(start_date: datetime.date, end_date: datetime.date) -> str:
	"""
	Format a date range like the legacy Past Shows pages.

	Examples:
	- November 8th – 9th
	- September 30th – October 1st

	Args:
		start_date (datetime.date): Start date.
		end_date (datetime.date): End date.

	Returns:
		str: Formatted date range (no year).
	"""
	month_start = start_date.strftime('%B')
	month_end = end_date.strftime('%B')
	start_day = start_date.day
	end_day = end_date.day

	start_part = f'{month_start} {start_day}{ordinal_suffix(start_day)}'
	if start_date == end_date:
		return start_part

	if month_start == month_end:
		end_part = f'{end_day}{ordinal_suffix(end_day)}'
	else:
		end_part = f'{month_end} {end_day}{ordinal_suffix(end_day)}'

	return start_part + ' – ' + end_part


#============================================
def pictures_cell_markdown(pictures: list) -> str:
	"""
	Render pictures cell markdown from a list of {url: ...} dicts.

	Args:
		pictures (list): List of dicts with key 'url'.

	Returns:
		str: Markdown for the pictures cell.
	"""
	if not pictures:
		return ''

	parts = []
	for pic in pictures:
		if not isinstance(pic, dict):
			continue
		url_str = normalize_url(str(pic.get('url', '') or ''))
		if not url_str:
			continue
		parts.append(f'[Link]({url_str})')

	return ' '.join(parts)


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
	Write a text file to disk (only if content changed).

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
def build_rows_for_year(past_events: list, venues: dict, year: int) -> list:
	"""
	Build table rows for a year from past events.

	Args:
		past_events (list): List of event dicts.
		venues (dict): Venues dict keyed by id.
		year (int): Year.

	Returns:
		list: Rows suitable for render_year_table.
	"""
	events = [e for e in past_events if e['start_date'].year == year]
	events = sorted(events, key=lambda e: e['start_date'], reverse=True)

	rows = []
	for event in events:
		venue = venues.get(event['venue'], {})
		show_name = str(venue.get('name', '')).strip()
		rows.append({
			'date': format_date_range(event['start_date'], event['end_date']),
			'show': show_name,
			'pictures': event.get('pictures', []),
		})
	return rows


#============================================
def generate_past_shows_pages(input_yaml: str, docs_dir: str, current_year: int, dry_run: bool, today=None):
	"""
	Generate Past Shows pages into mkdocs/docs/past-shows/.

	Args:
		input_yaml (str): Input YAML data file path (schema 2).
		docs_dir (str): MkDocs docs directory.
		current_year (int): Current year to show on the overview page.
		dry_run (bool): If True, do not write files.
		today: Optional override for today's date (datetime.date).
	"""
	if today is None:
		today = datetime.date.today()

	raw = read_yaml_file(input_yaml)
	venues, events = normalize_schema2(raw)

	past_events = []
	for event in events:
		if classify_event(event['start_date'], event['end_date'], today) == 'past':
			past_events.append(event)

	years = sorted({e['start_date'].year for e in past_events}, reverse=True)
	decades: dict = {}
	for year in years:
		decade_start = decade_start_for_year(year)
		if decade_start not in decades:
			decades[decade_start] = []
		decades[decade_start].append(year)
	for decade_start in decades:
		decades[decade_start] = sorted(decades[decade_start], reverse=True)

	decade_starts = sorted(decades.keys(), reverse=True)
	past_shows_dir = os.path.join(docs_dir, 'past-shows')

	# Overview page: current year + decade links
	overview_md = overview_front_matter()
	overview_md += '<!-- Generated from data/shows.yml. Edit that file instead. -->\n\n'

	current_year_rows = build_rows_for_year(past_events, venues, current_year)
	overview_md += render_year_section(current_year, current_year_rows)
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
		decade_md += '<!-- Generated from data/shows.yml. Edit that file instead. -->\n\n'

		for year in decades[decade_start]:
			year_rows = build_rows_for_year(past_events, venues, year)
			decade_md += render_year_section(year, year_rows)
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
	# Simple asserts for new pure functions
	assert ordinal_suffix(1) == 'st'
	assert ordinal_suffix(2) == 'nd'
	assert ordinal_suffix(3) == 'rd'
	assert ordinal_suffix(4) == 'th'
	assert classify_event(datetime.date(2025, 1, 1), datetime.date(2025, 1, 2), datetime.date(2025, 1, 3)) == 'past'

	main()
