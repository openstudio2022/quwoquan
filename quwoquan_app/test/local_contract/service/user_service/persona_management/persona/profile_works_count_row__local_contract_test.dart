// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-002.t1
//
// 记录 Tab 计数行三态契约：「共有 N 条记录」只允许表达真实结算结果。
// - 列表请求整页失败（无缓存）→ 不得渲染「共有 0 条记录」，只渲染错误态；
// - 成功空列表 → 渲染「共有 0 条记录」+ 真实空态文案；
// - 成功有数据 → 渲染真实计数。
// 回归背景：gamma 上 ListUserPosts 契约漂移导致整页解码失败时，页面同时
// 出现「共有 0 条记录」与「内容暂时无法显示」，伪空态冒充事实计数。
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart'
    show profileRecommendationSlots;
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_works_tab.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentAuthorPostsQuery;

import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/user_service/account/user_account/user_account_profile_typed_double.dart';

class _NoNetworkHttpOverrides extends HttpOverrides {}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

/// 对象级 typed double：作者作品读面整页失败（如契约解码 FormatException）。
final class _ThrowingAuthorPostsReader implements ContentAuthorPostsReader {
  const _ThrowingAuthorPostsReader(this.error);

  final Object error;

  @override
  Future<CursorPage<ContentPostViewData>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = ContentAuthorPostsQuery.defaultLimit,
  }) {
    return Future.error(error);
  }
}

Widget _buildApp({
  required InMemoryContentPostStore store,
  ContentAuthorPostsReader? authorPostsReader,
}) {
  return ProviderScope(
    overrides: [
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      ...mockContentFacetOverrides(
        store: store,
        authorPostsReader: authorPostsReader,
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
    ],
    child: MaterialApp(
      theme: ThemeData.light(),
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

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  testWidgets('列表整页失败且无缓存：不渲染「共有 0 条记录」，只渲染错误态', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        store: InMemoryContentPostStore(),
        authorPostsReader: _ThrowingAuthorPostsReader(
          const FormatException(
            'ContentPostProjection: unknown wire field "status"',
          ),
        ),
      ),
    );
    await _pumpFrames(tester);

    // 伪空态禁止：错误态与「共有 0 条记录」不得同屏。
    expect(find.textContaining('条记录'), findsNothing);
    expect(find.byType(AppSectionErrorState), findsOneWidget);
    // 契约解码失败映射到 invalidContent 恢复组（与 gamma 真实事故同文案）。
    expect(find.text(SearchText.recoveryInvalidContentTitle), findsOneWidget);
  });

  testWidgets('成功空列表：渲染「共有 0 条记录」与真实空态文案', (tester) async {
    await tester.pumpWidget(_buildApp(store: InMemoryContentPostStore()));
    await _pumpFrames(tester);

    expect(find.text(UITextConstants.profileRecordsTotal(0)), findsOneWidget);
    expect(
      find.text(ProfileText.profileCreationEmptyAllMine),
      findsOneWidget,
    );
    expect(find.byType(AppSectionErrorState), findsNothing);
  });

  testWidgets('成功有数据：渲染真实计数', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        store: InMemoryContentPostStore(
          posts: [
            contentPostViewDataBuilder(
              postId: 'works-count-article',
              contentType: 'article',
              authorId: 'nature_photographer',
              title: '极简摄影的真谛',
            ),
            contentPostViewDataBuilder(
              postId: 'works-count-photo',
              contentType: 'image',
              authorId: 'nature_photographer',
              title: '光影的节奏',
              mediaUrls: const [testContentImageUrl],
            ),
          ],
        ),
      ),
    );
    await _pumpFrames(tester);

    expect(find.text(UITextConstants.profileRecordsTotal(2)), findsOneWidget);
    expect(find.byType(AppSectionErrorState), findsNothing);
  });
}
