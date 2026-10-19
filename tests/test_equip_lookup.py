"""装备 / Pack 速查表：数字口径、JOIN、兜底与产物。

Run:  python -m tests.test_equip_lookup

这个功能最容易出的错**都不会让页面崩**：读错了一个文件、几条引用没连上、
枚举回落到 ``#23`` —— 页面照样打开，只是数字不对。所以断言全部落在数字上，
而且用样本 mod 的实测值当基准（`A World in Flames`，工坊 3388575848 ——
它同时带 ``GFX/Unit`` 和 ``GFX/Deck``，是唯一能验证「装备 × pack」两边都齐的样本）：

    装备 3686（另有 936 个 Mimetic 影子单位不计）
    = 有 pack 2247 + 仅载具 317 + 无 pack 1122
    pack 5415 → 连到装备 5414，悬空 1（WF_VDV_HMG_RUS，mod 自己写错了）
    AG 牌组 2265 · 孤儿 pack 1885 · 新增 775
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _env                                              # noqa: E402

from ndfbin_decks.io import modlocator                    # noqa: E402
from ndfbin_decks.io import equip_lookup as EL             # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []

#: 样本 mod 的实测基准。改这些数字等于改验收标准，必须同时说明为什么。
BASE_TOTAL = 3686
BASE_HAVE = 2247
BASE_VEH = 317
BASE_NONE = 1122
BASE_PACKS = 5415
BASE_DECKS = 2265
BASE_ORPHAN = 1885
BASE_NEW = 775
BASE_SKIPPED = 936


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  {detail}" if detail else ""))


def json_block(text: str, marker: str):
    """抽出 ``const <marker>=…;`` 里的那个 JSON —— 页面能跑不算数，能解析才算。"""
    start = text.index(f"const {marker}=") + len(f"const {marker}=")
    value, _end = json.JSONDecoder().raw_decode(text[start:])
    return value


def main() -> int:
    mods = _env.mods()
    if not mods:
        _env.skip("no WARNO mod workspace on this machine")

    sample = mods.get(_env.SAMPLE)
    if sample is None:
        _env.skip(f"the sample mod ({_env.SAMPLE}) is not installed — "
                  "the numeric baselines are measured against it")
    try:
        if not EL.slot_path(sample, EL.SLOT_UNIT):
            _env.skip(f"sample mod {_env.SAMPLE} lacks GFX/Unit")
    except Exception as exc:                           # noqa: BLE001
        _env.skip(f"sample mod unreadable: {exc}")

    # ---- 1. 口径 -----------------------------------------------------
    print("\n=== 1. 装备口径（影子单位不该占行） ===")
    lookup = EL.build_lookup(sample)
    counts = lookup.counts()
    check("装备数与样本一致", counts["total"] == BASE_TOTAL, f"{counts['total']}")
    check("交叉表自洽：有 pack + 仅载具 + 无 pack == 总数",
          counts["have"] + counts["veh"] + counts["none"] == counts["total"],
          f"{counts['have']}+{counts['veh']}+{counts['none']}")
    check("有 pack / 仅载具 / 无 pack 三个数都对",
          (counts["have"], counts["veh"], counts["none"])
          == (BASE_HAVE, BASE_VEH, BASE_NONE),
          f"{counts['have']}/{counts['veh']}/{counts['none']}")
    check("影子单位被排除且报了数",
          len(lookup.skipped) == BASE_SKIPPED, f"{len(lookup.skipped)}")
    check("被排除的都是没有 UI 的 Mimetic 对象",
          all("Mimetic" in n for n in lookup.skipped),
          str([n for n in lookup.skipped if "Mimetic" not in n][:3]))
    check("每条装备都有可重建的对象名",
          all(e.descriptor.startswith("Descriptor_") for e in lookup.equipments))
    check("只有 unit / building 两类",
          {e.kind for e in lookup.equipments} == {"unit", "building"},
          str({e.kind for e in lookup.equipments}))
    check("新增数与基线差一致", counts["new"] == BASE_NEW, f"{counts['new']}")
    check("词条解析确实解出了一部分（否则说明根本没连 .dic）",
          lookup.named[0] > 0, f"{lookup.named[0]}/{lookup.named[1]}")

    # ---- 2. JOIN -----------------------------------------------------
    print("\n=== 2. pack → 装备 的 JOIN ===")
    check("pack 数与样本一致", counts["packs"] == BASE_PACKS, f"{counts['packs']}")
    check("AG 牌组数与样本一致", counts["decks"] == BASE_DECKS, f"{counts['decks']}")
    check("孤儿 pack 与样本一致", counts["orphan"] == BASE_ORPHAN,
          f"{counts['orphan']}")
    check("被引用 pack + 孤儿 == 总数",
          counts["packs_used"] + counts["orphan"] == counts["packs"])
    check("悬空引用只有一个，且点名到具体装备",
          lookup.dangling == ["Descriptor_Unit_WF_VDV_HMG_RUS"],
          str(lookup.dangling))
    attached = sum(1 for p in lookup.packs if p.unit)
    check("pack 都指了装备", attached == counts["packs"], f"{attached}")
    hit = sum(1 for e in lookup.equipments if e.packs_unit)
    check("有 pack 的装备数 == 连上的条目数（不是 pack 数）",
          hit == counts["have"], f"{hit}")
    named = [p for p in lookup.packs if p.name]
    check("原版改名恢复得比没有强", len(named) > 3000, f"{len(named)}/{counts['packs']}")
    check("恢复的名字没有双前缀",
          not any("StrategicPack_StrategicPack" in p.name for p in lookup.packs))
    check("mod 自己的新 pack 确实没有原名（这就是边界）",
          any(not p.name for p in lookup.packs))

    # ---- 3. 枚举 -----------------------------------------------------
    print("\n=== 3. 枚举：Coalition / TypeStrategicCount 是整数，得查表 ===")
    strategics = {e.strategic for e in lookup.equipments if e.strategic}
    check("所有战略分类都解成了名字，没有 #23 这类回落",
          not any(s.startswith("#") for s in strategics),
          str([s for s in strategics if s.startswith("#")][:3]))
    check("解出来的分类在枚举表里",
          strategics <= set(EL.STRATEGIC_FALLBACK.values()),
          str(sorted(strategics - set(EL.STRATEGIC_FALLBACK.values()))[:3]))
    howitzers = [e for e in lookup.equipments if e.role == "howitzer"]
    check("炮兵的战略分类基本都是 Howitzer（26）",
          sum(1 for e in howitzers if e.strategic == "Howitzer") >= 140,
          f"{sum(1 for e in howitzers if e.strategic == 'Howitzer')}/{len(howitzers)}")
    # 内置回落表必须和 base.zip 里的权威枚举逐项一致 —— 否则「游戏加值时滞后」
    # 这句话就是空话，而这张表是唯二会静默变质的东西（另一个是装备口径）。
    base = EL.load_baseline()
    if base.strategic:
        check("内置枚举表与 base.zip 的枚举定义逐项一致",
              base.strategic == EL.STRATEGIC_FALLBACK,
              f"{len(base.strategic)} 项")
    else:
        print("  --   no base.zip here, the fallback table cannot be cross-checked")
    pacts = [e for e in lookup.equipments if e.country in EL.PACT_COUNTRIES]
    nato = [e for e in lookup.equipments if e.country in EL.NATO_COUNTRIES]
    odd = [e for e in pacts if e.coalition != "PACT"]
    check("华约国家判成 PACT，例外只有字段缺失的那 2 个",
          len(odd) == 2 and all(e.class_name.startswith("Unit_WF_Orion") for e in odd),
          str([(e.class_name, e.coalition) for e in odd]))
    check("这 2 个例外在页面提醒里点名了，而不是悄悄算作 NATO",
          any("Coalition 字段冲突" in n for n in lookup.notes),
          str([n for n in lookup.notes if "Coalition" in n])[:100])
    check("北约国家都判成 NATO（字段缺失 = 0 = NATO）",
          nato and all(e.coalition == "NATO" for e in nato),
          str({e.coalition for e in nato}))

    # ---- 4. 缺 GFX/Unit ----------------------------------------------
    print("\n=== 4. 没有 GFX/Unit 的 mod：说人话，不出表 ===")
    berlin = mods.get(_env.BERLIN)
    if berlin is None:
        print("  --   Berlin mod not installed, skipped")
    else:
        try:
            EL.build_lookup(berlin)
            check("缺 GFX/Unit 时拒绝导出", False, "它居然导出来了")
        except EL.LookupUnavailable as exc:
            check("缺 GFX/Unit 时拒绝导出", True)
            check("理由里点名了缺哪个文件", "GFX/Unit" in str(exc), str(exc)[:60])

    # ---- 5. 缺 GFX/Deck：退到基线 ------------------------------------
    print("\n=== 5. 只带 GFX/Unit 时，pack 退到 base.zip ===")
    tmp = Path(tempfile.mkdtemp(prefix="lookup-nodeck-"))
    unit_src = EL.slot_path(sample, EL.SLOT_UNIT)
    (tmp / "Gen" / "NDF" / "GFX").mkdir(parents=True)
    shutil.copy(unit_src, tmp / "Gen" / "NDF" / "GFX" / "Unit.ndfbin")
    shutil.copy(Path(sample.deploy) / "Config.ini", tmp / "Config.ini")
    fake = modlocator.ModPaths(name="nodck", deploy=tmp, config=sample.config,
                               source=modlocator.SOURCE_MANUAL)
    try:
        partial = EL.build_lookup(fake)
    except EL.LookupUnavailable as exc:
        check("没有 GFX/Deck 也能出表", False, str(exc))
        partial = None
    if partial is not None:
        check("没有 GFX/Deck 也能出表", True)
        check("装备数不变（Unit 才是装备的来源）",
              len(partial.equipments) == BASE_TOTAL, f"{len(partial.equipments)}")
        check("pack 数与基线一致", len(partial.packs) == 2685, f"{len(partial.packs)}")
        check("牌组数用基线的 2208", partial.decks == 2208, f"{partial.decks}")
        check("页面里明说了来源是原版模板",
              any("原版模板" in n for n in partial.notes), str(partial.notes)[:80])
        check("基线 pack 全部有原名",
              all(p.name for p in partial.packs))

    # ---- 6. HTML -----------------------------------------------------
    print("\n=== 6. 产物：单文件、可解析、无外链 ===")
    text = EL.render_html(lookup)
    for section in ("0. 概览", "1. 分类统计", "2. 装备速查", "3. Pack 速查",
                    "4. 需生成 Pack 的装备"):
        check(f"含章节 {section}", section in text)
    check("页面够大（数据确实内嵌了）", len(text) > 800_000, f"{len(text):,} 字符")
    check("没有任何外部引用（断网可用）",
          "http://" not in text and "https://" not in text)
    units = json_block(text, "__UNITS__")
    packs = json_block(text, "__PACKS__")
    check("内嵌的装备数据能解析", len(units) == BASE_TOTAL, f"{len(units)}")
    check("内嵌的 pack 数据能解析", len(packs) == BASE_PACKS, f"{len(packs)}")
    check("装备行里带了新增标记", sum(u["nw"] for u in units) == BASE_NEW)
    check("新增标记里确实有没 pack 的（使用者最关心的那批）",
          any(u["nw"] and not u["pu"] and not u["pt"] for u in units))
    check("JSON 里的 < 被转义，不会提前闭合 script",
          "</script>" not in json.dumps(EL._json_for_script({"x": "</script>"}))
          and "\\u003c/script" in EL._json_for_script({"x": "</script>"}))
    check("超长名字不会破坏 HTML（转义生效）",
          "&lt;script&gt;" in EL.render_html(
              EL.Lookup(mod_label="<script>x</script>")))

    # ---- 7. 只读 -----------------------------------------------------
    print("\n=== 7. 只读：不碰 mod 里的文件 ===")
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
              for p in (EL.slot_path(sample, EL.SLOT_UNIT),
                        EL.slot_path(sample, EL.SLOT_DECK)) if p}
    EL.build_lookup(sample)
    after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
             for p in (EL.slot_path(sample, EL.SLOT_UNIT),
                       EL.slot_path(sample, EL.SLOT_DECK)) if p}
    check("Unit.ndfbin / Deck.ndfbin 一字未动", before == after, str(before))

    # ---- 8. CLI ------------------------------------------------------
    print("\n=== 8. 命令行入口 ===")
    out = Path(tempfile.mkdtemp(prefix="lookup-cli-")) / "cli.html"
    code = EL.main(["--mod", _env.SAMPLE, "--out", str(out)])
    check("CLI 退出码 0", code == 0, str(code))
    check("CLI 写出了文件", out.is_file() and out.stat().st_size > 800_000,
          f"{out.stat().st_size if out.is_file() else 0}")

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} / {len(PASS) + len(FAIL)}")
    if FAIL:
        print("失败项：")
        for name in FAIL:
            print(f"  - {name}")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
