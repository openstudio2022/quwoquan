# infra-capacity · design

- [MUST] 容量、并发、持久性与成本假设有当前证据和量化边界。
  check: 读取目标 DEC/SLI；任一假设无当前测量来源或只有定性描述时判失败。
- [MUST] 故障恢复与回滚资源在目标环境可用。
  check: 读取回滚拓扑；依赖已释放资源或无容量余量时判失败。
- [MUST NOT] 引用历史容量快照或角色文档作为现状事实。
  check: 逐条核对证据时间与来源；非本次运行或 canonical context 时判失败。
