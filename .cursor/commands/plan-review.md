---
name: /plan-review
id: plan-review
category: Planning
description: 规划前多角色交叉检视规格、任务清单与验收标准的完备性，按商用成熟度刷新规划（不写实现）
---

# /plan-review

目标：在冻结或开发**之前**，用多角色视角交叉检视当前规划（**目标 / 规格 / 任务清单 / 验收标准**）的完备性，定位盲区与不符合项，并把规划**刷新**到商用上线水准。只读审视 + 刷新规划文档，不写实现代码。

适用：已通过 `/explore` 明确一棵树归属，且已有初版 `spec.md` / `acceptance.yaml` / 任务清单（草案或会话计划），准备 `/baseline` 冻结或 `/dev` 执行之前。

对标基线：交互与视觉对标 **微信 / 小红书** 与 **Apple HIG**；功能完备性、可靠性与可运营性对标成熟商用 App。

真相源（不得绕过）：`specs/00_MASTER_DEVELOPMENT_FLOW.md`、特性树 `spec.md/design.md/acceptance.yaml`、`contracts/metadata/**`、`.cursor/rules/**`（尤其 `13-coding-discipline.mdc` 八角色 R01–R32）。

---

## 多角色交叉检视清单

逐角色判定 `✓ 满足 / ⚠ 待补 / ✗ 阻断`。每条 `⚠`/`✗` 必须落到**具体规格段落或具体任务项**，禁止空泛结论。

| 角色 | 检视重点（规划是否已写清） |
|---|---|
| 设计师 / UX | 信息架构与导航壳；按住/松手/滑动等交互范式对标微信/小红书；录制/加载/上传/发送等**过程动效**；空态/错误态/权限态/加载态四态齐全；深浅色、断点自适应、无障碍与触控热区；视觉全部走 `AppColors/AppSpacing/AppTypography/UITextConstants` 语义 token。 |
| 产品经理 / 产品设计师 | 用户价值与北极星指标；功能闭环**无盲区**（主流程 + 边界 + 失败 + 并发）；AppRoot Journey/Scenario 影响；Out of Scope 明确；登录/权限入口满足「关闭安全态 + 成功目标态」无死循环。 |
| 架构设计专家 | 一棵树归属正确；DDD 单向依赖与边界合理；抽象克制（R24，不新增旁路分支）；存储无关、`contracts/metadata` 为字段/错误码/path/surface/operation 唯一真相源；端云 DTO↔struct↔YAML 对齐；可扩展不可逆。 |
| 代码评审专家 | 规划是否要求强类型（禁 `Map<String,dynamic>`/`any` 穿透）、无硬编码 path/错误码/surface、无空 catch、codegen 不手改；**未上线即清理过往兼容与死代码，统一升级到新契约**，不保留兼容分支。 |
| 测试与质量专家 | 验收意图 UAT/SIT/GWT/contract 完整；T1~T4 证据矩阵可形成；Mock↔Remote 一致（T3 断言在 T2 有对应）；`acceptance.yaml` 声明的测试路径可落地；门禁可绿。 |
| 运维与运营专家 | SLO/KPI、告警阈值、采样与 TTL；灰度与回滚演练；新页面/新 API/新行为信号的**埋点与归因链**（曝光/停留/异常 + referralSource/feedRequestId）；AB 可分桶；env-seed-first（alpha/beta/gamma）。 |
| 工程能力 / 自动化专家 | metadata→verify→codegen 顺序；触发范围门禁脚本明确且可重复；CI 闭环；规划本身可被 `make gate` / 专项 `verify_*` 校验，不依赖人工记忆。 |

---

## 产出（刷新后的规划）

1. **刷新 `spec.md`**：补齐目标、范围、Out of Scope、UX 与过程动效、权限与异常语义、并发与可靠性、SLO/灰度/回滚/观测。
2. **刷新 `acceptance.yaml`**：将不符合项转化为可测 GWT/UAT/SIT/contract，绑定 T1~T4 与磁盘测试路径。
3. **刷新任务清单**：可执行、职责归位（按 DDD 与目录约束）、每项含测试与验收，标注触发门禁。
4. **不符合项台账**：每项给出处置——`本轮补齐` / `转 specs/changelog/CR-*.yaml` / `显式列入 Out of Scope`，不允许悬空。

---

## 阻断（返回 `GATE_BLOCK`）

- 无法定位一棵树归属，或验收不可测、缺 T1~T4 证据矩阵。
- 字段/错误码/path/surface/operation 未以 `contracts/metadata` 为真相源。
- 用户可见可发布能力缺 SLO/KPI、权限、生命周期、灰度、回滚或观测。
- 发现方案未收敛或存在重大架构分叉 → 退回 `/prd` + `/design`。

---

## 与其他命令的关系

| 命令 | 时机 | 与本命令差异 |
|---|---|---|
| `/explore` | 规划最前 | 只定位归属；`/plan-review` 检视并刷新已有规划 |
| `/prd` `/design` | 冻结规格/设计 | 产出单层文档；`/plan-review` 跨角色横向检视完备性 |
| `/baseline` | 冻结 | `/plan-review` 通过后再 `/baseline` |
| `/plan-next` | 任务后 | 本命令面向「执行前刷新」，`/plan-next` 面向「执行后再规划」 |
