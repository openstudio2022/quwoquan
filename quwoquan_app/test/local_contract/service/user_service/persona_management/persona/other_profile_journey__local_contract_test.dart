// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-005
//
// This is intentionally a local contract. It injects profile/relationship
// doubles and blocks network, so it verifies the presentation shell rather
// than claiming Gamma Remote user acceptance evidence.
import 'dart:io';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart'
    show profileRecommendationSlots;
import 'package:quwoquan_app/runtime/di/profile_presentation_slots.dart'
    show profileParticipantSlots;
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/runtime/di/author_impact_provider.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_shell.dart';

import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/profile_interaction_activity_view/author_impact_fixtures.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/user_service/account/user_account/user_account_profile_typed_double.dart';

/// 他人主页（other 模式）头部操作（返回/更多）可达，更多面板提供
/// 分享/拉黑/举报；交集区不崩溃（无交集不占位）。
class _NoNetworkHttpOverrides extends HttpOverrides {}

class _EmptyIntersectionRepository implements IntersectionRepository {
  const _EmptyIntersectionRepository();

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return intersectionInboxSummaryFixture(totalCount: 0, totalNewCount: 0);
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 20,
  }) async {
    return const <IntersectionReason>[];
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    return const <IntersectionReason>[];
  }
}

class _StaticCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => true;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    return RelationshipCapabilityViewData(
      viewerPersonaId: 'viewer-profile',
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

Widget _scopedApp() {
  return ProviderScope(
    overrides: [
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      authorImpactQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
      intersectionRepositoryProvider.overrideWithValue(
        const _EmptyIntersectionRepository(),
      ),
      authorImpactProvider.overrideWith((ref, request) async {
        return AuthorImpactSummary(
          authorId: request.personaId,
          total: 1,
          items: <AuthorImpactItem>[
            authorImpactItemFixture(
              impactId: 'impact-server-fact-001',
              helpType: 'spread',
              action: 'share',
              intersectionDimension: 'content',
              tagRef: 'content/nature-photography',
              source: 'source:content_share',
              count: 1,
              primaryText: '有1位读者转发了这位作者的内容',
              subtitleText: '来自自然摄影内容分享',
            ),
          ],
        );
      }),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _StaticCapabilityRepository(),
      ),
    ],
    child: MaterialApp(
      theme: ThemeData.light(),
      home: const ProfileShell(
        recommendationSlots: profileRecommendationSlots,
        participantSlots: profileParticipantSlots,
        mode: ProfileMode.other,
        userId: 'nature_photographer',
      ),
    ),
  );
}

void _setPhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3.0;
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 20}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 80));
  }
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  testWidgets('他人主页头部返回/更多可达，更多面板含 分享/拉黑/举报', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scopedApp());
    await _pumpFrames(tester);

    expect(find.byType(ProfileShell), findsOneWidget);
    expect(find.text('有1位读者转发了这位作者的内容'), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.back), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.ellipsis), findsOneWidget);

    await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(AppBottomModalSurface), findsOneWidget);
    expect(find.text('分享'), findsOneWidget);
    expect(find.text('拉黑'), findsOneWidget);
    expect(find.text('举报'), findsOneWidget);

    await tester.tap(find.text('分享'));
    // 分享 = AppToast「即将上线」（非弹层）；页面含未 settle 的网络图占位，
    // 故用有限帧推进（与进入时 _pumpFrames 同策略），不能用 pumpAndSettle。
    await _pumpFrames(tester);
    expect(find.byType(AppBottomModalSurface), findsNothing);
    // 推进 AppToast 3s 自动消失定时器，避免 pending timer。
    await tester.pump(const Duration(seconds: 4));
  });
}
