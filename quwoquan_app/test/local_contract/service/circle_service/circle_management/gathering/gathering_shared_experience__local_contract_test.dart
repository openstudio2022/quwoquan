// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-008

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_detail_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart'
    show ContentGatheringPostsReader;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantUsePolicy, ContentPostProjection, ContentGatheringPostsQuery;

import '../../../../../support/service/circle_service/circle_management/gathering/gathering_test_support.dart';

// 共同经历聚合区三态契约（诚实红线）：
// - ≥2 名不同作者公开关联 → 「共同经历」聚合；
// - 仅 1 名作者 → 「个人回顾」；
// - 0 条且行动已结束 → 「行动时间已结束」，不伪造内容；
// - 行动未结束且无内容、非参与者 → 区块不渲染；
// - active 参与者可见「发布回顾」入口并携带 (gatheringId, title) 进创作流。

ContentPostViewData _recapPost({required String id, required String authorId}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: id,
      contentType: 'image',
      contentIdentity: 'work',
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: authorId,
      authorDisplayName: '作者-$authorId',
      authorAvatarUrl: '',
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      body: '回顾内容 $id',
      coverUrl: '',
      mediaUrls: const <String>[],
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.utc(2026, 8, 9),
    ),
  );
}

final class _GatheringPostsReaderDouble implements ContentGatheringPostsReader {
  _GatheringPostsReaderDouble({this.posts = const <ContentPostViewData>[]});

  final List<ContentPostViewData> posts;
  String? lastGatheringId;

  @override
  Future<CursorPage<ContentPostViewData>> listPostsByGathering({
    required String gatheringId,
    String? cursor,
    int limit = ContentGatheringPostsQuery.defaultLimit,
  }) async {
    lastGatheringId = gatheringId;
    return CursorPage<ContentPostViewData>(items: posts, nextCursor: null);
  }
}

Future<InMemoryGatheringPort> _pumpDetail(
  WidgetTester tester, {
  required GatheringPublicDetailSlice publicDetail,
  required _GatheringPostsReaderDouble recapReader,
  void Function(String gatheringId, String gatheringTitle)? onPublishRecap,
}) async {
  final port = InMemoryGatheringPort(
    detail: GatheringDetailPresentationSlice(
      publicDetail: publicDetail,
      privateDetail: null,
    ),
  );
  await tester.binding.setSurfaceSize(const Size(430, 1200));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        ...gatheringBoundaryOverrides(port, gatheringPostsReader: recapReader),
      ],
      child: CupertinoApp(
        home: GatheringDetailPage(
          gatheringId: 'gathering-1',
          copy: gatheringDetailTestCopy,
          onPublishRecap: onPublishRecap,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return port;
}

void main() {
  group('Gathering 共同经历聚合区 local_contract', () {
    testWidgets('≥2 名不同作者公开关联 → 共同经历聚合列表', (tester) async {
      final reader = _GatheringPostsReaderDouble(
        posts: <ContentPostViewData>[
          _recapPost(id: 'post-1', authorId: 'persona-a'),
          _recapPost(id: 'post-2', authorId: 'persona-b'),
        ],
      );
      await _pumpDetail(
        tester,
        publicDetail: publicGatheringDetail(
          temporal: GatheringTemporalPhase.ended,
        ),
        recapReader: reader,
      );

      expect(reader.lastGatheringId, 'gathering-1');
      expect(
        find.byKey(GatheringDetailPage.sharedExperienceKey),
        findsOneWidget,
      );
      expect(
        find.text(gatheringDetailTestCopy.sharedExperienceTitle),
        findsOneWidget,
      );
      expect(find.text('回顾内容 post-1'), findsOneWidget);
      expect(find.text('回顾内容 post-2'), findsOneWidget);
    });

    testWidgets('仅 1 名作者 → 个人回顾，不冒充共同经历', (tester) async {
      final reader = _GatheringPostsReaderDouble(
        posts: <ContentPostViewData>[
          _recapPost(id: 'post-1', authorId: 'persona-a'),
          _recapPost(id: 'post-3', authorId: 'persona-a'),
        ],
      );
      await _pumpDetail(
        tester,
        publicDetail: publicGatheringDetail(
          temporal: GatheringTemporalPhase.ended,
        ),
        recapReader: reader,
      );

      expect(
        find.text(gatheringDetailTestCopy.sharedExperienceSingleTitle),
        findsOneWidget,
      );
      expect(
        find.text(gatheringDetailTestCopy.sharedExperienceTitle),
        findsNothing,
      );
    });

    testWidgets('0 条且行动已结束 → 诚实空态，不伪造内容', (tester) async {
      await _pumpDetail(
        tester,
        publicDetail: publicGatheringDetail(
          temporal: GatheringTemporalPhase.ended,
        ),
        recapReader: _GatheringPostsReaderDouble(),
      );

      expect(
        find.byKey(GatheringDetailPage.sharedExperienceKey),
        findsOneWidget,
      );
      expect(
        find.text(gatheringDetailTestCopy.sharedExperienceEndedEmpty),
        findsOneWidget,
      );
    });

    testWidgets('0 条且行动未结束、非参与者 → 区块不渲染', (tester) async {
      await _pumpDetail(
        tester,
        publicDetail: publicGatheringDetail(
          temporal: GatheringTemporalPhase.upcoming,
        ),
        recapReader: _GatheringPostsReaderDouble(),
      );

      expect(find.byKey(GatheringDetailPage.sharedExperienceKey), findsNothing);
      expect(find.byKey(GatheringDetailPage.publishRecapKey), findsNothing);
    });

    testWidgets('active 参与者可见发布回顾入口并携带行动上下文', (tester) async {
      String? recapGatheringId;
      String? recapTitle;
      await _pumpDetail(
        tester,
        publicDetail: publicGatheringDetail(
          temporal: GatheringTemporalPhase.inProgress,
          participationState: GatheringParticipationState.active,
        ),
        recapReader: _GatheringPostsReaderDouble(),
        onPublishRecap: (gatheringId, title) {
          recapGatheringId = gatheringId;
          recapTitle = title;
        },
      );

      final recapButton = find.byKey(GatheringDetailPage.publishRecapKey);
      expect(recapButton, findsOneWidget);
      await tester.ensureVisible(recapButton);
      await tester.tap(recapButton);
      await tester.pump();

      expect(recapGatheringId, 'gathering-1');
      expect(recapTitle, 'Public Gathering');
    });

    testWidgets('completed 后 active 非 host 参与者仍可见发布回顾入口（催回顾回链契约）', (
      tester,
    ) async {
      // 结束催回顾通知回链行动详情后，参与者必须能真的发出回顾：
      // host 完成行动不关闭 participation（云侧契约同源断言），
      // completed + active 的入口可见性在此钉死。
      String? recapGatheringId;
      await _pumpDetail(
        tester,
        publicDetail: publicGatheringDetail(
          lifecycle: GatheringLifecycleStatus.completed,
          temporal: GatheringTemporalPhase.ended,
          participationState: GatheringParticipationState.active,
          outcome: GatheringOutcomeStatus.occurred,
        ),
        recapReader: _GatheringPostsReaderDouble(),
        onPublishRecap: (gatheringId, title) => recapGatheringId = gatheringId,
      );

      final recapButton = find.byKey(GatheringDetailPage.publishRecapKey);
      expect(recapButton, findsOneWidget);
      await tester.ensureVisible(recapButton);
      await tester.tap(recapButton);
      await tester.pump();
      expect(recapGatheringId, 'gathering-1');
    });

    testWidgets('completed 后非参与者不出现发布回顾入口', (tester) async {
      await _pumpDetail(
        tester,
        publicDetail: publicGatheringDetail(
          lifecycle: GatheringLifecycleStatus.completed,
          temporal: GatheringTemporalPhase.ended,
          outcome: GatheringOutcomeStatus.occurred,
        ),
        recapReader: _GatheringPostsReaderDouble(),
      );
      expect(find.byKey(GatheringDetailPage.publishRecapKey), findsNothing);
    });
  });
}
