import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/pages/edit_profile_page.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';

/// T28 旅程：我的主页 → 编辑资料 → 修改昵称 → 保存 → 返回 → 验证主页展示新昵称
class _EditProfileMockRepository extends MockUserProfileRepository {
  _EditProfileMockRepository() : super();

  final Map<String, dynamic> _updatedProfile = {};

  @override
  Future<void> updateProfile(ProfileEditUpdatePayload data) async {
    _updatedProfile.addAll(data.toRepositoryMap());
  }

  @override
  Future<ProfileSubjectViewData> getUserProfile(String userId) async {
    final base = await super.getUserProfile(userId);
    if (_updatedProfile.isEmpty) return base;
    final nick = _updatedProfile['nickname'] as String?;
    return ProfileSubjectViewData(
      subAccountId: base.subAccountId,
      ownerUserId: base.ownerUserId,
      subjectType: base.subjectType,
      userHandle: (_updatedProfile['userHandle'] as String?) ?? base.userHandle,
      username: (_updatedProfile['username'] as String?) ?? base.username,
      displayName:
          (nick != null && nick.isNotEmpty) ? nick : base.displayName,
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
          relationshipCapabilityRepositoryProvider
              .overrideWithValue(_ThrowingCapabilityRepository()),
          currentUserIdProvider.overrideWithValue(currentUserId),
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
      await tester.pumpAndSettle(const Duration(seconds: 5));

      expect(find.text(UITextConstants.profileEditLabel), findsOneWidget);
      await tester.tap(find.text(UITextConstants.profileEditLabel));
      await _pumpFrames(tester, count: 10);

      expect(find.text(UITextConstants.editProfile), findsOneWidget);

      await tester.enterText(
        find.byType(CupertinoTextField).first,
        newNickname,
      );
      await _pumpFrames(tester);

      await tester.tap(find.text('保存'));
      await tester.pumpAndSettle(const Duration(seconds: 5));

      expect(find.text(newNickname), findsAtLeastNWidgets(1));
    });
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}
