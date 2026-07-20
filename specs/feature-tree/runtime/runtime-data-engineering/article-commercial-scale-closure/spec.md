# L3 特性：article-commercial-scale-closure

## 概述

面向浙江、四川旅行垂类的文章商业化放量 Story：把文章来源站点纳入统一
onboarding 合同与共享 commercial pool，建立唯一 commercial execution branch，
依次完成 Canary、H200、H1000 与 H10K 真实发布；日产 100,000 只允许依据 H10K
权威成本、吞吐和下游消费证据外推。

## 归属

- L1_domain_service: `runtime`
- L2_business_capability: `runtime-data-engineering`
- L3_story: `article-commercial-scale-closure`

## 范围

### In Scope

- article 商业主线的唯一执行分支：`download -> build -> content_plan -> produce -> publish -> ship/import -> verify`
- 开放式旅行/摄影文章来源站点统一 onboarding 合同与 shared commercial pool
- 站点 admission 分层：`commercial_release` / `controlled_trial` / `reference_only` / `blocked`
- 文章来源与独立开放许可插图的 typed role、逐资产 rights/provenance 与 mixed-layout
- 真实 `cursor_sdk` managed authoring、authoritative `TokenLedger`、预算 kill switch
- Canary（浙江 2、四川 1）、H200、H1000、H10K 的独立 article execution 与 immutable release
- H10K 必须每省 5,000、共 10,000 条 accepted/canonical/Gamma 可查询文章在 24 小时内完成
- 基于 H10K 实测的 100,000/日 evaluate-only 评估

### Out of Scope

- image 与 video lane 的独立生产逻辑
- creator pool 新一轮扩池与 persona 设计
- 100,000/日实际生产
- 每个新增站点都单独跑一套独立 H100/H1000；本 Story 只验 shared commercial pool 总体能力

## 核心原则

1. **唯一商业分支**：文章商业化执行只认 `qwq-data task execute` 创建的单
   execution 主线，不再并行维护第二套 source-planning、produce 或 release 语义。
2. **开放式扩站但共享验收**：新老站点全部走统一 onboarding 合同，进入 shared pool 后共同承担 H100/H1000 配额；不要求每站各自单独关门。
3. **文本与插图双角色闭包**：文章文本事实源和插图资产必须分别记录来源、权利与用途；无逐图权利时不得静默退化 `text_only` 或复用平台 UGC 原图。
4. **模型与成本可复现**：author/reviewer 使用 execution manifest 冻结的具体模型；每次 turn 的权威 usage、真实 billed cost、重试成本和 passed-unit cost 必须增量落账。
5. **历史旁路必须清理**：退场的 `source_plan`、prior-plan source reuse、双 planning contract、旧 quota/reuse/provider 扩散不得继续干扰 commercial path。
6. **H10K 实跑，H100K 只外推**：H10K 缺少真实 release/import/API/App UAT/rollback/replay 任一证据都保持 NO_GO；100,000/日不实际生产。

## 真相源

- `specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md`
- `specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/acceptance.yaml`
- `docs/outstanding_risks_backlog.md`
- `quwoquan_data/verticals/travel/sources/source_registry.yaml`
- `quwoquan_data/scripts/content/execution/controller/orchestrator.py`
- `quwoquan_data/scripts/content/execution/controller/content_plan.py`
- `quwoquan_data/scripts/content/release/canonical/gate.py`

## 关键裁定

- article 商业化的主要 blocker 是站点准入、底稿与插图双角色权利闭包、planning contract 与历史旁路清理。
- shared commercial pool 的成功标准是“通过权利/质量门并能闭环下游可见性”的 released objects，而不是站点名册数量或 trial 漏斗数量。
- homepage 必须通过显式 `homepageExecutionId` 绑定已冻结、已发布的同档主页批次。

## 输出目录口径（数据输出规范）

- Canary/H200/H1000/H10K 每次运行都使用唯一 `.qwq_output/data/tasks/<executionId>/` 工作包；
  homepage 与 article 使用独立 execution，禁止混用运行身份。
- readiness/monitoring/audit 只认当前 execution 内的权威证据；approved canonical 只写
  `quwoquan_data/publish/**`，immutable release 只写 `.qwq_output/data/releases/<releaseId>/`。
- 搜索补全供给使用独立 execution，不能和主线共享冻结目标、状态或准出口径。
