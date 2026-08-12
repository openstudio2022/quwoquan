// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_interaction_state.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantUsePolicy, ContentPostProjection;

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';

final class _LifecycleFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(
        DiscoveryFeedState(
          items: <ContentPostViewData>[
            ContentPostViewData.fromWire(
              ContentPostProjection(
                postId: 'post_tracker_lifecycle',
                contentType: 'micro',
                contentIdentity: 'moment',
                authorId: 'author_tracker_lifecycle',
                authorDisplayName: 'Lifecycle Author',
                authorAvatarUrl: '',
                authorBackgroundUrl: null,
                authorRoleLabel: '',
                authorIdentityTags: const <String>[],
                authorVerified: false,
                assistantUsePolicy: AssistantUsePolicy.inherit,
                likeCount: 0,
                commentCount: 0,
                shareCount: 0,
                createdAt: DateTime.utc(2026, 8, 9),
                updatedAt: null,
                publishedAt: null,
                body: 'Tracker lifecycle contract content.',
                mediaUrls: const <String>[],
                intersectionReasons: const [],
              ),
            ),
          ],
        ),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.content,
    generation: 0,
  );
}

final class _GuestAuthSessionController extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}

final class _NoopPostInteractionStateNotifier
    extends PostInteractionStateNotifier {
  @override
  PostInteractionState build() => const PostInteractionState();

  @override
  void applyConfirmedPosts(Iterable<ContentPostViewData> posts) {}
}

final class _TrackerLifecycleProbe {
  int cancelCount = 0;
}

List<Override> _boundaryOverrides({required List<Override> extra}) =>
    <Override>[...sealedCloudBoundaryOverrides(), ...extra];

void main() {
  testWidgets(
    'cold content build keeps the behavior tracker subscribed for the frame',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final tracker = ContentBehaviorTracker(
        reporter: RecordingContentBehaviorRepository(),
        enablePeriodicFlush: false,
      );
      addTearDown(tracker.dispose);
      final probe = _TrackerLifecycleProbe();

      await tester.pumpWidget(
        ProviderScope(
          overrides: _boundaryOverrides(
            extra: <Override>[
              authSessionControllerProvider.overrideWith(
                _GuestAuthSessionController.new,
              ),
              contentFeatureFlagProvider(
                'enable_article_distribution_profiles',
              ).overrideWithValue(false),
              discoveryFeedMapProvider.overrideWith(
                _LifecycleFeedMapNotifier.new,
              ),
              postInteractionStateProvider.overrideWith(
                _NoopPostInteractionStateNotifier.new,
              ),
              contentBehaviorTrackerProvider.overrideWith((ref) {
                ref.onCancel(() {
                  probe.cancelCount += 1;
                });
                return tracker;
              }),
            ],
          ),
          child: CupertinoApp(
            home: ScreenUtilInit(
              designSize: const Size(390, 844),
              child: MediaQuery(
                data: const MediaQueryData(size: Size(390, 844)),
                child: HomeMultiFormFeed(
                  isDark: false,
                  channelId: 'recommend',
                  template: 'single_column_multiform',
                  onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(tester.takeException(), isNull);
      expect(
        probe.cancelCount,
        0,
        reason:
            'build must watch the tracker instead of performing a read-only '
            'subscription that is cancelled in the same frame',
      );
    },
  );
}
