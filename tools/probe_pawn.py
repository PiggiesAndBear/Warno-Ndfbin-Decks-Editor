"""Recon of the *strategic* attributes an Army General deck carries.

The four things a mod author wants to edit — 部队类型 / 移动方式 / 行动点 /
炮兵支援覆盖范围 — are **not** in ``Deck.ndfbin``.  That file is only the
organisation: companies, platoons and the ``(PackIndex, Number)`` windows.  The
attributes live one level up, in ``Gen/NDF/GFX/Pawn.ndfbin``, where each AG deck
has a ``TEntityDescriptor`` exported as ``Descriptor_Unit_<deck identifier>``.

The shape that decides whether this is easy or dangerous:

* a pawn's attributes are **modules** — separate top-level objects that the pawn
  lists in ``ModulesDescriptors`` as plain ``obj_ref``s;
* the compiler **dedupes identical modules**, so one
  ``TActionPointsModuleDescriptor`` can be shared by 1600+ pawns while
  ``TDeckModuleDescriptor`` / ``TTypeUnitModuleDescriptor`` /
  ``TStrategicLabelModuleDescriptor`` are one-per-pawn.

Editing a shared module in place would therefore rewrite every deck that
references it.  ``attr`` prints the sharing factor next to each value, because
that single number is what separates "edit it" from "clone it and repoint".

Usage::

    probe_pawn.py classes                 # what is in the file
    probe_pawn.py join                    # deck identifier -> pawn export
    probe_pawn.py attr                    # per-attribute distribution + sharing
    probe_pawn.py pawn SOV_1GTA_595Reco   # one pawn's module list
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ndfbin_decks.core import cndf_codec                  # noqa: E402
from ndfbin_decks.core.deckmodel import DeckFile          # noqa: E402
from ndfbin_decks.io import modlocator                    # noqa: E402

PAWN = "Gen/NDF/GFX/Pawn.ndfbin"

#: The attributes worth exposing, and the module each one lives on.
#: ``shared`` is filled in at runtime — see :func:`ref_counts`.
ATTRS = {
    "行动点": ("TActionPointsModuleDescriptor", "InitialActionPoint"),
    "行动点（每回合恢复）": ("TActionPointsModuleDescriptor", "ActionPointRecoveryPerTurn"),
    "移动方式": ("TStrategicMovementModuleDescriptor", "_ShortDatabaseName"),
    "战斗角色": ("TStrategicBattleModuleDescriptor", "BattleRole"),
    "炮兵支援覆盖范围(AP)": ("TStrategicBattleModuleDescriptor", "BattleSupportRadiusInAPCase"),
    "防空拦截半径(AP)": ("TStrategicBattleModuleDescriptor", "AirDenyRadiusInAPCase"),
    "视野隐蔽加成": ("TVisibilityModuleDescriptor", "UnitConcealmentBonus"),
    "影响强度": ("TInfluenceMapModuleDescriptor", "InfluenceStrength"),
    "疲劳上限": ("TStrategicFatigueModuleDescriptor", "MaxFatigue"),
    "分数/价值": ("TDeckModuleDescriptor", "Score"),
}


def pawn_path(mod_name: str | None) -> tuple[Path, object]:
    """``(Pawn.ndfbin, mod)`` for the first mod that ships one."""
    for m in modlocator.discover():
        if mod_name and m.name != mod_name:
            continue
        try:
            p = m.deploy / PAWN
        except Exception:                    # noqa: BLE001
            continue
        if p.is_file():
            return p, m
    raise SystemExit("没找到任何 mod 的 Gen/NDF/GFX/Pawn.ndfbin")


class Pawns:
    """One decoded ``Pawn.ndfbin`` plus the indexes the commands need."""

    def __init__(self, path: Path):
        self.path = path
        _doc, self.info = cndf_codec.decode(path.read_bytes(), str(path))
        self.objs = self.info["objects"]
        self.by_id = {o["id"]: o for o in self.objs}
        self.exports = {oid: p.rsplit("/", 1)[-1]
                        for oid, p in self.info["exports"].items()}
        self._refs: Counter | None = None

    # -- helpers -----------------------------------------------------------
    def refs(self) -> Counter:
        """How many times each object is referenced.  Cached."""
        if self._refs is None:
            out: Counter = Counter()

            def walk(node):
                if isinstance(node, list):
                    for x in node:
                        walk(x)
                elif isinstance(node, dict):
                    if "object_id" in node and node["object_id"] != 0xFFFFFFFF:
                        out[node["object_id"]] += 1
                    for k, v in node.items():
                        if k not in ("object_id", "class_id"):
                            walk(v)
            for o in self.objs:
                for pr in o["properties"]:
                    walk(pr["value"])
            self._refs = out
        return self._refs

    @staticmethod
    def prop(obj: dict, name: str):
        for pr in obj["properties"]:
            if pr["property_name"] == name:
                return pr["value"]
        return None

    @classmethod
    def scalar(cls, obj: dict, name: str):
        v = cls.prop(obj, name)
        return v.get("value") if isinstance(v, dict) else v

    def modules_of(self, name: str) -> tuple[str, list[tuple[str, dict]]]:
        """``(resolved export name, [(class name, module object), ...])``.

        The export is ``Descriptor_Unit_pion_<identifier>`` while the deck's own
        identifier says just ``pion_<identifier>``, so the prefix is not
        guessable — try the known spellings, then fall back to a substring
        search and refuse anything ambiguous.
        """
        oid = next((i for i, n in self.exports.items() if n == name), None)
        if oid is None:
            for cand in (f"Descriptor_Unit_{name}", f"Descriptor_Unit_pion_{name}"):
                oid = next((i for i, n in self.exports.items() if n == cand), None)
                if oid is not None:
                    name = cand
                    break
        if oid is None:
            hits = [n for n in self.exports.values() if name in n]
            if len(hits) == 1:
                name = hits[0]
                oid = next(i for i, n in self.exports.items() if n == name)
        if oid is None:
            return name, []
        lst = self.prop(self.by_id[oid], "ModulesDescriptors") or {}
        out = []
        for item in lst.get("items", []):
            obj = self.by_id.get(item.get("object_id"))
            if obj is not None:
                out.append((obj["class"], obj))
        return name, out

    def strings_behind(self, obj: dict, prop: str) -> list[str]:
        """Follow one ``obj_ref`` property to the string list it points at.

        The strategic icon is not stored on the pawn: the pawn points at a
        ``TBUCKToolAlternativeValues...`` object whose ``Values`` list holds the
        texture names.  Those are shared, so the icon is a *reference*, not a
        literal — worth knowing before offering it as an editable field.
        """
        ref = self.prop(obj, prop)
        target = self.by_id.get(ref.get("object_id")) if isinstance(ref, dict) else None
        if target is None:
            return []
        vals = self.prop(target, "Values")
        if isinstance(vals, dict):
            items = vals.get("items")
        else:
            items = vals if isinstance(vals, list) else None
        if not items:
            return []
        return [x.get("value") if isinstance(x, dict) else x for x in items]


def cmd_classes(p: Pawns) -> None:
    print(f"=== {p.path}")
    print(f"    {len(p.objs)} 个对象 / {len(p.exports)} 个导出\n")
    hist = Counter(o["class"] for o in p.objs)
    refs = p.refs()
    print(f"{'类':46s} {'对象':>6} {'被引':>7} {'平均共享':>8}")
    for cls, n in sorted(hist.items(), key=lambda t: -t[1]):
        ids = [o["id"] for o in p.objs if o["class"] == cls]
        tot = sum(refs[i] for i in ids)
        if tot:
            print(f"    {cls:42s} {n:6d} {tot:7d} {tot/n:8.1f}")


def cmd_join(p: Pawns, mod) -> None:
    deck = DeckFile(mod.deck_bin)
    names = {b.identifier for b in deck.battalions()}
    have = set(p.exports.values())
    hit = {n for n in names if f"Descriptor_Unit_{n}" in have}
    print(f"{mod.name}")
    print(f"    AG 营 {len(names)} 个；其中有同名战略 pawn 的 "
          f"{len(hit)} 个 = {len(hit)/len(names):.1%}")
    if names - hit:
        print(f"    落空：{sorted(names - hit)[:8]}")
    pawn_only = {n[len('Descriptor_Unit_'):] for n in have
                 if n.startswith("Descriptor_Unit_")} - names
    print(f"    pawn 有、营没有的 {len(pawn_only)} 个：{sorted(pawn_only)[:8]}")


def cmd_attr(p: Pawns) -> None:
    refs = p.refs()
    for label, (cls, field) in ATTRS.items():
        holders = [o for o in p.objs if o["class"] == cls]
        if not holders:
            print(f"\n### {label}: {cls} 里没有这个类")
            continue
        weighted: Counter = Counter()
        for o in holders:
            v = p.scalar(o, field)
            weighted[str(v)] += refs[o["id"]]
        has = sum(v for k, v in weighted.items() if k != "None")
        objs = len(holders)
        tot = sum(weighted.values())
        print(f"\n### {label}  [{cls}.{field}]")
        print(f"    {objs} 个对象承载 {tot} 个 pawn 的引用"
              f"（平均 {tot/objs:.0f} 个 pawn 共用一个）"
              f"；{has} 个 pawn 真的写了这个字段")
        for k, v in sorted(weighted.items(), key=lambda t: -t[1])[:8]:
            print(f"      {v:6d}  {k}")
        # The sharing factor, not the object count, is what decides the edit
        # strategy: one object per pawn can be changed in place, a shared one
        # has to be cloned or the change lands on every pawn that points at it.
        if tot <= objs * 1.05:
            print("      ★ 一 pawn 一对象（独有）—— 可以原地改")
        else:
            print(f"      ★★ 共享（平均 {tot/objs:.0f} 个 pawn 一个）"
                  f"—— 必须克隆再重指向，原地改会波及全部引用者")


def cmd_icons(p: Pawns) -> None:
    """Pawn-weighted distribution of the strategic icon (the ``部队类型`` shown
    on the map).  The icon is a *reference* to a shared ``Values`` list, so —
    like the movement type — it is shared unless cloned."""
    refs = p.refs()
    seen: Counter = Counter()
    for o in p.objs:
        if o["class"] != "TStrategicLabelModuleDescriptor":
            continue
        ico = p.strings_behind(o, "BackgroundTexture")
        seen[" + ".join(x.replace("Texture_STRATEGIC_", "") for x in ico)
             or "(none)"] += refs[o["id"]]
    print(f"=== 战略图标（部队类型）  pawn 加权 {sum(seen.values())}")
    for k, v in sorted(seen.items(), key=lambda t: -t[1]):
        print(f"    {v:6d}  {k}")


def cmd_names(p: Pawns) -> None:
    """How many module objects kept their source NDF name.

    The compiler leaves ``_ShortDatabaseName`` on modules it deduplicated, which
    means the UI can label them with the name the source used instead of an
    object id.
    """
    have = [o for o in p.objs if p.prop(o, "_ShortDatabaseName")]
    print(f"=== 保留源码名的对象 {len(have)} / {len(p.objs)}")
    mods = [o for o in have if "Module" in o["class"] or "Descriptor" in o["class"]]
    print(f"    其中模块/描述符类 {len(mods)}")
    for o in have[:10]:
        print(f"    #{o['id']:<6} {o['class']:44s} "
              f"{p.scalar(o, '_ShortDatabaseName')}")


def cmd_pawn(p: Pawns, name: str) -> None:
    export, mods = p.modules_of(name)
    if not mods:
        raise SystemExit(f"没有这个 pawn：{name}")
    refs = p.refs()
    print(f"=== {export}   {len(mods)} 个模块")
    print(f"{'#':>3} {'模块类':44s} {'被引':>6} {'属性'}")
    for i, (cls, obj) in enumerate(mods):
        props = {}
        for pr in obj["properties"]:
            v = pr["value"]
            props[pr["property_name"]] = v.get("value") if isinstance(v, dict) else v
        ico = p.strings_behind(obj, "BackgroundTexture")
        if ico:
            props["图标"] = ico
        print(f"{i:3d} {cls:44s} {refs[obj['id']]:6d} {props}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mod", help="mod 名（默认第一个带 Pawn.ndfbin 的）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("classes")
    sub.add_parser("icons")
    sub.add_parser("names")
    sub.add_parser("join")
    sub.add_parser("attr")
    p = sub.add_parser("pawn"); p.add_argument("pawn")
    args = ap.parse_args()

    path, mod = pawn_path(args.mod)
    pawns = Pawns(path)
    if args.cmd == "classes":
        cmd_classes(pawns)
    elif args.cmd == "join":
        cmd_join(pawns, mod)
    elif args.cmd == "attr":
        cmd_attr(pawns)
    elif args.cmd == "icons":
        cmd_icons(pawns)
    elif args.cmd == "names":
        cmd_names(pawns)
    else:
        cmd_pawn(pawns, args.pawn)


if __name__ == "__main__":
    main()
