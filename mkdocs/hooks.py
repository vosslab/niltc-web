#!/usr/bin/env python3

# Standard Library
import os
import sys
import datetime


#============================================
def on_pre_build(config, **kwargs):
	"""
	MkDocs hook: generate shows-related pages from YAML before building.
	"""
	repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
	if repo_root not in sys.path:
		sys.path.insert(0, repo_root)

	import python_tools.past_shows
	import python_tools.upcoming_shows
	import python_tools.homepage_next_show
	import python_tools.news_enrich
	import python_tools.news_render

	input_yaml = os.path.join(repo_root, 'data', 'shows.yml')
	today = datetime.date.today()
	current_year = today.year

	python_tools.past_shows.generate_past_shows_pages(
		input_yaml=input_yaml,
		docs_dir=config.docs_dir,
		current_year=current_year,
		dry_run=False,
		today=today,
	)

	python_tools.upcoming_shows.generate_upcoming_shows_page(
		input_yaml=input_yaml,
		docs_dir=config.docs_dir,
		dry_run=False,
		today=today,
	)

	python_tools.homepage_next_show.update_homepage_next_show(
		input_yaml=input_yaml,
		docs_dir=config.docs_dir,
		dry_run=False,
		today=today,
	)

	# In the News (optional enrichment to avoid network calls in local dev)
	news_csv = os.path.join(repo_root, 'data', 'in_the_news.csv')
	news_yaml = os.path.join(repo_root, 'data', 'in_the_news.yml')
	news_review = os.path.join(repo_root, 'data', 'in_the_news_needs_review.csv')
	news_snapshot = os.path.join(repo_root, 'data', 'in_the_news_needs_snapshot.csv')

	news_enrich_enabled = False
	if hasattr(config, 'extra') and isinstance(config.extra, dict):
		news_enrich_enabled = bool(config.extra.get('news_enrich', False))

	if news_enrich_enabled:
		python_tools.news_enrich.enrich_news(
			input_csv=news_csv,
			output_yaml=news_yaml,
			review_csv=news_review,
			snapshot_csv=news_snapshot,
			sleep_max=1.0,
			timeout=20.0,
			max_items=None,
		)

	data = python_tools.news_render.read_yaml_file(news_yaml)
	content = python_tools.news_render.render_in_the_news_page(data)
	output_path = os.path.join(config.docs_dir, 'in-the-news', 'index.md')
	python_tools.news_render.write_text_file_if_changed(output_path, content)
