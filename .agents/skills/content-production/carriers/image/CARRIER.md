# Image · 原生图片作品

本文件唯一拥有作品边界、说明模板与评分；取得来源时只读 [sources 的实际站点小节](sources.md)。

## 输入与作品边界

- 对象身份 `posts/image/<angle>/<title>/<seq>` 与地点关联分开。有可核实地点时，target 指向已发布或同批先发布的真实 homepage；旅行与自然生态摄影无确证拍摄地时，不填写 entityId/entityRef/entityType/region，不造假地点或物种主页，使用既有题材标签。半填地点身份拒绝。候选/选择见 [candidate](schemas/candidate.schema.json)、[selection](schemas/selection.schema.json) 与 [common](../../schemas/common.schema.json)。
- 当前中间字段使用候选 `id` 和 `assets[].id`：命名空间 + 原生作品/资产 ID，不增造 workId 字段，不用标题、日期、列表位置作身份。图虫一个 post、iNaturalist 一个 observation、Pinterest 一个 pin 保持一个候选。
- 一个 image target 显式选一个原生图片作品，选择其中非空、不重复的有序资产子集；选择部分资产时在 relevance 说明取舍。一作品多图不拆成多个对象，不静默截断或合并作品来凑数。
- Commons 每个 File 与 Openverse 每条原作品引用保持独立；同作者同日期不构成合集证明。Flickr photoset 或跨文件合集只有明确作品证据才可按契约处理，当前 adapter 不自动把多个候选合为一个作品。
- 一作品 N 张图构造一个 target、N 条媒体来源与 N 个有序 assetRefs；每张保留各自原来源、许可、署名，不能统一造一个作者或许可。

## 页面识别与原作记录

- 获取方式由宿主据实际页面决定，不按站点写死：识别单图作品、轮播/灯箱、纵向/分页/懒加载相册、发现列表、转载预览及图文混合页面。列表只供发现，推荐卡片不属于当前原作；同一页面不必然同一作品，同一原作跨页也不拆作品。
- 新取得原作使用 selection 的 `sourceWork/sourceWorkEvidence` 保留作品身份、实际响应或明确摘录、取得范围和有序成员，定义只引用 Data 共用 schema。完整响应不等于完整图集；默认取全可采用成员，局部采用说明遗漏原因并保持相对原序，未知不猜为完整。旧未声明记录不补造历史原件。
- 原生成员 ID 与下载 URL 分离；缩略图/高清图是同一成员的不同版本。封面可引用轮播成员而不再插入一图；正文配图保留位置和说明，视频 poster 只绑定视频，参考链接不是下载指令。图标、广告、相关推荐等未采用媒体留在原响应，不进入成品 media；内容主题确实涉及标志时才有据采用，不按尺寸或 SVG 后缀一刀切。
- 实际 byte/sha256、选定成员、原序及用途经过取得、草稿、审核、入仓、分发逐层核对；schema通过不证明已看全图或App连播通过。同一原作多张图片只计一个作品，轮报告分别记录作品数、图片数和多图作品数。

## 选材与观察

- 优先清晰、曝光正常、主体切题的实景摄影，非扫描件/地图/图表/截图。长边约 ≥1600px、长宽比 ≤3:1 是排序建议；更宽全景谨慎选取，默认每实体少量，不扩大准入硬门。
- 下载实际尺寸优先于 API 原图尺寸；图虫下载只有较小版本时如实提示，不因达不到建议尺寸就断言 image 不合法。传输与媒体处理的实际预算仍依 Data 契约。
- 作者 seal 前逐张看原图或足够大的单图预览（通常 ≥1200px），核对画面主体、水印及 title/caption；文件名或地点不能代替主体观察，拼图仅选材。细节不足省略无法判断的描述，必要像素不可读则 blocked。证据中原图、大单图预览与派生图按实际来源、尺寸和处理准确命名，不把放大/派生图称原图。画面与说明不符或主体错绑按素材不相关拒绝，恢复遵循共享 QA 决策。
- 无可靠地点合法，不把全国补点变成强制绑点；半填地点身份仍拒绝。
- `author_signature` 可保留且不得抹除；`platform_logo|stock_agency` 优先换素材，水印本身只记录，不作为新硬门。未观察为 `unknown/unknown`，不能写 null。
- 热度/QI/FP/VI、图虫 favorites/views、Flickr faves 等只排序；author 前与 publish 前均用 canonical inventory 核查。同源作品不新发第二个 image Post；正文/封面复用相同稳定资产不等于新作品。不同 ID 同 SHA/pHash、同 ID 不同字节/来源均拒绝，不用更名或拆图绕过。

## 唯一产物与说明模板

author 只写 `4.draft/image_work.json`：`title`、非空总 `caption`、有序 `assetRefs`，可选真实 `creatorProfileId/tagRefs/assetCaptions`；seal 前核 tagRefs 解析到既有 taxonomy 且与观察主体一致；schema/executionId/objectRef 由 seal 补机械字段。

- 标题：有据地点时写地点 + 画面中可辨识的核心主体/视角；无确证地点只写主体/视角，不猜地点、季节或昼夜。
- 总 caption：作品层面的主体与有据背景；地点、季节、光线、拍摄故事仅在像素或来源确证时写，不伪装作者亲历，不补假地点。
- 逐图 `assetCaptions`：键必须唯一解析到已选择资产，值非空；未给某图说明沿用总 caption。优先用完整 `sources/<unit>/assets/<fileName>` 消歧，同名图片不靠改 description 伪造不同来源。未知引用、未选资产、别名重复由 Data author seal 拒绝。
- `assetRefs` 的顺序即作品顺序，不能因候选重排/文件重名改变。Data 投影只在文件名冲突时按来源资产身份消歧，仍保持权利、来源集合与顺序。

字段契约见 [image_work](../../../../../quwoquan_data/schema/content/image_work.schema.json)。输出 `manifest.assets[].caption`，由 Service `PostMediaItem.caption` 到 App 逐图说明保持同义，不借 title 替代；保存与投影不代表真实 App 验收完成。`adapter.lint` 只提示缺作品说明，不替代像素核查。

## 当前草稿核读与质量纠偏

按[共享 QA 决策](../../references/dispatch.md#qa-整批交总监)核当前草稿 `image_work.json`、来源及每张选用资产的可读像素，核对总说明、逐图说明、顺序与真实原作身份。像素不可读即 blocked，不得 approved；拼图不代替逐图观察。主体/说明矛盾须引用 exact 资产与原句交作者纠正。

“不标未核树种”等生产术语、内部取证限制和审核提示只留在证据中，不进消费者 caption；无法证实的树种、地点和季节直接省略，不把限制说明写成摄影叙述。既有 approved 不代替本轮观察，分数只记录，旧成品问题只点名交修订建议，不覆写历史 review 或换 ID 重发。

QA 对当前标题、总说明与逐图说明未逐段核读不能宣称“无残留”；发现残留须引用 exact 原句，关键词未命中不证明语义无残留，也不能凭旧 approved 或资产可读就替当前文案作保证。

## 六维评分

独立 reviewer 可在唯一 seal.review 输入中给 1–5 整数；2/4 介于锚点间，缺评分不补零，只记录不影响 admission。素材无关等仍按 review 拒绝规则处理。

| 维度键 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- |
| `subject_relevance` | 实体不明或主体杂乱 | 主体明确、实体可辨 | 一眼可辨且主体突出 |
| `technical_quality` | 模糊、过曝/欠曝、噪点重 | 清晰、曝光正常 | 细节/动态范围好、无明显缺陷 |
| `composition_aesthetics` | 随手拍、水平歪斜 | 构图规矩 | 构图讲究、光线出彩 |
| `uniqueness` | 常见打卡机位 | 有一定视角 | 有据的罕见时机/视角，具记忆点 |
| `caption_value` | 只重复标题 | 交代地点及可证场景 | 地点、视角、背景信息充分，季节/故事有据才写 |
| `rights_clarity` | unknown | unverified 但许可原文可读 | verified 且署名清楚 |
### 消费者等级与证据

评分必须引用实际观察的 exact 资产、说明及 rubric 版本；未观察的适用维度保持“未评定”，不得填 `N/A` 或补零。`rights_clarity` 是独立权利轴，不参与内容等级平均，也不表示商业授权。内容等级：D=任一适用内容维度为1；C=无1但有2；B=全部适用内容维度至少3；A=B且核心 `subject_relevance|composition_aesthetics|caption_value` 至少4；S=核心均5、其余适用内容维度至少4且经跨队复核。单队场景不以同队独立 QA 冒充跨队复核；缺少跨队复核证明时不标 S，只记录已证实的分数及满足条件的较低等级与证据缺口。跨队复核仅为 S 等级证据，不新增发布审批、不改变 admission、不改 sealed review；旧对象只读评估，不回写历史审核。硬阻断优先。未知地点不是虚假缺陷，常见机位不自动低质；不得因器材或制作手法加分。
