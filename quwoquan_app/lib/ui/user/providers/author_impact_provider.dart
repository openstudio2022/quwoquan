import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/providers/provider_cache.dart';

/// 主页打动摘要数据源（他人主页 / 我的主页共用，按 userId 维度缓存）。
///
/// 失败时由消费方按 async 三态收起模块（不造假、不放占位数字）。
///
/// 短时缓存：我的主页同时挂载打动摘要与交集卡，且 push 进入「打动」详情后
/// 返回会重建消费方；90s TTL 让同一会话内的瞬时重建复用已取数据，避免重复
/// `GetAuthorImpact`（backlog R-ID09 验收项④）。
const Duration _authorImpactCacheTtl = Duration(seconds: 90);

/// 容器作用域打动缓存：随 ProviderContainer 释放回收，无定时器。
final _authorImpactCacheProvider = Provider<TtlCache<AuthorImpactSummary>>(
  (ref) => TtlCache<AuthorImpactSummary>(),
);

/// 摘要读取的主体与实际触发 surface；两者共同决定 generated operation 的调用上下文。
typedef AuthorImpactRequest = ({String personaId, AppUiSurface surface});

final authorImpactProvider = FutureProvider.autoDispose
    .family<AuthorImpactSummary, AuthorImpactRequest>((ref, request) async {
      final cache = ref.read(_authorImpactCacheProvider);
      final cacheKey = '${request.surface.id}:${request.personaId}';
      final hit = cache.readFresh(cacheKey, _authorImpactCacheTtl);
      if (hit != null) {
        return hit.value;
      }
      final summary = await ref
          .watch(authorImpactQueryProvider(request.surface))
          .getAuthorImpact(request.personaId);
      cache.write(cacheKey, summary);
      return summary;
    });
