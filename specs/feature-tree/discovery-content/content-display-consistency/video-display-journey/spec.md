# L3 Story：video-display-journey（视频旅程） (`video-display-journey`)

> 所属能力：[`content-display-consistency`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望**视频独立旅程**：视频频道 / 首页混合流 → 视频未播放封面 → 视频沉浸式浏览器 → 作者详情，端到端数据源一致、交互状态跨页面同步、重入状态保持。与图片旅程模式一致，按 category=video 隔离，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- 首页混合流、视频频道、通用视频卡、作品浏览器的视频未播放封面展示。
- `thumbnailUrl` 优先、同源 `coverUrl` 回退、点击后进入真实视频播放的展示合同。
- 用户上传视频与数据工程导入视频在 feed/read model 中使用同一封面合同。
- 关注、点赞、收藏、评论数、转发数和重入状态在列表、浏览器、作者详情间同步。

### Out of Scope

- 首页端侧运行时临时抽帧。
- 视频转码、加音乐、特效、美颜、剪辑能力本身。
- 商用全矩阵 beta/gamma/prod 非 dry-run 设备报告；该证据归 runtime-media 矩阵。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 视频未播放态展示同源封面并点击后播放

- 首页/视频频道/作品浏览器的同一视频 post 未播放态封面一致，点击后能进入同一 `videoUrl` 的播放态。

<a id="req-002"></a>
### REQ-002 视频 feed、沉浸浏览器与作者详情状态一致

- 四环境 composition 仅通过同一组 typed Remote Query/Command port 同步与恢复状态；测试 double 只存在测试树，不维护 runner fixture、运行时 Mock/Remote 切换或页面级第二状态源。

<a id="req-003"></a>
### REQ-003 数据工程导入视频与用户上传视频展示合同一致

- 列表视频与沉浸式视频必须通过同一 DTO/read model 展示标题、媒体、作者与交集事实。

<a id="req-004"></a>
### REQ-004 两种视频 profile 共享会话状态、P0 时间轴与独立拖动增强

- 两种 profile 的控制层只能消费 `PlaybackSnapshot`；seek、首帧与暂停状态不得从 Widget 局部推断。
- compact、regular 与 expanded 视口必须保持文本和控制区不碰撞，并在文字缩放、评论重绑、过滤恢复和媒体重排后保持同一媒体身份。

<a id="req-005"></a>
### REQ-005 约束：production Remote-only 与 Alpha/test 隔离

- **约束**：四环境 production composition、runner 与 UAT support 不得提供 Mock/Remote 切换或 fixture override；对象级 typed double 只存在测试树。
- 按 category=video 隔离，不与图片混用
- 不得把 `videoUrl` 当图片 URL 交给 image loader
- 首页、通用视频卡、作品浏览器、沉浸式浏览器首帧态必须消费同一封面优先级，不允许使用无关 seed 图、作者头像、地点图、视频 URL 或端侧运行时临时抽帧。
- 数据工程导入视频与用户上传视频使用同一展示合同，不能通过入口差异维护第二套封面字段。
- 封面展示、点击播放、错误恢复和停留/互动行为必须具备 `referralSource` / `feedRequestId` / trace 传递，支撑推荐与运营分析。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/discovery_feed.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/video_post.yaml`
- canonical：`quwoquan_app/lib/ui/discovery/widgets/home_multi_form_feed_media_grid.dart`
- canonical：`quwoquan_app/lib/components/media/video/player/video_player_widget.dart`
- canonical：`quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer.dart`
- canonical：`quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_canvas.dart`
- canonical：`quwoquan_app/lib/ui/content/comments/providers/comment_provider.dart`
- canonical：`quwoquan_data/schema/content/post_manifest.schema.json`
- canonical：`quwoquan_service/services/content-service/cmd/import/main.go`
- canonical：`quwoquan_app/lib/cloud/runtime/models/content_post_view_data.dart`
- canonical：`quwoquan_app/lib/components/media/video/player/video_playback_session.dart`
- canonical：`quwoquan_app/lib/ui/discovery/widgets/works_immersive_viewer_controls.dart`
- canonical：`specs/feature-tree/runtime/runtime-media/design.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 视频未播放态展示同源封面并点击后播放

- GIVEN 发现流或视频频道返回至少一个 `contentType=video` 的 post。
- GIVEN 该 post 包含 `videoUrl`，并包含 `thumbnailUrl` 或同源 `coverUrl`。
- WHEN 用户打开首页混合流、视频频道或作品浏览器，看到视频未播放态，并点击视频进入播放。
- THEN 未播放态优先展示 `thumbnailUrl`，缺失时只回退到同一 post/media asset 的 `coverUrl`。
- THEN UI 不把 `videoUrl` 当图片 URL 交给 image loader，也不使用无关 seed 图、作者头像或地点图作为封面。
- THEN 视频播放器初始化成功后从封面切换到真实视频画面，并能提供 ready/首帧状态证据；只出现页面节点不构成播放成功。
- THEN 初始化失败时保留同源封面。可恢复失败展示准确的消费者主文案、副文案和“重试”；内容不可用时展示消费者说明且不提供无效重试。
- THEN 用户可见界面不展示证书、CA、DNS、CDN、host、端口、HTTP 状态码、环境名或原始异常文本；内部失败类别仅进入结构化无 PII 观测。
- THEN 点击播放携带 `referralSource`、`feedRequestId` 或等效 trace，上报进入与播放行为。

<a id="gwt-002"></a>
### GWT-002 视频 feed、沉浸浏览器与作者详情状态一致

- GIVEN 用户在视频频道或首页打开一个视频 post，并进入视频沉浸式浏览器。
- GIVEN 该视频 post 具备作者、关注、点赞、收藏、评论数和转发数等互动状态。
- WHEN 用户在视频沉浸式浏览器点赞、收藏、关注作者，进入作者详情后再返回。
- THEN 视频频道、首页卡片、沉浸浏览器和作者详情展示同一 post 与作者状态。
- THEN 关注、点赞、收藏状态跨页面同步；作者详情关注变更返回后浏览器展示同步更新。
- THEN 左右滑动顺序与视频频道 feed 一致，滑动到底按同一数据源加载更多。

<a id="gwt-003"></a>
### GWT-003 数据工程导入视频与用户上传视频展示合同一致

- GIVEN feed 中同时存在用户上传的视频 post 与数据工程导入的视频 post。
- GIVEN 两类视频均包含 `videoUrl` 与 `thumbnailUrl/coverUrl`。
- WHEN 用户在首页、视频频道和作品浏览器查看两类视频，并分别点击播放。
- THEN 两类视频未播放态均按同一 `thumbnailUrl -> coverUrl` 优先级展示封面。
- THEN 点击后均进入播放器消费 `videoUrl`，不会因为来源不同走不同 UI 或不同封面字段。
- THEN 数据工程导入视频缺封面时不会进入可发布 feed，必须在导入 gate 或服务 importer 阶段失败。

<a id="gwt-004"></a>
### GWT-004 两种视频 profile 共享会话状态、P0 时间轴与独立拖动增强

- GIVEN Feed 中存在已发布且处理状态为 ready 的视频 post，其 descriptor 含 verifiedDurationMs；P1-A 视频可额外含 previewTrack，P1-B 视频可额外含 ABR descriptor。
- GIVEN 首页内嵌视频和同一 post 的 WorkBrowser 均由同一个 VideoPlaybackSession 命令/快照合同驱动。
- WHEN 用户自动播放、手动暂停/续播、拖动时间轴、切集、离屏或前后台切换。
- THEN feedInline 的被动进度轨始终贴视频底边并保持可见，真实总时长常驻轨道右上方；不显示左侧播放按钮，不使用黑色时长胶囊，也不因 44dp 语义热区抬高视觉轨道。
- THEN immersiveWorkBrowser 的时间轴视觉轨紧贴底部互动工具栏上沿并与 caption rail 对齐；控制层只包含轨道与轨道上方的短暂总时长 overlay，不显示左侧播放按钮，正常播放时轨道保持可见。
- THEN 标题、正文与交集说明组成同一文本区并始终位于总时长/时间轴之上
- AND 总时长仅在首次进入或切集完成后最多显示 5 秒，不为它单独占据一行。若文本区实际 RenderParagraph 字形矩形与总时长 RenderBox 无法保持最小安全间距，则只隐藏视觉总时长
- AND 短文本未占满右侧时不得按整条 rail 误判。轨道与无障碍 current/total 语义必须保留。
- THEN paused 使用 4dp 轨道和 8dp 当前位置，中央只显示无背景、无边框、三个角圆润的放大播放三角；scrubbing 使用 6dp 轨道和 12dp 当前位置，P0 以更大等宽数字显示目标时间/有效总时长，P1-A 才在其上方追加服务端 storyboard 预览。
- THEN 拖动仅改变虚拟 target，释放时只提交一次 seek
- AND 取消回到原位置
- AND 原本暂停或 manualPause 不会因 seek、自动播放、前后台、焦点或切集而自行续播。
- THEN 缺少 previewTrack、能力受限、节流或预览失败时只显示时间浮标
- AND P1-A/P1-B 可分别关闭且不影响 P0
- AND 未知时长禁用拖动，buffering、ended、failure 不伪装为正常播放。
- THEN 页面、控件、焦点协调器不得直接调用原生 controller 的 play/pause/seek；过期 generation 回调不得影响当前作品。
- THEN 当前视频会话按 viewport epoch、post、media delivery identity 与 episode index 原子绑定；评论分屏、过滤移除/恢复和 mediaItems 重排恢复同一媒体时不得回到第 1 集或复用已失效会话，普通重建/重排不得重启五秒窗口，真实 1→2→1 切集则每次开启新窗口。

## 6. 依赖

- 前置要求：[`content-display-consistency`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 视频未播放态展示同源封面并点击后播放

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：首页/视频频道/作品浏览器的同一视频 post 未播放态封面一致，点击后能进入同一 `videoUrl` 的播放态。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 视频 feed、沉浸浏览器与作者详情状态一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：四环境 Remote-only 状态同步与重入保持均由同一 typed port 合同覆盖，测试 double 仅在测试树中且不维护页面级第二状态源。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 数据工程导入视频与用户上传视频展示合同一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：三层证据均证明两类视频通过同一 DTO/read model 展示。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 两种视频 profile 共享会话状态、P0 时间轴与独立拖动增强

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：两种 profile 的控制层只消费 PlaybackSnapshot，并由本地契约、受控视觉验收和真实设备 seek/首帧证据共同证明。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效
