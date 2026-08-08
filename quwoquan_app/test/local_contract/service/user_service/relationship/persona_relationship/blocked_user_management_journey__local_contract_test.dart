// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/blocked_users_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'fixture_user_current',
    activePersonaId: 'fixture_user_current',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
}

typedef _ListBlockedHandler =
    Future<BlockedUserSlice> Function(ListBlockedUsersQuery query);
typedef _UnblockHandler =
    Future<BlockCommandResult> Function(UnblockUserCommand command);

final class _ControlledPersonaRelationshipFacet
    implements BlockCommandWriter, BlockedListQuery {
  const _ControlledPersonaRelationshipFacet({
    required this.onListBlocked,
    required this.onUnblock,
  });

  final _ListBlockedHandler onListBlocked;
  final _UnblockHandler onUnblock;

  @override
  Future<BlockCommandResult> blockUser(BlockUserCommand command) {
    throw UnsupportedError('blockUser is outside this page contract');
  }

  @override
  Future<BlockedUserSlice> listBlockedUsers(ListBlockedUsersQuery query) =>
      onListBlocked(query);

  @override
  Future<BlockCommandResult> unblockUser(UnblockUserCommand command) =>
      onUnblock(command);
}

void main() {
  testWidgets('Unblock ACK 不移除条目，直到 fresh Remote readback 确认缺席', (
    tester,
  ) async {
    final readback = Completer<BlockedUserSlice>();
    var listCall = 0;
    final facet = _ControlledPersonaRelationshipFacet(
      onListBlocked: (query) {
        listCall += 1;
        return listCall == 1
            ? Future.value(_slice(items: [_blockedItem]))
            : readback.future;
      },
      onUnblock: (command) async => _unblockedResult(command),
    );

    await _pumpPage(tester, facet);
    await _confirmUnblock(tester);

    expect(find.text(_blockedItem.displayName), findsOneWidget);
    expect(find.text(ContentText.blockedUsersEmptyTitle), findsNothing);

    readback.complete(_slice());
    await tester.pumpAndSettle();
    expect(find.text(ContentText.blockedUsersEmptyTitle), findsOneWidget);
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('fresh Remote readback 遍历到末页后才确认移除', (tester) async {
    final finalPage = Completer<BlockedUserSlice>();
    var listCall = 0;
    final facet = _ControlledPersonaRelationshipFacet(
      onListBlocked: (query) {
        listCall += 1;
        return switch (listCall) {
          1 => Future.value(_slice(items: [_blockedItem])),
          2 => Future.value(
            _slice(items: [_otherBlockedItem], nextCursor: 'next-page'),
          ),
          _ => finalPage.future,
        };
      },
      onUnblock: (command) async => _unblockedResult(command),
    );

    await _pumpPage(tester, facet);
    await _confirmUnblock(tester);
    expect(find.text(_blockedItem.displayName), findsOneWidget);

    finalPage.complete(_slice());
    await tester.pumpAndSettle();
    expect(find.text(_blockedItem.displayName), findsNothing);
    expect(listCall, 3);
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('Remote readback failure 保留 last-confirmed 条目与 retry', (
    tester,
  ) async {
    var listCall = 0;
    final facet = _ControlledPersonaRelationshipFacet(
      onListBlocked: (query) {
        listCall += 1;
        if (listCall == 1) {
          return Future.value(_slice(items: [_blockedItem]));
        }
        return Future.error(StateError('readback unavailable'));
      },
      onUnblock: (command) async => _unblockedResult(command),
    );

    await _pumpPage(tester, facet);
    await _confirmUnblock(tester);
    await tester.pumpAndSettle();

    _expectBlockedItemAndRetry();
  });

  testWidgets('Remote readback 未收敛时保留条目与 retry', (tester) async {
    var listCall = 0;
    final facet = _ControlledPersonaRelationshipFacet(
      onListBlocked: (query) {
        listCall += 1;
        return Future.value(_slice(items: [_blockedItem]));
      },
      onUnblock: (command) async => _unblockedResult(command),
    );

    await _pumpPage(tester, facet);
    await _confirmUnblock(tester);
    await tester.pumpAndSettle();

    expect(listCall, 2);
    _expectBlockedItemAndRetry();
  });

  testWidgets('超时后的 late readback 不得移除 last-confirmed 条目', (tester) async {
    final lateReadback = Completer<BlockedUserSlice>();
    var listCall = 0;
    final facet = _ControlledPersonaRelationshipFacet(
      onListBlocked: (query) {
        listCall += 1;
        return listCall == 1
            ? Future.value(_slice(items: [_blockedItem]))
            : lateReadback.future;
      },
      onUnblock: (command) async => _unblockedResult(command),
    );

    await _pumpPage(tester, facet);
    await _confirmUnblock(tester);
    await tester.pump(const Duration(seconds: 11));
    await tester.pump();
    _expectBlockedItemAndRetry();

    lateReadback.complete(_slice());
    await tester.pump();
    expect(find.text(_blockedItem.displayName), findsOneWidget);
  });

  testWidgets('被 mutation 取代的 late pagination response 不覆盖确认结果', (
    tester,
  ) async {
    final latePage = Completer<BlockedUserSlice>();
    var listCall = 0;
    final facet = _ControlledPersonaRelationshipFacet(
      onListBlocked: (query) {
        listCall += 1;
        return switch (listCall) {
          1 => Future.value(
            _slice(items: [_blockedItem], nextCursor: 'late-page'),
          ),
          2 => latePage.future,
          _ => Future.value(_slice()),
        };
      },
      onUnblock: (command) async => _unblockedResult(command),
    );

    await _pumpPage(tester, facet);
    await tester.tap(find.text(ContentText.loadMore));
    await tester.pump();
    await _confirmUnblock(tester);
    await tester.pumpAndSettle();
    expect(find.text(_blockedItem.displayName), findsNothing);

    latePage.complete(_slice(items: [_blockedItem]));
    await tester.pump();
    expect(find.text(_blockedItem.displayName), findsNothing);
    await tester.pump(const Duration(seconds: 4));
  });
}

Future<void> _pumpPage(
  WidgetTester tester,
  _ControlledPersonaRelationshipFacet facet,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        authSessionControllerProvider.overrideWith(
          _AuthenticatedSessionController.new,
        ),
        personaRelationshipBlockWriterProvider.overrideWith(
          (ref, surface) => facet,
        ),
        blockedListQueryProvider.overrideWithValue(facet),
      ],
      child: const CupertinoApp(home: BlockedUsersPage()),
    ),
  );
  await tester.pumpAndSettle();
  expect(find.text(_blockedItem.displayName), findsOneWidget);
}

Future<void> _confirmUnblock(WidgetTester tester) async {
  await tester.tap(find.text(ContentText.blockedUsersUnblock));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
  await tester.tap(
    find.widgetWithText(CupertinoDialogAction, ContentText.blockedUsersUnblock),
  );
  await tester.pump();
}

void _expectBlockedItemAndRetry() {
  expect(find.text(_blockedItem.displayName), findsOneWidget);
  expect(find.text(ContentText.blockedUsersEmptyTitle), findsNothing);
  expect(find.byType(CupertinoAlertDialog), findsOneWidget);
  expect(find.text(ContentText.tryAgain), findsOneWidget);
}

BlockCommandResult _unblockedResult(UnblockUserCommand command) =>
    BlockCommandResult(
      targetPersonaId: command.targetPersonaId,
      blocked: false,
      idempotentReplay: false,
      updatedAt: DateTime.utc(2026, 8, 8),
    );

BlockedUserSlice _slice({
  List<BlockedListItemView> items = const <BlockedListItemView>[],
  String? nextCursor,
}) => BlockedUserSlice(items: items, nextCursor: nextCursor);

final _blockedItem = BlockedListItemView(
  targetPersonaId: 'ps_target',
  displayName: 'Blocked Target',
  userHandle: 'blocked-target',
  avatarUrl: '',
  blockedAt: DateTime.utc(2026, 8, 8),
);

final _otherBlockedItem = BlockedListItemView(
  targetPersonaId: 'ps_other',
  displayName: 'Other Blocked User',
  userHandle: 'other-blocked-user',
  avatarUrl: '',
  blockedAt: DateTime.utc(2026, 8, 7),
);
