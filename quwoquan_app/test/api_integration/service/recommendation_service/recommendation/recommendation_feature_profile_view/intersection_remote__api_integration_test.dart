// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/recommendation_api_contract_harness.dart';

void main() {
  RecommendationApiContractHarness? harness;

  setUpAll(() async => harness = await RecommendationApiContractHarness.create());
  tearDownAll(() async {
    await harness?.close();
  });

  test('generated Remote 读取 my intersection summary', () async {
    final stopwatch = Stopwatch()..start();
    final summary = await harness!.intersections.getMyIntersectionSummary();
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(1500));
    expect(summary.totalCount, greaterThanOrEqualTo(0));
    expect(summary.dimensions, isA<List<IntersectionDimensionTally>>());
  });

  test('generated Remote 列出 my intersections inbox', () async {
    final inbox = await harness!.intersections.listMyIntersections(limit: 10);

    expect(inbox, isA<List<IntersectionReason>>());
  });
}
