---
name: quwoquan-data-content
description: Produce truthful, richly-illustrated, narrative travel/route content via the qwq-data CLI (plan -> download -> produce -> media check-images -> verify). Use when the user asks about 内容生产、冷启动文章、游记/线路成稿、图片安全/水印/人脸、画报载体、selutel data pipeline, 数据工程出稿, or quwoquan_data content quality.
---
# quwoquan Data Content

本仓库的数据内容生产必须通过统一 CLI `qwq-data`（= `python3 quwoquan_data/scripts/cli.py`）。
脚本只做 IO 准备与校验，语义加工在 Agent 会话内完成；禁止为单个场景新写孤立可执行脚本。

## 唯一入口（CLI-first）

```
python3 quwoquan_data/scripts/cli.py <command> ...
```

| 命令 | 作用 |
|---|---|
| `plan` | 把内容指令解析为 compose_brief（含叙事契约/imagePlan/imagePolicy） |
| `download` | 多平台素材获取 + 来源质量评分 + 匿名化 |
| `produce --stage compose-brief` | 准备阶段：analyze 证据 → 选图 → 落「写作契约」`writing_pack.json` + `prompt.md` + 占位 `article.md`（**不拼正文**） |
| `produce --stage review` | 校验阶段：读会话模型写回的 `article.md` → 三道门 + 既有质量门 → 裁决 |
| `produce --stage review --materialize` | review 通过后将 approved 结果落地为 post package（含账本/实体 sidecar） |
| `media check-images` | 真实 CV 图片门：人脸/水印/OCR 文叠/感知去重 |
| `annotate` | Human-in-loop 标注：发布前对账本图片/事实/文章下人判定、打分、置发布态、记再加工 |
| `ship` | 一键发布：promote→重建索引→按环境确定性采样写 sample bundle→(可选)调用服务侧 importer 灌库 |
| `verify` | 收紧范围校验 post package（schema + 语义 + 图片 + 三道门） |
| `template lint` | 模板蓝图门禁（含 route 叙事契约 / gallery imagePolicy） |

## 正文创作只能由会话模型完成（禁止脚本拼正文）

`compose` 阶段已**彻底删除**所有脚本拼接正文（`_compose_*_article`/`_render_*`/`_pad_*`/`_fact_sentence`/`_emotion_sentence` 等不复存在）。
正文必须由**当前会话模型（Agent）**基于 `writing_pack.json` 与 `prompt.md` 语义创作，写回 `produce/drafts/{ref}.article.md`，并以 `generator=agent` 写 `draft_meta.json`。

### 草稿 IO 契约（`produce/<task>/<batch>/drafts/`）

| 文件 | 产出方 | 内容 |
|---|---|---|
| `{ref}.writing_pack.json` | CLI compose-brief | 证据点/图资源/mustIncludeFacts/叙事约束/分节意图/source 路径 |
| `{ref}.prompt.md` | CLI compose-brief | 给会话模型的人类可读写作指令 |
| `{ref}.article.md` | **会话模型** | 创作的正文（compose-brief 先写占位，待 Agent 覆盖） |
| `{ref}.draft_meta.json` | **会话模型** | `generator=agent` / `model` / `citedSourcePaths` / `coveredFacts` |

`generator` 仅 `agent` 能进入交付面；`template`（脚本拼接）与 `pending`（未创作）一律被门禁拒绝。

## 标准三段式（每个步骤强制）

`[CLI compose-brief：IO+选图+写作契约] → [Agent semantic：会话模型创作正文写回草稿] → [CLI review/materialize+gate]`

- CLI 负责 IO/拉取/落盘/打分/校验/落写作契约；语义创作只在会话模型内完成；
- 每个 stage 必落 stage result + gate report，失败写 repair report 并按 `fallbackStage` 回退重跑直至全绿（provenance/traceability/叙事问题回退到 `agent_compose` 重新创作）。

## 三道真实性门（review + verify 交付面强制）

1. **generator 出处门**：`draft_meta`/manifest 必须 `generator=agent` 且带 `model` 与 `citedSourceRefs`；非 agent 直接 `revision_needed`，`materialize` 拒绝落地。
2. **模板指纹门**：扫描旧脚本模板的强/弱指纹短语（`_common/template_fingerprints.py`），命中即判为机械拼接并阻断。
3. **事实可回溯门**：`mustIncludeFacts` 必须在正文出现；正文中带单位的关键数值（票价/海拔/时长等）必须能在 source 证据中回溯。

## Human-in-loop 标注 + 发布门（账本驱动）

review 阶段对每张图片/关键事实/文章产出 **agent 判定+打分**，写 `produce/review/ledger/{ref}.json`，
并把抽取的专有实体写 `produce/review/entities/{ref}.json`（无主页者自动生成关联实体主页 `page.md`）。
materialize 把账本与实体 sidecar 随 post 拷入 `posts/.../review/`。

发布态（`_common/review_ledger.py` 状态机，统一推导不持久化为事实）：
- 人裁定优先：`humanOverride=publishable/discard`，或 `humanJudgment=credible` / `humanScore>=3` → 可发布；`doubtful` → fix。
- 人未裁定看 agent：`agentJudgment=doubtful` 必须人确认（`requireHumanWhenDoubtful`）；`credible` 且 `agentScore>=3` → 可发布，否则 fix。
- 低质量（分低）可再加工，`reprocessCount` 累计，超 `maxAttempts(3)` 锁定，除非人裁定可发布。

含人脸/后端缺失的图片**不再硬阻断 review**，而是记账本存疑、转 annotate，由发布门兜底（`promote` 过滤）。

```bash
# 查看待人工处理队列（fix 态 / 需人确认）
python3 quwoquan_data/scripts/cli.py annotate --task <task> --batch <batch> --list
# 人判定 + 打分
python3 quwoquan_data/scripts/cli.py annotate --task <task> --batch <batch> --ref <ref> --kind image --target <assetId> --judgment credible --score 4
# 直接置发布态 / 记一次再加工
python3 quwoquan_data/scripts/cli.py annotate --task <task> --batch <batch> --ref <ref> --kind image --target <assetId> --override discard
python3 quwoquan_data/scripts/cli.py annotate --task <task> --batch <batch> --ref <ref> --kind article --target <ref> --reprocess
```

`promote_to_publish` / `ship` 的发布门据账本：文章须 publishable；discard 图从 manifest/articleAssetManifest/正文剔除；
无主页的 entityRef 过滤；任一处于 fix 则跳过该 post 并报告。

## 一键发布 + 按环境采样 + 服务侧灌库 importer

`publish/` 是单一发布主线（无版本目录，prod 全量）。`ship` 按 `deploy/shared/content_sampling_manifest.yaml`
对每个环境**确定性采样**（`rank=sha1(salt|ref)`，`<sampleRatio` 入选 + bucket cap + max），产出端云桥契约
`publish/sample_bundles/{env}.json`（选中的 postRef/entityRef）。

服务侧 importer 真正把 posts/entities 灌进运行库（mongo），消费 publish 主线 + sample bundle，幂等 upsert：

```bash
# 数据侧：发布 + 全环境采样
python3 quwoquan_data/scripts/cli.py ship --task <task> --batch <batch> --copy-entities
# 仅对现有主线重采样某环境
python3 quwoquan_data/scripts/cli.py ship --skip-promote --env gamma,beta
# 采样后直接灌库（调用服务侧 importer）
python3 quwoquan_data/scripts/cli.py ship --task <task> --batch <batch> --import --mongo-uri mongodb://localhost:27017

# 服务侧 importer（也可独立运行）：posts→content 库、entities→entity 库
cd quwoquan_service && go run ./services/content-service/cmd/import \
  --publish-root ../quwoquan_data/publish \
  --sample-bundle ../quwoquan_data/publish/sample_bundles/gamma.json \
  --mongo-uri mongodb://localhost:27017 --env gamma

# 真实 mongo 写入路径测试（起一次性 mongod，跑完销毁，不碰已有数据）
bash quwoquan_service/scripts/content/run_content_import_mongo_test.sh
```

## 关键命令示例

```bash
# 1) 准备写作契约（不产出正文）
python3 quwoquan_data/scripts/cli.py produce --task <task> --batch <batch> --content-type article --stage compose-brief

# 2) 会话模型按 produce/<task>/<batch>/drafts/<ref>.prompt.md + writing_pack.json 创作正文，
#    写回 drafts/<ref>.article.md 与 draft_meta.json(generator=agent)。此步在 Agent 会话内完成。

# 3) 校验三道门 + 既有质量门；通过则落地
python3 quwoquan_data/scripts/cli.py produce --task <task> --batch <batch> --content-type article --stage review --materialize

# 图片安全门（unsafe=水印/平台文字 即阻断；含人脸 -> 人工复核）
python3 quwoquan_data/scripts/cli.py media check-images --task <task> --batch <batch>

# 校验：批量审计只针对交付面 release/（current=当前 schema 门禁默认；all=全部 release）。
# runtime 中间批次不进批量审计（由 produce review 门禁产出时把关），需要时用 --task/--batch 显式校验。
python3 quwoquan_data/scripts/cli.py verify --scope current   # 门禁默认：当前 schema release
python3 quwoquan_data/scripts/cli.py verify --scope all       # 全部 release（含旧 schema）
python3 quwoquan_data/scripts/cli.py verify --task <task> --batch <batch>  # 显式校验某中间批次（仍严格）
python3 quwoquan_data/scripts/cli.py verify --release <release_id>
```

## 硬约束（违反即门禁拦截）

1. **正文只由会话模型创作**：禁止任何脚本拼接/模板填充正文。CLI 只产出写作契约与占位，正文必须由 Agent 写回 `drafts/{ref}.article.md`(`generator=agent`)。
2. **CLI 优先 + Skill 只暴露 CLI**：新能力一律实现为 `<command>/handler.py`(`register_parser`+`handle_*`) + 可选 `gate.py`，复用逻辑沉到 `_common/`。禁止新增 `scripts/**` 下可直接 `__main__` 运行的业务入口脚本（旧脚本只能留薄壳委托 CLI）。
3. **真相源**：路径/错误码/字段/叙事契约/imagePolicy 先改 metadata/blueprint/schema，再 `template lint` / 业务逻辑；codegen 与 schema 不手绕。
4. **三道真实性门**：generator 出处门 + 模板指纹门 + 事实可回溯门，review 与 verify 交付面强制；非 agent / 命中指纹 / 数值不可回溯一律阻断。
5. **图片治理**：发布图必须过 `media check-images`；unsafe→改稿，needs_review(人脸/后端缺失)→人工复核，近重复→去重。
6. **载体路由**：图多文少→gallery（配小字、禁大空白）；图带交叠文字→article（避免大空白）。
7. **游记感密度**：route 文章必须有出发动机、显式喜欢/不喜欢、取舍判断；注意事项就地融入，禁独立"实用信息/来源平台"清单块。
8. **Mock/来源隔离**：不泄露平台名/作者名/用户名/水印；来源痕迹必须改写。

## 门禁

- `bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh`（template lint 系列 + `verify --scope current`）。
- `python3 quwoquan_data/scripts/verify/verify_cli_first.py`（拦截新增直跑业务入口脚本）。
- 契约测试：`quwoquan_data/tests/test_image_safety_gate.py`、`test_route_assets_layout.py`、`test_gallery_carrier.py`、`test_travelogue_density.py`、`test_review_image_gate.py`、`test_route_brief_and_evidence.py`、`test_entity_composer.py`、`test_verify_pilot_gwt.py`、`test_article_markdown_contract.py`、`test_hitl_pipeline.py`（manifest 最小化+账本+实体主页）、`test_annotate_publish_filter.py`（标注 CLI+发布门）、`test_ship_sampling.py`（确定性采样+ship e2e）、`test_mixed_layout_gate.py`（图文混编门）、`test_review_ledger_state_machine.py`、`test_asset_id_stability.py`。
- 服务侧 importer 测试：`loader_test.go`（publish→doc 加载 + sample bundle 过滤）+ `mongo_import_test.go`（真实 mongo 写入：插入/字段/幂等重跑/唯一索引/load→upsert 子集，由 `quwoquan_service/scripts/content/run_content_import_mongo_test.sh` 起临时 mongod 跑）。
- 去版本化/去区域硬编码门禁：`python3 quwoquan_data/scripts/verify_no_legacy_hardcode.py`（禁止 `publish/v{N}` / `/v{N}/` objectKey / `chuanxi` 等回归）。
