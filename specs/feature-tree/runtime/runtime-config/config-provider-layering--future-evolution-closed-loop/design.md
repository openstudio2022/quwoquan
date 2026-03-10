# Design: future-evolution-closed-loop

## 设计动因

`config-provider-layering` 已完成当前交付闭环，但 C11~C13 属于跨阶段演进事项，若继续停留在父节点任务列表中，容易缺少独立验收与门禁，导致长期“计划化未落地”。

因此将其收敛到独立 L4 节点，形成可迭代闭环。

## 设计决策

1. **C11（低风险热更新）采用“白名单 + 双阶段验证”**
   - 白名单字段由 metadata 显式声明
   - 配置变更先静态校验，再灰度生效
   - 高风险字段（连接拓扑、鉴权）保持“仅灰度发布，不热更新”

2. **C12（runtime/config 公共库）采用“适配层迁移”**
   - 先抽象 `Load/Validate/Compat` 三类接口
   - 服务侧保留兼容适配器，逐服务切换
   - 门禁对比“迁移前后同输入同输出”

3. **C13（漂移检测）采用“声明式规则 + 只读审计”**
   - 规则源自 Git 期望态与运行时快照
   - 检测输出为 report，不直接改写运行态
   - 漂移分级：info/warn/fail

## 门禁草案（详细）

- **verify 层（开发态）**
  - `scripts/verify_config_hot_reload_scope.sh`
    - 校验热更新字段必须在低风险白名单
  - `scripts/verify_runtime_config_api_contract.sh`
    - 校验公共库接口签名与向后兼容约束
  - `scripts/verify_config_drift_rules.sh`
    - 校验漂移规则完整性与阈值格式

- **CI 层（回归态）**
  - workflow job: `config-evolution-regression`
  - 执行：
    - local/integration/prod 加载一致性回归
    - 热更新灰度场景回归（低风险字段）
    - 漂移检测样例回归（期望/实际差异）

- **gate-full 层（发布前）**
  - 新增聚合入口（草案）：
    - `make gate-config-evolution`
    - 并入 `make gate-full`（pre-release 阻断）

## 适用场景与约束

适用：
- 多服务复用同一配置加载能力
- 配置变更频繁、要求可追溯与可回滚

约束：
- 不支持高风险字段热更新
- 不在本节点处理配置中心接入细节（由上游平台节点承接）

## 未来演进

- E1：完成 C11 白名单热更新 MVP（单服务）
- E2：完成 C12 公共库抽象并迁移 content/recommendation
- E3：完成 C13 漂移检测规则与 CI 阻断策略
