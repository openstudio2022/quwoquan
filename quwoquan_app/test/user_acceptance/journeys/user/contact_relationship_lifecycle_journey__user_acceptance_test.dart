import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/contact_search_result_page.dart';
import '../../../support/fakes/contact_profile_queries.dart';

void main() {
  testWidgets('搜索联系人后执行关注意图并回显已添加终态', (tester) async {
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
          userRelationshipStateProvider.overrideWith(
            _LifecycleRelationshipNotifier.new,
          ),
        ],
        child: const CupertinoApp(
          home: ContactSearchResultPage(initialQuery: 'alice'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.addContact), findsOneWidget);
    await tester.tap(find.text(UITextConstants.addContact));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.contactAlreadyAdded), findsWidgets);
    await tester.pump(const Duration(seconds: 4));
  });
}

final class _LifecycleRelationshipNotifier
    extends UserRelationshipStateNotifier {
  @override
  UserRelationshipState build() => const UserRelationshipState();

  @override
  Future<void> setFollowingWithSync(
    String subAccountId, {
    required bool currentFollowing,
    required bool shouldFollow,
    required AppUiSurface sourceSurface,
    bool flushImmediately = true,
  }) async {
    state = UserRelationshipState(
      followingSubAccountIds: shouldFollow
          ? <String>{subAccountId}
          : const <String>{},
      knownSubAccountIds: <String>{subAccountId},
    );
  }
}
