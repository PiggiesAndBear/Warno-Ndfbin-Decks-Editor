"""Replace one equipment across a chosen level of the organisation.

Why this is a dialog of its own rather than another button: **replace is not
pick**.  Picking touches one entry; replacing rewrites every entry in the scope
that uses the same equipment.  Before pressing the button the modder has to see
the blast radius — how many battalions, companies, platoons, entries and
individual units move — so the dialog shows it live and recomputes it on every
change of scope or target.

The scope level is four mutually exclusive buttons, widest last, because
widening the scope is the whole point of the feature and must be impossible to
do by accident.  The buttons carry the same 师/营/连/排 vocabulary as the tree,
so the dialog and the tree can never disagree about what a level means.

The picker on the right is the same :class:`~.swap_dialog.SwapDialog` used for a
single swap — one equipment list, one AG-provenance gate, no second place where
"which packs are legal" could drift.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

# ``LEVEL_LABELS`` comes from the same module as ``LEVELS``: a second copy was
# how the 国家 level ended up with a button and no label.
from ..edit.bulk import LEVELS, LEVEL_LABELS, Scope
from .swap_dialog import SwapDialog


class ReplaceDialog(QDialog):
    """Choose *what* to replace, *with what*, and *how far* it reaches."""

    def __init__(self, session, scope: Scope, display, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量替换装备")
        self.resize(1040, 680)
        self.session = session
        self.display = display
        self._entry_scope = scope
        self._level = scope.kind if scope.kind in LEVELS else "battalion"
        self._from_pack: int | None = None
        self._to_key = None
        self._to_label = ""
        self._rows: list[tuple[int, int, int]] = []

        root = QVBoxLayout(self)

        intro = QLabel(
            "把所选<b>范围</b>内用到左栏装备的每一条，一次性换成右栏装备。<br>"
            "<b>件数与槽位顺序不变</b>——游戏仍按原来的数量派兵，只是换了装备；"
            "因此该操作不会产生非法布局。")
        intro.setWordWrap(True)
        root.addWidget(intro)

        root.addWidget(self._build_scope_box())

        columns = QHBoxLayout()
        columns.addLayout(self._build_from_column(), 1)
        columns.addLayout(self._build_middle(), 0)
        columns.addLayout(self._build_to_column(), 1)
        root.addLayout(columns, 1)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_btn = buttons.button(QDialogButtonBox.Ok)
        self.ok_btn.setText("替换")
        self.ok_btn.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._apply_level(self._level, initial=True)

    # -- widgets -----------------------------------------------------------

    def _build_scope_box(self) -> QWidget:
        box = QGroupBox("范围")
        row = QHBoxLayout(box)
        row.addWidget(QLabel("替换范围："))
        self._level_btns: dict[str, QPushButton] = {}
        for kind in LEVELS:
            btn = QPushButton(LEVEL_LABELS[kind])
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setToolTip(f"影响范围：{LEVEL_LABELS[kind]} 之内的全部条目")
            if kind == "country":
                # The country is read off the division label, so a division
                # without one has no country to widen to.  Disabled rather
                # than hidden: the level exists, it just cannot apply *here*.
                country = self._entry_scope.country
                if country:
                    btn.setToolTip(
                        f"影响范围：{LEVEL_LABELS[kind]} —— {country} 的全部师，"
                        f"共 {len(self._level_scope_divisions(country))} 个")
                else:
                    btn.setEnabled(False)
                    btn.setToolTip(
                        "起始营所在师没有可识别的国家前缀（例如未标师的营），"
                        "无法按国家替换")
            btn.clicked.connect(lambda _c=False, k=kind: self._apply_level(k))
            row.addWidget(btn)
            self._level_btns[kind] = btn
        row.addStretch(1)
        self.scope_label = QLabel("")
        row.addWidget(self.scope_label)
        return box

    def _build_from_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.addWidget(QLabel("<b>范围内用到的装备</b>"))
        self.from_list = QListWidget()
        self.from_list.setAlternatingRowColors(True)
        self.from_list.currentItemChanged.connect(
            lambda *_: self._refresh_summary())
        col.addWidget(self.from_list, 1)
        self.from_count = QLabel("")
        col.addWidget(self.from_count)
        return col

    def _build_middle(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.addStretch(1)
        arrow = QLabel("→")
        arrow.setAlignment(Qt.AlignCenter)
        col.addWidget(arrow)
        col.addStretch(1)
        return col

    def _build_to_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.addWidget(QLabel("<b>换成</b>"))
        self.to_btn = QPushButton("选择装备…")
        self.to_btn.clicked.connect(self._on_pick_target)
        col.addWidget(self.to_btn)
        self.to_label = QLabel("<i>尚未选择</i>")
        self.to_label.setWordWrap(True)
        col.addWidget(self.to_label)
        col.addStretch(1)
        return col

    # -- scope -------------------------------------------------------------

    def _level_scope_divisions(self, country: str) -> list:
        """The divisions a country-wide replace would cover."""
        return [d for d in self.session.divisions() if d.country == country]

    def _scope_for(self, kind: str) -> Scope:
        """The entry scope widened (or narrowed) to ``kind``.

        The coordinates come from wherever the user was in the tree, so opening
        on a platoon and widening to 师 still targets *that* division rather
        than the first one in the list.
        """
        e = self._entry_scope
        return Scope(kind=kind, division=e.division, deck_id=e.deck_id,
                     ci=e.ci, si=e.si, country=e.country)

    def _apply_level(self, kind: str, *, initial: bool = False) -> None:
        self._level = kind
        btn = self._level_btns.get(kind)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
        self.scope_label.setText(f"当前：{LEVEL_LABELS[kind]}")
        self._reload_from()

    def _reload_from(self) -> None:
        scope = self._scope_for(self._level)
        executor = self.session.scoped_replace(scope, -1)
        self._rows = executor.usage()
        self.from_list.clear()
        for pack_id, entries, units in self._rows:
            key = self.session.packs.pack_key(pack_id)
            name = self.display(key.unit) if key else f"pack#{pack_id}"
            bits = [name]
            if key and key.transporter:
                bits.append(f"[{self.display(key.transporter)}]")
            if key and key.experience is not None:
                bits.append(f"经验{key.experience}")
            bits.append(f"— {entries} 条 / {units} 件")
            item = QListWidgetItem(" ".join(bits))
            item.setData(Qt.UserRole, pack_id)
            item.setToolTip(f"pack#{pack_id}\n范围内 {entries} 条装备，共 {units} 件")
            self.from_list.addItem(item)
        self.from_count.setText(
            f"{len(self._rows)} 种装备" if self._rows else "范围内没有装备")
        if self._rows:
            self.from_list.setCurrentRow(0)
        self._refresh_summary()

    # -- target ------------------------------------------------------------

    def _on_pick_target(self) -> None:
        row = self.from_list.currentRow()
        current = None
        if 0 <= row < len(self._rows):
            current = self.session.packs.pack_key(self._rows[row][0])
        dlg = SwapDialog(self.session, current, self)
        dlg.setWindowTitle("选择替换用的装备")
        if dlg.exec() != QDialog.Accepted:
            return
        key = dlg.chosen()
        if key is None:
            return
        self._to_key = key
        self._to_label = (f"{self.display(key.unit)}"
                          + (f" [{self.display(key.transporter)}]"
                             if key.transporter else "")
                          + (f" 经验{key.experience}"
                             if key.experience is not None else " 继承经验"))
        self.to_label.setText(self._to_label)
        self._refresh_summary()

    # -- summary -----------------------------------------------------------

    def _refresh_summary(self) -> None:
        row = self.from_list.currentRow()
        if not (0 <= row < len(self._rows)) or self._to_key is None:
            self.summary.setText("选择左侧装备与右侧目标后显示影响范围。")
            self.ok_btn.setEnabled(False)
            return
        from_pack = self._rows[row][0]
        if from_pack == _pack_id_for(self.session, self._to_key):
            self.summary.setText("目标与来源相同，无需替换。")
            self.ok_btn.setEnabled(False)
            return
        executor = self.session.scoped_replace(
            self._scope_for(self._level), from_pack)
        survey = executor.survey()
        self.summary.setText(
            f"<b>影响范围</b>：{survey.summary()}<br>"
            f"件数与槽位顺序保持不变；共改写 {len(survey.decks)} 个营。")
        self.ok_btn.setEnabled(bool(survey.entries))

    # -- result ------------------------------------------------------------

    def result(self) -> tuple[Scope, int, object] | None:
        """``(scope, from_pack_id, to_key)`` when everything was chosen."""
        row = self.from_list.currentRow()
        if not (0 <= row < len(self._rows)) or self._to_key is None:
            return None
        return self._scope_for(self._level), self._rows[row][0], self._to_key


def _pack_id_for(session, key) -> int | None:
    """The pack object id a key would resolve to, or ``None``."""
    return session.packs.index.find(key)
