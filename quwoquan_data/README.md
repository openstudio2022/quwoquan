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
.qwq_output/env/<env>/runs/data-release/...              ship/import/API/readiness evidence
.qwq_output/env/<env>/runs/release-lifecycle-exit/...    rollback/replay Exit receipts
.qwq_output/env/<env>/runs/release-acceptance/...        append-only UAT lease events
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
# 目标任务初始化（规格已冻结，当前尚未实现；调用前必须确认 CLI 已落地）
python3 quwoquan_data/scripts/cli.py task init --help

# 阶段 receipt 与只读状态
python3 quwoquan_data/scripts/cli.py task stage-open --help
python3 quwoquan_data/scripts/cli.py task semantic-prepare --help
python3 quwoquan_data/scripts/cli.py task semantic-record --help
python3 quwoquan_data/scripts/cli.py task stage-gate --help
python3 quwoquan_data/scripts/cli.py task stage-close --help
python3 quwoquan_data/scripts/cli.py task fleet-status --help

# 结构与发布门禁
python3 quwoquan_data/scripts/cli.py verify content-execution-layout
python3 quwoquan_data/scripts/cli.py verify reusable-data-contract
python3 quwoquan_data/scripts/cli.py verify runtime-input-ownership
python3 quwoquan_data/scripts/cli.py verify publish-purity
python3 quwoquan_data/scripts/cli.py verify output-root-isolation
python3 quwoquan_data/scripts/cli.py verify release-lifecycle --release <releaseId>

# Canonical 发布与环境交付
python3 quwoquan_data/scripts/cli.py release --help
python3 quwoquan_data/scripts/cli.py ship --help

# 全量 Data gate（唯一静态组合入口）
python3 quwoquan_data/scripts/cli.py verify all
```

`task init` 只定义为 deterministic work-package initializer：confirmed demand 与 immutable candidate bindings 全量校验后，原子创建 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`，不推进 stage。当前实现尚未落地；在代码与 local contract 存在前，文档示例不是“命令可用”的声明。

新任务禁止使用仓内 semantic `task preflight`、`task execute`（包括 plan-only）、pool-dispatch/campaign 或人工手写工作包。宿主 Cursor/Codex IDE/CLI Agent 自行管理账号、key 与模型能力；Data 仓库不读取宿主 key/model，也不通过 SDK/provider preflight 授权 production。保留的脚本能力只有 deterministic source/CAS/publish/release/ship/receipt 与两个无业务判断薄 runner。

### Verify 三类入口

1. **static all**：`python3 quwoquan_data/scripts/cli.py verify all` 是唯一静态 gate 组合，不要新增平行 `verify-*` Make/脚本入口。
2. **on-demand**：需要具体 release、execution 或环境参数时，使用显式子命令（如 `verify release-lifecycle`、`verify execution-readiness`、`verify publish-purity`）。
3. **runtime library**：`scripts/verify/*.py` 与领域模块供 CLI/gate import；直接 `python3 .../verify_*.py` 只供本地调试，不算正式入口。

`scripts/` 保持 `cli.py` / `core/` / `content/` / `governance/` / `verify/` 闭集；稳定脚本名用语义描述，禁止阶段编号、批次编号和数字分片名。


## 输出边界

`.qwq_output/data/` 一级只允许：

```text
tasks/       单次 execution 工作包
releases/    不可变数据发布包
local/       repo 级可重跑缓存与 workspace 报告
```

静态配置、证书生成规则、网络拓扑、部署模板不属于 output。环境配置归各领域 `configs/deploy` 或 `quwoquan_ops/environments`；output 只记录运行产生的状态、证据和包。
删除整个 `.qwq_output/` 后，依赖声明、recipe、prompt、template、schema、policy 与部署规则仍必须完整存在于代码仓；缓存可加速执行，但不得成为任务启动或重建的前置真相源。
