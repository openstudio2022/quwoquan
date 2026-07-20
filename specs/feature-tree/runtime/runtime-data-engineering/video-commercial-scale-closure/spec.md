# L3 特性：video-commercial-scale-closure

## 概述

面向浙江、四川旅行对象的真实源视频商业放量 Story。抖音、TikTok、微博、头条和
旅游垂类站默认只作 discovery/reference；只有无需绕过登录、DRM 或反爬、可直接下载、
无水印、原创者可识别且 source post/original asset 可追溯的单资产，才可按用户确认的
风险归因策略进入候选。

## 归属

- L1_domain_service: `runtime`
- L2_business_capability: `runtime-data-engineering`
- L3_story: `video-commercial-scale-closure`

## In Scope

- 真实源视频下载、探测、无水印/OCR、音轨权利、转码、poster、字幕、checksum 与 provenance。
- metadata-first `SourceAttribution` 从 Data manifest 到 Service read model、App DTO、
  Feed/分享/沉浸式播放器的同源展示。
- 原创者与平台虚拟发布作者分离；来源链接不冒充 authorization proof。
- `risk_accepted_attribution_only`、`commercialAuthorizationStatus=not_verified`、
  投诉/下架、权利撤回、纠错与审计。
- Canary（真实源视频 3 条）、H200、H1000、H10K 的完整发布与 Gamma 消费证据。

## Out of Scope

- 把 `rights_cleared_image_sequence` 计入 sourced-video 里程碑。
- 去水印、绕过登录/DRM/反爬或把可下载解释为取得商业授权。
- 100,000/日实际生产。

## 核心合同

1. 用户确认的风险策略不改变版权事实：无商业授权时必须明确 `not_verified`，不得标成
   licensed、authorized 或 commercially-cleared。
2. 原创音乐权利不明时剥离并替换已授权音轨；watermark/audio/model/property-release
   均为对象级 admission。
3. `SourceAttribution` 是 metadata 唯一真相源，Data、Service、App 与观测不得复制字段表。
4. H10K 必须每省 5,000、共 10,000 条真实 sourced-video accepted/canonical/Gamma
   可查询对象在 24 小时内完成；图片序列视频数量始终为 0。
5. H10K 前必须有对象存储/VOD、Range/CDN、Android/iOS 真机、SLS QoE、
   gray-initial/carry-on/full 非 dry-run 与 rollback 证据。
6. 缺权利、归因、真实媒体、权威成本或下游消费任一证据都保持 NO_GO。

## 真相源

- `quwoquan_data/verticals/travel/sources/source_registry.yaml`
- `quwoquan_data/verticals/travel/rights/license_policy.yaml`
- `quwoquan_service/contracts/metadata/content/post/projections/video_post.yaml`
- `quwoquan_service/contracts/metadata/content/post/projections/content_post_detail_wire.yaml`
- `docs/outstanding_risks_backlog.md`
