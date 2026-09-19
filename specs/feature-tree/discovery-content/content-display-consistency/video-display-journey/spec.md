# L3 Story：video-display-journey（视频旅程） (`video-display-journey`)

> 所属能力：[`content-display-consistency`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)
>
> 设计引用：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望**视频独立旅程**：视频频道 / 首页混合流 → 视频未播放封面 → 视频沉浸式浏览器 → 作者详情，端到端数据源一致、交互状态跨页面同步、重入状态保持。与图片旅程模式一致，按 category=video 隔离，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- 首页混合流、视频频道、通用视频卡、作品浏览器的视频未播放封面展示。
- `thumbnailUrl` 优先、同源 `coverUrl` 回退、点击后进入真实视频播放的展示合同。
- 用户上传视频与数据工程导入视频在 feed/read model 中使用同一封面合同。
- 关注、点赞、评论数、转发数和重入状态在列表、浏览器、作者详情间同步；不恢复 Post 收藏，既有实体「想去」不属于本次新增能力。

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
- 作品视频与图片共用 [`works-immersive-viewer` REQ-024](../../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#req-024) 的有效比例、真实区域测量与三个整栏档位；按 `h=W/r` 对 `H0=C−T、H1=C、H2=H` 选择最高可覆盖区域，不足普通区时 contain 且留白上 45% 下 55%，其余只上下等量裁剪。禁止按“竖视频”身份无条件 cover、左右裁剪、拉伸或部分侵入整栏。
- 仅当前媒体 `r>1`、实际视口为竖屏普通模式且视频可查看时，在实际画面下方居中显示“扩展图标＋全屏”，热区至少 44pt；删除右下 current-time 与同行小图标整行。竖屏与横向全屏均无常驻 current/total，时间只在 scrub 浮标和无障碍真实进度语义中使用。尺寸未知、无可查看目标或已经是宽视口时不提供冗余或无效入口。
- 竖屏作品有效时长严格大于 30000ms 时，未播放、播放与暂停轨道整体低亮度常显；零进度不绘制亮线或亮点。时长不超过 30000ms 默认隐藏视觉轨，触摸/水平拖动揭示后 5 秒无操作再隐藏，持续拖动挂起计时；该局部规则不得隐藏竖屏标题、工具栏或全屏入口，inlineFeed 行为不变。
- 竖屏 scrubbing 时配文、居中全屏入口及关联/交集同用 `VideoPlaybackSnapshot.isScrubbing` 暂时退出可视、命中与无障碍树，但保留测量空间，不改档位、裁剪或媒体位置；进度条上方只显示 target/total。拖动轨道与 thumb 共用贴底视觉基准并彼此垂直居中，只从原位置向上增厚，不迁移到 44pt 命中区中心。end/cancel 同步恢复原 chrome；仅 end 提交一次 seek，cancel 不 seek。原本 playing 时 controller 全程继续播放且 scrub 不额外发 pause/play，原本 paused/manualPause/ended 仍不播放；清除虚拟 target 后恢复有效播放计时。playing cancel 保留自然推进的最新实际位置，paused cancel 恢复原稳定位置。
- 显式横向模式按 [`works-immersive-viewer` REQ-025](../../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#req-025) 只局部旋转查看器、控件和内部弹层 90°，媒体在完整横向视口 contain，不请求系统横屏、不随传感器切换，也不新增浏览器系统全屏能力。顶部仅返回/标题/更多，中央显式播放/暂停；作者头像/名称/关注与赞转评仍在底部，右下独立收起；进度条位于整组工具栏上方，所有已知有效时长（含 ≤30000ms）随控件显示，中性白/灰轨道与白色拖动点，不用红色。
- 横向播放或暂停同用最后有效交互结束后 5 秒隐藏全部普通控件（含两个退出按钮）及专属渐变的单一计时器；轻点只显隐，不同时播放/暂停。scrub、弹层、输入、关键无障碍操作与失败挂起计时，结束或恢复后重新计时；横向不得叠加短视频局部 timer 或暂停 pinned 常显。系统返回/Esc 与无障碍退出始终可达。
- 进入与退出仅改变展示模式，不创建第二播放器、不重复解析播放源、不重放进入前旧时间；退出消费同一 session 最新实际位置与播放 intent，例如 00:10 进入、00:20 收起应继续 00:20，横向手动暂停后收起仍暂停。横向禁切作品、翻图、切集；模式切换取消未提交 scrub/pageflip，作者/评论往返恢复同一媒体和最新互动状态。主导航整个沉浸周期隐藏且不占位，收起横向不恢复主导航。

<a id="req-005"></a>
### REQ-005 约束：统一媒体获取与 Alpha 制品隔离

- **约束**：四环境 production composition、runner 与 UAT support 不得提供 Mock/Remote 切换或 fixture override；对象级 typed double 只存在测试树。
- Alpha 使用制品绑定 Bundled 获取器，Beta/Gamma/Prod 共用 Remote 实现且仅配置不同。Post 视频、封面、预览 manifest/sprite 原始引用交给同一 typed port，平台与来源判断不得进入业务。
- 可选预览的空端点/缺轨/失败不得阻断 P0 播放；Alpha 不关闭预览掩盖获取错误。私有视频只接受真实校验 lease，不以 URL scheme 或缓存身份授予权限。
- 按 category=video 隔离，不与图片混用
- 不得把 `videoUrl` 当图片 URL 交给 image loader
- 首页、通用视频卡、作品浏览器、沉浸式浏览器首帧态必须消费同一封面优先级，不允许使用无关 seed 图、作者头像、地点图、视频 URL 或端侧运行时临时抽帧。
- 数据工程导入视频与用户上传视频使用同一展示合同，不能通过入口差异维护第二套封面字段。
- 封面展示、点击播放、错误恢复和停留/互动行为必须具备 `referralSource` / `feedRequestId` / trace 传递，支撑推荐与运营分析。

<a id="req-006"></a>
### REQ-006 视频全入口共享命令与读失败语义

- 首页、视频频道、竖/横屏控制区、作者作品、搜索/路由直达与评论内 Post 点赞均经 [动作意图 REQ-003](../content-action-intent-contract/spec.md#req-003) 的 typed coordinator 与真实 surface；不维护视频专用 writer/outbox。
- 本人状态、pending 与统计按 [状态同步 REQ-003](../viewer-profile-state-sync-contract/spec.md#req-003) 至 [REQ-006](../viewer-profile-state-sync-contract/spec.md#req-006) 处理；无 pending 的读失败不制造待同步，数字未知只占位数字、本人未知不盲 toggle。
- 互动读失败不重建播放器、不丢当前播放位置；目标真正失权时按内容资格进入不可访问，不用旧缓存或乐观按钮继续放行。actor 切换和旧回调同样受分区/epoch 保护。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/discovery_feed.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/video_post.yaml`
- canonical：`quwoquan_app/lib/service/content_service/content/post/presentation/home_multi_form_feed_media_grid.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/media_asset/presentation/video_player_widget.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_canvas.dart`
- canonical：`quwoquan_app/lib/service/content_service/content/comment/application/comment_provider.dart`
- canonical：`quwoquan_data/schema/content/post_manifest.schema.json`
- canonical：`quwoquan_service/services/content-service/cmd/import/main.go`
- canonical：`quwoquan_app/lib/service/content_service/content/post/application/public/content_post_view_data.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/media_asset/presentation/video_playback_session.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_controls.dart`
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
- GIVEN 该视频 post 具备真实作者身份、本人关系/点赞结果和有来源的互动统计，不存在 Post 收藏事实。
- WHEN 用户在竖屏或显式横向浏览器点赞、关注作者，进入作者详情或评论后再返回。
- THEN 各页面共享同一 actor/target 状态；关注只有 receipt 确认才改变最终关系，点赞按钮乐观但数字保持有效服务端基线，统计追齐后不额外 +1。
- THEN 作者详情的较新确认返回后同步更新；旧 Feed、capability、viewer 返回值不得覆盖，读取失败不伪 pending、不清已接纳意图，Post 收藏入口不回归。
- THEN 竖屏浏览操作的滑动顺序与视频频道 feed 一致，滑动到底按同一数据源加载更多；显式横向全屏专注当前媒体，禁止切作品与切集，收起后恢复浏览操作。

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
- THEN 竖屏 immersiveWorkBrowser 的时间轴视觉轨紧贴底部互动工具栏上沿并与 caption rail 对齐，不显示左侧播放按钮；有效时长严格大于 30000ms 时暗淡轨道常显，29999ms 与 30000ms 默认隐藏。
- THEN 竖屏短视频隐藏视觉轨时仍保留透明且至少 44pt 的触摸热区；触摸或水平拖动立即显示，停止操作后 5 秒隐藏，持续拖动不得中途隐藏。纵向意图不提交 seek，取消不提交 seek，水平拖动释放只提交一次；横向全部控件隐藏时不保留该独立可拖动热区，轻点仅唤出控件。
- THEN 竖屏作品视频使用与图片同源的有效比例及三个整栏档位：`h=W/r≤H0` 在普通区完整 contain、留白上 45% 下 55%；`H0<h<H1` 裁到 `H0`；`H1≤h<H` 裁到 `H1` 且顶部整栏透明；`h≥H` 裁到 `H` 且上下整栏透明。裁剪始终上下等量、全宽等比，无左右裁剪、拉伸或半栏覆盖；匹配视口时无裁剪，9:16 在长屏上不强行满屏。
- AND 媒体、可选居中“图标＋全屏”入口、信息区、配文、轨道和底栏消费同一实测几何；入口仅在可查看宽视频且当前竖屏普通视口显示于实际画面下方。竖屏固定顺序为入口区 → 可选关联区（含单份交集推荐解释）→ 配文 → 时间轴 → 底栏，无常驻 current-time 行；最多两行关联信息独立测量但不伪造数据，缺席时高度/间隔为零。402×874、平板和大字下不碰撞，隐藏 chrome 不释放空间或改变媒体档位/裁剪。
- AND 未知时长不显示虚假时间、不允许 seek，返回/更多等安全操作仍可达，不暴露无效进度热区；无障碍 current/total 语义与 inlineFeed 既有被动常显行为独立。
- THEN 显式横向全屏仅把查看器与内部控件/弹层局部旋转 90°，宽高、触摸与安全区一致；不请求手机物理方向、不依赖方向 API 拒绝/成功分支、不随传感器转换，也不新增浏览器系统全屏能力。横向媒体在完整视口 contain，顶栏仅返回/标题/更多，中央显式播放/暂停；底部保留作者头像/名称/关注与赞转评的现有分组、右下独立收起，进度条在整组上方，中性白/灰不使用红色。
- AND 横向所有已知有效时长（含 29999/30000/30001ms）随统一控件状态显示时间轴，不常驻 current/total，只有 scrub 浮标。就绪并进入完成后 4.9 秒仍可见，满 5 秒全部普通控件及专属渐变隐藏（含退出），播放与暂停相同；隐藏控件不可命中且不残留无障碍节点，媒体几何不变。轻点只显隐，不误暂停/续播；scrub/弹层/输入/关键无障碍操作/失败挂起 timer，恢复后重新计时，旧短视频 timer 与暂停 pinned 不竞争。
- AND 返回先关闭弹层，无弹层时左上返回、右下收起、系统 back/Esc 同一逻辑只收起一层；隐藏时系统与无障碍退出仍可达。退出保留同一 post/episode 与同一 session 的最新位置和 intent，00:10 进入、00:20 退出不得回跳，横向暂停后竖屏仍暂停；主导航在整个沉浸周期隐藏，收起横向不恢复主壳。
- AND 模式切换取消尚未提交的 scrub/pageflip，不提交虚拟 target；横向滑动不切作品、翻图或切集，进度拖动与按钮仍可用。评论/更多在同一旋转宿主打开，作者页按正常竖屏打开；往返恢复同一 post/episode、最新播放和互动状态，不重新开始播放。
- THEN 竖屏不超过 30000ms 的作品视频在轨道揭示时保留 paused 4dp 轨道/8dp 当前位置、scrubbing 6dp 轨道/12dp 当前位置的既有规则，不以暂停强制常显；竖屏中央保留无背景、无边框、三个角圆润的放大播放三角。P0 仅 scrub 显示目标时间/有效总时长，P1-A 才在其上方追加服务端 storyboard 预览。
- THEN 竖屏 30001ms 及更长作品未播放时全轨低亮度，零进度没有 progress 线或 thumb；播放与暂停均保持低亮度，触摸揭示或拖动结束后也不得留下高亮细线。静息视觉轨仍贴工具栏边界且左右不越过原 rail；横向轨道可见性仅服从整组控件，不保留竖屏时长边界或暂停常显分支。
- WHEN 竖屏作品开始水平 scrubbing，THEN 配文、居中全屏入口、关联及交集均不可见、不可命中且无 semantics，但测量空间不变；各 slot 同步消费同一 snapshot，不使用各自 timer。target/total 留在进度条上方；长作品等宽数字由 base 提高至 lg，拖动轨道由 6dp 增至 8dp，thumb 由 12dp 增至 16dp，轨道、progress 与 thumb 在原贴底视觉范围内共用中心线并向上增厚，44pt 只作为命中区，左右轨道长度不扩展。
- WHEN 竖屏 scrubbing end 或 cancel，THEN 原配文、居中全屏入口与关联/交集恢复且媒体矩形不变，无 current-time 行回归；end 只 seek 一次，cancel 不 seek，playing/paused intent 各自保持。原本 playing 的 controller 从 begin 到 end/cancel 不额外发 pause/play，cancel 丢弃虚拟 target 并保留自然推进的最新实际位置；原本 paused 的 cancel 恢复原稳定位置。清除虚拟 target 后有效播放计时继续累计。30000ms 与 30001ms 必须有边界测试，竖屏短视频隐藏/五秒、长视频低亮度常显及键盘/无障碍 seek 保持；横向拖动结束后仅重启统一五秒计时。
- THEN 拖动仅改变虚拟 target，释放时只提交一次 seek；播放中的拖动持续播放
- AND 取消不提交 seek，paused 回稳定位置，playing 保留自然推进的最新实际位置
- AND 原本暂停或 manualPause 不会因 seek、自动播放、前后台、焦点或切集而自行续播。
- THEN 缺少 previewTrack、能力受限、节流或预览失败时只显示时间浮标
- AND P1-A/P1-B 可分别关闭且不影响 P0
- AND 未知时长禁用拖动，buffering、ended、failure 不伪装为正常播放；已知时长 ended 保持 100% 稳定位置，thumb 中心位于轨道可见末端并与轨道垂直居中，只有显式 replay 才提交归零 seek。
- THEN 页面、控件、焦点协调器不得直接调用原生 controller 的 play/pause/seek；过期 generation 回调不得影响当前作品。
- THEN 当前视频会话按 viewport epoch、post、media delivery identity 与 episode index 原子绑定；评论分屏、过滤移除/恢复和 mediaItems 重排恢复同一媒体时不得回到第 1 集或复用已失效会话，计时器按 post/episode/session generation 取消，切页或切集不得让上一媒体的延迟回调影响当前媒体；普通重建不重新显示短视频轨道，不再保留首次进入或切集开启五秒时长窗口的旧轨。

<a id="gwt-005"></a>
### GWT-005 视频直达与模式往返保持真实互动结果

- GIVEN 同一 actor 由 Feed、作者作品、搜索/路由直达视频，或在评论内操作宿主 Post，视频可正常播放。
- WHEN 竖/横屏往返、点赞/关注、本人附着或统计子读失败、另一设备确认变更后回到前台。
- THEN 各入口经真实 surface 的同一 coordinator；关注云确认、点赞按钮乐观但数字不 +1，无 pending 的读失败只降级对应区块，不重建播放器或丢播放位置。
- AND 当前 unknown、确认版本与 actor 分区跨模式保留；旧页面结果不能覆盖新确认。目标已失权进入不可访问，不用旧缓存继续授权，Post 收藏不回归。

## 6. 依赖

- 前置要求：[`content-display-consistency`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

本次互动增量的待实现测试：`quwoquan_app/test/local_contract/journeys/cross_page_interaction_consistency/cross_page_interaction_consistency__local_contract_test.dart` 与 `quwoquan_app/test/local_contract/journeys/viewer_profile_state_sync/viewer_profile_state_sync__local_contract_test.dart` 扩展绑定本 Story `GWT-002`、`GWT-005`；`quwoquan_app/test/api_integration/service/content_service/content/content_reaction/content_reaction_remote__api_integration_test.dart` 证明同 actor receipt/readback；`quwoquan_app/test/user_acceptance/service/content_service/content/content_reaction/like_post__user_acceptance_test.dart` 和 `quwoquan_app/test/user_acceptance/journeys/profile/profile_journey__user_acceptance_test.dart` 扩展视频直达、横向、评论/作者往返的双真机子句并绑定对应 `spec_ref`。这些是后续断言落点，不是已实现/通过记录。

<a id="open-005"></a>
### OPEN-005 视频全入口的互动结果分型证据缺失

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`REQ-006`、`GWT-005` 尚缺真实 surface、统计失败/unknown、actor 隔离、目标撤权与播放器不重建的组合证据。
- 完成判定：视频入口逐项 local_contract/API/双真机直接绑定 `GWT-005`，并与 `OPEN-002` 的新 `GWT-002` 同候选取证；已有播放或几何证据不替代互动闭环。

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
- 完成判定：`REQ-002` 与 `GWT-002` 的当前语义满足且真实测试 `spec_ref` 有效；旧 Post 收藏与数字即时 +1 断言不证明本次规格。

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
- 影响或价值：尚缺两种 profile 的会话真相源、整栏几何、竖屏 30 秒边界与横向统一五秒模式当前合同的 local_contract、受控视觉及真实设备 seek/首帧证据；旧物理方向拒绝、常驻时间/退出或进入旧位置恢复证据不得替代。
- 完成判定：`GWT-004` 逐子句由真实测试 `spec_ref` 绑定，覆盖 `H0/H1/H` 整栏阈值与无左右裁剪、29999/30000/30001ms、ended 100% 末端共中心、固定贴底拖动基准、playing scrub 零额外 pause/play、cancel 最新实际位置与 QoE 连续、横向所有已知时长白灰时间轴、无常驻时间、4.9 秒/5 秒、播放/暂停、scrub/弹层/失败挂起、轻点只显隐、隐藏不可命中与最新位置/intent 连续。Android/iPhone 设备及适用平板/宽视口 user_acceptance 单独证明局部旋转触摸/安全区、退出/back、作者/评论往返、禁切集与主导航始终隐藏；设备证据尚缺，不以测试/编译或模拟器结果冒充。
