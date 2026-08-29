// spec_ref: specs/feature-tree/spec.md#uat-003
// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
/// user_acceptance Patrol: release-bound 核心 Remote readback 组合旅程。
///
/// 覆盖 startup/feed/entity/article/image/video/Creator/avatar/recovery。
/// 登录后联系人、会话、消息与本人主页由 content-free BASIC 单轨验收。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/signed_grant_image.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_state_provider.dart';

import '../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../support/runtime/patrol/patrol_app_content_screenshot.dart';
import '../../../support/runtime/patrol/patrol_core_readback_support.dart';
import '../../../support/runtime/patrol/patrol_environment_harness.dart';

const _videoWorkId = String.fromEnvironment('VIDEO_PLAYBACK_CANARY_WORK_ID');
const _apiContractEnv = String.fromEnvironment('API_CONTRACT_ENV');
const _appRuntimeEnv = String.fromEnvironment('APP_RUNTIME_ENV');
const _releaseId = String.fromEnvironment('DATA_RELEASE_ID');
const _releaseClass = String.fromEnvironment('DATA_RELEASE_CLASS');
const _productLifecycleState = String.fromEnvironment(
  'PRODUCT_LIFECYCLE_STATE',
);
const _homepageId = String.fromEnvironment('DATA_RELEASE_HOMEPAGE_ID');
const _homepageTitle = String.fromEnvironment('DATA_RELEASE_HOMEPAGE_TITLE');
const _articleWorkId = String.fromEnvironment('DATA_RELEASE_ARTICLE_WORK_ID');
const _articleTitle = String.fromEnvironment('DATA_RELEASE_ARTICLE_TITLE');
const _imageWorkId = String.fromEnvironment('DATA_RELEASE_IMAGE_WORK_ID');
const _imageTitle = String.fromEnvironment('DATA_RELEASE_IMAGE_TITLE');
const _creatorName = String.fromEnvironment('DATA_RELEASE_CREATOR_NAME');
const _creatorUserHandle = String.fromEnvironment(
  'DATA_RELEASE_CREATOR_USER_HANDLE',
);
const _creatorPersonaId = String.fromEnvironment(
  'DATA_RELEASE_CREATOR_PERSONA_ID',
);
const _creatorAvatarAssetId = String.fromEnvironment(
  'DATA_RELEASE_CREATOR_AVATAR_ASSET_ID',
);
const _tagLabel = String.fromEnvironment('DATA_RELEASE_TAG_LABEL');
const _videoAttribution = String.fromEnvironment(
  'DATA_RELEASE_VIDEO_ATTRIBUTION',
);
const _videoPageCount = int.fromEnvironment('DATA_RELEASE_VIDEO_PAGE_COUNT');

const _homeFeedKey = ValueKey<String>('home-feed-recommend');
// 视频书不再有顶栏专用入口图标，改为首页一级文本频道。Journey 断言的始终是
// 「从首页可达视频书沉浸消费」，锚点随实现落到频道 Tab。
const _homeFeaturedEntryKey = ValueKey<String>('home-primary-tab-featured');
const _homeSearchChromeKey = ValueKey<String>('home-primary-tab-chrome');
const _worksTopBackKey = ValueKey<String>('works-top-back');
const _videoErrorKey = ValueKey<String>('video-player-error');
const _feedCardProbeKeys = <ValueKey<String>>[
  ValueKey<String>('home-feed-card-0'),
  ValueKey<String>('home-feed-card-1'),
  ValueKey<String>('home-feed-card-2'),
  ValueKey<String>('feed-patch-reporter-0'),
];
const _homeContentTapKeys = <ValueKey<String>>[
  ValueKey<String>('home-moment-grid-tile-0'),
  ValueKey<String>('home-relation-card-media'),
  ValueKey<String>('home-article-card'),
];
const _videoProbeKeys = <ValueKey<String>>[
  ValueKey<String>('works-video-stage-$_videoWorkId-0'),
  ValueKey<String>('works-video-$_videoWorkId-0'),
  ValueKey<String>('home-video-player-$_videoWorkId'),
];

void main() {
  patrolTest(
    'environment_app_core_readback',
    tags: ['user-acceptance', 'app-core-readback', 'environment-smoke'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      _expectSelectedNonProdEnvironment();
      await launchEnvironmentPatrolApp($);
      expect(
        find.text(FoundationText.startupRecoveryTitle),
        findsNothing,
        reason: 'recovery page is not a successful dual-platform baseline',
      );
      expect(
        _videoWorkId.trim(),
        isNotEmpty,
        reason: 'app-core-readback requires an injected video playback canary work id',
      );
      _expectReleaseInputs();

      await _expectHomeFeed($);
      await _expectReleaseSurface(
        $,
        AppRoutePaths.homepageDetail(id: _homepageId),
        _homepageTitle,
        readyFinder: find.byKey(TestKeys.homepageDetailPage),
      );
      await _expectReleaseSurface(
        $,
        AppRoutePaths.workBrowser(
          workId: _articleWorkId,
          source: 'releaseReadback',
        ),
        _articleTitle,
        readyFinder: find.byKey(TestKeys.worksImmersivePager),
      );
      expect(
        find.byKey(const ValueKey<String>('immersive-author-group')),
        findsOneWidget,
        reason: 'release-bound article must expose its creator action surface',
      );
      expect(
        find.byKey(const ValueKey<String>('immersive-author-name-slot')),
        findsOneWidget,
        reason: 'release-bound article must expose its creator name slot',
      );
      await _expectReleaseCreatorProfile($);
      await _expectReleaseSurface(
        $,
        AppRoutePaths.workBrowser(
          workId: _imageWorkId,
          source: 'releaseReadback',
        ),
        _imageTitle,
        readyFinder: find.byKey(TestKeys.worksImmersivePager),
      );
      await _expectImageDecode($);
      await patrolGoTo(
        $,
        AppRoutePaths.workBrowser(
          workId: _videoWorkId,
          source: 'appCoreReadback',
        ),
      );
      await _expectVideoPlayback($);
      expect(
        await _waitForAnyFinder($, <Finder>[
          find.textContaining(_videoAttribution),
        ]),
        isTrue,
        reason: 'release-bound video source attribution must reach the App unchanged',
      );
      await _expectFeaturedVideoBook($);
    },
  );
}

void _expectSelectedNonProdEnvironment() {
  expect(
    _apiContractEnv,
    anyOf('alpha', 'beta', 'gamma'),
    reason: 'app core readback only accepts alpha/beta/gamma',
  );
  expect(
    _appRuntimeEnv,
    _apiContractEnv,
    reason: 'APP_RUNTIME_ENV and API_CONTRACT_ENV must name the same target',
  );
}

void _expectReleaseInputs() {
  final required = <String, String>{
    'DATA_RELEASE_ID': _releaseId,
    'DATA_RELEASE_CLASS': _releaseClass,
    'PRODUCT_LIFECYCLE_STATE': _productLifecycleState,
    'DATA_RELEASE_HOMEPAGE_ID': _homepageId,
    'DATA_RELEASE_HOMEPAGE_TITLE': _homepageTitle,
    'DATA_RELEASE_ARTICLE_WORK_ID': _articleWorkId,
    'DATA_RELEASE_ARTICLE_TITLE': _articleTitle,
    'DATA_RELEASE_IMAGE_WORK_ID': _imageWorkId,
    'DATA_RELEASE_IMAGE_TITLE': _imageTitle,
    'DATA_RELEASE_CREATOR_NAME': _creatorName,
    'DATA_RELEASE_CREATOR_USER_HANDLE': _creatorUserHandle,
    'DATA_RELEASE_CREATOR_PERSONA_ID': _creatorPersonaId,
    'DATA_RELEASE_CREATOR_AVATAR_ASSET_ID': _creatorAvatarAssetId,
    'DATA_RELEASE_TAG_LABEL': _tagLabel,
    'DATA_RELEASE_VIDEO_ATTRIBUTION': _videoAttribution,
  };
  for (final entry in required.entries) {
    expect(
      entry.value.trim(),
      isNotEmpty,
      reason: '${entry.key} must bind this UAT to one immutable release',
    );
  }
  expect(
    _releaseClass,
    anyOf('research', 'commercial'),
    reason: 'release class must be explicit and governed',
  );
  expect(
    _productLifecycleState,
    _releaseClass,
    reason:
        'App readback must preserve the release lifecycle without inference',
  );
  expect(
    _videoPageCount,
    greaterThanOrEqualTo(1),
    reason: 'release video page must contain at least one exact work id',
  );
}

Future<void> _expectReleaseSurface(
  PatrolIntegrationTester $,
  String route,
  String expectedTitle, {
  required Finder readyFinder,
}) async {
  await patrolGoTo($, route);
  final retryFinders = <Finder>[
    find.text(ContentText.tryAgain),
    find.text(SearchText.reload),
  ];
  await _waitForAnyFinder($, <Finder>[readyFinder, ...retryFinders]);
  if (readyFinder.evaluate().isEmpty) {
    final retryFinder = retryFinders
        .where((finder) => finder.evaluate().isNotEmpty)
        .firstOrNull;
    if (retryFinder != null) {
      await $.tester.tap(retryFinder.first);
    }
    await _waitForAnyFinder($, <Finder>[readyFinder]);
  }
  expect(
    readyFinder,
    findsOneWidget,
    reason:
        'release $_releaseId route $route must reach its production surface; '
        'visible text=${_visibleTextSnapshot()}',
  );
  final normalizedExpectedTitle = _normalizeVisibleText(expectedTitle);
  final titleFinder = find.byWidgetPredicate((widget) {
    final value = switch (widget) {
      Text() => widget.data ?? widget.textSpan?.toPlainText() ?? '',
      RichText() => widget.text.toPlainText(),
      _ => '',
    };
    return _normalizeVisibleText(value).contains(normalizedExpectedTitle);
  });
  final rendered = await _waitForAnyFinder($, <Finder>[titleFinder]);
  expect(
    rendered,
    isTrue,
    reason:
        'release $_releaseId surface $route must render its expected title '
        '"$expectedTitle"; visible text=${_visibleTextSnapshot()}',
  );
}

String _normalizeVisibleText(String value) =>
    value.replaceAll(RegExp(r'\s+'), ' ').trim();

String _visibleTextSnapshot() {
  final values = <String>{};
  for (final element in find.byType(Text).evaluate()) {
    final widget = element.widget as Text;
    final value = (widget.data ?? widget.textSpan?.toPlainText() ?? '').trim();
    if (value.isNotEmpty) {
      values.add(value);
    }
  }
  for (final element in find.byType(RichText).evaluate()) {
    final value = (element.widget as RichText).text.toPlainText().trim();
    if (value.isNotEmpty) {
      values.add(value);
    }
  }
  return values
      .take(30)
      .map((value) {
        final compact = value.replaceAll(RegExp(r'\s+'), ' ');
        return compact.length <= 120
            ? compact
            : '${compact.substring(0, 120)}…';
      })
      .join(' | ');
}

Future<void> _expectHomeFeed(PatrolIntegrationTester $) async {
  final visible = await _waitForAnyKey($, _feedCardProbeKeys);
  expect(
    visible,
    isTrue,
    reason: 'home feed must render at least one real card, not HTTP 200 alone',
  );
  final contentTargets = <Finder>[];
  for (final key in _feedCardProbeKeys) {
    final feedEntry = find.byKey(key);
    if (feedEntry.evaluate().isEmpty) {
      continue;
    }
    for (final contentKey in _homeContentTapKeys) {
      final contentTarget = find.descendant(
        of: feedEntry.first,
        matching: find.byKey(contentKey),
      );
      if (contentTarget.evaluate().isNotEmpty) {
        contentTargets.add(contentTarget.first);
      }
    }
  }
  expect(
    contentTargets,
    isNotEmpty,
    reason:
        'visible release content entries must expose a content media target',
  );
  expect(
    await _waitForAnyFinder(
      $,
      contentTargets
          .map(
            (target) => find.descendant(
              of: target,
              matching: find.byKey(appImageLoadSuccessKey),
            ),
          )
          .toList(growable: false),
    ),
    isTrue,
    reason:
        'a visible release content media target must decode its own image; an author '
        'avatar cannot satisfy this assertion',
  );
  final releaseContentTarget = contentTargets.firstWhere(
    (target) => find
        .descendant(of: target, matching: find.byKey(appImageLoadSuccessKey))
        .evaluate()
        .isNotEmpty,
  );
  expect(
    find.descendant(
      of: releaseContentTarget,
      matching: find.byKey(appImageLoadErrorKey),
    ),
    findsNothing,
    reason: 'first release content media must not render an image error state',
  );
  await $.tester.ensureVisible(releaseContentTarget);
  final offsetBefore = _homeFeedOffset($);
  expect(
    offsetBefore,
    isNotNull,
    reason: 'home feed must expose a readable scroll position before detail',
  );
  await $(releaseContentTarget).tap();
  expect(
    await _waitForAnyFinder($, <Finder>[
      find.byKey(TestKeys.worksImmersivePager),
    ]),
    isTrue,
    reason: 'tapping home content must open its production detail surface',
  );
  await $.tester.tap(find.byKey(_worksTopBackKey).first);
  await $(find.byKey(_homeSearchChromeKey))
      .waitUntilVisible(timeout: const Duration(seconds: 40));
  expect(find.byKey(_homeSearchChromeKey), findsOneWidget);
  expect(
    _homeFeedOffset($),
    closeTo(offsetBefore!, 1),
    reason:
        'returning from content detail must preserve the home feed position',
  );
}

Future<void> _expectImageDecode(PatrolIntegrationTester $) async {
  final imageCanvas = find.byKey(
    ValueKey<String>('works-status-content-canvas-$_imageWorkId'),
  );
  expect(
    await _waitForAnyFinder($, <Finder>[
      find.descendant(
        of: imageCanvas,
        matching: find.byKey(
          const ValueKey<String>('image-book-decoded-surface'),
        ),
      ),
    ]),
    isTrue,
    reason: 'release-bound image detail must finish a real image decode',
  );
}

Future<void> _expectReleaseCreatorProfile(PatrolIntegrationTester $) async {
  await patrolGoTo(
    $,
    AppRoutePaths.userProfile(userHandle: _creatorUserHandle),
  );
  expect(
    await _waitForAnyFinder($, <Finder>[find.textContaining(_creatorName)]),
    isTrue,
    reason: 'release $_releaseId creator profile must render its display name',
  );

  final profile = patrolMountedContainer()
      .read(profileNotifierProvider(_creatorUserHandle))
      .profile;
  expect(
    profile,
    isNotNull,
    reason: 'release $_releaseId creator profile must resolve through Remote',
  );
  expect(profile!.personaId, _creatorPersonaId);
  expect(profile.userHandle, _creatorUserHandle);
  expect(profile.displayName, _creatorName);

  const avatarKey = ValueKey<String>('profile-header-avatar-image');
  final avatarFinder = find.byKey(avatarKey);
  expect(
    await _waitForAnyFinder($, <Finder>[avatarFinder]),
    isTrue,
    reason:
        'release avatar $_creatorAvatarAssetId must enter the trusted image pipeline',
  );
  // 资产身份按 typed 交付绑定核验，而不是在 URL 里做子串匹配：research 相位的
  // 头像走短签，交付地址是 CAS 路径加签名 query，里面并不含 assetId，按 URL
  // 断言会把「私有交付正确工作」误判成失败。
  final signedAvatar = find.descendant(
    of: avatarFinder,
    matching: find.byType(SignedGrantImage),
  );
  if (signedAvatar.evaluate().isNotEmpty) {
    expect(
      $.tester.widget<SignedGrantImage>(signedAvatar.first).assetId,
      _creatorAvatarAssetId,
      reason:
          'release creator profile must bind the exact avatar asset '
          '$_creatorAvatarAssetId through the signed delivery atom',
    );
  } else {
    expect(
      $.tester.widget<AppAvatarImage>(avatarFinder).imageUrl,
      contains(_creatorAvatarAssetId),
      reason:
          'public release creator profile must bind the exact avatar asset '
          '$_creatorAvatarAssetId',
    );
  }
  expect(
    await _waitForAnyFinder($, <Finder>[
      find.descendant(
        of: avatarFinder,
        matching: find.byKey(appImageLoadSuccessKey),
      ),
    ]),
    isTrue,
    reason: 'release avatar $_creatorAvatarAssetId must finish a real decode',
  );
}

Future<void> _expectFeaturedVideoBook(PatrolIntegrationTester $) async {
  await patrolGoTo($, AppRoutePaths.home);
  expect(
    await _waitForAnyKey($, _feedCardProbeKeys),
    isTrue,
    reason: 'video book entry must start from a non-empty home feed',
  );
  final feedOffsetBefore = _homeFeedOffset($);
  expect(
    feedOffsetBefore,
    isNotNull,
    reason: 'video book entry must start from a readable home feed state',
  );

  final entryVisible = await _waitForAnyFinder($, <Finder>[
    find.byKey(_homeFeaturedEntryKey),
  ]);
  expect(
    entryVisible,
    isTrue,
    reason: 'video book home entry must be reachable',
  );
  await $.tester.tap(find.byKey(_homeFeaturedEntryKey).first);
  await $.pump(const Duration(seconds: 1));

  final pagerVisible = await _waitForAnyFinder($, <Finder>[
    find.byKey(TestKeys.worksImmersivePager),
  ], timeout: const Duration(seconds: 60));
  expect(
    pagerVisible,
    isTrue,
    reason: 'video book must open its immersive pager',
  );
  // 视频书唯一消费 premium_stream 池：canonical 空态（「暂无内容/内容加载
  // 完毕」黑屏）意味着 premium 供给缺失，属于环境 readiness 回归而非可通过态。
  expect(
    find
        .byWidgetPredicate(
          (widget) =>
              widget.key is ValueKey<String> &&
              (widget.key! as ValueKey<String>).value.startsWith(
                'works-internal-feed-empty-',
              ),
          description: 'video book canonical empty state',
        )
        .evaluate(),
    isEmpty,
    reason:
        'video book must not settle on the canonical empty state '
        '(premium_stream pool must be release-bound non-empty)',
  );

  final releaseVideoStage = find.descendant(
    of: find.byKey(TestKeys.worksImmersivePager),
    matching: find.byKey(ValueKey<String>('works-video-stage-$_videoWorkId-0')),
  );
  final videoStageVisible = await _waitForAnyFinder($, <Finder>[
    releaseVideoStage,
  ], timeout: const Duration(seconds: 60));
  expect(
    videoStageVisible,
    isTrue,
    reason: 'video book premium_stream must expose a real playable video page',
  );

  const playerReadyKey = ValueKey<String>('video-player-ready');
  final playerReady = find.byKey(playerReadyKey);
  expect(
    await _waitForAnyFinder($, <Finder>[
      playerReady,
    ], timeout: const Duration(seconds: 60)),
    isTrue,
    reason: 'video book must mount a native playable surface',
  );
  await $.tester.tap(playerReady.first);
  await $.pump(const Duration(milliseconds: 300));
  expect(
    find.byKey(_videoErrorKey).evaluate(),
    isEmpty,
    reason: 'video book playback interaction must not enter an error state',
  );
  expect(
    GoRouterState.of(
      $.tester.element(find.byKey(TestKeys.worksImmersivePager).first),
    ).uri.path,
    AppRoutePaths.home,
    reason: 'video book screenshot terminal must remain on the home route',
  );
  await emitPatrolAppContentPageScreenshotReady(
    $,
    environment: _apiContractEnv,
    suite: 'app-core-readback',
    route: AppRoutePaths.home,
    terminalKey: TestKeys.worksImmersivePager.value,
    terminalFinder: find.byKey(TestKeys.worksImmersivePager),
  );

  final pager = find.byKey(TestKeys.worksImmersivePager);
  final pageController = $.tester.widget<PageView>(pager.first).controller;
  expect(
    pageController,
    isNotNull,
    reason: 'video book pager must expose its production page controller',
  );
  final initialPage = pageController!.page;
  expect(initialPage, isNotNull, reason: 'video book page must be attached');
  if (_videoPageCount > 1) {
    var switchedPage = await _dragToDifferentVideoBookPage(
      $,
      pageController,
      initialPage!,
      const Offset(0, -620),
    );
    if (!switchedPage) {
      switchedPage = await _dragToDifferentVideoBookPage(
        $,
        pageController,
        initialPage,
        const Offset(0, 620),
      );
    }
    expect(
      switchedPage,
      isTrue,
      reason: 'video book must switch to a different release-bound page',
    );
  } else {
    expect(
      releaseVideoStage,
      findsOneWidget,
      reason: 'single-page video book must retain its exact release-bound work',
    );
  }

  await $.tester.tap(find.byKey(_worksTopBackKey).first);
  await $(find.byKey(_homeSearchChromeKey))
      .waitUntilVisible(timeout: const Duration(seconds: 40));
  expect(find.byKey(_homeSearchChromeKey), findsOneWidget);
  expect(
    _homeFeedOffset($),
    closeTo(feedOffsetBefore!, 1),
    reason: 'returning from video book must preserve the home feed position',
  );

  await $.tester.tap(find.byKey(_homeFeaturedEntryKey).first);
  expect(
    await _waitForAnyFinder($, <Finder>[
      find.byKey(TestKeys.worksImmersivePager),
    ]),
    isTrue,
    reason: 'app-core screenshot terminal must be the video book pager',
  );
  if (_videoPageCount == 1) {
    expect(
      await _waitForAnyFinder($, <Finder>[
        releaseVideoStage,
      ], timeout: const Duration(seconds: 60)),
      isTrue,
      reason: 'single-page video book re-entry must restore the same release-bound work',
    );
  }
}

double? _homeFeedOffset(PatrolIntegrationTester $) {
  final scrollable = find.descendant(
    of: find.byKey(_homeFeedKey),
    matching: find.byType(Scrollable),
  );
  if (scrollable.evaluate().isEmpty) {
    return null;
  }
  return $.tester.state<ScrollableState>(scrollable.first).position.pixels;
}

Future<bool> _dragToDifferentVideoBookPage(
  PatrolIntegrationTester $,
  PageController controller,
  double initialPage,
  Offset offset,
) async {
  final pager = find.byKey(TestKeys.worksImmersivePager);
  await $.tester.drag(pager.first, offset);
  await $.pump(const Duration(seconds: 1));
  final currentPage = controller.page;
  return currentPage != null && currentPage.round() != initialPage.round();
}

Future<void> _expectVideoPlayback(PatrolIntegrationTester $) async {
  final stageVisible = await _waitForAnyKey(
    $,
    _videoProbeKeys,
    timeout: const Duration(seconds: 60),
  );
  expect(
    stageVisible,
    isTrue,
    reason: 'configured video canary stage must render',
  );
  final ready = await _waitForAnyKey($, const <ValueKey<String>>[
    ValueKey<String>('video-player-ready'),
  ], timeout: const Duration(seconds: 60));
  expect(ready, isTrue, reason: 'native video player must reach ready state');
  expect(
    find.byKey(const ValueKey<String>('video-player-error')).evaluate(),
    isEmpty,
    reason:
        'Gateway success with Media unreachable must still fail this journey',
  );
}

Future<bool> _waitForAnyKey(
  PatrolIntegrationTester $,
  Iterable<Key> keys, {
  Duration timeout = const Duration(seconds: 40),
}) {
  return _waitForAnyFinder($, keys.map(find.byKey), timeout: timeout);
}

Future<bool> _waitForAnyFinder(
  PatrolIntegrationTester $,
  Iterable<Finder> finders, {
  Duration timeout = const Duration(seconds: 40),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (final finder in finders) {
      if (finder.evaluate().isNotEmpty) {
        return true;
      }
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return false;
}
