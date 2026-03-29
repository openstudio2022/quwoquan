# Design：iOS 原生页面壳 + 门禁

## 上游规格

- `spec.md`、`acceptance.yaml`、`specs/02_IOS_NATIVE_FRONTEND_UX_SPEC.md`

## 方案对比

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| A. 纯文档 + Code Review | 零成本 | 无法阻断 | 拒绝 |
| B. 正则门禁（v1） | 实现快、与现有 python gate 一致 | 存在误报/漏报边界 | **采纳为 v1** |
| C. Dart analyzer plugin | 精确 | 开发与维护成本高 | **未来 v2** |
| D. 仅 flutter analyze custom_lint | 中等精确 | 需引入依赖与规则包 | 备选 |

## 选型结论

采用 **方案 B**：`verify_ios_native_surface_gate.py` 扫描约定 glob，检测 **`return Scaffold(`**（Material 根壳典型写法）。与 `AppScaffold`（内部 `CupertinoPageScaffold`）不冲突。

### 扫描范围（v1）

1. `quwoquan_app/lib/ui/**/pages/**/*.dart`
2. `quwoquan_app/lib/components/**/*_page.dart`
3. `quwoquan_app/lib/components/media/camera/camera_capture_page.dart`（命名例外，显式列入 glob 列表于脚本内）

### 豁免机制

- 文件路径列入 `specs/gates/ios_native_surface_allowlist.yaml` 的 `allow_scaffold_return` 列表时，允许出现 `return Scaffold(`。
- **政策**：allowlist 只减不增；新增功能页 **不得** 申请长期豁免，须直接使用 iOS 壳。

### 与 AppScaffold 关系

- `AppScaffold` → `CupertinoPageScaffold` + 透明 `Material` 子节点：**允许**，不触发 `return Scaffold(` 检测。

## 观测与 SLO

- **门禁成功率**：`make gate` 在干净树 100% 通过。
- **误报**：若出现，在 `plan.yaml` 记 slice 调整正则或范围。

## 回滚

从 `gate_repo.sh` 移除对本脚本的调用（需 CR 与负责人记录）；不推荐静默删除规则。

## T1~T4 证据

见 `acceptance.yaml` 中 `evidence_matrix`。

## 与 metadata/codegen

本 L3 **不涉及** `contracts/metadata` 变更；无需 `make codegen`。
