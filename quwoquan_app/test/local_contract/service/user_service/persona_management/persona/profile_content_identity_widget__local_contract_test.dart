import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart'
    show profileRecommendationSlots;
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_works_tab.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/user_service/account/user_account/user_account_profile_typed_double.dart';

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

Widget _buildApp() {
  final posts = [
    contentPostViewDataBuilder(
      postId: 'profile-article',
      contentType: 'article',
      authorId: 'nature_photographer',
      title: '极简摄影的真谛',
    ),
    contentPostViewDataBuilder(
      postId: 'profile-photo',
      contentType: 'image',
      authorId: 'nature_photographer',
      title: '光影的节奏',
      mediaUrls: const [testContentImageUrl],
    ),
  ];
  return ProviderScope(
    overrides: [
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      ...mockContentFacetOverrides(
        store: InMemoryContentPostStore(posts: posts),
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
            recommendationSlots: profileRecommendationSlots,
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
