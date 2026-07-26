# L2 Business Capability：主页发现与挂载 (`homepage-discovery-and-attach`)

> 所属领域：[`shared-homepage-network`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让用户发现具体事物的主页，并在发布内容时以单一引用把内容挂接到该主页。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“homepage-discovery-and-attach-journey”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-009`](../../spec.md#scn-009)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：让用户发现具体事物的主页，并在发布内容时以单一引用把内容挂接到该主页。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`homepage-attach-in-publish-flow`](./homepage-attach-in-publish-flow/spec.md)：两个入口产生的挂载字段与回流聚合语义一致。
- [`homepage-entry-and-preview`](./homepage-entry-and-preview/spec.md)：入口断裂为零：六类入口全部可达 homepageDetail 且埋点带 referralSource。
- [`homepage-search-and-picker`](./homepage-search-and-picker/spec.md)：picker 页 loading/error/empty/populated 四态齐备且选择结果可回填。
- [`missing-homepage-suggestion-and-review`](./missing-homepage-suggestion-and-review/spec.md)：幂等接收用户建议，并保证候选在审核发布前不可公开发现。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 主页发现与挂载能力组合结果

- 本能力必须组合直属 Story 与公开契约，交付“用户发现具体事物主页并在发布内容时挂载 canonical 主页引用”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 口碑内容必须先选主页的强约束

- 口碑内容必须先选主页的强约束。
- 前台统一使用“主页”和具体类目名，不对用户显示“实体”。
- 主页搜索结果必须提供足够的区分信息，避免同名主页造成误挂载。
- `口碑` 必须且只能绑定 1 个主主页。
- 全局发布入口与主页内发布入口必须共用同一套发布页，只改变默认上下文。
- 补充主页成功提交后，用户必须能回到原发布链路，不允许丢失当前编辑上下文。
- 主页搜索、主页详情路由、发布上下文与请求头 page context 必须以 metadata 为唯一真相源。
- 用户补充主页后，记录进入 `candidate / pending_verify`，审核通过前不能作为正式主页公开展示。
- 口碑因依附主页存在，若未选主页则不得发布成功。
- 主页详情加载失败时，用户仍应可以回到结果列表或发布器，不能卡死在中间页。

## 6. 契约与依赖

- 上游能力：[`shared-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 homepage discovery and attach journey 能力 SIT

- GIVEN 执行“homepage discovery and attach journey 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“homepage discovery and attach journey 能力”对应动作。
- THEN 直属 Story 共同交付“用户发现具体事物主页并在发布内容时挂载 canonical 主页引用”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 homepage discovery and attach journey 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：用户发现具体事物主页并在发布内容时挂载 canonical 主页引用。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
