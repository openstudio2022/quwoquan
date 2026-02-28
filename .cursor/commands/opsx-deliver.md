---
name: /opsx-deliver
id: opsx-deliver
category: Workflow
description: 端到端交付（Apply 条件就绪后，验收驱动完成开发 → 验证 → 归档 → 提交入库）
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — 阶段 3+4+5

在具备 `/opsx-apply` 条件后，**以 acceptance.yaml A1~A8 验收标准为驱动**，迭代完成开发，直至全部验收满足，再依次执行验证、归档与代码提交入库。适用于「一气呵成交付到合入」的场景。

**端到端链路**：特性 → **deliver 入库（L1/L2 自测通过）** → **/opsx-deploy 集成验证（L3/L4）** → 灰度到生产。

---

## 前置条件检查（执行前必须满足）

与 `/opsx-apply` 相同：

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | 目标特性已创建 | 目标节点目录存在，且包含 spec.md、design.md、tasks.md、acceptance.yaml |
| 2 | G0+G1 已通过 | 曾有 `/opsx-ff` 完成，且 make verify + codegen 已通过 |
| 3 | tasks.md 已就绪 | tasks.md 中有可执行任务列表，顺序为 metadata → codegen → 业务逻辑 → 测试 |
| 4 | 节点层级符合规范 | 目标节点层级符合 `01_FEATURE_TREE_LEVEL_DEFINITIONS.md` |

**若不满足**：不执行；输出 `/opsx-apply` 的补全列表，引导用户补全后再执行 `/opsx-deliver`。

---

## 执行流程

### 阶段 1：验收驱动的迭代开发（Apply 循环）

以 **acceptance.yaml A1~A8** 为北极星，不断驱动完成未满足的验收项，直至全部满足。

#### 1.1 加载验收标准与 tasks

1) 读取 `acceptance.yaml`，解析 A1~A8 及各验收项的含义与判定方式  
2) 读取 `tasks.md`，加载当前交付任务列表  
3) 建立「验收项 ↔ 任务/实现」的映射（显式或隐含均可）

#### 1.2 验收驱动循环

```
循环：
  1) 对照 acceptance.yaml A1~A8，逐项检查当前实现是否满足
  2) 若全部满足 → 退出循环，进入阶段 2
  3) 若存在未满足项 → 识别对应的 tasks 或实现缺口
  4) 选取下一未完成任务或缺口，执行实现（metadata → codegen → 业务逻辑 → 测试）
  5) 每完成一个 task 或缺口，立即执行 G2：
       make build
       make test-contract
  6) 更新 tasks.md 完成标记
  7) 回到步骤 1
```

**约束**（与 `/opsx-apply` 相同）：DDD 分层、metadata-first、runtime 统一、codegen 保护、Dart 设计系统、Feature 隔离。

#### 1.3 循环退出条件

- 所有 A1~A8 验收项均已满足  
- tasks.md 当前交付任务均已标记完成  

---

### 阶段 2：验证（G3）

开发完成后，AI Agent **必须自动执行**：

```bash
make gate-full
```

包含：metadata 一致性、DDD 结构约束、codegen hash、端侧语义、特性树一致性、契约测试。

**失败** → 输出错误 + 修复建议 → 修复后重跑 gate-full → 通过后进入阶段 3。

---

### 阶段 3：归档

G3 通过后，执行归档逻辑（与 `/opsx-archive` 一致）：

1) 标记特性为 `archived`  
2) 生成复盘摘要  
3) 进入阶段 4

---

### 阶段 4：提交入库（G4）——分支开发模式

执行 `/submit-with-gate` 逻辑；**提交前必须执行 L1+L2 门禁并通过**（`make gate`），否则不得 commit。**默认采用分支开发模式**：在分支上开发 → 提交到远程分支 → 合入主干 → 从远程主干同步到本地主干。

1) 获取 `git status`、当前分支 `CURRENT_BRANCH`，分析变更范围  
2) **执行 L1+L2 门禁**（`make gate` 或按 scope）并通过  
3) 按范围执行审计（端侧 / 云侧 / 特性树）  
4) 审计通过后提交并推送**到当前分支**：
   ```bash
   git add -A
   git commit -m "<message>"
   git push origin <CURRENT_BRANCH>
   ```
5) 若当前**不在 main**，按分支开发模式执行：同步主干 → 合并到开发分支 → 推送开发分支 → 合入主干
   ```bash
   git checkout main
   git pull origin main                      # 同步主干到本地
   git checkout <CURRENT_BRANCH>
   git merge main                            # 合并主干到本地开发分支
   git push origin <CURRENT_BRANCH>          # 推送开发分支到远端
   git checkout main
   git merge <CURRENT_BRANCH> -m "Merge branch '<CURRENT_BRANCH>'"
   git push origin main                      # 合入主干
   git checkout <CURRENT_BRANCH>             # 切回开发分支
   ```
6) 若当前**已在 main**，则 push 后同步即可：`git pull origin main`（如有必要）

**前置**：工作区在仓库根、已配置 git 与 `origin`。若无待提交改动，跳过本阶段并提示。

---

## 与其他命令的关系

| 命令 | 作用 | 与 /opsx-deliver 关系 |
|------|------|----------------------|
| /opsx-apply | 逐 task 实施，每 task 后 G2 | deliver 的阶段 1 复用 apply 的实施逻辑与 G2 |
| /opsx-verify | 验证 + G3 门禁 | deliver 的阶段 2 等价于 verify |
| /opsx-archive | 归档特性 | deliver 的阶段 3 等价于 archive |
| /submit-with-gate | 审计 + 提交 + 推送 | deliver 的阶段 4 等价于 submit-with-gate |

**/opsx-deliver** = Apply（验收驱动循环）+ Verify + Archive + Submit，一气呵成完成从「apply 条件就绪」到「代码入库」的全流程。

**后续步骤**：入库后执行 `/opsx-deploy`，完成部署到 integration、L3/L4 集成验证、灰度到 prod。

---

## 输出摘要

全部完成后输出：

```
交付完成：<feature-name>

| 阶段 | 状态 |
|------|------|
| 1. 验收驱动开发 | A1~A8 满足，tasks 完成 |
| 2. 验证 (G3) | make gate-full 通过 |
| 3. 归档 | 已标记 archived |
| 4. 提交入库 (G4) | 已 commit + push |

变更摘要：<git diff --stat>

后续：执行 /opsx-deploy 完成 integration 部署、L3/L4 验证、灰度到 prod。
```
