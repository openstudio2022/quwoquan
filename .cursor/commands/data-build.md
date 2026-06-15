---
name: /data-build
id: data-build
category: Workflow
description: 数据工程 · 实体/标签/主页构建阶段
---

# data-build

## 命令目的
基于 catalog 生成标准化实体、标签层级树和实体主页。

## 输入
- `--task {taskId}` `--batch {batchId}` `--stage {prepare|validate|all}`
- coverageTargets：来自 `tasks/{taskId}/task.yaml` 的 `scope.coverageTargets`（每项 `{entityType, name}`，经 _defaults 继承解析）
- SOP：`sop/主页/{领域}/{类型}/{guide,template,example}.md`（全局单一真相源，不拷进任务）

## 实体三层目录

实体按「领域/类型/名称」三层组织，与标签维度 `实体类型/{领域}/{类型}` 保持一致：

```
entities/
  地点/景区/峨眉山/
  地点/遗址/东风堰/
  地点/打卡地/成都太古里/
  地点/博物馆/三星堆博物馆/
  地点/美食街/锦里小吃街/
  地点/古镇/阆中古城/
  地点/餐厅/陈麻婆豆腐/
  机构/学校/四川大学/
  活动/赛事/成都马拉松/
```

## 三段式（与三层目录实体模型一致）

### prepare — `qwq-data build --task {id} --batch {b} --stage prepare`
为每个 coverageTarget 写产出契约 `batches/{b}/build/inputs/entity_page/{ref}.json`，并写
`assistant_tasks/entity_page.json`。每个契约 payload 含：
- `name/domain/etype/entityRef/outputDir`（产出目录 = `entities/{领域}/{类型}/{名称}/`）
- `sopDir/sopTemplate/sopGuide/sopExample`（全局 SOP 路径，按需注入）
- `minChars=800`、`conditionAxes`（effective）、`regionMenu/seasonMenu`（catalog 合法取值）

### agent（模型执行，ReAct）
1. 归一化名称（中文规范名）、推导领域/类型分类（对应 `tags/实体类型/{领域}/{类型}`）、tagRefs/geoTagRef
2. 检索真实素材（不足→再检索；见 `/data-download`），按 `sopTemplate` 物化到 `outputDir`：
   - `page.md`：按 SOP 模板，**去空白 ≥ 800 字**，嵌入 /entity/ + /tag/ + asset:// 引用
   - `_entity.json`：含 `label/domain/type/sourceTaskId`，地形/季节确定时写
     `conditionProfile{regions[],seasons[],altitudeMeters,notes}`，**regions/seasons 取值须 ∈ regionMenu/seasonMenu**
   - `manifest.json`：含 tagRefs/assets/timestamps
3. 标签物化到 `tags/{dim}/{path}/_definition.json`（无 tagId，含 label/labelEn/description/timestamps）

### validate（采纳门）— `qwq-data build --task {id} --stage validate`
逐 coverageTarget 校验，全绿 exit 0、否则 exit 1（阻断 promote）：
- 三件套齐全：`_entity.json + page.md + manifest.json`
- `page.md` 去空白 ≥ 800 字
- `_entity.json` 必填 `label/domain/type/sourceTaskId`，且 domain/type 与目录一致
- 若写 `conditionProfile`：须含 regions 或 seasons，且取值 ∈ `region_catalog`/`season_catalog`
- 通过即「采纳」，`promote --copy-entities` 据此把主页拷入 publish，发布门 `entity_homepage_exists` 放行 entityRefs

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-build` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
