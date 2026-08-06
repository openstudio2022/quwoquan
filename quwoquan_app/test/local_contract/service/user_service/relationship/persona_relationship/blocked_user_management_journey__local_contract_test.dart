// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/blocked_users_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/user_service/relationship/persona_relationship/persona_relationship_typed_double.dart';

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

void main() {
  testWidgets('拉黑用户可在设置列表查看并解除（UAT 旅程）', (tester) async {
    final facet = InMemoryPersonaRelationshipFacet();
    await facet.blockUser(BlockUserCommand(targetPersonaId: 'ps_target'));

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

    expect(find.text('ps_target'), findsOneWidget);
    expect(find.text(ContentText.blockedUsersUnblock), findsOneWidget);

    await tester.tap(find.text(ContentText.blockedUsersUnblock));
    await tester.pumpAndSettle();
    await tester.tap(find.text(ContentText.blockedUsersUnblock).last);
    await tester.pumpAndSettle();

    expect(find.text(ContentText.blockedUsersEmptyTitle), findsOneWidget);
    final slice = await facet.listBlockedUsers(ListBlockedUsersQuery());
    expect(slice.items, isEmpty);
    await tester.pump(const Duration(seconds: 4));
  });
}
