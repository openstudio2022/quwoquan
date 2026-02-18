## Why

个人私人助理已完成从应用内功能向平台化商业能力的升级，需要在 OpenSpec 变更流中沉淀统一工件，确保后续灰度、验收、审计与持续演进有单一基线。  
当前缺少可直接用于 `opsx-apply` 的 change 工件，导致流程阻塞。

## What Changes

- 新增 `personal-assistant-commercial-v1` change 工件，承接既有商业化实现结果。
- 将商业化能力规格统一归并到 `personal-assistant-commercial-v1` 能力目录，作为后续优化与回归基线。
- 固化生产强化约束：SLO 告警策略路由、抑制窗口、自动降级与人工恢复、灰度操作序列与命令清单。
- 将现状定义为“已实现基线”，用于后续增量变更而非重复建设。

## Capabilities

### New Capabilities
- `personal-assistant-commercial-v1`: 个人私人助理商业化平台基线能力（网关、推理循环、技能治理、适配器服务化、可观测与生产强化）。

### Modified Capabilities
- `chat`: 对话链路改为接入能力网关并承载 runId/traceId 观测字段。
- `app-global`: 应用级运行配置新增商业网关、告警路由与 provider 自动降级相关参数。

## Impact

- OpenSpec 变更工件：`openspec/changes/personal-assistant-commercial-v1/*`
- 统一能力规格：`openspec/specs/personal-assistant-commercial-v1/spec.md`
- 受影响模块：`lib/personal_assistant/*`、`lib/features/assistant/*`、`lib/features/chat/*`、`lib/main.dart`
- 运维与验收：`personal_assistant/docs/*`、`personal_assistant/scripts/*`
