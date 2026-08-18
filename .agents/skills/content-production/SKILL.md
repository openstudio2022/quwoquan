---
name: content-production
description: Run the canonical quwoquan data content workflow from reusable inputs through one execution work package, immutable release, environment import, and App UAT, and diagnose or resume a failed execution. Make sure to use this skill whenever the user mentions 按区域生成主页, 跑内容任务, 内容生产, 生产内容并导入环境, 复核 execution, 恢复内容任务, 重试实体任务, immutable release, or 数据发布, even without an explicit command.
metadata:
  kind: workflow
---

# content-production

从可复用输入到 execution 工作包、immutable release、环境导入与 App UAT 的内容生产主线。
五段执行契约见根 `AGENTS.md`。唯一编排入口：

```bash
python3 quwoquan_data/scripts/cli.py <command> ...
```

脚本负责 IO、契约、下载、校验、发布与证据；**正文语义创作只由 Agent 完成**。
禁止新增直跑业务脚本、静态任务实例、分片运行根或第二套发布流程。

## 触发

无斜杠命令，自然语言自动触发：内容生产、区域主页、execution 恢复/重试、
immutable release、环境导入、App UAT。

## 输入

- family / vertical / contentType 与 `--family` recipe 路径。
- 区域范围（`--region-ref`）、selector、count、stage。
- `executionId`（格式 `YYYYMMDD--<vertical>-<contentType>-<intent>--<scope>--<pilot|scale|full>-<sequence>`）；
  诊断/恢复时为已存在的工作包 ID。
- 目标环境与 canonical source；凭证：仓外 `0600` 的 `~/.config/quwoquan/cursor_api_key`。

## 角色

见 [references/roles/](references/roles/)，六个执行角色按主线顺序接力：

- [planner](references/roles/planner.md)：冻结 scope 与 execution。
- [source-researcher](references/roles/source-researcher.md)：收集可追溯来源。
- [content-author](references/roles/content-author.md)：只基于 source 与 prompt 创作正文。
- [quality-reviewer](references/roles/quality-reviewer.md)：校验 schema/事实/媒体/标签。
- [rights-reviewer](references/roles/rights-reviewer.md)：校验授权与商用范围。
- [release-operator](references/roles/release-operator.md)：publish / ship / 环境导入 / UAT。

## 执行

自由度：低（CLI 门面与阶段顺序固定）。

单一 execution work package 主线：

```text
0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review
-> publish -> release -> ship -> 环境导入 -> App UAT
```

开始前 preflight，再用唯一任务门面执行：

```bash
python3 quwoquan_data/scripts/cli.py task preflight --json
python3 quwoquan_data/scripts/cli.py task execute \
  --execution-id YYYYMMDD--travel-homepage-coverage--cn-region-a--pilot-001 \
  --family content/travel/homepage/homepage \
  --region-ref china/test-region-a \
  --selector priority \
  --count 1 \
  --stage run
```

- 仓库输入、工作包布局、canonical/publish 路径与命名约束见
  [references/execution-layout.md](references/execution-layout.md)。
- 诊断与恢复（同 ID resume、递增 sequence + `retryOf`）见
  [references/diagnose-and-resume.md](references/diagnose-and-resume.md)。
- 每次运行由 `0.plan/request.json` 冻结目标、数量和阶段；任一运行先完成真实来源、
  逐图权利、Agent 创作、独立 review、canonical 原子发布、目标环境幂等导入、
  服务 API 核验、消费者 UAT、回滚与重放，才能创建下一次运行。

## 交付件

**immutable release + 环境导入证据**：execution work package、canonical 对象、
release id、环境导入回执与 App UAT 结果。

送审前自检（publish 前逐项）：

```bash
python3 quwoquan_data/scripts/cli.py task preflight --json
python3 quwoquan_data/scripts/cli.py verify content-execution-layout
python3 quwoquan_data/scripts/cli.py verify publish-purity
python3 quwoquan_data/scripts/cli.py verify release-lifecycle --release <releaseId>
python3 quwoquan_data/scripts/cli.py verify all
python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --profile integration
```

## 内置评审

- publish 前 POST 调 `review`（workflow=`content-production`，segment=POST，
  deliverable=`content-release`），角色 data-quality + data-legal——板外复核，
  独立于本 Skill 内 quality-reviewer / rights-reviewer 执行角色的自查。

## 失败与停止

- 脚本不生成、拼接或填充正文；不新增第二任务身份、运行根、发布流或环境 seed。
- [MUST NOT] 补写缺失的 source、rights、review 或 release 证据。
- 失败必须保留明确的阶段与原因，不得迁移、兼容或伪造通过。
- 凭证、来源、权利、Gamma、API 或 App 任一真实证据缺失：返回带 executionId 的
  `GATE_BLOCK`，不得用 fixture、skip、历史数据或估算报告替代。
- 任何输出不得包含 key、片段或指纹。

## HANDOFF

- **产出物**：release 与 UAT 证据，报告给用户。
- **未决项去向**：失败 execution 保留阶段与原因，恢复入口见 diagnose-and-resume。
- **唯一合法下游**：App 侧问题交接 `dev`；其余报告给用户结束。
- **证据链**：`.qwq_output/data/tasks/<executionId>/evidence/`、
  `.qwq_output/data/releases/<releaseId>/`、
  `.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/`。
