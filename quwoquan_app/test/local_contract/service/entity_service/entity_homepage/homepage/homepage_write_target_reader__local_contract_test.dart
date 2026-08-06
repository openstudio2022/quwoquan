// spec_ref: specs/feature-tree/shared-homepage-network/spec.md#dom-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_write_target_reader.dart';

import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';

void main() {
  test('Homepage 只向认领与状态上报公开最小写目标投影', () async {
    final HomepageWriteTargetReader reader = MockHomepageRepository();

    final target = await reader.getHomepageWriteTarget(
      'homepage_sight_west_lake',
    );

    expect(target.homepageId, 'homepage_sight_west_lake');
    expect(target.title, '西湖景区');
    expect(target.status, 'published');
    expect(target.claimStatus, 'unclaimed');
  });
}
