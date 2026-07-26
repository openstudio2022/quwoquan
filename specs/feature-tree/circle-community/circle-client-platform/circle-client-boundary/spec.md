# L3 Story：圈子端侧数据边界 (`circle-client-boundary`)

> 所属能力：[圈子端侧平台](../spec.md)
>
> Journey / Scenario：[`JNY-008 / SCN-014`](../../../spec.md#scn-014)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为圈子成员，我希望页面始终展示同一份服务端圈子、成员与动态事实，并在网络失败时看到明确恢复方式，从而避免不同页面状态互相漂移。

## 2. 范围与非目标

### In Scope

- 页面只经 typed Repository 读取圈子、成员与动态；缓存仅保存已确认快照。
- Remote 模式失败时保持错误或已有数据，不切回 Mock 伪成功。

### Out of Scope

- circle-service 的聚合规则与圈子页面视觉改版。

## 3. 行为要求

### REQ-001 单一端侧数据源

- 同一登录主体的圈子详情、成员列表和动态必须来自同一 Repository 模式；切换主体或环境时旧状态必须失效。

## 4. 契约引用

- operation：`quwoquan_service/services/circle-service/contracts/circle_management/circle/operations.yaml`
- membership：`quwoquan_service/services/circle-service/contracts/circle_management/circle_membership/operations.yaml`

## 5. 验收场景

### GWT-001 Remote 失败不回退 Mock

- GIVEN App 运行于 Remote 模式且已展示一份服务端确认的圈子快照。
- WHEN 后续成员或动态请求失败。
- THEN 页面保留可识别的已有快照并展示恢复动作，不注入 Mock 成员、动态或成功提示。

## 6. 依赖

- 前置要求：父能力的 Repository 与状态容器边界。
- 上游事实：circle-service 的圈子和成员投影。
- 下游结果：一致页面状态或结构化失败。
- 父级设计：`DEC-001`

## 7. 开放事项

### OPEN-001 端侧模式隔离证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺直接绑定本节点的 Remote/Mock 隔离测试。
- 完成判定：`GWT-001` 在 provider/widget local_contract 中有直接 `spec_ref`。
