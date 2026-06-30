# P2 阶段证据：内容载体重构（HTML 图文混排 + 连续图合并占位 figuregroup）

> 规划真相源：`提示词重构与三类解耦放量_2f1c2e11`（P2 = id `p2-html-mixed-layout`）。
> 根因：R-CS10「图文混排丢失」——抽取器对相邻连续图每张独立产 `:::figure`（连续 6 张拆 6 个），
> 正文图文交错被打散、AI 易丢图；标题层级丢失退化为纯文本。

## 一、改了什么（精确数据管线路径）

### 新增唯一真相源
- `quwoquan_data/scripts/_common/figure_groups.py`（新）：连续图组占位（figuregroup）契约与回填逻辑的**唯一真相源**：
  - `FIGURE_GROUP_RE` / `iter_figure_groups` / `figure_group_ids`：解析正文中的 `:::figuregroup` 块；
  - `build_figure_group_block` / `build_single_figure_block`：构造占位；
  - `expand_figure_groups`：**回填**——把每个 figuregroup 展开为 N 个连续 `:::figure` 单图块（下游统一消费单图形态，零改造）；
  - `figure_group_integrity_issues`：**带回完整性**——底稿组被丢弃/拆成单图/改 assetId 时报问题；
  - `prune_unbound_group_images`：**绑定后清理**——剔除组内未同源下载的 `source-inline` 占位 + 重算 count + 删空组；
  - `figure_image_count`：组内逐张 + 单图统一计数。

### 抽取器（保结构 + 合并占位）
- `quwoquan_data/scripts/download/fetch.py` `_InlineFigureHTMLTextExtractor`：
  - **标题保结构**：`h1`–`h6` → markdown `#`–`######` 级标题（`_HEADING_TAGS`），保留段落/标题/图文交错顺序；
  - **连续图合并**：相邻连续 `<img>`（仅被空白/块边界分隔）缓冲为 `_pending_images`，遇真实正文文字/标题/文末即 flush——单图→`:::figure`、≥2 张→**单个 `:::figuregroup count=N`**（内部 N 张同序 assetId）；
  - 一旦出现真实文字立即 flush，绝不跨正文段落误并；内联清单（占位↔src）仍与每张图一一对应、同序。

### 回填契约落地（AI 原样带回 → CLI 展开同源连续图）
- `quwoquan_data/scripts/_common/source_unit.py` `bind_inline_source_placeholders`：绑定真实 assetId 后调用 `prune_unbound_group_images` 清理组内未绑定图行。
- `quwoquan_data/scripts/produce/materialize.py` `_resolve_materialized_article`：发布物化处 `expand_figure_groups` 把组占位回填为 N 个同源单图块（`figure_groups_expanded` 动作）。
- `quwoquan_data/scripts/build/homepage.py` `materialize_entity_page`：实体主页先判 figuregroup 带回完整性，再 `expand_figure_groups` 回填。

### 门禁/计量对齐 figuregroup
- `quwoquan_data/scripts/_common/content_evidence.py` `clean_source_markdown`：新增 `_is_structural_figure_line` 守卫——`:::figure/:::figuregroup` 起止围栏与 `![..](asset://..)` 图片引用**保结构原样保留**，修复「无字母收尾 `:::` 被当噪声删」导致 `source.clean.md`（AI 优先消费的底稿）图文块被打散的问题。
- `quwoquan_data/scripts/_common/base_draft.py` `compute_base_draft_readiness`：先 `expand_figure_groups` 再计图片张数/图注/正文字数（图主导底稿 readiness 不被合并占位低估）。
- `quwoquan_data/scripts/produce/route_review.py`：
  - 新增 **`figureGroupIntegrity`** 硬门（对原始 body 判，底稿与 fidelity 同源）；
  - `_check_mixed_layout` 先展开组再判穿插/空档；`_opening_paragraph` 剥图正则扩为 `:::figure(?:group)?`。
- 同步把 `:::figure\b` 剥图正则扩为 `:::figure(?:group)?\b`：`materialize._strip_text_only_asset_markup`、`homepage._homepage_gate_body`。

### 测试（抽取器 / 回填契约）
- `quwoquan_data/tests/local_contract/download/test_inline_source_images__local_contract_test.py`：新增
  `test_inline_extractor_merges_consecutive_images_into_figuregroup`（连续 3 图→单组 count=3；文字隔断的单图保单图块；H2/H3 标题保结构；内联清单同序覆盖全部 4 张）。
- `quwoquan_data/tests/local_contract/common/test_figure_group_backfill__local_contract_test.py`（新）：expand 回填 / 带回完整性（正确带回不误报、丢图/拆图/改 id 报问题）/ prune 剔除未绑定与删空组 / 计数 / `clean_source_markdown` 保结构。
- 接入 `quwoquan_data/scripts/verify/verify_quwoquan_data.sh`。

## 二、回填契约（占位符 AI 原样带回 → CLI 回填）

```
page.html (图文混排真相源)
  → 抽取器：保段落/标题/图文交错 + 相邻连续图合并为单个 :::figuregroup(N) 占位
  → source.md / source.clean.md（净化不打散围栏） → 底稿 → 创作 agent
  → agent 原样带回 :::figuregroup 占位（figureGroupIntegrity 硬门校验带回）
  → CLI 在发布/主页物化处 expand_figure_groups：占位内部回填 N 张同源连续单图块
```

## 三、验证证据（local_contract，本机 venv）

```
python3 quwoquan_data/tests/local_contract/download/test_inline_source_images__local_contract_test.py
  → inline source image tests passed (5)   # 含 figuregroup 合并 + 标题保结构
python3 quwoquan_data/tests/local_contract/common/test_figure_group_backfill__local_contract_test.py
  → figure group backfill tests passed (7)
python3 quwoquan_data/scripts/verify/verify_prompt_templates.py
  → PASS verify_prompt_templates: 4 families, budgets + ratchets OK
.venv/bin/python -m pytest 质量门/底稿保真/字数自适应 → 41 passed
逐文件（模拟门禁隔离）：test_route_brief_and_evidence(13) / test_entity_composer(7) /
  test_review_image_gate(11) / test_route_assets_layout(5) 全绿
```

实导出抽取器样例（3 连续图 + 文字隔断单图 + H2/H3）：
```
## 第一站 五花海
清晨抵达五花海，湖水斑斓。
:::figuregroup id="grp-001" count="3"
![source image](asset://source-inline-001)
![source image](asset://source-inline-002)
![source image](asset://source-inline-003)
:::
随后前往五彩池。
:::figure
![source image](asset://source-inline-004)
source image
:::
### 交通贴士
建议自驾。
```

## 四、说明 / 剩余风险

- 已知**他流漂移、非本任务**：`tests/local_contract/build/test_entity_object_stages__local_contract_test.py`
  依赖 `build.homepage.finalize_entity_objects`，该符号在 HEAD 即不存在（`git show HEAD:...|grep -c=0`），
  且不在 `verify_quwoquan_data.sh` 套件内；不在本任务作用域，未碰。
- 上述 produce 测试在**同一 pytest 会话内**连跑会因既有跨测试运行时根状态污染出现 3 例 order-dependent 失败，
  逐文件隔离（与门禁实际执行方式一致，各 `python3 <file>` 独立进程）全绿；非本次 figuregroup 改动引入。
- 真实端到端「连续图占位被 composer 带回」的产物级证据归 P7 四川放量批次落账（本阶段为 contract/抽取器/回填层证据）。
