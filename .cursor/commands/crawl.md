---
name: /crawl
id: crawl
category: Workflow
description: quwoquan_data 端到端内容供给总控
---

## 目标

`/crawl` 是自然语言路由入口，实际执行必须收束到 `qwq-data task` 主干。
当前不再直接操作 `quwoquan_data/runtime/**`、`.qwq_sandbox/**`、`artifacts/**`
或一次性 runner shell。

## 自然语言等价触发

当用户说“跑抓取总控”“跑内容候选到发布闭环”“按省市区生成主页批次”等价于 `/crawl`。

## Spec Entry

- AppRoot Journey/Scenario：`runtime/system-architecture-and-engineering-guide`
- L1/L2/L3：按当前数据任务或目录治理 Story 绑定。
- 验收意图：`SIT + contract`
- 测试证据：`local_contract + api_integration`

## Pre-work Reflection

- metadata-first：读取 `quwoquan_service/contracts/metadata/**`，不自建第二真相源。
- data CLI-first：只用 `python3 quwoquan_data/scripts/cli.py`。
- output-first：运行输出只进 `.qwq_output/**`。
- E2E：需要证明 Data -> Service -> App -> Observability 无断点时再触发跨域验证。

## 真相源

- 任务定义：`quwoquan_data/control_plane/tasks/**/task.yaml`
- 可复用配方：`quwoquan_data/control_plane/families/**/*.recipe.yaml`
- 运行输出：`.qwq_output/local/data-runtime/**`
- 运行报告：`.qwq_output/runs/data/**`
- 发布真相源：`quwoquan_data/publish/**`
- 发布包：`.qwq_output/release/data/**`

## 主入口

地域主页批次使用薄门面：

```bash
python3 quwoquan_data/scripts/cli.py task geo-homepages \
  --profile h100 \
  --country 中国 \
  --province 四川省 \
  --limit 100 \
  --stage run
```

通用批次编排使用 recipe：

```bash
python3 quwoquan_data/scripts/cli.py task run-recipe \
  content/travel/homepage/h100 \
  --limit 100 \
  --stage run
```

## 验收

```bash
python3 quwoquan_data/scripts/cli.py task lint
python3 quwoquan_data/scripts/cli.py verify output-root-isolation
python3 quwoquan_data/scripts/cli.py verify --scope current
```

禁止把旧 `runtime/`、`.qwq_sandbox/`、`artifacts/` 路径作为当前入口或证据。

## Exit Review

- 规格达成：任务定义、recipe、运行参数与发布真相源一致。
- 测试证据：至少完成 `task lint` 与 `verify output-root-isolation`。
- 剩余风险：如需真实下载、ship/import 或远端环境，必须单独列明未跑原因。

## 输出

输出只允许是 `.qwq_output/**` 报告、`quwoquan_data/publish/**` 发布真相源和必要的验收摘要。
