# Observability output contract

运行观测只保留 `logs`、`metrics`、`traces` 三类信号。环境运行写入：

```text
.qwq_output/env/<env>/observability/<runId>/
  manifest.json
  logs/
  metrics/
  traces/
  attachments/
```

数据内容执行不建立第二个观测根。任务事件和质量指标属于同一工作包，写入
`.qwq_output/data/tasks/<executionId>/evidence/`；ship/import 的环境观测写入对应
`.qwq_output/env/<env>/observability/<runId>/`，并由
`.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/links.json` 关联。

`manifest.json` 持有 env、runId、releaseId、dataReleaseId、gitSha 和
schema。日志行不重复这些上下文。

## 日志类型

只允许六个文件名：

- `deploy.log`：CI/CD 和 stackctl 步骤。
- `runtime.log`：服务生命周期与内部事件。
- `access.log`：HTTP、RPC、MQ 与 App 请求。
- `event.log`：App 或数据任务事件。
- `exception.log`：异常与失败。
- `audit.log`：运维或特权操作。

每条记录为逗号分隔文本，不使用 JSONL。固定前缀从 `ts,level` 开始，`msg`
永远是最后一列；可能含逗号、自由文本、属性或堆栈的内容全部并入 `msg`。
堆栈续行必须以空白开头，新记录必须匹配 ISO 时间与
`,DEBUG|INFO|WARN|ERROR,`。

字段顺序：

- `deploy.log`：`ts,level,step,result,msg`
- `runtime.log`：`ts,level,event,result,req,trace,msg`
- `access.log`：`ts,level,method,route,status,durMs,req,trace,msg`
- `event.log`：`ts,level,event,result,req,trace,msg`
- `exception.log`：`ts,level,err,req,trace,msg`
- `audit.log`：`ts,level,action,target,result,msg`

版本、环境、服务、实例、run、release 和 session 上下文只放路径、collector
labels 或 manifest。统计数据进入 `metrics/snapshot.json` 或
`metrics/prometheus.prom`；trace 只保留 `traces/links.json`，全量 span 进入后端。

`.qwq_output/env/<env>/runs/` 是报告与证据目录，不是日志目录。run 目录只保留
`report.json`、`summary.json`、`summary.md` 与 `links.json`；原始日志、trace dump
和临时 stdout/stderr 进入对应 observability run 或外部观测后端。
