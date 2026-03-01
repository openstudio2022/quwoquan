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
| **L3** | 已部署 staging HTTP | pre-release-gate 的 deploy 完成后 |
| **L4** | 已部署 staging + 真机/FTL | pre-release-gate 的 deploy 完成后 |

L3、L4 必须等打包并部署到 integration 后才能跑，否则无法验证真实环境。

---

## 2. Workflow 命名规范（序号 + 首字母大写）

| 序号 | Workflow | 环境 | 说明 |
|------|----------|------|------|
| 01 | App Pipeline | Main Branch | 端侧 CI：Flutter analyze、macOS 构建 |
| 02 | Service Pipeline | Main Branch | 云侧 CI：Go build、Python 镜像、Kustomize prod 校验 |
| 03 | Delivery Gate | Main Branch | PR/入库质量门：拓扑 + L1 + L2 |
| 04 | Pre-Release Gate | Integration | v*-rc* → deploy → L3 → L4 |
| 05 | Deploy To Prod (Gray) | Production — Gray | 半自动 workflow_dispatch |
| 06 | Deploy To Prod (Auto) | Production — Full | 全自动 pre-release 通过后触发 |

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

### 4.1 delivery-gate — PR/入库阶段质量门（L1+L2）

- **触发**：PR、push → dev1.0/main
- **职责**：topology、metadata、L1、L2
- **Job 命名**：Delivery Gate — Topology / Service (L2) / App (L1)

**内部去重**：从 `scripts/gate_repo.sh` 的 run_service 中移除已在 topology 执行的 3 个脚本，避免重复。

### 4.2 app_pipeline — 只做打包，不做 L1

- **触发**：PR、push → main/master（paths: quwoquan_app/**）、tags v*
- **调整**：
  - **移除** `test` job 中的 `flutter test`（L1 由 gate 负责）
  - **保留** `flutter analyze`
  - **保留** `build-macos`（v* tag 时构建）
- **说明**：PR 时 gate 已跑 L1，app_pipeline 不再重复跑测试。

### 4.3 Service Pipeline (02) — 只做构建与部署校验，不做 L2

- **触发**：PR、push → main/master（paths: quwoquan_service/**, deploy/**）
- **调整**：
  - **移除** `build-go` 中的 `make test-unit`（L2 由 Delivery Gate 负责）
  - **保留** `make build`、Python 镜像构建、`validate-deploy`
- **说明**：PR 时 Delivery Gate 已跑 L2，Service Pipeline 只负责构建与 kustomize 校验。

### 4.6 02/03 重复检查（Service Pipeline vs Delivery Gate）

| 执行内容 | 02 Service Pipeline | 03 Delivery Gate | 是否重复 |
|----------|---------------------|------------------|----------|
| Go build | ✅ `make build` | ❌ | 否 |
| Go test (L2) | ❌ | ✅ `make gate` 含 go test | 否 |
| Kustomize build | ✅ aliyun-**prod** | ✅ aliyun/volcengine/huaweicloud-**integration** | **否**（目标不同：prod vs integration） |
| 拓扑 / metadata / 契约 | ❌ | ✅ gate_repo.sh | 否 |

**结论**：02 与 03 无重复执行。02 侧重构建与 prod 部署清单校验；03 侧重质量门（L1+L2、integration kustomize）。两者可并行触发（如 PR 变更 quwoquan_service 时），职责互补。

### 4.4 pre-release-gate — L3/L4 在 deploy 后执行

- **触发**：v*-rc* tag、workflow_dispatch
- **调整**：
  - **gate job**：改为 `make gate`（仅 L1+L2），不再运行 `make gate-full`（去掉 L3）
  - **deploy-integration**：保持，部署到 integration
  - **l3-api-contract**：保持，部署完成后跑 L3
  - **l4-android / l4-ios**：保持，部署完成后跑 L4
- **流程**：gate(L1+L2) → deploy → L3 → L4
- **说明**：L3、L4 必须依赖 deploy-integration 完成，否则无真实环境可测。

### 4.5 L3 — 已整合进 pre-release-gate

- **移除** `daily-api-contract.yml`
- L3 仅在 pre-release-gate 的 post-deploy 阶段执行

---

## 5. 整合后流程示意

```
PR / push
├── delivery-gate（PR/入库质量门）
│   ├── Delivery Gate — Topology
│   ├── Delivery Gate — Service (L2)
│   └── Delivery Gate — App (L1)
│
├── app_pipeline（仅当 paths 含 quwoquan_app）
│   ├── Flutter analyze（无 L1）
│   └── build-macos：v* tag 时
│
└── Service Pipeline（仅当 paths 含 quwoquan_service 或 deploy）
    ├── Go build（无 L2）
    ├── Python 镜像
    └── validate-deploy

v*-rc* tag
└── pre-release-gate
    ├── Pre-release Gate — L1+L2 (pre-deploy)
    ├── deploy-integration
    ├── Pre-release Gate — L3 (post-deploy)
    └── Pre-release Gate — L4 Android/iOS (FTL)
```

---

## 6. 实施清单

| 序号 | 文件 | 修改内容 | 状态 |
|------|------|----------|------|
| 1 | `gate.yml` → `delivery-gate.yml` | 重命名，job 标注阶段 | ✅ |
| 2 | `scripts/gate_repo.sh` | run_service 中移除 topology 脚本 | ✅ |
| 3 | `app_pipeline.yml` | 移除 `flutter test`，仅保留 `flutter analyze` | ✅ |
| 4 | `service_pipeline.yml` | 移除 `make test-unit` | ✅ |
| 5 | `pre-release-gate.yml` | gate-full → gate；job 命名标注 pre-deploy/post-deploy | ✅ |
| 6 | `daily-api-contract.yml` | 删除，L3 统一整合进 pre-release-gate | ✅ |
| 7 | `deploy/shared/ci_cd_end_to_end_design.md` | 更新 workflow 名称与说明 | ✅ |

---

## 7. 风险与回退

- **风险**：delivery-gate 未触发时，对应 pipeline 将不再跑 L1/L2。
- **缓解**：delivery-gate 无 paths 过滤，PR/push 都会跑；app_pipeline、Service Pipeline 有 paths 过滤，仅变更对应目录时运行，此时 delivery-gate 也会运行。
- **回退**：恢复被移除的 test-unit、flutter test 即可。
