# Personal Assistant Skill 目录结构与渐进式披露设计

> **版本**：v1.1 · **日期**：2026-03-07（更新活跃技能列表）
> **范围**：`assets/assistant/skills/*` 目录规范、运行时加载策略、槽位国际化、开发就绪度评估  
> **从属**：`assistant/docs/skill_development_standard.md` 的配套实施细则
>
> **收口说明**：当前 Skill / Tool 扩展请优先阅读：
> - `PERSONAL_ASSISTANT_SKILL_AND_TOOL_EXTENSIBILITY.md`
> - `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`
> - `PERSONAL_ASSISTANT_SKILL_MULTI_AGENT_SPEC.md`
> - `PERSONAL_ASSISTANT_SKILL_MULTI_AGENT_TASK_TEMPLATE.md`
>
> 本文档保留为详细参考，不再作为第一入口。

---

## 一、工程目录全景

```
quwoquan_app/
├── assets/assistant/
│   ├── config/                              ← 全局运行时配置（代码读，不进模型）
│   │   ├── agent_run_observability_schema.json
│   │   ├── progress_text_policy.json
│   │   ├── react_policy.json
│   │   └── retrieval_time_contract.json     ← 全局时间槽位约束
│   │
│   ├── prompts/                             ← Prompt Stack 各层模板
│   │   ├── global/
│   │   │   ├── stack.identity.md            ← L1 全局身份
│   │   │   ├── stack.safety.md              ← L2 安全与降级边界
│   │   │   ├── stack.persona.md             ← L3 全局人格/语气
│   │   │   ├── stack.tool_policy.md         ← L4 工具与执行约束
│   │   │   ├── phase.output_contract.*.md   ← L5 分阶段输出契约
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
└── assistant/docs/                 ← 设计文档根目录
    ├── skill_development_standard.md        ← 开发与交付标准（主规范）
    └── skill-directory-and-progressive-disclosure-design.md  ← 本文档
```

补充：更深层 legacy implementation 仍可能位于 `lib/personal_assistant/`，但不再作为当前推荐入口。

---

## 二、Skill 目录结构（最终确定版）

每个 `skills/{domain}/` 目录下可以直接放 `skill/`，也可以在需要时再分出 `subdomain/skill/`。
原则上，**领域必选，子领域可选**；只有当某个领域内部存在明显不同的意图族、工具链或输出模板时，才值得引入子领域。

```
skills/{domain}/
├── {skill}/
│   ├── SKILL.md                          ← 技能主控文档（frontmatter + body 正文）
│   ├── references/                       ← 模型可读参考材料
│   ├── dialogue/                         ← 对话状态机（运行时按状态渐进加载）
│   ├── scripts/                          ← 始终加载的策略叠加层
│   └── config/                           ← 结构化策略
└── {subdomain}/
    ├── {skill}/
    └── ...
```

### 各文件角色一览

| 文件 | 消费者 | 加载时机 | 注入方式 |
|---|---|---|---|
| `SKILL.md` body | 模型 | 每轮（bootstrap） | 全量合并进 skill instruction |
| `scripts/skill.policy.md` | 模型 | 每轮（bootstrap） | 追加合并进 skill instruction |
| `references/tool-call-guidance.md` | 模型 | tool_call 阶段 | phase-aware 追加 |
| `references/output-examples.md` | 模型 | answer 阶段 | phase-aware 追加（few-shot） |
| `references/domain-knowledge.md` | 模型 | ask_user / answer 阶段 | phase-aware 追加 |
| `dialogue/state_transition_contract.json` | 代码 | 首次请求后缓存 | 解析为 `DialogueRoundScript` |
| `dialogue/state_machine.md` | 模型 | 每轮，按当前状态摘录 | 通过 `statePromptExcerpt` 字段 |
| `dialogue/state_prompts.md` | 模型 | 每轮，按当前状态摘录 | 通过 `stateMachineExcerpt` 字段 |
| `dialogue/dialogue_judge_prompt.md` | 代码→模型 | 状态无法直接判定时 | LLM fallback 判定 call |
| `dialogue/state_transition_test_cases.json` | 测试 | CI 门禁 | `DialogueStateRuntime` 单测 |
| `config/retrieval_policy.json` | 代码 | 工具执行时 | 程序化配置，不进 prompt |

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
          │  技能动态注入层    │ （assistant_agent_loop / phase owner 组装，按轮次/阶段变化）
          │                   │
          │  [bootstrap]       │ ← 路由后 skill pack（每轮）
          │  [phase-specific]  │ ← 按 nextAction 阶段加载 references/*
          │  [dialogue]        │ ← 当前状态的 state 摘录（每轮渐进）
          │  [session context] │ ← 历史摘要 + 近期工具观测（按需）
          └───────────────────┘
                   +
          ┌───────────────────┐
          │  对话脚本 JSON     │ ← dialogueRoundScript（每轮，作为 system message）
          │  当前状态机摘录    │
          └───────────────────┘
```

### 3.2 Phase-aware 加载策略

Phase 由上一轮模型输出的 `nextAction` 字段决定：

```
上一轮 nextAction       → 本轮 phase    → 追加的 references 文件
─────────────────────────────────────────────────────────────────
(首轮 / 无上轮结果)     → bootstrap    → 无追加（仅 skill pack）
tool_call               → tool_call    → references/tool-call-guidance.md
ask_user                → ask_user     → references/domain-knowledge.md（槽位补全提示）
answer                  → answer       → references/output-examples.md（few-shot）
retry                   → tool_call    → references/tool-call-guidance.md
abort / fallback        → answer       → references/output-examples.md（降级示例）
```

### 3.3 首轮目录树与推荐技能

首轮不直接暴露全量 skill，而是先给模型看 **领域 /（可选）子领域 / skill** 的目录树。

对每个领域或子领域节点，只展示 1 到 5 个推荐 skill，作为该节点最常用的入口。这里使用的是“推荐技能”语义，而不是“commonSkills”语义：它表示**优先候选**，不是全部常用集合。

模型可以：

- 直接选中某个 skill
- 先选领域
- 先选子领域
- 一次选多个 skill
- 没选中 skill 时交给系统级默认 skill 承接

模型在同一轮里可以同时返回多个目标：

- 主 skill
- 支持 skill
- 领域
- 子领域

这用于减少来回澄清次数，同时保持路径可解释。

### 3.4 领域与子领域定义原则

#### 原则

1. **领域必选，子领域可选。**
2. 只有当一个领域内部存在显著不同的意图族、工具链、状态机或输出模板时，才引入子领域。
3. 领域本身足够单一、稳定、路径短时，可以直接从领域到 skill，不必强行加子领域。
4. 如果子领域存在，也不要求每个领域都必须暴露子领域。
5. 推荐技能只显示在当前节点下最常见的 1 到 5 个入口，不把技能池一股脑塞给模型。

#### 当前领域建议

| 领域 | 子领域是否推荐 | 建议子领域示例 | 说明 |
|---|---|---|---|
| `weather` | 否 | 无 | 领域本身已足够单一，直接到 skill |
| `travel` | 是 | `transport`、`planning`、`booking` | 旅行/出行统一大类，含订车、导航、景点、酒店、美食等 |
| `local_life` | 是 | `food`、`place`、`service` | 本地生活意图差异较大，但不宜拆得过细 |
| `calendar_task` | 是 | `calendar`、`meeting`、`communication`、`task`、`project` | 归入办公/任务/生产力，覆盖日历、会议、邮件、消息、待办 |
| `knowledge_general` | 否/弱建议 | `concept`、`translation`（可选） | 若后续 skill 密度提升可再拆 |
| `finance_consumer` | 是 | `budget`、`loan`、`investment`、`insurance` | 金融场景差异明显，子领域边界清楚 |
| `health_wellness` | 是 | `symptom`、`nutrition`、`sleep`、`exercise` | 健康咨询需要更细分但仍保持少量入口 |
| `education_learning` | 是 | `exam`、`tutoring`、`writing`、`planning` | 教育类常见子路径明确 |
| `work_productivity` | 是 | `efficiency`、`career`、`project` | 工作效率、办公协作、项目推进、职业规划可稳定区分 |
| `shopping_decision` | 是 | `comparison`、`selection`、`deal` | 购物/商品/交易前决策，偏选购与优惠，不拆得过细 |
| `policy_public_service` | 是 | `policy`、`procedure`、`materials` | 政策与办事路径可区分 |
| `emotion_companion` | 否 | 无 | 以连续陪伴为主，保持扁平更好 |
| `fortune_astrology` | 否 | 无 | 趣味类，通常直接到 skill |
| `search_fallback` | 否 | 无 | 搜索兜底处理，对应系统级默认 skill |

#### 目录树展示方式

- 领域节点下面优先展示该领域最常用的推荐技能。
- 如果领域下存在子领域，则先展示子领域，再在子领域下展示 1 到 5 个推荐技能。
- 如果某个领域没有子领域，模型直接从领域节点选 skill。
- 如果用户一句话可能命中多个技能，目录树允许一次返回多个技能，模型负责给出 primary / supporting 关系。

#### 当前分类是否还缺少领域

结合 openclaw 这类技能市场的常见分布，以及小趣私人助理当前的场景边界，除了现有 15 个 skill 对应的领域外，还建议评估以下候选领域是否需要独立启用：

| 候选领域 | 是否建议当前启用 | 说明 |
|---|---|---|
| `news_current_events` | 视需求 | 适合“热点/新闻/实时事件”类查询，和知识问答不同 |
| `communication_writing` | 视需求 | 邮件、通知、文案、改写、摘要，必要时可并入 work_productivity |
| `media_management` | 视需求 | 图片/视频/音频整理、检索、命名、相册类任务 |
| `content_creation` | 视需求 | 生成文案、海报、短视频脚本、创意内容 |
| `social_community` | 暂缓 | 社区互动、帖子、评论、社交平台操作，若产品不涉社交可不启用 |
| `smart_home` | 暂缓 | 若未来接设备控制可单独成域 |
| `maps_location` | 可并入 travel/local_life | 若定位、路线、周边与导航复杂度升高，再独立 |
| `shopping_services` | 可并入 shopping_decision | 若出现电商下单、售后、优惠券等大量动作，再拆分 |

这些候选领域不要求当前全部启用，但它们能帮助判断：当某个领域内部已经出现“明显不同的意图族、工具链或状态机”时，再把它从现有领域里拆出去。

#### 跨 domain 组合意图支持

有些用户一句话会同时覆盖多个 domain，例如：

- 旅行 + 订酒店 + 找景点 + 找美食
- 办公 + 日历 + 会议 + 邮件 + 消息
- 购物 + 对比 + 下单前决策

这类意图不要拆成多个互相抢主导权的独立会话，而是让模型选出：

- 一个 **primary domain / primary skill**
- 若干 **supporting skills**
- 一个 **共享计划对象**，用于承接统一规划

推荐的处理方式是：

1. 首轮模型可以一次返回多个 skill，但必须明确主次。
2. 如果用户目标天然是一个统一计划，例如“预定咖啡 + 景点 + 美食”，优先由主 skill 承载总计划，其余 skill 作为 supporting skills。
3. 在 skill session 中，统一维护一个共享计划状态，例如 itinerary / task list / booking list / contact list / timeline。
4. 当某个 supporting skill 完成局部任务后，把结果回写到共享计划，再由主 skill 继续推进。
5. 如果跨 domain 的冲突无法消解，再由模型澄清，而不是让代码强行路由分裂。

#### `news_current_events` 的子领域建议

如果后续启用实时新闻类目，建议采用**少量、边界清晰**的子领域，而不是按新闻源或话题无限细分：

| 领域 | 子领域建议 | 说明 |
|---|---|---|
| `news_current_events` | `breaking_news` | 突发新闻、头条、热点事件 |
| `news_current_events` | `topic_digest` | 某一主题的新闻聚合与摘要 |
| `news_current_events` | `local_news` | 本地新闻、城市事件、区域资讯 |
| `news_current_events` | `analysis_brief` | 事件简报、背景梳理、影响分析 |

这类拆法的目标不是把新闻话题穷举，而是让模型能先判断“新闻/实时事件”与“百科知识”不同，再在少量稳定子类里继续选。

### 3.5 对话状态机的渐进式加载（已实现）

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

### 3.6 Phase-aware 加载的代码扩展点

当前 phase owner 的 skill context loader 需要显式接收 phase。扩展方案：

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
// bootstrap: 加载路由后 skill pack
// tool_call: bootstrap + 加载 references/tool-call-guidance.md
// answer:    bootstrap + 加载 references/output-examples.md
// ask_user:  bootstrap + 加载 references/domain-knowledge.md
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
| `travel_transport` | hybrid | realtime | 交通路线、导航、实时路况，属于 travel 下的“出行/交通”入口 |
| `travel_planning` | hybrid | research | 旅行攻略、景点、酒店机票，属于 travel 下的“行程规划”入口 |
| `local_life` | hybrid | realtime | 餐厅美食、本地服务、周边推荐 |
| `calendar_task` | task | none | 日程管理、提醒设置、待办跟踪、会议、邮件、消息等办公任务入口 |
| `knowledge_general` | qa | research | 百科知识、原理解释、事实查询 |
| `finance_consumer` | qa | research | 理财、投资、贷款预算 |
| `health_wellness` | qa | research | 健康咨询、养生、症状科普 |
| `education_learning` | qa | research | 学习辅导、考试备考 |
| `work_productivity` | hybrid | research | 工作效率、办公协作、职业规划、项目推进 |
| `shopping_decision` | hybrid | research | 购物/商品/交易前决策、选购对比、性价比分析 |
| `policy_public_service` | qa | research | 政策解读、政务服务 |
| `emotion_companion` | qa | none | 情感陪伴、心理疏导 |
| `fortune_astrology` | qa | none | 星座运势、占卜趣味 |
| `search_fallback` | qa | research | 搜索兜底处理（系统级默认 skill） |

### 4.1 当前 15 个 skill 的领域 / 子领域 / 推荐技能映射

> 说明：这里的“推荐技能”是该领域或子领域下优先暴露给模型的入口，不是全部技能池。  
> 子领域是可选的；当领域本身足够单一时，可以直接由领域进入 skill。

| 当前 skill | 领域 | 子领域（可选） | 推荐技能 | 备注 |
|---|---|---|---|---|
| `weather` | `weather` | 无 | `weather` | 领域单一，直接到 skill |
| `travel_transport` | `travel` | `transport` | `travel_transport` | 旅行/出行统一大类下的交通/导航入口 |
| `travel_planning` | `travel` | `planning` | `travel_planning` | 旅行/出行统一大类下的行程/景点/酒店规划入口 |
| `local_life` | `local_life` | `food` / `place` / `service` | `local_life` | 本地生活总入口，不再拆过细 |
| `calendar_task` | `work_productivity` | `calendar` / `meeting` / `communication` / `task` / `project` | `calendar_task` | 归入办公/任务/生产力，覆盖日历、会议、邮件、消息 |
| `knowledge_general` | `knowledge_general` | 可选 `concept` / `translation` | `knowledge_general` | 当前保持扁平，后续按需求再细分 |
| `finance_consumer` | `finance` | `budget` / `loan` / `investment` / `insurance` | `finance_consumer` | 金融意图差异明显，建议子领域化 |
| `health_wellness` | `health` | `symptom` / `nutrition` / `sleep` / `exercise` | `health_wellness` | 健康咨询需细分问题族 |
| `education_learning` | `education` | `exam` / `tutoring` / `writing` / `planning` | `education_learning` | 学习场景常见路径较稳定 |
| `work_productivity` | `work` | `efficiency` / `career` / `project` | `work_productivity` | 办公/任务/生产力主域，承接日历、会议、邮件、消息、项目 |
| `shopping_decision` | `shopping` | `comparison` / `selection` / `deal` | `shopping_decision` | 购物/商品/交易前决策，承接选购、对比、优惠 |
| `policy_public_service` | `policy` | `procedure` / `materials` / `policy` | `policy_public_service` | 办事流程与材料清单建议拆分 |
| `emotion_companion` | `emotion` | 无 | `emotion_companion` | 陪伴类更适合保持扁平连续 |
| `fortune_astrology` | `fortune` | 无 | `fortune_astrology` | 趣味/娱乐类可直接到 skill |
| `search_fallback` | `system` | 无 | `search_fallback` | 系统级默认 skill，兜底承接 |

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
| **Phase-aware 加载实现** | phase owner 的 `_resolveSkillContext` 增加 `phase` 参数，加载 `reference_docs`/`script_guides` 对应文件 | 0.5d |
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
