# L3 Story：内容创建更新 (`post-create-update`)

> 所属能力：[`publish-comment-reaction`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望从拍摄得到的图片可进入图片选择器底部缩略条或创作编辑器图片列表，并参与排序、编辑和发布，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “内容创建更新”的输入、可观察主路径、失败语义以及与父能力的交接。
- 图片作品从相册选择、拍摄、编辑、排序、完成回填到发布的端侧主链路。
- 图片发布远端媒体上传、完成、绑定、发布与展示回读契约。
- 全局照片/视频入口按发布目标进入图片或视频发布子流程，最终 payload 语义互斥。
- 视频作品从相册选择、拍摄、选封面、完成回填到发布的端侧主链路。
- 视频封面字段、封面策略、远端发布 payload 与发布后 feed 回读契约。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 内容创建更新

- 从拍摄得到的图片可进入图片选择器底部缩略条或创作编辑器图片列表，并参与排序、编辑和发布。

<a id="req-002"></a>
### REQ-002 图片拍摄为高保黑色拍照确认流并统一进图片编辑页

- 从拍摄得到的图片可进入图片选择器底部缩略条或创作编辑器图片列表，并参与排序、编辑和发布。

<a id="req-003"></a>
### REQ-003 图片发布以本地草稿和一次性 PublishIntent 可靠提交

- 草稿必须自动保存；显式放弃后不得恢复，崩溃重启后可恢复未放弃草稿。
- 同一 `PublishIntent` 在并发重复或响应丢失后最多创建一个 Post，并返回原回执。
- 发布恢复成功后无需用户再次点击，页面直接进入发布结果并可回读内容。
- 尚未被服务端接受的发布意图被取消时，未完成上传必须先完成权威 abort 对账，已完成且未被 Post 引用的 MediaAsset 必须经 owner 命令逻辑删除并由耐久 worker 回收对象；任一步未确认都必须保留本地任务继续恢复。

<a id="req-004"></a>
### REQ-004 视频选择与拍摄进入深色视频选封面主链路

- 相册视频与拍摄视频均能进入统一视频编辑状态，包含 `videoPath`、`durationMs` 和默认封面候选。

<a id="req-005"></a>
### REQ-005 视频选封面与一次性 PublishIntent 使用同源远端封面契约

- Mock 与 Remote 必须使用同一视频 payload；远端创建与回读必须保留同一视频与封面身份。

<a id="req-006"></a>
### REQ-006 数据工程视频导入与用户上传视频使用同一封面展示契约

- 数据工程导入视频与用户上传视频必须生成同一展示契约，App 不得按来源维护第二套字段。

<a id="req-007"></a>
### REQ-007 建立四类内容（微趣/美图/视频/文章）统一创作与发布契约，补齐端云发布链路

- 建立四类内容（微趣/美图/视频/文章）统一创作与发布契约，补齐端云发布链路。
- 支持作者在发布后变更圈子分发关系（追加/移除），但内容本体不可修改（仅允许删除）。
- 图片与视频必须在选择结果、编辑页和发布 payload 上保持互斥：一键成片属于图片路径，完成后仍进入图片创作壳；视频路径不得展示一键成片或复用图片下一步按钮语义。
- 用户可见文案必须来自 `UITextConstants` 或 l10n；新增中文不得散落在页面实现中。
- 底部缩略条仅在有选中图片时出现，按添加顺序展示。
- 内容不足一屏时也必须从左起始，不得呈现视觉居中。
- 每张缩略图可点叉删除，也可拖动调整顺序。
- 顶部右侧提供“草稿箱”，点击进入本地草稿恢复列表；恢复后的图片顺序、编辑后路径和创作状态必须回到当前图片发布子流程。
- 图片编辑页返回图片选择器时，必须携带完整图片顺序和编辑后路径；图片编辑页点击 `下一步` 时，必须把同一份最新顺序和编辑状态传入图片创作页。
- 创作页进入图片 flow 时，顶部主标题固定为 `图片创作`，并使用浅色页面统一主导航标题语义；首屏标题不再以 34% 透明度弱化显示。
- 创作页图片网格、图片选择器底部缩略条、图片编辑器底部缩略条必须共用同一拖拽几何真相源：拖到第 N 位时，目标区间内图片在悬停阶段即时移位并空出目标槽位，松手后才提交最终顺序。
- 图片 flow 触达的标题/提示文案优先收口到 `CreatePageText` / `UITextConstants`，不得在页面实现里继续散落硬编码中文。

<a id="req-008"></a>
### REQ-008 Alpha 包只包含远端单轨发布链路

- Alpha 包不得包含发布 Mock、内存仓储或绕过 canonical API 的备用入口。

<a id="req-009"></a>
### REQ-009 权限、错误、主题与断点不改变位置选择业务语义

- 发布成功后必须进入明确结果面；失败时保留用户输入，并提供与错误语义一致的恢复动作。

<a id="req-010"></a>
### REQ-010 该能力需被微趣、图片、视频、文章四类发布流程统一复用

- 该能力需被微趣、图片、视频、文章四类发布流程统一复用。
- 位置选择统一通过云侧 `integration-service` 获取（不直连地图 SDK），支持默认附近位置与地名搜索。
- 若地图服务不可用，必须允许用户回退为“不显示位置”继续发布；限流场景端侧静默保持最近成功结果。
- 圈子列表是公开发布的可选分发设置；查询不可用时发布确认页必须明确显示
  “圈子暂不可用”，记录结构化异常并允许用户不选圈子继续发布，禁止未捕获异常或伪造圈子。
- 图标与高品质内容创作定位匹配：是否公开、发布到圈子入口采用统一风格的图标。
- **iOS 交互语义**：选择器页面统一 `CupertinoPageScaffold + CupertinoNavigationBar`，Modal 一律使用 `xmark` 关闭语义；Cupertino 页面禁止混用 Material 交互组件（如 Checkbox、SnackBar）。

<a id="req-011"></a>
### REQ-011 内容创建、媒体发布与发布后回读保持同一结果语义

- 图片与视频作品必须经同一内容创建、媒体发布和发布后回读链路；全局照片入口、视频入口与相机兼容入口必须返回同构结果，失败时不得写入成功事实。

<a id="req-012"></a>
### REQ-012 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_app/lib/components/media/picker/create_media_picker_page.dart`
- canonical：`quwoquan_app/lib/core/services/media_picker_service.dart`
- canonical：`quwoquan_app/lib/ui/content/entry/pages/create_page.dart`
- canonical：`quwoquan_app/lib/components/media/camera/camera_capture_page.dart`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`
- canonical：`quwoquan_app/lib/cloud/services/content/content_repository.dart`
- canonical：`quwoquan_app/lib/ui/content/entry/services/create_page_remote_helpers.dart`
- canonical：`quwoquan_app/lib/ui/content/entry/pages/video_editor_page.dart`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/fields.yaml`
- canonical：`quwoquan_app/lib/ui/content/entry/providers/create_editor_provider.dart`
- canonical：`quwoquan_data/schema/content/post_manifest.schema.json`
- canonical：`quwoquan_data/scripts/content/release/canonical/gate.py`
- canonical：`quwoquan_service/services/content-service/cmd/import/main.go`
- canonical：`quwoquan_service/services/integration-service/contracts/external_integration/location/operations.yaml`
- canonical：`quwoquan_service/services/integration-service/contracts/external_integration/location/errors.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml`
- 协作规格：[`error-permission-display-semantics`](../../../runtime/runtime-client-foundation/error-permission-display-semantics/spec.md)
- canonical：`quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 内容创建更新

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“内容创建更新”对应的公开行为。
- THEN 从拍摄得到的图片可进入图片选择器底部缩略条或创作编辑器图片列表，并参与排序、编辑和发布。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-003"></a>
### GWT-003 图片发布以本地草稿和一次性 PublishIntent 可靠提交

- GIVEN 用户编辑图片并产生可恢复的本地草稿。
- WHEN 用户提交、重放提交或在响应丢失后恢复发布。
- THEN 同一 PublishIntent 至多创建一个 Post，放弃的草稿不恢复，成功结果可直接回读。
- AND 取消未受理意图时，上传 session 与已完成 MediaAsset 均到达权威 aborted/discarded 终态后才移除本地任务，重复或丢响应不泄漏对象。

<a id="gwt-004"></a>
### GWT-004 视频选择与拍摄进入深色视频选封面主链路

- GIVEN 用户从相册选择或拍摄视频。
- WHEN 视频进入创作编辑流程。
- THEN 页面使用统一视频编辑状态，包含 videoPath、durationMs 与默认封面候选。

<a id="gwt-005"></a>
### GWT-005 视频选封面与一次性 PublishIntent 使用同源远端封面契约

- GIVEN 用户为视频选择封面并发起发布。
- WHEN Mock 或 Remote 创建并回读内容。
- THEN 两条路径使用同形 payload，且回读保留同一视频与封面身份。

<a id="gwt-006"></a>
### GWT-006 数据工程视频导入与用户上传视频使用同一封面展示契约

- GIVEN 数据工程导入视频和用户上传视频进入展示链路。
- WHEN App 读取两类内容。
- THEN 两者使用同一封面展示契约，且页面不按来源维护第二套字段。

<a id="gwt-007"></a>
### GWT-007 App 只经 generated operation client 读取附近位置与搜索结果

- GIVEN 用户在创作页读取附近位置或搜索结果。
- WHEN App 发起位置查询。
- THEN 请求仅经生成的 operation client 访问云侧 integration-service，并在不可用时保留可继续发布的恢复路径。

<a id="gwt-008"></a>
### GWT-008 可选圈子查询不可用不阻断公开发布

- GIVEN 用户发布公开内容，且圈子列表 query 暂时不可用。
- WHEN 用户打开发布确认页并不选择圈子。
- THEN 页面显示明确的圈子不可用状态，仍可确认发布且提交空 circleIds。
- AND 失败被结构化记录，不出现未捕获异常、空白页或本地伪造圈子。

## 6. 依赖

- 前置要求：[`publish-comment-reaction`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 图片选择器达到商用品质的深色 iOS 图片发布体验

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：图片选择器可把当前顺序图片带入图片编辑页；图片编辑页返回选择器或点击底部“下一步”进入创作页时，该顺序与底部缩略条悬停后的最终顺序一致。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-008"></a>
### OPEN-008 场景化创作模板与提示词

- 类型：`future_plan`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：校园经验、路线记录、住宿反馈、地点打卡、对象评价和圈内问答缺少可选择模板，首次创作者仍需从空白页开始。
- 完成判定：6 类模板通过 metadata/config 单源下发，选择率与发布转化事件可观测，未选择模板仍可正常创作。
- 依赖：content config metadata 与 event catalog。

<a id="open-002"></a>
### OPEN-002 图片发布以本地草稿和一次性 PublishIntent 可靠提交

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：local_contract 证明自动保存、显式放弃、单 intent 和崩溃恢复。
- api_integration 证明并发重复/响应丢失均只创建一个 Post。
- user_acceptance 证明用户无需再次点击即可完成发布与回读。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 视频选择与拍摄进入深色视频选封面主链路

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：相册视频与拍摄视频均能进入统一视频编辑状态，包含 `videoPath`、`durationMs` 和默认封面候选。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 视频选封面与一次性 PublishIntent 使用同源远端封面契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：Mock/Remote 的视频 payload 形态在 local contract 对齐，Remote/API 在 api_integration 证明创建与回读闭环。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-005"></a>
### OPEN-005 数据工程视频导入与用户上传视频使用同一封面展示契约

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：数据工程 schema/gate、服务 importer local contract 与端云 api_integration 能证明导入视频和用户上传视频使用同一展示契约。
- 完成判定：`GWT-006` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-006"></a>
### OPEN-006 App 只经 generated operation client 读取附近位置与搜索结果

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：local_contract、api_integration 与 alpha package contract 均通过。
- 完成判定：`GWT-007` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-007"></a>
### OPEN-007 内容创建更新 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“内容创建更新”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
