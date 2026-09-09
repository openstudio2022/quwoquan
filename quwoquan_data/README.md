# quwoquan_data

`quwoquan_data` 负责趣我圈内容生产的可复用输入、不可变 execution 工作包、canonical 内容对象与 immutable producer release handoff。内容生产的唯一流程真相源见 [content-production Skill](../.agents/skills/content-production/SKILL.md)；本 README 只给出工程边界和最短操作入口，不复制步骤细则。

## Skill + AI Agent

宿主 Cursor/Codex IDE/CLI Agent 是唯一内容语义主体：点名来源与实体相关性、创作、独立评审，并明确 approved 对象、cohort 与 milestone。Skill 的 [producer.py](../.agents/skills/content-production/scripts/producer.py) 提供 `source/download/preview/build-inputs/lint` 单阶段工具：来源取得与预览/下载可按宿主显式输入出网，本地构造与 lint 不出网；工具不创作、不判分、不推进或恢复，也不包装 seal/publish。未实现来源由宿主通用工具处理，实际入口只在各载体 `sources.md` 小节声明。

producer 固定为六步 `init → acquire → author → review → publish → release`，`release finalize` 成功即 `END`。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion、rollback/replay 全部 out of scope；下游 owner 是 Environment Ops scheduler，Data 不创建环境 acceptance。

Data CLI 拥有 identity-only init、零网络 ingest、schema/digest/ref/media 校验、create-once seal、单对象 publish 与 explicit cohort release。一个 execution 一个真实 author，reviewer 独立；它只写现有 execution 级 `seal.review.json`，CLI 扇出逐对象 `content_review.json`。派发/预算/身份与失败恢复只读 Skill 的 [dispatch](../.agents/skills/content-production/references/dispatch.md)、[session](../.agents/skills/content-production/references/session.md)，不另建 actor authority、runner 或完成台账。

## 工作包与只读恢复

准备工作区位于 `.qwq_output/data/local/workspace/content-production/<shardId>/rounds/<roundId>/`：round 根保留 `round.json/pool.before.json/pool.after.json/report.md`，每个 `<carrier>/` 放本轮候选、选择、ingest/seal 输入、sources、downloads 与 preview；shard 根只放范围/预算与按需 frontier，不作完成台账。CLI execution 物理根保持不变：

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

恢复与部分产物归属按 [session](../.agents/skills/content-production/references/session.md#失败与续跑)；以池和 receipts 为事实，不把聊天摘要、shard 或 workspace 临时 claim 当 producer 进度。init 不要求下载前置，宿主可直接写现有 round spec；build-inputs 只是构造同一输入的可选机械入口。

```bash
python3 quwoquan_data/scripts/cli.py task init --help
python3 quwoquan_data/scripts/cli.py task acquire --help
python3 quwoquan_data/scripts/cli.py task seal --help
```

## 取得、发布与 release

`task acquire` 只消费本地 `ingest.json` 与实际字节，计算摘要/探测/预算派生并登记来源、权利与媒体 holder；`quwoquan_data/scripts/content/source/**`、`content/execution/**` 与 `core/**` 不访问来源网络。Skill 工具不是 Data CLI 的新来源网络入口，也不复制其 probe/derive/CAS/seal。来源访问与权利按 [sourcing](../.agents/skills/content-production/references/sourcing.md) 记录，未授权/版权保留/未知权利不因类别而阻断，缺事实不能补造许可或作者。

`4.draft` 每对象只保留一份 carrier 主产物，`5.review` 每对象只保留 CLI 扇出的 `content_review.json`；质量评分只记录。单对象 publish 与 explicit cohort finalize 继续由 Data CLI 唯一写 canonical 包及 handoff，输入、命令与准出细则只在 [pipeline](../.agents/skills/content-production/references/pipeline.md)，不在 README 复制载体模板或第二流程。

## 独立内容仓与持久性

以下是已冻结的目标契约，不是迁移完成声明；实现、最小回归与精确授权切换分别由 [发布仓 OPEN-027](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-027)、[对象包 OPEN-025](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#open-025) 和 [身份切换 OPEN-001](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/canonical-content-identity-recovery/spec.md#open-001) 承接。现有 production/cutover 成果、媒体保护副本及历史 release/receipt 原件全部保留。

- canonical 内容仓为 `/Users/zhaoyuxi/Projects/quwoquan/publish`，与 `data-engineering/` 等源码工作树平级，是独立 Git 仓而不是源码 worktree、submodule 或 symlink。`QWQ_PUBLISH_ROOT` 绑定仓身份；根缺失/不符就阻断，不回退仓内旧树。源码保留 schema/Skill/CLI/tests，执行包的原物理布局不变。
- `repository.json` 只绑定仓身份、布局版本与工程契约摘要，不保存绝对路径、active release、统计或 token。对象 inventory 只遍历声明对象根，不把 `.git`、仓元数据或 releases 计作对象；共享写锁定位于共同内容根，不随各源码 output root 漂移。

```text
publish/                                      # 独立内容仓，实际初始化/搬迁须另授权
  repository.json
  entities/<domain>/<真实行政链>/<type>/p0001/<name>/<seq>/
  entities/<非地域domain>/<已有主类型路径>/p0001/<name>/<seq>/
  posts/<article|image|video>/<angle>/p0001/<name>/<seq>/
    manifest.json                             # 实体事实也在同一 manifest
    page.md | article.md                      # 仅 homepage/article 的最终正文
    content_review.json                       # 原审核结论及原对象摘要
    records/<序号>.json                        # 追加式入池/退役事实
    media/<实际交付文件>                       # final image/video/poster/真实字幕
    sources/s001/{source.json,evidence.<实际扩展名>}
  creators/<creatorProfileId>/                 # 独立 profile、avatar 与来源
  tags/<现有标签路径>/_definition.json
  releases/<releaseId>/{cohort.json,producer_release_handoff.json}
```

- 地域来自已核实的主行政区标签，默认国家/省/市/区县，但只证实到市/省、直辖市、省直管县与境外均保留真实链，不补“未知区县”。跨区域只有一个主落点、其余归属仍可查询。地域适用性显式，非地点仅预留结构，不新增 producer；posts 不复制地域树。
- 分区始终从 `p0001` 开始，空类不建空目录。容量只看条目数与随体逻辑字节；同名组不拆不搬，新组选容得下的最低归一化负载分区、平分按编号，无合适分区才开新分区，超大组仅报告例外。阈值由 Data policy 单点拥有，不按日期/轮次分批、不自动均衡。
- 名称统一规范化并拒绝碰撞/路径穿越；实体同名范围为同领域/主行政归属/主类型，posts 为同载体/主分类。稳定 ID/ref 不从路径重算，条目 `seq` 是不复用的正整数且允许空洞，不是内容版本。同物新版本仍沿用身份，唯一对象里程碑不重复累计版本。
- `manifest.json` 是身份/版本/实体事实/正文引用/有序媒体/业务依赖单源；采用来源的事实与必要原件随体，不保留重复 refs/source catalog/rights 旁车或生成式授权证明。review 原件与 records 各自保留，迁移只追加原件 binding/新版本事实，不伪造重新审核。生成公共 attribution 由 importer 从唯一 source/manifest 投影。
- content library（默认 `~/.local/share/quwoquan/content_library`，`QWQ_LIBRARY_ROOT`）只负责采集复用；完整作品和 release 物化不要求原库在场，不跨包 symlink。final media 按 manifest 的相对 path/sha256/bytes/mime 对账，纯搬家不转码、不伪造字幕。来源站失效不影响本地成品。
- golden media（默认 `~/.local/share/quwoquan/golden_media`，`QWQ_CARRIED_MEDIA_ROOT`）独立保护副本继续保留，不准 gc/hygiene 触碰既有保护根及任何保留作品/release 引用摘要。普通 Git 不跟踪媒体，忽略规则/硬链接不算备份，同卷完整拷贝不证明抗盘损坏；无异卷/远端恢复证据时明确该层耐久性未建立，见 [耐久性 OPEN-002](../specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md#open-002)。
- verify/消费只读，不隐式下载、回填 library 或修复对象；媒体根不可达、单文件缺失、摘要损坏与来源证据缺失分开报告。恢复须显式操作并验证独立副本的 exact bytes，来源 URL 不保证重建转码字节。旧 `verify all` 的隐式回填尚未退役前不能当作纯只读入口，本说明不宣称相关实现已完成。
- finalize 只保存既有 cohort/handoff 两份 terminal 事实，绑定工程 baseline/实际契约摘要与内容仓身份、所选 ID/版本/包摘要/定位清单的 exact 快照；只有匹配实际字节才记内容 commit，不新增两次提交门槛。历史 `reference/releases`、bundle、review 与 receipts 保留原字节；可重建范围必须有固定时间/cohort/exact build 输入和测试支持，不能承诺重建 AI 判断或外部网页。
- 实际搬迁、旧树删除、init/clone、commit/push、备份外写与环境激活各须精确授权；一个 lane 的配置不证明全局已切换。在飞工作区不自动清理，删除运行证据会失去该次执行审计。

```bash
python3 quwoquan_data/scripts/cli.py release publish-object --help
python3 quwoquan_data/scripts/cli.py release finalize --help
python3 quwoquan_data/scripts/cli.py release handoff-verify --help
```

M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 累计，每级形成自己的 full explicit cohort/release/handoff；凡已完成 canonical publish 且 review approved 的对象都可复用进入 cohort。handoff 以 canonical publish proof 为凭，记录 `producerBaselineRevision` 与 `producerContractDigest`，不含 UAT/import/readback/EAF/promotion/rollback。任何外部 consumer 只可只读上述 immutable producer facts。

## 可复用输入与输出边界

受版本控制的可复用输入只位于 `control_plane/`、`verticals/`、`reference/`、`prompts/`、`templates/` 与 `schema/`；不得写入任务地区、数量、日期、execution identity 或运行输出。旧 `reference/releases/<releaseId>/` 是需保护的 terminal 原件，不是可复用输入。独立内容仓只保存 approved canonical objects 与必要引用闭包：最终媒体、采用来源的必要真实证据、review 原件和追加式入池/退役 records 必须保留；未经采用的大下载、草稿、prompt、日志与 execution receipts 不默认进入发布包。禁止 raw 中间产物不等于禁止 sources 证据。

`.qwq_output/data/` 一级只允许：

```text
tasks/       不可变 producer execution 工作包与 create-once receipts
releases/    环境无关 immutable release 与 handoff 事实
local/       cache/ runs/ workspace/；生产输入放 workspace/content-production/<shard>/rounds/<round>/
```

删除 `.qwq_output/` 不得损失依赖声明、recipe、prompt、template、schema、policy 或部署规则。组合验证入口仍为下列命令；目标契约要求纯只读，隐式恢复退役及新随体回归通过前不要把旧实现当作纯检查运行。显式恢复命令由现有 CLI 的实际帮助与 schema 确认，不在文档虚构新入口：

```bash
python3 quwoquan_data/scripts/cli.py verify all
```
