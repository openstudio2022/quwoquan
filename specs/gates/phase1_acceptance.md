# Phase 1 验收凭证 — 稻城亚丁标杆 + 川西/四川景区 fan-out

- 阶段：内容飞轮工程 Phase 1（纯 `quwoquan_data`，真实素材→主页→文章→publish 到当前环境集合）
- 状态：PASSED
- 日期：2026-06-01
- 任务：`旅行/地域/四川省/景区/景区全覆盖`
- 批次：`phase1_daocheng`（标杆）、`phase1_fanout`（fan-out）

## 交付总览

| 维度 | 目标 | 实际 |
|---|---|---|
| 真实文章 N | ≈13 篇过门 | **11 篇**（稻城 3 + fan-out 8）全部 `approved` + `materialize` + `ship` |
| 实体主页 | ≥800 字 + conditionProfile | **6/6**（900–1136 字，均含 `regions`/`seasons`） |
| 发布环境 | 当前环境集合 + prod 全量 | `publish_meta.shipSummary` 当前环境集合齐全：prod 全量 / alpha·beta·gamma 各 10% |
| 抽检 | 3 篇真实可发布 | 稻城攻略 / 海螺沟攻略 / 九寨沟体验：动机开篇+亮点+不足+事实就地融入+figure 完整 |

### 6 实体 × 11 篇明细

| 实体 | 主页字数 | conditionProfile | 文章 |
|---|---|---|---|
| 稻城亚丁（标杆） | 1136 | regions/seasons | 攻略 + 体验 + 影像志（3） |
| 四姑娘山 | 916 | regions/seasons | 攻略 + 体验（2） |
| 海螺沟 | 941 | regions/seasons | 攻略 + 体验（2） |
| 九寨沟 | 900 | regions/seasons | 攻略 + 体验（2） |
| 都江堰 | 903 | regions/seasons | 攻略（1） |
| 乐山大佛 | 931 | regions/seasons | 攻略（1） |

全部 11 篇通过：模板指纹 / 事实可回溯 / 出处三道门 + `evidenceQuality` / `factTraceability` / `numericTraceability` / `travelogueDensity` / `entityCoverage` / `carrierConsistency` / `imageGate`。

## 关键技术债清偿（本阶段修复）

### 1. composer 主实体 entityRef 短格式 → 发布门误过滤（GATE_BLOCK 级，已修）
- **现象**：`promote` dry-run 中所有 post 的 `entityRefs` 被 `filtered (no homepage)`，主实体失去关联。
- **根因**：`route_workflow` / `entity_workflow` 把主实体拼成 `/entity/{name}` 短格式，而 `publish_filter._parse_entity_ref` 需 `domain/type/name` 三段，短格式解析失败 → 误判无主页。
- **修复（单一真相源）**：在 `_common/entity_extract.py` 新增共享 `normalize_entity_refs`，用 compose input 已有的 `subject.type`（如 `地点/景区`）补全为 `/entity/{domain}/{type}/{name}`；两个 workflow 共用、删除重复逻辑（R25 横切提取）。
- **回归测试**：`tests/test_entity_composer.py::test_normalize_entity_refs_full_path` + e2e materialize 断言 manifest `entityRefs` 为可解析全路径（R13）。

### 2. 图片下载限流阻断（已修）
- `download/fetch.py`：`_USER_AGENT` 补合规联系方式；`_http_get_bytes` 对 `HTTP 429/503` 加指数退避重试 + `Retry-After` 解析，解 Wikimedia Commons 限流导致的 `images=0`。

### 3. needs_review 图不硬拦 produce（边界确认，符合设计）
- 景观图误判人脸 / 缺 CV 后端 → `needs_review`，`produce review` 记账不硬拦，延到 `publish` 人工门裁决；`unsafe`/重复图仍硬拦。

## gate-out 校验

| 校验 | 命令 | 结果 |
|---|---|---|
| 11 篇过门 + 物化 | `produce --stage review --materialize`（两批） | approved=11 failed=0 |
| 主页合规 | 6 实体 page.md ≥800 字 + `_entity.json.conditionProfile` | 6/6 PASS |
| 发布门保留实体 | `promote_to_publish --dry-run` | filtered entityRefs = 0 |
| ship 当前环境集合 | `cli ship --task … --batch …`（两批） | prod/gamma/beta/alpha bundle 全写，`publish_meta.lastShip` 更新 |
| entityRef 全路径回归 | `tests/test_entity_composer.py` | 4 PASS（含 `test_normalize_entity_refs_full_path`） |
| 全量门禁 | `make verify-quwoquan-data` | PASSED |

## 反思账本

已通过 `cli task record-run` 沉淀至 `tasks/旅行/地域/四川省/景区/景区全覆盖/notes.md`（run `run_20260601_215839`）：
- 归因：composer entityRef 契约不一致（执行/契约问题，非证据不足）。
- 决策：subject.type 驱动全路径补全 + 共享函数 + 回归测试；限流退避；needs_review 人工门兜底。

## Phase 1 结论与后续

- [x] 标杆复刻：稻城亚丁 3 篇真实成稿，作为 fan-out 范式。
- [x] fan-out：川西/四川 5 景区真实素材 → 主页 → 文章 → publish 到当前环境集合。
- [x] 真相源收敛：实体引用补全逻辑单一化 + 回归测试防回退。
- [ ] 后续（next）：都江堰/乐山补体验篇凑 N≈13；川西其余景区继续 fan-out；接服务侧 `content-service/cmd/import` 灌 alpha 冒烟，打通端云桥。
