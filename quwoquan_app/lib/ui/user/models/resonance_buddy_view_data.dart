import 'package:flutter/foundation.dart';

/// 「我的交集」推荐趣友原型行（清单目标 UserWorkDto 为作品侧；趣友卡为独立 UI 模型，无页内 Map）。
@immutable
class ResonanceBuddyViewData {
  const ResonanceBuddyViewData({
    required this.profileSubjectId,
    required this.displayName,
    required this.avatarUrl,
    required this.bio,
    required this.resonancePoints,
  });

  final String profileSubjectId;
  final String displayName;
  final String avatarUrl;
  final String bio;
  final int resonancePoints;

  Map<String, dynamic> toWireMap() => <String, dynamic>{
    'profileSubjectId': profileSubjectId,
    'displayName': displayName,
    'avatarUrl': avatarUrl,
    'bio': bio,
    'resonancePoints': resonancePoints,
  };

  factory ResonanceBuddyViewData.fromWireMap(Map<String, dynamic> m) {
    return ResonanceBuddyViewData(
      profileSubjectId: (m['profileSubjectId'] ?? '').toString(),
      displayName: (m['displayName'] ?? '').toString(),
      avatarUrl: (m['avatarUrl'] ?? '').toString(),
      bio: (m['bio'] ?? '').toString(),
      resonancePoints: (m['resonancePoints'] as num?)?.toInt() ?? 0,
    );
  }

  /// 与历史 ResonanceDashboard 一致的演示数据（Remote 未接交集 API 前）。
  static const List<ResonanceBuddyViewData> prototype = <ResonanceBuddyViewData>[
    ResonanceBuddyViewData(
      profileSubjectId: 'res_u1',
      displayName: '陈摄影师',
      avatarUrl:
          'https://images.unsplash.com/photo-1603987248955-9c142c5ae89b?q=80&w=150',
      bio: '徕卡玩家 / 极简主义者',
      resonancePoints: 12,
    ),
    ResonanceBuddyViewData(
      profileSubjectId: 'res_u2',
      displayName: '阿强',
      avatarUrl:
          'https://images.unsplash.com/photo-1755519024555-a660fefc8dc3?q=80&w=150',
      bio: '阿那亚常客 / 自由撰稿人',
      resonancePoints: 9,
    ),
    ResonanceBuddyViewData(
      profileSubjectId: 'res_u3',
      displayName: 'Sarah',
      avatarUrl:
          'https://images.unsplash.com/photo-1643816831234-e7cb32194e92?q=80&w=150',
      bio: '胶片摄影爱好者',
      resonancePoints: 8,
    ),
  ];
}
