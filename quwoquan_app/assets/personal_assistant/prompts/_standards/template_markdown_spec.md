# Template Markdown Spec 2.0

## 1. Mandatory Sections

Every template must include these sections in order:

1. `## 任务背景`
2. `## 任务目标`
3. `## 约束`
4. `## 执行要求`
5. `## 任务规划` (for plan/requery) or `## 前置检查` (for answer)
6. `## 输出格式`
7. `## 反思与自检`
8. `=== CONTEXT_DATA_START ===`
9. data payload placeholders only
10. `=== CONTEXT_DATA_END ===`

## 2. Data and Instruction Boundary

- Instruction and constraints must appear before data section.
- Raw context data is only allowed in data section.
- Data section must not include new instructions.

## 3. Slot-driven Prompting

Templates must consume context via slots:

- `contextSlots`
- `fillActions`
- `missingCriticalSlots`

When slot status is `need_query`, templates must output executable tasks instead of final answer.

## 4. Output Contract Discipline

Template output must be JSON only. No prose wrapper.

Required answer fields:

- `result`
- `evidence`
- `reasoningBasis`
- `selfCheck`
- `diagnostics`

