# -*- coding: utf-8 -*-
"""Acceptance for the deck-tree visualization.

The page is a *rendering* of the same object graph the editor edits, so the
checks here are about the two ways that can go wrong without anything crashing:

* the payload silently dropping nodes — a country bucket that loses the decks
  with no country code, a platoon skipped because it has no dictionary name;
* the page claiming something the file does not say — a wrong count, a
  ``Σ != 池`` that goes unmentioned, a division counted twice.

Rendering itself (expand, filter, the node-link diagram) was verified in a real
browser; these assertions pin the data contract that the JavaScript consumes.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _env import BERLIN, TEST, deck, skip                  # noqa: E402
from ndfbin_decks.app.session import Session               # noqa: E402
from ndfbin_decks.io import modlocator                     # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from visualization import deck_tree                        # noqa: E402

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if not cond:
        FAILURES.append(label)
    print(f"  {'OK  ' if cond else 'FAIL'}  {label}" +
          (f"  — {detail}" if detail else ""))


def payload_of(name: str) -> tuple[dict, Session]:
    mod = modlocator.resolve(name)
    session = Session.load(mod.deck_bin, resolve_names=False, mod=mod)
    return deck_tree.build_tree(mod), session


#: level -> (child level, index of the child array) — the payload's shape,
#: restated here so a change to the writer's layout breaks this test rather
#: than silently making the page wrong.
KIDS = {
    "country": ("division", 2),
    "division": ("battalion", 1),
    "battalion": ("company", 4),
    "company": ("platoon", 1),
    "platoon": ("entry", 2),
}


def walk(payload):
    """Every (kind, node) pair, depth first."""
    def go(kind, node):
        yield kind, node
        kids = KIDS.get(kind)
        if kids:
            for child in node[kids[1]]:
                yield from go(kids[0], child)
    for country in payload["c"]:
        yield from go("country", country)


def main() -> int:
    if not deck(TEST).is_file():
        skip("the Test mod is not installed")

    print("=== 1. the payload is the file's tree, not a subset ===")
    payload, session = payload_of(TEST)
    counts = payload["meta"]["counts"]
    battalions = session.battalions()

    check("every AG battalion is in the page",
          counts["battalions"] == len(battalions),
          f"{counts['battalions']} vs {len(battalions)}")
    check("every division is in the page",
          counts["divisions"] == len(session.divisions()),
          f"{counts['divisions']} vs {len(session.divisions())}")
    check("every entry is in the page",
          counts["entries"] == sum(len(p.entries)
                                   for b in battalions for c in b.companies
                                   for p in c.platoons),
          str(counts["entries"]))

    seen = [n[1] for k, n in walk(payload) if k == "battalion"]
    names = {b.export_name for b in battalions}
    check("no battalion appears twice",
          len(seen) == len(set(seen)), f"{len(seen)} rows, {len(set(seen))} names")
    check("no battalion is missing from the tree",
          set(seen) == names,
          str(sorted(names - set(seen))[:3]))

    # The unlabelled bucket is the one that a naive group-by would drop: a deck
    # whose DeckDivision has no underscore has no country.
    with_country = sum(len(c[2]) for c in payload["c"])
    check("divisions without a country still get a bucket (or none exist)",
          with_country == counts["divisions"],
          f"{with_country} grouped vs {counts['divisions']} total")

    print()
    print("=== 2. the data the page reads is well formed ===")
    units = payload["u"]
    bad_entry = []
    bad_platoon = []
    for kind, node in walk(payload):
        if kind == "entry":
            if len(node) != 4 or node[0] < 0 or node[0] >= len(units):
                bad_entry.append(node)
            elif node[2] != -1 and not (0 <= node[2] < len(units)):
                bad_entry.append(node)
        elif kind == "platoon" and len(node) != 4:
            bad_platoon.append(node)
    check("every entry is [unit, count, transporter, xp] with valid indexes",
          not bad_entry, str(bad_entry[:2]))
    check("every platoon is [index, hq, entries, name]",
          not bad_platoon, str(bad_platoon[:1]))
    check("equipment names are interned (the table has no duplicates)",
          len(units) == len(set(units)), f"{len(units)} names")

    # pool vs sum is the one number that decides whether the file can be saved;
    # the page must carry both rather than showing only the sum.
    pools = [(n[2], n[3]) for k, n in walk(payload) if k == "battalion"]
    check("every battalion carries both 槽池 and Σ(Number)",
          all(isinstance(a, int) and isinstance(b, int) for a, b in pools),
          str(pools[:2]))

    print()
    print("=== 3. the page is one file and it parses back ===")
    html = deck_tree.render_html(payload)
    check("it is a complete document",
          html.startswith("<!DOCTYPE html>") and html.rstrip().endswith("</html>"))
    check("the data is embedded, not fetched",
          "const D = {" in html and '"u":' in html)
    url = re.search(r'(?:src|href)\s*=\s*["\']https?://', html)
    check("nothing is loaded from the network", url is None,
          url.group(0) if url else "")
    check("no template placeholder was left behind",
          "__DATA__" not in html and "__TITLE__" not in html)
    blob = re.search(r"const D = (\{.*?\});\n", html, re.S)
    check("the embedded JSON reads back to the same tree",
          blob is not None and json.loads(blob.group(1))["meta"]["counts"]
          == counts)
    check("the page is big enough to be the real tree, not an empty shell",
          len(html) > 500_000, f"{len(html) / 1048576:.2f} MB")

    print()
    print("=== 4. exporting is read-only ===")
    target = deck(TEST)
    before = (target.stat().st_size, target.stat().st_mtime_ns)
    out = Path(tempfile.mkdtemp()) / "tree.html"
    code = deck_tree.main(["--mod", TEST, "--out", str(out)])
    after = (target.stat().st_size, target.stat().st_mtime_ns)
    check("the CLI wrote a file", code == 0 and out.is_file() and out.stat().st_size > 0,
          f"exit {code}")
    check("Deck.ndfbin is untouched (size and mtime)",
          before == after, f"{before} -> {after}")

    print()
    print("=== 5. a second mod, so the shape is not Test-specific ===")
    if deck(BERLIN).is_file():
        berlin, _s = payload_of(BERLIN)
        c = berlin["meta"]["counts"]
        check("Berlin exports its own battalions",
              c["battalions"] == 2266, str(c["battalions"]))
        check("Berlin's divisions all land in a country bucket",
              sum(len(x[2]) for x in berlin["c"]) == c["divisions"],
              f"{c['divisions']}")
        check("the AGF pseudo-country is kept, not dropped as 'not a country'",
              any(x[0] == "AGF" for x in berlin["c"]),
              str([x[0] for x in berlin["c"]]))
    else:
        print("  --   Berlin is not installed, skipped")

    print()
    if FAILURES:
        print(f"FAIL — {len(FAILURES)} check(s) failed: {FAILURES[:4]}")
        return 1
    print("PASS — the tree matches the file, level for level")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
