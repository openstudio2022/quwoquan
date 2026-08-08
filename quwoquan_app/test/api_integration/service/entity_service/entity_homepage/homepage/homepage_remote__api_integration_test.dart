// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-search-and-picker/spec.md#gwt-001
// readiness_case: homepage_search_homepages_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/entity_api_contract_harness.dart';

EntityApiContractHarness? _harness;

EntityApiContractHarness get _api => _harness!;

void main() {
  setUpAll(() async => _harness = await EntityApiContractHarness.create());
  tearDownAll(() => _harness?.close());

  test('generated Remote 搜索共享主页返回 canonical slice', () async {
    final stopwatch = Stopwatch()..start();
    final slice = await _api.query.searchHomepages(
      HomepageSearchQuery(query: '北京', limit: 10),
    );
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(1500));
    expect(slice.items, isNotEmpty);
    expect(slice.items.every((item) => item.homepageId.isNotEmpty), isTrue);

    final events = await _api.telemetry.waitForEvents(minimumCount: 2);
    final searchEvent = events.singleWhere(
      (event) =>
          event.canonicalOperationId ==
          AppCloudOperationIds.entityHomepageSearchHomepages,
    );
    expect(searchEvent.succeeded, isTrue);
    expect(searchEvent.statusCode, 200);
    expect(searchEvent.requestId, isNotEmpty);
    expect(searchEvent.traceId, isNotEmpty);
  });

  test('不存在的 homepageId 保留 canonical not_found error', () async {
    await expectLater(
      _api.query.getHomepageDetail('nonexistent_homepage_000000'),
      throwsA(
        isA<CloudException>().having(
          (error) => error.statusCode,
          'statusCode',
          404,
        ),
      ),
    );
  });
}
