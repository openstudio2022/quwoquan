import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/pages/edit_profile_page.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';

import '../../../support/harness/profile_shell_scroll_utils.dart';

/// T28 旅程：我的主页 → 编辑资料 → 修改昵称 → 保存 → 返回 → 验证主页展示新昵称
class _EditProfileMockRepository extends MockUserProfileRepository {
  _EditProfileMockRepository() : super();

  final Map<String, dynamic> _updatedProfile = {};

  @override
  Future<void> updateProfile(ProfileEditUpdatePayload data) async {
    _updatedProfile.addAll(data.toRepositoryMap());
  }

  @override
  Future<SubAccountProfileViewData> getUserProfile(String userId) async {
    final base = await super.getUserProfile(userId);
    if (_updatedProfile.isEmpty) return base;
    final nick = _updatedProfile['nickname'] as String?;
    return SubAccountProfileViewData(
      subAccountId: base.subAccountId,
      ownerUserId: base.ownerUserId,
      subjectType: base.subjectType,
      userHandle: (_updatedProfile['userHandle'] as String?) ?? base.userHandle,
      username: (_updatedProfile['username'] as String?) ?? base.username,
      displayName: (nick != null && nick.isNotEmpty) ? nick : base.displayName,
      avatarUrl: base.avatarUrl,
      backgroundUrl: base.backgroundUrl,
      bio: (_updatedProfile['bio'] as String?) ?? base.bio,
      followerCount: base.followerCount,
      followingCount: base.followingCount,
      postCount: base.postCount,
      circleCount: base.circleCount,
      likeCount: base.likeCount,
      isolationLevel: base.isolationLevel,
      profileVisibility: base.profileVisibility,
      inheritsFromOwner: base.inheritsFromOwner,
      overriddenFields: base.overriddenFields,
      updatedAt: base.updatedAt,
    );
  }
}

/// 已登录态会话存储测试替身：MyProfilePage 现在依据 auth.isAuthenticated
/// 决定渲染真实主页还是未登录占位页，旅程测试必须注入已登录会话。
class _AuthenticatedAuthSessionStore implements AuthSessionStore {
  const _AuthenticatedAuthSessionStore();

  @override
  Future<StoredAuthSession> read() async {
    return const StoredAuthSession(
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      ownerId: 'user_001',
      activeSubAccountId: 'user_001',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'install-id',
      lastRefreshAtEpochMs: 0,
      lastForegroundAuthCheckAtEpochMs: 0,
      manualLoggedOut: false,
      launchPromptDismissed: false,
    );
  }

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

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_001',
    activeSubAccountId: 'user_001',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
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

  group('编辑资料昵称更新旅程', () {
    testWidgets('T28：进入我的主页 → 编辑资料 → 修改昵称 → 保存 → 返回 → 主页展示新昵称', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      const currentUserId = 'user_001';
      const newNickname = '测试新昵称_999';

      final mockRepo = _EditProfileMockRepository();
      final app = ProviderScope(
        overrides: [
          userProfileRepositoryProvider.overrideWithValue(mockRepo),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _ThrowingCapabilityRepository(),
          ),
          currentUserIdProvider.overrideWithValue(currentUserId),
          authSessionStoreProvider.overrideWithValue(
            const _AuthenticatedAuthSessionStore(),
          ),
          authSessionControllerProvider.overrideWith(
            _AuthenticatedSessionController.new,
          ),
        ],
        child: MaterialApp.router(
          routerConfig: GoRouter(
            initialLocation: '/profile',
            routes: [
              GoRoute(
                path: '/profile',
                builder: (context, state) => const MyProfilePage(),
                routes: [
                  GoRoute(
                    path: 'edit',
                    builder: (context, state) => const EditProfilePage(),
                  ),
                ],
              ),
            ],
          ),
        ),
      );

      await tester.pumpWidget(app);
      await _pumpFrames(tester, count: 20);

      expect(
        find.byKey(const ValueKey<String>('profile-header-edit')),
        findsNothing,
      );
      final editProfileAction = find.text(UITextConstants.profileEditLabel);
      await revealProfileSummaryWidget(tester, editProfileAction);
      expect(editProfileAction, findsAtLeastNWidgets(1));
      await tester.tap(editProfileAction.first);
      await _pumpFrames(tester, count: 10);

      expect(find.text(UITextConstants.editProfile), findsOneWidget);
      final navTitleBottom = tester
          .getBottomLeft(find.text(UITextConstants.editProfile))
          .dy;
      final coverTop = tester
          .getTopLeft(find.text(UITextConstants.editProfileCoverLabel))
          .dy;
      expect(
        coverTop,
        greaterThan(navTitleBottom),
        reason: '资料编辑字段必须完整落在 iOS 导航栏下方，不能被顶栏遮挡',
      );
      expect(
        find.byType(ProfileIosGroupedSection),
        findsNWidgets(4),
        reason: '编辑资料主表单必须拆成媒体、基础资料、账号社交、扩展资料四个区块',
      );

      final orderedLabels = <String>[
        UITextConstants.editProfileCoverLabel,
        UITextConstants.editProfileAvatarLabel,
        UITextConstants.editProfileNicknameLabel,
        UITextConstants.editProfileGenderLabel,
        UITextConstants.editProfileBirthdayLabel,
        UITextConstants.editProfileRegionLabel,
        UITextConstants.editProfilePhoneLabel,
        UITextConstants.editProfileQuwoquanIdLabel,
        UITextConstants.editProfileQrCodeLabel,
        UITextConstants.editProfileBioLabel,
        UITextConstants.editProfileTagsLabel,
      ];
      var previousTop = -1.0;
      for (final label in orderedLabels) {
        final top = tester.getTopLeft(find.text(label).first).dy;
        expect(top, greaterThan(previousTop), reason: '$label 字段顺序不正确');
        previousTop = top;
      }

      final coverPreviewSize = tester.getSize(
        find.byKey(const ValueKey<String>('edit-profile-cover-preview')),
      );
      final avatarPreviewSize = tester.getSize(
        find.byKey(const ValueKey<String>('edit-profile-avatar-preview')),
      );
      expect(
        coverPreviewSize,
        avatarPreviewSize,
        reason: '封面与头像缩略图必须使用同一媒体预览语义尺寸',
      );
      expect(
        coverPreviewSize.width,
        coverPreviewSize.height,
        reason: '媒体行缩略图必须保持稳定正方形槽位，避免右侧宽度漂移',
      );
      expect(
        find.text(UITextConstants.editProfileFillCtaValue),
        findsAtLeastNWidgets(1),
        reason: '未填写资料应使用可行动的中性补全提示',
      );
      expect(
        find.text(UITextConstants.editProfileSelectCtaValue),
        findsAtLeastNWidgets(1),
        reason: '选择型空值应以简短好处提示用户补充',
      );
      expect(
        find.text(UITextConstants.editProfileGenderUnsetValue),
        findsAtLeastNWidgets(1),
        reason: '未设置性别时不应默认显示为不展示',
      );
      expect(
        find.byIcon(CupertinoIcons.doc_on_doc),
        findsNothing,
        reason: '趣我圈号行只展示系统分配的号，不显示额外图标',
      );

      await tester.tap(find.text(UITextConstants.editProfileGenderLabel).first);
      await _pumpFrames(tester, count: 8);
      expect(find.text(UITextConstants.editProfileGenderMale), findsWidgets);
      expect(find.text(UITextConstants.editProfileGenderFemale), findsWidgets);
      expect(find.byIcon(CupertinoIcons.person_2), findsNothing);
      await tester.tap(
        find.text(UITextConstants.editProfileGenderUnspecified).last,
      );
      await _pumpFrames(tester, count: 8);

      await tester.tap(find.text(UITextConstants.editProfileRegionLabel).first);
      await _pumpFrames(tester, count: 8);
      expect(find.text(UITextConstants.editProfileRegionTitle), findsOneWidget);
      expect(find.text('广东'), findsOneWidget);
      await tester.tap(find.text('广东'));
      await _pumpFrames(tester, count: 8);
      expect(find.text('深圳'), findsOneWidget);
      expect(
        find.byIcon(CupertinoIcons.chevron_forward),
        findsNothing,
        reason: '广东二级城市是最终选择项，不应再显示继续选择箭头',
      );
      await tester.scrollUntilVisible(
        find.text('云浮'),
        500,
        scrollable: find.byType(Scrollable).last,
      );
      await _pumpFrames(tester, count: 4);
      expect(find.text('云浮'), findsOneWidget);
      await tester.tap(find.text('云浮'));
      await _pumpFrames(tester, count: 8);

      await tester.tap(
        find.byKey(const ValueKey<String>('edit-profile-nickname-row')),
      );
      await _pumpFrames(tester, count: 8);
      expect(find.text(UITextConstants.editProfileNicknameLabel), findsWidgets);
      await tester.enterText(
        find.byType(CupertinoTextField).first,
        newNickname,
      );
      await _pumpFrames(tester);
      await tester.tap(
        find.byKey(const ValueKey<String>('edit-profile-text-save')),
      );
      await _pumpFrames(tester, count: 8);

      await tester.tap(find.byKey(const ValueKey<String>('edit-profile-save')));
      await _pumpFrames(tester, count: 20);

      expect(find.text(newNickname), findsAtLeastNWidgets(1));
      expect(
        mockRepo._updatedProfile['regionTagRef'],
        'Topic/地理/行政区/中国/广东省/云浮市',
      );
      expect(mockRepo._updatedProfile.containsKey('regionCode'), isFalse);
      await tester.pump(const Duration(seconds: 4));
    });
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}
