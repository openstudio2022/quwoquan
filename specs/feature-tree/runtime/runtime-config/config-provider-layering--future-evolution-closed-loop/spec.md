# L4 细节：future-evolution-closed-loop

## 功能定位

为 `config-provider-layering` 的后续演进项（C11~C13）建立独立闭环包，统一承接：
- 低风险配置热更新（C11）
- `runtime/config` 公共库抽象复用（C12）
- 配置漂移检测（Git 期望 vs 运行时实际，C13）

目标是将“规划项”转为可执行交付线，避免长期搁置。

## 范围

本节点负责：
- 演进目标、边界与分阶段任务定义
- 门禁草案（本地 verify、CI、发布前 gate-full）
- 验收口径（A1/A3/A4/A7/A8）

本节点不负责：
- 一次性完成所有实现代码
- 替代现有 `config-provider-layering` 主节点的既有门禁

## 核心约束

- 热更新仅适用于低风险配置字段，禁止覆盖高风险连接/鉴权类字段
- 公共库抽象必须保持现有服务启动语义兼容
- 漂移检测只读，不允许直接修改运行中实例配置
- 任何演进项必须保持 `default -> env -> version -> env vars` 基线不变

## 门禁草案（概要）

- G1（本地）：
  - `scripts/verify_config_hot_reload_scope.sh`（低风险白名单）
  - `scripts/verify_runtime_config_api_contract.sh`（公共库接口契约）
  - `scripts/verify_config_drift_rules.sh`（漂移规则有效性）
- G2（CI）：
  - 增加 `config-evolution-regression` workflow 任务
  - 执行 split local/integration/prod 配置加载回归 + 漂移模拟
- G3（发布前）：
  - `make gate-full` 追加演进门禁聚合 target（草案）

## 验收概要

- A1：C11~C13 均有明确实施路径与边界
- A3：演进门禁在 verify/CI/gate-full 三层可执行
- A4：热更新与漂移检测具备审计可观测输出
- A7：演进不破坏现有配置契约与目录标准
- A8：关键场景具备自动化测试与回归入口
