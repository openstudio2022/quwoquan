## 1. Baseline Consolidation（已实现能力基线固化）

- [x] 1.1 盘点并统一 `lib/personal_assistant/` 现有模块边界（engine/tools/skills/memory/gateway/connectors），清理重复入口与临时代码
- [x] 1.2 统一 `AssistantTraceEvent`、`AssistantRunRequest/Response`、`AssistantToolResult` 协议字段并补充兼容层测试
- [x] 1.3 将 App 内调用统一收敛到 `assistant_gateway`，移除聊天页和助手页中的分散调用分支

## 2. Independent Config & Model Routing（独立配置与多模型路由）

- [x] 2.1 新增 `personal_assistant` 独立配置目录与加载器（优先本地配置 + 环境变量前缀），默认不读取 moltbot
- [x] 2.2 为 `SwitchableAssistantLlmProvider` 增加配置来源优先级与回退策略（local default -> remote configured）
- [x] 2.3 增加模型管理接口验收测试：列模型、查询当前模型、切换模型、配置缺失回退

## 3. Skill Runtime & Market Expansion（声明式技能与市场扩容）

- [x] 3.1 为 Skill manifest 增加 schema 校验（字段完整性、executionTarget 合法性、参数类型约束）
- [x] 3.2 完善 `tool_chain` 执行器：支持多工具串联、上下文透传、步骤失败短路与错误聚合
- [x] 3.3 扩展技能市场：技能分类、版本号、启停状态持久化升级与刷新机制

## 4. Toolkit & Device Capability Routing（工具集与多设备能力路由）

- [x] 4.1 定义 device profile（mobile/tablet/pc）与 capability matrix（local-only/remote-preferred/hybrid）
- [x] 4.2 在工具与技能执行链路中加入路由决策层，根据设备能力自动选择本地执行或远程转发
- [x] 4.3 为 websearch、本地上下文、相册、intent bridge 补充统一错误码与降级文案

## 5. Open Gateway & External Channels（对外网关与渠道接入）

- [x] 5.1 加强 `assistant_http_gateway`：token 鉴权中间件、请求校验、错误响应规范化
- [x] 5.2 为网关增加基础限流与审计日志（run / skills / invokeSkill）
- [x] 5.3 完成 OpenClaw/飞书调用适配示例与可运行脚本（请求样例、返回样例、失败样例）

## 6. App Integration & End-to-End Acceptance（端到端验收）

- [x] 6.1 完成 App 内“私人助手对话”链路验收：文本问答触发 AgentLoop + 可见 trace
- [x] 6.2 完成“飞书语音指令 -> OpenClaw -> personal_assistant skill(websearch)”链路验收
- [x] 6.3 补充回归测试与文档：多设备差异、独立配置说明、部署与回滚步骤
