# quwoquan_data

`quwoquan_data` 负责可复用内容输入、不可变 execution 工作包、canonical 内容对象与环境无关 immutable release handoff。内容生产的唯一流程真相源见 [content-production Skill](../.agents/skills/content-production/SKILL.md)；本 README 只给出工程边界和最短操作入口，不复制阶段细则。

## Skill + AI Agent

宿主 Cursor/Codex IDE/CLI AI Agent 是内容语义工作的主体：选择来源与素材、质量判断、compose、创作正文/image caption/video script、自检、独立 review，并显式决定阶段 `pass|blocked`、typed issues、approved 对象、release cohort 与 milestone。仓库代码只处理确定性初始化、atomic download/CAS、schema/digest/ref/media hard facts、create-once receipt、单对象 publish 与 explicit cohort immutable release。

producer 固定为九阶段并在 `release -> END`；精确阶段顺序与每阶段契约只在 Skill 中定义。环境 import/activate/readback/health、API/App UAT、EAF、promotion、rollback/replay 是 release handoff 的下游并行 workflow，不属于内容生产阶段或完成条件。既有 `ship` CLI/环境实现保留给下游 owner。

每次只执行当前 Skill stage contract。正文、caption/script、review、typed issue、verdict、approved 对象、cohort、milestone、后继和恢复动作都不能由脚本代替 AI 决定。ReliableTask 继续作为跨域通用基础设施存在，但不参与 Data producer 阶段推进。批量并发、限流与 reviewer session 编排属于宿主 runtime，不写仓内状态。

## 工作包与只读恢复

任务输出位于：

```text
.qwq_output/data/tasks/<executionId>/
  execution_manifest.json
  0.plan/
  sources/
  entities/**/<1.download..5.review>/
  posts/<carrier>/**/<1.download..5.review>/
  _shared/
    stage-open/<sequence>-<stage>.json
    receipts/<sequence>-<stage>.json
  evidence/
    publish_refs/
```

新任务由 `task init` 原子创建 manifest、plan request 与 target set。每阶段开始前由 AI 用 `task stage-open` 点名并冻结 exact input refs；完成后用 `task stage-close` 提交 actor、verdict、typed issues、result refs 和真实 verifier facts。

恢复只读 create-once producer receipts：最后一份 `pass` receipt 对应 Skill 固定后继；已有 OPEN 而无 CLOSE 时，在同一冻结输入上重做当前阶段；最后一份 receipt 为 `blocked` 时创建新的 execution；`release` pass 后只交 handoff 并结束。恢复不改写旧 receipt，也不从聊天摘要、宿主调度或环境状态推断 producer 进度。

```bash
python3 quwoquan_data/scripts/cli.py task init --help
python3 quwoquan_data/scripts/cli.py task stage-open --help
python3 quwoquan_data/scripts/cli.py task stage-close --help
```

## 下载、发布与 release handoff

`sources` 由 AI 写逐 target source plan；`1.download` 使用窄命令下载媒体并写入 CAS。下载器只封装已选来源，不替 AI 选择候选。

```bash
python3 quwoquan_data/scripts/cli.py task acquire-images --help
python3 quwoquan_data/scripts/cli.py task acquire-videos --help
```

通过独立 review 的对象在 `publish` 逐个提交；每个 approved object package 单独执行 create-once canonical transaction，不做 execution 级批量发布。`release` 只消费 AI 显式给出的 exact cohort，生成环境无关 immutable release；不得隐式选择全部可发布对象。

```bash
python3 quwoquan_data/scripts/cli.py release publish-object --help
python3 quwoquan_data/scripts/cli.py release pool-build --help
python3 quwoquan_data/scripts/cli.py release handoff --help
```

release build 完成后，AI 先以 release refs 关闭 sequence 009 receipt，再调用 `release handoff`。writer 只机械读取并重验该 receipt、release、explicit cohort、逐对象 content-pool projection 与 producer baseline，create-once 写 release 根下的 `producer_release_handoff.json`；handoff 不进入 payload，因而 receipt/payload 与 handoff 保持单向、无 digest 循环。required contract 包含 release ref/payload+header digest、完整排序 execution IDs 及每个 execution 的 sequence-009 receipt output ref/digest、explicit cohort ref/digest、AI 显式 milestone、`homepage|article|image|video|total` counts、逐对象内嵌 query document/canonical digest 与 40 位 producer baseline commit revision；reader 仅依赖 sealed release bytes + handoff。

下游环境 owner 只读上述 immutable facts，并可使用现存 `python3 quwoquan_data/scripts/cli.py ship --help` 能力执行环境操作；其结果不回写 producer execution。

## 可复用输入与输出边界

受版本控制的可复用输入只位于 `control_plane/`、`verticals/`、`reference/`、`prompts/`、`templates/` 与 `schema/`；不得写入任务地区、数量、日期、execution identity 或运行输出。`publish/` 只保存 approved canonical objects 及其必要引用闭包，不保存 raw source、草稿、prompt、日志或 receipt。

`.qwq_output/data/` 一级只允许：

```text
tasks/       不可变 producer execution 工作包与 create-once receipts
releases/    环境无关 immutable release 与 handoff 事实
local/       可删除重跑的本地缓存与报告
```

删除 `.qwq_output/` 不得损失依赖声明、recipe、prompt、template、schema、policy 或部署规则。静态检查的组合入口保持为：

```bash
python3 quwoquan_data/scripts/cli.py verify all
```
