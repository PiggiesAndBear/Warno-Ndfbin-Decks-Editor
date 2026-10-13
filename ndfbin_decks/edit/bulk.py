"""Batch equipment replace over a chosen slice of the organisation.

A single swap re-points one slot.  A *replace* answers a different question —
"this division fields 40 T-72M1 across six battalions; make them all T-72B" —
and it needs the blast radius up front, because the answer is a rewrite of
dozens of decks at once.

**The scope is an explicit choice, never an accident.**  Widening from one
platoon to a whole division is the entire point of the feature, so the caller
must name the level; there is no "apply to everything" fallback that a slip of
the mouse could reach.

**The operation is deliberately conservative.**  It only changes *which pack a
window points at* — never the count, never the window order, never a company's
membership.  Because the relayout is re-emitted from the substituted packs,
``Σ(Number) == len(DeckPackList)`` still holds by construction, so a replace
cannot make a deck non-canonical and needs no re-tiling or re-validation dance
of its own.  That is what makes it safe to run across a whole division.

Scope levels mirror the organisation the UI shows:

===========  =============================================
``platoon``  one platoon (排) of one company of one battalion
``company``  every platoon of one company (连)
``battalion`` every company of one battalion (营)
``division`` every battalion of one division (师)
``country``  every battalion of every division of one 国家
===========  =============================================

The country level is derived, not stored: no deck in the file records a
country, so :func:`~ndfbin_decks.io.divisions.country_code` reads it off the
division label.  That is enough for a replace, which only ever asks "is this
window inside my slice".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.deckmodel import DeckFile
from ..edit.equip import DeckEditor, PackKey
from ..edit.quantity import Retiler
from ..io.divisions import country_code

#: Widest first — the UI shows them in this order so the user reads the scope
#: as a widening, not a list of unrelated buttons.
LEVELS = ("platoon", "company", "battalion", "division", "country")

LEVEL_LABELS = {
    "platoon": "本排 Pl",
    "company": "本连 Co",
    "battalion": "本营 Bn",
    "division": "本师 Div",
    "country": "本国 Nat",
}


@dataclass(frozen=True)
class Scope:
    """A slice of the organisation, named by level."""

    kind: str
    #: ``$/GFX/Division/...`` when ``kind == "division"``
    division: str | None = None
    #: country code when ``kind == "country"``, and also carried on the narrower
    #: levels so the UI can widen a selection to the country it sits in
    country: str | None = None
    deck_id: int | None = None
    ci: int | None = None
    si: int | None = None

    def contains(self, division: str | None, deck_id: int,
                 ci: int, si: int) -> bool:
        if self.kind == "country":
            # Derived from the label, exactly as the picker derived it, so the
            # two can never disagree about which divisions are Soviet.
            return bool(self.country) and country_code(division) == self.country
        if self.kind == "division":
            return division == self.division
        if deck_id != self.deck_id:
            return False
        if self.kind == "battalion":
            return True
        if ci != self.ci:
            return False
        if self.kind == "company":
            return True
        return si == self.si

    def label(self) -> str:
        return LEVEL_LABELS.get(self.kind, self.kind)


@dataclass
class ReplaceSurvey:
    """The blast radius, computed before anything is written."""

    decks: set[int] = field(default_factory=set)
    companies: int = 0
    platoons: int = 0
    entries: int = 0
    #: sum of the counts of the affected windows — how many in-game units move
    units: int = 0

    def summary(self) -> str:
        if not self.entries:
            return "范围内没有用到该装备"
        return (f"{len(self.decks)} 个营 · {self.companies} 个连 · "
                f"{self.platoons} 个排 · {self.entries} 条装备 · "
                f"{self.units} 件单位")


@dataclass
class ReplaceResult:
    ok: bool = False
    note: str = ""
    survey: ReplaceSurvey = field(default_factory=ReplaceSurvey)
    #: pack object id every affected window now points at
    to_pack_id: int | None = None
    #: ``True`` when an existing pack was reused rather than created
    reused: bool = True
    created_pack_id: int | None = None
    decks: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.ok:
            return self.note or "未执行"
        bits = [f"{self.survey.entries} 条装备 → pack#{self.to_pack_id}"]
        bits.append("复用既有装备包" if self.reused
                    else f"新建 pack#{self.created_pack_id}")
        bits.append(f"（{len(self.decks)} 个营）")
        return "，".join(bits)


class ScopedReplace:
    """Swap one pack for another across a :class:`Scope`.

    Reads the live graph on every call, so a survey taken before an unrelated
    edit and an apply after it cannot disagree.
    """

    def __init__(self, deck: DeckFile, packs: DeckEditor, retiler: Retiler,
                 scope: Scope, from_pack_id: int):
        self.deck = deck
        self.packs = packs
        self.retiler = retiler
        self.scope = scope
        self.from_pack_id = from_pack_id

    # -- reading -----------------------------------------------------------

    def _division_of(self, deck_id: int) -> str | None:
        obj = self.deck._by_id.get(deck_id)
        if obj is None:
            return None
        props = {p["property_name"]: p["value"] for p in obj["properties"]}
        return self.deck._str(props, "DeckDivision") or None

    def _windows(self):
        """``(division, deck_id, ci, si, ei, pack_id, count)`` for every AG window.

        Skips skirmish decks: a replace is an Army General operation, and the
        PvP decks share the file but never a pack with AG.
        """
        from ..io import agfilter
        for o in self.deck.info["objects"]:
            if o["class"] != "TDeckDescriptor":
                continue
            props = {p["property_name"]: p["value"] for p in o["properties"]}
            if not agfilter.is_ag_pawn_deck(props):
                continue
            did = o["id"]
            division = self.deck._str(props, "DeckDivision") or None
            pool = [it.get("object_id") for it in
                    props.get("DeckPackList", {}).get("items", []) or []]
            for ci, cgref in enumerate(
                    props.get("DeckCombatGroupList", {}).get("items", []) or []):
                cg = self.deck._by_id.get(cgref.get("object_id"))
                if cg is None:
                    continue
                cg_props = self.deck._props(cg)
                for si, sgref in enumerate(
                        cg_props.get("SmartGroupList", {}).get("items", []) or []):
                    sg = self.deck._by_id.get(sgref.get("object_id"))
                    if sg is None:
                        continue
                    sg_props = self.deck._props(sg)
                    for ei, tup in enumerate(
                            sg_props.get("PackIndexUnitNumberList", {})
                            .get("items", []) or []):
                        idx = tup.get("key", {}).get("value")
                        count = tup.get("value", {}).get("value") or 0
                        if idx is None or not (0 <= idx < len(pool)):
                            continue
                        yield (division, did, ci, si, ei, pool[idx], count)

    def _in_scope(self):
        """``(deck_id, ci, si, ei, pack_id, count)`` for windows in scope."""
        for division, did, ci, si, ei, pack_id, count in self._windows():
            if not self.scope.contains(division, did, ci, si):
                continue
            if pack_id != self.from_pack_id:
                continue
            yield did, ci, si, ei, pack_id, count

    # -- planning ----------------------------------------------------------

    def usage(self, limit: int = 400) -> list[tuple[int, int, int]]:
        """``(pack_id, entries, units)`` for every pack the scope fields.

        This is the "which equipment do you want to replace" list.  Sorted by
        how much the scope uses it, because the pack a modder is hunting for is
        almost always one of the heavily used ones.
        """
        tally: dict[int, list[int]] = {}
        for did, ci, si, _ei, pid, count in self._in_scope_all():
            row = tally.setdefault(pid, [0, 0])
            row[0] += 1
            row[1] += count
        rows = [(pid, e, u) for pid, (e, u) in tally.items()]
        rows.sort(key=lambda r: (-r[1], -r[2], r[0]))
        return rows[:limit]

    def _in_scope_all(self):
        """Every in-scope window, regardless of which pack it uses."""
        for division, did, ci, si, ei, pack_id, count in self._windows():
            if self.scope.contains(division, did, ci, si):
                yield did, ci, si, ei, pack_id, count

    def survey(self) -> ReplaceSurvey:
        """What an apply would touch.  Cheap enough to call on every keystroke."""
        out = ReplaceSurvey()
        companies: set[tuple] = set()
        platoons: set[tuple] = set()
        for did, ci, si, _ei, _pid, count in self._in_scope():
            out.decks.add(did)
            companies.add((did, ci))
            platoons.add((did, ci, si))
            out.entries += 1
            out.units += count
        out.companies = len(companies)
        out.platoons = len(platoons)
        return out

    # -- writing -----------------------------------------------------------

    def apply(self, to_key: PackKey) -> ReplaceResult:
        """Repoint every in-scope window at a pack offering ``to_key``."""
        res = ReplaceResult()
        res.survey = self.survey()
        if not res.survey.entries:
            res.note = "范围内没有用到该装备，无需替换"
            return res

        to_pack_id, reused = self.packs.ensure_pack(to_key)
        if to_pack_id < 0:
            res.note = "无法创建目标装备包"
            return res
        res.to_pack_id, res.reused = to_pack_id, reused
        if not reused:
            res.created_pack_id = to_pack_id

        if to_pack_id == self.from_pack_id:
            res.note = "目标与来源相同"
            return res

        # Grouped per deck: the relayout is a whole-deck operation, so one
        # relay per affected battalion is both correct and the minimum work.
        per_deck: dict[int, dict[tuple[int, int, int], int]] = {}
        for did, ci, si, ei, _pid, _count in self._in_scope():
            per_deck.setdefault(did, {})[(ci, si, ei)] = to_pack_id

        for did, edits in per_deck.items():
            out = self.retiler.relay(did, pack_edits=edits)
            if not out.ok:
                res.note = f"{self.retiler._deck_name(did)}: {out.note}"
                return res
            res.decks.append(self.retiler._deck_name(did))

        # The relayout changed pools and pair lists; every derived view (the
        # battalion tree, the catalogue's usage counts) must be rebuilt.
        self.deck.invalidate()
        res.ok = True
        return res
