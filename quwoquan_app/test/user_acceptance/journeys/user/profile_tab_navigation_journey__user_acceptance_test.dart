import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_visit_writer.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
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
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../support/cloud_services/content_facet_overrides.dart';
import '../../../support/cloud_services/repository_mock_reexports.dart';
import '../../../support/harness/profile_shell_scroll_utils.dart';

class _JourneyProfileInteractionFacet
    implements
        ContentProfileInteractionQueryFacet,
        ContentProfileInteractionReadFactAppendFacet {
  final List<AppendContentProfileInteractionReadFactCommand> appendedFacts =
      <AppendContentProfileInteractionReadFactCommand>[];

  @override
  Future<ContentProfileInteractionPage> listActivities(
    ContentProfileInteractionPageQuery query, {
    required ContentProfileInteractionDirection direction,
  }) async {
    if (direction != ContentProfileInteractionDirection.received) {
      return ContentProfileInteractionPage(
        items: const <ContentProfileInteractionActivity>[],
      );
    }
    final now = DateTime.utc(2026, 7, 19, 12);
    final activityType = query.type.wireValue;
    return ContentProfileInteractionPage(
      items: <ContentProfileInteractionActivity>[
        ContentProfileInteractionActivity(
          activityId: 'journey-$activityType',
          activityType: activityType,
          direction: direction.wireValue,
          actorSubAccountId: 'journey-actor',
          actorDisplayName: '你的皮炎有点辣',
          targetSubAccountId: query.subAccountId,
          targetContentId: 'journey-post',
          targetContentType: 'image',
          targetContentSummary: '真实互动投影旅程',
          displaySubAccountId: 'journey-actor',
          displayName: '你的皮炎有点辣',
          primaryText: switch (query.type) {
            ContentProfileInteractionType.like => '赞了你的作品',
            ContentProfileInteractionType.comment => '评论了你的作品',
            ContentProfileInteractionType.share => '转发了你的作品',
          },
          previewText: '真实互动投影旅程',
          previewObjectId: 'journey-post',
          previewRouteId: 'workBrowser',
          filterKeys: <String>[
            switch (query.type) {
              ContentProfileInteractionType.like => 'likes',
              ContentProfileInteractionType.comment => 'comments',
              ContentProfileInteractionType.share => 'shares',
            },
          ],
          createdAt: now,
          occurredAt: now,
        ),
      ],
    );
  }

  @override
  Future<ContentProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) async {
    appendedFacts.add(command);
    return ContentProfileInteractionReadFactAck(
      factId: 'journey-${command.activityId}-${command.state.wireValue}',
      activityId: command.activityId,
      state: command.state.wireValue,
      occurredAt: DateTime.utc(2026, 7, 19, 12),
      replayed: false,
    );
  }
}

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
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {}

  @override
  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {}

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

class _AuthenticatedSessionController extends AuthSessionController {
  _AuthenticatedSessionController(this.activeSubAccountId);

  final String activeSubAccountId;

  @override
  AuthSessionState build() => AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: activeSubAccountId,
    activeSubAccountId: activeSubAccountId,
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
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
/// 同时实现 [IntersectionVisitWriter]：推进水位后未读清零，
/// 模拟云侧 IntersectionVisitState 单调水位语义。
class _JourneyIntersectionRepository
    implements IntersectionRepository, IntersectionVisitWriter {
  final Set<String> visitedDimensions = <String>{};

  bool get _relationshipVisited =>
      visitedDimensions.contains('') ||
      visitedDimensions.contains('relationship');

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {
    visitedDimensions.add((dimension ?? '').trim());
  }

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    final newCount = _relationshipVisited ? 0 : 2;
    return IntersectionInboxSummary(
      totalCount: 4,
      totalNewCount: newCount,
      dimensions: <IntersectionDimensionTally>[
        IntersectionDimensionTally(
          dimension: 'relationship',
          label: '关系',
          count: 4,
          newCount: newCount,
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
        objectKind: 'circle',
        displayName: '黄金投资圈',
        primaryText: '你和林清越等4位用户都关注「黄金投资圈」',
        actorEvidenceTotalCount: 4,
        actorEvidenceCompleteness: 'complete',
        representativeActor: IntersectionRepresentativeActor(
          actorId: 'u_lin',
          displayName: '林清越',
          relationLabel: '联系人',
          privacyState: 'visible',
          target: IntersectionTarget(
            objectType: 'user',
            objectId: 'u_lin',
            objectKind: 'person',
            routeId: 'userProfile',
          ),
        ),
        primarySpans: <IntersectionTextSpan>[
          IntersectionTextSpan(text: '你和', role: 'plain'),
          IntersectionTextSpan(
            text: '林清越',
            role: 'object',
            target: IntersectionTarget(
              objectType: 'user',
              objectId: 'u_lin',
              objectKind: 'person',
              routeId: 'userProfile',
            ),
          ),
          IntersectionTextSpan(text: '等', role: 'plain'),
          IntersectionTextSpan(
            text: '4',
            role: 'count',
            target: IntersectionTarget(
              objectId: 'relationship',
              routeId: 'myIntersections',
            ),
          ),
          IntersectionTextSpan(text: '位用户都关注「', role: 'plain'),
          IntersectionTextSpan(
            text: '黄金投资圈',
            role: 'object',
            target: IntersectionTarget(
              objectType: 'circle',
              objectId: 'fixture_circle_gold_invest',
              objectKind: 'circle',
              routeId: 'circleDetail',
            ),
          ),
          IntersectionTextSpan(text: '」', role: 'plain'),
        ],
        source: 'sharedEntityAttention',
        timeBucket: 'today',
        actionTargetId: 'fixture_circle_gold_invest',
        freshAt: DateTime.now().toUtc().toIso8601String(),
      ),
    ];
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

bool _tapIntersectionSpanByText(WidgetTester tester, String text) {
  final richTexts = tester.widgetList<RichText>(
    find.descendant(
      of: find.byType(InteractiveIntersectionText),
      matching: find.byType(RichText),
    ),
  );
  for (final richText in richTexts) {
    var tapped = false;
    richText.text.visitChildren((span) {
      if (span is TextSpan && span.text == text) {
        final recognizer = span.recognizer;
        if (recognizer is TapGestureRecognizer && recognizer.onTap != null) {
          recognizer.onTap!();
          tapped = true;
          return false;
        }
      }
      return true;
    });
    if (tapped) return true;
  }
  return false;
}

Widget _scopedApp({
  ProfileMode mode = ProfileMode.mine,
  String userId = 'nature_photographer',
  List<Override> extraOverrides = const <Override>[],
  _JourneyProfileInteractionFacet? profileInteractions,
}) {
  final interactionFacet =
      profileInteractions ?? _JourneyProfileInteractionFacet();
  final intersections = _JourneyIntersectionRepository();
  return ProviderScope(
    overrides: [
      ...mockContentFacetOverrides(MockContentRepository()),
      intersectionRepositoryProvider.overrideWithValue(intersections),
      intersectionVisitWriterProvider.overrideWithValue(intersections),
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      authorImpactQueryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _NotFollowingRelationshipCapability(),
      ),
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
      authSessionControllerProvider.overrideWith(
        () => _AuthenticatedSessionController(
          mode == ProfileMode.mine ? userId : 'test_viewer',
        ),
      ),
      profileInteractionQueryFacetProvider.overrideWithValue(interactionFacet),
      profileInteractionReadFactAppendFacetProvider.overrideWithValue(
        interactionFacet,
      ),
      ...extraOverrides,
    ],
    child: MaterialApp(
      builder: (context, child) =>
          _AuthWarmup(child: child ?? const SizedBox.shrink()),
      home: ProfileShell(mode: mode, userId: userId),
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

Future<void> _tapProfileInteractionSubTab(
  WidgetTester tester,
  String label,
) async {
  final tab = find.descendant(
    of: find.byKey(
      const ValueKey<String>('profile-interaction-secondary-tabs'),
    ),
    matching: find.text(label),
  );
  expect(tab, findsOneWidget);
  await tester.ensureVisible(tab);
  await tester.pump();
  final rect = tester.getRect(tab);
  const safeTop = 160.0;
  if (rect.top < safeTop) {
    await tester.drag(
      find.byType(Scrollable).first,
      Offset(0, safeTop - rect.top),
      warnIfMissed: false,
    );
    await tester.pump();
  }
  await tester.tap(tab, warnIfMissed: false);
  await tester.pump();
}

Future<void> _tapProfileInteractionDirection(
  WidgetTester tester,
  String label,
) async {
  final direction = find.descendant(
    of: find.byKey(
      const ValueKey<String>('profile-interaction-direction-switch'),
    ),
    matching: find.text(label),
  );
  expect(direction, findsOneWidget);
  await tester.ensureVisible(direction);
  await tester.pump();
  final rect = tester.getRect(direction);
  const safeTop = 160.0;
  if (rect.top < safeTop) {
    await tester.drag(
      find.byType(Scrollable).first,
      Offset(0, safeTop - rect.top),
      warnIfMissed: false,
    );
    await tester.pump();
  }
  await tester.tap(direction, warnIfMissed: false);
  await tester.pump();
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
      expect(find.text(ChatText.contactsTabCircles), findsOneWidget);
    });

    testWidgets('旅程 A3：切换到互动 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tapProfilePrimaryTab(tester, '互动');
      await _pumpFrames(tester, count: 20);
      await _tapProfileInteractionSubTab(
        tester,
        UITextConstants.interactionSubShares,
      );
      await _pumpFrames(tester, count: 10);

      // 方向只对「转发」语义成立；赞/评论不展示无意义方向开关。
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

      await _tapProfileInteractionDirection(
        tester,
        UITextConstants.profileInteractionDirectionSent,
      );
      await _pumpFrames(tester, count: 10);
      expect(currentDirection(), InteractionDirection.sent);

      await _tapProfileInteractionDirection(
        tester,
        UITextConstants.profileInteractionDirectionReceived,
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

    testWidgets('旅程 D3：mine 模式渲染二维码、分享与设置入口', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(
        find.byKey(const ValueKey<String>('profile-header-edit')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('profile-header-qr-code')),
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
      // 赞没有 received/sent 双向语义，方向开关只在转发二级页展示。
      expect(
        find.text(UITextConstants.profileInteractionDirectionReceived),
        findsNothing,
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

    testWidgets('旅程 E4：收到的转发可见满一秒后追加 seen fact', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final interactions = _JourneyProfileInteractionFacet();

      await tester.pumpWidget(_scopedApp(profileInteractions: interactions));
      await _pumpFrames(tester);
      await tapProfilePrimaryTab(tester, '互动');
      await _pumpFrames(tester, count: 20);
      await _tapProfileInteractionSubTab(
        tester,
        UITextConstants.interactionSubShares,
      );
      await _pumpFrames(tester, count: 10);
      final shareActivity = find.text('你的皮炎有点辣').first;
      await tester.ensureVisible(shareActivity);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1100));
      await tester.pump();

      expect(
        interactions.appendedFacts.any(
          (fact) =>
              fact.state == ContentProfileInteractionReadState.seen &&
              fact.activityId == 'journey-share',
        ),
        isTrue,
      );
    });

    testWidgets('旅程 E4：交集与打动模块从 Repository 加载', (tester) async {
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

  group('旅程 交集端到端（我的主页→我的交集→列表→对象主页）', () {
    testWidgets('旅程 E5：交集事实预览下钻分组列表，再进对象主页', (tester) async {
      final behaviorRepo = MockBehaviorRepository();
      final tracker = ContentBehaviorTracker(
        reporter: behaviorRepo,
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
                GoRoute(
                  path: AppRoutePaths.circleDetailPathTemplate.replaceAll(
                    '{id}',
                    ':id',
                  ),
                  builder: (_, state) =>
                      Text('CIRCLE:${state.pathParameters['id']}'),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      // 我的主页卡与下钻列表消费同一 canonical fact，不另造摘要真相源。
      expect(find.text('你和林清越等4位用户都关注「黄金投资圈」'), findsOneWidget);

      // 我的交集：点击事实行下钻详情页。
      await tester.tap(find.text('你和林清越等4位用户都关注「黄金投资圈」'));
      await tester.pumpAndSettle();
      expect(find.text('今天 1条'), findsOneWidget);
      expect(find.text('你和林清越等4位用户都关注「黄金投资圈」'), findsOneWidget);

      // 对象主页：点击详情页事实句中的圈子名进入主题对象，并埋点归因。
      expect(_tapIntersectionSpanByText(tester, '黄金投资圈'), isTrue);
      await tester.pumpAndSettle();
      expect(find.text('CIRCLE:fixture_circle_gold_invest'), findsOneWidget);
      expect(
        behaviorRepo.recorded.last.contentId,
        'fixture_circle_gold_invest',
      );
    });

    testWidgets('旅程 E6：打开交集列表推进已读水位并清零红点（IntersectionVisitState 闭环）', (
      tester,
    ) async {
      final repo = _JourneyIntersectionRepository();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            intersectionRepositoryProvider.overrideWithValue(repo),
            intersectionVisitWriterProvider.overrideWithValue(repo),
          ],
          child: const CupertinoApp(home: MyIntersectionInboxPage()),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));

      // 打开列表即触发 loadAndMarkVisited：typed 写面收到全维度推进。
      expect(repo.visitedDimensions, contains(''));

      // 水位推进后 summary 未读清零（红点消失的唯一数据来源）。
      final summary = await repo.getMyIntersectionSummary();
      expect(summary.totalNewCount, 0);
      expect(summary.dimensions.single.newCount, 0);
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
        findsNothing,
      );
      expect(tester.getTopLeft(summaryFinder).dy, closeTo(summaryBefore, 8));
    });
  });

  group('旅程错误路径', () {
    testWidgets('旅程 B1：空用户数据下页面不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(userId: 'nonexistent_user_xyz'));
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
