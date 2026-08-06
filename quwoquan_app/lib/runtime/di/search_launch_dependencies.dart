import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/actions/global_search_launch_port.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';

/// [GlobalSearchLaunchPort] 的 search 域 production 实现。
///
/// 只有本组合根文件可以构造 search 域的 [SearchLaunchContext]；
/// 全局壳层动作只依赖端口。
final class _SearchDomainGlobalSearchLaunchAdapter
    implements GlobalSearchLaunchPort {
  const _SearchDomainGlobalSearchLaunchAdapter();

  @override
  Future<void> open(
    BuildContext context, {
    required String entrySurfaceId,
    String initialScopeWire = 'all',
    String prefilledQuery = '',
  }) {
    return context.push(
      AppRoutePaths.globalSearch,
      extra: SearchLaunchContext(
        entrySurfaceId: entrySurfaceId,
        initialScope: SearchScope.fromWire(initialScopeWire),
        prefilledQuery: prefilledQuery,
      ),
    );
  }
}

final globalSearchLaunchPortProvider = Provider<GlobalSearchLaunchPort>(
  (ref) => const _SearchDomainGlobalSearchLaunchAdapter(),
);
