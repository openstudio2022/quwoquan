/// 云客户端 `Map<String, dynamic>` 自查锚点（非 CI 门禁）。
///
/// **A — 合规**：codegen `XxxDto.fromMap` / `toMap`；HTTP 解码器单次 wire Map。
/// **B — Repository 内**：仅作 parse 输入，方法返回类型须为 DTO 或 `void`+out 参数，不得把业务 Map 当作对外契约。
/// **C — 待收敛**：Mock/Remote 分叉、Obs/Realtime 半结构化 payload 仍散落 Map 的，按域回填 metadata projection 后删除。
///
/// **StrictTyping（手写 `lib/cloud`）**：与助手策略一致，跨文件不得用裸 `dynamic`/`Object?` 作业务契约；`Object?` 仅见于解码入口（如 [CloudResponseDecoder]、[CloudHttpClient.getJson]）下一跳须转为 DTO 或 [CloudJsonMap]（`typedef`，见 `cloud_wire_json_types.dart`）的局部 parse。
library;
