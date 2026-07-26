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


- [`session-preference-memory-control`](./session-preference-memory-control/spec.md)：服务与 App local_contract 通过。

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

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注提供一致的小趣体验。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
