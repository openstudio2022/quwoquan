# 载体契约：homepage

四载体共用十阶段契约（[stage-contracts/](../stage-contracts/)）；本文件只写
entity homepage 的差异判据。产物清单真相源是
`quwoquan_data/scripts/core/stage_artifact_contract.py`，此处不复制。

## 对象根与坐标

- 对象根：`entities/<域>/<类型>/<名称>/`（唯一使用 `entities/**` 根的载体，
  与 canonical `publish/entities/**` 同构）。
- 坐标即实体身份（target 的 `entityType/name`），无 angle/title/seq。

## 各阶段差异

- `0.plan`：target 需 `qualifiedHomepageSource`（provider/title/url，
  schema `quwoquan_data/schema/execution/target_set.schema.json`）。
- `3.compose`：产物为 `entity_page_input.json`（非 writing_pack）；
  `verify stage-artifacts` 以此识别 homepage lane。
- `5.review`：homepage 采用 quota verdict 语义（对象级合格判定与
  article 的 rubric 独立）。
- `publish`：成品 `_entity.json` + `page.md`；delivery intent 的实体绑定为
  `entityRef`（`/entity/` 前缀）+ `tagRefs`，creator 语义与 post 载体不同
  （homepage 不做 carrier 匹配）。

## 状态

receipt 协议下 homepage lane 尚未走通首个对象；验收锚点绑定
`multi-carrier-release/spec.md` 的 `GWT-001`，实现缺口按该 spec 的 OPEN
项跟踪，本文件不虚构未实现的命令。
