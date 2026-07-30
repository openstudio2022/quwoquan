import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/contact_search_result_page.dart';
import '../../../../../support/fakes/contact_profile_queries.dart';

void main() {
  testWidgets('联系人搜索真实渲染云侧能力位与添加主动作', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileQueryProvider.overrideWith(
            (ref, surface) => ContactProfileQueryFake(
              searchItems: <SocialRelationSearchItemView>[
                SocialRelationSearchItemView(
                  personaId: 'persona-alice',
                  userHandle: 'alice',
                  displayName: 'Alice',
                  headline: '摄影作者',
                  chatAvailable: false,
                  relationshipCapability: RelationshipCapabilityDto(
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
