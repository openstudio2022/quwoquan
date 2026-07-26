import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  test('hot queries come from the immutable search fixture', () async {
    final reader = AlphaHotQueryReader();
    final slice = await reader.listHotQueries(ListHotQueriesQuery(limit: 3));

    expect(slice.items, hasLength(3));
    expect(
      slice.items.first.relevance,
      greaterThanOrEqualTo(slice.items.last.relevance),
    );
  });

  test(
    'recent search uses the server semantic key and stays bounded',
    () async {
      final facet = AlphaRecentSearchFacet(
        clock: () => DateTime.utc(2026, 7, 19),
      );

      final first = await facet.upsertRecentSearch(
        UpsertRecentSearchCommand(query: ' 成都旅行 ', scope: 'all'),
      );
      final replayedSemantic = await facet.upsertRecentSearch(
        UpsertRecentSearchCommand(query: '成都旅行', scope: 'ALL'),
      );
      expect(replayedSemantic.entryId, first.entryId);

      for (var index = 0; index < 15; index++) {
        await facet.upsertRecentSearch(
          UpsertRecentSearchCommand(query: 'query-$index', scope: 'all'),
        );
      }
      final slice = await facet.listRecentSearches(ListRecentSearchesQuery());
      expect(slice.items, hasLength(12));
    },
  );

  test(
    'recent search delete and scoped clear mirror the command facet',
    () async {
      final facet = AlphaRecentSearchFacet();
      final all = await facet.upsertRecentSearch(
        UpsertRecentSearchCommand(query: 'all', scope: 'all'),
      );
      await facet.upsertRecentSearch(
        UpsertRecentSearchCommand(query: 'posts', scope: 'posts'),
      );

      await facet.deleteRecentSearch(
        DeleteRecentSearchCommand(entryId: all.entryId),
      );
      await facet.clearRecentSearches(
        ClearRecentSearchesCommand(scope: 'posts'),
      );

      final slice = await facet.listRecentSearches(ListRecentSearchesQuery());
      expect(slice.items, isEmpty);
    },
  );

  test('search feedback dedupes the same semantic fact', () async {
    final writer = AlphaSearchFeedbackWriter();
    final command = ReportSearchFeedbackCommand(
      searchRequestId: 'req-1',
      eventType: SearchFeedbackEventType.click,
      objectId: 'post-1',
    );

    await writer.reportSearchFeedback(command);
    await writer.reportSearchFeedback(command);

    expect(writer.recorded, hasLength(1));
  });
}
