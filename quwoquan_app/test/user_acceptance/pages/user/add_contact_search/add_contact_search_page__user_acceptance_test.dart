import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/contact_search_result_page.dart';
import '../../../../support/fakes/contact_profile_queries.dart';

void main() {
  testWidgets('联系人搜索真实渲染云侧能力位与添加主动作', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileQueryProvider.overrideWith(
            (ref, surface) => ContactProfileQueryFake(
              searchItems: <SocialRelationSearchItemView>[
                SocialRelationSearchItemView.fromMap(<String, dynamic>{
                  'subAccountId': 'persona-alice',
                  'username': 'alice',
                  'displayName': 'Alice',
                  'headline': '摄影作者',
                  'relationshipCapability': <String, dynamic>{
                    'relationState': 'not_following',
                    'canFollow': true,
                    'canUnfollow': false,
                    'canOpenConversation': false,
                  },
                }),
              ],
            ),
          ),
        ],
        child: const CupertinoApp(
          home: ContactSearchResultPage(initialQuery: 'alice'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Alice'), findsOneWidget);
    expect(find.text(UITextConstants.addContact), findsOneWidget);
    expect(find.text(UITextConstants.addContactSearchNoResult), findsNothing);
  });
}
