# quwoquan_data 提示词模板层（prompts/）

本目录是 producer 与模型交互提示词的版本化真相源。`scripts/core/prompt_render.py` 只负责加载、展开
partial、校验变量与渲染；不决定内容、不投影输出，也不承载 runner、resolver 或工作流状态。

## 现役模板族

- 四载体 author：`article_author`、`entity_homepage`、`image_curation`、`video_author`。
- 统一独立 reviewer：`content_independent_review`。
- source 阶段窄判断：`homepage_source_judge`；它不属于最终内容 review。

每个模板族只有同目录的 `system.md + task.md + vars.yaml` 三件套。废弃的 repair prompt 和按载体拆分的
最终 reviewer 不保留兼容入口。

## 最小输入契约

四个 author 每对象只接收：

- `target`；
- `retained_evidence_excerpts`；
- `selected_blueprint_intent`（一份 selected blueprint/结构叙事意图；image 仅含选图、排序、caption 意图）；
- `output_path`。

统一 reviewer 每对象只接收：

- `draft`；
- `claim_evidence_refs`；
- `assets_rights_packet`。

prompt 不接收全量 registry、template/style catalog、producer 阶段协议或尚未产生的发布态对象。
运行 actor、invocation 与摘要由 stage receipt 冻结，不抄写进业务产物。

## 证据与 rights 边界

`selected_blueprint_intent` 只提供结构意图，不能提供事实。`mustInclude` 仅在 retained evidence excerpts 有直接
证据时覆盖；票价、时间、价格、里程等没有直接证据时必须换角度或省略，不得补造。

面向读者的正文可去除平台噪声，但 source/rights evidence 中的 canonical credit/license/terms 必须保留在
rights packet，供统一 reviewer 逐资产判断。

## 单产物

- `4.draft` 每对象只写 `page.md`、`draft.article.md`、`image_work.json`、`video_script.json` 之一。
- `5.review` 每对象只写 `content_review.json`，最小顶层字段为 `decision`、`dimensions`、
  `blockingIssues`、`assetRights`。
- reviewer 只审不改，只读输入 refs，不运行命令。

## 渲染与 lint

模板使用 `{{var}}`，partial 使用 `{{> _shared/partials/x.md}}`。动态值中的双花括号由渲染器中性化；
模板本身出现未声明或未闭合占位符会失败。

```bash
python3 quwoquan_data/scripts/verify/verify_prompt_templates.py
python3 -m pytest quwoquan_data/tests/local_contract/core/test_prompt_render__behavior__functional__local_contract_test.py -q
```

门禁只检查模板三件套可渲染、无残留占位符、基本行数预算与既有脚本 ratchet；不执行内容工作流。
