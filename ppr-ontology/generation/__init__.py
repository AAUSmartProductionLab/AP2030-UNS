"""Public entrypoints for the generation package.

This allows package-style invocation, e.g.:
	import generation
	generation.run()
"""

from .run import main


def run() -> None:
	"""Run the generation pipeline CLI entry point."""
	main()


__all__ = ["main", "run"]
