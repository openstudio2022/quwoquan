# 载体契约：image

四载体共用 producer 九阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写 image 作品差异判据。产物清单真相源是 `quwoquan_data/scripts/core/stage_artifact_contract.py`，此处不复制。

## 对象根与坐标

- 对象根：`posts/image/<angle>/<title>/<seq>/`，坐标由 `0.plan/target_set.json` 冻结（同 article）。

## 各阶段差异

- `1.download`：workUnit 由 media source admission 的 immutable manifest/receipt exact pair 冻结；rights 状态不因下载升级。媒体字节走 CAS，不入对象根。
- `3.compose`：AI 写 `writing_pack.json`，选择 sourceCollection/assets 与 caption 意图；脚本不得选择素材或写 caption。
- `4.draft`：AI 写 `image_work.json`（含 caption）及 common draft meta/self-check/envelope；无 article 正文。
- `5.review`：`media_ref_review.json` 是主判据之一；每个 asset 需完整权利链。
- `publish`：物化 `manifest.json`（无 `article.md`），事务要求至少一个 rights-bound asset；跨 canonical 去重由事务核心强制。
- `release`：只随 AI explicit cohort/milestone 交付，不以环境结果反向改变 image 资格。

## 状态

receipt 协议下 image producer lane 尚未走通首个对象；验收锚点绑定 `multi-carrier-release/spec.md` 的 `GWT-020` 与 M100 producer 计数，未实现项按该 spec OPEN 跟踪。
