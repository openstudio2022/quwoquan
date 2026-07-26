# L2 Business Capability：运行时助手 (`runtime-assistant`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“runtime-assistant”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-009 / SCN-017`](../../spec.md#scn-017)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-018`](../../spec.md#scn-018)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-009 / SCN-020`](../../spec.md#scn-020)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`assistant-mentioned-consumer`](./assistant-mentioned-consumer/spec.md)：处理失败进入 DLQ 可重放；小趣被移除成员后 ack-and-drop。
- [`context-grounded-answering`](./context-grounded-answering/spec.md)：上下文过期/缺失时降级为通用回答且不伪造事实。
- [`proactive-subscription-delivery`](./proactive-subscription-delivery/spec.md)：仅 active 订阅经用户策略、静默、consent、频控、成员身份与 Redis lease 门控投递；失败复用稳定 deliveryId 补偿。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime assistant 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 QA Runner 过程抽屉必须保留最终答案生成阶段叙事

- QA Runner 过程抽屉必须保留最终答案生成阶段叙事；检索引用列表视觉上只展示编号标题，保留点击跳转能力，不展示裸 URL。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime assistant 能力 SIT

- GIVEN 执行“runtime assistant 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime assistant 能力”对应动作。
- THEN 直属 Story 共同交付“SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime assistant 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：SuggestedActionsGenerator：根据 PageContext + 内容分析 + 画像，按 8 种页面场景生成差异化建议操作。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
