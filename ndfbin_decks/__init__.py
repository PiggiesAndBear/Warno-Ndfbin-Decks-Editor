"""Read and edit WARNO Army General deck binaries (``Deck.ndfbin``)."""

#: Single source of truth for the release number.  ``build_exe.py`` greps this
#: line to name the artefact and ``main.py`` logs it at startup, so the file
#: name, the version resource and the runtime report cannot disagree.
__version__ = "0.7"

#: The product, as it appears on the EXE, in its Properties dialog and in the
#: log header.
APP_NAME = "Warno Ndfbin Decks Editor"

#: What the taskbar shows when the pointer rests on this window's button.
#:
#: Windows renders the *window title* there, so this is what the title is set
#: to.  The product name stays visible where an identity actually has to be —
#: the file name, its Properties sheet and Task Manager — rather than being
#: repeated in every window.
APP_TAGLINE = "Play Any Unit In Any Mod"
