import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/public/recent_search_entry_view.dart';

/// RecentSearchState 对外公开的本地恢复存储 seam。
///
/// application/presentation 只认强类型状态；SharedPreferences、编码与命名空间
/// 哈希等实现细节留在 adapters，并由 runtime/di 负责装配。
abstract interface class RecentSearchHistoryStore {
  Future<RecentSearchHistorySnapshot> load();

  Future<void> save(RecentSearchHistorySnapshot snapshot);

  Future<void> clear();
}

/// 最近搜索本地可恢复状态。
final class RecentSearchHistorySnapshot {
  const RecentSearchHistorySnapshot({
    this.entries = const <RecentSearchEntryView>[],
    this.pendingUpsertKeys = const <String>{},
    this.pendingDeleteKeys = const <String>{},
    this.pendingClear = false,
  });

  final List<RecentSearchEntryView> entries;
  final Set<String> pendingUpsertKeys;
  final Set<String> pendingDeleteKeys;
  final bool pendingClear;
}
