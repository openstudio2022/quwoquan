## Context

当前私人助理链路已具备 ReAct 主循环与双门禁原型能力，但仍存在三类工程问题：  
1) 关键提示词与上下文拼装策略部分写在代码中，难以灰度与快速回滚；  
2) 垂类覆盖不足且契约不统一，难以做差异化增长；  
3) 规格层同时存在 `personal-assistant-commercial-v1` 与 `personal-assistant-domain-orchestration-v1`，维护成本高且易分叉。

本次变更需要跨 `engine/protocol/observability/specs/assets` 多模块改造，并引入“模板注册 + 19 垂类目录（18 主 + 1 兜底） + 结构化 run 响应”统一架构。核心约束：
- 2 个总控模板（总规划/最终汇总）与 19 垂类模板必须可动态替换；
- 模板版本必须支持灰度；
- 记录规格目录需清理为统一入口；
- 对外 run 响应新增结构化字段需兼容旧消费者。

## Goals / Non-Goals

**Goals:**
- 实现 2 个总控模板 + 19 垂类模板（18 主 + 1 兜底）的模板驱动运行时，不在业务代码中写死提示词。
- 建立 19 垂类统一输入输出契约与前后置条件（Precondition/Postcondition）。
- 在 run 响应中输出结构化对象（context/domain/synthesis/fill tasks），支持前端直接渲染补齐任务卡片。
- 将规格统一到 `openspec/specs/personal-assistant/spec.md`，记录两个目录仅保留迁移说明。
- 模板版本支持灰度选择与回滚。

**Non-Goals:**
- 不在本次实现完整训练或推荐排序系统。
- 不引入新的外部 SaaS 编排平台。
- 不强制替换现有所有工具，只在助手主链路接入模板驱动。

## Decisions

### Decision 1: 引入 TemplateRuntime（模板运行时）
- **Choice**: 新增模板运行时组件（registry + renderer + selector），统一加载 `assets/personal_assistant/prompts/**`。
- **Why**: 避免提示词散落在代码，支持版本化与灰度。
- **Alternative considered**: 继续在代码中拼接字符串；被拒绝，无法灰度和回滚。

### Decision 2: 2 总 + 19 垂类统一目录
- **Choice**: 域目录固定为 19 个 `domainId`（18 主垂类 + `fallback_general_search`），每域至少一套主任务模板与补查模板；总控模板为 `planner.global_plan` 与 `synthesizer.final_answer`。
- **Why**: 统一契约，支持自动化验证和统计。
- **Alternative considered**: 按模型自由生成 domain；被拒绝，稳定性与可观测性不足。

### Decision 3: run 响应新增 structuredResponse 字段（向后兼容）
- **Choice**: 在 `AssistantRunResponse` 中新增结构化字段，不移除 `finalText/traces`。
- **Why**: 兼容旧客户端，允许新客户端渐进启用结构化渲染。
- **Alternative considered**: 直接替换旧响应结构；被拒绝，破坏性过大。

### Decision 4: 双门禁固化为显式阶段
- **Choice**: 显式记录 `ContextAssembly -> DomainPreconditionCheck -> DomainExecution -> SynthesisReadinessCheck -> GlobalSynthesis`。
- **Why**: 满足“上下文不足先补齐、汇总不足回流补齐”的可审计闭环。
- **Alternative considered**: 仅依赖模型隐式判断；被拒绝，难以验证与定位问题。

### Decision 5: 规格统一，记录规格目录最小化
- **Choice**: `personal-assistant` 作为唯一主规格；两个记录目录仅保留迁移说明文件。
- **Why**: 消除规范分叉，降低长期维护成本。
- **Alternative considered**: 双规格长期并行；被拒绝，冲突与重复维护风险高。

## Risks / Trade-offs

- **[Risk] 模板数量增加（2+19）导致管理复杂度上升** → **Mitigation**: 统一模板命名约定、变量字典校验、模板 CI 检查。
- **[Risk] 新结构化响应引入兼容问题** → **Mitigation**: 保留旧字段，新增字段可选，灰度启用。
- **[Risk] 某些垂类（卜卦/星座/情感）存在内容安全与合规风险** → **Mitigation**: 增加 domain 风险等级与 guardrail 模板，输出强制不确定性与免责声明。
- **[Risk] 双门禁可能增加时延** → **Mitigation**: 最小上下文优先，缺失项按需补齐，设置预算与早停阈值。
- **[Risk] 灰度策略选择失误影响体验** → **Mitigation**: 按用户分层和白名单灰度，保留一键回滚模板版本能力。

## Migration Plan

1. 新增模板运行时与模板目录结构（先接入总1/总2，再接入 19 域）。  
2. 扩展协议：`AssistantRunRequest/Response` 增加设备/GPS与 structuredResponse 字段。  
3. 在 `AgentLoop` 接入模板驱动上下文组装、双门禁检查、gap fill 回流。  
4. 逐域接入 19 垂类契约与模板，先以 fallback 模板跑通，再替换域专用模板。  
5. 更新 observability：记录 templateId/version、结构化阶段字段。  
6. 规格迁移：统一写入 `personal-assistant/spec.md`，记录两规格改为合并说明。  
7. 灰度发布：先内部，再小流量，监控准确率/覆盖率/冲突率/P95/成本，异常则回滚模板版本。  

Rollback:
- 模板层回滚：切回上一个稳定 `templateVersion`；
- 功能层回滚：关闭 structuredResponse 渲染开关，继续使用旧 `finalText + traces`。

## Open Questions

- 19 垂类的一期优先级是否固定全开，还是按流量分批启用（建议分批）？
- `structuredResponse` 的字段是否需要在 stream 模式逐段输出，还是先只在非 stream 落地？
- 卜卦/星座域的默认“娱乐免责声明”文案是否由法务统一提供？
