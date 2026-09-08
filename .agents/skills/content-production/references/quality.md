# 四载体质量评分（草案：只记录、不门禁、定期校准）

评分由 reviewer 在 `seal.review.json` 的每个对象下以 `qualityScores{维度: 1–5 整数}` 与可选 `qualityNotes` 申报，`task seal --stage 5.review` 只校验维度属于该载体闭集并原样透传进 `content_review.json`，publish 原样携带进 `quwoquan_data/publish/**`。评分缺席合法，脚本不补零、不算分、不聚合；评分不改变 `decision`（reject 仍只有三类：关键论断缺证据、安全/隐私、素材不相关或不可播放），不进入 admission、pool eligibility 或 cohort。维度键闭集在 `quwoquan_data/scripts/core/control_types.py::QUALITY_DIMENSIONS_BY_CARRIER` 与 `content_review.schema.json`。

统一分级：1 = 不合格但未触 reject 三类；3 = 合格、可发布、无亮点；5 = 该载体的标杆。2/4 介于其间。

## homepage（实体主页）

| 维度键 | 含义 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- | --- |
| `fact_traceability` | 事实可溯源 | 多处事实在 `source.md` 找不到 | 全部事实可查，个别表述略泛 | 每条事实可逐句对应来源，数字/年代精确 |
| `information_completeness` | 信息完整 | 位置/类型/看点/到达/季节五要素缺 ≥3 | 五要素齐但有一两项只有一句 | 五要素齐且每项对游客决策够用 |
| `structure_clarity` | 结构清晰 | 无分段或 H1 缺失 | H1 + 分段合理 | 分段标题即信息地图，扫读即得 |
| `practical_value` | 实用性 | 只有百科转述，无游客视角 | 有到达/门票/时长中的两项 | 到达、门票、时长、最佳时段、注意事项俱全且具体 |
| `image_relevance` | 配图相关与质量 | 配图与实体无关或明显低质 | 配图切题、清晰 | 配图切题且能代表实体特征，text_only 时按 3 分记 |
| `source_quality` | 来源质量 | 百科正文 < 600 字或无结构化事实 | 正文充实、有信息框 | 正文厚、信息框完整、近期有更新 |

## article（文章）

| 维度键 | 含义 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- | --- |
| `fact_traceability` | 事实可溯源 | 关键论断在来源中找不到 | 事实可查 | 事实可查且多源互证 |
| `originality` | 原创性 | 明显复述来源表达或段落搬运 | 亲笔重述，表达不同于来源 | 有独立组织与观点，来源只作事实 |
| `angle_and_title` | 角度与标题 | 无角度，标题即实体名 | 角度明确、标题点题 | 角度鲜明、标题有吸引力且不夸张 |
| `practical_density` | 实用信息密度 | 路线/时间/费用/贴士全无 | 含两项具体信息 | 路线、时间、费用、贴士俱全且可执行 |
| `readability` | 可读性与结构 | 段落冗长、无小节 | 分段合理、语句通顺 | 节奏好、开头即抓人、结尾有落点 |
| `image_match` | 配图匹配 | 配图与正文无关 | 配图切题 | 配图与段落一一呼应，caption 有信息量；text_only 记 3 |

## image（图片作品）

| 维度键 | 含义 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- | --- |
| `subject_relevance` | 切题与主体明确 | 看不出是该实体或主体杂乱 | 主体明确、可辨识实体 | 一眼可辨实体且主体突出 |
| `technical_quality` | 技术质量 | 模糊、过曝/欠曝、噪点重 | 清晰、曝光正常 | 细节丰富、动态范围好、无明显缺陷 |
| `composition_aesthetics` | 构图与美感 | 随手拍、水平歪斜 | 构图规矩 | 构图讲究、光线出彩 |
| `uniqueness` | 独特性 | 标准打卡机位、随处可见 | 有一定视角 | 罕见时机/视角/季节，具记忆点 |
| `caption_value` | caption 信息价值 | 只重复标题 | 交代地点与季节 | 地点、季节、视角、故事俱全 |
| `rights_clarity` | 权利清晰度 | `unknown` | `unverified` 但 license 原文可读 | `verified` 且署名清楚 |

## video（视频）

| 维度键 | 含义 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- | --- |
| `subject_relevance` | 切题与实体可辨识 | 看不出实体 | 实体可辨识 | 实体为主角且有标志性镜头 |
| `visual_quality` | 画质 | 抖动、模糊、< 720p 观感 | 稳定清晰 | 稳定、曝光准、色彩自然、细节丰富 |
| `editing_rhythm` | 剪辑与节奏 | 开头拖沓、片段不完整 | 开头即景、节奏平稳 | 节奏与内容匹配、有起承转合 |
| `audio_fit` | 音轨适配 | 噪声/无关配乐/突兀口播 | 原声或配乐不干扰 | 音画相得益彰；无音轨时按 3 记 |
| `unique_perspective` | 独特视角 | 常见地面机位 | 有航拍或延时 | 航拍/延时/秘境等罕见视角 |
| `rights_clarity` | 权利清晰度 | `unknown` | `unverified` 但 license 可读 | `verified`（Commons/CC BY）且署名清楚 |

## 校准节律

- 每 5 轮用 `jq` 只读聚合 `quwoquan_data/publish/**/content_review.json`，按载体×维度出分布与均值：

```text
find quwoquan_data/publish -name content_review.json -print0 | xargs -0 jq -c 'select(.qualityScores) | {carrier:(.objectRef|split("/")[0:2]|join("/")), scores:.qualityScores}' | jq -s 'group_by(.carrier) | map({carrier:.[0].carrier, n:length, mean:(map(.scores|to_entries)|flatten|group_by(.key)|map({(.[0].key):((map(.value)|add)/length)})|add)})'
```

- 抽 10 个对象由主会话复评，与 reviewer 分数比对；横向不合理（某 reviewer 系统性偏高/偏低、某维度全 5 无区分度、来源热度与质量倒挂）时修订本文件的锚点与 [sourcing.md](sourcing.md) 的候选级筛选阈值，不改门禁、不改 schema 闭集之外的字段。
- 评分体系在 M1000 收官报告里作为附录定稿；此前一直是草案。

## 修订记录

- 初版：四载体各六维、1/3/5 锚点，随 M1000 放量计划建立；尚无实测分布。
