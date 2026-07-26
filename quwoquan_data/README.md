# quwoquan_data

`quwoquan_data` 负责可复用内容生产输入、单次内容执行、可发布数据对象和环境发布包。
唯一入口是：

```bash
python3 quwoquan_data/scripts/cli.py
```

## 三段职责

### 1. 可复用输入（代码仓）

```text
control_plane/families/   recipe、preset、runtime profile
verticals/                覆盖主清单与垂类静态规则
reference/                受版本控制的参考数据
prompts/                  Agent 提示词
templates/                内容模板
schema/                   execution、post、publish 等契约
```

这些目录只保存跨任务复用的规则，禁止写省份批次、日期、executionId 或运行输出路径。
`content/travel/{homepage,article,image,video}` 各自拥有可复用 preset、prompt 与强类型执行契约；
视频正文由 Agent 产出结构化脚本，CLI 只做权利校验、确定性渲染与证据封装。

### 2. Execution 工作包（`.qwq_output`）

```text
.qwq_output/data/tasks/<executionId>/
  execution_manifest.json
  0.plan/
  sources/
  entities/.../1.content.source..5.review/
  posts/<kind>/.../1.content.source..5.review/
  _shared/
  evidence/
  publish_ref.json
```

`executionId` 是唯一运行身份：

```text
YYYYMMDD--<vertical>-<contentType>-<intent>--<scope>--<pilot|scale|full>-<sequence>
```

同一 ID 只允许参数完全相同的 resume；新尝试递增 sequence，并通过 `retryOf` 关联。
工作包包含规划、来源、五阶段过程、审计证据和 release 引用，可整体删除后重跑，不提交 Git。

### 3. 发布与环境证据

```text
quwoquan_data/publish/                         approved canonical objects
.qwq_output/data/releases/<releaseId>/         immutable environment-neutral package
.qwq_output/env/<env>/runs/data-release/...    ship/import/API/UAT evidence
```

`publish/**` 只允许最终 `creators/entities/posts/media` 对象，以及被这些对象引用的
`tags/<tagRef>/_definition.json` consumer snapshot。control-plane taxonomy 仍是唯一可编辑真相源；
发布树只物化被引用叶子，禁止复制整棵 taxonomy、creator profile、raw source、草稿、prompt、日志、
报告、导入回执或环境配置。

## 异常契约

Data 离线流水线使用 `scripts/core/data_issue.py` 与
`schema/_common/data_issue.schema.json` 作为唯一内部异常契约。`code`、`recovery`、
`stage/ref/lane` 驱动自动重试、回退和停止；`message` 只供人读，
禁止解析文案决定控制流。`attrs` 只允许受限的 string-only 小字段。

服务 HTTP 边界仍使用 `quwoquan_service/contracts/runtime_errors` 和 metadata
`errors.yaml`。Data importer/ship 进入服务边界时必须显式映射稳定 Data issue code 与
服务错误码；两者不共享持久化对象，也不复制第二份错误文案真相源。

## 主要命令

```bash
# 任务门面
python3 quwoquan_data/scripts/cli.py task execute --help

# 环境与凭证
python3 quwoquan_data/scripts/cli.py task preflight --json

# 结构与发布门禁
python3 quwoquan_data/scripts/cli.py verify content-execution-layout
python3 quwoquan_data/scripts/cli.py verify reusable-data-contract
python3 quwoquan_data/scripts/cli.py verify runtime-input-ownership
python3 quwoquan_data/scripts/cli.py verify publish-purity
python3 quwoquan_data/scripts/cli.py verify output-root-isolation
python3 quwoquan_data/scripts/cli.py verify release-lifecycle --release <releaseId>

# Canonical 发布与 taxonomy
python3 quwoquan_data/scripts/cli.py release --help
python3 quwoquan_data/scripts/cli.py governance taxonomy --help

# 全量 Data gate
python3 quwoquan_data/scripts/cli.py verify all
```

Cursor SDK 凭证默认只从仓外、权限为 `0600` 的
`~/.config/quwoquan/cursor_api_key` 动态读取；`QWQ_CURSOR_API_KEY_FILE`
仅用于受控测试或显式替换该位置。禁止 token 环境变量、仓内凭证、指纹或 token
片段进入日志与 manifest。

## 输出边界

`.qwq_output/data/` 一级只允许：

```text
tasks/       单次 execution 工作包
releases/    不可变数据发布包
local/       repo 级可重跑缓存与 workspace 报告
```

静态配置、证书生成规则、网络拓扑、部署模板不属于 output。环境配置归各领域 `configs/deploy` 或 `quwoquan_ops/environments`；output 只记录运行产生的状态、证据和包。
删除整个 `.qwq_output/` 后，依赖声明、recipe、prompt、template、schema、policy 与部署规则仍必须完整存在于代码仓；缓存可加速执行，但不得成为任务启动或重建的前置真相源。
