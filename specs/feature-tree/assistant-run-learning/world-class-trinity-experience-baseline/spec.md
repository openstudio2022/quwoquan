# L2 Business Capability：小趣统一体验 (`world-class-trinity-experience-baseline`)

> 所属领域：[`assistant-run-learning`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“world-class-trinity-experience-baseline”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-009 / SCN-017`](../../spec.md#scn-017)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注提供一致的小趣体验，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story


- [`session-preference-memory-control`](./session-preference-memory-control/spec.md)：结构化文风偏好的即时注入、可见、遗忘与撤销恢复。
- [`native-tool-calling-model-routing`](./native-tool-calling-model-routing/spec.md)：以提供方原生工具调用协议选择工具，并按运行阶段与问题类型路由模型档位及降级。
- [`tool-fabric-runtime`](./tool-fabric-runtime/spec.md)：统一执行工具的时限、重试、循环检测与失败恢复，并保证策略允许工具真实可用。
- [`skill-progressive-disclosure-routing`](./skill-progressive-disclosure-routing/spec.md)：在策略允许集合内选择领域技能，并按需加载技能提示正文。
- [`planner-aggregation-orchestration`](./planner-aggregation-orchestration/spec.md)：决定下一步动作含向用户反问，统一单技能与多技能编排并裁决答案边界。
- [`context-assembly-slot-filling`](./context-assembly-slot-filling/spec.md)：运行前装配授权后的上下文与槽位状态，并以统一渠道声明约束公开场合记忆边界。
- [`long-term-memory-compaction`](./long-term-memory-compaction/spec.md)：记录可撤销的事实型长期记忆，并以滚动摘要压缩长会话历史。
- [`trajectory-replay-evaluation-gate`](./trajectory-replay-evaluation-gate/spec.md)：以覆盖全部技能的可重复轨迹回放阻断工具、澄清、引用和答案边界的静默回归。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 小趣统一体验能力组合结果

- 本能力必须组合直属 Story 与公开契约，交付“以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注提供一致的小趣体验”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 OpenClaw 类实现：统一 `run / runStream / skills / invoke` 能力面，远端优先，具备流式事件和渠道互操作能力

- **OpenClaw 类实现**：统一 `run / runStream / skills / invoke` 能力面，远端优先，具备流式事件和渠道互操作能力。
- 统一能力面，而不是本地/远端/渠道各说一套协议。
- Tool Fabric 和安全守卫在模型之外统一治理。
- 不把兜底能力做成低质模板回复，fallback 也必须是高水准通用能力。
- 第三方 Skill 商店化运营与全端统一 UI 不属于本能力范围。
- 明确正式编排面，统一以 `skillRuns[]` 执行单 skill 与多 skill 问题：
- 明确聚合面，新增 `AggregationState` 统一判断：
- `Tool Fabric`：统一工具元数据、参数 schema、权限、预算、结果截断、循环检测。
- `CapabilityGateway`：统一 `localOnly / remotePreferred / hybrid`，并对齐 `run / runStream / skills / invoke` 能力面。
- 统一本地和远端的结果质量门控，远端不满足商用品质时稳定回退。

## 6. 契约与依赖

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 world class trinity experience baseline 能力 SIT

- GIVEN 执行“world class trinity experience baseline 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“world class trinity experience baseline 能力”对应动作。
- THEN 直属 Story 共同交付“以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注提供一致的小趣体验”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 world class trinity experience baseline 能力 SIT

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：`SIT-001` 已由 local contract、API integration 与 user acceptance 三层真实测试直接 `spec_ref`；gamma-local 仍需受保护的 DNS-01 账号与令牌完成公开 TLS 装配，缺失时不得绕过门禁启动环境或把未执行旅程包装为通过。
- 完成判定：受控环境注入 gamma-local DNS-01 输入后，通过 `stackctl up/health/inspect` 建立完整第一方拓扑，并执行 assistant API integration 与真实 Remote user acceptance 旅程。
