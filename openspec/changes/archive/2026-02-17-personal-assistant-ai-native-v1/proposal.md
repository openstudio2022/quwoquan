## Why

趣我圈当前“小趣”入口与页面已成型，但核心仍以 mock 逻辑为主，缺少可持续扩展的 AI 原生引擎能力。现在需要建立一个内置在 `quwoquan_app` 的 `personal_assistant` 核心引擎，使 App 对话、Skill 市场、系统能力调用和多渠道开放形成统一能力底座。

## What Changes

- 在 `quwoquan_app/lib/personal_assistant/` 内建立 AI 原生引擎分层：AgentLoop、ReAct runtime、tool registry、skill runtime、memory、gateway/connectors。
- 引入可切换模型提供器：本地优先 + OpenAI 兼容远程模型（首期接入 MiMo），支持运行时模型切换和失败回退。
- 建立声明式无 Shell Skill 体系（YAML/JSON），支持 `ios_intent`、`android_intent`、`native_api`、`tool_chain` 执行目标映射。
- 建立系统能力工具集（websearch、本地上下文、相册、intent bridge）并纳入统一 trace。
- 建立 Skill 市场基础能力（技能发现、启用/禁用、订阅状态）并接入助理页面。
- 对现有会话入口做最小侵入改造：`/chat/assistant` 直接走 personal_assistant 引擎，展示 tool/skill trace。
- 提供对外统一网关接口（`/v1/run`、`/v1/skills`、`/v1/skills/invoke`）供 OpenClaw/飞书等渠道集成，且不暴露内部 UI。

## Capabilities

### New Capabilities

- `personal-assistant-engine`: 个人私人助手核心引擎（AgentLoop + ReAct + trace + session）。
- `personal-assistant-skill-runtime`: 声明式无 Shell Skill 加载、路由与执行目标映射能力。
- `personal-assistant-toolkit`: 系统能力工具集与统一工具注册执行框架。
- `personal-assistant-model-routing`: 多模型配置加载、切换与回退策略。
- `personal-assistant-skill-market`: 技能市场基础能力（目录、订阅、启用状态）。
- `personal-assistant-open-gateway`: 对外统一网关与渠道集成能力（OpenClaw/飞书）。

### Modified Capabilities

- `chat`: 小趣会话从 mock 回复升级为引擎驱动对话和工具轨迹展示。
- `app-global`: 小趣从 UI 入口升级为 AI 原生核心能力，形成 App 内主体验与外部渠道统一编排。

## Impact

- Affected code:
  - `lib/features/chat/pages/chat_detail_page.dart`
  - `lib/features/assistant/pages/assistant_home_page.dart`
  - `lib/personal_assistant/**` (new)
  - `assets/personal_assistant/skills/**` (new)
- APIs:
  - New local HTTP gateway endpoints: `/v1/run`, `/v1/skills`, `/v1/skills/invoke`
- Dependencies:
  - 增加 `yaml` 解析依赖；后续阶段可扩展向量库与本地模型依赖
- Systems:
  - 模型配置独立化（不依赖 moltbot 运行时），但支持兼容其配置格式导入用于迁移期
