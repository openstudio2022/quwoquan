# 会话 C：页面强类型治理（规格摘要）

与 [page_abc_governance.md](page_abc_governance.md) 中 **C** 节一致；本文件补充 **browse 日志 envelope**、**创作埋点** 与 **中枢收口** 约定。

## 1. 门禁

- 扫描集与 `verify_page_matrix_scan_complete.py` 一致（64 路径）。
- 验收：`python3 scripts/verify_page_abc_governance.py --enforce-c`。

### 1.1 门禁 C 与架构目标的关系（勿混用）

- **门禁 C** 仅检测 64 路径源文件中的字面量 `\bdynamic\b` 与 `Map<String, dynamic>`；**通过 C 不等于完成类型化**。
- **架构目标**：与契约/入库/可观测一致的结构须 **`contracts/metadata` → `make codegen-app` → 生成 DTO**；页面/shell 持 **具体类型**，仅在 `.toMap()` / `fromMap` 边界与 `Map<String, dynamic>` 交接。
- **禁止**用 `Map<String, Object?>` 或松散 Map 在页面层「替代」codegen；亦**禁止**为躲 C 扫描而只做字面量替换却不补 metadata。

## 2. 客户端 browse / page_access 日志（metadata + codegen）

**真相源**：[`quwoquan_service/contracts/metadata/ops/event_record/projections/`](../../../quwoquan_service/contracts/metadata/ops/event_record/projections/) 下 `app_log_*.yaml`（`client_projection`）。

**端侧产物**（禁止手改）：`quwoquan_app/lib/cloud/runtime/generated/ops/app_log_*.g.dart`，例如：

- `AppLogBottomNavTapMeta` — bottom_nav_tap 的 `actionMeta`
- `AppLogPageBrowsePayload` / `AppLogPageBrowseSummaryPayload` — `event=browse`
- `AppLogPageOpenPayload` / `AppLogPageOpenSummaryPayload` — `event=open`
- `AppLogPageReturnPayload` / `AppLogPageReturnSummaryPayload` — `event=return`

调用方（如 `MainAppShell`、`page_access_log_util`）构造 **DTO 实例** 后 `.toMap()` 传入 `AppLogService.writeEvent`（`toMap()` 仅在生成体内含 `Map<String, dynamic>`，业务/shell 源文件不手写该 map 字面量）。

与 [ops/event_record/fields.yaml](../../../quwoquan_service/contracts/metadata/ops/event_record/fields.yaml) 运营入库字段独立：本地 JSONL 为诊断/回放；运营入库走 `OpsEventRecordInput` / `AnalyticsService`。

## 3. 创作页埋点（create_*）

`create_page` 侧 `create_editor_ready`、`create_draft_saved`、`create_publish_success` 等事件的 **properties** 应与内容域语义一致（`postId`、`editorKind`、可选 `surfaceId`）；新增属性前先补 **metadata**，再 `make codegen-app`，在 app 侧使用 **生成类型**（同上模式），禁止页面内手写匿名 Map。

## 4. AppLog 中枢

- `AppLogService.writeEvent` / `writeRunFile` 入参仍为 **`Map<String, dynamic>`**（与 `AppLogRedactor` / 落盘 JSON 一致）。
- **禁止**用 `Map<String, Object?>` 作为「类型化」替代；结构化内容须来自 **metadata 生成的 DTO** 再 `.toMap()`。
- **64 路径内**禁止字面量 `Map<String, dynamic>` 与 `dynamic`（门禁扫描）。

## 5. 参考命令

```bash
make verify-app-page-abc-governance
python3 scripts/verify_page_abc_governance.py --enforce-c
```
