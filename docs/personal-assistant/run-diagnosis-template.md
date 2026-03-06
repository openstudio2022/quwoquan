# Personal Assistant Run 诊断模板（通用版）

本模板用于排查一次复杂 Run（尤其是“过程空白 / 参考不相关 / 助手不可用 / 流式异常”）。

适用范围：

- 个人助理全链路（AgentLoop/ReAct/LLM/Tool/Search/UI）
- Debug 全量日志与 Release 采样日志
- 线上故障复盘、回归验证、质量门禁沉淀

---

## 1. 基本信息

- 诊断人：
- 日期：
- 环境：`debug | release`
- 平台：`iOS | Android | Web | Desktop`
- App 版本：
- 构建号：
- 领域来源（sourceDomain）：`assistant | content | discovery | chat | create | ...`
- 服务来源（sourceService）：`quwoquan_app | quwoquan_service | python_worker`
- 组件（component）：
- 交互对象（target）：
- 日志类型（logType）：`runtime | api | exception | audit | metric | business`
- 日志级别（level）：`debug | info | warn | error | fatal`
- 会话 ID（sessionId）：
- 运行 ID（runId）：
- 追踪 ID（traceId）：
- Span ID（spanId）：
- 父 Span ID（parentSpanId）：
- 请求 ID（requestId）：
- 云侧请求 ID（cloudRequestId）：
- Python 任务 ID（pythonJobId）：
- 关联 ID（correlationId）：
- 用户问题原文：
- 期望结果：
- 实际结果：

---

## 2. UI 现象记录（先用户视角）

- 页面路径（pageType）：
- 是否出现“助手暂时不可用”：
- 是否出现过程时间线空白：
- 是否出现 references 与问题不相关：
- 是否出现 JSON 原文泄漏：
- 是否出现“正在查询...”卡住：
- 是否可复现：`100% | 偶现`
- 复现步骤（精确到按钮/输入）：

---

## 3. 阶段诊断清单（S0~S11）

> 每个阶段填写：状态、证据日志、关键信息、异常点、结论。

## S0 模型配置装载

- 状态：`ok | degraded | error`
- 证据：
- 关键字段：`selectedSource / selectedModelRef / missingFields`
- 结论：

## S1 目录装载（模板/工具/路由）

- 状态：
- 证据：
- 关键字段：`catalogType / itemCount / catalogVersion`
- 结论：

## S2 历史与记忆装载

- 状态：
- 证据：
- 关键字段：`recallCount / filteredRecallCount / filterReasons`
- 结论：

## S3 上下文组装

- 状态：
- 证据：
- 关键字段：`canEnterDomain / missingSlots / fillTaskCount`
- 结论：

## S4 领域路由与 Skill 装载

- 状态：
- 证据：
- 关键字段：`candidateDomains / selectedDomain / selectedSkillId`
- 结论：

## S5 对话状态机脚本

- 状态：
- 证据：
- 关键字段：`currentStateId / detectedEvent / suggestedNextStateId`
- 结论：

## S6 模板渲染与变量填充

- 状态：
- 证据：
- 关键字段：`templateId / templateVersion / missingVariables`
- 结论：

## S7 LLM 调用与解析

- 状态：
- 证据：
- 关键字段：`statusCode / finishReason / toolCallsCount / parseStatus`
- 结论：

## S8 ReAct 工具执行与回灌

- 状态：
- 证据：
- 关键字段：`iteration / stepId / toolName / toolCallId / toolSuccess`
- 结论：

## S9 搜索 provider 链路

- 状态：
- 证据：
- 关键字段：`providerSelected / fallbackChain / authorityScore / freshnessHours`
- 结论：

## S10 流式输出与 UI 映射

- 状态：
- 证据：
- 关键字段：`streamChunkCount / chunkDropCount / renderMode / uiReferenceCount`
- 结论：

## S11 持久化写回

- 状态：
- 证据：
- 关键字段：`sessionWriteOk / memoryWriteOk / memoryTextSource`
- 结论：

---

## 4. 多日志对齐（Cross-Log Correlation）

- 统一检索入口（推荐）：`sourceDomain + sourceService + component + correlationId`
- `agent/interactions` 对齐：
- `integrations/llm` 对齐：
- `integrations/search` 对齐：
- `ui` 事件对齐：
- 云侧服务日志对齐：
- Python 工程日志对齐：
- 是否同一 `correlationId` 完整贯通端云：`是 | 否`
- 是否同一 `runId/traceId/spanId` 在单侧内完整贯通：`是 | 否`
- 若否，断点位置：

---

## 5. 根因归类

主根因（仅选 1）：

- [ ] 配置/装载问题（模型、模板、工具目录）
- [ ] 协议问题（tool_call_id、消息序列）
- [ ] 模型响应解析问题（choices/message 结构）
- [ ] 工具参数或执行问题
- [ ] 搜索可用性问题（timeout/network/provider）
- [ ] 搜索质量问题（无关 references、authority=0）
- [ ] 历史污染问题（session/memory/UI 回灌）
- [ ] 流式与 UI 渲染问题（chunk 过滤、timeline/references 映射）
- [ ] 其他：

次要根因：

---

## 6. 影响面评估

- 影响用户范围：
- 影响能力范围（weather/search/...）：
- 影响环境（debug/release）：
- 发生频率：
- 风险等级：`P0 | P1 | P2 | P3`

---

## 7. 修复方案（先策略后实现）

- 修复点 1：
  - 文件/模块：
  - 预期变化：
  - 验证点：
- 修复点 2：
- 修复点 3：

是否需要灰度：

---

## 8. 回归验证清单

- [ ] 同 query 连续 3 次运行结果稳定
- [ ] 不出现降级文案污染下一轮历史
- [ ] 不出现 JSON 原文泄漏
- [ ] timeline 不为空（有阶段数据）
- [ ] references 与 query 同域（抽样检查）
- [ ] release 模式下可通过 boost 拿到 full payload
- [ ] 端云 Python 三侧可通过 `correlationId` 贯通同一问题
- [ ] 日志五元组完整：`logType/level/component/target/action`
- [ ] 两层来源标识完整：`sourceDomain/sourceService`
- [ ] 对应 L0/L1/L2/L3 测试通过

---

## 9. 最终结论（对业务方可读）

- 问题摘要：
- 根因摘要：
- 是否与流量/限流相关：
- 当前状态：`已修复 | 缓解中 | 待修复`
- 下步动作与 ETA：

---

## 附录 A：常见 failureCode 速查

- `LLM_HTTP_400`：协议/参数错误
- `LLM_HTTP_429`：限流/配额
- `TOOL_PROTOCOL_MISMATCH`：tool_call 序列不一致
- `SEARCH_TIMEOUT`：搜索超时
- `SEARCH_QUALITY_INSUFFICIENT`：结果不相关或权威性不足
- `HISTORY_CONTAMINATION_GUARD_TRIGGERED`：历史污染拦截生效
- `RENDER_FILTER_OVERDROP`：UI 过滤过度导致展示空白

