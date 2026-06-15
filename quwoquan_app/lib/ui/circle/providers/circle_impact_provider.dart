import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_impact_summary.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 圈子影响摘要数据源（按 circleId 缓存）。
///
/// 失败、加载、空数据由消费方收起，不在端侧拼装影响事实。
final circleImpactProvider = FutureProvider.autoDispose
    .family<CircleImpactSummary, String>((ref, circleId) {
      return ref.watch(circleRepositoryProvider).getCircleImpact(circleId);
    });
