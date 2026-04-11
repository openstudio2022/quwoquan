/// GET /v1/circles/{circleId}/stats 等返回的统计 wire（松散 JSON，见合约
/// `quwoquan_service/contracts/metadata/social/circle/projections/circle_stats_wire.yaml`）。
///
/// 展示层请使用 [CircleStatsViewData.fromStatsWire]（见 `ui/circle/models/circle_stats_view_data.dart`）。
class CircleStatsWireDto {
  const CircleStatsWireDto({required this.raw});

  /// 原始键保留，便于观测与兼容别名（如 totalMembers / members）。
  final Map<String, dynamic> raw;

  factory CircleStatsWireDto.fromMap(Map<String, dynamic> m) {
    return CircleStatsWireDto(raw: Map<String, dynamic>.from(m));
  }
}
