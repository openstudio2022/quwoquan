# data-batch-run

用途：批量编排数据工程内容生产。Skill 只负责调用 CLI、分发 `compose_brief`、触发 compose/review/materialize/promote，不代写正文。

## 两种规模 · 一套动词

单/多 agent 共用同一套 `qwq-data` 动词与同一 DAG，差异只在「驱动者 + 并发 + CHECKPOINT 接缝」（见 `quwoquan_data/docs/fanout_scaffold_spec.md`）：

- **单分区/小批（默认，本页「标准流程」）**：会话内单 agent 顺序跑，CHECKPOINT 由会话 Agent 创作后 `--resume`。
- **大规模分层（多省/区县/多对象）→ 委托 fanout**：先 `qwq-data task decompose` 发现式分片冻结计划，再 `qwq-data task run --mode fanout` 建多 task/batch + 入队叶子，最后外部 `agent_ops/runners/fanout_runner.py` 多 worker 并行（每 worker=独立 cloud agent）。

```bash
# 阶段 A：发现式分解 + 冻结（agent 联网枚举分区/叶子写回）
python3 quwoquan_data/scripts/cli.py task decompose init --plan <planId> --goal "全国景点主页" --vertical travel --entity-type "地点/景区" --category 景区 --strategy by-partition --concurrency 8
python3 quwoquan_data/scripts/cli.py task decompose add-partition --plan <planId> --key 四川省
python3 quwoquan_data/scripts/cli.py task decompose add-leaves   --plan <planId> --partition 四川省 --leaves "九寨沟,稻城亚丁,峨眉山"
python3 quwoquan_data/scripts/cli.py task decompose show   --plan <planId>          # 发现门
python3 quwoquan_data/scripts/cli.py task decompose freeze --plan <planId> --confirm # 人工冻结

# 阶段 B：确定性分层调度（建 task/batch + 入队叶子，幂等可重放）
python3 quwoquan_data/scripts/cli.py task run --mode fanout --plan <planId> --strategy by-partition --concurrency 8

# 外部多 worker 执行（cursor-sdk 真实执行）+ 归并治理
python3 agent_ops/runners/fanout_runner.py --plan <planId> --strategy by-partition --concurrency 8
python3 quwoquan_data/scripts/cli.py task rollup --plan <planId>
```

`--mode fanout --strategy flat-pool --concurrency 1` 与单模式同终态（退化等价）；策略可一键切 `by-partition / flat-pool / by-leaf / by-batch`。

## 标准流程（单分区/小批）

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
python3 quwoquan_data/scripts/verify/verify_content_quality.py --task <task> --batch <batch>
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

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-batch-run` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
