# /explore

目标：只读澄清增量归属，不写代码。

必须输出：
- AppRoot Journey/Scenario：`<id 或无影响>`
- `L1_domain_service`：`<domain>`
- `L2_business_capability`：`<capability>`
- `L3_story`：`<story 或需新建>`
- 验收意图：UAT / SIT / GWT / contract
- 测试证据：T1 / T2 / T3 / T4
- metadata、seed、mock、页面质量、runtime error、发布风险

阻断：无法定位树归属、验收或测试证据时返回 `GATE_BLOCK`。
