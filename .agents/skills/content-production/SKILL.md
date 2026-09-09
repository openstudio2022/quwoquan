---
name: content-production
description: Run or resume the six-step Data producer workflow - init, acquire, author, review, publish, release - from a topic to canonical 趣我圈 objects and an immutable milestone handoff.
metadata:
  kind: workflow
---

# content-production

为用户愿意去的地方生产 homepage、article、image、video。宿主负责来源选择、内容、评审与阶段推进；Skill 工具只做被点名的单阶段机械动作；Data CLI 拥有 execution、入池与 immutable handoff。

## 触发与输入

- 新任务一次澄清主体、地域/主题、四载体目标、轮次与站点预算、停止条件、随体备份及授权；只在开始或范围改变时读 [session 的输入段](references/session.md#输入与分片)。默认值必须明示，不能代替提交或发布授权。
- 实体只用 taxonomy `Entity/地点/*` 现有叶子；默认一个实体 1 homepage + 1 article（独立角度）+ 1–2 image [+ video]，不是强制配额。先查 `release pool-query`，已存在对象不重复 init，eligible 与 excluded 分开处理。
- 产生 `content-release` 时，PRE 运行 `make feature-context TARGET=<exact-path>` 保存 content-addressed immutable owner manifest exact ref；纯只读且无送审交付只允许 `report-only/no-review-deliverable`。
- 只加载当前载体：[homepage](carriers/homepage/CARRIER.md)、[article](carriers/article/CARRIER.md)、[image](carriers/image/CARRIER.md)、[video](carriers/video/CARRIER.md)。取来源才读该载体 `sources.md` 的实际站点小节，不要求全读 references 或其它载体。

## 执行

| 步骤 | 宿主决定与输入 | 机械动作 / 按需说明 |
| --- | --- | --- |
| init | 冻结本轮对象身份与 executionId；不要求先下载 | `task init --round`；[输入与 init](references/pipeline.md#输入与-init) |
| acquire | 选来源、看素材、填事实与显式选择 | Skill `source/download/preview/build-inputs`；Data 零网络 `task acquire` + seal；[取得](references/pipeline.md#acquire) |
| author | 一个真实 author 写本 execution 的唯一 carrier 草稿 | 可选 `lint`；主会话 `task seal --stage 4.draft`；[创作](references/pipeline.md#author) |
| review | 另一个真实会话写唯一 `seal.review.json` | 主会话 seal 扇出逐对象 review；[评审](references/pipeline.md#review) |
| publish | 逐个点名 approved 对象，先 homepage 后引用它的 post | `release publish-object`；[入池](references/pipeline.md#publish) |
| release | 明确授权、explicit cohort、milestone、baseline | `release finalize`；[handoff](references/pipeline.md#release-与-handoff) |

- 主会话拥有澄清、全部 Data CLI 机械命令、派发与收官。取证可由主会话或本 execution 的 author 完成；正文、caption、video script、verdict、typed issue、评分、cohort 与恢复决定不得交给脚本。
- Skill `source/download/preview` 可按宿主显式输入出网，`build-inputs/lint` 不出网；不包装 seal/publish，不建 runner、调度器、actor authority 或自动恢复。来源访问与权利只在取证时读 [sourcing](references/sourcing.md)。
- 一个 execution 恰有一个 author actor；reviewer 必须是与它不同 session/runId 的真实独立会话，可用同一 model family。单会话同时最多两个不重叠 author，不嵌套派发，review 串行。需要派发才读 [dispatch](references/dispatch.md)。
- `starting up` 不是进度也不是失败，不得据此补发相同或替代调用。恢复先核实宿主调用已确定失败或终止；已有部分产物保留作者归属，不换身份覆盖。

## 完成证据

- 现行硬事实包括 HTTPS 来源、bytes/sha256 与申报 sha1（有则）一致、权利必填字段在场、独立 author/reviewer、schema/ref 与 create-once 身份闭包、explicit cohort 达到里程碑计数。license、accessPolicy、权利疑虑、水印、文风、结构、长度、分辨率建议、配图率、热度与质量评分只记录或 advisory，不新增准入硬门。
- producer 完成 = 三份 seal receipt 连续闭合 + 逐对象 publish 事务 + `release finalize` 的 immutable handoff。handoff 含工程 `producerBaselineRevision/producerContractDigest` 与独立内容仓身份/exact 内容快照，terminal cohort/handoff 位于 `$QWQ_PUBLISH_ROOT/releases/<releaseId>/`；缺根/错仓阻断，不回退源码内旧根。release 唯一类别为 `production`；当前对象只用新 schema，许可与授权事实如实保留。旧 `reference/releases`、receipt/release 原字节保留作离线审计，不作当前输入。
- 一轮只写 `rounds/<roundId>/report.md`，保留 `pool.before.json/pool.after.json`；报告六段及评分分布见 [session 的收官段](references/session.md#收官)。计数从 `pool-query` 读，不能把并行会话的全池净增算成本片产量。
- canonical 元数据与仓外媒体 holder 的耐久性见 [Data 边界](../../../quwoquan_data/AGENTS.md)。提交按 `commit` Skill、镜像按已授权目标执行；在飞工作区不得自动清理，删除运行证据会失去该次过程审计。

## 失败与停止

- 候选不可用则换候选；单对象失败退轮；execution 身份/完整性失败保持 `blocked`，补齐用显式 `retryOf` 新 execution；目标短缺只报告缺口，不冒充完成。具体分层按需读 [session 的失败段](references/session.md#失败与续跑)。
- 达到约定计数、前沿耗尽、连续零净增达上限、超放弃/轮次预算、用户中止或授权不足即收官。不得绕过登录墙、付费墙、验证码、DRM 或反爬挑战。
- 恢复只读池与 receipts：找首个未闭合步骤继续；已有 receipt 或 reviewer 产物的工作单元不得再次派发。不从 `shard.json`、workspace 临时 claim、聊天摘要或调度状态推导 workflow 完成。

## 条件性交接

- 缺口交 `plan-next`，未完 execution 交 `continue`，送审交 `review`，提交交 `commit`，可复用教训交 `distill`；源码/spec 变更走 Feature workflow。
- 产生 `content-release` 时，POST 把 PRE owner identity ref 原样作为 `--owner-identity`、current candidate evidence 作为 `--candidate-evidence` 调用 Review（workflow=`content-production`、deliverable=`content-release`），registry 只派一名 reviewer。
- `release finalize` 成功即 producer `END`。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion/rollback/replay 由下游 Environment Ops scheduler 独立拥有，不进入 producer handoff、恢复或完成条件。
