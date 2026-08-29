# observability · dev

- [MUST] trace/request、错误、日志、指标与告警跨端云同源且有真实 emitter。
  evidence: observability-catalog
- [MUST] 新增信号声明采样、保留、阈值与 owner。
  check: 读取新增 catalog 项；缺采样/保留/阈值/owner 任一项时判失败。
- [MUST NOT] 用目录声明或 dashboard 名称冒充运行时发射证据。
  check: 读取 emitter 与运行 evidence；只有声明无发射点时判失败。
