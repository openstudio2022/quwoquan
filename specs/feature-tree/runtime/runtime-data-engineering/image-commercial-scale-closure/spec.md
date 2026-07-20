# L3 特性：image-commercial-scale-closure

## 概述

面向浙江、四川旅行对象的图片商业放量 Story。通过逐图权利、无水印、对象匹配和
跨批去重合同，依次完成 Canary、H200、H1000 与 H10K 真实发布；100,000/日只依据
H10K 权威证据外推。

## 归属

- L1_domain_service: `runtime`
- L2_business_capability: `runtime-data-engineering`
- L3_story: `image-commercial-scale-closure`

## In Scope

- Wikimedia、Openverse、Pinterest、授权图库与摄影师池的分层准入。
- 原始落地页、原图 URL、作者、license/terms 或 authorization proof、usage scope、
  model/property release、watermark/OCR 与 collectedAt 的逐资产证据。
- SHA-256、pHash 与视觉相似度去重。
- 真实 Cursor SDK 用户可见标题/配文、独立 reviewer 与权威成本账本。
- Canary（浙江 2、四川 1）、H200、H1000、H10K 的 execution、canonical、
  immutable release、Gamma import/API/App UAT、rollback/replay。

## Out of Scope

- 把 `fetchable=false` 或 `crawlAllowed=false` 的站点批量抓取。
- 把 Pinterest 归因发布依据描述为商业版权授权。
- 100,000/日实际生产。

## 核心合同

1. discovery/reference 来源不自动取得发布资格；每张图独立完成 rights admission。
2. 水印只能拒绝，禁止去除；作者、来源和权利信息必须进入对象属性与消费者展示。
3. 同一视觉资产跨 URL、尺寸和批次只允许一个 canonical identity。
4. H10K 必须每省 5,000、共 10,000 张 unique accepted/canonical/Gamma 可查询图片在
   24 小时内完成，accepted throughput 不低于 416.67/h。
5. author/reviewer usage、真实 billed cost、重试成本与 unitPassedCost 必须权威落账；
   超预算立即停止派发。
6. 文件存在、候选数、dry-run 或 assembled release 不计完成。

## 真相源

- `quwoquan_data/verticals/travel/sources/source_registry.yaml`
- `quwoquan_data/verticals/travel/rights/license_policy.yaml`
- `quwoquan_data/schema/release/asset_rights_closure.schema.json`
- `quwoquan_data/scripts/content/release/canonical/rollout_attestation.py`
- `docs/outstanding_risks_backlog.md`
