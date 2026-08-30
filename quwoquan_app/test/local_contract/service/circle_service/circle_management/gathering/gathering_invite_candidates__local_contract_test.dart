// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show intersectionRepositoryProvider;
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_detail_page.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/gathering/gathering_test_support.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

// 婉拒后体面再邀契约：host 邀请控制台从「手填 personaId」升级为
// 「真实人对人交集候选点选 + 手填兜底」。
// - 候选来自发起者的人对人交集（objectKind=person，displayName/personaId 齐全）；
// - 点选候选填入邀请框，提交仍走同一 typed invite command（幂等键不变）；
// - 候选读取失败或为空只保留手填，不渲染空态、不阻断 host 控制台。

final class _PersonCandidateRepository implements IntersectionRepository {
  const _PersonCandidateRepository();

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return intersectionInboxSummaryFixture(totalCount: 2);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    return <IntersectionReason>[
      intersectionReasonFixture(
        dimension: 'place',
        intersectionId: 'ix_candidate_person',
        objectKind: 'person',
        actionTargetId: 'persona-candidate-1',
        displayName: '林清越',
        primaryText: '你和林清越都想去顶峰公园',
      ),
      // 人对物交集不得进入邀请候选。
      intersectionReasonFixture(
        dimension: 'place',
        intersectionId: 'ix_candidate_place',
        objectKind: 'place',
        actionTargetId: 'homepage-peak-park',
        displayName: '顶峰公园',
        primaryText: '你想去顶峰公园',
      ),
    ];
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

final class _FailingCandidateRepository implements IntersectionRepository {
  const _FailingCandidateRepository();

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    throw StateError('candidates unavailable');
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    throw StateError('candidates unavailable');
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

Future<void> _pumpHostDetail(
  WidgetTester tester, {
  required InMemoryGatheringPort port,
  required IntersectionRepository repository,
}) async {
  await tester.binding.setSurfaceSize(const Size(430, 1600));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        ...gatheringBoundaryOverrides(port),
        intersectionRepositoryProvider.overrideWithValue(repository),
      ],
      child: CupertinoApp(
        home: GatheringDetailPage(
          gatheringId: 'gathering-1',
          copy: gatheringDetailTestCopy,
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

InMemoryGatheringPort _hostPort() {
  return InMemoryGatheringPort(
    detail: GatheringDetailPresentationSlice(
      publicDetail: publicGatheringDetail(),
      privateDetail: privateGatheringDetail(authority: hostAuthority),
    ),
  );
}

void main() {
  testWidgets('人对人交集候选点选填入邀请框并经 typed invite 提交', (tester) async {
    final port = _hostPort();
    await _pumpHostDetail(
      tester,
      port: port,
      repository: const _PersonCandidateRepository(),
    );

    expect(find.text(GatheringText.inviteCandidatesLabel), findsOneWidget);
    final candidateChip = find.byKey(
      const ValueKey<String>('gathering-invite-candidate-persona-candidate-1'),
    );
    await tester.ensureVisible(candidateChip);
    expect(find.text('林清越'), findsOneWidget);
    // 人对物交集不进入候选。
    expect(
      find.byKey(
        const ValueKey<String>('gathering-invite-candidate-homepage-peak-park'),
      ),
      findsNothing,
    );

    await tester.tap(candidateChip);
    await tester.pump();
    await tester.ensureVisible(
      find.byKey(const ValueKey<String>('gathering-invite')),
    );
    await tester.tap(find.byKey(const ValueKey<String>('gathering-invite')));
    await tester.pumpAndSettle();

    expect(port.inviteCalls, 1);
    expect(port.lastInvite!.participantPersonaId, 'persona-candidate-1');
  });

  testWidgets('候选读取失败只保留手填兜底，不渲染候选区', (tester) async {
    final port = _hostPort();
    await _pumpHostDetail(
      tester,
      port: port,
      repository: const _FailingCandidateRepository(),
    );

    expect(find.text(GatheringText.inviteCandidatesLabel), findsNothing);
    expect(find.text(gatheringDetailTestCopy.personaIdLabel), findsWidgets);
  });
}
