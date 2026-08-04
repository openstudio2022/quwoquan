import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/user/account/user_account/domain/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_works_tab.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/content/content/post/mock_content_repository.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

Widget _buildApp() {
  return ProviderScope(
    overrides: [
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      ...mockContentFacetOverrides(MockContentRepository()),
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

  testWidgets('主页创作容器以内联二级页签暴露 metadata 定义的四个筛选项', (tester) async {
    await tester.pumpWidget(_buildApp());
    await _pumpFrames(tester);

    // 二级过滤改为内联横滑二级页签：四个过滤项常驻可见，默认选中「全部」。
    expect(
      find.byKey(const ValueKey<String>('profile-works-filter-button')),
      findsNothing,
    );
    expect(find.text('全部'), findsOneWidget);
    expect(find.text('图片'), findsOneWidget);
    expect(find.text('视频'), findsOneWidget);
    expect(find.text('长文'), findsOneWidget);
  });

  testWidgets('切到长文后可筛到长文作品', (tester) async {
    await tester.pumpWidget(_buildApp());
    await _pumpFrames(tester);

    await tester.tap(find.text('长文'));
    await _pumpFrames(tester, count: 4);

    expect(find.text('极简摄影的真谛'), findsOneWidget);
    expect(find.text('光影的节奏'), findsNothing);
  });
}
