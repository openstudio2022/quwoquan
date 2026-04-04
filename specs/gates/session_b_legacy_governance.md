# 会话 B：业务 Legacy 门禁

扫描目录（相对于 `quwoquan_app/lib`）：

- `ui/`
- `cloud/services/`
- `cloud/runtime/`
- `core/`

## 命令

```bash
# 报告（默认 exit 0）
python3 scripts/verify_session_b_legacy_governance.py
make verify-app-session-b-legacy

# Markdown 摘要
python3 scripts/verify_session_b_legacy_governance.py --markdown

# 收口：业务 Legacy 模式必须为 0
python3 scripts/verify_session_b_legacy_governance.py --enforce

# 另要求零 flutter_riverpod/legacy.dart import（业务代码须使用 Riverpod 3 主 API：
# Notifier / NotifierProvider / autoDispose.family 等；可与 `--enforce` 叠加）
python3 scripts/verify_session_b_legacy_governance.py --enforce --enforce-riverpod-legacy-zero
```

本地或 CI 若需与「零 legacy import」对齐，直接运行上条 `python3 ... --enforce --enforce-riverpod-legacy-zero`（或在 CI 脚本中等价调用）。

规范全文见已批准的「会话 B」实施计划（不重复粘贴）。
