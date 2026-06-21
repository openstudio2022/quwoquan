import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/pages/my_intersection_inbox_page.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/author_impact_card.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_inbox_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

import '../../../support/harness/profile_shell_scroll_utils.dart';

class _AuthedSessionStore implements AuthSessionStore {
  const _AuthedSessionStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'test_viewer',
    activeSubAccountId: 'test_viewer',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: 0,
    lastForegroundAuthCheckAtEpochMs: 0,
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );

  @override
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

/// 在 pump 期间主动 watch 登录态，让他人主页关注/私信按钮的 requireLogin 放行。
class _AuthWarmup extends ConsumerWidget {
  const _AuthWarmup({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(authSessionControllerProvider);
    return child;
  }
}

/// 他人主页用「未关注」能力位，使 [ProfileActionBar] 在 capability 已就绪时渲染（非 null）。
class _NotFollowingRelationshipCapability
    extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto.fromFollowFlags(
      viewerId: 'test_viewer',
      targetId: targetUserId,
      isFollowing: false,
      isFollowedBy: false,
    );
  }
}

/// 端到端旅程用 Stub：主页事实交集 + 详情页时间桶列表（契约字段对齐）。
class _JourneyIntersectionRepository implements IntersectionRepository {
  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(
      totalCount: 4,
      totalNewCount: 2,
      dimensions: <IntersectionDimensionTally>[
        IntersectionDimensionTally(
          dimension: 'relationship',
          label: '关系',
          count: 4,
          newCount: 2,
          briefText: '3 位联系人来过你的主页',
        ),
      ],
    );
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    return <IntersectionReason>[
      IntersectionReason(
        dimension: 'relationship',
        intersectionClass: 'fact',
        intersectionId: 'ix_journey_rel',
        objectKind: 'person',
        displayName: '林清越',
        primaryText: '你和林清越等4位用户都关注「黄金投资圈」',
        source: 'sharedEntityAttention',
        timeBucket: 'today',
        actionTargetId: 'u_lin',
        freshAt: DateTime.now().toUtc().toIso8601String(),
      ),
    ];
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

Widget _scopedApp({
  ProfileMode mode = ProfileMode.mine,
  List<Override> extraOverrides = const <Override>[],
}) {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _NotFollowingRelationshipCapability(),
      ),
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
      ...extraOverrides,
    ],
    child: MaterialApp(
      builder: (context, child) =>
          _AuthWarmup(child: child ?? const SizedBox.shrink()),
      home: ProfileShell(mode: mode, userId: 'nature_photographer'),
    ),
  );
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 10}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void _setPhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3.0;
}

Finder _profileSegment(String label) {
  return find.descendant(
    of: find.byKey(const ValueKey<String>('profile-shell-primary-tabs-inline')),
    matching: find.text(label),
  );
}

Finder _pinnedProfileSegment(String label) {
  return find.descendant(
    of: find.byKey(const ValueKey<String>('profile-shell-primary-tabs-pinned')),
    matching: find.text(label),
  );
}

Finder _profileActionLabel(String label) {
  return find.descendant(
    of: find.byType(ProfileActionBar),
    matching: find.text(label),
  );
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  group('旅程正常路径', () {
    testWidgets('旅程 A1：默认展示创作 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);
      // 摘要区变高后一级 Tab 为首屏外 lazy sliver，先滚动构建再断言。
      await revealProfilePrimaryTabs(tester);
      expect(
        _profileSegment(UITextConstants.profileTabCreations),
        findsOneWidget,
      );
    });

    testWidgets('旅程 A2：圈子进入统计区而非一级 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      expect(_profileSegment('圈子'), findsNothing);
      expect(find.text(UITextConstants.contactsTabCircles), findsOneWidget);
    });

    testWidgets('旅程 A3：切换到互动 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tapProfilePrimaryTab(tester, '互动');
      await _pumpFrames(tester, count: 20);

      // 方向切换收敛到一级 Tab 右侧：两个选项同时可见，直接点选即可切换，
      // 不再挤占互动二级分类，也不再弹出底部工具栏。
      expect(
        find.text(UITextConstants.profileInteractionDirectionReceived),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.profileInteractionDirectionSent),
        findsOneWidget,
      );

      InteractionDirection currentDirection() {
        return ProviderScope.containerOf(
              tester.element(find.byType(ProfileShell)),
            )
            .read(profileNotifierProvider('nature_photographer'))
            .interactionDirection;
      }

      expect(currentDirection(), InteractionDirection.received);

      await tester.tap(
        find.text(UITextConstants.profileInteractionDirectionSent),
      );
      await _pumpFrames(tester, count: 10);
      expect(currentDirection(), InteractionDirection.sent);

      await tester.tap(
        find.text(UITextConstants.profileInteractionDirectionReceived),
      );
      await _pumpFrames(tester, count: 10);
      expect(currentDirection(), InteractionDirection.received);
    });
  });

  group('旅程 v2 布局验证', () {
    testWidgets('旅程 D1：不渲染 @username', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      expect(find.textContaining('@'), findsNothing);
    });

    testWidgets('旅程 D2：other 模式渲染「关注」与「私信」入口', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(_profileActionLabel(UITextConstants.follow), findsOneWidget);
      expect(
        _profileActionLabel(UITextConstants.profileDirectMessage),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.profileGreet), findsNothing);
    });

    testWidgets('旅程 D3：mine 模式渲染昵称编辑入口、分享与设置入口', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(
        find.byKey(const ValueKey<String>('profile-header-edit')),
        findsOneWidget,
      );
      expect(
        find.byIcon(CupertinoIcons.arrowshape_turn_up_right),
        findsOneWidget,
      );
      expect(
        find.byIcon(AppNavigationSemanticConstants.settingsActionIcon),
        findsOneWidget,
      );
      expect(find.text('分身管理'), findsNothing);
    });
  });

  group('旅程数据加载正确性', () {
    testWidgets('旅程 E1：创作 Tab 展示 Repository 帖子数据（点赞数可见）', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      // 内容查询快照默认走 SharedPreferences 持久化，widget 测试无 SP mock 时
      // ensureHydrated 永不收敛，会卡死 loadProfile 的并发拉取；本用例需要真实创作
      // 数据，单独关闭该缓存的持久化以让 Repository 帖子可加载。
      await tester.pumpWidget(
        _scopedApp(
          extraOverrides: <Override>[
            contentQuerySnapshotStoreProvider.overrideWithValue(
              ContentQuerySnapshotStore(persistToPreferences: false),
            ),
          ],
        ),
      );
      // 图片占位动画会让 pumpAndSettle 永不收敛，统一用定帧泵帧。
      await _pumpFrames(tester, count: 20);
      // 创作为默认一级 Tab；摘要区变高后内容首屏外，先滚动构建一级 Tab 与其下
      // 创作内容（与 E3 互动同源的 reveal 模式），再断言 Repository 帖子可见。
      await revealProfilePrimaryTabs(tester);
      await _pumpFrames(tester, count: 20);
      expect(find.text('光影的节奏'), findsAtLeastNWidgets(1));
    });

    testWidgets('旅程 E2：获赞统计点击进入互动点赞', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(find.text(UITextConstants.circleLikes));
      await _pumpFrames(tester, count: 20);
      // 切到互动后，一级 Tab 与互动内容仍为首屏外 lazy sliver，滚动构建再断言。
      await revealProfilePrimaryTabs(tester);
      await _pumpFrames(tester, count: 10);
      expect(
        find.text(UITextConstants.interactionSubLikes),
        findsAtLeastNWidgets(1),
      );
      expect(
        find.text(UITextConstants.profileInteractionDirectionReceived),
        findsOneWidget,
      );
    });

    testWidgets('旅程 E3：互动 Tab 展示 Repository 互动列表', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tapProfilePrimaryTab(tester, '互动');
      await _pumpFrames(tester, count: 20);
      expect(find.text('你的皮炎有点辣'), findsOneWidget);
    });

    testWidgets('旅程 E4：交集与影响力模块从 Repository 加载', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);
      // 一级 Tab 为首屏外 lazy sliver，先滚动构建；摘要区为整段 sliver 仍同时构建，
      // 滚动后仍可测量各模块相对纵向次序。
      await revealProfilePrimaryTabs(tester);
      await _pumpFrames(tester, count: 5);
      expect(
        find.byKey(const ValueKey<String>('profile-shell-profile-card')),
        findsOneWidget,
      );
      expect(find.byType(MyIntersectionInboxCard), findsOneWidget);
      expect(find.byKey(AuthorImpactCard.cardKey), findsOneWidget);
      expect(find.text(DiscoveryFeedText.myIntersectionsTitle), findsOneWidget);
      expect(find.text(UITextConstants.profileImpactTitleMine), findsOneWidget);
      expect(find.byKey(MyIntersectionInboxCard.cardKey), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('profile-shell-primary-tabs-inline')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('profile-tab-body-creations')),
        findsOneWidget,
      );

      final profileTop = tester
          .getTopLeft(
            find.byKey(const ValueKey<String>('profile-shell-profile-card')),
          )
          .dy;
      final intersectionTop = tester
          .getTopLeft(find.byKey(MyIntersectionInboxCard.cardKey))
          .dy;
      final impactTop = tester
          .getTopLeft(find.byKey(AuthorImpactCard.cardKey))
          .dy;
      final contentTop = tester
          .getTopLeft(
            find.byKey(
              const ValueKey<String>('profile-shell-primary-tabs-inline'),
            ),
          )
          .dy;

      expect(profileTop, lessThan(intersectionTop));
      expect(intersectionTop, lessThan(impactTop));
      expect(impactTop, lessThan(contentTop));
    });
  });

  group('旅程 交集端到端（我的主页→我的连接→列表→对象主页）', () {
    testWidgets('旅程 E5：维度简报下钻分组列表，再进对象主页', (tester) async {
      final behaviorRepo = MockBehaviorRepository();
      final tracker = ContentBehaviorTracker(
        repository: behaviorRepo,
        maxBatchSize: 1,
        enablePeriodicFlush: false,
      );
      addTearDown(tracker.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            intersectionRepositoryProvider.overrideWithValue(
              _JourneyIntersectionRepository(),
            ),
            behaviorRepositoryProvider.overrideWithValue(behaviorRepo),
            contentBehaviorTrackerProvider.overrideWithValue(tracker),
          ],
          child: CupertinoApp.router(
            routerConfig: GoRouter(
              initialLocation: '/',
              routes: <RouteBase>[
                GoRoute(
                  path: '/',
                  builder: (_, _) => const CupertinoPageScaffold(
                    child: SafeArea(
                      child: MyIntersectionInboxCard(isDark: false),
                    ),
                  ),
                ),
                GoRoute(
                  path: AppRoutePaths.myIntersectionsPathTemplate,
                  builder: (_, state) => MyIntersectionInboxPage(
                    dimension: state.uri.queryParameters['dimension'] ?? '',
                    sourceRef: state.uri.queryParameters['sourceRef'] ?? '',
                    filter: state.uri.queryParameters['filter'] ?? '',
                    timeBucket: state.uri.queryParameters['timeBucket'] ?? '',
                    intersectionId:
                        state.uri.queryParameters['intersectionId'] ?? '',
                  ),
                ),
                GoRoute(
                  path: '/user/:username',
                  builder: (_, state) =>
                      Text('USER:${state.pathParameters['username']}'),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      // 我的主页：高保事实交集卡从 Repository 加载。
      expect(find.text('你和林清越等4位用户都关注「黄金投资圈」'), findsOneWidget);

      // 我的交集：点击事实行下钻详情页。
      await tester.tap(find.text('你和林清越等4位用户都关注「黄金投资圈」'));
      await tester.pumpAndSettle();
      expect(
        find.text(DiscoveryFeedText.intersectionTimeBucketToday),
        findsOneWidget,
      );
      expect(find.text('你和林清越等4位用户都关注「黄金投资圈」'), findsOneWidget);

      // 对象主页：点击详情页事实行进入其主页，并埋点归因。
      await tester.tap(find.text('你和林清越等4位用户都关注「黄金投资圈」'));
      await tester.pumpAndSettle();
      expect(find.text('USER:u_lin'), findsOneWidget);
      expect(behaviorRepo.recorded.last.contentId, 'u_lin');
    });
  });

  group('旅程交互操作', () {
    testWidgets('旅程 F1：other 模式点击关注按钮切换状态', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);

      final followBtn = _profileActionLabel('关注').first;
      expect(followBtn, findsOneWidget);
      await tester.tap(followBtn);
      await _pumpFrames(tester);
      expect(_profileActionLabel('已关注'), findsOneWidget);
    });

    testWidgets('旅程 F2：创作 Tab 展示用户创作内容', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);
      // 摘要区变高后一级 Tab 为首屏外 lazy sliver，先滚动构建再断言。
      await revealProfilePrimaryTabs(tester);
      expect(
        _profileSegment(UITextConstants.profileTabCreations),
        findsOneWidget,
      );
    });

    testWidgets('旅程 F3：一级 tab 吸顶后切换不会把整页头部重置回内容区', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -900));
      await _pumpFrames(tester, count: 12);

      final summaryFinder = find.byKey(
        const ValueKey<String>('profile-shell-summary-card'),
      );
      final summaryBefore = tester.getTopLeft(summaryFinder).dy;

      final interactionTab = _pinnedProfileSegment('互动').evaluate().isNotEmpty
          ? _pinnedProfileSegment('互动')
          : _profileSegment('互动');
      await tester.tap(interactionTab);
      await _pumpFrames(tester, count: 12);
      final primaryTabs = _pinnedProfileSegment('互动').evaluate().isNotEmpty
          ? find.byKey(
              const ValueKey<String>('profile-shell-primary-tabs-pinned'),
            )
          : find.byKey(
              const ValueKey<String>('profile-shell-primary-tabs-inline'),
            );
      expect(
        find.descendant(
          of: primaryTabs,
          matching: find.text(
            UITextConstants.profileInteractionDirectionReceived,
          ),
        ),
        findsOneWidget,
      );
      expect(tester.getTopLeft(summaryFinder).dy, closeTo(summaryBefore, 8));
    });
  });

  group('旅程错误路径', () {
    testWidgets('旅程 B1：空用户数据下页面不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            userProfileRepositoryProvider.overrideWithValue(
              const MockUserProfileRepository(),
            ),
          ],
          child: MaterialApp(
            home: ProfileShell(
              mode: ProfileMode.mine,
              userId: 'nonexistent_user_xyz',
            ),
          ),
        ),
      );
      await _pumpFrames(tester);
      // 空用户数据下仍应正常渲染：滚动构建首屏外一级 Tab 并断言不崩溃。
      await revealProfilePrimaryTabs(tester);
      expect(
        _profileSegment(UITextConstants.profileTabCreations),
        findsOneWidget,
      );
    });
  });

  group('旅程边界/幂等', () {
    testWidgets('旅程 C1：mine 模式显示设置按钮，不显示 more', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(
        find.byIcon(AppNavigationSemanticConstants.settingsActionIcon),
        findsOneWidget,
      );
      expect(find.byIcon(CupertinoIcons.ellipsis), findsNothing);
    });

    testWidgets('旅程 C2：other 模式显示 more 按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(find.byIcon(CupertinoIcons.ellipsis), findsOneWidget);
      expect(
        find.byIcon(AppNavigationSemanticConstants.settingsActionIcon),
        findsNothing,
      );
    });
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}
