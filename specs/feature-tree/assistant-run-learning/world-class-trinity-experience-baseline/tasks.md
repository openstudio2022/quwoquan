# 开发任务：world-class-trinity-experience-baseline（重分解）

## 状态盘点（来自当前仓库）

- 已完成：天气链路隐私文案收敛、城市优先解析、本地定位失败后再追问、基础回归测试新增。
- 未完成：关键路径仍存在文本匹配分支；`md+json` 强契约未落地；Subagent 调度未接入主会话。

---

## Phase 0：冻结基线与风险清理（先做）

- [ ] P0-1 盘点并标记所有字符串判断分支（尤其 `llm_provider`、`react_runtime`），产出待替换清单。
- [ ] P0-2 确认 `assistant_run` metadata 现状与缺口（fields/errors/service 对协议支持度）。
- [ ] P0-3 定义灰度开关：`structured_decision_enabled`、`subagent_enabled`。

---

## Phase 1：协议化改造（P0，必做）

### A. metadata 扩展（对应 /qwq-extend 场景）

- [x] M1 (`S11 add-field`) 在 `assistant_run/fields.yaml` 增补协议字段：
  - `decisionJson`, `toolObservations`, `subagentRuns`, `renderMode`, `contractVersion`。
- [x] M2 (`S21 add-errors`) 完整化错误码：
  - `tool_observation_invalid`, `decision_parse_failed`, `subagent_timeout`, `subagent_contract_invalid`。
- [ ] M3 (`S25 add-test-contracts`) 增加协议契约测试元数据骨架（run/runStream/decision parsing）。

### B. codegen 与校验

- [x] C1 执行 `make verify-metadata`。
- [x] C2 执行 `make codegen` 与 `make codegen-app`。
- [ ] C3 校验 generated 产物无手改。

### C. 运行时改造

- [x] I1 引入 `assistant_turn_v2` 解析器（machine + markdown 双通道）。
- [x] I2 引入 `tool_observation_v1` 标准化器，替换关键字符串分支。
- [x] I3 天气垂类先接入结构化补槽（城市已知/未知/定位失败/工具失败）。
- [ ] I4 i18n key 渲染链路接入（决策层不再写死中文）。

---

## Phase 2：Subagent 与编排升级（P1）

- [x] S2-1 引入 `subagent_plan_v1`、`subagent_result_v1` 协议。
- [x] S2-2 在主 Agent 增加 `spawn_subagent` 决策执行器（带预算与超时）。
- [x] S2-3 子任务结果回注主会话并参与最终汇总。
- [x] S2-4 UI 增加 subagent timeline 事件显示。

---

## Phase 3：渲染与交互稳定化（P1）

- [x] U1 Markdown 结构块解析器稳定化（compare/trend/diagram）。
- [x] U2 解析失败降级路径统一（永不阻断主答复）。
- [x] U3 runStream 事件顺序一致性（trace/chunk/final）与前端消费治理。
- [x] U4 动作建议与补槽追问组件化（统一样式、统一可中断行为）。

---

## Phase 4：能力平台化（P2）

- [ ] X1 Prompt Stack 平台化（global/runtime/domain/recovery/output-contract）。
- [ ] X2 Skill DSL 标准化（manifest + slot_contract + tool_binding + response_style）。
- [ ] X3 私有数据 connector tools 接入规范与权限网关。
- [ ] X4 质量与成本看板（success rate、slot fill rate、latency、fallback ratio）。

---

## 测试分解（必须同步）

- [x] T1 单元：decision/tool-observation/subagent 协议解析。
- [ ] T2 单元：i18n key 映射与降级文案。
- [x] T3 组件：timeline + markdown blocks + subagent progress。
- [ ] T4 契约：run/runStream JSON shape + error mapping。
- [ ] T5 集成：remotePreferred/hybrid/localOnly 三路径一致性。
- [x] T6 回归：天气四主链 + 工具失败恢复链。

---

## 发布策略

- [ ] R1 先天气垂类灰度（10% -> 50% -> 100%）。
- [ ] R2 协议版本化：`assistant_turn_v2` 与旧路径并行两周。
- [ ] R3 关键指标门禁：`decision_parse_success >= 99.5%`、`render_fallback_rate < 1%`。

---

## 当前冲刺（本周可开工）

- [x] Sprint-1 完成 Phase 1 的 M1/M2/C1/C2/I1/I2/I3/T1/T6。
- [ ] Sprint-2 完成 Phase 2 的 S2-1/S2-2/S2-3/T3/T5（天气域先行）。

---

## Phase 5：规范与交付件落实（新标准）

- [x] D1 将 `skill_development_standard.md` 升级为“全流程标准”，不再局限于 Skill。
- [x] D2 生成个人助理全栈规范文档：`docs/personal-assistant/personal-assistant-fullstack-standard.md`。
- [x] D3 在 `docs/personal-assistant/README.md` 建立新规范索引与阅读顺序。
- [x] D4 在本节点 `design.md` 补齐组件/包图、用例图、流程图与映射表。
- [ ] D5 将“设计-任务-验收-测试”映射规则纳入自动检查（先 WARNING 后 BLOCKING）。
