import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

/// T4 旅程：他人主页（other 模式）头部操作（返回/更多）可达，
/// 更多面板提供 分享/拉黑/举报；交集区不崩溃（无交集不占位）。
class _NoNetworkHttpOverrides extends HttpOverrides {}

class _StaticCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => true;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto(
      viewerSubAccountId: 'viewer-profile',
      targetSubAccountId: targetUserId,
      relationState: 'not_following',
      canFollow: true,
      canUnfollow: false,
      canFollowBack: false,
      canGreet: true,
      canOpenConversation: false,
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
      userProfileRepositoryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _StaticCapabilityRepository(),
      ),
    ],
    child: MaterialApp(
      theme: ThemeData.light(),
      home: const ProfileShell(
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
    await tester.pumpAndSettle();
    expect(find.byType(AppBottomModalSurface), findsNothing);
    await tester.pump(const Duration(seconds: 4));
  });
}
