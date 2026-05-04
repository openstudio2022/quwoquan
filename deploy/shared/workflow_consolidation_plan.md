# Workflow 整合方案

> 原则：gate 按阶段命名；L1+L2 在 delivery-gate 完成；L3/L4 必须等待打包部署完成后执行（pre-release-gate 的 post-deploy 阶段）。
>
> **特性树**：`specs/feature-tree/runtime/deliver-deploy-prod-pipeline/workflow-naming-consolidation/`

---

## 1. 分层与职责

| 层级 | 依赖 | 执行时机 |
|------|------|----------|
| **L1** | 无（Mock） | delivery-gate 阶段 |
| **L2** | MongoDB、Redis（testcontainers） | delivery-gate 阶段 |
| **L3** | 已部署 gamma HTTP | pre-release-gate 的 deploy 完成后 |
| **L4** | 已部署 staging + 真机/FTL | pre-release-gate 的 deploy 完成后 |

L3、L4 必须等打包并部署到 integration 后才能跑，否则无法验证真实环境。

---

## 2. Workflow 命名规范（序号 + 首字母大写）

| 序号 | Workflow | 环境 | 说明 |
|------|----------|------|------|
| 01 | App Pipeline | Release / Manual | 端侧发布构建：v* tag / 手动 macOS 构建 |
| 02 | Service Pipeline | Main Branch | main 后云侧构建：Go build、Python 镜像、Kustomize prod 校验 |
| 03 | Delivery Gate | PR Rule | PR 主门禁：拓扑 + L1 + L2 |
| 04 | Pre-Release Gate | Integration / PR Rule | deploy integration → L3 → L4 → gamma smoke |
| 05 | App Env Device Matrix | PR Rule / Self-hosted | self-hosted 动态设备矩阵唯一入口 |
| 06 | Deploy To Prod (Gray) | Production — Gray | 半自动 workflow_dispatch |
| 07 | Deploy To Prod (Auto) | Production — Full | main 后自动推进 |
| 08 | Deploy Gamma ECS | Gamma / Onebox | 手动发布与复验链路 |

---

## 3. L3 整合

**L3 统一整合进 pre-release-gate，不单独保留 daily workflow。**

| 阶段 | L3 | 说明 |
|------|-----|------|
| **delivery-gate** | ❌ | PR 代码未部署，无法验证 |
| **pre-release-gate**（post-deploy） | ✅ | deploy 完成后，L3 验证新部署的 API 契约 |

L3 仅在 **Pre-release Gate — L3 (post-deploy)** job 中执行，依赖 deploy-integration 完成。

---

## 4. 整合方案

### 4.1 delivery-gate — PR 主门禁（L1+L2）

- **触发**：`pull_request(main)`、`workflow_dispatch`
- **职责**：topology、metadata、L1、L2
- **Job 命名**：Delivery Gate — Topology / Service (L2) / App (L1)

**内部去重**：从 `scripts/gate_repo.sh` 的 run_service 中移除已在 topology 执行的 3 个脚本，避免重复。

### 4.2 app_pipeline — 只做端侧发布构建

- **触发**：`push.tags = v*`、`workflow_dispatch`
- **调整**：
  - **移除** L1/L2 相关重复校验
  - **保留** `build-macos`（v* tag 时构建）
- **说明**：PR required checks 已由 `03` 兜底，01 不再参与主干阻断。

### 4.3 Service Pipeline (02) — 只做 main 后构建与部署校验，不做 L2

- **触发**：`push.main`（paths: `quwoquan_service/**`, `deploy/**`）与 `workflow_dispatch`
- **调整**：
  - **移除**重复的服务级 test job（L2 由 Delivery Gate 负责）
  - **保留** `make build`、Python 镜像构建、`validate-deploy`
- **说明**：02 只负责 post-main 构建与 prod 部署清单校验。

### 4.6 02/03 重复检查（Service Pipeline vs Delivery Gate）

| 执行内容 | 02 Service Pipeline | 03 Delivery Gate | 是否重复 |
|----------|---------------------|------------------|----------|
| Go build | ✅ `make build` | ❌ | 否 |
| Go test (L2) | ❌ | ✅ `make gate` 含 go test | 否 |
| Kustomize build | ✅ aliyun-**prod** | ✅ aliyun/volcengine/huaweicloud-**integration** | **否**（目标不同：prod vs integration） |
| 拓扑 / metadata / 契约 | ❌ | ✅ gate_repo.sh | 否 |

**结论**：02 与 03 无重复执行。02 侧重构建与 prod 部署清单校验；03 侧重质量门（L1+L2、integration kustomize）。两者可并行触发（如 PR 变更 quwoquan_service 时），职责互补。

### 4.4 pre-release-gate — PR 发布验证

- **触发**：`pull_request(main)`、`workflow_dispatch`
- **调整**：
  - **deploy-integration**：保持，部署到 integration
  - **l3-api-contract**：保持，部署完成后跑 L3
  - **l4-mobile-self-hosted**：保持，部署完成后跑 L4
  - **assistant-runtime-gamma**：保持，部署完成后跑 gamma smoke
- **流程**：deploy → L3 → L4 → gamma smoke
- **说明**：`03` 已承担 L1/L2，因此 04 不再重复 gate。

### 4.5 L3 — 已整合进 pre-release-gate

- **移除** `daily-api-contract.yml`
- L3 仅在 pre-release-gate 的 post-deploy 阶段执行

---

## 5. 整合后流程示意

```
pull request -> main
├── delivery-gate（主门禁）
│   ├── Delivery Gate — Topology
│   ├── Delivery Gate — Service (L2)
│   └── Delivery Gate — App (L1)
│
├── app-env-device-matrix（self-hosted）
│   ├── discover_devices
│   ├── android
│   └── ios
│
└── pre-release-gate
    ├── deploy-integration
    ├── Pre-release Gate — L3 (post-deploy)
    ├── Pre-release Gate — L4 mobile (self-hosted)
    └── Assistant runtime smoke (gamma)

push main
├── Service Pipeline
└── Deploy To Prod (Auto)

tag / manual
└── App Pipeline
```

---

## 6. 实施清单

| 序号 | 文件 | 修改内容 | 状态 |
|------|------|----------|------|
| 1 | `gate.yml` → `delivery-gate.yml` | 重命名，job 标注阶段 | ✅ |
| 2 | `scripts/gate_repo.sh` | run_service 中移除 topology 脚本 | ✅ |
| 3 | `app_pipeline.yml` | 收缩为 tag / manual 的端侧发布构建 | ✅ |
| 4 | `service_pipeline.yml` | 移除重复服务 test job，仅保留 main 后构建 / 校验 | ✅ |
| 5 | `pre-release-gate.yml` | 改为 `pull_request(main)`；移除重复 gate；保留 deploy/L3/L4/gamma smoke | ✅ |
| 6 | `app-env-device-matrix-self-hosted.yml` | 升级为唯一 05 设备矩阵入口；支持 `pull_request(main)` / workflow_call / 手动 | ✅ |
| 7 | `deploy/shared/ci_cd_end_to_end_design.md` | 更新 workflow 名称、触发与主干门禁说明 | ✅ |
| 8 | `merge-dev1.0-to-main.yml` | 删除；以显式 PR + required checks 取代 | ✅ |

---

## 7. 风险与回退

- **风险**：`main` 分支 required checks 配置不完整，会出现代码进入 `main` 前未真正经过 `03/04/05`。
- **缓解**：在 `main` 分支保护中显式配置 required checks，并通过一次 `dev1.0 -> main` 验收 PR 验证。
- **回退**：可临时重新为 03/04/05 增加 `workflow_dispatch` 手动补跑，但不建议恢复旧的定时合流模型。
