import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_session_state.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_suggestion_models.dart';

void main() {
  group('SearchScope wire codec', () {
    test('按枚举声明的 canonical wireValue 解码，未知值回到 all', () {
      for (final scope in SearchScope.values) {
        expect(SearchScope.fromWire(scope.wireValue), scope);
      }
      expect(SearchScope.fromWire('unknown'), SearchScope.all);
      expect(SearchScope.fromWire(null), SearchScope.all);
    });
  });

  group('SearchObjectSelection', () {
    test('值相等与 Set 实例无关，hashCode 一致', () {
      const a = SearchObjectSelection(
        targets: {SearchObjectTarget.contacts},
        contentTypes: {SearchContentTypeFilter.article},
      );
      final b = SearchObjectSelection(
        targets: {SearchObjectTarget.contacts},
        contentTypes: {SearchContentTypeFilter.article},
      );
      expect(a, equals(b));
      expect(a.hashCode, b.hashCode);
    });

    test('枚举集合顺序不同仍相等', () {
      final a = SearchObjectSelection(
        contentTypes: {
          SearchContentTypeFilter.video,
          SearchContentTypeFilter.article,
        },
      );
      final b = SearchObjectSelection(
        contentTypes: {
          SearchContentTypeFilter.article,
          SearchContentTypeFilter.video,
        },
      );
      expect(a, equals(b));
      expect(a.hashCode, b.hashCode);
    });
  });

  group('SearchLaunchContext', () {
    test('字段相同则新建实例仍相等且 hash 一致', () {
      final a = SearchLaunchContext(
        entrySurfaceId: 'surface',
        prefilledQuery: 'hello',
        searchObjectSelection: const SearchObjectSelection(
          targets: {SearchObjectTarget.circles},
        ),
      );
      final b = SearchLaunchContext(
        entrySurfaceId: 'surface',
        prefilledQuery: 'hello',
        searchObjectSelection: SearchObjectSelection(
          targets: {SearchObjectTarget.circles},
        ),
      );
      expect(a, equals(b));
      expect(a.hashCode, b.hashCode);
    });

    test('prefilledQuery 不同则不等', () {
      final a = SearchLaunchContext(entrySurfaceId: 'x');
      final b = SearchLaunchContext(entrySurfaceId: 'x', prefilledQuery: 'y');
      expect(a, isNot(equals(b)));
    });
  });

  group('SearchSessionState', () {
    test('拆分后展示状态仍通过 search presentation models 强类型 API 暴露', () {
      const launchContext = SearchLaunchContext(entrySurfaceId: 'surface');
      const initial = SearchSessionState(launchContext: launchContext);

      expect(initial.viewMode, SearchViewMode.historyBrowse);

      final live = initial.copyWith(
        query: '川西',
        suggestionSections: const <SearchSuggestionSection>[
          SearchSuggestionSection(
            kind: SearchSuggestionSectionKind.network,
            items: <SearchSuggestionEntry>[
              SearchSuggestionEntry.network(
                NetworkSearchSuggestion(query: '川西露营'),
              ),
            ],
          ),
        ],
      );

      expect(live.viewMode, SearchViewMode.liveSuggestions);
      expect(
        live.suggestionSections.single.items.single.kind,
        SearchSuggestionEntryKind.network,
      );
    });
  });
}
