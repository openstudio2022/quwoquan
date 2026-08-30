# ux · dev · flutter-page

- [MUST] 页面四态、恢复动作、响应式与可访问性均落地。
  check: 读取页面与测试；缺任一适用状态或恢复入口时判失败。
- [MUST] 页面依赖 typed presentation，并使用设计系统 token。
  evidence: app-page-object-contract
- [MUST NOT] 私有断点、硬编码样式、dynamic 展示模型或平台字面分支。
  check: 读取 diff；命中任一禁止形态时判失败。
