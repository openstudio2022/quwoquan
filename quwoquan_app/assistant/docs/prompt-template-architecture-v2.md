# 提示词模板架构 v2 —— 全局统一与最优设计

> **收口说明**：当前 Prompt 相关必读入口为 `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md` 与 `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`。本文档保留为 Prompt 细节设计参考。

> 基于现有引擎实现 + 业界一流实践（Anthropic System Prompt 设计、OpenAI Assistants API、Microsoft Copilot Stack）的完整分析与重构方案。

---

## 一、现状诊断

### 1.1 当前 System Prompt 组装链路

```
llm_provider._resolvePlannerPrompt()
├── appendLayer('stack.identity')             // 身份与使命
├── appendLayer('stack.safety')               // 安全与降级边界
├── appendLayer('stack.persona')              // 全局人格与语气
├── appendLayer('stack.tool_policy')          // 工具权限与执行约束
├── appendPhaseContract(phase)                // 分阶段输出契约
└── stagePrompt (planner/synthesizer/...)     // 阶段模板 + 末尾 {{上下文变量}}
    合并方式: stackLayers.join('\n\n')        // 分层文本顺序拼接

phase owner（额外注入的数据消息）
├── system: "当前轮次状态机脚本（必须遵循）：" + JSON
├── system: "最小上下文锚点：" + anchor text
├── system: "可查询能力目录：" + catalog text
├── system: "记忆检索：" + recalled texts
├── system: "会话记录摘要：" + summary
└── system: "上下文组装结果（仅按需使用）：" + JSON envelope
```

### 1.2 识别到的核心问题

| # | 问题 | 具体表现 | 影响 |
|---|------|---------|------|
| P1 | **身份宣言过薄** | `global_system` 仅 5 行笼统约束，无命名、无使命、中英混写 | 角色锚点弱，模型跨轮人设漂移 |
| P2 | **skill 注入位置错误** | `domainSkillInstruction` 通过 `{{}}` 嵌入 `runtime_policy` 中间 | skill 指令被策略规则文本包夹，模型注意力被稀释 |
| P3 | **persona 无独立容器** | skill.policy.md 的人设/语气被混入 `mergedInstruction` 大文本 | 模型无法区分「我应该扮演什么角色」和「执行规则是什么」 |
| P4 | **上下文为 JSON blob** | `contextEnvelope` 整个 JSON 对象注入，模型需解析嵌套结构 | 定位单个槽位（如城市名）的认知负担高 |
| P5 | **输出契约需要严格分阶段** | 单一 output contract 会让 planning 与 synthesis 共用同一约束 | planning 需要 JSON 格式，synthesis 需要 userMarkdown，互相干扰 |
| P6 | **system 消息过多且无序** | 旧单文件 owner 曾用 6 个 `insert(0,...)` 注入，最终顺序与语义优先级不一致 | 模型上下文窗口利用率低，重要信息被挤到中间 |
| P7 | **全局策略英文残留** | `global_policy` 全英文，与中文 skill 指令混合 | 语言一致性差，模型在中文回答时可能产生风格跳跃 |
| P8 | **无 System Prompt Cache** | 每次请求重新组装全部固定层 | 浪费首次 token 计费（Anthropic/OpenAI 均支持固定前缀缓存） |
| P9 | **对话状态与 skill 脱节** | 状态机脚本作为独立 system 消息，与 skill 指令无关联标记 | 模型难以将「当前状态 S2」与「skill 中 S2 应做什么」关联 |
| P10 | **模板变量无类型预处理** | `_stringify()` 简单 toString，Map/List 直接转字符串 | JSON 类型变量在 Markdown 模板中呈现为 `{key: value}` 非人类可读格式 |

---

## 二、业界一流提示词结构原则

### 2.1 语义分区原则（Semantic Sectioning）

每个功能区块用明确标记隔离（XML 标签 / `##` 标题 / `===` 分隔符），模型按区块聚焦注意力。

**Anthropic 实践**：
```xml
<instructions>具体指令</instructions>
<context>动态上下文</context>
<examples>少样本示例</examples>
```

**本系统当前做法**：五层文本 `\n\n` 拼接，无语义标记 → 区块边界模糊。

### 2.2 固定层 vs 动态层分离（Static vs Dynamic）

| 类别 | 内容 | 变化频率 | 位置 |
|------|------|----------|------|
| 固定层 | 身份、安全、语气基线 | 从不变 | System Prompt 最前 |
| 半固定层 | 输出契约、工具策略 | 按阶段变 | System Prompt 中段 |
| 动态层 | skill 指令、上下文、状态 | 每轮变 | System Prompt 末段或独立消息 |

**收益**：固定层可利用 Prompt Caching（Anthropic Claude 缓存命中后首次 token 成本降低 90%，OpenAI 降低 50%）。

### 2.3 上下文接近性原则（Context Proximity）

- 与当前 user message 最相关的信息放在 prompt 末尾（离 user 消息最近）
- 固定策略规则放最前
- 研究表明模型对 prompt 首尾的注意力最高（「Lost in the Middle」现象）

### 2.4 输出规范内聚原则（Output Contract Cohesion）

- 每个阶段的输出规范独立描述，不依赖全局契约推断
- 禁止 planning 阶段加载 userMarkdown 格式规范，禁止 synthesis 加载 JSON 结构说明

### 2.5 指令与数据分离原则（Instruction-Data Separation）

当前 `=== CONTEXT_DATA_START/END ===` 是正确做法，应在所有注入点保持一致。

---

## 三、提示词模板 v2 架构

### 3.0 排序核心原则

排序遵循三条互相制约的原则，按优先级排列：

**原则 1：指令前置——模型必须尽早知道「干什么」**

模型的认知路径应当是：
```
我是谁（底线） → 这轮干什么（任务） → 干成什么样（输出） → 怎么干（技能/工具） → 基于什么干（数据）
```
任务定义（planner/synthesizer 等阶段模板）必须出现在前 300 token 以内。
决不能让模型读完 500+ token 的全局策略后才知道自己要做规划还是做回答。

**原则 2：指令与数据分离——数据永远在指令之后**

所有「怎么做」的指令（§1-§6）必须在所有「基于什么做」的数据（§7-§8）之前。
数据区放在 prompt 末尾、紧贴 user 消息，利用模型对首尾的高注意力（避免 Lost in the Middle）。

**原则 3：稳定前缀最大化——缓存层从外到内递减变化频率**

```
L1 固定前缀（所有请求共享）→ identity + safety           ~200 token  ← 缓存命中率最高
L2 阶段前缀（同阶段共享）  → L1 + task + output_contract ~600 token  ← 同一轮 ReAct 循环中缓存
L3 技能前缀（同技能共享）  → L2 + persona + skill + tool ~900 token  ← 同一会话同域缓存
L4 动态层（每轮变化）      → state + context              ~200 token  ← 不缓存
```

三条原则的优先级：**原则 1 > 原则 2 > 原则 3**。
当缓存与认知顺序冲突时，优先保证模型尽早拿到任务定义。

### 3.1 消息架构（指令优先序）

```
┌═══════════════════════════════════════════════════════════════════════════════════════════════╗
║  MESSAGE 1: SYSTEM PROMPT（指令层——全部「怎么做」集中在此）                                    ║
║                                                                                               ║
║  ┌─ L1 固定前缀 ─────────────────────────────────────────────────────────────────────────┐   ║
║  │ §1  <identity>        我是谁 + 底线信念             [固定，~80 token]                  │   ║
║  │ §2  <safety>          硬性禁止 + 降级协议 + 危机识别  [固定，~120 token]                │   ║
║  └────────────────────────────────────────────────────────────────── 缓存边界 L1 ──────┘   ║
║                                                                                               ║
║  ┌─ L2 阶段前缀 ─────────────────────────────────────────────────────────────────────────┐   ║
║  │ §3  <task>            本轮任务定义（planner/synthesizer）                              │   ║
║  │                       ——模型在此处（~250 token）已知「这轮干什么」                      │   ║
║  │ §4  <output_contract> 本阶段输出规范（phase-specific：plan/answer/ask_user）           │   ║
║  └────────────────────────────────────────────────────────────────── 缓存边界 L2 ──────┘   ║
║                                                                                               ║
║  ┌─ L3 技能前缀 ─────────────────────────────────────────────────────────────────────────┐   ║
║  │ §5  <persona>         全局语气基线 + 当前技能人设覆盖                                  │   ║
║  │ §6  <domain_skill>    技能目标/领域知识/工具指引/输出示例（phase-aware）                │   ║
║  │ §6b <tool_policy>     可用工具 + 调用原则 + 规范                                       │   ║
║  └────────────────────────────────────────────────────────────────── 缓存边界 L3 ──────┘   ║
╠═══════════════════════════════════════════════════════════════════════════════════════════════╣
║  MESSAGE 2: DATA（数据层——全部「基于什么做」集中在此，紧贴对话记录）                          ║
║                                                                                               ║
║  ┌─ L4 动态层（每轮变化，不缓存）───────────────────────────────────────────────────────┐   ║
║  │ §7  <dialogue_state>  当前对话状态 + 待填充槽位 + 本轮约束                             │   ║
║  │ §8  <context_slots>   语义化上下文（位置/时间/画像/记忆/设备）                         │   ║
║  └──────────────────────────────────────────────────────────────────────────────────────┘   ║
╠═══════════════════════════════════════════════════════════════════════════════════════════════╣
║  MESSAGE 3+: CONVERSATION HISTORY + USER MESSAGE                                              ║
║  §9 记录消息 + 当前 user 消息                                                                ║
╚═══════════════════════════════════════════════════════════════════════════════════════════════╝
```

### 3.2 模型认知路径（逐层解读）

```
token 0-80:    "我是沃助理，底线是诚实/安全/尊重"                    ← 角色锚定
token 80-200:  "禁止编造实时数据，危机时提供热线"                    ← 红线约束
token 200-500: "你是总控规划器，拆解任务、补齐槽位、生成检索计划"     ← 任务定义！核心指令！
token 500-700: "输出 JSON，必须含 slotFillPlan/searchPlans..."        ← 知道输出什么格式
token 700-850: "你当前扮演天气助理，专业清晰..."                      ← 知道用什么风格
token 850-1100:"城市已就绪→执行检索；禁止编造天气数据..."             ← 具体技能指令
token 1100-1300:"当前状态 S1_城市补全，city=深圳，GPS=22.5,114.0..."  ← 数据（紧贴 user 消息）
token 1300+:   "深圳天气怎么样"                                      ← user 消息
```

**对比 v2 初版的问题**：初版让模型在 token 0-550 读完 identity → persona → safety → tool_policy，到 token 550+ 才在 stage prompt 中看到"你是总控规划器"。模型读了大量"怎么表现"的细节后，才知道"干什么"——这违反了认知效率原则。

### 3.3 设计理由

| 设计决策 | 理由 |
|---------|------|
| §1-§2 (identity+safety) 放最前 | 前提条件，且完全固定（~200 token），L1 缓存命中率最高 |
| §3 (task) 紧跟安全层 | **模型在 ~250 token 处就知道这轮干什么**，这是全文最重要的位置 |
| §4 (output_contract) 紧跟 task | 知道干什么后立即知道输出什么格式，形成完整的「任务-产出」认知闭环 |
| §5-§6 (persona+skill) 在 task 之后 | 先有任务定义，再叠加领域细节——模型此时已有任务框架，skill 指令作为补充而非主体 |
| §7-§8 (state+context) 独立为 MESSAGE 2 | 纯数据，不含指令，放在末尾紧贴 user 消息，利用尾部高注意力 |
| 指令层和数据层分属两条消息 | 指令-数据边界清晰，模型不会混淆"什么是规则"和"什么是本轮输入" |
| 消息总数 2+history（从 7+ 降为 2） | 进一步减少消息边界解析开销 |

---

## 四、各区块详细设计（按指令优先序排列）

> 以下区块按模型实际阅读顺序编号，与 3.1 消息架构一一对应。

### §1 身份宣言 `<identity>` — L1 固定前缀

**当前基线**（身份模板收敛前）：
```
你是商用级个人助理，必须遵守：
- 隐私最小化：仅在必要时调用工具能力；
- 不编造事实：证据不足时明确说明；
- 回复稳定：优先输出可执行下一步；
- 全程尊重用户意图与语言风格。
```

**v2 设计**：
```markdown
<identity>
你是「沃助理」——趣我圈商用级智能个人助理。

## 核心使命
帮助用户做出更好的决策、节省时间、解决实际问题。

## 基本信念
- 诚实：不编造事实，证据不足时坦诚说明
- 精准：直击用户真实需求，不绕弯子
- 安全：任何回复不得造成用户真实损害
- 尊重：全程尊重用户意图、语言风格与文化背景
</identity>
```

**改进点**：
- 有命名（「沃助理」）→ 角色锚点清晰，跨轮次不漂移
- 「使命」而非「规则清单」→ Anthropic Constitutional AI 设计哲学
- ~80 token，不占配额
- 纯中文，消除语言混杂
- 位置：**prompt 首部**，与 §2 一起构成 L1 固定前缀

---

### §2 安全边界 `<safety>` — L1 固定前缀

**当前**：分散在 `global_system`（2 行）+ `recovery_policy`（4 行）+ `global_policy`（4 行英文），共 3 个文件。

**v2 设计**（合并为独立区块，紧跟 identity）：
```markdown
<safety>
## 硬性禁止
- 禁止编造实时数据（天气/金融/医疗/交通）
- 禁止给出不可逆的有害建议（法律/医疗/金融的最终决策）
- 禁止向用户暴露内部字段名、JSON 结构、工具调用链、状态机状态名
- 禁止输出引发隐私恐慌的能力宣示文案

## 降级协议
- 证据质量低：诚实降级 + 提供官方信源路径
- 工具调用失败：说明限制 + 可重试一次，再失败则降级回答
- 高风险垂类（医疗/法律/金融）：必须附带专业人士建议提示

## 危机识别
- 检测到自杀/自伤/暴力/虐待等危机信号时：
  1. 立即提供安全热线（全国 24 小时心理援助热线 400-161-9995）
  2. 表达关切，不进行信息性回复
  3. 不进行诊断或评估
</safety>
```

**为什么 safety 在 identity 之后、task 之前**：
- 安全是前提条件（prerequisite），模型必须在知道任务之前就加载红线
- 与 identity 一起构成 L1 固定前缀（~200 token），**所有请求共享缓存**
- 三类安全规则层级分明（禁止→降级→危机），中文统一

---

### §3 任务定义 `<task>` — L2 阶段前缀

**当前**：stagePrompt（如 `planner.global_plan.md`）被放在 `_resolvePlannerPrompt` 的**最后一层**拼入，模型要读完 ~550 token 的全局策略才看到。

**v2 设计**（提前到第 3 位，~250 token 处模型已知干什么）：

task 区块直接由 stagePrompt 模板文件（如 `planner.global_plan.md`、`synthesizer.final_answer.md`）渲染，用 `<task>` 标签包裹：

```markdown
<task>
## 任务背景
你是商用级个人助理总控规划器，需要把用户问题拆解为可执行的垂类任务图。

## 任务目标
1. 路由到 19 垂类中的一个或多个域
2. 给出串并行执行计划
3. 对缺失上下文生成补齐任务
4. 为后续答案阶段准备证据和诊断信息

## 约束
- 查询必须单主题，跨主题问题必须拆分任务
- 不得伪造证据；证据不足时必须触发补查
- 高风险垂类必须带安全边界与免责声明

## 执行要求
- 输出 JSON，禁止自然语言包裹
- 必须输出 slotFillPlan / searchPlans / contextSlots
- 先补关键槽位，再执行联网查询

## 反思与自检
- 是否覆盖用户所有子问题？
- slotFillPlan 是否完整？
- 有 web_search 时 queryNormalization 是否已输出？
</task>
```

**关键改变**：
- 任务定义从 prompt **末尾**移到 **第 3 位**（~250 token 处）
- 模型读完 identity + safety 后**立即知道这轮干什么**
- 与 §4 output_contract 一起构成 L2 阶段前缀，同阶段连续调用可共享缓存
- stagePrompt 不再包含 `{{domainSkillInstruction}}` 占位符（skill 已分离到 §6）
- **反思与自检嵌入任务定义**——模型在知道"干什么"的同时就知道"输出前要验什么"，而不是生成完再回头检查

**自检/反思设计原则（v2 核心改进）**：

记录问题：`## 反思与自检` 放在 prompt 末尾、`selfCheck` 是布尔打勾（无证据链）、曾额外引入 `postcondition_check` LLM 调用。这三种方式都是**事后补救**，模型已经生成了不合格的输出，再回头检查为时已晚。

v2 方案：**预检（pre-check）嵌入 §3 task + 自检证据链嵌入 §4 output_contract**

```
§3 <task> 中的反思约束（模型生成前就看到）:
  ## 反思与自检（输出前必须验证）
  - 是否覆盖用户所有子问题？逐条对照
  - 每条关键结论是否有对应 evidence？若无则不得输出为确定性结论
  - 格式是否合规？标题/加粗/列表/追问区
  - 是否有编造数据？所有实时数据必须来自工具结果

§4 <output_contract> 中的 selfCheck 证据链要求:
  selfCheck.checks 数组中每条必须包含:
  - rule: 检查项名称
  - passed: boolean
  - evidence: 一句话说明为什么通过/不通过（引用具体字段或数据来源）
  若任何 check 不通过 → decision.nextAction 必须改为 ask_user 或 degrade
```

效果：模型在 ~300 token 处就知道"输出前要自检"，在 ~700 token 处知道"selfCheck 必须带证据链"。这比放在末尾的 `## 反思与自检` 有效得多——模型会在**生成过程中**就注意合规性。

---

### §4 阶段输出规范 `<output_contract>` — L2 阶段前缀

**旧问题**：单一 output contract 文件会被所有阶段共用，缺少 phase 边界。

**v2 设计**（紧跟 task，形成「任务-产出」认知闭环）：

模型在知道"干什么"后立即知道"输出什么格式"。按 phase 分化，仅加载当前阶段对应的契约。

#### phase=plan（规划阶段）

```markdown
<output_contract phase="plan">
输出纯 JSON，字段直接平铺（无 payload 嵌套）：
- `decision`：{nextAction, confidence, reasoning}
- `userMarkdown`：一行进度说明
- `slotFillPlan`：{slot: {from, value, confidence}}
- `searchPlans`：[{tool, query, depends}]
- `queryNormalization`（有 web_search 时）：{normalized, variants, inputIssues}
- `askUser` / `missingContextSlots`：追问目标槽位与缺失上下文（有缺失时）
- `selfCheck`：{passed, checks[{rule, ok, evidence}]}

selfCheck 必须验证：
- slots_covered + query_plan_valid

selfCheck.passed=false → nextAction 必须改为 ask_user。
禁止自然语言包裹。
</output_contract>
```

#### phase=answer（回答阶段）

```markdown
<output_contract phase="answer">
输出 JSON，`userMarkdown` 字段为面向用户的 Markdown：

**结构规则**
- 第一行必须是 `## {领域 emoji} {简明标题}`（标题 ≤16 字）
- 关键数值用 `**加粗**` + 正确单位（¥/°C/%/km 等）
- 多项并列用 `-` 无序列表；有序步骤用 `1.` 有序列表
- 风险/免责放 `> 引用块`
- 每条列表项 ≤30 字，超长拆子列表
- 结尾必须有 `---` + `💬 **你可能还想了解**`（2-4 条启发式追问）

**数值格式标准**
| 类型 | 正确格式 | 错误格式 |
|------|---------|---------|
| 温度 | `**25°C**` | "25度" |
| 人民币 | `**¥1,299**` | "1299元" |
| 涨跌幅 | `▲ **+3.5%**` / `▼ **-1.2%**` | "+3.5%" |
| 评分 | `★★★★☆` | "4星" |

**亲和性要求**
- 情绪信号优先共情，再给信息
- 结论必须出现在前三行
- 每次回复至少 1 条可立即执行的建议

**禁止**
- userMarkdown 中出现任何 JSON 字段名
- 纯散文、无标题、无结构的回复
- 暴露内部状态/版本号/工具名

selfCheck 必须验证（每条带 evidence）：
- slots_covered / evidence_sufficient / format_compliant / safety_cleared / no_hallucination

selfCheck.passed=false → nextAction 改为 degrade。
</output_contract>
```

#### phase=ask_user（追问阶段）

```markdown
<output_contract phase="ask_user">
输出 JSON，`userMarkdown` 字段为面向用户的追问：

- 第一行说明为什么需要追问（1 句话）
- 追问内容明确、选项化（如"请问您想查的是 A 还是 B？"）
- 每轮最多追问 1 个关键槽位
- 禁止笼统追问（如"请提供更多信息"）
</output_contract>
```

**实现方式**：不需要创建 3 个物理文件，而是在 `_resolvePlannerPrompt` 中根据 `templateId` 判断当前阶段，选择性加载对应的输出契约段。

---

### §5 人设风格 `<persona>` — L3 技能前缀

**当前**：`global_policy` 全英文 + skill.policy.md 的角色/语气被混入 `mergedInstruction` 大文本块。

**v2 设计**（在 task + output_contract 之后，模型已有任务框架，persona 作为执行风格补充）：
```markdown
<persona>
## 全局语气基线
- 专业、温暖、直接；避免过度正式或过度随意
- 结论先行：最重要的结论出现在前三行
- 结构优先：用标题、列表、表格组织信息，避免大段散文

## 语言规则
- 中文输入 → 中文回复
- 英文输入 → 英文回复
- 拼音输入 → 识别语义后以中文回复
- 检索允许双语并行，但回复保持单一语言

## emoji 规范
- 标题 emoji：每域 1 个专属 emoji（见技能定义）
- 列表功能性 emoji：✅ ⚠️ 💡 📍 📅 等，行首使用，辅助视觉扫描
- 每行不超过 2 个 emoji；连续 3 行不得都有 emoji
- 情感类 emoji（🌸💙🤗🫂）仅限情感陪伴/社交闲聊技能

## 当前技能人设覆盖
{{skillPersona}}
</persona>
```

**为什么 persona 在 task 之后而非之前**：
- 模型先知道"这轮做规划"比先知道"语气要温暖"更重要
- persona 是执行风格修饰，不是核心任务定义
- 放在 L3 层，同技能多轮对话可缓存

**处理逻辑变更**：
```
现有 skill.policy.md 结构：
  ## 角色定位     ──→ 提取为 skillPersona，注入 §5 <persona>
  ## 语气要求     ──→ 提取为 skillPersona，注入 §5 <persona>
  ## 语言策略     ──→ 提取为 skillPersona，注入 §5 <persona>
  ## 领域边界     ──→ 保留在 §6 <domain_skill> 中
  ## 必须包含章节  ──→ 保留在 §6 <domain_skill> 中
```

**具体实现**：skill.policy.md 拆为两个逻辑段 —— persona 段（角色+语气+语言）和 constraint 段（边界+章节），分别注入不同区块。拆分通过加载时解析 `## ` 标题实现，不需要物理拆分文件。

---

### §6 垂类技能体 `<domain_skill>` — L3 技能前缀

**当前**：`mergedInstruction` 将 globalPolicy + SKILL.md body + skillPolicy 用 `---` 拼接。

**v2 设计**（独立 system 消息，结构化容器）：

```markdown
<domain_skill id="{{domainId}}" name="{{skillName}}">

## 技能目标与工作方式
{{skillInstructionBody}}

## 领域约束与边界
{{skillConstraints}}

## 领域知识背景
{{domainKnowledge}}

## 工具调用指引（规划阶段可见）
{{toolCallGuidance}}

## 输出示例（回答阶段可见）
{{outputExamples}}

</domain_skill>
```

**phase-aware 加载规则**：

| 子区块 | 规划阶段 | 回答阶段 | 追问阶段 |
|--------|---------|---------|---------|
| 技能目标与工作方式（SKILL.md body） | ✅ 加载 | ✅ 加载 | ✅ 加载 |
| 领域约束与边界（policy 的边界+章节段） | ✅ 加载 | ✅ 加载 | ✅ 加载 |
| 领域知识背景（domain-knowledge.md） | ✅ 加载 | ✅ 加载 | ❌ 不加载 |
| 工具调用指引（tool-call-guidance.md） | ✅ 加载 | ❌ 不加载 | ❌ 不加载 |
| 输出示例（output-examples.md） | ❌ 不加载 | ✅ 加载 | ❌ 不加载 |

---

### §6b 工具使用规则 `<tool_policy>` — L3 技能前缀

**当前**：`runtime_policy` 中的 2 行 + 工具列表通过变量注入。

**v2 设计**（紧跟 domain_skill，同属 L3 技能前缀）：
```markdown
<tool_policy>
## 可用工具
{{availableToolNames}}

## 调用原则
- 隐私最小化：仅在用户问题确实需要外部数据时调用工具
- 精算预算：工具失败允许重试 1 次，随后进入降级回答
- 禁止无效调用：工具结果与问题无关时立即停止后续调用
- 渐进策略：先补关键槽位，再执行联网查询

## 工具调用规范
{{toolInvocationGuidelines}}
</tool_policy>
```

**为什么 tool_policy 在 L3 而非 L2**：
- 可用工具列表和调用规范因技能不同而不同（天气用 web_search，占卜可能不用工具）
- 放在 L3 层，与 persona + skill 一起，同技能多轮可缓存
- 模型在 §3 task 中已知"先补槽位再查询"的大策略，§6b 只是具体工具规范

---

### §7 对话状态 `<dialogue_state>` — L4 数据层

**当前**：JSON 格式的 `DialogueRoundScript`，作为独立 system 消息，用 `jsonEncode` 注入。

**v2 设计**（语义化 Markdown，属于 MESSAGE 2 数据层）：

```markdown
<dialogue_state domain="{{domainId}}" turn="{{turnIndex}}">
## 当前状态
- 状态: {{currentStateId}}
- 已就绪槽位: {{readySlotsSummary}}
- 待填充槽位: {{missingSlotsSummary}}

## 本轮检测事件
- 检测到的事件: {{detectedEvent}}
- 建议下一状态: {{suggestedNextStateId}}
- 下一状态候选: {{nextStateCandidates}}

## 当前状态执行指引
{{statePromptExcerpt}}

## 约束
- 本轮最多追问 {{maxQuestionsPerTurn}} 个问题
- 待填充槽位必须先补齐，再给出最终回答
{{additionalConstraints}}
</dialogue_state>
```

**改进点**：
- 从 JSON 改为 Markdown → 模型解析效率更高
- 属于 MESSAGE 2 数据层 → 与 context_slots 一起，纯数据，紧贴 user 消息
- 显式输出 ready/missing 槽位摘要 → 模型无需计算

---

### §8 结构化上下文 `<context_slots>` — L4 数据层

**当前**：`contextEnvelope` 是嵌套 JSON 对象（~500 token），注入为独立 system 消息。

**v2 设计**（语义分组 Markdown）：

```markdown
<context_slots>
## 📍 位置信息
- 当前城市: {{city}}（来源: {{citySource}}，置信度: {{cityConfidence}}）
- GPS: {{gpsLat}}, {{gpsLng}}（精度: {{locationPrecision}}，更新: {{locationTimestamp}}）

## 📅 时间信息
- 设备本地时间: {{deviceLocalTime}}
- 时区: {{timezone}}

## 👤 用户画像
- 沟通风格: {{communicationStyle}}
- 高频使用域: {{topDomains}}
- 兴趣标签: {{interestTags}}

## 🗂 对话记忆
- 会话摘要: {{historySummarySnippet}}
- 最近提及城市: {{recentCityMentions}}
- 记录检索反馈: {{historicalRetrievalFeedback}}

## 📱 设备信息
- 设备: {{deviceModel}}（{{deviceOs}}）
- 渠道: {{deviceProfile}}

## 🧠 槽位补全信号
{{slotFillHints}}
</context_slots>
```

**改进点**：
- 按语义分组而非按数据来源 → 模型按需扫描
- 每个值有来源+置信度标注 → 模型可评估可信度
- Markdown 格式而非 JSON → 减少解析开销
- 保留 `slotFillHints` 作为一个聚合信号区（原有功能不丢失）

**实现方式**：在 `context_orchestrator.dart` 的 `assemble()` 方法中新增 `toPromptMarkdown()` 方法，输出语义化 Markdown。

---

### §9 对话记录

**保持不变**：`user` / `assistant` 消息交替传入。

**优化建议**：
- 记录消息压缩（已有 `summarize_session`）：超过 5 轮时自动触发
- 工具调用记录不显示原始 JSON，仅保留摘要

---

## 五、模型返回结构 v2

### 5.0 设计原则——模型输出 vs 引擎注入

JSON 结构中的字段必须分清两类：

| 类别 | 谁生成 | 原则 | 示例 |
|------|--------|------|------|
| **模型输出** | LLM 推理生成 | 只包含模型能推理的字段，零冗余 | decision, userMarkdown, selfCheck |
| **引擎注入** | phase owner / react_runtime 在收到模型输出后补入 | 模型不可能知道的运行时元数据 | domainId, stateId, promptTokens, latencyMs |

**删除的字段及原因**：

| 删除字段 | 原因 |
|---------|------|
| `contractId` | 常量，模型每次输出同一串字符浪费 token。引擎在收到响应后自动补入 |
| `phase` | 与 `decision.nextAction` 语义重复。引擎从 nextAction 推导 |
| `diagnostics.stateId` | 引擎从 `DialogueStateRuntime` 已知，模型无法准确生成 |
| `diagnostics.detectedEvent` | 同上，状态机事件由引擎检测 |
| `diagnostics.phaseAwareLoaded` | 引擎侧加载逻辑，模型完全不知道加载了哪些 .md 文件 |
| `diagnostics.promptTokenEstimate` | 引擎计算 |
| `diagnostics.latencyHintMs` | 引擎测量 |
| `payload` 包裹层 | 不同阶段的字段直接平铺到顶层，`nextAction` 已区分阶段，不需要额外嵌套 |

### 5.1 模型输出结构（扁平化，零冗余）

模型只输出以下字段，按 `nextAction` 不同，部分字段可选：

```json
{
  "decision": {
    "nextAction": "tool_call",
    "confidence": 0.92,
    "reasoning": "城市已识别，需查询实时天气"
  },

  "userMarkdown": "正在查询深圳实时天气…",

  "slotFillPlan": {
    "city": { "from": "user_query", "value": "深圳", "confidence": 0.9 }
  },
  "searchPlans": [
    { "tool": "web_search", "query": "深圳 实时天气 2026年3月5日", "depends": [] }
  ],
  "queryNormalization": {
    "normalized": "深圳实时天气",
    "variants": ["深圳天气预报", "shenzhen weather today"],
    "inputIssues": []
  },

  "missingContextSlots": [],
  "result": null,
  "evidence": [],
  "reasoningBasis": [],

  "selfCheck": {
    "passed": true,
    "checks": [
      { "rule": "slots_covered", "ok": true, "evidence": "city=深圳(0.9)" },
      { "rule": "query_plan_valid", "ok": true, "evidence": "1 条 web_search 任务" }
    ]
  }
}
```

**字段说明（按 nextAction 的存在性）**：

| 字段 | tool_call | answer | ask_user | degrade | 类型 |
|------|:---------:|:------:|:--------:|:-------:|------|
| `decision` | 必须 | 必须 | 必须 | 必须 | `{nextAction, confidence, reasoning}` |
| `userMarkdown` | 一行进度 | 完整 Markdown | 追问文案 | 降级说明 | string |
| `slotFillPlan` | 必须 | — | — | — | `{slot: {from, value, confidence}}` |
| `searchPlans` | 必须 | — | — | — | `[{tool, query, depends}]` |
| `queryNormalization` | 有 web_search 时 | — | — | — | `{normalized, variants, inputIssues}` |
| `askUser` / `missingContextSlots` | — | — | 必须 | — | `{slotId, prompt}` + `string[]` |
| `result` | — | 必须 | — | — | string（综合结论） |
| `evidence` | — | 必须 | — | — | `[{source, text, quality}]` |
| `reasoningBasis` | — | 必须 | — | — | `[{text, source, confidence}]` |
| `selfCheck` | 必须 | 必须 | — | — | `{passed, checks[{rule, ok, evidence}]}` |

**关键优化**：
- **无 `payload` 嵌套**——字段直接平铺，模型不需要想"我在哪个 phase，要放到 payload 下面"
- **无 `contractId`**——常量由引擎补入
- **无 `diagnostics`**——全部由引擎注入，模型不输出
- **selfCheck.checks 简化**——`ok` 替代 `passed`（省 3 字符 × N 条），`evidence` 一句话
- **字段名语义统一**——`slotFillPlan.city.from` 而非 `detectedFrom`（更短更直观）

### 5.2 引擎注入结构（模型输出后补入）

引擎在收到模型 JSON 后，包装为完整的运行时信封：

```json
{
  "_meta": {
    "contractId": "assistant_turn",
    "domainId": "weather",
    "stateId": "S2_天气检索",
    "detectedEvent": "E_城市已就绪",
    "phaseAwareLoaded": ["domain-knowledge.md", "tool-call-guidance.md"],
    "promptTokens": 1840,
    "completionTokens": 320,
    "latencyMs": 340,
    "modelId": "claude-sonnet-4-20250514",
    "timestamp": "2026-03-05T14:25:03Z"
  },

  ... 模型输出的所有字段原样保留 ...
}
```

`_meta` 前缀下划线表示"非模型产出"，便于代码中区分。

**关于 stateId 和 detectedEvent**：
- `S2_天气检索`：S 前缀 = State，由 `dialogue/state_transition_contract.json` 定义，引擎通过 `DialogueStateRuntime.buildRoundScript()` 计算
- `E_城市已就绪`：E 前缀 = Event，同样由引擎状态机检测
- 这两个值注入到 prompt 的 §7 `<dialogue_state>` 中供模型参考，但模型**不需要在响应中回显它们**
- 引擎在组装最终 response 时，从 `dialogueRoundScript` 中取出并写入 `_meta`

**关于 phaseAwareLoaded**：
- 由 phase owner 的 reference loader 决定加载哪些 references
- 加载逻辑基于 `dialogueRoundScript.requiredFieldsForNextState.isNotEmpty`
- 模型完全不知道这个信息——它只看到加载后的内容（已注入 §6 `<domain_skill>`）
- 引擎在组装 response 时记录到 `_meta` 用于可观测性

### 5.3 与现有契约的兼容性

| 现有字段 | v2 变更 | 说明 |
|---------|---------|------|
| `contractId` | 移入 `_meta`（引擎注入） | 模型不再输出，省 token |
| `phase` | 删除 | 从 `decision.nextAction` 推导 |
| `decision.nextAction` | 保持 | 无变化 |
| `userMarkdown` | 保持 | 无变化 |
| `payload.*` | 平铺到顶层 | `payload.slotFillPlan` → `slotFillPlan` |
| `result` | 平铺到顶层 | `payload.result` → `result` |
| `evidence` | 保持 | 结构从对象改为数组 |
| `reasoningBasis` | 保持 | 结构从字符串改为数组 |
| `selfCheck` | 增强 | `checks[].evidence` 证据链 |
| `diagnostics` | 移入 `_meta`（引擎注入） | 模型不再输出 |

**迁移策略**：引擎 `_parseAnswerPayload` 同时兼容 v3（当前）和 v4（新），通过检查顶层是否有 `payload` 字段判断版本

---

## 六、模板处理逻辑变更设计

### 6.1 消息组装流程（phase owner 重构）

```
当前（7+ system messages，指令分散）:
  LLM provider prepend:
    system: identity + safety + persona + tool_policy + phaseContract + stagePrompt
  旧单文件 owner insert(0,...) × 6:
    system: "状态机脚本 JSON"
    system: "上下文锚点"
    system: "能力目录"
    system: "记忆检索"
    system: "会话摘要"
    system: "上下文组装 JSON"
  问题：模型在 7 条 system 消息中找指令，task 定义在 stagePrompt（最后拼入主 system），
        数据散布在 6 条独立消息中，指令-数据完全混合。

v2（2 system messages + history，指令优先序）:
  MESSAGE 1（指令层）: §1 identity → §2 safety → §3 task → §4 output_contract → §5 persona → §6 skill + §6b tool_policy
  MESSAGE 2（数据层）: §7 dialogue_state → §8 context_slots（含记忆/画像/位置/能力目录）
  MESSAGE 3+: 对话记录（user/assistant 交替）
```

### 6.2 `_resolvePlannerPrompt` 重构（指令优先序）

```
当前:
  appendLayer('stack.identity')               // ~80 token，身份
  appendLayer('stack.safety')                 // ~120 token，边界
  appendLayer('stack.persona')                // ~100 token，人格
  appendLayer('stack.tool_policy')            // ~80 token，工具规则
  appendPhaseContract(phase)                  // ~200 token，按阶段加载
  + stagePrompt                              // ~400 token，任务定义 ← 问题：最重要的内容在最后

v2（重排序）:
  ── L1 固定前缀（所有请求共享，缓存命中率最高）──
  appendLayer('stack.identity')               // §1 ~80 token，我是谁
  appendLayer('stack.safety')                 // §2 ~120 token，底线
  ── L2 阶段前缀（同阶段共享）──
  + stagePrompt                              // §3 ~400 token，★ 任务定义提前到第 3 位！
  appendPhaseContract(phase)                  // §4 ~200 token，本阶段输出规范
  ── L3 技能前缀（同技能共享）──
  appendLayer('stack.persona')                // §5 ~100 token，含 {{skillPersona}}
  appendDomainSkill(...)                      // §6 ~200 token，skill 指令 + phase-aware references
  appendLayer('stack.tool_policy')            // §6b ~80 token，工具规则
```

关键变化：
- stagePrompt（任务定义）从**最后一层**提前到**第 3 层**
- 模型在 ~250 token 处就知道"这轮要做规划/回答"
- identity + safety 固定不变，是 L1 缓存前缀
- task + output_contract 同阶段不变，是 L2 缓存前缀

### 6.3 skill.policy.md 拆分加载

```dart
/// 从 skill.policy.md 中解析出 persona 段和 constraint 段
({String persona, String constraints}) _splitSkillPolicy(String policyMarkdown) {
  // persona 段 = ## 角色定位 + ## 语气要求 + ## 语言策略
  // constraint 段 = ## 领域边界 + ## 必须包含的章节
  // 按 ## 标题切分，归类到对应段
}
```

### 6.4 context_orchestrator 输出格式变更

```dart
/// 新增：输出语义化 Markdown 格式的上下文
String toPromptMarkdown(ContextAssemblyResult assembly) {
  // 按 §8 模板输出 <context_slots>...</context_slots>
}
```

### 6.5 模板变量预处理增强

当前 `_stringify()` 对 Map/List 直接 `.toString()`，导致 JSON 类型在 Markdown 模板中不可读。

```dart
/// v2: 智能序列化，Map/List 输出为 Markdown 列表或表格
String _smartStringify(dynamic value, {String indent = ''}) {
  if (value is Map) {
    return value.entries
        .map((e) => '$indent- ${e.key}: ${_smartStringify(e.value)}')
        .join('\n');
  }
  if (value is List) {
    if (value.isEmpty) return '（无）';
    return value.map((e) => '$indent- ${_smartStringify(e)}').join('\n');
  }
  return value?.toString() ?? '';
}
```

---

## 七、文件变更清单

### 7.1 新增/重写的模板文件

| 文件 | 动作 | 说明 |
|------|------|------|
| `prompts/global/stack.identity.md` | **新建** | §1 身份宣言（L1 固定前缀） |
| `prompts/global/stack.safety.md` | **新建** | §2 合并安全+恢复（L1 固定前缀） |
| `prompts/global/phase.output_contract.plan.md` | **新建** | §4 规划阶段输出规范（L2 阶段前缀） |
| `prompts/global/phase.output_contract.answer.md` | **新建** | §4 回答阶段输出规范（L2 阶段前缀） |
| `prompts/global/stack.persona.md` | **新建** | §5 人设风格基线 + `{{skillPersona}}`（L3 技能前缀） |
| `prompts/global/stack.tool_policy.md` | **新建** | §6b 工具使用规则（L3 技能前缀） |

### 7.2 模板文件处置

| 文件 | 动作 | 说明 |
|------|------|------|
| `planner.global_plan.md` | **重写** | 去掉 `{{domainSkillInstruction}}`，上下文变量改用 Markdown 格式 |
| `synthesizer.final_answer.md` | **重写** | 去掉内联格式规范（移入 phase contract），精简 |
| `synthesizer.multi_skill_fusion.md` | **下线** | 多技能融合并回 answer 合成链路，不再使用独立模板 |
| `planner.postcondition_check.md` | **下线** | postcondition 校验不再使用独立模板 |
| `summarize_session.md` | **保留** | 无需修改 |

### 7.3 废弃的模板文件

| 文件 | 说明 |
|------|------|
| `stack.identity.md` | 身份与使命基线 |
| `stack.safety.md` | 安全、降级与危机边界 |
| `stack.persona.md` | 全局人格与语气基线 |
| `stack.tool_policy.md` | 工具权限、执行规则与预算约束 |
| `phase.output_contract.*.md` | 按阶段拆分的输出契约 |

### 7.4 代码变更

| 文件 | 变更 |
|------|------|
| `llm_provider.dart` | `_resolvePlannerPrompt()` 重构：**L1(identity→safety) → L2(stagePrompt→phaseContract) → L3(persona→skill→tool_policy)**，增加 phase 参数 |
| `local_phase_execution_owner.dart` | 消息注入从 6+ system messages 合并为 **2 条**（指令层+数据层） |
| `local_phase_execution_owner.dart` | 旧 `insert(0,...)` 注入合并为结构化 data message，输出 `<dialogue_state>` + `<context_slots>` |
| `local_phase_execution_owner.dart` | `_mergeSkillInstructions` 输出 `<domain_skill>` XML 容器，persona 段独立注入 `<persona>` |
| `context_orchestrator.dart` | 新增 `toPromptMarkdown()` 方法，输出语义化 Markdown 替代 JSON blob |
| `template_renderer.dart` | `_stringify()` 升级为 `_smartStringify()`，Map/List 输出可读 Markdown |
| `template_validator.dart` | 新增 stack.identity / stack.safety / stack.persona / stack.tool_policy 的验证规则 |

---

## 八、完整消息示例（天气查询 · 规划阶段）

用户输入"深圳天气怎么样"时，模型收到的完整消息序列（按指令优先序）：

### MESSAGE 1: 指令层（§1 → §6b，全部「怎么做」）

```
═══ L1 固定前缀（所有请求共享，~200 token）═══

<identity>
你是「沃助理」——趣我圈商用级智能个人助理。

## 核心使命
帮助用户做出更好的决策、节省时间、解决实际问题。

## 基本信念
- 诚实：不编造事实，证据不足时坦诚说明
- 精准：直击用户真实需求，不绕弯子
- 安全：任何回复不得造成用户真实损害
- 尊重：全程尊重用户意图、语言风格与文化背景
</identity>

<safety>
## 硬性禁止
- 禁止编造实时数据（天气/金融/医疗/交通）
- 禁止向用户暴露内部字段名、JSON 结构、工具调用链
- 禁止输出引发隐私恐慌的能力宣示文案

## 降级协议
- 工具调用失败：说明限制 + 可重试一次，再失败则降级回答
- 证据质量低：诚实降级 + 提供官方信源路径

## 危机识别
- 检测到危机信号：提供安全热线（400-161-9995），停止信息性回复
</safety>

═══ L2 阶段前缀（同阶段共享，~400 token）═══
═══ ★ 模型在此处（~250 token）已知这轮要做什么 ═══

<task>
## 任务背景
你是商用级个人助理总控规划器，需要把用户问题拆解为可执行的垂类任务图。

## 任务目标
1. 路由到 19 垂类中的一个或多个域
2. 给出串并行执行计划
3. 对缺失上下文生成补齐任务
4. 为后续答案阶段准备证据和诊断信息

## 约束
- 查询必须单主题，跨主题问题必须拆分任务
- 不得伪造证据；证据不足时必须触发补查
- 高风险垂类必须带安全边界与免责声明

## 执行要求
- 输出 JSON，禁止自然语言包裹
- 必须输出 slotFillPlan / searchPlans / contextSlots
- 先补关键槽位，再执行联网查询

## 槽位自动补全（Layer 0）
...（slotFillPlan 规则，同现有 planner.global_plan.md）

## 查询规范化（Layer 1）
...（queryNormalization 规则）

## 反思与自检
- 是否覆盖用户所有子问题？
- slotFillPlan 是否完整？
- 有 web_search 时 queryNormalization 是否已输出？
</task>

<output_contract phase="plan">
输出纯 JSON，结构必须包含：
- decision（含 nextAction: tool_call / answer / ask_user）
- slotFillPlan（每个槽位的来源/值/策略）
- searchPlans（查询任务列表，含依赖关系和停止条件）
- queryNormalization（有 web_search 时必须：normalizedQuery + queryVariants + inputIssues）
- subagentPlan（跨域时：副技能子任务声明，含 domainId）

当 nextAction=tool_call 时：
- userMarkdown 仅需一行进度说明（如"正在查询深圳实时天气…"）

禁止自然语言包裹，禁止 Markdown 格式。
</output_contract>

═══ L3 技能前缀（同技能共享，~300 token）═══

<persona>
## 全局语气基线
- 专业、温暖、直接
- 结论先行，结构优先
- 中文输入→中文回复；英文→英文；拼音→识别语义后中文回复

## 当前技能人设
你是一位专业天气助理，以精准、平静、实用为核心。
语气要求：专业清晰，关键指标优先呈现，结构简洁。
</persona>

<domain_skill id="weather" name="天气查询">

## 技能目标与工作方式
（SKILL.md body 内容）

## 领域约束与边界
- 禁止编造实时天气数据
- 实时证据缺失时须说明不确定性并给出重试/官方来源路径
- 必须包含：当前状况摘要、关键指标、实用出行建议、免责声明、追问建议

## 领域知识背景
（references/domain-knowledge.md 内容 —— 始终加载）

## 工具调用指引
（references/tool-call-guidance.md 内容 —— 仅规划阶段可见）

</domain_skill>

<tool_policy>
## 可用工具
web_search

## 调用原则
- 隐私最小化：仅在需要外部数据时调用
- 工具失败允许重试 1 次，随后降级回答
</tool_policy>
```

### MESSAGE 2: 数据层（§7-§8，全部「基于什么做」，紧贴 user 消息）

```
<dialogue_state domain="weather">
## 当前状态
- 状态: S1_城市补全
- 已就绪槽位: city=深圳（来源: user_query，置信度 0.9）
- 待填充槽位: 无

## 本轮检测事件
- 检测到的事件: E_城市已就绪
- 建议下一状态: S2_天气检索

## 当前状态执行指引
城市已确认，执行天气数据检索...

## 约束
- 本轮最多追问 1 个问题
</dialogue_state>

<context_slots>
## 📍 位置信息
- 当前城市: 深圳（来源: user_query，置信度: high）
- GPS: 22.5431, 114.0579（精度: high，更新: 2026-03-05T14:20:00）

## 📅 时间信息
- 设备本地时间: 2026-03-05 14:25
- 时区: Asia/Shanghai

## 👤 用户画像
- 沟通风格: prefer_concise
- 高频使用域: weather, travel_planning

## 🗂 对话记忆
- 会话摘要: （无，首轮对话）
- 最近提及城市: 深圳

## 📱 设备信息
- 设备: iPhone 15 Pro（iOS 19.1）
- 渠道: mobile

## 🧠 槽位补全信号
- gpsCity: 深圳（置信度: high）
- ruleExtractedCity: 深圳
- historySummarySnippet: （空）
</context_slots>
```

### MESSAGE 3: User

```
深圳天气怎么样
```

### 模型认知路径复盘

```
token    0-80:   "我是沃助理，信念=诚实/精准/安全/尊重"    ← 身份锚定
token   80-200:  "禁止编造实时数据，危机提供热线"           ← 底线加载
token  200-600:  ★ "你是总控规划器，拆解任务、补齐槽位"     ← 核心！知道干什么了
token  600-800:  "输出 JSON，含 slotFillPlan/searchPlans"   ← 知道输出什么格式
token  800-900:  "你是天气助理，专业清晰"                   ← 知道用什么风格
token  900-1100: "天气技能指令 + 工具调用指引"               ← 具体怎么做
token 1100-1300: "状态=S1，city=深圳，GPS=22.5..."          ← 数据（紧贴 user）
token     1300+: "深圳天气怎么样"                           ← user 消息

指令区（§1-§6b）= token 0-1100，纯指令，无数据干扰
数据区（§7-§8）  = token 1100-1300，纯数据，紧贴 user 消息
```

---

## 九、实施路线图（开发任务清单）

> 以下为 `/try` 命令进入开发阶段的完整任务分解。每个任务标注 ID，便于追踪。

### 阶段一：模板文件新建（不改代码逻辑）

| ID | 任务 | 工时 | 输入 | 产出 | 验收标准 |
|----|------|------|------|------|----------|
| T1.1 | 新建 `stack.identity.md` | 0.5h | 既有身份/安全模板 | §1 身份宣言 | 含命名「沃助理」、使命、信念 4 条 |
| T1.2 | 新建 `stack.safety.md` | 0.5h | 既有安全/恢复模板 | §2 安全边界 | 含硬性禁止 4 条 + 降级协议 3 条 + 危机识别 |
| T1.3 | 新建 `stack.persona.md` | 0.5h | 既有人格/语气模板 | §5 人设风格 + `{{skillPersona}}` 占位符 | 含语气基线 + 语言规则 + emoji 规范 |
| T1.4 | 新建 `stack.tool_policy.md` | 0.3h | 既有工具策略模板 | §6b 工具规则 + `{{availableToolNames}}` | 含调用原则 4 条 |
| T1.5 | 新建 `phase.output_contract.plan.md` | 0.5h | `output_contract` + 本文档 §4 设计 | plan 阶段输出规范 | 含 selfCheck 证据链要求（slots_covered + query_plan_valid）|
| T1.6 | 新建 `phase.output_contract.answer.md` | 0.5h | `output_contract` + `synthesizer.final_answer` 格式段 | answer 阶段输出规范 | 含 selfCheck 证据链要求（5 条 check rule + evidence）|
| T1.7 | 重写 `planner.global_plan.md` | 1h | 现有文件 + §3 task 设计 | task 模板（去掉 `{{domainSkillInstruction}}`） | 含反思与自检嵌入任务定义（非末尾） |
| T1.8 | 精简 `synthesizer.final_answer.md` | 0.5h | 现有文件 | 去掉内联格式规范（移入 phase contract） | 格式规范零重复 |
| T1.9 | 19 个 SKILL.md 正文路径修正 | 0.5h | 全部 SKILL.md | `scripts/tool-call-guidance` → `references/tool-call-guidance` | `grep scripts/tool-call-guidance` 返回 0 |

### 阶段二：Prompt 组装重构（改代码）

| ID | 任务 | 工时 | 改动文件 | 关键变更 | 验收标准 |
|----|------|------|----------|----------|----------|
| T2.1 | `_resolvePlannerPrompt` 指令优先序 | 2h | `llm_provider.dart` | appendLayer 序列改为 identity → safety → stagePrompt → phaseContract → persona → skill → toolPolicy | 单测：system prompt 中 task 出现在 identity 和 safety 之后 |
| T2.2 | 消息注入合并为 2 条 | 2h | `local_phase_execution_owner.dart` | 旧 6 个 `insert(0,...)` → 结构化 data message，输出 `<dialogue_state>` + `<context_slots>` | messages 数组中 system 消息 ≤ 2 条 |
| T2.3 | skill.policy.md 拆分加载 | 1h | `local_phase_execution_owner.dart` | `_splitSkillPolicy()` 按 `## ` 标题分 persona/constraint 两段 | persona 段注入 §5，constraint 段留 §6 |
| T2.4 | `toPromptMarkdown()` | 1h | `context_orchestrator.dart` | 新方法：contextEnvelope → `<context_slots>` 语义 Markdown | 输出含 📍📅👤🗂📱🧠 分区 |
| T2.5 | `<domain_skill>` XML 容器 | 0.5h | `local_phase_execution_owner.dart` | `_mergeSkillInstructions` 输出带 `<domain_skill id="...">` 包裹 | XML 结构正确 |
| T2.6 | `<dialogue_state>` Markdown 化 | 1h | `local_phase_execution_owner.dart` | JSON → 结构化 Markdown + `<dialogue_state>` 容器 | 无 jsonEncode 注入 |
| T2.7 | selfCheck 证据链引擎校验 | 1h | `local_phase_execution_owner.dart` | `_mergeSelfCheck` 增加 evidence 字段处理，缺 evidence 时标记 warn | diagnostics 中可见 selfCheck 质量 |

### 阶段三：SSE 事件协议（根治解析 + 流式）

| ID | 任务 | 工时 | 改动文件 | 关键变更 | 验收标准 |
|----|------|------|----------|----------|----------|
| T3.1 | 定义 `AssistantStreamEvent` v2 | 1h | 新建 `protocol/stream_events.dart` | 12 种事件类型 + 数据结构 | 类型定义通过 analyze |
| T3.2 | phase owner emit 过程事件 | 2h | `local_phase_execution_owner.dart` | 在规划/搜索/合成节点 emit 类型化事件 | trace 日志可见各阶段事件 |
| T3.3 | react_runtime emit 搜索事件 | 1h | `react_runtime.dart` | toolStart → `searchStarted`，toolResult → `searchCompleted` | 事件包含 resultCount + coverage |
| T3.4 | synthesizer 输出格式重构 | 1h | `phase.output_contract.answer.md` + `llm_provider.dart` | JSON 保留稳态语义 + 运行时事件流式 | 流式文本不再依赖 JSON 内嵌字段 |
| T3.5 | `reasonStream.onDelta` → `answerDelta` | 1h | `local_phase_execution_owner.dart` | `onDelta: (_) {}` → emit answerDelta | 真实流式 token 传到 UI |
| T3.6 | stream entry 适配 | 1h | `local_assistant_entry.dart` / `remote_assistant_entry.dart` | 删除旧 chunk 文本推断逻辑 | 无伪流式代码 |
| T3.7 | chat_detail_page 事件路由 | 2h | `chat_detail_page.dart` | switch-case 替换启发式过滤 | 删除 `_looksLikeJsonEnvelope` + `contains("contractId")` |
| T3.8 | 统一 JSON 解析器 | 1.5h | 新建 `engine/llm_response_parser.dart` | `LlmResponseParser.parse()` 统一入口 | 13 个分散点 → 1 个统一入口 |
| T3.9 | 清除分散解析点 | 1.5h | 6 个文件 | 替换为 `LlmResponseParser.parse()` | UI 层 0 个 jsonDecode 调用 |

### 阶段四：优化增强 + 测试

| ID | 任务 | 工时 | 改动文件 | 关键变更 | 验收标准 |
|----|------|------|----------|----------|----------|
| T4.1 | `_smartStringify()` | 1h | `template_renderer.dart` | Map/List → 可读 Markdown | 嵌套 Map 输出为层级列表 |
| T4.2 | Prompt Cache 标记 | 1h | `llm_provider.dart` | L1 固定前缀识别 + cache_control 参数 | Anthropic API 缓存生效 |
| T4.3 | 模板验证器更新 | 0.5h | `template_validator.dart` | 注册 stack.identity / safety / persona / tool_policy | validate 通过 |
| T4.4 | 契约测试适配 | 2h | 测试文件 | 更新断言匹配新结构 | `flutter test` 全绿 |
| T4.5 | E2E 冒烟测试 | 1h | 手动 | 天气/占卜/购物 3 个域端到端验证 | 流式显示 + selfCheck 有 evidence |

### 总计

| 阶段 | 工时 | 核心价值 |
|------|------|----------|
| 阶段一：模板文件 | 5h | 指令优先序 + 自检证据链 + 路径修正 |
| 阶段二：代码重构 | 8.5h | 7+ messages → 2 messages + JSON→Markdown |
| 阶段三：SSE 协议 | 12h | 根治解析 bug + 真实流式 + 13→1 解析点 |
| 阶段四：优化测试 | 5.5h | 缓存 + 验证 + 测试 |
| **合计** | **~31h** | **约 5 个工作日** |

### 实施依赖关系

```
阶段一（模板文件）——无依赖，可立即开始
    │
    ├── T1.1-T1.9 可并行
    │
    ▼
阶段二（代码重构）——依赖阶段一的模板文件
    │
    ├── T2.1 + T2.2 可并行
    ├── T2.3-T2.6 依赖 T2.1/T2.2
    │
    ▼
阶段三（SSE 协议）——依赖阶段二的消息合并
    │
    ├── T3.1 无依赖，可与阶段二并行
    ├── T3.2-T3.5 依赖 T3.1
    ├── T3.6-T3.7 依赖 T3.2
    ├── T3.8-T3.9 可与 T3.2-T3.7 并行
    │
    ▼
阶段四（优化测试）——依赖全部前序阶段
```

---

## 十、引擎 SSE 事件协议——根治响应解析与流式显示

### 10.0 问题根因分析

当前系统反复出现"响应解析错误"和"prompt 内容污染输出"，**根因不是某个 JSON 解析函数写得不好，而是整个协议设计的方向错了**：

```
当前架构（根因）：
  LLM → 单条 JSON blob（含 decision + userMarkdown + diagnostics + ...）
    → phase owner 拿到完整 JSON 后：
      → _decodeJsonObject() 用 3 种策略猜测 JSON 边界
      → _extractJsonCandidateBlocks() 用括号深度扫描
      → _tryDecodeMap() 逐块尝试解析
      → _guardSynthesisNextAction() 二次解析
      → _ensureAssistantTurnV2EnvelopeText() 三次解析
    → stream entry 拿到完整文本后：
      → _resolveChunkDisplayText() 提取 userMarkdown
      → _chunkText() 按句/24 字切分
      → 逐块 emit "伪流式" chunk
    → chat_detail_page 收到 chunk 后：
      → _looksLikeJsonEnvelope() 启发式过滤
      → contains('"contractId"') 字符串匹配
      → appendStreamingChunk() 拼接文本
    → completed 后：
      → _resolveAssistantDisplayText() 再次括号深度扫描
```

**这套链路的每一环都在"猜"**：猜 JSON 在哪里、猜哪段是 prompt 泄露、猜哪段是用户可见文本。每修一个 case 就引入新的边界条件，所以**反复修不好**。

**增量 JSON 解析（方案 A）和双轨输出（方案 B）同样不稳定**：
- 方案 A：半截 JSON 可能在 `"userMarkdown": "正在` 处断裂——无法确定何时提取、遇到转义引号怎么办、嵌套 Markdown 中的 `{}` 怎么处理。每种边界条件都是一个新 bug。
- 方案 B：模型不可靠地分离"先输出纯文本再输出 JSON"——混合输出、顺序反转、漏输出其中一轨，都会发生。

**根本解法是改变协议——让引擎（而非客户端）决定"这段内容是什么"，通过类型化 SSE 事件传递**。

### 10.1 业界参考

| 产品 | 事件协议 | 关键事件类型 |
|------|----------|-------------|
| OpenAI Assistants API | SSE | `thread.run.step.created`、`thread.message.delta`、`thread.run.requires_action` |
| Anthropic Messages | SSE | `content_block_start`、`content_block_delta`、`content_block_stop`、`message_delta` |
| Google Gemini | Streaming | Typed chunks with `finishReason`、`citationMetadata` |
| Cursor IDE | SSE | `thinking`、`code_edit`、`text`、`tool_call` 等分区域渲染 |

共同模式：**引擎知道自己在做什么，emit 类型化事件，客户端按事件类型路由到不同 UI 区块**。

### 10.2 v2 事件类型设计

```dart
enum AssistantStreamEventType {
  // ── 过程事件（process）──
  planStarted,        // 规划开始：引擎开始处理用户请求
  slotFilling,        // 槽位补全中：正在从上下文/GPS/记录中自动补齐
  searchQueryGenerated,// 搜索查询生成：展示规范化后的搜索词
  searchStarted,      // 搜索执行中：发起 web_search
  searchCompleted,    // 搜索完成：返回结果摘要（条数 + 置信度）
  replanning,         // 重新规划：证据不足/质量不够，需要补查
  synthesisStarted,   // 合成开始：所有证据就绪，开始生成答案

  // ── 内容事件（content）──
  answerDelta,        // 答案增量：userMarkdown 的纯文本 chunk（可直接渲染）
  progressText,       // 进度文案：plan 阶段的用户可见提示（如"正在查询深圳天气…"）

  // ── 终态事件（terminal）──
  completed,          // 完成：附带完整 structuredResponse（含 diagnostics）
  degraded,           // 降级完成：附带降级原因 + fallback 文本
}
```

### 10.3 事件数据结构

```dart
class AssistantStreamEvent {
  final AssistantStreamEventType type;
  final String? text;                    // answerDelta / progressText / searchQuery
  final Map<String, dynamic>? metadata;  // 可选诊断/上下文
  final AssistantRunResponse? response;  // 仅 completed/degraded 时

  // 工厂构造器（按事件类型）
  factory AssistantStreamEvent.planStarted({String? domainId, String? stateId});
  factory AssistantStreamEvent.slotFilling({required Map<String, dynamic> slotStatus});
  factory AssistantStreamEvent.searchQueryGenerated({required String query, List<String>? variants});
  factory AssistantStreamEvent.searchStarted({String? toolName});
  factory AssistantStreamEvent.searchCompleted({int? resultCount, double? coverage});
  factory AssistantStreamEvent.replanning({required String reason});
  factory AssistantStreamEvent.synthesisStarted();
  factory AssistantStreamEvent.answerDelta(String text);
  factory AssistantStreamEvent.progressText(String text);
  factory AssistantStreamEvent.completed(AssistantRunResponse response);
  factory AssistantStreamEvent.degraded(AssistantRunResponse response);
}
```

### 10.4 引擎侧 emit 点（phase owner + react_runtime）

```
phase_owner.runSingleRound():
  ├── emit(planStarted)                    ← 进入 _runSingleRound
  ├── _resolveSkillContext
  ├── _buildTemplateVariables
  ├── emit(slotFilling, slotStatus)        ← dialogueRoundScript 构建后
  │
  ├── react_runtime.run():
  │   ├── llm_provider.reason()            ← planner 调用
  │   ├── _parseToolCalls()
  │   ├── emit(searchQueryGenerated, q)    ← 解析出 queryNormalization 时
  │   ├── tool.execute()
  │   │   ├── emit(searchStarted)          ← web_search 开始
  │   │   └── emit(searchCompleted, n)     ← web_search 完成
  │   ├── 若 replan:
  │   │   └── emit(replanning, reason)
  │   └── 若 answer:
  │       ├── emit(synthesisStarted)
  │       ├── llm_provider.reasonStream()  ← synthesizer 调用
  │       │   └── onDelta: emit(answerDelta, delta)  ← ★ 关键！每个 token 都 emit
  │       └── 完整 JSON 解析（不再需要客户端猜测）
  │
  └── emit(completed, response)
```

**关键变化**：
- `answerDelta` 来自 `llm_provider.reasonStream()` 的 `onDelta` 回调——这是**真实的** LLM token 流，不是事后切分的伪流式
- 但 `answerDelta` **只在 synthesizer 阶段** emit，此时模型输出的是 `userMarkdown` 内容
- planner 阶段模型输出的是 JSON（不可流式展示），所以 planner 阶段只 emit `progressText`
- 引擎完成 JSON 解析后 emit `completed`（含完整 structuredResponse），客户端不需要解析 JSON

### 10.5 解决 synthesizer 阶段的 JSON vs 流式矛盾

**当前原则**：流式由运行时事件通道承载，`assistant_turn` / JSON 只保留稳态语义。

**当前做法**：
1. 运行时通过 `answerDelta` / `progressText` 等事件向 UI 传递流式内容。
2. `assistant_turn` 在完成态返回完整 JSON，保留 `decision`、`userMarkdown`、`selfCheck` 等稳态字段。
3. 不再依赖嵌套 `understanding.streamText` / `answerProcessing.streamText`，也不再把回答拆成“结构化前缀 + 自由文本体”。
4. 引擎在完成态补入 `_meta`（`contractId`、`domainId`、`stateId`、`latencyMs` 等）用于可观测与诊断。

### 10.6 UI 侧事件消费——按类型路由到区块

```
chat_detail_page 事件订阅:

switch (event.type) {
  case planStarted:
    → 显示"规划中"阶段卡片
  case slotFilling:
    → 更新阶段卡片：展示已补齐的槽位
  case searchQueryGenerated:
    → 阶段卡片增加一行："搜索：深圳 实时天气 2026年3月"
  case searchStarted:
    → 阶段卡片进入"搜索中"状态（loading 动画）
  case searchCompleted:
    → 阶段卡片更新："找到 4 条结果，覆盖率 85%"
  case replanning:
    → 阶段卡片增加一行："补充搜索：{reason}"
  case synthesisStarted:
    → 隐藏阶段卡片的 loading，准备答案区域
  case answerDelta:
    → 追加文本到答案气泡（真实流式！）
    → 无需 _looksLikeJsonEnvelope 过滤（协议保证是纯文本）
    → 无需 contains("contractId") 过滤（协议保证是纯文本）
  case progressText:
    → 更新进度指示器文本
  case completed:
    → 最终渲染（若 answerDelta 已流式完成，此时只做 selfCheck 校验）
    → 写入 session/memory（直接用 response.userMarkdown，不需要再从 JSON 提取）
  case degraded:
    → 显示降级提示 + fallback 文本
}
```

**UI 侧不再需要的代码（可删除）**：
- `_looksLikeJsonEnvelope()` — 不需要了，answerDelta 协议保证是纯文本
- `contains('"assistant_turn_v2"')` 过滤 — 不需要了
- `_resolveAssistantDisplayText()` 中的括号深度扫描 — 不需要了
- `appendStreamingChunk()` 中的启发式过滤 — 不需要了

### 10.7 当前事件类型对照 & 迁移

```
记录方案（含已下线模板）:
  enum AssistantRunStreamEventType { trace, chunk, completed, failed }
  - trace: 笼统的追踪事件（toolStart/toolResult/assistantDelta/streamDelta 混在一起）
  - chunk: 无类型的文本片段（可能是 JSON、可能是 Markdown、可能是进度文案——客户端猜）
  - completed: 完整响应
  - failed: 错误

v2:
  trace → 拆分为 planStarted / slotFilling / searchStarted / searchCompleted / replanning / synthesisStarted
  chunk → 拆分为 answerDelta（纯文本保证） / progressText（进度文案保证）
  completed → completed（不变，但 response 中无需客户端提取 userMarkdown）
  failed → degraded（携带降级原因 + fallback 文本，而非 errorMessage 字符串）
```

### 10.8 13 个 JSON 解析点的清除计划

当前 6 个文件中有 13+ 个分散的 JSON 解析点。v2 协议下，**客户端和 stream entry 将不再需要解析 JSON**：

| 文件 | 当前解析点 | v2 变更 |
|------|-----------|---------|
| `local_phase_execution_owner._decodeJsonObject` | 3 策略猜测 | 保留，但仅在引擎内部使用，不暴露给下游 |
| `local_phase_execution_owner._extractJsonCandidateBlocks` | 括号深度扫描 | 同上 |
| `local_phase_execution_owner._extractDisplayTextForStorage` | indexOf('{') | 直接用 `response.userMarkdown`，无需从 JSON 提取 |
| `react_runtime._extractToolCallsFromJsonText` | indexOf('{') | 升级为统一解析器 `LlmResponseJsonParser` |
| `assistant_stream_projector._resolveChunkDisplayText` | 多路判断 | **删除**——不再需要，answer 由 answerDelta 事件流式传递 |
| `assistant_stream_projector._chunkText` | 按句切分 | **删除**——不再需要伪流式 |
| `chat_detail_page._looksLikeJsonEnvelope` | 字符串匹配 | **删除**——事件协议保证 answerDelta 是纯文本 |
| `chat_detail_page._resolveAssistantDisplayText` | 括号深度扫描 | **删除**——completed 事件直接携带 userMarkdown |
| `chat_message_bubble._tryDecode` | jsonDecode | **简化**——content 字段已是纯 Markdown，不再是 JSON |
| `session_manager._sanitizeForSummary` | _jsonDecodeFirst | **简化**——session 写入的就是 userMarkdown，不再是 JSON |

**净效果**：13 个分散解析点 → 引擎内部 1 个统一解析器，客户端/UI 层 **0 个 JSON 解析点**。

### 10.9 与 prompt 模板架构的协同

```
prompt 端（§1-§8）    ←→    响应端（SSE 事件协议）

§3 <task>               →    引擎知道当前阶段（plan/answer）→ emit 对应阶段事件
§4 <output_contract>    →    各阶段输出稳态 JSON（引擎解析，不直接传给客户端）
                             流式文本由运行时事件通道承载（如 `answerDelta` / `progressText`）
§6 <domain_skill>       →    引擎知道当前域 → emit 带 domainId 的事件
§7 <dialogue_state>     →    引擎知道状态转换 → emit slotFilling 事件
§8 <context_slots>      →    引擎自动补齐 → emit slotFilling 事件
```

prompt 模板和 SSE 事件协议是一个硬币的两面：
- prompt 告诉模型**怎么思考和输出**
- SSE 事件协议告诉客户端**怎么接收和显示**
- 引擎是中间桥梁——**解析模型输出 → 转换为类型化事件**

---

## 十一、Token 成本收益预估

以天气查询场景为例：

| 维度 | 当前 | v2 | 变化 |
|------|------|-----|------|
| 固定层 token (L1) | ~350 | ~200 | -43%（仅 identity + safety） |
| 阶段前缀 (L2) | 散布各处 | ~400 | task 提前 + output_contract 紧跟 |
| 技能层 (L3) | ~500 | ~300 | persona 精简 + skill 聚焦 |
| 数据层 (L4) | ~800 | ~400 | JSON → Markdown，去重复 |
| **总 system prompt** | **~1650** | **~1300** | **-21%** |
| L1 Prompt Cache 命中率 | 0% | **100%** | ~200 token 跨请求缓存 |
| L2 Prompt Cache 命中率 | 0% | **~70%** | 同阶段连续请求（ReAct 循环内） |
| System messages 数 | 7+ | **2** | 模型解析开销大幅 ↓ |

**缓存层收益分析**：
- L1（identity + safety，~200 token）：**所有请求共享**，Anthropic API 缓存 ~90% 折扣
- L2（+ task + output_contract，~600 token 累计）：同一 ReAct 循环内 3-5 次调用共享
- L3（+ persona + skill + tool，~900 token 累计）：同一会话同域多轮共享

---

## 附录 A：文件目录结构对照

```
当前:
prompts/global/
├── stack.identity.md             ← 身份与使命基线
├── stack.safety.md               ← 安全、降级与危机边界
├── stack.persona.md              ← 全局人格与语气基线
├── stack.tool_policy.md          ← 工具权限与执行约束
├── phase.output_contract.plan.md ← 规划阶段输出契约
├── phase.output_contract.answer.md ← 回答阶段输出契约
├── planner.global_plan.md        ← 保留，重写
├── synthesizer.final_answer.md   ← 保留，精简
├── planner.postcondition_check.md← 已下线
├── synthesizer.multi_skill_fusion.md ← 已下线
└── summarize_session.md          ← 保留

当前（指令优先序）:
prompts/global/
├── stack.identity.md                     ← 新建 §1（L1 固定前缀）
├── stack.safety.md                       ← 新建 §2（L1 固定前缀）
├── planner.global_plan.md                ← 重写 §3（L2 阶段前缀，任务定义提前！）
├── synthesizer.final_answer.md           ← 精简 §3（answer 阶段的 task）
├── phase.output_contract.plan.md         ← 新建 §4（L2 阶段前缀）
├── phase.output_contract.answer.md       ← 新建 §4
├── stack.persona.md                      ← 新建 §5（L3 技能前缀）
├── stack.tool_policy.md                  ← 新建 §6b（L3 技能前缀）
└── summarize_session.md                  ← 保留（独立流程，不走主 prompt）
```

## 附录 B：`_ResolvedSkillContext` 返回结构增强

```dart
class _ResolvedSkillContext {
  final String skillName;
  final String instructionMarkdown;  // SKILL.md body + constraints
  final String personaOverride;      // 新增：persona 段（角色+语气+语言）
  final String phaseReferences;      // phase-aware 参考文件内容
}
```

## 附录 C：模板 meta.json 变更

```json
{
  "stack.identity": { "requiredVariables": [] },
  "stack.persona": { "requiredVariables": ["skillPersona"] },
  "stack.safety": { "requiredVariables": [] },
  "stack.tool_policy": { "requiredVariables": ["availableToolNames", "toolInvocationGuidelines"] },
  "phase.output_contract.plan": { "requiredVariables": [] },
  "phase.output_contract.answer": { "requiredVariables": [] }
}
```
