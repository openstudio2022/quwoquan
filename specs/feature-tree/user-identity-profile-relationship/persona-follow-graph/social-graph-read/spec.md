# L3 Story：社交图谱读取 (`social-graph-read`)

> 所属能力：[`persona-follow-graph`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “社交图谱读取”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 社交图谱读取

- 分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。

<a id="req-002"></a>
### REQ-002 分页主键与排序必须围绕 FollowEdge.createdAt 或等价稳定游标

- 分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。
- 公开读取必须遵守分身可见性与 block 过滤规则。
- 被 block 或 strict isolation 的主体，在列表与能力读取中必须使用一致的不可见或受限语义。
- 列表分页不能因为过滤而串页或重复页。
- 关系能力读取不得泄露超出产品允许范围的 block 事实。
- 内部可以基于 owner 审计映射做治理，但对外列表不得暴露 owner 关联。
- 分身停用后，其记录 follow 图谱如何继续公开展示，必须服从 `persona-profile-subject-and-visibility` 的公开可见性合同。

<a id="req-003"></a>
### REQ-003 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-004"></a>
### REQ-004 资料页社交统计、关系列表与私信入口必须由公开对象能力组合

- 关注数、粉丝数、圈子数及其分页列表必须从各 owning object 的具名 reader/public seam 读取，不得在 presentation 或 runtime shell 拼接私有 store、adapter 或派生计数。
- 列表页必须使用稳定 cursor；重复页、过滤后的空洞与局部失败不得被包装成“没有关系”。
- 关注、取关等关系动作必须经 `persona_relationship` command；从资料统计页发起私信只能经 `chat.conversation` 的公开 command 创建或复用会话，不得直写聊天投影。
- 单一区块失败不得清空其他已成功区块；动作失败必须保留动作前关系态与可重试入口。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 社交图谱读取

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“社交图谱读取”对应的公开行为。
- THEN 分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 资料统计页分页读取关系与圈子并从公开命令发起关系动作或私信

- GIVEN 查看者以 production Remote composition 打开真实用户资料统计页，目标具备可读的关注、粉丝和圈子事实。
- WHEN App 分别经 owning object 的公开 reader 加载计数与分页列表，并按 relationship capability 发起关注或取关。
- WHEN 查看者从目标资料页发起私信，App 只经 `chat.conversation` 公开 command 创建或复用会话，再导航到 canonical conversation。
- THEN 各列表使用稳定 cursor、无重复或串页，且 block、visibility 与 persona isolation 过滤在统计和明细中一致。
- AND 任一区块失败只显示该区块的 canonical recovery，不得把失败包装为空列表或清空其他成功区块。
- AND 关系命令或私信命令失败时保留动作前状态与重试入口；只有 production Remote 读回收敛后才更新最终关系态或进入会话。
- AND 只有绑定同一 candidate、真实 Provider 与 production Remote 的 Android 物理设备及 iPhone 物理设备 `ReadinessResultBundle` 均通过时，本验收场景才计通过；Widget、模拟器、动态 skip 或 typed double 不计。

## 6. 依赖

- 前置要求：[`persona-follow-graph`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 社交图谱读取 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明 `GWT-001` 的稳定分页语义与 `GWT-002` 的多区块 Remote 组合、关系动作、私信跳转和失败恢复均满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 与 `GWT-002` 均有职责匹配的真实 production runner 与逐场景 `spec_ref`；`GWT-002` 还必须取得绑定同一 candidate 的 Android 与 iPhone 物理设备 `ReadinessResultBundle`，failed、blocked、skipped、模拟器或测试 double 结果均不计通过。
