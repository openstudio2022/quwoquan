import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/application/content/post/author_impact_query.dart';
import 'package:quwoquan_app/application/rtc/call_session/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/application/user/profile/profile_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/sub_account_profile_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/components/rtc/rtc_call_entry_presenter.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/providers/author_impact_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/author_impact_card.dart';
import 'package:quwoquan_app/ui/user/widgets/other_profile_intersection_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_permission_guard.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/harness/profile_shell_scroll_utils.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_secondary_tab_bar.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';
import '../../../../support/fakes/test_profile_interaction_facets.dart';
import '../../../../support/fixtures/author_impact_fixtures.dart';

/// 在 UI 测试中使 capability 保持 null（current 关注/私信 布局）
class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

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

class _MutualCallCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto(
      viewerSubAccountId: 'viewer-profile',
      targetSubAccountId: targetUserId,
      relationState: 'mutual',
      canStartVoiceCall: true,
      canStartVideoCall: true,
      isBlocked: false,
      isBlockedBy: false,
    );
  }
}

class _FlippableProfileAuthSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);

  void loginNow() {
    state = const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'access-token',
      ownerId: 'viewer-profile',
      activeSubAccountId: 'viewer-profile',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'install-id',
    );
  }
}

class _AuthenticatedProfileAuthSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    ownerId: 'viewer-profile',
    activeSubAccountId: 'viewer-profile',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
}

class _RecordingBlockWriter implements BlockCommandWriter {
  String? blockedTarget;

  @override
  Future<BlockCommandResult> blockUser(BlockUserCommand command) async {
    blockedTarget = command.targetSubAccountId;
    return BlockCommandResult(
      targetSubAccountId: command.targetSubAccountId,
      blocked: true,
      idempotentReplay: false,
      updatedAt: DateTime.utc(2026, 7, 20),
    );
  }

  @override
  Future<BlockCommandResult> unblockUser(UnblockUserCommand command) async {
    return BlockCommandResult(
      targetSubAccountId: command.targetSubAccountId,
      blocked: false,
      idempotentReplay: false,
      updatedAt: DateTime.utc(2026, 7, 20),
    );
  }
}

class _EmptyIntersectionRepository implements IntersectionRepository {
  const _EmptyIntersectionRepository();

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 0, totalNewCount: 0);
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 20,
  }) async {
    return const <IntersectionReason>[];
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
    return const <IntersectionReason>[];
  }
}

/// 首屏聚合失败仓库：getUserHomepageBundle 抛错，用于验证 ProfileShell 结构化错误态。
class _FailingHomepageBundleRepository extends MockUserProfileRepository {
  const _FailingHomepageBundleRepository();

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String subAccountId,
  ) async {
    throw Exception('homepage-bundle 加载失败（测试）');
  }
}

abstract class _ProfileBundleOverrideRepository
    extends MockUserProfileRepository {
  const _ProfileBundleOverrideRepository();

  Future<SubAccountProfileViewData> profileFor(String userId);

  @override
  Future<SubAccountProfileViewData> getUserProfile(String userId) =>
      profileFor(userId);

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String subAccountId,
  ) async {
    final base = await super.getUserHomepageBundle(subAccountId);
    return UserHomepageBundleViewData(
      profile: await profileFor(subAccountId),
      stats: base.stats,
      relationshipCapability: base.relationshipCapability,
      tabCounts: base.tabCounts,
      viewerContext: base.viewerContext,
      cacheVersion: base.cacheVersion,
    );
  }
}

/// 默认昵称态（未编辑）本人档案：昵称即默认用户名、未自定义、无头像/封面/简介/标签。
/// 用于验证我的主页空态引导，并断言不再回退到「探索者 / 趣我圈号」占位。
class _DefaultNicknameProfileRepository
    extends _ProfileBundleOverrideRepository {
  const _DefaultNicknameProfileRepository();

  static const String defaultNickname = '新同学_260622_6698692';

  @override
  Future<SubAccountProfileViewData> profileFor(String userId) async {
    return SubAccountProfileViewData.fromSubAccountProfileWire(
      SubAccountProfileWireDto(
        subAccountId: userId,
        ownerUserId: userId,
        userHandle: userId,
        username: userId,
        displayName: defaultNickname,
        nickname: defaultNickname,
        nicknameCustomized: false,
        avatarUrl: '',
        backgroundUrl: '',
        bio: '',
        identityTags: const <String>[],
      ),
    );
  }
}

/// 已自定义昵称的本人档案：nicknameCustomized=true，用于断言昵称行编辑入口不回归。
class _CustomizedNicknameProfileRepository
    extends _ProfileBundleOverrideRepository {
  const _CustomizedNicknameProfileRepository();

  @override
  Future<SubAccountProfileViewData> profileFor(String userId) async {
    return SubAccountProfileViewData.fromSubAccountProfileWire(
      SubAccountProfileWireDto(
        subAccountId: userId,
        ownerUserId: userId,
        userHandle: userId,
        username: userId,
        displayName: '我的专属昵称',
        nickname: '我的专属昵称',
        nicknameCustomized: true,
        avatarUrl: '',
        backgroundUrl: '',
        bio: '',
        identityTags: const <String>[],
      ),
    );
  }
}

/// Query ViewData 已解析的头像源：主头像与吸顶头像必须共用同一值。
class _ResolvedAvatarProfileRepository
    extends _ProfileBundleOverrideRepository {
  const _ResolvedAvatarProfileRepository();

  static const String resolvedAvatar =
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC'
      'AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';

  @override
  Future<SubAccountProfileViewData> profileFor(String userId) async {
    return SubAccountProfileViewData.fromSubAccountProfileWire(
      SubAccountProfileWireDto(
        subAccountId: userId,
        ownerUserId: userId,
        userHandle: userId,
        username: userId,
        displayName: '头像同源用户',
        nickname: '头像同源用户',
        nicknameCustomized: true,
        avatarUrl: resolvedAvatar,
        backgroundUrl: '',
        bio: '头像同源回归',
        identityTags: const <String>['摄影'],
      ),
    );
  }
}

class _NoUserPostsContentRepository extends MockContentRepository {
  _NoUserPostsContentRepository() : super(seedPosts: const <PostBaseDto>[]);

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = 20,
  }) async {
    return const CursorPage<PostBaseDto>(
      items: <PostBaseDto>[],
      nextCursor: null,
    );
  }
}

PhotoPostDto _profileBackgroundPost(String authorId) {
  return PhotoPostDto(
    id: '${authorId}_cover_source',
    type: 'photo',
    identity: 'work',
    assistantUsePolicy: 'inherit',
    authorId: authorId,
    displayName: '封面来源用户',
    avatarUrl:
        'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
    authorBackgroundUrl:
        'media/image/s/archived-image/post/fixture_photo_001/v1/image-2.png',
    authorRoleLabel: '摄影',
    authorIdentityTags: const <String>['摄影'],
    authorVerified: false,
    body: '封面回退来源',
    coverUrl:
        'media/image/s/archived-image/post/fixture_photo_001/v1/image-2.png',
    imageUrls: const <String>[
      'media/image/s/archived-image/post/fixture_photo_001/v1/image-2.png',
    ],
    likeCount: 1,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.utc(2026, 6, 24),
  );
}

Widget _scopedApp({
  required ProfileMode mode,
  String userId = 'nature_photographer',
  ThemeMode themeMode = ThemeMode.light,
  double textScaleFactor = 1.0,
  String? initialAvatarUrl,
  String? initialDisplayName,
  String? initialBackgroundUrl,
  RelationshipCapabilityRepository? capabilityRepository,
  ProfileQuery profileQuery = const MockUserProfileRepository(),
  AuthorImpactQuery authorImpactQuery = const MockUserProfileRepository(),
  MockContentRepository? contentRepository,
  VoidCallback? onBack,
  List overrides = const [],
}) {
  return ProviderScope(
    overrides: [
      profileQueryProvider.overrideWith((ref, surface) => profileQuery),
      authorImpactQueryProvider.overrideWith(
        (ref, surface) => authorImpactQuery,
      ),
      ...mockContentFacetOverrides(
        contentRepository ?? MockContentRepository(),
      ),
      profileInteractionQueryFacetProvider.overrideWithValue(
        const TestProfileInteractionFacets(),
      ),
      profileInteractionReadFactAppendFacetProvider.overrideWithValue(
        const TestProfileInteractionFacets(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        capabilityRepository ?? _ThrowingCapabilityRepository(),
      ),
      intersectionRepositoryProvider.overrideWithValue(
        const _EmptyIntersectionRepository(),
      ),
      ...overrides,
    ],
    child: MaterialApp(
      builder: (context, child) {
        final mediaQuery = MediaQuery.of(context);
        return MediaQuery(
          data: mediaQuery.copyWith(
            textScaler: TextScaler.linear(textScaleFactor),
          ),
          child: child ?? const SizedBox.shrink(),
        );
      },
      themeMode: themeMode,
      theme: ThemeData.light(),
      darkTheme: ThemeData.dark(),
      home: ProfileShell(
        mode: mode,
        userId: userId,
        initialAvatarUrl: initialAvatarUrl,
        initialDisplayName: initialDisplayName,
        initialBackgroundUrl: initialBackgroundUrl,
        onBack: onBack,
      ),
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

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  group('ProfileShell — 渲染契约', () {
    testWidgets('mine 模式渲染设置按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(
        find.byIcon(AppNavigationSemanticConstants.settingsActionIcon),
        findsOneWidget,
      );
    });

    testWidgets('分身管理开关关闭时我的主页不展示分身管理按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.mine,
          overrides: [
            personaManagementFeatureFlagProvider.overrideWith((ref) => false),
          ],
        ),
      );
      await _pumpFrames(tester);

      expect(find.text(UITextConstants.profilePersonasLabel), findsNothing);
      expect(find.text(UITextConstants.personaSwitchProfile), findsNothing);
      expect(find.text(UITextConstants.profileEditLabel), findsOneWidget);
    });

    testWidgets('默认昵称态展示头像/封面/简介/标签引导与 QR，且不出现探索者/趣我圈号', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.mine,
          userId: 'fixture_user_current',
          profileQuery: const _DefaultNicknameProfileRepository(),
          contentRepository: _NoUserPostsContentRepository(),
        ),
      );
      await _pumpFrames(tester);

      // 默认昵称（云侧「前缀_YYMMDD_7位尾号」）直接展示，不再回退到「探索者」占位。
      expect(
        find.text(_DefaultNicknameProfileRepository.defaultNickname),
        findsWidgets,
      );
      // 内部用户号 / 趣我圈号 / 探索者 等占位身份对 UI 完全不可见。
      expect(find.textContaining('趣我圈号'), findsNothing);
      expect(find.textContaining('探索者'), findsNothing);
      expect(
        find.byKey(const ValueKey<String>('profile-header-handle')),
        findsNothing,
      );
      // 空态引导：头像 / 封面 / 简介 / 标签。
      expect(find.text(UITextConstants.profileUploadAvatar), findsWidgets);
      expect(find.text(UITextConstants.profileUploadCover), findsOneWidget);
      expect(find.text(UITextConstants.profileEmptyBioPrompt), findsWidgets);
      expect(find.text(UITextConstants.profileEmptyTagsPrompt), findsOneWidget);
      // 昵称行不再承载小画笔；新增二维码固定在 header trailing 区。
      expect(
        find.byKey(const ValueKey<String>('profile-header-edit')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('profile-header-qr-code')),
        findsOneWidget,
      );
    });

    testWidgets('改过昵称（nicknameCustomized）后我的主页不展示昵称行编辑入口', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.mine,
          userId: 'fixture_user_current',
          profileQuery: const _CustomizedNicknameProfileRepository(),
        ),
      );
      await _pumpFrames(tester);

      expect(find.text('我的专属昵称'), findsWidgets);
      expect(
        find.byKey(const ValueKey<String>('profile-header-edit')),
        findsNothing,
      );
    });

    testWidgets('已解析头像源在主头像与吸顶头像使用同一可加载组件渲染', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.mine,
          userId: 'fixture_user_current',
          profileQuery: const _ResolvedAvatarProfileRepository(),
        ),
      );
      await _pumpFrames(tester, count: 20);

      expect(
        find.byKey(const ValueKey<String>('profile-header-avatar-image')),
        findsOneWidget,
      );
      expect(
        tester
            .widget<AppAvatarImage>(
              find.byKey(const ValueKey<String>('profile-header-avatar-image')),
            )
            .imageUrl,
        _ResolvedAvatarProfileRepository.resolvedAvatar,
      );

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -900));
      await _pumpFrames(tester, count: 12);
      expect(
        find.byKey(
          const ValueKey<String>('profile-shell-compact-avatar-image'),
        ),
        findsOneWidget,
      );
      expect(
        tester
            .widget<AppCachedNetworkImage>(
              find.byKey(
                const ValueKey<String>('profile-shell-compact-avatar-image'),
              ),
            )
            .imageUrl,
        _ResolvedAvatarProfileRepository.resolvedAvatar,
      );
    });

    testWidgets('空 initialAvatarUrl 不遮蔽 profile 返回的头像源', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          userId: 'fixture_user_current',
          initialAvatarUrl: '',
          profileQuery: const _ResolvedAvatarProfileRepository(),
        ),
      );
      await _pumpFrames(tester, count: 20);

      expect(
        tester
            .widget<AppAvatarImage>(
              find.byKey(const ValueKey<String>('profile-header-avatar-image')),
            )
            .imageUrl,
        _ResolvedAvatarProfileRepository.resolvedAvatar,
      );
    });

    testWidgets('有作品回退背景图时不展示添加封面', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.mine,
          userId: 'fixture_user_current',
          profileQuery: const _DefaultNicknameProfileRepository(),
          contentRepository: MockContentRepository(
            seedPosts: <PostBaseDto>[
              _profileBackgroundPost('fixture_user_current'),
            ],
          ),
        ),
      );
      await _pumpFrames(tester, count: 20);

      expect(find.text(UITextConstants.profileUploadCover), findsNothing);
    });

    testWidgets('无任何背景图时展示添加封面', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.mine,
          userId: 'fixture_user_current',
          profileQuery: const _DefaultNicknameProfileRepository(),
          contentRepository: _NoUserPostsContentRepository(),
        ),
      );
      await _pumpFrames(tester, count: 20);

      expect(find.text(UITextConstants.profileUploadCover), findsOneWidget);
    });

    testWidgets('二维码位于 header trailing 区并贴近资料卡右边界', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);

      final qrFinder = find.byKey(
        const ValueKey<String>('profile-header-qr-code'),
      );
      final cardFinder = find.byKey(
        const ValueKey<String>('profile-shell-profile-card'),
      );
      expect(qrFinder, findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('profile-header-edit')),
        findsNothing,
      );

      final cardRight = tester.getTopRight(cardFinder).dx;
      final qrRight = tester.getTopRight(qrFinder).dx;
      expect(
        (cardRight - AppSpacing.containerMd) - qrRight,
        closeTo(0, AppSpacing.containerLg),
      );
    });

    testWidgets('other 模式渲染返回和更多按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          userId: 'u_lin',
          capabilityRepository: _StaticCapabilityRepository(),
          overrides: [
            currentUserIdProvider.overrideWithValue('viewer-profile'),
            objectSharedReasonsProvider.overrideWith((ref, query) async {
              return <IntersectionReason>[
                IntersectionReason(
                  dimension: 'relationship',
                  intersectionPoints: <IntersectionPoint>[
                    IntersectionPoint(
                      pointId: 'shared-followees',
                      pointClass: 'fact',
                      dimension: 'relationship',
                      sourceRef: 'sharedFollowees',
                      label: '共同关注的人',
                      displayText: '共同关注的人',
                      count: 2,
                    ),
                  ],
                ),
              ];
            }),
          ],
        ),
      );
      await _pumpFrames(tester);
      expect(find.byIcon(CupertinoIcons.back), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.ellipsis), findsOneWidget);
    });

    testWidgets('mine 渲染记录、互动、足迹主 Tab，圈子进入统计区', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await revealProfilePrimaryTabs(tester);
      // 统计行也有「记录」标签，主 Tab 断言一律限定在 inline tabs 容器内。
      expect(
        _inlinePrimaryTab(UITextConstants.profileTabCreations),
        findsOneWidget,
      );
      expect(_inlinePrimaryTab('互动'), findsOneWidget);
      // V5：足迹=浏览历史，仅本人主页可见（ui_config modes: [mine]）。
      expect(
        _inlinePrimaryTab(UITextConstants.profileTabFootprint),
        findsOneWidget,
      );
      expect(_inlinePrimaryTab('圈子'), findsNothing);
      expect(_inlinePrimaryTab('生活'), findsNothing);
      expect(find.text(ChatText.contactsTabCircles), findsOneWidget);
    });

    testWidgets('other 仅渲染记录、互动主 Tab，足迹隐私门控不出现', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          userId: 'u_lin',
          capabilityRepository: _StaticCapabilityRepository(),
        ),
      );
      await _pumpFrames(tester);
      await revealProfilePrimaryTabs(tester);
      expect(
        _inlinePrimaryTab(UITextConstants.profileTabCreations),
        findsOneWidget,
      );
      expect(_inlinePrimaryTab('互动'), findsOneWidget);
      // 他人主页禁止展示浏览历史足迹。
      expect(
        _inlinePrimaryTab(UITextConstants.profileTabFootprint),
        findsNothing,
      );
    });

    testWidgets('mine 模式四段式文案不串入 other 口径', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);

      expect(find.text(DiscoveryFeedText.myIntersectionsTitle), findsWidgets);
      expect(find.text(UITextConstants.profileImpactTitleMine), findsOneWidget);
      expect(find.text(UITextConstants.profileWhyRecommendTitle), findsNothing);
      expect(find.text(UITextConstants.profileImpactTitleOther), findsNothing);
    });

    testWidgets('other 模式默认空数据也保留交集与打动模块空态', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          capabilityRepository: _StaticCapabilityRepository(),
          overrides: [
            currentUserIdProvider.overrideWithValue('viewer-profile'),
            objectSharedReasonsProvider.overrideWith(
              (ref, query) async => const <IntersectionReason>[],
            ),
          ],
        ),
      );
      await _pumpFrames(tester);

      expect(find.byKey(OtherProfileIntersectionCard.cardKey), findsOneWidget);
      expect(find.byKey(OtherProfileIntersectionCard.emptyKey), findsOneWidget);
      expect(
        find.text(UITextConstants.profileIntersectionEmptyOther),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(OtherProfileIntersectionCard.cardKey),
          matching: find.text(DiscoveryFeedText.intersectionViewAll),
        ),
        findsNothing,
      );
      expect(find.byKey(AuthorImpactCard.cardKey), findsOneWidget);
      expect(find.byKey(AuthorImpactCard.emptyKey), findsOneWidget);
      expect(
        find.text(UITextConstants.profileImpactEmptyOther),
        findsOneWidget,
      );
    });

    testWidgets('打动摘要读取失败展示可重试终态，重试后恢复数据', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var attempts = 0;

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          capabilityRepository: _StaticCapabilityRepository(),
          overrides: [
            authorImpactProvider.overrideWith((ref, request) async {
              attempts++;
              if (attempts == 1) {
                throw StateError('author impact temporarily unavailable');
              }
              return AuthorImpactSummary(
                authorId: request.subAccountId,
                total: 0,
                items: const <AuthorImpactItem>[],
              );
            }),
          ],
        ),
      );
      await _pumpFrames(tester);

      expect(
        find.text(UITextConstants.profileImpactUnavailableTitleOther),
        findsOneWidget,
      );
      expect(find.text(UITextConstants.tryAgain), findsOneWidget);

      final retryAction = find.text(UITextConstants.tryAgain);
      await tester.ensureVisible(retryAction);
      await tester.tap(retryAction);
      await _pumpFrames(tester);

      expect(attempts, greaterThanOrEqualTo(2));
      await tester.drag(
        find.byType(CustomScrollView).first,
        const Offset(0, 1200),
      );
      await tester.pump();
      expect(find.byKey(AuthorImpactCard.cardKey), findsOneWidget);
      expect(
        find.text(UITextConstants.profileImpactUnavailableTitleOther),
        findsNothing,
      );
    });

    testWidgets('other 模式四段式文案不串入 mine 口径', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          userId: 'u_lin',
          capabilityRepository: _StaticCapabilityRepository(),
          overrides: [
            currentUserIdProvider.overrideWithValue('viewer-profile'),
            objectSharedReasonsProvider.overrideWith((ref, query) async {
              return <IntersectionReason>[
                IntersectionReason(
                  dimension: 'relationship',
                  primaryText: '你和林清越都关注胶片摄影',
                  objectKind: 'entity',
                  actionTargetId: 'homepage_topic_film_photo',
                  primarySpans: <IntersectionTextSpan>[
                    IntersectionTextSpan(text: '你和', role: 'plain'),
                    IntersectionTextSpan(text: '林清越', role: 'plain'),
                    IntersectionTextSpan(text: '都关注', role: 'plain'),
                    IntersectionTextSpan(
                      text: '胶片摄影',
                      role: 'object',
                      target: IntersectionTarget(
                        objectType: 'homepage',
                        objectId: 'homepage_topic_film_photo',
                        objectKind: 'entity',
                        routeId: 'homepageDetail',
                      ),
                    ),
                  ],
                  intersectionPoints: <IntersectionPoint>[
                    IntersectionPoint(
                      pointId: 'shared-followees',
                      pointClass: 'fact',
                      dimension: 'relationship',
                      sourceRef: 'sharedFollowees',
                      label: '共同关注的人',
                      displayText: '共同关注的人',
                      count: 2,
                    ),
                  ],
                ),
              ];
            }),
            authorImpactProvider.overrideWith((ref, request) async {
              return AuthorImpactSummary(
                authorId: request.subAccountId,
                total: 2,
                items: <AuthorImpactItem>[
                  authorImpactItemFixture(
                    helpType: 'community',
                    action: 'join',
                    intersectionDimension: 'interest',
                    tagRef: 'interest/film-photography',
                    source: 'source:circle_join',
                    count: 2,
                    primaryText: '2人加入相关圈子',
                    subtitleText: '来自胶片摄影圈',
                  ),
                ],
              );
            }),
          ],
        ),
      );
      await _pumpFrames(tester);

      expect(
        find.text(UITextConstants.profileImpactTitleOther),
        findsOneWidget,
      );
      expect(find.byKey(OtherProfileIntersectionCard.cardKey), findsOneWidget);
      expect(
        find.descendant(
          of: find.byKey(OtherProfileIntersectionCard.cardKey),
          matching: find.text(DiscoveryFeedText.intersectionViewAll),
        ),
        findsOneWidget,
      );
      expect(find.text(DiscoveryFeedText.myIntersectionsTitle), findsNothing);
      expect(find.text(UITextConstants.profileImpactTitleMine), findsNothing);
    });

    testWidgets('用户主页主区块表面使用更多功能同源语义 token', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await revealProfilePrimaryTabs(tester);

      final tabsSurface = tester.widget<Container>(
        find.byKey(const ValueKey<String>('profile-shell-primary-tabs-inline')),
      );
      final tabsDecoration = tabsSurface.decoration! as BoxDecoration;
      final isDark =
          CupertinoTheme.of(
            tester.element(find.byType(ProfileShell)),
          ).brightness ==
          Brightness.dark;
      expect(
        tabsDecoration.color,
        SettingsSemanticConstants.conversationSheetCardSurface(isDark),
      );
      expect(tabsDecoration.border, isNull);
    });

    testWidgets('一级 Tab 吸顶态保留与顶部工具栏的分隔轮廓', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -900));
      await _pumpFrames(tester, count: 12);

      final pinnedTabsSurface = tester.widget<Container>(
        find.byKey(const ValueKey<String>('profile-shell-primary-tabs-pinned')),
      );
      final pinnedDecoration = pinnedTabsSurface.decoration! as BoxDecoration;

      expect(pinnedDecoration.border, isNotNull);
    });

    testWidgets('浅色吸顶态搜索按钮跟随工具栏前景色保持可见', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -900));
      await _pumpFrames(tester, count: 12);

      final searchIcon = tester.widget<Icon>(
        find.descendant(
          of: find.byKey(TestKeys.globalSearchLauncherButton),
          matching: find.byIcon(CupertinoIcons.search),
        ),
      );

      expect(searchIcon.color, isNot(CupertinoColors.white));
    });

    testWidgets('窄屏大字号下保持自适应不溢出', (tester) async {
      tester.view.physicalSize = const Size(320, 690);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final capturedErrors = <FlutterErrorDetails>[];
      final originalOnError = FlutterError.onError;
      FlutterError.onError = (details) {
        capturedErrors.add(details);
      };
      try {
        await tester.pumpWidget(
          _scopedApp(mode: ProfileMode.mine, textScaleFactor: 1.4),
        );
        await _pumpFrames(tester, count: 20);
      } finally {
        FlutterError.onError = originalOnError;
      }

      final overflowErrors = capturedErrors
          .map((details) => details.exceptionAsString())
          .where((message) => message.contains('A RenderFlex overflowed'))
          .toList(growable: false);

      expect(overflowErrors, isEmpty);
    });
  });

  group('ProfileShell — 几何与分层', () {
    testWidgets('ProfileHeader 不渲染 @username', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(find.textContaining('@'), findsNothing);
    });

    testWidgets('头像保持约 1/3 在背景、2/3 在资料区', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      final backgroundFinder = find.byKey(
        const ValueKey<String>('profile-shell-background-layer'),
      );
      final summaryFinder = find.byKey(
        const ValueKey<String>('profile-shell-summary-card'),
      );
      final avatarFinder = find.byKey(
        const ValueKey<String>('profile-header-avatar'),
      );
      final backgroundBottom = tester.getBottomLeft(backgroundFinder).dy;
      final summaryTop = tester.getTopLeft(summaryFinder).dy;
      final avatarTop = tester.getTopLeft(avatarFinder).dy;
      final avatarBottom = tester.getBottomLeft(avatarFinder).dy;
      final avatarHeight = tester.getSize(avatarFinder).height;

      expect(summaryTop, closeTo(backgroundBottom, 2));
      final backgroundShare = (backgroundBottom - avatarTop) / avatarHeight;
      final summaryShare = (avatarBottom - backgroundBottom) / avatarHeight;
      expect(
        backgroundShare,
        closeTo(UserProfileUIConfig.headerLayout.avatarOverlapRatio, 0.08),
      );
      expect(summaryShare, closeTo(1 - backgroundShare, 0.08));
    });

    testWidgets('other 模式在 capability 延迟时仍保持基础壳层渲染', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(find.byType(ProfileShell), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.back), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.ellipsis), findsOneWidget);
    });

    testWidgets('下拉时背景顶边固定，资料区与一级 tab 整体下移', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);

      final backgroundFinder = find.byKey(
        const ValueKey<String>('profile-shell-background-layer'),
        skipOffstage: false,
      );
      final summaryFinder = find.byKey(
        const ValueKey<String>('profile-shell-summary-card'),
        skipOffstage: false,
      );
      final tabsFinder = find.byKey(
        const ValueKey<String>('profile-shell-primary-tabs-inline'),
        skipOffstage: false,
      );

      final beforeBackgroundTop = tester.getTopLeft(backgroundFinder).dy;
      final beforeBackgroundHeight = tester.getSize(backgroundFinder).height;
      final beforeSummaryTop = tester.getTopLeft(summaryFinder).dy;
      final beforeTabsTop = tester.getTopLeft(tabsFinder).dy;

      await tester.drag(find.byType(CustomScrollView), const Offset(0, 180));
      await tester.pump();

      final afterBackgroundTop = tester.getTopLeft(backgroundFinder).dy;
      final afterBackgroundHeight = tester.getSize(backgroundFinder).height;
      final afterSummaryTop = tester.getTopLeft(summaryFinder).dy;
      final afterTabsTop = tester.getTopLeft(tabsFinder).dy;

      expect(afterBackgroundTop, closeTo(beforeBackgroundTop, 0.5));
      expect(afterBackgroundHeight, greaterThan(beforeBackgroundHeight));
      expect(afterSummaryTop, greaterThan(beforeSummaryTop));
      expect(afterTabsTop, greaterThan(beforeTabsTop));
    });

    testWidgets('我的主页四大板块左右齐屏，内容 surface 不再内缩', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);

      final screenWidth =
          tester.view.physicalSize.width / tester.view.devicePixelRatio;
      final profileCard = find.byKey(
        const ValueKey<String>('profile-shell-profile-card'),
      );
      final intersectionCard = find.byKey(
        const ValueKey<String>('my-intersection-inbox-card'),
      );
      final impactCard = find.byKey(
        const ValueKey<String>('author-impact-card'),
      );
      for (final finder in <Finder>[
        profileCard,
        intersectionCard,
        impactCard,
      ]) {
        expect(finder, findsOneWidget);
        expect(tester.getTopLeft(finder).dx, closeTo(0, AppSpacing.hairline));
        expect(
          tester.getTopRight(finder).dx,
          closeTo(screenWidth, AppSpacing.hairline),
        );
      }

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -520));
      await tester.pumpAndSettle();
      final tabSurface = find.byKey(
        const ValueKey<String>('profile-shell-tab-surface'),
      );
      expect(tabSurface, findsOneWidget);
      expect(tester.getTopLeft(tabSurface).dx, closeTo(0, AppSpacing.hairline));
      expect(
        tester.getTopRight(tabSurface).dx,
        closeTo(screenWidth, AppSpacing.hairline),
      );
    });

    testWidgets('上滑时封面随内容上移，下拉仍保持顶边固定拉伸', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);

      final backgroundFinder = find.byKey(
        const ValueKey<String>('profile-shell-background-layer'),
        skipOffstage: false,
      );
      final beforeTop = tester.getTopLeft(backgroundFinder).dy;

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -320));
      await tester.pump();
      final afterScrollTop = tester.getTopLeft(backgroundFinder).dy;
      expect(afterScrollTop, lessThan(beforeTop));

      await tester.drag(find.byType(CustomScrollView), const Offset(0, 420));
      await tester.pump();
      await tester.drag(find.byType(CustomScrollView), const Offset(0, 180));
      await tester.pump();
      final afterPullTop = tester.getTopLeft(backgroundFinder).dy;
      expect(afterPullTop, closeTo(beforeTop, 0.5));
    });
  });

  group('ProfileShell — 交互契约', () {
    testWidgets('圈子不再作为一级 Tab 渲染', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await revealProfilePrimaryTabs(tester);
      expect(_inlinePrimaryTab('圈子'), findsNothing);
      expect(find.text(ChatText.contactsTabCircles), findsOneWidget);
    });

    testWidgets('切换到互动 Tab 渲染 ProfileInteractionTab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(
        find.byKey(
          const ValueKey<String>('profile-interaction-direction-switch'),
        ),
        findsNothing,
      );
      await tapProfilePrimaryTab(tester, '互动');
      await _pumpFrames(tester, count: 20);
      expect(find.byType(ProfileInteractionTab), findsOneWidget);
      final primaryTabs = find.byKey(
        const ValueKey<String>('profile-shell-primary-tabs-inline'),
      );
      expect(
        find.descendant(
          of: primaryTabs,
          matching: find.byKey(
            const ValueKey<String>('profile-interaction-direction-switch'),
          ),
        ),
        findsNothing,
      );
      final secondaryTabs = find.byType(ProfileSecondaryTabBar);
      expect(
        find.descendant(
          of: secondaryTabs,
          matching: find.text(
            UITextConstants.profileInteractionDirectionReceived,
          ),
        ),
        findsNothing,
      );
      expect(
        find.descendant(
          of: secondaryTabs,
          matching: find.text(UITextConstants.profileInteractionDirectionSent),
        ),
        findsNothing,
      );
    });

    testWidgets('other 模式更多按钮打开统一底部动作面板', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);

      await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(AppBottomModalSurface), findsOneWidget);
      expect(find.byType(CupertinoActionSheet), findsNothing);
      expect(find.text('分享'), findsOneWidget);
      expect(find.text('拉黑'), findsOneWidget);
      expect(find.text('举报'), findsOneWidget);

      await tester.tap(find.text('分享'));
      await tester.pumpAndSettle();

      expect(find.byType(AppBottomModalSurface), findsNothing);
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('拉黑成功后失效主页缓存并离开受限主页', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final writer = _RecordingBlockWriter();
      var leaveCount = 0;

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          userId: 'u_block_target',
          onBack: () => leaveCount += 1,
          overrides: [
            authSessionControllerProvider.overrideWith(
              _AuthenticatedProfileAuthSession.new,
            ),
            personaRelationshipBlockWriterProvider.overrideWith(
              (ref, surface) => writer,
            ),
          ],
        ),
      );
      await _pumpFrames(tester);

      await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
      await tester.pumpAndSettle();
      await tester.tap(find.text(UITextConstants.profileBlockUser));
      await tester.pumpAndSettle();
      await tester.tap(find.text(UITextConstants.profileBlockUser));
      await _pumpFrames(tester);

      expect(writer.blockedTarget, 'u_block_target');
      expect(leaveCount, 1);
      expect(find.text(UITextConstants.profileBlockSuccess), findsOneWidget);
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('登录成功后一次性续接原 Persona 视频呼叫', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final startedIntents = <RtcCallEntryIntent>[];

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          userId: 'u_lin',
          capabilityRepository: _MutualCallCapabilityRepository(),
          overrides: [
            authSessionControllerProvider.overrideWith(
              _FlippableProfileAuthSession.new,
            ),
            rtcCallEntryPresenterProvider.overrideWithValue(
              RtcCallEntryPresenter(
                permissionRequest: (_, _) async =>
                    CallPermissionOutcome.granted,
                callStarter: (_, intent, _, _) async {
                  startedIntents.add(intent);
                  return 'fixture-call-id';
                },
                outgoingNavigator: (_, _) {},
              ),
            ),
          ],
        ),
      );
      await _pumpFrames(tester);
      final container = ProviderScope.containerOf(
        tester.element(find.byType(ProfileShell)),
      );
      container
          .read(authContinuationProvider.notifier)
          .set(
            const StartDirectCallContinuation(
              targetUserId: 'u_lin',
              callType: 'video',
            ),
            ownerToken: 'profile-call-entry',
          );

      (container.read(authSessionControllerProvider.notifier)
              as _FlippableProfileAuthSession)
          .loginNow();
      await _pumpFrames(tester);

      expect(startedIntents, hasLength(1));
      expect(startedIntents.single.mediaType, RtcCallEntryMediaType.video);
      expect(startedIntents.single.targetUserId, 'u_lin');
      expect(container.read(authContinuationProvider), isNull);
      await _pumpFrames(tester);
      expect(startedIntents, hasLength(1), reason: '续接必须 one-shot，不能重复发起');
    });

    testWidgets('互动二级 Tab 跟随内容滚动并可回显', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await tapProfilePrimaryTab(tester, '互动');
      await _pumpFrames(tester, count: 20);

      final subTabFinder = find.descendant(
        of: find.byKey(
          const ValueKey<String>('profile-interaction-secondary-tabs'),
        ),
        matching: find.text(UITextConstants.interactionSubLikes),
      );
      final before = tester.getTopLeft(subTabFinder);

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -600));
      await _pumpFrames(tester, count: 12);
      final afterScrollUp = tester.getTopLeft(subTabFinder);
      expect(afterScrollUp.dy, lessThan(before.dy));

      await tester.drag(find.byType(CustomScrollView), const Offset(0, 260));
      await _pumpFrames(tester, count: 12);
      final afterScrollBack = tester.getTopLeft(subTabFinder);
      expect(afterScrollBack.dy, greaterThan(afterScrollUp.dy));
    });

    testWidgets('列表区左滑先切创作二级 Tab，越界后才切一级 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);
      // 左滑切二级 Tab 需要 fling 落在创作列表区（works grid），先滚到其可见。
      await revealProfileSummaryWidget(
        tester,
        find.byKey(const ValueKey<String>('profile-works-grid')),
      );

      final swipeSurface = find.byKey(
        const ValueKey<String>('profile-works-grid'),
      );

      Future<void> flingVisibleWorksGridLeft() async {
        final origin = tester.getTopLeft(swipeSurface) + const Offset(48, 32);
        await tester.flingFrom(origin, const Offset(-420, 0), 1200);
        await _pumpFrames(tester, count: 12);
      }

      for (var i = 0; i < UserProfileUIConfig.creationSubTabs.length - 1; i++) {
        await flingVisibleWorksGridLeft();
        expect(find.byType(ProfileInteractionTab), findsNothing);
      }

      await flingVisibleWorksGridLeft();

      expect(find.byType(ProfileInteractionTab), findsOneWidget);
    });

    testWidgets('一级 tab 吸顶后切换创作与互动不会把整页重置到 tab 下方', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -900));
      await _pumpFrames(tester, count: 12);

      final summaryFinder = find.byKey(
        const ValueKey<String>('profile-shell-summary-card'),
      );

      final summaryBefore = tester.getTopLeft(summaryFinder).dy;
      final interactionTab = _pinnedPrimaryTab('互动').evaluate().isNotEmpty
          ? _pinnedPrimaryTab('互动')
          : _inlinePrimaryTab('互动');
      final creationsTab =
          _pinnedPrimaryTab(
            UITextConstants.profileTabCreations,
          ).evaluate().isNotEmpty
          ? _pinnedPrimaryTab(UITextConstants.profileTabCreations)
          : _inlinePrimaryTab(UITextConstants.profileTabCreations);

      await tester.tap(interactionTab);
      await _pumpFrames(tester, count: 12);
      final summaryAfterInteraction = tester.getTopLeft(summaryFinder).dy;
      expect(summaryAfterInteraction, closeTo(summaryBefore, 8));
      expect(find.byType(ProfileInteractionTab), findsOneWidget);

      await tester.tap(creationsTab);
      await _pumpFrames(tester, count: 12);
      final summaryAfterCreations = tester.getTopLeft(summaryFinder).dy;
      expect(summaryAfterCreations, closeTo(summaryBefore, 8));
      expect(
        find.byKey(const ValueKey<String>('profile-works-grid')),
        findsOneWidget,
      );
    });

    testWidgets('创作二级 tab 与列表首屏之间没有异常大留白', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);
      await revealProfilePrimaryTabs(tester);

      final tabsFinder = find.byKey(
        const ValueKey<String>('profile-works-secondary-tabs'),
      );
      final gridFinder = find.byKey(
        const ValueKey<String>('profile-works-grid'),
      );
      final gap =
          tester.getTopLeft(gridFinder).dy -
          tester.getBottomLeft(tabsFinder).dy;

      expect(gap, greaterThanOrEqualTo(0));
      expect(gap, lessThanOrEqualTo(24));
    });
  });

  group('ProfileShell — 暗色模式 (T61)', () {
    testWidgets('暗色模式下 mine 模式渲染不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(mode: ProfileMode.mine, themeMode: ThemeMode.dark),
      );
      await _pumpFrames(tester);
      await revealProfilePrimaryTabs(tester);
      expect(
        _inlinePrimaryTab(UITextConstants.profileTabCreations),
        findsOneWidget,
      );
      expect(
        find.byIcon(AppNavigationSemanticConstants.settingsActionIcon),
        findsOneWidget,
      );
    });

    testWidgets('暗色模式下 other 模式基础壳层渲染不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          themeMode: ThemeMode.dark,
          capabilityRepository: _StaticCapabilityRepository(),
        ),
      );
      await _pumpFrames(tester);
      expect(find.byType(ProfileShell), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.back), findsOneWidget);
    });

    testWidgets('AnnotatedRegion 存在于渲染树', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(
        find.byWidgetPredicate(
          (w) => w is AnnotatedRegion<SystemUiOverlayStyle>,
        ),
        findsAtLeastNWidgets(1),
      );
    });
  });

  group('ProfileShell — 错误态渲染', () {
    testWidgets('空 userId 不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine, userId: ''));
      await _pumpFrames(tester);
      await revealProfilePrimaryTabs(tester);
      expect(
        _inlinePrimaryTab(UITextConstants.profileTabCreations),
        findsOneWidget,
      );
    });

    testWidgets('首屏聚合失败渲染结构化错误态并提供重试', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(
          mode: ProfileMode.other,
          userId: 'stranger_failing',
          profileQuery: const _FailingHomepageBundleRepository(),
        ),
      );
      await _pumpFrames(tester);

      // 首屏失败不被乐观壳层静默吞掉：结构化错误态可见 + 重试入口（R17/R20）。
      expect(find.text(UITextConstants.tryAgain), findsOneWidget);
    });
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

Finder _inlinePrimaryTab(String label) {
  return find.descendant(
    of: find.byKey(const ValueKey<String>('profile-shell-primary-tabs-inline')),
    matching: find.text(label),
  );
}

Finder _pinnedPrimaryTab(String label) {
  return find.descendant(
    of: find.byKey(const ValueKey<String>('profile-shell-primary-tabs-pinned')),
    matching: find.text(label),
  );
}
