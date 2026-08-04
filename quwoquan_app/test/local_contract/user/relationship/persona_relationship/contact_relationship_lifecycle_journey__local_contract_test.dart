// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/contact_search_result_page.dart';
import '../../../../support/fakes/contact_profile_queries.dart';

void main() {
  testWidgets('搜索联系人后执行关注意图并回显已添加终态', (tester) async {
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

    expect(find.text(ContactText.addContact), findsOneWidget);
    await tester.tap(find.text(ContactText.addContact));
    await tester.pumpAndSettle();

    expect(find.text(ContactText.contactAlreadyAdded), findsWidgets);
    await tester.pump(const Duration(seconds: 4));
  });
}

final class _LifecycleRelationshipNotifier
    extends UserRelationshipStateNotifier {
  @override
  UserRelationshipState build() => const UserRelationshipState();

  @override
  Future<void> setFollowingWithSync(
    String personaId, {
    required bool currentFollowing,
    required bool shouldFollow,
    required AppUiSurface sourceSurface,
    bool flushImmediately = true,
  }) async {
    state = UserRelationshipState(
      followingPersonaIds: shouldFollow
          ? <String>{personaId}
          : const <String>{},
      knownPersonaIds: <String>{personaId},
    );
  }
}
