# 趣我圈 iOS 原生前端 UX 规范

## 1. 文档定位

本规范是 `quwoquan_app/` 前端 UI 的 iOS 原生画质唯一体验标准，覆盖：

- 侵入式图片/视频浏览器
- 作者主页 / 他人主页
- 创作编辑页 / 发布流程
- 各类 post 卡片 / 列表 / 圈子封面
- 底部导航、一级 tab、二级 tab
- Action Sheet、半屏面板、弹窗选项

适用范围：`quwoquan_app/lib/**/*.dart`

当旧设计说明、通用设计规则与本规范冲突时，iOS-facing UI 以本规范为准。

本规范中的关键词含义：

- `MUST`：强制，违反即视为体验缺陷
- `SHOULD`：强烈建议，除非有明确更高优先级理由
- `MAY`：可选，仅用于局部增强

## 2. 体验总原则

### 2.1 Native First

- 所有 iOS-facing 页面 `MUST` 优先使用 Cupertino 语义与 iOS 动态色，而不是先做 Material 再“套皮”。
- 交互反馈 `MUST` 是轻、稳、可预期的，不允许用夸张位移、过重阴影、过厚毛玻璃制造“高级感”。

### 2.2 Content First

- 内容密度 `MUST` 优先于装饰密度。
- 图片、视频、正文、标题是主角；玻璃、胶囊、阴影、描边只能为可读性与操作服务，不能抢占主体注意力。
- 卡片、主页、编辑器 `MUST` 尽量减少无效留白，优先复用统一内容宽度与边距语义。

### 2.3 Single Material Per Layer

- 同一视觉层 `MUST` 只有一种主材质。
- 同一块区域禁止同时出现“系统纯白 + 暖白 + 毛玻璃白”三套表面。
- 文本承载区 `MUST NOT` 使用重毛玻璃；毛玻璃只允许用于浮层 chrome，例如顶部栏、底部栏、轻量页码指示器、半屏面板背景。

### 2.4 Stable Geometry

- 选中态 `MUST` 通过色彩、透明度、字号细微差异表达，`MUST NOT` 通过粗体跳变、轴线漂移、容器高度变化表达。
- 一级 tab、二级 tab、底部导航、沉浸式工具栏 `MUST` 保持视觉中轴稳定。
- 吸顶区域 `MUST NOT` 出现重复实例、双层 tab、前后圆角断裂或背景漏光。

### 2.5 Symmetric Dark Mode

- 每一个浅色材质 `MUST` 有深色对应材质。
- 深色模式不是“把背景改黑”，而是要保留层级、可读性、轻玻璃和触控反馈的一致体验。

### 2.6 High-Touch Quality

- 所有点击目标 `MUST` 不小于 `44x44`。
- 主工具栏、主操作按钮 `SHOULD` 达到 `48x48` 级别。
- 所有边缘吸附、卡片对齐、点状指示器、图标数字同行 `MUST` 保证共线与居中。

### 2.7 Adaptive Screens

- 所有 iOS-facing UI `MUST` 同时为浅色/深色、`compact` / `regular` / `expanded` 三档屏幕设计，而不是只做单一手机尺寸。
- 响应式的目标是“保持同一体验语义”，不是给不同屏幕做不同产品。
- `compact` 屏幕 `SHOULD` 优先收紧间距和芯片宽度，但 `MUST NOT` 牺牲 44x44 热区、文字可读性与视觉中轴。
- `expanded` 屏幕 `SHOULD` 主要放大留白节奏、动作位对称宽度、芯片宽度和内容最大宽度；`MUST NOT` 把手机布局机械拉宽成松散大平板界面。
- 断点切换 `MUST` 平滑、稳定；禁止因为断点变化导致 tab 居中失效、工具栏漂移、卡片几何失衡。

### 2.8 No Android Leakage

- iOS-facing UI `MUST NOT` 直接暴露 Android 默认视觉或交互语义。
- 若因能力复用必须使用 Material 组件，`MUST` 只复用行为底座，视觉层必须重新映射到 `AppColors`、`AppSpacing`、`AppTypography` 与 Cupertino / iOS 语义。
- `MUST NOT` 引入默认 Material ripple、FAB、Snackbar、厚 elevation 卡片、下划线型 tab indicator、Android 式紧密表单/列表、Android 式大色块底部导航。

## 3. 语义 Token 体系

### 3.1 Token 唯一来源

前端视觉与交互语义只允许来自以下四层：

- `AppColors`
- `AppSpacing`
- `AppTypography`
- `DesignSemanticConstants`

规则：

- 缺失语义 `MUST` 先补 token，再写 UI。
- 业务组件内 `MUST NOT` 发明新的视觉字面量常量来替代全局 token。
- 一次性局部计算可以有私有常量，但 `MUST NOT` 承担跨组件视觉语义。

### 3.2 颜色语义

| 语义 | 当前 token | 规范 |
|---|---|---|
| 页面背景 | `AppColors.iosPageBackground()` / `ColorType.pageBackground` | 全局页面底色，必须稳定、退后 |
| 常规主表面 | `AppColors.iosGroupedSurface()` / `ColorType.backgroundPrimary` | 列表、卡片、内容容器 |
| 抬升表面 | `AppColors.iosGroupedSurfaceElevated()` / `ColorType.surfaceElevated` | 浮起卡片、sheet 内容面 |
| 资料区语义白 | `AppColors.iosProfileSurface()` | 作者主页资料区唯一 iOS 暖白材质 |
| 深色沉浸背景 | `AppColors.worksBackground` | 侵入式浏览器、作品频道强制背景 |
| 轻玻璃表面 | `ColorType.glassSurface` | 工具栏、轻浮层、轻毛玻璃指示器 |
| 分割线 | `AppColors.iosSeparator()` / `ColorType.separatorSubtle` / `separatorOpaque` | 层级分界，不抢眼 |
| 主文字 | `AppColors.iosLabel()` / `ColorType.foregroundPrimary` | 标题、正文主信息 |
| 次文字 | `AppColors.iosSecondaryLabel()` / `ColorType.foregroundSecondary` | 时间、说明、元信息 |
| 第三文字 | `AppColors.iosTertiaryLabel()` / `ColorType.foregroundTertiary` | 极弱说明、未选中态 |
| 强调色 | `AppColors.iosAccent()` / `ColorType.primary` | 主 CTA、选中态、高价值入口 |
| 破坏色 | `AppColors.iosDestructive()` / `AppColors.error` | 删除、举报、危险操作 |

颜色规则：

- `MUST NOT` 在同一层同时混用 `iosGroupedSurfaceLight` 与 `iosProfileSurfaceLight` 制造“白块感”。
- `MUST NOT` 用高饱和纯蓝去强调普通管理操作；只有导航主动作和关键 CTA 才使用品牌强调色。
- 毛玻璃底色 `SHOULD` 低 alpha，目标是“有材质、弱存在感”，不是做明显半透明黑板。

### 3.3 间距语义

| 语义 | 当前 token | 规范 |
|---|---|---|
| 内容左右边距 | `AppSpacing.feedContentHorizontal(context)` | 关注流、圈子页、资料页正文统一内容边距 |
| 内容最大宽度 | `AppSpacing.feedMaxContentWidth` | 关注流、资料页、主要内容区共用最大宽度 |
| Post 列表区边距 | `AppSpacing.postPreviewSectionPadding` | Post 栅格/列表统一外边距 |
| Post 卡片间距 | `AppSpacing.postPreviewGridSpacing` | Post 栅格与列表统一间距 |
| Post 内边距 | `AppSpacing.postPreviewCardPadding` | 标题、配文、footer 统一内边距 |
| 组内间距 | `AppSpacing.intraGroup*` | 图标-数字、标题-副文案、chip 组 |
| 组间间距 | `AppSpacing.interGroup*` | 卡片组、区块组、tab 区块 |
| 容器内边距 | `AppSpacing.container*` | 卡片、sheet、弹窗、编辑区容器 |

间距规则：

- Post 预览体系 `MUST` 默认走 `8px` 内容优先密度语义，不允许私自回退到更松的 12/16。
- 媒体预览 `MUST` 默认 edge-to-edge；标题与正文才使用卡片内边距。
- 新页面 `MUST` 先选语义级别（container / intraGroup / interGroup），再选数值级别（xs/sm/md/lg/xl）。

### 3.4 几何与尺寸语义

| 语义 | 当前 token | 规范 |
|---|---|---|
| 紧凑断点 | `AppSpacing.compactBreakpoint` | `< 360`，小屏压密度但不压触控热区 |
| 扩展断点 | `AppSpacing.expandedBreakpoint` | `>= 600`，大屏放大节奏但不重做 IA |
| 响应式尺寸函数 | `AppSpacing.responsiveValue()` | 根据 `compact / regular / expanded` 返回尺寸 |
| 响应式字体函数 | `AppTypography.responsive()` | 根据 `compact / regular / expanded` 返回字号 |
| 底部导航高 | `AppSpacing.bottomNavHeight` | 底部主导航唯一高度 |
| 一级 tab 高 | `AppSpacing.tabNavigationHeight` | 顶部主导航唯一高度 |
| 二级 tab 高 | `AppSpacing.subTabNavigationHeight` | 次级分类导航唯一高度 |
| 工具栏触控下限 | `AppSpacing.toolbarMinTouchHeight` | 底栏和浮层工具按钮最小触控高度 |
| 主图标按钮最小热区 | `AppSpacing.iconButtonMinSizeSm` | 44x44 最小可触控标准 |
| 关注按钮宽度 | `AppSpacing.followButtonWidthCompact` | 媒体浏览器顶部跟随/已关注按钮 |
| 资料页基础背景比 | `AppSpacing.profileHeaderBaseHeightRatio` | 默认约 1/4 屏高 |
| 资料页拉伸上限 | `AppSpacing.profileHeaderMaxStretchHeightRatio` | 下拉可到约 1/2 屏高 |
| 创作抽屉最大比 | `AppSpacing.createEntrySheetMaxHeightRatio` | 创作入口半屏/抽屉高度上限 |
| 助理面板高度比 | `assistantPanelHeightRatioMin/Max` | 半屏面板统一范围 |
| Sheet 手柄尺寸 | `createEntrySheetHandleWidth/Height` | 所有 iOS 风格半屏拖拽手柄统一 |
| 一级 tab 芯片基宽 | `tabChipBaseWidth` / `tabChipBaseWidthVideoImmersion` | 居中 tab 稳定锚点 |
| 一级 tab 芯片间距 | `primaryTabChipGap` | 主导航组内间距唯一来源 |
| 标题两侧锚点宽 | `discoveryHeaderSideAnchorMinWidth` | 保证标题中轴稳定 |

尺寸规则：

- 所有跨屏尺寸差异 `MUST` 优先使用 `AppSpacing.responsiveValue()` 与 `AppTypography.responsive()`，禁止在业务组件里手写第二套断点体系。
- 断点固定为三档：`compact < 360`、`regular 360-599`、`expanded >= 600`。
- `compact` 允许缩小 chip 宽度、组间距、文案字号一级，但 `MUST NOT` 小于最小可读字号与 44x44 热区。
- `expanded` 允许放大 tab gap、左右锚点宽度、内容最大宽度与留白节奏，但 `MUST NOT` 让正文列宽无限扩张；主内容仍要受 `feedMaxContentWidth` 约束。

### 3.5 圆角语义

| 语义 | 当前 token | 规范 |
|---|---|---|
| 微小圆角 | `AppSpacing.smallBorderRadius` | tag、输入框、轻按钮 |
| 标准圆角 | `AppSpacing.borderRadius` | 常规卡片、图像、输入框 |
| 内容预览圆角 | `AppSpacing.contentPreviewCornerRadius` | post、圈子封面、圈子图标、媒体缩略图统一 |
| 大容器圆角 | `AppSpacing.largeBorderRadius` | 大卡片、面板、页面级容器 |
| 圆形 | `AppSpacing.circularBorderRadius` | 圆形按钮、圆点、圆头像 |

圆角规则：

- Post、圈子封面、圈子 icon、预览图 `MUST` 统一使用 `contentPreviewCornerRadius`。
- 一级 tab 区和资料区交界 `MUST NOT` 出现两个不同圆角语义打架。
- 圆角变化 `SHOULD` 只表达层级，不表达状态。

### 3.6 字体与层级语义

| 语义 | 当前 token | 规范 |
|---|---|---|
| 大标题 | `iosLargeTitle` / `iosProfileTitle` | 页面级标题、资料页大标题 |
| 二级/三级标题 | `iosTitle2` / `iosTitle3` | 区块标题、编辑器重点标题 |
| 导航标题 | `iosNavTitle` | 顶栏、弹窗头部、导航标题 |
| 正文 | `iosBody` | 主要阅读文字 |
| 次正文 | `iosSubheadline` / `iosFootnote` | metadata、说明、辅助信息 |
| Caption | `iosCaption1` / `iosCaption2` | 极弱说明、角标、chip |
| 一级 tab 文案 | `AppTypography.primaryTabLabel` | 选中与未选中基线一致 |
| 底部导航文案 | `bottomNavLabelUnselected` / `Selected` | 选中可放大，不加粗 |

字体规则：

- 导航选中态 `MUST NOT` 依赖 bold 变化；用颜色和字号轻微变化即可。
- 作者名、post 标题、卡片标题 `SHOULD` 用 `medium` / `semiBold`，`MUST NOT` 默认上重黑体。
- 正文行高优先 `bodyLineHeight` / `lineHeightRelaxed`，禁止挤压成 Android 式紧密块。

### 3.7 毛玻璃与动效语义

当前项目未独立抽出 `AppMotion`，因此临时规范如下：

- 微交互 `SHOULD` 维持在 `180-260ms`
- 结构性展开/收起 `SHOULD` 维持在 `260-420ms`
- 优先使用 `easeOut` / `easeOutCubic`

毛玻璃规则：

- 正文块 `MUST NOT` 使用重毛玻璃。
- 顶部栏、底部栏、sheet、轻量页码指示器 `MAY` 使用低 alpha 玻璃。
- 玻璃目标感受是“轻质覆盖层”，不是“半透明深色大板”。

## 4. 分场景规则

### 4.1 侵入式图片/视频浏览器

- 背景 `MUST` 使用 `AppColors.worksBackground`。
- 图片/视频页码指示器 `MUST` 在文字之上。
- 页码指示器 `MUST` 最多显示 `6` 个点；图片更多时使用滑动窗口。
- 当前点 `MUST` 与其它点共线，只允许亮度变化，禁止尺寸或垂直位置跳变。
- 指示器 `SHOULD` 带轻玻璃质感，但透明度要高，减少对媒体的遮挡。
- 有标题/正文时，指示器与文字块整体 `MUST` 尽量向下贴近底部工具栏，不要单独悬浮在图中央。
- 文章 `MUST NOT` 显示图片/视频页码指示器。
- 标题/正文区 `MUST NOT` 使用毛玻璃。
- “我的 post” 底栏 `MUST NOT` 显示作者头像和关注按钮；只保留赞、转、评三等分且图标数字同行。
- “他人 post” 底栏 `MUST` 保留作者、关注、互动三列，但作者区与互动区边界要稳定。

### 4.2 作者主页 / 资料页

- 资料区 `MUST` 使用 `AppColors.iosProfileSurface()` 作为唯一主表面。
- 资料区和一级 tab 区 `MUST` 保持连续背景层级，不能出现圆角漏光、背景穿帮、白块断裂。
- 资料区宽度 `MUST` 共享 `feedMaxContentWidth` 语义。
- 顶部背景默认 `MUST` 约为 `1/4` 屏高，下拉拉伸上限 `MUST` 约为 `1/2` 屏高。
- 一级 tab 吸顶后 `MUST` 只有一个实例，不能出现重复 tab。
- 一级 tab 与顶部工具栏 `MUST` 用同一套 separator 语义分隔。
- 作者名 `SHOULD` 保持黑色但较轻字重，避免厚重。

### 4.3 Post 卡片 / 列表 / 圈子封面

- Post 预览 `MUST` 使用共享组件骨架，差异只允许在 footer slot。
- 图片/视频 `MUST` 占满 post 预览顶部，不额外留顶部和左右白边。
- post、关注流卡片、作者主页卡片、圈子封面、圈子图标 `MUST` 统一 `contentPreviewCornerRadius`。
- Post 标题与配文层级 `MUST` 克制，不能比操作区更抢眼。
- 自己的 post footer `MUST` 用赞/转/评；圈子 post footer `MUST` 用作者头像/作者名等上下文信息。

### 4.4 创作编辑页 / 编辑器

- 创作入口、滤镜、裁剪、发布页 `MUST` 使用统一容器、间距、按钮高度和圆角语义。
- 半屏创建面板 `MUST` 使用 `createEntrySheetMaxHeightRatio` 和统一手柄尺寸。
- 编辑页工具面板 `SHOULD` 轻质、低噪声，不允许同时叠多层边框、渐变、阴影。
- 文本编辑、标题输入、封面预览 `MUST` 保持稳定栅格与一致的容器层级。

### 4.5 底部导航 / 一级 tab / 二级 tab

- 底部导航高度 `MUST` 固定为 `bottomNavHeight`。
- 一级 tab 高度 `MUST` 固定为 `tabNavigationHeight`，二级 tab 为 `subTabNavigationHeight`。
- 一级 tab、底部导航的选中态 `MUST NOT` 用粗体；用颜色、透明度、字号细微差表达。
- 一级 tab `MUST` 保持视觉居中锚点稳定；左右动作位要对称占位。
- 一级和二级 tab 的 separator `MUST` 使用统一轻分割线语义。

### 4.6 弹窗、选项、半屏面板

- 全局搜索 `MUST` 使用全屏搜索面板，覆盖状态栏到底部安全区，作为唯一允许的全屏全局浮层。
- 创作入口、更多功能、评论、联系人选择等全局浮层 `MUST NOT` 做成全屏不透明页面；它们 `MUST` 作为贴底出现的非全屏面板，保留上半屏上下文可见。
- 选项弹窗、更多菜单、Action Sheet `MUST` 采用低噪声容器与明确分组。
- 头部高度 `SHOULD` 统一 `modalHeaderHeight`。
- 拖拽手柄 `MUST` 使用统一尺寸和位置语义。
- 非全屏底部面板高度 `MUST` 由内容决定，并受统一最大高度比例约束；超过上限后仅内部内容滚动，外层面板不再继续长高。
- 破坏性操作 `MUST` 和普通操作视觉分组。
- 弹窗蒙层 `MUST` 轻，不允许过黑或过厚毛玻璃遮蔽主内容。

### 4.7 组件级响应式清单

以下表格是 iOS-facing UI 唯一允许的组件级断点调整范围。若需求超出表内能力，`MUST` 先补全局 token，再更新本规范，不允许在业务组件里手写第二套 responsive map。

#### 4.7.1 一级 / 二级 Tab

| 属性 | compact | regular | expanded | 备注 |
|---|---|---|---|---|
| 容器高度 | `AppSpacing.tabNavigationHeight` / `AppSpacing.subTabNavigationHeight` | 同 compact | 同 compact | 一级 / 二级高度固定，不因断点变化 |
| 芯片基宽 | `AppSpacing.tabChipBaseWidth - AppSpacing.xs` | `AppSpacing.tabChipBaseWidth` | `AppSpacing.tabChipBaseWidth + AppSpacing.sm` | 沉浸式主 tab 以 `tabChipBaseWidthVideoImmersion` 为基准做同规则调整 |
| 芯片间距 | `AppSpacing.primaryTabChipGap` | `AppSpacing.primaryTabChipGap` | `AppSpacing.primaryTabChipGap + AppSpacing.xs` | 只允许扩间距，不允许改对齐方式 |
| 左右锚点宽 | `AppSpacing.discoveryHeaderSideAnchorMinWidth - AppSpacing.containerXs` | `AppSpacing.discoveryHeaderSideAnchorMinWidth` | `AppSpacing.discoveryHeaderSideAnchorMinWidth + AppSpacing.containerSm` | 保证标题中轴稳定 |
| 文案字号 | `AppTypography.iosSubheadline` | `AppTypography.primaryTabLabel` | `AppTypography.primaryTabLabel` | 选中态只允许轻微字号 / 颜色差 |
| 文案字重 | `AppTypography.primaryTabLabelWeight` | 同 compact | 同 compact | 禁止 bold 跳变 |
| 表面 / 分割线 | 继承当前页面单层表面 + `AppColors.iosSeparator()` | 同 compact | 同 compact | 资料页场景继承 `iosProfileSurface()` |

#### 4.7.2 底部导航

| 属性 | compact | regular | expanded | 备注 |
|---|---|---|---|---|
| 容器高度 | `AppSpacing.bottomNavHeight` | 同 compact | 同 compact | 高度固定，不允许做 Android 式增厚底栏 |
| 单项最小热区 | `AppSpacing.iconButtonMinSizeSm` + `AppSpacing.toolbarMinTouchHeight` | 同 compact | 同 compact | 全模式保持 `44x44` 以上 |
| 图标尺寸 | `AppSpacing.iconMedium` | 同 compact | 同 compact | 视觉缩放通过留白，不通过 icon 放大 |
| 文案字号 | 未选 `AppTypography.iosCaption1` / 选中 `AppTypography.iosFootnote` | 未选 `AppTypography.bottomNavLabelUnselected` / 选中 `AppTypography.bottomNavLabelSelected` | 同 regular | 不允许粗体、跳位或下划线指示 |
| 左右内容内边距 | `AppSpacing.containerXs` | `AppSpacing.containerSm` | `AppSpacing.containerMd` | expanded 只增加空气感 |
| 表面语义 | `AppColors.iosGroupedSurface()` 或 `ColorType.glassSurface` | 同 compact | 同 compact | 同一底栏只能选一种主材质 |
| 项目分布 | `Expanded` 等分布局 | 同 compact | 同 compact | 禁止中心 FAB、安卓式凸起主按钮 |

#### 4.7.3 Post 卡片 / 列表 / 圈子封面

| 属性 | compact | regular | expanded | 备注 |
|---|---|---|---|---|
| 内容最大宽度 | `AppSpacing.feedMaxContentWidth` | 同 compact | 同 compact | expanded 只增加外部留白，不放开正文列宽 |
| 区域外边距 | `AppSpacing.postPreviewSectionPadding` | `AppSpacing.postPreviewSectionPadding` | `AppSpacing.postPreviewSectionPadding + AppSpacing.containerXs` | 所有 post 列表统一语义 |
| 卡片间距 | `AppSpacing.postPreviewGridSpacing - AppSpacing.intraGroupXs` | `AppSpacing.postPreviewGridSpacing` | `AppSpacing.postPreviewGridSpacing + AppSpacing.intraGroupXs` | 只允许微调密度 |
| 卡片内边距 | `AppSpacing.postPreviewCardPadding` | `AppSpacing.postPreviewCardPadding` | `AppSpacing.postPreviewCardPadding + AppSpacing.intraGroupXs` | 标题 / 配文 / footer 共用 |
| 圆角 | `AppSpacing.contentPreviewCornerRadius` | 同 compact | 同 compact | post、圈子封面、圈子 icon、媒体缩略图统一 |
| 标题字号 | `AppTypography.iosFootnote` | `AppTypography.iosSubheadline` | `AppTypography.iosSubheadline` | 标题不允许重黑体 |
| 配文 / metadata | `AppTypography.iosCaption1` / `AppTypography.iosCaption2` | `AppTypography.iosFootnote` / `AppTypography.iosCaption1` | 同 regular | 正文与 metadata 分层稳定 |
| 媒体展示 | edge-to-edge | edge-to-edge | edge-to-edge | 禁止额外顶部或左右白边 |
| Footer 语义 | 自己的 post 用赞 / 转 / 评；圈子 post 用作者头像 / 作者名 | 同 compact | 同 compact | 只改 footer slot，不改骨架 |

#### 4.7.4 Sheet / Action Sheet / 半屏面板

| 属性 | compact | regular | expanded | 备注 |
|---|---|---|---|---|
| 呈现类型 | 全局搜索全屏；其它全局面板贴底非全屏 | 同 compact | 同 compact | 不允许把评论 / 更多 / 创作做成第二套全屏页 |
| 内容最大宽度 | 全局搜索全屏；其它贴底面板为 `min(screenWidth, AppSpacing.feedMaxContentWidth)` | `min(screenWidth, AppSpacing.feedMaxContentWidth)` | `min(screenWidth, AppSpacing.feedMaxContentWidth)` | 大屏不能拉成整屏大抽屉 |
| 最大高度比 | 创作入口 `AppSpacing.createEntrySheetMaxHeightRatio`；通用底部面板 `AppSpacing.modalSheetMaxHeightRatio` | 同 compact | 同 compact | 助理面板遵循 `assistantPanelHeightRatioMin/Max` |
| 头部高度 | `AppSpacing.modalHeaderHeight` | 同 compact | 同 compact | 头部高度固定 |
| 拖拽手柄 | `AppSpacing.createEntrySheetHandleWidth` / `AppSpacing.createEntrySheetHandleHeight` | 同 compact | 同 compact | 位置与尺寸语义统一 |
| 内容内边距 | `AppSpacing.containerSm` | `AppSpacing.containerMd` | `AppSpacing.containerLg` | expanded 只增加空气感 |
| 圆角 | `AppSpacing.largeBorderRadius` | 同 compact | 同 compact | 只用于大容器 |
| 主表面 | `AppColors.iosGroupedSurfaceElevated()` | 同 compact | 同 compact | 玻璃只允许在顶部 chrome 或蒙层 |
| 蒙层 | `ColorType.modalScrim` | 同 compact | 同 compact | 必须保留背后页面上下文，不允许整屏白底盖住上半部分 |
| 破坏性操作 | `AppColors.iosDestructive()` | 同 compact | 同 compact | 必须独立分组，不混入普通操作 |

#### 4.7.5 作者主页 / 资料页

| 属性 | compact | regular | expanded | 备注 |
|---|---|---|---|---|
| 资料区主表面 | `AppColors.iosProfileSurface()` | 同 compact | 同 compact | 禁止叠第二套白色层级 |
| 内容最大宽度 | `AppSpacing.feedMaxContentWidth` | 同 compact | 同 compact | 所有资料页与内容流共用 |
| 默认顶部背景比 | `AppSpacing.profileHeaderBaseHeightRatio` | 同 compact | 同 compact | 默认约 `1/4` 屏高 |
| 拉伸上限比 | `AppSpacing.profileHeaderMaxStretchHeightRatio` | 同 compact | 同 compact | 下拉约可到 `1/2` 屏高 |
| 头像尺寸 | `AppSpacing.avatarUserLg` | `AppSpacing.avatarUserXl` | `AppSpacing.avatarUserXl` | 通过尺寸与侵入比例保持重心 |
| 内容左右边距 | `AppSpacing.feedContentHorizontal(context)` | 同 compact | 同 compact | 由统一函数处理断点 |
| 作者名字号 | `AppTypography.iosTitle2` | `AppTypography.iosProfileTitle` | `AppTypography.iosProfileTitle` | 黑色但较轻字重 |
| 行动按钮触控高 | `AppSpacing.toolbarMinTouchHeight` | 同 compact | 同 compact | 管理按钮不能做安卓式实心 CTA |
| 分割线 | `AppColors.iosSeparator()` | 同 compact | 同 compact | 资料区与一级 tab 共用同一语义 separator |
| 一级 tab 嵌套 | 复用 `4.7.1` | 复用 `4.7.1` | 复用 `4.7.1` | 不允许再造第二套资料页 tab 规则 |

## 5. 绝对禁止

- 硬编码颜色、blur、alpha、圆角、导航高度、边距、字号、图标尺寸
- 硬编码 breakpoint、在组件内手写第二套 `compact / regular / expanded` 分支
- 用两种不同白表面在同一层制造“白块对撞”
- 用重毛玻璃承载正文或标题
- 一级/二级 tab 通过加粗或位移表达选中态
- 页码指示器放在文字之下
- 页码指示器超过 `6` 个点直接铺开
- 当前点比其它点“跳高”或偏离水平线
- 自己的 post 在沉浸式浏览器里继续显示作者头像/关注
- 在 post 预览上给媒体额外加无意义白边
- 在作者主页资料区与一级 tab 交界处留下背景漏光
- 直接引入 Android 默认视觉 / 交互：Material 默认 ripple、FAB、Snackbar、厚阴影卡片、下划线型 tab indicator、安卓式密集表单 / 列表 / 底栏
- 在 iOS-facing UI 中以 Android 设计稿、Android 组件默认态或 Material 默认动效作为基线

## 6. 新增 Token 的流程

新增前端视觉语义时必须按以下顺序：

1. 判断是否能复用现有 `AppColors` / `AppSpacing` / `AppTypography`
2. 若不能复用，先补全局 token
3. 若属于跨页面体验规则，同步更新本规范
4. 再在业务组件使用

命名要求：

- 先语义，后组件
- 先抽象层级，后具体场景
- 避免 `lightBlueButtonPadding2` 这类样式命名
- 推荐使用 `contentPreview*`、`profileHeader*`、`toolbar*`、`sheet*`、`tab*` 这一类语义命名

## 7. 评审清单

每个 iOS-facing UI 变更在合入前必须逐项确认：

- 是否完全复用了语义 token，而不是字面量
- 是否只有一套主材质，而不是多套白块/玻璃混用
- 是否支持浅色/深色且层级一致
- 是否同时验证了 `compact / regular / expanded` 三档断点下的几何稳定性
- 是否补齐了对应组件的响应式 token 使用表或明确声明“复用既有表”
- 是否保持内容优先密度
- 是否保证导航、tab、底栏、工具栏视觉中轴稳定
- 是否满足 44x44 最小热区
- 是否保证沉浸式浏览器的指示器、标题、底栏不互相打架
- 是否在自己 post / 他人 post / 圈子 post 三个分支上都保持语义一致
- 是否确认未引入任何 Android 默认视觉、交互或动效
- 是否运行 `flutter analyze`

## 8. 产品、设计、编码与测试命令及门禁

### 8.1 产品 / `/prd`

必备产出：

- `spec.md`
- `acceptance.yaml`
- 浅色 / 深色双模式矩阵
- `compact / regular / expanded` 组件级响应式 token 使用表
- “为何不引入 Android 语义”的对标结论与边界

门禁：

- 缺少任一产出，`GATE_BLOCK`
- 未明确组件级响应式 token 来源，`GATE_BLOCK`
- 以 Android 交互或 Material 默认样式为基线，`GATE_BLOCK`

### 8.2 设计 / `/design`

必备产出：

- `design.md`
- `plan.yaml`
- 组件级 token 映射、浅深色对应关系、断点调整边界
- 受影响组件的响应式回归点清单

必跑命令：

```bash
make -C quwoquan_service verify-metadata
make codegen
make codegen-app
```

门禁：

- 未说明三档断点如何保持同一 IA 与几何锚点，`GATE_BLOCK`
- 未说明浅色 / 深色如何成对落地，`GATE_BLOCK`
- 未说明如何避免 Android 默认视觉泄露，`GATE_BLOCK`

### 8.3 编码 / `/dev`

编码要求：

- 颜色、间距、圆角、字号、breakpoint、surface、separator `MUST` 只来自全局 token
- 断点差异 `MUST` 优先使用 `AppSpacing.responsiveValue()` 与 `AppTypography.responsive()`
- 若需 Material 组件，只能保留行为能力；默认视觉必须重映射到 iOS token

必跑命令：

```bash
cd quwoquan_app && flutter analyze
cd quwoquan_app && flutter test test/components/ test/ui/
```

若改动涉及 Repository / 云侧契约 / metadata，追加：

```bash
cd quwoquan_app && flutter test test/cloud/
make -C quwoquan_service build
make -C quwoquan_service test-contract
```

门禁：

- 出现硬编码视觉字面量或硬编码 breakpoint，直接视为不通过
- 出现 Android 默认 ripple、FAB、厚阴影、下划线 tab indicator、Snackbar / BottomSheet 默认态，直接视为不通过
- 未为受影响组件补齐最小 `T1/T2` 证据，直接视为不通过

### 8.4 测试 / `/verify` 与 `/commit`

必须覆盖的验证矩阵：

- 浅色 / 深色
- `compact / regular / expanded`
- 涉及场景的关键分支，例如“我的 post / 他人 post / 圈子 post”
- 导航、tab、底栏、sheet 的几何稳定性与最小热区

必跑命令：

```bash
cd quwoquan_app && flutter test test/cloud/ test/components/ test/ui/
make gate
```

全量交付或发布前追加：

```bash
make gate-full
```

门禁：

- 缺任一断点或任一模式的验证证据，`GATE_BLOCK`
- 出现视觉回归但无对应测试或验收更新，`GATE_BLOCK`
- 代码先行偏离规范、文档未同步，`GATE_BLOCK`

## 9. 执行要求

后续任何前端开发如果涉及视觉、交互、导航、层级、弹窗、工具栏、卡片、编辑器，均 `MUST` 先遵循本规范，再实现功能。

如功能需求与本规范冲突，必须先更新规范，再更新代码，不允许业务代码先行分叉。
