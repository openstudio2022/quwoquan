// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feedback-ingestion-sampling/spec.md#gwt-001

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/content/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/content/content/post/application/home_feed_post_open_action.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentPostProjection;

import '../../../../support/cloud_services/behavior_repository_double.dart';

const String _policyA =
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const String _policyB =
    'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

void main() {
  testWidgets(
    'home click and immersive route use the selected channel policyDigest',
    (tester) async {
      final reporter = MockBehaviorRepository();
      final recommendPost = _post('recommend-post');
      final campusPost = _post('campus-post');
      final extras = <MediaViewerExtra>[];
      late final GoRouter router;
      router = GoRouter(
        initialLocation: '/',
        routes: <RouteBase>[
          GoRoute(
            path: '/',
            builder: (context, state) => Consumer(
              builder: (context, ref, _) => Material(
                child: Column(
                  children: <Widget>[
                    TextButton(
                      key: const ValueKey<String>('open-recommend'),
                      onPressed: () => unawaited(
                        openHomeFeedPost(
                          context,
                          ref,
                          post: recommendPost,
                          mediaIndex: 0,
                          channelId: 'recommend',
                          feedPosts: <ContentPostViewData>[recommendPost],
                        ),
                      ),
                      child: const Text('recommend'),
                    ),
                    TextButton(
                      key: const ValueKey<String>('open-campus'),
                      onPressed: () => unawaited(
                        openHomeFeedPost(
                          context,
                          ref,
                          post: campusPost,
                          mediaIndex: 0,
                          channelId: 'campus',
                          feedPosts: <ContentPostViewData>[campusPost],
                        ),
                      ),
                      child: const Text('campus'),
                    ),
                  ],
                ),
              ),
            ),
          ),
          GoRoute(
            path: '/works/browser/:workId',
            builder: (context, state) {
              final extra = state.extra! as MediaViewerExtra;
              if (extras.isEmpty || !identical(extras.last, extra)) {
                extras.add(extra);
              }
              return const Material(child: Text('viewer'));
            },
          ),
        ],
      );
      addTearDown(router.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            behaviorReporterProvider.overrideWithValue(reporter),
            discoveryFeedMapProvider.overrideWith(
              () => _SeededFeedMap(<String, AsyncValue<DiscoveryFeedState>>{
                'recommend': AsyncData(
                  DiscoveryFeedState(
                    items: <ContentPostViewData>[recommendPost],
                    feedRequestId: 'frq_recommend',
                    policyDigest: _policyA,
                  ),
                ),
                'campus': AsyncData(
                  DiscoveryFeedState(
                    items: <ContentPostViewData>[campusPost],
                    feedRequestId: 'frq_campus',
                    policyDigest: _policyB,
                  ),
                ),
              }),
            ),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );

      await tester.tap(find.byKey(const ValueKey<String>('open-recommend')));
      await tester.pumpAndSettle();
      expect(extras.single.feedRequestId, 'frq_recommend');
      expect(extras.single.policyDigest, _policyA);
      expect(reporter.recorded.single.action, BehaviorEventType.click);
      expect(reporter.recorded.single.policyDigest, _policyA);

      router.pop();
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey<String>('open-campus')));
      await tester.pumpAndSettle();
      expect(extras.last.feedRequestId, 'frq_campus');
      expect(extras.last.policyDigest, _policyB);
      expect(reporter.recorded.last.action, BehaviorEventType.click);
      expect(reporter.recorded.last.policyDigest, _policyB);
    },
  );
}

final class _SeededFeedMap extends DiscoveryFeedMapNotifier {
  _SeededFeedMap(this.seed);

  final Map<String, AsyncValue<DiscoveryFeedState>> seed;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() => seed;
}

ContentPostViewData _post(String id) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: id,
      contentType: 'micro',
      contentIdentity: 'moment',
      assistantUsePolicy: 'allow',
      authorId: 'author-$id',
      authorDisplayName: 'Attribution Author',
      authorAvatarUrl: '',
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      body: 'Attribution body',
      mediaUrls: const <String>[],
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.utc(2026, 7, 29),
    ),
  );
}
