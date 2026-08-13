// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show
        gatheringDetailGatheringPostsReaderProvider,
        gatheringDetailSocialProofReaderProvider;
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_detail_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart'
    show ContentGatheringPostsReader, ContentGatheringSocialProofReader;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentGatheringPostsQuery, GatheringSocialProofSummary;

import '../../../../../support/service/circle_service/circle_management/gathering/gathering_test_support.dart';

// 发起人往绩（organizer 锚点两级诚实计数）展示契约：
// - publishedCount > 0 才渲染「发起 N 次 · 成形 M 次 · 经历 K 次」；
// - 零发起或读取失败不渲染，不伪造；
// - 计数由 recommendation 聚合派生，页面只透传展示。

final class _EmptyRecapReader implements ContentGatheringPostsReader {
  @override
  Future<CursorPage<ContentPostViewData>> listPostsByGathering({
    required String gatheringId,
    String? cursor,
    int limit = ContentGatheringPostsQuery.defaultLimit,
  }) async {
    return const CursorPage<ContentPostViewData>(
      items: <ContentPostViewData>[],
      nextCursor: null,
    );
  }
}

final class _SocialProofReaderDouble
    implements ContentGatheringSocialProofReader {
  _SocialProofReaderDouble({this.summary, this.error});

  final GatheringSocialProofSummary? summary;
  final Object? error;
  String? lastAnchorKind;
  String? lastObjectId;

  @override
  Future<GatheringSocialProofSummary> getGatheringSocialProof({
    required String anchorKind,
    required String objectId,
  }) async {
    lastAnchorKind = anchorKind;
    lastObjectId = objectId;
    if (error != null) throw error!;
    return summary!;
  }
}

Future<void> _pumpDetail(
  WidgetTester tester, {
  required _SocialProofReaderDouble socialProof,
}) async {
  final port = InMemoryGatheringPort(
    detail: GatheringDetailPresentationSlice(
      publicDetail: publicGatheringDetail(),
      privateDetail: null,
    ),
  );
  await tester.binding.setSurfaceSize(const Size(430, 1200));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        ...gatheringBoundaryOverrides(port),
        gatheringDetailGatheringPostsReaderProvider.overrideWithValue(
          _EmptyRecapReader(),
        ),
        gatheringDetailSocialProofReaderProvider.overrideWithValue(
          socialProof,
        ),
      ],
      child: CupertinoApp(
        home: GatheringDetailPage(
          gatheringId: 'gathering-1',
          copy: gatheringDetailTestCopy,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('Gathering 发起人往绩展示 local_contract', () {
    testWidgets('发起 >0 时按 organizer 锚点渲染两级诚实计数', (tester) async {
      final reader = _SocialProofReaderDouble(
        summary: const GatheringSocialProofSummary(
          anchorKind: 'organizer',
          objectId: 'host-persona',
          publishedCount: 5,
          formedCount: 3,
          experiencedCount: 2,
        ),
      );
      await _pumpDetail(tester, socialProof: reader);

      expect(reader.lastAnchorKind, 'organizer');
      expect(reader.lastObjectId, 'host-persona');
      expect(
        find.byKey(GatheringDetailPage.organizerStatsKey),
        findsOneWidget,
      );
      expect(
        find.text(GatheringText.detailOrganizerStats(5, 3, 2)),
        findsOneWidget,
      );
    });

    testWidgets('零发起不渲染，不伪造', (tester) async {
      await _pumpDetail(
        tester,
        socialProof: _SocialProofReaderDouble(
          summary: const GatheringSocialProofSummary(
            anchorKind: 'organizer',
            objectId: 'host-persona',
            publishedCount: 0,
            formedCount: 0,
            experiencedCount: 0,
          ),
        ),
      );

      expect(find.byKey(GatheringDetailPage.organizerStatsKey), findsNothing);
    });

    testWidgets('读取失败静默缺席，不冒充计数', (tester) async {
      await _pumpDetail(
        tester,
        socialProof: _SocialProofReaderDouble(
          error: StateError('social proof unavailable'),
        ),
      );

      expect(find.byKey(GatheringDetailPage.organizerStatsKey), findsNothing);
      // 详情主体不受影响。
      expect(find.byKey(GatheringDetailPage.viewKey), findsOneWidget);
    });
  });
}
