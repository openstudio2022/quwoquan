# quwoquan_data 提示词模板层（prompts/）

本目录是**所有与模型交互环节**的提示词真相源。提示词正文从 `.py` 字符串拼接迁出到此处的 md
模板，`.py`（经 `core/prompt_render.py`）只负责「加载模板 + 计算动态数据块 + 校验占位符 + 组装」。
**禁止再在 `scripts/**` 里硬编码 prompt 正文**（模板 lint ratchet 拦截回归）。

## 目录结构

```
prompts/
├── README.md                 # 本文件：写作规范（标签清单 + always/never 范式）
├── homepage/                 # 实体主页提示词（静态、可复用）
│   ├── article_author.system.md
│   ├── entity_homepage.system.md
│   ├── image_curation.system.md
│   └── review_repair.system.md
├── article/ image/ video/    # 其他内容类型的提示词
├── _shared/partials/         # 复用片段（被内容类型模板经 include 引用）
│   ├── constraints_fidelity.md
│   ├── figure_group_contract.md
│   ├── output_format_article.md
│   ├── output_format_homepage.md
│   └── output_format_image.md
└── vars/                     # 每个模板族的占位符 schema（供渲染器校验 + lint）
    ├── article_author.vars.yaml
    ├── entity_homepage.vars.yaml
    ├── image_curation.vars.yaml
    └── review_repair.vars.yaml
```

## 宿主无关的格式骨架

每个环节一套 `system + task(+partials)`，统一经 `prompt_render.render(name, system_vars, task_vars)`
产出 `prompt.md`。**静态在前、动态在后**，中间有物理分隔（`---`）。

- **系统提示词（system，静态）** 用 XML 标签分区：
  - `<role>` — 人设与目标（一句话定位「创作 agent」，**不写「会话模型」**）。
  - `<capabilities>` — 可调用的工具 / 可做的事。
  - `<constraints>` — 约束，分 `<always>`（正向必须）与 `<never>`（负向禁止）；**只保留少量必要硬约束**，
    详细评审规则不在创作 prompt 复述；独立宿主 AI 按 `5.review` stage contract 显式评审并 close。
  - `<output_format>` — 产出格式（写回哪个文件、draft_meta 字段、figure 块写法）。
- **任务区（task，动态）** 承载 `<documents>`（底稿 / 素材 / 证据，`<source>` + `<document_content>`）
  与本次任务参数；few-shot 示例（如有）放任务区，不放系统区。

## 占位符规范

- `{{var}}`：变量替换；变量名必须在该模板族的 `vars/{name}.vars.yaml` 中声明（required 或 optional）。
- `{{> _shared/partials/x.md}}`：包含复用片段（递归展开，可含自己的 `{{var}}`）。
- 模板静态文本渲染后**不得残留** `{{` / `}}`（未闭合占位符 = 契约违例）；动态 source 文本中的同类分隔符由渲染器中性化后插入。
- **动态数据块**（素材列表 / 底稿正文 / 证据点等）由调用方在 `.py` 中构造为 markdown 字符串，
  以 `{{xxx_block}}` 形式传入；模板只承载结构骨架与静态指令，数据不写死进模板。

## always / never 约束范式

```
<constraints>
  <always>
    - 以下方底稿为骨架忠实轻改，保留原叙述顺序与关键事实细节。
  </always>
  <never>
    - 禁止编造票价/海拔/里程等带单位数字（拿不准写区间或定性）。
    - 禁止伪装真人亲历（我亲自/亲眼看到/我去了…）。
  </never>
</constraints>
```

## 门禁

- `python3 quwoquan_data/scripts/cli.py template lint`：占位符闭合 / vars 必填齐备 /
  系统/任务行数预算 / `scripts/**` 不得硬编码 prompt 正文（ratchet）。
- 渲染契约测试 `tests/local_contract/common/test_prompt_render__local_contract_test.py`：
  fixtures 渲染产物含正确分区与已填变量、缺必填变量报错；已接入 `qwq-data verify all`。
