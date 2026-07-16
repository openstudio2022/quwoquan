import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

import '../../../support/harness/profile_shell_scroll_utils.dart';

/// T4 旅程：我的主页一级 2 Tab（创作/互动）端到端可达，圈子进入统计区。
class _NoNetworkHttpOverrides extends HttpOverrides {}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

Widget _scopedApp() {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
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

  testWidgets('我的主页可浏览创作/互动，圈子作为统计入口展示', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scopedApp());
    await _pumpFrames(tester);
    await revealProfilePrimaryTabs(tester);

    // 默认创作 Tab：二级子页存在。
    expect(
      find.byKey(const ValueKey<String>('profile-works-secondary-tabs')),
      findsOneWidget,
    );

    expect(find.text(UITextConstants.contactsTabCircles), findsOneWidget);

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

    expect(find.text(UITextConstants.interactionSubAll), findsNothing);
    await revealProfileSummaryWidget(
      tester,
      find.text(UITextConstants.interactionSubShares),
    );
    await tester.tap(find.text(UITextConstants.interactionSubShares));
    await _pumpFrames(tester, count: 4);
    expect(
      find.text(UITextConstants.profileInteractionDirectionReceived),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.profileInteractionDirectionSent),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.profileShareReceivedEmptyTitle),
      findsOneWidget,
    );

    await tester.tap(
      find.text(UITextConstants.profileInteractionDirectionSent),
    );
    await _pumpFrames(tester, count: 4);
    expect(
      find.text(UITextConstants.profileShareInitiatedEmptyTitle),
      findsOneWidget,
    );
    expect(find.text('互动明细'), findsNothing);
  });
}
