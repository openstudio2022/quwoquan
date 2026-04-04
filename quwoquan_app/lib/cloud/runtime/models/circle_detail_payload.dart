import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';

/// [CircleRepository.getCircle] 的强类型封装：实体 [circle] + 视角相关 wire 字段。
///
/// [repositoryMergeBase] 仅供 Mock/Remote 在 [updateCircle] 等路径做 map 合并，UI 禁止依赖。
class CircleDetailPayload {
  CircleDetailPayload._(this.circle, this._wire);

  factory CircleDetailPayload.fromWire(Map<String, dynamic> wire) {
    final copy = Map<String, dynamic>.from(wire);
    return CircleDetailPayload._(CircleDto.fromMap(copy), copy);
  }

  final CircleDto circle;

  final Map<String, dynamic> _wire;

  String? get viewerRole => _wire['role']?.toString();

  /// Wire 未带 `joinStatus` 时返回 null，由调用方保留上一轮 UI 状态。
  String? get joinStatusIfPresent {
    if (!_wire.containsKey('joinStatus')) return null;
    return (_wire['joinStatus'] ?? 'none').toString();
  }

  /// Wire 未带 `isFollowed` 时返回 null，由调用方保留上一轮 UI 状态。
  bool? get isFollowedIfPresent =>
      _wire.containsKey('isFollowed') ? _wire['isFollowed'] as bool? : null;

  String? get categoryId => _wire['categoryId']?.toString();

  Map<String, dynamic> repositoryMergeBase() => Map<String, dynamic>.from(_wire);
}
