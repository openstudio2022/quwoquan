/// 云端 JSON wire 的 SSOT 别名（非 metadata 生成物也可引用）。
///
/// 用于替代业务方法签名中重复的 `Map<String, dynamic>`，并与
/// [CloudResponseDecoder] / HTTP 解码路径对齐。
library;

/// `jsonDecode` 后 **对象** 根或 DTO `fromMap`/`fromJson` 输入。
typedef CloudJsonMap = Map<String, dynamic>;

/// HTTP 客户端单次响应经 `jsonDecode` 后的值（对象 / 列表 / 标量 / null）。
typedef CloudHttpDecodedJson = Object?;
