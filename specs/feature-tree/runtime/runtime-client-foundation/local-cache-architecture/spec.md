# L3 Story：本地对象缓存架构（local-cache-architecture） (`local-cache-architecture`)

> 所属能力：[`runtime-client-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-004](../design.md#dec-004)、[L2 DEC-007](../design.md#dec-007)

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
- snapshot 年龄以可验证时钟计算，时钟倒退或年龄无法证明时不得延长有效期；年龄小于 5 分钟为 fresh，安全范围仍有效时直接返回且不等待 blocked-keywords 等远端前置，也不重复远端读取。之后只可显式 stale 展示；最大年龄严格小于 24 小时，年龄等于或超过 24 小时即失效并主动清退，磁盘恢复与 resident 读取使用同一边界。fresh 不豁免已知撤回、权限失效或版本失效。
- 实际持久化与恢复路径必须保真保留已验证内容身份、混合对象卡锚点、页面顺序与完整页链；不能只让测试 codec 保存字段。沿用现有数量与 UTF-8 byte 硬预算，不扩大页数、对象数或预下载范围。
- 在线无网冷启动只能恢复同一已验证 target/environment、source、audience/principal 和内容摘要下的 last-confirmed 历史身份，不能从磁盘猜当前 active release。仅 public 内容且同 scope 的本地 visibility/permission 策略仍有效时可回放，缺任一证明保持不可回放。
- 持久化只按完整 snapshot 页追加；单页超过 item 或剩余 byte 预算时不得截断 items 后保留跳跃 cursor，feed 只恢复从首屏 cursor 连续可达的页链。
- 总预算竞争时优先保留最近首页 feed 的连续页链；独立 userPosts 超限不得阻断首页首屏。并发更新只能由单活跃写入合并并最终落下最新快照，旧写不得晚到覆盖新状态。

<a id="req-002"></a>
### REQ-002 定义统一 CacheReadResult<T> 输出合同

- 定义统一 `CacheReadResult<T>` 输出合同。
- 定义业务对象特性树必须补齐的缓存规格与验收项。
- 过期、已删除/撤回、权限不可证明、内容身份或完整性无效时不展示旧值，并撤出已可见 items；返回 canonical 失败或安全空态，不把它当作命中。
- stale fallback 仅允许可确定的网络/连接超时、5xx 或 429，且仍满足同 scope/public/本地策略/最大年龄约束并明确标记历史。caller 取消、总 deadline 耗尽、401/403、协议/contract 或 digest 校验失败禁止 fallback，并撤出受影响可见 items；不能用宽泛 catch 掩盖失败。

<a id="req-003"></a>
### REQ-003 网络图片统一加载与缓存

- 业务组件不得直接调用 `Image.network`、`NetworkImage` 或第三方 `CachedNetworkImage`；内容图统一使用 `AppCachedNetworkImage` 的 `thumbnail / cover / inline / full` preset，头像统一使用 `AppAvatarImage` 或 `AppCircularAvatar`。
- 统一入口必须处理 canonical 候选 URL、解码尺寸、磁盘缓存分层、失败负缓存、占位/失败状态和媒体加载观测；禁止用 allowlist 长期保留旁路。

<a id="req-004"></a>
### REQ-004 同安装的上下文隔离与有界恢复

- 持久 namespace 固定绑定已验证 target 与 environment，再隔离 source、principal/audience 和内容身份；同为 prod 的 prod-sim 与 prod-hosted 不共享 token、配置或缓存。同 authority 的有效配置刷新不更换授权 namespace、不无故注销；无可证明来源的历史 token 不发送到任一环境，需重新认证。
- installId 保持安装级，不因切环境重新生成，也不赋予或恢复账号授权。切换环境/source/principal/release 时取消旧请求、播放器和 outbox flush、失效 resident、cursor、session 与 feedRequestId；旧成功、失败、下载及持久化 completion 均不得回写新上下文，包括 A→B→A。
- 详情对象及其 resident 副本最大年龄均严格小于 24 小时，年龄等于上限即失效；不能由 QuerySnapshot 的 freshness 自动延长。运营配置 LKG 按已验证 target 隔离，并以 [`app-remote-config` REQ-004](../app-remote-config/spec.md#req-004) 的已验证快照最大年龄判断；年龄等于或超过其上限即失效，未声明或无法验证最大年龄不得用于放行展示；媒体文件与短签 grant 分别验证完整性、许可与有效期，不继承元数据缓存命中。
- Alpha 制品内快照不是在线 stale 缓存，不受在线 24 小时窗口限制，只消费可离线再分发的公开许可；永久离线不能承诺服务器即时撤权。其 source identity 不得冒充服务端 active release。

## 4. 契约引用

- Post projection、feed cursor 与归因字段只引用 content-service 的 [`content/post/fields.yaml`](../../../../../quwoquan_service/services/content-service/contracts/content/post/fields.yaml) 和 [`content/post/operations.yaml`](../../../../../quwoquan_service/services/content-service/contracts/content/post/operations.yaml)。
- QuerySnapshot 是上述 canonical 读模型的端侧可重建派生缓存，不另建字段台账或第二套 wire schema。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 QuerySnapshot 短退重启与频道切换复用

- GIVEN 用户已浏览首页推荐、精品或个人作品第一页，已有同 scope 的持久 query snapshot，拟回放内容为 public 且本地 visibility/permission 与最大年龄仍有效。
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

<a id="gwt-003"></a>
### GWT-003 历史读取不跨授权上下文且迟到结果不回写

- GIVEN 同一安装先后使用不同已验证 target，持久缓存中有公开/受限内容及有效/过期策略，且旧请求被延迟完成。
- WHEN 无网冷启动、刷新配置、发生可恢复或不可恢复失败，或执行 A→B→A 环境/账号/内容切换。
- THEN 仅同 target/environment/source/principal/内容身份下且本地策略有效的 public 历史可显式 stale 展示；fresh 小于 5 分钟不请求远端，详情与 snapshot 年龄等于或超过 24 小时即撤出，运营 LKG、媒体与 grant 独立过期。
- THEN 仅确定 network/timeout、5xx、429 可尝试上述 fallback；取消、总 deadline 耗尽、401/403、contract/digest 失败撤出受影响可见 items，不生成成功事实。
- THEN 实际磁盘重启保留 activation identity、对象卡锚点及完整连续页链，仍满足既有数量和 byte 预算；旧 completion 不改变新上下文，prod-sim/prod-hosted token 不互发，同 authority 配置刷新保留登录，installId 不恢复授权。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-007](../design.md#dec-007)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 QuerySnapshot 短退重启与频道切换复用

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺单个 snapshot 内字段级 canonical byte 上限和真机磁盘压力下的预算定标。expired snapshot 已按 24 小时最大可恢复年龄在读取与磁盘恢复时主动清退，整页编码也已改为无输出预算预检后逐字段/逐 item 写入，避免物化整页 Map/List 与局部 JSON String。完整页原子持久化、连续 feed 页链与总 UTF-8 wire byte 硬限已有本地合同，但不得把有界总 payload 冒充字段 owner 与真机证据已关闭。
- 完成判定：`GWT-001` 对应 fresh/stale/expired、无网络重启、窗口续填、主动 LRU/TTL、单页字段预算和真机磁盘压力证据全部通过

<a id="open-002"></a>
### OPEN-002 安全历史恢复与上下文切换尚缺实际持久层证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：last-confirmed 身份恢复、target 授权 namespace、context epoch 防 ABA、详情/resident 截止边界与运营 LKG 最大年龄尚未形成同一实现闭环；现有 codec 或内存命中不能证明磁盘重启保留 activation/cards，也不能证明无远端策略前置。
- 完成判定：`GWT-003` 的每个结果由实际 persistence/restart、可控时钟/取消/延迟 completion 的 local_contract，真实 HTTP 错误分类的 api_integration，以及设备断网/切环境 user_acceptance 绑定；必须证明运营 LKG 实际使用 canonical 快照的有限最大年龄，而非仅解码该字段或无期限回放。
- 依赖：账户存储、配置 LKG 与内容缓存 owner 共用已验证 target 和上下文失效协议；详情、媒体/grant 的独立预算保持有效。
