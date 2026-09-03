# quwoquan_data

`quwoquan_data` 负责可复用内容输入、不可变 execution 工作包、canonical 内容对象、release 与环境交付。内容生产的唯一业务流程见 [content-production Skill](../.agents/skills/content-production/SKILL.md)；本 README 只给出工程边界和最短操作入口，不复制阶段细则。

## Skill + AI Agent

宿主 Cursor/Codex IDE/CLI AI Agent 是内容语义工作的主体：选择来源、取舍素材、创作、自检、独立 review，并显式决定阶段 `pass|blocked`、发布对象和 release cohort。仓库代码只处理确定性初始化、下载/CAS、schema 与引用闭包校验、create-once receipt、单对象 publish、immutable release 和 ship 原子 IO。

固定十阶段为：

```text
0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review
-> publish -> release -> ship -> END
```

每次只执行当前阶段及其 Skill stage contract。正文、review、typed issue、verdict、后继阶段和恢复动作都不能由脚本代替 AI 决定。ReliableTask 继续作为跨域通用基础设施存在，但不参与 Data 内容阶段推进。

## 工作包与只读恢复

任务输出位于：

```text
.qwq_output/data/tasks/<executionId>/
  execution_manifest.json
  0.plan/
  sources/
  entities/**/<1.download..5.review>/
  posts/<carrier>/**/<1.download..5.review>/
  _shared/stage-authority/<stage>/open.json
  _shared/receipts/<stage>.json
  evidence/publish_refs/
```

新任务由 `task init` 原子创建 manifest、plan request 与 target set。每阶段开始前由 AI 用 `task stage-open` 显式提交并冻结 exact input refs；完成后用 `task stage-close` 提交 actor、verdict、typed issues、result refs 和真实 verifier facts。

恢复只读 create-once receipts：最后一份 `pass` receipt 对应十阶段中的固定后继；已有 OPEN 而无 CLOSE 时，在同一冻结输入上重做当前阶段；最后一份 receipt 为 `blocked` 时创建新的 execution。恢复过程不改写旧 receipt，也不从聊天摘要或可变运行状态推断进度。

```bash
python3 quwoquan_data/scripts/cli.py task init --help
python3 quwoquan_data/scripts/cli.py task stage-open --help
python3 quwoquan_data/scripts/cli.py task stage-close --help
```

## 下载、发布与交付

`sources` 阶段由 AI 写逐 target source plan；`1.download` 使用窄命令下载媒体并写入内容寻址存储（CAS）。下载器只封装已选来源，不替 AI 选择候选。

```bash
python3 quwoquan_data/scripts/cli.py task acquire-images --help
python3 quwoquan_data/scripts/cli.py task acquire-videos --help
```

通过独立 review 的对象在 `publish` 阶段逐个提交；每个 approved object package 单独执行 create-once canonical transaction，不做 execution 级批量发布。`release` 只消费 AI 显式给出的 exact cohort，生成环境无关的 immutable release；不得隐式选择“全部可发布对象”。`ship` 只消费该 release 的精确身份，显式执行目标环境 apply、import/readback、health 与环境 acceptance。

```bash
python3 quwoquan_data/scripts/cli.py release --help
python3 quwoquan_data/scripts/cli.py ship --help
```

`acceptanceProfile=m1_api_consumer` 保留环境生命周期、Service API consumer fresh facts 与同 identity 的环境 acceptance，不要求 App/设备证据。`acceptanceProfile=environment_promotion` 才额外要求对应 App UAT 与 target binding。Service API integration 和环境 acceptance 是交付证据，不是内容编排入口。

## 可复用输入与输出边界

受版本控制的可复用输入只位于 `control_plane/`、`verticals/`、`reference/`、`prompts/`、`templates/` 与 `schema/`；不得写入任务地区、数量、日期、execution identity 或运行输出。`publish/` 只保存 approved canonical objects 及其必要引用闭包，不保存 raw source、草稿、prompt、日志或 receipt。

`.qwq_output/data/` 一级只允许：

```text
tasks/       不可变 execution 工作包与 create-once receipts
releases/    环境无关的 immutable release
local/       可删除重跑的本地缓存与报告
```

删除 `.qwq_output/` 不得损失依赖声明、recipe、prompt、template、schema、policy 或部署规则。静态检查的组合入口保持为：

```bash
python3 quwoquan_data/scripts/cli.py verify all
```
