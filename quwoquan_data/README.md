# quwoquan_data

`quwoquan_data` 负责 Travel Research 可复用内容输入、不可变 execution 工作包、canonical 内容对象与 immutable producer release handoff。内容生产的唯一流程真相源见 [content-production Skill](../.agents/skills/content-production/SKILL.md)；本 README 只给出工程边界和最短操作入口，不复制步骤细则。

## Skill + AI Agent

宿主 Cursor/Codex IDE/CLI Agent 是唯一内容语义主体：判定来源类型与载体、点名来源 URL 与相关性理由、创作每对象唯一 carrier 产物、以另一个真实会话独立写 `content_review.json` 的判断字段，并显式决定 approved 对象、release cohort 与 milestone。仓库代码只处理 identity-only 初始化、机械取得字节与权利硬事实、schema/digest/ref/media 校验、create-once seal receipt、单对象 publish 与 explicit cohort immutable release。

producer 固定为六步 `init → acquire → author → review → publish → release`，`release finalize` 成功即 `END`。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion、rollback/replay 全部 out of scope；下游 owner 是 Environment Ops scheduler，Data 不创建环境 acceptance。

两个 actor：主会话直接完成 init/acquire/author/publish/release；`review` 由另一个 reviewer 会话完成，全局至多一个前台 reviewer 调用。不得新增 resolver/projector/runner/controller/queue/registry/SDK、actor projection、stage-open 或自动恢复。

## 工作包与只读恢复

```text
.qwq_output/data/tasks/<executionId>/
  execution_manifest.json
  0.plan/{request.json,target_set.json}
  sources/<unit>/{meta.json,source.md,snapshot.*,assets/}
  sources/plans/<sha256>.json            # acquire 请求原文
  entities/**/<1.download|4.draft|5.review>/
  posts/<carrier>/**/<1.download|4.draft|5.review>/
  _shared/receipts/{001-1.download,002-4.draft,003-5.review}.json
  evidence/object-transactions/
```

恢复只读 `_shared/receipts/`：找首个未闭合步骤继续；最后一份 receipt 为 `blocked` 时创建新 execution。恢复不改写旧 receipt，也不从聊天摘要、宿主调度或环境状态推断 producer 进度。

```bash
python3 quwoquan_data/scripts/cli.py task init --help
python3 quwoquan_data/scripts/cli.py task acquire --help
python3 quwoquan_data/scripts/cli.py task seal --help
```

## 取得、发布与 release

`task acquire` 只接收 AI 点名的 `{kind: page|image|video, url, relevance}`：MediaWiki 页面走 API 取纯文本；Commons 文件页走 imageinfo API 取直链、license、作者，下载字节并算 sha256，图片按预算降采样，视频 ffprobe 并抽 poster。license 不在研究白名单（CC0/CC BY/CC BY-SA/PD）即 `GATE_BLOCK`。

`4.draft` 每对象只保留 `page.md|draft.article.md|image_work.json|video_script.json` 之一，标题/tagRefs/creatorProfileId 由产物自身声明；`5.review` 每对象只保留 `content_review.json`，`task seal --stage 5.review` 补齐机械字段。approved 对象逐个 `publish-object`；`release finalize` 消费 AI 显式 cohort，一次完成 pool-build、release-integrity 与 create-once handoff。

```bash
python3 quwoquan_data/scripts/cli.py release publish-object --help
python3 quwoquan_data/scripts/cli.py release finalize --help
python3 quwoquan_data/scripts/cli.py release handoff-verify --help
```

M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 累计，每级形成自己的 full explicit cohort/release/handoff；凡已完成 canonical publish 且 review approved 的对象都可复用进入 cohort。handoff 以 canonical publish proof 为凭，记录 `producerBaselineRevision` 与 `producerContractDigest`，不含 UAT/import/readback/EAF/promotion/rollback。任何外部 consumer 只可只读上述 immutable producer facts。

## 可复用输入与输出边界

受版本控制的可复用输入只位于 `control_plane/`、`verticals/`、`reference/`、`prompts/`、`templates/` 与 `schema/`；不得写入任务地区、数量、日期、execution identity 或运行输出。`publish/` 只保存 approved canonical objects 及其必要引用闭包，不保存 raw source、草稿、prompt、日志或 receipt。

`.qwq_output/data/` 一级只允许：

```text
tasks/       不可变 producer execution 工作包与 create-once receipts
releases/    环境无关 immutable release 与 handoff 事实
local/       cache/ runs/ workspace/ 三个子目录；本次 run 的输入放 workspace/<run>/
```

删除 `.qwq_output/` 不得损失依赖声明、recipe、prompt、template、schema、policy 或部署规则。静态检查的组合入口保持为：

```bash
python3 quwoquan_data/scripts/cli.py verify all
```
