# L2 特性：deliver-deploy-prod-pipeline

## 功能说明

从特性到入库（L1/L2 自测通过），再到 `main` 前 ECS gamma 主门禁验证，再到生产端到端打通的**平台交付流水线**。当前主门禁模型是：

- `03. Delivery Gate` 负责 L1/L2。
- `05. App Env Device Matrix` 负责本地 self-hosted alpha/beta Android/iOS 设备矩阵。
- `04. Pre-Release Gate` 负责 ECS gamma hosted pre 链 + 本地 self-hosted gamma Android/iOS assistant/avatar 旅程。
- `02/07` 负责 main 后构建与发布后续动作。

## 范围

- **deliver 入库**：验收驱动开发 → G3 gate-full → 归档 → G4 提交合入（L1/L2 通过）
- **ECS gamma 主门禁**：G5a 通过 hosted ECS pre 链部署 gamma onebox / pre，并执行 hosted gamma 探测
- **本地 self-hosted 设备验证**：G5b 在当前开发 Mac 上执行 alpha/beta/gamma Android+iOS 设备矩阵，并生成可审计证据
- **灰度到 prod**：G5c 按 config-release 规范灰度步进 5→25→50→100，SLO 卡点
- **local-gamma left shift**：作为提交前本地预测试，复用 gamma 语义与旅程注册表，但不再作为 merge gate

## 适用范围与约束

- **适用**：`main` PR 阻断、ECS gamma pre 验证、prod 灰度发布与回滚
- **当前范围**：`04` 的主部署目标为 ECS gamma / onebox；`08` 为手动 wrapper；prod 仍按现有发布链路推进
- **不适用**：任何绕过 PR required checks 直接进入 `main` 的路径
- **约束**：
  - `03/04/05` 必须保持稳定 required check 名称。
  - `04/05` 都要求 Android 与 iOS 两个平台存在且全部通过。
  - 设备矩阵 artifact 必须包含设备清单、原始日志、命令清单与截图证据。
  - `deploy/shared/gamma_validation_suites.json` 是 gamma 核心旅程的单源。

## 与父/子节点关系

**父节点**：runtime（L1 能力域）

| 子节点 | 职责 | 优先级 |
|--------|------|--------|
| **integration-deploy-and-l3-l4-gate** | 已演进为 ECS gamma 主门禁与本地 self-hosted gamma 旅程 | **优先（前置）** |
| **multi-cloud-deploy-overlay** | prod 侧部署覆盖层与切换 | **优先** |
| **gray-release-to-prod** | G5c 灰度步进 + SLO 卡点 + 回滚 | **优先** |
| **local-gamma-mirror** | 提交前左移预测试，复用 gamma 语义与旅程 | **并行配套** |
| **multi-environment-instance-isolation** | 端侧多模拟器实例与 beta/gamma 单套服务生命周期 | **并行配套** |

## 验收标准概要

- A1：PR 到 `main` 时触发 `03/04/05`，并以 ECS gamma + 本地 Android/iOS 设备验证阻断合入
- A2：`04` 的 hosted ECS gamma pre 链失败即阻塞发布
- A3：`04/05` 的 self-hosted Android/iOS 设备矩阵失败即阻塞发布
- A4：gamma assistant/avatar 基线旅程以 `deploy/shared/gamma_validation_suites.json` 为单源，并预留后续业务对象扩展入口
- A5：灰度步进 5→25→50→100 可执行
- A6：每步 SLO 卡点可执行；异常可一键回滚
- A7：`deliver_to_production_runbook.md` 完整可执行
- A8：`process_domain_mapping` 校验继续在 gate 中
