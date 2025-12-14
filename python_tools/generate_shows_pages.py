#!/usr/bin/env python3

# Standard Library
import os
import sys
import argparse
import datetime


#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed arguments.
	"""
	parser = argparse.ArgumentParser(description="Generate shows-related pages from data/shows.yml")

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
		help='Override current year for the Past Shows overview page',
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
def main():
	"""
	Run all shows-related generators (Upcoming Shows, Past Shows, and homepage next show block).
	"""
	args = parse_args()

	repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	if repo_root not in sys.path:
		sys.path.insert(0, repo_root)

	import python_tools.past_shows
	import python_tools.upcoming_shows
	import python_tools.homepage_next_show

	today = datetime.date.today()
	current_year = args.current_year
	if current_year is None:
		current_year = today.year

	python_tools.past_shows.generate_past_shows_pages(
		input_yaml=args.input_file,
		docs_dir=args.docs_dir,
		current_year=current_year,
		dry_run=args.dry_run,
		today=today,
	)

	python_tools.upcoming_shows.generate_upcoming_shows_page(
		input_yaml=args.input_file,
		docs_dir=args.docs_dir,
		dry_run=args.dry_run,
		today=today,
	)

	python_tools.homepage_next_show.update_homepage_next_show(
		input_yaml=args.input_file,
		docs_dir=args.docs_dir,
		dry_run=args.dry_run,
		today=today,
	)


if __name__ == '__main__':
	main()

