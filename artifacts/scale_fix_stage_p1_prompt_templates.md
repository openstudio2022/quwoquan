# P1 阶段证据：提示词模板体系 + 全环节模板化 + 指令区精简

## 目标（对齐规划 P1/P1b）

把膨胀且未分区的 prompt 正文从 `.py` 字符串拼接迁出到受版本控制的 md 模板，按业界
（claude code / codex）系统提示词格式分区，删除「会话模型」措辞与 review gate 硬门复述
（gate 细则收回 review），补模板 lint + 渲染契约测试并接入 `verify_quwoquan_data.sh`。

## 根因回顾

- `writing_pack.render_prompt_md` 自 283 行起把 review gate 几十条硬门复述进指令区 140+ 行，
  303 行硬编码「必须由你——会话模型」。
- `homepage._render_entity_page_prompt` 同样在脚本里硬拼整段指令 + 章节均衡/时间线归并硬门。
- `draft_io` 整套契约文案仍是「会话模型」心智。

## 改动清单（仅 quwoquan_data/**）

### 新增提示词模板层 `quwoquan_data/prompts/`
- `README.md`：模板层契约（目录结构 / XML 标签分区 / `{{占位符}}` 与 `{{> partials/x.md}}` / lint 门禁）。
- `system/*.system.md`：四个环节族静态系统提示词，XML 分区
  `<role><capabilities><constraints>(always/never)<output_format>`，人设统一为「创作 agent」。
  - `article_author` / `entity_homepage` / `image_curation` / `review_repair`。
- `task/*.task.md`：四个环节族任务区模板（动态上下文 `<documents>` + `{{占位符}}`，静态在前动态在后）。
- `partials/`：可复用片段 `constraints_fidelity.md` / `output_format_{article,homepage,image}.md` /
  `figure_group_contract.md`（连续图 figure/figuregroup 占位「AI 原样带回」契约，供 P2 复用）。
- `vars/*.vars.yaml`：每族 system/task 区 required/optional 变量声明（渲染期校验真相源）。

### 渲染器 `_common/prompt_render.py`
- 加载模板 + 递归展开 partial（防自包含死循环）+ 按 vars schema 校验（必填存在 / 用到的变量必须声明 /
  渲染后无残留 `{{`）+ system/task 物理分隔组装。
- `PROMPTS_ROOT` 跟代码走（`_REPO_DATA_ROOT/prompts`，`QWQ_PROMPTS_ROOT` 仅供测试覆盖），不随
  运行时 `QWQ_DATA_ROOT` 漂移。
- 行数预算常量 `SYSTEM_LINE_BUDGET=80` / `TASK_LINE_BUDGET=120`，lint 与渲染契约共用。

### 三个渲染函数改为消费模板（指令区外置，脚本只构造动态数据块）
- `writing_pack.render_prompt_md` → `render("article_author", ...)`；
  `_render_image_task_prompt` → `render("image_curation", ...)`。
  - 删除「会话模型」措辞、「## 创作要求（必须由你——会话模型…）」标题、
    「### 体裁结构与 Review Gate 硬门槛」「## Review Gate 硬检查（reviewGateChecklist）」
    「## 产出方式」等 gate 硬门复述块（gate 细则收回 review）。
  - 保留创作方向数据块：creativeBrief / persona / writingIntent / 底稿编辑硬合同（去 gate 数值复述）/
    带单位数字白名单 / 章节意图 / 证据点 / 配图清单 + figure 占位契约。
- `homepage._render_entity_page_prompt` → `render("entity_homepage", ...)`；章节均衡/时间线归并硬要求
  收进系统 `<constraints>`，任务区只下发底稿来源/章节结构/底稿正文/同源配图清单等动态块。

### 心智清理
- `_common/draft_io.py` 与 `quwoquan_data/scripts/**` 全量「会话模型」→「创作 agent」（9 文件）。

### 门禁
- 新增 `verify/verify_prompt_templates.py`：四族模板三件齐备 + 必填变量可渲染 + 用到变量 ⊆ 声明 +
  必填变量必须真用 + system/task 行数预算 + ratchet（scripts 无「会话模型」、迁移函数必须经 render()）。
- 新增 `tests/local_contract/common/test_prompt_render__local_contract_test.py`：四族渲染、缺必填/未声明/
  残留占位符报错、partial 展开、fmt_bullets、article 任务区带回 figure/figuregroup 占位。
- 两者接入 `verify/verify_quwoquan_data.sh`（lint 紧随 `template lint`；渲染契约测试进 local_contract common 批）。

## 验证

```
python3 quwoquan_data/scripts/verify/verify_prompt_templates.py
  -> PASS verify_prompt_templates: 4 families, budgets + ratchets OK
pytest quwoquan_data/tests/local_contract/common/test_prompt_render__local_contract_test.py
  -> 10 passed
pytest produce/test_creative_autonomy_gate.py produce/test_route_brief_and_evidence.py \
       produce/test_entity_composer.py local_contract/task/test_managed_local_runtime ...
  -> 61 passed
python3 tests/build/test_build_homepage.py            -> 20 passed
python3 scripts/verify/verify_no_runtime_draft_kit.py -> PASSED
python3 tests/common/test_agent_executor_contract.py  -> 6 passed
pytest local_contract/produce/test_task_author_review -> 27 passed
```

prompt 行数：article author 由 ~170 行降为模板渲染（系统区静态可复用、任务区只承载动态数据）。

## 残留/说明（诚实记录）

- `task/run.py` 的 `produce_author` 调度 preamble（`_checkpoint_prompts`）仍内联一份 author_source_contract
  + gate 阈值复述，属 prompt.md 之外的「调度操作层」第二来源。它不在规划 P1b 明确点名的三个函数内，
  且其 local_contract 测试（`test_managed_local_runtime`）刻意断言这些字符串；本阶段未拆解以免越界破坏契约。
  → 已登记为 P1 残留项，建议后续单独收敛为「只指向 4.draft/prompt.md + 写回契约 + repair 自纠环」薄壳，
  同步更新对应契约测试。本阶段 prompt.md（模板单源）已不含 gate 复述。
