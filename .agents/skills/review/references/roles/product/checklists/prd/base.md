# product · prd

- [MUST] 用户、场景、价值与 In/Out Scope 明确。
  check: 读取 Story 开头与 scope；缺主体/场景/结果或任一 scope 侧时判失败。
- [MUST] L1/L2/L3 owner 唯一，验收锚点能绑定真实测试。
  evidence: feature-tree
- [MUST] 未完成能力进入最低可关闭节点的 OPEN，不写成现行事实。
  check: 对照实现/测试；无证据的现行 REQ 或悬空未决项时判失败。
- [MUST NOT] 建中央 registry、changelog 或第二套状态台账。
  check: 读取 diff；出现跨节点可写状态汇总时判失败。
