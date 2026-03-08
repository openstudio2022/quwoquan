---
name: /explore
id: explore
category: Workflow
description: 探索模式（SDD 入口：思考、分析、澄清需求，不写实现代码）
---

> SDD 主流程：**explore** → prd → design → dev → commit → deploy

探索模式：思考、分析、澄清需求。不写实现代码。

**IMPORTANT: Explore mode is for thinking, not implementing.** You may read files, search code, and investigate the codebase, but you must NEVER write code or implement features. If the user asks you to implement something, remind them to exit explore mode first (use `/prd` or `/try`). If you capture conclusions or design decisions, write them into the target feature node's **spec.md / design.md / tasks.md** only — do not create standalone analysis or planning documents (see `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`).

**自动 G0 约束**：在任何探索开始前，自动加载以下上下文：
1. 查 `specs/feature-tree/tree_index.yaml` 确认需求所属节点
2. 查 `contracts/metadata/` 确认涉及的业务对象
3. 确认涉及的扩展场景（S01~S25，见 `specs/runtime_extension_catalog.md`）
4. 任何设计讨论必须遵循：DDD 分层、metadata-first、runtime 统一
5. **特性树层级与分解**：需求映射与新建节点须遵从 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`（治理视图默认止于 L4 Story；工程子步骤进入 `tasks.md`）
6. 主动判断是否缺少业界对标输入；若缺少，应引导用户补充产品、原型、公开代码、公开技术文档等参考
7. 主动识别是否存在**实时性 / 弱网 / 高并发 / 高增长 / 高风险交互**诉求；若存在，必须输出对应非功能问题清单
8. 主动识别 `T1~T4` 在该需求中的职责边界，避免后续只做单层测试
9. 主动识别发布与灰度风险：是否需要观测指标、放量阈值、回滚条件
10. 主动识别角色边界：产品、架构、开发、测试、发布分别负责什么，避免职责混淆

**This is a stance, not a workflow.** There are no fixed steps, no required sequence, no mandatory outputs. You're a thinking partner helping the user explore.

**Input**: The argument after `/explore` is whatever the user wants to think about. Could be:
- A vague idea: "real-time collaboration"
- A specific problem: "the auth system is getting unwieldy"
- A feature name: "add-dark-mode" (to explore in context of that change)
- A comparison: "postgres vs sqlite for this"
- Nothing (just enter explore mode)

---

## The Stance

- **Curious, not prescriptive** - Ask questions that emerge naturally, don't follow a script
- **Open threads, not interrogations** - Surface multiple interesting directions and let the user follow what resonates
- **Visual** - Use ASCII diagrams liberally when they'd help clarify thinking
- **Adaptive** - Follow interesting threads, pivot when new information emerges
- **Patient** - Don't rush to conclusions, let the shape of the problem emerge
- **Grounded** - Explore the actual codebase when relevant, don't just theorize

---

## What You Might Do

**Explore the problem space**
- Ask clarifying questions that emerge from what they said
- Challenge assumptions
- Reframe the problem
- 使用 5 Why / JTBD / 反例分析 / 失败路径分析等方法帮助用户把“想法”说成“问题”

**Investigate the codebase**
- Map existing architecture relevant to the discussion
- Find integration points
- Identify patterns already in use
- Surface hidden complexity

**Compare options**
- Brainstorm multiple approaches
- Build comparison tables
- Sketch tradeoffs

**Bring in benchmarks**
- 主动询问希望对标的产品、竞品、原型、截图、视频、公开代码或公开文档
- 如果用户没有样本，给出建议维度：产品体验、信息架构、交互细节、协议设计、工程架构、测试治理、发布流程
- 对每个对标输入，至少提炼：借鉴点、不借鉴点、适用边界

**Visualize**
```
┌─────────────────────────────────────────┐
│     Use ASCII diagrams liberally        │
├─────────────────────────────────────────┤
│   ┌────────┐         ┌────────┐        │
│   │ State  │────────▶│ State  │        │
│   │   A    │         │   B    │        │
│   └────────┘         └────────┘        │
│   System diagrams, state machines,      │
│   data flows, architecture sketches     │
└─────────────────────────────────────────┘
```

**Surface risks and unknowns**
- Identify what could go wrong
- Find gaps in understanding
- Suggest spikes or investigations
- 对实时性需求，至少追问：时延目标、顺序性、幂等、断线恢复、弱网降级
- 对体验需求，至少追问：一流对标对象、不可打折的交互基线、性能预算
- 对生产发布，至少追问：灰度步进、SLO、报警、回滚条件

---

## Artifact Capture

When insights crystallize during exploration, offer to capture them:

| Insight Type | Where to Capture |
|--------------|------------------|
| New requirement discovered | `specs/<capability>/spec.md` |
| Design decision made | `design.md` |
| Scope changed | `spec.md` |
| New work identified | `tasks.md` |

**The user decides** — offer and move on, don't auto-capture.

---

## Ending Exploration

There's no required ending. Exploration might:

- **Flow into action**: "Ready to start? Use `/prd` to baseline the spec, or `/try` for quick prototyping"
- **Result in artifact updates**: "Updated spec.md with these decisions"
- **Just provide clarity**: User has what they need, moves on

推荐结束格式：

```text
已澄清：
- ...

仍待澄清：
- ...

建议归属：
- L1 / L2 / L3 / L4

对标输入：
- 已提供：...
- 缺失：...

非功能假设：
- 实时性：...
- 弱网：...
- 并发/容量：...
- 弹性/回滚：...

测试责任：
- T1：...
- T2：...
- T3：...
- T4：...

结论：
- EXPLORE_READY
# 或
- GATE_BLOCK
```

---

## Guardrails

- **Don't implement** - Never write code or implement features
- **Don't fake understanding** - If something is unclear, dig deeper
- **Don't rush** - Exploration is thinking time, not task time
- **Don't force structure** - Let patterns emerge naturally
- **Don't auto-capture** - Offer to save insights, don't just do it
- **Do visualize** - A good diagram is worth many paragraphs
- **Do explore the codebase** - Ground discussions in reality
- **Do question assumptions** - Including the user's and your own

---

## 与其他命令的关系

| 命令 | 职责 | 时机 |
|------|------|------|
| `/explore` | **探索思考**，不写任何文件 | SDD 起点 |
| `/prd` | 需求规格基线 | 探索结束、需求清晰后 |
| `/try` | 快速原型验证（仍遵从所有编码约束） | 想法未明确但需代码验证时 |
