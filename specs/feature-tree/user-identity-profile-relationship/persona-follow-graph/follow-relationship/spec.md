# L3 Story：关注关系 (`follow-relationship`)

> 所属能力：[`persona-follow-graph`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望owner 不能作为默认 follow 主体参与社交关系建立，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “关注关系”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 关注关系

- owner 不能作为默认 follow 主体参与社交关系建立。

<a id="req-002"></a>
### REQ-002 follow / unfollow 的命令主体必须是当前 active persona 或显式选择的 persona

- follow / unfollow 的命令主体必须是当前 active persona 或显式选择的 persona。
- owner 不能作为默认 follow 主体参与社交关系建立。
- follow 边的 `followerId / followeeId` 语义必须统一映射到 `ProfileSubject` 级别，而不是漂移在 owner/user 级别。
- 重复 follow 必须幂等，不得重复计数。
- unfollow 不存在的边应当是安全 no-op 或明确可恢复错误，不允许破坏计数。
- 如果 `BlockEdge` 表示任一方向的强屏蔽，follow 写入必须被拒绝或无效化，具体语义由 user 域统一定义。
- follow 写入侧不能绕过 `BlockEdge` 直接落边。
- follow 写入成功与否，不得泄露不应暴露的屏蔽细节。
- 平台审计可追踪 follow 命令与分身主体；普通读接口不得反推出 owner 映射。
- user 域之外不得复制 follow 写入契约。

<a id="req-003"></a>
### REQ-003 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 关注关系

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“关注关系”对应的公开行为。
- THEN owner 不能作为默认 follow 主体参与社交关系建立。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`persona-follow-graph`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
