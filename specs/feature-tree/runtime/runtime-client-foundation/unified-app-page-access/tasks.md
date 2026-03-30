# unified-app-page-access 任务

## M1：/baseline（2026-03-30）

- [x] `spec.md` / `design.md` / `coverage-surfaces.md` / `acceptance.yaml` / `plan.yaml`
- [x] `app_routes.yaml` 登记 `welcome` + `make codegen-app` → `AppRoutePaths.welcome`
- [x] `CR-20260330-013-unified-app-page-access-baseline.yaml`
- [x] `tree_index.yaml` 注册 L3（`baseline_complete` + tag `P4`）
- [x] `page-horizontal-quality-spec.md` P4 交叉引用本 L3

## /dev（待执行）

- [ ] slice-2：`QuWoQuanAppRoot` + `app_router` redirect
- [ ] slice-3：`WelcomeScreen` 去手写埋点
- [ ] slice-4：`pageName` 全表
- [ ] slice-5：嵌套 push 审计（`coverage-surfaces.md` §3）
