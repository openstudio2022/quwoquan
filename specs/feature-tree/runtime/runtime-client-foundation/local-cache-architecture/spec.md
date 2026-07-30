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

- feed 与 userPosts 共用持久化 ContentQuerySnapshotStore，清理临时资源不删除 post metadata，离线内容清理可删除 query snapshot。
- snapshot 按 viewer/query identity 保存有界首屏与续接窗口、cursor、版本和鲜度；内存、磁盘数量与持久化 UTF-8 wire bytes 均有硬预算。
- snapshot 在 5 分钟内为 fresh，之后仅以 stale-while-revalidate 回显；最大可恢复年龄为 24 小时，超过后读取与磁盘恢复都必须主动删除，不得跨日回放旧排序。
- 持久化只按完整 snapshot 页追加；单页超过 item 或剩余 byte 预算时不得截断 items 后保留跳跃 cursor，feed 只恢复从首屏 cursor 连续可达的页链。
- 总预算竞争时优先保留最近首页 feed 的连续页链；独立 userPosts 超限不得阻断首页首屏。并发更新只能由单活跃写入合并并最终落下最新快照，旧写不得晚到覆盖新状态。

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

- Post projection、feed cursor 与归因字段只引用 content-service 的 [`content/post/fields.yaml`](../../../../../quwoquan_service/services/content-service/contracts/content/post/fields.yaml) 和 [`content/post/operations.yaml`](../../../../../quwoquan_service/services/content-service/contracts/content/post/operations.yaml)。
- QuerySnapshot 是上述 canonical 读模型的端侧可重建派生缓存，不另建字段台账或第二套 wire schema。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 QuerySnapshot 短退重启与频道切换复用

- GIVEN 用户已浏览首页推荐、精品或个人作品第一页，ContentRepository 已写入 query snapshot。
- WHEN 用户频道切换、回滑、短退重启，或在 profile works 区再次打开已看内容列表。
- THEN 端侧先回显 snapshot 中的 post 文本、作者快照、互动计数与 cursor，再后台刷新；命中 fresh snapshot 时不重复请求远端。
- AND 无网络时从持久 snapshot 还原有界首屏与可执行重试；恢复网络后使用同一 query identity 执行 stale-while-revalidate，不把旧数据伪装为 fresh。
- AND 长滚动不会使内存/磁盘 snapshot 无界增长，精确 UTF-8 持久 payload 不超过硬上限，窗口裁剪后仍保留完整页、cursor、顺序和跨页去重语义。
- AND 无关 surface 的超大 snapshot 不饿死首页首屏，多次 put/clear/invalidate 并发到达时持久层最终等于最新内存状态且同时最多一个写入。

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
- 影响或价值：仍缺单个 snapshot 内字段级 canonical byte 上限和真机磁盘压力下的预算定标。expired snapshot 已按 24 小时最大可恢复年龄在读取与磁盘恢复时主动清退，整页编码也已改为无输出预算预检后逐字段/逐 item 写入，避免物化整页 Map/List 与局部 JSON String。完整页原子持久化、连续 feed 页链与总 UTF-8 wire byte 硬限已有本地合同，但不得把有界总 payload 冒充字段 owner 与真机证据已关闭。
- 完成判定：`GWT-001` 对应 fresh/stale/expired、无网络重启、窗口续填、主动 LRU/TTL、单页字段预算和真机磁盘压力证据全部通过
