# L3 Story：创作模式与界面信息架构统一 (`creation-mode-and-surface-ia-unification`)

> 所属能力：[`content-type-framework`](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者，我希望从统一创作入口进入文字或互斥的照片/视频编辑器，并在顶栏看到可恢复的草稿保存状态，从而以一致心智完成内容创建与发布。

## 2. 范围与非目标

### In Scope

- 创作首层三动作菜单、社交动作保留与媒体编辑器双编辑器心智。
- 照片入口、视频入口、旧相机兼容和图片/视频真实结果分流。
- 图片路径承载一键成片、图片编辑与图片创作三段一致性；视频路径不暴露一键成片。
- 编辑器顶栏草稿入口、保存状态、本地草稿页、自动保存、继续编辑与清稿时机统一。

### Out of Scope

- 重做图片编辑器内部工具。
- 新增外部分享 SDK。
- 新增 metadata 字段。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 加号入口保留创作与社交动作并按真实媒体结果分流

- 用户只需要在入口选择开始动作，系统能根据真实媒体结果进入图片或视频编辑状态，且发布 payload 的 `contentType` 与最终媒体类型一致。

<a id="req-002"></a>
### REQ-002 编辑器顶栏草稿入口与保存状态可靠反映本地草稿

- 用户能从同一本地草稿入口恢复三类草稿，并且保存/清除时机与退出确认语义一致，不出现误清稿或旧状态覆盖新状态。

<a id="req-003"></a>
### REQ-003 `添加联系人`、`发起群聊`、`创建圈子` 作为第二个无标题列表组保留在移动端 `+` 面板内

- `添加联系人`、`发起群聊`、`创建圈子` 作为第二个无标题列表组保留在移动端 `+` 面板内；不得退回图标宫格或使用 `加联系`、`建圈子` 等缩写。
- 同一路由体系可保留现有 `create-entry` / `create` 路由 ID，但用户可见心智统一为“双编辑器”。
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
- canonical：`quwoquan_app/lib/content/media/media_upload_session/presentation/create_media_picker_page.dart`
- canonical：`quwoquan_app/lib/components/media/camera/camera_capture_page.dart`
- canonical：`quwoquan_app/lib/content/content/post/presentation/create_page.dart`
- canonical：`quwoquan_app/lib/content/content/post/domain/create_editor_models.dart`
- canonical：`quwoquan_app/lib/content/content/post/adapters/create_draft_local_storage.dart`
- canonical：`quwoquan_app/lib/core/auth/auth_gate.dart`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 加号入口保留创作与社交动作并按真实媒体结果分流

- GIVEN 用户从底栏或发现页全局 `+` 打开创作入口。
- GIVEN 设备相册和相机权限可用，且相册内同时存在图片和视频。
- WHEN 用户查看入口 sheet，并分别点击“发布照片”“发布视频”“写文字”以及三条社交动作。
- WHEN 用户在照片或视频入口中选择/拍摄图片或视频。
- THEN 移动端入口显示 `发布照片`、`发布视频`、`写文字`、`添加联系人`、`发起群聊`、`创建圈子` 与 `取消`。
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

## 6. 依赖

- 前置要求：[`content-type-framework`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
