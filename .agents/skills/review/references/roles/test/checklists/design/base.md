# test · design

- [MUST] 每个 command/query port 与失败终态已选定正确证据层。
  check: 读取设计的证据映射；任一 port/terminal 无层级时判失败。
- [MUST] 测试 double 只在对象级 local_contract，可达图不进入环境 App。
  check: 读取装配边界；double 可由环境入口导入时判失败。
- [MUST NOT] 以较低层证据替代 api_integration 或 user_acceptance。
  check: 对照验收意图与测试层；降层替代时判失败。
