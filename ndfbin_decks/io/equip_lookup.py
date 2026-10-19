"""装备 / pack 速查表：从 mod 编译后的 ``.ndfbin`` 生成一份单文件 HTML。

**它回答什么问题.** 「这件装备能不能进将军模式？不能的话缺什么？」——
所以表要同时给出三件事：装备是什么（名字/国家/角色/战略分类）、它有没有
pack（有 = 能直接进 AG）、以及 mod 相对原版新增了什么。

**数据从哪来.** 优先读 mod 自己的编译产物：

======================  ===============================================
``GFX/Unit``            ``TEntityDescriptor``（装备）+ 挂在它身上的模块
``GFX/Deck``            ``TDeckPackDescriptor``（AG pack）+ ``TDeckDescriptor``
======================  ===============================================

**三处 ``.ndf`` → ``.ndfbin`` 的落差**，每一处都有确定的解法：

1. **装备名**。编译产物里没有对象名，但 ``ClassNameForDebug`` 100% 可读
   （``Unit_2K11_KRUG_DDR``），对象名由 ``"Descriptor_" + ClassNameForDebug``
   重建。``NameToken`` 是 ``loc_hash``，只能靠 mod 自带的 ``.dic`` 解，
   覆盖率天生很低（原版词条封在 ``Data/PC/*.dat`` 里），所以它是**附加列**。
2. **两个枚举字段是整数**。``Coalition`` 与 ``TypeStrategicCount`` 编译后
   只剩 ``int32`` —— 但 ``base.zip`` 里有权威的枚举定义
   （``GameData/Gameplay/Constantes/Enumerations/*.ndf``，形如
   ``Infantry is 12``），所以**不需要猜**。取不到时回落到内置表并写明。
3. **pack 没有名字**。``TDeckPackDescriptor`` 只有 ``UnitDescriptor`` /
   ``TransporterDescriptor`` / ``ExperienceLevel`` / ``Number`` 四个字段，
   连 export 都没有。原版那批可以按内容签名从 ``StrategicPacks.ndf`` 反查
   回原名；mod 新加的只能给一个合成标签（``装备 [载具] · XP1``）。

**缺文件的边界.** ``GFX/Unit`` 缺了就**不导**——那说明这个 mod 没改装备，
一张全来自原版的表会被误读成「我的 mod」。``GFX/Deck`` 缺了则退到基线：
packs 只存在于这个文件里，没有它 mod 就不可能有自己的 pack，用原版的是
**语义正确**而不是凑数，但页面顶部必须写清楚。

**页面本身是中文文档.** 与 ``doc/使用教程.md`` 同一类东西 —— 它是导出给人看的
成品，不是界面控件，所以正文不跟界面语言切换；而错误、提醒这些**会弹在对话框里**
的话都走 :func:`tr`，该翻的照翻。

**所有「对不上」都要收集起来.** 悬空引用、剥前缀才连上的 FOB、没有 UI
模块的影子单位 —— 静默丢掉的话，用户只会看到「装备少了一件」却不知道
为什么。这些全部进 :attr:`Lookup.notes`，并在 HTML 顶部列出来。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..core import cndf_codec
from ..i18n import tr
from . import localisation, modlocator, unit_universe

#: ``[Config]`` 里这两个槽位决定「哪些文件是这个 mod 自己的」。
SLOT_UNIT = "GFX/Unit"
SLOT_DECK = "GFX/Deck"

#: 槽位 -> 部署目录下的相对路径。**只认这一条**：同一个 mod 里可能同时存在
#: ``Gen/NDF/GFX/Deck.ndfbin``（游戏读的）和 ``Gen/NDF/Deck.ndfbin``（历史遗留），
#: 读错那个所有数字整体偏 —— 实测样本 mod 是 5415 与 5248 pack 的差别。
SLOT_FILES = {
    SLOT_UNIT: ("Gen", "NDF", "GFX", "Unit.ndfbin"),
    SLOT_DECK: ("Gen", "NDF", "GFX", "Deck.ndfbin"),
}

#: ``base.zip`` 里的枚举定义。它们是**权威**的：显式写了整数，不是按顺序猜。
ENUM_DIR = "GameData/Gameplay/Constantes/Enumerations"

#: ``base.zip`` 里装备与 pack 的明文源，只用来取「名字清单」与「原版 pack 名」。
BASE_UNIT_FILES = (
    "GameData/Generated/Gameplay/Gfx/UniteDescriptor.ndf",
    "GameData/Generated/Gameplay/Gfx/BuildingDescriptors.ndf",
)
BASE_PACK_FILE = "GameData/Generated/Gameplay/Decks/StrategicPacks.ndf"
BASE_DECK_FILE = "GameData/Generated/Gameplay/Decks/StrategicDecks.ndf"

#: 取不到 ``base.zip`` 时的回落表。来源即上面 ENUM_DIR 的两个文件，
#: 实测逐项一致；游戏加值时 ``base.zip`` 会先一步反映出来，所以它只是兜底。
STRATEGIC_FALLBACK: dict[int, str] = {
    0: "CMD_Inf", 1: "CMD_Veh", 2: "CMD_Tank", 3: "CMD_Hel", 4: "Reco",
    5: "Reco_Hel", 6: "Reco_Inf", 7: "Reco_Veh", 8: "Supply", 9: "Supply_Hel",
    10: "Support", 11: "Transport", 12: "Infantry", 13: "Engineer",
    14: "Armor", 15: "Armor_Heavy", 16: "Ifv", 17: "AA", 18: "AA_Veh",
    19: "AA_Hel", 20: "Manpad", 21: "AT", 22: "AT_Veh", 23: "AT_Gun",
    24: "AT_Hel", 25: "Mortar", 26: "Howitzer", 27: "Mlrs", 28: "Hel_Support",
    29: "Hel_Transport", 30: "Air_AA", 31: "Air_Sead", 32: "Air_AT",
    33: "Air_Support", 34: "Battalion", 35: "NotCounted", 36: "Length",
}
COALITION_FALLBACK: dict[int, str] = {0: "NATO", 1: "PACT"}

#: 国家码 -> 显示名。只覆盖原版出现过的；mod 自己发明的码原样显示，
#: 白名单会在换 mod 的那一刻失效。
COUNTRY_NAMES: dict[str, str] = {
    "SOV": "苏联", "US": "美国", "FR": "法国", "UK": "英国", "RFA": "西德",
    "DDR": "东德", "POL": "波兰", "TCH": "捷克斯洛伐克", "BEL": "比利时",
    "NL": "荷兰", "ESP": "西班牙", "DK": "丹麦", "CAN": "加拿大",
    "LUX": "卢森堡",
}

#: ``UnitRole`` -> 中文。同样只作显示，遇到没登记的值原样输出。
ROLE_NAMES: dict[str, str] = {
    "reco": "侦察", "appui": "火力支援", "infantry": "步兵", "AA": "防空",
    "transport": "输送车", "AT": "反坦克", "armor": "坦克", "supply": "补给",
    "hq_inf": "步兵指挥", "howitzer": "榴弹炮", "hq_veh": "车辆指挥",
    "mortar": "迫击炮", "hq_tank": "坦克指挥", "engineer": "工兵",
    "ifv": "步战车", "mlrs": "火箭炮", "sead": "反辐射", "hq_helo": "直升机指挥",
    "uav": "无人机",
}

#: 华约国家码。只用来发现「国家与 Coalition 字段打架」的个案 —— 编译器会
#: 省略默认值，所以字段缺失就等于 NATO(0)；万一某个华约单位漏写了这一行，
#: 表里会显示成 NATO / 苏联，看着像 bug。这种情况要报出来，而不是悄悄改。
PACT_COUNTRIES = frozenset({"SOV", "DDR", "POL", "TCH"})
NATO_COUNTRIES = frozenset({"US", "FR", "UK", "RFA", "BEL", "NL", "ESP",
                            "DK", "CAN", "LUX"})

#: 装备的判据：**这个实体被导出成 ``$/GFX/Unit/Descriptor_Unit_*``**。
#:
#: ★★ 不能用 ``ClassNameForDebug`` 的前缀 —— 那是**作者自己起的显示名**，
#: 不带 ``Unit_`` 的完全正常。实测 ``Honor Or Death``：3701 个可选单位里
#: 有 751 个的调试名是 ``2S22_BOGDANA_UKR``、``AAteam_BARKAN_ISR`` 这种，
#: 按前缀筛会**整批丢掉**，而 pack 与编辑器的部队下拉框都按导出名认它们。
#:
#: 导出路径也是 pack 引用单位时用的那一个字符串，所以拿它当主键，
#: 「清单里有」与「编辑器认得出」天然一致。规则与
#: :data:`ndfbin_decks.io.unit_universe.UNIT_PATH_RE` 是同一条 —— 复用，
#: 免得两处各写一份、哪天又走岔。
UNIT_PATH_RE = unit_universe.UNIT_PATH_RE

#: 没有这条导出的 ``TEntityDescriptor`` 就不是可选单位：Mimetic 影子单位
#: （模板实例化、0 个 pack 指向）与 District 贴图区块都在这一类里。
#: 实测两个 mod 上「有导出」与「有 UI 模块」是**同一批对象**，所以这里只取前者,
#: 它才是 pack 真正指向的东西；万一某个导出缺 UI 模块，那几行会缺角色/价格,
#: 但**仍然在表里**，不会像以前那样整条消失。

#: UI 模块。它提供名字/角色/价格，但**不是**装备的判据（判据是导出名，见上）：
#: 少了它那几行会空着，可它仍然是 pack 能指向的东西，不该从表里消失。
UI_MODULE = "TUnitUIModuleDescriptor"
TYPE_MODULE = "TTypeUnitModuleDescriptor"
FORM_MODULE = "TFormationModuleDescriptor"


class LookupUnavailable(RuntimeError):
    """这个 mod 导不出表，消息是给人看的一句话。"""


@dataclass
class Equipment:
    """一行装备。``descriptor`` 是从 ``ClassNameForDebug`` 重建的对象名。"""

    descriptor: str
    class_name: str
    name: str = ""
    token_hex: str = ""
    coalition: str = ""
    country: str = ""
    role: str = ""
    strategic: str = ""
    formation: str = ""
    price: str = ""
    icon: str = ""
    kind: str = "unit"
    is_new: bool = False
    #: 有它作为 ``Unit`` 的 pack 数 / 只作为 ``Transporter`` 的 pack 数
    packs_unit: int = 0
    packs_transport: int = 0

    @property
    def label(self) -> str:
        return self.name or self.class_name


@dataclass
class PackRow:
    """一行 pack。``name`` 只有从基线反查到时才有值。"""

    object_id: int = -1
    name: str = ""
    unit: str = ""
    transport: str = ""
    xp: int = 0
    decks: int = 0


@dataclass
class Lookup:
    """一张表要渲染的全部数据 + 它的来历。"""

    mod_name: str = ""
    mod_label: str = ""
    mod_source: str = ""
    generated: str = ""
    equipments: list[Equipment] = field(default_factory=list)
    packs: list[PackRow] = field(default_factory=list)
    decks: int = 0
    #: 一份文件对应一句来源说明，原样进页面顶部
    sources: list[str] = field(default_factory=list)
    #: 口径问题（悬空引用、影子单位、剥前缀…），一条一句
    notes: list[str] = field(default_factory=list)
    #: 悬空的 pack → 装备引用
    dangling: list[str] = field(default_factory=list)
    #: 没有 $/GFX/Unit 导出、未计入装备表的对象名
    skipped: list[str] = field(default_factory=list)
    #: 词条解析覆盖，``(已解出, 总数)``
    named: tuple[int, int] = (0, 0)
    elapsed: float = 0.0

    # -- 派生统计，全部由同一份 equipments 算出来，避免三处各算一遍 --------

    def counts(self) -> dict:
        have = sum(1 for e in self.equipments if e.packs_unit)
        veh = sum(1 for e in self.equipments
                  if not e.packs_unit and e.packs_transport)
        none_ = len(self.equipments) - have - veh
        used = sum(1 for p in self.packs if p.decks)
        return {
            "total": len(self.equipments),
            "new": sum(1 for e in self.equipments if e.is_new),
            "have": have,
            "veh": veh,
            "none": none_,
            "packs": len(self.packs),
            "packs_used": used,
            "orphan": len(self.packs) - used,
            "decks": self.decks,
        }

    def country_rows(self) -> list[tuple]:
        """``[(码, 名, 有 pack, 仅载具, 无 pack, 新增, 合计)]``，按合计降序。"""
        acc: dict[str, list[int]] = {}
        for e in self.equipments:
            row = acc.setdefault(e.country or "?", [0, 0, 0, 0, 0])
            row[4] += 1
            if e.is_new:
                row[3] += 1
            if e.packs_unit:
                row[0] += 1
            elif e.packs_transport:
                row[1] += 1
            else:
                row[2] += 1
        out = [(code, COUNTRY_NAMES.get(code, code), *vals) for code, vals in acc.items()]
        return sorted(out, key=lambda r: (-r[6], r[0]))

    def role_rows(self) -> list[tuple[str, str, int]]:
        acc: dict[str, int] = {}
        for e in self.equipments:
            if e.role:
                acc[e.role] = acc.get(e.role, 0) + 1
        return [(k, ROLE_NAMES.get(k, ""), n)
                for k, n in sorted(acc.items(), key=lambda kv: -kv[1])]

    def strategic_rows(self) -> list[tuple[str, int]]:
        acc: dict[str, int] = {}
        for e in self.equipments:
            if e.strategic:
                acc[e.strategic] = acc.get(e.strategic, 0) + 1
        return sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))

    def coalition_rows(self) -> list[tuple[str, int]]:
        acc: dict[str, int] = {}
        for e in self.equipments:
            key = e.coalition or "（未标注）"
            acc[key] = acc.get(key, 0) + 1
        return sorted(acc.items(), key=lambda kv: -kv[1])


# ---------------------------------------------------------------------------
# base.zip：基线、枚举、原版 pack 名
# ---------------------------------------------------------------------------


@dataclass
class Baseline:
    """``Mods/ModData/base.zip`` 里那点能用得上的东西。

    只读三类内容，**不做 NDF 解析**：枚举定义（显式整数）、装备导出名清单、
    pack / 牌组的规整块。三者都是 ModGen 生成的机器格式，块边界稳定。
    """

    path: Path | None = None
    unit_names: set[str] = field(default_factory=set)
    strategic: dict[int, str] = field(default_factory=dict)
    coalitions: dict[int, str] = field(default_factory=dict)
    packs: dict[str, dict] = field(default_factory=dict)      # 名 -> {unit, trans, xp}
    decks: dict[str, list[str]] = field(default_factory=dict)  # 牌组名 -> pack 名
    #: ``(装备尾名, 载具尾名, xp)`` -> 出现过的 pack 名
    signatures: dict[tuple, list[str]] = field(default_factory=dict)
    error: str = ""
    elapsed: float = 0.0

    @property
    def usable(self) -> bool:
        return bool(self.unit_names)


#: 基线只解析一次：4 个文本加起来约 14 MB，导出多个 mod 时会反复要同一份。
_BASELINE_CACHE: dict[Path, tuple[float, Baseline]] = {}

_PACK_RE = re.compile(
    r"^(?:export\s+)?Descriptor_(StrategicPack_\w+)\s+is\s+DeckPackDescriptor\s*\(\s*(.*?)^\)",
    re.M | re.S)
_DECK_RE = re.compile(
    r"^export\s+Descriptor_Deck_(\w+)\s+is\s+TDeckDescriptor\s*\(\s*(.*?)^\)",
    re.M | re.S)
_UNIT_RE = re.compile(
    r"^export\s+Descriptor_Unit_(\w+)\s+is\s+TEntityDescriptor", re.M)
_ENUM_RE = re.compile(r"^\s+(\w+)\s+is\s+(\d+)", re.M)


def base_zip_path() -> Path | None:
    """``<WARNO>/Mods/ModData/base.zip`` —— ModGen 的原版模板快照。

    位置由 :func:`modlocator.warno_root` 推出来，不写死盘符：Steam 库可以
    在任何盘上。
    """
    try:
        root = modlocator.warno_root()
    except Exception:                                  # noqa: BLE001
        return None
    for candidate in (root / "Mods" / "ModData" / "base.zip",
                      root / "Mods" / "ModData" / "Base.zip"):
        if candidate.is_file():
            return candidate
    return None


def load_baseline(path: Path | None = None) -> Baseline:
    """读（并缓存）基线。缺 ``base.zip`` 时返回空对象而不是抛异常。"""
    path = path or base_zip_path()
    if path is None or not path.is_file():
        return Baseline(error=tr("找不到 base.zip（原版模板），新增标记与枚举名只能回落"))
    try:
        stamp = path.stat().st_mtime
    except OSError as exc:
        return Baseline(path=path, error=str(exc))
    hit = _BASELINE_CACHE.get(path)
    if hit is not None and hit[0] == stamp:
        return hit[1]

    base = Baseline(path=path)
    t0 = time.perf_counter()
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            for member in BASE_UNIT_FILES:
                if member in names:
                    base.unit_names |= set(
                        _UNIT_RE.findall(zf.read(member).decode("utf-8", "replace")))

            for enum_name, target in (("TypeStrategicDetailedCount", "strategic"),
                                      ("Coalition", "coalitions")):
                member = f"{ENUM_DIR}/{enum_name}.ndf"
                if member not in names:
                    continue
                text = zf.read(member).decode("utf-8", "replace")
                table = {int(num): name for name, num in _ENUM_RE.findall(text)}
                if table:
                    setattr(base, target, table)

            if BASE_PACK_FILE in names:
                text = zf.read(BASE_PACK_FILE).decode("utf-8", "replace")
                for m in _PACK_RE.finditer(text):
                    body = m.group(2)
                    unit = re.search(r"^\s*Unit\s*=\s*(\S+)", body, re.M)
                    trans = re.search(r"^\s*Transport\s*=\s*(\S+)", body, re.M)
                    xp = re.search(r"^\s*Xp\s*=\s*(\d+)", body, re.M)
                    name = "Descriptor_" + m.group(1)
                    base.packs[name] = {
                        "unit": unit.group(1) if unit else "",
                        "trans": trans.group(1) if trans else "",
                        "xp": int(xp.group(1)) if xp else 0,
                    }

            if BASE_DECK_FILE in names:
                text = zf.read(BASE_DECK_FILE).decode("utf-8", "replace")
                for m in _DECK_RE.finditer(text):
                    body = m.group(2)
                    lst = re.search(r"DeckPackList\s*=\s*\[(.*?)\]", body, re.S)
                    base.decks[m.group(1)] = (
                        re.findall(r"~/(\w+)", lst.group(1)) if lst else [])
    except (OSError, zipfile.BadZipFile) as exc:
        return Baseline(path=path, error=f"{type(exc).__name__}: {exc}")

    for name, rec in base.packs.items():
        sig = _signature(rec["unit"], rec["trans"], rec["xp"])
        base.signatures.setdefault(sig, []).append(name)
    base.elapsed = time.perf_counter() - t0
    _BASELINE_CACHE[path] = (stamp, base)
    return base


def _tail(ref: str) -> str:
    """``$/GFX/Unit/Descriptor_Unit_X`` -> ``Descriptor_Unit_X``（空引用 -> ``""``）。"""
    return str(ref or "").rsplit("/", 1)[-1]


def _bare(ref: str) -> str:
    """去掉 ``Descriptor_`` 与 ``Unit_``/``Building_``，得到两套名字的公共部分。"""
    name = _tail(ref)
    if name.startswith("Descriptor_"):
        name = name[len("Descriptor_"):]
    return re.sub(r"^(Unit|Building)_", "", name)


def _signature(unit: str, transport: str, xp: int) -> tuple:
    return (_bare(unit), _bare(transport), int(xp or 0))


# ---------------------------------------------------------------------------
# 解码
# ---------------------------------------------------------------------------


def _scalar(obj: dict, name: str):
    for prop in obj["properties"]:
        if prop["property_name"] == name:
            value = prop["value"]
            return value.get("value") if isinstance(value, dict) else value
    return None


def _raw(obj: dict, name: str):
    for prop in obj["properties"]:
        if prop["property_name"] == name:
            return prop["value"]
    return None


def _module_ids(obj: dict) -> list[int]:
    modules = _raw(obj, "ModulesDescriptors") or {}
    return [item.get("object_id") for item in modules.get("items") or []
            if isinstance(item, dict)]


def _resolve(path: Path) -> dict:
    """Decode one container, turning any failure into a sentence the user can act on."""
    try:
        _doc, info = cndf_codec.decode(path.read_bytes(), str(path))
    except Exception as exc:                           # noqa: BLE001
        raise LookupUnavailable(
            tr("读不了 {path}（{err}）", path=path,
               err=f"{type(exc).__name__}: {exc}")
        ) from exc
    return info


def _decode_enum(value, table: dict[int, str], fallback: str = "") -> str:
    """``int32`` 枚举 -> 名字。

    缺字段 = 0：编译器会**省略默认值**，所以 ``Coalition`` 缺失就是 NATO(0)、
    ``TypeStrategicCount`` 缺失就是 CMD_Inf(0)。这不是猜 —— 实测样本 mod 里
    所有北约国家的装备都没有 ``Coalition`` 字段，所有 PACT 的都是 1。
    """
    if value is None:
        return table.get(0, fallback)
    try:
        return table.get(int(value), fallback or f"#{value}")
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def slot_path(mod: modlocator.ModPaths, slot: str) -> Path | None:
    if mod.deploy is None:
        return None
    path = Path(mod.deploy).joinpath(*SLOT_FILES[slot])
    return path if path.is_file() else None


def build_lookup(mod: modlocator.ModPaths, *, lang: str = "SC") -> Lookup:
    """一个 mod 的完整速查数据。导不出时抛 :class:`LookupUnavailable`。"""
    t0 = time.perf_counter()
    lookup = Lookup(
        mod_name=mod.name,
        mod_label=mod.label or mod.name,
        mod_source=mod.source_label,
        generated=time.strftime("%Y-%m-%d %H:%M"),
    )

    unit_path = slot_path(mod, SLOT_UNIT)
    if unit_path is None:
        raise LookupUnavailable(tr(
            "这个 mod 没有 GFX/Unit（Gen/NDF/GFX/Unit.ndfbin），说明它没有改装备。\n"
            "没有装备表就没什么可导的 —— 想看出厂基线请用原版模板另做一份。"))

    base = load_baseline()
    strategic = base.strategic or STRATEGIC_FALLBACK
    coalitions = base.coalitions or COALITION_FALLBACK
    if not base.strategic:
        lookup.notes.append(tr(
            "枚举表没从 base.zip 读到，用的是内置回落表（来源：原版枚举 .ndf，"
            "游戏加值时可能滞后）。"))
    if base.error:
        lookup.notes.append(base.error)

    # ---- 装备 ---------------------------------------------------------
    unit_info = _resolve(unit_path)
    by_id = {o["id"]: o for o in unit_info["objects"]}
    resolver = localisation.NameResolver.from_mod(mod, lang)
    lookup.sources.append(tr("装备 · {what}", what=f"{unit_path.name}（{_size(unit_path)}）"))
    if not mod.has(SLOT_UNIT):
        lookup.notes.append(tr(
            "Config.ini 的 [Config] 段没有声明 GFX/Unit，但文件存在 —— 已照读；"
            "如果这个 mod 同时留着一份旧的 Unit.ndfbin，请确认读的是要用的那一份。"))

    #: object_id -> ``Descriptor_Unit_X``，来自文件自己的导出表。
    #: 这是单位的**身份**：pack 引用它、编辑器下拉框也用它。
    exported = {oid: path.rsplit("/", 1)[-1]
                for oid, path in (unit_info.get("exports") or {}).items()
                if isinstance(path, str) and UNIT_PATH_RE.match(path)}

    for obj in unit_info["objects"]:
        if obj["class"] != "TEntityDescriptor":
            continue
        descriptor = exported.get(obj["id"])
        class_name = _scalar(obj, "ClassNameForDebug")
        class_name = class_name if isinstance(class_name, str) else ""
        if descriptor is None:
            # 不是可选单位（Mimetic 影子单位 / 贴图区块）：报一句，不占行。
            lookup.skipped.append(class_name or f"#{obj['id']}")
            continue
        modules = [by_id[mid] for mid in _module_ids(obj) if mid in by_id]
        item = Equipment(
            descriptor=descriptor,
            # 显示名用作者写的调试名；它可能没有 Unit_ 前缀，那也照样显示。
            class_name=class_name or _bare(descriptor),
            kind="building" if class_name.startswith("Building_") else "unit",
        )
        for module in modules:
            cls = module["class"]
            if cls == TYPE_MODULE:
                item.country = _scalar(module, "MotherCountry") or ""
                item.coalition = _decode_enum(_scalar(module, "Coalition"), coalitions)
            elif cls == UI_MODULE:
                item.role = _scalar(module, "UnitRole") or ""
                item.strategic = _decode_enum(
                    _scalar(module, "TypeStrategicCount"), strategic)
                item.icon = _scalar(module, "MenuIconTexture") or ""
                item.price = _scalar(module, "PriceCategory") or ""
                token = _raw(module, "NameToken")
                if isinstance(token, dict):
                    item.token_hex = token.get("value_hex") or ""
                    if item.token_hex:
                        resolved = resolver.resolve(bytes.fromhex(item.token_hex))
                        item.name = resolved.text or ""
            elif cls == FORM_MODULE:
                item.formation = _scalar(module, "TypeUnitFormation") or ""
        # 基线里的名字是 ``Descriptor_Unit_X`` 的 X —— 与 _bare 去前缀后的结果同形。
        item.is_new = bool(base.unit_names) and _bare(descriptor) not in base.unit_names
        lookup.equipments.append(item)

    if lookup.skipped:
        lookup.notes.append(tr(
            "另有 {n} 个 TEntityDescriptor 对象没有 $/GFX/Unit 导出"
            "（Mimetic 影子单位、贴图区块之类），不是可选单位，未计入装备表。",
            n=len(lookup.skipped)))
    # 按显示名排序：对象 id 的顺序是编译顺序，读表的人不按那个找东西。
    lookup.equipments.sort(key=lambda e: (e.label.lower(), e.class_name))
    lookup.named = (sum(1 for e in lookup.equipments if e.name),
                    len(lookup.equipments))
    odd = [e for e in lookup.equipments
           if (e.country in PACT_COUNTRIES and e.coalition == "NATO")
           or (e.country in NATO_COUNTRIES and e.coalition == "PACT")]
    if odd:
        names = "、".join(e.class_name for e in odd[:5])
        lookup.notes.append(tr(
            "{n} 个装备的国家与 Coalition 字段冲突（{names}）：表里按字段显示，"
            "因为游戏读的就是这个值；要改请回 mod 里把 Coalition 补上。",
            n=len(odd), names=names + ("…" if len(odd) > 5 else "")))
    if lookup.named[1] and lookup.named[0] < lookup.named[1]:
        lookup.notes.append(tr(
            "装备显示名只有 {got}/{total} 能从 mod 自带的 .dic 解出 —— "
            "原版词条封在 Data/PC/*.dat 里，所以表里以作者写的调试名为主。",
            got=lookup.named[0], total=lookup.named[1]))

    # ---- 装备 → pack 的归属 -------------------------------------------
    # 两条边类型不同：pack 指的是**路径串**（``trans_ref``），牌组指的是
    # **object_id**（同文件内）。所以这里按去前缀的名字建索引，而不是按 id。
    by_bare = {_bare(e.descriptor): e for e in lookup.equipments}

    deck_path = slot_path(mod, SLOT_DECK)
    deck_from_mod = deck_path is not None
    if deck_from_mod:
        _fill_from_compiled(lookup, deck_path, by_bare, base)
        lookup.sources.append(tr(
            "pack / 牌组 · {what}", what=f"{deck_path.name}（{_size(deck_path)}）"))
    else:
        _fill_from_baseline(lookup, base, by_bare)
        lookup.sources.append(tr(
            "pack / 牌组 · base.zip 的 StrategicPacks.ndf / StrategicDecks.ndf"
            "（这个 mod 没有 GFX/Deck，用的是原版）"))
        lookup.notes.append(tr(
            "本 mod 未覆盖 GFX/Deck：pack 与牌组数据来自原版模板。"
            "这是语义正确的 —— pack 只存在于 Deck 里，没有它 mod 不可能有自己的 pack。"))

    if not mod.has(SLOT_DECK) and deck_from_mod:
        lookup.notes.append(tr(
            "Config.ini 的 [Config] 段没有声明 GFX/Deck，但文件存在 —— "
            "已照读，请确认它确实是这个 mod 要用的那一份。"))

    lookup.packs.sort(key=lambda p: (p.unit.lower(), p.xp, p.name))
    lookup.elapsed = time.perf_counter() - t0
    return lookup


def _size(path: Path) -> str:
    n = path.stat().st_size
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1048576:.2f} MB"


def _fill_from_compiled(lookup: Lookup, deck_path: Path,
                        by_bare: dict, base: Baseline) -> None:
    """读 mod 自己的 ``Deck.ndfbin``：pack 表 + 牌组引用计数。"""
    info = _resolve(deck_path)
    descriptors = {e.descriptor for e in lookup.equipments}

    packs = [o for o in info["objects"] if o["class"] == "TDeckPackDescriptor"]
    for obj in packs:
        row = PackRow(
            object_id=obj["id"],
            unit=_tail(_scalar(obj, "UnitDescriptor")),
            transport=_tail(_scalar(obj, "TransporterDescriptor")),
            xp=int(_scalar(obj, "ExperienceLevel") or 0),
        )
        names = base.signatures.get(_signature(row.unit, row.transport, row.xp)) or []
        # 签名相同的就是同一内容，原版给了它一个名字；两个不同名字共享同一
        # 签名时无法判断是哪一个，宁可不写。
        row.name = names[0] if len(names) == 1 else ""
        lookup.packs.append(row)

    decks = [o for o in info["objects"]
             if o["class"] == "TDeckDescriptor"
             and _scalar(o, "DeckIdentifier") is not None]
    lookup.decks = len(decks)
    per_pack: dict[int, int] = {}
    for obj in decks:
        refs = {item.get("object_id") for item in
                (_raw(obj, "DeckPackList") or {}).get("items") or []
                if isinstance(item, dict)}
        for pid in refs:
            per_pack[pid] = per_pack.get(pid, 0) + 1
    for row in lookup.packs:
        row.decks = per_pack.get(row.object_id, 0)

    stripped = 0
    for row in lookup.packs:
        target = by_bare.get(_bare(row.unit))
        if target is None:
            lookup.dangling.append(row.unit or "(空 Unit)")
            continue
        # FOB 是唯一需要剥前缀的一类：pack 写 Descriptor_Unit_FOB_DDR，
        # 对象是 Building_FOB_DDR。记下条数，否则「为什么少了一件」没人答得上。
        if row.unit and row.unit not in descriptors:
            stripped += 1
        target.packs_unit += 1
        if row.transport:
            carrier = by_bare.get(_bare(row.transport))
            if carrier is not None:
                carrier.packs_transport += 1
            else:
                lookup.dangling.append(row.transport)
    _note_dangling(lookup)
    if stripped:
        lookup.notes.append(tr(
            "其中 {n} 条 pack 的引用与装备对象名不同名（FOB 之类：pack 写 "
            "Descriptor_Unit_X、对象是 Building_X），已按去掉 Unit_/Building_ "
            "前缀后的名字连上。", n=stripped))


def _fill_from_baseline(lookup: Lookup, base: Baseline, by_bare: dict) -> None:
    """:mod:`GFX/Deck` 缺失时的兜底：用 ``base.zip`` 的明文 pack / 牌组。

    语义上是**正确**的而不是凑数：pack 只存在于 ``GFX/Deck``，没有它这个 mod
    不可能有自己的 pack，游戏里用的就是原版那批。
    """
    if not base.packs:
        lookup.notes.append(tr("base.zip 里没读到 pack 数据，这一节空着。"))
        return
    used: dict[str, int] = {}
    for packs in base.decks.values():
        for name in set(packs):
            used[name] = used.get(name, 0) + 1
    lookup.decks = len(base.decks)
    for name, rec in base.packs.items():
        row = PackRow(name=name, unit=_tail(rec["unit"]),
                      transport=_tail(rec["trans"]), xp=int(rec["xp"] or 0),
                      decks=used.get(name, 0))
        lookup.packs.append(row)
        target = by_bare.get(_bare(row.unit))
        if target is None:
            lookup.dangling.append(row.unit or "(空 Unit)")
        else:
            target.packs_unit += 1
        if row.transport:
            carrier = by_bare.get(_bare(row.transport))
            if carrier is not None:
                carrier.packs_transport += 1
    _note_dangling(lookup)


def _note_dangling(lookup: Lookup) -> None:
    if not lookup.dangling:
        return
    unique = sorted(set(lookup.dangling))
    shown = "、".join(unique[:6]) + ("…" if len(unique) > 6 else "")
    lookup.notes.append(tr(
        "{n} 条 pack 的装备引用在这个 mod 的装备表里找不到（悬空引用）：{names}",
        n=len(unique), names=shown))


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

#: 页面的样式与脚本。整体沿用一个已被使用者读惯的版式：顶部卡片看总量、
#: 下面分段可搜可筛。**全部内联**，断网、单文件可开。
_CSS = """
 body{font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:0;
      background:#f6f7f9;color:#1a1a1a}
 header{background:#1f2937;color:#fff;padding:16px 24px}
 header h1{margin:0;font-size:19px} header p{margin:4px 0 0;color:#9ca3af;font-size:12px}
 header code{color:#e5e7eb;background:#374151;padding:1px 5px;border-radius:4px}
 main{padding:16px 24px 70px;max-width:1680px}
 h2{font-size:16px;margin:26px 0 10px;padding-bottom:6px;border-bottom:2px solid #e5e7eb}
 .cards{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}
 .card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px 16px;min-width:150px}
 .card b{display:block;font-size:23px;line-height:1.25}
 .card span{color:#6b7280;font-size:12px}
 .card.hi{border-color:#10b981;background:#f0fdf4}
 .card.warn{border-color:#f59e0b;background:#fffbeb}
 .card.new{border-color:#6366f1;background:#eef2ff}
 table.grid{width:100%;border-collapse:collapse;background:#fff;font-size:12.5px}
 table.grid th{background:#f3f4f6;text-align:left;padding:6px 8px;border:1px solid #e5e7eb;
               position:sticky;top:0;z-index:2}
 table.grid td{padding:4px 8px;border:1px solid #eef0f2;vertical-align:top}
 table.grid tbody tr:hover{background:#f8fafc}
 .bar{position:sticky;top:0;z-index:5;background:#f6f7f9;padding:8px 0;
      border-bottom:1px solid #e5e7eb;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
 input,select{font:13px inherit;padding:6px 9px;border:1px solid #d1d5db;border-radius:6px;
              background:#fff}
 label.chk{font-size:13px;display:flex;gap:6px;align-items:center;white-space:nowrap}
 .cnt{color:#6b7280;font-size:12px;margin-left:auto}
 code,.mono{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:#374151}
 .tag{font-size:11px;border-radius:9px;padding:1px 7px;background:#eef2ff;color:#3730a3;
      white-space:nowrap}
 .ok{background:#ecfdf5;color:#065f46}.no{background:#fef2f2;color:#991b1b}
 .mid{background:#fffbeb;color:#92400e}.newt{background:#e0e7ff;color:#3730a3;font-weight:600}
 .warn{background:#fffbeb;border-left:3px solid #f59e0b;padding:9px 13px;font-size:13px;margin:10px 0}
 .note{background:#eff6ff;border-left:3px solid #3b82f6;padding:9px 13px;font-size:13px;margin:10px 0}
 .bad{background:#fef2f2;border-left:3px solid #ef4444;padding:9px 13px;font-size:13px;margin:10px 0}
 .mini{width:100%;font-size:12px} .mini th,.mini td{padding:3px 7px;border:1px solid #eef0f2}
 details{margin:8px 0} summary{cursor:pointer;font-weight:600;padding:4px 0;font-size:13px}
 .wrap{max-height:70vh;overflow:auto;border:1px solid #e5e7eb;border-radius:8px;background:#fff}
 .wrap table.grid{border-radius:8px}
 .muted{color:#9ca3af}
"""

_JS = """
const U=__UNITS__,P=__PACKS__,S=__META__;
/* 上限只是防一张病态的大表把浏览器卡死；样本 mod 的 5415 个 pack 要能一次看全。 */
const CAP=8000;
const ROLE_ZH=S.roles, CTY_ZH=S.countries;
function esc(s){return (s==null?'':''+s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function roleCn(r){return r?(ROLE_ZH[r]||r):'—'}
function stratTag(s){return s?'<code>'+esc(s)+'</code>':'<span class="muted">—</span>'}
function ctyCell(c){
  if(!c) return '<span class="muted">—</span>';
  const zh=CTY_ZH[c];
  return (zh?esc(zh)+' ':'')+'<code>'+esc(c)+'</code>';
}
function packState(u){return u.pu>0?'yes':(u.pt>0?'veh':'no')}
function packBadge(u){
  if(u.pu>0) return '<span class="tag ok">&#10003; '+u.pu+'</span>';
  if(u.pt>0) return '<span class="tag mid">仅载具 '+u.pt+'</span>';
  return '<span class="tag no">&#10007; 无</span>';
}
function newTag(u){return u.nw?'<span class="tag newt">★ 新增</span>':''}
/* 第二行的调试名只在它比显示名多提供信息时才画：没有词条名时两行会是同一串。 */
function nameSub(u){
  return (u.name&&u.name!==u.cn)?'<div class="mono muted">'+esc(u.cn)+'</div>':'';
}
function packLabel(p){
  let s=esc(p.un||'?');
  if(p.tn) s+=' <span class="muted">['+esc(p.tn)+']</span>';
  if(p.x) s+=' <span class="tag">XP'+p.x+'</span>';
  return s;
}

function fill(id,rows){
  const tb=document.querySelector('#'+id+' tbody');
  tb.innerHTML=rows.join('');
}

/* ---- 0/1 统计表（一次性，不随筛选变） ---- */
fill('tcov',S.cov.map(r=>'<tr><td>'+esc(r[1])+' <code>'+esc(r[0])+'</code></td>'
  +'<td><span class="tag ok">'+r[2]+'</span></td><td>'+r[3]+'</td>'
  +'<td><span class="tag '+(r[4]?'no':'')+'">'+r[4]+'</span></td>'
  +'<td>'+(r[5]?'<span class="tag newt">'+r[5]+'</span>':'<span class="muted">0</span>')+'</td>'
  +'<td>'+r[6]+'</td></tr>'));
fill('trole',S.roles_d.map(r=>'<tr><td><code>'+esc(r[0])+'</code></td><td>'+esc(r[1]||'—')
  +'</td><td>'+r[2]+'</td></tr>'));
fill('tstrat',S.strat_d.map(r=>'<tr><td><code>'+esc(r[0])+'</code></td><td>'+r[1]+'</td></tr>'));
fill('tcoal',S.coal_d.map(r=>'<tr><td>'+esc(r[0])+'</td><td>'+r[1]+'</td></tr>'));

/* ---- 2 装备速查 ---- */
function renderU(){
  const q=document.getElementById('q').value.trim().toLowerCase();
  const fc=document.getElementById('fc').value, fo=document.getElementById('fo').value,
        fr=document.getElementById('fr').value, fs=document.getElementById('fs').value,
        fn=document.getElementById('fn').checked;
  let n=0,h=[];
  for(let i=0;i<U.length;i++){const u=U[i];
    if(fc&&u.coal!==fc) continue;
    if(fo&&u.cty!==fo) continue;
    if(fr&&u.role!==fr) continue;
    if(fs&&packState(u)!==fs) continue;
    if(fn&&!u.nw) continue;
    if(q&&(u.name+' '+u.cn+' '+u.id+' '+u.strat+' '+(u.form||'')).toLowerCase().indexOf(q)<0) continue;
    n++; if(n>CAP) continue;
    h.push('<tr><td>'+esc(u.name||u.cn)+' '+newTag(u)+nameSub(u)+'</td>'
      +'<td>'+esc(u.coal||'—')+'</td><td>'+ctyCell(u.cty)+'</td>'
      +'<td>'+roleCn(u.role)+'</td><td>'+stratTag(u.strat)+'</td>'
      +'<td>'+esc(u.form||'—')+'</td><td>'+esc(u.price||'—')+'</td>'
      +'<td>'+packBadge(u)+'</td></tr>');
  }
  fill('tbl',h);document.getElementById('cnt').textContent=n+' / '+U.length+(n>CAP?'（只显示前 '+CAP+'，请细化筛选）':'');
}
/* ---- 3 Pack 速查 ---- */
function renderP(){
  const q=document.getElementById('q2').value.trim().toLowerCase();
  const fx=document.getElementById('fx').value, fu=document.getElementById('fu').value;
  let n=0,h=[];
  for(let i=0;i<P.length;i++){const p=P[i];
    if(fx!==''&&String(p.x)!==fx) continue;
    if(fu==='used'&&!p.n) continue;
    if(fu==='orphan'&&p.n) continue;
    if(q&&((p.p||'')+' '+p.un+' '+(p.tn||'')+' '+p.un0+' '+p.tn0).toLowerCase().indexOf(q)<0) continue;
    n++; if(n>CAP) continue;
    h.push('<tr><td>'+packLabel(p)+'</td>'
      +'<td class="mono">'+(p.p?esc(p.p):'<span class="muted">（mod 新增，无原名）</span>')+'</td>'
      +'<td class="mono">'+esc(p.un0)+'</td>'
      +'<td>'+(p.n?'<span class="tag ok">'+p.n+' 个牌组</span>':'<span class="tag mid">孤儿</span>')+'</td>'
      +'<td class="mono">'+(p.oid>=0?'#'+p.oid:'<span class="muted">—</span>')+'</td></tr>');
  }
  fill('tbl2',h);document.getElementById('cnt2').textContent=n+' / '+P.length+(n>CAP?'（只显示前 '+CAP+'，请细化筛选）':'');
}
/* ---- 4 无 pack 的装备 ---- */
function renderN(){
  const q=document.getElementById('q3').value.trim().toLowerCase();
  const fc=document.getElementById('f3c').value, fr=document.getElementById('f3r').value,
        fn=document.getElementById('f3n').checked;
  let n=0,h=[];
  for(let i=0;i<U.length;i++){const u=U[i];
    if(u.pu>0||u.pt>0) continue;
    if(fc&&u.cty!==fc) continue;
    if(fr&&u.role!==fr) continue;
    if(fn&&!u.nw) continue;
    if(q&&(u.name+' '+u.cn+' '+u.id).toLowerCase().indexOf(q)<0) continue;
    n++; if(n>CAP) continue;
    h.push('<tr><td>'+esc(u.name||u.cn)+' '+newTag(u)+nameSub(u)+'</td>'
      +'<td>'+esc(u.coal||'—')+'</td><td>'+ctyCell(u.cty)+'</td>'
      +'<td>'+roleCn(u.role)+'</td><td>'+stratTag(u.strat)+'</td></tr>');
  }
  fill('tbl3',h);document.getElementById('cnt3').textContent=n+' / '+S.none+(n>CAP?'（只显示前 '+CAP+'）':'');
}
['q','fc','fo','fr','fs'].forEach(id=>document.getElementById(id).addEventListener('input',renderU));
document.getElementById('fn').addEventListener('change',renderU);
['q2','fx','fu'].forEach(id=>document.getElementById(id).addEventListener('input',renderP));
['q3','f3c','f3r'].forEach(id=>document.getElementById(id).addEventListener('input',renderN));
document.getElementById('f3n').addEventListener('change',renderN);
renderU();renderP();renderN();
"""


def _json_for_script(payload) -> str:
    """``json.dumps`` 对 ``<script>`` 是危险的：字符串里的 ``</script>``
    会提前闭合标签。转义 ``<`` 即可，JSON 语义不变。"""
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c"))


def render_html(lookup: Lookup) -> str:
    """把一张表渲染成单文件 HTML（内嵌 JSON，无外部依赖）。"""
    counts = lookup.counts()
    countries = lookup.country_rows()
    roles = lookup.role_rows()
    strategic = lookup.strategic_rows()
    coalitions = lookup.coalition_rows()

    units = [{
        "id": e.descriptor,
        "cn": e.class_name,
        "name": e.name,
        "coal": e.coalition,
        "cty": e.country,
        "role": e.role,
        "strat": e.strategic,
        "form": e.formation,
        "price": e.price,
        "kind": e.kind,
        "nw": 1 if e.is_new else 0,
        "pu": e.packs_unit,
        "pt": e.packs_transport,
    } for e in lookup.equipments]

    # pack → 装备的显示名查表。**先建字典再渲染**：5415 个 pack 逐个遍历
    # 3686 个装备是两千万次比较，页面上看不出来，但导出要等十几秒。
    display = {_bare(e.descriptor): (e.name or e.class_name)
               for e in lookup.equipments}

    packs = [{
        "p": p.name,
        "x": p.xp,
        "n": p.decks,
        "un": display.get(_bare(p.unit), _bare(p.unit)),
        "tn": display.get(_bare(p.transport), _bare(p.transport)),
        "un0": p.unit,
        "tn0": p.transport,
        "oid": p.object_id,
    } for p in lookup.packs]

    meta = {
        "cov": [list(r) for r in countries],
        "roles": ROLE_NAMES,
        "countries": COUNTRY_NAMES,
        "roles_d": [[r[0], r[1], r[2]] for r in roles],
        "strat_d": [list(r) for r in strategic],
        "coal_d": [list(r) for r in coalitions],
        "none": counts["none"],
    }

    # 新增标记：只在基线读到时才有意义，否则整列是 0，得说清楚。
    new_without_pack = sum(1 for e in lookup.equipments
                           if e.is_new and not e.packs_unit and not e.packs_transport)
    new_note = ""
    if counts["new"]:
        new_note = (
            f"其中 <b>★ 新增 {counts['new']}</b> 是原版基线里没有的装备；"
            f"这 {counts['new']} 个里 <b>{new_without_pack}</b> 个还没有任何 pack"
            " —— 它们就是「新单位在将军模式里选不到」的那批。")

    notes_html = "".join(
        f'<div class="{"warn" if i % 2 == 0 else "note"}">{html.escape(n)}</div>'
        for i, n in enumerate(lookup.notes))

    sources_html = "<br>".join(html.escape(s) for s in lookup.sources)
    role_options = "".join(
        f'<option value="{html.escape(k)}">{html.escape((v + " " if v else "") + k)}</option>'
        for k, v, _n in roles)
    cty_options = "".join(
        f'<option value="{html.escape(code)}">{html.escape(name)} {html.escape(code)}</option>'
        for code, name, *_rest in countries if code != "?")
    coal_options = "".join(
        f'<option>{html.escape(k)}</option>' for k, _n in coalitions if k)

    return f"""<!doctype html><html lang="zh"><meta charset="utf-8">
<title>{html.escape(lookup.mod_label)} · 装备 / Pack 速查表</title>
<style>{_CSS}</style>
<header><h1>{html.escape(lookup.mod_label)} · 装备 / Pack 速查表</h1>
<p>{html.escape(lookup.mod_name)}（{html.escape(lookup.mod_source)}） · {html.escape(lookup.generated)}
 · <code>ndfbin_decks/io/equip_lookup.py</code><br>{sources_html}</p></header>
<main>

<h2>0. 概览</h2>
<div class="cards">
 <div class="card"><b>{counts['total']}</b><span>全部装备</span></div>
 <div class="card new"><b>{counts['new']}</b><span>★ 原版没有的新装备</span></div>
 <div class="card hi"><b>{counts['have']}</b><span>已有 pack · 可直接进 AG</span></div>
 <div class="card"><b>{counts['veh']}</b><span>仅作载具出现</span></div>
 <div class="card warn"><b>{counts['none']}</b><span>完全无 pack · 需先建 pack</span></div>
 <div class="card"><b>{counts['packs']}</b><span>全部 AG pack</span></div>
 <div class="card hi"><b>{counts['packs_used']}</b><span>被牌组实际引用</span></div>
 <div class="card"><b>{counts['orphan']}</b><span>孤儿 pack（定义了没人用）</span></div>
 <div class="card"><b>{counts['decks']}</b><span>AG 牌组总数</span></div>
</div>
<div class="note"><b>怎么读这三个数：</b>
「已有 pack {counts['have']}」= 现有编制里已经在用的装备；
「完全无 pack {counts['none']}」= <b>想让它出现在将军模式，就得先生成一个 pack</b>
（这就是「装备选择器里选不到」的那些）；「仅作载具 {counts['veh']}」= 只被别的 pack
当运输工具引用，自己不是可选装备。{new_note}
<br><span class="muted">装备口径：这个文件里**导出成
<code>$/GFX/Unit/Descriptor_Unit_*</code>** 的实体 —— 导出名就是 pack 引用单位时
用的那个字符串，所以「表里有」与「编辑器下拉框认得出」是同一批。
<code>ClassNameForDebug</code> 只是显示名（作者可以不起 <code>Unit_</code> 前缀），
不带 UI 模块的会缺角色与价格，但仍然在表里。</span>
</div>
{notes_html}

<h2>1. 分类统计</h2>
<details open><summary>各国装备的 pack 填装情况（最有行动价值的一张表）</summary>
<table class="grid mini" id="tcov"><thead><tr>
<th>国家</th><th>✓ 有 pack</th><th>仅作载具</th><th>✗ 无 pack</th><th>★ 新增</th><th>合计</th>
</tr></thead><tbody></tbody></table>
<p style="font-size:12.5px;color:#6b7280;margin:6px 0 0">
「★ 新增」= 原版基线里没有这个装备。某国一行「✓ 有 pack」为 0，
说明这个国家的装备完全没进将军模式 —— 不是数据缺失，而是它压根不参战。</p></details>
<details open><summary>按兵种角色 UnitRole（{len(roles)} 种）</summary>
<table class="grid mini" id="trole"><thead><tr><th>角色</th><th>中文</th><th>数量</th></tr></thead>
<tbody></tbody></table></details>
<details><summary>按战略分类 TypeStrategicCount（{len(strategic)} 种）</summary>
<table class="grid mini" id="tstrat"><thead><tr><th>分类</th><th>数量</th></tr></thead>
<tbody></tbody></table></details>
<details><summary>按联盟</summary>
<table class="grid mini" id="tcoal"><thead><tr><th>联盟</th><th>数量</th></tr></thead>
<tbody></tbody></table></details>

<h2>2. 装备速查（{counts['total']} 个）</h2>
<div class="bar">
 <input id="q" size="28" placeholder="搜装备名 / 调试名 / 对象名…">
 <select id="fc"><option value="">全部联盟</option>{coal_options}</select>
 <select id="fo"><option value="">全部国家</option>{cty_options}</select>
 <select id="fr"><option value="">全部角色</option>{role_options}</select>
 <select id="fs"><option value="">全部 pack 状态</option>
   <option value="yes">✓ 有 pack</option><option value="veh">仅作载具</option>
   <option value="no">✗ 无 pack</option></select>
 <label class="chk"><input type="checkbox" id="fn"> 只看新增</label>
 <span class="cnt" id="cnt"></span></div>
<div class="wrap"><table class="grid" id="tbl"><thead><tr>
<th>装备</th><th>联盟</th><th>国家</th><th>角色</th><th>战略分类</th><th>编队</th>
<th>价格</th><th>packs</th></tr></thead><tbody></tbody></table></div>

<h2>3. Pack 速查（{counts['packs']} 个）</h2>
<div class="note"><b>「被 N 个牌组引用」是第二重判断。</b>
pack 定义存在 ≠ 有编制在用。<b>孤儿 pack</b>（定义了但没有牌组指向）在 AG 里
<b>仍然可选</b>，只是没有任何编制用它 —— 对改编制的人来说这反而是现成的素材。
<br><span class="muted">N 是<b>不同牌组</b>的个数，不是引用条数 —— 一个 pack 占用的
每个槽位都会在 DeckPackList 里重复出现，按条数会数出比牌组总数还大的值。
<br>编译后的 pack <b>没有对象名</b>（<code>TDeckPackDescriptor</code> 只有
Unit/Transporter/ExperienceLevel/Number 四个字段），所以「原始包名」一列只有
能从原版模板反查回来时才有值，其余显示内容标签。</span></div>
<div class="bar">
 <input id="q2" size="30" placeholder="搜装备 / 载具 / 原版包名…">
 <select id="fx"><option value="">全部 XP</option><option value="0">无 XP</option>
   <option value="1">XP 1</option><option value="2">XP 2</option>
   <option value="3">XP 3</option></select>
 <select id="fu"><option value="">全部使用状态</option>
   <option value="used">被牌组引用</option><option value="orphan">孤儿（没人用）</option></select>
 <span class="cnt" id="cnt2"></span></div>
<div class="wrap"><table class="grid" id="tbl2"><thead><tr>
<th>内容</th><th>原始包名</th><th>装备对象名</th><th>被牌组引用</th><th>object_id</th>
</tr></thead><tbody></tbody></table></div>

<h2>4. 需生成 Pack 的装备（{counts['none']} 个）</h2>
<div class="warn">这些装备在游戏里存在，但<b>没有任何 pack 指向它</b>，
所以将军模式的装备选择器里找不到。要让某个编制用上它，需要新建一条
<code>Descriptor_StrategicPack_*</code>（编辑器里的「Build New Equipment」）。</div>
<div class="bar">
 <input id="q3" size="28" placeholder="搜装备名 / 调试名…">
 <select id="f3c"><option value="">全部国家</option>{cty_options}</select>
 <select id="f3r"><option value="">全部角色</option>{role_options}</select>
 <label class="chk"><input type="checkbox" id="f3n"> 只看新增</label>
 <span class="cnt" id="cnt3"></span></div>
<div class="wrap"><table class="grid" id="tbl3"><thead><tr>
<th>装备</th><th>联盟</th><th>国家</th><th>角色</th><th>战略分类</th>
</tr></thead><tbody></tbody></table></div>

</main>
<script>
const __UNITS__={_json_for_script(units)};
const __PACKS__={_json_for_script(packs)};
const __META__={_json_for_script(meta)};
{_JS}
</script>
</html>
"""


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """``python -m ndfbin_decks.io.equip_lookup --mod <名称|工坊id> [--out x.html]``"""
    ap = argparse.ArgumentParser(
        prog="equip_lookup",
        description="从 mod 编译后的 ndfbin 导出一份装备 / pack 速查表（单文件 HTML）。")
    ap.add_argument("--mod", required=True,
                    help="mod 目录名、显示名或创意工坊 id（子串匹配）")
    ap.add_argument("--out", default="",
                    help="输出路径；默认 装备速查-<mod 名>-<日期>.html")
    ap.add_argument("--lang", default="SC", help="词条语言（默认 SC，缺失回落 DEV）")
    args = ap.parse_args(argv)

    try:
        mod = modlocator.resolve(args.mod)
    except modlocator.ModNotFound as exc:
        print(f"找不到 mod：{exc}", file=sys.stderr)
        return 2
    try:
        lookup = build_lookup(mod, lang=args.lang)
    except LookupUnavailable as exc:
        print(f"{lookup_error_prefix()}{exc}", file=sys.stderr)
        return 3

    out = Path(args.out) if args.out else Path(
        f"装备速查-{_safe_name(mod.name)}-{time.strftime('%Y%m%d')}.html")
    out.write_text(render_html(lookup), encoding="utf-8")

    counts = lookup.counts()
    print(f"{out}  {out.stat().st_size / 1048576:.2f} MB")
    print(f"  装备 {counts['total']}（新增 {counts['new']}）· "
          f"有 pack {counts['have']} / 仅载具 {counts['veh']} / 无 pack {counts['none']}")
    print(f"  pack {counts['packs']}（被引用 {counts['packs_used']}、孤儿 {counts['orphan']}）"
          f"· AG 牌组 {counts['decks']}")
    for note in lookup.notes:
        print(f"  注意：{note}")
    return 0


def lookup_error_prefix() -> str:
    return "导不出这张表："


def _safe_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


if __name__ == "__main__":
    raise SystemExit(main())
