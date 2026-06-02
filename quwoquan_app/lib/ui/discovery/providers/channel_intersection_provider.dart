import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 首页 / 频道交集推荐（事实 + 概率混排，过保鲜期/冷却窗口）。
///
/// 真相源 = content-service `GET /v1/content/feed/intersections?channel=`，
/// 端按 channelId 取数；alpha mock 经 [MockIntersectionRepository] 提供 campus/travel
/// 专属交集。无数据时返回空（不展示模块，G2 不造假）。
final channelIntersectionReasonsProvider = FutureProvider.autoDispose
    .family<List<IntersectionReason>, String>((ref, channelId) async {
      final repo = ref.watch(intersectionRepositoryProvider);
      return repo.getFeedIntersections(channel: channelId);
    });
