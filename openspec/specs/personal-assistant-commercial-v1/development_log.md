# 个人私人助理商业化 v1 开发记录（App端）

## 范围声明

- 本轮实现范围限定于趣我圈 App 端。
- 云端接口与存储仅预留扩展位，默认走本地 mock。

## 已完成事项（对齐记录澄清）

1. 能力目录与逐步披露检索
   - `AssistantRunRequest` 增加 `capabilityCatalog/contextScopeHint/privacyProfile/privacyPolicy`
   - 引入 `unified_retrieval` 统一检索工具，支持按能力目录按需检索
   - `AgentLoop` 注入“能力目录 + 最小上下文锚点”，避免全量上下文塞入

2. 统一检索接口标准化
   - 新增 retrieval 协议模型：request/result/item/routeDecision
   - 新增 provider SPI 与路由服务
   - 接入四类 provider：web/memory/conversation/page_context
   - page_context 覆盖 discovery/circles/create/chat/home 差异化检索

3. 细粒度隐私策略（非一刀切）
   - 支持 capability/provider/pageType/webRound/redaction 细粒度控制
   - web 检索支持脱敏后出网（手机号/邮箱等）
   - 策略进入 router 与 service，并可在 context 中覆盖

4. 多轮 loop 策略
   - 支持按证据覆盖度与新增证据决定是否继续检索
   - 支持 round 级 query 扩展（如补“最新”）
   - 支持 web 轮次上限控制

5. 本地 mock 同步机制 + 一键切换
   - 新增 sync 模块：mode/adapter/gateway
   - 默认 `local_mock`，可切 `cloud_stub` 占位模式
   - 通过 provider 暴露 `assistentSyncGatewayProvider`

6. 使用即标注与双层评分（无权重）
   - 新增 learning 模块：interaction_event、metric_score、daily_aggregate
   - 评分输出按指标分项，不做加权综合分
   - 支持 user 维度与 tag×domain 维度聚合
   - 聊天问答回包后写入学习事件并走 sync gateway

7. UI 问题修复
   - 聊天气泡文本截断改为 clip，避免末字丢失
   - 聊天页新增显式标注入口：有帮助/没帮助/纠正
   - 开发态新增回放页：查询计划/策略决策/轮次轨迹/评分聚合快照
   - 回放页补齐显式标注统计视图：原因码分布 / domain 分布 / 用户标签分布

## 本次会话任务审视结论

- 本次会话中明确提出的开发任务均已闭环完成：
  - 逐步披露检索 + 统一检索标准化 + 多轮 loop
  - 本地 mock 优先 + 云端占位切换
  - 使用即标注 + 显式标注入口
  - 双层评分聚合（user、tag×domain）
  - 开发态回放页（含策略与统计视图）

## 后续可选增强（不影响当前验收）

1. 可观测闭环增强
   - 需要新增策略裁决 trace 字段：policyDecision/privacyActions/denyReasons
   - 需要在 retrieval service 输出每轮 evidence 质量日志

2. 策略中心增强
   - 需要将 privacyPolicy 与 loop 阈值统一归并到配置中心多层级命中（global/page/tag/session）

3. 本地验收面板
   - 已提供开发态回放页与统计视图；仍可增加按时间范围筛选与导出

## 验收建议（当前可执行）

- 场景回归：天气、创作优化、圈子相关、记录对话追问
- 隐私策略：allow/limited/deny 三档切换验证
- 检索策略：仅本地能力、混合能力、web 限轮能力验证
- 学习闭环：检查 learning_store 是否落盘、分项评分是否生成、mock sync 是否收到事件

