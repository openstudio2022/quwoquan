// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-004
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart'
    show profileRecommendationSlots;
import 'package:quwoquan_app/runtime/di/profile_presentation_slots.dart'
    show profileParticipantSlots;
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/presentation/profile_interaction_tab.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_shell.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/content_service/content/profile_interaction_activity_view/test_profile_interaction_facets.dart';
import '../../../../../support/service/user_service/persona_management/persona/profile_shell_scroll_utils.dart';
import '../../../../../support/service/user_service/account/user_account/user_account_profile_typed_double.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';

/// 本地契约：主页一级 Tab 与互动二级导航使用明确的 typed Facet 状态。
class _NoNetworkHttpOverrides extends HttpOverrides {}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

class _EmptyIntersectionRepository implements IntersectionRepository {
  const _EmptyIntersectionRepository();

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async =>
      const IntersectionInboxSummary(
        totalCount: 0,
        totalNewCount: 0,
        dimensions: [],
        generatedAt: '2026-08-03T00:00:00Z',
        totalStrengthenedCount: 0,
        totalReactivatedCount: 0,
      );

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 20,
  }) async => const <IntersectionReason>[];

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 20,
  }) async => const <IntersectionReason>[];
}

Widget _scopedApp() {
  final contentConfig = InMemoryContentConfigRepository();
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      behaviorRepositoryProvider.overrideWithValue(
        RecordingContentBehaviorRepository(),
      ),
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      authorImpactQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
      profileInteractionQueryFacetProvider.overrideWithValue(
        const TestProfileInteractionFacets(),
      ),
      profileInteractionReadFactAppendFacetProvider.overrideWithValue(
        const TestProfileInteractionFacets(),
      ),
      contentConfigRepositoryProvider.overrideWithValue(contentConfig),
      intersectionRepositoryProvider.overrideWithValue(
        const _EmptyIntersectionRepository(),
      ),
    ],
    child: MaterialApp(
      theme: ThemeData.light(),
      home: const ProfileShell(
        recommendationSlots: profileRecommendationSlots,
        participantSlots: profileParticipantSlots,
        mode: ProfileMode.mine,
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
  tearDown(() {
    HttpOverrides.global = null;
  });

  testWidgets('我的主页可浏览创作/互动，圈子作为统计入口展示', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scopedApp());
    await _pumpFrames(tester);
    await revealProfilePrimaryTabs(tester);

    expect(
      find.byKey(const ValueKey<String>('profile-works-secondary-tabs')),
      findsOneWidget,
    );
    expect(find.text(ChatText.contactsTabCircles), findsOneWidget);

    await tapProfilePrimaryTab(tester, '互动');
    await _pumpFrames(tester);
    expect(find.byType(ProfileInteractionTab), findsOneWidget);
    expect(find.text('生活'), findsNothing);
  });

  testWidgets('我的主页互动转发可在二级同行切换收到与我发起', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scopedApp());
    await _pumpFrames(tester);
    await revealProfilePrimaryTabs(tester);
    await tapProfilePrimaryTab(tester, '互动');
    await _pumpFrames(tester);

    expect(find.text(ProfileText.interactionSubAll), findsNothing);
    await revealProfileSummaryWidget(
      tester,
      find.text(ProfileText.interactionSubShares),
    );
    await tester.tap(find.text(ProfileText.interactionSubShares));
    await _pumpFrames(tester, count: 4);
    expect(
      find.text(ProfileText.profileInteractionDirectionReceived),
      findsOneWidget,
    );
    expect(
      find.text(ProfileText.profileInteractionDirectionSent),
      findsOneWidget,
    );
    expect(
      find.text(ProfileText.profileShareReceivedEmptyTitle),
      findsOneWidget,
    );

    await tester.tap(find.text(ProfileText.profileInteractionDirectionSent));
    await _pumpFrames(tester, count: 4);
    expect(
      find.text(ProfileText.profileShareInitiatedEmptyTitle),
      findsOneWidget,
    );
    expect(find.text('互动明细'), findsNothing);
  });
}
