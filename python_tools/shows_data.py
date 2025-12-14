#!/usr/bin/env python3

# Standard Library
import html
import datetime

# PIP3 modules
import yaml


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
def format_date_range_legacy(start_date: datetime.date, end_date: datetime.date) -> str:
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
def format_date_range_with_year(start_date: datetime.date, end_date: datetime.date) -> str:
	"""
	Format an event range with year, for upcoming/current pages.

	Examples:
	- December 13–14, 2025
	- September 30 – October 1, 2025

	Args:
		start_date (datetime.date): Start date.
		end_date (datetime.date): End date.

	Returns:
		str: Human-friendly date range including year.
	"""
	if start_date == end_date:
		return start_date.strftime('%B ') + str(start_date.day) + ', ' + str(start_date.year)

	if start_date.year != end_date.year:
		return (
			start_date.strftime('%B ') + str(start_date.day) + ', ' + str(start_date.year)
			+ ' – '
			+ end_date.strftime('%B ') + str(end_date.day) + ', ' + str(end_date.year)
		)

	if start_date.month == end_date.month:
		return start_date.strftime('%B ') + str(start_date.day) + '–' + str(end_date.day) + ', ' + str(start_date.year)

	return (
		start_date.strftime('%B ') + str(start_date.day)
		+ ' – '
		+ end_date.strftime('%B ') + str(end_date.day)
		+ ', '
		+ str(start_date.year)
	)


if __name__ == '__main__':
	# Simple asserts for new pure functions
	assert ordinal_suffix(1) == 'st'
	assert ordinal_suffix(2) == 'nd'
	assert ordinal_suffix(3) == 'rd'
	assert ordinal_suffix(4) == 'th'
	assert format_date_range_with_year(datetime.date(2025, 12, 13), datetime.date(2025, 12, 14)) == 'December 13–14, 2025'
