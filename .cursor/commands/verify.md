# /verify

目标：以同一规格父链审核增量是否真实达成。

检查：

1. `make feature-context TARGET=<target>` 的 REQ/UAT/DOM/SIT/GWT/DEC 是否与代码和行为一致。
2. `local_contract / api_integration / user_acceptance` 是否覆盖对应验收锚点；测试结果而非文档状态是证据。
3. metadata/codegen、Mock↔Remote、runtime error、权限、生命周期、页面四态、性能、安全隐私、可靠性、观测、配置、灰度和回滚是否适用并有证据。
4. 跨域变更是否证明 Data → Service → App → Behavior → Recommendation → Observability → Environment 无断点。
5. `make verify-feature-tree` 和 `make feature-tree-change-report` 是否通过；不得有未归属业务变更。
6. 已完成 OPEN 是否删除并转为当前规格；未完成项是否仍位于最低 owner 节点。

输出通过/阻断、证据、未跑验证原因和 Exit Review。任何适用维度无证据、OPEN `block` 未解决或测试失败时返回 `GATE_BLOCK`。

自然语言等价触发：“验证”“检查是否完成”“收口”。
