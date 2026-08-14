// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-001.t4
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-002.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-004.t6
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart'
    show profileRecommendationSlots;
import 'package:quwoquan_app/runtime/di/profile_presentation_slots.dart'
    show profileParticipantSlots;
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_shell.dart';

import '../../../../../support/service/user_service/persona_management/persona/profile_shell_scroll_utils.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_repository_typed_double.dart';
import '../../../../../support/service/user_service/account/user_account/user_account_profile_typed_double.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

/// 创作 Tab（V5）：二级子页恰为 全部/图片/视频/长文，全链路无「微趣/moment」概念。
class _NoNetworkHttpOverrides extends HttpOverrides {}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

Widget _scopedApp() {
  return ProviderScope(
    overrides: [
      ...sealedCloudBoundaryOverrides(),
      // 记录 Tab 计数行只在列表成功结算后渲染（见 profile_works_count_row
      // 契约测试）；本用例断言计数行常驻位置，因此必须提供真实成功的
      // 作者作品读面，而不是让 works 请求撞封印边界失败。
      ...mockContentFacetOverrides(
        store: InMemoryContentPostStore(
          posts: [
            contentPostViewDataBuilder(
              postId: 'creations-tab-photo',
              contentType: 'image',
              authorId: 'nature_photographer',
              title: '光影的节奏',
              mediaUrls: const [testContentImageUrl],
            ),
          ],
        ),
      ),
      behaviorRepositoryProvider.overrideWithValue(
        RecordingContentBehaviorRepository(),
      ),
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      authorImpactQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      contentRuntimeConfigProvider.overrideWithValue(
        buildAlphaContentRuntimeConfigDefaults(),
      ),
      intersectionRepositoryProvider.overrideWithValue(
        InMemoryIntersectionRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
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

Future<void> _pumpFrames(WidgetTester tester, {int count = 12}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 80));
  }
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  test('codegen creationSubTabs 恰为 全部/图片/视频/长文（无 micro/moment）', () {
    final ids = UserProfileUIConfig.creationSubTabs.map((t) => t.id).toList();
    expect(ids, <String>['all', 'image', 'video', 'article']);
    expect(ids.contains('micro'), isFalse);
    expect(ids.contains('moment'), isFalse);
  });

  testWidgets('创作 Tab 二级过滤改为内联横滑二级页签，全部/图片/视频/长文常驻可见', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scopedApp());
    await _pumpFrames(tester);
    await revealProfilePrimaryTabs(tester);

    // 二级过滤与互动页同源：四个过滤项以横滑二级页签内联铺开、常驻可见，
    // 不再收敛为漏斗图标 + 浮层菜单。
    final subTabs = find.byKey(
      const ValueKey<String>('profile-works-secondary-tabs'),
    );
    expect(subTabs, findsOneWidget);

    // 旧漏斗入口与浮层菜单不再存在。
    expect(
      find.byKey(const ValueKey<String>('profile-works-filter-button')),
      findsNothing,
    );
    expect(find.byType(CupertinoActionSheet), findsNothing);

    for (final key in const <String>[
      'creation_sub_all',
      'creation_sub_image',
      'creation_sub_video',
      'creation_sub_text',
    ]) {
      expect(
        find.descendant(
          of: subTabs,
          matching: find.text(UITextConstants.contentLabelForKey(key)),
        ),
        findsOneWidget,
      );
    }

    // 数量统计放到二级页签之下，仍可见。
    expect(
      find.descendant(of: subTabs, matching: find.textContaining('条记录')),
      findsOneWidget,
    );

    // 无微趣残留
    expect(find.text('微趣'), findsNothing);
  });
}
