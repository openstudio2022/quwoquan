# quwoquan_data

`quwoquan_data` 负责 Travel Research 可复用内容输入、不可变 execution 工作包、canonical 内容对象与 immutable producer release handoff。内容生产的唯一流程真相源见 [content-production Skill](../.agents/skills/content-production/SKILL.md)；本 README 只给出工程边界和最短操作入口，不复制阶段细则。

## Skill + AI Agent

宿主 Cursor/Codex IDE/CLI Agent 是唯一内容语义主体：选择来源与素材、质量判断、compose、创作每对象唯一 carrier draft、自检、独立写每对象唯一 `content_review.json`，并显式决定 `pass|blocked`、typed issues、approved 对象、release cohort 与 milestone。仓库代码只处理 identity-only 初始化、atomic download/CAS、schema/digest/ref/media hard facts、create-once receipt、单对象 publish 与 explicit cohort immutable release。

producer 固定为九阶段并在 `release -> END`；精确阶段顺序与每阶段契约只在 Skill 中定义。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion、rollback/replay 全部 out of scope，不属于 producer 阶段、handoff 字段、恢复或完成条件。

每次只执行当前 Skill stage contract。正文、caption/script、review、typed issue、verdict、approved 对象、cohort、milestone、后继和恢复动作都不能由脚本代替 Agent 决定。不同 execution 可由宿主原生并行；同一 execution 的 `4.draft` 全部对象由一个 author 会话负责，`5.review` 全部对象由另一个 reviewer 会话负责。不得新增 resolver/projector/runner/controller/queue/registry/SDK、actor projection 或自动恢复。

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

新任务由 `task init` 从只冻结目标对象身份的 candidate bindings 原子创建 manifest、plan request 与 target set；不要求 pre-init source/media admission。每阶段开始前由 Agent 用 `task stage-open` 点名并冻结 exact input refs；完成后用 `task stage-close` 提交 actor、verdict、typed issues、result refs 和真实 verifier facts。

恢复只读 create-once producer receipts：最后一份 `pass` receipt 对应 Skill 固定后继；已有 OPEN 而无 CLOSE 时，在同一冻结输入上重做当前阶段；最后一份 receipt 为 `blocked` 时创建新的 execution；`release` pass 后只交 handoff 并结束。恢复不改写旧 receipt，也不从聊天摘要、宿主调度或环境状态推断 producer 进度。

```bash
python3 quwoquan_data/scripts/cli.py task init --help
python3 quwoquan_data/scripts/cli.py task stage-open --help
python3 quwoquan_data/scripts/cli.py task stage-close --help
```

## 下载、发布与 release handoff

`sources` 由 Agent 选择来源并写逐 target source plan；`1.download` 才取得 bytes、生成 source units/source refs/CAS 与 MIME/digest/probe/rights hard facts。下载器只封装已选来源，不替 Agent 选择候选；不要求 `source.clean.md|source.layout.json|source.quality.json`。

```bash
python3 quwoquan_data/scripts/cli.py task acquire-images --help
python3 quwoquan_data/scripts/cli.py task acquire-videos --help
```

`4.draft` 每对象只保留 `page.md|draft.article.md|image_work.json|video_script.json` 之一，author actor/invocation、自检与 digests 由 sequence-006 receipt 冻结；`5.review` 每对象只保留 `content_review.json`，reviewer actor/invocation 与 exact digest 由 sequence-007 receipt 冻结。通过独立 review 的对象在 `publish` 逐个提交；`release` 只消费 Agent 显式 exact cohort，不得隐式全选。

```bash
python3 quwoquan_data/scripts/cli.py release publish-object --help
python3 quwoquan_data/scripts/cli.py release pool-build --help
python3 quwoquan_data/scripts/cli.py release handoff --help
```

release build 完成后，Agent 先以 release refs 关闭 sequence 009 receipt，再调用 `release handoff`。M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 累计，每级形成自己的 full explicit cohort/release/handoff；更高级别复用 canonical 对象及其原 execution/publish proof，不伪造新九阶段 receipts。writer 机械重验 release、cohort、逐对象 content-pool projection、原 producer proofs 与 baseline 后 create-once 写 `producer_release_handoff.json`。handoff 只含 producer facts，不含 UAT/sample authority/import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback。

任何外部 consumer 只可只读上述 immutable producer facts；其操作与结果不回写 producer execution，也不构成 producer 完成条件。

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
