// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';

import '../../../../../support/runtime/api_contract/tag_api_contract_harness.dart';

void main() {
  late TagApiContractHarness harness;

  setUpAll(() async => harness = await TagApiContractHarness.create());
  tearDownAll(() => harness.close());

  test('generated Remote 解析 canonical tagRef', () async {
    final stopwatch = Stopwatch()..start();
    final resolved = await harness.catalog.resolveTag('Topic/旅行');
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(1500));
    expect(resolved.tagRef, 'Topic/旅行');
    expect(resolved.label, isNotEmpty);
  });

  test('generated Remote 列出 tag children', () async {
    final children = await harness.catalog.listChildren('Topic');

    expect(children, isNotEmpty);
    expect(children.every((child) => child.tagRef.isNotEmpty), isTrue);
  });

  test('不存在的 tagRef 保留 canonical not_found error', () async {
    await expectLater(
      harness.catalog.resolveTag('Topic/nonexistent_tag_ref_000'),
      throwsA(isA<CloudException>().having((error) => error.statusCode, 'statusCode', 404)),
    );
  });
}
