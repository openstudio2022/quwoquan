# ux · prd

- [MUST] 页面成功、加载、空、错误、权限与恢复状态均有可验收描述。
  check: 读取页面 GWT；缺任一适用状态或恢复动作时判失败。
- [MUST] 响应式、可访问性与平台能力降级边界明确。
  evidence: feature-tree
- [MUST NOT] 把组件实现细节写成全局规则。
  check: 读取 diff；功能/组件事实落入根规则或角色时判失败。
