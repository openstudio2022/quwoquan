# 会话、轮次与恢复

本文件只拥有任务范围、并发、停止与收官约束，不构建共享调度器或完成台账。

## 输入与分片

首次澄清以下决定，未回答的非授权项采用明示默认并写进本轮 `report.md`；范围改变才重新澄清。

| 决定 | 声明式默认 / 边界 |
| --- | --- |
| 主体 | 取现有 creator 注册表旅行博主档；不虚构 creatorProfileId 或亲历人设 |
| 地域与主题 | 必须点名本片地域；实体不限 A 级，类型只取 `Entity/地点/*` 现有叶子；视频可偏河山、航拍、自驾实景 |
| 目标与配比 | 声明四载体目标及 milestone；默认每实体 1 homepage + 1 article + 1–2 image [+ video]，视频可从已有实体补充 |
| 单轮预算 | 新路径先按显式小轮验证；视频默认最多 5 条，原件总预算 ≤2.5GiB，另计转码 staging、迁移与备份峰值；不以预计耗时承诺产量 |
| 并发 | 主会话负责短文本 author，最多一个独立 reviewer 串行；只有宿主已稳定完成调用才启第二个不重叠 author，不嵌套派发 |
| 停止 | 默认单轮放弃比例 40%、连续 2 轮零净增；另声明 maxRounds 与站点请求预算 |
| 耐久与授权 | 确认 `QWQ_PUBLISH_ROOT` 独立内容仓身份、随体/保护副本根与用户指定备份位置，以及提交、finalize/发布等明确授权；默认值不签发授权 |

多省会话由用户启动，不由 Skill 创建 31 个 worker。按 canonical 主归属省分配跨省实体，发现别名后核对类型、行政区与实体身份，不能只拿百科标题做池集合差。协调者分配各站点总预算与错峰时段，单会话预算不得乘以 31；同站请求及共享冲突写点串行，不新建网络调度服务。

`shardId` 是任务范围而非宿主 sessionId；跨会话续跑可复用同 shard，必须保留既有 round。`shard.json` 的 `authorizationNote` 仅引用用户授权；工作区临时 claim 只协调写 scope，不是 workflow 进度或完成依据。

## 工作区与写者

```text
.qwq_output/data/local/workspace/content-production/<shardId>/
  shard.json
  frontier/<carrier>/                 按需复用的发现快照
  rounds/<roundId>/
    round.json                        本轮身份输入
    pool.before.json / pool.after.json
    report.md                         唯一人读收官
    <carrier>/
      candidates.json / selection.json / ingest.json
      seal.acquire.json / seal.author.json / seal.review.json
      sources/<sourceId>/source.md     page 原文；原响应也留在 sources/
      downloads/index.json            下载事实，不是 AI 决策
      preview/                        按资产身份与来源摘要绑定
      cli.log                         命令与实际退出结果
.qwq_output/data/tasks/<executionId>/  CLI 拥有的工作包与 receipts
.qwq_output/data/releases/<releaseId>/ CLI 拥有的 release/handoff
```

候选快照由来源工具单写，选择由 AI 单写；同轮多来源用不冲突快照名，不覆盖原始响应。选择/ingest 一经消费即冻结，改变素材须重建尚未消费输入或新 execution。下载索引只反映真实取得；不用 plan.json、report.json、actors.json、重复 review 输入或 dispatch 快照再包一层。frontier 不保存 completed/used 台账。

execution 内 author 只写其 `4.draft`，reviewer 只写一份 execution 级 seal 判断输入；CLI 单写 receipts 与逐对象 review。execution 原工作包布局不迁移，不等于独立内容仓按地域/分区定位的发布目录；稳定 `entityId/entityRef` 原样跨阶段传递。`QWQ_PUBLISH_ROOT` 显式绑定平级独立 Git 仓（不是源码 worktree、submodule 或 symlink），缺根/错仓阻断；对象的 manifest、采用来源证据与最终媒体随体，terminal cohort/handoff 位于该仓 `releases/<releaseId>/`，旧 `reference/releases` 原件保留。派发输入及身份细则仅在需要派发时读 [dispatch](dispatch.md)。

## 失败与续跑

| 层级 | 处置 |
| --- | --- |
| 候选 | 空正文、消歧失败、无相关素材、不可达或挑战页等换候选；429/503 停止该站本轮剩余请求。候选筛选建议不升级为准入硬门；robots/ToS 或未授权本身不阻断入池 |
| 对象 | 单 target ingest 失败、草稿违规、review rejected 或 publish 闭包失败使对象退轮；记录实际 typed issue，其余对象继续，由有效对象决定 receipt verdict |
| execution | 身份冲突、字节漂移、独立 actor 不成立、seal 链断或零合规产物保持 blocked；补齐只能显式新 execution + retryOf，不回退/重写旧 receipt |
| 目标 | 计数短缺写缺口，不算失败也不算完成 |
| 宿主调用 | 先确认原调用确定失败/终止，再由主会话决定恢复；未能确认就停止派发，不能猜测 provider 状态 |

- `starting up` 不是进度也不是失败，不得据此补发相同或替代调用。启动等待只消费宿主完成/失败通知，不轮询 transcript、不因超时 interrupt；无法确认状态时停止新增派发。
- 已有 receipt 或 reviewer 产物的工作单元不得再次派发。作者已有部分产物时只在原真实 actor 可核验的前提下续写，不能换作者覆盖后冒充同一执行；无法保持归属则保留原件并报告阻断。
- 「池里已存在什么」只读 `release pool-query`；「在飞到哪步」只读 `_shared/receipts/`，找首个未闭合步骤继续。缺 actor 身份不猜模型/provider/runId，不伪造 seal；不从聊天摘要、shard 或 claim 推断闭合。
- 长转码等用宿主工具级后台，遵循宿主等待/完成通知规则；不用 shell `&/nohup`、轮询启动状态或超时自动补发。

## 收官

达到约定计数、前沿耗尽、零净增达上限、轮次/放弃预算耗尽、用户中止或授权不足时结束本轮。只写本轮 `report.md`，六段不可省：

1. 目标与 `pool-query` 实际四载体计数，引用 `pool.before.json/pool.after.json`。
2. 本片新增与复用的 exact objectRefs/publish proof；并行时不以全池净增代本片产量。
3. 放弃的候选/对象、原因及处置层，不另建永久淘汰台账。
4. blocked execution 与首个 typed blocker，保留失败命令/退出码。
5. 未闭合缺口、尚未验证的来源/投影/下游边界。
6. 下一轮最小入口、所需授权及本轮采用的默认与假设。

附本轮评分分布；每 5 轮按 exact objectRefs 与 review digest 分开统计 execution reviewed、published、eligible 三集合，缺评分不补零、不反写已封存产物。保留六维，锚点只维护在载体 `CARRIER.md`；集中得分先查锚点与证据，不强拉分布或凭少量视频归纳普遍结论。耗时分开记录来源请求、下载/转码、作者工作、provider 排队、review 与 publish，未实测项留空。M1000 可附实际来源使用、权利及水印记录分布。

每轮获授权后按 `commit` Skill 在独立内容仓提交 canonical 增量并按授权目标镜像随体媒体；工程 baseline 与内容快照分别绑定，无匹配内容 commit 不冒称已提交，也不强制双提交。在飞输入、原件与来源证据不自动删除；工作区可再生产不等于网络页面或 AI 判断可逐字节重建，删除运行证据即损失该次过程审计。canonical pool、版本化 handoff、仓外 library 与随体媒体不清理。
