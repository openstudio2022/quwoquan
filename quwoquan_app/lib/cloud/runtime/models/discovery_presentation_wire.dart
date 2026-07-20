/// 发现流展示 wire 的强类型封装。
///
/// 发现流 DTO 需要显式保留扩展展示字段时使用的强类型边界（R04）。
/// 对消费方暴露强类型 getter；
/// [toWireMap] 把底层 canonical wire row 透传给统一映射器
/// [ContentSurfaceViewMapper.fromDto]（其 `tagRefs` / read-presentation 取数仍以
/// wire map 为入参）。
class DiscoveryPresentationWire {
  const DiscoveryPresentationWire(this._fields);

  /// 从底层 canonical wire row 构造；row 为空返回 null。
  static DiscoveryPresentationWire? fromRow(Map<String, dynamic>? row) {
    if (row == null) {
      return null;
    }
    return DiscoveryPresentationWire(row);
  }

  final Map<String, dynamic> _fields;

  /// 内容标签引用（已去空白、去空）。
  List<String> get tagRefs {
    final raw = _fields['tagRefs'];
    if (raw is List) {
      return raw
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return const <String>[];
  }

  /// 可见性（默认 public）。
  String get visibility => _fields['visibility']?.toString() ?? 'public';

  /// 透传底层 canonical wire row，供统一映射器
  /// [ContentSurfaceViewMapper.fromDto] 的 `wire` 入参消费。
  Map<String, dynamic> toWireMap() => _fields;
}
