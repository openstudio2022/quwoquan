# test · dev · app

- [MUST] 对象级 typed double 与 production Remote composition 物理隔离。
  evidence: app-mock-isolation
- [MUST] 状态、错误恢复及关键视觉行为有可归因断言。
  check: 读取新增测试；只断言存在/非空或缺恢复终态时判失败。
- [MUST NOT] 删除像素/语义断言、动态 skip 或放宽期望让测试转绿。
  check: 对照测试 diff；命中任一弱化形态时判失败。
