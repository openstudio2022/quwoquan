# 分支策略

> 与 `deliver_to_production_runbook.md`、`ci_cd_end_to_end_design.md` 对齐。日节奏发布策略见 `specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/`。

---

## 1. 策略概要

| 分支 | 用途 | 合入方式 |
|------|------|----------|
| **dev1.0** | 日常开发合入 | PR 合并；delivery-gate（L1+L2）通过 |
| **main** | 发布主干 | **仅由定时 merge 更新**（merge-dev1.0-to-main workflow） |

- **日常 PR**：目标分支为 **dev1.0**，禁止直接合并到 main
- **main 更新**：每日定时（如 6:00 Asia/Shanghai）由 `07. Merge dev1.0 To Main` workflow 自动 merge dev1.0 → main；**merge  job 仅在** `dev1.0` 当前 HEAD 对应的 **Delivery Gate**（`delivery-gate.yml`）已成功时执行（见 `scripts/ci_assert_delivery_gate_green_for_branch.py`）
- **本地 push 后等待变绿**：`bash scripts/gh_wait_delivery_gate_green.sh dev1.0 3600`（与 `/.cursor/commands/commit.md` 一致）

---

## 1.1 本地开发约定

- **日常开发**：请在 **dev1.0** 分支进行，提交并推送到 `origin/dev1.0`。
- **main**：仅作为发布版本分支，不直接提交；由定期/定时将 dev1.0 合入 main 更新。
- 合入前请确保在 dev1.0 上已通过 delivery-gate（L1+L2）。

---

## 2. 日节奏流程

```
日常开发
  → PR 合并到 dev1.0（delivery-gate L1+L2 通过）
  → 每日 6:00（scheduled）merge dev1.0 → main
  → push to main 触发 pre-release-gate（gate → deploy integration → L3 → L4）
  → pre-release 通过 → deploy-prod-auto Stage 1 自动灰度
```

---

## 3. GitHub 分支保护建议

| 分支 | 建议配置 |
|------|----------|
| **main** | 禁止 direct push；需 PR 合并；或配置为仅允许来自 merge workflow 的 push |
| **dev1.0** | PR 需 delivery-gate 通过；可允许 maintainer direct push |

---

## 4. 参考

- `deploy/shared/deliver_to_production_runbook.md` — 端到端 runbook
- `deploy/shared/ci_cd_end_to_end_design.md` — CI/CD 闭环
- `.github/workflows/merge-dev1.0-to-main.yml` — 定时 merge workflow
