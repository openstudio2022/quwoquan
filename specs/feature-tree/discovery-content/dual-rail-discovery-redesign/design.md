# L2 Design：统一发现与聚焦浏览 (`dual-rail-discovery-redesign`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让统一内容流与媒体、文章聚焦面共享对象与互动事实，取消退役身份分轨而保留有效浏览交互”需要 `article-rich-content-blocks`、`works-immersive-viewer`、`works-unified-feed` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让统一内容流与媒体、文章聚焦面共享对象与互动事实，取消退役身份分轨而保留有效浏览交互。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`article-rich-content-blocks`](./article-rich-content-blocks/spec.md)：`blocks` 字段变更必须走 metadata → codegen；`.g.dart` 禁止手改。
- [`works-immersive-viewer`](./works-immersive-viewer/spec.md)：共享浏览器壳承载不同聚焦面，保留翻页、阅读与评论交接，不使用 BackdropFilter 评论 Drawer。
- [`works-unified-feed`](./works-unified-feed/spec.md)：统一混排流承接等高图片宫格、任意媒体定位打开与返回上下文。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 统一内容流按权威目的面进入聚焦浏览

- 决策：复用 [`content-type-framework DEC-004/005`](../content-type-framework/design.md#dec-004) 的单字段投影和云物化目的面，以及 [`content-display-consistency DEC-002/003`](../content-display-consistency/design.md#dec-002) 的 Surface 与布局边界；本能力只拥有浏览会话交接，不创建第二份身份或布局表。
- 理由：相同 Post 的互动和媒体事实不因列表或聚焦面变化而产生新身份；浏览器壳复用不等于媒体与文章目的面合并。
- 被否决方案：保留作品/点滴双轨、从附件嗅探内容形态、用兼容目的面替换真实目的面、保留旧投影作兜底。
- 约束与影响：等高宫格与所选媒体定位由统一内容流拥有；媒体位置、阅读、评论交接和返回由浏览器 Story 拥有。评论沿既有上压分屏，不使用毛玻璃 Drawer；原 pageflip 几何主线与有效交互不随旧轨删除。
- 测试与恢复：真实列表到聚焦面的测试锁定所选对象/媒体、cursor、评论结果及返回位置；缺失投影或加载失败仅保留 canonical 恢复，不改跳另一 feed。接口或能力未就绪时保留 OPEN，禁止回滚到旧身份双读。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`article-rich-content-blocks`](./article-rich-content-blocks/spec.md)、[`works-immersive-viewer`](./works-immersive-viewer/spec.md)、[`works-unified-feed`](./works-unified-feed/spec.md)
- 关联验收：`SIT-001`、[`统一流 GWT-002`](./works-unified-feed/spec.md#gwt-002)、[`浏览器 GWT-021`](./works-immersive-viewer/spec.md#gwt-021)

<a id="dec-002"></a>
### DEC-002 pageflip 单一几何主线与作品浏览归属

- 决策：文章与图片书共用一条 pageflip 几何主线；基础几何和文章翻页实现都归属到本能力的 `works-immersive-viewer` Story，不由全局规则、Review 角色或 harness adapter 复制功能事实。
- 影响 Story：[`works-immersive-viewer`](./works-immersive-viewer/spec.md)
- 关联要求：`REQ-003`、`REQ-009`、`REQ-011`、`REQ-016`、`REQ-017`、`REQ-018`、`REQ-019`、`REQ-020`、`REQ-021`
- 几何不变量：单指手势先锁定水平方向，纵向意图交还父级。任意帧只允许一个 moving leaf、一条 seam/fold 和一条 free edge。commit 在应用 animation plan 最后一帧后才能同步 `completeAnimation` 与 page index；cancel 保持当前索引。
- 坐标投影：spread spine 固定为 `bounds.left + bounds.width / 2`。portrait 单页的 `bounds.width = 2 * pageWidth`，可见页左边缘是 `bounds.left + pageWidth`，不得把负值 `bounds.left` 当成可见边缘。book point 投影到 viewport 时，forward 使用 `bounds.left + bounds.width / 2 + point.dx`，BACK 使用 `bounds.left + bounds.width / 2 - point.dx`。
- BACK 视觉输入：页面绑定、提交与 suppression 始终保持 semantic `direction == back`，portrait 视觉几何使用 `visualGeometryDirection == forward`。visual replay 采用反向时间，并允许 X 在 `-pageWidth..pageWidth` 单调推进；不得裁成 `0..pageWidth`。
- 局部裁剪：forward 的 sheet-local X 为 `point.dx - anchor.dx`，BACK 为 `anchor.dx - point.dx`。portrait Route-B 的 recto/front 与 verso/back 必须由同一 canonical moving-sheet polygon 互补切分；landscape/fallback 仍消费原生 BACK 分支。
- BACK 主路径：文章 portrait BACK 固定使用 Route-B：L0 是完整 current/right underlay，L1 是唯一 previous moving leaf，并在同一 `Positioned + Transform.rotate + ClipPath` surface 内按 `ArticlePageBackwardLeafFrame` 切分 recto/front 与 verso/back。禁止 previous-front page-space replacement、独立 front/back 平面或额外 moving sheet。
- 页面与诊断绑定：`bottomLayerPageIndex == currentPageIndex`，`flippingLayerPageIndex == currentPageIndex - 1`；recto/verso 绑定 flipping index，bottom 绑定 current index。`flippingClipArea/bottomClipArea`、anchor/angle、fold/free-edge、face partition 与诊断字段必须直接派生自同一 calculation/frame/resolver，诊断不得反向成为绘制真相源。
- 几何验收：BACK previous moving sheet 必须与 visible current page 形成正面积交集，且不能整体落在当前页左边界之外；动画后段同时存在正面积 recto、verso 与 current 三个互不冒充的可见分区。
- 材质与加载：图片 moving sheet 每帧只绘制一张完整页面的 front 或 back 材质；禁止重叠纹理子页、压缩子纹理、重复完整纹理起点，也不得以黑色舞台填补本应由背面材质覆盖的区域。加载/失败状态冻结到落平后首个静态帧，再应用排队状态。
- 边界：不抽取新 DeckHost、painter、partition 或通用纹理类型，不新建文章翻页主线、诊断坐标链或改写同步 `completeAnimation` 时序。图片展示层位于 `components/media/image/book/`，只接收 URL 列表、页码回调和边界 overflow 回调，不依赖 discovery/content DTO、Riverpod provider、GoRouter 或 `ui/**`。
- 降级与体验：Reduce Motion 下不显示动态翻页层，但仍原子切换页面。失败保留返回和可恢复动作。
- 页码与 chrome：浏览器不因媒体类型改变深色沉浸背景，系统层、媒体层与文章纸张内页尾的页码边界由 Story `REQ-003` 单点声明。不得显示媒体类型标识或常驻筛选 Tab，也不回退到 rubber-band `PageView` 主体验。
- 关联验收：`GWT-003`、`GWT-010`、`GWT-015`、`GWT-016`、`GWT-017`、`GWT-018`、`GWT-019`、`GWT-020`

<a id="dec-003"></a>
### DEC-003 图片视频整栏几何与信息区单源

- 决策：viewer 的图片/video surface、图片静态页/翻页纹理和 chrome 消费同一几何结果；同一布局阶段测量收起态顶部、底部整组、可选全屏入口及真实信息，再产出媒体显示窗口、等比缩放/上下裁剪量、入口、information、caption、timeline 与 toolbar 矩形。不再产出独立 current-time 行或按媒体类型分叉的 cover/contain 策略，几何模型只拥有展示窗口，不拥有素材、播放或互动事实。
- 几何边界：消费 Story `REQ-024` 的 `r、W/H/T/B/E/C`，以 `h=W/r` 和 `H0=C−T、H1=C、H2=H` 选择可覆盖的最高完整区域。普通不足时 contain 与上 45%/下 55% 留白；跨档只将多余高度上下等量裁剪，保持全宽、无左右裁剪/拉伸，不存在连续侵入半栏的中间档。图片纹理正反面与静态层必须用同一窗口和裁剪输入，不重写 DEC-002 的 pageflip 引擎。
- 理由与否决：完整整栏透明及可测试的真实区域优先于保留所有像素；否决所有媒体一律 contain、竖视频无条件 cover、只按固定素材比例分类、逐像素侵入顶部/底部和把 9:16 强行满屏。留白 45/55 不能用于裁剪；不新增超长图阈值、阅读器或第二图片几何链。
- 布局与绘制：竖屏信息顺序为实际画面下方居中全屏入口 → 可选关联区（含单份交集）→ 配文 → 时间轴 → 作者/关注/赞转评底栏；无入口或关联则实测高度/间隔为零，关联最多两行且不创建事实。入口热区与间距进入 `E`，底部整组和安全区进入 `B`；小屏/大字先收起可展开内容，零高媒体区不是有效布局。整屏档底栏绘制层须真实透明，无高不透明度填充或模糊盖层；仅局部弱渐变保证控件可读，不隐藏系统图标或伪造平台不可绘制区域。token 与文案留在所属 viewer/design-system/l10n，不修改无关共享常量。
- 稳定性与恢复：普通播放、控件显隐、scrub 与配文展开不改变档位或已测空间；真实视口/媒体变化以原子切档或整层转场避免任意帧半栏覆盖。几何只读当前有效比例和实际约束，不消费传感器，不持有 native controller；播放与 seek 只向同一 VideoPlaybackSession 发命令。图片/视频加载未知、失败或重试仍使用同一 surface 与既有等待恢复链，无有效目标不提供入口，不靠默认 16:9 假定成功。
- 时间轴边界：竖屏 ≤30000ms 继续触摸揭示后五秒、>30000ms 继续低亮度常显；scrub 的 caption/入口/关联同步消费同一 snapshot，隐藏但不释放空间，end 单次 seek、cancel 零 seek且 intent 不变。横向所有已知有效时长统一服从 DEC-004 全组显隐，不用竖屏 timer/暂停 pinned 竞争；inlineFeed 不改变。未提交拖动及旧计时器按 post/media/session generation 取消，未知时长不制造 seek 或时间。
- 测试与观测 seam：纯几何与 Widget 实测矩形覆盖八类代表比例、402×874/长屏/平板/大字、`H0/H1/H` 等值及两侧、上下等裁、整栏原子转场和显隐不跳动；图片静态/纹理与视频同输入同窗口。时间轴覆盖 29999/30000/30001ms、未知时长、取消和持续拖动；Android/iPhone 设备单独证明真实透明、安全区与系统图标可读，不以几何测试代替。观测复用现有 session seek、媒体失败与等待时长事件；等待继续既有 3 秒/6 秒预算，不另建指标或竞争 timer。
- 关联要求与验收：`works-immersive-viewer` REQ-005/GWT-005、REQ-024/GWT-023，`video-display-journey` REQ-004/GWT-004，`photo-display-journey` REQ-001/GWT-001。回滚只能整体回滚同一几何/绘制/时间轴增量，不在当前合同下保留双布局或旧 current-time 链；若需恢复旧产品行为须先重新确认规格，不能作为故障 fallback。

<a id="dec-004"></a>
### DEC-004 局部横向模式与统一控件显隐由 viewer 单轨拥有

- 决策：viewer 单一展示状态机拥有竖屏普通/局部横向模式与横向控件显隐；只有当前可查看 image/video 有效比例 `r>1` 且实际视口为竖屏普通模式时暴露入口。进入采用同一查看器局部 90° 旋转宿主，手机上边固定对应横向画面左边，宽高/触摸/安全区/内部弹层锚点同源转换；宽视口不重复旋转，不新增 route、播放器、播放源请求或桌面浏览器系统全屏。
- 方向 owner 与否决：全 App 固定正向竖屏策略属于 runtime owner，媒体只消费实际窗口和用户显式模式。否决物理横屏租约、方向捕获/请求/拒绝/恢复状态链、按手机姿态切模式，以及退出时恢复允许所有方向；不把相机素材旋转元数据与页面方向混为一谈。平台系统分享/键盘仍由系统呈现，不强行旋转系统 UI，也不释放 App 方向约束。
- chrome 边界：横向完整视口 contain，控件只叠加不压缩媒体。顶栏只放返回/作品标题/更多，底部沿现有作者头像/名称/关注与赞转评分组，右下独立收起；自己的作品保留隐藏作者/关注语义。视频中央显式播放/暂停，所有已知有效时长的中性白/灰时间轴在整组底栏上方，只有 scrub 有目标/总时长；图片无播放/进度/时间。标题省略与局部弱渐变不能影响返回/更多/收起的独立热区。
- 单一计时器：媒体就绪且进入完成、或最后有效交互结束后开始 5 秒计时，统一隐藏所有普通控件和专属渐变，包括两个退出按钮；播放、暂停、图片同规则，隐藏即退出 hit-test/semantics，不改变媒体几何。隐藏时轻点仅唤出并重新计时，可见时非按钮画面轻点仅收起；play/pause 只由显式中央按钮向既有 session 发命令。系统返回/Esc 及可发现的无障碍显示/退出保留，不用常驻视觉按钮绕过合同。
- 交互挂起与生命周期：scrub、内部弹层、文本输入、关键无障碍操作和加载失败挂起倒计时，结束/关闭/恢复后从零计时；计时器按当前模式与 post/media/session generation 唯一绑定，模式切换/离开/dispose 取消，过期回调不改新媒体或主壳。横向不保留 timeline 局部五秒或 paused pinned；竖屏保留原 30 秒边界。未知时长禁 seek；失败只作用媒体/动作局部并保留 canonical 重试与退出，不吞错误或制造 ready。
- 一致性与命令：mode reducer 只取消未提交 scrub/pageflip、读取当前稳定媒体身份/局部阅读上下文和播放快照，不直接操作 native controller 或复制互动事实；进出均沿同一 VideoPlaybackSession 持续消费最新实际位置和 intent，不在进入时冻结一个用于退出 seek 的旧 snapshot。00:10 进入、00:20 收起继续 00:20；横向手动暂停收起仍暂停。横向禁切作品/翻图/切集，但不吞 seek、按钮与系统返回。
- 弹层与主壳恢复：返回先关评论/更多，后收起横向；左上返回、右下收起、系统返回/Esc 以同一幂等 reducer 收敛，重复操作不退出整个查看器。评论右侧面板和更多局部菜单在旋转宿主内；作者/登录独立页面正常竖屏，往返恢复同一 post/media、标题作者绑定与最新互动。整个沉浸周期持有已有主壳隐藏租约，收起横向不释放；仅真正退出查看器时由原 owner 释放，迟到回调不得恢复其他页面导航。
- 测试、观测与回滚 seam：geometry/Widget 注入时钟覆盖 4.9 秒/5 秒、图片与播放/暂停、持续拖动、弹层/失败挂起、轻点不误播放、隐藏不命中、时间轴全时长、最新 position/intent、禁翻图/切集及幂等返回；设备验证局部坐标、安全区、四向手机姿态、标题作者/评论/系统面板往返和主导航租约，平台强制行为如实记录，静态 API 不代替设备。复用现有 session 与媒体错误观测，无新 wire/指标；回滚保持单轨，整体撤回本模式增量，不回退到物理方向请求、旧 snapshot seek 或第二播放器，产品行为改变需先重新冻结规格。
- 关联要求与验收：`works-immersive-viewer` REQ-025/GWT-026/GWT-024/GWT-025、REQ-024/GWT-023，`video-display-journey` REQ-004/GWT-004，`photo-display-journey` REQ-001/GWT-001。

<a id="dec-005"></a>
### DEC-005 底部主导航视觉几何与关注失败局部化

- 决策：中央 `+` 的视觉容器宽度与语义命中盒分离，视觉可适度收窄但 hit-test/无障碍盒至少 48pt；导航布局 owner 保持相邻项与语义顺序不变。关注命令继续由关系 typed port 拥有，完整 Alpha 注入本地演练实现，页面只消费状态与 canonical failure。
- 恢复与测试 seam：关注 optimistic/pending 状态只在命令成功 readback 后提交；typed 失败回滚该动作并展示局部恢复，不把 viewer/page capability 改写为 unavailable。真实 Alpha App 从可见控件执行关注、作者/评论往返与 readback；对象端口层的孤立证据不能构成完整用户旅程证据。
- 关联要求与验收：`works-immersive-viewer` REQ-023/GWT-022。

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 观测首屏、下一页、viewer 切换、媒体 ready、文章分页和互动同步延迟。
- 统一内容流保持信息密度与可预测打开行为，聚焦面保持低视觉疲劳与连续浏览；两者不再绑定退役内容身份。
- 布局、色彩和字体使用 App token/asset，不在页面硬编码主题常量。
