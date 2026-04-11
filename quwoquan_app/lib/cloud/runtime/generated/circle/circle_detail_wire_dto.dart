/// 圈子详情响应中的「视角」投影（GetCircle 等路径 wire 顶层字段）。
///
/// 对齐：contracts/metadata/social/circle/projections/circle_detail_viewer_wire.yaml
class CircleDetailWireDto {
  const CircleDetailWireDto({
    this.role,
    this.joinStatus,
    this.isFollowed,
    this.categoryId,
  });

  final String? role;
  final String? joinStatus;
  final bool? isFollowed;
  final String? categoryId;

  factory CircleDetailWireDto.fromViewerWire(Map<String, dynamic> wire) {
    return CircleDetailWireDto(
      role: wire['role']?.toString(),
      joinStatus: wire.containsKey('joinStatus')
          ? (wire['joinStatus'] ?? 'none').toString()
          : null,
      isFollowed: wire.containsKey('isFollowed')
          ? wire['isFollowed'] as bool?
          : null,
      categoryId: wire['categoryId']?.toString(),
    );
  }
}
