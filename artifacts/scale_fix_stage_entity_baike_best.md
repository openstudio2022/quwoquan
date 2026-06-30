# 阶段证据：实体=百科择优单源（契约测试 + 门禁接线）

任务节点：`fix-entity-baike-best`
绑定特性树：AppRoot 内容工厂 → L1 数据工程(quwoquan_data) → L2 实体主页生产 →
L3 百科择优单源
验收意图：contract（local_contract）
测试证据层：`local_contract`

## 审视结论：择优单源逻辑已实现，本步补齐契约证据

逐点核对 `build/homepage.py::_entity_base_draft` 与 `build/homepage_text.py`：

- **百科分级择优**：`_HOMEPAGE_PRIMARY_KIND_BONUS` 已按质量分级——维基百科(120) > 百度百科(110)
  > 搜狗百科(105) > 字节百科(100) > 通用百科(95) > 景区官网(90) > 官网/官方(85)。
- **单一最佳源**：`_entity_base_draft` 过滤 `priority>0`（百科/官方）→ `_factReady`（可用事实≥4）
  → 按 `(factReady, priority, factCount, score, length)` 降序，取 `best = candidates[0]`，
  主页三件套（`text` / `sectionOutline` / `primaryEvidenceRef`）全部来自这**一个**来源单元。
- **无跨源污染**：`_homepage_base_source_issues` 硬门要求 compose base == quality base（防漂移）、
  base 必须是 encyclopedia/wiki/official（`is_primary`）、禁止 author 游记/攻略/点评
  （`_HOMEPAGE_GUIDE_PENALTY` 命中即 `-1000` 排除）。

即「多百科按质量择优取最佳单一源做主页三件套、无跨源污染」**功能已具备**。本步只补**契约证据**
并接入门禁（此前 `test_release_integrity_gate.py` 未在 `verify_quwoquan_data.sh`）。

## 改动（仅 `quwoquan_data/**`）

`quwoquan_data/tests/verify/test_release_integrity_gate.py`：

- 新增 `test_homepage_base_draft_picks_best_single_baike_no_cross_source`：
  - 维基 + 百度 + 搜狗三百科同存 ⇒ `_entity_base_draft` 取**维基**（最高优先级单一源），
    `primaryEvidenceRef == sourceRef`（三件套同源），且不落到百度/搜狗。
  - 去掉维基后退取**百度**（仍单一最佳源，绝不跨源拼接）。

`quwoquan_data/scripts/verify/verify_quwoquan_data.sh`：

- 在 `test_build_homepage.py` 后接入 `test_release_integrity_gate.py`（pytest），覆盖
  百科择优单源 + 三件套同源 + 禁游记回退 + 发布完整性门。

## 验证结果（系统 venv python）

- 新增用例：1 passed（0.20s）。
- `test_release_integrity_gate.py` 全文件：13 passed（0.22s，原 12 + 新 1）。
- 既有 `test_homepage_base_draft_never_falls_back_to_guide_source`（wiki 优先于 guide、仅 guide 返回 {}）：仍绿。

## 剩余 / 后续增强（非阻断）

- 当前择优排序以「来源类型优先级 + factCount + score + length」为主；用户列出的「图文/时效」
  （是否含图、更新时间）尚未作为显式 tiebreak。核心「择优最佳单一百科、无跨源」已满足；
  图文/时效 tiebreak 作为后续质量增强，按需登记 backlog。
