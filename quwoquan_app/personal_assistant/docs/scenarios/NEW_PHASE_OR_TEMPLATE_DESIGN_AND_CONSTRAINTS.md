# 新增 Phase 或 Prompt 模板设计与约束

> **从属**：`../PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`

## 1. 适用场景

当新增 planner / synthesizer / web / dialogue 相关 phase，或新增模板、改模板合同、改模板注入顺序时，必须阅读本文。

## 2. 正确落点

主要变更应优先落在：

- `assets/personal_assistant/prompts/`
- prompt 标准合同与模板变量定义
- parser / serializer 的 typed contract

## 3. 设计约束

- 禁止在运行时代码中直接拼接提示词正文
- 禁止把某个 phase 的输出合同写死在 parser 外围逻辑中
- 指令与数据必须分离
- 若引入新 phase，必须定义输入、输出、缺失变量处理与回滚方案

## 4. 验收要点

- 模板文件、合同文件、运行时变量绑定一致
- 新 phase 有对应的解析与测试
- 不引入第二套 prompt 或 phase 真相源
