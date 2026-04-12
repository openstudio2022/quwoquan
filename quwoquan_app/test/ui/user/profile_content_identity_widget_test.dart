import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_works_tab.dart';

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

Widget _buildApp() {
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
      darkTheme: ThemeData.dark(),
      home: const Scaffold(
        body: SizedBox(
          height: 800,
          child: ProfileWorksTab(
            mode: ProfileMode.mine,
            userId: 'nature_photographer',
            isDark: false,
          ),
        ),
      ),
    ),
  );
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 10}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  testWidgets('主页创作容器暴露 metadata 定义的四个筛选项', (tester) async {
    await tester.pumpWidget(_buildApp());
    await _pumpFrames(tester);

    expect(find.text('全部'), findsOneWidget);
    expect(find.text('图片'), findsOneWidget);
    expect(find.text('视频'), findsOneWidget);
    expect(find.text('文字'), findsOneWidget);
  });

  testWidgets('切到文字后可筛到文字作品', (tester) async {
    await tester.pumpWidget(_buildApp());
    await _pumpFrames(tester);

    await tester.tap(find.text('文字'));
    await _pumpFrames(tester, count: 4);

    expect(find.text('极简摄影的真谛'), findsOneWidget);
    expect(find.text('光影的节奏'), findsNothing);
  });
}
