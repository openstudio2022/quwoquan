// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#open-007
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show
        gatheringDetailGatheringPostsReaderProvider,
        gatheringDetailSocialProofReaderProvider;
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_detail_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart'
    show ContentGatheringPostsReader, ContentGatheringSocialProofReader;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentGatheringPostsQuery, GatheringSocialProofSummary;

import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';
import '../../../../../support/service/circle_service/circle_management/gathering/gathering_test_support.dart';

// 漏斗辅证埋点契约（product_action 轨）：join 成功后触发
// gathering_flywheel/gathering_join_succeeded；埋点只记成功事实、
// 失败不阻断主流程；分子分母真相源仍是域事实投影（rec 漏斗读面）。

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

final class _ZeroSocialProofReader implements ContentGatheringSocialProofReader {
  @override
  Future<GatheringSocialProofSummary> getGatheringSocialProof({
    required String anchorKind,
    required String objectId,
  }) async {
    return GatheringSocialProofSummary(
      anchorKind: anchorKind,
      objectId: objectId,
      publishedCount: 0,
      formedCount: 0,
      experiencedCount: 0,
    );
  }
}

void main() {
  testWidgets('join 成功触发 gathering_flywheel 漏斗辅证埋点', (tester) async {
    final recorder = RecordingAppTelemetryRecorder();
    final port = InMemoryGatheringPort(
      detail: GatheringDetailPresentationSlice(
        publicDetail: publicGatheringDetail(),
        privateDetail: null,
      ),
    );
    await tester.binding.setSurfaceSize(const Size(430, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ...gatheringBoundaryOverrides(port),
          gatheringDetailGatheringPostsReaderProvider.overrideWithValue(
            _EmptyRecapReader(),
          ),
          gatheringDetailSocialProofReaderProvider.overrideWithValue(
            _ZeroSocialProofReader(),
          ),
          journeyEventTrackerProvider.overrideWithValue(
            JourneyEventTracker(telemetryReporter: recorder),
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

    await tester.ensureVisible(find.text(gatheringDetailTestCopy.joinAction));
    await tester.tap(find.text(gatheringDetailTestCopy.joinAction));
    await tester.pumpAndSettle();

    expect(port.joinCalls, 1);
    final actions = recorder.recorded
        .map((entry) => entry.action)
        .where((action) => action.isNotEmpty)
        .toList();
    expect(actions, contains('gathering_join_succeeded'));
  });
}
