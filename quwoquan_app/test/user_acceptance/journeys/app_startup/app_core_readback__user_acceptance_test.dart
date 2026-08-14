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
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_state_provider.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../support/runtime/patrol/patrol_core_readback_support.dart';
import '../../../support/runtime/patrol/patrol_environment_harness.dart';

const _videoWorkId = String.fromEnvironment('VIDEO_PLAYBACK_CANARY_WORK_ID');
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

const _feedCardProbeKeys = <ValueKey<String>>[
  ValueKey<String>('home-feed-card-0'),
  ValueKey<String>('feed-patch-reporter-0'),
  ValueKey<String>('dual-discovery-card-0'),
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
      await launchEnvironmentPatrolApp($);
      expect(
        find.text(FoundationText.startupRecoveryTitle),
        findsNothing,
        reason: 'recovery page is not a successful dual-platform baseline',
      );
      expect(
        _videoWorkId.trim(),
        isNotEmpty,
        reason:
            'app-core-readback requires an injected video playback canary work id',
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
      for (final projection in <String>[_creatorName, _tagLabel]) {
        expect(
          await _waitForAnyFinder($, <Finder>[find.textContaining(projection)]),
          isTrue,
          reason:
              'release-bound article must expose creator and tag projections',
        );
      }
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
      await _expectFeaturedVideoBook($);
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
        reason:
            'release-bound video source attribution must reach the App unchanged',
      );
    },
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
}

Future<void> _expectReleaseSurface(
  PatrolIntegrationTester $,
  String route,
  String expectedTitle, {
  required Finder readyFinder,
}) async {
  await patrolGoTo($, route);
  final retryFinder = find.text(ContentText.tryAgain);
  await _waitForAnyFinder($, <Finder>[readyFinder, retryFinder]);
  if (readyFinder.evaluate().isEmpty && retryFinder.evaluate().isNotEmpty) {
    await $(ContentText.tryAgain).tap();
    await _waitForAnyFinder($, <Finder>[readyFinder]);
  }
  expect(
    readyFinder,
    findsOneWidget,
    reason:
        'release $_releaseId route $route must reach its production surface; '
        'visible text=${_visibleTextSnapshot()}',
  );
  final titleFinder = find.textContaining(expectedTitle, findRichText: true);
  final rendered = await _waitForAnyFinder($, <Finder>[titleFinder]);
  expect(
    rendered,
    isTrue,
    reason:
        'release $_releaseId surface $route must render its expected title '
        '"$expectedTitle"; visible text=${_visibleTextSnapshot()}',
  );
}

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
  expect(
    $.tester.widget<AppAvatarImage>(avatarFinder).imageUrl.trim(),
    isNotEmpty,
    reason:
        'release avatar $_creatorAvatarAssetId must resolve to a public media URL',
  );
}

Future<void> _expectFeaturedVideoBook(PatrolIntegrationTester $) async {
  final opened = await _waitForAnyFinder($, <Finder>[
    find.text(AppConceptConstants.premium),
  ]);
  expect(opened, isTrue, reason: 'video book tab label must be reachable');
  await $.tap(find.text(AppConceptConstants.premium).first);
  await $.pump();
  await $.pump(const Duration(seconds: 1));
  final stageVisible = await _waitForAnyFinder($, <Finder>[
    find.byWidgetPredicate(
      (widget) =>
          widget.key is ValueKey<String> &&
          (widget.key! as ValueKey<String>).value.startsWith('works-video'),
      description: 'video book stage',
    ),
    ..._videoProbeKeys.map(find.byKey),
  ], timeout: const Duration(seconds: 60));
  expect(
    stageVisible,
    isTrue,
    reason: 'video book tab must show a real video stage',
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
    reason: 'video book must not settle on the canonical empty state '
        '(premium_stream pool must be release-bound non-empty)',
  );
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
