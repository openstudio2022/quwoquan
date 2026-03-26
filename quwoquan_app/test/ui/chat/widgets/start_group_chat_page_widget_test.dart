import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/start_group_chat_page.dart';

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final message = details.exception.toString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

void main() {
  testWidgets('选中联系人后可提交并跳转到新会话', (tester) async {
    _suppressImageErrors();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryProvider.overrideWithValue(MockChatRepository()),
          userProfileRepositoryProvider.overrideWithValue(
            const MockUserProfileRepository(),
          ),
        ],
        child: MaterialApp.router(
          routerConfig: GoRouter(
            initialLocation: '/chat/start-group',
            routes: [
              GoRoute(
                path: '/chat/start-group',
                builder: (context, state) => StartGroupChatPage(onBack: () {}),
              ),
              GoRoute(
                path: '/chat/:id',
                builder: (_, state) =>
                    Scaffold(body: Text('chat:${state.pathParameters['id']}')),
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.byType(StartGroupChatPage), findsOneWidget);
    expect(find.text('发起群聊（1）'), findsNothing);

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();

    expect(find.text('发起群聊（1）'), findsOneWidget);

    await tester.tap(find.text('发起群聊（1）'));
    await tester.pumpAndSettle();

    expect(find.textContaining('chat:conv_new_'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });
}
