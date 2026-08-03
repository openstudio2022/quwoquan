// spec_ref: specs/feature-tree/spec.md#uat-003
// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
/// user_acceptance Patrol: 四核心 Remote readback 组合旅程。
///
/// 覆盖首页非空卡片、视频书首帧、消息收件箱（先 Remote provision）与我的会话一致。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

import '../../../support/patrol/patrol_core_readback_support.dart';
import '../../../support/patrol/patrol_environment_harness.dart';

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
const _tagLabel = String.fromEnvironment('DATA_RELEASE_TAG_LABEL');
const _videoAttribution = String.fromEnvironment(
  'DATA_RELEASE_VIDEO_ATTRIBUTION',
);

const _feedCardProbeKeys = <ValueKey<String>>[
  ValueKey<String>('home-feed-card-0'),
  ValueKey<String>('dual-discovery-card-0'),
];
const _profileProbeKeys = <ValueKey<String>>[
  ValueKey<String>('profile-header-avatar'),
  ValueKey<String>('profile-shell-summary-card'),
];
const _videoProbeKeys = <ValueKey<String>>[
  ValueKey<String>('works-video-stage-$_videoWorkId-0'),
  ValueKey<String>('works-video-$_videoWorkId-0'),
  ValueKey<String>('home-video-player-$_videoWorkId'),
];

void main() {
  patrolTest(
    'environment_app_core_readback',
    tags: ['t4', 'app-core-readback', 'environment-smoke'],
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

      final provision = await provisionPatrolCoreChatConversation($);
      await _expectHomeFeed($);
      await _expectReleaseSurface(
        $,
        AppRoutePaths.homepageDetail(id: _homepageId),
        _homepageTitle,
      );
      await _expectReleaseSurface(
        $,
        AppRoutePaths.workBrowser(
          workId: _articleWorkId,
          source: 'releaseReadback',
        ),
        _articleTitle,
      );
      expect(
        await _waitForAnyFinder($, <Finder>[
          find.textContaining(_creatorName),
          find.textContaining(_tagLabel),
        ]),
        isTrue,
        reason:
            'release-bound article must expose its creator or tag projection',
      );
      await _expectReleaseSurface(
        $,
        AppRoutePaths.workBrowser(
          workId: _imageWorkId,
          source: 'releaseReadback',
        ),
        _imageTitle,
      );
      await _expectFeaturedVideoBook($);
      await patrolGoTo($, AppRoutePaths.chat);
      await _expectProvisionedChatInbox($, provision);
      await patrolGoTo($, AppRoutePaths.profile);
      await _expectProfileMatchesSession($);
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
  String expectedTitle,
) async {
  await patrolGoTo($, route);
  expect(
    await _waitForAnyFinder($, <Finder>[find.textContaining(expectedTitle)]),
    isTrue,
    reason: 'release $_releaseId surface must render its expected title',
  );
}

Future<void> _expectHomeFeed(PatrolIntegrationTester $) async {
  final visible = await _waitForAnyKey($, _feedCardProbeKeys);
  expect(
    visible,
    isTrue,
    reason: 'home feed must render at least one real card, not HTTP 200 alone',
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
}

Future<void> _expectProvisionedChatInbox(
  PatrolIntegrationTester $,
  PatrolCoreChatProvision provision,
) async {
  final rowKey = ValueKey<String>('chat-inbox-row-${provision.conversationId}');
  final visible = await _waitForAnyFinder($, <Finder>[
    find.byKey(rowKey),
    find.textContaining(provision.messageText),
  ]);
  expect(
    visible,
    isTrue,
    reason:
        'message inbox must show the Remote-provisioned conversation '
        '(${provision.conversationId})',
  );
  await $.tap(find.byKey(rowKey));
  await $.pump();
  await $.pump(const Duration(seconds: 1));
  final opened = await _waitForAnyFinder($, <Finder>[
    find.textContaining(provision.messageText),
  ]);
  expect(
    opened,
    isTrue,
    reason: 'opening the provisioned conversation must show the seeded message',
  );
}

Future<void> _expectProfileMatchesSession(PatrolIntegrationTester $) async {
  final session = patrolAuthenticatedSession(patrolMountedContainer());
  final visible = await _waitForAnyKey($, _profileProbeKeys);
  expect(visible, isTrue, reason: 'my profile shell must render');
  expect(
    session.ownerId.trim(),
    isNotEmpty,
    reason: 'profile journey requires authenticated owner id',
  );
  expect(
    session.activePersonaId.trim(),
    isNotEmpty,
    reason: 'profile journey requires authenticated persona id',
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
