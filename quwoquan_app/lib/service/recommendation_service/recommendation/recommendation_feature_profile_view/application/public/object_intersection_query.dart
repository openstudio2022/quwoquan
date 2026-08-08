/// Recommendation 对象页交集查询的纯值请求。
///
/// Source owner 只负责提供当前用户与页面对象身份；具体 Remote 查询与展示由
/// runtime/di 绑定到 recommendation participant。
final class ObjectIntersectionQuery {
  const ObjectIntersectionQuery({
    required this.objectAId,
    required this.objectAType,
    required this.objectBId,
    required this.objectBType,
    this.limit = 6,
  });

  final String objectAId;
  final String objectAType;
  final String objectBId;
  final String objectBType;
  final int limit;

  bool get isResolvable =>
      objectAId.isNotEmpty &&
      objectBId.isNotEmpty &&
      !(objectAId == objectBId && objectAType == objectBType);

  @override
  bool operator ==(Object other) =>
      other is ObjectIntersectionQuery &&
      other.objectAId == objectAId &&
      other.objectAType == objectAType &&
      other.objectBId == objectBId &&
      other.objectBType == objectBType &&
      other.limit == limit;

  @override
  int get hashCode =>
      Object.hash(objectAId, objectAType, objectBId, objectBType, limit);
}
