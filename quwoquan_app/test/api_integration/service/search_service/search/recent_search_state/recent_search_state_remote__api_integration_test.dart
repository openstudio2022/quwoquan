// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/recent-search-sync-and-voice-asr/spec.md#gwt-001
// readiness_case: recent_search_state_list_recent_searches_app_api
// readiness_case: recent_search_state_upsert_recent_search_app_api
// readiness_case: recent_search_state_delete_recent_search_app_api
// readiness_case: recent_search_state_clear_recent_searches_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/search_api_contract_harness.dart';

void main() {
  test('RecentSearchState production Remote 完成写入、查询、删除与清空', () async {
    final harness = await SearchApiContractHarness.create();
    addTearDown(harness.close);
    final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    final scope = 'all';
    final firstQuery = 'qwq_nohit_recent_$nonce';
    final secondQuery = 'qwq_nohit_recent_${nonce}_clear';

    final first = await harness.withIdempotencyKey(
      'recent-upsert-$nonce',
      () => harness.recentSearch.upsertRecentSearch(
        UpsertRecentSearchCommand(query: firstQuery, scope: scope),
      ),
    );
    expect(first.entryId, isNotEmpty);
    expect(first.query, firstQuery);

    final replayed = await harness.withIdempotencyKey(
      'recent-upsert-$nonce',
      () => harness.recentSearch.upsertRecentSearch(
        UpsertRecentSearchCommand(query: firstQuery, scope: scope),
      ),
    );
    expect(replayed.entryId, first.entryId);

    final deduplicated = await harness.withIdempotencyKey(
      'recent-upsert-deduplicated-$nonce',
      () => harness.recentSearch.upsertRecentSearch(
        UpsertRecentSearchCommand(query: firstQuery, scope: scope),
      ),
    );
    expect(deduplicated.entryId, first.entryId);

    final listed = await harness.recentSearch.listRecentSearches(
      ListRecentSearchesQuery(scope: scope),
    );
    expect(listed.map((entry) => entry.entryId), contains(first.entryId));
    expect(
      listed.where((entry) => entry.entryId == first.entryId),
      hasLength(1),
    );

    await harness.withIdempotencyKey(
      'recent-delete-$nonce',
      () => harness.recentSearch.deleteRecentSearch(
        DeleteRecentSearchCommand(entryId: first.entryId),
      ),
    );
    final afterDelete = await harness.recentSearch.listRecentSearches(
      ListRecentSearchesQuery(scope: scope),
    );
    expect(
      afterDelete.map((entry) => entry.entryId),
      isNot(contains(first.entryId)),
    );

    final second = await harness.withIdempotencyKey(
      'recent-upsert-clear-$nonce',
      () => harness.recentSearch.upsertRecentSearch(
        UpsertRecentSearchCommand(query: secondQuery, scope: scope),
      ),
    );
    expect(second.entryId, isNotEmpty);

    await harness.withIdempotencyKey(
      'recent-clear-$nonce',
      () => harness.recentSearch.clearRecentSearches(
        ClearRecentSearchesCommand(scope: scope),
      ),
    );
    final afterClear = await harness.recentSearch.listRecentSearches(
      ListRecentSearchesQuery(scope: scope),
    );
    expect(afterClear, isEmpty);

    final events = await harness.telemetry.waitForEvents(minimumCount: 10);
    expect(events.every((event) => event.succeeded), isTrue);
    final searchEvents = events.where(
      (event) => <String>{
        AppCloudOperationIds.searchRecentSearchStateListRecentSearches,
        AppCloudOperationIds.searchRecentSearchStateUpsertRecentSearch,
        AppCloudOperationIds.searchRecentSearchStateDeleteRecentSearch,
        AppCloudOperationIds.searchRecentSearchStateClearRecentSearches,
      }.contains(event.canonicalOperationId),
    );
    expect(
      searchEvents.map((event) => event.canonicalOperationId).toSet(),
      <String>{
        AppCloudOperationIds.searchRecentSearchStateListRecentSearches,
        AppCloudOperationIds.searchRecentSearchStateUpsertRecentSearch,
        AppCloudOperationIds.searchRecentSearchStateDeleteRecentSearch,
        AppCloudOperationIds.searchRecentSearchStateClearRecentSearches,
      },
    );
    expect(
      searchEvents.every(
        (event) =>
            event.requestId.trim().isNotEmpty &&
            event.traceId.trim().isNotEmpty,
      ),
      isTrue,
    );
  });
}
