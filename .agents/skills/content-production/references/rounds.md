# 轮次、失败处置与收官

本文件只写领域约束：一个轮次是什么、失败怎么放弃、什么时候停、收官必须回答什么。规划、并行、续跑、送审、提交都用宿主原生能力与既有通用 Skill，这里不再实现一遍。

## 澄清一次的决定闭集与声明式默认

| 决定 | 默认值 | 说明 |
| --- | --- | --- |
| 创作主体 | `creatorProfileId` 取 creator 注册表现有旅行博主档 | 缺省时收官报告必须写明「采用默认人设」 |
| 地域与主题范围 | 以维基类目「<省>境内的全国重点文物保护单位」「<省>国家级风景名胜区」为前沿 | 反向从类目选题，不从本地名单撞维基 |
| 里程碑与四载体配比 | 下一级里程碑目标；homepage : article : image 各 1 实体 1 篇，video 独立轮 | 见 [handoff.md](handoff.md) 的目标表 |
| 单轮规模与并行 | 25 实体/轮（25 homepage + 25 article + 25 image），视频 13–15 条/轮；同时 ≤ 3 轮 | 四 execution 各派一个 author 子 Agent |
| 放弃比例上限 | 单轮 40% | 超限即停轮报告，通常意味着前沿质量、来源变更或水印结构性问题 |
| 零净增停机 | 连续 2 轮 `pool-query` 四载体计数无增长 | 说明方法失效，换方法而不是硬跑 |
| 随体媒体落盘 | `QWQ_CARRIED_MEDIA_ROOT` 指向的仓外 durable 根 | 不进 git |
| 授权闸口 | `release finalize` 与任何 git 提交必须等用户明确授权 | 其余动作按本 Skill 自主推进 |

## 一个轮次

固定顺序：discover → init → acquire → author → review → publish → 计数。

- discover：AI 用检索与读页从维基类目反向拉候选，逐个核验条目存在、非消歧义、正文厚度、同条目 Commons 配图；先用 `release pool-query` 做集合差，已发布的实体不再 init。
- init：一份 `round.json` 建本轮全部 carrier execution（见 [steps.md](steps.md)）。
- acquire：每个 execution 的 author 出网取证、下载、写 `source.md`、看图申报水印，再按 execution 提交一份 `ingest.json`；主会话运行 `task acquire` 与 `seal 1.download`。下载节流的实测底线：`upload.wikimedia.org` 对匿名连续下载约 10 个文件（1 秒间隔）后返回 429，且 90 秒退避内不恢复；因此单轮下载按 ≥3 秒间隔、每 8 个文件停 60 秒，收到 429 立即停止本轮下载并把未到手的候选按候选级放弃（原因码 `source_throttled`），不在同一轮内反复重试。
- 视频候选必须先能落到一个已发布或同轮发布的实体：Commons 视频说明常不点名实体（「Pandoj. Ĉengduo」「Temple near Hangzhou」），点不到实体或实体已被永久排除的视频一律候选级放弃；视频轮应从「已有 homepage 的实体」出发反查 `Videos from <地区>`/`Drone videos from China`，而不是从视频出发找实体。
- author：每对象一个 carrier 产物；主会话运行 `seal 4.draft`。
- review：另一会话按 execution 写一份 `reviews`；主会话运行 `seal 5.review`。
- publish：主会话对 approved 对象逐个 `release publish-object`，**homepage 必须先于引用它的 post**，否则 post 在 release 时 `REFERENCE_MISSING`。
- 计数：`release pool-query` 得到当前 eligible 四载体计数，与目标比对。

`verify all` 不进每轮路径，只在 `release finalize` 与提交前跑。

## 失败四层与唯一处置

| 层 | 触发 | 处置 |
| --- | --- | --- |
| 候选级 | 条目不存在、消歧义页、正文过薄、水印为 `platform_logo|stock_agency`、图片与实体无关、来源不可达 | 换候选。零成本放弃、不落台账：判据可重放，再次选题时同一候选会被同一判据再次排除 |
| 对象级 | ingest 单 target 失败、review `rejected`、publish 闭包失败 | 该对象退出本轮，execution 继续；短缺写 typed issue，receipt 仍 `pass` |
| execution 级 | create-once 冲突、字节漂移、author 与 reviewer 同 session/runId、seal 链断 | 该 execution `blocked`，其余 execution 不受影响；补齐只能新建 `executionId` 并在 `round.json` 的 `retryOf` 显式绑定前序 execution，禁止自动派生 |
| 目标级 | 四载体计数不达标 | 不是失败，是账；进收官报告缺口，绝不当作完成 |
| 派发级 | 子 Agent 在写出任何产物前被宿主以确定性错误结束（如 `Model not available`/区域不支持 provider），transcript 只有 prompt 与零到数次 Read，对象目录无产物、无 receipt | 不属 execution 失败：该工作单元没有任何 receipt 或产物，可串行重派**一次**；再失败则由主会话自己担任该 execution 的 author（主会话本就是合法 author actor）。`starting up` 不是此类，不得据此重派 |

只有「人工裁决过的例外」需要记忆（例如某实体被用户明确排除），写入最低可关闭节点的 `OPEN-###` 或 spec，不新造第二状态源。

## 水印判定力度

- image 载体对象逐张看图：它们本身就是产品。
- homepage/article 配图：先看 Commons 侧信号（`Category:Images with watermarks`、`{{Watermark}}` 模板、说明文本提到 signature/logo），再抽样看图。
- video：逐个看抽帧 poster。
- 申报 `watermarkStatus=present` 时必须给 `watermarkKind` 与 `watermarkNote`；`author_signature` 通常可用且不得抹去，`platform_logo|stock_agency` 原则上不进 image 载体。不去水印、不给发布物烧制水印。
- 看图一律看 `ingest.json` 里 `filePath` 指向的**下载原件**，不看 ingest 产出的派生体：超预算图会被降采样成 webp，宿主看图工具解不了 webp，作者与 reviewer 子 Agent 若只拿到派生体路径就只能申报 `unknown`。派发子 Agent 时把原件路径一并给出；原件过大无法打开时由主会话先生成一份 jpg 预览再派发。主会话在选材时对原件的目视即为该资产的水印与相关性判定，写进 ingest 清单后对下游阶段有效。

## 终止条件闭集

命中任一即收官：

1. `pool-query` 四载体计数达到约定目标。
2. 候选前沿耗尽。
3. 连续 N 轮净增为零。
4. 用户中止，或撞上授权闸口（提交、`release finalize`）。

另：单轮放弃比例超过上限即停轮报告。

## 六段收官报告

任一段缺失即收官未完成；计数只从 `pool-query` 读，不从记忆读。

1. 目标 vs `pool-query` 实际四载体计数。
2. 本次新增与复用对象数。
3. 放弃清单：逐条候选或对象 + 原因码 + 处置层。
4. blocked execution 及其首个 typed blocker。
5. 未闭合缺口。
6. 下一轮最小可执行入口（交 `plan-next`）；澄清时采用的默认值与假设逐条列出。

## 续跑

- 「已存在什么」只读 `release pool-query`。
- 「在飞 execution 到哪一步」只读 `.qwq_output/data/tasks/<executionId>/_shared/receipts/`。
- 本会话在飞状态只活在宿主 todos。
- 缺口交 `plan-next`，未完 execution 交 `continue`，送审交 `review`，提交交 `commit`，反复出现的教训交 `distill`。
