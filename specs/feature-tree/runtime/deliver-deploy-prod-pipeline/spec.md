# L2 特性：deliver-deploy-prod-pipeline

## 功能说明

从特性到入库（L1/L2 自测通过），再到集成验证（L3/L4），再到生产端到端打通的**平台交付流水线**。支持多云部署（阿里云、火山引擎、华为云）灵活切换，实现 deliver → deploy 到 integration → L3/L4 验证 → 灰度到 prod 的完整闭环。

## 范围

- **deliver 入库**：验收驱动开发 → G3 gate-full → 归档 → G4 提交合入（L1/L2 通过）
- **deploy integration**：G5a 将构建物部署到 integration 环境
- **L3/L4 集成验证**：G5b 在 integration 上执行 L3 API Contract 与 L4 Patrol 测试，阻塞发布
- **灰度到 prod**：G5c 按 config-release 规范灰度步进 5→25→50→100，SLO 卡点
- **多云支持**：部署到阿里云 ACK、火山引擎 VKE、华为云 CCE，通过环境变量或配置切换，Kustomize/Manifest 与云厂商解耦

## 适用范围与约束

- **适用**：integration/prod 环境部署；pre-release 流水线；灰度发布与回滚
- **当前范围**：优先阿里云 ACK；火山引擎 VKE、华为云 CCE 通过 overlay 或 cloud-provider 目录支持
- **不适用**：dev 本地开发（仍为独立服务启动）；单云绑定、无法切换的硬编码部署
- **约束**：`process_domain_mapping.yaml` 与云厂商无关；K8s 标准 API；灰度步进与 SLO 与云厂商无关

## 与父/子节点关系

**父节点**：runtime（L1 能力域）

| 子节点 | 职责 | 优先级 |
|--------|------|--------|
| **integration-deploy-and-l3-l4-gate** | G5a 部署 integration + G5b L3/L4 集成验证；pre-release workflow 串联 | **优先（前置）** |
| **multi-cloud-deploy-overlay** | 多云（阿里云/火山引擎/华为云）Kustomize overlay 与切换 | **优先** |
| **gray-release-to-prod** | G5c 灰度步进 + SLO 卡点 + 回滚 | **优先** |

## 验收标准概要

- A1：pre-release tag 触发 gate-full + L3 + L4 串联
- A2：L3 对 integration 执行，失败阻塞发布
- A3：L4 Patrol/FTL 在 pre-release 执行，失败阻塞发布
- A4：支持通过配置/环境变量切换部署到阿里云、火山引擎、华为云
- A5：灰度步进 5→25→50→100 可执行
- A6：每步 SLO 卡点可执行；异常可一键回滚
- A7：deliver_to_production_runbook 完整可执行
- A8：process_domain_mapping 校验在 gate 中
