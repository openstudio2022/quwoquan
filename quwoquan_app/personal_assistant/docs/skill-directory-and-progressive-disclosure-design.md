# Personal Assistant Skill 目录结构与渐进式披露设计

> **版本**：v1.1 · **日期**：2026-03-07（更新活跃技能列表）
> **范围**：`assets/personal_assistant/skills/*` 目录规范、运行时加载策略、槽位国际化、开发就绪度评估  
> **从属**：`personal_assistant/docs/skill_development_standard.md` 的配套实施细则
>
> **收口说明**：当前 Skill / Tool 扩展请优先阅读：
> - `PERSONAL_ASSISTANT_SKILL_AND_TOOL_EXTENSIBILITY.md`
> - `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`
>
> 本文档保留为详细参考，不再作为第一入口。

---

## 一、工程目录全景

```
quwoquan_app/
├── assets/personal_assistant/
│   ├── config/                              ← 全局运行时配置（代码读，不进模型）
│   │   ├── agent_run_observability_schema.json
│   │   ├── progress_text_policy.json
│   │   ├── react_policy.json
│   │   └── retrieval_time_contract.json     ← 全局时间槽位约束
│   │
│   ├── prompts/                             ← Prompt Stack 各层模板
│   │   ├── global/
│   │   │   ├── stack.global_system.md       ← L1 全局身份与安全
│   │   │   ├── stack.runtime_policy.md      ← L2 本轮预算/权限/工具
│   │   │   ├── stack.recovery_policy.md     ← L3 失败恢复策略
│   │   │   ├── stack.output_contract.md     ← L4 输出契约（assistant_turn）
│   │   │   ├── stack.global_policy.md       ← L5 全局政策叠加
│   │   │   ├── planner.global_plan.md       ← Planner 主模板
│   │   │   └── synthesizer.*.md             ← Synthesizer 模板族
│   │   ├── domain_routing/                  ← 领域路由目录
│   │   └── web/                             ← Web 查询规划模板
│   │
│   └── skills/                              ← 技能资产根目录（详见二）
│       ├── {domain}/                        ← 每个技能一个目录
│       └── *.skill.yaml                     ← 轻量技能（知识问答等）
│
├── lib/assistant/
│   ├── application/
│   │   └── assistant_edge_service.dart      ← 当前 edge assistant 装配入口
│   ├── runtime/
│   │   └── assistant_runtime.dart           ← 当前公开 runtime 封装
│   ├── skills/
│   │   ├── assistant_skill_runtime.dart     ← Skill loader + market service
│   │   └── skill_manifest.dart              ← Manifest 数据模型
│   ├── tools/
│   │   └── tool_schema.dart                 ← 当前工具合同入口
│   └── capabilities/
│       └── capabilities.dart                ← 当前 capability catalog
│
└── personal_assistant/docs/                 ← 设计文档根目录
    ├── skill_development_standard.md        ← 开发与交付标准（主规范）
    └── skill-directory-and-progressive-disclosure-design.md  ← 本文档
```

补充：更深层 legacy implementation 仍可能位于 `lib/personal_assistant/`，但不再作为当前推荐入口。

---

## 二、Skill 目录结构（最终确定版）

每个 `skills/{domain}/` 目录的完整结构如下：

```
skills/{domain}/
│
├── SKILL.md                              ← 技能主控文档（frontmatter + body 正文）
│
├── references/                           ← 模型可读的参考材料（phase-aware 加载）
│   ├── domain-knowledge.md               ← 领域约束、槽位策略、安全边界
│   ├── output-examples.md                ← 输出 few-shot 示例（answer 阶段注入）
│   └── tool-call-guidance.md             ← 工具调用指引（tool_call 阶段注入）
│                                            [从 scripts/ 迁入，已有文件需同步重命名]
│
├── dialogue/                             ← 对话状态机（运行时按状态渐进加载）
│   ├── state_transition_contract.json    ← 状态转移图 + requiredFieldsByState
│   ├── state_machine.md                  ← 状态机说明（按状态摘录注入）
│   ├── state_prompts.md                  ← 各状态执行提示词（按状态摘录注入）
│   ├── dialogue_judge_prompt.md          ← LLM 事件判定器（关键词匹配 fallback 用）
│   └── state_transition_test_cases.json  ← 状态迁移自动化测试用例
│
├── scripts/
│   └── skill.policy.md                   ← 始终加载的策略叠加层（语气/persona/强制段落）
│
└── config/
    └── retrieval_policy.json             ← 检索策略配置（工具代码读，不进模型 prompt）
```

### 各文件角色一览

| 文件 | 消费者 | 加载时机 | 注入方式 |
|---|---|---|---|
| `SKILL.md` body | 模型 | 每轮（bootstrap） | 全量合并进 `domainSkillInstruction` |
| `scripts/skill.policy.md` | 模型 | 每轮（bootstrap） | 追加合并进 `domainSkillInstruction` |
| `references/tool-call-guidance.md` | 模型 | tool_call 阶段 | phase-aware 追加 |
| `references/output-examples.md` | 模型 | answer 阶段 | phase-aware 追加（few-shot） |
| `references/domain-knowledge.md` | 模型 | ask_user / answer 阶段 | phase-aware 追加 |
| `dialogue/state_transition_contract.json` | 代码 | 首次请求后缓存 | 解析为 `DialogueRoundScript` |
| `dialogue/state_machine.md` | 模型 | 每轮，按当前状态摘录 | 通过 `statePromptExcerpt` 字段 |
| `dialogue/state_prompts.md` | 模型 | 每轮，按当前状态摘录 | 通过 `stateMachineExcerpt` 字段 |
| `dialogue/dialogue_judge_prompt.md` | 代码→模型 | 关键词匹配失败时 | LLM fallback 判定 call |
| `dialogue/state_transition_test_cases.json` | 测试 | CI 门禁 | `DialogueStateRuntime` 单测 |
| `config/retrieval_policy.json` | 代码 | `web_search` 工具执行时 | 程序化配置，不进 prompt |

> **目录约定**：`references/` 是唯一的"模型可读材料"目录；`config/` 是唯一的"代码读取的结构化配置"目录。两者不混用。

---

## 三、渐进式披露设计

### 3.1 整体分层架构

```
每一轮 LLM 调用的 Prompt = Prompt Stack + 动态注入层
                              │
          ┌───────────────────┤
          │   Prompt Stack    │ （llm_provider 组装，每轮固定）
          │                   │
          │  L1 global_system  │
          │  L2 runtime_policy │
          │  L3 recovery_policy│
          │  L4 output_contract│
          └───────────────────┘
                   +
          ┌───────────────────┐
          │  技能动态注入层    │ （agent_loop 组装，按轮次/阶段变化）
          │                   │
          │  [bootstrap]       │ ← SKILL.md body + skill.policy.md（每轮）
          │  [phase-specific]  │ ← 按 nextAction 阶段加载 references/*
          │  [dialogue]        │ ← 当前状态的 state 摘录（每轮渐进）
          │  [session context] │ ← 记忆召回 + 历史摘要（按需）
          └───────────────────┘
                   +
          ┌───────────────────┐
          │  对话脚本 JSON     │ ← dialogueRoundScript（每轮，作为 system message）
          │  当前状态机摘录    │
          └───────────────────┘
```

### 3.2 Phase-aware 加载策略

Phase 由上一轮模型输出的 `decision.nextAction` 字段决定：

```
上一轮 nextAction       → 本轮 phase    → 追加的 references 文件
─────────────────────────────────────────────────────────────────
(首轮 / 无上轮结果)     → bootstrap    → 无追加（仅 SKILL + policy）
tool_call               → tool_call    → references/tool-call-guidance.md
ask_user                → ask_user     → references/domain-knowledge.md（槽位补全提示）
answer                  → answer       → references/output-examples.md（few-shot）
retry                   → tool_call    → references/tool-call-guidance.md
abort / fallback        → answer       → references/output-examples.md（降级示例）
```

### 3.3 对话状态机的渐进式加载（已实现）

`DialogueStateRuntime` 当前行为（以天气技能为例）：

```
第 1 轮（用户: "深圳天气"）
  state_transition_contract.json → 加载并缓存
  当前状态: S0_意图识别
  检测事件: E_天气意图命中
  建议下一状态: S1_城市补全
  注入模型: state_prompts.md 中 S1_城市补全 段落（≤1200字符）
            state_machine.md 中 S1_城市补全 段落（≤1200字符）

第 2 轮（工具返回城市=深圳）
  状态前进: S1_城市补全 → S2_天气检索
  检测事件: E_城市已就绪
  注入模型: state_prompts.md 中 S2_天气检索 段落
            state_machine.md 中 S2_天气检索 段落

第 3 轮（工具返回天气数据）
  状态前进: S2_天气检索 → S3_结果渲染
  检测事件: E_检索成功
  注入模型: state_prompts.md 中 S3_结果渲染 段落（含 few-shot 示例注入）
```

### 3.4 Phase-aware 加载的代码扩展点

当前 `agent_loop._resolveSkillContext` 无 phase 参数。扩展方案：

```dart
// 当前（已实现）
Future<_ResolvedSkillContext> _resolveSkillContext({
  required String domainId,
  required String userQuery,
}) async { ... }

// 目标（待实现）
Future<_ResolvedSkillContext> _resolveSkillContext({
  required String domainId,
  required String userQuery,
  required String phase,           // 新增: 'bootstrap' | 'tool_call' | 'answer' | 'ask_user'
}) async {
  // bootstrap: 加载 SKILL body + skill.policy.md（现有逻辑，不变）
  // tool_call: bootstrap + 加载 frontmatter.script_guides 指向的文件
  // answer:    bootstrap + 加载 frontmatter.reference_docs 里的 output-examples.md
  // ask_user:  bootstrap + 加载 frontmatter.reference_docs 里的 domain-knowledge.md
}
```

SKILL.md frontmatter 中的 `reference_docs` / `script_guides` 字段即为 phase mapping 的声明：

```yaml
reference_docs: references/domain-knowledge.md references/output-examples.md
script_guides:  references/tool-call-guidance.md
```

- `script_guides` → tool_call 阶段加载
- `reference_docs` 中的 `output-examples.md` → answer 阶段加载
- `reference_docs` 中的 `domain-knowledge.md` → ask_user / answer 阶段加载

---

## 四、当前活跃技能目录

### 4.0 活跃技能（15 个）

路由由 LLM 自主选择（读取 `domain_routing_catalog.json` 中的 `description`），不再依赖 `intentKeywords` 关键词匹配。

| domainId | mode | searchPolicy.strategy | 说明 |
|---|---|---|---|
| `weather` | hybrid | realtime | 天气查询、出行建议、穿衣推荐 |
| `travel_transport` | hybrid | realtime | 交通路线、导航、实时路况 |
| `travel_planning` | hybrid | research | 旅行攻略、景点、酒店机票 |
| `local_life` | hybrid | realtime | 餐厅美食、本地服务、周边推荐 |
| `calendar_task` | task | none | 日程管理、提醒设置、待办跟踪 |
| `knowledge_general` | qa | research | 百科知识、原理解释、事实查询 |
| `finance_consumer` | qa | research | 理财、投资、贷款预算 |
| `health_wellness` | qa | research | 健康咨询、养生、症状科普 |
| `education_learning` | qa | research | 学习辅导、考试备考 |
| `work_productivity` | hybrid | research | 工作效率、职业规划 |
| `shopping_decision` | hybrid | research | 选购对比、性价比分析 |
| `policy_public_service` | qa | research | 政策解读、政务服务 |
| `emotion_companion` | qa | none | 情感陪伴、心理疏导 |
| `fortune_astrology` | qa | none | 星座运势、占卜趣味 |
| `fallback_general_search` | qa | research | 通用搜索兜底 |

### 废弃技能（已下线，目录仍存在但不在路由中启用）

| 废弃 domainId | 处理方式 |
|---|---|
| `huawei_cloud_qa` | 下线，不再路由 |
| `social_companion_chat` | 合并入 `emotion_companion` |
| `relationship_matchmaking` | 合并入 `emotion_companion` |
| `family_parenting` | 合并入 `emotion_companion` |
| `divination_fortune` | 合并为 `fortune_astrology` |
| `astrology_constellation` | 合并为 `fortune_astrology` |

---

## 五、槽位国际化检查结果

### 5.1 检查结论

对 15 个活跃技能的 `skill.policy.md` 进行全量扫描，结论如下：

| 检查项 | 现状 | 是否满足 |
|---|---|---|
| 响应语言随用户语言 | 全部 15 个活跃技能均声明 "Follow user language for final response" | ✅ |
| 双语检索声明 | 部分技能声明了 bilingual retrieval 策略 | ✅（部分） |
| 搜索引擎查询规范化 | `planner.global_plan.md` 的 `queryNormalization` 覆盖拼音→中文、英文→中文 | ✅ |
| 查询变体（提升召回） | `queryVariants` 3 条变体（精确/宽泛/权威域） | ✅ |
| 提示词统一中文 | `skill.policy.md` 全部为**英文** | ❌ 不符合标准 |
| 槽位级别双语注解 | `domain-knowledge.md` 无槽位语言规则 | ❌ 缺失 |
| 搜索查询上下文为中文 | `_withTimeConstraintQuery` 附加"时间范围:..." | ✅ |
| 权威域名列表 | `config/retrieval_policy.json` 的 `authorityDomains` 覆盖目标语言域名 | ✅ |

### 4.2 两个核心问题

**问题 1：`skill.policy.md` 全部为英文**

当前 `skill.policy.md` 是合并进 `domainSkillInstruction` 的 prompt 层，最终传给 LLM。按"提示词统一中文"原则，该文件应使用中文。

以 `finance_consumer/scripts/skill.policy.md` 为例，应改为：

```markdown
# 技能策略 v1
skill_id: finance_consumer

## 角色定位
你是一个风险意识优先的消费金融助理。

## 语气要求
- 专业、谨慎、以数据为中心。

## 语言策略
- 最终回答语言跟随用户输入语言。
- 全球市场术语允许双语检索（中英文查询变体）。

## 领域边界
- 禁止给出"保本/保收益"类表述。
- 所有金融建议必须附带风险提示。

## 必须包含的章节
1. 结论与适用性评估
2. 指标数据与对比
3. 风险与约束
4. 免责声明（引用块格式）
5. 追问建议
```

**问题 2：槽位级别缺少双语检索注解**

当前 `domain-knowledge.md` 记录槽位策略（如 `city` 补全顺序），但没有声明"该槽位的搜索查询应生成哪些语言的变体"。

### 4.3 槽位国际化设计规范

#### 规则 1：槽位存储语言（统一中文）

所有槽位在内存和 `slotState` JSON 中统一使用中文存储：

```json
{
  "slotState": {
    "city": { "value": "深圳", "source": "user_query" },
    "company_name": { "value": "比亚迪", "source": "user_query" },
    "symptom": { "value": "头痛", "source": "user_query" }
  }
}
```

#### 规则 2：搜索查询双语扩展（通过 queryVariants）

模型在 `queryNormalization.queryVariants` 中负责生成双语变体。各技能在 `references/domain-knowledge.md` 的槽位策略节中声明哪些槽位需要英文变体：

```markdown
## 槽位国际化规则

| 槽位 | 存储语言 | 搜索变体策略 |
|---|---|---|
| city | 中文（深圳） | queryVariants 中生成英文变体（Shenzhen） |
| timeScope | 枚举值 | 无需双语 |
| company_name | 中文（比亚迪） | queryVariants 中生成 A 股代码（002594）+ 英文名（BYD） |
| symptom | 中文（头痛） | queryVariants 中可包含医学术语英文（headache, cephalalgia） |
```

#### 规则 3：提示词语言（统一中文）

| 文件 | 语言要求 |
|---|---|
| `SKILL.md` 正文 | **中文** |
| `scripts/skill.policy.md` | **中文**（当前为英文，需整体迁移） |
| `references/domain-knowledge.md` | **中文** |
| `references/output-examples.md` | **中文**（示例内容与实际输出语言一致） |
| `references/tool-call-guidance.md` | **中文** |
| `dialogue/state_prompts.md` | **中文** |
| `dialogue/state_machine.md` | **中文** |
| `dialogue/dialogue_judge_prompt.md` | **中文** |
| `config/retrieval_policy.json` | 字段值英文（JSON 标准），`contextConstraints` 中文 |

#### 规则 4：双语检索触发条件（按技能声明）

在 `skill.policy.md` 的"语言策略"节中声明本技能的双语检索触发条件：

| 技能 | 双语检索策略 |
|---|---|
| weather | 国际城市名同时生成英文查询变体 |
| finance_consumer | 全球市场术语、外资公司名、指数代码生成英文变体 |
| health_wellness | 医学专业术语生成英文变体（用于 PubMed 等权威域） |
| education_learning | 课程名、平台名生成英文变体（MOOC/Coursera 等） |
| travel_planning | 目的地、景点名生成英文变体（提升国际源覆盖） |
| travel_transport | 航班代码、跨境交通术语保留英文 |
| shopping_decision | 跨境商品品牌、型号保留英文 |
| local_life | 城市名、品牌名可选双语 |
| policy_public_service | 港澳台、国际组织政策可双语 |
| 其他技能 | 默认中文，不生成双语变体 |

---

## 六、开发就绪度评估

### 5.1 P0（可立即开发，无阻塞）

| 任务 | 对应代码位置 | 预估工时 |
|---|---|---|
| **Phase-aware 加载实现** | `agent_loop._resolveSkillContext` 增加 `phase` 参数，加载 `reference_docs`/`script_guides` 对应文件 | 0.5d |
| **tool-call-guidance 迁移** | 15 个活跃技能将 `scripts/tool-call-guidance.md` 重命名移入 `references/`，更新 SKILL.md frontmatter | 0.5d |
| **skill.policy.md 中文化** | 15 个活跃技能将 `skill.policy.md` 由英文改写为中文 | 1d |
| **state_transition_test_cases 接入测试** | 新建 `test/personal_assistant/dialogue_state_transition_contract_test.dart` | 0.5d |

### 5.2 P1（需要小范围规格确认后开发）

| 任务 | 前置条件 | 预估工时 |
|---|---|---|
| **domain-knowledge.md 补充槽位语言规则** | 确认各技能槽位清单（天气/金融/健康等各 2~5 个） | 1d |
| **dialogue_judge_prompt.md 接入运行时** | 确认 LLM fallback 触发阈值（置信度 < N 时启用） | 1d |
| **output-examples.md few-shot 效果验证** | 在 acceptance_vm_test 中增加 answer 阶段质量回归 | 0.5d |

### 5.3 P2（需要正式 spec 后开发）

| 任务 | 缺什么 | 备注 |
|---|---|---|
| `slot-contract.md` 创建（15 个活跃技能） | 各技能槽位全集定义尚未文档化 | 可在 domain-knowledge.md 中先用表格暂代 |
| `dialogue_judge_prompt.md` 升级为通用 LLM 状态判定服务 | 需设计 judge 模型的 token 预算策略 | 独立 subagent 方向 |

### 5.4 门禁补充

以下检查项应补入 `skill_standard_contract_test.dart`：

```dart
// 新增检查：tool-call-guidance 必须在 references/ 下
test('tool-call-guidance must be in references/', () {
  // 检查 scripts/ 下不存在 tool-call-guidance.md
  // 检查 references/ 下存在 tool-call-guidance.md
});

// 新增检查：skill.policy.md 不包含英文段落标题
test('skill.policy.md must use Chinese section headers', () {
  // 检查不包含 ## Persona、## Tone、## Language Strategy 等英文标题
  // 检查包含 ## 角色定位 或 ## 语气要求 等中文标题
});

// 新增检查：domain-knowledge.md 包含槽位国际化规则表格
test('domain-knowledge.md should declare slot i18n rules', () {
  // 检查包含"槽位国际化规则"或"槽位语言"相关章节
});
```

---

## 七、变更对照表（迁移路径）

| 变更项 | 当前状态 | 目标状态 | 是否破坏性 |
|---|---|---|---|
| `scripts/tool-call-guidance.md` | 存在，运行时不加载 | 移入 `references/tool-call-guidance.md`，Phase-aware 加载 | 否（仅重命名+加载）|
| `scripts/skill.policy.md` | 英文，始终加载 | 中文，始终加载 | 否（内容改写，接口不变）|
| `references/output-examples.md` | 存在，运行时不加载 | answer 阶段 phase-aware 加载 | 否（新增加载逻辑）|
| `references/domain-knowledge.md` | 存在但内容空洞 | 补充槽位语言规则，ask_user 阶段加载 | 否（内容增量）|
| `dialogue/dialogue_judge_prompt.md` | 存在，运行时不用 | 关键词匹配失败时触发 LLM 判定 | 否（新增 fallback 路径）|
| `dialogue/state_transition_test_cases.json` | 存在，无对应测试 | 接入 `dialogue_state_transition_contract_test.dart` | 否（新增测试）|
| `config/retrieval_policy.json` | 已加载，已生效 | 不变 | — |
