// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/contact-home-relationship-projection/spec.md#gwt-001
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contacts_row.dart';
import 'package:quwoquan_app/runtime/di/navigation/chat_contact_navigation.dart';

void main() {
  testWidgets('联系人主页只使用 canonical userHandle，不以 personaId 回退', (tester) async {
    final row = ChatContactsRow(
      kind: ChatContactsRowKind.user,
      id: 'persona-42',
      personaId: 'persona-42',
      userHandle: 'alice_public',
      displayName: 'Alice',
      avatarUrl: '',
      subtitle: '',
    );
    final router = _routerFor(row);
    addTearDown(router.dispose);

    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.tap(find.byKey(const ValueKey<String>('open-contact')));
    await tester.pumpAndSettle();

    expect(find.text('profile:alice_public'), findsOneWidget);
    expect(find.text('profile:persona-42'), findsNothing);
  });

  testWidgets('联系人缺少 userHandle 时 fail-closed，不产生伪主页导航', (tester) async {
    final row = ChatContactsRow(
      kind: ChatContactsRowKind.user,
      id: 'persona-42',
      personaId: 'persona-42',
      displayName: 'Alice',
      avatarUrl: '',
      subtitle: '',
    );
    final router = _routerFor(row);
    addTearDown(router.dispose);

    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.tap(find.byKey(const ValueKey<String>('open-contact')));
    await tester.pumpAndSettle();

    expect(find.text('contact-list'), findsOneWidget);
    expect(find.textContaining('profile:'), findsNothing);
  });
}

GoRouter _routerFor(ChatContactsRow row) {
  return GoRouter(
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (context, state) => Scaffold(
          body: TextButton(
            key: const ValueKey<String>('open-contact'),
            onPressed: () => openChatContactsRow(context, row),
            child: const Text('contact-list'),
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.userProfilePathTemplate.replaceAll(
          '{userHandle}',
          ':userHandle',
        ),
        builder: (context, state) =>
            Text('profile:${state.pathParameters['userHandle'] ?? ''}'),
      ),
    ],
  );
}
