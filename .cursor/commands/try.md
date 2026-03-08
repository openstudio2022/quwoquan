---
name: /try
id: try
category: Workflow
description: 原型模式（快速验证想法，无需特性树分解，所有编码约束完整遵从）
---

> 适用场景：想法尚未明确、需要快速验证技术可行性或产品方向，才能决定是否基线化。

## 核心定位

`/try` 是一种**"先实验，再基线"**的工作模式。

**仅豁免**：不要求提前创建特性树节点（spec.md/design.md/tasks.md/acceptance.yaml）。

**完整遵从**：所有其他核心约束——DDD 分层、metadata-first、runtime 统一、Dart 编码规范、错误码规范、codegen 保护、**PA 引擎契约规范**、最小 TDD 闭环、关键非功能验证——**一条不豁免**。

---

## 与标准流程的差异

| 约束 | 标准流程（/prd → /design → /dev） | /try |
|------|--------------------------------|------|
| 特性树分解（spec/design/tasks/acceptance） | **必须** | **豁免** |
| DDD 分层约束 | 必须 | **必须** |
| metadata-first（新实体先更新 YAML） | 必须 | **必须** |
| runtime 统一能力（runtime/errors 等） | 必须 | **必须** |
| Dart 编码规范（禁止硬编码字面量等） | 必须 | **必须** |
| 错误码规范（禁止硬编码） | 必须 | **必须** |
| codegen 保护（DO NOT EDIT 禁止手改） | 必须 | **必须** |
| PA 引擎契约规范（引擎逻辑禁止字段名字符串字面量；活跃版本≤2个；修改契约字段须走 `/extend pa-contract`） | 必须 | **必须** |
| 最小测试先行（Red → Green → Refactor） | 必须 | **必须** |
| 关键 NFR 验证（实时性 / 弱网 / 性能 / 弹性） | 必须 | **必须** |
| G2 卡点（make build + test-contract） | 每 task 后 | 每次主要变更后 |

---

## 执行方式

### 1. 声明原型目标

开始时需明确：

- **验证什么**：要回答的核心问题是什么？
- **成功标准**：什么结果说明这个想法可行？
- **预计范围**：大致会涉及哪些层（UI / domain / infrastructure）？
- **对标输入**：如有标杆产品、原型、截图/视频、公开代码或公开技术文档，需说明借鉴点与验证重点；如无，也应说明“本次不依赖外部对标”
- **最小测试闭环**：用什么失败测试证明假设成立或失败？
- **NFR 假设**：是否涉及实时性、弱网、并发、容量、交互体验？

---

### 2. 遵从所有编码约束实施

**Go 端（强制）**：
- domain 禁止 import application/adapters/infrastructure
- 仅 infrastructure + tests 可 import 数据库驱动（go.mongodb.org、jackc/pgx、go-redis）
- 必须使用 runtime/errors、runtime/config、runtime/messaging、runtime/http
- codegen 文件（DO NOT EDIT）禁止手改
- **新建实体/字段 → 必须先更新 `contracts/metadata/` YAML → 再 `make codegen`**

**Dart 端（强制）**：
- 禁止硬编码视觉字面量（fontSize、EdgeInsets、Color、BorderRadius、width/height）
- 禁止相对路径 import（必须 `package:`）
- Feature 禁止直接 import 其他 Feature 内部文件
- 错误码禁止硬编码，端侧用 `*ErrorCode.fromCode().toDisplayMessage(l10n)`
- Mock/Remote 切换通过 Provider，禁止 UI 直接 `new MockXxxRepository()`

**编码约束来源**：同 `01-arch-constraints.mdc`（Go）+ `02-dart-coding.mdc`（Dart）。

---

### 3. 每次主要变更后执行 G2 卡点

**先做最小 TDD 闭环**：
- 先写一个能证明关键假设的失败测试
- 再写最小实现让测试转绿
- 再做必要重构与补充观测
- 若是实时性原型，至少模拟弱网/高延迟/断线之一
- 若是体验原型，至少给出一个对标交互与本方案差异结论

```bash
make build                         # 编译通过（云侧）
make test-contract                 # 契约测试通过（云侧）
# 端侧变更时追加：
flutter test test/cloud/ test/components/ test/ui/
```

失败 → 修复后继续，不得遗留编译错误或测试失败。

---

### 4. 验证完成后的选择

- **验证失败（想法不可行）** → 清理原型代码，记录结论，无需后续步骤
- **验证成功（想法可行）** → 执行 `/land` 将原型成果基线化

**要求**：
- `/try` 不是长期工作模式；验证成功后必须通过 `/land` 回补到特性树四件套与标准 SDD 链路
- 若原型过程中形成了明确的对标结论，也应在 `/land` 后同步吸收到 `spec.md / design.md`

---

## 约束说明

### 为什么 /try 仍要遵从 metadata-first？

原型也会产生真实的实体和数据结构。如果原型绕过 metadata，数据模型就无法被 codegen 保护，也无法在 `/land` 时自动生成正确的基线制品。**以正确方式完成原型，后续基线化成本更低**。

### 为什么 /try 仍要遵从 DDD 分层？

原型代码很可能直接演进为生产代码（特别是验证成功后）。从一开始就保持正确的分层，避免 `/land` 后还需要大规模重构。

---

## 输出示例

启动时：

```
/try 启动

验证目标：<要回答的核心问题>
成功标准：<什么结果说明可行>
涉及范围：<domain / infrastructure / Dart UI>

[约束加载]
  ✓ DDD 分层约束已激活
  ✓ metadata-first 约束已激活
  ✓ Dart 编码规范已激活
  ✓ G2 卡点已激活（每次主要变更后）

[开始实施...]
```

验证完成后：

```
/try 验证完成

结论：<可行 / 不可行>

关键发现：
  - <发现 1>
  - <发现 2>

产生的变更：
  - contracts/metadata/...（已更新）
  - services/.../...（已实现）
  - quwoquan_app/lib/...（已实现）

最小 TDD 闭环：PASS / FAIL
G2 卡点：make build PASS / make test-contract PASS

NFR 结论：
  - 实时性/弱网/并发/体验：<是否验证、结论如何>

下一步：
  ✓ 可行 → 执行 /land 将原型成果基线化
  ✗ 不可行 → 记录结论，清理原型代码（git checkout -- . 或 git stash）
```

---

## 与其他命令的关系

| 命令 | 职责 | 与 /try 关系 |
|------|------|-------------|
| `/explore` | 探索思考，不写任何代码 | try 前可先 explore |
| `/try` | **原型实验**，快速验证想法 | 验证阶段 |
| `/land` | 将原型成果基线化 | try 验证成功后的必须步骤 |
| `/prd` → `/design` → `/dev` | 标准 SDD 全流程 | try + land 完成后，可继续迭代用标准流程 |
