# 阶段契约：sources

每个 target 只产生来源计划；本阶段不得抓取、下载或物化 source unit。

## PRE

- `0.plan` CLOSE 为 pass。
- OPEN 由 AI 显式冻结 target set、request、source policy、taxonomy/vertical policy refs。

## DURING

AI 逐 target 调研并写一份 source plan，再用 `python3 quwoquan_data/scripts/cli.py task write-source-plan --input <source-plan.json>` 提交。命令把 plan 的 `executionId`、`carrier`、`targetRef` 精确绑定当前 execution 的 `0.plan/target_set.json`，并 create-once 写到 `sources/plans/<sha256(targetRef UTF-8)>.json`（64 位小写十六进制、不带 `sha256:`）；不得直接构造可逆路径、使用目录扫描或近似匹配推测 target。每个 plan 至少说明候选 HTTPS URL/作品页、source class、目标关联理由、预期用途（正文底稿/结构化事实/媒体）、由 AI 明确选择的 `sourceUseMode`（`licensed_adaptation|factual_reference_only|rights_audit_only`）、rights 调查项、下载需求与替代候选。

正文底稿保持三百科闭集；结构化事实可额外规划官网或政府/文旅门户，且必须规划逐字段 `factSources`。搜索索引只能发现候选，不能冒充最终来源。AI 可迭代调研，但不得在本阶段写 `source unit`、`source_refs`、抓取正文或媒体 holdings。

## POST

```bash
python3 quwoquan_data/scripts/cli.py verify source-plan --execution-id <id>
```

该门按 `target_set.targetRefs` 精确计算路径并要求逐 target 唯一覆盖，不扫描猜测计划。AI 另行自检每个 target 是否有可执行来源计划、rights 调查路径和替代候选，提交真实 verifier facts。

## HANDOFF

- `resultRefs`：逐 target source plans。
- pass 后由 Skill 固定进入 `1.download`。
- 无可执行来源时 blocked；新尝试使用新 execution，不在原 execution 回跳。
