import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/contact_confirm_page.dart';

import '../../../../../support/service/user_service/persona_management/persona/contact_profile_queries.dart';

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-002
void main() {
  testWidgets('联系人确认页真实展示目标资料、来源和能力位主动作', (tester) async {
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(),
    ]);

    await _pumpPage(
      tester,
      capabilities: capabilities,
      commands: _RecordingRelationshipCommands(),
    );

    expect(find.text('Alice'), findsOneWidget);
    expect(find.textContaining('alice'), findsOneWidget);
    expect(find.text(ContactText.addContactConfirmSourceScan), findsOneWidget);
    expect(find.text(ContactText.addContactSheetTitle), findsWidgets);
  });

  testWidgets('Follow typed ACK 后仍等待 authoritative readback 才显示已添加', (
    tester,
  ) async {
    final readback = Completer<RelationshipCapabilityViewData>();
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(),
      () => readback.future,
    ]);
    final commands = _RecordingRelationshipCommands();
    await _pumpPage(tester, capabilities: capabilities, commands: commands);

    await tester.tap(_addButton());
    await tester.pump();

    expect(commands.followCalls, 1);
    expect(capabilities.calls, 2);
    expect(find.text(ContactText.contactAlreadyAdded), findsNothing);

    readback.complete(
      _capability(relationState: 'following', canFollow: false),
    );
    await tester.pumpAndSettle();

    expect(_addedButton(), findsOneWidget);
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('canFollow false 禁用主动作且不发 FollowUser', (tester) async {
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(canFollow: false),
    ]);
    final commands = _RecordingRelationshipCommands();
    await _pumpPage(tester, capabilities: capabilities, commands: commands);

    final button = tester.widget<CupertinoButton>(_addButton());
    expect(button.onPressed, isNull);
    expect(commands.followCalls, 0);
  });

  testWidgets('FollowUser Remote failure 保留候选并提供显式重试', (tester) async {
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(),
    ]);
    final commands = _RecordingRelationshipCommands(
      onFollow: () async => throw StateError('remote follow failed'),
    );
    await _pumpPage(tester, capabilities: capabilities, commands: commands);

    await tester.tap(_addButton());
    await tester.pumpAndSettle();

    expect(commands.followCalls, 1);
    expect(find.text('Alice'), findsOneWidget);
    expect(find.text(ContactText.contactAlreadyAdded), findsNothing);
    expect(find.text(ContentText.tryAgain), findsOneWidget);
  });

  testWidgets('FollowUser ACK 但 readback 未收敛时保留候选并提供重试', (tester) async {
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(),
      () async => _capability(),
    ]);
    final commands = _RecordingRelationshipCommands();
    await _pumpPage(tester, capabilities: capabilities, commands: commands);

    await tester.tap(_addButton());
    await tester.pumpAndSettle();

    expect(commands.followCalls, 1);
    expect(capabilities.calls, 2);
    expect(find.text('Alice'), findsOneWidget);
    expect(find.text(ContactText.contactAlreadyAdded), findsNothing);
    expect(find.text(ContentText.tryAgain), findsOneWidget);
  });

  testWidgets('超时 attempt 的 late readback 不覆盖新 attempt 已确认状态', (tester) async {
    final lateReadback = Completer<RelationshipCapabilityViewData>();
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(),
      () => lateReadback.future,
      () async => _capability(relationState: 'following', canFollow: false),
    ]);
    final commands = _RecordingRelationshipCommands();
    await _pumpPage(tester, capabilities: capabilities, commands: commands);

    await tester.tap(_addButton());
    await tester.pump();
    await tester.pump(const Duration(seconds: 11));
    await tester.pumpAndSettle();
    expect(find.text(ContentText.tryAgain), findsOneWidget);

    await tester.tap(find.text(ContentText.tryAgain));
    await tester.pumpAndSettle();
    expect(commands.followCalls, 2);
    expect(_addedButton(), findsOneWidget);

    lateReadback.complete(_capability());
    await tester.pump();
    expect(_addedButton(), findsOneWidget);
    await tester.pump(const Duration(seconds: 4));
  });
}

Future<void> _pumpPage(
  WidgetTester tester, {
  required _CapabilitySequence capabilities,
  required _RecordingRelationshipCommands commands,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        personaQueryProvider.overrideWith(
          (ref, surface) => ContactPersonaQueryFake(profile: _profile()),
        ),
        relationshipCapabilityRepositoryForSurfaceProvider.overrideWith(
          (ref, surface) => capabilities,
        ),
        personaRelationshipCommandWriterProvider.overrideWith(
          (ref, surface) => commands,
        ),
      ],
      child: const CupertinoApp(
        home: ContactConfirmPage(
          targetUserId: 'persona-alice',
          handle: 'alice',
          source: 'scan',
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Finder _addButton() =>
    find.widgetWithText(CupertinoButton, ContactText.addContactSheetTitle);

Finder _addedButton() =>
    find.widgetWithText(CupertinoButton, ContactText.contactAlreadyAdded);

PersonaProfileViewData _profile() => PersonaProfileViewData(
  personaId: 'persona-alice',
  ownerUserId: 'owner-alice',
  subjectType: 'persona',
  userHandle: 'alice',
  displayName: 'Alice',
  avatarUrl: '',
  backgroundUrl: '',
  bio: '摄影作者',
  followerCount: 12,
  followingCount: 8,
  postCount: 3,
  circleCount: 1,
  likeCount: 20,
  isolationLevel: 'open',
  profileVisibility: 'public',
  inheritsFromOwner: false,
  overriddenFields: const <String>[],
  updatedAt: DateTime.utc(2026, 7, 20),
);

RelationshipCapabilityViewData _capability({
  String relationState = 'not_following',
  bool canFollow = true,
  bool isBlocked = false,
  bool isBlockedBy = false,
}) => RelationshipCapabilityViewData(
  viewerPersonaId: 'persona-current',
  targetPersonaId: 'persona-alice',
  relationState: relationState,
  canFollow: canFollow,
  canUnfollow: relationState == 'following' || relationState == 'mutual',
  canFollowBack: relationState == 'followed_by',
  canGreet: true,
  canOpenConversation: false,
  canCreateDirectConversation: false,
  canSendMessage: false,
  hasPendingGreeting: false,
  hasFormalConversation: false,
  canStartVoiceCall: false,
  canStartVideoCall: false,
  isBlocked: isBlocked,
  isBlockedBy: isBlockedBy,
);

typedef _CapabilityStep = Future<RelationshipCapabilityViewData> Function();

final class _CapabilitySequence implements RelationshipCapabilityRepository {
  _CapabilitySequence(this._steps);

  final List<_CapabilityStep> _steps;
  int calls = 0;

  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => true;

  @override
  Future<RelationshipCapabilityViewData> getCapability(String targetUserId) {
    if (targetUserId != 'persona-alice') {
      throw StateError('unexpected target: $targetUserId');
    }
    if (calls >= _steps.length) {
      throw StateError('unexpected capability readback');
    }
    return _steps[calls++]();
  }
}

final class _RecordingRelationshipCommands
    implements PersonaRelationshipCommandWriter {
  _RecordingRelationshipCommands({this._onFollow});

  final Future<void> Function()? _onFollow;
  int followCalls = 0;

  @override
  Future<void> follow(
    String targetPersonaId, {
    required String sourceSurfaceId,
  }) async {
    if (targetPersonaId != 'persona-alice' ||
        sourceSurfaceId != 'addContactConfirm') {
      throw StateError('unexpected FollowUser command binding');
    }
    followCalls += 1;
    await _onFollow?.call();
  }

  @override
  Future<void> unfollow(String targetPersonaId) {
    throw UnsupportedError('unfollow is not part of this page contract');
  }
}
