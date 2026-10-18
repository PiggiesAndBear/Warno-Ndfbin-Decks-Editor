# Warno Ndfbin Decks Editor

**Play Any Unit In Any Mod.**

A desktop editor for WARNO **Army General** deck binaries (`Deck.ndfbin`). Point
it at a mod, walk down 师 Div → 营 Bn → 连 Co → 排 Pl, and change what a
battalion actually fields — without touching the mod's source tree and without
recompiling anything.

[中文说明](README.zh-CN.md) · [User manual (中文)](doc/使用教程.md)

![icon](assets/icon-256.png)

---

## Why this exists

Deck data lives in a compiled binary. The usual workflow to change one item is:
edit the mod's NDF sources, rebuild the whole mod in ModGen, redeploy it, launch
the game, and find out whether it worked. Doing that to answer "what if this
battalion had T-80s instead?" is absurd.

This tool reads and writes that binary directly.

## What it does

| | |
|---|---|
| **Change quantities** | 4 tanks → 6 tanks, and the rest of the battalion's slot layout is re-laid automatically |
| **Swap equipment** | Pick from what the mod already has, or build a combination it does not |
| **Insert / remove entries** | Add another equipment line to a platoon, or drop one |
| **Batch replace** | Swap one piece of equipment — or **merge several kinds into one** — across a 排 / 连 / 营 / 师 / whole **country**, with the blast radius shown before anything is written |
| **Variants** | Give an entry a different transport, or pin its experience level |
| **Filters** | Country → division → battalion, all type-to-search |
| **Interface language** | 简体中文 / English, switched live — no restart, and unsaved edits survive |

Safety is not bolted on:

* **The file is validated before every save.** Structural problems abort the
  write; the file is not touched.
* **A `.bak` is written** next to the original when overwriting it.
* **Edits are entry-scoped, not slot-scoped**, so a half-converted entry cannot
  be produced (see [the slot model](#the-slot-model) below).

## What it does *not* do

* No editing of the 师 / 营 / 连 / 排 structure itself — only what is inside a
  platoon.
* No renaming (that is localisation data).
* No unit stats or weapon values (different files).
* **No cross-mod equipment.** See [the rule](#why-cross-mod-is-forbidden) — this
  one matters.

## Install

**Download the EXE** from the [Releases](../../releases) page and run it. Windows
will warn you that the publisher is unknown: the binary is unsigned, so
SmartScreen has nothing to check it against. `More info` → `Run anyway`.

**Or run from source** (Python 3.10+):

```bat
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

The editor finds mods in two places on its own:

| Where | What |
|---|---|
| `Saved Games\EugenSystems\WARNO\mod\<name>\` | mods built and deployed locally |
| `<steamapps>\workshop\content\1611600\<id>\` | Steam Workshop subscriptions |

Steam libraries are located through `libraryfolders.vdf`, not by guessing, so an
install on a second drive is found. If a mod still does not appear — an
extracted archive, a USB stick, a second Windows account — the **打开 mod
文件夹** button takes any directory and scans it.

## Quick start

1. Pick a mod.
2. Pick a country, then a division; or just type into the division box.
3. Find the platoon in the tree on the left.
4. Click a row in the table on the right (one row = one equipment entry).
5. Use the buttons: **改件数** / **换装备** / **插入条目** / **删除条目**.
   Double-clicking a row jumps straight to the equipment picker.
6. **保存**. Restart the game and check.

Full walkthrough, screenshots of every dialog and a troubleshooting chapter:
[`doc/使用教程.md`](doc/使用教程.md) (Chinese).

---

## How it works

### The container

A `.ndfbin` is an `EUG0`/`CNDF` container: a section table (`CLAS`, `PROP`,
`STRG`, `EXPR`, `TRAN`, `CHNK`, `TOPO`, `IMPR`, `OBJE`), a zstandard-compressed
object graph, and an import table holding the string paths objects refer to.

`ndfbin_decks/core/cndf_codec.py` decodes and re-encodes it losslessly — the
self-check asserts a decode→encode round trip is **byte-identical** for every
file it is given. That property is what makes everything else trustworthy: if
re-emitting an untouched file changes a single byte, no edit can be trusted.

Writing a reference to a path that is not yet in the import table means growing
that table, which is where `IMPR` and `TRAN` are rebuilt.

### The slot model

This is the one concept worth understanding, and it is the source of the
project's sharpest bug.

A deck does not store "one equipment per slot". It stores **entries**, and an
entry owns a run of consecutive slots that must all hold the same thing:

```
Co0 / Pl0 / entry #1   says 3   ->  slots 0, 1, 2
Co0 / Pl0 / entry #2   says 2   ->  slots 3, 4
Co0 / Pl1 / entry #1   says 1   ->  slot  5
```

An earlier version of this tool let you rewrite a single slot. On a real file
that produced `[T72_CMD_SOV, BM27, BM27]` inside a 3-slot entry — a **mixed
entry**, which is illegal. Worse, the next edit would collapse that entry onto
its first slot and silently delete the other two.

So:

* **Editing is entry-scoped.** The pool is re-emitted from each entry's own
  data, which makes a half-converted entry *unrepresentable* rather than merely
  rejected.
* **The validator reports a mixed entry as a hard error**, and the re-tiler
  refuses to re-lay one instead of guessing which of the two equipment types was
  meant.
* **Changing a quantity re-lays the rest of the battalion**, because the slots
  are contiguous — that is not a side effect, it is the invariant.

### Army General vs PvP

One `Deck.ndfbin` holds both AG and skirmish/PvP decks. Measured on a reference
file: AG references 2690 pack objects, PvP references 2483, and the two sets
overlap by **zero**. They are separate populations with incompatible structure,
so mixing them breaks the game.

Hence the roster is built from *"has an Army General deck fielded this?"*, not
from *"is this pack in the file"*. The obvious-looking alternative — "does it
have an experience level defined?" — was tried and rejected: it wrongly excludes
311 AG-legal packs, because omitting the experience is a legitimate way to say
*inherit the division's*.

### Why cross-mod is forbidden

If an AG deck references a unit that the mod being loaded does not define, the
game **does not error**. It renders an empty unit. The failure is silent and
almost impossible to diagnose from in-game behaviour.

So the picker's existing-equipment list only ever contains packs from the file
being edited, and a hand-typed name is checked against the mod's own definition
files before it is accepted. The type used to address a pack is `(unit,
transporter, experience, number)`; a combination that does not exist gets a new
pack object appended, which is how "build a combination the mod does not have"
works while staying inside the mod.

### Where equipment definitions come from

A unit list built only from what a file *references* misses most of the game. The
real sources, in order of authority:

| Source | Form |
|---|---|
| `<WARNO>/Mods/ModData/base.zip` | UniteDescriptor.ndf — the vanilla baseline, ~2898 units |
| `<mod>/GameData/.../UniteDescriptor.ndf` | a mod's source tree, local mods only |
| `<mod>/Gen/NDF/GFX/Unit.ndfbin` | compiled — the only form a Workshop mod ships |

`base.zip` is ModGen's own copy and is refreshed with game patches, which is why
it is preferred over a mod's own stale snapshot. Reading a `Unit.ndfbin` used to
cost 2.0 s (56223 objects); the export table alone answers the question, so
`cndf_codec.read_exports()` does that instead — **0.028 s**, verified equal to a
full decode.

---

## Project layout

```
main.py                     single entry point (frozen EXE and source runs alike)
build_exe.py                builds the one-file EXE into build_<ver>/dist_<ver>/
verify_exe.py               smoke-tests a built EXE before it may be released
run_editor.py               thin shim so 启动编辑器.bat keeps working
assets/make_icon.py         builds app.ico from any image (multi-size, DIB entries)

ndfbin_decks/
  paths.py                  where files live: in a bundle vs in a source checkout
  core/
    cndf_codec.py           .ndfbin container: decode / encode / grow imports
    cndf_layout.py          section-table (TOPO/CHNK) walk
    deckmodel.py            the deck graph: decks, companies, platoons, entries
    validator.py            W1-W4 invariants, run before every save
    differ.py               what changed between two files
  io/
    modlocator.py           discovers mods: Saved Games, Workshop, any folder
    agfilter.py             Army General vs PvP classification
    unit_universe.py        every unit a mod can field, with provenance
    divisions.py            division label -> country (RDA is East Germany)
    localisation.py         display names from a mod's dictionaries
    tradic.py               .dic dictionary reader
  edit/
    equip.py                the pack pool, and entry-scoped swapping
    quantity.py             the re-tiler: the only place slot layout is produced
    structure.py            insert / remove entries
    bulk.py                 scoped batch replace with a blast-radius survey
  app/
    session.py              one open file and the editors bound to it
    gui.py                  the window
    swap_dialog.py          equipment picker / combination builder
    replace_dialog.py       batch replace
    catalog.py              the pickable-equipment catalogue
  selfcheck.py              byte-level round trip over every file given to it

tests/                      acceptance tests, one per guarantee
doc/使用教程.md              user manual (Chinese, no programming assumed)
```

## Tests

```bat
.venv\Scripts\python -m tests.test_model
.venv\Scripts\python -m ndfbin_decks.selfcheck
```

Every test prints a final `PASS` / `FAIL` line. The suite runs against **real
WARNO files**, so it needs the game installed and a few mods deployed:

| Mod | Used for |
|---|---|
| `Test` | the main dataset |
| `WarnoAGF_berlin_1989` | a mod with a real mixed-entry defect, used as a regression case |
| `Northern Thunder` (Workshop `3816950018`) | adds a third dataset where it is present |

Nothing is hard-coded: locations are discovered through the same
`modlocator` the editor uses, and a test whose data is missing prints
`SKIP — …` and exits 0 rather than raising. A missing game reads as a skip, not
as "this project is broken".

`tests/test_release.py` guards the release invariants — that the version has one
source, that the icon is in a format PyInstaller will accept, that the window
title is the taskbar tagline, and that the build script cannot delete the
published binary.

## Building a release

```bat
py -3 -m venv .venv-build
.venv-build\Scripts\pip install -r requirements.txt -r requirements-build.txt
.venv-build\Scripts\python build_exe.py        # -> dist_<ver>/Warno Ndfbin Decks Editor v<ver>.exe
.venv-build\Scripts\python verify_exe.py       # launches it headless, asserts, kills it
```

Build, verify and publish are three separate steps on purpose. The build writes
only to `build_<ver>/` and `dist_<ver>/` and **never touches `dist/`**, so a
failed build cannot destroy the last good release. `verify_exe.py` launches the
candidate in a throwaway directory, asserts that it started, resolved its whole
module graph, reported the expected version and left no errors — then measures
the native window title and reads the icon back out of the PE. Only then is
promoting it to `dist/` a one-line copy.

Measured on the v0.5 build: **1.6 s** warm start, twice — the same as v0.4, so
adding a hand-painted palette costs nothing measurable.  Almost all of it is the
one-file bundle unpacking itself, and a first launch of a freshly copied binary
is 4.1 s because Defender scans a file it has not seen before.  That is why the number is worth taking twice before believing
it.

## Notes and limitations

* The icon is derived from a photograph that is **not** part of this repository.
  `assets/make_icon.py` regenerates `app.ico` from any image.
* Windows-only in practice: the mod discovery and the icon/version resources are
  Windows-specific. The binary format code has no Windows dependency.
* The build is **unsigned**, so SmartScreen will warn on first run.
* PvP / skirmish decks are deliberately left alone.
* Not affiliated with Eugen Systems. WARNO and its file formats are theirs.

## License

[Apache License 2.0](LICENSE).
