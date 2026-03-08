---
name: /commit
id: commit
category: Workflow
description: 提交入库（根流程唯一 submit 语义命令；标准流读取 /dev 自动归档结果）
---

> SDD 主流程：... → dev（已自动归档） → **commit** → deploy

在特性开发完成后，一步执行**提交入库**（L1+L2 门禁 → 审计 → git commit → push → merge）。标准流程下，归档应已由 `/dev` 自动完成。

**语义统一**：
- 根目录 `/commit` 是仓库流程中**唯一 submit 语义命令**
- 历史 `submit-with-gate` / `submit-with-audit` 仅作兼容入口，必须遵循与 `/commit` 相同的门禁与职责分工

若因历史流程或人工修复尚未归档，`/commit` 可兼容补做归档；但这不是标准流程。

---

## 前置条件检查

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | 目标特性四类文档齐全 | spec.md、design.md、tasks.md、acceptance.yaml 均存在 |
| 2 | tasks 当前交付任务已完成 | tasks.md 中当前交付任务全部 `[x]`（按 Story 交付完成） |
| 3 | acceptance 无 pending | 所有 An status ≠ `pending`（须为 implemented/waived/deferred），且核心项具备 `T1~T4` 映射 |
| 4 | dev 实施已完成 | 代码实现完整，本地 make build 通过 |
| 5 | 非功能验收已闭环 | 实时性 / 弱网 / 并发 / 弹性 / 体验等要求已有证据 |
| 6 | 灰度与回滚条件已就绪 | 发布时不会临时补观测与回滚参数 |

**若不满足**：输出补全列表，不执行：

```
前置条件不满足：
□ tasks 未完成 → 先执行 /dev 完成实施
□ acceptance 有 pending → 更新 An status 为 implemented/waived/deferred
□ 四类文档不齐全 → 补全后重试
```

---

## 执行流程

### 阶段 1：读取已自动完成的归档结果（兼容未归档场景）

标准期望：目标特性已由 `/dev` 自动归档。

若目标特性尚未归档（`acceptance.yaml` 中 `archived ≠ true`），执行兼容补归档：

**1a. 前置检查**：
- tasks.md 当前交付任务全部 `[x]`
- acceptance.yaml 所有 An status ≠ `pending`
- status=`implemented` 的 An 的 `tests[].file` 在仓库中存在

**1b. 自动 G3 门禁**：

```bash
make gate-full
```

包含：metadata 一致性、DDD 结构约束、codegen hash 比对、端侧语义审计、云侧契约测试、特性树一致性（四类文档 + acceptance 状态）。

**任一失败 → 停止 → 输出错误 + 修复建议 → 修复后重跑。**

**1c. 归档回写**（G3 通过后）：

```yaml
# acceptance.yaml 顶层
archived: true
archived_at: <ISO8601 当前时间>
```

```yaml
# specs/feature-tree/tree_index.yaml
status: completed
```

（若节点在 tree_index 中找不到 → 输出 WARNING + 提示手动添加。）

若已归档（archived=true）→ 直接进入阶段 2。

---

### 阶段 2：提交入库（根流程 submit 语义）

**2.1 获取当前状态**：

```bash
git branch --show-current
git status -sb
```

若无待提交改动 → 提示「当前没有可提交的改动」并结束。

**2.2 确定变更范围，执行 L1+L2 门禁**：

| 变更范围 | 门禁命令 |
|---------|---------|
| quwoquan_app/ | L1: `flutter test test/cloud/ test/components/ test/ui/` |
| quwoquan_service/ | L2: `cd quwoquan_service && make gate` |
| 两者都有 | L1 + L2（推荐：`make gate` 全量） |
| specs/ 或 contracts/ | `make verify` |

**L1 或 L2 任一失败 → 不执行提交，输出修复建议。**

**若为高风险特性，额外要求**：
- 校验 `acceptance.yaml` 中 `non_functional_acceptance` 已补齐
- 校验 `design.md` 中灰度、SLO、回滚、观测章节存在
- 校验归档报告可说明 `T1~T4` 与 NFR 证据归属

**2.3 审计**（按变更范围）：
- 端侧变更：`flutter analyze` + 硬编码视觉字面量检查
- 云侧变更：DDD 层级导入 + 数据库驱动隔离 + runtime 统一能力
- metadata 变更：`make verify`
- 特性树变更：tree_index ↔ 目录 + 四类文档完整性

审计不通过 → 生成修复计划（文件:行号 + 违反规则 + 修复建议）→ 用户批准 → 自动修复 → 重审。

**2.4 提交推送**（审计通过后）：

```bash
git add -A
git commit -m "<feat|fix|chore>: <message>"
git push origin <CURRENT_BRANCH>
```

**2.5 合入主干**（若非 main 分支）：

```bash
git checkout main
git pull origin main                        # 同步主干到本地
git checkout <CURRENT_BRANCH>
git merge main                              # 合并主干到开发分支
git push origin <CURRENT_BRANCH>            # 推送开发分支
git checkout main
git merge <CURRENT_BRANCH> -m "Merge branch '<CURRENT_BRANCH>'"
git push origin main                        # 合入主干
git checkout <CURRENT_BRANCH>              # 切回开发分支
```

---

## 输出摘要

```
提交完成：<feature-name>

| 阶段         | 状态                        |
|--------------|-----------------------------|
| 归档         | archived=true，status=completed |
| make gate-full | PASS                      |
| L1+L2 门禁   | PASS                        |
| 审计         | PASS                        |
| 非功能验收   | PASS                        |
| 灰度条件     | READY                       |
| git commit   | <hash>                      |
| git push     | origin/<branch>             |

下一步：/deploy 完成 integration 部署、L3/L4 验证、灰度到 prod。
```

---

## 与其他命令的关系

| 命令 | 作用 | 与 /commit 关系 |
|------|------|----------------|
| `/archive` | 兼容补归档 | commit 在发现未归档时可兜底调用其等价逻辑 |
| `/dev` | 逐 task 实施并自动归档 | commit 的标准前置 |
| `/deliver` | dev + commit 全链路 | deliver 的最后一步等价于 commit |
| `/deploy` | 部署到 integration → prod | commit 完成后执行 |
