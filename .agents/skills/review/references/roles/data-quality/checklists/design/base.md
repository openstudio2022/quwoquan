# data-quality · design

- [MUST] 数据对象、来源身份、阶段结果与恢复语义有唯一 owner。
  check: 读取目标 DEC 与 contracts；任一状态有多个可写 owner 或无 typed terminal 时判失败。
- [MUST] 发布、激活、readback 与 App 消费是彼此独立的证据终态。
  evidence: data-static-contract
- [MUST NOT] 用第二套 registry 或人工台账复制管线状态。
  check: 读取 diff；出现可写状态 registry/inventory/baseline 时判失败。
