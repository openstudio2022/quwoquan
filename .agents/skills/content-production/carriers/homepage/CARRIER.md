# Homepage · 实体主页

本文件唯一拥有主页模板、加工与评分；仅取来源时读 [sources 的实际站点小节](sources.md)。共享命令按需见 [pipeline](../../references/pipeline.md#输入与-init)。

## 输入与产物

- 稳定身份由调用方显式声明的 `entityId`/`entityRef` 冻结，不按名称路径、物理目录或维基标题派生；target 为 `carrier=homepage` 加 `entityType/name/region` 与上述身份，作者 seal 前核对类型、行政区与 tagRefs 均解析到既有 taxonomy。execution 物理叶子只取 `entityRef` 摘要以隔离同名实体，不等于业务 ID，也不等于内容仓地域/分区 locator。先读 pool-query 的 occupied、eligible 与 invalid/excluded，合并 manifest/record 实际身份消歧；无效但占用的身份不能再次创建，也不算已完成。
- 候选/选择遵循 [candidate](schemas/candidate.schema.json)、[selection](schemas/selection.schema.json) 与 [common](../../schemas/common.schema.json)。sources 中恰有一个 `role=primary`，必须是 `wikipedia|baidu_baike|toutiao_baike` 的 page；其它同实体百科可为 supplement，配图为 media。脚本只校验结构，不用 confirmed 布尔替 AI 证明实体正确。
- 唯一 author 产物 `4.draft/page.md`；frontmatter 可声明 `title/tagRefs/creatorProfileId`，正文 H1 为实体名。多百科新产物显式写 `primarySourceRef: sources/<unit>/source.md`，取自本对象已取得的 `1.download/source_refs.json`，不是 candidateId、URL 或工作区路径。Data author schema/seal 拥有绑定校验，来源排列与 selection role 不自动替代该声明。
- publish 写入独立内容仓对象包：`manifest.json` 单写身份、结构化实体事实、正文引用与有序媒体/依赖，最终正文为 `page.md`，采用来源进 `sources/`，媒体（有则）进 `media/`，审核原件与追加式 `records/` 保留；不再生成 `_entity.json` 旁车。primarySourceRef 绑定的实体头、包内主源与正文归属须一致。字段契约见 [homepage_author](../../../../../quwoquan_data/schema/content/homepage_author.schema.json)。

## 候选与加工

- 主页主源顺序只由 [sources](sources.md#主源顺序与交叉核实) 拥有，homepage 至少一个实际百科 page；名单与校验支持不证明已实现采集。首句、对象类型、行政区、别名与信息框交叉核对，排除同名人物/异地实体/消歧页。
- 正文约 ≥600 字、有信息框或 ≥3 条结构化事实者优先；这是候选质量建议，不是新增长度门。携程热度、点评数、pageviews 只排序；有切题清晰配图优先，0 张合法为 text_only。
- 缺到达/门票/开放/季节等事实时定点补查同实体百科或公开官方事实，保留来源与取得时点；不扩张百科主源闭集。多源冲突或时效不明就留缺口，不把最新网页等同最新事实。
- 只补游客决策需要的事实：不复制百科长文，不堆尺寸流水、名单或传说。历史只保留与看点直接相关的事实，不能把传闻写成确定事实。全国覆盖用官方名单、非评级与长尾入口，不把知名景区重复增产当覆盖完成。已发布事实或行政区错误走同身份新版，不另造实体。
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

## 当前草稿核读与质量纠偏

按[共享 QA 决策](../../references/dispatch.md#qa-整批交总监)核读当前草稿、实际采用来源与必要配图；缺观察即 blocked，不得 approved。本域重点核地点身份、行政区与景区类型；已确认的地理/到达矛盾须引用原句与来源交作者纠正，不能用“现场为准”代偿。

不能只因身份清楚就给 `practical_value` 高分：概览、看点及有据决策信息须落在实际正文，不能把充实来源压成空泛入口。生产术语、取证限制和评分提示留在内部证据，不进入读者正文；没有来源的栏目省略，不为质量建议补造事实。

QA 对当前标题与正文未逐段核读不能宣称“无残留”；发现残留须引用 exact 原句，关键词未命中不证明语义无残留，也不能凭旧 approved 或栏目齐全就替当前文案作保证。

## 六维评分

独立 reviewer 在唯一 `seal.review.json` 中填 1–5 整数，2/4 介于锚点之间；只记录，不决定 admission，缺评分不补零。关键论断缺证据仍按 review 三类拒绝处理，不以低分代替。

| 维度键 | 1 分 | 3 分 | 5 分 |
| --- | --- | --- | --- |
| `fact_traceability` | 多处事实不能在来源定位 | 事实可查，个别表述略泛 | 可逐句对应，数字/年代精确 |
| `information_completeness` | 游客理解实体所需的关键事实缺失，难以形成判断 | 有据回答该实体的关键问题，仍有决策信息缺口 | 关键问题得到充分回答，适用条件和已知缺口清楚；无来源槽位不硬凑 |
| `structure_clarity` | 无分段或 H1 缺失 | H1 与分段合理 | 标题即信息地图，扫读可得 |
| `practical_value` | 空泛百科转述，不能支持游客判断 | 以有据事实回答游客的具体决策问题，不按栏目计数 | 看点取舍与实际决策信息具体有据，适用条件和时效清楚，可支持选择或行动 |
| `image_relevance` | 配图明显低质或不切题 | 切题清晰；text_only 记 3 | 准确代表实体特征且画质好 |
| `source_quality` | 采用来源对关键事实无支持，或实体、时效不匹配 | 采用来源与正文事实相关、可追溯，必要时效可查 | 关键事实有可靠来源支持，必要处交叉核实且冲突与时效清楚；不按信息框或栏目齐全加分 |
### 消费者等级与证据

评分必须给出 exact 段落、来源或资产理由及 rubric 版本；未实际观察的适用维度是“未评定”，不得填 `N/A` 或补零。权利清晰度单列，不与内容质量求平均。运营等级只作独立质量读回：D=任一适用内容维度为1；C=无1但有2；B=全部适用内容维度至少3；A=B且核心维度 `fact_traceability|information_completeness|practical_value` 至少4；S=核心均5、其余适用维度至少4且经跨队复核。单队场景不以同队独立 QA 冒充跨队复核；缺少跨队复核证明时不标 S，只记录已证实的分数及满足条件的较低等级与证据缺口。跨队复核仅为 S 等级证据，不新增发布审批、不改变 admission、不改 sealed review；旧对象只读评估，不回写历史审核。任何硬阻断优先于等级，高分不能抵消。高分不奖励字数、信息框或栏目齐全；核心是来源真实支持且游客问题得到回答。
