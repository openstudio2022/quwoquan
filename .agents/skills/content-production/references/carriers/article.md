# 载体契约：article

四载体共用 producer 九阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写 article 差异判据。产物清单真相源是 `quwoquan_data/scripts/core/stage_artifact_contract.py`，此处不复制。

## 对象根与坐标

- 对象根：`posts/article/<angle>/<title>/<seq>/`（与 canonical publish 同构）。
- 坐标 `publishAngle/publishTitle/publishSeq` 由 `0.plan/target_set.json` 逐 target 冻结；`verify content-execution-layout` 对错根/缺坐标 fail closed。

## 各阶段差异

- `1.download`：`source_refs.json` 绑定 encyclopedia-primary 来源；纯文字 article 无媒体 CAS 依赖（`publishMediaMode=text_only`）。
- `3.compose`：AI 写 `writing_pack.json`，冻结 `baseSourceRef`、`creatorProfileRef`、`tagRefs` 与事实锚点。
- `4.draft`：AI 写 `draft.article.md` + `draft_meta.json` + `author_self_check.json` + `agent_result_envelope.json`；正文主张不得越出冻结 evidence。
- `5.review`：`attestation.json` 需 `decision=approved` 且机械 gate、独立 reviewer 与 media/rights 判定闭合；同一实际 model family 不阻断准出。
- `publish`：AI 为 approved article 准备 `article.md` + `manifest.json`，再逐对象调用 canonical 单对象事务；text-only 对象不要求 rights-bound asset。
- `release`：只按 AI 显式 cohort/milestone 进入 immutable handoff；环境消费不是载体阶段。

## 完成判据锚点

M1 producer 实证链见 `multi-carrier-release/spec.md` 的 `GWT-020`；环境实证由下游 owner 的 OPEN 独立跟踪。
