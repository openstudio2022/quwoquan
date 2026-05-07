# L3 特性：multi-environment-instance-isolation

## 功能说明

在不新增第六环境、不改动现有 `APP_RUNTIME_ENV` 枚举的前提下，收敛 alpha / beta / gamma 的多实例运行规则：

- 端侧 App 允许在**不同模拟器**并行运行多个实例。
- beta 云侧本地集成栈始终只允许**一套**，启动新实例前必须先停止旧实例再重启。
- gamma 继续保持 ECS / local-gamma mirror 的**单套**服务语义；并行只体现在多个端侧实例可同时访问同一套 gamma。

## 范围

- 端侧多实例启动入口、实例记录、stop/list 诊断能力。
- beta 单套服务生命周期：启动前 stop 旧栈、回收固定端口、清理失效 pid。
- gamma 单套部署/本地 mirror 切换语义：清理已有实例后重启，不扩展为多套并行。
- 环境矩阵、业务数据清单、runbook 与报告字段的单套/多实例口径。
- `T1 -> T4` 中与端侧多模拟器并行、beta/gamma 单套切换相关的验证路径。

## Out of Scope

- 不新增 `APP_ENV` / `APP_RUNTIME_ENV` 枚举。
- 不新增 `app_local_gamma_seed_manifest.json` 或其他新环境 seed manifest。
- 不支持“同一模拟器同时安装多个环境包”；当前交付只覆盖**不同模拟器**并行。
- 不规划 beta 多套并行或 gamma 多套 ECS 并行部署。
- 不改动业务 Repository、metadata、codegen 或 UI IA。

## 适用范围与约束

- 适用：本地 alpha / beta / gamma 手工调试、`local-gamma mirror` 左移验证、beta 手工联调、gamma 端侧接入与部署 runbook。
- 约束：
  - 端侧每次启动必须显式绑定 `device-id` 或等价唯一设备选择结果。
  - beta 固定端口组 `18080 / 18087 / 18088` 在任意时刻只归属于一套 beta 栈。
  - gamma 入口始终只指向一套 ECS gamma 或一套 local-gamma mirror。
  - 端侧实例记录只用于诊断与 stop/list，不得演化为服务端多套编排。

## 与父/子节点关系

**父节点**：deliver-deploy-prod-pipeline（L2）

| 关联节点 | 说明 |
|----------|------|
| `local-gamma-mirror` | 复用 gamma 语义做本地左移，但本特性要求其保持单套切换语义 |
| `multi-environment-wave-deployment` | 复用五环境统一语义，不新增新环境枚举 |
| `gray-release-to-prod` | gamma/prod-gray/prod 的发布口径不因端侧多实例而改变 |

## 支持矩阵

| 维度 | alpha | beta | gamma |
|------|-------|------|-------|
| 端侧不同模拟器并行 | 支持 | 支持 | 支持 |
| 端侧同一模拟器多包安装 | 不在本次范围 | 不在本次范围 | 不在本次范围 |
| 云侧多套并行 | 不作为本次目标 | 禁止 | 禁止 |
| 启动新实例前 stop 旧栈 | 仅在涉及本地服务时适用 | 必须 | 必须（部署 / mirror 切换） |

## 验收标准概要

- A1：存在可检索的规格、设计、验收与计划四件套，明确端侧多实例与 beta/gamma 单套边界。
- A2：环境矩阵、业务数据清单与 runbook 明确“端侧可多实例、beta/gamma 服务端单套”的统一口径。
- A3：端侧启动入口支持按 `env + device-id` 启动、停止、列举实例，并记录诊断信息。
- A4：beta 启动链路在启动新栈前会停止旧栈、回收固定端口并清理残留子进程。
- A5：gamma 部署 / local-gamma mirror 切换遵循单套清理后重启语义，不出现第二套并行栈。
- A6：至少一条 `T4` 验证覆盖 alpha / beta / gamma 三个端侧实例分别运行在不同模拟器。
