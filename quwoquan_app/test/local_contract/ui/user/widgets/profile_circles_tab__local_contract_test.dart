import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

/// 圈子已从主页一级 Tab 收口到统计区入口。
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
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
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

  testWidgets('主页不再渲染圈子一级 Tab，统计区展示圈子入口', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scopedApp());
    await _pumpFrames(tester);

    expect(find.text(ChatText.contactsTabCircles), findsOneWidget);
    expect(find.text('极简摄影俱乐部'), findsNothing);
  });
}
