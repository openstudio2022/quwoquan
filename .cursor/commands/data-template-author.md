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

   **目录与标签系统同构（`template lint` 阻断）**：蓝图文件路径由内容确定性推导，不得另起一套目录。
   - entity 蓝图：`blueprints/Entity/{subject.type}/{角度}.tmpl.yaml`（如 `Entity/地点/景区/攻略.tmpl.yaml`，与 `publish/tags/Entity/{domain}/{type}` 同构，角度=`templateId` 下划线后段）。
   - topic 蓝图：`blueprints/Format/内容角度/{subject.type 末段}/{角度}.tmpl.yaml`（如 `Format/内容角度/线路/环线攻略.tmpl.yaml`，与 `publish/tags/Format/内容角度` 同构）。

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

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-template-author` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
