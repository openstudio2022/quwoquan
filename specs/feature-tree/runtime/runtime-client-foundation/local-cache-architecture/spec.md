# L3 Story：本地对象缓存架构（local-cache-architecture） (`local-cache-architecture`)

> 所属能力：[`runtime-client-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望建立一套端云一体的对象级缓存架构，覆盖 `UserProfile`、`Post`、`Conversation`、`Comment`、媒体资源与查询快照，确保页面能复用统一缓存输出、离线可回显、弱网不闪空、滚动不重复请求，并通过对象版本与出站队列实现最终一致，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- QuerySnapshot 持久化与 stale-while-revalidate 命中
- Post/User 最小对象快照复用
- 图片 preset 入口与媒体缓存轻量本地优先
- 快速滑动下视频单活跃与资源预取抑制

### Out of Scope

- 完整离线视频平台
- 预测式大规模预下载
- 业务 UI 内平台分支

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 QuerySnapshot 短退重启与频道切换复用

- feed 与 userPosts 共用 ContentQuerySnapshotStore，清理临时资源不删除 post metadata，离线内容清理可删除 query snapshot。

<a id="req-002"></a>
### REQ-002 定义统一 CacheReadResult<T> 输出合同

- 定义统一 `CacheReadResult<T>` 输出合同。
- 定义业务对象特性树必须补齐的缓存规格与验收项。
- `expired`：可展示骨架或旧值，但必须触发刷新。

<a id="req-003"></a>
### REQ-003 网络图片统一加载与缓存

- 业务组件不得直接调用 `Image.network`、`NetworkImage` 或第三方 `CachedNetworkImage`；内容图统一使用 `AppCachedNetworkImage` 的 `thumbnail / cover / inline / full` preset，头像统一使用 `AppAvatarImage` 或 `AppCircularAvatar`。
- 统一入口必须处理 canonical 候选 URL、解码尺寸、磁盘缓存分层、失败负缓存、占位/失败状态和媒体加载观测；禁止用 allowlist 长期保留旁路。

## 4. 契约引用

- canonical：`object-cache-policy.yaml#objects.QuerySnapshot`
- canonical：`object-cache-policy.yaml#objects.Post`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 QuerySnapshot 短退重启与频道切换复用

- GIVEN 用户已浏览首页推荐、精品或个人作品第一页，ContentRepository 已写入 query snapshot。
- WHEN 用户频道切换、回滑、短退重启，或在 profile works 区再次打开已看内容列表。
- THEN 端侧先回显 snapshot 中的 post 文本、作者快照、互动计数与 cursor，再后台刷新；命中 fresh snapshot 时不重复请求远端。

<a id="gwt-002"></a>
### GWT-002 网络图片只经统一入口加载

- GIVEN App 页面需要显示头像、封面、缩略图或正文图片。
- WHEN 图片 URL 有效、为空、加载中或最终失败。
- THEN 统一图片组件按用途选择缓存 preset，并返回稳定图片或本地占位/失败状态，同时记录加载结果。
- AND 全量源码扫描不存在统一组件之外的直接网络图片 API，也不存在对应过渡 allowlist。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 QuerySnapshot 短退重启与频道切换复用

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：feed 与 userPosts 共用 ContentQuerySnapshotStore，清理临时资源不删除 post metadata，离线内容清理可删除 query snapshot。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效
