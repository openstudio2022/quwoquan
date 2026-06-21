import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/providers/provider_cache.dart';

/// 主页影响力摘要数据源（他人主页 / 我的主页共用，按 userId 维度缓存）。
///
/// 失败时由消费方按 async 三态收起模块（不造假、不放占位数字）。
///
/// 短时缓存：我的主页同时挂载影响力摘要与交集卡，且 push 进入「我的影响力」详情后
/// 返回会重建消费方；90s TTL 让同一会话内的瞬时重建复用已取数据，避免重复
/// `GetAuthorImpact`（backlog R-ID09 验收项④）。
const Duration _authorImpactCacheTtl = Duration(seconds: 90);

/// 容器作用域影响力缓存：随 ProviderContainer 释放回收，无定时器。
final _authorImpactCacheProvider = Provider<TtlCache<AuthorImpactSummary>>(
  (ref) => TtlCache<AuthorImpactSummary>(),
);

final authorImpactProvider = FutureProvider.autoDispose
    .family<AuthorImpactSummary, String>((ref, userId) async {
      final cache = ref.read(_authorImpactCacheProvider);
      final hit = cache.readFresh(userId, _authorImpactCacheTtl);
      if (hit != null) {
        return hit.value;
      }
      final summary = await ref
          .watch(userProfileRepositoryProvider)
          .getAuthorImpact(userId);
      cache.write(userId, summary);
      return summary;
    });
