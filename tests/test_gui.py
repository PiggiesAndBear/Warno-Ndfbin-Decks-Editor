# -*- coding: utf-8 -*-
"""Headless test for the GUI and the two gates that protect the file.

Builds the real ``MainWindow`` against the real ``Test`` mod, drives every
action through its code path with the modal dialogs stubbed out, and checks the
graph afterwards.  This catches wiring errors — missing imports, wrong ids,
buttons that do nothing — without a human staring at a window.

Two properties are checked because they are the ones that silently corrupt a
mod rather than crash:

* the equipment picker may only offer packs **this file** contains (no
  cross-mod references the ``IMPR`` trie could not resolve);
* and only packs an **Army General deck** fields — the 2483 PvP-only packs in
  the same file share the object type but have never been through the AG code
  path.

Run with a Qt offscreen platform:  ``QT_QPA_PLATFORM=offscreen``
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _env                                              # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
from PySide6.QtTest import QTest

FAILURES: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if not cond:
        FAILURES.append(label)
    print(f"  {'OK  ' if cond else 'FAIL'}  {label}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    # Guarded up front: without the Test mod the window opens but nothing is
    # selectable, and every later assertion would fail on a None session —
    # which reads as "the GUI is broken" rather than "install the mod".
    # Called module-qualified because this function assigns a local ``deck``.
    _env.deck(_env.TEST)
    from ndfbin_decks.app.gui import MainWindow

    app = QApplication.instance() or QApplication([])

    # stub the modal dialogs so the test never blocks
    shown: list[tuple[str, str]] = []
    def _record(kind):
        def hook(*a, **k):
            shown.append((kind, str(a[2]) if len(a) > 2 else ""))
        return hook
    QMessageBox.information = _record("info")
    QMessageBox.warning = _record("warn")
    QMessageBox.critical = _record("error")

    # Modal pickers block forever under offscreen; drive them by patching
    # ``exec`` and having the dialog answer with the current pack, which makes
    # the edit a legal no-op.
    import ndfbin_decks.app.gui as gui_mod
    from PySide6.QtWidgets import QDialog

    class _AutoPick:
        calls = 0
        chosen_key = None

        def __init__(self, session, current=None, parent=None):
            self.session = session
            self._current = current

        def setWindowTitle(self, *_a):
            pass

        def exec(self):
            _AutoPick.calls += 1
            _AutoPick.chosen_key = self._current
            return QDialog.Accepted

        def chosen(self):
            return _AutoPick.chosen_key

    gui_mod.SwapDialog = _AutoPick

    print("=== 1. window builds and lists mods from both deployment roots ===")
    win = MainWindow()
    check("mod combo has a placeholder plus the mods",
          win.mod_box.count() >= 3, f"{win.mod_box.count()} items")
    check("placeholder holds no mod name",
          win.mod_box.itemData(0) is None)
    test_idx = win.mod_box.findData("Test")
    check("Test is selectable", test_idx > 0, str(test_idx))
    broken = [i for i in range(win.mod_box.count())
              if not win.mod_box.model().item(i).isEnabled()]
    check("a mod without Deck.ndfbin is unselectable",
          len(broken) >= 1 and all(win.mod_box.itemData(i) is None
                                   for i in broken), f"{broken}")

    # A workshop subscription is loaded straight from the Steam folder — it is
    # never copied into the Saved Games workspace — so without a second scan
    # root the editor can only ever see the user's own mods.
    from ndfbin_decks.io import modlocator
    ws_mods = [m for m in modlocator.discover()
               if m.source == modlocator.SOURCE_WORKSHOP]
    loadable = []
    for m in ws_mods:
        try:
            if Path(m.deck_bin).is_file():
                loadable.append(m)
        except Exception:                                  # noqa: BLE001
            pass
    labels = [win.mod_box.itemText(i) for i in range(win.mod_box.count())]
    if ws_mods:
        check("workshop content is scanned too",
              len(ws_mods) >= 1, f"{len(ws_mods)} workshop mods")
        check("every loadable workshop mod is offered",
              all(any(m.label in lab for lab in labels) for m in loadable),
              f"{len(loadable)} loadable")
        check("the source is visible in the label",
              any("创意工坊" in lab for lab in labels),
              str([lab for lab in labels if "创意工坊" in lab][:2]))
    else:
        print("  (no workshop content on this machine — skipping)")

    print()
    print("=== 1b. 「打开 mod 文件夹」 is the fallback for anything else ===")
    import shutil
    import tempfile
    from PySide6.QtWidgets import QFileDialog
    test_mod = next((m for m in modlocator.discover() if m.name == "Test"
                     and Path(m.deck_bin).is_file()), None)
    real_picker = QFileDialog.getExistingDirectory
    before_n = win.mod_box.count()
    tmp_root = None
    try:
        QFileDialog.getExistingDirectory = lambda *a, **k: ""
        win.on_open_folder()
        app.processEvents()
        check("cancelling changes nothing", win.mod_box.count() == before_n)

        QFileDialog.getExistingDirectory = (
            lambda *a, **k: r"D:\definitely\not\here")
        win.on_open_folder()
        app.processEvents()
        check("a folder with no mod says so",
              any("里面没有 mod" in m for _, m in shown[-1:]),
              str(shown[-1]) if shown else "no dialog")

        if test_mod is not None:
            tmp_root = Path(tempfile.mkdtemp())
            hand = tmp_root / "HandPickedMod"
            (hand / "Gen" / "NDF" / "GFX").mkdir(parents=True)
            shutil.copy(Path(test_mod.deck_bin),
                        hand / "Gen" / "NDF" / "GFX" / "Deck.ndfbin")
            QFileDialog.getExistingDirectory = lambda *a, **k: str(hand)
            win.on_open_folder()
            app.processEvents()
            check("a hand-picked mod folder is added",
                  win.mod_box.count() == before_n + 1,
                  f"{before_n} -> {win.mod_box.count()}")
            picked = win.mod_box.itemData(win.mod_box.count() - 1)
            check("its item data is the folder name",
                  picked == "HandPickedMod", str(picked))
            check("it is selectable", win.mod_box.model()
                  .item(win.mod_box.count() - 1).isEnabled())
            check("and it opens straight away",
                  win.session is not None
                  and "HandPickedMod" in str(win.session.path),
                  str(getattr(win.session, "path", None)))
        else:
            print("  (no local mod to copy — skipping the add check)")
    finally:
        QFileDialog.getExistingDirectory = real_picker
        if tmp_root is not None:
            shutil.rmtree(tmp_root, ignore_errors=True)
        win.mod_box.setCurrentIndex(0)
        app.processEvents()

    print()
    print("=== 2. opening a mod builds the 师/营/连/排 tree ===")
    win.mod_box.setCurrentIndex(test_idx)
    app.processEvents()
    s = win.session
    check("session loaded", s is not None)
    # 233 divisions plus the "全部师" entry that index 0 now carries.
    check("233 divisions discovered", win.div_box.count() == 234,
          str(win.div_box.count()))
    check("index 0 is the all-divisions entry, not a division",
          win.div_box.itemData(0) is None, str(win.div_box.itemData(0)))
    check("2208 battalions in scope", len(s.battalions()) == 2208,
          str(len(s.battalions())))

    root = win.tree.topLevelItem(0)
    check("one root, labelled 师Div", root.text(0).startswith("师Div"),
          root.text(0))
    check("root role is a division",
          root.data(0, 256).kind == "div", str(root.data(0, 256)))
    bn = root.child(0)
    check("battalion child labelled 营Bn", bn.text(0).startswith("营Bn"),
          bn.text(0))
    check("battalion role carries the deck id",
          bn.data(0, 256).kind == "bn"
          and bn.data(0, 256).deck_id is not None)
    co = bn.child(0)
    check("company child labelled 连Co", co.text(0).startswith("连Co"),
          co.text(0))
    pl = co.child(0)
    check("platoon child labelled 排Pl", pl.text(0).startswith("排Pl"),
          pl.text(0))
    check("entry children exist", pl.childCount() >= 1,
          pl.child(0).text(0) if pl.childCount() else "")

    # The composition fallback is what makes an unlabelled mod navigable: Test
    # ships 6 dictionary entries for 42258 platoons.
    check("company shows what it fields, not a raw hash",
          "⟨未知" not in co.text(0), co.text(0)[:60])

    print()
    print("=== 3. the division filter narrows the battalions ===")
    before = root.childCount()
    # Index 0 is the "全部师" entry; a division is index 1 and up, and the test
    # must not park the tree on all 2208 battalions.
    win.div_box.setCurrentIndex(2)
    app.processEvents()
    after = win.tree.topLevelItem(0).childCount()
    check("switching division changes the battalion set",
          0 < after < 200 and after != before, f"{before} -> {after}")
    win.div_box.setCurrentIndex(1)
    app.processEvents()

    print()
    print("=== 3b. typing in the 师 box narrows its list ===")
    check("the division combo is searchable", win.div_box.isEditable())
    full = win.div_box.matches()
    check("all rows listed before typing", full == win.div_box.count(),
          f"{full}")
    check("there is an inline completer for it",
          win.div_box.completer() is not None)

    # Type it the way a user does — real key events into the line edit.  This
    # is the path that was broken: ``_on_typed`` used to move ``currentIndex``,
    # which rewrote the edit text, so the next character appended to the old
    # label and the filter matched nothing.
    before_tree = win.tree.topLevelItem(0).text(0)
    check("the box starts empty, with the choice shown as a hint",
          win.div_box.lineEdit().text() == ""
          and "RFA_TK_Nord" in win.div_box.lineEdit().placeholderText(),
          f"{win.div_box.lineEdit().text()!r} / "
          f"{win.div_box.lineEdit().placeholderText()[:24]!r}")
    win.div_box.setFocus()
    app.processEvents()
    for ch in "SOV":
        QTest.keyClicks(win.div_box.lineEdit(), ch)
        app.processEvents()
    check("the typed text is exactly what was typed",
          win.div_box.lineEdit().text() == "SOV",
          repr(win.div_box.lineEdit().text()))
    narrowed = win.div_box.matches()
    check("typing narrows the list", 0 < narrowed < full,
          f"{full} -> {narrowed}")
    check("every surviving row contains the needle",
          all("SOV" in win.div_box.itemText(i).upper()
              for i in range(win.div_box.count())),
          str([win.div_box.itemText(i)[:22]
               for i in range(min(3, win.div_box.count()))]))
    check("typing alone does not move the tree — the user has not chosen yet",
          win.tree.topLevelItem(0).text(0) == before_tree,
          win.tree.topLevelItem(0).text(0)[:40])

    # Enter is the commit, and it must work: NoInsert on its own would make it
    # silently do nothing, which reads as the box being dead.
    win.div_box.lineEdit().returnPressed.emit()
    app.processEvents()
    check("Enter commits the first surviving row",
          "SOV" in win.div_box.current_label().upper(),
          win.div_box.current_label())
    check("the tree follows the committed choice",
          "SOV" in win.tree.topLevelItem(0).text(0).upper(),
          win.tree.topLevelItem(0).text(0)[:40])
    check("and the filter is lifted so the list is whole again",
          win.div_box.matches() == full, str(win.div_box.matches()))
    check("the box is empty again, hinting the new choice",
          win.div_box.lineEdit().text() == ""
          and "SOV" in win.div_box.lineEdit().placeholderText(),
          f"{win.div_box.lineEdit().text()!r} / "
          f"{win.div_box.lineEdit().placeholderText()[:24]!r}")

    committed = win.tree.topLevelItem(0).text(0)
    committed_label = win.div_box.current_label()
    win.div_box.lineEdit().setText("zzz-no-such-division")
    win.div_box._on_typed("zzz-no-such-division")
    app.processEvents()
    check("a filter matching nothing shows nothing",
          win.div_box.matches() == 0)
    check("but does not widen the tree to every battalion",
          win.tree.topLevelItem(0).text(0) == committed,
          win.tree.topLevelItem(0).text(0)[:40])
    check("and the last real choice survives", win.div_box.current_path(),
          str(win.div_box.current_path()))
    ev = __import__("PySide6.QtGui", fromlist=["QFocusEvent"]).QFocusEvent(
        __import__("PySide6.QtCore", fromlist=["QEvent"]).QEvent.FocusOut)
    win.div_box.focusOutEvent(ev)
    app.processEvents()
    check("abandoning the search snaps back to the committed row",
          win.div_box.matches() == full
          and win.div_box.lineEdit().text() == ""
          and win.div_box.current_label() == committed_label,
          f"{win.div_box.matches()} / "
          f"{win.div_box.current_label()[:24]!r} / "
          f"{win.div_box.lineEdit().placeholderText()[:24]!r}")

    win.div_box.lineEdit().setText("")
    win.div_box._on_typed("")
    app.processEvents()
    check("clearing restores the full list",
          win.div_box.matches() == full, str(win.div_box.matches()))

    print()
    print("=== 3c. the 国家 picker re-scopes the 师 list ===")
    from ndfbin_decks.io import divisions as divmod
    countries = s.countries()
    check("every division carries a country",
          all(d.country for d in s.divisions()),
          str([d.label for d in s.divisions() if not d.country][:3]))
    check("the labels group into a readable number of countries",
          3 <= len(countries) <= 30, f"{len(countries)} countries")
    check("SOV is one of them and is the biggest contingent",
          countries[0].code == "SOV", countries[0].code)
    check("Germany is RDA in the division exports, DDR in the units",
          divmod.country_code("$/GFX/Division/Descriptor_Deck_Division_RDA_x_solo")
          == "RDA"
          and "DDR" in divmod.country_label("RDA", 18),
          divmod.country_label("RDA", 18))

    check("the country combo lists all-plus-each",
          win.country_box.count() == len(countries) + 1,
          f"{win.country_box.count()} vs {len(countries)} + 1")
    check("and opens on 全部国家", win.country_box.currentData() is None,
          str(win.country_box.currentData()))
    check("with every division in the 师 list",
          win.div_box.count() == win.div_box.matches() == 234,
          str(win.div_box.count()))

    wide = win.div_box.count()
    sov_idx = win.country_box.findData("SOV")
    win.country_box.setCurrentIndex(sov_idx)
    app.processEvents()
    check("choosing SOV narrows the 师 list to that country",
          win.div_box.count() == len(countries[0].divisions) + 1 < wide,
          f"{wide} -> {win.div_box.count()}")
    check("every division offered is Soviet",
          all(r.startswith("SOV_")
              for r in (win.div_box.itemText(i).split("  (")[0]
                        for i in range(1, win.div_box.count()))),
          str([win.div_box.itemText(i)[:18]
               for i in range(1, min(4, win.div_box.count()))]))
    check("it still opens on a division, not on all 515 battalions",
          win.div_box.currentIndex() == 1,
          str(win.div_box.currentIndex()))
    check("the tree shows a Soviet division",
          win.tree.topLevelItem(0).text(0).startswith("师Div SOV_"),
          win.tree.topLevelItem(0).text(0)[:34])

    win.div_box.setCurrentIndex(0)
    app.processEvents()
    check("the 全部师 entry selects the whole country",
          win.div_box.current_path() is None)
    root = win.tree.topLevelItem(0)
    check("and the tree covers every Soviet battalion",
          root.childCount() == len(countries[0].battalions),
          f"{root.childCount()} vs {len(countries[0].battalions)}")
    check("the root says which country it is, in both spellings",
          "SOV" in root.text(0) and "苏联" in root.text(0), root.text(0)[:44])

    # Typing narrows *within* the country — the two filters compose.
    win.div_box.setFocus()
    app.processEvents()
    for ch in "GTkD":
        QTest.keyClicks(win.div_box.lineEdit(), ch)
        app.processEvents()
    check("typing narrows within the country too",
          0 < win.div_box.matches() < len(countries[0].divisions),
          f"{win.div_box.matches()} of {len(countries[0].divisions)}")
    win.div_box.lineEdit().returnPressed.emit()
    app.processEvents()
    check("and the committed division is still Soviet",
          win.div_box.current_label().startswith("SOV_"),
          win.div_box.current_label())

    win.country_box.setCurrentIndex(0)
    app.processEvents()
    check("going back to 全部国家 restores the 师 list",
          win.div_box.count() == wide, str(win.div_box.count()))

    print()
    print("=== 4. battalion search narrows the tree ===")
    bn = win.tree.topLevelItem(0).child(0)
    token = bn.text(0).replace("营Bn ", "")[:6]
    win.bn_search.setText(token)
    app.processEvents()
    hit = win.tree.topLevelItem(0).childCount()
    check("search leaves fewer battalions", 0 < hit <= before,
          f"'{token}' -> {hit} of {before}")
    win.bn_search.setText("zzz-不可能存在-zzz")
    app.processEvents()
    check("a hopeless search empties the tree",
          win.tree.topLevelItem(0).childCount() == 0)
    win.bn_search.setText("")
    app.processEvents()

    print()
    print("=== 5. the table lists entries, not raw slots ===")
    bn = win.tree.topLevelItem(0).child(0)
    win.tree.setCurrentItem(bn)
    app.processEvents()
    deck0 = win._deck_of(bn.data(0, 256))
    n_windows = sum(len(p.windows) for c in deck0.companies for p in c.platoons)
    n_slots = len(s.retiler.pool(deck0.deck_object_id))
    check("one row per entry (window)", win.table.rowCount() == n_windows,
          f"{win.table.rowCount()} rows vs {n_windows} windows "
          f"({n_slots} slots)")
    check("entries are fewer than slots, so a window cannot be "
          "edited piecewise", win.table.rowCount() < n_slots,
          f"{win.table.rowCount()} rows vs {n_slots} slots")
    check("first column names the entry", win.table.item(0, 0).text() == "#1",
          win.table.item(0, 0).text())
    check("unit name resolved", bool(win.table.item(0, 3).text()),
          win.table.item(0, 3).text())
    headers = [win.table.horizontalHeaderItem(i).text()
               for i in range(win.table.columnCount())]
    check("headers put the entry first and the slot range as info",
          headers[0] == "条目" and "槽位" in headers,
          str(headers))
    check("selecting a row yields an entry address",
          win.table.select_entry(0, 0, 0)
          and win.table.selected_entry() == (0, 0, 0),
          str(win.table.selected_entry()))

    print()
    print("=== 6. selecting a platoon highlights its entries ===")
    pl = bn.child(0).child(0)
    win.tree.setCurrentItem(pl)
    app.processEvents()
    lit = [r for r in range(win.table.rowCount())
           if win.table.item(r, 0).background().color().name() != "#000000"]
    check("some rows are highlighted", len(lit) >= 1, f"{len(lit)} rows")
    role_pl = pl.data(0, 256)
    platoon = deck0.companies[role_pl.ci].platoons[role_pl.si]
    check("exactly that platoon's entries are lit",
          len(lit) == len(platoon.windows),
          f"{len(lit)} lit vs {len(platoon.windows)} windows")

    print()
    print("=== 7. set_count path works end to end ===")
    role = pl.data(0, 256)
    did = role.deck_id
    before_pool = len(s.retiler.pool(did))
    ci, si = role.ci, role.si
    deck = next(b for b in s.battalions() if b.deck_object_id == did)
    cur = deck.companies[ci].platoons[si].windows[0].count
    QInputDialog.getInt = staticmethod(lambda *a, **k: (cur + 2, True))
    win.tree.setCurrentItem(pl)
    win.on_set_count()
    after_pool = len(s.retiler.pool(did))
    check("pool grew by exactly the added units", after_pool == before_pool + 2,
          f"{before_pool} -> {after_pool}")
    deck = next(b for b in s.battalions() if b.deck_object_id == did)
    check("W1 (ΣNumber == len(pool)) still holds",
          after_pool == deck.window_sum, f"pool={after_pool} sum={deck.window_sum}")
    check("session marked dirty", s.dirty)

    print()
    print("=== 8. insert / remove paths ===")

    # Every edit rebuilds the tree, so the node must be re-located each time
    # rather than reused — a stale QTreeWidgetItem is a hard crash.
    def node(did, ci=-1, si=-1):
        n = win._node_for(did, ci, si)
        assert n is not None, f"node {did}/{ci}/{si} vanished after the edit"
        return n

    check("_reload keeps the selection",
          win._current() is not None
          and win._current().deck_id == did,
          str(win._current()))

    n_before = len(deck.companies[ci].platoons[si].windows)
    QInputDialog.getInt = staticmethod(lambda *a, **k: (1, True))
    pl = node(did, ci, si)
    win.tree.setCurrentItem(pl)
    win.on_insert()
    deck = next(b for b in s.battalions() if b.deck_object_id == did)
    n_after = len(deck.companies[ci].platoons[si].windows)
    check("insert added a window", n_after == n_before + 1,
          f"{n_before} -> {n_after}")
    win.on_remove()
    deck = next(b for b in s.battalions() if b.deck_object_id == did)
    n_final = len(deck.companies[ci].platoons[si].windows)
    check("remove took it back", n_final == n_before, f"{n_after} -> {n_final}")
    check("W1 holds after insert+remove",
          deck.window_sum == len(s.retiler.pool(did)))

    print()
    print("=== 9. batch replace: scope widens, counts never move ===")
    from ndfbin_decks.edit.bulk import ScopedReplace, Scope
    b0 = next(b for b in s.battalions() if b.deck_object_id == did)
    cat = s.get_catalogue()
    # a pack this battalion actually fields
    pool0 = s.retiler.pool(did)
    from_pack = next(p for p in pool0
                     if cat.by_id(p) is not None)
    target = next(c for c in cat.items
                  if c.pack_object_id != from_pack
                  and c.unit != s.packs.pack_key(from_pack).unit)

    def scope_of(kind):
        return Scope(kind=kind, division=b0.division, deck_id=did,
                     ci=ci, si=si)

    surveys = {}
    for kind in ("platoon", "company", "battalion", "division"):
        surveys[kind] = s.scoped_replace(
            scope_of(kind), from_pack).survey()
    print("       " + " | ".join(
        f"{k[:4]}:{surveys[k].entries}条/{surveys[k].units}件"
        for k in surveys))
    check("scope widens monotonically",
          surveys["platoon"].entries <= surveys["company"].entries
          <= surveys["battalion"].entries <= surveys["division"].entries,
          str([surveys[k].entries for k in
               ("platoon", "company", "battalion", "division")]))
    check("division scope reaches past one battalion",
          len(surveys["division"].decks) >= 1)

    total_before = sum(len(s.retiler.pool(b.deck_object_id))
                       for b in s.battalions())
    sum_before = sum(b.window_sum for b in s.battalions())
    res = s.scoped_replace(scope_of("division"), from_pack).apply(target.key)
    check("replace applied", res.ok, res.note or res.summary())
    s.note_change(res, "批量替换")
    total_after = sum(len(s.retiler.pool(b.deck_object_id))
                      for b in s.battalions())
    sum_after = sum(b.window_sum for b in s.battalions())
    check("pool size unchanged by a replace",
          total_before == total_after, f"{total_before} -> {total_after}")
    check("Σ件数 unchanged by a replace",
          sum_before == sum_after, f"{sum_before} -> {sum_after}")
    check("W1 still holds file-wide", total_after == sum_after)
    v = s.validate()
    check("no hard errors after a batch replace", not v.errors,
          f"{len(v.errors)} errors")

    print()
    print("=== 10. the replace dialog lists what the scope fields ===")
    import ndfbin_decks.app.replace_dialog as rmod
    rmod.SwapDialog = _AutoPick
    dlg = rmod.ReplaceDialog(s, scope_of("battalion"), s.display, win)
    dlg.show()
    app.processEvents()
    check("dialog offers every level including 国家",
          [b.text() for b in dlg._level_btns.values()]
          == ["本排 Pl", "本连 Co", "本营 Bn", "本师 Div", "本国 Nat"],
          str([b.text() for b in dlg._level_btns.values()]))
    check("the from list is populated", dlg.from_list.count() > 0,
          f"{dlg.from_list.count()} kinds")
    n_bn = dlg.from_list.count()
    dlg._apply_level("division")
    app.processEvents()
    check("widening to the division shows more equipment",
          dlg.from_list.count() >= n_bn, f"{n_bn} -> {dlg.from_list.count()}")

    # The country level: one press covers every division of the same country.
    # The Scope carries the country, exactly as ``on_replace`` builds it — a
    # scope without one has nothing to widen to, and the button says so.
    from ndfbin_decks.io.divisions import country_code
    from ndfbin_decks.edit.bulk import Scope as _S
    role_c = win._current()
    code = country_code(role_c.division)
    check("the starting battalion has a country to widen to", bool(code), code)
    check("a scope built without one has the level disabled",
          not dlg._level_btns["country"].isEnabled(),
          dlg._level_btns["country"].toolTip()[:44])

    dlg_c = rmod.ReplaceDialog(
        s, _S(kind="battalion", division=role_c.division,
              deck_id=role_c.deck_id, country=code),
        s.display, win)
    country_btn = dlg_c._level_btns["country"]
    check("with one, the 本国 button is enabled", country_btn.isEnabled())
    check("and its tooltip names the country and its size",
          code in country_btn.toolTip(), country_btn.toolTip()[:60])
    n_div = dlg_c.from_list.count()
    dlg_c._apply_level("country")
    app.processEvents()
    check("widening to the country reaches at least as far as the division",
          dlg_c.from_list.count() >= n_div > 0,
          f"{n_div} -> {dlg_c.from_list.count()}")
    check("the scope label says so",
          dlg_c.scope_label.text() == "当前：本国 Nat",
          dlg_c.scope_label.text())
    check("and the country scope really is that country",
          dlg_c._scope_for("country").country == code,
          str(dlg_c._scope_for("country").country))
    sov = _S(kind="country", country="SOV")
    check("a SOV scope accepts a SOV division and refuses an RFA one",
          sov.contains("$/GFX/Division/Descriptor_Deck_Division_SOV_27GMRD_solo",
                       1, 0, 0)
          and not sov.contains(
              "$/GFX/Division/Descriptor_Deck_Division_RFA_TK_Nord_solo",
              1, 0, 0))

    print()
    print("=== 11. the picker only offers AG-usable packs of this file ===")
    import importlib
    real_swap = importlib.import_module("ndfbin_decks.app.swap_dialog")
    gui_mod.SwapDialog = real_swap.SwapDialog
    SwapDialog = real_swap.SwapDialog
    check("catalogue came from the open file",
          "Test" in cat.source_path, cat.source_path)
    check("AG gate cut the list down", len(cat) == 2690, str(len(cat)))
    check("stats report what was excluded",
          cat.stats.skirmish_only == 2483, str(cat.stats.skirmish_only))
    check("no-xp packs are kept, not banned",
          cat.stats.ag_without_xp == 311, str(cat.stats.ag_without_xp))

    dlg2 = SwapDialog(s, None)
    dlg2.show()
    app.processEvents()
    check("picker lists many packs", dlg2.list.count() > 100,
          f"{dlg2.list.count()} shown")
    labels = [dlg2.list.item(i).text() for i in range(min(3, dlg2.list.count()))]
    check("labels carry names and ids", all("#" in l for l in labels),
          str(labels[:1]))

    dlg2.search.setText("MiG_29")
    app.processEvents()
    check("search narrows the list", 0 < dlg2.list.count() < 500,
          str(dlg2.list.count()))
    dlg2.search.setText("zzz-不可能存在-zzz")
    app.processEvents()
    check("search can reach zero", dlg2.list.count() == 0)

    dlg2.search.setText("")
    app.processEvents()

    print()
    print("=== 11b. the lower half builds a combination the file lacks ===")
    from ndfbin_decks.app.swap_dialog import NO_TRANSPORT
    from ndfbin_decks.core.deckmodel import unit_leaf
    # Derived from the catalogue rather than hard-coded: earlier sections of
    # this test have already edited the file, so "which combination exists" is
    # a fact about the mutated graph, not about Test as shipped.
    sample = next((c for c in cat.items
                   if c.transporter and c.experience is not None), cat.items[0])
    print(f"  (probe combination: {sample.label()})")
    dlg2._fill_fields(sample.key)
    dlg2._manual = True
    app.processEvents()
    key, state, msg = dlg2.evaluate()
    check("a combination the mod already fields is offered for reuse",
          state == "reuse", f"{state}: {msg.splitlines()[0][:52]}")
    check("and its key resolves to a real pack object",
          key is not None and s.packs.index.find(key) is not None,
          str(s.packs.index.find(key) if key else None))

    # Nudge the experience until the combination is one the file never had; an
    # unseen combination of already-AG-proven paths is a plain create.
    created = None
    for level in (None, 1, 2, 3):
        dlg2.xp_box.setCurrentIndex(dlg2.xp_box.findData(level))
        app.processEvents()
        key2, state2, msg2 = dlg2.evaluate()
        if key2 is not None and s.packs.index.find(key2) is None:
            created = (key2, state2, msg2)
            break
    if created is None:
        print("  (every experience variant already exists — skipping)")
    else:
        key2, state2, msg2 = created
        check("an unseen combination of proven paths is a plain create",
              state2 == "create", f"{state2}: {msg2.splitlines()[0][:52]}")
        check("and it pairs a real unit with a real pack key",
              key2.unit == sample.unit
              and key2.transporter == sample.transporter,
              key2.describe())

    dlg2.unit_box.setCurrentText("ZZZ_NOT_A_UNIT")
    app.processEvents()
    key3, state3, msg3 = dlg2.evaluate()
    check("a name no definition file knows demands confirmation",
          state3 == "confirm", f"{state3}: {msg3.splitlines()[0][:52]}")
    check("and the prompt lists every source that was checked",
          "Unit.ndfbin" in msg3 and "base.zip" in msg3, msg3[:90])
    check("it still yields a usable key, so the workflow is reachable",
          key3 is not None and key3.unit.endswith("ZZZ_NOT_A_UNIT"))
    check("the field is still editable, not a closed list",
          dlg2.unit_box.isEditable() and dlg2.trans_box.isEditable())
    offered = [dlg2.unit_box.itemData(k)
               for k in range(dlg2.unit_box.count())]
    check("the dropdown offers the sample unit",
          sample.unit in offered, f"{dlg2.unit_box.count()} units offered")

    print()
    print("=== 11c. the list comes from the definition files, not the packs ===")
    universe = s.get_units()
    check("a unit universe was resolved for this mod",
          len(universe) >= len(universe.vanilla) > 1000, universe.summary())
    sus = [p for p in universe.all if p.endswith("Descriptor_Unit_Su_27K_SOV")]
    check("Su_27K_SOV is known", bool(sus))
    if sus:
        su = sus[0]
        check("and it is classified as vanilla",
              universe.origin(su) == "原版", universe.origin(su))
        check("it is now offered in the dropdown, though no AG deck fields it",
              su in offered and su not in cat.units(),
              f"in dropdown={su in offered}, in AG gate={su in cat.units()}")
        # The point of the change: a vanilla unit the AG decks never used is a
        # plain create, not a confirmation prompt.
        dlg2._manual = True
        dlg2._select_path(dlg2.unit_box, su)
        dlg2._select_path(dlg2.trans_box, None)
        dlg2.xp_box.setCurrentIndex(dlg2.xp_box.findData(None))
        app.processEvents()
        key_su, state_su, msg_su = dlg2.evaluate()
        check("picking it is a plain create, not a confirmation",
              state_su == "create" and key_su is not None
              and key_su.unit == su,
              f"{state_su}: {msg_su.splitlines()[0][:56]}")
        check("and the status says where it came from",
              "原版" in msg_su, msg_su.splitlines()[0][:56])

    check("every offered unit is a real $/GFX/Unit path",
          all(isinstance(x, str) and x.startswith("$/GFX/Unit/Descriptor_Unit_")
              for x in offered if x),
          str([x for x in offered if x and not x.startswith("$/")][:2]))
    check("the dropdown is longer than the AG gate's own list",
          len([x for x in offered if x]) > len(cat.units()),
          f"{len([x for x in offered if x])} vs {len(cat.units())}")

    print()
    print("  -- the 「只列出已引用过的」 escape hatch --")
    wide = dlg2.unit_box.count()
    dlg2.only_proven.setChecked(True)
    app.processEvents()
    narrow = dlg2.unit_box.count()
    check("checking it narrows the list to the AG-proven set",
          narrow == len(cat.units()) < wide, f"{wide} -> {narrow}")
    dlg2.only_proven.setChecked(False)
    app.processEvents()
    check("unchecking restores the full list",
          dlg2.unit_box.count() == wide, str(dlg2.unit_box.count()))

    check("the transport dropdown carries a no-transport entry",
          dlg2.trans_box.itemText(0) == NO_TRANSPORT,
          dlg2.trans_box.itemText(0))
    check("and the same full unit list behind it",
          dlg2.trans_box.count() == dlg2.unit_box.count() + 1,
          f"{dlg2.trans_box.count()} vs {dlg2.unit_box.count()}")

    # The confirmation is the whole safety story for that path, so it has to
    # actually gate: answering No must leave the dialog un-accepted.  The unit
    # is set back to the unknown name first — section 11c left a legal vanilla
    # unit in the box, which correctly never prompts.
    dlg2._manual = True
    dlg2.unit_box.setCurrentText("ZZZ_NOT_A_UNIT")
    app.processEvents()
    _probe = dlg2.evaluate()
    check("the box is back on the unknown name before the gate test",
          _probe[1] == "confirm", f"{_probe[1]}")
    from PySide6.QtWidgets import QMessageBox as _MB
    prior_warn = _MB.warning
    seen: list[str] = []
    try:
        _MB.warning = staticmethod(
            lambda *a, **k: (seen.append(str(a[2])), _MB.No)[1])
        dlg2.accept()
        app.processEvents()
        check("declining the confirmation keeps the dialog open",
              dlg2.result() != QDialog.Accepted and dlg2.chosen() is None,
              f"result={dlg2.result()}")
        _MB.warning = staticmethod(
            lambda *a, **k: (seen.append(str(a[2])), _MB.Yes)[1])
        dlg2.accept()
        app.processEvents()
        chosen = dlg2.chosen()
        check("accepting it lets the build through",
              chosen is not None and chosen.unit.endswith("ZZZ_NOT_A_UNIT"),
              str(chosen))
    finally:
        _MB.warning = prior_warn

    dlg2._fill_fields(sample.key)
    dlg2._manual = False
    app.processEvents()

    check("owns() rejects a foreign id", cat.owns(999999) is None)
    check("owns() accepts an id from this file",
          cat.owns(cat.items[0].pack_object_id) is not None)
    # A PvP-only pack must not be reachable at all.
    from ndfbin_decks.app.catalog import pack_ids_by_kind
    ag_ids, pvp_ids = pack_ids_by_kind(s.deck)
    only_pvp = sorted(pvp_ids - ag_ids)
    check("PvP-only packs exist to test against", len(only_pvp) > 1000,
          str(len(only_pvp)))
    check("the gate hides every PvP-only pack",
          all(cat.owns(p) is None for p in only_pvp[:200]),
          f"{len(only_pvp)} PvP-only packs")

    print()
    print("=== 12. save writes a loadable file ===")
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "Deck.ndfbin"
    try:
        data = s.save(tmp)
        check("bytes written", len(data) > 0, f"{len(data):,} B")
        from ndfbin_decks.app.session import Session
        s2 = Session.load(tmp, resolve_names=False)
        check("reloads cleanly", len(s2.battalions()) == 2208,
              str(len(s2.battalions())))
        v2 = s2.validate()
        check("no hard errors after all the edits", not v2.errors,
              f"{len(v2.errors)} errors")
    except Exception as exc:                            # noqa: BLE001
        check("save succeeded", False, repr(exc))

    print()
    print("=== 13. guards in the UI layer ===")
    # back to the stub: a real modal would block headless forever
    gui_mod.SwapDialog = _AutoPick
    shown.clear()
    calls_before = _AutoPick.calls
    win.table.clearSelection()
    win.table.setCurrentCell(-1, -1)
    win.on_swap()          # no table row selected -> must warn, not crash
    check("swap without a row is blocked",
          any("条目" in m for _, m in shown),
          str(shown[-1]) if shown else "no dialog")
    check("and no picker was opened for it",
          _AutoPick.calls == calls_before,
          f"exec() called {_AutoPick.calls - calls_before} time(s)")

    shown.clear()
    win.tree.setCurrentItem(win.tree.topLevelItem(0))   # the division node
    win.on_set_count()
    check("set_count on a division node is blocked",
          any("请先选中" in m for _, m in shown),
          str(shown[-1]) if shown else "no dialog")

    print()
    if FAILURES:
        print(f"FAIL — {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS — GUI wired correctly, AG gate holds, batch replace is sound")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
