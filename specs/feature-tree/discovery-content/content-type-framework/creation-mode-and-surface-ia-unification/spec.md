# L3 Story：创作模式与界面信息架构统一 (`creation-mode-and-surface-ia-unification`)

> 所属能力：[`content-type-framework`](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)、[`JNY-011 / SCN-027`](../../../spec.md#scn-027)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为想表达兴趣的用户，我希望 C 位优先进入照片、视频、文字等内容创作，其他社交创建只在次级“更多”中按上下文出现，并且不提供无上下文 Gathering；当内容中的交集证据给出可兑现下一步时，再进入唯一 Gathering composer。

## 2. 范围与非目标

### In Scope

- C 位与 Web 创建工作台首层只承载内容创作，直接展示照片、视频、文字等现有内容动作；底栏与 `create-entry` 深链复用同一 gated handler。
- 其他社交创建可放在次级“更多”，但不得包含无内容/交集上下文的 Gathering；普通群聊继续由 Chat owner 的上下文入口创建。
- Gathering composer 只由内容交集证据半屏中的 canonical `start_gathering` hint、邀请/通知、再约一次或合法任务深链进入。
- 游客先进入具体内容编辑器并完成选材与编辑；只有在实际发布或选择把草稿保存到账号时才触发登录 continuation，关闭登录回原编辑器且不循环，成功续接原发布或保存动作。
- 照片入口、视频入口、旧相机兼容和图片/视频真实结果分流。
- 图片路径承载一键成片、图片编辑与图片创作三段一致性；视频路径不暴露一键成片。
- 编辑器顶栏草稿入口、保存状态、本地草稿页、自动保存、继续编辑与清稿时机统一。

### Out of Scope

- 重做图片编辑器内部工具。
- 新增外部分享 SDK。
- 在本规格复制或临时发明 route/surface/action ID；缺失 canonical contracts/metadata 时保持 OPEN，不以代码字符串先行。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 C 位首层固定为内容创作

- 移动端 C 位与 Web 创建工作台首层直接显示照片、视频、文字等内容创作动作，不显示“发起活动”。
- 照片、视频、文字进入既有内容创作；系统根据真实媒体结果进入图片或视频编辑状态，最终发布类型与真实媒体一致。
- 普通群聊、添加联系人、创建圈子等动作回到各自上下文入口或次级“更多”，不占 C 位首层；次级入口也不得提供无上下文 Gathering。
- Gathering composer 继续是 Circle owner 的唯一创建页，但只承接内容交集、邀请/通知、再约一次和合法任务深链，不由全局 C 位直接曝光。

<a id="req-002"></a>
### REQ-002 编辑器顶栏草稿入口与保存状态可靠反映本地草稿

- 用户能从同一本地草稿入口恢复三类草稿，并且保存/清除时机与退出确认语义一致，不出现误清稿或旧状态覆盖新状态。

<a id="req-003"></a>
### REQ-003 内容创作末端共用无循环登录 continuation

- 游客打开 C 位、Web 创建工作台或 `create-entry` 深链时先看到内容创作动作，并可进入照片、视频或文字编辑器完成选材、编辑、滤镜与排版；进入编辑器和本地媒体处理不得触发登录。
- 登录门只允许出现在实际发布提交前，以及游客退出时显式选择“登录并保存草稿”后；发布登录成功必须自动续接原发布动作，保存登录成功必须把原草稿保存到当前账号并关闭编辑器。
- 游客编辑中的草稿可以在当前设备匿名 actor scope 内临时自动保存用于崩溃恢复；登录成功后必须以同一草稿 identity 并入当前账号 scope，确认账号副本可读后再删除匿名副本，迁移失败不得丢失任一可恢复副本。
- 游客退出有内容的编辑器时必须选择“登录并保存草稿 / 不保存直接退出 / 取消”；不保存直接退出必须清除临时草稿，取消必须留在编辑器。
- 关闭发布或保存草稿登录页必须回到原编辑器并保留全部编辑状态，不得自动重触发登录；登录成功必须续接触发登录的准确末端动作，不得丢失 typed prefill context。
- 底栏 C 位、Web 创建工作台与 `create-entry` 深链必须复用同一免登录创作 handler；缺失 route/surface/action contract 时不得用本地字符串、裸建群或错误内容页伪承接。
- Gathering 与普通群聊互不转换：已有会话仅可作为 Gathering 来源，原成员仍需成功响应才进入活动群聊；其创建入口不因此回到 C 位。
- 用户可见内容创作心智统一为“双编辑器”。
- 图片与视频互斥，不能共存。
- 用户取消照片/视频选择或相机且编辑器没有任何内容时，创作页必须关闭并回到来源页，不保留空白草稿。
- 视频发布子流程：视频选择页复用图片选择页的深色三列宫格结构，第 1 格固定为 `拍视频`，其余格展示 `全部视频`；不得展示 `一键成片`，也不得复用图片选择器的 `一键成片` / `下一步(n)` 语义误导用户。
- 图片与视频进入编辑状态后仍保持互斥；切换类型只能发生在草稿态，且必须通过“删空当前媒体后选择另一类”的显式动作完成。
- 图片 flow 顶部主标题固定为 `图片创作`；该标题使用浅色页面统一主导航标题语义，不在首屏以弱透明度淡化。
- 图片列表（创作页网格、图片选择器已选条、图片编辑器缩略条）统一复用 `MediaReorderableView`；拖拽悬停到目标槽位时，其余项必须即时前移/后移空出目标位，松手后才提交最终顺序。
- 路由切换、媒体继续追加、删除后改类型等操作不得造成草稿结构性损坏
- 编辑器顶栏初始空白态右侧显示 `草稿`，点击进入统一的**本地草稿页**；入口 sheet 不再展示草稿行

## 4. 契约引用

- canonical：`specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md`
- canonical：`quwoquan_app/lib/service/content_service/media/media_upload_session/presentation/create_media_picker_page.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/media_upload_session/presentation/camera_capture_page.dart`
- canonical：`quwoquan_app/lib/service/content_service/content/post/presentation/create_page.dart`
- canonical：`quwoquan_app/lib/service/content_service/content/post/domain/create_editor_models.dart`
- canonical：`quwoquan_app/lib/service/content_service/content/post/adapters/create_draft_local_storage.dart`
- canonical：`quwoquan_app/lib/runtime/auth/auth_gate.dart`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 C 位内容创作分流

- GIVEN 用户从底栏或发现页全局 `+` 打开创作入口。
- GIVEN 设备相册和相机权限可用，且相册内同时存在图片和视频。
- WHEN 用户查看入口 sheet，并选择照片、视频或文字。
- WHEN 用户在照片或视频入口中选择/拍摄图片或视频。
- THEN 首层直接显示 `发布照片`、`发布视频`、`写文字` 与 `取消`，不显示 `发起活动`。
- THEN 添加联系人、创建圈子与普通群聊不在首层；任何“更多”入口也不包含无上下文 Gathering。
- THEN `发布照片` 副文案固定为 `从相册选照片或拍照`。
- THEN `发布视频` 副文案固定为 `从相册选视频或拍视频`。
- THEN 入口不显示发布/互动分组标题、图标、旧宫格、社交入口缩写或草稿行。
- THEN `/create?type=gallery` 打开图片选择器，允许从相册选照片或拍照，返回图片编辑状态。
- THEN `/create?type=video` 打开视频选择器，允许从相册选视频或拍视频，返回视频编辑状态。
- THEN `/create?type=capture` 仅作为旧相机/深链兼容入口，默认拍照且同页可切到录像；拍照返回图片编辑状态，录像返回视频编辑状态。
- THEN `/create?type=write` 直接进入文字为主编辑器。

<a id="gwt-002"></a>
### GWT-002 编辑器顶栏草稿入口与保存状态可靠反映本地草稿

- GIVEN 用户已通过创作入口产生至少一条图片、视频或长文草稿，且草稿仍保存在当前设备。
- GIVEN 本地草稿可能完整，也可能只剩标题、配文或部分媒体引用。
- WHEN 用户从底栏 `+` 进入任一编辑器，未编辑时点击顶栏 `草稿`，进入本地草稿页并选择任一草稿继续编辑。
- WHEN 用户在创作页内继续编辑、切到子页面、切后台、关闭创作页或发布内容。
- THEN 入口 sheet 不显示草稿行；编辑器顶栏初始空白态显示 `草稿` 并进入全屏本地草稿页。
- THEN 发生编辑后，顶栏从 `草稿` 变为 `保存中...`、`已保存` 或 `保存失败，点按重试`；保存失败可点按重试。
- THEN `已保存` 只能在写入成功并 reload 校验 payload 与索引均可读后出现。
- THEN 本地草稿页按最近更新时间倒序展示草稿卡片，卡片能区分图片、视频、长文；图片/视频缺素材时仍保留原类型并显示占位。
- THEN 本地草稿页每次进入或 App 恢复时 reload 当前 actor scope；游客草稿只允许在当前设备匿名 actor scope 内作为临时崩溃恢复副本，登录续接后以同一草稿 identity 并入当前账号 scope，确认账号副本可读后再删除匿名副本，且不得落到其他用户 scope。
- THEN 只有当草稿发生编辑变化时才进入自动保存；dirty 状态下最多每 10 秒自动保存一次。
- THEN 切到相册、相机、图片编辑、视频编辑、位置、圈子、发布确认等子页面，或创作页失焦 / App 退后台时，会立即保存一次当前草稿。
- THEN 已登录用户关闭有内容的创作页时弹出“是否保存草稿”确认：保存=写回最新状态，放弃=清除当前草稿，取消=继续编辑且不清稿。
- THEN 游客关闭有内容的创作页时弹出“登录并保存草稿 / 不保存直接退出 / 取消”：登录成功=保存到当前账号并关闭，关闭登录=回原编辑器且不循环，不保存直接退出=清除临时草稿并关闭，取消=继续编辑且不清稿。

<a id="gwt-003"></a>
### GWT-003 游客完成编辑后才登录并续接准确末端动作

- GIVEN 游客分别从底栏 C 位、Web 创建工作台或 `create-entry` 深链打开创作面板，并选择照片、视频或文字。
- WHEN 游客在不登录的情况下完成选材与编辑，点击发布并关闭登录，再次 pump；随后再次点击发布并完成登录。
- THEN 三个入口均直接进入准确编辑器，进入编辑器、选图、选视频、相机、滤镜和排版过程不触发登录。
- THEN 关闭发布登录后回到原编辑器，全部编辑状态保留且不再次弹登录；登录成功后准确续接并自动完成原发布动作。
- WHEN 游客退出有内容的编辑器，分别选择登录并保存草稿、不保存直接退出和取消。
- THEN 登录并保存完成后，匿名临时草稿以同一 identity 并入当前账号 scope、可从草稿页读取且编辑器关闭；关闭登录回原编辑器且不循环。
- THEN 不保存直接退出清除匿名临时草稿并关闭；取消保留编辑状态并停留在编辑器。
- AND 面板全程不出现无上下文 Gathering，普通群聊不创建 Gathering。

## 6. 依赖

- 前置要求：[`content-type-framework`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 C 位内容动作与登录续接尚未准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前实现仍可能在首层或次级入口混入无上下文 Gathering，尚缺移动/Web/create-entry 三入口同源的免登录编辑、发布/保存草稿末端 continuation 与真实 UAT。
- 完成判定：`GWT-001`、`GWT-003` 由 Widget/local_contract 与 production Remote user_acceptance 直接覆盖；游客可完成三类编辑，关闭末端登录后回原编辑器且不循环，登录成功准确续接发布或账号草稿保存，C 位与次级入口均无无上下文 Gathering。
- 依赖：[`gathering-coordination`](../../../circle-community/gathering-coordination/spec.md) 与后续 contracts/metadata 准入。

<a id="open-002"></a>
### OPEN-002 游客临时草稿并入账号 scope 与退出语义尚未准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`GWT-002` 新增游客本地临时草稿、登录后同 identity 并入账号 scope，以及游客退出三分支语义；当前尚缺实现和直接测试证据。
- 完成判定：`GWT-002` 的游客 scope 并入、源副本安全删除、迁移失败保留、登录并保存、不保存退出与取消分支均由 local_contract 和真实设备 user_acceptance 直接覆盖。
- 依赖：账号登录完成后的 active Persona identity、设备本地草稿存储和 `post-login-landing` continuation。
