// spec_ref: specs/feature-tree/spec.md#uat-003
// spec_ref: specs/feature-tree/chat-conversation/chat-experience-optimization/spec.md#sit-001
// spec_ref: specs/feature-tree/chat-conversation/chat-experience-optimization/chat-list-ui-polish/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/profile-commercial-readiness/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/profile-commercial-readiness/spec.md#gwt-002
/// user_acceptance Patrol: test-live 登录后核心社交 Remote readback。
///
/// 本旅程只消费 runner 从 current mutable test-live identity 打开的受保护会话，
/// 覆盖联系人四 tab、direct/group 会话与消息、本人主页/头像/works 恢复；不依赖
/// Data release。真实登录 UI 与短信 OTP 仍由独立 Provider Patrol 验收，本测试不将
/// token handoff 冒充登录行为。内容、Creator 与媒体只由 release-bound CORE 验收。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contact_home_filter.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contacts_row.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/presentation/chat_message_bubble.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_state_provider.dart';

import '../../../support/runtime/patrol/patrol_core_readback_support.dart';
import '../../../support/runtime/patrol/patrol_environment_harness.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';

const _requireAvatarMediaCanary = bool.fromEnvironment(
  'MEDIA_AVATAR_CANARY_REQUIRED',
  defaultValue: true,
);

const _profileProbeKeys = <ValueKey<String>>[
  ValueKey<String>('profile-header-avatar'),
  ValueKey<String>('profile-shell-summary-card'),
];

void main() {
  patrolTest(
    'environment_post_auth_core_social_readback',
    tags: ['user-acceptance', 'environment-smoke'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 12)),
    ($) async {
      await launchEnvironmentPatrolApp($);
      expect(
        find.text(FoundationText.startupRecoveryTitle),
        findsNothing,
        reason: 'recovery page is not a successful post-auth baseline',
      );
      expect(
        _requireAvatarMediaCanary,
        isTrue,
        reason:
            'MEDIA_AVATAR_CANARY_REQUIRED cannot disable the trusted avatar readback',
      );

      final session = patrolAuthenticatedSession(patrolMountedContainer());
      expect(
        session.ownerId.trim(),
        isNotEmpty,
        reason: 'test-live runner must open a protected current owner session',
      );
      expect(
        session.activePersonaId.trim(),
        isNotEmpty,
        reason:
            'test-live runner must open a protected current persona session',
      );

      final provision = await provisionPatrolCoreChatConversation($);
      await patrolGoTo($, AppRoutePaths.chat);
      await _expectProvisionedChatInbox($, provision);
      await patrolGoTo($, AppRoutePaths.chat);
      await _expectChatBusinessSurfaces($);
      await patrolGoTo($, AppRoutePaths.profile);
      await _expectProfileMatchesSession($);
    },
  );
}

Future<void> _expectProvisionedChatInbox(
  PatrolIntegrationTester $,
  PatrolCoreChatProvision provision,
) async {
  final rowKey = ValueKey<String>('chat-inbox-row-${provision.conversationId}');
  expect(
    await _waitForAnyFinder($, <Finder>[find.byKey(rowKey)]),
    isTrue,
    reason:
        'message inbox must show the Remote-provisioned conversation '
        '(${provision.conversationId})',
  );
  await $.tap(find.byKey(rowKey));
  await $.pump();
  expect(
    await _waitForAnyFinder($, <Finder>[
      find.textContaining(provision.messageText),
    ]),
    isTrue,
    reason: 'opening the provisioned conversation must show its Remote message',
  );
}

Future<void> _expectChatBusinessSurfaces(PatrolIntegrationTester $) async {
  final readback = await readPatrolCoreBusinessReadback($);
  for (final filter in const <String>['all', 'direct', 'group']) {
    expect(
      readback.messageRows[filter],
      isNotEmpty,
      reason: 'message home $filter must contain Remote-provisioned data',
    );
  }

  final directRow = readback.messageRows['direct']!.first;
  final groupRow = readback.messageRows['group']!.first;
  for (final entry in <String, String>{
    ChatText.chatPrivateMessages: directRow.id,
    ChatText.groupChat: groupRow.id,
  }.entries) {
    await $.tap(find.text(entry.key).last);
    await $.pump();
    final rowFinder = find.byKey(
      ValueKey<String>('chat-inbox-row-${entry.value}'),
    );
    expect(
      await _waitForAnyFinder($, <Finder>[rowFinder]),
      isTrue,
      reason: '${entry.key} tab must render its Remote conversation row',
    );
    await $.tap(rowFinder);
    await $.pump();
    expect(
      await _waitForAnyFinder($, <Finder>[find.byType(ChatMessageBubble)]),
      isTrue,
      reason: '${entry.key} conversation must render Remote message bubbles',
    );
    await patrolGoTo($, AppRoutePaths.chat);
  }

  await $.tap(find.text(ChatText.chatPrimaryContacts).first);
  await $.pump();
  const contactTabs = <ChatContactHomeFilter, String>{
    ChatContactHomeFilter.all: ChatText.contactsTabAll,
    ChatContactHomeFilter.mutual: ChatText.contactsTabMutualFollow,
    ChatContactHomeFilter.circle: ChatText.contactsTabCircles,
    ChatContactHomeFilter.group: ChatText.contactsTabGroups,
  };
  for (final entry in contactTabs.entries) {
    final rows = readback.contactRows[entry.key]!;
    expect(
      rows,
      isNotEmpty,
      reason: 'contact home ${entry.key.wireValue} must not be empty',
    );
    await $.tap(find.text(entry.value).last);
    await $.pump();
    expect(
      await _waitForAnyFinder($, <Finder>[
        find.byKey(ValueKey<String>('chat-contact-row-${rows.first.id}')),
      ]),
      isTrue,
      reason: '${entry.value} tab must render its Remote contact row',
    );
  }

  final userRows = readback.contactRows[ChatContactHomeFilter.all]!
      .where((row) => row.kind == ChatContactsRowKind.user)
      .toList(growable: false);
  expect(userRows, isNotEmpty, reason: 'all contacts must include user rows');
  expect(
    userRows.every((row) => row.avatarUrl.trim().isNotEmpty),
    isTrue,
    reason: 'Remote contact users must expose loadable avatar URLs',
  );
  await $.tap(find.text(ChatText.contactsTabAll).last);
  await $.pump();
  final userRow = userRows.first;
  final userRowFinder = find.byKey(
    ValueKey<String>('chat-contact-row-${userRow.id}'),
  );
  expect(
    await _waitForAnyFinder($, <Finder>[userRowFinder]),
    isTrue,
    reason: 'all contacts must render its Remote user row',
  );
  final avatarImage = find.descendant(
    of: userRowFinder,
    matching: find.byType(AppCachedNetworkImage),
  );
  expect(
    avatarImage,
    findsOneWidget,
    reason: 'Remote contact avatar must enter the trusted image pipeline',
  );
  expect(
    $.tester.widget<AppCachedNetworkImage>(avatarImage).imageUrl.trim(),
    userRow.avatarUrl.trim(),
    reason: 'contact row must render the exact Remote avatar projection',
  );
}

Future<void> _expectProfileMatchesSession(PatrolIntegrationTester $) async {
  final session = patrolAuthenticatedSession(patrolMountedContainer());
  expect(
    await _waitForAnyKey($, _profileProbeKeys),
    isTrue,
    reason: 'my profile shell must render',
  );
  final profileState = await _waitForProfileTerminal(
    $,
    session.activePersonaId,
  );
  final profile = profileState.profile;
  expect(
    profile,
    isNotNull,
    reason: 'my profile must resolve the authenticated Remote identity',
  );
  expect(profile!.personaId, session.activePersonaId);
  expect(profile.ownerUserId, session.ownerId);
  expect(
    profile.avatarUrl.trim(),
    isNotEmpty,
    reason: 'my profile must expose the API-provisioned avatar URL',
  );
  const avatarKey = ValueKey<String>('profile-header-avatar-image');
  final avatarFinder = find.byKey(avatarKey);
  expect(
    await _waitForAnyFinder($, <Finder>[avatarFinder]),
    isTrue,
    reason: 'my profile avatar must enter the trusted image pipeline',
  );
  expect(
    $.tester.widget<AppAvatarImage>(avatarFinder).imageUrl.trim(),
    profile.avatarUrl.trim(),
    reason: 'my profile must render the exact Remote avatar projection',
  );
  expect(
    profileState.isWorksLoading,
    isFalse,
    reason: 'my profile works must reach a terminal state',
  );
  expect(
    profileState.worksFailure,
    isNull,
    reason: 'my profile works query must not finish in an error state',
  );
}

Future<ProfileState> _waitForProfileTerminal(
  PatrolIntegrationTester $,
  String personaId, {
  Duration timeout = const Duration(seconds: 45),
}) async {
  final container = patrolMountedContainer();
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    final state = container.read(profileNotifierProvider(personaId));
    if (state.profile != null &&
        !state.isIdentityLoading &&
        !state.isWorksLoading) {
      return state;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return container.read(profileNotifierProvider(personaId));
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
