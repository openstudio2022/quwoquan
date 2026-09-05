# 载体契约：homepage

四载体共用 producer 九阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写 entity homepage 差异判据。产物清单真相源是 `quwoquan_data/scripts/core/stage_artifact_contract.py`，此处不复制。

## 对象根与坐标

- 对象根：`entities/<域>/<类型>/<名称>/`（唯一使用 `entities/**` 根的载体，与 canonical `publish/entities/**` 同构）。
- 坐标即实体身份（target 的 `entityType/name`），无 angle/title/seq。

## 各阶段差异

- `0.plan`：target 需 `qualifiedHomepageSource`。
- `3.compose`：AI 写 `entity_page_input.json`；机械 verifier 以此识别 homepage lane。
- `4.draft`：AI 写 `page.md` 及 common draft meta/self-check/envelope。
- `5.review`：homepage 采用对象级 quota verdict 语义，仍须独立 AI 评审。
- `publish`：成品 `_entity.json` + `page.md`；delivery intent 的实体绑定为 `entityRef` + `tagRefs`，creator 语义与 post 载体不同。
- `release`：homepage count 与 content-pool handoff binding 必须随 explicit cohort 进入 producer handoff。

## 状态

receipt 协议下 homepage producer lane 尚未走通首个对象；验收锚点绑定 `multi-carrier-release/spec.md` 的 `GWT-020`，实现缺口按该 spec 的 OPEN 项跟踪，本文件不虚构未实现命令或环境完成。
