# -*- coding: utf-8 -*-
"""Acceptance for readable division names.

A division's display name is a ``loc_hash`` in ``Division.ndfbin`` and a table
lookup in the mod's ``.dic`` files — no decryption, no token recovery.  What
this checks:

* the read path finds those dictionaries wherever the author put them
  (``UNITS`` family, arbitrary namespace — there is no ``DIVISIONS`` family in
  any of the three sample mods);
* the name reaches the 师 picker through ``Session.divisions()``;
* **and that it degrades**: vanilla divisions point at the game's own
  dictionaries sealed in ``Data.dat`` (EDAT v2), so they must keep the
  export-name label instead of becoming empty or a hash-shaped string.

⚠ The counts below are third-party mod content.  If they move, check whether
the author updated the mod before assuming a regression — the same rule as
``test_equip_lookup``.  A real regression looks like *every* division losing
its name, or a name landing on the wrong division.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _env import NORTHERN_THUNDER, TEST, deck, mods           # noqa: E402
from ndfbin_decks.io import division_names, divisions, modlocator  # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if not cond:
        FAILURES.append(label)
    print(f"  {'OK  ' if cond else 'FAIL'}  {label}" +
          (f"  — {detail}" if detail else ""))


def resolver_for(name: str):
    """``(DivisionNames, ModPaths)`` or ``None`` when the mod is absent."""
    mod = mods().get(name)
    if mod is None:
        return None
    return division_names.from_mod(mod), mod


def main() -> int:
    print("=== 1. a mod that ships dictionaries gets real names ===")
    got = resolver_for(NORTHERN_THUNDER)
    if got is None:
        print(f"SKIP — {NORTHERN_THUNDER} not installed (it is a workshop mod)")
        return 0
    nt, nt_mod = got
    print(f"  {nt.summary()}")
    check("Northern Thunder resolves a quarter of its divisions",
          nt.resolved == 128, str(nt.resolved))
    check("out of every division it declares",
          nt.declared == 513, str(nt.declared))

    names = sorted(set(nt.names.values()))
    check("those 128 share only 28 distinct names",
          len(names) == 28, f"{len(names)}: {names[:4]}")
    check("the names are readable, not hashes",
          all(len(n) > 4 and not n.startswith("AGF_") for n in names))
    check("a known division resolves to its real name",
          "94th Guards MR Division" in nt.names.values(),
          str([n for n in names if "Guards" in n][:3]))

    # 同一 hash 的 _solo / _multi / _challenge 变体各有自己的 export 路径，
    # 都要拿到名字 —— 这是 `_hashes` 用 list 而不是单个路径的原因。
    check("several variant paths share one name",
          nt.resolved > len(names),
          f"{nt.resolved} paths / {len(names)} names")

    print()
    print("=== 2. the name reaches the 师 picker ===")
    from ndfbin_decks.app.session import Session
    match = modlocator.resolve(NORTHERN_THUNDER)
    session = Session.load(Path(match.deck_bin), resolve_names=False, mod=match)
    picked = session.divisions()
    real = [d for d in picked if d.label in nt.names.values()]
    check("Session.divisions() uses the dictionary name",
          len(real) == 128, f"{len(real)} of {len(picked)} 师")
    check("and keeps the division id for scope/replace",
          all(d.path.startswith("$/GFX/Division/") for d in real))
    check("and still derives the country from the path",
          all(d.country for d in real), str([d.country for d in real[:5]]))

    print()
    print("=== 3. vanilla divisions degrade instead of breaking ===")
    vanilla = [d for d in picked if d.label not in nt.names.values()]
    check("they are still listed", len(vanilla) > 200, str(len(vanilla)))
    check("with the export-name label, not a hash",
          any(d.label == divisions.division_label(d.path) for d in vanilla))
    check("and none of them resolved to an empty string",
          all(d.label.strip() for d in picked))

    print()
    print("=== 4. a mod with no dictionary at all ===")
    got = resolver_for(TEST)
    if got is None:
        print(f"SKIP — {TEST} not installed")
    else:
        st, _mod = got
        print(f"  {st.summary()}")
        check("no crash, and almost nothing resolves",
              st.resolved <= 2, f"{st.resolved}/{st.declared}")
        check("it still declares the divisions it has", st.declared > 300,
              str(st.declared))

    print()
    print("=== 5. missing inputs are empty, not fatal ===")
    empty = division_names.from_mod(None)
    check("no mod -> empty", len(empty) == 0 and not empty.has_any)
    check("resolve() on empty returns None", empty.resolve("x") is None)
    check("summary says so instead of dividing by zero",
          "no Division" in empty.summary(), empty.summary())

    # A real mod whose Division.ndfbin is gone: the resolver must not raise.
    class _NoBin:
        division_bin = Path("does-not-exist/Division.ndfbin")
        def localisation_gen_dir(self):
            return None

    check("a missing Division.ndfbin -> empty",
          len(division_names.from_mod(_NoBin())) == 0)

    print()
    if FAILURES:
        print(f"FAIL — {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS — division names resolve where the mod ships a dictionary, "
          "and degrade to export labels everywhere else")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
