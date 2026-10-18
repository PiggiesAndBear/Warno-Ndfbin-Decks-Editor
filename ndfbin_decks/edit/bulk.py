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

**Several sources may fold into one target.**  "Make every T-72M, T-72M1 and
T-72B in this division a T-72B" is one question, not three, and answering it in
three passes would re-tile the same battalions three times.  The set of sources
is therefore the input; :meth:`ScopedReplace.apply` groups the edits per deck
exactly as it already did, so widening from one source to many changes one
predicate and no other line of the write path.

**The target is never one of its own sources.**  Selecting three sources and
then picking one of them as the target means "fold the *others* into this one",
so the target is dropped from the set and the exclusion is reported rather than
silently turning the whole request into a no-op.

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

from collections.abc import Iterable
from dataclasses import dataclass, field

from ..core.deckmodel import DeckFile
from ..edit.equip import DeckEditor, PackKey
from ..edit.quantity import Retiler
from ..io.divisions import country_code
from ..i18n import live, tr

#: Widest first — the UI shows them in this order so the user reads the scope
#: as a widening, not a list of unrelated buttons.
LEVELS = ("platoon", "company", "battalion", "division", "country")

LEVEL_LABELS = live(globals(), "LEVEL_LABELS", lambda: {
    "platoon": tr("本排 Pl"),
    "company": tr("本连 Co"),
    "battalion": tr("本营 Bn"),
    "division": tr("本师 Div"),
    "country": tr("本国 Nat"),
})


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
    #: how many distinct source packs were actually hit
    sources: int = 0

    def summary(self) -> str:
        if not self.entries:
            return tr("范围内没有用到该装备")
        head = (tr("{sources} 种装备", sources=self.sources) if self.sources > 1 else "")
        return ((head + " · " if head else "")
                + tr("{v0} 个营 · {companies} 个连 · {platoons} 个排 · {entries} 条装备 · {units} 件单位",
                    v0=len(self.decks),
                    companies=self.companies,
                    platoons=self.platoons,
                    entries=self.entries,
                    units=self.units,
                ))


@dataclass
class ReplaceRow:
    """One source→target pair, as the dialog showed it.

    Keyed by *content* (:class:`~.equip.PackKey`) rather than by pack object id:
    a file routinely carries several pack objects with the same signature, and
    a row stands for the equipment, not for one of its objects.
    """

    source_key: PackKey | None = None
    target_key: PackKey | None = None
    #: every pack object the source resolved to in scope
    source_ids: list[int] = field(default_factory=list)
    target_id: int = -1
    reused: bool = True
    entries: int = 0
    units: int = 0
    note: str = ""

    def describe(self) -> str:
        src = self.source_key.label() if self.source_key else "?"
        dst = self.target_key.label() if self.target_key else "?"
        return f"{src} → {dst}"


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
    #: the target was also selected as a source, so it was dropped from the set
    target_also_a_source: bool = False
    #: how many source packs actually moved something
    sources: int = 0
    #: one entry per pair, in the order the caller gave them
    rows: list[ReplaceRow] = field(default_factory=list)

    def summary(self) -> str:
        if not self.ok:
            return self.note or tr("未执行")
        if len(self.rows) > 1:
            created = len({r.target_id for r in self.rows if not r.reused})
            bits = [tr("{v1} 组装备 · {entries} 条 · {units} 件单位",
                       v1=len(self.rows),
                       entries=self.survey.entries,
                       units=self.survey.units),
                    tr("（{v0} 个营）", v0=len(self.decks))]
            if created:
                bits.append(tr("新建 {v0} 个 pack", v0=created))
            return "，".join(bits)
        bits = [tr("{entries} 条装备 → pack#{to_pack_id}",
            entries=self.survey.entries,
            to_pack_id=self.to_pack_id,
        )]
        if self.sources > 1:
            bits.insert(0, tr("{sources} 种来源", sources=self.sources))
        bits.append(tr("复用既有装备包") if self.reused
                    else tr("新建 pack#{created_pack_id}", created_pack_id=self.created_pack_id))
        bits.append(tr("（{v0} 个营）", v0=len(self.decks)))
        if self.target_also_a_source:
            bits.append(tr("目标本身也是来源，已从来源中剔除"))
        return "，".join(bits)


class ScopedReplace:
    """Swap one pack for another across a :class:`Scope`.

    Reads the live graph on every call, so a survey taken before an unrelated
    edit and an apply after it cannot disagree.
    """

    def __init__(self, deck: DeckFile, packs: DeckEditor, retiler: Retiler,
                 scope: Scope, from_packs: int | Iterable[int] = -1):
        self.deck = deck
        self.packs = packs
        self.retiler = retiler
        self.scope = scope
        # Normalised once, here, so nothing downstream has to ask whether it
        # was handed one id or several.  A bare ``-1`` means "no filter", which
        # is how the picker asks for the list of everything the scope fields.
        self.from_pack_ids: frozenset[int] = (
            frozenset({from_packs}) if isinstance(from_packs, int)
            else frozenset(from_packs))

    @property
    def from_pack_id(self) -> int | None:
        """The single source, when there is exactly one.

        Kept for the callers that replace one pack; ``None`` when this executor
        was built for several, so a caller cannot quietly take the first one
        and believe it replaced the lot.
        """
        if len(self.from_pack_ids) == 1:
            return next(iter(self.from_pack_ids))
        return None

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

    def _in_scope(self, sources: frozenset[int] | None = None):
        """``(deck_id, ci, si, ei, pack_id, count)`` for windows in scope.

        ``sources`` overrides which packs count as a source — :meth:`apply`
        passes the set with the target removed, so a survey taken after the
        target is known describes exactly what will move.
        """
        wanted = self.from_pack_ids if sources is None else sources
        if not wanted:
            return
        for division, did, ci, si, ei, pack_id, count in self._windows():
            if not self.scope.contains(division, did, ci, si):
                continue
            if pack_id not in wanted:
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

    def survey(self, sources: Iterable[int] | None = None) -> ReplaceSurvey:
        """What an apply would touch.  Cheap enough to call on every keystroke."""
        wanted = (self.from_pack_ids if sources is None
                  else frozenset(sources))
        out = ReplaceSurvey()
        companies: set[tuple] = set()
        platoons: set[tuple] = set()
        hit: set[int] = set()
        for did, ci, si, _ei, pid, count in self._in_scope(wanted):
            out.decks.add(did)
            companies.add((did, ci))
            platoons.add((did, ci, si))
            hit.add(pid)
            out.entries += 1
            out.units += count
        out.companies = len(companies)
        out.platoons = len(platoons)
        out.sources = len(hit)
        return out

    # -- writing -----------------------------------------------------------

    def usage_by_key(self) -> dict:
        """``{content key: (entries, units)}`` for what the scope fields."""
        out: dict = {}
        for _did, _ci, _si, _ei, pid, count in self._in_scope_all():
            key = self.packs.pack_key(pid)
            if key is None:
                continue
            row = out.setdefault(key, [0, 0])
            row[0] += 1
            row[1] += count
        return {k: (v[0], v[1]) for k, v in out.items()}

    def _mixed_decks(self, deck_ids: set[int]) -> list[str]:
        """Decks in *deck_ids* whose windows mix packs (W3), by name.

        ``Retiler.relay`` refuses such a window, and it must: re-laying it would
        collapse the window onto its first pack and delete the rest.  A batch is
        all-or-nothing, so these are looked for *before* the first write instead
        of being discovered halfway through.
        """
        out: list[str] = []
        for obj in self.deck.info["objects"]:
            if obj["class"] != "TDeckDescriptor" or obj["id"] not in deck_ids:
                continue
            props = self.deck._props(obj)
            pool = [it.get("object_id") for it in
                    props.get("DeckPackList", {}).get("items", []) or []]
            mixed = False
            for cg_ref in props.get("DeckCombatGroupList", {}).get("items", []) or []:
                cg = self.deck._by_id.get(cg_ref.get("object_id"))
                if cg is None:
                    continue
                for sg_ref in (self.deck._props(cg).get("SmartGroupList", {})
                               .get("items", []) or []):
                    sg = self.deck._by_id.get(sg_ref.get("object_id"))
                    if sg is None:
                        continue
                    for tup in (self.deck._props(sg)
                                .get("PackIndexUnitNumberList", {})
                                .get("items", []) or []):
                        start = tup.get("key", {}).get("value")
                        count = tup.get("value", {}).get("value") or 0
                        if start is None:
                            continue
                        seen = {pool[s] for s in range(start, start + count)
                                if 0 <= s < len(pool)}
                        if len(seen) > 1:
                            mixed = True
                            break
                    if mixed:
                        break
                if mixed:
                    break
            if mixed:
                out.append(self.retiler._deck_name(obj["id"]))
        return out

    def apply_mapping(self, mapping: dict) -> ReplaceResult:
        """Repoint every in-scope window according to ``{source: target}``.

        **Simultaneous, not chained.**  Each window is looked up by the pack it
        holds *now*, and the whole deck is re-laid in one ``relay`` call, so
        ``{A: B, B: A}`` swaps the two.  Running the same thing as two
        single-target replaces merges them instead: the first pass moves every A
        onto B, the second moves them all back onto A, and the distinction
        between the two types is gone.

        **All or nothing.**  Every row is checked before anything is written — a
        source the scope never uses, a row that would change nothing, a deck
        carrying a mixed window.  If one row fails, nothing is written at all
        and the note names the row.

        Args:
            mapping: source content key → target content key.  Both are
                :class:`~.equip.PackKey`, so two pack objects with the same
                signature are one row, which is what the dialog lists.
        """
        res = ReplaceResult()
        rows = [ReplaceRow(source_key=src, target_key=dst)
                for src, dst in mapping.items()]
        res.rows = rows
        if not rows:
            res.note = tr("没有要替换的装备")
            return res

        usage = self.usage_by_key()
        problems: list[str] = []
        for i, row in enumerate(rows, 1):
            if row.target_key is None:
                problems.append(tr("第 {i} 行没有选目标", i=i))
            elif row.target_key == row.source_key:
                problems.append(tr("第 {i} 行的目标与来源相同", i=i))
            elif row.source_key not in usage:
                problems.append(tr("第 {i} 行的来源在范围内没有用到", i=i))
        if problems:
            res.note = "；".join(problems) + tr("　—— 整体未执行")
            return res

        # Collect first, write later: this pass yields the deck set the W3
        # pre-flight needs, so a refusal still costs nothing.
        buckets: dict = {}
        companies: set = set()
        platoons: set = set()
        for did, ci, si, ei, pid, count in self._in_scope_all():
            key = self.packs.pack_key(pid)
            row = next((r for r in rows if r.source_key == key), None)
            if row is None:
                continue
            bucket = buckets.setdefault(key, {"windows": [], "pids": set(),
                                              "entries": 0, "units": 0})
            bucket["windows"].append((did, ci, si, ei))
            bucket["pids"].add(pid)
            bucket["entries"] += 1
            bucket["units"] += count
            companies.add((did, ci))
            platoons.add((did, ci, si))

        deck_ids = {did for did, _c, _s, _e, pid, _n in self._in_scope_all()
                    if self.packs.pack_key(pid) in mapping}
        mixed = self._mixed_decks(deck_ids)
        if mixed:
            res.note = tr("这些营里有混合窗口，重排会删掉装备，已整体拒绝：{v0}",
                          v0="、".join(mixed[:5]))
            return res

        target_ids: dict = {}
        for row in rows:
            pack_id, reused = self.packs.ensure_pack(row.target_key)
            if pack_id < 0:
                res.note = tr("无法创建目标装备包：{v0}", v0=row.target_key.label())
                return res
            target_ids[row.target_key] = pack_id
            row.target_id, row.reused = pack_id, reused
        res.to_pack_id = (next(iter(target_ids.values()))
                          if len(target_ids) == 1 else None)
        res.reused = all(row.reused for row in rows)

        per_deck: dict[int, dict[tuple[int, int, int], int]] = {}
        for row in rows:
            bucket = buckets.get(row.source_key)
            if bucket is None:
                continue
            row.source_ids = sorted(bucket["pids"])
            row.entries, row.units = bucket["entries"], bucket["units"]
            target = target_ids[row.target_key]
            for did, ci, si, ei in bucket["windows"]:
                per_deck.setdefault(did, {})[(ci, si, ei)] = target
            res.created_pack_id = res.created_pack_id or (
                None if row.reused else row.target_id)

        for did, edits in per_deck.items():
            out = self.retiler.relay(did, pack_edits=edits)
            if not out.ok:
                done = len(res.decks)
                res.note = f"{self.retiler._deck_name(did)}: {out.note}"
                if done:
                    res.note += tr("（已写入 {v0} 个营，其余未动）", v0=done)
                return res
            res.decks.append(self.retiler._deck_name(did))

        res.survey = ReplaceSurvey(
            decks=set(per_deck), companies=len(companies),
            platoons=len(platoons), entries=sum(r.entries for r in rows),
            units=sum(r.units for r in rows), sources=len(rows))
        res.sources = len([r for r in rows if r.entries])
        # Only the decks actually rewritten lose their cached tree.
        self.deck.invalidate(set(per_deck))
        res.ok = True
        return res

    def apply(self, to_key: PackKey) -> ReplaceResult:
        """The many-to-one shortcut: fold every source into ``to_key``.

        A source that already offers ``to_key`` is *dropped*, not refused —
        "make all of these into that one" includes the one that is already it —
        and the drop is reported through
        :attr:`ReplaceResult.target_also_a_source`.  :meth:`apply_mapping`
        refuses such a row instead, because there the user wrote that pair
        deliberately and a row that changes nothing is a mistake.
        """
        keys = [self.packs.pack_key(p) for p in self.from_pack_ids]
        keys = [k for k in keys if k is not None]
        dropped = any(k == to_key for k in keys)
        mapping = {k: to_key for k in keys if k != to_key}
        res = self.apply_mapping(mapping)
        res.target_also_a_source = dropped
        if not mapping:
            res.note = tr("目标与来源相同")
        return res
