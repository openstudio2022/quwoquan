// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-002
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_homepage_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/contact_search_result_page.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/user_service/persona_management/persona/contact_profile_queries.dart';

void main() {
  testWidgets('搜索 capability 不允许关注时保留候选但禁用动作', (tester) async {
    final commands = _RecordingRelationshipCommands();
    await _pumpSearchPage(
      tester,
      profileQuery: ContactProfileQueryFake(
        searchItems: <SocialRelationSearchItemViewData>[
          _searchItem(
            displayName: 'Alice',
            capability: _capability(canFollow: false, isBlocked: true),
          ),
        ],
      ),
      capabilities: _CapabilitySequence(const <_CapabilityStep>[]),
      commands: commands,
    );

    expect(find.text('Alice'), findsOneWidget);
    expect(_actionButton(tester, ContactText.addContact).onPressed, isNull);
    expect(commands.followCalls, 0);
  });

  testWidgets('fresh preflight 与 Follow ACK 后 readback 收敛才显示已添加', (
    tester,
  ) async {
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(),
      () async => _capability(relationState: 'following', canFollow: false),
    ]);
    final commands = _RecordingRelationshipCommands();
    await _pumpSearchPage(
      tester,
      capabilities: capabilities,
      commands: commands,
    );

    await tester.tap(find.text(ContactText.addContact));
    await tester.pumpAndSettle();

    expect(commands.followCalls, 1);
    expect(capabilities.calls, 2);
    expect(
      _actionButton(tester, ContactText.contactAlreadyAdded).onPressed,
      isNull,
    );
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('fresh preflight 发现 blocked 时不发命令并保留结果与重试', (tester) async {
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(canFollow: false, isBlocked: true),
    ]);
    final commands = _RecordingRelationshipCommands();
    await _pumpSearchPage(
      tester,
      capabilities: capabilities,
      commands: commands,
    );

    await tester.tap(find.text(ContactText.addContact));
    await tester.pumpAndSettle();

    expect(commands.followCalls, 0);
    expect(find.text('Alice'), findsOneWidget);
    expect(find.text(ContentText.tryAgain), findsOneWidget);
  });

  testWidgets('FollowUser Remote failure 保留搜索结果且 retry 在 pending 解除后可用', (
    tester,
  ) async {
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(),
      () async => _capability(),
    ]);
    final commands = _RecordingRelationshipCommands(
      onFollow: () async => throw StateError('remote follow failed'),
    );
    await _pumpSearchPage(
      tester,
      capabilities: capabilities,
      commands: commands,
    );

    await tester.tap(find.text(ContactText.addContact));
    await tester.pumpAndSettle();
    expect(commands.followCalls, 1);
    expect(find.text('Alice'), findsOneWidget);
    expect(find.text(ContentText.tryAgain), findsOneWidget);

    await tester.tap(find.text(ContentText.tryAgain));
    await tester.pumpAndSettle();
    expect(commands.followCalls, 2);
    expect(find.text('Alice'), findsOneWidget);
  });

  testWidgets('Follow ACK 但 authoritative readback 未收敛时不显示伪成功', (tester) async {
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(),
      () async => _capability(),
    ]);
    final commands = _RecordingRelationshipCommands();
    await _pumpSearchPage(
      tester,
      capabilities: capabilities,
      commands: commands,
    );

    await tester.tap(find.text(ContactText.addContact));
    await tester.pumpAndSettle();

    expect(commands.followCalls, 1);
    expect(find.text('Alice'), findsOneWidget);
    expect(find.text(ContactText.contactAlreadyAdded), findsNothing);
    expect(find.text(ContentText.tryAgain), findsOneWidget);
  });

  testWidgets('超时 attempt 的 late readback 不覆盖新 attempt 已确认状态', (tester) async {
    final lateReadback = Completer<RelationshipCapabilityViewData>();
    final capabilities = _CapabilitySequence(<_CapabilityStep>[
      () async => _capability(),
      () => lateReadback.future,
      () async => _capability(),
      () async => _capability(relationState: 'following', canFollow: false),
    ]);
    final commands = _RecordingRelationshipCommands();
    await _pumpSearchPage(
      tester,
      capabilities: capabilities,
      commands: commands,
    );

    await tester.tap(find.text(ContactText.addContact));
    await tester.pump();
    await tester.pump(const Duration(seconds: 11));
    await tester.pumpAndSettle();
    expect(find.text(ContentText.tryAgain), findsOneWidget);

    await tester.tap(find.text(ContentText.tryAgain));
    await tester.pumpAndSettle();
    expect(commands.followCalls, 2);
    expect(
      _actionButton(tester, ContactText.contactAlreadyAdded).onPressed,
      isNull,
    );

    lateReadback.complete(_capability());
    await tester.pump();
    expect(
      _actionButton(tester, ContactText.contactAlreadyAdded).onPressed,
      isNull,
    );
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('同 query 并发搜索只接受最新 generation', (tester) async {
    final first = Completer<List<SocialRelationSearchItemViewData>>();
    final second = Completer<List<SocialRelationSearchItemViewData>>();
    final search = _SearchSequence(<_SearchStep>[
      (query) => first.future,
      (query) => second.future,
    ]);
    await _pumpSearchPage(
      tester,
      profileQuery: search,
      capabilities: _CapabilitySequence(const <_CapabilityStep>[]),
      commands: _RecordingRelationshipCommands(),
      settle: false,
    );
    expect(search.calls, 1);

    await tester.tap(find.byType(CupertinoSearchTextField));
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pump();
    expect(search.calls, 2);

    second.complete(<SocialRelationSearchItemViewData>[
      _searchItem(displayName: 'Latest'),
    ]);
    await tester.pump();
    await tester.pump();
    expect(find.text('Latest'), findsOneWidget);

    first.complete(<SocialRelationSearchItemViewData>[
      _searchItem(displayName: 'Stale'),
    ]);
    await tester.pump();
    await tester.pump();
    expect(find.text('Latest'), findsOneWidget);
    expect(find.text('Stale'), findsNothing);
  });
}

Future<void> _pumpSearchPage(
  WidgetTester tester, {
  ProfileQuery? profileQuery,
  required _CapabilitySequence capabilities,
  required _RecordingRelationshipCommands commands,
  bool settle = true,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        profileQueryProvider.overrideWith(
          (ref, surface) =>
              profileQuery ??
              ContactProfileQueryFake(
                searchItems: <SocialRelationSearchItemViewData>[
                  _searchItem(displayName: 'Alice'),
                ],
              ),
        ),
        relationshipCapabilityRepositoryForSurfaceProvider.overrideWith(
          (ref, surface) => capabilities,
        ),
        personaRelationshipCommandWriterProvider.overrideWith(
          (ref, surface) => commands,
        ),
      ],
      child: const CupertinoApp(
        home: ContactSearchResultPage(initialQuery: 'alice'),
      ),
    ),
  );
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    await tester.pump();
  }
}

CupertinoButton _actionButton(WidgetTester tester, String label) {
  final buttons = tester.widgetList<CupertinoButton>(
    find.ancestor(of: find.text(label), matching: find.byType(CupertinoButton)),
  );
  return buttons.firstWhere(
    (button) => button.child is Text && (button.child as Text).data == label,
  );
}

SocialRelationSearchItemViewData _searchItem({
  required String displayName,
  RelationshipCapabilityViewData? capability,
}) => SocialRelationSearchItemViewData(
  personaId: 'persona-alice',
  userHandle: 'alice',
  displayName: displayName,
  chatAvailable: false,
  relationshipCapability: capability ?? _capability(),
);

RelationshipCapabilityViewData _capability({
  String relationState = 'not_following',
  bool canFollow = true,
  bool isBlocked = false,
  bool isBlockedBy = false,
}) => RelationshipCapabilityViewData(
  viewerPersonaId: 'persona-viewer',
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
      throw StateError('unexpected capability read');
    }
    return _steps[calls++]();
  }
}

final class _RecordingRelationshipCommands
    implements PersonaRelationshipCommandWriter {
  _RecordingRelationshipCommands({this.onFollow});

  final Future<void> Function()? onFollow;
  int followCalls = 0;

  @override
  Future<void> follow(
    String targetPersonaId, {
    required String sourceSurfaceId,
  }) async {
    if (targetPersonaId != 'persona-alice' ||
        sourceSurfaceId != 'addContactSearch') {
      throw StateError('unexpected FollowUser command binding');
    }
    followCalls += 1;
    await onFollow?.call();
  }

  @override
  Future<void> unfollow(String targetPersonaId) {
    throw UnsupportedError('unfollow is not part of this page contract');
  }
}

typedef _SearchStep =
    Future<List<SocialRelationSearchItemViewData>> Function(String query);

final class _SearchSequence implements ProfileQuery {
  _SearchSequence(this._steps);

  final List<_SearchStep> _steps;
  int calls = 0;

  @override
  Future<List<SocialRelationSearchItemViewData>> searchSocialRelations({
    required String query,
    int limit = 20,
  }) {
    if (calls >= _steps.length) {
      throw StateError('unexpected search request');
    }
    return _steps[calls++](query);
  }

  @override
  Future<PersonaProfileViewData> getUserProfile(String userId) {
    throw UnsupportedError('profile detail is outside this page contract');
  }

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(String personaId) {
    throw UnsupportedError('homepage is outside this page contract');
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) {
    throw UnsupportedError('stats are outside this page contract');
  }
}
