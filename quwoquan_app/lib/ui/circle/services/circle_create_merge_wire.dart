import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_write_wire_dtos.dart';

/// 创建圈子后合并 wire 与远端返回，供 [CircleDto.fromMap] 使用。
Map<String, dynamic> mergeCreateCircleWireWithCreated(
  CircleCreateWireDto wire,
  CircleDto created,
) {
  final wireMap = wire.toMockMergeMap();
  final createdMap = created.toMap();
  return <String, dynamic>{
    ...wireMap,
    ...createdMap,
    'role': createdMap['role'] ?? 'owner',
    'joinStatus': createdMap['joinStatus'] ?? 'joined',
    'isFollowed': createdMap['isFollowed'] ?? true,
    'memberCount': createdMap['memberCount'] ?? 1,
    'postCount': createdMap['postCount'] ?? 0,
    'weeklyActiveCount': createdMap['weeklyActiveCount'] ?? 0,
    'createdAt': createdMap['createdAt'] ?? DateTime.now().toIso8601String(),
    'updatedAt': createdMap['updatedAt'] ?? DateTime.now().toIso8601String(),
  };
}
