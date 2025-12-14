#!/usr/bin/env python3
# Moved from python-tools/ to python_tools/

# Standard Library
import os
import sys

#============================================
def main():
	"""
	Run the Past Shows generator.
	"""
	repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	if repo_root not in sys.path:
		sys.path.insert(0, repo_root)

	# local repo modules
	import python_tools.past_shows

	python_tools.past_shows.main()


if __name__ == '__main__':
	main()
