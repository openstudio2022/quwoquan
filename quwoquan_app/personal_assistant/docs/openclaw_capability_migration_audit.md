# OpenClaw 能力迁移审计（趣我圈 Personal Assistant）

## 目标

本审计用于核对 OpenClaw 的核心能力是否已经迁移到 `quwoquan_app` 的 `personal_assistant` 引擎，并标注商业化完成度。

## 能力矩阵

| OpenClaw 能力域 | 趣我圈当前实现 | 完成度 | 说明 |
| --- | --- | --- | --- |
| AgentLoop 多阶段执行 | ReAct++ (`Plan/Act/Observe/Reflect/Replan`) | 高 | 已在 `react_runtime.dart` 落地状态循环、预算、重规划。 |
| 工具总线与能力路由 | ToolRegistry + CapabilityRouter + CapabilityGateway | 高 | 已支持 `localOnly/remotePreferred/hybrid` 路由。 |
| 知识问答策略引擎 | `KnowledgeQaEngine` | 高 | 支持初查/补查/交叉验证/归纳输出，并产出结论/依据/不确定性。 |
| 搜索供应商统一 | Brave / Perplexity / OpenClaw Proxy | 高 | `web_search` 工具统一 provider 抽象。 |
| 技能市场治理 | tier/channel/device/订阅策略 | 高 | Manifest + Gateway 硬约束，默认免订阅知识问答。 |
| 外部网关开放 | `/v1/run` `/v1/run/stream` `/v1/skills/*` `/v1/sessions/*` | 高 | 含鉴权、限流、审计和 SSE trace。 |
| 飞书渠道接入 | 演示脚本 + channel ACL | 中高 | 已打通 invoke/run/stream；生产级 bot adapter 可继续外置部署。 |
| OpenClaw 双向调用 | `OpenClawBridge` 本地/远程互调 | 中高 | 已支持 PA->OpenClaw 远程和 OpenClaw->PA 本地绑定调用。 |
| 长期记忆与会话 | Session 持久化 + VectorStore 持久化 | 中高 | 当前为轻量持久化实现，后续可平滑替换真实 ObjectBox 实体层。 |
| 可观测性 | runId/traceId/toolCallId | 高 | 请求/响应/trace 贯通，支持跨渠道追踪。 |

## 仍建议持续强化（不阻塞当前商业级首版）

1. **生产级 Feishu Adapter 服务化**：将示例脚本替换为可部署 webhook/事件总线服务。
2. **策略中心化配置**：将知识问答域策略抽离到配置文件并支持热更新。
3. **更强记忆检索**：接入真实 embedding 模型，替换当前轻量 embedding。
4. **成本治理**：增加 provider 级耗时/成本统计看板与动态路由策略。

## 结论

当前 `personal_assistant` 已完成从 MVP 到商业级首版架构升级，核心能力可与 OpenClaw 对齐并实现双向互操作。剩余项属于“生产规模化增强”，不属于能力缺失。

