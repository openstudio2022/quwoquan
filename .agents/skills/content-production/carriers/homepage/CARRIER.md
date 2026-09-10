# Homepage · 实体主页

本文件唯一拥有主页模板、加工与评分；仅取来源时读 [sources 的实际站点小节](sources.md)。共享命令按需见 [pipeline](../../references/pipeline.md#输入与-init)。

## 输入与产物

- 身份是 `entities/<域>/<类型>/<名称>`；target 为 `carrier=homepage/entityType/name/region`，类型与行政区须解析到现有 taxonomy。先读 pool-query 的 occupied、eligible 与 invalid/excluded，合并 manifest/record 实际身份消歧；无效但占用的身份不能再次创建，也不算已完成，不以维基标题或目录末段替代实体身份。
- 候选/选择遵循 [candidate](schemas/candidate.schema.json)、[selection](schemas/selection.schema.json) 与 [common](../../schemas/common.schema.json)。sources 中恰有一个 `role=primary`，必须是 `wikipedia|toutiao_baike` 的 page；其它同实体百科可为 supplement，配图为 media。脚本只校验结构，不用 confirmed 布尔替 AI 证明实体正确。
- 唯一 author 产物 `4.draft/page.md`；frontmatter 可声明 `title/tagRefs/creatorProfileId`，正文 H1 为实体名。多百科新产物显式写 `primarySourceRef: sources/<unit>/source.md`，取自本对象已取得的 `1.download/source_refs.json`，不是 candidateId、URL 或工作区路径。Data author schema/seal 拥有绑定校验，来源排列与 selection role 不自动替代该声明。
- publish 生成 `_entity.json + page.md + manifest.json` 及必要闭包；primarySourceRef 绑定的实体头、source_catalog 主源与正文归属须一致。字段契约见 [homepage_author](../../../../../quwoquan_data/schema/content/homepage_author.schema.json)，不建旁车文件。

## 候选与加工

- 维基优先作事实骨架但非必需；缺条目或信息薄可用头条百科，homepage 至少一个实际百科 page。首句、对象类型、行政区、别名与信息框交叉核对，排除同名人物/异地实体/消歧页。
- 正文约 ≥600 字、有信息框或 ≥3 条结构化事实者优先；这是候选质量建议，不是新增长度门。携程热度、点评数、pageviews 只排序；有切题清晰配图优先，0 张合法为 text_only。
- 缺到达/门票/开放/季节等事实时定点补查同实体百科或公开官方事实，保留来源与取得时点；不扩张百科主源闭集。多源冲突或时效不明就留缺口，不把最新网页等同最新事实。
- 只补游客决策需要的事实：不复制百科长文，不堆尺寸流水、名单或传说。历史只保留与看点直接相关的事实，不能把传闻写成确定事实。
- 配图逐项确认实体与用途，地图、旗徽、同名异地图片不能冒充实景。配图取证与水印按共享 sourcing；封面可复用的范围由 canonical inventory 决定，不扩张跨 Post 去重规则。

## 移动端模板

目标 400–800 字，短段落、易扫读；仅填有来源的槽位，空章节省略，不补造交通、票价、开放时间或季节。模板/长度 lint 全为 advisory。

| 顺序 | 段名 | 内容 |
| --- | --- | --- |
| H1 | 实体名 | 真实 canonical 名称 |
| H2 | 概览 | 是什么、在哪里、值得去的核心理由 |
| H2 | 看点 | 2–4 个有据特色，突出游客能看到/体验什么 |
| H2 | 到达 | 外部交通与有据的内部交通/步行提示 |
| H2 | 门票与开放 | 已核实的价格、时段、预约与适用条件；时效不明省略 |
| H2 | 季节与贴士 | 有据的季节特点、注意事项，不编造“最佳光线” |
| 可选 H2 | 历史 / 参见 | 与游览有关的简短历史或可回查关联 |

`adapter.lint` 提示陌生段名、缺概览、空节与总文本超过 800；它不会生成内容、判断事实或要求所有槽位齐全。

## 六维评分

独立 reviewer 在唯一 `seal.review.json` 中填 1–5 整数，2/4 介于锚点之间；只记录，不决定 admission，缺评分不补零。关键论断缺证据仍按 review 三类拒绝处理，不以低分代替。

| 维度键 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- |
| `fact_traceability` | 多处事实不能在来源定位 | 事实可查，个别表述略泛 | 可逐句对应，数字/年代精确 |
| `information_completeness` | 位置/类型/看点/到达/季节缺 ≥3 | 要素基本齐，部分简略 | 各项对游客决策够用；缺来源不硬凑 |
| `structure_clarity` | 无分段或 H1 缺失 | H1 与分段合理 | 标题即信息地图，扫读可得 |
| `practical_value` | 只有百科转述 | 到达/门票/时长中有两项 | 到达、门票、时长、时段、注意事项具体有据 |
| `image_relevance` | 配图明显低质或不切题 | 切题清晰；text_only 记 3 | 准确代表实体特征且画质好 |
| `source_quality` | 正文薄或无结构化事实 | 正文充实、有信息框 | 信息充分、结构化事实完整且时效可查 |
