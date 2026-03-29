# ios-native-page-enforcement 任务

## 当前交付

### M1：静态门禁脚本与 allowlist

- [x] 新增 `scripts/verify_ios_native_surface_gate.py`
- [x] 新增 `specs/gates/ios_native_surface_allowlist.yaml` 登记存量例外
- [x] 违规输出 path:line 与规则引用，失败 exit 1

### M2：gate 集成

- [x] `scripts/gate_repo.sh` 在 quwoquan_app 段调用 `verify_ios_native_surface_gate.py`

### M3：规范与页面根壳收敛

- [x] `specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md`、`07-ios-native-ux`、`.cursor/rules` 与 `page-layout-semantics` 对齐根壳策略说明
- [x] 批量将约定路径下的业务页根壳改为 `AppScaffold` / `CupertinoPageScaffold`（或经 allowlist 登记）

## 后续（技术债）

- [ ] 将 `ios_native_surface_allowlist.yaml` 收缩至零（逐页消减 Material 根 `Scaffold`）
