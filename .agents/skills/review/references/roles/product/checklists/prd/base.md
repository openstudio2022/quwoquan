# product · prd

- [MUST] 用户、场景、价值与 In/Out Scope 明确。
  check: 读取 Story 开头与 scope；缺主体/场景/结果或任一 scope 侧时判失败。
- [MUST] L1/L2/L3 owner 唯一，验收锚点能绑定真实测试。
  evidence: feature-tree
- [MUST] 未完成能力进入最低可关闭节点的 OPEN，不写成现行事实。
  check: 对照实现/测试；无证据的现行 REQ 或悬空未决项时判失败。
- [MUST NOT] 建中央自然语言 resolver、第二流程正文、changelog 或跨节点状态台账。
  check: 读取 diff；出现复制 Skill 生命周期或跨节点可写状态汇总时判失败；Human/Review owner 内的版本化映射不按中央流程正文判否。
