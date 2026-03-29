# Tasks: search-execution-routing-policy

## 当前交付任务

- [x] T1: 冻结 `local_only / remote_only / hybrid_remote_fallback_local` execution mode 与 typed degrade signal → A1
- [x] T2: 让统一搜索 facade 依据 objectType 和 execution mode 路由 provider → A1
- [ ] T3: 扩展更多 provider 失败场景的 degrade signal 与观测埋点 → A1

## 未来演进任务

- [ ] F1: 在保持 query-first 简洁接口的前提下补充更多 planner hint
