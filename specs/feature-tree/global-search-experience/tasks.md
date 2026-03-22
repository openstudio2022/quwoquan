# global-search-experience 任务列表

> 任务顺序：metadata → codegen → 业务逻辑 → 测试 → gate → 交付
> 状态标记：[x] 已完成 / [ ] 待完成

## 当前交付任务

- [x] T1: 新建独立 `global-search-experience` L1，并完成历史 chat 搜索节点治理退出与索引对齐 → C1
- [x] T2: 冻结 `_shared`、`content`、`user`、`messages`、`circle`、`assistant` 的搜索 metadata 拓扑与职责边界 → C1 C2
- [x] T3: 冻结全局搜索的商用基线、生命周期、弱网降级、一把上线与整版回滚口径 → C2 C3
- [x] T4: 补齐 `README.md`、`tasks.md`、`acceptance.yaml` 交付状态与证据，保证能力节点可通过仓库级 gate → C1 C2 C3

## 搁置任务（带规划）

- [ ] P1: 搜索召回/排序专项优化，触发条件为站内搜索精度或吞吐成为主瓶颈
- [ ] P2: 密信账号隔离下的搜索权限细分，触发条件为私密账号与子账号策略冻结

## 未来演进任务

- [ ] F1: 全局搜索线上观测看板与告警闭环
- [ ] F2: 推荐词、热搜词与个性化召回策略
