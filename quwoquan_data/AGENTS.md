# quwoquan_data Agent Guide

在 `quwoquan_data/` 工作时，除仓库根 `AGENTS.md` 外先阅读 `quwoquan_data/README.md`。

## Data 内容生产边界

`.agents/skills/content-production/SKILL.md` 是 Data 内容生产十阶段唯一业务工作说明：

```text
0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review
-> publish -> release -> ship
```

宿主 AI 直接读 OPEN 冻结上下文、选择来源与素材、写正文或 video script、逐对象自检与独立 review，并显式提交 `actor/verdict/typedIssues/resultRefs/verifierFacts`。代码不得决定业务阶段、来源、内容、review、verdict、typed issue、后继或恢复。

代码允许边界只有：

- `task init` 原子创建三份工作包输入；
- `task stage-open` 冻结 AI 显式 input refs 的 exact bytes；
- `task stage-close` 重验 exact bytes/schema/verifier facts 并 create-once 写 receipt；
- 下载与媒体 CAS；
- schema、摘要、引用闭包、媒体/环境硬事实 verify；
- approved 单对象 publish 事务、显式 cohort immutable release、ship apply/readback/health/EAF 原子 IO。

禁止保留或新增 stage-gate registry、semantic prepare/record wrapper、runner/fleet/lane claim、agent/controller/queue/campaign/recovery、自动恢复、execution-state reducer、managed SDK/provider、第二 registry/processor/脚本。旧 sequence-017 不修、不迁、不兼容；任何旧轨引用、import、CLI、schema、fixture、test 与文档必须在物理删除增量中归零，不得用 shim 或 dual-read 保留。

新能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>` 的现有边界，不新增可直接运行的业务脚本。schema、metadata、taxonomy 与内容契约先行。脚本不得拼正文、video script、rubric、rights 结论或 attestation。

## 内容与证据

- 两条供给线均需闭合：内容稿件（homepage/article/image/video 等）与 entity/tag/media/rights 治理。
- `sources` 只写每 target 的来源计划，不物化 source unit；`1.download` 才按计划生成 source units、source refs 与 CAS holdings。
- `3.compose` 的选材由 AI 完成；`4.draft` 必须有正文或 `video_script`、draft meta、self-check 与 agent result envelope；`5.review` 由独立 AI 逐对象写 rubric、reviewer、media、rights 与 attestation，禁止脚本合成。
- homepage 正文底稿仅允许 Wikipedia、百度百科公开词条、今日头条百科；结构化事实可额外使用官网与政府/文旅门户，并逐字段保留 `factSources`。OTA、聚合门户与媒体不得伪装为正文主证据。
- 不可追溯 source、rights、creator/tag/entity/media identity 或 review 结论不得 publish。
- approved 对象由 AI 逐个调用单对象事务；release cohort 必须显式，禁止 all-publishable；ship 必须由 AI 显式执行 apply、readback/health 与 EAF。

## E2E 完成

完成必须同时绑定十阶段 receipts、immutable release、环境 import/readback/health 与同 identity `EnvironmentAcceptanceFact`。

- `m1_api_consumer`：以 Alpha 服务/API consumer 的 16-cell fresh raw facts 闭合，不要求 App/设备 UAT。
- `environment_promotion`：才要求 target-bound App UAT raw facts、target binding 与 promotion EAF。

不得把 release-only、静态 gate、fixture、旧 proof、sequence-017 或 counts 当作环境完成。涉及环境操作时同步读取 `quwoquan_ops/AGENTS.md`。

## 工程卫生

`.qwq_output/` 仅放可删除重建的运行产物、证据与缓存。控制面真相源不得写入 output。Python bytecode、pytest cache 与工具缓存按仓库既有隔离规则落盘；禁止在仓库根创建临时脚本。不要运行长门禁，按改动范围执行短静态检查或文档引用检查。
