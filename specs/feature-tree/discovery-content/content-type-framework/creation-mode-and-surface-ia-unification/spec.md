# L3 Story：创作模式与界面信息架构统一 (`creation-mode-and-surface-ia-unification`)

> 所属能力：[`content-type-framework`](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)、[`JNY-011 / SCN-027`](../../../spec.md#scn-027)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为想把兴趣表达为内容、活动或会话的用户，我希望 C 位首层只看到“发内容 / 发起活动 / 发起群聊”三个并列选择，并在选择具体动作后进入各自唯一流程；作为内容创作者，我仍能在“发内容”二级入口进入文字或互斥的照片/视频编辑器，并获得可靠草稿状态。

## 2. 范围与非目标

### In Scope

- C 位与 Web 创建工作台首层“发内容 / 发起活动 / 发起群聊”三动作，以及底栏与 `create-entry` 深链的同一 gated handler。
- “发内容”二级照片/视频/文字动作、媒体编辑器双编辑器心智与草稿状态。
- “发起活动”进入唯一 Gathering composer 并自动 provision 活动群聊；“发起群聊”只进入普通群聊创建。
- 游客先看动作面板，选择具体动作才触发登录 continuation；关闭回安全来源且不循环，成功续接原动作。
- 照片入口、视频入口、旧相机兼容和图片/视频真实结果分流。
- 图片路径承载一键成片、图片编辑与图片创作三段一致性；视频路径不暴露一键成片。
- 编辑器顶栏草稿入口、保存状态、本地草稿页、自动保存、继续编辑与清稿时机统一。

### Out of Scope

- 重做图片编辑器内部工具。
- 新增外部分享 SDK。
- 在本规格复制或临时发明 route/surface/action ID；缺失 canonical contracts/metadata 时保持 OPEN，不以代码字符串先行。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 C 位首层固定为发内容、发起活动、发起群聊

- 移动端 C 位与 Web 创建工作台首层只显示“发内容 / 发起活动 / 发起群聊”；活动与群聊必须并列且互不合并。
- “发内容”二级显示照片、视频、文字并进入既有内容创作；系统根据真实媒体结果进入图片或视频编辑状态，最终发布类型与真实媒体一致。
- “发起活动”进入 Circle owner 的统一 Gathering composer，成功后使用该 Gathering 的唯一 contextual room；“发起群聊”只创建 Chat owner 的普通 Conversation，不创建 Gathering。
- 添加联系人、创建圈子等动作回到各自上下文入口，不占 C 位首层。

<a id="req-002"></a>
### REQ-002 编辑器顶栏草稿入口与保存状态可靠反映本地草稿

- 用户能从同一本地草稿入口恢复三类草稿，并且保存/清除时机与退出确认语义一致，不出现误清稿或旧状态覆盖新状态。

<a id="req-003"></a>
### REQ-003 三条具体动作共用无循环登录 continuation

- 游客打开 C 位或 `create-entry` 深链时先看到三动作面板；只有选择“发内容 / 发起活动 / 发起群聊”具体动作才触发登录。
- 关闭登录必须回到不会再次触发登录门的安全来源；登录成功必须续接用户刚选定的内容编辑器、Gathering composer 或普通群聊创建，不得丢失 typed prefill context。
- 底栏 C 位、Web 创建工作台与 `create-entry` 深链必须复用同一 gated handler；缺失 route/surface/action contract 时不得用本地字符串、裸建群或错误内容页伪承接。
- 活动与普通群聊互不转换：已有会话仅可作为 Gathering 来源，原成员仍需成功响应才进入活动群聊。
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
### GWT-001 C 位三动作与内容二级分流

- GIVEN 用户从底栏或发现页全局 `+` 打开创作入口。
- GIVEN 设备相册和相机权限可用，且相册内同时存在图片和视频。
- WHEN 用户查看入口 sheet，分别点击“发内容”“发起活动”“发起群聊”，并在发内容二级入口选择照片、视频或文字。
- WHEN 用户在照片或视频入口中选择/拍摄图片或视频。
- THEN 首层只显示 `发内容`、`发起活动`、`发起群聊` 与 `取消`，活动与群聊并列且不互相创建。
- THEN `发内容` 二级显示 `发布照片`、`发布视频` 与 `写文字`；添加联系人、创建圈子不在首层。
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
- THEN 本地草稿页每次进入或 App 恢复时 reload 当前登录用户 scope；从底栏加号真实链路保存的草稿不得落到游客或其他用户 scope。
- THEN 只有当草稿发生编辑变化时才进入自动保存；dirty 状态下最多每 10 秒自动保存一次。
- THEN 切到相册、相机、图片编辑、视频编辑、位置、圈子、发布确认等子页面，或创作页失焦 / App 退后台时，会立即保存一次当前草稿。
- THEN 关闭创作页时弹出“是否保存草稿”确认：保存=写回最新状态，放弃=清除当前草稿，取消=继续编辑且不清稿。

<a id="gwt-003"></a>
### GWT-003 游客先看面板并续接准确动作

- GIVEN 游客分别从底栏 C 位、Web 创建工作台或 `create-entry` 深链打开全局发起面板。
- WHEN 游客选择任一具体动作后关闭登录，再次 pump；随后重新选择并完成登录。
- THEN 关闭后回到安全来源且不再次弹登录，三个入口行为一致。
- THEN 登录成功准确续接原内容编辑器、Gathering composer 或普通群聊创建，并保留 typed prefill context。
- AND 发起活动不退化为普通建群，发起群聊不创建 Gathering。

## 6. 依赖

- 前置要求：[`content-type-framework`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 C 位 Gathering 动作与登录续接尚未准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前实现仍以照片/视频/文字和添加联系人/群聊/圈子六项为首层，尚缺统一 Gathering composer、活动与群聊并列语义、三入口共用 gated handler、具体动作 continuation，以及所需 canonical route/surface/action contracts。
- 完成判定：`GWT-001`、`GWT-003` 由 Widget/local_contract 与 production Remote user_acceptance 直接覆盖；关闭登录后再 pump 不循环，登录成功进入准确目标，活动不退化裸建群。
- 依赖：[`gathering-coordination`](../../../circle-community/gathering-coordination/spec.md) 与后续 contracts/metadata 准入；本次 M0 不编辑 metadata、contracts 或代码。
