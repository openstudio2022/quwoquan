# L5 横切能力：skill-store-and-ecosystem

## 功能说明
- Skill Store 管理服务：Skill 注册/发布/版本管理/审核/评分。
- 沙箱执行环境：Ecosystem Skill 资源隔离。
- 用户端 Skill 发现 + 安装 + 授权管理界面。
- Skill 版本灰度 + 效果评估 + 自动择优。

## 约束
- Ecosystem Skill 必须在沙箱中执行，不得直接访问生产数据库。
- Skill 发布必须经过审核。

## 验收标准
- A1：Skill 注册 → 审核 → 灰度发布 → 用户安装 → 使用。
- A3：沙箱隔离 + 灰度 + 效果评估。
- A5：运营管理全流程。
- A6：安全隔离 + 数据不泄露。
