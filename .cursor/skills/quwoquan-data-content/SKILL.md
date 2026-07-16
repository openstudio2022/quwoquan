---
name: quwoquan-data-content
description: Run the canonical quwoquan data content workflow from reusable inputs through one execution work package, immutable release, environment import, and App UAT.
---
# quwoquan Data Content

数据内容生产只有一个入口：

```bash
python3 quwoquan_data/scripts/cli.py <command> ...
```

脚本负责 IO、契约、下载、校验、发布与证据；正文语义创作只由 Agent 完成。禁止新增直跑业务脚本、静态任务实例、分片运行根或第二套发布流程。

## 三段职责

### 1. 可复用工程输入

只允许进入版本库：

```text
quwoquan_data/control_plane/families/content/<vertical>/<contentType>/
quwoquan_data/verticals/
quwoquan_data/reference/
quwoquan_data/prompts/
quwoquan_data/templates/
quwoquan_data/schema/
```

- family recipe 只声明可复用规模、runtime 和质量参数，不包含省份、日期、实体、executionId 或输出路径。
- 省市范围、discovery、limit、milestone 和 executionId 只通过 CLI 参数进入执行。
- 实体类型只读 taxonomy/schema；内容结构和语言规则只读 template/prompt。
- 默认凭证源是仓外且权限为 `0600` 的 `~/.config/quwoquan/cursor_api_key`；
  `QWQ_CURSOR_API_KEY_FILE` 只允许受控测试或显式替换该位置。任何输出不得包含
  key、片段或指纹。

### 2. 单任务 execution 工作包

每次内容任务只写：

```text
.qwq_output/data/tasks/<executionId>/
  execution_manifest.json
  0.plan/
  sources/
  entities/**/1.content.source..5.review/
  posts/<kind>/**/1.content.source..5.review/
  _shared/
  evidence/
  publish_ref.json
```

`executionId` 必须符合：

```text
YYYYMMDD--<vertical>-<contentType>-<intent>--<scope>--<canary|m1|m2|m3>-<sequence>
```

同一 ID 只允许 resume。新尝试递增 sequence，并在根 manifest 中声明 `retryOf`。不允许 taskId、batchId、planId、workerId 或其它平行身份。

标准阶段为：

```text
0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review
```

阶段 packet 只携带 `executionId` 关联根 manifest；recipe、参数、源码、prompt 和来源 revision 不在每个对象重复写入。

正文和实体主页只能由 Agent 基于 source、writing pack 与 prompt 创作。脚本不得生成、拼接或填充正文。图片、事实、权利、creator、tag、实体与 review 决策必须可回溯。

## 3. 发布与环境输出

approved 对象先原子写入 canonical：

```text
quwoquan_data/publish/{creators,entities,posts,media,tags}/
```

canonical 只含最终业务对象，不得包含 raw source、草稿、prompt、日志、报告、SOP、环境回执或运行状态。

静态 release 与环境证据分离：

```text
.qwq_output/data/releases/<releaseId>/
.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/
```

`ship apply|rollback` 只读 canonical 和 immutable release desired state。导入回执、API 核验、回滚与重放证据写环境 run；禁止修改 canonical，禁止 dual-read 或旧路径 fallback。

## 唯一任务门面

```bash
python3 quwoquan_data/scripts/cli.py task geo-homepages --execution-id <id> ...
```

`geo-homepages` 是唯一任务门面，聚合 target selection、执行、readiness、publish 与 ship，不建立独立 schema、runner 或输出根。

## 浙江四川准出

顺序固定：浙江金丝雀、四川金丝雀、M1、M2、M3 两省全覆盖。任何前序未绿不得启动后序。

每个金丝雀必须完成：真实百科 source v2、逐图权利、Agent 主页、review、canonical 原子发布、Gamma 幂等导入、服务 API 核验、动态 App UAT、回滚与重放。

最终执行：

```bash
python3 quwoquan_data/scripts/cli.py task preflight --json
python3 quwoquan_data/scripts/cli.py verify content-execution-layout
python3 quwoquan_data/scripts/cli.py verify publish-purity
python3 quwoquan_data/scripts/cli.py verify two-province-coverage-release --release <releaseId>
python3 quwoquan_data/scripts/cli.py verify all
python3 quwoquan_ops/cli/stackctl.py verify --env gamma --kind all --tier all
```

凭证、来源、权利、Gamma、API 或 App 任一真实证据缺失，必须返回带 executionId 的 `GATE_BLOCK`，不得用 fixture、skip、历史数据或估算报告替代。
