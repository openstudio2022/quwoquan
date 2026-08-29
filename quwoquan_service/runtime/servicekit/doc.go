// Package servicekit 是服务模块装配套件：把各 Go 服务 bootstrap 中重复的
// 运行时身份解析、配置快照加载与身份校验、Redis 场景路由、消息传输装配、
// 观测栈、auth 栈、通用 servicehost.Module 生命周期、standalone 壳与
// config sync 接入收敛为可复用构件。
//
// 三层边界（specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md DEC-027）：
//   - runtime/servicehost 拥有进程相位机与 Composition 身份；
//   - runtime/servicekit 拥有模块装配套件（本包）；
//   - 各服务 cmd/api bootstrap 只保留 config 结构体、env override 钩子与领域装配。
//
// 依赖边界：本包只允许依赖 runtime/* 与 internal/platform/*，
// 不得 import 任何服务的 internal、generated 或顶层共享 generated/**。
// 依赖 generated 产物的输入（operation guard、server timeouts、
// message binding descriptor、stream rootID）由服务 bootstrap 构造后以值对象传入。
package servicekit
