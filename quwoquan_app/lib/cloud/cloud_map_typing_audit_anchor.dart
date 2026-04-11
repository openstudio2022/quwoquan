/// 云客户端 `Map<String, dynamic>` 自查锚点（非 CI 门禁）。
///
/// **A — 合规**：codegen `XxxDto.fromMap` / `toMap`；HTTP 解码器单次 wire Map。
/// **B — Repository 内**：仅作 parse 输入，方法返回类型须为 DTO 或 `void`+out 参数，不得把业务 Map 当作对外契约。
/// **C — 待收敛**：Mock/Remote 分叉、Obs/Realtime 半结构化 payload 仍散落 Map 的，按域回填 metadata projection 后删除。
library;
