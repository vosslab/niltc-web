#!/usr/bin/env python3

# Standard Library
import os
import re
import datetime

# local repo modules
import python_tools.shows_data


#============================================
def pick_next_event(events: list, today: datetime.date) -> tuple:
	"""
	Pick the next relevant event (current preferred, otherwise next upcoming).

	Args:
		events (list): List of event dicts.
		today (datetime.date): Today's date.

	Returns:
		tuple: (event, status) or (None, '') if none.
	"""
	current_events = []
	upcoming_events = []
	for event in events:
		status = python_tools.shows_data.classify_event(event['start_date'], event['end_date'], today)
		if status == 'current':
			current_events.append(event)
		elif status == 'upcoming':
			upcoming_events.append(event)

	if current_events:
		current_events = sorted(current_events, key=lambda e: (e['start_date'], e['id']))
		return (current_events[0], 'current')

	if upcoming_events:
		upcoming_events = sorted(upcoming_events, key=lambda e: (e['start_date'], e['id']))
		return (upcoming_events[0], 'upcoming')

	return (None, '')


#============================================
def format_city_state_zip(venue: dict) -> str:
	"""
	Format city/state/postal line.

	Args:
		venue (dict): Venue dict.

	Returns:
		str: One line, or ''.
	"""
	city = str(venue.get('city', '')).strip()
	state = str(venue.get('state', '')).strip()
	postal_code = str(venue.get('postal_code', '')).strip()

	out = ''
	if city:
		out += city
	if state:
		if out:
			out += ', '
		out += state
	if postal_code:
		if out:
			out += ' '
		out += postal_code

	return out


#============================================
def render_next_show_block(event: dict, status: str, venue: dict) -> list:
	"""
	Render the homepage "next show" block as lines (without indentation).

	Args:
		event (dict): Event dict.
		status (str): Event status classification (current/upcoming).
		venue (dict): Venue dict.

	Returns:
		list: List of markdown lines.
	"""
	name = str(venue.get('name', '')).strip()
	website = str(venue.get('website', '')).strip()

	lines = []
	if not event or not name:
		lines.append('No upcoming shows are currently scheduled.')
		lines.append('')
		lines.append('Past events: see [Past Shows](past-shows/index.md).')
		return lines

	if status == 'current':
		lines.append(f'We are currently at **{name}**.')
	else:
		lines.append(f'Our next show is at **{name}**.')

	lines.append('')
	lines.append(python_tools.shows_data.format_date_range_with_year(event['start_date'], event['end_date']))
	lines.append('')

	address = str(venue.get('address', '')).strip()
	if address:
		lines.append(address + '  ')
	csz = format_city_state_zip(venue)
	if csz:
		lines.append(csz)
	if address or csz:
		lines.append('')

	if website:
		lines.append(f'[Website]({website})')
		lines.append('')

	lines.append('More dates: see [Upcoming Shows](upcoming-shows/index.md).  ')
	lines.append('Past events: see [Past Shows](past-shows/index.md).')

	return lines


#============================================
def replace_between_markers(text: str, marker_name: str, replacement_lines: list) -> str:
	"""
	Replace the content between marker comments, preserving indentation.

	Markers must be present as:
	<!-- <marker_name>:BEGIN -->
	<!-- <marker_name>:END -->

	Args:
		text (str): Input text.
		marker_name (str): Marker base name.
		replacement_lines (list): New content lines (no indentation).

	Returns:
		str: Updated text.
	"""
	begin_marker = f'<!-- {marker_name}:BEGIN -->'
	end_marker = f'<!-- {marker_name}:END -->'

	begin_idx = text.find(begin_marker)
	end_idx = text.find(end_marker)
	if begin_idx < 0 or end_idx < 0 or end_idx <= begin_idx:
		raise ValueError(f'Missing markers: {marker_name}')

	begin_line_start = text.rfind('\n', 0, begin_idx) + 1
	begin_line_end = text.find('\n', begin_idx)
	if begin_line_end < 0:
		raise ValueError(f'Invalid marker line: {marker_name}')

	end_line_start = text.rfind('\n', 0, end_idx) + 1

	indent_match = re.match(r'^[ \t]*', text[begin_line_start:begin_idx])
	indent = ''
	if indent_match:
		indent = indent_match.group(0)

	inner = ''
	for line in replacement_lines:
		if line == '':
			inner += '\n'
		else:
			inner += indent + line + '\n'

	return text[:begin_line_end + 1] + inner + text[end_line_start:]


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
def update_homepage_next_show(input_yaml: str, docs_dir: str, dry_run: bool, today=None):
	"""
	Update mkdocs/docs/index.md next show block from data/shows.yml.

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

	next_event, status = pick_next_event(events, today)
	venue = {}
	if next_event:
		venue = venues.get(next_event['venue'], {})

	block_lines = render_next_show_block(next_event, status, venue)

	index_path = os.path.join(docs_dir, 'index.md')
	with open(index_path, 'r', encoding='utf-8') as f:
		text = f.read()

	updated = replace_between_markers(text, 'SHOWS_NEXT', block_lines)
	write_text_file(index_path, updated, dry_run)


if __name__ == '__main__':
	# Simple asserts for new pure functions
	assert format_city_state_zip({'city': 'Arlington Heights', 'state': 'IL', 'postal_code': '60004'}) == 'Arlington Heights, IL 60004'
	e = {'id': '2025-12-ahml', 'venue': 'ahml', 'start_date': datetime.date(2025, 12, 13), 'end_date': datetime.date(2025, 12, 14), 'status': 'confirmed', 'pictures': []}
	ev, st = pick_next_event([e], datetime.date(2025, 12, 14))
	assert st == 'current'
