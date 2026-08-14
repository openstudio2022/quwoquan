# L3 Story：图片编辑 (`image-editing`)

> 所属能力：[`publish-comment-reaction`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望图片编辑器商用化：工具全真实现（占位清零）、曲线/白平衡/马赛克/文字补齐、全局撤销与放弃保护、像素引擎同源与页面观测，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- 一级工具（滤镜/裁剪/旋转/专业工具/文字/马赛克）与专业工具箱（整体/局部/HSL/黑白色阶/曲线/白平衡）全部真实像素级实现。
- 确认即烘焙 + 文件快照全局撤销/重做/历史回退；back 放弃确认与顶栏完成提交。
- ImageEditorExportEngine 预览导出同源、解码降采样上限。
- page.media.image_editor 四事件埋点与 image_editor_tool_used 工具分布。

### Out of Scope

- 消除笔/涂鸦/贴纸/美颜（M3 规划）。透视校正已升格为现行能力，见 REQ-005
  与 GWT-008。
- FilterCatalogRelease 云目录与 MediaAsset 图片 variants（独立 M2 Story）。
- EditRecipe/FilterUsageFact/FilterUsageStatsView 上云与圈子交集（独立 M3 Story）。
- 媒体上传/发布链路（归属 post-create-update）。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 工具入口零占位，所见工具即真实效果

- 全仓无占位符号；工具确认路径全部经 ImageEditorExportEngine 烘焙

<a id="req-002"></a>
### REQ-002 曲线为真实多通道 LUT 编辑器

- 曲线引擎必须保持控制点有序并支持恒等、单调、S 曲线与提亮，确认后效果写入导出像素。

<a id="req-003"></a>
### REQ-003 马赛克与文字为图上实绘图层

- 模型 wire roundtrip 必须保留笔刷、路径与颜色；命中路径后像素合成结果必须与预览一致。

<a id="req-004"></a>
### REQ-004 全局撤销/重做与放弃保护

- 步骤栈必须支持撤销、重做、放弃与完成；不可用工具必须禁用且不得创建空步骤。

<a id="req-005"></a>
### REQ-005 所有可见编辑工具必须产生真实像素结果

- 所有对用户可见的编辑工具必须产生真实像素结果，禁止占位面板或确认后无效果的空壳工具。
- 唯一像素真相源 `ImageEditorExportEngine`：解码（`decodeConstrained`，长边上限 4096 防 OOM；预览降采样 1440）、裁剪、旋转/翻转、矩阵应用、局部径向锚点、曲线 LUT、HSL 分带（`applyHslBands`）、马赛克化与笔画合成、文字合成、PNG/JPEG 编码。预览与导出共用同一几何/参数，禁止第二坐标链或把局部调整退化为全图平均矩阵。
- HSL 八通道必须是真实分色相带算法：逐像素 RGB↔HSL，按色相带（±10° 平滑过渡）
  与饱和度门控（灰阶像素不参与）选择性调节 hue/saturation/luminance；禁止把
  各通道取平均后进全局矩阵冒充分带。编辑会话预览用降采样 CPU 同算法渲染，
  确认烘焙与预览不得跳变。
- 整体面板的锐化/纹理/结构必须是 luma 通道 unsharp mask，采用分离 box blur 与
  三档半径；高光/阴影必须按亮度分区加权调节；颗粒必须是确定性 hash 噪声层，三者
  同走 `applyDetailAdjustmentsToRgbaPixels`。禁止折算为对比度/亮度矩阵系数冒充。
- 局部径向锚点必须走真算法管线（`applyLocalAdjustmentsToRgbaPixels`）：每锚点
  纯色彩矩阵与细节类逐像素调节按径向权重混合回原图；CPU 权重与预览
  ShaderMask 共用同一分段渐变（`kLocalRadialStops`），编辑会话预览由 CPU
  同管线渲染，确认烘焙不跳变。
- 自然饱和度（vibrance）必须逐像素按当前饱和度反比施加增益：低饱和像素提升多、
  已饱和像素受保护不削顶、肤色带（hue 15°–50°）衰减、灰阶不动；禁止折算为
  全局饱和度矩阵系数。降噪必须是亮度边缘引导的保边平滑：平坦区向模糊值收敛
  去噪、边缘权重衰减保细节，RGB 三通道同权重抑制色噪。
- 透视校正必须由 `PerspectiveGeometry` 作为唯一几何真相源：预览 Transform 与
  导出烘焙共用同一 Matrix4 透视核与填充缩放（二分内接测试），禁止预览/导出
  各自构造矩阵形成第二坐标链。
- 滤镜目录必须与整体面板同源：滤镜纯色彩参数走矩阵、细节类参数
  （vibrance/texture/sharpen/structure/highlight/shadow/grain/lightSense）
  走 `ImageEditorDetailSpec` 逐像素管线，禁止折算进 ColorMatrix 冒充；
  滤镜目录小缩略图允许纯矩阵轻量近似（仅供挑选参考，须注明语义）。
  fade（褪色）为显式声明的「黑场抬升 + 轻度去饱和」精确线性实现（白点不动）；
  lightSense（光感）为暗部提亮 + 亮部微压 + 大半径局部对比的
  逐像素 ambiance 真算法，禁止亮度/对比系数拼凑。
- 晕影（vignette）必须是径向平滑衰减的逐像素实现：正值边角压暗、负值
  边角提亮、中心不动、径向单调；走 detail 管线与整体面板同源。
- 白平衡吸管必须与灰世界自动共用同一「中性灰采样 → 温度/色调」反解
  纯函数（与温度/色调正向矩阵互逆），点选采样取邻域平均；禁止吸管
  与自动各自建立第二套解算。

<a id="req-006"></a>
### REQ-006 真实 FilterCatalog 读取与发布职责交接

- `media.image_editor` 的滤镜目录必须由 generated client 经 production Remote 读取当前 active `FilterCatalogRelease`；主路径必须校验 release 身份与 canonical digest，bootstrap、fixture、测试 double 或未绑定当前候选的缓存结果不得冒充该读取成功。
- 编辑器只拥有本地编辑会话、像素烘焙与完成结果交接；媒体上传、`MediaAsset` 生命周期和 `Post` 发布继续由各自对象的公开 command 拥有，编辑器不得直接写入这些事实或把本地文件当作已发布结果。
- 目录不可用、摘要不一致、导出或交接失败时必须保留原图与已确认的编辑历史，提供对同一 Remote 或同一完成动作的可执行重试，并禁止空结果、旧目录或 Toast 冒充成功终态。

## 4. 契约引用

- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/presentation/image_editor_page.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/presentation/image_editor_export_engine.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/presentation/image_editor_curve_models.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/presentation/image_editor_curve_panel.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/presentation/image_editor_mosaic_models.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/presentation/image_editor_text_models.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/presentation/image_editor_step_stack.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/presentation/image_editor_top_bar.dart`
- canonical：`quwoquan_service/services/content-service/contracts/media/filter_catalog_release/operations.yaml#GetActiveFilterCatalog`
- canonical：`quwoquan_service/services/content-service/contracts/media/filter_catalog_release/projections/filter_catalog_slice.yaml#FilterCatalogSlice`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 工具入口零占位，所见工具即真实效果

- GIVEN 用户从图片选择器/相机/创作页进入图片编辑器
- WHEN 用户遍历底部工具栏与专业工具箱的全部入口并逐一确认
- THEN 底部工具栏为滤镜/裁剪/旋转/专业工具/文字/马赛克 6 项；不存在相框入口。
- THEN 专业工具箱为调整图片/局部/HSL/黑白色阶/曲线/白平衡/透视 7 项；不存在修复/色调对比度/魅力光晕占位项。
- THEN 任何面板不出现「操作模版或内容」「即将支持」类占位文案。
- THEN 每个工具确认后当前图片文件被真实烘焙（文件路径变更且像素变化）。

<a id="gwt-002"></a>
### GWT-002 曲线为真实多通道 LUT 编辑器

- GIVEN 用户进入专业工具箱曲线面板
- WHEN 用户切换 RGB/R/G/B 通道、添加/拖动控制点并确认
- THEN 面板展示直方图背景、对角基线与通道曲线；控制点可增删拖动（每通道最多 8 点，端点仅纵向）。
- THEN LUT 由 Fritsch–Carlson 单调插值生成，无过冲；预览与导出使用同一 LUT。
- THEN 确认后图片按曲线烘焙并入撤销栈；取消不产生任何变更。

<a id="gwt-003"></a>
### GWT-003 马赛克与文字为图上实绘图层

- GIVEN 用户进入马赛克或文字工具
- WHEN 马赛克涂抹并确认；文字添加/拖缩旋/样式颜色切换并确认
- THEN 马赛克涂抹路径实时显示对应马赛克效果
- AND 笔画可单步撤销
- AND 确认后全尺寸合成。
- THEN 文字项以图层渲染，选中态可编辑样式（纯色/描边/底纹）与 8 色板颜色，双击重新编辑内容。
- THEN 预览与导出共用同一归一化几何（buildMosaicStrokePath / buildTextPainter）。

<a id="gwt-004"></a>
### GWT-004 全局撤销/重做与放弃保护

- GIVEN 用户完成了至少一步工具确认
- WHEN 用户点击顶栏撤销/重做/记录，或点击 back
- THEN 撤销恢复上一步文件快照
- AND 重做恢复
- AND 新步骤清空重做栈
- AND 历史面板可回退到任一步之前。
- THEN back 弹出破坏性放弃确认
- AND 确认后宿主收到 null 不更新
- AND 无修改时直接退出。
- THEN 顶栏「完成」提交编辑结果并上报 submit 埋点。

<a id="gwt-007"></a>
### GWT-007 细节/分区/颗粒真算法

- GIVEN 一张含边缘与明暗分区的图片进入专业工具整体面板。
- WHEN 用户调节锐化/纹理/结构、高光/阴影或颗粒并确认烘焙。
- THEN 锐化以 unsharp mask 增强边缘对比，远离边缘的平坦区不被全局改变。
- THEN 高光调节只作用亮部像素、阴影调节只作用暗部像素，越区像素逐字节不变。
- THEN 颗粒产生真实噪声方差且同 seed 逐字节可复现；预览与烘焙同一管线不跳变。

<a id="gwt-006"></a>
### GWT-006 HSL 分色相带真算法

- GIVEN 一张含多个色相区域的图片进入专业工具 HSL 面板。
- WHEN 用户只调节某一个色相通道（如橙色饱和度）并确认烘焙。
- THEN 仅该色相带（含 ±10° 平滑过渡）内的像素被调节，非目标带像素逐字节不变。
- THEN 灰阶像素（低饱和度）不被任何通道调节。
- THEN 色相带跨 0°（红带 345°–15°）时环绕两侧均生效。

<a id="gwt-008"></a>
### GWT-008 透视校正预览烘焙同源

- GIVEN 用户进入专业工具箱透视面板。
- WHEN 用户调节水平/垂直透视轴（±30°）并确认烘焙。
- THEN 预览 Transform 与导出烘焙共用 `PerspectiveGeometry` 的同一矩阵构造与
  填充缩放，同参数下角点投影一致，禁止第二坐标链。
- THEN 水平透视使左右边缘沿深度方向产生对称梯形位移，垂直透视同理作用上下
  边缘；填充缩放保证变换后画面完整覆盖原范围框（无露底）。
- THEN 确认后入撤销栈；取消恢复面板打开前的参数。

<a id="gwt-009"></a>
### GWT-009 滤镜目录与整体面板同源

- GIVEN 滤镜目录中的滤镜预设含细节类参数（如 vibrance/锐化/颗粒）。
- WHEN 用户选中滤镜并确认烘焙。
- THEN 滤镜纯色彩矩阵不响应细节类参数（仅含细节参数的滤镜矩阵为恒等）；
  细节类参数经同一缩放导出并走与整体面板同一逐像素管线。
- THEN 含细节参数的滤镜主预览由 CPU 同管线渲染，确认烘焙不跳变；
  纯色彩滤镜继续走 GPU 矩阵。
- THEN fade 满值时黑点精确抬升至 lift×255、白点不动；lightSense 正值提亮
  暗部、亮部只微压，暗部变化大于亮部。

<a id="gwt-005"></a>
### GWT-005 production Remote FilterCatalog 到编辑结果交接

- GIVEN 已认证用户从真实创作入口打开 `media.image_editor`，当前候选存在已激活且摘要可校验的 `FilterCatalogRelease`。
- WHEN App 通过 generated client 与 production Remote 读取 active FilterCatalog，用户应用至少一个目录滤镜和一个本地像素工具后提交完成结果。
- THEN 页面使用同一 release 的目录定义产生真实像素变化，并只把编辑结果交还所属创作流程；编辑器自身不创建 `MediaAsset` 或 `Post` 成功事实。
- AND Remote、目录摘要、导出或交接失败时保留原图与已确认历史，用户可重试同一边界或安全放弃，且 fixture、bootstrap、动态 skip、错误转空与旧 release 不得计为成功。
- AND 本场景只有在同一 commit、ContractGraph、candidate、environment 与真实 Provider 上取得 Android 物理设备及 iPhone 物理设备 `ReadinessResultBundle` 后才计通过；模拟器、Widget-only、blocked、failed 或 skipped 结果均不计。

## 6. 依赖

- 前置要求：[`publish-comment-reaction`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 图片编辑 production Remote 与双物理设备验收

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Data/content media sourceDigest 与发布物当前仍冻结，本场景保持 `WAIT_CONTENT`；尚缺绑定同一候选的 active FilterCatalog production Remote readback、真实创作交接以及 Android/iPhone 双物理设备结果，现有像素 local_contract、Widget 或 App Remote 代码不得替代。
- 完成判定：`GWT-005` 的每条结果均由职责匹配的 production user_acceptance runner 直接 `spec_ref`，且 Android 与 iPhone 物理设备 `ReadinessResultBundle` 绑定同一 commit、ContractGraph、candidate、environment 与真实 Provider 并全部为 passed。

<a id="open-003"></a>
### OPEN-003 滤镜目录 loading/failure 两条 widget 测试存量挂死

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前 `image_editor_filter_catalog__local_contract_test.dart` 的
  「catalog loading keeps filter panel explicit and non-blocking」与
  「catalog failure exposes retry and recovers to canonical presets」两条
  用例存在 10 分钟硬超时的存量挂死；疑因测试用裸 `ProviderScope`（未注入 sealed cloud boundary overrides）使真实 provider 在 fake async 下挂死。
  目录 loading/failure 的行为语义仍由页面实现承载，尚缺可信测试证据。
- 完成判定：两条测试以 sealed overrides 或对象级 typed double 修复后稳定
  通过，且 `GWT-001` 中滤镜目录 loading/失败重试行为被真实测试
  `spec_ref` 绑定。