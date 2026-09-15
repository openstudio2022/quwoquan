---
name: content-production
description: Run or resume the six-step Data producer workflow - init, acquire, author, review, publish, release - from a topic to canonical 趣我圈 objects and an immutable milestone handoff.
metadata:
  kind: workflow
---

# content-production

为用户愿意去的地方生产 homepage、article、image、video。宿主拥有来源选择、内容、评审与阶段推进；Skill 工具只做显式指定的单阶段机械动作，Data CLI 拥有 execution、入池与 immutable handoff。正确生成并保存的完整成品即可供各环境选用：publish 是保存成品，release 是冻结分发快照，不再做对象激活或环境专属重审；环境只决定选取数量与装配，Alpha 可打包百级子集。

## 触发与输入

- 新任务一次确认主体、地域/主题、阶段目标与自主追加范围、总费用/站点/存储预算、停止条件、随体备份及动作授权；只在开始或范围改变时读 [session 输入](references/session.md#输入与分片)。已有授权直接引用，普通选题和续领不逐批审批；默认值不代替发布、finalize 或 Git 原授权。
- 实体只用 taxonomy `Entity/地点/*` 现有叶子；主页:文章:图片作品:视频作品的 1:2:3:4 仅为整体建议，可在价值和已授权预算内规划至基础建议的50倍，不改正式 M 档。热门多作、冷门零作合法，同实体唯一主页；详见 [session 规模口径](references/session.md)。先查 `release pool-query`（轮内点名，全池只在检查点），已有对象不重复 init，eligible 与 excluded 分开。
- 产生 `content-release` 时 PRE 运行 `make feature-context TARGET=<exact-path>` 保存 content-addressed immutable owner manifest exact ref；纯只读无送审交付为 `report-only/no-review-deliverable`。
- 知识加载顺序：根规则 → 本 Skill → 当前阶段 [pipeline](references/pipeline.md)/[session](references/session.md)，需要派发才读 [dispatch](references/dispatch.md)；团队岗位读 [team](references/team.md)，Grok 团队首次创建、无任务刷新或带任务接管先读唯一入口 [grok-team-bootstrap](references/grok-team-bootstrap.md)，再按其指针读 [grok-team-rebuild](references/grok-team-rebuild.md)。只加载当前载体 [homepage](carriers/homepage/CARRIER.md)、[article](carriers/article/CARRIER.md)、[image](carriers/image/CARRIER.md)、[video](carriers/video/CARRIER.md)，取来源才读该载体 `sources.md` 的对应站点小节。Bot 记忆只保存这些指针，不复制第二份流程。
- 本 lane 的 Skill 根钉 data-engineering 工作树，内容仓由 `QWQ_PUBLISH_ROOT` 绑定独立 Git 仓身份。实际绝对路径以账号部署绑定为准，见 [grok-team-rebuild](references/grok-team-rebuild.md)。不得把另一 lane 的 Skill 根与本树 tasks 混用。云端 `/workspace` 不是内容仓。 多实例启动只证明客户端 profile 生命周期；production eligibility 还须按 bootstrap 读回账号/cloud computer、本机 daemon、独立 output/workspace、共享 coordination DB、外盘 UUID 与 generation fence。客户端版本变化须重验，唯一全局收官者之外不得 finalize/Git。

## 执行

1. **init**：冻结对象身份、executionId，不要求先下载；`task init --round`，见 [输入与 init](references/pipeline.md#输入与-init)。
2. **acquire**：宿主选来源、看素材并显式申报事实；Skill `source/download/preview/build-inputs`，Data 零网络 `task acquire` + seal，见 [取得](references/pipeline.md#acquire)。
3. **author**：本人获准运行 author seal，全部有效 resultRefs 封存后一次整批交 QA，见 [创作](references/pipeline.md#author)。
4. **review**：独立 QA 自主领取一批，写唯一 `seal.review.json` 并运行 review seal，整批结果直接交总监，见 [评审](references/pipeline.md#review)。
5. **publish**：总监作为唯一收官者按原授权逐个点名 approved 对象并 readback，先 homepage 后依赖 post，不等其他批齐套，见 [入池](references/pipeline.md#publish)。
6. **release**：总监在正式交付点按原授权、explicit cohort、milestone、baseline 执行 `release finalize`；Git 仍需原授权，见 [handoff](references/pipeline.md#release-与-handoff)。

创作者就是本人 execution 的主会话，自主取得小批、取证、创作、自检并运行获准的 init/acquire/author seal；不保留另一主会话代跑的双轨。独立 QA 负责 review seal，总监唯一 publish/finalize/Git 并主动保流，管家保障工具资源。岗位、共享事实与沟通见 [team](references/team.md)，授权/两批在制/恢复见 [session](references/session.md)，整批交接见 [dispatch](references/dispatch.md)。正文、caption、script、verdict、typed issue、评分、cohort 与恢复决定不交脚本。Skill `source/download/preview` 仅按宿主显式输入出网，`build-inputs/lint` 不出网；不包装 seal/publish，不建 runner、调度器或自动恢复。来源访问和权利按 [sourcing](references/sourcing.md)。

一个 execution 恰有一个 author；reviewer 是未参与该批创作的不同 session/runId 真实会话，可同一 model family、同一 host。多作者和多 QA 只并行不同小批，不设全团队两 author 或单 QA 串行限制；每作者容量和资源以 session 唯一规则为准。`starting up` 不是进度也不是失败，不得据此补发相同或替代调用；恢复先核实调用确已终止，保留部分产物作者归属。actor 原样引用宿主 native session/run；禁止自造 sessionId，Grok Bot 不得把 `host`/`provider` 写成 `cursor`。同 shard 内只允许不重叠 execution 写者，不覆盖另一写者的在飞工作。

## 完成证据

- HTTPS 来源、bytes/sha256 与已申报 sha1、权利必填字段、独立 author/reviewer、schema/ref、create-once 与 explicit cohort 计数必须成立；license、accessPolicy、权利疑虑、水印、文风、配图率、热度、评分只记录/advisory。
- producer 完成 = 三份 seal receipt + 逐对象 publish 事务 + `release finalize` immutable handoff，绑定 `producerBaselineRevision/producerContractDigest`、独立内容仓身份和 exact 快照。terminal cohort/handoff 位于 `$QWQ_PUBLISH_ROOT/releases/<releaseId>/`；缺根/错仓拒绝，不回退源码内旧根。
- release 不携带类别或命名就绪轨道，不把 research 改成 production 常量；内容默认公开，环境差异由下游配置表达。对象级原权利词汇和审核原件保留；新布局转换不伪造重审，旧 receipt/release 只作离线审计。
- 每轮报告六段与评分见 [session 收官](references/session.md#收官)，保留池前后读回；不把并行全池净增归给本片。元数据与媒体耐久性见 [Data 边界](../../../quwoquan_data/AGENTS.md)，按授权提交/镜像，不自动清理在飞产物。

## 失败与停止

候选不可用则换来源；单对象失败退轮；execution 身份或完整性失败保持 `blocked`，只以 `retryOf` 新建；数量不足记缺口。见 [session 失败](references/session.md#失败与续跑)。达到目标、前沿耗尽、连续零净增、超预算、用户中止或授权不足即收官。不得规避登录墙、付费墙、验证码、DRM、反爬挑战。

恢复只读池与 receipts，找首个未闭合步骤继续；已有 receipt 或 reviewer 产物的工作单元不得再次派发，不从临时 claim、聊天摘要、Routine 创建事件或调度状态推导完成。本机不可达、验证码、429、磁盘不足写 `GATE_BLOCK` 后停，不改写云端 `/workspace` 冒充内容仓。

## 条件性交接

缺口交 `plan-next`，未完 execution 交 `continue`，送审交 `review`，提交交 `commit`；源码/spec 变更走 Feature workflow。content-release POST 以 `--owner-identity` 携带 PRE owner identity ref，以 `--candidate-evidence` 携带 current candidate evidence，registry 只派一名 reviewer。

`release finalize` 成功即 producer END；import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion/rollback/replay 由 Environment Ops scheduler 独立拥有，不进入 producer handoff 或完成条件。
