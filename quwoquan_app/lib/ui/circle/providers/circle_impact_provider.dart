import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 圈子影响摘要数据源（按 circleId 缓存）。
///
/// 失败、加载、空数据由消费方收起，不在端侧拼装影响事实。
final circleImpactProvider = FutureProvider.autoDispose
    .family<CircleImpactSlice, String>((ref, circleId) {
      return ref
          .watch(circleDetailQueryProvider)
          .impact(CircleImpactQuery(circleId: circleId));
    });
