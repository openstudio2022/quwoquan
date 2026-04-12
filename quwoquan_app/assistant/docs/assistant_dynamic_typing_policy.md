# 助手栈 dynamic / 弱类型使用策略（Allowlist + Strict 验收）

## 双轨目标

- **Allowlist（默认工程口径）**：不追求字面量消灭 `dynamic`，而是**限制裸传播**——业务逻辑优先使用 **codegen 契约**、**只读 View** 或 **显式 Codec**，仅在边界解码。
- **StrictTyping（手写代码验收口径）**：在 **`lib/**` 手写源码**（不含 `**/generated/**`、各类 `*.g.dart`）中，**禁止**跨模块/跨层函数签名与返回值使用裸 `dynamic`、`Object?` 作为契约；**禁止**将 `Map<String, dynamic>` 当作在多个目录之间传递的「业务 DTO」。允许的例外仅见于下文 **Strict 豁免**，且必须在边界处**下一跳**收敛为具体类型、`Normalized*`、或 **metadata 生成类型**。

生成文件中的 `Map<String, dynamic> fromJson(...)` 等由 `make codegen-app` 与 SSOT 决定，**不纳入** Strict 字面门禁，但新增/变更契约仍须走 metadata。

## 三类允许弱类型的区域（新增代码默认归入其一并加简短注释；Strict 下仍须在边界收敛）

1. **`LLM_RAW`** — 流式/片段 JSON、模型输出在 `AssistantTurnOutput.fromJson` 完成前的形状；允许 `String`/`Map`/token 级处理。典型：`llm_provider`、流式字段抽取。
2. **`VENDOR_JSON`** — 外部 HTTP/MCP/搜索供应商 payload；允许在边界解析为 `Normalized*` 或小 DTO 前使用 `Map`/JSON。典型：`websearch_tool`、`openclaw_bridge`。
3. **`EXTENSION_MAP`** — 元数据声明为 `type: map` / `any` 的持久化字段及刻意保留的扩展键；**禁止**在深层业务函数签名上使用裸 `dynamic` 传递。已升级为 **`partitioned_map`（路径 B）** 的字段：编排层应使用 **生成 Core 类型** + `extensions` map，ReadView 仅作兼容薄层。

## Strict 豁免（极薄边界）

以下仅在**单文件或单调用栈的解码边界**允许出现 `Map<String, dynamic>` / 短暂 `dynamic`，且调用方下一跳须为具体类型：

- HTTP/JSON **单次 decode** 入口（如 gateway、codec）；
- **LLM / 供应商** 原始片段（归类 `LLM_RAW` / `VENDOR_JSON`）；
- 元数据明确为 **扩展桶** 的 `extensions` 字段（`Map<String, dynamic>`），且不得再拆成裸 `dynamic` 向深层传递。

## 注释约定（复制即用）

```dart
// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — RunArtifacts `*Partitioned.extensions` 或遗留 ReadView。
// ASSISTANT_WEAK_TYPE: LLM_RAW — 尚未契约化的模型输出片段。
// ASSISTANT_WEAK_TYPE: VENDOR_JSON — 供应商原始 JSON，边界归一化后进入工具结果。
```

## 可选：度量（不阻断 CI）

在仓库根或 `quwoquan_app` 下执行：

```bash
./assistant/scripts/count_dynamic_in_assistant.sh
```

用于观察 `lib/assistant` 与 `lib/ui/assistant` 中 `dynamic` 与 `Object?` 命中行数趋势；不作为硬门禁。新增裸 `dynamic` 传播时建议加 `ASSISTANT_WEAK_TYPE` 注释（见上文）。

## 当前阶段：`answerDecision` / `diagnostics`（路径 B 已启用）

- **SSOT**：`contracts/metadata/assistant/run_artifacts/schema.yaml` 将二者声明为 **`type: partitioned_map`**：稳定键由子契约 **Core** 类型承载，其余键进入 **`extensions`**；JSON 线上仍为**单一对象**（与路径 A  wire 形状兼容），由生成代码与 `RunArtifactsMapPartition` 负责拆分/合并。
- **ReadView**（`run_artifacts_map_read_views.dart`）保留为兼容层；优先在新代码使用 **`runArtifacts.answerDecision.core`**、**`runArtifacts.diagnostics.core`** 与 **`extensions`**（生成类型名为 `RunArtifacts*Partitioned`）。
- **Go `wirepoc`**：仍为 `json.RawMessage` 承载整段对象（PoC 不做字段级拆分），与 Dart 细分类型共存。

若再收窄扩展桶或新增稳定键，须同步改 `map_stable_keys`、子契约字段、`CODEGEN_COVERAGE.md` 与相关 fixture。

## SSOT

结构化契约以仓库根目录下 `quwoquan_service/contracts/metadata/assistant/` 为准；覆盖表见同目录 `CODEGEN_COVERAGE.md`（相对 `quwoquan_app` 为 `../quwoquan_service/contracts/metadata/assistant/`）。

## 元数据或 `RunArtifacts` 形状大改后的验收

- 跑 `flutter test test/assistant/assistant_wire_fixture_roundtrip_test.dart`（与 `wire_min_run_artifacts.json` / Go `wirepoc` 对齐）。
- 有设备时补跑 `integration_test/assistant_manual_replay_test.dart`，必要时更新 `integration_test/support/assistant_replay_baseline.dart` 说明。

## 共享 fixture 路径（测试）

单测优先使用 [`test/assistant/assistant_test_fixture_paths.dart`](../../test/assistant/assistant_test_fixture_paths.dart) 的 `assistantMetadataFixturePath` / `assistantLoadRunArtifactsFixture`，避免手写相对路径分叉与无类型 `Map` 夹具。
