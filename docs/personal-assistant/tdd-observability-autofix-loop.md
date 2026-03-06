# 小趣助手：TDD + 可观测自主修复闭环

## 设计原则

**问题越早在"距离用户越远的层"被拦截，修复代价越低。**  
目标：在 UI 回归测试之前，通过 L0（静态）→ L1（协议）→ L2（引擎）→ L3（UI 契约）四层测试体系，提前拦截所有已知类型的问题。

---

## 1. 四层测试体系

| 层级 | 执行方式 | 覆盖目标 | 执行时机 | Gate 阻断 |
|---|---|---|---|---|
| **L0 静态分析** | `python3 scripts/verify_degraded_response_contract.py` | 降级响应无根因、JSON 泄漏到 finalText、catch 无 $error | `make gate` | 是 |
| **L1 协议契约** | `flutter test` (桶 A) | 降级响应根因字段、消息历史协议、可观测字段完整性 | `make gate` | 是 |
| **L2 引擎集成** | `flutter test` (桶 B) | 工具观察协议、结构化输出、agent_loop 上下文守护 | `make gate` | 是 |
| **L3 UI 契约** | `flutter test` (桶 C) | 消息构建逻辑、渲染稳定性（无网络依赖）| `make gate` | 是 |
| **L4 Live Smoke** | 真实模型调用 | 端到端响应质量 | Nightly | 否（advisory）|

---

## 2. 测试文件映射（L0~L3 全覆盖）

### L0：`scripts/verify_degraded_response_contract.py`

检查点：
- `capability_gateway.dart` / `agent_loop.dart`：每处 `'助手暂时不可用'` 构造位置必须有 `errorCode`
- 每处 `degraded: true` 必须有 `errorCode`
- `finalText` 字面量不得含 `assistant_turn_v2` / `contractVersion`
- catch 块 trace.message 必须含 `$error`（保留根因）
- `acceptance.yaml` 引用的测试文件必须实际存在
- 关键日志字段必须存在：`logType`、`level`、`sourceDomain`、`sourceService`、`component`、`target`
- 端云关联字段必须存在：`traceId`、`spanId`、`requestId`、`correlationId`

### L1（桶 A）：最先执行，失败即退

| 测试文件 | 验收 | 核心命题 |
|---|---|---|
| `degraded_response_root_cause_contract_test.dart` | A3/A8 | degraded response 必须携带合法 errorCode 和动态根因 trace |
| `message_history_protocol_contract_test.dart` | A3/A8 | load() 过滤降级消息、dynamic 类型不被 toString()、summarizeRecent 不泄漏 JSON |
| `observability_root_cause_contract_test.dart` | A4/A8 | runId/traceId 非空、lifecycleStart/End 必须存在、toolCallId 一致 |
| `quality_metrics_gate_test.dart` | A9 | decisionParseSuccessRate ≥ 99.5%、renderFallbackRate < 1% |
| `history_contamination_guard_test.dart` | A3/A8 | 失败文案不得污染下一轮 LLM 输入历史 |
| `test/ui/assistant/contract/assistant_message_history_contract_test.dart` | A3/A10 | chat_detail_page 消息过滤逻辑（isError/degradedPrefix/streaming/empty）|
| `cross_stack_log_contract_test.dart` | A4/A8 | `sourceDomain/sourceService/component/target` 与 `correlationId` 端云可贯通 |

### L2（桶 B）：引擎集成

| 测试文件 | 验收 |
|---|---|
| `structured_response_contract_test.dart` | A9/A10 |
| `react_runtime_tool_observation_contract_test.dart` | A3/A8 |
| `dual_gate_integration_test.dart` | A3 |
| `agent_loop_context_gate_test.dart` | A3 |
| `observability_completeness_test.dart` | A4 |

### L3（桶 C）：UI Widget 契约

| 测试文件 | 验收 |
|---|---|
| `test/ui/chat/widgets/` 下所有测试 | A10 |

---

## 3. Gate 命令

```bash
# 本地完整 gate（L0 + L1 + L2 + L3）
make gate

# 仅跑 L0 + 桶 A（最快反馈，30s 内）
python3 scripts/verify_degraded_response_contract.py && \
  bash scripts/run_pa_core_tests.sh --bucket-a

# 完整 PA Core（桶 A + B + C）
bash scripts/run_pa_core_tests.sh
```

---

## 4. 编程助手自主修复循环

```
1. 发现问题（用户报告 UI 出现"助手暂时不可用"或空过程）
   ↓
2. 先跑最快的检查：
   python3 scripts/verify_degraded_response_contract.py
   bash scripts/run_pa_core_tests.sh --bucket-a
   ↓
3. 根据失败测试名定位根因文件：
   ...degraded_response_root_cause... → capability_gateway.dart / run_response.dart
   ...message_history_protocol...     → session_manager.dart
   ...history_contamination...        → agent_loop.dart / session_manager.dart / chat_detail_page.dart
   ...observability_root_cause...     → trace_events.dart / run_response.dart
   ...assistant_message_history...    → chat_detail_page.dart (line 1007-1027)
   ...tool_observation...             → react_runtime.dart / llm_provider.dart
   ↓
4. 修复代码
   ↓
5. 重跑同一失败测试，直到通过
   ↓
6. 回跑完整 PA Core：bash scripts/run_pa_core_tests.sh
   ↓
7. 最后 make gate
```

---

## 5. 可观测最小要求（必须）

- 每次 run 必须包含：`runId`、`traceId`
- 每次 run 必须包含：`sourceDomain`、`sourceService`
- 每条关键事件必须包含：`logType`、`level`、`component`、`target`
- 跨端云追踪必须包含：`spanId`、`requestId`、`correlationId`
- traces 至少有：`lifecycleStart` 与 `lifecycleEnd`
- structured response 必须包含：`qualityMetrics.decisionParseSuccess`、`renderFallback`、`heuristicFallbackUsed`
- 工具回合协议必须满足：`assistant(tool_calls)` → `tool(tool_call_id)` → `assistant(answer)`
- 降级响应必须包含：`errorCode`（非空）、`traces[type=toolError].message`（含根因动态信息）

---

## 6. 测试与验收标准绑定

`acceptance.yaml` 中每条验收标准明确绑定测试文件（按 L0/L1/L2/L3 分层注释）：
- A3 → L1 degraded + history + message_history + react_runtime_tool_observation + ui/assistant/contract
- A4 → L1 observability_root_cause + L2 observability_completeness + L2 log_completeness
- A8 → L0 脚本 + L1 全部桶 A 测试 + L2 structured/protocol/tool 相关
- A9 → L1 quality_metrics_gate + L2 structured_response + json_answer_parse
- A10 → L3 UI + L2 structured_response + quality_metrics_gate

`scripts/verify_degraded_response_contract.py` 中的规则 5 会自动检查 acceptance.yaml 引用的测试文件是否存在，确保映射不腐化。
