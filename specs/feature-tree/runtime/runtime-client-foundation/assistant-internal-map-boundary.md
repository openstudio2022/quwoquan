# Assistant 域：内部 `Map<String, dynamic>` 边界说明

与 Map 类型化整改计划 **阶段 5** 对齐：目标是 **进入 `lib/ui/assistant/**` 的数据强类型化**；以下目录允许在迁移完成前保留结构化 Map（JSON/LLM/工具协议），**不得**作为规避页面门禁 C 的手段。

## 允许保留 Map 为主的内部目录（约定）

| 路径前缀 | 说明 |
|----------|------|
| `lib/assistant/infrastructure/llm/` | Provider 响应解析、流式分片 |
| `lib/assistant/tool/impl/` | 工具入参/出参 wire |
| `lib/assistant/orchestration/local_phase_execution_owner.dart` | 编排状态机（应逐步投影为契约类型） |
| `lib/assistant/protocol/` | 协议载荷；**对外持久化/同步**应优先已有 codegen 模型 |
| `lib/assistant/generated/` | 生成体（含 `.g.dart`），按门禁不手改 |

## UI 边界

- `lib/ui/assistant/**`：**目标零业务 Map**；过渡期内仅允许经 `ContentPostDetailPayload` 同类模式或 ViewModel 收口。
- 字段名字符串：仅允许出现在 `tryParse` / `fromJson` / codegen 生成体内（见工程 Dart 规范个人助理契约节）。

## 复核命令

```bash
python3 scripts/report_map_typing_baseline.py
make verify-app-page-abc-governance-enforce-c
```
