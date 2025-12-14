#!/usr/bin/env python3

# Standard Library
import os
import sys
import datetime


#============================================
def on_pre_build(config, **kwargs):
	"""
	MkDocs hook: generate Past Shows pages from YAML before building.
	"""
	repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
	if repo_root not in sys.path:
		sys.path.insert(0, repo_root)

	import python_tools.past_shows

	input_yaml = os.path.join(repo_root, 'data', 'shows.yml')
	current_year = datetime.date.today().year

	python_tools.past_shows.generate_past_shows_pages(
		input_yaml=input_yaml,
		docs_dir=config.docs_dir,
		current_year=current_year,
		dry_run=False,
	)
