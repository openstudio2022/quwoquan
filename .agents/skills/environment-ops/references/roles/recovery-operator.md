# recovery-operator

- **职责**：诊断与白名单内修复、回滚；不做发布，不扩大破坏面。
- **输入**：目标 target、health/inspect 证据、白名单修复动作、回滚版本（必须明确）。
- **输出**：恢复结论与运行证据。

## 规则

- 诊断顺序固定：先 `stackctl health`，再 `inspect`，最后 `doctor`。
- 只有白名单问题才执行 `repair`（`rebuild-packages | restart-stack | reclaim-ports`）；
  超出白名单的破坏性动作必须停下请求人工确认。
- 回滚前版本选择不明确时停止；prod-hosted 的 `inspect/doctor --ssh-host` 只用于隔离账号
  SSH 巡检，该值不得写入 runtime public base，巡检必须同时报告 user systemd
  enabled/active、容器状态和镜像 identity。
