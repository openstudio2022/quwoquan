# 开发任务：future-evolution-closed-loop

## 统一门禁矩阵（草案）

| 阶段命令 | 必过项（最小集） | 不通过处理 |
|---|---|---|
| `/opsx-ff` | ① C11~C13 分解为独立 spec/design/tasks/acceptance；② 三类门禁脚本草案定义；③ CI job 草案定义 | 阻断 FF，先补规格 |
| `/opsx-apply` | ① 热更新白名单校验可执行；② 公共库接口契约校验可执行；③ 漂移规则校验可执行 | 阻断 apply，先补脚本 |
| `submit-with-gate` | ① config-evolution 回归 job 通过；② gate-full 聚合门禁通过；③ 漂移报告产物可追溯 | 禁止提交入库 |

## 当前交付任务（规划闭环）

### Wave 1 — C11 低风险热更新

- [ ] F1 定义低风险字段白名单来源与格式（metadata-first）
- [ ] F2 新增 `scripts/verify_config_hot_reload_scope.sh`（门禁草案实现）
- [ ] F3 增加热更新灰度回归样例（local/integration）

### Wave 2 — C12 runtime/config 公共库

- [ ] F4 定义 `runtime/config` 公共接口契约（Load/Validate/Compat）
- [ ] F5 新增 `scripts/verify_runtime_config_api_contract.sh`（接口兼容门禁）
- [ ] F6 为 content-service/recommendation-service 提供迁移适配层

### Wave 3 — C13 配置漂移检测

- [ ] F7 定义漂移规则模型（Git expected vs runtime snapshot）
- [ ] F8 新增 `scripts/verify_config_drift_rules.sh`（规则门禁）
- [ ] F9 输出漂移报告（`deploy/shared/evidence/config-drift/*.md`）

### Wave 4 — CI 与 gate-full 聚合

- [ ] F10 新增 `config-evolution-regression` workflow job
- [ ] F11 新增 `make gate-config-evolution` 聚合命令并接入 `make gate-full`
- [ ] F12 补齐 deliver 证据包（门禁日志、回归报告、漂移报告）

## 搁置任务（带规划）

- [ ] F13 配置中心实时推送联动（需上游平台能力稳定后启用）
  - 搁置原因：当前优先完成 Git 真源 + 规则校验闭环

## 未来演进任务

- [ ] F14 漂移检测接入告警分级与自动工单
- [ ] F15 热更新策略自动推荐（基于历史稳定性）
