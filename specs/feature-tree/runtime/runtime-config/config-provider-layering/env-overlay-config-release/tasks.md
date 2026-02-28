# 开发任务：env-overlay-config-release

## 当前交付任务（与 deliver 对齐）

### Wave 1 — 运行时核心实现

- [x] E1 实现配置路径解析（default + APP_ENV）
- [x] E2 实现深度覆盖与字段冲突规则
- [x] E3 实现环境变量覆盖（最高优先级）
- [x] E4 增加 `APP_ENV` 合法性校验与 fail-fast
- [x] E5 增加 `CONFIG_VERSION` / `IMAGE_VERSION` 兼容校验
- [x] E6 增加启动 preflight（Redis 连通性与关键字段校验）

### Wave 2 — 自动化验证

- [x] E7 完成单元测试：覆盖顺序、非法环境、版本兼容
- [x] E8 完成集成测试：local/integration/prod 三环境加载
- [x] E9 完成容器场景验证：`CONFIG_ROOT=/etc/qwq-config` 外部挂载加载

### Wave 3 — 门禁接入（去重后由本节点主实现）

- [x] E9.1 新服务创建流程接入自动配置脚本
  - 在 S04（new-service）执行链中调用 `bootstrap_service_config_layout.sh`
  - 验证新服务首次创建即满足配置目录门禁
- [x] E10 实现门禁脚本并接入 CI：
  - `verify_service_config_layout.sh`
  - `verify_service_env_contract.sh`
  - `verify_config_release_version_mapping.sh`
  - `verify_config_image_compat.sh`
- [x] E11 将门禁接入 `make gate` / `make gate-full`
- [x] E12 产出 deliver 证据包（test/gate 输出、示例配置、运行截图）
  - `deploy/service/config-release/reports/2026-02-27-config-release-drill.md`

## 搁置任务（带规划）

- [ ] E13 低风险配置热刷新（watch + atomic swap）
  - 搁置原因：优先保证灰度发布与回滚闭环

## 未来演进任务

- [ ] E14 接入配置中心推送（依旧保留 Git 版本控制）
- [ ] E15 提供 `/config/effective` 只读诊断端点（脱敏）
