# L3 子特性：dart-semantic-gate

## 功能说明

端侧 Dart 编码规范的**自动化守门**，在 Plan→Create→Implement→Verify→Submit 全链路拦截：
- 硬编码视觉字面量（width/height/leadingSize、fontSize、EdgeInsets、Color 等）
- iOS 语义风格违规（行尾箭头语义、Cupertino 页面混用 Material 交互、selector leading 语义）

确保设计系统 token（AppSpacing、AppTypography、AppColors）与 iOS 全局语义被持续执行。

| L4 子节点 | 职责 |
|-----------|------|
| `verify-script-and-gate-integration` | 新建 verify_dart_semantic.py + 纳入 gate_repo.sh |
| `rules-and-flow-enhancement` | 02-dart-coding、06 规则、00_MASTER_DEVELOPMENT_FLOW 补充触控/布局禁止示例与约束 |
| `ff-deliver-semantic-checklist` | design/tasks 模板增加编码规范小节；opsx-apply 对 Dart 变更自动跑语义检查 |
| `design-token-metadata-registry` | 设计 token 注册表（contracts/metadata）→ codegen/lint 联动（未来演进） |

## 范围

- **必检**：width、height、leadingSize、fontSize、size、EdgeInsets、BorderRadius、Color(0x)
- **必检（iOS 语义）**：`Icons.chevron_right`、`CupertinoPageScaffold` 中 `Checkbox`/`SnackBar`/`ScaffoldMessenger`、selector 页面 `CupertinoIcons.back`
- **白名单**：lib/core/design_system/、lib/core/constants/、*_test.dart fixture
- **不负责**：云侧 Go 代码、非 Dart 文件

## 适用范围与约束

- **适用**：quwoquan_app/lib/**/*.dart
- **约束**：gate 必须调用 verify_dart_semantic，失败即阻塞
- **不适用**：设计系统定义文件、测试 fixture

## 与父/子节点关系

- 父节点：runtime-client-foundation L2
- 子节点：4 个 L4（见上表）

## 验收标准概要

- A1：verify_dart_semantic.py 存在且能检出 width: 44 等硬编码
- A2：gate_repo.sh run_app 中调用该脚本
- A3：02-dart-coding 含 width/height/leadingSize 禁止示例
- A4：FF 模板含编码规范小节；opsx-apply 对 Dart 变更执行语义检查
