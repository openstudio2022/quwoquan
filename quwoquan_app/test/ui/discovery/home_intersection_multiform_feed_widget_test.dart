import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/spacing/discovery_feed_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/home_multi_form_feed.dart';
import 'package:shared_preferences/shared_preferences.dart';

TextSpan _spanByText(RichText richText, String text) {
  TextSpan? result;
  richText.text.visitChildren((span) {
    if (span is TextSpan && span.text == text) {
      result = span;
      return false;
    }
    return true;
  });
  return result!;
}

int _fontWeightValue(TextSpan span) =>
    span.style?.fontWeight?.value ?? FontWeight.normal.value;

IntersectionReason _reason({String intersectionClass = 'fact'}) {
  final target = IntersectionTarget(
    objectId: 'fixture_user_lin',
    objectKind: 'person',
    routeId: 'userProfile',
  );
  return IntersectionReason(
    dimension: 'relationship',
    intersectionId: 'ix_post_lin',
    intersectionClass: intersectionClass,
    objectKind: 'person',
    source: 'sharedFollowees',
    pointSummarySnapshotId: 'snap_lin',
    primaryText: '你与林清越等 3 位都来这里互动过',
    primarySpans: <IntersectionTextSpan>[
      IntersectionTextSpan(text: '你与', role: 'plain'),
      IntersectionTextSpan(text: '林清越', role: 'object', target: target),
      IntersectionTextSpan(text: '等 ', role: 'plain'),
      IntersectionTextSpan(
        text: '3',
        role: 'count',
        target: IntersectionTarget(
          objectId: 'relationship',
          objectKind: 'tag',
          routeId: 'myIntersections',
        ),
      ),
      IntersectionTextSpan(text: ' 位都来这里互动过', role: 'plain'),
    ],
    sampleVisuals: <IntersectionVisual>[
      IntersectionVisual(
        assetKind: 'avatar',
        imageUrl: '',
        displayName: '林清越',
        target: target,
      ),
    ],
  );
}

MicroPostDto _microPost({
  List<String> imageUrls = const <String>[
    'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
  ],
  IntersectionReason? reason,
  String avatarUrl = '',
}) {
  final effectiveReason = reason ?? _reason();
  return MicroPostDto(
    id: 'post_intersection_demo_${effectiveReason.intersectionClass}_${imageUrls.length}',
    type: 'moment',
    identity: 'moment',
    authorId: 'user_demo',
    displayName: '小趣用户',
    avatarUrl: avatarUrl,
    authorBackgroundUrl: null,
    authorRoleLabel: '旅行创作者',
    authorIdentityTags: const <String>['摄影', '川西'],
    authorVerified: true,
    assistantUsePolicy: 'allow',
    likeCount: 12,
    commentCount: 3,
    shareCount: 1,
    createdAt: DateTime(2026),
    updatedAt: null,
    publishedAt: null,
    body: '川西雪山和校园摄影路线',
    imageUrls: imageUrls,
    videoUrl: null,
    durationMs: null,
    intersectionReasons: <IntersectionReason>[effectiveReason],
  );
}

PhotoPostDto _photoPost({
  required int width,
  required int height,
  List<String> imageUrls = const <String>[
    'media/image/s/archived-image/post/fixture_photo_002/v1/cover.png',
  ],
}) {
  return PhotoPostDto(
    id: 'photo_${width}_${height}_${imageUrls.length}',
    type: 'photo',
    identity: 'work',
    assistantUsePolicy: 'allow',
    authorId: 'user_photo',
    displayName: '影像作者',
    avatarUrl: '',
    authorBackgroundUrl: null,
    authorRoleLabel: '摄影师',
    authorIdentityTags: const <String>['风光'],
    authorVerified: false,
    body: '不同素材宽高比测试',
    coverUrl: imageUrls.first,
    imageUrls: imageUrls,
    width: width,
    height: height,
    likeCount: 1,
    commentCount: 2,
    shareCount: 3,
    createdAt: DateTime(2026),
    updatedAt: null,
    publishedAt: null,
    intersectionReasons: <IntersectionReason>[_reason()],
  );
}

VideoPostDto _videoPost({required int width, required int height}) {
  return VideoPostDto(
    id: 'video_${width}_$height',
    type: 'video',
    identity: 'work',
    assistantUsePolicy: 'allow',
    authorId: 'user_video',
    displayName: '视频作者',
    avatarUrl: '',
    authorBackgroundUrl: null,
    authorRoleLabel: '旅行视频',
    authorIdentityTags: const <String>['影像'],
    authorVerified: false,
    body: '视频画面下方的配文',
    videoUrl: 'media/video/s/archived-video/beta-sample.mp4',
    thumbnailUrl:
        'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
    coverUrl:
        'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
    width: width,
    height: height,
    durationMs: 65000,
    likeCount: 1,
    commentCount: 2,
    shareCount: 3,
    createdAt: DateTime(2026),
    updatedAt: null,
    publishedAt: null,
    intersectionReasons: <IntersectionReason>[_reason()],
  );
}

PostBaseDto _alphaShowcaseHomePost() {
  return _microPost();
}

class _ArticleLayoutPost extends PostBaseDto {
  const _ArticleLayoutPost({
    required this.id,
    this.bodyValue = '正文第一行，正文第二行，正文第三行，正文第四行会被折叠进全文入口。',
    this.coverUrlValue = '',
  });

  @override
  final String id;
  final String bodyValue;
  final String coverUrlValue;

  @override
  String get type => 'article';
  @override
  String get identity => 'work';
  @override
  String get displayFormat => 'note';
  @override
  String get assistantUsePolicy => 'allow';
  @override
  String get authorId => 'user_article';
  @override
  String get displayName => '文章作者';
  @override
  String get avatarUrl => '';
  @override
  String? get authorBackgroundUrl => null;
  @override
  String get authorRoleLabel => '旅行作者';
  @override
  List<String> get authorIdentityTags => const <String>['长文'];
  @override
  bool get authorVerified => false;
  @override
  String get title => '川西路线长文标题';
  @override
  String? get body => bodyValue;
  @override
  String? get coverUrl => coverUrlValue;
  @override
  int get likeCount => 1;
  @override
  int get commentCount => 2;
  @override
  int get shareCount => 3;
  @override
  DateTime get createdAt => DateTime(2026);
  @override
  List<IntersectionReason>? get intersectionReasons => <IntersectionReason>[
    _reason(),
  ];
  @override
  Map<String, dynamic> toMap() => <String, dynamic>{'id': id};
}

class _NoopMediaDownloadCache extends MediaDownloadCache {
  @override
  Future<String?> getCachedFilePath(String url) async => null;
}

Widget _buildFeed(
  PostBaseDto post, {
  ContentBehaviorTracker? tracker,
  bool authenticated = false,
  void Function(PostBaseDto post, int index, {List<PostBaseDto>? feedPosts})?
  onPostTap,
}) {
  return ProviderScope(
    key: ValueKey<String>('feed-scope-${post.id}'),
    overrides: [
      discoveryFeedMapProvider.overrideWith(
        () => _SinglePostFeedMapNotifier(post),
      ),
      mediaDownloadCacheProvider.overrideWithValue(_NoopMediaDownloadCache()),
      if (authenticated)
        authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
      if (tracker != null)
        contentBehaviorTrackerProvider.overrideWithValue(tracker),
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
            onPostTap: onPostTap,
          ),
        ),
      ),
    ),
  );
}

Widget _buildRealProviderFeed() {
  return ProviderScope(
    child: CupertinoApp(
      home: ScreenUtilInit(
        designSize: const Size(390, 844),
        child: const MediaQuery(
          data: MediaQueryData(size: Size(390, 844)),
          child: HomeMultiFormFeed(
            isDark: false,
            channelId: 'recommend',
            template: 'single_column_multiform',
            onUserTap: _noopUserTap,
          ),
        ),
      ),
    ),
  );
}

void _noopUserTap(
  String userId, {
  String? avatarUrl,
  String? displayName,
  String? backgroundUrl,
}) {}

void main() {
  testWidgets('单列 post 内展示作者身份、媒体、交集与底部更多', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildFeed(_microPost()));
    await tester.pump();

    expect(
      find.byKey(const ValueKey('home-relation-card-header')),
      findsOneWidget,
    );
    expect(find.text('旅行创作者 · 摄影 · 川西'), findsOneWidget);
    expect(find.text('关注'), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.checkmark_seal_fill), findsOneWidget);
    expect(
      find.byKey(const ValueKey('home-relation-card-media')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('home-relation-card-reason')),
      findsOneWidget,
    );
    expect(
      find.text(DiscoveryFeedText.homeFeedIntersectionReasonLabel),
      findsNothing,
    );
    expect(find.byKey(const ValueKey('home-intersection-glyph')), findsNothing);
    final reasonBox = tester.widget<DecoratedBox>(
      find.byKey(const ValueKey('home-relation-card-reason')),
    );
    final reasonDecoration = reasonBox.decoration as BoxDecoration;
    expect(reasonDecoration.color, isNotNull);
    expect(reasonDecoration.border, isNotNull);
    final reasonRadius = reasonDecoration.borderRadius! as BorderRadius;
    expect(
      reasonRadius.topLeft.x,
      DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
    );
    final richText = tester.widget<RichText>(
      find.descendant(
        of: find.byType(InteractiveIntersectionText),
        matching: find.byType(RichText),
      ),
    );
    expect(richText.text.toPlainText(), '你与林清越等 3 位都来这里互动过');
    final textContext = tester.element(
      find.byType(InteractiveIntersectionText),
    );
    final plainColor = AppColors.iosLabel(textContext);
    final isDark = CupertinoTheme.of(textContext).brightness == Brightness.dark;
    final accentColor = isDark
        ? AppColors.profileSloganAccentDark
        : AppColors.profileSloganAccentLight;
    expect(_spanByText(richText, '你与').style?.color, plainColor);
    expect(_spanByText(richText, '等 ').style?.color, plainColor);
    expect(_spanByText(richText, ' 位都来这里互动过').style?.color, plainColor);
    expect(plainColor, isNot(AppColors.iosSecondaryLabel(textContext)));
    expect(_spanByText(richText, '林清越').style?.color, accentColor);
    expect(_spanByText(richText, '3').style?.color, accentColor);
    expect(
      _fontWeightValue(_spanByText(richText, '林清越')),
      greaterThan(_fontWeightValue(_spanByText(richText, '你与'))),
    );
    expect(
      _fontWeightValue(_spanByText(richText, '3')),
      greaterThan(_fontWeightValue(_spanByText(richText, '等 '))),
    );
    expect(
      find.byKey(const ValueKey('home-relation-card-actions')),
      findsOneWidget,
    );
    expect(find.text('更多'), findsOneWidget);
  });

  testWidgets('推荐卡片把头像、图片、视频统一投影为 secure local media candidates', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeed(
        _microPost(
          avatarUrl:
              'media/avatar/s/archived-avatar/circle/fixture_circle_city/v1/avatar.png',
        ),
      ),
    );
    await tester.pump();

    final avatarImages = tester
        .widgetList<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
        .where((widget) => widget.cdnPreset == CdnImagePreset.avatar)
        .toList(growable: false);
    expect(avatarImages, hasLength(1));
    expect(
      avatarImages.single.imageUrlCandidates,
      containsAll(<String>[
        'https://localhost:17100/media/avatar/s/archived-avatar/circle/fixture_circle_city/v1/avatar.png',
        'https://127.0.0.1:17100/media/avatar/s/archived-avatar/circle/fixture_circle_city/v1/avatar.png',
        'https://10.0.2.2:17100/media/avatar/s/archived-avatar/circle/fixture_circle_city/v1/avatar.png',
        'https://alpha-avatar.quwoquan-env.test:17100/media/avatar/s/archived-avatar/circle/fixture_circle_city/v1/avatar.png',
      ]),
    );

    final contentImages = tester
        .widgetList<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
        .where((widget) => widget.cdnPreset != CdnImagePreset.avatar)
        .toList(growable: false);
    expect(contentImages, isNotEmpty);
    expect(
      contentImages.any(
        (widget) =>
            widget.imageUrlCandidates?.contains(
              'https://localhost:17100/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
            ) ??
            false,
      ),
      isTrue,
    );

    await tester.pumpWidget(_buildFeed(_videoPost(width: 1080, height: 1920)));
    await tester.pump();

    final player = tester.widget<VideoPlayerWidget>(
      find.byType(VideoPlayerWidget),
    );
    expect(
      player.videoUrlCandidates,
      containsAll(<String>[
        'https://localhost:17100/media/video/s/archived-video/beta-sample.mp4',
        'https://127.0.0.1:17100/media/video/s/archived-video/beta-sample.mp4',
        'https://10.0.2.2:17100/media/video/s/archived-video/beta-sample.mp4',
        'https://alpha-video.quwoquan-env.test:17100/media/video/s/archived-video/beta-sample.mp4',
      ]),
    );
  });

  testWidgets('默认 Provider 加载首页推荐时保留 showcase 作者头像 media candidates', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    SharedPreferences.setMockInitialValues(const <String, Object>{});

    await tester.pumpWidget(_buildRealProviderFeed());
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('晨间记录者'), findsWidgets);

    final avatars = tester
        .widgetList<RoundedSquareAvatar>(find.byType(RoundedSquareAvatar))
        .toList(growable: false);
    expect(avatars, isNotEmpty);
    expect(
      avatars.first.imageUrl,
      'media/avatar/s/archived-avatar/circle/fixture_circle_city/v1/avatar.png',
    );

    final avatarImages = tester
        .widgetList<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
        .where((widget) => widget.cdnPreset == CdnImagePreset.avatar)
        .toList(growable: false);
    expect(avatarImages, isNotEmpty);
    expect(
      avatarImages.first.imageUrlCandidates,
      contains(
        'https://localhost:17100/media/avatar/s/archived-avatar/circle/fixture_circle_city/v1/avatar.png',
      ),
    );
  });

  testWidgets('任务B·分层强度：推测型交集证据行弱于事实型', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    double bgAlphaOf(WidgetTester t) {
      final box = t.widget<DecoratedBox>(
        find.byKey(const ValueKey('home-relation-card-reason')),
      );
      return ((box.decoration as BoxDecoration).color!).a;
    }

    double borderAlphaOf(WidgetTester t) {
      final box = t.widget<DecoratedBox>(
        find.byKey(const ValueKey('home-relation-card-reason')),
      );
      final border = (box.decoration as BoxDecoration).border! as Border;
      return border.top.color.a;
    }

    await tester.pumpWidget(
      _buildFeed(_microPost(reason: _reason(intersectionClass: 'fact'))),
    );
    await tester.pump();
    final factBgAlpha = bgAlphaOf(tester);
    final factBorderAlpha = borderAlphaOf(tester);

    await tester.pumpWidget(
      _buildFeed(_microPost(reason: _reason(intersectionClass: 'recommended'))),
    );
    await tester.pump();
    final recommendedBgAlpha = bgAlphaOf(tester);
    final recommendedBorderAlpha = borderAlphaOf(tester);

    // 事实型（共同关注/到访/收藏）必须比推测型视觉更强。
    expect(recommendedBgAlpha, lessThan(factBgAlpha));
    expect(recommendedBorderAlpha, lessThan(factBorderAlpha));
    // 但推测型仍保留具体证据行（不消失），泛化标签不出现。
    expect(
      find.text(DiscoveryFeedText.homeFeedIntersectionReasonLabel),
      findsNothing,
    );
  });

  testWidgets('任务A·加载态：空数据加载中展示骨架屏而非白屏', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeedScope(
        notifier: _LoadingFeedMapNotifier.new,
        disableAnimations: true,
      ),
    );
    await tester.pump();

    expect(find.byKey(const ValueKey('home-feed-skeleton')), findsOneWidget);
    expect(find.byKey(const ValueKey('home-feed-empty')), findsNothing);
  });

  testWidgets('任务A·空态：加载完成无内容展示运营兜底文案与再试', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeedScope(notifier: _EmptyFeedMapNotifier.new),
    );
    await tester.pump();

    expect(find.byKey(const ValueKey('home-feed-empty')), findsOneWidget);
    expect(find.text(DiscoveryFeedText.homeFeedEmptyTitle), findsOneWidget);
    expect(
      find.text(DiscoveryFeedText.homeFeedEmptyDescription),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('home-feed-empty-retry')), findsOneWidget);
    // 空态禁止落到空白滚动视图。
    expect(find.byKey(const ValueKey('home-feed-skeleton')), findsNothing);
  });

  testWidgets('首页关注按钮登录态点击后同步为已关注', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildFeed(_microPost(), authenticated: true));
    await tester.pump();

    expect(find.text(UITextConstants.follow), findsOneWidget);
    final followButton = find.byKey(
      const ValueKey<String>('home-post-author-follow-button'),
    );
    expect(followButton, findsOneWidget);
    final followWidth = tester.getSize(followButton).width;
    expect(followWidth, AppSpacing.followButtonWidth);

    await tester.tap(find.text(UITextConstants.follow));
    await tester.pump();

    expect(find.text(UITextConstants.following), findsOneWidget);
    final followingButton = find.byKey(
      const ValueKey<String>('home-post-author-follow-button'),
    );
    expect(followingButton, findsOneWidget);
    expect(tester.getSize(followingButton).width, followWidth);
  });

  testWidgets('首页 canonical mock feed 往返后保留交集 span 强调与点击目标', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildFeed(_alphaShowcaseHomePost()));
    await tester.pump();

    final richText = tester.widget<RichText>(
      find.descendant(
        of: find.byType(InteractiveIntersectionText),
        matching: find.byType(RichText),
      ),
    );
    final textContext = tester.element(
      find.byType(InteractiveIntersectionText),
    );
    final nameSpan = _spanByText(richText, '林清越');
    final countSpan = _spanByText(richText, '3');

    final isDark = CupertinoTheme.of(textContext).brightness == Brightness.dark;
    final accentColor = isDark
        ? AppColors.profileSloganAccentDark
        : AppColors.profileSloganAccentLight;
    expect(nameSpan.style?.color, accentColor);
    expect(countSpan.style?.color, accentColor);
    expect(
      _fontWeightValue(nameSpan),
      greaterThan(_fontWeightValue(_spanByText(richText, '你与'))),
    );
    expect(nameSpan.recognizer, isA<TapGestureRecognizer>());
    expect(countSpan.recognizer, isA<TapGestureRecognizer>());
  });

  testWidgets('个人记录图片按 1-9+ 图规则展示并在末格聚合剩余张数', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    Future<void> pumpMomentGrid(int count) async {
      await tester.pumpWidget(
        _buildFeed(
          _microPost(
            imageUrls: List<String>.generate(
              count,
              (index) =>
                  'media/image/s/archived-image/post/fixture_photo_001/v1/image-$index.png',
            ),
          ),
        ),
      );
      await tester.pump();
    }

    await pumpMomentGrid(1);
    expect(find.byKey(const ValueKey('home-moment-grid')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('home-moment-grid-tile-0')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('home-moment-grid-more')), findsNothing);
    final bodyTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-relation-card-body')))
        .dy;
    final gridTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-relation-card-media')))
        .dy;
    final reasonTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-post-inline-intersection')))
        .dy;
    expect(bodyTop, lessThan(reasonTop));
    expect(gridTop, lessThan(reasonTop));
    final singleGrid = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid')),
    );
    final singleCard = tester.getSize(
      find.byKey(const ValueKey('home-feed-card-0')),
    );
    expect(singleGrid.width, closeTo((singleCard.width - 32) / 3, 8));
    final singleTile = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid-tile-0')),
    );
    expect(singleTile.width, closeTo(singleGrid.width, 1));

    await pumpMomentGrid(2);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(2),
    );
    final doubleGrid = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid')),
    );
    final doubleCard = tester.getSize(
      find.byKey(const ValueKey('home-feed-card-0')),
    );
    expect(doubleGrid.width, closeTo((doubleCard.width - 32) * 2 / 3, 8));
    final doubleFirstTile = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid-tile-0')),
    );
    expect(doubleFirstTile.width, closeTo(singleTile.width, 4));

    await pumpMomentGrid(4);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(4),
    );
    expect(find.byKey(const ValueKey('home-moment-grid-more')), findsNothing);
    final fourGrid = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid')),
    );
    expect(fourGrid.width, greaterThan(doubleGrid.width));

    await pumpMomentGrid(5);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(3),
    );
    expect(find.text('+2'), findsOneWidget);
    expect(find.byKey(const ValueKey('home-moment-grid-more')), findsOneWidget);

    await pumpMomentGrid(6);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(6),
    );
    expect(find.byKey(const ValueKey('home-moment-grid-more')), findsNothing);

    await pumpMomentGrid(7);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(6),
    );
    expect(find.text('+1'), findsOneWidget);
    final moreTile = find.byKey(const ValueKey('home-moment-grid-tile-5'));
    final moreStack = tester.widget<Stack>(moreTile);
    expect(moreStack.children.first, isA<AppCachedNetworkImage>());
    expect(
      find.descendant(
        of: moreTile,
        matching: find.byType(AppCachedNetworkImage),
      ),
      findsOneWidget,
    );
    final scrim = tester.widget<DecoratedBox>(
      find.byKey(const ValueKey('home-moment-grid-more-scrim')),
    );
    final scrimDecoration = scrim.decoration as BoxDecoration;
    expect(scrimDecoration.color, isNull);
    expect(scrimDecoration.gradient, isA<LinearGradient>());
    final gradient = scrimDecoration.gradient! as LinearGradient;
    expect(gradient.colors, isNot(contains(AppColors.overlayStrong)));
    final morePill = tester.widget<DecoratedBox>(
      find.descendant(
        of: find.byKey(const ValueKey('home-moment-grid-more')),
        matching: find.byType(DecoratedBox),
      ),
    );
    final pillDecoration = morePill.decoration as BoxDecoration;
    expect(pillDecoration.color, isNot(AppColors.overlayStrong));
    expect(pillDecoration.color, isNot(AppColors.overlayMedium));
    expect(pillDecoration.borderRadius, isNotNull);
    final pillSize = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid-more')),
    );
    final tileSize = tester.getSize(moreTile);
    expect(pillSize.height, DiscoveryFeedSpacing.homeFeedGridMorePillHeight);
    expect(pillSize.width, lessThan(tileSize.width * 0.5));

    await pumpMomentGrid(8);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(6),
    );
    expect(find.text('+2'), findsOneWidget);

    await pumpMomentGrid(10);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(9),
    );
    expect(find.text('+1'), findsOneWidget);
  });

  testWidgets('图片 post 单图满宽，多图使用横滑轮播、底部点状与右上角数字指示器', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildFeed(_photoPost(width: 1600, height: 900)));
    await tester.pump();
    final card = tester.getSize(find.byKey(const ValueKey('home-feed-card-0')));
    final media = find.byKey(const ValueKey('home-relation-card-media'));
    final landscape = tester.getSize(
      find.descendant(of: media, matching: find.byType(ClipRRect)).first,
    );
    expect(landscape.width, closeTo(card.width - 32, 8));
    final landscapeClip = tester.widget<ClipRRect>(
      find.descendant(of: media, matching: find.byType(ClipRRect)).first,
    );
    final landscapeRadius = landscapeClip.borderRadius as BorderRadius;
    expect(
      landscapeRadius.topLeft.x,
      DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
    );
    expect(
      find.descendant(
        of: media,
        matching: find.byType(InteractiveIntersectionText),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('home-post-inline-intersection')),
        matching: find.byKey(const ValueKey('home-intersection-glyph')),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: media,
        matching: find.byKey(const ValueKey('home-intersection-glyph')),
      ),
      findsNothing,
    );
    expect(
      find.descendant(of: media, matching: find.byType(BackdropFilter)),
      findsNothing,
    );
    expect(
      find.descendant(of: media, matching: find.byIcon(CupertinoIcons.link)),
      findsNothing,
    );
    final mediaTop = tester.getTopLeft(media).dy;
    final reasonTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-post-inline-intersection')))
        .dy;
    final bodyTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-relation-card-body')))
        .dy;
    expect(mediaTop, lessThan(bodyTop));
    expect(bodyTop, lessThan(reasonTop));

    await tester.pumpWidget(
      _buildFeed(
        _photoPost(
          width: 1600,
          height: 900,
          imageUrls: List<String>.generate(
            8,
            (index) =>
                'media/image/s/archived-image/post/fixture_photo_002/v1/image-$index.png',
          ),
        ),
      ),
    );
    await tester.pump();
    expect(find.byType(PageView), findsWidgets);
    expect(
      find.byKey(const ValueKey('home-image-carousel-counter')),
      findsOneWidget,
    );
    expect(find.text('1/8'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('home-image-carousel-dots')),
      findsOneWidget,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-image-carousel-dot-',
            ),
      ),
      findsNWidgets(6),
    );
    final dot = tester.widget<AnimatedContainer>(
      find.byKey(const ValueKey('home-image-carousel-dot-0')),
    );
    final dotDecoration = dot.decoration as BoxDecoration;
    expect(dotDecoration.color, isNot(AppColors.black));
    expect(dotDecoration.shape, BoxShape.circle);
  });

  testWidgets('视频 post 首帧先延迟初始化，避免焦点瞬间抢播', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final post = _videoPost(width: 900, height: 1600);
    await tester.pumpWidget(_buildFeed(post));
    await tester.pump();

    final media = find.byKey(const ValueKey('home-relation-card-media'));
    expect(
      find.byKey(ValueKey<String>('home-video-focus-paused-${post.id}')),
      findsOneWidget,
    );
    expect(
      find.byKey(ValueKey<String>('home-video-player-${post.id}')),
      findsOneWidget,
    );
    expect(find.byType(VideoPlayerWidget), findsOneWidget);
    final player = tester.widget<VideoPlayerWidget>(
      find.byKey(ValueKey<String>('home-video-player-${post.id}')),
    );
    expect(player.initialize, isFalse);
    expect(player.autoPlay, isFalse);
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('home-post-inline-intersection')),
        matching: find.byKey(const ValueKey('home-intersection-glyph')),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: media,
        matching: find.byType(InteractiveIntersectionText),
      ),
      findsNothing,
    );
    expect(find.text('视频画面下方的配文'), findsOneWidget);

    final reasonTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-post-inline-intersection')))
        .dy;
    final mediaTop = tester.getTopLeft(media).dy;
    final bodyTop = tester.getTopLeft(find.text('视频画面下方的配文')).dy;
    expect(mediaTop, lessThan(bodyTop));
    expect(bodyTop, lessThan(reasonTop));
    final card = tester.getSize(find.byKey(const ValueKey('home-feed-card-0')));
    final video = tester.getSize(
      find.descendant(of: media, matching: find.byType(ClipRRect)).first,
    );
    expect(video.width, lessThan(card.width - 32));
    expect(video.width, greaterThan((card.width - 32) * 0.55));
  });

  test('视频 post 外层播放按钮只属于未初始化静态封面态', () {
    final source = File(
      'lib/ui/discovery/widgets/home_multi_form_feed_media_grid.dart',
    ).readAsStringSync();
    expect(source, contains('if (!initialize && !autoPlay)'));
    expect(source, isNot(contains('if (!autoPlay)\n              Center(')));
  });

  test('视频快滑抑制事件走统一 cache telemetry sink', () {
    final postCardSource = File(
      'lib/ui/discovery/widgets/home_multi_form_feed_post_cards.dart',
    ).readAsStringSync();
    final mediaSource = File(
      'lib/ui/discovery/widgets/home_multi_form_feed_media.dart',
    ).readAsStringSync();

    expect(postCardSource, contains('cacheTelemetrySinkProvider'));
    expect(postCardSource, contains('video.init.suppressed_fast_scroll'));
    expect(mediaSource, isNot(contains('developer.log')));
  });

  testWidgets('文章 post 支持无图短文、无图长文、上文下图和左文右图', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeed(
        const _ArticleLayoutPost(
          id: 'article_text_short',
          bodyValue: '这是一段三行内能读完的短文摘要。',
        ),
      ),
    );
    await tester.pump();
    expect(find.byKey(const ValueKey('home-article-card')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('home-article-layout-text-only')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('home-article-full-text')), findsNothing);
    final titleText = tester.widget<Text>(
      find.byKey(const ValueKey('home-post-title')),
    );
    expect(titleText.maxLines, 1);
    final summaryText = tester.widget<Text>(find.text('这是一段三行内能读完的短文摘要。'));
    expect(summaryText.style?.fontWeight, FontWeight.normal);
    final inlineTop = tester
        .getTopLeft(
          find.byKey(const ValueKey('home-article-inline-intersection')),
        )
        .dy;
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('home-article-inline-intersection')),
        matching: find.byKey(const ValueKey('home-intersection-glyph')),
      ),
      findsNothing,
    );
    final bodyTop = tester.getTopLeft(find.textContaining('这是一段')).dy;
    expect(bodyTop, lessThan(inlineTop));

    await tester.pumpWidget(
      _buildFeed(
        const _ArticleLayoutPost(
          id: 'article_text_long',
          bodyValue:
              '这是一段无图长文摘要，用来验证首页文章卡在超过三行时才展示全文入口。它继续补充场景、人物和路线，让文本在手机宽度下自然溢出第三行，并且点击整卡或全文入口都进入同一篇文章浏览器。',
        ),
      ),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey('home-article-layout-text-only')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('home-article-full-text')),
      findsOneWidget,
    );

    await tester.pumpWidget(
      _buildFeed(
        const _ArticleLayoutPost(
          id: 'article_side',
          bodyValue: '短图文保持左文右图，快速扫读也能看到封面。',
          coverUrlValue:
              'media/image/s/archived-image/post/fixture_article_001/v1/cover.png',
        ),
      ),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey('home-article-layout-side-image')),
      findsOneWidget,
    );
    final sideSummary = tester.widget<Text>(find.text('短图文保持左文右图，快速扫读也能看到封面。'));
    expect(sideSummary.style?.fontWeight, FontWeight.normal);
    final titleRect = tester.getRect(
      find.byKey(const ValueKey('home-post-title')),
    );
    final thumbRect = tester.getRect(
      find.byKey(const ValueKey('home-article-side-thumb')),
    );
    final thumbAspectRatio = thumbRect.width / thumbRect.height;
    expect(
      thumbAspectRatio,
      closeTo(DiscoveryFeedSpacing.homeFeedArticleSideThumbAspectRatio, 0.02),
    );
    final bodyRect = tester.getRect(find.text('短图文保持左文右图，快速扫读也能看到封面。'));
    final intersectionRect = tester.getRect(
      find.byKey(const ValueKey('home-article-inline-intersection')),
    );
    expect(thumbRect.top, greaterThan(titleRect.bottom - 1));
    expect((bodyRect.top - thumbRect.top).abs(), lessThan(2));
    expect(bodyRect.right, lessThan(thumbRect.left + 1));
    expect(intersectionRect.top, greaterThan(thumbRect.bottom - 1));
    expect(intersectionRect.right, greaterThanOrEqualTo(bodyRect.right - 1));
    expect(intersectionRect.right, lessThan(thumbRect.left + 1));

    await tester.pumpWidget(
      _buildFeed(
        const _ArticleLayoutPost(
          id: 'article_top',
          bodyValue:
              '有图长文在摘要较长时采用上文下图，让图片承担情绪收束，正文先交代推荐理由和阅读入口。这里继续补充一段描述，让布局明确进入上文下图状态。',
          coverUrlValue:
              'media/image/s/archived-image/post/fixture_article_001/v1/image-2.png',
        ),
      ),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey('home-article-layout-top-image')),
      findsOneWidget,
    );
  });

  testWidgets('文章整卡与全文入口点击进入同一沉浸 pageflip 打开链路', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final opened = <PostBaseDto>[];
    await tester.pumpWidget(
      _buildFeed(
        const _ArticleLayoutPost(
          id: 'article_open',
          bodyValue:
              '这是一段用于点击测试的长文摘要，用来确保全文入口出现。它继续补充场景、人物和路线，让文本在手机宽度下自然溢出第三行，并且点击整卡或全文入口都进入同一篇文章浏览器。',
        ),
        onPostTap: (post, _, {feedPosts}) => opened.add(post),
      ),
    );
    await tester.pump();

    await tester.tap(find.byKey(const ValueKey('home-article-card')));
    await tester.pump();
    expect(opened.map((post) => post.id), <String>['article_open']);

    await tester.tap(find.byKey(const ValueKey('home-article-full-text')));
    await tester.pump();
    expect(opened.map((post) => post.id), <String>[
      'article_open',
      'article_open',
    ]);
  });

  testWidgets('内容卡曝光与媒体点击透传 referralSource、position、feedRequestId', (
    tester,
  ) async {
    final behaviorRepo = MockBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      repository: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    var opened = false;
    await tester.pumpWidget(
      _buildFeed(
        _microPost(),
        tracker: tracker,
        onPostTap: (_, _, {feedPosts}) => opened = true,
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    final impressions = behaviorRepo.recorded
        .where(
          (event) =>
              event.action == BehaviorAction.impression &&
              event.contentId == 'post_intersection_demo_fact_1',
        )
        .toList(growable: false);
    expect(impressions, hasLength(1));
    expect(impressions.single.position, 0);
    expect(impressions.single.referralSource, ReferralSource.organicFeed);

    await tester.tap(find.byKey(const ValueKey('home-moment-grid-tile-0')));
    await tester.pump();
    expect(opened, isTrue);
    final clicks = behaviorRepo.recorded
        .where((event) => event.action == BehaviorAction.click)
        .toList(growable: false);
    expect(clicks, hasLength(1));
    expect(clicks.single.position, 0);
    expect(clicks.single.referralSource, ReferralSource.organicFeed);
    expect(clicks.single.feedRequestId, isNotEmpty);
  });

  // ── N6：交集 span 点击埋点带全归因，且保持 tag_click 推荐权重语义 ──
  testWidgets(
    '点击交集名字 span → trackTagClick 透传 intersectionSourceRef + evidenceId',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final behaviorRepo = MockBehaviorRepository();
      final tracker = ContentBehaviorTracker(
        repository: behaviorRepo,
        maxBatchSize: 1,
        enablePeriodicFlush: false,
      );
      addTearDown(tracker.dispose);

      await tester.pumpWidget(_routedFeed(_microPost(), tracker: tracker));
      await tester.pump();

      final richText = tester.widget<RichText>(
        find.descendant(
          of: find.byType(InteractiveIntersectionText),
          matching: find.byType(RichText),
        ),
      );
      final nameSpan = _spanByText(richText, '林清越');
      (nameSpan.recognizer! as TapGestureRecognizer).onTap!();
      await tester.pump();
      await tracker.flush();

      final clicks = behaviorRepo.recorded
          .where((event) => event.action == BehaviorAction.tagClick)
          .toList(growable: false);
      expect(clicks, hasLength(1));
      final click = clicks.single;
      // 关键回归：sourceRef / evidenceId 由 attribution 真正转发到埋点（此前被丢）。
      expect(click.intersectionSourceRef, equals('sharedFollowees'));
      expect(click.intersectionEvidenceId, equals('snap_lin'));
      expect(click.intersectionId, equals('ix_post_lin'));
      expect(click.intersectionDimension, equals('relationship'));
      expect(click.intersectionTagRefs, isNotNull);
    },
  );
}

/// N6：带 GoRouter 的 feed 宿主，使交集 span 点击的 `context.push` 可达，
/// 从而验证 onTrack → trackTagClick 的归因字段透传（`/user/:username` 复用
/// resolvePath(userProfile) 的 codegen 路由）。
Widget _routedFeed(
  PostBaseDto post, {
  required ContentBehaviorTracker tracker,
}) {
  final router = GoRouter(
    initialLocation: '/',
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (_, _) => ScreenUtilInit(
          designSize: const Size(390, 844),
          child: MediaQuery(
            data: const MediaQueryData(size: Size(390, 844)),
            child: HomeMultiFormFeed(
              isDark: false,
              channelId: 'recommend',
              template: 'single_column_multiform',
              onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
              onPostTap: null,
            ),
          ),
        ),
      ),
      GoRoute(
        path: '/user/:username',
        builder: (_, state) => Text('USER:${state.pathParameters['username']}'),
      ),
    ],
  );
  return ProviderScope(
    key: ValueKey<String>('routed-feed-scope-${post.id}'),
    overrides: [
      discoveryFeedMapProvider.overrideWith(
        () => _SinglePostFeedMapNotifier(post),
      ),
      mediaDownloadCacheProvider.overrideWithValue(_NoopMediaDownloadCache()),
      contentBehaviorTrackerProvider.overrideWithValue(tracker),
    ],
    child: CupertinoApp.router(routerConfig: router),
  );
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      ownerId: 'test-user',
      activeSubAccountId: 'test-sub-account',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

class _SinglePostFeedMapNotifier extends DiscoveryFeedMapNotifier {
  _SinglePostFeedMapNotifier(this.post);

  final PostBaseDto post;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(DiscoveryFeedState(items: <PostBaseDto>[post])),
    };
  }

  @override
  Future<void> load(String channelId, {bool force = false}) async {}
}

class _EmptyFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(const DiscoveryFeedState(items: <PostBaseDto>[])),
    };
  }

  @override
  Future<void> load(String channelId, {bool force = false}) async {}
}

class _LoadingFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': const AsyncLoading<DiscoveryFeedState>(),
    };
  }

  @override
  Future<void> load(String channelId, {bool force = false}) async {}
}

Widget _buildFeedScope({
  required DiscoveryFeedMapNotifier Function() notifier,
  bool disableAnimations = false,
}) {
  return ProviderScope(
    overrides: [discoveryFeedMapProvider.overrideWith(notifier)],
    child: CupertinoApp(
      home: ScreenUtilInit(
        designSize: const Size(390, 844),
        child: MediaQuery(
          data: MediaQueryData(
            size: const Size(390, 844),
            disableAnimations: disableAnimations,
          ),
          child: HomeMultiFormFeed(
            isDark: false,
            channelId: 'recommend',
            template: 'single_column_multiform',
            onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
          ),
        ),
      ),
    ),
  );
}
