## 1. 规格归并与基线冻结

- [x] 1.1 创建 `personal-assistant-commercial-v1` change 工件（proposal/specs/design/tasks）
- [x] 1.2 将商业化能力规格统一归并到 `openspec/specs/personal-assistant-commercial-v1/spec.md`
- [x] 1.3 在 change specs 中声明统一规格目录与验收入口

## 2. 平台化能力对齐（已实现核验）

- [x] 2.1 对齐 ReAct++ 推理循环与多步重规划能力（Plan/Act/Observe/Reflect/Replan）
- [x] 2.2 对齐知识问答策略链与结构化输出（结论/依据/不确定性）
- [x] 2.3 对齐 skill 商业治理字段与网关侧约束校验
- [x] 2.4 对齐 Adapter SPI 非侵入接入与 Feishu/OpenClaw 首发能力
- [x] 2.5 对齐 provider 策略路由、运行时状态与临时禁用机制

## 3. 生产强化闭环（已实现核验）

- [x] 3.1 对齐 SLO 评估与告警等级触发
- [x] 3.2 对齐告警策略路由（日志/Webhook/Feishu）与抑制窗口
- [x] 3.3 对齐 critical 自动降级（禁用异常 provider）与人工恢复接口
- [x] 3.4 对齐成本账本、审计日志与灰度门禁观测项

## 4. 灰度与商用验收

- [x] 4.1 固化 24h 灰度操作序列与回滚阈值
- [x] 4.2 固化 canary/告警路由/渠道联调命令清单
- [x] 4.3 完成 OpenSpec apply 可执行状态校验（all_done）
