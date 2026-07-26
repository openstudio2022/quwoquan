import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/contact_confirm_page.dart';
import '../../../../../support/fakes/contact_profile_queries.dart';

void main() {
  testWidgets('联系人确认页真实展示目标资料、来源和能力位主动作', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          personaQueryProvider.overrideWith(
            (ref, surface) => ContactPersonaQueryFake(
              profile: SubAccountProfileViewData(
                subAccountId: 'persona-alice',
                ownerUserId: 'owner-alice',
                subjectType: 'persona',
                userHandle: 'alice',
                username: 'alice',
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
    expect(
      find.text(UITextConstants.addContactConfirmSourceScan),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.addContactSheetTitle), findsWidgets);
  });
}

final class _ConfirmCapabilityRepository
    implements RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => true;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto(
      viewerSubAccountId: 'persona-current',
      targetSubAccountId: targetUserId,
      relationState: 'not_following',
      canFollow: true,
    );
  }
}
