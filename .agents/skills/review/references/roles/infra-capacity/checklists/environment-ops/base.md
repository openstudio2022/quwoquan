# infra-capacity · environment-ops

- [MUST] 放量前目标与回滚版本容量均满足峰值，并写明当前水位与增量依据。
  evidence: environment-release-evidence
- [MUST] 回滚不依赖已释放或已缩容资源。
  check: 读取 rollout/rollback 资源绑定；依赖不可用资源时判失败。
- [SHOULD] 环境变更的成本增量有可复核估算。
