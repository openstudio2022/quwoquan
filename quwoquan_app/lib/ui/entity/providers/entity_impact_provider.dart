import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_impact_summary.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 实体（共享主页）影响摘要数据源（按 homepageId 缓存）。
///
/// 与圈子影响（[circleImpactProvider]）同构：失败 / 加载 / 空数据由消费方收起，
/// 不在端侧拼装影响事实（G2 不造假、不占位）。
final entityImpactProvider = FutureProvider.autoDispose
    .family<EntityImpactSummary, String>((ref, homepageId) {
      return ref.watch(homepageQueryProvider).getEntityImpact(homepageId);
    });
