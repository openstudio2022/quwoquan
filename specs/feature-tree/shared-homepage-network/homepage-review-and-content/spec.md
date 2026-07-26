# L2 Business Capability：主页评价与内容聚合 (`homepage-review-and-content`)

> 所属领域：[`shared-homepage-network`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让用户围绕共享主页完成理解、比较、浏览内容、查看评价与继续贡献内容。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“homepage-review-and-content-journey”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-009`](../../spec.md#scn-009)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：让用户围绕共享主页完成理解、比较、浏览内容、查看评价与继续贡献内容。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`homepage-content-and-question-aggregation`](./homepage-content-and-question-aggregation/spec.md)：记录/讨论聚合四态齐备且点击回流埋点在。
- [`homepage-contextual-publish-entry`](./homepage-contextual-publish-entry/spec.md)：主页内入口与全局创作入口产出同一挂载语义。
- [`homepage-overview-and-module-shell`](./homepage-overview-and-module-shell/spec.md)：用户可见文案禁止出现“实体”，按具体类型或对象名表达，例如 `大学 · 北京海淀`、`认识清华大学`、`大家在聊清华大学`；兜底使用“这个主页”。
- [`homepage-review-read-and-score-summary`](./homepage-review-read-and-score-summary/spec.md)：五个 operation（create/update/delete/list/mine）在 alpha mock 与 remote 行为同构且全部 per-op commercial ready。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 主页评价与内容聚合能力组合结果

- 本能力必须组合直属 Story 与公开契约，交付“用户围绕共享主页完成理解、比较、内容浏览、评价与上下文创作”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 主页首屏必须在不滚动或少量滚动内回答“这是什么、值不值得看、我接下来能做什么”

- 主页首屏必须在不滚动或少量滚动内回答“这是什么、值不值得看、我接下来能做什么”。
- 主页模块必须独立加载和独立降级，单模块失败不影响其它模块渲染。
- 从主页进入发布时，当前主页必须自动作为默认上下文带入。
- baseline 不保留旧的主页碎片卡片并行治理，应统一收口到主页模块骨架。

## 6. 契约与依赖

- 上游能力：[`shared-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 homepage review and content journey 能力 SIT

- GIVEN 执行“homepage review and content journey 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“homepage review and content journey 能力”对应动作。
- THEN 直属 Story 共同交付“用户围绕共享主页完成理解、比较、内容浏览、评价与上下文创作”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 homepage review and content journey 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：用户围绕共享主页完成理解、比较、内容浏览、评价与上下文创作。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
