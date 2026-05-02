# assistant_handwritten 弱类型盘点

**口径**：与 [`verify_assistant_search_weak_typing_ratchet.py`](../../scripts/verify_assistant_search_weak_typing_ratchet.py) 一致——`quwoquan_app/lib/assistant/**/*.dart`，排除 `**/assistant/generated/**` 与 `*.g.dart`。

**生成**：脚本一次性扫描（仓库内自跑 `python3` 即可复现）；以下为某次快照汇总。

**诚信说明**：表中 **关键字/字面量计数** 仅反映棘轮口径，**不等于**「弱类型已语义清零」。将 `dynamic` 改为 `Object?` 或替换 `.cast` **若无 metadata/codegen 或具名领域类型跟进**，不得称为主要收口成果——见 [`assistant_search_weak_typing_governance.md`](assistant_search_weak_typing_governance.md) §1.1。

## 1. 汇总

| 指标 | 值 |
|------|-----|
| 含弱类型命中文件数 | 185 |
| `Map<String, dynamic>` 字面量（合计） | 1352 |
| `dynamic` 关键字（合计） | 2931 → **2779**（记录 Wave：**关键字层面**调整，**非**等价于 DTO 化；见上） |

**棘轮基线文件**：[`assistant_search_weak_typing_baseline.json`](assistant_search_weak_typing_baseline.json)。

## 2. 按业务分桶（路径启发式）

| 分桶 | 说明 |
|------|------|
| `tool` | `tool/**` |
| `retrieval` | `retrieval/**` |
| `orchestration` | `orchestration/**` + `conversation/orchestration/**` |
| `protocol` | `protocol/**` |
| `contracts` | `contracts/**` + `reasoning/contracts/**` |
| `llm` | `infrastructure/llm/**` |
| `context` | `context/**` |
| `transcript` | `transcript/**` + `application/transcript/**` |
| `api` | `api/**` |
| `application` | `application/**`（不含 transcript 子路径已单列） |
| `other` | 其余（含 `reasoning/runtime`、`skill` 等） |

## 3. Top 文件（map + dynamic 合计降序，前 45）

| 合计 | Map | Dyn | 分桶 | 相对路径 |
|------|-----|-----|------|----------|
| 747 | 197 | 550 | orchestration | orchestration/local_phase_execution_owner.dart |
| 286 | 104 | 182 | tool | tool/impl/web/websearch_tool.dart |
| 192 | 67 | 125 | llm | infrastructure/llm/llm_provider.dart |
| 160 | 43 | 117 | other | reasoning/runtime/react_runtime.dart |
| 104 | 42 | 62 | tool | tool/impl/search/search_tool.dart |
| 97 | 36 | 61 | protocol | protocol/persisted_assistant_turn.dart |
| 96 | 19 | 77 | orchestration | orchestration/phases/understand_phase.dart |
| 92 | 26 | 66 | other | reasoning/runtime/retrieval_outcome_resolver.dart |
| 57 | 17 | 40 | protocol | protocol/run_request.dart |
| 56 | 21 | 35 | orchestration | conversation/orchestration/session_manager.dart |
| 56 | 15 | 41 | tool | tool/runtime/tool_metadata_registry.dart |
| 56 | 20 | 36 | orchestration | orchestration/phases/bootstrap_phase.dart |
| 55 | 24 | 31 | retrieval | retrieval/domain/retrieval_broker.dart |
| 52 | 11 | 41 | transcript | application/transcript/assistant_replay_record_factory.dart |
| 51 | 18 | 33 | protocol | protocol/recent_dialogue_rounds.dart |
| 47 | 19 | 28 | contracts | contracts/assistant_answer_payload_read_view.dart |
| 44 | 13 | 31 | transcript | transcript/replay/assistant_replay_record.dart |
| 43 | 11 | 32 | orchestration | orchestration/phases/finalize_runner.dart |
| 40 | 2 | 38 | api | api/assistant_api_gateway.dart |
| 40 | 13 | 27 | other | skill/domain/skill_manifest.dart |
| 40 | 10 | 30 | context | context/assembly/context_orchestrator.dart |
| 39 | 14 | 25 | orchestration | orchestration/conversation_spine.dart |
| 39 | 14 | 25 | application | application/assistant_journey_projector.dart |
| 38 | 16 | 22 | transcript | transcript/row/assistant_transcript_timeline_row.dart |
| 38 | 15 | 23 | other | skill/execution/assistant_skill_executor.dart |
| 37 | 12 | 25 | other | infrastructure/openclaw_bridge.dart |
| 35 | 15 | 20 | llm | infrastructure/llm/openai_compatible_chat_wire.dart |
| 34 | 15 | 19 | contracts | contracts/run_artifacts_map_read_views.dart |
| 34 | 13 | 21 | context | context/assembly/evidence_evaluator.dart |
| 33 | 15 | 18 | contracts | contracts/run_artifacts_map_partition.dart |
| 33 | 8 | 25 | transcript | transcript/persisted_timeline/persisted_timeline_turn_codec.dart |
| 32 | 13 | 19 | protocol | protocol/assistant_session_wire.dart |
| 31 | 11 | 20 | tool | tool/impl/web/web_fetch_tool.dart |
| 30 | 12 | 18 | retrieval | retrieval/contracts/retrieval_models.dart |
| 30 | 12 | 18 | other | reasoning/runtime/baseline_kernel.dart |
| 29 | 8 | 21 | protocol | protocol/assistant_replay_trace_payload.dart |
| 28 | 9 | 19 | other | learning/assistant_learning_runtime.dart |
| 28 | 9 | 19 | application | application/remote_assistant_entry.dart |
| 26 | 10 | 16 | other | sync/adapters/local_mock_sync_adapter.dart |
| 25 | 9 | 16 | orchestration | orchestration/state/agent_execution_state.dart |
| 25 | 12 | 13 | contracts | reasoning/contracts/agent_run_observability.dart |
| 24 | 6 | 18 | orchestration | orchestration/phases/evidence_digest_phase.dart |
| 22 | 5 | 17 | other | conversation/explainability/dialogue_state_runtime.dart |
| 22 | 9 | 13 | tool | tool/schema/tool_schema.dart |
| 22 | 8 | 14 | llm | infrastructure/llm/model_config.dart |

## 4. 与 Wave 规划的关系

- **Wave B 优先靶**：工具链 `websearch_tool` / `search_tool`；检索 `retrieval_outcome_resolver`（本表已标出）。
- **Wave C 优先靶**：`react_runtime`、`llm_provider`、`understand_phase`；**最大单文件**为 `local_phase_execution_owner.dart`，需单独里程碑，不宜与工具链混在同一小 PR。

详见 [`assistant_handwritten_metadata_wave_targets.yaml`](assistant_handwritten_metadata_wave_targets.yaml)。
