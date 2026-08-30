# 载体契约：article

四载体共用十阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写
article 的差异判据。产物清单真相源是
`quwoquan_data/scripts/core/stage_artifact_contract.py`，此处不复制。

## 对象根与坐标

- 对象根：`posts/article/<angle>/<title>/<seq>/`（与 canonical publish 同构）。
- 坐标 `publishAngle/publishTitle/publishSeq` 由 `0.plan/target_set.json`
  逐 target 冻结；`verify content-execution-layout` 对错根/缺坐标 fail closed。

## 各阶段差异

- `1.download`：`source_refs.json` 绑定 encyclopedia-primary 来源；
  纯文字 article 无媒体 CAS 依赖（`publishMediaMode=text_only`）。
- `3.compose`：`writing_pack.json`（schema
  `quwoquan_data/schema/content/writing_pack.schema.json`）必须冻结
  `baseSourceRef`（单底稿）、`creatorProfileRef`（canonical creators 目录名）、
  `tagRefs`（canonical tags 引用，publish-closure 校验无悬空）。
- `4.draft`：产物 `draft.article.md` + `draft_meta.json` +
  `author_self_check.json` + `agent_result_envelope.json`；
  envelope `files[].path` 相对 `4.draft/`；正文主张不得越出证据边界
  （evidencePoints / 底稿）。
- `5.review`：`attestation.json` 需 `decision=approved` 且
  `deterministicGate/independentReviewer/mediaRefReview` 全 `passed`；
  judge 与 `4.draft` 生成模型异族（`verify rubric --generation-family` 兜底）。
- `publish`：`release publish-execution` 物化 `article.md` + `manifest.json`
  （schema `quwoquan_data/schema/content/post_manifest.schema.json`）；
  text_only 对象不要求 rights-bound asset。

## 完成判据锚点

M1 实证链见 `multi-carrier-release/spec.md` 的 `GWT-020`。
