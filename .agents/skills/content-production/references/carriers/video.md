# 载体契约：video

四载体共用 producer 九阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写 video 作品差异判据。产物清单真相源是 `quwoquan_data/scripts/core/stage_artifact_contract.py`，此处不复制。

## 对象根与坐标

- 对象根：`posts/video/<angle>/<title>/<seq>/`，坐标由 `0.plan/target_set.json` 冻结（同 article）。

## 各阶段差异

- `1.download`：与 image 同走 media source admission exact pair；取得模块可机械提取 poster，并分别冻结视频/poster 的 ref、SHA-256、bytes、MIME 与 inherited rights facts。
- `3.compose`：AI 选择视频证据与叙事/剪辑意图并写 `writing_pack.json`。
- `4.draft`：AI 写 `video_script.json`，包含 title、caption 与可执行叙事/镜头/声音或字幕意图，同时写 common draft meta/self-check/envelope；sourced clip 短于 policy 下限时 typed discard。
- `5.review`：`media_ref_review.rightsReviews[]` 分别覆盖 source video 与 poster；任何继承字段漂移 fail closed。
- `publish`：物化需冻结 poster identity 并回指已独立 rights-review 的 source poster CAS；事务核心拒绝跨 canonical 内容复用。
- `release`：video count 与两类 media handoff binding 随 explicit cohort 交付；播放/UAT 是下游环境 owner 责任。

## 状态

receipt 协议下 video producer lane 尚未走通首个对象；M100 producer 里程碑计数为 10，验收锚点绑定 `multi-carrier-release/spec.md` 的 `GWT-020`，未实现项按该 spec OPEN 跟踪。
