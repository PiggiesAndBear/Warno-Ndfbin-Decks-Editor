"""Read-only visualizations built from a mod's ndfbin files.

Nothing in the editor imports this package — it is a set of standalone
generators (currently the deck tree) that produce one HTML file each.  Kept
inside the package so ``python -m visualization.deck_tree`` works and so the
tools travel with the code they read.
"""
