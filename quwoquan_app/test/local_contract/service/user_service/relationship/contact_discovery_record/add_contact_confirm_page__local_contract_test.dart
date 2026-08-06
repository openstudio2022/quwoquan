import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/presentation/contact_confirm_page.dart';
import '../../../../../support/service/user_service/persona_management/persona/contact_profile_queries.dart';

void main() {
  testWidgets('联系人确认页真实展示目标资料、来源和能力位主动作', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          personaQueryProvider.overrideWith(
            (ref, surface) => ContactPersonaQueryFake(
              profile: PersonaProfileViewData(
                personaId: 'persona-alice',
                ownerUserId: 'owner-alice',
                subjectType: 'persona',
                userHandle: 'alice',
                displayName: 'Alice',
                avatarUrl: '',
                backgroundUrl: '',
                bio: '摄影作者',
                followerCount: 12,
                followingCount: 8,
                postCount: 3,
                circleCount: 1,
                likeCount: 20,
                isolationLevel: 'open',
                profileVisibility: 'public',
                inheritsFromOwner: false,
                overriddenFields: const <String>[],
                updatedAt: DateTime.utc(2026, 7, 20),
              ),
            ),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _ConfirmCapabilityRepository(),
          ),
        ],
        child: const CupertinoApp(
          home: ContactConfirmPage(
            targetUserId: 'persona-alice',
            handle: 'alice',
            source: 'scan',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Alice'), findsOneWidget);
    expect(find.textContaining('alice'), findsOneWidget);
    expect(find.text(ContactText.addContactConfirmSourceScan), findsOneWidget);
    expect(find.text(ContactText.addContactSheetTitle), findsWidgets);
  });
}

final class _ConfirmCapabilityRepository
    implements RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => true;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    return RelationshipCapabilityViewData(
      viewerPersonaId: 'persona-current',
      targetPersonaId: targetUserId,
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
    );
  }
}
