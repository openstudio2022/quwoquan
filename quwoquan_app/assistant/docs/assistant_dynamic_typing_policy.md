# 助手栈 dynamic / 弱类型使用策略（Allowlist）

目标不是消灭 `dynamic` 关键字，而是**限制裸传播**：业务逻辑优先使用 **codegen 契约**、**只读 View** 或 **显式 Codec**，仅在边界解码。

## 三类允许弱类型的区域（新增代码默认归入其一并加简短注释）

1. **`LLM_RAW`** — 流式/片段 JSON、模型输出在 `AssistantTurnOutput.fromJson` 完成前的形状；允许 `String`/`Map`/token 级处理。典型：`llm_provider`、流式字段抽取。
2. **`VENDOR_JSON`** — 外部 HTTP/MCP/搜索供应商 payload；允许在边界解析为 `Normalized*` 或小 DTO 前使用 `Map`/JSON。典型：`websearch_tool`、`openclaw_bridge`。
3. **`EXTENSION_MAP`** — 元数据声明为 `type: map` / `any` 的持久化字段（如 `RunArtifacts.answerDecision`、`diagnostics`）及刻意保留的扩展键；**禁止**在深层业务函数签名上使用裸 `dynamic` 传递，应使用 **ReadView** 或 `Map<String, dynamic>` + 视图。

## 注释约定（复制即用）

```dart
// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — RunArtifacts.answerDecision 扩展键，用 RunArtifactsAnswerDecisionReadView。
// ASSISTANT_WEAK_TYPE: LLM_RAW — 尚未契约化的模型输出片段。
// ASSISTANT_WEAK_TYPE: VENDOR_JSON — 供应商原始 JSON，边界归一化后进入工具结果。
```

## 可选：度量（不阻断 CI）

在仓库根或 `quwoquan_app` 下执行：

```bash
./assistant/scripts/count_dynamic_in_assistant.sh
```

用于观察 `lib/assistant` 与 `lib/ui/assistant` 中 `dynamic` 与 `Object?` 命中行数趋势；不作为硬门禁。新增裸 `dynamic` 传播时建议加 `ASSISTANT_WEAK_TYPE` 注释（见上文）。

## 当前阶段：`answerDecision` / `diagnostics` 契约战略（工程缺省）

在协议/产品未另行签发「核心字段 object 化」需求前，采用 **路径 A**：

- **A（现行）**：metadata 继续将 `RunArtifacts.answerDecision`、`diagnostics` 声明为 `type: map`；端上通过 **ReadView**、**`map_stable_keys` 分区**、**wire fixture 往返** 锁定稳定键与扩展键，不在业务层手写全封闭 DTO。
- **B（待拍板）**：在 `contracts/metadata/assistant/run_artifacts/schema.yaml` 等 SSOT 中拆 **核心 `object` + 扩展 map**（或 codegen 支持未知键保留），再 `make codegen-app`、更新共享 fixture 与 Go `wirepoc`。

若后续切换至 B，须同步更新本节与 `CODEGEN_COVERAGE.md` 说明。

## SSOT

结构化契约以仓库根目录下 `quwoquan_service/contracts/metadata/assistant/` 为准；覆盖表见同目录 `CODEGEN_COVERAGE.md`（相对 `quwoquan_app` 为 `../quwoquan_service/contracts/metadata/assistant/`）。

## 元数据或 `RunArtifacts` 形状大改后的验收

- 跑 `flutter test test/assistant/assistant_wire_fixture_roundtrip_test.dart`（与 `wire_min_run_artifacts.json` / Go `wirepoc` 对齐）。
- 有设备时补跑 `integration_test/assistant_manual_replay_test.dart`，必要时更新 `integration_test/support/assistant_replay_baseline.dart` 说明。

## 共享 fixture 路径（测试）

单测优先使用 [`test/assistant/assistant_test_fixture_paths.dart`](../../test/assistant/assistant_test_fixture_paths.dart) 的 `assistantMetadataFixturePath`，避免手写相对路径分叉。
