## Context

`personal-assistant-commercial-v1` 已完成核心实现，本设计文档用于将既有实现固化为可验收、可灰度、可演进的工程基线。  
目标不是补丁兼容，而是平台化能力收敛：控制面与数据面分离、可扩展 provider/adapter、可审计可治理的生产强化闭环。

## Goals / Non-Goals

### Goals

- 以 `assistent` 语义和 `/v1/assistent/*` 对外 API 形成稳定商用接口。
- 固化 ReAct++（Plan/Act/Observe/Reflect/Replan）推理循环与结构化知识问答输出。
- 固化 skill 商业治理（tier/channel/device/permission/defaultEnabled）。
- 固化 Adapter SPI 非侵入式接入与 provider 策略路由。
- 固化 SLO -> 告警路由 -> 抑制 -> 自动降级 -> 人工恢复全链路。

### Non-Goals

- 不在本变更中引入 `/v2/*` 对外 API。
- 不新增第二套并行规格目录。

## Architecture

### 1) Runtime Plane

- `agent_loop` + `react_runtime` 承载 ReAct++ 主循环。
- `skill_router` + `skill_executor` 承载技能选择与执行。
- `memory_hub` + 向量存储承载 STM/MTM/LTM 的语义召回。

### 2) Gateway Plane

- `assistent_api_gateway` 统一暴露 providers/skills/runs/stream/sessions/costs/alerts/adapters。
- 网关负责鉴权、ACL、参数标准化、错误码与观测字段注入。

### 3) Control Plane

- `assistent_provider_registry` 管 provider 注册与运行时状态（含临时禁用）。
- `assistent_provider_policy` 联动成本、时延、健康、SLO 快照进行选路。
- `assistent_configuration_center` 提供运行配置快照与动态读取。

### 4) Observability & Governance

- `assistent_trace_service` 统一 runId/traceId/toolCallId。
- `assistent_slo_monitor` 输出 warning/critical 判定。
- `assistent_alert_dispatcher` 实现日志/Webhook/Feishu 路由与抑制窗口。
- critical 告警触发自动降级，`/providers/{id}/recover` 提供人工恢复。

## Key Design Constraints

- 对外命名统一：`assistent*` + `/v1/*`。
- Adapter 必须走 SPI，禁止在核心链路硬编码渠道分支。
- 安全校验必须支持 `none | token | hmac_sha256`，HMAC 使用常量时间比较并支持时间戳窗口。
- UI 改造必须遵循 `AppColors`、`AppSpacing`、`AppTypography`、`UITextConstants`，禁止硬编码视觉常量。

## Acceptance Mapping

- 规格基线：`openspec/specs/personal-assistant-commercial-v1/spec.md`
- 运行联调：`personal_assistant/scripts/assistent_canary_check.sh`
- 告警联调：`personal_assistant/scripts/assistent_alert_route_test.sh`
- 渠道联调：`personal_assistant/scripts/feishu_openclaw_voice_demo.sh`

以上映射用于确保“规格 -> 实现 -> 运维脚本 -> 灰度验收”一致。
