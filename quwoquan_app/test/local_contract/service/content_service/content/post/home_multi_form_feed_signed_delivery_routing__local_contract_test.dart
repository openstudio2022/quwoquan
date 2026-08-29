// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_interaction_state.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/signed_grant_image.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AssistantUsePolicy,
        ContentPostProjection,
        MediaDeliveryAccessMode,
        MediaOriginalAccessGrant,
        PostMediaItem,
        RequestContentMediaOriginalAccessCommand;

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';

/// 对象级 typed double：grant 兑换永挂起，让 SignedGrantImage 停在占位态。
/// 接线测试只断言「typed 声明分流到桥接原子」，不消费兑换结果。
final class _HangingOriginalAccessGateway implements OriginalAccessQuotaGateway {
  final Completer<MediaOriginalAccessGrant> _never =
      Completer<MediaOriginalAccessGrant>();

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => _never.future;
}

/// 每个用例注入的静态 feed 内容（notifier 经 overrideWith 无参构造）。
List<ContentPostViewData> _feedItems = <ContentPostViewData>[];

final class _StaticFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(DiscoveryFeedState(items: _feedItems)),
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
  void applyConfirmedPosts(
    Iterable<ContentPostViewData> posts, {
    Set<String> pendingLikePostIds = const <String>{},
  }) {}
}

ContentPostViewData _post({
  List<String> mediaUrls = const <String>[],
  List<PostMediaItem>? mediaItems,
  String authorAvatarUrl = '',
  String? authorAvatarAssetId,
  MediaDeliveryAccessMode? authorAvatarAccessMode,
}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: 'post_signed_routing',
      contentType: 'micro',
      contentIdentity: 'moment',
      authorId: 'author_signed_routing',
      authorDisplayName: 'Routing Author',
      authorAvatarUrl: authorAvatarUrl,
      authorAvatarAssetId: authorAvatarAssetId,
      authorAvatarAccessMode: authorAvatarAccessMode,
      authorBackgroundUrl: null,
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      assistantUsePolicy: AssistantUsePolicy.inherit,
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.utc(2026, 8, 20),
      updatedAt: null,
      publishedAt: null,
      body: 'signed delivery routing contract content.',
      mediaUrls: mediaUrls,
      mediaItems: mediaItems,
      intersectionReasons: const [],
    ),
  );
}

Future<void> _pumpFeed(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(390, 844));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  final tracker = ContentBehaviorTracker(
    reporter: RecordingContentBehaviorRepository(),
    enablePeriodicFlush: false,
  );
  addTearDown(tracker.dispose);

  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        ...sealedCloudBoundaryOverrides(),
        contentBehaviorTrackerProvider.overrideWith((ref) => tracker),
        authSessionControllerProvider.overrideWith(
          _GuestAuthSessionController.new,
        ),
        contentFeatureFlagProvider(
          'enable_article_distribution_profiles',
        ).overrideWithValue(false),
        discoveryFeedMapProvider.overrideWith(_StaticFeedMapNotifier.new),
        postInteractionStateProvider.overrideWith(
          _NoopPostInteractionStateNotifier.new,
        ),
        signedMediaDeliveryCoordinatorProvider.overrideWithValue(
          SignedMediaDeliveryCoordinator(
            gateway: _HangingOriginalAccessGateway(),
          ),
        ),
      ],
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
}

void main() {
  testWidgets('signedGrant feed 图分流到 SignedGrantImage（kind=image），公开头像不受影响', (
    tester,
  ) async {
    const url = 'https://media.example.test/private/one.jpg';
    _feedItems = <ContentPostViewData>[
      _post(
        mediaUrls: const <String>[url],
        mediaItems: const <PostMediaItem>[
          PostMediaItem(
            kind: 'image',
            url: url,
            mediaAssetId: 'asset-feed-1',
            accessMode: MediaDeliveryAccessMode.signedGrant,
          ),
        ],
        authorAvatarUrl: 'https://cdn.example.test/avatar-public.jpg',
      ),
    ];
    await _pumpFeed(tester);

    expect(tester.takeException(), isNull);
    final signed = tester.widget<SignedGrantImage>(
      find.byType(SignedGrantImage),
    );
    expect(signed.assetId, 'asset-feed-1');
    expect(signed.kind, MediaDeliveryKind.image);
    expect(signed.accessMode, MediaDeliveryAccessMode.signedGrant);
  });

  testWidgets('public feed 图维持既有公开路径，不经私有媒体桥接原子', (tester) async {
    const url = 'https://cdn.example.test/public/one.jpg';
    _feedItems = <ContentPostViewData>[
      _post(
        mediaUrls: const <String>[url],
        // 存量 public 投影：契约缺席 accessMode。
        mediaItems: const <PostMediaItem>[PostMediaItem(kind: 'image', url: url)],
      ),
    ];
    await _pumpFeed(tester);

    expect(tester.takeException(), isNull);
    expect(find.byType(SignedGrantImage), findsNothing);
    final publicImages = tester
        .widgetList<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
        .where((image) => image.imageUrl == url);
    expect(publicImages, hasLength(1), reason: '公开媒体必须维持既有 AppCachedNetworkImage 路径');
  });

  testWidgets('signedGrant 作者头像分流到 SignedGrantImage（kind=avatar）', (tester) async {
    _feedItems = <ContentPostViewData>[
      _post(
        authorAvatarUrl: 'media/avatar/private-author.jpg',
        authorAvatarAssetId: 'asset-avatar-1',
        authorAvatarAccessMode: MediaDeliveryAccessMode.signedGrant,
      ),
    ];
    await _pumpFeed(tester);

    expect(tester.takeException(), isNull);
    final signed = tester.widget<SignedGrantImage>(
      find.byType(SignedGrantImage),
    );
    expect(signed.assetId, 'asset-avatar-1');
    expect(signed.kind, MediaDeliveryKind.avatar);
  });
}
