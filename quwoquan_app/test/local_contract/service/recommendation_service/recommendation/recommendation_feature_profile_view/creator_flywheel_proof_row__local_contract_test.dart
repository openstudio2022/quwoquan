// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#req-005
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-005
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-008
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show profileHomeSocialProofReaderProvider;
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/creator_flywheel_proof_row.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

final class _StubSocialProofReader implements ContentGatheringSocialProofReader {
  _StubSocialProofReader({
    this.formed = 0,
    this.experienced = 0,
    this.failure,
  });

  final int formed;
  final int experienced;
  final Object? failure;
  String? requestedAnchorKind;
  String? requestedObjectId;

  @override
  Future<GatheringSocialProofSummary> getGatheringSocialProof({
    required String anchorKind,
    required String objectId,
  }) async {
    requestedAnchorKind = anchorKind;
    requestedObjectId = objectId;
    final error = failure;
    if (error != null) {
      throw error;
    }
    return GatheringSocialProofSummary(
      anchorKind: anchorKind,
      objectId: objectId,
      publishedCount: 0,
      formedCount: formed,
      experiencedCount: experienced,
    );
  }
}

List<Override> _boundaryOverrides(_StubSocialProofReader reader) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    profileHomeSocialProofReaderProvider.overrideWithValue(reader),
  ];
}

Future<void> _pumpRow(
  WidgetTester tester,
  _StubSocialProofReader reader, {
  String personaId = 'creator-1',
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: _boundaryOverrides(reader),
      child: CupertinoApp(
        home: CupertinoPageScaffold(
          child: CreatorFlywheelProofRow(personaId: personaId),
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  testWidgets('成形与经历两级计数按 creator 锚点直出（端不估算）', (tester) async {
    final reader = _StubSocialProofReader(formed: 3, experienced: 2);
    await _pumpRow(tester, reader);

    expect(reader.requestedAnchorKind, 'creator');
    expect(reader.requestedObjectId, 'creator-1');
    expect(find.byKey(CreatorFlywheelProofRow.rowKey), findsOneWidget);
    expect(
      find.text(
        DiscoveryFeedText.creatorFlywheelFormedLabel(3) +
            DiscoveryFeedText.creatorFlywheelExperiencedSuffix(2),
      ),
      findsOneWidget,
    );
  });

  testWidgets('经历为 0 只陈述成形事实（两级不互相冒充）', (tester) async {
    final reader = _StubSocialProofReader(formed: 1);
    await _pumpRow(tester, reader);
    expect(
      find.text(DiscoveryFeedText.creatorFlywheelFormedLabel(1)),
      findsOneWidget,
    );
  });

  testWidgets('成形为 0 整行不渲染（零计数不伪造社会证明）', (tester) async {
    final reader = _StubSocialProofReader();
    await _pumpRow(tester, reader);
    expect(find.byKey(CreatorFlywheelProofRow.rowKey), findsNothing);
  });

  testWidgets('读取失败静默不渲染（L0 氛围层，不阻塞主页）', (tester) async {
    final reader = _StubSocialProofReader(
      failure: StateError('social proof unavailable'),
    );
    await _pumpRow(tester, reader);
    expect(find.byKey(CreatorFlywheelProofRow.rowKey), findsNothing);
  });

  testWidgets('personaId 为空不发请求不渲染', (tester) async {
    final reader = _StubSocialProofReader(formed: 5);
    await _pumpRow(tester, reader, personaId: '  ');
    expect(reader.requestedAnchorKind, isNull);
    expect(find.byKey(CreatorFlywheelProofRow.rowKey), findsNothing);
  });
}
