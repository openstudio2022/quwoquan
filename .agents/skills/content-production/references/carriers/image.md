# 载体契约：image

四载体共用十阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写
image 作品的差异判据。产物清单真相源是
`quwoquan_data/scripts/core/stage_artifact_contract.py`，此处不复制。

## 对象根与坐标

- 对象根：`posts/image/<angle>/<title>/<seq>/`，坐标由 `0.plan/target_set.json`
  冻结（同 article）。

## 各阶段差异

- `1.download`：workUnit 由 media source admission 的 immutable
  manifest/receipt exact pair 冻结；rights 状态不因下载升级
  （L2 `design.md#dec-022`：admission 与 post-author independent review
  是两个顺序固定的 append-only fact）。媒体字节走 CAS，不入对象根。
- `3.compose`：不产正文；接受结构化 sourceCollection/assets/caption
  证据包（generator=image_evidence_pack），1..20 个 assets，
  title ≤80 字、caption ≤300 字。
- `4.draft`：无 `draft.article.md`；成品身份由 assets 清单承载。
- `5.review`：`mediaRefReview` 是主判据之一；每个 asset 需完整权利链
  （rightsAuditStatus/usageScope/distributionDecision）。
- `publish`：物化产 `manifest.json`（无 `article.md`），事务要求至少一个
  rights-bound asset；跨 canonical 精确/感知去重由事务核心强制。

## 状态

receipt 协议下 image lane 尚未走通首个对象；验收锚点绑定
`multi-carrier-release/spec.md` 的 `GWT-001` 与 M100 里程碑计数
（`GWT-004`），实现缺口按该 spec 的 OPEN 项跟踪。
