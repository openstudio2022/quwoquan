# 助手子域弱类型边界约定（ASSISTANT_WEAK_TYPE）

与「模型交互」清理一致：业务语义不沿无名 `Map` 长距离传递；`dynamic` / `Object?` 仅出现在 **边界** 或 **明确标注** 的窄化函数。

## 标签语义（文件/类首行或紧邻弱类型 API）

| 标签 | 含义 |
|------|------|
| `JSON_BOUNDARY` | `jsonDecode`、持久化读写、与 Run/Trace 的 Map 往返；允许 `Map<String,dynamic>`，应尽快投影为 metadata 生成类型。 |
| `VENDOR_JSON` | 第三方 LLM / OpenAI 兼容 HTTP；允许供应商匿名 Map；优先用私有不可变 DTO（如 `LlmUsageLedgerEntry`）收窄对外暴露。 |
| `EXTENSION_MAP` | 协议故意保留的扩展桶（如 `structuredResponse` 未知键）；读路径应经 `AssistantRunStructuredBundle` / ReadView。 |
| `LLM_RAW` | 模型原始文本与流式拼接；解析完成后应落在 `AssistantTurnOutput` / `LlmParseResult`。 |

## 度量

弱类型统计脚本已随旧本地助理栈下线；当前仅保留本约定作为边界说明，不再维护独立趋势脚本。
