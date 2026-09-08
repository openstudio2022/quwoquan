# 轮次、失败处置与收官

本文件只写领域约束：一个轮次是什么、失败怎么放弃、什么时候停、收官必须回答什么。规划、并行、续跑、送审、提交都用宿主原生能力与既有通用 Skill，这里不再实现一遍。

## 澄清一次的决定闭集与声明式默认

| 决定 | 默认值 | 说明 |
| --- | --- | --- |
| 创作主体 | `creatorProfileId` 取 creator 注册表现有旅行博主档 | 缺省时收官报告必须写明「采用默认人设」 |
| 地域与主题范围 | 大陆实体按 [sourcing.md](sourcing.md) 分层前沿开放消费；视频偏壮美河山（川西、新疆、西藏、雪山江河湖海、航拍、全国游）；港澳台只补视频 | 实体口径不限 A 级、不设上限 |
| 里程碑与四载体配比 | 规格底线 M1000 = 1000/1000/1000/100；生产目标四载体各 1000；一个实体产 1 homepage + 1 article + 1–2 image [+ video] | 见 [handoff.md](handoff.md) |
| 单轮规模与并行 | 实体轨 25 实体/轮（25 homepage + 25 article + 25 image）+ 视频轨约 28 条/轮；同时 ≤ 2 轮流水 | 每 execution 各派一个 author 子 Agent 与一个 reviewer 子 Agent |
| 放弃比例上限 | 单轮 40% | 超限即停轮报告，通常意味着前沿质量、来源变更或水印结构性问题 |
| 零净增停机 | 连续 2 轮 `pool-query` 四载体计数无增长 | 说明方法失效，换方法而不是硬跑 |
| 随体媒体落盘与备份 | `QWQ_CARRIED_MEDIA_ROOT` 指向的仓外 durable 根；每轮 rsync 到用户指定备份路径（默认 `~/Backups/quwoquan_golden_media`） | 都不进 git |
| 授权闸口 | `release finalize` 必须等用户明确授权；每轮 `content(data)` 提交需用户事先授予常设授权，否则每轮逐次确认 | 其余动作按本 Skill 自主推进 |

## 一个轮次

固定顺序：discover → init → acquire → author → review → publish → 计数 → 提交与镜像。

- discover：主会话按 [sourcing.md](sourcing.md) 从前沿快照取候选（携程景点榜热度排序 ∪ 维基类目 ∪ 秘境名单），先 `release pool-query` 做集合差，再逐条做候选级质量筛选（百科厚度、配图、游记长度、图片分辨率、视频时长/清晰度/落实体）；已发布的实体不再 init。
- init：一份 `round.json` 建本轮全部 carrier execution（见 [steps.md](steps.md)）。
- acquire：默认由主会话批量完成——API 响应落文件、`jq` 生成 ingest 行、通用工具落盘 `source.md`、合规 UA 串行下载、看原件申报水印；视频 execution 的下载与 `task acquire`（含转码）放后台 shell。主会话运行 `task acquire` 与 `seal 1.download`。author/reviewer 子 Agent 在跑时，主会话即开始下一轮的 discover 与 acquire（双轮流水）。
- author：每 execution 派一个 author 子 Agent，提示词内嵌：execution 根绝对路径、对象与来源清单、允许的 tagRefs 闭集、`creatorProfileId`、原件图片路径、「一条 shell 批量 cat 来源，读一个写一个」的节律、不运行 CLI/不出网/不改来源。主会话运行 `seal 4.draft`；违规对象由 seal 以 typed issue 退轮，不阻塞其余。
- review：每 execution 派一个 reviewer 子 Agent（与该 execution 的 author 不同会话；不同 execution 的 reviewer 并行），提示词内嵌：只评 `002-4.draft` resultRefs 里的对象、批量 cat 读产物、关键论断回查 `source.md`、image 看原件、video 看 poster、按 [quality.md](quality.md) 六维打分、只写一份 `seal.review.json`。主会话运行 `seal 5.review`。
- publish：主会话对 approved 对象用一条 shell 循环逐个 `release publish-object`，**homepage 必须先于引用它的 post**，否则 post 在 release 时 `REFERENCE_MISSING`。
- 计数：`release pool-query` 得到当前 eligible 四载体计数，与目标比对。
- 提交与镜像：按 `commit` Skill 提交 `quwoquan_data/publish/**`（`content(data): 内容池增量 rNN`），随后 `rsync -a ~/.local/share/quwoquan/golden_media/ <备份路径>/`。

`verify all` 不进每轮路径，只在 `release finalize` 与提交前跑。

## 视频候选必须先落实体

Commons 与 YouTube 的说明常不点名实体（「Pandoj. Ĉengduo」「Temple near Hangzhou」「新疆自驾十天」）；点不到实体或实体已被永久排除（OPEN-021）的视频一律候选级放弃；多实体线路视频落主实体。视频轮从「已有 homepage 的实体」与本轮 T1 实体出发反查，而不是从视频出发找实体。

## 失败四层与唯一处置

| 层 | 触发 | 处置 |
| --- | --- | --- |
| 候选级 | 条目不存在、消歧义页、正文过薄、游记过短/软广、图片分辩率不足或 `platform_logo|stock_agency` 水印、图片与实体无关、视频非实景或落不到实体、来源站点 robots/ToS 禁止、来源不可达或 429/503 | 换候选。零成本放弃、不落台账：判据可重放，再次选题时同一候选会被同一判据再次排除 |
| 对象级 | ingest 单 target 失败、4.draft 产物违规（`DATA.SEAL.DRAFT_INVALID`）、review `rejected`、publish 闭包失败 | 该对象退出本轮，execution 继续；短缺写 typed issue，receipt 仍 `pass` |
| execution 级 | create-once 冲突、字节漂移、author 与 reviewer 同 session/runId、seal 链断、零合规产物 | 该 execution `blocked`，其余 execution 不受影响；补齐只能新建 `executionId` 并在 `round.json` 的 `retryOf` 显式绑定前序 execution，禁止自动派生 |
| 目标级 | 四载体计数不达标 | 不是失败，是账；进收官报告缺口，绝不当作完成 |
| 派发级 | 子 Agent 在写出任何产物前被宿主以确定性错误结束（如 `Model not available`/区域不支持 provider），transcript 只有 prompt 与零到数次 Read，对象目录无产物、无 receipt | 不属 execution 失败：该工作单元没有任何 receipt 或产物，可串行重派**一次**；再失败则由主会话自己担任该 execution 的 author（主会话本就是合法 author actor）。`starting up` 不是此类，不得据此重派 |

只有「人工裁决过的例外」需要记忆（例如某实体被用户明确排除），写入最低可关闭节点的 `OPEN-###` 或 spec，不新造第二状态源。

## 水印判定力度

- image 载体对象逐张看图：它们本身就是产品。
- homepage/article 配图：先看来源侧信号（Commons `Category:Images with watermarks`、`{{Watermark}}` 模板、说明文本提到 signature/logo；Flickr 说明与标签），再抽样看图。
- video：逐个看抽帧 poster；二传平台烫印（抖音/快手 logo）按 `platform_logo` 候选级排除。
- 申报 `watermarkStatus=present` 时必须给 `watermarkKind` 与 `watermarkNote`；`author_signature` 通常可用且不得抹去，`platform_logo|stock_agency` 原则上不进 image 载体。不去水印、不给发布物烧制水印。
- 看图一律看 `ingest.json` 里 `filePath` 指向的**下载原件**，不看 ingest 产出的派生体：超预算图会被降采样成 webp，宿主看图工具解不了 webp。派发子 Agent 时把原件路径一并给出；原件过大无法打开时由主会话先生成一份 jpg 预览再派发。主会话在选材时对原件的目视即为该资产的水印与相关性判定，写进 ingest 清单后对下游阶段有效。

## 终止条件闭集

命中任一即收官：

1. `pool-query` 四载体计数达到约定目标。
2. 候选前沿耗尽。
3. 连续 N 轮净增为零。
4. 用户中止，或撞上授权闸口（`release finalize`、未获常设授权的提交）。

另：单轮放弃比例超过上限即停轮报告。

## 六段收官报告

任一段缺失即收官未完成；计数只从 `pool-query` 读，不从记忆读。

1. 目标 vs `pool-query` 实际四载体计数。
2. 本次新增与复用对象数。
3. 放弃清单：逐条候选或对象 + 原因码 + 处置层。
4. blocked execution 及其首个 typed blocker。
5. 未闭合缺口。
6. 下一轮最小可执行入口（交 `plan-next`）；澄清时采用的默认值与假设逐条列出。

附录：本轮 `qualityScores` 按载体×维度的分布（[quality.md](quality.md) 的聚合命令）；每 5 轮做一次校准并记录锚点修订。

## 续跑

- 「已存在什么」只读 `release pool-query`。
- 「在飞 execution 到哪一步」只读 `.qwq_output/data/tasks/<executionId>/_shared/receipts/`。
- 本会话在飞状态只活在宿主 todos。
- 缺口交 `plan-next`，未完 execution 交 `continue`，送审交 `review`，提交交 `commit`，反复出现的教训交 `distill`。
