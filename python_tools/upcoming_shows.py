#!/usr/bin/env python3

# Standard Library
import os
import datetime

# local repo modules
import python_tools.shows_data


#============================================
def upcoming_front_matter() -> str:
	"""
	Get front matter for the Upcoming Shows page.

	Returns:
		str: YAML front matter.
	"""
	out = ''
	out += '---\n'
	out += 'title: \"Upcoming Shows\"\n'
	out += 'type: \"page\"\n'
	out += 'wp_id: 145\n'
	out += 'wp_link: \"https://niltc.org/upcoming-shows\"\n'
	out += 'date: \"2011-01-17T03:06:09\"\n'
	out += '---\n'
	out += '\n'
	return out


#============================================
def format_venue_block(venue: dict) -> str:
	"""
	Format venue address block.

	Args:
		venue (dict): Venue dict.

	Returns:
		str: Markdown lines.
	"""
	lines = []
	address = str(venue.get('address', '')).strip()
	city = str(venue.get('city', '')).strip()
	state = str(venue.get('state', '')).strip()
	postal_code = str(venue.get('postal_code', '')).strip()

	if address:
		lines.append(address)

	csz = ''
	if city:
		csz += city
	if state:
		if csz:
			csz += ', '
		csz += state
	if postal_code:
		if csz:
			csz += ' '
		csz += postal_code
	if csz:
		lines.append(csz)

	return '  \n'.join(lines)


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
		os.makedirs(parent_dir, exist_ok=True)

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
def generate_upcoming_shows_page(input_yaml: str, docs_dir: str, dry_run: bool, today=None):
	"""
	Generate mkdocs/docs/upcoming-shows/index.md from data/shows.yml.

	Args:
		input_yaml (str): Input YAML data file path (schema 2).
		docs_dir (str): MkDocs docs directory.
		dry_run (bool): If True, do not write files.
		today: Optional override for today's date (datetime.date).
	"""
	if today is None:
		today = datetime.date.today()

	raw = python_tools.shows_data.read_yaml_file(input_yaml)
	venues, events = python_tools.shows_data.normalize_schema2(raw)

	current_events = []
	upcoming_events = []
	for event in events:
		status = python_tools.shows_data.classify_event(event['start_date'], event['end_date'], today)
		if status == 'current':
			current_events.append(event)
		elif status == 'upcoming':
			upcoming_events.append(event)

	current_events = sorted(current_events, key=lambda e: e['start_date'])
	upcoming_events = sorted(upcoming_events, key=lambda e: e['start_date'])

	out = upcoming_front_matter()
	out += '<!-- Generated from data/shows.yml. Edit that file instead. -->\n\n'
	out += 'Times may vary by venue. Please check the venue website for the most up-to-date hours.\n\n'

	if current_events:
		out += '## Happening now\n\n'
		for event in current_events:
			venue = venues.get(event['venue'], {})
			out += f'### {venue.get("name", "")}\n\n'
			if venue.get('website'):
				out += f'[Website]({venue.get("website")})\n\n'
			out += python_tools.shows_data.format_date_range_with_year(event['start_date'], event['end_date']) + '\n\n'
			address_block = format_venue_block(venue)
			if address_block:
				out += address_block + '\n\n'

	if upcoming_events:
		out += '## Upcoming\n\n'
		for event in upcoming_events:
			venue = venues.get(event['venue'], {})
			out += f'### {venue.get("name", "")}\n\n'
			if venue.get('website'):
				out += f'[Website]({venue.get("website")})\n\n'
			out += python_tools.shows_data.format_date_range_with_year(event['start_date'], event['end_date']) + '\n\n'
			address_block = format_venue_block(venue)
			if address_block:
				out += address_block + '\n\n'
	else:
		if not current_events:
			out += '_No upcoming shows currently scheduled._\n'

	output_path = os.path.join(docs_dir, 'upcoming-shows', 'index.md')
	write_text_file(output_path, out, dry_run)


if __name__ == '__main__':
	assert format_venue_block({'address': '500 N. Dunton Ave.', 'city': 'Arlington Heights', 'state': 'IL', 'postal_code': '60004'}) == '500 N. Dunton Ave.  \nArlington Heights, IL 60004'
