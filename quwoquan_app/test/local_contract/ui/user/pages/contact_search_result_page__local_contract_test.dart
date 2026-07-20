import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/contact_search_result_page.dart';
import '../../../../support/fakes/contact_profile_queries.dart';

void main() {
  testWidgets('联系人搜索按 typed capability 渲染添加动作', (tester) async {
    await _pumpSearchPage(
      tester,
      ContactProfileQueryFake(
        searchItems: <SocialRelationSearchItemView>[
          SocialRelationSearchItemView.fromMap(<String, dynamic>{
            'subAccountId': 'persona-alice',
            'username': 'alice',
            'displayName': 'Alice',
            'relationshipCapability': <String, dynamic>{
              'relationState': 'not_following',
              'canFollow': true,
              'canUnfollow': false,
              'canOpenConversation': false,
            },
          }),
        ],
      ),
    );

    expect(find.text('Alice'), findsOneWidget);
    expect(find.text(UITextConstants.addContact), findsOneWidget);
  });

  testWidgets('联系人搜索失败展示结构化页面错误而非空结果', (tester) async {
    await _pumpSearchPage(
      tester,
      ContactProfileQueryFake(searchError: StateError('search unavailable')),
    );

    expect(find.text(UITextConstants.pageLoadFailedTitle), findsOneWidget);
    expect(find.text(UITextConstants.addContactSearchNoResult), findsNothing);
  });
}

Future<void> _pumpSearchPage(
  WidgetTester tester,
  ContactProfileQueryFake query,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [profileQueryProvider.overrideWith((ref, surface) => query)],
      child: const CupertinoApp(
        home: ContactSearchResultPage(initialQuery: 'alice'),
      ),
    ),
  );
  await tester.pumpAndSettle();
}
