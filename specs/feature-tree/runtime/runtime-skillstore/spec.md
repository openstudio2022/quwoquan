# L2 特性：runtime-skillstore

## 功能说明
- Skill Store：Skill 注册、版本管理、状态机（draft → review → approved → gray → published → archived）。
- 审核流程：自动检查（context scope 合理性、tool 依赖上限、DataClassMax 策略）+ 人工审核。
- 灰度发布：按流量百分比灰度，支持基线对比和效果评估。
- 沙箱配置：生态 Skill 资源限制（内存/CPU/超时/网络策略/API 白名单）。
- 指标采集：调用次数、成功率、延迟、用户评分。

## 约束
- 状态转换严格遵循有限状态机，非法转换拒绝。
- 生态 Skill 的 DataClassMax=SENSITIVE 自动审核不通过。
- 沙箱 NetworkPolicy 默认 internal，生态 Skill 不可 external。

## 验收标准
- A1：Skill 注册 → 审核 → 灰度 → 正式发布完整流程。
- A6：自动审核拦截过度权限的生态 Skill。
- A8：状态转换 + 自动审核全覆盖测试。
