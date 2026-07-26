// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/recent-search-sync-and-voice-asr/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/search_recent_history_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  late SearchRecentHistoryStore store;

  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    store = SearchRecentHistoryStore(actorNamespace: 'owner-a::persona-a');
  });

  test('本地最近搜索缓存以强类型记录往返', () async {
    final updatedAt = DateTime.utc(2026, 7, 24, 5, 30);
    final entry = RecentSearchEntryView(
      entryId: 'all%3A%3A%E8%A5%BF%E6%B9%96%3A%3A',
      query: '西湖',
      scope: SearchScope.all,
      facet: null,
      updatedAt: updatedAt,
    );

    await store.save(
      SearchRecentHistoryCacheSnapshot(
        entries: <RecentSearchEntryView>[entry],
        pendingUpsertKeys: const <String>{'all||西湖'},
        pendingDeleteKeys: const <String>{'all||已删除'},
        pendingClear: true,
      ),
    );
    final restored = await store.load();

    expect(restored.entries, hasLength(1));
    expect(restored.entries.single.entryId, entry.entryId);
    expect(restored.entries.single.query, entry.query);
    expect(restored.entries.single.scope, SearchScope.all);
    expect(restored.entries.single.facet, isNull);
    expect(restored.entries.single.updatedAt, updatedAt);
    expect(restored.pendingUpsertKeys, const <String>{'all||西湖'});
    expect(restored.pendingDeleteKeys, const <String>{'all||已删除'});
    expect(restored.pendingClear, isTrue);
  });

  test('损坏缓存显式失败，不能伪装为空历史', () async {
    await store.save(const SearchRecentHistoryCacheSnapshot());
    final prefs = await SharedPreferences.getInstance();
    final storageKey = prefs.getKeys().singleWhere(
      (key) => key.startsWith(SearchRecentHistoryStore.storageKeyPrefix),
    );
    await prefs.setString(storageKey, '{"query":"西湖"}');

    await expectLater(store.load(), throwsA(isA<FormatException>()));
  });

  test('不同账号与 Persona 物理隔离，旧全局缓存不迁移', () async {
    final updatedAt = DateTime.utc(2026, 7, 24, 5, 30);
    final entry = RecentSearchEntryView(
      entryId: 'remote-entry-a',
      query: '西湖',
      scope: SearchScope.all,
      facet: null,
      updatedAt: updatedAt,
    );
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      'global_search_recent_entries_v1',
      '[{"query":"不应迁移"}]',
    );
    await store.save(
      SearchRecentHistoryCacheSnapshot(entries: <RecentSearchEntryView>[entry]),
    );

    final otherPersona = SearchRecentHistoryStore(
      actorNamespace: 'owner-a::persona-b',
    );
    expect((await otherPersona.load()).entries, isEmpty);
    expect(
      (await store.load()).entries.map((item) => item.entryId),
      const <String>['remote-entry-a'],
    );
    expect(prefs.containsKey('global_search_recent_entries_v1'), isFalse);
  });
}
