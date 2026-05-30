/// 发现流展示 wire 的强类型封装。
///
/// 替代 `ContentRepository.discoveryPresentationWireForPost` 既有的
/// `Map<String, dynamic>?` 裸返回（R04）。对消费方暴露强类型 getter；
/// 过渡期通过 [toLegacyRow] 兼容尚未迁移到 `ContentSurfaceView` 的 surface，
/// 待 D1b 四 surface 接入统一 model 后移除 [toLegacyRow]。
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

  /// 内容标签（已去空白、去空）。
  List<String> get tags {
    final raw = _fields['tags'];
    if (raw is List) {
      return raw
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return const <String>[];
  }

  /// 来源圈子名（无则空串）。
  String get circleName => _fields['circleName']?.toString().trim() ?? '';

  /// 可见性（默认 public）。
  String get visibility => _fields['visibility']?.toString() ?? 'public';

  /// 过渡期兼容：返回底层 wire row。
  ///
  /// 仅供尚未迁移到 `ContentSurfaceView` 的 surface 使用；统一 model 接入后移除。
  Map<String, dynamic> toLegacyRow() => _fields;
}
