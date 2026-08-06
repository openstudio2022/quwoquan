import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/contact_search_result_page.dart';
import '../../../../../support/service/user_service/persona_management/persona/contact_profile_queries.dart';

void main() {
  testWidgets('联系人搜索真实渲染云侧能力位与添加主动作', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileQueryProvider.overrideWith(
            (ref, surface) => ContactProfileQueryFake(
              searchItems: <SocialRelationSearchItemViewData>[
                SocialRelationSearchItemViewData(
                  personaId: 'persona-alice',
                  userHandle: 'alice',
                  displayName: 'Alice',
                  headline: '摄影作者',
                  chatAvailable: false,
                  relationshipCapability: RelationshipCapabilityViewData(
                    viewerPersonaId: 'persona-viewer',
                    targetPersonaId: 'persona-alice',
                    relationState: 'not_following',
                    canFollow: true,
                    canUnfollow: false,
                    canFollowBack: false,
                    canGreet: true,
                    canOpenConversation: false,
                    canCreateDirectConversation: false,
                    canSendMessage: false,
                    hasPendingGreeting: false,
                    hasFormalConversation: false,
                    canStartVoiceCall: false,
                    canStartVideoCall: false,
                    isBlocked: false,
                    isBlockedBy: false,
                  ),
                ),
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
    expect(find.text(ContactText.addContact), findsOneWidget);
    expect(find.text(ContactText.addContactSearchNoResult), findsNothing);
  });
}
