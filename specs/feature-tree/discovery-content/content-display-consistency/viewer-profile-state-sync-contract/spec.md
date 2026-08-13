# L3 Story：浏览器与作者主页状态同步 (`viewer-profile-state-sync-contract`)

> 所属能力：[`content-display-consistency`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为在内容与作者主页间切换的用户，
我希望让关注、拉黑和互动状态通过统一关系投影即时同步，
从而返回任一页面时都看到一致且已确认的关系状态。

## 2. 范围与非目标

### In Scope

- “浏览器与作者主页状态同步”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 浏览器与作者主页状态同步

- 必须消费 `owner-persona-homepage-unification` 定义的 canonical `RelationshipCapabilityView` 关系矩阵。

<a id="req-002"></a>
### REQ-002 viewer、profile、feed 同时 watch 统一 provider

- viewer、profile、feed 同时 watch 统一 provider。
- 必须消费 `owner-persona-homepage-unification` 定义的 canonical `RelationshipCapabilityView` 关系矩阵。
- 关系态必须用对象真相源驱动，而不是页面局部状态拼装。
- 网络写回必须与 UI 即时反馈分层。
- 端侧待同步状态只持久化 `desiredBoolValue + confirmedBoolValue` 的 canonical outbox entry；禁止读取 `needsRemoteSync`、guard-only 旧形态或通过缺失字段反推确认态，非法记录必须失效清除且不得发出远程写入。
- outbox 自动重试期间的瞬时失败保持静默，不打扰用户。
- entry 首次入队时间超过 `maxPendingAge` 必须进入终态失败：放弃重试并移除 entry、回滚乐观布尔态到已确认值（计数由权威投影下次刷新收敛）、发布可订阅的终态失败信号。
- 终态失败必须以统一恢复语义的警示轻提示告知用户，文案来自恢复组，不新增字面量。
- feed/详情读投影携带 viewer 维度 `viewerLiked`（`content_post_projection.yaml` / `content_post_detail_slice.yaml`）：true/false 为服务端权威值，`null` 表示本次响应
  未附着 viewer 态（匿名请求或附着降级），端侧不得据 `null` 回滚本地状态。
- App 以权威投影 hydrate 本地点赞态时，仍有待同步 like 意图的 post 由本地 pending
  意图优先；计数无条件采纳权威值。附着降级不阻断内容主路径。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 浏览器与作者主页状态同步

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“浏览器与作者主页状态同步”对应的公开行为。
- THEN viewer、profile 与 feed 消费同一 canonical `RelationshipCapabilityView` 关系矩阵。
- AND 同一交互的本地 outbox 只存在一份 canonical entry；旧字段或错误 JSON 类型不会被迁移成待同步命令。
- AND feed/详情响应的 `viewerLiked` 权威值 hydrate 本地点赞态；`null` 不回滚本地态，
  待同步 like 意图优先于权威投影。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`content-display-consistency`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

- 无。
