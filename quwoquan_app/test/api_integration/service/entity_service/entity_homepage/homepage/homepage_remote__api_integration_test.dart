// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/entity_api_contract_harness.dart';

void main() {
  late EntityApiContractHarness harness;

  setUpAll(() async => harness = await EntityApiContractHarness.create());
  tearDownAll(() => harness.close());

  test('generated Remote 搜索共享主页返回 canonical slice', () async {
    final stopwatch = Stopwatch()..start();
    final slice = await harness.query.searchHomepages(
      HomepageSearchQuery(query: '北京', limit: 10),
    );
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(1500));
    expect(slice.items, isNotEmpty);
    expect(slice.items.every((item) => item.homepageId.isNotEmpty), isTrue);
  });

  test('不存在的 homepageId 保留 canonical not_found error', () async {
    await expectLater(
      harness.query.getHomepageDetail('nonexistent_homepage_000000'),
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
