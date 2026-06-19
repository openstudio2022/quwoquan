# 内容生产商用 SLO/KPI · 产能 · 成本 · 人审闭环（公共层机制）

> 本文件把整改计划第六阶段「运营专家视角」与「放量三档量化化」固化为可审计判据。
> 仅含跨垂类通用的运营机制与量化阈值；具体 region/batch 的目标值写任务 `notes.md`。

## 1. 质量 SLO/KPI（量化）

所有指标按批次（batch）滚动统计，进入仪表板字段。阈值为商用放量门槛，可随 golden set 标定调整。

| 指标 | 定义 | 商用阈值 | 数据来源 |
| --- | --- | --- | --- |
| 首过 approved 率 | produce review 一次通过（无 revision）篇数 / 总篇数 | ≥ 70% | `produce` review stage result |
| 人工返工率 | 人审判 revision/human_review 篇数 / 抽检篇数 | ≤ 15% | 人审账本 |
| 跨篇相似度 P95 | 同批 skeleton/simhash 相似度分布 P95 | ≤ 0.62 (n-gram) / ≤ 0.80 (simhash) | `_common/quality_gates` |
| 图文完备率 | 正文图文闭环通过篇数 / 总篇数 | = 100% | `imageReferenceClosure` |
| 事实回溯率 | mustIncludeFacts 可在 source 命中篇数 / 总篇数 | ≥ 95% | `factTraceability` |
| 读者阶段/题材覆盖率 | 实际题材配比与下单配比的吻合度 | ≥ 90% | content_plan vs 交付 |
| 机械稿逃逸率 | 抽检发现的"过机检但人审判机械"篇数 / 抽检篇数 | ≤ 5% | 人审 + golden set |
| 标题兑现率 | 标题承诺在正文或图片配文中被明确兑现的对象 / 总对象 | ≥ 95% | `Creative Quality Gate` |
| 信息密度合格率 | 每段提供新信息、无空泛套话的对象 / 抽检对象 | ≥ 90% | AI review + 人审抽检 |
| 非模板感合格率 | 无固定句式堆叠、无同构段落的对象 / 抽检对象 | ≥ 90% | reducer + 人审抽检 |
| 作者边界通过率 | 虚拟作者披露、无虚假亲历/资质/背书的对象 / 总对象 | = 100% | `Persona Boundary Gate` |
| 快速失败延迟 P95 | 不可恢复对象从发现到标记 abandoned/manual_required 的耗时 | ≤ 15 分钟 | object queue timing |
| stuck job 率 | 超 deadline 且未被 reaper 处理的 job / 总 job | = 0 | object queue summary |
| 单对象 token 预算命中率 | 未超预算且有 `TokenLedger` 的对象 / 总对象 | ≥ 98% | `TokenLedger` |

机检门（硬轨）拦截率/误杀率以 golden set 度量为准：拦截率 ≥ 95%、误杀率 ≤ 5%（见 `measure_gate_goldenset.py`）。

AI 自主创作质量按 [`agent_content_supply_operating_model.md`](agent_content_supply_operating_model.md) 的 Creative Workspace 和独立审校流程计量：只要事实、权利、载体和作者边界被锁定，AI 在标题、结构、叙事和表达上的创新应被鼓励；但所有创新必须通过标题兑现、信息密度、非模板感、证据边界和人格边界门。

## 2. 产能模型

端到端单篇耗时拆解（用于换算日产）：

```
日产目标 = 并发数 × (有效工时 / 单篇端到端耗时) × 首过率
单篇端到端耗时 = download(分摊) + compose-brief + agent 创作 + review + (repair 期望)
人审吞吐 = 抽检比例 × 日产 / 人审单篇工时
```

- 并发阶梯由 `object_queue` 配置：`concurrency=2`（试运行）→ `4`（稳定）→ 更高（仅 SLO 达标后）。
- 瓶颈点：高并发时 download IO 与 reducer 相似度计算为主要瓶颈；reducer 用 SimHash O(n·篇) 增量，避免全量两两爆炸。
- 同 `baseSourceRef` 互斥会降低有效并发，需在选题阶段分散底稿来源。

## 3. 成本模型

| 成本项 | 单位 | 说明 |
| --- | --- | --- |
| 创作 token | 元/篇 | Agent 单篇创作 + self-check + repair 期望次数 |
| rubric 评审 token | 元/篇 | LLM-as-judge 多次评分（按对象缓存，仅变更重评） |
| 图片/视频处理 | 元/篇 | media check-images（人脸/水印/OCR/去重） |
| 人审工时 | 元/篇 | 抽检比例 × 人审单篇工时 × 工时成本 |
| **单位合格内容成本** | 元/合格篇 | 总成本 / (交付篇 × 首过率) |

embedding/rubric 调用按对象增量缓存，避免规模化时算力爆炸。

## 4. 人审角色与 SLA

| 角色 | 职责 | SLA |
| --- | --- | --- |
| 总编辑 | 定义抽检比例与终裁；商用放量签字 | 抽检结论 ≤ 1 工作日 |
| 垂类编辑 | 维护题材矩阵、版面与禁用语域词表（注入 SOP `bannedRegisterTerms`） | 词表/题材更新 ≤ 2 工作日 |
| 标注/复核 | 单篇人审打分、机械稿标注、golden set 维护 | 单篇复核 ≤ 30 分钟，升级 ≤ 2 小时 |

升级路径：机检 dead（attempt 超限）→ 标注复核 → 垂类编辑 → 总编辑终裁。

## 5. 多样性运营

- 批次按题材配比下单（攻略/体验/咨询/路线/图集/视频脚本），避免同质堆积。
- 同 `baseSourceRef` 复用受控：reducer `source_reuse_risk` 标记需人工确认或重选底稿。

## 6. 放量三档（量化判据，替代主观"通过"）

| 档位 | 准入判据（全部满足） | 并发 |
| --- | --- | --- |
| **不可放量** | 任一硬门未全绿，或 golden set 拦截率 < 95% / 误杀率 > 5% | — |
| **可小批（≤10 篇）** | 单篇 + 第二篇不同 intent 样板通过机检与人审；首过率 ≥ 70%；图文完备率 100%；事实回溯率 ≥ 95% | 2 |
| **可试点放量（≤50 对象/天）** | 连续 2 个小批达标；机械稿逃逸率 ≤ 5%；跨篇相似度 P95 达标；人工返工率 ≤ 15%；成本/产能模型可算 | 4 |
| **规模化** | 试点连续达标 + 商用就绪 Gate（算法门 + 单一 gate library/队列幂等/测试接入 + SLO/产能/成本/人审闭环）全绿 + 总编辑签字 | 仅 SLO 达标后逐档提升 |

放量判定必须可审计：每档引用上述指标的实际值与阈值，不接受主观"看起来不错"。

## 7. 组织运行与协同 KPI

公司治理式 Agent 组织的运行质量也进入放量判据：

| 指标 | 定义 | 商用阈值 |
| --- | --- | --- |
| 职责分离覆盖率 | source、creative plan、authoring、review、release 由独立角色或独立 job 承担的对象占比 | = 100% |
| Envelope 采纳率 | 通过 `AgentResultEnvelope` 被 controller 采纳的完成对象 / 完成对象 | = 100% |
| Gate 单裁决率 | 每个对象每个 gate 只有一个最终 `GateVerdict` 的比例 | = 100% |
| 对象级修复率 | 失败后只重跑失败对象和失败阶段的次数 / 总修复次数 | ≥ 95% |
| 批次并发槽位利用率 | 活跃 job 数 / 配置并发上限的时间加权平均 | ≥ 80% |
| 反馈回流覆盖率 | 有消费或举报信号的对象产生 feedback packet 的比例 | ≥ 95% |
