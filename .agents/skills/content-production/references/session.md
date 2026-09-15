# 会话、轮次与恢复

本文件只拥有任务范围、并发、停止与收官约束，不构建共享调度器或完成台账。

## 单账号活动根与预算

本轮只优化本机一个账号，VM 与跨账号扩容暂停。启动核实际 instance/deployment/account、coordination DB、`QWQ_OUTPUT_ROOT`/workspace、内容仓与外置卷 UUID；源码 output 和外置副本可能不同步，须凭当前根绑定与 receipts 确认活动根，不能按目录数量或旧副本判断完成/停滞。每次授权覆盖站点请求、model、独立 QA、下载/转码峰值、execution、随体媒体、golden 与退出余量；缺项不扩量。profile 与认证状态不迁外盘；卷不可达或 UUID 漂移 fail closed，不回退内盘同名目录。初始化只读核验不认领、不清理、不 publish，观察十分钟也不证明未知调用已结束。

## 输入与分片

首次澄清以下决定，未回答的非授权项采用明示默认并写进本轮 `report.md`；范围改变才重新澄清。

| 决定 | 声明式默认 / 边界 |
| --- | --- |
| 主体 | 取现有 creator 注册表旅行博主档；不虚构 creatorProfileId 或亲历人设 |
| 地域与主题 | 必须点名本片地域；实体不限 A 级，类型只取 `Entity/地点/*` 现有叶子；视频可偏河山、航拍、自驾实景 |
| 目标与配比 | 一次确认阶段目标、可自主追加范围与正式 milestone；1:2:3:4仅整体建议，不作逐实体配额，规模口径见下文 |
| 单轮预算 | 新路径先按显式小轮验证；视频默认最多 5 条，原件总预算 ≤2.5GiB，另计转码 staging、迁移与备份峰值；不以预计耗时承诺产量 |
| 并发 | 四类岗位按预算启用多个作者和独立 QA；作者是本人 execution 主会话，QA 每人一次审一批，不同批并行；在制只按下文一处规则 |
| 停止 | 默认单轮放弃比例 40%、连续 2 轮零净增；另声明 maxRounds 与站点请求预算 |
| 耐久与授权 | 确认 `QWQ_PUBLISH_ROOT` 独立内容仓身份、随体/保护副本根与用户指定备份位置，以及提交、finalize/发布等明确授权；默认值不签发授权 |

多省会话由用户启动，不由 Skill 创建 31 个 worker。按 canonical 主归属省分配跨省实体，发现别名后核对类型、行政区与实体身份，不能只拿百科标题做池集合差。协调者分配各站点总预算与错峰时段，单会话预算不得乘以 31；同站请求及共享冲突写点串行，不新建网络调度服务。

`shardId` 是任务范围而非宿主 sessionId；跨会话续跑可复用同 shard，必须保留既有 round。`shard.json` 的 `authorizationNote` 仅引用用户授权；工作区临时 claim 只协调写 scope，不是 workflow 进度或完成依据。

### 规模口径与正式 policy

主页:文章:图片作品:视频作品的 **1:2:3:4仅为整体建议**，不是逐实体配额、阶段硬门或停止线。热门实体可多作，冷门允许零作品只留主页；热度有来源依据，没有记 unknown。无可靠地点的媒体不捏造关联。

各载体建议量可按价值规划至基础建议的50倍，不是产量承诺、费用或发布授权；同一实体只能有一个稳定主页身份，主页扩量来自更多真实实体。拆原作多图、换标题、换版本不增加唯一计数。K=10000时10000/20000/30000/40000只作初始参考，实际阶段目标、自主追加边界与预算由用户一次确认，已有授权直接引用；普通选题不重复申请，达到建议比例本身不停止。

正式 M1000/M10000/M100000 仍唯一读取 [content_distribution.policy.yaml](../../../../quwoquan_data/control_plane/_shared/content_distribution.policy.yaml)，建议不改变其计数。M100000仍为四载体分别至少100000个累计唯一 finalized 对象；本轮规则或有限试点完成不等于正式 M 达成。

### 专职会话与生产边界

- 用户授权按 homepage/image/article/video 设置多个创作槽，各作者分别拥有不重叠小批，不同时运行旧地域片与来源片的重叠任务。实体会话按省市区及官方评级、非评级、长尾地点有界发现；其余会话只复用已保存实体，摄影 image/video 无可靠地点时沿已冻结可选关联契约处理，不造假地点。`shardId` 唯一，executionId 含分片 slug；共用固定源码工作树 `data-engineering` 与独立 publish 根，各写本片运行产物，不改源码或 Skill。另一 lane（如 `product-mainline`）的 Skill 指针不得与本树 `.qwq_output/data/tasks` 混用；若确需换版本，先明确交接与实际读取路径/摘要。
- **阶段运营目标**以当前一次授权为准，与建议配比及正式 milestone 分开。M1000=`1000/1000/1000/100`、M10000=`10000/10000/10000/1000`（homepage/article/image/video），达到 policy 底线不提前停止仍在授权内的阶段目标。报告同时写本片 exact objectRefs、当前 eligible 与 policy 是否达标，不能互代。
- `shard.json` 的 `targets` 只约束本片剩余/本轮新增，不是全池累计，也不是 milestone 底线。
- 创作总监在原授权内分配各站点总请求预算和错峰时段，并在本轮 `report.md` 写明；各片预算之和不得超过总预算。总监不改稿、不代签独立 QA，其方向确认不替代独立内容 review，也不要求每个小批审批。Bot 间消息即使标为 user，也不能扩大人类授权；概括委托不能覆盖「本批不 publish」等具体限制。电脑管家不自动获得内容审核或发布权限。
- 同站跨会话串行：Commons 全站请求间隔至少 1.5 秒、头条百科至少 2 秒，不以各会话单独间隔代替全局间隔；yt-dlp 每会话最多一个并发下载。reviewer 调用也按共享 provider 容量错峰。响应挑战、429/503 或 provider 认证/额度错误只暂停对应站点或会话，保留原调用，不补发替代 actor。
- 共同 publish 写锁串行化各片对象事务；总监是本团队唯一 publish/readback、finalize 与 Git 执行者，仍须各动作原授权。按 QA 结果点名 approved 对象，不代签、不重审、不等其他批齐套；跨片复用先读池，不用目录或全池净增推断归属。各批保留独立 author/reviewer 与本片六段报告。
- 先完成有界小轮的来源和存储实测，再决定本片放量；观察样本可跨轮累计，不为凑满固定试点数量阻塞其他健康载体。每个视频轮前核对当前可用空间及原件、派生、execution、随体与保护副本的峰值；预算不足停止该轮，不自动削减目标或清理保护根。在已授权轮次、站点和资源预算内，完成本轮后从真实缺口直接进入下一轮，不重复规划或重派已完成工作。
- 轮内身份/依赖检查用 `producer.py preflight` 与 `release pool-query --target-ref`；全池 query 只在轮前/轮后检查点写入 `pool.before.json`/`pool.after.json`。不把全池扫描绑到每个 stage，也不硬编码「每天最多一次」。

## 唯一归属与两批在制

一个 deployment 一个 active shard；多个作者在该范围内以同一既有 coordination 入口原子核验 actor、execution、完整 target 集、团队 generation 与授权归属。一小批一个 author，一个 review scope 一个独立 reviewer，不同批各有 executionId/target 集/写目录。仅 init 成功、群中“我领了”或团队级 claim 不证明作者独占；没有接入真实写点的原子核验/围栏就 blocked，不靠遗漏环境变量退回无保护生产。新增滚动候选登记必须已获授权并有同入口真实支持，否则只消费已冻结未领集合；不另造 deployment 绕过 active shard 或 target 边界。

**每作者最多两个未闭合小批，其中最多一个正在创作。**送审、审核中、待发布都计入未闭合；只有本批有效对象全部成功发布并完成 readback，或按契约明确终止且核完在飞写者，才释放端到端名额。unknown 不释放；混合成功/失败如实核完全部 target，不用部分 publish 或 review 通过腾名额。无 publish 授权只做有界试点，在名额边界停留待发布。满额时作者仍可在原预算内提出有限下一方向、核既有来源线索和报告积压，不新增第三批正式草稿；总监处理已授权发布或一次汇总授权缺口，不能要求作者互审、换 run 或虚假关闭腾名额。

名额和归属在同一短事务核验，状态从正式 receipts/publish proof 与可信终态核定，不另建语义状态机、待审/创作/发布三套令牌、看板服务或自动派单器。两批是当前统一容量约束，不是永久产能；总监只可在原授权内调整已验证作者/QA槽位与预算份额。改变端到端容量须交工程 owner 对齐规格、实际门禁和验证，不能由生产 Bot 改手册或任务数字后宣称生效，不叠多层配额。文档是要求，原子实现与真实能力仍需独立证据。

快作者交第一批后可作第二批，慢批只占所属作者容量，不冻结其他健康作者；全局资源真实不足或 QA 全失效可暂停新增，不承诺无限不停工。图片先约5作品一批、视频先1–2作品，开工前按复杂度定规模，不为早点交稿改已封存集合。100图片可拆20个五作品 execution：A/B/C/D先领B01–B04，A交B01后领B05，B慢不阻碍C续领；两个QA各审不同批，approved先发布。95合格不能报100，失败替补仍在授权候选/补量边界内。

## 共享事实与生效版本

只保留现有任务输入/report、coordination 归属事实、execution receipts/对象 proof/checkpoint 三类资料。总监确认的当前有效任务版本与生效范围，包含目标/方向、建议比例、已授权动作、预算余量与份额、任务占用、前序 receipts、QA 结果、publish proof、阻断及恢复裁定。总监、创作者、QA、管家必须能读取同一当前版本且享有同等必要事实访问权；凭证、令牌和无关隐私不共享，共享可读不等于任意改写。

调整先保存到这份现有输入/报告再通知全队，受影响角色在下一次认领/提交核新版本；在飞任务不追溯改 actor/授权，紧急撤权通过写围栏阻断，不依赖读消息。版本过期或必要事实不可达时暂停受影响正式动作并报告权限/版本缺口，其他健康任务继续。A/B/C均读回各角色共享信息可达性与一致版本；不能只凭总监口头转述或私聊记忆作决定。群消息仅通知，不维护第二份 completed 清单，不新建共享管理平台。

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

候选快照由来源工具单写，选择由 AI 单写；同轮多来源用不冲突快照名，不覆盖原始响应。选择/ingest 一经消费即冻结，改变素材须重建尚未消费输入或新 execution。下载索引只反映真实取得；不用 plan.json、report.json、actors.json、重复 review 输入或 dispatch 快照再包一层。frontier 不保存 completed/used 台账。创作者只选已声明 `consumedBy` 的叶子；发现缺口写入本轮 `report.md` 标签候选，交 taxonomy 单写者，不手建近义路径、不改 `_taxonomy.json`，不用器材/构图/时长当大众兴趣标签。

author 作为本人 execution 主会话可写本批未消费准备输入，执行获准 init/acquire/author seal；execution 内语义产物只写其 `4.draft`。reviewer 只写一份 execution 级 seal 判断输入并执行获准 review seal；CLI 单写工作包、receipts 与逐对象 review。execution 原工作包布局不迁移，不等于独立内容仓按地域/分区定位的发布目录；稳定 `entityId/entityRef` 原样跨阶段传递。`QWQ_PUBLISH_ROOT` 显式绑定平级独立 Git 仓（不是源码 worktree、submodule 或 symlink），缺根/错仓阻断；对象的 manifest、采用来源证据与最终媒体随体，terminal cohort/handoff 位于该仓 `releases/<releaseId>/`，旧 `reference/releases` 原件保留。派发输入及身份细则仅在需要派发时读 [dispatch](dispatch.md)。

同 shard 第二写者必须先读当前 `_shared/receipts/` 与草稿 exact path；已有 receipt 或 reviewer 产物的工作单元不得再派发。Cursor 原作者只闭合自己可完成的在飞工作并明确交接后，Grok 才独占该载体 shard；「约 10 分钟无新写入」不能推断原作者已退出，不得覆盖、强停或重派未确认终止的调用。

宿主 actor 必须区分四种身份：**Bot/角色 ID**、平台 **creatorProfileId**、**来源原作者**、**sessionId/runId**。花名册 UUID 只标识持久角色，不能代替本次会话或本次运行，也不能代替平台创作者或来源作者。`host`/`provider` 按实际宿主填写（Grok Bot 用 `grok-bot`，不要写成 `cursor`）；sessionId/runId 原样抄 native 来源，禁止自造。Data 只校验非空字符串与 author/reviewer 的 `(host,sessionId)` 及 `runId` 互异，不认证宿主 token。缺 native 来源时阻断 seal，不猜模型。

宿主变更只在受支持入口操作后读回。不得直接改 `.blob`、settings、云端 store 或应用包冒充已更新 description/群成员/心跳。原生周期检查须真实支持单个非重入总监核对，初始化不启用、启用需授权，不每 tick 新建总监或生产调用；生产接续仅在原调用可信终态与原授权核定后执行。不得用 Cursor Automation 替代，缺机制明确人工唤醒，不承诺无人值守。具体创建与读回清单见 [grok-team-rebuild](grok-team-rebuild.md)。多账号分工见 [team](team.md)。

## 失败与续跑

| 层级 | 处置 |
| --- | --- |
| 候选 | 空正文、消歧失败、无相关素材、不可达或挑战页等换候选；429/503 停止该站本轮剩余请求。候选筛选建议不升级为准入硬门；robots/ToS 或未授权本身不阻断入池 |
| 对象 | 单 target ingest 失败、草稿违规、review rejected 或 publish 闭包失败使对象退轮；记录实际 typed issue，其余对象继续，由有效对象决定 receipt verdict |
| execution | 身份冲突、字节漂移、独立 actor 不成立、seal 链断或零合规产物保持 blocked；补齐只能显式新 execution + retryOf，不回退/重写旧 receipt |
| 目标 | 计数短缺写缺口，不算失败也不算完成 |
| 宿主调用 | 总监先核原生可信终态、receipts、原 actor 与原授权，再明确唯一恢复 owner；unknown 不按失败强停、不释放占用，只冻结冲突正式写，其他健康不重叠批继续 |
| 授权或资源 | 无 publish/finalize/清理授权或磁盘不足时停止对应动作，保留已有产物，不改写成另一种失败 |

- `starting up` 不是进度也不是失败，不得据此补发相同或替代调用。启动等待只消费宿主完成/失败通知，不轮询 transcript、不因超时 interrupt；无法确认状态时停止该冲突范围新增派发，保留原 scope/证据，不冻结其他安全已授权批。
- 已有 receipt 或 reviewer 产物的工作单元不得再次派发。作者已有部分产物时只在原真实 actor 可核验的前提下续写，不能换作者覆盖后冒充同一执行；无法保持归属则保留原件并报告阻断。
- 「池里已存在什么」只读 `release pool-query`（轮内点名 `--target-ref` 或 `preflight`；全池只在检查点）；「在飞到哪步」只读 `_shared/receipts/`，找首个未闭合步骤继续。缺 actor 身份不猜模型/provider/runId，不伪造 seal；不从聊天摘要、shard、Routine 创建事件、daemon `inflightCount` 或 claim 推断闭合。
- blocked execution 才以显式新 execution + `retryOf` 补齐；已 pass 或已发布对象的内容纠正不能泛用 retryOf。homepage 走既有 `release object-transaction revise-homepage`；article/image/video 通用修订能力未证明前，不换标题/ID 绕重，不覆写 sealed bytes。
- review 文件：已封存只复用，不覆盖。未封存但完整者先核原 reviewer 与当前草稿绑定。部分或不可读者先确认原调用终态并保留原件，再判断原 actor 能否继续。文件存在不是完成，也不是永久禁止恢复。无法保留归属时阻断。晚到文件不替换正式 review。seal 绑定 draft digest 不证明 reviewer 读过草稿。
- 长转码/下载用宿主工具级后台，遵循已验证的等待/完成通知能力；不用 shell `&/nohup`、固定 sleep 占用执行调用、轮询启动状态或超时自动补发。观察调用不捎带下载、生产或恢复，新增工作单独确认本批预算与scope；已有输出按身份/摘要核复用，不因标题写“Retry”就重跑所有候选。同站点共享预算、同会话下载约束不因多开一个观察调用而扩大。
- 离线测试必须隔离到独立临时根，并绑定 `QWQ_PUBLISH_ROOT`、library、golden。禁止测试默认命中正式仓，也不让生产覆盖测试保护根。用例通过数不等于整组命令 PASS。

目录或 receipt 缺失先核实际活动根、原写者和既有恢复裁定，不因一次未找到就认定删除，不把备份 receipt 回填为当前通过；无法证明恢复边界时仅阻断对应批并报 owner。旧 nonce/claim 的重放只能用于已确认的同一幂等请求，不能因重建目录自行认定可复用；新 execution 也不自动终止旧调用或释放其名额。

阻塞按三步处理：本岗能解就在原授权与未冻结输入范围内解决；不能解直接找对应责任人；只暂停受影响动作。原任务负责人保留跟进责任，接收方承担解阻责任，无人承接或跨角色冲突由总监兜底。既有 report/checkpoint 只留一条“阻塞事实／解阻责任人／下一动作／下次检查”，恢复后由受影响角色确认一次，不新建状态机或全员报数。

普通未封存输入错误由作者自主修正/换候选；同类确定性错误再次发生停止盲重试，报管家/工程 owner，总监跟到明确结论。QA/发布拥堵先处理等待较久的合格批、清晰退回和已授权发布，再按真实负荷调整已验证槽位与批量；不只扩作者、不取消独立审核、不放宽名额堆稿。调用正常终止提醒原负责人续领，blocked 依 retryOf 恢复；重发通知不等于重发生产，同一恢复一个 owner。unknown、失联、额度耗尽不靠 mtime、TTL 或退出登录抢占；无可信终态或获准隔离能力就报告带 owner 的 blocked 并请求用户。新登录身份独立，不冒用旧 actor，已封存成果复用。

总监主动检查节奏、完整小时群报与下一检查裁定只由 [team](team.md#主动保流检查) 拥有；同一原生非重入检查约10分钟核异常、整点汇总上个完整小时，不新建第二调度器。无基线、读取失败、Mac不可达或范围不完整报 unknown，不伪造零；首次入池与 eligible 净变化分开，修订/身份归并/退出不算新增，完整小时键去重且发送失败保留原生回执。总监也失联时用户最终接管，管家能通知即通知。不能假设同账号还有最后交接预算，只保证已持久化证据可恢复，不承诺未落盘推理不丢失。

## 收官

达到约定计数、前沿耗尽、零净增达上限、轮次/放弃预算耗尽、用户中止或授权不足时结束本轮。只写本轮 `report.md`，六段不可省：

1. 目标与 `pool-query` 实际四载体计数，引用 `pool.before.json/pool.after.json`。
2. 本片新增与复用的 exact objectRefs/publish proof；并行时不以全池净增代本片产量。
3. 放弃的候选/对象、原因及处置层，不另建永久淘汰台账。
4. blocked execution 与首个 typed blocker，保留失败命令/退出码。
5. 未闭合缺口、尚未验证的来源/投影/下游边界。
6. 下一轮最小入口、所需授权及本轮采用的默认与假设。

附本轮来源网站统计：只读点名同根、同阶段的对象范围；按唯一作品/对象去版本，同作品同网站计一次。分别报告作品页网站覆盖数、覆盖率（该网站涉及作品/全部范围作品，跨站合计可超过100%）和来源关联构成占比（该站去重作品关联/所有有效网站关联，非空时合计100%）。另列缺来源、无法解析、不同网站数；发现平台与原站沿革单列，CDN/许可页/百科尾部引用不算采用网站，多图原作与视频poster不重复计数。空样本不除零，缺来源不从总分母删除。只补现有report/团队消息，不建台账，不据统计推进生产；只读入口为 `python3 .agents/skills/content-production/scripts/producer.py --workspace <明确内容根> source-stats --manifest <对象相对目录>/manifest.json ...`，参数不是候选或execution草稿目录；输出结构化JSON至stdout，不触发数据库/媒体校验或发布。当前实现限点名canonical manifest，同一ID取所选最高版本，同ID同版本多locator拒绝；执行期统计需先明确其独立输入契约，不能把本命令用于草稿后宣称已发布。原站列仅反映结构化originalUrl，未核原始响应沿革。旧双根不得合并统计，便利样本不外推全库。

附本轮评分分布；每 5 轮按 exact objectRefs 与 review digest 分开统计 execution reviewed、published、eligible 三集合，缺评分不补零、不反写已封存产物。同一观察窗口另列：

1. **首审通过率**：首次实际受审且有终态的唯一对象中 approved 的比例；同时列 draft 前退轮。
2. **返工后通过率**：固定原对象 cohort 的已闭合恢复结果，不能只看成功 retry 分母。
3. **发布成功率**：本期实际尝试 publish 的 approved 对象中事务成功的比例；未授权/未尝试/在飞分开，replayed 不当净新增。
4. **端到端产出**：冻结目标中最终唯一、approved、published、eligible；并列候选淘汰与未闭合依赖。没有完整目标集则不报比例。
5. **审核有效性**：发现的事实/视觉错误、approved 但证据不足的抽样、评分理由是否对应正文/媒体。
6. **时间**：来源请求、下载/转码、author、provider 排队、review、publish 与授权/交接等待分开记录。只用原生开始/结束事件；仅有文件 mtime 时只写落盘间隔并注明不可归因。缺值留空，不补零，不把 mtime 差当模型时长。

保留六维，锚点只维护在载体 `CARRIER.md`；集中得分先查锚点与证据，不强拉分布或凭少量视频归纳普遍结论。M1000/M10000 可附实际来源使用、权利及水印记录分布，并同时标明运营目标与 policy 底线。

同质量、载体和冷热缓存条件下另报净 eligible 产速、端到端周期、WIP、最老未闭合项、首审/返工及每合格对象成本；无 native 时间则等待/产速缺值，不编数字、不承诺翻倍。规则/本地测试、真实 Bot 生效、生产净增和正式 M 达成分别举证。

总监每轮获原授权后按 `commit` Skill 在独立内容仓提交 canonical 增量并按授权目标镜像随体媒体；工程 baseline 与内容快照分别绑定，无匹配内容 commit 不冒称已提交，也不强制双提交。在飞输入、原件与来源证据不自动删除；工作区可再生产不等于网络页面或 AI 判断可逐字节重建，删除运行证据即损失该次过程审计。canonical pool、版本化 handoff、仓外 library 与随体媒体不清理。
