# 仓库输入与 execution 布局

## 可复用工程输入（唯一允许进版本库的内容输入）

```text
quwoquan_data/control_plane/families/content/<vertical>/<contentType>/
quwoquan_data/verticals/
quwoquan_data/reference/
quwoquan_data/prompts/
quwoquan_data/templates/
quwoquan_data/schema/
```

- family recipe 只声明可复用规模、runtime 和质量参数，不包含省份、日期、实体、
  executionId 或输出路径。
- 区域范围、discovery、count、execution phase 和 executionId 只通过 CLI 参数进入执行。
- 实体类型只读 taxonomy/schema；内容结构和语言规则只读 template/prompt。
- 宿主 Cursor/Codex 的账号、key 与模型能力归宿主自身；Data 仓库、工作包、日志与 receipt 不读取或保存它们。

## 单任务 execution 工作包

每次内容任务只写：

```text
.qwq_output/data/tasks/<executionId>/
  execution_manifest.json
  0.plan/
  sources/
  entities/<域>/<类型>/<名称>/<1.download..5.review>/          # 仅 homepage 载体
  posts/<carrier>/<angle>/<title>/<seq>/<1.download..5.review>/ # article|image|video
  _shared/
    execution_state.json          # 唯一状态快照，只经 save_execution_state 写
    receipts/<seq>-<stage>.json   # 阶段交接回执链（权威条目，create-once）
    claims/                       # lane claim（可清理过程层，心跳 + TTL）
  evidence/
  publish_ref.json
```

对象根按载体分根 **fail closed**（DEC-027，与 canonical publish 同构）：
article/image/video 对象落在 `entities/**` 下、或 homepage 对象落在
`posts/**` 下，都会被 `verify content-execution-layout` 在 `0.plan` /
`1.download` 截面拦截。post 载体的 `<angle>/<title>/<seq>` 坐标由
`0.plan/target_set.json` 逐 target 冻结
（`publishAngle/publishTitle/publishSeq`，schema 真相源
`quwoquan_data/schema/execution/target_set.schema.json`），对象五阶段目录
按该坐标创建；creator 与 tag 绑定（`creatorProfileRef/tagRefs`）由
`3.compose/writing_pack.json` 冻结。

- 工作包根条目 allowlist 由 `quwoquan_data/scripts/core/paths.py` 拥有；
  `_shared` 条目必须先登记角色（authoritative/reclaimable）再写入。
- 对象级五阶段目录名与每阶段必需产物清单的真相源是
  `quwoquan_data/scripts/core/stage_artifact_contract.py`，本 skill 不复制。

`executionId` 必须符合：

```text
YYYYMMDD--<vertical>-<contentType>-<intent>--<scope>--<pilot|scale|full>-<sequence>
```

同一 ID 只允许 resume。新尝试递增 sequence，并在根 manifest 中声明 `retryOf`。
不允许 taskId、batchId、planId、workerId 或其它平行身份。

阶段 packet 只携带 `executionId` 关联根 manifest；recipe、参数、源码、prompt 和
来源 revision 不在每个对象重复写入。图片、事实、权利、creator、tag、实体与
review 决策必须可回溯。

## 发布与环境输出

approved 对象先原子写入 canonical：

```text
quwoquan_data/publish/{creators,entities,posts,media,tags}/
```

canonical 只含最终业务对象，不得包含 raw source、草稿、prompt、日志、报告、SOP、
环境回执或运行状态。

静态 release 与环境证据分离：

```text
.qwq_output/data/releases/<releaseId>/
.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/
```

`ship apply|rollback` 只读 canonical 和 immutable release desired state。
导入回执、API 核验、回滚与重放证据写环境 run；禁止修改 canonical，
禁止 dual-read 或旧路径 fallback。

禁止暴露阶段角色命令、退役的双层运行身份或第二运行根。
