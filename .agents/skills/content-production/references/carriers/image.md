# 载体契约：image

四载体共用 producer 九阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写 image 作品差异判据。产物 authoring source 是对应 stage contract；当前 Python artifact contract 必须在后续实现中服从该文档，本次不修改。

## 对象根与坐标

- 对象根：`posts/image/<angle>/<title>/<seq>/`，坐标由 `0.plan/target_set.json` 冻结（同 article）。

## 各阶段差异

- `1.download`：identity-only candidate 不含 pre-init admission；本阶段才取得媒体 bytes、写 source refs/CAS 与 MIME/digest/probe/rights hard facts，rights 状态不因下载升级。
- `3.compose`：AI 写 `writing_pack.json`，选择 sourceCollection/assets 与 caption 意图；脚本不得选择素材或写 caption。
- `4.draft`：同一 execution 的唯一 author 会话每对象只写 `image_work.json`（含 caption）；无 article 正文，自检与 digests 由 sequence-006 receipt 冻结。
- `5.review`：另一个 reviewer 会话每对象只写 `content_review.json`；每个 asset 的完整权利链与最终 decision 在该文件单写。
- `publish`：物化 `manifest.json`（无 `article.md`），事务要求至少一个 rights-bound asset；跨 canonical 去重由事务核心强制。
- `release`：只随 AI explicit cohort/milestone 交付，不以环境结果反向改变 image 资格。

## 状态

receipt 协议下 image producer lane 尚未走通首个对象；M1/M10/M100/M1000 按累计唯一 finalized 对象计数，验收锚点绑定 `multi-carrier-release/spec.md` 的 `GWT-020`/`GWT-034`。
