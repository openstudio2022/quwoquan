# dart-semantic-gate 设计

## 设计动因

硬编码视觉字面量（如 width: 44、leadingSize: 44）在 FF/deliver/gate 全链路未被拦截，根因：
1. verify_dart_semantic 被引用但脚本不存在
2. gate 未调用
3. 规则中 inline 检查范围与模式不全

## 方案

采用四层策略：L1 脚本→L2 规则→L3 FF 前置→L4 元数据（未来）。

### L1：verify_dart_semantic.py

- 扫描 quwoquan_app/lib/**/*.dart
- 正则检出：width/height、leadingSize、fontSize、size、EdgeInsets、BorderRadius、Color(0x)
- 白名单：design_system/、constants/、*_test.dart 内 fixture
- 输出：path:line: snippet，exit 1 表示失败

### L2：规则增强

- 02-dart-coding：补充 width/height/leadingSize 禁止与 AppSpacing.minInteractiveSize 示例
- 06-semantic-consistency-audit：将 inline Python 替换为调用脚本
- 00_MASTER_DEVELOPMENT_FLOW：Implement 约束表增加一行

### L3：FF/deliver 前置

- design.md 模板：可选「编码规范与设计 token」小节
- tasks.md 模板：含 UI 的 task 增加「执行 verify_dart_semantic」步骤
- opsx-apply：变更含 lib/**/*.dart 时自动执行脚本

### L4：元数据驱动（未来演进）

- contracts/metadata/_shared/design_tokens.yaml
- codegen 生成常量，lint 用白名单
- 当前不实施，列入搁置

## 适用场景与约束

- 适用：所有涉及 quwoquan_app/lib 变更的迭代
- 约束：无 metadata 变更，无 Go codegen；纯脚本+规则+流程

## 未来演进

- design-token-metadata-registry 实施后，verify_dart_semantic 可读取 token 白名单，减少误报
