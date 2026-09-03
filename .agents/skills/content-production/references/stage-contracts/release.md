# 阶段契约：release

immutable release 只能消费宿主 AI 显式 cohort；禁止隐式 `all-publishable` 或按目录全选。

## PRE

- `publish` CLOSE 为 pass。
- AI 在 OPEN 显式冻结 cohort 中每个 canonical object/pool record exact ref/digest、release class、release identity 与 taxonomy/content-library bindings。
- cohort 必须逐对象列出且非空；对象资格由既有 schema/硬事实 verifier 重验，不由 release builder 自动扩展。

## DURING

AI 调用现有 immutable release build 原子 IO，并把显式 cohort 作为输入。逐对象不合格时 AI 决定排除并重开本阶段的新 execution 尝试，或提交 blocked；不得让 builder 回退到所有可发布对象，也不得原地修改既有 release。

## POST

```bash
python3 quwoquan_data/scripts/cli.py verify release-integrity --release <releaseId>
```

AI 对账 release payload 与 OPEN cohort 完全一致，保存 releaseId/releaseDigest 与 verifier facts。

## HANDOFF

- `resultRefs`：immutable release exact refs/digests、显式 cohort binding。
- pass 后由 Skill 固定进入 `ship`。
