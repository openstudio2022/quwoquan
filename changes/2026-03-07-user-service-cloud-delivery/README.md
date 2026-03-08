# 特性：<填写标题>

## 目标（User Value）
- [ ] <目标1>

## 范围（Bounded Context）
- **云侧服务/对象**：<content/chat/user/orchestrator/...>
- **端侧页面/对象**：<module.object.page/action>
- **接口**：<OpenAPI paths>
- **OpsX 变更**：<opsx-change-id>
- **OpsX 相关规格**：<opsx-spec-a, opsx-spec-b>

## 非目标（明确不做什么）
- [ ] <non-goal>

## 风险与回滚
- **风险**：<risk>
- **回滚**：<rollback plan>

## 里程碑（必须按顺序）
- [ ] 1) contracts-first：先改 `quwoquan_service/contracts/openapi/*.yaml` 与相关 contracts
- [ ] 2) specs：更新 `quwoquan_service/specs/*`
- [ ] 3) tasks：更新 `quwoquan_service/tasks.md`（引用 §0 全服务统一能力）+ 端侧任务
- [ ] 4) TDD：先写测试，再实现（单测/契约测/集成测）
- [ ] 5) gate：本地 `make gate` + CI required checks 全绿才允许合入

