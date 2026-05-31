# data-template-author

用途：作为专业编辑维护 `quwoquan_data/templates/` 模板库。只创建或审校模板、作者画像和路由，不生成用户正文。

## 输入

- 新模板需求：主体、意图、载体、读者、风格画像、创作者画像。
- 可选：参考模板 ID。

## 流程

1. 先运行：

```bash
python3 quwoquan_data/scripts/cli.py template coverage --vertical travel
python3 quwoquan_data/scripts/cli.py template coverage --vertical campus
```

2. 若新增模板，优先用 scaffold：

```bash
python3 quwoquan_data/scripts/cli.py template new --from 景区_攻略 --to 新模板ID
```

3. 编辑 `quwoquan_data/templates/blueprints/**/*.tmpl.yaml`，必须包含：
   - `subject`
   - `intent`
   - `carrier`
   - `styleFamily`
   - `creatorPersona`
   - `render`
   - `imagePlan`
   - `recommendation`

4. 新增作者画像时编辑 `quwoquan_data/templates/creator_profiles/system_builtin/*.creator.yaml`，必须使用系统可消费的 `authorId/subAccountId`。

5. 准出门禁：

```bash
python3 quwoquan_data/scripts/cli.py template lint
python3 quwoquan_data/scripts/cli.py template creator-lint
python3 quwoquan_data/scripts/cli.py template rec-contract
```

## 禁止

- 禁止在模板中写用户正文。
- 禁止在正文模板里出现 `isSystemBuiltin`、`qualityScore`、`routingReason`、`coldStartBoost`。
- 禁止使用不存在的 `tagRef` 或硬编码未登记作者。
