# Image · 原生图片作品

本文件唯一拥有作品边界、说明模板与评分；取得来源时只读 [sources 的实际站点小节](sources.md)。

## 输入与作品边界

- 对象身份 `posts/image/<angle>/<title>/<seq>`；target 指向真实实体，引用的 homepage 已发布或同批先发布。候选/选择见 [candidate](schemas/candidate.schema.json)、[selection](schemas/selection.schema.json) 与 [common](../../schemas/common.schema.json)。
- 当前中间字段使用候选 `id` 和 `assets[].id`：命名空间 + 原生作品/资产 ID，不增造 workId 字段，不用标题、日期、列表位置作身份。图虫一个 post、iNaturalist 一个 observation、Pinterest 一个 pin 保持一个候选。
- 一个 image target 显式选一个原生图片作品，选择其中非空、不重复的有序资产子集；选择部分资产时在 relevance 说明取舍。一作品多图不拆成多个对象，不静默截断或合并作品来凑数。
- Commons 每个 File 与 Openverse 每条原作品引用保持独立；同作者同日期不构成合集证明。Flickr photoset 或跨文件合集只有明确作品证据才可按契约处理，当前 adapter 不自动把多个候选合为一个作品。
- 一作品 N 张图构造一个 target、N 条媒体来源与 N 个有序 assetRefs；每张保留各自原来源、许可、署名，不能统一造一个作者或许可。

## 选材与观察

- 优先清晰、曝光正常、主体切题的实景摄影，非扫描件/地图/图表/截图。长边约 ≥1600px、长宽比 ≤3:1 是排序建议；更宽全景谨慎选取，默认每实体少量，不扩大准入硬门。
- 下载实际尺寸优先于 API 原图尺寸；图虫下载只有较小版本时如实提示，不因达不到建议尺寸就断言 image 不合法。传输与媒体处理的实际预算仍依 Data 契约。
- 先用单图/拼图选材，再对选用每张原图或足够大的单图预览确认主体、水印和 caption；通常 ≥1200px，无法获得足够细节就省略无法判断的描述。拼图不用于写最终说明。
- `author_signature` 可保留且不得抹除；`platform_logo|stock_agency` 优先换素材，水印本身只记录，不作为新硬门。未观察为 `unknown/unknown`，不能写 null。
- 热度/QI/FP/VI、图虫 favorites/views、Flickr faves 等只排序；author 前与 publish 前均用 canonical inventory 核查。同源作品不新发第二个 image Post；正文/封面复用相同稳定资产不等于新作品。不同 ID 同 SHA/pHash、同 ID 不同字节/来源均拒绝，不用更名或拆图绕过。

## 唯一产物与说明模板

author 只写 `4.draft/image_work.json`：`title`、非空总 `caption`、有序 `assetRefs`，可选真实 `creatorProfileId/tagRefs/assetCaptions`；schema/executionId/objectRef 由 seal 补机械字段。

- 标题：地点 + 画面中可辨识的核心主体/视角，不猜季节或昼夜。
- 总 caption：作品层面的地点、主体与有据背景；季节、光线、拍摄故事仅在像素或来源确证时写，不伪装作者亲历。
- 逐图 `assetCaptions`：键必须唯一解析到已选择资产，值非空；未给某图说明沿用总 caption。优先用完整 `sources/<unit>/assets/<fileName>` 消歧，同名图片不靠改 description 伪造不同来源。未知引用、未选资产、别名重复由 Data author seal 拒绝。
- `assetRefs` 的顺序即作品顺序，不能因候选重排/文件重名改变。Data 投影只在文件名冲突时按来源资产身份消歧，仍保持权利、来源集合与顺序。

字段契约见 [image_work](../../../../../quwoquan_data/schema/content/image_work.schema.json)。输出 `manifest.assets[].caption`，由 Service `PostMediaItem.caption` 到 App 逐图说明保持同义，不借 title 替代；保存与投影不代表真实 App 验收完成。`adapter.lint` 只提示缺作品说明，不替代像素核查。

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
