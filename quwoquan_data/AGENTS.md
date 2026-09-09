# quwoquan_data Agent Guide

在 `quwoquan_data/` 工作时，除仓库根 `AGENTS.md` 外先阅读 `quwoquan_data/README.md`。

## Data 内容生产边界

[content-production Skill](../.agents/skills/content-production/SKILL.md) 是 producer 唯一流程真相源。本文件只声明工程不变量；阶段输入与命令由 Skill `references/pipeline.md` 拥有，派发由 `references/dispatch.md` 拥有，预算、恢复、工作区布局与收官由 `references/session.md` 拥有，载体模板与来源入口按当前 `CARRIER.md` / `sources.md` 渐进加载，不在 Data 复制步骤正文。

- 宿主 Cursor/Codex Agent 是唯一语义主体。机械代码不得决定来源、实体相关性、正文/caption/video script、review、verdict、评分、typed issue、approved、cohort、milestone、后继或恢复；不以脚本代替看媒体、创作和独立评审。
- Data CLI 的 `task acquire` 是零网络 ingest：`quwoquan_data/scripts/content/source/**`、`content/execution/**` 与 `core/**` 不得有 HTTP/socket 出网点，由 local_contract 静态门锁定。`content/release/environment/public_api_client.py` 只验证自家服务，不是来源网络入口。
- 来源侧机械能力归版本控制的 Skill `scripts/` 与点名载体模块；其中 `source/download/preview` 可按宿主显式输入出网，`build-inputs/lint` 只做本地构造与 advisory。未实现来源由宿主通用工具取得，不宣称自动化；不复制 Data probe/derive/CAS/seal，不包装 seal/publish。
- Data 机械能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>` 现有单阶段边界。禁止 stage-open、宿主 verifierFacts、resolver/projector/runner/controller/queue/registry/SDK、actor projection、stage-gate、execution-state reducer、自动恢复或第二轮次台账；不得用 shim/dual-read 留第二轨。
- 一个 execution 一个真实 author，reviewer 必须是不同 session/runId 的独立会话。reviewer 只写 execution 级 `seal.review.json`，CLI 唯一扇出逐对象 `content_review.json` 并补齐机械权利转录；不建 `actors.json` 或第二身份 authority。
- producer 以 `release finalize` 的 immutable handoff 为终点。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion、rollback 与 replay 由下游 Environment Ops scheduler 独立拥有，不进入 producer handoff、恢复或完成条件，Data 不写 EAF。外部 consumer 结果不得回写 producer receipt 或改变 cohort/release bytes。

## 内容与证据

- 实体类型只取 taxonomy `Entity/地点/*` 现有叶子。homepage 主源保持百科闭集（zh.wikipedia / 头条百科 `www.baike.com`），第三方文章只作 `factual_reference_only`；image/video 绑定真实作品来源。
- 来源访问与权利原则只由 Skill `references/sourcing.md` 拥有：访问策略、版权保留、未知权利与需授权事实只记录，不因类别阻断入池；公众可见性归运营策略。禁止技术性规避登录墙、付费墙、验证码、DRM 或反爬挑战。
- 硬事实为 HTTPS 来源、申报 sha1（有则）与本地字节一致、bytes/sha256 精确、必填权利字段在场、独立 author/reviewer、schema/ref 与 create-once 对象身份闭包，以及显式 cohort 达到里程碑计数。权利取值、真实派生修改、水印、热度与质量评分如实记录，不伪造事实或增设质量准入门；字段与枚举只以 `schema/content/` 单一说明为准。
- 每对象只留一个 carrier 主产物（`page.md|draft.article.md|image_work.json|video_script.json`），标题/tagRefs/creatorProfileId 由产物自身声明。author seal 校验引用与 homepage 百科主源；每对象只保留一份 seal 生成的 `content_review.json`，不允许脚本生成语义判断。
- 单对象违规保留 typed issue，不伪造整 execution 成功或覆盖 blocked receipt。approved 对象必须由宿主逐个点名调用单对象原子 canonical 事务；release cohort 与 milestone 必须显式，禁止 all-publishable；排序、canonical 化与 `expectedCarrierCounts` 派生由 finalize 完成。
- release 只有 `production` 类别，媒体按公开 slice 交付。商用级权利字段只记录不要求；文章配图张数不设下限。里程碑计数与完成证据只按 Skill，本文不维护第二完成台账。

## 持久性与工程卫生

- canonical 内容仓为与源码工作树平级的 `/Users/zhaoyuxi/Projects/quwoquan/publish` 独立 Git 仓，通过 `QWQ_PUBLISH_ROOT` 显式绑定仓身份；不是源码 worktree、submodule 或 symlink。缺根/错仓必须阻断，不回退 `quwoquan_data/publish`。本规则冻结目标契约，不表示实际迁仓已完成，当前差距见 [发布仓 OPEN-027](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-027)。
- 地域实体按 `entities/<domain>/<真实行政链>/<type>/p0001/<name>/<seq>/` 管理，非地域结构仅预留 `entities/<domain>/<已有主类型路径>/p0001/<name>/<seq>/`；posts 按 `posts/<carrier>/<angle>/p0001/<name>/<seq>/`。行政链来自真实主 geoTagRef，不虚构缺层；地域适用性显式，当前不扩展非地点 producer。名称/分区/条目只作 locator，稳定 ID/ref 不变，seq 不等于版本。
- 对象包的 `manifest.json` 单写身份、结构化实体事实、正文引用与有序媒体/依赖；正文只保留最终 `page.md`/`article.md`，image/video 无伪正文。采用来源及必要真实证据进入包内 `sources/`，最终媒体进入 `media/`；不把禁止 raw 草稿误解为禁止采用来源证据，不跨包 symlink。审核原件与追加式 `records/` 各自保留，不伪造重审或复制第二套 manifest/source authority。
- content library（`QWQ_LIBRARY_ROOT`）用于采集复用，完整作品/release 不依赖它消费；独立 golden media（`QWQ_CARRIED_MEDIA_ROOT`）保护副本继续保留。普通 Git 不跟踪媒体，`.gitignore`/硬链接不算备份，同卷拷贝不证明抗卷损坏；异卷/远端恢复未验证就如实未建立，任何 gc/hygiene 不触碰现有保护根或任一保留作品/release 所引用媒体。
- verify 与普通消费必须只读、缺失/损坏/来源证据不足 typed 阻断，不隐式下载、回填库或修复包；恢复是显式操作并逐摘要验证独立副本，不承诺来源直链能复原派生字节。当前实现/证据差距见 [对象包 OPEN-025](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-025) 与 [耐久性 OPEN-002](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#open-002)，未改为只读前不得把旧 `verify all` 当纯检查。
- finalize 只保存现有 `cohort.json` / `producer_release_handoff.json` 到内容仓 `releases/<releaseId>/`，绑定工程 baseline/契约摘要与内容仓身份/exact 内容快照；有匹配内容 commit 才记录，不强制双提交。旧 `reference/releases`、release bundle 与 receipts 原件保留；本规则不授权移动、删除或初始化仓库。
- 共同 publish 根的写锁不依赖各源码 OUTPUT_ROOT，publish/显式整理/Git ref 更新串行；只枚举声明对象根，`.git`、仓元数据与 releases 不进入对象 inventory。分区仅用条目数与随体逻辑字节，同名组不拆、不自动搬家，不建分区 authority 或后台健康框架。
- `.qwq_output/` 仅放可删除重建的运行产物、证据与缓存，不得承载控制面真相源或助手脚本。`data/local/` 只允许 `cache/`、`runs/`、`workspace/`；具体生产布局归 Skill，execution `tasks/` 与 receipts 原物理布局不迁移。删除运行证据会失去该次执行审计，在飞工作区不得自动清理。
- authoring source 先行；提交、发布和镜像必须满足用户授权。Python bytecode、pytest cache 与工具缓存按根规则隔离，禁止仓库根临时脚本。不要运行长门禁，只按实际改动执行短静态检查、回归或文档引用检查。
