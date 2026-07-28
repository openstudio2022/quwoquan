// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-004
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

import '../../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';
import '../../../../support/fakes/test_profile_interaction_facets.dart';
import '../../../../support/harness/profile_shell_scroll_utils.dart';

/// 本地契约：主页一级 Tab 与互动二级导航使用明确的 typed Facet 状态。
class _NoNetworkHttpOverrides extends HttpOverrides {}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

class _EmptyIntersectionRepository implements IntersectionRepository {
  const _EmptyIntersectionRepository();

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async =>
      IntersectionInboxSummary(totalCount: 0, totalNewCount: 0);

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
  final contentConfig = MockContentRepository();
  return ProviderScope(
    overrides: [
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

    await tester.tap(
      find.text(ProfileText.profileInteractionDirectionSent),
    );
    await _pumpFrames(tester, count: 4);
    expect(
      find.text(ProfileText.profileShareInitiatedEmptyTitle),
      findsOneWidget,
    );
    expect(find.text('互动明细'), findsNothing);
  });
}
