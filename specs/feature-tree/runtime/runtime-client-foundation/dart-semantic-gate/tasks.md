# dart-semantic-gate 任务

## 当前交付任务

| 任务 | 对应 L4 | 顺序 |
|------|---------|------|
| M1 新建 scripts/verify_dart_semantic.py | verify-script-and-gate-integration | 1 |
| M2 修改 gate_repo.sh 调用脚本 | verify-script-and-gate-integration | 2 |
| M3 更新 02-dart-coding、06 规则、00_MASTER_DEVELOPMENT_FLOW | rules-and-flow-enhancement | 3 |
| M4 更新 FF 模板（design/tasks）与 opsx-apply 逻辑 | ff-deliver-semantic-checklist | 4 |

### M1：verify_dart_semantic.py

- [x] 新建 `scripts/verify_dart_semantic.py`
- [x] 正则：width、height、leadingSize、fontSize、size、EdgeInsets、BorderRadius、Color(0x)
- [x] 新增 iOS 语义规则：`Icons.chevron_right`、`CupertinoPageScaffold` 混用 Material 交互、selector leading back
- [x] 白名单：lib/core/design_system/、lib/core/constants/
- [x] 输出 path:line:snippet，失败 exit 1
- [x] 能检出 publish_circle_select_page 历史硬编码（回归验证）

### M2：gate 集成

- [x] 在 gate_repo.sh run_app 中，flutter analyze 之后追加调用
- [x] `python3 scripts/verify_dart_semantic.py || exit 1`
- [x] gate 文案明确包含 iOS 语义门禁说明

### M3：规则与流程

- [x] 02-dart-coding §1.1 补充 width/height/leadingSize 禁止示例
- [x] 02-dart-coding §2.2 补充触控/布局尺寸 API 表
- [x] 06-semantic-consistency-audit 提交前检查改为调用脚本
- [x] 00_MASTER_DEVELOPMENT_FLOW Implement 约束表增加「硬编码触控/布局尺寸禁止」

### M4：PRD/Design/Deliver 前置

- [x] `/prd`/`/design`/`/dev` 相关命令文档或逻辑：design 模板增加「编码规范与 token」可选小节
- [x] tasks 模板：含 UI 的 task 增加 verify_dart_semantic 步骤
- [x] `/dev`：变更含 lib/**/*.dart 时自动执行脚本

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|------|----------|--------------|
| design-token-metadata-registry | 需 contracts 层设计 token 注册表，与现有 AppSpacing 手写结构有整合成本 | L1~L3 交付并通过 gate 后，评估是否启动 |

## 未来演进任务

- design_tokens.yaml → codegen 生成常量 → verify_dart_semantic 白名单联动
- 与 app-locale-infrastructure 的 CJK 字面量规则合并到同一脚本
