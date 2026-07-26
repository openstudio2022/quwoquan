---
name: /crawl
id: crawl
category: Workflow
description: quwoquan_data 单 execution 内容生产与发布总门面
---

## 目标

把一个内容目标从运行参数、真实来源、五阶段生产、review、canonical publish、
immutable release 一直编排到环境导入。只允许调用 `qwq-data task execute` 门面，
不暴露阶段角色命令、退役的双层运行身份或第二运行根。

## 自然语言等价触发

用户说“按区域生成主页”“跑内容任务到发布”“生产内容并导入环境”时，均按本命令语义执行。

## Spec Entry

- AppRoot Journey/Scenario：按内容消费 Journey 绑定。
- L1/L2/L3：按当前内容垂类、能力与 Story 绑定。
- 验收意图：`contract + SIT + UAT`。
- 测试证据：`local_contract + api_integration + user_acceptance`。

## Pre-work Reflection

- 可复用 recipe/prompt/template/schema 不得包含地域、日期、实体或输出路径。
- 运行参数必须包含可读 `executionId`；同 ID 只 resume，新尝试递增 sequence 并写 `retryOf`。
- 正文由 Agent 基于 source 与 prompt 创作；不得用 fixture、拼接正文或历史产物补绿。
- 凭证默认只从仓外 `~/.config/quwoquan/cursor_api_key` 动态读取；显式
  `QWQ_CURSOR_API_KEY_FILE` 仅用于受控替换。开始前执行 `task preflight`。

## 唯一入口

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

## 输出边界

- 可复用源码：`quwoquan_data/{control_plane,verticals,reference,prompts,templates,schema}/`。
- 单执行工作包：`.qwq_output/data/tasks/<executionId>/`。
- 发布业务真相源：`quwoquan_data/publish/{creators,entities,posts,media,tags}/`。
- 不可变发布包：`.qwq_output/data/releases/<releaseId>/`。
- 环境执行证据：`.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/`。

## Exit Review

```bash
python3 quwoquan_data/scripts/cli.py verify execution-readiness --execution-id <executionId>
python3 quwoquan_data/scripts/cli.py verify output-root-isolation
python3 quwoquan_data/scripts/cli.py verify publish-purity
```

如来源、权利、Cursor、环境导入、API 或 App UAT 未闭合，返回带 executionId 的
`GATE_BLOCK`，不得跳过或复用旧输出。
