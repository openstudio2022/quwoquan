// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-006
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-002
// readiness_case: tag_node_view_resolve_tag_app_api
// readiness_case: tag_node_view_list_tag_children_app_api
// readiness_case: tag_node_view_validate_tag_refs_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/tag_api_contract_harness.dart';

void main() {
  TagApiContractHarness? harness;

  setUpAll(() async => harness = await TagApiContractHarness.create());
  tearDownAll(() async {
    final currentHarness = harness;
    if (currentHarness != null) {
      await currentHarness.close();
    }
  });

  test('generated Remote 解析 canonical tagRef', () async {
    final stopwatch = Stopwatch()..start();
    final resolved = await harness!.catalog.resolveTag('Topic/旅行');
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(1500));
    expect(resolved.tagRef, 'Topic/旅行');
    expect(resolved.label, isNotEmpty);
  });

  test('generated Remote 列出 tag children', () async {
    final children = await harness!.catalog.listChildren('Topic');

    expect(children, isNotEmpty);
    expect(children.every((child) => child.tagRef.isNotEmpty), isTrue);
  });

  test('不存在的 tagRef 保留 canonical not_found error', () async {
    await expectLater(
      harness!.catalog.resolveTag('Topic/nonexistent_tag_ref_000'),
      throwsA(
        isA<CloudException>().having(
          (error) => error.statusCode,
          'statusCode',
          404,
        ),
      ),
    );
  });

  test('generated Remote 以 active release 校验叶子并拒绝旧兴趣根', () async {
    var parentTagRef = 'Audience/用户/兴趣偏好';
    var leafTagRef = '';
    var taxonomyReleaseId = '';
    final visited = <String>{};
    for (var depth = 0; depth < 8 && leafTagRef.isEmpty; depth += 1) {
      expect(
        visited.add(parentTagRef),
        isTrue,
        reason: 'taxonomy must be acyclic',
      );
      final children = await harness!.catalog.listChildren(parentTagRef);
      expect(
        children,
        isNotEmpty,
        reason: 'active interest taxonomy is required',
      );
      final leafIndex = children.indexWhere((child) => !child.hasChildren);
      final candidate = leafIndex >= 0 ? children[leafIndex] : children.first;
      if (candidate.hasChildren) {
        parentTagRef = candidate.tagRef;
        continue;
      }
      leafTagRef = candidate.tagRef;
      taxonomyReleaseId = candidate.releaseId;
    }
    expect(
      leafTagRef,
      isNotEmpty,
      reason: 'active taxonomy must expose a leaf',
    );
    expect(taxonomyReleaseId, isNotEmpty);

    final validation = await harness!.catalog.validateRefs(
      expectedTaxonomyReleaseId: taxonomyReleaseId,
      tagRefs: <String>[leafTagRef, 'Topic/兴趣'],
    );

    expect(validation.taxonomyReleaseId, taxonomyReleaseId);
    expect(validation.valid, <String>[leafTagRef]);
    expect(validation.invalid, <String>['Topic/兴趣']);

    final events = await harness!.telemetry.waitForEvents(minimumCount: 1);
    final validationEvents = events
        .where(
          (event) =>
              event.canonicalOperationId ==
              AppCloudOperationIds.tagTagNodeViewValidateTagRefs,
        )
        .toList(growable: false);
    expect(validationEvents, hasLength(1));
    expect(validationEvents.single.succeeded, isTrue);
    expect(validationEvents.single.statusCode, 200);
    expect(validationEvents.single.requestId, isNotEmpty);
    expect(validationEvents.single.traceId, isNotEmpty);
  });
}
