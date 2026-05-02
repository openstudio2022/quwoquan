# Assistant metadata ↔ 生成产物覆盖表

SSOT：`contracts/metadata/assistant/**/schema.yaml`（及 `assistant_run/fields.yaml` 等云侧实体定义）。端侧 Dart 契约由 `quwoquan_service/tools/codegen_app_metadata` 在 `make codegen-app` 时生成。

## 1. `schema.yaml`（runtime / 协议）↔ `lib/assistant/generated/contracts/*.g.dart`

| metadata 目录 | `dart_class`（根类型） | 生成文件 |
|---------------|------------------------|----------|
| `aggregation_state/` | （见 schema） | `aggregation_state.g.dart` |
| `answer_boundary_policy/` | （见 schema） | `answer_boundary_policy.g.dart` |
| `assistant_journey/` | （见 schema） | `assistant_journey.g.dart` |
| `assistant_process_timeline/` | （见 schema） | `assistant_process_timeline.g.dart` |
| `assistant_replay_case/` | （见 schema） | `assistant_replay_case.g.dart` |
| `assistant_run_response/` | （见 schema） | `assistant_run_response.g.dart` |
| `assistant_skill_manifest/` | （见 schema） | `assistant_skill_manifest.g.dart` |
| `assistant_tool_metadata/` | （见 schema） | `assistant_tool_metadata.g.dart` |
| `assistant_trace_event/` | （见 schema） | `assistant_trace_event.g.dart` |
| `assistant_turn/` | `AssistantTurnOutput` | `assistant_turn.g.dart` |
| `context_assembly_result/` | （见 schema） | `context_assembly_result.g.dart` |
| `context_continuity_policy/` | （见 schema） | `context_continuity_policy.g.dart` |
| `context_fill_task/` | （见 schema） | `context_fill_task.g.dart` |
| `dialogue_round_script/` | （见 schema） | `dialogue_round_script.g.dart` |
| `planner_contracts/` | （见 schema） | `planner_contracts.g.dart` |
| `preference_fact/` | （见 schema） | `preference_fact.g.dart` |
| `react_observation/` | （见 schema） | `react_observation.g.dart` |
| `recall_result/` | （见 schema，专用模板） | `recall_result.g.dart` |
| `run_artifacts/` | `RunArtifacts` | `run_artifacts.g.dart` |
| `task_graph/` | （见 schema） | `task_graph.g.dart` |

端上补充（非生成）：`answerDecision` / `diagnostics` 已为 **`type: partitioned_map`**（路径 B）：生成类型为 `*Partitioned`（`core` + `extensions`），wire 仍为单一 JSON object；只读投影与 `??` 合并辅助见 `quwoquan_app/lib/assistant/contracts/run_artifacts_map_read_views.dart`。

`map_stable_keys`（`run_artifacts/schema.yaml`）由 codegen 生成 [`run_artifacts_map_stable_keys.g.dart`](../../../../quwoquan_app/lib/assistant/generated/contracts/run_artifacts_map_stable_keys.g.dart)；分区合并见 [`run_artifacts_map_partition.dart`](../../../../quwoquan_app/lib/assistant/contracts/run_artifacts_map_partition.dart)。
| `slot_schema/` | （见 schema） | `slot_schema.g.dart` |
| `subagent_plan/` | （见 schema，专用模板） | `subagent_plan.g.dart` |
| `synthesis_readiness_result/` | （见 schema） | `synthesis_readiness_result.g.dart` |
| `tool_assessment/` | （见 schema） | `tool_assessment.g.dart` |
| `turn_synthesis_state/` | （见 schema） | `turn_synthesis_state.g.dart` |
| `understanding_result/` | （见 schema） | `understanding_result.g.dart` |

**枚举**：`assistant/_shared/enums.yaml` → `lib/assistant/generated/enums/assistant_runtime_enums.g.dart`。

## 2. 盘点结论（缺口）

- **`answerDecision` / `diagnostics`**：已实现路径 B（`partitioned_map` + Dart wrapper 类）；Go `wirepoc` 仍为整段 `json.RawMessage`（字段级 struct 可选后续增强）。
- **带 `dart_class` + `library_path` 的 `schema.yaml` 共 26 个**，与 `lib/assistant/generated/contracts/` 下 **26 个** `*.g.dart` **一一对应**，无「有 schema 未注册生成」的缺口。
- **未使用本路径 `schema.yaml` 的 assistant 元数据**（云聚合 / 技能同意等）：`assistant_run/*`（非单文件 `schema.yaml`）、`skill_consent/*` —— 由 **`assistant_run/fields.yaml` + `service.yaml`** 描述 HTTP 视图与实体；端侧列表/策略等 wire 类型由 **`codegen_app_metadata` → `assistant_cloud_api_wire.g.dart`** 生成（见生成器 `assistant_api_wire_codegen.go`），与 `AssistantRepository` 对齐。
- **Go 侧**：协议形状 PoC 见 `generated/assistant/wirepoc/`（`run_artifacts` + `assistant_turn` 同构 struct + CI `go test`）；业务服务全面消费需后续接入 assistant-service。

## 3. 共享 wire fixture（端云对照）

- `test_fixtures/wire_min_run_artifacts.json` — 最小 `RunArtifacts` JSON（Dart `RunArtifacts.fromJson` + Go `runartifacts.RunArtifacts` round-trip）。
- `test_fixtures/wire_min_assistant_turn.json` — 最小 `AssistantTurnOutput` JSON（Dart + Go `assistantturn`）。
- `test_fixtures/wire_min_run_request.json` — 最小 `AssistantRunRequest` HTTP body（Dart `AssistantRunRequest.fromJson`，见 `test/assistant/assistant_run_request_fixture_test.dart`）。
- `test_fixtures/wire_session_turn_run_artifacts.json` — 会话记录里助手轮次常见 `runArtifacts` 壳（`journey.readiness` + `understandingSnapshot`，由单测覆写 `userFacingSummary`）。

## 4. 相关命令

- 端侧：`make codegen-app`（仓库根）或 `make -C quwoquan_service codegen-app`。
- 元数据校验：`make -C quwoquan_service verify-metadata`。
- Go wire PoC：`make -C quwoquan_service test-unit`（已包含 `./generated/assistant/wirepoc/...`）或单独 `go test ./generated/assistant/wirepoc/...`。
