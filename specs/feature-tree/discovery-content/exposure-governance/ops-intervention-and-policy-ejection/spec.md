# L3 Story：ops-intervention-and-policy-ejection

## 功能说明

商用推荐系统需要可审计的运营干预和内容治理剔除能力。人工加权、置顶、精品、热点等干预必须有入口、作用域、审计和回滚；违规或下架内容必须实时剔除推荐池。

## 范围

- 人工加权、置顶、精品、热点运营的策略入口规格。
- 干预作用域：channel、segment、content_id、tag、entity、time_window。
- 审计字段：operator、reason、scope、before/after、expiresAt、rollbackRef。
- 内容下架、审核失败、违规判定后的推荐池剔除延迟。

## 非目标

- 本轮不实现 product-ops 或 content-service 写入入口。
- 不绕过内容 eligibility、审核状态和单一真相源。

## 验收标准

- A1：运营干预不得直接改 UI 或本地 mock 列表。
- A2：所有干预必须可审计，可过期，可回滚。
- A3：违规/下架剔除进入 `policy_takedown_ejection_latency`。
- A4：干预审计覆盖率进入 `ops_intervention_audit_coverage`。
