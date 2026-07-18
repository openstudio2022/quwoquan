# article-commercial-scale-closure

## 概述

面向旅行与摄影垂类的文章商业化收口 Story：把开放式文章来源站点纳入统一 onboarding 合同与共享 commercial pool，清理历史 article/homepage 旁路，建立唯一 commercial execution branch，并以真实 `cursor_sdk` + 最新 `composer` 模型完成 `H100 -> H1000` 端到端验证，再基于真实证据评估 `10k/日` 可行性。

## 归属

- L1_domain_service: `runtime`
- L2_business_capability: `runtime-data-engineering`
- L3_story: `article-commercial-scale-closure`

## 范围

### In Scope

- article/homepage 商业主线的唯一执行分支：`download -> build -> content_plan -> produce -> publish -> ship/import -> verify`
- 开放式旅行/摄影文章来源站点统一 onboarding 合同与 shared commercial pool
- 站点 admission 分层：`commercial_release` / `controlled_trial` / `reference_only` / `blocked`
- 真实 `cursor_sdk` managed authoring、authoritative `TokenLedger`、`firstPassRate`、`sdk_monitoring`、`managed_batch_audit`
- H100 article+homepage 真实闭环
- H1000 在 H100 全绿后的同轮放量验证
- 基于 H1000 实测的 `10k/日` evaluate-only 评估
- 当前 article/homepage 商业 blocker：source sufficiency、mixed-layout、homepage closure、release/import/search/reco visibility

### Out of Scope

- Pinterest image-only 商业线
- video lane 商业化
- creator pool 新一轮扩池与 persona 设计
- 10k/日与 100k/日实际生产放量交付
- 每个新增站点都单独跑一套独立 H100/H1000；本 Story 只验 shared commercial pool 总体能力

## 核心原则

1. **唯一商业分支**：文章商业化执行只认 `qwq-data task execute` 创建的单
   execution 主线，不再并行维护第二套 source-planning、produce 或 release 语义。
2. **开放式扩站但共享验收**：新老站点全部走统一 onboarding 合同，进入 shared pool 后共同承担 H100/H1000 配额；不要求每站各自单独关门。
3. **证据优先于数量**：`H100/H1000` 完成必须同时具备真实 `env_ready_report`、`task_execution_state`、`token_ledger`、`managed_batch_audit`、`sdk_monitoring` 与 release/import/search/reco 证据。
4. **只用最新 composer 主线**：内容生成执行统一使用 `cursor_sdk` 与默认最新 `composer`，不再用细版本口径制造执行漂移。
5. **历史旁路必须清理**：退场的 `source_plan`、prior-plan source reuse、双 planning contract、旧 quota/reuse/provider 扩散不得继续干扰 commercial path。
6. **10k 只做 evaluate**：没有 H1000 的真实 throughput / `unitPassedCost` / `sourceReadyObjectCapacity` / `firstPassRate`，不得承诺日产万级可行。

## 真相源

- `specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md`
- `specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/acceptance.yaml`
- `docs/outstanding_risks_backlog.md`
- `quwoquan_data/verticals/travel/sources/source_registry.yaml`
- `quwoquan_data/scripts/content/execution/controller/orchestrator.py`
- `quwoquan_data/scripts/content/execution/controller/content_plan.py`
- `quwoquan_data/scripts/content/release/canonical/gate.py`

## 关键裁定

- 当前 image-only 商业验证已收紧在 `geo-content-trinity` 的 Pinterest lane，本 Story 不再复用该验收口径。
- article 商业化的真正问题不在后半条 `produce -> publish` 主线，而在前半条来源准入、planning contract 与历史旁路清理。
- shared commercial pool 的成功标准是“通过权利/质量门并能闭环下游可见性”的 released objects，而不是站点名册数量或 trial 漏斗数量。

## 输出目录口径（数据输出规范）

- H100/H1000 每次运行都使用唯一 `.qwq_output/data/tasks/<executionId>/` 工作包；
  homepage 与 article 使用独立 execution，禁止混用运行身份。
- readiness/monitoring/audit 只认当前 execution 内的权威证据；approved canonical 只写
  `quwoquan_data/publish/**`，immutable release 只写 `.qwq_output/data/releases/<releaseId>/`。
- 搜索补全供给使用独立 execution，不能和主线共享冻结目标、状态或准出口径。
