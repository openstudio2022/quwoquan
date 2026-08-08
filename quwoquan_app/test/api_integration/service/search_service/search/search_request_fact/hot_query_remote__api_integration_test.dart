// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
// readiness_case: search_request_fact_list_hot_queries_app_api
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/search_api_contract_harness.dart';

void main() {
  test('production hot-query Remote returns one bounded typed slice', () async {
    final harness = await SearchApiContractHarness.create();
    addTearDown(harness.close);
    const requestedLimit = 6;

    final slice = await harness.hotQueries.listHotQueries(
      ListHotQueriesQuery(limit: requestedLimit),
    );

    expect(
      slice.items,
      isNotEmpty,
      reason: 'the real term-heat projection must return a query candidate',
    );
    expect(slice.items.length, lessThanOrEqualTo(requestedLimit));
    expect(
      slice.items.every(
        (item) => item.query.trim().isNotEmpty && item.relevance.isFinite,
      ),
      isTrue,
    );
    for (var index = 1; index < slice.items.length; index += 1) {
      expect(
        slice.items[index - 1].relevance,
        greaterThanOrEqualTo(slice.items[index].relevance),
      );
    }

    final events = await harness.telemetry.waitForEvents(minimumCount: 1);
    expect(events, hasLength(1));
    final event = events.single;
    expect(
      event.canonicalOperationId,
      AppCloudOperationIds.searchSearchRequestFactListHotQueries,
    );
    expect(event.succeeded, isTrue);
    expect(event.statusCode, 200);
    expect(event.requestId.trim(), isNotEmpty);
    expect(event.traceId.trim(), isNotEmpty);
  });
}
