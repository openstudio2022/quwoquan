# 阶段契约：sources

每个 target 只产生来源计划；本阶段不得抓取、下载或物化 source unit。

## PRE

AI 在 OPEN 只提交并冻结 target set、request、source policy、taxonomy/vertical policy 的 exact refs。

## DURING

AI 逐 target 调研并写 source plan，再用当前真实命令逐份原子落盘：

```bash
python3 quwoquan_data/scripts/cli.py task write-source-plan --input <source-plan.json>
```

AI 明确选择候选 HTTPS URL/作品页、source class、目标关联理由、预期用途、`sourceUseMode`、rights 调查项、下载需求与替代候选。正文底稿保持三百科闭集；结构化事实可额外规划官网或政府/文旅门户，并规划逐字段 `factSources`。搜索索引只能发现候选，不能冒充最终来源。本阶段不得写 source unit、source refs、抓取正文或媒体 holdings。

## POST

机械 verifier：

```bash
python3 quwoquan_data/scripts/cli.py verify source-plan --execution-id <id>
```

AI self-check：每个 target 是否有可执行来源计划、可追溯最终来源、rights 调查路径与替代候选；正文/结构化事实来源是否遵守闭集。无可执行来源则 blocked。

## HANDOFF

- receipt ref/digest；
- `resultRefs`：逐 target source plan exact refs/digests；
- `typedIssues`；
- Skill 固定后继：`1.download`。
