# L3 Story：错误权限展示语义 (`error-permission-display-semantics`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为遇到错误或权限限制的用户，
我希望在页面、分身和评论等入口看到同源错误提示与可执行恢复动作，
从而知道发生了什么并能安全继续。

## 2. 范围与非目标

### In Scope

- “错误权限展示语义”的输入、可观察主路径、失败语义以及与父能力的交接。
- 页面级错误按 UiErrorSemantic.presentation 选择载体。
- 跨页面/沉浸入口失败态按 sourceAppearanceMode 保持来源外观。
- 错误组件与宿主页面/模态的导航所有权。
- 整页、区块、刷新、分页和动作失败的分层载体。
- `AppUserRecoveryGroup` 的唯一用户文案与动作合同。
- `AppRequestWaitController` 的 1.5/3/6 秒等待节奏与 `AppPageLoadArbiter` 的页面唯一裁决。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。
- 启动或运行时根级不可恢复异常页面；该页面由 `cold-start-performance` 与 `unrecoverable-runtime-recovery` 的业务栈外恢复宿主持有，不复用普通页面错误卡、诊断或重试语义。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 错误权限展示语义

- 统一错误组件、Persona 页、评论区与栈页面必须按相同 canonical error 选择展示层级和恢复动作。

<a id="req-002"></a>
### REQ-002 错误恢复不复制宿主导航

- 错误恢复不得复制或重置宿主导航；恢复成功后返回原页面上下文。

<a id="req-003"></a>
### REQ-003 表单失败按操作锚点单通道呈现

- 表单失败必须在操作锚点单通道呈现，并与共享 `UiErrorSemantic` 使用同一错误分类。

<a id="req-004"></a>
### REQ-004 播放与加载失败提供无歧义恢复或退出路径

- 媒体播放或页面加载失败必须只提供真实可用的重试、替代路径或退出动作。

<a id="req-005"></a>
### REQ-005 AuthGateReason + AuthContinuation 的统一用户语义

- `AuthGateReason` + `AuthContinuation` 的统一用户语义。
- `UiErrorSemantic` 与统一 resolver 契约。
- 视频播放失败的内联覆盖层：可恢复时只展示“重新加载”，不支持播放时展示“返回”并真实离开媒体区域。
- 整页阻塞、区块阻塞、局部软失败、刷新失败、分页失败必须选择不同载体，不得用同一灰色卡片覆盖所有失败。
- **约束**：必须使用设计系统 token（AppTypography、AppSpacing、AppColors）；文案必须来自 l10n。
- **门禁**：页面不得直接消费裸 `RuntimeFailureKind` 或手写 “加载失败/请先登录/操作失败” 作为最终页态语义。
- 沉浸式或跨页面入口的首屏错误必须保留来源 `sourceAppearanceMode`，错误页不继承错误的深色沉浸上下文。
- 聊天语音发送失败仅 status bar（`chatVoicePendingRetry`），禁止 actionDialog 叠加。
- 表单发送/提交/依赖失败在操作点附近使用 `AppFormErrorCard`，字段校验使用 `AppInlineFieldError`；二者必须复用同一透明圆形感叹号错误行，同一失败不得再叠加 Toast、dialog 或第二段弱提示。
- 错误标题只说明状态；页面名称和业务对象不得覆盖恢复组标题、说明或动作。

<a id="req-006"></a>
### REQ-006 必须完成“error-permission-display-semantics”并获得明确的成功或失败结果，且失败时不得写入成功事实

- 系统必须完成“error-permission-display-semantics”并获得明确的成功或失败结果，且失败时不得写入成功事实。

<a id="req-007"></a>
### REQ-007 列表首屏失败 / 缓存回退失败 / 分页追加失败三类语义必须区分

- 列表首屏失败 / 缓存回退失败 / 分页追加失败三类语义必须区分。

<a id="req-008"></a>
### REQ-008 JIT 麦克风权限 — 无冗余 App modal

- 同一次手势无 2+ App modal。

<a id="req-009"></a>
### REQ-009 语音发送失败 — 单一低打扰载体

- modal 与 status bar 不同时出现。

<a id="req-010"></a>
### REQ-010 权限说明与继续动作一致

- 权限说明必须解释当前阻断原因，继续按钮只能触发说明中声明的下一步动作。

<a id="req-011"></a>
### REQ-011 统一协调层：AppPermissionCoordinator + AppPermissionSurface（jit / page）

- **统一协调层**：`AppPermissionCoordinator` + `AppPermissionSurface`（`jit` / `page`）
- gate 语义：权限被拒绝时说明“当前为什么不能继续”以及“继续所需动作”。
- **统一 gate 载体**：权限态与登录门禁态共享 `AppInlineGateState` 结构，但图标、按钮和副说明由权限语义决定。

<a id="req-012"></a>
### REQ-012 页面错误只表达已确认事实，不猜测原因

- 页面必须先根据 canonical error code 归入唯一用户恢复组，再由恢复组选择标题、说明与恢复动作；未知临时失败进入 `reloadLater`，不得推断为设备离线。
- 只有系统已确认设备离线或无路由时才允许展示“网络未连接”；DNS、连接拒绝、TLS、客户端超时、5xx、可恢复响应异常和未知临时失败统一进入 `reloadLater`，同时在脱敏日志与遥测中保留原 canonical error code。
- 取消或被新请求取代的操作静默吸收，不展示错误。
- 成功空结果使用空态，不伪装成失败。
- 已有缓存时保留内容，并使用非阻断“内容未更新”提示。
- 整页错误只允许一个真实可执行的主操作；没有 handler 的动作不得显示。
- 整页错误不得显示图标、插画、诊断折叠区或技术卡片；所有 build mode 的用户 widget 与 semantics tree 均不得出现 operation、canonical error code、route、requestId、traceId、端口、内部域名、证书路径或堆栈。
- operation、canonical error code、route、surface、requestId 与 traceId 只进入脱敏日志与遥测，不得以 debug build 作为向用户界面暴露技术字段的授权边界。

<a id="req-013"></a>
### REQ-013 用户恢复组合同唯一且按可执行下一步聚类

| 恢复组 | 固定标题 | 固定说明 | 固定动作 |
|---|---|---|---|
| `connectNetwork` | 网络未连接 | 打开手机的 Wi‑Fi 或移动数据后，重新加载。 | 重新加载 |
| `reloadLater` | 暂时无法加载 | 趣我圈暂时没有响应，请稍后重新加载。 | 重新加载 |
| `loginAgain` | 需要重新登录 | 登录后，可以继续刚才的操作。 | 重新登录 |
| `enablePermission` | 需要开启权限 | 在设置中允许此权限后，返回继续。 | 去设置 |
| `waitThenReload` | 请稍等一下 | 操作有点频繁，`{n}` 秒后可以重新加载。 | 倒计时后重新加载 |
| `updateApp` | 需要更新应用 | 更新到最新版本后，可以继续使用。 | 立即更新 |
| `noAccess` | 当前不能查看 | 你的账号暂时不能查看此内容。 | 返回 |
| `contentGone` | 内容已不可用 | 内容已被删除或下架。 | 返回 |
| `contentUnavailable` | 当前内容无法使用 | 返回后，可以继续查看其他内容。 | 返回 |

- 不透明 404 只能进入 `contentUnavailable`；只有明确 tombstone、删除或下架事实才进入 `contentGone`。
- `updateApp` 只有在最低版本不满足且官方更新入口已验证时可用；普通 404 不得猜测为版本问题。
- 用户文案禁止出现 DNS、TLS、CA、证书、host、端口、HTTP、解析、连接拒绝、上游、契约、响应格式和堆栈。

<a id="req-014"></a>
### REQ-014 等待节奏与页面唯一裁决

- 缓存查找最多占前 1.5 秒。3 秒只显示“还在加载，请稍候”。页面首屏和媒体准备最迟 6 秒进入成功、空态或错误终态。
- 页面和区块使用共享低疲劳占位；视频保留同源封面，300ms 后显示紧凑进度，3 秒显示慢提示，6 秒进入恢复组终态。
- cancel、supersede、返回与 dispose 必须终止旧 generation，旧结果不得回写。
- 关键首屏无内容时只显示一个整页状态。有缓存时保留内容并显示一个非阻断提示。一个可选区块失败由区块呈现。两个以上失败由页面合并。
- 多恢复组同时失败时只显示最高优先级：`updateApp → loginAgain → enablePermission → connectNetwork → waitThenReload → reloadLater → noAccess/contentUnavailable`；页面级状态可见时隐藏子区块 loading/error。

## 4. 契约引用

- 父级设计：[`runtime-client-foundation`](../design.md)
- canonical：`quwoquan_service/services/content-service/contracts/content/post/errors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 错误权限展示语义

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“错误权限展示语义”对应的公开行为。
- THEN 页面使用与错误类别匹配的唯一载体，恢复成功后回到原上下文，无法恢复时提供明确退出路径。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-006"></a>
### GWT-006 JIT 麦克风权限无冗余 App modal

- GIVEN 用户以一次手势触发需要麦克风权限的操作。
- WHEN 权限说明或系统授权流程显示。
- THEN App 只展示一个必要的权限载体，不叠加第二个 App modal。

<a id="gwt-007"></a>
### GWT-007 语音发送失败使用单一低打扰载体

- GIVEN 语音消息发送失败。
- WHEN 页面呈现该失败。
- THEN 用户只看到可恢复的单一低打扰载体，modal 与 status bar 不同时出现。

<a id="gwt-008"></a>
### GWT-008 权限说明与继续动作一致

- GIVEN 页面显示权限 primer。
- WHEN 用户阅读说明并选择继续。
- THEN 文案解释当前阻断原因，继续动作只触发说明声明的下一步。

<a id="gwt-009"></a>
### GWT-009 页面加载错误不猜测原因并提供真实恢复动作

- GIVEN 首页首屏、缓存回退、分页追加或页面切换期间发生 canonical failure。
- WHEN 页面解析并呈现该失败。
- THEN 标题、说明与唯一恢复动作均由 canonical error code 对应的用户恢复组决定，未知失败不得猜测为网络原因，技术诊断只在脱敏日志与遥测中保留原 canonical error code。
- AND 取消操作不展示错误、成功空结果只展示空态、缓存回退不遮挡已有内容。

<a id="gwt-013"></a>
### GWT-013 同一恢复组在全 App 使用完全相同语义

- GIVEN 首页、主页、搜索、聊天或视频书收到不同 canonical failure。
- WHEN 这些失败映射到同一 `AppUserRecoveryGroup`。
- THEN 标题、说明、动作与 copyKey 完全相同，页面不得按业务对象改写。
- AND 任意 build mode 的用户 widget 与 semantics tree 均不包含错误图标、插画或 operation/errorCode/route/requestId/traceId。
- AND 不透明 404 不显示“已删除”，普通连接失败不显示“网络未连接”。

<a id="gwt-014"></a>
### GWT-014 页面和视频在统一预算内进入唯一终态

- GIVEN 页面关键首屏、两个可选区块或视频播放器正在取数和初始化。
- WHEN 请求到达 300ms、3 秒或 6 秒节点，或被取消、替换、返回与释放。
- THEN 只显示当前范围允许的一个等待或错误状态，6 秒内进入终态，旧 generation 不回写，媒体槽位被释放。
- AND 两个以上区块失败时页面只显示一个最高优先级恢复组提示。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-003"></a>
### OPEN-003 JIT 麦克风权限 — 无冗余 App modal

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：同一次手势无 2+ App modal。
- 完成判定：`GWT-006` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 语音发送失败 — 单一低打扰载体

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：modal 与 status bar 不同时出现。
- 完成判定：`GWT-007` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-005"></a>
### OPEN-005 Page L2 primer 文案与继续按钮一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：verify_permission_primer_copy.py 通过。
- 完成判定：`GWT-008` 对应行为满足且真实测试 `spec_ref` 有效。
