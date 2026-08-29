# ux · design

- [MUST] 页面 owner、typed presentation、route/surface 与设计系统边界唯一。
  evidence: app-page-object-contract
- [MUST] 状态、恢复、响应式和可访问性约束可被测试证明。
  check: 读取目标 design/GWT；任一约束无测试判据时判失败。
- [MUST NOT] 页面私有断点、硬编码 token 或平台字面分支形成第二套设计系统。
  check: 读取设计与 diff；命中任一私有规则时判失败。
