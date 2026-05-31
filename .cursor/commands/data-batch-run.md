# data-batch-run

用途：批量编排数据工程内容生产。Skill 只负责调用 CLI、分发 `compose_brief`、触发 compose/review/materialize/promote，不代写正文。

## 标准流程

1. 校验模板库：

```bash
python3 quwoquan_data/scripts/cli.py template lint
python3 quwoquan_data/scripts/cli.py template creator-lint
python3 quwoquan_data/scripts/cli.py template rec-contract
python3 quwoquan_data/scripts/cli.py template region-season-lint
```

2. 将用户指令解析为 10D 输入：

- subject：entity 或 topic
- intent：攻略、路线推荐、深度报道、探店、美图等
- carrier：article/image/review/video
- audience：读者人格
- creatorPersona：由模板路由匹配
- region：地域条件维（高原/沿海海岛/平原都市/沙漠戈壁/山地森林/雨林秘境/雪山/乡村田园），不参与选模板，只做条件注入
- season：季节条件维（春/夏/秋/冬/雨季/旱季/旺季/淡季），同样只做条件注入

地域/季节是正交条件修饰维：同一模板在不同 region/season 下注入不同 facts、风险、打包与图位，禁止为每个地域/季节另建模板。

3. 生成 compose brief：

```bash
python3 quwoquan_data/scripts/cli.py plan \
  --instruction "为川西做自驾线路攻略，面向休闲游客" \
  --output quwoquan_data/runtime/tasks/<task>/batches/<batch>/produce/inputs/compose/<ref>.json
```

或显式输入（含地域/季节条件维）：

```bash
python3 quwoquan_data/scripts/cli.py plan \
  --subject topic \
  --kind 线路 \
  --vertical travel \
  --intent 路线推荐 \
  --audience selfDriveTraveler \
  --region 高原 \
  --season 冬 \
  --entity-refs 地点/景区/四姑娘山,地点/古镇/丹巴甲居 \
  --output quwoquan_data/runtime/tasks/<task>/batches/<batch>/produce/inputs/compose/<ref>.json
```

`--region/--season` 命中且模板声明 `conditionAxes` 适用时，brief 会注入 `conditionContext` 与对应 `mustIncludeFacts/imagePlan`，并透传到 recommendation manifest。地域季节矩阵批量生产示例：同一受众 × {高原, 沿海海岛} × {夏, 冬} 跑成多个 brief。

4. 对每个 brief 调用 `data-content-compose` 生成正文；不得在本 Skill 内写正文。

5. 生成后运行：

```bash
python3 quwoquan_data/scripts/cli.py produce --task <task> --batch <batch> --type article --materialize
python3 quwoquan_data/scripts/verify_content_quality.py --task <task> --batch <batch>
```

6. 门禁通过后再 publish/promote。

## 自驾与地理制作优先路由

- 自驾路书：`--subject topic --kind 线路 --intent 路线推荐 --audience selfDriveTraveler`
- 地理深读：`--subject topic --kind 主题 --intent 深度报道`
- 图文画报：`--subject topic --kind 主题 --intent 美图 --audience photoTraveler`
- 专业导览：`--subject entity --kind 景区 --intent 行前指南`

## 禁止

- 禁止跳过 `template lint`。
- 禁止把 `creatorProfileId`、`isSystemBuiltin`、推荐权重写进正文。
- 禁止没有真实 sources 时直接 promote。
