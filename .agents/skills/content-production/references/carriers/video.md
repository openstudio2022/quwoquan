# 载体契约：video

四载体共用 producer 九阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写 video 作品差异判据。产物 authoring source 是对应 stage contract；当前 Python artifact contract 必须在后续实现中服从该文档，本次不修改。

## 对象根与坐标

- 对象根：`posts/video/<angle>/<title>/<seq>/`，坐标由 `0.plan/target_set.json` 冻结（同 article）。

## 各阶段差异

- `1.download`：identity-only candidate 不含 pre-init admission；本阶段才取得视频 bytes/CAS，可机械提取 poster，并分别冻结视频/poster 的 ref、SHA-256、bytes、MIME 与 inherited rights hard facts。
- `3.compose`：AI 选择视频证据与叙事/剪辑意图并写 `writing_pack.json`。
- `4.draft`：同一 execution 的唯一 author 会话每对象只写 `video_script.json`，包含 title、caption 与可执行叙事/镜头/声音或字幕意图；自检与 digests 由 sequence-006 receipt 冻结，sourced clip 短于 policy 下限时 typed issue。
- `5.review`：另一个 reviewer 会话每对象只写 `content_review.json`，其中逐资产 rights 结论分别覆盖 source video 与 poster；任何继承字段漂移 fail closed。
- `publish`：物化需冻结 poster identity，并回指已由唯一 `content_review.json` 给出逐资产 rights 结论的 source poster CAS；事务核心拒绝跨 canonical 内容复用。
- `release`：video count、两类 media handoff binding 与原 producer proof 随 explicit cohort 交付；播放/UAT 不属于 producer workflow。

## 状态

receipt 协议下 video producer lane 尚未走通首个对象；M1/M10/M100/M1000 按累计唯一 finalized 对象计数，验收锚点绑定 `multi-carrier-release/spec.md` 的 `GWT-020`/`GWT-034`。
