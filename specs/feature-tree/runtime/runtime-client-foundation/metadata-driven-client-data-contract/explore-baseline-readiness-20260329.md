# Explore：元数据驱动客户端数据契约 — baseline 就绪度与全页缺口（2026-03-29）

> **L1 / L2 / L3**：`runtime` → `runtime-client-foundation` → `metadata-driven-client-data-contract`  
> **对照源**：`spec.md` / `design.md` / `acceptance.yaml` / `plan.yaml`、`specs/gates/metadata_driven_ui_gap_inventory.yaml`、`page-horizontal-quality-matrix.md`（P2 列）、`quwoquan_app/scripts/runtime/verify_metadata_driven_ui_gate.py`、`CR-20260329-004-metadata-driven-client-data-contract.yaml`

---

## 1. 目标、范围、交付物、验收 — 核对结论

| 项 | 结论 |
|----|------|
| **目标** | **已写清**：唯一真相源 metadata → codegen；Mock/Remote 同源类型；UI 目标态禁止长期裸 Map（过渡期靠缺口清单）。与横向维度 **P2** 语义一致。 |
| **范围 In** | 契约层、Repository 边界、页面消费目标态、缺口清单、门禁脚本、**不**承诺本会话全量改码 — **与 plan slice-1 一致**。 |
| **范围 Out** | 一次性替换全仓库 Map、重定义 Go Registry、PA 内部 LLM 契约 — **已声明**；云 API 调用仍须 codegen。 |
| **交付物** | spec/design/acceptance/plan、inventory YAML、verify 脚本、`gate_repo.sh` 引用、tree_index、CR — **均已存在**（CR 状态见 §5）。 |
| **验收 A1–A7** | 文档与清单、CR 路径、tree、design 中 Mock/Remote 原则 — **可满足**；**T3/T4** 在 acceptance 中标记为 partial/deferred，**符合**「baseline 不关门实现」策略。 |

---

## 2. 是否可以进入 `/baseline`？

**可以进入「规格 + 清单 + 门禁」类 baseline**（冻结流程与可追溯缺口），理由：

1. **spec-first / metadata-first** 口径已在 `spec.md` 写死，且与仓库 `.cursor` 规则一致。  
2. **全扫描基线路径**已在 `metadata_driven_ui_gap_inventory.yaml` 与 `page-horizontal-quality-matrix.md` 对齐声明（含 `app/shell`、`welcome`、`components` 全屏页）。  
3. **门禁** `verify_metadata_driven_ui_gate.py` 已接入 `gate_repo.sh`；默认模式不阻断 `partial`，`QWQ_METADATA_UI_GATE_STRICT=1` 才卡 `current_map`。  
4. **plan** 已把「全页登记」落在 slice-4，**实现状态与 inventory 现状一致**（登记完成 ≠ DTO 化完成）。

**不可混为一谈**：baseline **不**等于「全应用 P2 全部 ✓」或「全页 UI 已 codegen DTO」。后者属于 **slice-2～4 及后续 /dev**，须在清单中从 `partial` → `compliant` 逐域收敛。

---

## 3. 全页面覆盖 — 漏项核对

**矩阵数据行**（含 T0、`app/shell`）：与 `metadata_driven_ui_gap_inventory.yaml` 中 `ui_pages.path` **一一对应**，未发现矩阵有路径未登记。  
**额外清单项**（合理）：`content` 域下列 `media_post_card.dart` — **非 `*_page.dart`**，属 Feed 关键组件，应在清单保留；矩阵可在备注或后续「关键组件附表」交叉引用（当前矩阵正文未占行，**非漏页**）。

**挂靠面**（矩阵已有文字约定）：`PublishLocationSearchPage`、`_CreateEntryRoutePage` — 清单挂在父 `*_page.dart` 行备注即可，**baseline 可接受**；若后续审计争议，可在 inventory 增加 `sub_surfaces: []` 结构化字段（**可选改进**）。

**排除项**：`chat_display_fallbacks.dart` 仅 export — 矩阵已排除，**一致**。

---

## 4. 主要 Gap（重新分析）

### G1：横向矩阵 **P2=✓** 与清单 **status: partial** 大面积不一致（**已处理**）

- **现象（记录）**：矩阵曾将多数业务页标 **P2=✓**，与清单 **`partial`** 矛盾。  
- **已落地**：`page-horizontal-quality-spec.md` **P2** 已写明以清单 `status` 映射符号；**矩阵 P2 列已按清单批量回写**（`partial`→`○`，`compliant`→`✓`，`exempt`→`—`；T0 `circles_hub` 维持全列 `—`）。  
- **备选（未采用）**：另增 **P9「UI 契约消费」** 列 — 仅在若需同时展示「API 已 metadata」与「UI 已 DTO」两维时启用。  

### G2：**P2 验收口径**在两条线（横向 spec vs L3 spec）未写「以清单为准」

- **修改方案**：在 `metadata-driven-client-data-contract/spec.md` 的「验收重点摘要」或「覆盖矩阵」增加一行：**P2 是否达标以 `metadata_driven_ui_gap_inventory.yaml` 的 `status` 为权威，横向矩阵须与之同步或可推导**。

### G3：门禁 **仅校验路径存在性**（及 STRICT 下 current_map）

- **Gap**：无法发现「矩阵有路径但清单漏登记」或「P2 符号与 status 矛盾」。  
- **修改方案**：新增可选脚本 `verify_matrix_inventory_p2_alignment.py`（或扩展现有脚本）：读取矩阵表格中带 `lib/` 的行，解析 P2 列，与 inventory 聚合表比对；**默认 warn**，`STRICT` 失败。

### G4：`target_dto: TBD` 过多

- **Gap**：entity/search/rtc/assistant/circle 等多页 **无明确目标 DTO**，不利于排期。  
- **修改方案**：按域在独立 /dev 中 **先补 metadata/codegen 再填 target_dto**；或在清单中拆 `target_dto` / `blocking_metadata_issue` 两字段。

### G5：CR 归档（**已完成**）

- **已落地**：元数据驱动 CR 重编号为 **`CR-20260329-004-metadata-driven-client-data-contract`**，`status: baseline_complete`，与同日期 **`CR-20260329-003` settings-canonical** 解耦。

### G6：个人助理与云 API 边界（已 spec 声明，执行层仍易漏）

- **提醒**：PA 内部契约可走 `lib/personal_assistant/contracts/`；**一旦调云** 仍须 Repository + codegen — 建议在 assistant 域清单 `note` 中引用 `spec.md` 该条，便于 CR 评审。

---

## 5. 建议的后续动作

| 优先级 | 动作 | 状态 |
|--------|------|------|
| P0 | 统一 **P2 符号** 与 **inventory.status** | **已完成**（spec + 矩阵列） |
| P1 | `spec.md` 覆盖矩阵 + Explore 文档交叉引用 | **已完成** |
| P2 | **矩阵↔清单** 轻量校验脚本（防再次漂移） | **待办**（可选接入 gate） |
| P3 | 逐域消灭 `TBD` target_dto（随 metadata 扩展） | 待办 |
| P4 | CR-004 归档 `baseline_complete` + `make gate` | CR **已完成**；gate 建议在合入前本地跑 |

---

## 6. 结论摘要

- **元数据驱动 L3 功能规格**（目标/范围/交付/验收）**已具备进入 baseline 的文档条件**；**实现闭环**仍按 `plan.yaml` 分切片推进。  
- **全页面路径**在清单与矩阵层面 **无遗漏**；**P2 与清单 status** 已通过 **spec 口径 + 矩阵列回写** 对齐，避免「全 ✓」误导。  
- **待收敛**：`target_dto: TBD`、可选矩阵↔清单 CI；**CR-004 已 baseline_complete**；合入前建议本地 `make gate`。  
- **S2 会话（2026-03-30）**：横向九会话中 **P2 维** 的全页逐行对照、统计与「规格基线锁定」声明见 [`../page-horizontal-quality/s2-metadata-driven-contract-baseline-20260330.md`](../page-horizontal-quality/s2-metadata-driven-contract-baseline-20260330.md)。  
