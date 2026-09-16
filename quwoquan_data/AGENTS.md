# quwoquan_data Agent Guide

同时阅读根规则与 `quwoquan_data/README.md`。本文件只拥有 Data 工程不变量；producer 流程只读 [content-production Skill](../.agents/skills/content-production/SKILL.md) 及当前 reference/carrier，不复制正文。

## 语义与执行边界

- 宿主 AI 是唯一语义主体；机械代码不得决定来源、相关性、正文/caption/script、review/verdict/评分、cohort、后继或恢复，也不得代替看媒体与独立评审。宿主共用同一 Skill/CLI，不建第二流程或调度器。
- Data CLI `task acquire` 零网络；`scripts/content/{source,execution}/**` 与 `scripts/core/**` 不得 HTTP/socket 出网。来源机械能力只归 Skill `scripts/` 和点名载体；不复制 probe/derive/CAS/seal，不包装 seal/publish。
- 机械能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>` 单阶段边界。禁止 stage-open、宿主 verifierFacts、resolver/projector/runner/controller/queue/registry/SDK、actor projection、stage-gate、execution-state reducer、自动恢复、第二轮次台账及 shim/dual-read。
- 一个 execution 一个 author；reviewer 必须是不同 session/runId 的独立会话。reviewer 只写 execution 级 `seal.review.json`，CLI 唯一扇出 `content_review.json` 并转录机械权利事实；不建第二身份 authority。
- producer 终点及 Environment Ops 下游边界只读 Skill；外部结果不得回写 producer receipt 或改变 cohort/release bytes。

## 内容与证据

- 实体类型只取 taxonomy `Entity/地点/*` 叶子。homepage 主源闭集/顺序只读 source registry；来源身份可用不等于在线取证获准。第三方文章仅 `factual_reference_only`；image/video 绑定真实作品来源。
- 来源访问与权利只读 `references/sourcing.md`；不技术规避登录墙、付费墙、验证码、DRM 或反爬。未知权利如实记录，不因类别阻断入池；公众可见性归运营策略。
- 硬事实包括 HTTPS 来源与摘要一致、bytes/sha256、必填权利字段、独立 author/reviewer、schema/ref/create-once 闭包及显式 cohort 计数；其余如实记录，不增质量门。字段/枚举只读 `schema/content/`。
- 每对象只有一个 carrier 主产物，标题/tagRefs/creatorProfileId 由产物声明；author seal 校验引用与 homepage 主源。每对象只保留 seal 生成的一份 review，不让脚本生成语义判断。
- 单对象违规保留 typed issue，不覆盖 blocked receipt；approved 对象逐个点名走 canonical 原子事务，cohort/milestone 必须显式，禁止 all-publishable。
- release 单链路，不携带发布类别/命名就绪轨道。新写入禁止分类维 `usageScope=research|commercial`、`publicationAdmission=research_release|commercial_release`、`distributionDecision=research_allowed|commercial_allowed|blocked`、`variantPurpose=commercial_variant`，也不以 `production/default` 替代；只保留权利事实及资产用途 `usageScope=internal_reference|app_publish|editorial`。历史原件不改，活跃对象仅按 `DEC-023` 显式新版本 cutover；商用权利只记录不要求，文章配图无下限。

## 持久性与工程卫生

- canonical 内容仓是源码树平级的独立 Git 仓，以 `QWQ_PUBLISH_ROOT` 显式绑定；不得是源码 worktree/submodule/symlink。缺根/错仓阻断，不回退源码内旧根。离线测试必须以独立临时根绑定 publish/library/golden。迁仓差距见 [OPEN-027](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-027)。
- 对象包 `manifest.json` 单写身份/事实/有序依赖；只留最终正文与最终媒体，采用来源及必要证据随包，不跨包 symlink。审核原件与追加 records 分离，不复制 authority。
- library 仅供采集复用，作品/release 不依赖它；golden 保护副本保留。Git ignore/硬链接/同卷拷贝不证明备份，未验证异卷/远端恢复就如实报告；gc 不触碰保护根或被引用媒体。
- verify/普通消费只读，缺失、损坏或证据不足 typed 阻断，不隐式下载/回填/修复；恢复须显式且逐摘要验证。差距见对象包 `OPEN-025` 与耐久性 `OPEN-002`。
- finalize 仅保存 canonical cohort/handoff，绑定工程契约、内容仓身份及 exact 快照；有匹配内容 commit 才记录。旧 releases/bundle/receipts 原件保留，本规则不授权移动、删除或初始化仓库。
- publish/整理/Git ref 共享锁串行；只枚举声明对象根，`.git`、仓元数据、releases 不进 inventory。不建分区 authority 或后台健康框架。
- `.qwq_output/` 仅放可重建输出/证据/缓存，不承载控制面；`data/local/` 仅 `cache/runs/workspace`，execution 原布局不迁移。在飞产物不自动清理。
- authoring source 先行；提交/发布/镜像须授权。缓存按根规则隔离，禁止根临时脚本；验证按影响面执行。
