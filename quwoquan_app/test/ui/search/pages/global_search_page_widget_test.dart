import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/search/pages/global_search_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

GoRouter _buildRouter({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
  ),
  void Function(AssistantOpenContext?)? onAssistantOpenContext,
}) {
  return GoRouter(
    initialLocation: AppRoutePaths.globalSearch,
    routes: [
      GoRoute(
        path: AppRoutePaths.globalSearch,
        builder: (context, state) {
          return GlobalSearchPage(launchContext: launchContext);
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatDetailPathTemplate.replaceAll('{id}', ':id'),
        builder: (context, state) {
          final extra = state.extra is AssistantOpenContext
              ? state.extra! as AssistantOpenContext
              : null;
          onAssistantOpenContext?.call(extra);
          return Text('chat:${state.pathParameters['id']}');
        },
      ),
    ],
  );
}

Widget _buildApp({
  SearchLaunchContext launchContext = const SearchLaunchContext(
    entrySurfaceId: '/search',
  ),
  void Function(AssistantOpenContext?)? onAssistantOpenContext,
}) {
  return ProviderScope(
    child: MaterialApp.router(
      routerConfig: _buildRouter(
        launchContext: launchContext,
        onAssistantOpenContext: onAssistantOpenContext,
      ),
    ),
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await const MockUserProfileRepository().clearRecentSearches();
  });

  testWidgets('落地页展示本地最近搜索', (tester) async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'global_search_recent_entries_v1': jsonEncode(<Map<String, dynamic>>[
        <String, dynamic>{
          'entryId': 'recent_1',
          'query': '川西摄影',
          'scope': SearchScope.content.wireValue,
          'updatedAt': DateTime(2026, 3, 22, 10).toIso8601String(),
        },
      ]),
    });

    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    expect(find.text('最近搜索'), findsOneWidget);
    expect(find.text('川西摄影'), findsOneWidget);
    expect(find.text(SearchScope.content.label), findsWidgets);
  });

  testWidgets('输入关键词后展示跨域分组结果', (tester) async {
    await tester.pumpWidget(_buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '李',
    );
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pumpAndSettle();

    expect(find.text('社交关系'), findsWidgets);
    expect(find.text('聊天'), findsWidgets);
    expect(find.text('李想'), findsWidgets);
  });

  testWidgets('问小趣入口带搜索上下文跳转到助手对话', (tester) async {
    AssistantOpenContext? capturedContext;

    await tester.pumpWidget(
      _buildApp(
        onAssistantOpenContext: (context) {
          capturedContext = context;
        },
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey<String>('global_search_field')),
      '帮我找摄影圈',
    );
    await tester.pump();

    await tester.tap(find.text('问小趣'));
    await tester.pumpAndSettle();

    expect(
      find.text('chat:${AppConceptConstants.assistantConversationId}'),
      findsOneWidget,
    );
    expect(capturedContext?.source, AssistantSource.search);
    expect(capturedContext?.hints['sourceQuery'], '帮我找摄影圈');
    expect(capturedContext?.hints['fromGlobalSearch'], isTrue);
  });
}
