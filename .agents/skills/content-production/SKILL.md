---
name: content-production
description: Run or resume the six-step Data producer workflow - init, acquire, author, review, publish, release - from a topic to canonical 趣我圈 objects and an immutable milestone handoff.
metadata:
  kind: workflow
---

# content-production

为用户愿意去的地方生产 homepage、article、image、video。宿主拥有来源选择、内容、评审与阶段推进；Skill 工具只做显式指定的单阶段机械动作，Data CLI 拥有 execution、入池与 immutable handoff。

## 触发与输入

- 新任务一次澄清主体、地域/主题、四载体目标、轮次与站点预算、停止条件、随体备份及授权；只在开始或范围改变时读 [session 输入](references/session.md#输入与分片)。默认值须明示，不代替提交或发布授权。
- 实体只用 taxonomy `Entity/地点/*` 现有叶子；默认每实体 1 homepage + 1 article（独立角度）+ 1–2 image [+ video]，不作强制配额。先查 `release pool-query`，已有对象不重复 init，eligible 与 excluded 分开。
- 产生 `content-release` 时 PRE 运行 `make feature-context TARGET=<exact-path>` 保存 content-addressed immutable owner manifest exact ref；纯只读无送审交付为 `report-only/no-review-deliverable`。
- 只加载当前载体：[homepage](carriers/homepage/CARRIER.md)、[article](carriers/article/CARRIER.md)、[image](carriers/image/CARRIER.md)、[video](carriers/video/CARRIER.md)；取来源才读该载体 `sources.md` 的对应站点小节。

## 执行

1. **init**：冻结对象身份、executionId，不要求先下载；`task init --round`，见 [输入与 init](references/pipeline.md#输入与-init)。
2. **acquire**：宿主选来源、看素材并显式申报事实；Skill `source/download/preview/build-inputs`，Data 零网络 `task acquire` + seal，见 [取得](references/pipeline.md#acquire)。
3. **author**：一个真实 author 写本 execution 唯一 carrier 草稿；可选 `lint`，主会话 `task seal --stage 4.draft`，见 [创作](references/pipeline.md#author)。
4. **review**：另一个真实会话写唯一 `seal.review.json`；主会话 seal 扇出逐对象 review，见 [评审](references/pipeline.md#review)。
5. **publish**：逐个点名 approved 对象，先 homepage 后引用它的 post；`release publish-object`，见 [入池](references/pipeline.md#publish)。
6. **release**：明确授权、explicit cohort、milestone、baseline 后 `release finalize`，见 [handoff](references/pipeline.md#release-与-handoff)。

主会话拥有澄清、全部 Data CLI 机械命令、派发与收官。取证可由主会话或本 execution author 完成；正文、caption、script、verdict、typed issue、评分、cohort 与恢复决定不交脚本。Skill `source/download/preview` 仅按宿主显式输入出网，`build-inputs/lint` 不出网；不包装 seal/publish，不建 runner、调度器或自动恢复。来源访问和权利按 [sourcing](references/sourcing.md)。

一个 execution 恰有一个 author；reviewer 是不同 session/runId 的真实会话，可同一 model family。单会话同时最多两个不重叠 author，不嵌套派发，review 串行。需要派发才读 [dispatch](references/dispatch.md)。`starting up` 不是进度也不是失败，不得据此补发相同或替代调用；恢复先核实调用确已终止，保留部分产物作者归属。

## 完成证据

- HTTPS 来源、bytes/sha256 与已申报 sha1、权利必填字段、独立 author/reviewer、schema/ref、create-once 与 explicit cohort 计数必须成立；license、accessPolicy、权利疑虑、水印、文风、配图率、热度、评分只记录/advisory。
- producer 完成 = 三份 seal receipt + 逐对象 publish 事务 + `release finalize` immutable handoff，绑定 `producerBaselineRevision/producerContractDigest`、独立内容仓身份和 exact 快照。terminal cohort/handoff 位于 `$QWQ_PUBLISH_ROOT/releases/<releaseId>/`；缺根/错仓拒绝，不回退源码内旧根。
- release 不携带类别或命名就绪轨道，不把 research 改成 production 常量；内容默认公开，环境差异由下游配置表达。对象级原权利词汇和审核原件保留；新布局转换不伪造重审，旧 receipt/release 只作离线审计。
- 每轮报告六段与评分见 [session 收官](references/session.md#收官)，保留池前后读回；不把并行全池净增归给本片。元数据与媒体耐久性见 [Data 边界](../../../quwoquan_data/AGENTS.md)，按授权提交/镜像，不自动清理在飞产物。

## 失败与停止

候选不可用则换来源；单对象失败退轮；execution 身份或完整性失败保持 `blocked`，只以 `retryOf` 新建；数量不足记缺口。见 [session 失败](references/session.md#失败与续跑)。达到目标、前沿耗尽、连续零净增、超预算、用户中止或授权不足即收官。不得规避登录墙、付费墙、验证码、DRM、反爬挑战。

恢复只读池与 receipts，找首个未闭合步骤继续；已有 receipt 或 reviewer 产物的工作单元不得再次派发，不从临时 claim、聊天摘要或调度状态推导完成。

## 条件性交接

缺口交 `plan-next`，未完 execution 交 `continue`，送审交 `review`，提交交 `commit`；源码/spec 变更走 Feature workflow。content-release POST 以 `--owner-identity` 携带 PRE owner identity ref，以 `--candidate-evidence` 携带 current candidate evidence，registry 只派一名 reviewer。

`release finalize` 成功即 producer END；import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion/rollback/replay 由 Environment Ops scheduler 独立拥有，不进入 producer handoff 或完成条件。
