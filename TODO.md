# NdfbinDecksEditor · 待办清单

> 用法：勾选框改成 `[x]` 即完成。做一项就在下面「推进日志」追加一行。
>
> 阶段之间**不要跳**——每个阶段的产出是下一阶段的输入。

**项目目标**：一个能打开 / 编辑 / 保存 WARNO 将军模式 AG Pawn 牌组（`Deck.ndfbin`）

的桌面工具，面向 mod 创作者。

**编辑范围**（已确认，勿扩大）：

- ✅ 将军模式 Pawn 牌组（AG，判据见 T1.9）
- ❌ 遭遇战 / PvP 牌组（`DeckName` 存在的那批，含 `_multi` / `_challenge_OP_*`）

---

## 阶段 0 · 探索（已完成）

四份勘查报告已产出，核心结论都拿到了。

- [x] **T0.1** 摸清 `Gen/NDF/` 产物格式（EUG0/CNDF/zstd + GladNDFBin）
- [x] **T0.2** 验证旧 `cndf_codec.py` 可无损往返（6 文件 no-op 字节一致）
- [x] **T0.3** 提取完整字段表（从 `PROP` 段直接读 schema）
- [x] **T0.4** 发现并验证 `(PackIndex, Number)` 是**区间**语义
- [x] **T0.5** 找到 Berlin mod 的 58 个新增 AG 牌组
- [x] **T0.6** 找到工坊 mod（Northern Thunder）的 129 个新增 AG 牌组
- [x] **T0.7** 找到 Test mod 的就地修改（**39 牌组 / 7 师**，非初版说的 6/3）
- [x] **T0.8** 打通 `token → dic 键 → ndfbin loc_hash` 三方链路
- [x] **T0.9** 确认 loc_hash **不可逆**（40 算法 × 6 编码全落空）

**阶段 0 关闭。** 2026-10-12 决定：

- ~~T0.10 定位游戏本体词典~~ → **取消**。本体词典已加密进 `Data\PC\<build>\*.dat`，

  解密方式不详。**成本/收益不对等**，不作为项目前置条件。

  ⇒ 改由 T1.5 的「降级显示」方案兜底（已完成）。

---

## 阶段 1 · 基础模块（✅ 已完成）

- [x] **T1.1** 建项目骨架 `ndfbin_decks/`（`core/` `io/` + `tests/`）
- [x] **T1.2** 参考 `旧文件/deckedit/cndf_codec.py`(408) + `ndf_codec.py`(337)

  —— ⚠ 按「参考而非照搬」原则，逐条验证后采纳为 `core/cndf_codec.py` + `core/cndf_layout.py`
- [x] **T1.3** ★ **三 mod 往返自测通过** —— `python -m ndfbin_decks.selfcheck`

  → **7/7 未压缩体逐字节一致**（Berlin 6 文件 + Test 1 文件）

  → 性能：Deck 解码 1.35 s / 编码 0.40 s（61127 对象）
- [x] **T1.4** ★ `io/tradic.py`：TRAD 读取器 —— **8 种语言全部与明文 CSV 精确一致**

  （Test 的 `Platoon 5`/`4`/`2` 三组无歧义映射复现，0 碎片）

  ★ 额外发现并处理**哨兵记录**：末条 `00…80` 的文本是乱码，必须过滤

  （Berlin 的 `'вдоз й-елнаипрУ12ы3П.мётТуРОВМгяжк4'` 是俄文 byte-swap 残留）
- [x] **T1.5** ★ `io/localisation.py`：显示名解析（降级方案）

  —— 链路验证 **Test 5/6、Berlin 865/865 字典键逐字节命中 loc_hash**

  —— 实测覆盖率 **Test 0.062% / Berlin 9.693%**（本体词典放弃后的必然结果）

  —— 未命中降级为 `⟨未知 1d898951…⟩`，**哈希可复制**供外部查

  —— 无 `Name` 字段降级为 `⟨无名⟩`（原版有 16 个这样的连排）

  —— `is_hq()` 实现为**存在性判定**（不是 `== True`）
- [x] **T1.6** ~~定位游戏本体词典~~ → **已取消**（见阶段 0）
- [x] **T1.7** ★ `io/provenance.py`：溯源三档（vanilla / promoted / mod_new）+ `base.zip` 基线

  —— **三 mod 全部匹配实测**：Berlin 186(58+128) / N.Thunder 257(129+128) / Test 0 新增

  —— ★ 证实前缀法在 Test 上漏报 100%
- [x] **T1.8** ★★ `core/differ.py`：**两层 diff 引擎**

  —— ★ **39/39 全检出**（含 33 个同数量换装），修复了勘查阶段的漏报

  —— 装备层展开 + 排除纯引用字段（否则 2213 假差异）+ 连排区间下钻
- [x] **T1.9** `io/agfilter.py`：`is_ag_pawn_deck()` 双条件判定（无 `DeckName` **且** 有战斗群）

**五个验收命令全部 PASS**：

```bash
python -m ndfbin_decks.selfcheck      # 往返无损        7/7
python -m tests.test_tradic            # 词典 vs 明文CSV  8 语言全一致
python -m tests.test_localisation      # loc_hash 链路    865/865 命中
python -m tests.test_provenance        # 溯源三档         三 mod 全匹配
python -m tests.test_differ            # 两层 diff        39/39 检出
```

---

## 阶段 2 · 数据模型

> ⚠ **关于 `旧文件（疑似路线错误）/`**（2026-10-12 决策：**保留，谨慎采用**）
>
> 旧版打包出的 EXE **反复出现启动未响应，久治不愈**，
>
> 怀疑**工程路线上存在方向性错误**（不是局部 bug）。
>
> 处理原则：
>
> - ✅ **可参考**：数据结构设计（`DeckFile` / `Battalion` / `Company` / `Platoon` / `Entry`）、算法思路
> - ⚠️ **不直接采用 GUI 部分**（`deck_gui.py` 1352 行）—— 与未响应问题高度相关，
>
>   GUI **从零重写**，只借鉴交互设计意图
> - ⚠️ **逐模块验证**：每个模块搬过来后立刻跑三 mod 自测，
>
>   不通过就自己重写，**不要「修补旧的」**
> - 📌 阶段 7 前不删除，作为参考实现存档

- [x] **T2.1** ★ `core/deckmodel.py`：**贴近旧代码结构**（2026-10-12 决策：A 方案）

  `DeckFile` → `Battalion` → `Company` → `Platoon` → `Entry`

  —— 按指正修四处：`battalions()` 用 `is_ag_pawn_deck()` 取代 `AGF_` 前缀过滤、

  `IsHQ` 改存在性判定、`Window` 保留 `(PackIndex,Number)` 原始二元组、

  `name_hash` 保留哈希原文 + `display` 另行解析

  —— 规模验证：Test 2208 AG/128 PvP/42258 连排，Berlin 2266/43118，N.Thunder 2337/44450
- [x] **T2.2** 字段语义对齐完成 —— `IsHQ` 走 `localisation.is_hq()` 存在性判定；

  实测 **16 个连排无 `Name` 字段**，降级为 `⟨无名⟩`（与原版一致）
- [x] **T2.3** ★ `Window` 类显式建模区间：`pack_index` / `count` / `end` / `slots()` / `overlaps()`

  样例输出：`[0..2]x3`、`[3..5]x3` —— 用户直接看得懂「占用哪几个槽位」
- [x] **T2.4** 接入 `agfilter` —— `deck_objects(ag_only=True)` 为默认，

  `skirmish_count()` 单独报告被过滤数量（三个 mod 均为 128）
- [x] **T2.5** 接入 `localisation` —— `Platoon`/`Company` 各带 `name_hash` + `display`

  未命中显示 `⟨未知 5fe668d5…⟩`（哈希可复制），无 `Name` 显示 `⟨无名⟩`
- [x] **T2.6** 接入 `provenance` —— `Battalion.origin` 字段就位（待 GUI 填充展示）

  ★ 顺带完成 **T3.1–T3.4**（硬校验已随模型实现，见下）

---

## 阶段 3 · 校验器（写回前必跑）

- [x] **T3.1** 硬校验：`Σ(Number) == len(DeckPackList)`

  —— 原版 + 三 mod 的 AG 牌组 **100% 达标**，可硬拦
- [x] **T3.2** 硬校验：`PackIndex + Number <= len(DeckPackList)`
- [x] **T3.3** 硬校验：每个连排恰好被一个战斗群引用 —— ★ 修掉一个真 bug（见日志）
- [x] **T3.4** 硬校验：所有 `obj_ref` 的 `object_id < object_count` 且 `class_id` 匹配
- [ ] **T3.5** 软警告：每战斗群 `IsHQ` 数 ≠ 1

  ⚠ **别默认「1」是对的**：Berlin 255 个战斗群**全部是 0 个**
- [ ] **T3.6** 软警告：连排数 > `MaxNbSmartGroupByCombatGroup`(6)
- [ ] **T3.7** ★ **新建师时自动追加 `DivisionIds`**

  —— 两个 AGF mod 都漏了（5 / 129 个师），不注册则卡组无法存档
- [x] **T3.8** 写回后自动重解码校验 —— `selfcheck` 已按**未压缩体**判定

---

## 阶段 4 · 编辑操作

> **风险排序依据（2026-10-12 修正）**：按「牵连文件数 × 破坏数据的不变量」排。
>
> 初版把「改数量」排在「换装备」前面是**错的** —— 改数量会同时动
>
> `StrategicDecks.ndfbin` 与 `StrategicCombatGroups.ndfbin`，而换装备只动前者。

| 序 | 操作          | 牵连文件                                    | 破坏的不变量                                  |
| - | ----------- | --------------------------------------- | --------------------------------------- |
| 1 | **换装备**     | Deck                                    | 无（槽位数与区间都不变）                            |
| 2 | **改数量**     | Deck **+ CombatGroups**                 | `Σ(Number) == len` ⇒ 全部下游 PackIndex 要重排 |
| 3 | **插删 Pack** | Deck **+ CombatGroups**（+ 可能新建 pack 对象） | 同上，且可能需追加 `TDeckPackDescriptor`         |

- [x] **T4.1** ★★ **换装备** —— **已完成**，严格按工程文件逻辑实现

  —— 用户确认：工程文件下有现成 StrategicPacks 就直接改引用，没有就新建 Pack 对象

  —— 实测证实编译产物行为一致：pack 对象**内嵌在 Deck.ndfbin**（5182 个，**0 个导出**），

  `DeckPackList` 条目全部是纯 `obj_ref`（188505 条形态完全一致）

  —— ★ **唯一差别**：NDF 按**名字**查（`~/Descriptor_StrategicPack_*`），

  编译后 pack 无名字 ⇒ 编辑器按**内容签名**建索引：

  `PackKey = (UnitDescriptor, TransporterDescriptor, ExperienceLevel, Number)`

  —— 两条路径均实测通过：`edit/equip.py` 的 `swap_slot()`

  · reuse 命中已有 pack → 只改一个 `object_id`，**不追加任何对象**

  · 未命中 → `append_graph_objects` 追加 pack + 重建 `IMPR` 路径树

  —— 换装只动 `DeckPackList` 一个字段，**槽位数不变 ⇒ 区间完全不用动**
- [x] **T4.2** ★★ **改数量** —— **已完成**，按 W1–W4 整牌组规范化重算

  —— 原理参考 `WarnoModEditor-0.4.0/src/utils/ag_model.py` 的 `compile_deck()`

  —— ★★ **W1–W4 铁律已在 `.ndfbin` 上实测，三个 mod / 6811 个 AG 牌组各 100%**：

  W1 `ΣNumber == len(DeckPackList)` / W2 窗口不重叠 / W3 窗口内 pack 全同 /

  W4 `PackIndex` == 按「牌组→战斗群→连排→条目」顺序铺开的累计偏移

  —— ★ **W4 是钥匙**：`PackIndex` 不是存储状态而是算出来的 ⇒ 合法布局唯一 ⇒ 必须整牌组重算

  —— ★★ **幂等性实测**：对未改动牌组重算 215168 次（Test 70300 / Berlin 71364 /

  N.Thunder 73504），零漂移，重建字节与原文件**逐字节相同**

  —— 实测影响面：改一个数量平均重排 **18 个下游窗口**（最多 88），

  2160/2208 个牌组会跨战斗群边界 ⇒ 逐窗口局部改必然漏

  —— 新增/删除的槽位**复用该窗口已有的 pack 对象**（W3：N 个槽位是同一 pack 重复 N 次），

  不新建也不销毁 pack；因 97.2% 的 pack 跨牌组共享，减引用不会产生孤儿

  —— ★ 连排对象与牌组**严格 1:1 零共享**（129826 个对象各被引用 1 次）

  ⇒ 改一个牌组绝不牵连其他牌组

  —— 官方上限（连排≤6/战斗群≤5/条目≤3）改为**软警告**：原版数据自己就超

  （实测 7 连排、4 条装备、6 战斗群都存在），硬阻断会拒绝合法编辑

  —— `length` 字段必须与 `items` 同步，否则编码器报 collection length mismatch

  —— 两个编辑器（equip / quantity）**共享同一份解码图，就地修改**，

  各自拷贝会互相静默覆盖
- [ ] **T4.3** ★ **插入 / 删除 Pack** —— 风险最高，放最后

  \- 分两种情况：

  \- **a) 有现成的 `TDeckPackDescriptor`**（游戏里已存在该装备组合）

  → 只需在 `DeckPackList` 插入引用 + 重排 PackIndex

  \- **b) 没有现成的** → **必须新建 `TDeckPackDescriptor` 对象**

  → 用 `append_graph_objects` 追加，并自动延长 `CLAS`/`PROP`/`CHNK`

  → 新对象的 `ExperienceLevel` / `TransporterDescriptor` 要有默认值策略

  \- b 情况还要确认：新建的 pack 对象**能否被游戏正确识别**（未在游戏内验证过）
- [x] **T4.4** ★ **改`ExperienceLevel` / `TransporterDescriptor`** —— **已完成**
    
  —— 实测确认这两个字段属于**pack 内容签名**：2100 种装备里**1082 种**有多个变体，
    
  全由xp/transport 区分 ⇒ 改它们**不是原地写字段**，而是把槽位指向另一个 pack
    
  —— 实现：`DeckEditor.set_experience()` / `set_transporter()`（统一走 `_repoint`
    
  → `swap_slot` → `ensure_pack`），与 T4.1 完全同一条管线
    
  —— 实测取值分布：`ExperienceLevel` ∈ {1: 93740, 2: 69139, 缺失: 17563, 3: 1942}；
    
  `TransporterDescriptor` **53.90%** 有值、共 **218** 种
    
  —— ★ 顺带修一个真bug：新pack 对象必须注册进 `_by_id`，
    
  否则**未保存状态**下槽位指向的对象查不到（GUI 预览会失败）
- [ ] **T4.5** 新增 / 删除连排
- [ ] **T4.6** 新增 / 删除战斗群
- [ ] **T4.7** `IsHQ` 切换 —— ★ **取消勾选 = 删除属性，不是写 False**

  （全库 0 例「存在但为 False」，写了会留垃圾属性）
- [ ] **T4.8** 改名（从已有 loc_hash 下拉选，**不支持自由输入**）

---

## 阶段 5 · 溯源视图

- [ ] **T5.1** 牌组列表打三档来源标签
- [ ] **T5.2** 「mod 改了什么」面板：基线 diff 结果
- [ ] **T5.3** 师级聚合视图（「`TCH_1TkD` 师有 12 个牌组被修改」）
- [ ] **T5.4** 区分「源」与「产物」

  ⚠ 源可能比产物新（Test 源改 39 个、产物只体现 34 个）

  —— **判断「游戏里生效了什么」以产物为准**

---

## 阶段 6 · GUI（从零重写，不复用旧代码）

- [x] **T6.1** 骨架（PySide6）+ mod 选择器（复用 `io/modlocator`）—— **已完成，可实测**
    
  —— 复用 `WarnoModEditor-0.4.0/.venv`（已有 PySide6 6.3.2），只需补 zstandard/lz4
    
  —— 新增 `app/session.py`（三编辑器共享一份解码图+ 变更日志）
    
  与 `app/gui.py`；入口 `run_editor.py` + `启动编辑器.bat`
    
  —— 无 mod `Gen/` 的 AGF 暂存命名空间会抛 `ModNotFound` → 灰显跳过
- [x] **T6.2** 四层树：牌组 → 战斗群 → 连排 → **窗口** —— **已完成**
    
  —— 窗口层显示 `[i..j]xN 装备名`，点连排即高亮它占用的槽位
    
  —— 选中连排**等同于**选中其窗口（`_need` 允许 sg 走 entry 路径）
- [x] **T6.3** ★ **Pack 槽位表显示下标 0..N-1** —— **已完成**
    
  —— 六列：槽位 / 装备 / 运输 / 经验 / 件数 / **被引用于几个窗口**
    
  —— 「被引用于」列揭示 97.2% 的 pack 被多窗口共享 —— 这是替换装备时的关键约束
    
  —— 选中连排时其占用槽位**绿色高亮 + 加粗**，让「区间」语义可见
- [ ] **T6.4** ★ **区间冲突实时检测**：改 `Number` 时提示

  「将占用 pack[5..7]，第 8 号连排会与之冲突」
- [x] **T6.5a** ★ **换装对话框：明文装备下拉** —— **已完成**
    
  —— 新增 `app/catalog.py`（PackCatalogue）+ `app/swap_dialog.py`
    
  —— ★ **只提供本 mod 现有装备包，绝不跨 mod**（用户明确要求）：
    
  跨 mod 会引入 `IMPR` 树解析不了、游戏也无定义的装备，**静默失败**
    
  —— 边界写进代码：`build()` 只接受一个 DeckFile；`owns()`/`owns_key()`
    
  是唯一闸门；`parse_unit_path()` 纯语法不做存在性判断
    
  —— 实测：Test 的 Deck.ndfbin 含 5173 个可选 pack / 2100 种 unit，
    
  含 mod 自建的 `T72M1_TCH`；但**mod 定义却从未使用的装备不在其中**
    
  —— 界面：搜索（装备名/运输机/id/`经验3`/`xp3`）+ 国家分组 + 手动输入 + 经验等级
    
  —— 「插入装备条目」也改用同一对话框（原先硬编码沿用第一条装备）
- [x] **T6.5b** ★★ **换装重排不合规：槽位级换装是设计错误** —— **已修复**
    
  —— 用户实测「BM27 -> T72_CMD_SOV」后复核发现：只改了 1 个槽，
    
  而窗口 `start=0 count=3` 覆盖槽 0/1/2，结果成了混合窗口
    
  `[T72_CMD_SOV, BM27, BM27]`（原三槽均为 BM27，合规）
    
  —— ★ 根因：`DeckEditor.swap_slot` 直接 `pool[slot]=pack` **绕过 `relay`**。
    
  `DeckPackList` 是**窗口序列**非自由槽池；且重排器从 `pool[start]`
    
  重建池子，混合窗口下次重排会**塌陷到首槽、其余装备静默删除**
    
  —— ★ 修复三层（写成结构上无法再犯）：
    
  1\) 删除全部槽位级写入（`swap_slot`/`set_experience`/`set_transporter`）
    
  2\) 新增 `DeckEditor.swap_entry(did,ci,si,ei,want)`：`ensure_pack`
    
  \+ `relay(pack_edits={(ci,si,ei):pid})`，池子由各条目 pack 重新发射，
    
  **"半个窗口"无法表示**
    
  3\) `relay` 开头加 **W3 守卫**：窗口内 pack 不一致直接拒绝、不动数据
    
  —— 新增 `Retiler.heal_window()` 显式修复混合窗口，**必须指定保留哪个
    
  pack，拒绝猜测**（猜测就是重蹈覆辙）
    
  —— 界面 `SlotTable` -> **`EntryTable`**：一行 = 一个条目，
    
  槽位范围降级为只读信息；`on_swap` 只认表格行（原先回退树节点会弹模态框）
    
  —— ★ 模型陷阱：`platoon.entries` 是**槽位级**，`platoon.windows` 才是
    
  **条目级**且与 `relay._windows` 完全一致（实测 9082/9237 条零错位）
    
  —— 顺带修真 bug：`differ` 净增量统计（27 个换 3 个曾报 `-27`）；
    
  `_build_resolver` 无 `Gen/` 的 mod 会崩 `Session.load`
    
  —— 柏林文件已按用户选择修复为 3× T72_CMD_SOV：**全文件 0 error**
    
  （原 1 error），槽3以后零影响；备份 `.bak` + `.ndfbin.mixed.bak`
- [ ] **T6.5** 改名用**下拉框**（`localisation.all_names()` 提供候选）
- [x] **T6.10** ★★ 待选装备清单漏单位（原版 Su27 / 工坊 mod 自有单位） —— **已修复**
      —— 根因：清单是 `PackCatalogue.units()` =「本文件里被 **AG 牌组**引用过的
        pack 的 unit」。它答的是"这文件用过它吗"，用户问的是"这单位存在吗"。
        Test 文件引用 2100 种而原版定义 **2898** 种（漏 810）；
        A World in Flames 自有 788 个新单位只在 `Unit.ndfbin` 里，`Deck.ndfbin`
        一个都没引用 → 全漏。
      —— ★ **NDF 体系实测**：原版数据在
        `<WARNO>/Mods/ModData/base.zip` → `GameData/Generated/Gameplay/Gfx/
        UniteDescriptor.ndf`（文本，2898 个单位）。**不在** `<WARNO>/Gen/NDF/GFX/`
        （空的），也不在 `Data/PC/*/ZZ_*.dat`（20GB edat 归档）。
        项目树 `<mod>/GameData/.../UniteDescriptor.ndf`（仅本机 mod）；
        编译态 `<mod>/Gen/NDF/GFX/Unit.ndfbin`（工坊 mod 唯一形态，AWF 3686 ⊃ 2898）。
        共享 `Mods/ModData/base.zip` **优先于** mod 自带快照（后者可能落后一个补丁）。
      —— 新增 `io/unit_universe.py`：`UnitUniverse(vanilla/project/compiled/referenced)`
        + `origin()`（原版 / 本mod / 本文件）；`mod=None` 也拿共享基线。
      —— ★ 新增 codec 快路径 `read_exports()`：抽 `_open_containers()` 出去，
        只走 EXPR+TRAN → **2.001s → 0.028s（70×）**，与 `decode()['exports']` 逐条相等；
        `decode()` 改调 `_open_containers`，selfcheck 仍逐文件字节级往返 PASS。
      —— 对话框：下拉 = 全集（Test 2910 / AWF 3686）带来源标签
        `Su_27K_SOV · 原版`；新增「只列出将军模式已引用过的」复选框。
      —— ★ **安全判据改为「任何定义文件里有没有它」**（不再是 AG 引用与否）：
        原版/本 mod 单位 = 普通 `create` 并注明来源；三处都查不到才二次确认。
      —— 端到端（副本）：选 Su_27K_SOV → create、accept 零弹窗 →
        `created=59950` → 窗口 2 件全变 → 0 error → 写盘 → 读回一致 → 0 error。
      —— 新增 `tests/test_unit_universe.py`（6 节全 PASS）。
- [x] **T6.11** ★ 师下拉打字无效 + 国家选择 + 按国家批量替换 —— **已完成**
      —— (1) **师下拉输入无效**：两条 Qt 陷阱叠加。
        ① `_on_typed` 调了 `setCurrentIndex(0)` —— 可编辑下拉设置 currentIndex 会
        **改写输入框文本**，下一键接在后面：`SOV` → `SOV_27GMRD  (21 营)OV`，0 匹配。
        ② 过滤移除当前行时 **QComboBox 会清空输入框**（Qt 内部行为，`blockSignals`
        挡不住），需在过滤后把用户敲的文本放回去。
      —— ★ 最终设计（不依赖焦点）：**输入框恒为空，当前选择显示为占位提示**
        （`_sync_edit()`），且 `currentIndexChanged` 也接到它 —— 否则用户从下拉
        点选时文本框又留下标签。打字 = 全新搜索；回车提交首个匹配
        （`accept_typed`，否则 `NoInsert` 让回车静默无效）；补全弹窗点选 →
        `completer.activated` → `_pick_text(text)`；失焦 → `_restore()` 撤销未完成搜索。
        新增 `current_label()`（`currentText()` 现在恒为空）。
      —— ★ 修 `current_path()` 的两种 None：**有合法行但 data 为 None** = 用户选了
        「全部师/全部国家」，None 就是答案；**没有合法行** = 过滤掉了，回退 `_last_data`。
        之前一律回退，导致「全部师」条目根本选不动。
      —— (2) **国家**：新增数据层 `io/divisions.py`（师标签解析 + 国家码 + 别名）。
        规则 = 标签首个 token；实测 233/233、238/238、233/233 都有下划线。
        ★ **东德在师导出里是 `RDA`、在单位里是 `DDR`**（Eugen 是法国公司），
        别名表让 DDR/FRG/USSR/USA 都能命中，标签写作 `RDA / DDR  东德  (18 师 · 229 营)`。
        GUI 加 `国家 Nat` 下拉（在师左边）：选国家 → 师列表 233→54，
        索引 0 为「全部师（SOV · 54 师）」覆盖该国 515 营，树根 `师Div SOV 全国 · 苏联`；
        默认仍停在具体师上（「全部师」= 2208 营的树太大）。国家内可继续打字过滤。
      —— (3) **批量替换加「本国 Nat」层级**：`LEVELS` += `country`，
        `Scope.country` + `contains()` 用 `country_code()` 判定。没有国家的师按钮置灰。
        ★ 踩到 `replace_dialog.py` 自己抄了一份 `LEVEL_LABELS`（按钮有、标签 KeyError），
        改为统一从 `edit.bulk` 导入。
      —— 端到端（副本）：SOV 全国替换 `MANPAD_Igla_SOV` → 1780 条/2617 件/355 营，
        0.8s，0 error，写盘读回一致。★ **边界用跨国共用 pack 验证**：
        `pack#3649` 同时被 RDA(12 槽) 与 SOV(12 槽) 使用，SOV 全国替换后
        **SOV 残留 0、RDA 残留 12 原封不动**。
      —— 新增 `tests/test_divisions.py`；`test_gui` 扩 3b/3c 与批量国家层级。
## 阶段 7 · 打包发布

- [x] **T7.1** ★ 打包发布 v0.1（onefile EXE + 图标 + 任务栏悬停提示） —— **已完成**
      —— 产物：`dist/Warno Ndfbin Decks Editor v0.1.exe`
        37,656,685 B ｜ md5 `d911c803f98c73d35fbae2493c4074f5`
      —— **入口收敛为单一 `main.py`**（冻结与源码共用）；`run_editor.py` 变成
        4 行转调，免得两处 bootstrap 各自漂移。`ndfbin_decks/paths.py` 集中回答
        「文件在哪」：`resource_path()`（包内只读）vs `data_dir()`（用户目录）。
      —— ★ **窗口标题 = `Play Any Unit In Any Mod`**。Windows 任务栏悬停显示的
        就是**窗口标题**，所以标题直接设成这句；产品名留给文件名 / 属性页 /
        任务管理器，另外在界面右下角加了一枚灰色戳记 `Warno Ndfbin Decks
        Editor v0.1`。**实测**（`GetWindowText` 读真实窗口）标题就是这句原文，
        Qt 没有追加 `applicationDisplayName`。
      —— ★ **图标**：`assets/make_icon.py` 从源图自建 ICO（Qt 解码 + 逐级二分缩放），
        9 档 16/20/24/32/40/48/64/128/256，**每档都是 32 位 DIB 而非 PNG** ——
        PyInstaller 是把条目字节原样拷进 `RT_ICON`，PNG 条目会变成非法资源。
        实测：源图 → ICO → `RT_ICON` → 壳 `QFileIconProvider` 读回来就是那只熊。
      —— `--windowed` 的两个坑：① 冻结后 `stdout/stderr` 是 `None`，库一写入
        就 `AttributeError`；② 启动即崩时用户什么都看不到。`main.py` 把两者
        都接到 `%LOCALAPPDATA%\WarnoNdfbinDecksEditor\app.log`，异常另写
        `crash.log` 并弹框指路。`NDFDECKS_HOME` 可改写到别处（冒烟测试靠它隔离）。
      —— 启动耗时（实测）：**热启动 1.3–1.6 s**（1.3 s 解包 + 0.3 s 导入）；
        全新 EXE 首次冷启动约 4–7 s（Defender 扫描 + 无文件缓存）。
        包内 94 MB 未压缩载荷里 `opengl32sw.dll` 占 20.9 MB、Qt 翻译 5.8 MB ——
        想再瘦身需要换 spec 构建做载荷过滤，当前未做。
- [x] **T7.2** 发版流水线（构建 / 验证 / 提升三步分离）
      —— `build_exe.py`：版本号从 `ndfbin_decks/__init__.py` 正则读取（单一来源）；
        只写 `build_0.1/` 与 `dist_0.1/`，**绝不碰 `dist/`**（那是已发布二进制）；
        所有 `--add-data`/`--icon` 用绝对路径（相对路径会被按 spec 目录解析，
        PyInstaller 只 warn 不报错、退出码仍是 0）；缺产物返回 1；
        用 `CArchiveReader` 读回清单断言 8 项载荷 —— ★ 注意**纯 Python 模块在
        嵌套的 `PYZ-00.pyz` 里**，顶层 toc 只看得到载荷，不看 PYZ 会误报全部缺失。
      —— `verify_exe.py`：在**一次性 cwd** 里启动、`NDFDECKS_HOME` 指向临时目录，
        断言「有日志 / 版本号与代码一致 / 无 ERROR / 模块图已解析 / 进程仍存活」，
        再**实测原生窗口标题**与**壳读回的图标**，然后杀进程树（onefile 会派生子
        进程，只 terminate 父进程会留下野 GUI）。
      —— 提升：`cp dist_0.1/… dist/…` + 两侧 `md5sum` 比对一致。
        候选与发布版 md5 均为 `d911c803f98c73d35fbae2493c4074f5`。
      —— 新增 `tests/test_release.py`（30 项断言）守住版本单一来源、图标格式、
        标题即提示语、冻结路径语义、崩溃可见性、以及构建脚本不越界删目录。
- [ ] **T7.3** 发版前待办：代码签名（现在没签，首次运行会被 SmartScreen 拦）、
      可选载荷瘦身（见 T7.1）、onedir 变体（启动可再快，但要发文件夹）
- [ ] **T6.6** 校验结果面板（硬错误 / 软警告分色）
- [x] **T6.7** 保存前确认 + 备份 —— **已完成**
    
  —— 覆盖原文件前先写 `.ndfbin.bak`；有硬错误时拒绝保存并列出前5 条
- [ ] **T6.8** ⭐ **实地实测**（换装下拉已就绪）（当前最高优先）
    
  —— 双击 `启动编辑器.bat` → 双击 Test → 改数量 → 保存 → **进游戏验证**
    
  —— 待补：改名下拉（T6.5）、
    
  溯源标签（T5.x）、校验面板（T6.6）


## 阶段 8 · 界面多语言 + 批量替换升级（2026-10-13 立项）

### T8.1 ★ 界面本地化（英 / 法 / 德 / 俄）

> **立项实测（2026-10-13）** —— 先量了规模再定方案，不凭感觉：
>
> | 项                    | 实测值                                            |
> | -------------------- | ---------------------------------------------- |
> | 含中文的字符串字面量        | **392** 处（其中 **85** 处在 f-string 里）             |
> | 去重后不同的中文串         | **299** 条，共 **2833** 字，平均 9.5 字，291 条 ≤ 50 字   |
> | 分布                  | `app/` 249 · `edit/` 39 · `io/` 33 · `main.py` 3 · `core/` 1 |
> | `pyside6-lupdate/-lrelease/-linguist` | **本机可用**（PySide6 6.12.0 自带）                    |
> | Qt 自带 `qt_de/fr/ru/en.qm` | **已随 PyInstaller 打包**（就是那 5.8 MB）→ 标准按钮（Cancel→Annuler/Abbrechen/Отмена）**实测已能译** |
>
> ⇒ **翻译量不是瓶颈（1196 条译文），瓶颈是 299 处调用点改造**。方案围绕"改造自动化 + 可验证"来定。

- [x] **T8.1.1** ✅ `ndfbin_decks/i18n/`：自建 `tr()` + JSON 词表
      —— 已落地：`__init__.py`（`tr` / `live` / `set_language` / `available` / `coverage`）、
        `settings.py`（`data_dir()/settings.json`，纯文本可手改）、`qt_builtin.py`（Qt 自带 qm）
      —— ★★ **实测发现：模块级常量在 import 时求值，`tr()` 会把它冻在启动语言里。**
        9 处（`COUNTRY_NAMES` / `LEVEL_LABELS` / `HEADERS` / `EXPERIENCE_CHOICES` /
        `NO_TRANSPORT` / `TYPE_HINTS` / `SOURCE_LABELS` / `UNKNOWN_TEMPLATE` / `ANONYMOUS`）
        改用 `live(globals(), "NAME", lambda: …)` —— `set_language` 时重跑工厂，
        于是常量和窗口里现建的文字一样"活"。
      —— 语言下拉只列**真有词表**的（`i18n.available()`）：没有词表却列出来，
        用户点了得到中文，看起来像坏了，不像没做完。
      —— 选型：★ **不用 Qt Linguist 的 .ts/.qm**，用自建 JSON。理由：本项目没有 `.ui`
        文件，Linguist 赖以自动生成的 `retranslateUi()` 无从谈起；且需要给
        `edit/` `io/` 这些**非 QObject 模块**也做翻译（`QCoreApplication.translate`
        要手写 context）。JSON 可直接 review、无构建期依赖、切换语言无需重装 translator。
      —— **键 = 中文原文**（source-as-key）：zh_CN 不需要词表，缺失即回退原文，
        新增界面文本时不会出现"忘了加 key 就显示空白"。
      —— Qt 自带控件沿用 `qt_<lang>.qm`（运行时从 `QLibraryInfo.TranslationsPath` 加载），
        **不需要**把标准按钮抄进自己的词表。
- [x] **T8.1.2** ✅ `tools/i18n_wrap.py`：**codemod 把裸中文字面量包成 `tr(...)`**
      —— 实测：**295 处调用，去重 258 条键**，13 个文件 + `main.py`
        （81+31 / 32+8 / 30+3 / 19+10 / 13+6 …），运行 1 秒内，先用无参 dry-run 出清单
      —— ★★ **实测踩坑 1：f-string 内部的常量在 CPython 里报告的是"整个 f-string"的跨度**
        （`col_offset` 指向 `f`），于是同一段字节被改两次，产出垃圾语法。
        修法：处理 JoinedStr 时把整棵子树标记为已消费。
      —— ★★ **实测踩坑 2：按方法名判日志调用会吞掉 `QMessageBox.critical`**（那是给用户看的
        对话框，不是日志）。改成**接收者 + 方法名**双判据。
      —— ★★ **实测踩坑 3：字面量大括号只在"真有占位符"时才转义**。无字段的键不走
        `.format()`，转义了就会把 `{{` 原样显示出来。
      —— ★★ **实测踩坑 4：模块级 `AnnAssign`（`COUNTRY_NAMES: dict[str, str] = {…}`）**
        也要按常量处理，否则它留在启动语言里。
      —— 用 `ast` 定位（含 `col_offset` 精确字节区间），只改字面量那一小段，不动别处。
      —— f-string 转 `tr("…{name}…", name=expr)`：简单 `Name`/属性取原名，
        复杂表达式退化为 `v0/v1`，**绝不猜语义**。
      —— ★★ **验收不变量：codemod 前后「全部中文串的多重集合」必须逐条相同** ——
        证明没有改坏任何文本；再跑全量 14 项回归 + `python -m compileall`。
      —— 先 `--dry-run` 出改动清单，人工抽看再落盘。
- [x] **T8.1.3** ✅ `tools/i18n_sync.py`：从代码里扫 `tr("…")` 生成/更新词表
      —— 报告新增键 / 孤儿键 / **占位符不符**（后者会在渲染时 `KeyError`，必须拦在这）；
        `--min 90` 可给 CI 当闸门
      —— 现状：`en: 258/258 (100%)，占位符不符 0`
      —— 报告**新增键**（待译）与**孤儿键**（译文里已删的中文），退出码非 0 给 CI。
- [x] **T8.1.4** ✅ `ndfbin_decks/i18n/en.json`（**258/258，100%**）
- [x] **T8.1.4b** ❌ **取消** —— 用户决定（2026-10-13）：**只保留 zh_CN + en，不做 FR/DE/RU**
      —— 落地：`i18n.LANGUAGES` 收到 2 项（列表 = 本版本真正支持的语言，不列空头承诺）；
        `qt_builtin.QT_CODES` 同步收到 `zh_CN` / `en`；
        `tools/i18n_sync.py` 的默认语言列表改为**从 `i18n.TABLE_CODES` 派生**
        （原先写死 `["en","fr","de","ru"]`，取消后会天天报"fr 覆盖 0%"）
      —— ★ 教训：**写死的语言列表是第二个真相源**。凡是"支持哪些语言"，
        一律从 `LANGUAGES` 派生，别在工具里再抄一遍
      —— 将来要加：在 `LANGUAGES` 加一行 + 放同名 json + `QT_CODES` 加一项，其余自动
- [x] **T8.1.5** ✅ `tests/test_i18n.py`：**13 项断言全过**
      —— zh_CN 免表直通 / 英文 100% 覆盖 / 占位符集合一致 / **切语言后模块级常量跟着变**
        （实测 `LEVEL_LABELS["division"]` → `This division`、`COUNTRY_NAMES["SOV"]` →
        `Soviet Union`）/ 选择可持久化 / 未知语言码回退中文而不是空白
      —— 断言：每种语言的覆盖率 ≥ 阈值、译文里的 `{}` 占位符与原文**集合相同**
        （少一个就在运行时 `KeyError`/`IndexError`）。
- [x] **T8.1.6** ✅ 语言切换入口 + 记忆选择（`data_dir()/settings.json`）
      —— ★ **不重建窗口**：每段静态文字注册成 lambda（`self._rt(lambda: …)`），
        切语言就是**重放同一批 `tr()` 调用**，再 `_fill_tree()` + `_refresh_mods()`
        刷动态文字。重建窗口会丢未保存的改动，这条路不会。
      —— 下拉放在筛选栏最右，**条目用各自语言写自己的名字**，不需要"语言"这个标签
      —— Qt 自带控件走 `qt_builtin.install()`：`Cancel → Annuler / Abbrechen / Отмена`
      —— ★ **不重启、不重载文件**：`MainWindow.retranslate()` 重设静态文本，
        再 `_fill_tree()` 重刷动态文本；对话框是**用时才构造**的，自动跟随当前语言。
        这样切语言**不会丢未保存的改动**（重建窗口会丢）。
- [x] **T8.1.7** ❌ **取消** —— 随 FR/DE/RU 一并取消（复数需求只由俄语引出，
      zh 1 式 / en 2 式里 `{n} 个营` 直译够用）。真要做 RU 时再上 `trplural` + CLDR
- [x] **T8.1.8** ✅ 打包：`build_exe.py` 已按**逐个 json** 加 `--add-data`
      （目录源会把包的 .py 一起拷进去；JSON 是数据，静态分析永远找不到它）
      —— 缺表时构建直接失败，不会静默出一个"只会中文"的 EXE
      —— `tests/test_release.py` 补两条断言：
        ① **产物名不再写死 `v0.1.exe`**（改成校验 `APP_NAME` + 版本号拼装，
          否则每次发版都要改测试 —— 写死的"真相"必然过期）
        ② **下拉提供的语言 == 打包带的表**（`i18n.available()` vs `i18n/*.json`），
          防止"EXE 里点了英文却给中文"或"表做完了没进包"
- [ ] **T8.1.9** ★ **不译清单（写死，别顺手翻）**
      —— `APP_TAGLINE` = `Play Any Unit In Any Mod`（**任务栏悬停提示**，用户指定原文）
      —— 产品名 / 版本号 / 右下角戳记
      —— `app.log` 与 `crash.log` 内容（排障用，中英对照更省事）

### T8.2 ★ 批量替换：从「一换一」升级为「多换一」

> **立项实测（2026-10-13，Test 文件 `SOV_27GMRD` 师，仅内存不落盘）**：
>
> | 项               | 实测值                                        |
> | --------------- | ------------------------------------------ |
> | 该师范围内装备种类     | 88 种                                       |
> | 选 3 种作来源      | pack#4376(120条) + #4100(51条) + #5172(40条)   |
> | 影响范围          | **19 个营 · 69 个连 · 172 个排 · 211 条装备 · 422 件** |
> | 执行结果          | `211 条装备 → pack#5173，复用既有装备包`             |
> | 硬校验 errors    | **before 0 / after 0**                      |
> | W1（ΣNumber==len）| **19/19 个被改动的营全部成立**                      |
> | 非来源装备         | 残留来源 **0** 条；其它装备 863 条原封不动               |
>
> ⇒ ★ **数据层只需要改一个谓词**：`pack_id != self.from_pack_id`
> → `pack_id not in self.from_pack_ids`。`apply()` 本来就是「按营聚合 edits
> → 每个营一次 `relay`」，多种来源天然合并进同一次重排，**不需要两趟、不需要新管线**。

- [x] **T8.2.1** ✅ 数据层：`ScopedReplace.from_pack_id: int` → `from_pack_ids: frozenset[int]`
      —— `usage()` / `survey()` / `apply()` 共用同一个 `_in_scope()` 谓词，改一处即可
      —— `ReplaceSurvey` 增 `sources: int`（来源种数），`summary()` 里体现
      —— ★★ **实测发现：目标剔除必须按「内容」比，不能按「对象 id」比。** 文件里
        同时存在 pack#975 与 pack#4050 两个**签名相同**的对象，`ensure_pack(key)`
        解析到哪个由索引决定 —— 于是"用户勾的那行 id == 目标 id"这个判据**会漏**，
        把目标当成普通来源、拿它换它自己。改成 `pack_key(p) != to_key`。
- [x] **T8.2.2** ✅ 对话框左栏改**多选**（勾选框，不要求按住 Ctrl）
      —— 加「全选 / 清空」；已选种数实时显示
      —— ★ 目标装备若也在来源里：**从来源集合中剔除它并明说**（已按内容比较）
      —— ★★ **实测发现：左栏一行 = 一种装备，不是一个 pack 对象。** 同签名的两个
        pack 会并成**一行**显示，勾上即两个都换。否则用户看到两行同名条目，
        勾一个只换掉一半，且"目标是否也是来源"的判断也跟着错。
      —— ★★ **实测发现：`_set_all` 必须自己记录勾选。** 重绘期间 `itemChanged`
        被 `_loading` 静音，只设 checkState 的「全选」会画满整栏却仍报"已勾选 0 种"。
- [x] **T8.2.3** ✅ 影响范围按来源**汇总**（总数 + 种数）
      —— 每种各多少条**不需要展开**：左栏每行本来就写着"— N 条 / M 件"
- [x] **T8.2.4** ✅ `tests/test_gui.py` 加 `10b` / `10c` 两段
      —— 实测：`SOV_27GMRD` 师范围，3 种来源 → `3 种来源，501 条装备 → pack#975，
        复用既有装备包，（42 个营）`；残留 0、非来源零改动、窗口总数 1894 不变、
        hard error 0
      —— 另断言：多源 survey == 各单源 survey 之和（583 条 / 2507 件 / 42 营）
      —— 另断言：目标是唯一来源 → 拒绝并说明；目标+来源 → 剔除后执行
- [x] **T8.2.5** ✅ 手册 `doc/使用教程.md` 已同步；`dist/使用教程.md` 随发版同步
- [x] **T8.4** ✅ **批量替换左栏搜索框**（用户要求，随 v0.3 发版）
      —— 左栏上方 `QLineEdit`，`textChanged` → `_apply_filter()`，
        按**整行文字**匹配（装备名 / 运输载具 / `经验N`），`setHidden` 逐行控制
      —— ★★ **核心设计：筛选只管可见性，绝不动勾选。** 勾选存在 `_checked`
        （pack id 集合）里，与可见性正交；被筛掉的行仍计入"已勾选"，
        计数显示 `筛选出 12 / 400 种，已勾选 5 种`。
        理由：若打字顺手取消勾选，用户一边缩小范围一边就在悄悄缩小这次替换，
        而屏幕上没有任何提示 —— 正是这个对话框最不该发生的事
      —— ★ `全选` 只作用**可见行**（刚筛完点它 = "筛出来的全要"）；
        `清空` 连隐藏的一起清（否则会留下一个屏幕上根本看不到的勾选数）。
        两个按钮语义不同，因此把差别写进 tooltip
      —— ★ 切换范围（`_reload_from`）后**保留搜索词**并重新套用过滤；
        当前行被筛掉时自动落到第一个可见行（右侧选择器开在它上面）
      —— `tests/test_gui.py` 新增 **10d 段 10 项断言**：过滤生效 / 只隐藏不取消 /
        隐藏的勾选仍计数 / `全选` 边界 / `清空` 越界清理 / 清空搜索复原
      —— `en.json` 补 5 条 → **263/263 (100%)**

- [x] **T8.3** ✅ **发布 v0.2**（2026-10-13）
      —— 产物：`dist/Warno Ndfbin Decks Editor v0.2.exe`
        37,692,774 B ｜ md5 `67022cf6727421f0ab09b280ac3ea571`
      —— 内容 = **多换一**（T8.2）+ **界面多语言 zh_CN / en**（T8.1）
      —— 三步流水线照旧：`build_exe.py 0.2` → `verify_exe.py 0.2` → `cp` 进 `dist/`；
        两侧 md5 已比对一致；v0.1 归位到 `dist_0.1/`（未删）
      —— ★ 包内载荷**复核过一遍**（`check_bundled`，168 载荷 / 140 冻结模块）：
        `ndfbin_decks/i18n/en.json` **确实进了包** —— json 是数据不是模块，
        静态分析永远找不到它，不复核就会出一个"点了英文还是中文"的 EXE
      —— 启动耗时（实测两遍）：**热启动 1.3 s**；新二进制冷启动 3.7 s（Defender）
      —— 发版前改动：`tests/test_release.py` 产物名断言**不再写死 `v0.1.exe`**
        （写死的真相必然过期），并补「下拉语言 == 打包带的表」断言 —— 现在 31 项
      —— 双环境（PySide6 6.12 / 6.3.2）14 项回归全 PASS

---

## 阶段 9 · 部队组织架构筛选（2026-10-14 立项）

> 目标：把「阵营 / 战区 / 军 / 师 / 独立单位」做成筛选字段。
> 前置勘查已完成，报告在 `doc/部队组织架构勘查报告.md`（内部文档，不进公开仓库）。

- [x] **T9.1** ✅ **二进制勘查**：三级架构在 `UI/BattleOrder.ndfbin`，不在 `Deck.ndfbin`
      —— ★★ **层级是字段不是深度**：`BackgroundTexture` → 常量 `Value` =
        `Texture_STRATEGIC_{front,corps,division,brigade,regiment}`，
        **643/643 节点零缺失**。用 `Superior` 深度猜会错：25 个 corps 挂 corps、
        5 个 division 无上级、8 个战区级节点里 `TCH_CSLA` 标成 `brigade`
      —— ★★ **阵营不在树里**：7 个 front 的名字不含 NATO/PACT，得读
        `Division.ndfbin` 的 `DivisionTags`；两条独立路径**互证 159/159 一致**
      —— ★★ **`CountryId` / `TypeToken` 是陷阱**：只长在 71 条 `_multi`（多人模式）
        描述符上，而 **AG deck 一条都不引用**（`_solo` 才是 AG）。据此做筛选器会全空。
        `DivisionCoalition` 是 int32 且 175 条**全等于 1**，不是阵营
      —— ★ **`US_` 前缀不代表美国**：`US_BEL_1BEC` / `US_UK_1BrC` / `US_UK_3ArmDiv`
        实为 BEL / UK（据 `EmblemTexture`）。`divisions.country_code()` 取首段会误判，
        238 种里 4 种错（1.7%）
      —— ★ **两条连接路径的覆盖率**：
        ① deck → `Division.ndfbin`：**238/238 = 100%**，阵营 1025 NATO + 1241 PACT
        ② deck → `BattleOrder`：**1767/2266 = 78%**，其中 1709（75.4%）能追到战区级；
           499 个 deck / 74 种名字落空
      —— ★ 落空原因**不是书写格式**：规范化（去分隔符+小写+去后缀）能救回 **0** 种；
        `RDA_MBDIII` vs `RDA_MBIII`（差一个 D）、`ESP_Brigada_Jarama` vs `ESP_Jarama`
        是**两套独立命名**。前缀近似能"救回"18 种但会误配（`RFA_FlaKdo2` → `RFA_FlaKdo1`）
      —— ★ **文件不是每个 mod 都有**：`Test` 只有 `Deck.ndfbin`（无 Division / BattleOrder）；
        `Test` 用到的 233 种 division 名**全部**出现在 Berlin 的 `Division.ndfbin` 里
        —— 那份表是 vanilla 全量 + AGF 新增，`Test` 依赖游戏本体那份（封在 `Data/PC/*.dat`）
      —— 工具固化：`tools/probe_org.py {levels|tree|join|tags}`，双环境可跑
- [ ] **T9.2** `ndfbin_decks/io/battleorder.py`：把树读成
      `节点 → {name, level, parent, children, display}`，与 deck 解耦
      —— 层级判据：`层级 == front` **或** `是根且名字在战区组里`（后者值 225 个 deck）
      —— 缺文件时返回空树，不抛
- [x] **T9.3** ✅ 别名表：`ndfbin_decks/data/division_aliases.json`，**57 条逐条带判据**
      —— 依据分布：`emblem` 19 / `prefix` 19 / `abbr` 12 / `norm` 4 / `attach` 3，
        全部指向真实存在的节点（脚本断言过）
      —— ★★ **实测订正：上一版"规范化救回 0 种"是脚本 bug** —— 判定集合本身就是按
        "规范化后不命中"筛的，于是恒等于 0。实际有 **3 种是纯分隔符差异**
        （`RFA_TK_Nord`/`RFA_TK_Sud`/`POL_3_DLMB`，106 个 deck），去分隔符即命中
      —— ★ **不要用模糊规则生成这张表**：前缀近似会静默把 `RFA_FlaKdo2` 配到
        `RFA_FlaKdo1`。错映射比不映射更糟 —— 显示上毫无异常，营却被归到错误的军下
      —— 剩 **17 种 / 42 个 deck 树里真没有**（`SOV_*ORAP`/`*OCHAP` 独立航空团、
        `TCH_171SAM`/`251SAM`、`NATO_32ADG` 等），不是命名问题
- [ ] **T9.4** 筛选器接线：三级 + 「未知」一档
      —— 阵营（100%）→ 国家（98.3%）→ 战区/军/师（78%）
      —— ★ 落空的 499 个 deck 归入「未编入战斗序列」**并显示数量**，
        不许静默塞进某个战区
      —— ★ 未保存改动的筛选跳转要复用 T8.2 修好的 `_last_data` 路径（筛选链固化）
- [ ] **T9.5** `tests/test_org.py`：断言 front/corps/division 计数、阵营互证、
      层级 ≠ 深度（至少断言 `corps` 的父里同时有 front 和 corps）、
      缺 `BattleOrder.ndfbin` 时降级不抛
- [x] **T9.6** ✅ **填报《将军模式勘察表》**（用户模板 → `桌面/将军模式勘察表_填报.xlsx`）
      —— 三个 sheet：`军级-师`（230 行，用户指定两列格式）·
        `未归属单位`（17 种 / 42 个营 Pawn）· `口径说明`
      —— 表 = 上级（7 战区 + 35 军）→ 其直属下级，逐条对应 `Superior` 字段
      —— ★ **覆盖率两个口径**：定位到树 **2224/2266 = 98.1%**；能追到军
        **1864/2266 = 82.3%**。差额 402 = 战区直属 302 + 无上级独立编队 58 +
        树里没有 42 —— **没有一块是"丢了"**，82.3% 就是"归入军"的天花板
      —— ★★ **实测又发现一个分类 bug**：先前脚本拿带 `_Subordination` 后缀的名字比对
        战区表，永不命中，把 302 个战区直属单位误计入"AGF 独立编队"。以
        `tools/probe_org.py join` 的数字为准

---

## 阶段 10 · 原生二元组映射错误的修正可行性（2026-10-14 立项，只勘探未动手）

> 用户问：1GTA 595 侦察营有原生 `(PackIndex, Number)` 映射错误，现有功能能否修正？
> 报告 `doc/595侦察营映射勘查报告.md`（内部文档，gitignore 已挡）。

- [x] **T10.1** ✅ **确认是原生错误** —— 三份独立来源一致：官方明文源
      `base.zip → StrategicDecks.ndf`、柏林 mod `Deck.ndfbin`、`Test` mod `Deck.ndfbin`
      —— 错误形态：595 与 68 侦察营**排名字相同、窗口形状相同**，但类型序列整体
      **左旋一格**（`A[i] = B[(i+1) mod 5]`），件数没动。
      外显症状 = **指挥车落进非 HQ 的线上排**，HQ 排反倒拿到一辆坦克
- [x] **T10.2** ✅ **能修，但只能逐条换装备**（最小 **14** 条）
      —— ★★ **`swap_entry` 是"重指向"不是"改包"**：`ensure_pack` 只复用/新建，
        从不改既有 pack 的内容 → 因此**顺序无关、不需要过渡值（scratch）**。
        实测四种跑法（正序/逆序 × 19 条/14 条）**产物逐字节相同**（md5 `54afa5f1…`）
      —— 14 条全部复用既有 pack，**新建对象 0 个**，对象数 61,127 不变
- [x] **T10.3** ✅ **批量替换做不了这件事** —— `ScopedReplace` 是**多对一**
      （一组来源 → 一个目标）；连2/连3 需要的是**两窗口对调**：
      先 `A→B` 两边都变 B，再 `B→A` 又都变回 A —— **原地空转**
- [x] **T10.4** ✅ **编辑器看不见这个错误** —— `validate_battalion(595)` **0 条**；
      W1–W4 全过；全文件 0 硬错误、617 条 `hq_count` 警告。校验器只有结构规则，
      "这个排的装备符不符合编制语义"不在其中
      —— ★★ **排的 `Name` 是 obfuscated 显示键，不是类型键**：实测同一键在别处同时
        映射到 Igla 分队 / T-80BV / M1A1 等 144 种装备。
        **"按名字反查别处多数装备"这条自动检测路走不通，别往这个方向做工具**
- [x] **T10.5** ✅ **安全性实测**：爆炸半径**恰好 1 个营**（其余 2265 个营一字未动，
      含参照 68Reco）；**空跑保存逐字节相同**（写盘器无损）；原 mod 文件 md5 全程未变
- [ ] **T10.6** ⚠️ **三个必须实测确认的点**（都不是编辑器能决定的）
      —— ① `compiler-template.json` 把 `Gen/NDF/GFX/Deck.ndfbin` 列为**编译产物**并附
        SHA-256 清单（当前文件 `8ca80d0c…` ≠ 清单 `baa7781e…`，**早已不一致**，
        且运行时显然不校验）。但 AGF 重新 build 会**覆盖手改**；模板记录的源工作区
        `WarnoArmyGeneralFramework-main\artifacts\compiler-workspaces\WarnoAGFEditorBuild9A41607726CB`
        **现已不存在**
      —— ② `Config.ini` 的 `GFX/Deck=7cfc4220…`（标注"mod 兼容性检查用，勿改"）：
        实测**既不等于文件 md5 也不等于 sha256**，无法从形态判断改完要不要同步
      —— ③ `DeckFormatVersion = 1`：本次不改件数/槽位数（103 槽不变），
        理论上不影响存档，但需实测
- [x] **T10.8** ✅ 🐞 **外部用户报来的 `window […]xN exceeds the M-slot pool`**（我方未复现，已解出机制）
      —— 真相：`validator` 里的 `pool` **不是槽列表长度**，而是 `sum(len(entries))`
        = **被窗口覆盖的槽数**。所以这条报错的实际含义是
        **「池子里有槽没有任何排引用（洞）」**，不是"池子不够长"
      —— 复现：在槽 3 插一个无人引用的槽、其后窗口起点 +1 → 池 104 槽 / 覆盖 103 槽
        → 只报 `window [98..103]x6 exceeds the 103-slot pool`，**且不报 Σ 那条**
        （Σ == 覆盖数）—— 与截图形态完全一致
      —— 反推对方：`118` 行至少 1 个空槽，`195` 行至少 3 个空槽，≥2 个营
      —— ★ **已排除"对方跑旧版"**：解包 pre-fix v0.1 / v0.2 / v0.3 四个 EXE，
        比对 `deckmodel._build` / `_entry` / `validator.validate_battalion` 的
        `co_code` 摘要，**与本地源码逐字节相同**
      —— 成因：编辑器合法改动一律走 `relay`，**造不出**这种状态 → 来自编辑器之外
        （mod 自己的生成器 AGF 跳过槽却没重编号 / 手改 / 其它工具）
      —— 清理（实测）：对该营做任意一次走 relay 的编辑（「改件数」填回原值即可）
        → 池 `104 → 103`，校验 `1 error → 0`
      —— 💡 三个待改的缺口：① 对话框只显示 `message`、**不显示 `where`**
        （报错里其实带着营名）→ 报告者不知道是哪个营；② 只显示前 5 条、无汇总；
        ③ 文案 `exceeds the N-slot pool` 在"洞"情形下不准确，且校验器**缺 W2/W4
        （空档/重叠）规则** —— 补一条 `pool_gap` 能把 cryptic 变一眼看懂
      —— ★ 三条缺口已于 **T10.9** 修毕并发 v0.4
- [x] **T10.9** ✅ **修正并发布 v0.4**（2026-10-15）—— 三处一起改
      —— **① 校验器补上 W2/W4「空档 / 重叠」硬规则**（`pool_gap` / `pool_overlap`）：
        按 deck→cg→sg→entry 顺序走累计偏移 `run`，`w.pack_index > run` 报空档
        （并点名**第一个被顶晚的窗口**）、`< run` 报重叠。★ 校准：**13505 营 /
        427451 窗口，0 空档 0 重叠**（7 份文件），所以够格做硬错误
      —— ★★ **根因修正：`window_out_of_range` 以前拿 `pack_count` 当池长，而那是
        "被覆盖的槽数"** —— 于是**有洞的营**会被报成"超出池子"，把人指向错的地方。
        现在改比 `pool_slots`（= 真实 `len(DeckPackList)`），并补上"它到第几格"
      —— ★ **`Battalion.pool_slots` 新增**：把「槽池真实长度」与 `pack_count`
        （被覆盖槽数）分开。**`pack_count` 原来的文档写着 `= len(DeckPackList)`，
        与实现不符** —— 这个文实不符正是上面那个误导的源头
      —— **② 保存被拒的弹窗现在给出 `where`**：每条报错后跟一行
        `— pion_SOV_1GTA_595Reco · 连0/排1`（复用树里的词汇），末尾给
        「共 N 条硬错误，涉及 M 个营」+ 营名清单（各截前 5 条）
      —— **③ `en.json` 268/268 (100%)**（新增 5 条）
      —— 测试：`test_model` 加**「人为造伤」段 9 项断言**（真数据 0 违规 =
        规则从没被跑过，不造伤就分不清规则和笔误）：洞 → 报空档 / **不再**报越界 /
        不触 Σ / 消息点名槽号 / 报在第一个晚到的窗口；重叠 → 报重叠；relay 一改即愈；
        `test_gui` 加 **12b 段 5 项**：走真的 `on_save` 断言弹窗包含营名 + 连排位置 +
        计数，且 relay 编辑后不再拦
      —— 发版：`dist/Warno Ndfbin Decks Editor v0.4.exe`
        **37,696,339 B** ｜ md5 `92aad5d46adff2e9c73acd93e95258c8`
      —— `verify_exe.py 0.4` 全过；★ 另用解包工具从 EXE 里挖出 `pool_gap` /
        `belong to no platoon` / `claimed twice` / 两条弹窗新串，**证明新规则真进了包**
        （不是只改了源码）
      —— 热启动 **1.6 s**（测两遍；同机 v0.3 是 1.3 s，载荷只大 1.9 KB → 噪声）
      —— 手册新增「拒绝保存时那两条，怎么读」：两条报错的**逐字样例都是实测输出**
        （不是手写的），含读法与一句清法
      —— ★ 顺带发现：`ndfbin_decks/data/division_aliases.json` **不在包里** ——
        目前只有 `tools/probe_org.py` 读它，**不进包是对的**；但将来若让打包代码读
        `ndfbin_decks/data/*.json`，`build_exe.py` 必须补 `--add-data`
        （同一个"JSON 是数据不是模块"的坑，见 T8.1.8）
- [ ] **T10.7** 💡 **候选增强**（本次暴露的三个能力缺口，未做）
      —— ① **两营对照视图**：选一个基准营，逐窗口并排显示差异 ——
        `core/differ.py` 是**文件对文件**，不是营对营；现在只能人工逐营切表肉眼比
      —— ② 批量替换加「**原子对调**」模式（一来源 ↔ 一目标），否则置换表达不了
      —— ③ 保存时提示 `Config.ini` 兼容哈希 / AGF 模板需要同步

---

## 阶段 11 · 将军模式牌组属性编辑 —— ❌ **取消立项**（2026-10-16 用户决定）

> **决定：功能移交另一个通用编辑器项目 —— Warno Ndfbin Editor。**
> 理由：这本质上是**通用 NDF 属性编辑**（跨文件、改标量属性），
> 不是牌组编制编辑；放在本项目会把它逼成半个通用编辑器。
> 交接文件：`doc/移交-WarnoNdfbinEditor-AG牌组属性编辑.md`（本地，gitignore 已挡）。

- [x] **T11.1–T11.3** ✅ 前置数据勘查**已完成**，结论留在下面备查
      —— ★★ **四个属性一个都不在 `Deck.ndfbin` 里**（那文件只有编制，5 个类）。
        它们在 **`Gen/NDF/GFX/Pawn.ndfbin`**，以**模块**形式挂在每个营的
        `TEntityDescriptor`（导出名 `Descriptor_Unit_<牌组标识>`）上
      —— 落点：部队类型 = `TStrategicLabelModuleDescriptor.BackgroundTexture`；
        移动方式 = `TStrategicMovementModuleDescriptor`（**6 个共享描述符之一的引用，
        不是枚举**）；行动点 = `TActionPointsModuleDescriptor.InitialActionPoint` 等；
        炮兵支援 = `TStrategicBattleModuleDescriptor.BattleSupportRadiusInAPCase`
      —— ★ **营 ↔ pawn 一一对应 2265/2266 = 100.0%**；连接键建议用
        `TDeckModuleDescriptor.DeckIdentifier`（导出名带 `pion_` 前缀，别拼字符串）
      —— ★★ **唯一的安全边界：模块被编译器去重合并** —— 行动点 48 个对象承载 2265 个营
        （`InitialActionPoint=12` 那一个被 **1638 个营**引用）；移动方式 6 个 / 378；
        战斗角色 11 个 / 206。**原地改 = 一次改 1638 个营** → 必须
        **克隆新模块 + 重指向那一个营的 obj_ref**。
        而图标 / 分数 / 国家是「一营一对象」→ 可原地改
      —— ★ 二进制层本来就没问题：`selfcheck` 的 `ALL_BINS` **早就含 `GFX/Pawn`**，
        每次回归都在验；实测**逐字节相同**（18,285 对象，解码 0.49 s）
      —— 交叉验证：471 个营用 `howitzer` 移动 ↔ 471 个营有正支援半径，两边完全对上
- [x] **T11.4–T11.10** ❌ **取消** —— 实现工作（`io/pawn.py` / `edit/module.py` 的
      clone-on-write / 属性面板 / 校验器 / 双文件保存 / 隔离测试 / 待实测项）
      **全部随功能移交**，交接文件里已写成可执行的验收标准与清单。
- [x] **资产处理**
      —— ✅ `doc/移交-WarnoNdfbinEditor-AG牌组属性编辑.md`：含**契约 + 实现约束 +
        7 条验收标准 + 7 条待实测 + 全 30 个模块类字段表**，供对方直接用
      —— ✅ `tools/probe_pawn.py`：**留在本项目**（不被任何模块引用，删了也不影响回归），
        但交接文件已指明可一并移交；本项目若还要看 pawn 数据也随时能用
      —— ⚠️ 本项目**不实现**，也不再跟踪该功能的实现进度

---

## 阶段 12 · 界面修复：主题跟随系统 + 编辑后显示滞后（2026-10-18）

> 用户报两条：① 窗口配色要跟随系统深浅色；② 装备加减数量能生效，但
> 「组织 / 装备条目」的显示滞后且错乱。

- [x] **T12.1** ✅ **深浅色跟随系统**（`ndfbin_decks/app/theme.py`）
      —— ★★ **根因不是"没写主题"，是打包用的 Qt 版本根本做不到**：
        发布的 EXE 冻结在 **PySide6 6.3.2**，Windows 上选的是 `windowsvista` 样式，
        **它只认浅色**；`QStyleHints.colorScheme()` 要到 **Qt 6.5** 才有。
        实测同一台机器：Qt 6.12 的 `windows11` 默认就是 `#1e1e1e`（已跟随），
        6.3.2 的 `windowsvista` 恒为 `#efefef` —— 用 EXE 的人看到浅色，开发机看到深色
      —— 做法：**统一走 Fusion + 自绘调色板**（`windowsvista` 不逐角色遵守 `QPalette`，
        自绘深色在它上面是花的）。代价：不再是原生 Windows 外观；
        换来 dev 与 EXE 一致、深浅两套都定型
      —— 检测双路径：Qt `colorScheme()`（≥6.5）→ Windows 注册表
        `AppsUseLightTheme`（`winreg`，非 `reg.exe` —— 后者被安全策略拦）
      —— 实时切换：≥6.5 接 `colorSchemeChanged`；6.3.2 **无信号** → 2 s 轮询注册表
        （一次整数读取，比一次重绘便宜）
      —— ★ 顺带清掉两处**写死颜色**：表格里「继承」的灰 `#787878`、选中排的浅绿
        `(200,240,200)` —— 后者在深色下是大块亮绿。都改成 palette 相对
      —— 测试 `test_gui` 第 14 节 9 项：检测值 == 注册表、两套配色的窗口色与
        文字反差、运行时切换后表格仍在且有行
- [x] **T12.2** ✅ **组织/装备条目显示滞后错乱**
      —— ★★ **根因：`self._divisions` / `self._countries` 只在"切换 mod"时建一次**
        （`_on_mod_changed`）。它们不只是标签 —— 每个 `Division` 里装着一批
        **`Battalion` 快照**，而 `DeckFile.invalidate()` 每次编辑都会换掉这些对象。
        于是树用旧快照重建（标签、tooltip 全是改前的），表格却按 id 取到活对象 →
        **同一屏上两个视图来自两个时刻**
      —— 实测症状（修前）：排 tooltip `[0..1]x2` vs 活 `[0..3]x4`；
        连标签 `Howz_M101_105mm_RFA ×8` vs 活 `×8 · Iltis_RFA ×1 · M113_GreenArcher_RFA ×1`
        —— **新加进去的两种装备在树里根本没出现**，这正是"错乱"
      —— 修法：新增 `MainWindow._refresh_scope()`，`_reload()` 与 `_on_mod_changed()`
        共用；★ 另加一道防御 —— `EntryTable.fill()` **按 `deck_object_id` 重新取活的营**
        （`Session.battalion_by_id`），任何调用方递进旧快照都不会再造成
        "窗口来自旧快照 + 池子来自活对象"的错配
      —— 测试 `test_gui` 第 7b 节 5 项：tooltip == 活窗口、排/连标签 == 用活营重算的值、
        缓存列表的 Σ == 活 Σ。**修前 4 红，修后全绿**
- [x] **T12.3** ✅ **编辑后的 1 秒卡顿已修**（按营缓存 + 定向失效）
      —— 修前：`deck.battalions()` 每次编辑后**全量重建 2266 个营 ≈ 1008 ms**
        （单营 `_build` 6.3 ms；`invalidate()` 26 ms；编辑本身 25 ms）
      —— 修法：`DeckFile` 改成**按 `deck_object_id` 缓存 `Battalion`** +
        `invalidate(deck_ids=None)` 三档语义：
        `None` = 全失效（**默认，永远正确的兜底**）；
        `{id}` = 只失效这个营；`()` = 只重索引对象表、不动树（追加 pack 用）
      —— 失效点收敛到**唯一写入口** `Retiler.relay`（`set_count` / 换装备 / 增删条目 /
        批量替换全部经由它），它自己 `invalidate({deck_object_id})`
      —— 结果类 `RetileResult` / `SwapResult` / `EntryResult` 带上 `deck_object_id`，
        `Session.note_change` 走 `_touched_decks(res)`；`ScopedReplace` 用 `set(per_deck)`；
        **认不出营就退回全失效** —— 宁可慢，不可错
      —— ★ 实测：`battalions()` **1008 ms → 1.4 ms**；改一个营后
        **只有那一个营是新对象，其余 2207 个仍是同一批对象**（身份比对）
      —— 测试 `test_quantity` 第 6 节 5 项：只重建被改的营 / 其余同一对象 /
        该营 Σ==池 / **全量 `invalidate()` 仍会忘掉所有树**（兜底不许失效）
      —— ⚠️ 改的过程中犯过一次：把模块级 helper 插到了 `@dataclass` 和
        `class Division` 之间，`import` 照过、`Division()` 才炸
        —— 与「易错点」里"新增同名方法"同类：**位置错误的插入不会被 import 发现**
- [x] **T12.4** ✅ **发布 v0.5**（2026-10-18）
      —— 产物 `dist/Warno Ndfbin Decks Editor v0.5.exe`
        **37,701,708 B** ｜ md5 `35bd597d4c87eba57b0e25f36d7122d9`
      —— 内容 = 深浅色跟随系统 + 编辑后显示滞后修正 + 1 秒卡顿修正
      —— 流水线照旧：`build_exe.py 0.5` → `verify_exe.py 0.5` → `cp` 进 `dist/`；
        两侧 md5 一致；v0.4 归档到 `dist_0.4/`（同字节未删）
      —— ★ 包内新增 `ndfbin_decks/app/theme` 载荷断言（缺了会启动即崩）；
        另从 EXE 里挖出 `AppsUseLightTheme` / `_refresh_scope` / `_touched_decks`，
        **证明新代码真进了包**而不是只改了源码
      —— 热启动 **1.6 s**（测两遍，与 v0.4 相同 → 自绘调色板无可测开销）；
        新二进制冷启动 4.1 s（Defender）
      —— 双环境（PySide6 6.12 / 6.3.2）**15/15 全 PASS**
      —— ⚠️ 过程中自己引入过一个性能回归：`relay` 里的 `invalidate({id})` 最初
        也重建 6 万对象的索引（26 ms/次），把 `test_quantity` 的 7 万次循环从
        几分钟拖成几小时。**修法：把 `reindex()` 从 `invalidate()` 里拆出去** ——
        编辑不改对象表，就不该重建索引

---

## 阶段 13 · 「旅/团」级筛选（师与营之间）—— ❌ **取消立项**（2026-10-18 用户决定）

> 目标本是消除批量替换的颗粒度断层（例 `pion_RFA_TKNord_52Brig_Art525`，
> 师与营之间隔着 `52Brig`）。勘察已完成，**用户决定取消**，不要重复调研。
> 结论：可行但只覆盖 37.6%，且恰好漏掉一部分最大的师。

- [x] **T13.1** ✅ **勘察结论（留档备查）**
      —— 中间层从 `DeckIdentifier` 剥前缀 + 师标签得到（**必须 squash 规范化**：
        师标签 `RFA_TK_Nord` vs identifier `RFA_TKNord`），剩余段 0/1/2，
        **2 段时第 1 段即旅/团**
      —— 2266 营分为：**852 能切出（37.6%）** / 682 无中间层 / 567 师字段与名字不同名 /
        107 营即师本级 / 58 AGF 哈希名。852 → **298 组**，组大小众数 3 营
      —— 各国：TCH 71% RDA 68% SOV 59% POL 53% UK·CAN 41% ESP 20% **RFA 11.9%
        US 5.7% FR·NL·BEL·AGF·NATO 0%**
      —— ★ **断层最严重的大师里一半没有这一层**：≥10 营的 93 个师（1721 营）中 58 个有
        （845 营）、**35 个没有（876 营）**（`RFA_TK_Sud` 47 营、`RFA_12PzD` 24 营…）
      —— 三个坑：① 中间段混着旅/团/军区（`52Brig`/`VBK22`/`WBKII`/`PPCLI`/`10Art`），
        269 种取值只有 3 种带 `Brig`；② `DeckDivision` 自身层级不一致
        （`RFA_TKNord` 实为 **corps**；34 种/128 营的"师"其实是旅/团）；
        ③ `BattleOrder` 帮不上主忙（643 节点、deck 定位 98.1%，但中间 token 只对上
        **55/852**，且不含营级）
      —— 用户拍板过又取消的 4 个方向：师直辖桶 / 叫「旅/团」/ 下拉+树都要 / 加多选作用域
- [x] **T13.2** ❌ **实现全部取消** —— 一行代码都没写，无残留

---

## 阶段 14 · 批量替换「多对多」（2026-10-18 立项并完成）

> 用户拍板：① 同时映射、不传递；② 源与目标同行对同行，任一行不成立**整体拒绝**；
> ③ 形态用「表格 A」（每行一个目标 + 统一填充）。已实现。

- [x] **T14.1** ✅ **引擎：`ScopedReplace.apply_mapping()`**
      —— 入参 `{源内容 PackKey: 目标内容 PackKey}`
      —— ★★ **一次映射 → 每营一次 `relay`**，天然"同时生效"：
        实测 `{A:B, B:A}` 得到 `[B,A,B,A]`（严格对调）；
        而用旧做法顺序跑两次得到 `[A,A,A,A]`（**两类合并成一种**）
      —— ★★★ **必须按「内容」映射，不能按 pack 对象 id**：第一次按 id 写，
        A 只变成 B、B 纹丝未动 —— 同一内容在文件里可能有多个 pack 对象
      —— **整体拒绝**（全部在写之前判定）：某行没目标 / 目标=来源 / 来源不在范围内 /
        受影响营里有混合窗口（W3 预检，避免"改到一半才发现"）
      —— `apply(to_key)` 保留为「折叠成一个」的快捷入口（源=目标的那些行被**丢弃**
        并置 `target_also_a_source`），所以旧的「多对一」语义与测试不受影响
      —— 结果：新增 `ReplaceRow`（每对一行：源/目标 id、条数、件数、复用或新建），
        `ReplaceResult.rows`；`summary()` 在多行时改成"N 组 · 条 / 件 · 营数"
- [x] **T14.2** ✅ **对话框：每行一个目标**
      —— `_targets: {源内容: 目标内容}`（按**内容**记，换范围时配对能保留）
      —— 三个按钮：`本行改成…`（当前行）/ `统一设为…`（所有勾选行 = 旧多对一）/
        `清空目标`
      —— 行文本 = `来源 [载具] 经验N — 条 / 件 → 目标`；未选目标显示 `（未选目标）`
      —— 摘要实时校验并列明"第 X 行"；`result()` 改成
        `(scope, [(源 pack id 列表, 目标 key), …])`
      —— ★ 修了一个真 bug：`_refresh_row` 里 `setText` 也触发 `itemChanged`，
        走 `_on_check` 会把该行 id 从 `_checked` 里**按未勾选减掉** ——
        重绘必须用 `_loading` 静音
- [x] **T14.3** ✅ **测试与文档**
      —— `test_gui` 新增 **10b-2 节 11 项**：内容级 usage / 互换 / 窗口数不变 /
        Σ==池 / 每对一行统计 / 自指拒绝 / 幽灵源拒绝并指名行号 / **拒绝后文件一字未改**
      —— `test_gui` 10c 改写为新语义（环状配对 = 三行三个不同目标）
      —— 手册 4.4 整节重写：草图、三按钮对照表、「同时生效不成链、A↔B 是互换」、
        整体拒绝的三种提示
      —— `en.json` 279/279（100%），并**清掉 12 条孤儿**（旧文案）
- [x] **T14.4** ✅ **真正的表格（列对齐）**
      —— `from_list`（QListWidget）→ **`rows_table`（QTableWidget，5 列）**：
        勾选 / 来源 / 条·件 / 换成 / 改选按钮
      —— `QHeaderView.Stretch` 给「来源」和「换成」，计数与按钮按内容自适应
      —— 每行尾部一个 `改选…` 按钮（比"先选中行再点上方按钮"直接），
        `本行改成…` 保留为等价入口
      —— 交互全部迁到表格：`_set_all` / `_apply_filter`（`setRowHidden`）/
        `_visible_rows` / `_on_check`（只认第 0 列）
      —— ★ 上一轮那个 `setText` 触发 `itemChanged` 的坑在表格里同样存在，
        `_refresh_row` 依旧用 `_loading` 静音
      —— 测试：`from_list` → `rows_table`（`count()` → `rowCount()`、
        文字取第 1 列、隐藏用 `isRowHidden`）；10d 的筛选语义断言全部保留
      —— `en.json` **282/282（100%）**，清掉 5 条孤儿（含两条带前导空格的旧串）
- [x] **T14.5** ✅ **发布 v0.6**（2026-10-18）
      —— `dist/Warno Ndfbin Decks Editor v0.6.exe`
        **37,707,837 B** ｜ md5 `c03dbfd725f6dc76a921779c2fa08aa2`
      —— 内容 = 批量替换多对多 + 表格列对齐（本阶段全部）
      —— 流水线照旧；两侧 md5 一致；v0.5 归档到 `dist_0.5/`（同字节未删）
      —— 从 EXE 二进制里挖到 `rows_table` / `apply_mapping` / `改选…` / `整体未执行` /
        `QTableWidget`，确认新代码真在包里
      —— 热启动 **1.3 s**（测两遍；v0.5 是 1.6 s）；新二进制冷启动 4.5 s
      —— 双环境（PySide6 6.12 / 6.3.2）**15/15 全 PASS**

---

## 阶段 15 · 导出装备清单（2026-10-19 立项并完成）

> 用户反馈：使用者**不清楚 Mod 新单位的整体情况**（哪些新装备还没有 pack、
> 为什么装备选择器里选不到）。树和表一次只看一个营，翻不出这个答案。
> 产物：`ndfbin_decks/io/equip_lookup.py`（内核 + HTML + CLI）、动作栏按钮
> `导出装备清单`、`tests/test_equip_lookup.py`（50 项）。

- [x] **T15.1** ✅ **数据口径：装备 = 有 UI 模块的实体**（样本 `A World in Flames`）
      —— ★★ **不是「前缀是 Unit_/Building_」**：4622 个 `TEntityDescriptor` 里
        **936 个是 Mimetic 影子单位**（只有 `TMimeticTransform/Steering/FXManager` +
        `TLinkToOwner`），**没有 `TUnitUIModuleDescriptor`** —— 无名称、无角色、
        无价格、**0 个 pack 指向**，游戏里选不到
      —— 正确口径 **3686** = 有 pack **2247** + 仅载具 **317** + 无 pack **1122**
        （交叉表自洽，测试钉住）
      —— ★ **775 个新装备里 601 个没有任何 pack** —— 这就是「新单位选不到」的实质
- [x] **T15.2** ✅ **三处 `.ndf` → `.ndfbin` 落差，逐项有解**
      —— **装备名**：编译产物没有对象名，用 `"Descriptor_" + ClassNameForDebug`
        重建（100%）；`NameToken` 是 `loc_hash`，只能靠 mod 自带 `.dic`
        解出 **643/3686（17%）** → 词条名作附加列，作者写的调试名作主名
      —— **两个枚举是 int32**：`base.zip` 的
        `GameData/Gameplay/Constantes/Enumerations/{TypeStrategicDetailedCount,Coalition}.ndf`
        **明写整数**（`Infantry is 12` / `NATO is 0`）→ 优先读它，
        内置表只作回落，**测试断言两者 37 项逐项相等**
      —— ★ **编译器省略默认值**：`Coalition` 缺失 = 0 = NATO。样本里 2 个
        SOV 单位确实漏了这行 → 表里按字段显示成 NATO，**并在提醒里点名**
      —— ★★ **pack 没有名字**：`TDeckPackDescriptor` 只有 `UnitDescriptor` /
        `TransporterDescriptor` / `ExperienceLevel` / `Number`，无 export。
        原版那批按（装备+载具+XP）签名从 `StrategicPacks.ndf` 反查回原名
        **3538/5415**，其余给合成标签 + `object_id`
- [x] **T15.3** ✅ **缺文件分两种处理**
      —— **缺 `GFX/Unit` → 拒绝导出**（这个 mod 没改装备；一张全来自原版的表
        会被误读成「我的 mod」）—— 柏林 mod 实测走这条路
      —— **缺 `GFX/Deck` → 退到 `base.zip`**（pack 只存在于 Deck 里，没有它
        mod 不可能有自己的 pack，用原版是**语义正确**）。解析
        `StrategicPacks.ndf`（2685 个 / 0.01 s）与 `StrategicDecks.ndf`
        （12.5 MB / 2208 个 AG 牌组 / 0.22 s），页面顶部写明来源
- [x] **T15.4** ✅ **入口**
      —— GUI：动作栏 `导出装备清单`（排在「保存」之前 —— 它不改文件），
        导的是**当前选中的 mod**，不需要再选一次
      —— CLI：`python -m ndfbin_decks.io.equip_lookup --mod <名称|工坊id> --out x.html`
      —— 导出后弹窗交底：读了几份文件、多少条悬空引用、多少对象未计入
- [x] **T15.5** ✅ **测试与文档**
      —— `tests/test_equip_lookup.py` **50 项**：口径 / 交叉表自洽 / JOIN /
        枚举表与 base.zip 逐项一致 / 缺 Unit 报错 / 缺 Deck 兜底 / HTML 可解析且
        无外链 / **只读（两个 ndfbin 的 size+mtime 未变）** / CLI
      —— 页面用 QtWebEngine 实拍逐节看过；`node` 里跑页面脚本数出行数
      —— 手册新增 **4.5 导出装备清单**（第 4 节从「四个操作」改成「五个」）
      —— `en.json` **315/315（100%）**，0 待译 0 孤儿
- [x] **T15.6** ⚠️ **迁移经过（记一笔，免得将来有人去错仓库找代码）**
      —— 这个功能最初被实现进了 **Warno Ndfbin Editor**（因为它那份沟通稿里
        写的是 `ndfbin_decks/ndfedit/equip_lookup.py`），用户随后更正：
        **要的是本项目**。那边已 `git reset --hard` 回滚，代码迁到这里
      —— 迁移时的改动只有三处：包路径（`ndfedit/` → `io/`）、导入层级、
        提示语改走 `tr()`（本项目界面是双语的；**页面正文仍是中文**，
        与 `doc/使用教程.md` 同类，不跟界面语言切）
- [ ] **T15.7** 💡 未做：页面正文的英文版。如果哪天有英文用户，把 HTML 模板里的
      标题/表头也接进 `tr()` 即可 —— 目前判断不值得（使用者全是中文）
- [x] **T15.8** ✅ **发布 v0.7**（2026-10-19）
      —— `dist/Warno Ndfbin Decks Editor v0.7.exe`
        **37,775,868 B** ｜ md5 `731cc44c29497c377efbdda6ab310687`
      —— 内容 = 阶段 15 全部（`io/equip_lookup.py` + 动作栏入口 + 50 项测试）
      —— 流水线照旧：`build_exe.py 0.7` → `verify_exe.py 0.7` → `cp` 进 `dist/`；
        两侧 md5 一致；`dist/Decks编辑器使用教程.md` 一并刷新（48,543 B）
      —— 包内 **168 载荷 / 144 冻结模块**（v0.6 是 141，多出的是新模块）；
        `build_exe.check_bundled` 里新加的 `ndfbin_decks/io/equip_lookup` **命中 1**
      —— ★ 另用解包挖串独立复核：EXE 里能挖到 `equip_lookup`（2 个模块）、
        `导出装备清单`、`TUnitUIModuleDescriptor`、`Mimetic`、`StrategicPacks.ndf`
        —— **证明真代码进了包**，不是只有清单里那一行
      —— 热启动 **1.1 s**（三次 1.1 / 1.3 / 1.1；v0.6 量到 1.3 s，差异在噪声带，
        载荷只大 68 KB）；新二进制冷启动 3.6 s（Defender）
      —— 双环境（PySide6 6.12 / 6.3.2）**16/16 全 PASS**
      —— ⚠️ 发版前把 `.venv/Scripts/python.exe` 误写成 `C:/Users/123/.venv/...`
        一次（exit 127）—— 脚本没问题，是命令行手误；重跑即过
- [x] **T15.9** ✅ **修正：装备判据选错，丢掉整批单位**（2026-10-19，用户报）
      —— 现象：`Honor Or Death`（工坊 3395350736）导出的装备不全，缺了大量 mod
        新增装备；而编辑器改编制时**部队下拉框认得出**它们
      —— ★★ **根因：我拿 `ClassNameForDebug` 的前缀当判据**（`Unit_`/`Building_`），
        而那是**作者自己起的显示名**。该 mod 3701 个可选单位里 **751 个**的调试名是
        `2S22_BOGDANA_UKR`、`AAteam_BARKAN_ISR` 这类**不带前缀**的，整批被筛掉
      —— 正确判据：**该实体被导出成 `$/GFX/Unit/Descriptor_Unit_*`**。
        它同时是 **pack 引用单位时用的字符串**，所以「清单里有」与「下拉框认得出」
        天然是同一批 —— 直接复用 `unit_universe.UNIT_PATH_RE`，不另写一份
      —— 交叉验证（两个 mod 上完全一致）：
        `Honor Or Death` 导出 3701 / 有 UI 3701 / 交集 3701；
        `A World in Flames` 3686 / 3686 / 3686
      —— 修正前后：`Honor Or Death` 装备 **2950 → 3701**、
        **悬空引用 342 → 0**；`A World in Flames` 3686 不变，但
        **悬空 1 → 0**、有 pack **2247 → 2248**
      —— ★ 那条「悬空 1」其实是**我判断错误**：该单位导出成
        `Descriptor_Unit_WF_VDV_HMG_RUS`、调试名却写成 `Unit_VWF_VDV_HMG_RUS`，
        v0.7 的报告里把它算成「mod 笔误」，实际是**拿显示名当身份**造成的假引用
      —— `skipped` 的语义随之改成「没有 unit 导出」（AWF 940 = 936 Mimetic +
        4 个 `*_District`），文案与 `en.json` 同步（315/315）
      —— 测试 **58 项**，新增 §2b：该 mod 的 3701 数、零悬空、交叉表、
        无前缀单位在表里、以及**「清单集合 == 下拉框集合」的集合相等断言**
- [x] **T15.10** ✅ **按 v0.7 重打包**（2026-10-19，用户指定「依然按照 0.7 打包」）
      —— `dist/Warno Ndfbin Decks Editor v0.7.exe` 被**就地覆盖**为新构建
        **37,775,935 B** ｜ md5 `8f65c8bc91b4772b0be9b2d385097cb4`
        （覆盖前那份是 **37,775,868 B** ｜ `731cc44c29497c377efbdda6ab310687`）
      —— 包内 **168 载荷 / 144 冻结模块**，`check_bundled` 各项全命中
      —— ★ 解包挖串独立复核：`UNIT_PATH_RE`（2 模块）/ `没有 $/GFX/Unit 导出`（1）/
        `unit_universe`（3）都在；**旧的 `EQUIP_PREFIXES` 出现 0 次** ——
        不是「改了源码」，是真判据换掉了
      —— `verify_exe.py 0.7` 全过（版本 / 模块图 / 0 错误 / 原生标题 / 图标 4 档）
      —— 热启动 **1.3 s**（三次全 1.3）；新二进制冷启动 4.3 s（Defender）
      —— ⚠️ **教训：`dist_<ver>/` 不是存档处**。构建会先清空该目录，我放进去的
        旧版留证副本 `v0.7 (T15.9 之前).exe` **被一并删掉了**；旧二进制的 md5
        还留在上面那一行，但**字节已经没了**。要留证必须放到 `_pre_fix_backup/`
        这类**与构建目录无关**的地方
      —— 本次改动只有判据与文案，回归仍以上一轮的 **16/16 全 PASS** 为准
        （`test_equip_lookup` 59 项）
- [x] **T15.11** ✅ **导出按钮移到语言选择下方**（2026-10-19 用户要求）
      —— 理念：**编辑环（改件数/换装备/插删条目/批量替换/保存）作用于「你刚选中的那一行」；
        整 mod 只读的操作不属于这个环**。混在一起会让这个环看起来比实际更长，
        而且每加一个一次性工具都要把环上的按钮往左挤
      —— 做法：`_build_filter_bar` 从单行改成 `QVBoxLayout(两行)`：
        第一行（Mod / 打开文件夹 / 国家 / 师 / 营搜索 / 语言），
        第二行右对齐、只放低频工具 —— 右缘与语言框对齐（实测差 **0 px**），
        将来新增工具**从右往左**长
      —— 交互不变：`_label_actions` 仍是一个字典 + 一次 `_rt`，两行共用一个
        `_action_buttons`（编辑环在前、工具在后，与屏幕顺序一致），
        所以切语言时两行一起翻（实测 en/zh_CN 往返正确）
      —— 回归：双环境 **16/16 全 PASS**
      —— ⚠️ **手册 4.5 里仍写着「动作栏里有一个 导出装备清单」** ——
        用户本轮明确「不用修改教程」，所以**没动**；下次动手册时一并改
      —— 打包：仍按 0.7 就地覆盖，见下
- [x] **T15.12** ✅ **第三次按 0.7 重打包**（2026-10-19）
      —— `dist/Warno Ndfbin Decks Editor v0.7.exe`
        **37,776,096 B** ｜ md5 `212c33091d7cf388d9d354502eb63cdd`
      —— 覆盖前那份（**37,775,935 B** ｜ `8f65c8bc…`）这次**先归档到了安全处**：
        `_pre_fix_backup/v0.7_before_toolbar_move.exe` —— 那是与构建目录无关的目录，
        不会再被 `build_exe.py` 清掉（T15.10 的教训）
      —— `verify_exe.py 0.7` 全过；包内 **168 载荷 / 144 冻结模块**
      —— ★ 挖串复核：`tool_row` / `export_btn` / `_tool_buttons` 各在 **1 个模块**里 ——
        新布局代码真进了包
      —— 热启动 **1.3 s**（三次全 1.3，与上一版相同 → 多一行布局无可测开销）

---

## 易错点（都是本项目实际踩过的）

| 坑                                        | 后果                                                                                      | 对应任务                                    |
| ---------------------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------- |
| 指纹只比 `DeckPackList` 的 obj_ref 索引         | **漏报 85%**（`T55A`→`T72` 同数量换装查不出）                                                       | T1.8                                    |
| diff 不排除纯引用字段                            | 索引偏移 → **2213 个假差异**                                                                    | T1.8                                    |
| `IsHQ` 写成 `False`                        | 留「存在但为 False」属性，游戏仍按 HQ 处理                                                              | T4.7 / T2.2                             |
| 改数量不重排 PackIndex                         | **静默截断**下游连排，游戏不报错                                                                      | **T4.2** ✅已按 W1–W4 重算                   |
| ★ **改 `items` 忘了同步 `length`**            | 编码器抛 `NDF collection length mismatch`，看起来像 codec 坏了                                     | **T4.2** ✅已修正                           |
| ★ **战斗群字段名写成 `DeckSmartGroupList`**      | 取不到值 → 重算"零漂移"实为**全部调用被拒**的假通过                                                          | **T4.2** ✅实为 `SmartGroupList`           |
| ★ **两个编辑器各持一份对象浅拷贝**                     | 后保存的**静默覆盖**先保存的改动（换装被改数量覆盖）                                                            | **T4.2** ✅改为就地修改                        |
| ★ **给类新增与已有同名的方法**                       | Python 取**后定义**的那个 → 静默覆盖原有实现（实测：`invalidate` 被覆盖后`_by_id`/`_packs` 不再初始化，整个模型返回 0 战斗群） | 改文件后立刻 `grep -n "def 同名"` 确认唯一；或跑一遍模型验收 |
| 用「窗口第 i 个 entry」取该窗口的 pack               | `count=N` 展开成 N 个 entry，按下标取会拿到别的窗口的装备                                                  | **T4.2** ✅按槽位区间取                        |
| 新建师不追加 `DivisionIds`                     | 卡组无法存档                                                                                  | T3.7                                    |
| 期望 100% 连排都有名字                           | 本体词典已加密放弃，覆盖率天然只有 0.06%~9.7%                                                            | T1.5 ✅已实现降级                             |
| 用 `AGF_` 前缀做溯源                           | Test mod 漏报 **100%**                                                                    | T1.7                                    |
| 「有战斗群 ⇒ AG 牌组」                           | 17 个 PvP 牌组也有战斗群，会误收                                                                    | T1.9                                    |
| zstd level 不同就判「写坏了」                     | 白查一轮                                                                                    | T1.3 ✅自检按 body 判定                       |
| 以为 `.dic` 键要反查 token                     | 绕大弯路（键 == loc_hash）                                                                     | T1.5 ✅已验证                               |
| **把 `.dic` 末条哨兵当正常条目**                   | 出现乱码名（`'вдоз й-елнаипрУ12ы3П.мётТуРОВМгяжк4'`）                                          | T1.4 ✅已过滤                               |
| `Saved Games` 路径挂在安装目录下                  | `ModNotFound`                                                                           | T1.1 ✅已修正                               |
| **以为 AG 牌组的 `Number` 也很多样**              | 实测 **恒为 1**（557,561 槽位零例外）；21 种取值全在 PvP 侧                                               | T4.1 ✅已普查                               |
| ★ **把 `trans_ref` 的 index 当成 `TRAN` 下标** | 写入后 `Unresolved CNDF import index`。该 index 实为 **`IMPR` 路径树的节点 id**（节点 0 = `$` 根）        | T4.1 ✅已修正                               |
| ★ **先追加对象再重建路径树**                        | 顺序反了。`append_graph_objects` 会即时校验 ⇒ 必失败。必须**先长树→回填 id→再追加**                             | T4.1 ✅已修正                               |
| ★ **把 `Battalion` 缓存跨过一次编辑**            | 它是**快照**：`invalidate()` 之后活对象换了一批，缓存还指着旧的 → 两个视图来自两个时刻（树旧、表新），看着像"错乱" | **T12.2** ✅按 id 重取 / 编辑后重建作用域缓存 |

---

## 推进日志

| 日期         | 完成                             | 备注                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-10-12 | T0.1–T0.9                      | 四份勘查报告完成。发现并纠正 5 处自身错误                                                                                                                                                                                                                                                                                                                                                                  |
| 2026-10-12 | T0.10 取消                       | 本体词典加密在 `.dat`，成本/收益不对等，放弃；改走降级显示                                                                                                                                                                                                                                                                                                                                                       |
| 2026-10-12 | T4.x 重排                        | ★ 用户纠正风险排序：换装备 → 改数量 → 插删 Pack                                                                                                                                                                                                                                                                                                                                                          |
| 2026-10-12 | 全局约束                           | 旧 EXE 反复启动未响应 ⇒ 旧代码**保留但谨慎采用**，GUI 从零重写                                                                                                                                                                                                                                                                                                                                                 |
| 2026-10-12 | **T1.1–T1.9**                  | **★ 阶段 1 全部完成**。产出 2600+ 行，五个验收命令全 PASS                                                                                                                                                                                                                                                                                                                                                 |
|            |                                | 性能基线：Deck 61127 对象解码 1.35 s / 编码 0.40 s                                                                                                                                                                                                                                                                                                                                                 |
|            |                                | 覆盖率实测：Test 0.062% / Berlin 9.693%（本体词典放弃后的必然值）                                                                                                                                                                                                                                                                                                                                          |
|            |                                | ★ 阶段 1 中发现并修掉的坑：`.dic` 哨兵乱码、`Saved Games` 路径归属、<br />`fingerprint` 丢顺序导致 diff 返回 0                                                                                                                                                                                                                                                                                                      |
|            |                                | ★ `differ` 复现并修正了勘查阶段的漏报：39/39（含 33 个同数量换装）                                                                                                                                                                                                                                                                                                                                             |
| 2026-10-12 | **T4.1**                       | ★ **换装备完成**，严格按工程文件逻辑（reuse / create 双路径）<br />普查确认：AG 牌组 `Number` **恒为 1**（557,561 槽位零例外），<br />999/100/50 等 21 种取值**全在 128 个 PvP 牌组**里（999 全部带 `_challenge` 标记）<br />★ 实测证实：pack 对象内嵌 ndfbin 且**无导出名**，`DeckPackList` 全是纯 `obj_ref`<br />⇒ 编辑器按**内容签名**索引 pack，扮演 NDF 里包名的角色<br />★ 踩坑：trans_ref 的 index 是 **IMPR 树节点 id**，不是 TRAN 下标；<br />且必须**先长树→回填 id→再追加对象**，否则 append 的即时校验必失败 |
| 2026-10-12 | **T2.1–T2.6 + T3.1–T3.6/T3.8** | **阶段 2 完成 + 阶段 3 大半**（用户选 A 方案：贴近旧代码）<br />产出 `core/deckmodel.py` + `core/validator.py`，六个验收全 PASS                                                                                                                                                                                                                                                                                      |

| | | ★ 修掉一个真 bug：孤儿连排检查在 **window 循环内**计数，  
导致每个连排被数 3~4 次 → 42258 个假错误。  
教训：**校验器的度量点要和语义对齐** |

| | | ★ 阈值全部经四数据集标定：三个数据集**硬错误均为 0**。  
若「硬规则」在原版数据上报错，是规则错了不是数据错了 |

| | | 模型规模：Test 2208 AG/42258 连排、Berlin 2266/43118、N.Thunder 2337/44450；  
连排无 `Name` 数 = 16（与原版一致） |

| | | 软警告实测：hq_count 362/617/549，too_many_platoons 625/625/646 |

| 2026-10-13 | ★ **筛选链固化**（师下拉跳回第一个师） | ★ 根因：`_last_data` 只有 `set_options` / `_pick_text` 两条路径写入，**鼠标点下拉行**走的是 Qt 自己的 `currentIndexChanged`，`_last_data` 还停在默认值 27GMRD ⇒ 模态框抢焦点 → `focusOut → _restore()` 悄悄把索引设回 27GMRD（信号被 block，当场看不出来）→ 替换后 `_fill_tree` 读到 27GMRD。<br />"有时"= 打字+回车走 `_pick_text`（正确）不跳，鼠标点选才跳。<br />修三处：`_sync_edit` 记录已提交行 / `_restore` 无搜索时直接返回 / `set_options` 静默且原子（blockSignals）<br />新增 test_gui 3d「筛选链固化」；双环境 14/14 PASS；v0.1 原地重建（md5 `6eca8cea…`），提交 `a5ac887` |

| 2026-10-13 | **阶段 8 立项** | 用户提两项新需求：① 界面本地化（EN/FR/DE/RU）；② 批量替换一换一 → 多换一。<br />★ 两项都**先量规模再定方案**：本地化 392 处字面量 / 去重 299 条 / 2833 字；<br />多换一用 Test 文件实测 3 源 1 目标 = 211 条装备，0 error、W1 19/19 成立、非来源 863 条零改动。<br />⇒ 多换一的**数据层只改一个谓词**，本地化的**瓶颈是 299 处改造不是 1196 条译文** |
