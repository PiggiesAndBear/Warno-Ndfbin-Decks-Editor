# -*- coding: utf-8 -*-
"""Readable division names, resolved from the mod's own dictionaries.

``TDeckDivisionDescriptor.DivisionName`` is a **loc_hash** (type ``29``) — the
same kind of value as a smart group's ``Name``, and the very same 8 bytes that
key the ``.dic`` dictionaries.  A division's display name is therefore a plain
table lookup, exactly like a platoon's; nothing has to be decrypted.

Two things make this worth a module rather than three lines in ``Session``:

**The dictionaries are not where the deck's are.**  :class:`~.localisation.NameResolver`
reads ``PLATOONS`` / ``COMPANIES`` / ``UNITS`` from the mod's *preferred*
namespace, because that is where platoon names live.  Division names also land
in ``UNITS``, but the namespace and family are not fixed — Berlin puts its five
readable division names in ``WarnoAGFEditorBuild…/UNITS-DEV.dic``, Northern
Thunder its 128 in ``1234/UNITS-*.dic`` — so this reader merges **every family
in every namespace** and looks the hash up once.  Measured 2026-11-03: no
``DIVISIONS`` family exists in any of the three mods; a ``DIVISIONS``-only
reader would resolve nothing.

**Most divisions will not resolve, and that is not a bug.**  A readable name
needs a dictionary the mod ships.  Vanilla divisions point at the game's own
dictionaries, which live inside ``Data/PC/<build>/Data.dat`` — an EDAT **v2**
archive whose entries are compressed, and which this project has no reader for
(``cndf_layout.parse_edat_entries`` accepts v1 only).  So 385 of Northern
Thunder's 513 divisions stay unresolved, and callers must fall back to the
export-name label (:func:`~.divisions.division_label`), which is what the
picker showed before this module existed.

Measured across three mods — Berlin 5/389, ShowCase-FPV Strike 1/386,
Northern Thunder 128/513 — **every** resolved division is one the mod author
created; vanilla ones resolve in none of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core import cndf_codec
from . import tradic

DIVISION = "TDeckDivisionDescriptor"

#: Value type of a ``loc_hash`` — see :mod:`~.localisation`.
LOC_HASH = 29

#: Language to prefer.  ``DEV`` is the author's source form, which is what a
#: division name is normally written in; the other tables are translations of
#: it, so DEV is both the most complete and the least surprising.
DEFAULT_LANG = "DEV"


@dataclass
class DivisionNames:
    """``export path -> readable name``, plus how much of the file it covered.

    ``declared`` counts the divisions that carry a ``DivisionName`` hash at
    all; ``resolved`` how many of those a dictionary covered.  The gap is the
    honest number to show — a picker that silently falls back to export names
    looks identical whether the dictionaries are 0% or 99% useful.
    """

    names: dict[str, str] = field(default_factory=dict)
    declared: int = 0
    resolved: int = 0
    #: how many ``.dic`` files were read, for the log line
    files: int = 0
    source: Path | None = None

    @property
    def has_any(self) -> bool:
        return bool(self.names)

    def resolve(self, path: str | None) -> str | None:
        """The readable name for one division export path, or ``None``.

        ``None`` means "this mod ships no dictionary for that hash", which the
        caller must treat as "use the export-name label", never as "unnamed".
        """
        if not path:
            return None
        return self.names.get(path)

    def __len__(self) -> int:
        return len(self.names)

    def summary(self) -> str:
        if not self.declared:
            return "no Division.ndfbin"
        return (f"{self.resolved}/{self.declared} divisions named "
                f"({self.resolved / self.declared * 100:.1f}%) "
                f"from {self.files} dictionaries")


def _hashes(division_bin: Path) -> dict[bytes, list[str]]:
    """``{loc_hash: [export path, ...]}`` for every division in a file.

    Keyed by the **whole** export path (``$/GFX/Division/…/X_solo``), because
    that is what ``DeckDivision`` stores.  One hash can map to several paths:
    the ``_solo`` / ``_multi`` / ``_challenge`` variants of a division are
    separate objects that carry the same name (Northern Thunder has 492
    distinct hashes across 513 divisions), so the value is a **list** — storing
    one path per hash silently drops 21 of them.
    """
    doc, info = cndf_codec.decode(division_bin.read_bytes(), str(division_bin))
    out: dict[bytes, list[str]] = {}
    for obj in info["objects"]:
        if obj["class"] != DIVISION or not obj.get("is_top_object"):
            continue
        props = {p["property_name"]: p["value"] for p in obj["properties"]}
        value = props.get("DivisionName", {})
        if value.get("type_id") != LOC_HASH or not value.get("value_hex"):
            continue
        try:
            key = bytes.fromhex(value["value_hex"])
        except ValueError:
            continue
        export = info["exports"].get(obj["id"], "")
        if export:
            out.setdefault(key, []).append(export)
    return out


def _table(mod, lang: str) -> tuple[dict[bytes, str], int]:
    """``{hash: text}`` merged over every family in every namespace.

    ``lang`` is tried first and ``DEV`` fills the gaps, matching what
    :meth:`~.localisation.NameResolver.from_mod` does for platoon names.  The
    namespace is deliberately *not* narrowed to
    :meth:`~..io.modlocator.ModPaths.localisation_namespace` — that method picks
    the mod's biggest namespace, and a division name can sit in a smaller one.
    """
    root = None
    try:
        root = mod.localisation_gen_dir()
    except Exception:                                  # noqa: BLE001
        return {}, 0
    if root is None:
        return {}, 0

    wanted = [lang] if lang == "DEV" else [lang, "DEV"]
    table: dict[bytes, str] = {}
    files = 0
    for namespace in sorted(p for p in root.iterdir() if p.is_dir()):
        for suffix in wanted:
            for dic in sorted(namespace.glob(f"*-{suffix}.dic")):
                try:
                    entries = tradic.read(dic)
                except (tradic.TradError, OSError):
                    continue
                files += 1
                for key, text in entries.items():
                    # setdefault keeps the preferred language: the DEV pass
                    # only fills what `lang` did not have.
                    table.setdefault(key, text)
    return table, files


def from_mod(mod, lang: str = DEFAULT_LANG) -> DivisionNames:
    """Build the resolver for one mod; empty when it ships nothing usable.

    Never raises: a mod with no ``Division.ndfbin``, no ``Gen/`` or a damaged
    dictionary yields an empty result, and every lookup then returns ``None``.
    """
    empty = DivisionNames()
    if mod is None:
        return empty
    try:
        binary = Path(mod.division_bin)
    except Exception:                                  # noqa: BLE001
        return empty
    if not binary.is_file():
        return empty
    try:
        hashes = _hashes(binary)
    except Exception:                                  # noqa: BLE001
        return empty
    if not hashes:
        return empty

    table, files = _table(mod, lang)
    names = {path: table[key]
             for key, paths in hashes.items() if key in table
             for path in paths}
    try:
        root = mod.localisation_gen_dir()
    except Exception:                                  # noqa: BLE001
        root = None
    return DivisionNames(names=names,
                         declared=sum(len(p) for p in hashes.values()),
                         resolved=len(names), files=files, source=root)
