# 新增 Skill 设计与约束

> **从属**：`../PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`

## 1. 适用场景

当新增某个 `domainId`、重构某个 skill 目录，或把 runtime 中的垂类逻辑下沉到 skill 资产时，必须阅读本文。

## 2. 正确落点

新增 skill 的主要变更应落在：

- `assets/assistant/skills/{domain}/SKILL.md`
- `references/`
- `dialogue/`
- `scripts/`
- `config/retrieval_policy.json`

运行时代码只应补充加载、注册和合同消费，不应承载领域规则正文。

## 3. 设计约束

- 禁止通过 `assistant_agent_loop` / `local_phase_execution_owner` / `react_runtime` 为某个 domain 写特判
- 禁止把 trigger keywords 当作主路由策略
- 禁止把示例回答或追问文案硬编码在 runtime
- 新增 skill 时应同步补充 domain 描述、状态机和检索策略

## 4. 验收要点

- skill 目录结构完整
- skill 可被加载与注册
- phase-aware 注入路径正确
- 没有把本应属于 skill 的逻辑留在 runtime
- 测试覆盖 manifest、loader、dialogue contract 和相关回归
