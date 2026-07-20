# 会话 C：页面强类型治理（规格摘要）

与 [page_abc_governance.md](page_abc_governance.md) 中 **C** 节一致；本文件补充 **browse 日志 envelope**、**创作埋点** 与 **中枢收口** 约定。

## 1. 门禁

- 扫描集与 `verify_page_matrix_scan_complete.py` 一致（64 路径）。
- 验收：`python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-c`。

### 1.1 门禁 C 与架构目标的关系（勿混用）

- **门禁 C** 仅检测 64 路径源文件中的字面量 `\bdynamic\b` 与 `Map<String, dynamic>`；**通过 C 不等于完成类型化**。
- **架构目标**：与契约/入库/可观测一致的结构须 **`contracts/metadata` → `make codegen-app` → 生成 DTO**；页面/shell 持 **具体类型**，仅在 `.toMap()` / `fromMap` 边界与 `Map<String, dynamic>` 交接。
- **禁止**用 `Map<String, Object?>` 或松散 Map 在页面层「替代」codegen；亦**禁止**为躲 C 扫描而只做字面量替换却不补 metadata。

## 2. 客户端 browse / page_access 日志

云端产品遥测真相源为
[`ops/event_record/event_catalog.yaml`](../../quwoquan_service/contracts/metadata/ops/event_record/event_catalog.yaml)，
端侧生成产物为
`quwoquan_app/lib/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart`。

`page_access_log_util.dart` 同时写两条边界：

- 本地 `AppLogService`：只用于脱敏诊断与回放，payload Map 不自动上传。
- 云端 `AppTelemetryRecorder`：只接收 codegen 的 `AppTelemetryPayload.pageOpen/pageReturn`。

本地诊断 Map 不是 wire DTO，也不得反向成为运营事件契约。

## 3. 创作页埋点（create_*）

`create_page` 侧 `create_editor_ready`、`create_draft_saved`、`create_publish_success` 等事件的 **properties** 应与内容域语义一致（`postId`、`editorKind`、可选 `surfaceId`）；新增属性前先补 **metadata**，再 `make codegen-app`，在 app 侧使用 **生成类型**（同上模式），禁止页面内手写匿名 Map。

## 4. AppLog 中枢

- `AppLogService.writeEvent` / `writeRunFile` 的 Map 只存在于本地诊断边界，与 `AppLogRedactor` / 落盘 JSON 一致。
- 云端结构化内容必须来自 metadata 生成的 typed payload，禁止把本地诊断 Map 当作上传契约。
- **64 路径内**禁止字面量 `Map<String, dynamic>` 与 `dynamic`（门禁扫描）。

## 5. 参考命令

```bash
make verify-app-page-abc-governance
python3 quwoquan_app/scripts/runtime/verify_page_abc_governance.py --enforce-c
```

## 6. 契约测试与 Map 断言（非助手域）

- **推荐**：关键路径用 **codegen DTO 构造 fixture**，再 **`.toMap()`** 与请求体/响应体形状对比（或与 golden JSON 对齐），减少手写匿名 `Map` 的随意性。
- **可接受**：测试中 `json.decode(...) as Map<String, dynamic>`、以及对 **wire 形状** 的 `Map<String, dynamic>` 断言（解码后、收窄前）；这与 §1.1「边界与 `Map` 交接」一致。
- **不推荐**：在测试里用松散 `Map` 冒充「业务状态」却不对应具体 DTO；若断言的是跨层契约，优先补 metadata 与 fixture DTO。
- **生成体 `*.g.dart`**：内含 `_parse*(dynamic)` 等，**禁止手改**；弱类型收口走 metadata / codegen，不在契约测试里要求「字面量零 dynamic」。
