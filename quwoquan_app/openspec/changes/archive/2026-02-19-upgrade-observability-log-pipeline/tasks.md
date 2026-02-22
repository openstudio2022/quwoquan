## 1. OpenSpec 工件与规格增量

- [x] 1.1 创建 `upgrade-observability-log-pipeline` 变更工件（proposal/design/tasks/specs）
- [x] 1.2 新增日志目录与日志格式规范增量（开发态 + 商用态）
- [x] 1.3 新增“模拟器日志一键导出到项目 app_log”验收项

## 2. 日志基础设施层

- [x] 2.1 新增统一日志 schema/envelope 与 JSONL 写入器
- [x] 2.2 新增敏感字段脱敏器与商用态采样/提级策略
- [x] 2.3 新增日志路径解析与按日期目录写入能力

## 3. 业务埋点与交互链路

- [x] 3.1 接入页面访问日志（open/browse/return/exception）
- [x] 3.2 升级 agent run 日志为 input + interactions + output
- [x] 3.3 接入 LLM/search/cloud_api 请求与响应明细日志（无阶段抽象）
- [x] 3.4 接入性能统计日志（页面开关与关键操作）

## 4. 导出与联调

- [x] 4.1 实现模拟器日志一键导出到 `quwoquan_app/app_log/`
- [x] 4.2 增加导出结果提示（路径、run 数量、时间范围）
- [x] 4.3 完成天气问答链路联调与日志串联验证

## 5. 验证与回归

- [x] 5.1 运行静态检查与关键测试
- [x] 5.2 验证日志写入失败不影响主流程
- [x] 5.3 验证商用态策略：成功摘要/失败全量 + 动态提级
