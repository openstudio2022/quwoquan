// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-001
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_edit_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/profile_update_proposal/application/public/profile_update_proposal_ports.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_homepage_view_data.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_media_upload_gateway.dart';
import 'package:quwoquan_app/design_system/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/profile_presentation_slots.dart'
    show editProfileParticipantSlots;
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/edit_profile_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        ProfileCommandWriter,
        ProfileQrResolveWire,
        ProfileUpdateProposalListQuery,
        ProfileUpdateProposalQuery,
        ProfileUpdateProposalSlice,
        ProfileUpdateProposalView,
        ProfileUpdateSnapshot,
        UpdateUserProfileCommand;
import '../../../../../support/service/tag_service/tag/tag_node_view/tag_catalog_typed_double.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

import '../../../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';

/// T28 旅程：我的主页 → 编辑资料 → 修改昵称 → 保存 → 返回 → 验证主页展示新昵称
class _EditProfileMockRepository implements ProfileQuery, ProfileEditQuery {
  String? _updatedNickname;
  String? _updatedBio;
  UpdateUserProfileCommand? lastCommand;
  final List<UpdateUserProfileCommand> commands = <UpdateUserProfileCommand>[];

  void apply(UpdateUserProfileCommand command) {
    lastCommand = command;
    commands.add(command);
    _updatedNickname = command.nickname ?? _updatedNickname;
    _updatedBio = command.bio ?? _updatedBio;
  }

  @override
  Future<PersonaProfileViewData> getUserProfile(String userId) async {
    const base = PersonaProfileViewData(
      personaId: 'user_001',
      ownerUserId: 'user_001',
      subjectType: 'user',
      userHandle: 'test_user',
      displayName: '测试用户',
      avatarUrl: '',
      backgroundUrl: '',
      bio: '',
      followerCount: 0,
      followingCount: 0,
      postCount: 0,
      circleCount: 0,
      likeCount: 0,
      isolationLevel: 'open',
      profileVisibility: 'public',
      inheritsFromOwner: true,
      overriddenFields: <String>[],
      updatedAt: null,
    );
    final nick = _updatedNickname;
    if (nick == null && _updatedBio == null) {
      return base;
    }
    return PersonaProfileViewData(
      personaId: base.personaId,
      ownerUserId: base.ownerUserId,
      subjectType: base.subjectType,
      userHandle: base.userHandle,
      displayName: (nick != null && nick.isNotEmpty) ? nick : base.displayName,
      nicknameCustomized: nick != null || base.nicknameCustomized,
      avatarUrl: base.avatarUrl,
      avatarVersion: base.avatarVersion,
      backgroundUrl: base.backgroundUrl,
      bio: _updatedBio ?? base.bio,
      identityTags: base.identityTags,
      verified: base.verified,
      followerCount: base.followerCount,
      followingCount: base.followingCount,
      postCount: base.postCount,
      circleCount: base.circleCount,
      likeCount: base.likeCount,
      profileCompleteness: base.profileCompleteness,
      profileCompletenessMissingItems: base.profileCompletenessMissingItems,
      isolationLevel: base.isolationLevel,
      profileVisibility: base.profileVisibility,
      inheritsFromOwner: base.inheritsFromOwner,
      overriddenFields: base.overriddenFields,
      updatedAt: base.updatedAt,
    );
  }

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String personaId,
  ) async {
    final profile = await getUserProfile(personaId);
    final stats = UserProfileStatsViewData.fromProfile(profile);
    return UserHomepageBundleViewData(
      profile: profile,
      stats: stats,
      relationshipCapability: null,
      tabCounts: UserHomepageTabCountsViewData.fromStats(stats),
      viewerContext: UserHomepageViewerContextViewData(
        viewerPersonaId: 'user_001',
        isOwner: true,
        isGuest: false,
        relationToTarget: 'self',
        canViewFullProfile: true,
      ),
      cacheVersion: 'uat-profile-revision-a',
    );
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async {
    return UserProfileStatsViewData.fromProfile(await getUserProfile(userId));
  }

  @override
  Future<List<SocialRelationSearchItemViewData>> searchSocialRelations({
    required String query,
    int limit = 20,
  }) async => const <SocialRelationSearchItemViewData>[];

  @override
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() async {
    final profile = await getUserProfile('user_001');
    return ProfileEditSnapshotData(
      ownerUserId: profile.ownerUserId,
      personaId: profile.personaId,
      avatarUrl: profile.avatarUrl,
      avatarAssetId: '',
      avatarVersion: profile.avatarVersion,
      backgroundUrl: profile.backgroundUrl,
      backgroundAssetId: '',
      nickname: profile.displayName,
      gender: 'unspecified',
      birthDate: '',
      region: '',
      regionTagRef: lastCommand?.regionTagRef ?? '',
      userHandle: profile.userHandle,
      bio: profile.bio,
      occupationTagRef: '',
      interestTagRefs: const <String>[],
    );
  }

  @override
  Future<ProfileQrCardData> getProfileQrCard() async {
    return const ProfileQrCardData(
      publicProfileUrl: 'https://app.quwoquan.test/u/test_user',
      qrPayload: 'https://app.quwoquan.test/u/test_user?qr=uat',
      qrTokenId: 'uat-token',
      avatarUrl: '',
      displayName: '测试用户',
      region: '',
      shareText: '测试用户',
    );
  }

  @override
  Future<ProfileQrResolveWire> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) async {
    return ProfileQrResolveWire(
      personaId: 'user_001',
      userHandle: handle.isEmpty ? 'test_user' : handle,
      publicProfileUrl: 'https://app.quwoquan.test/u/test_user',
      scanStatus: 'accepted',
    );
  }
}

class _EditProfileCommandWriter implements ProfileCommandWriter {
  _EditProfileCommandWriter(this.repository);

  final _EditProfileMockRepository repository;

  @override
  Future<ProfileUpdateSnapshot> updateUserProfile(
    UpdateUserProfileCommand command,
  ) async {
    repository.apply(command);
    return ProfileUpdateSnapshot(
      userId: 'user_001',
      nickname: command.nickname ?? '',
      nicknameCustomized: command.nickname != null,
      profileVersion: 2,
      avatarVersion: 0,
      bio: command.bio,
      identityTags: const <String>[],
      updatedAt: DateTime.now().toUtc(),
    );
  }
}

class _EmptyProfileProposalQuery implements ProfileUpdateProposalReader {
  const _EmptyProfileProposalQuery();

  @override
  Future<ProfileUpdateProposalView> get(
    ProfileUpdateProposalQuery query,
  ) async {
    throw StateError('profile proposal not found');
  }

  @override
  Future<ProfileUpdateProposalSlice> list(
    ProfileUpdateProposalListQuery query,
  ) async {
    return ProfileUpdateProposalSlice(items: <ProfileUpdateProposalView>[]);
  }
}

class _RecordingNoNetworkClient extends http.BaseClient {
  final List<Uri> requestedUris = <Uri>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requestedUris.add(request.url);
    return http.StreamedResponse(
      const Stream<List<int>>.empty(),
      503,
      request: request,
    );
  }
}

class _ProfileEditJourneyEntry extends ConsumerStatefulWidget {
  const _ProfileEditJourneyEntry();

  @override
  ConsumerState<_ProfileEditJourneyEntry> createState() =>
      _ProfileEditJourneyEntryState();
}

class _ProfileEditJourneyEntryState
    extends ConsumerState<_ProfileEditJourneyEntry> {
  late Future<PersonaProfileViewData> _profile;

  @override
  void initState() {
    super.initState();
    _profile = _load();
  }

  Future<PersonaProfileViewData> _load() {
    return ref
        .read(profileQueryProvider(AppUiSurfaces.profileEdit))
        .getUserProfile('me');
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      child: SafeArea(
        child: FutureBuilder<PersonaProfileViewData>(
          future: _profile,
          builder: (context, snapshot) {
            if (!snapshot.hasData) {
              return const Center(child: CupertinoActivityIndicator());
            }
            return Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Text(snapshot.data!.displayName),
                CupertinoButton(
                  onPressed: () async {
                    await context.push('/profile/edit');
                    if (!mounted) return;
                    final refreshedProfile = _load();
                    setState(() {
                      _profile = refreshedProfile;
                    });
                  },
                  child: const Text(ProfileText.profileEditLabel),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// 已登录态会话存储测试替身。
class _AuthenticatedAuthSessionStore extends AuthSessionStore {
  _AuthenticatedAuthSessionStore();

  @override
  Future<StoredAuthSession> read() async {
    return const StoredAuthSession(
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      ownerId: 'user_001',
      activePersonaId: 'user_001',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'install-id',
      lastRefreshAtEpochMs: 0,
      lastForegroundAuthCheckAtEpochMs: 0,
      manualLoggedOut: false,
      launchPromptDismissed: false,
    );
  }
}

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_001',
    activePersonaId: 'user_001',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
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

  group('编辑资料昵称更新旅程', () {
    testWidgets('T28：进入我的主页 → 编辑资料 → 修改昵称 → 保存 → 返回 → 主页展示新昵称', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      const currentUserId = 'user_001';
      const newNickname = '测试新昵称_999';

      final mockRepo = _EditProfileMockRepository();
      final noNetworkClient = _RecordingNoNetworkClient();
      final contentStore = InMemoryContentPostStore();
      final app = ProviderScope(
        overrides: [
          contentRuntimeConfigProvider.overrideWithValue(
            buildProductionContentRuntimeConfigDefaults(),
          ),
          cloudHttpClientProvider.overrideWithValue(
            CloudHttpClient(
              client: noNetworkClient,
              timeout: const Duration(milliseconds: 10),
            ),
          ),
          profileQueryProvider.overrideWith((ref, surface) => mockRepo),
          profileEditQueryProvider.overrideWith((ref, surface) => mockRepo),
          profileCommandWriterProvider.overrideWithValue(
            _EditProfileCommandWriter(mockRepo),
          ),
          profileMediaUploadGatewayProvider.overrideWithValue(
            const _UnusedProfileMediaUploadGateway(),
          ),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            relationshipCapabilityRepositoryFrom(
              const TestRelationshipCapabilityQuery.mutual(),
            ),
          ),
          tagCatalogQueryProvider.overrideWithValue(TagCatalogTypedDouble()),
          currentUserIdProvider.overrideWithValue(currentUserId),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData(
              personaId: currentUserId,
              ownerUserId: currentUserId,
              subjectType: 'persona',
              displayName: '测试用户',
              avatarUrl: '',
              contextVersion: 1,
              isPrimary: true,
            ),
          ),
          profileEditProposalQueryReaderProvider.overrideWithValue(
            const _EmptyProfileProposalQuery(),
          ),
          userProfileContentAuthorPostsReaderProvider.overrideWithValue(
            InMemoryContentAuthorPostsReader(contentStore),
          ),
          authSessionStoreProvider.overrideWithValue(
            _AuthenticatedAuthSessionStore(),
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
                builder: (context, state) => const _ProfileEditJourneyEntry(),
                routes: [
                  GoRoute(
                    path: 'edit',
                    builder: (context, state) => const EditProfilePage(
                      participantSlots: editProfileParticipantSlots,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      );

      await tester.pumpWidget(app);
      await _pumpFrames(tester, count: 20);

      final editProfileAction = find.text(ProfileText.profileEditLabel);
      expect(editProfileAction, findsOneWidget);
      await tester.tap(editProfileAction.first);
      await _pumpFrames(tester, count: 10);

      expect(find.text(SettingsText.editProfile), findsOneWidget);
      final navTitleBottom = tester
          .getBottomLeft(find.text(SettingsText.editProfile))
          .dy;
      final coverTop = tester
          .getTopLeft(find.text(ProfileText.editProfileCoverLabel))
          .dy;
      expect(
        coverTop,
        greaterThan(navTitleBottom),
        reason: '资料编辑字段必须完整落在 iOS 导航栏下方，不能被顶栏遮挡',
      );
      expect(
        find.byType(ProfileIosGroupedSection),
        findsNWidgets(4),
        reason: '无待处理提案时，编辑资料主表单必须呈现媒体、基础资料、账号社交、扩展资料四个区块',
      );

      final orderedLabels = <String>[
        ProfileText.editProfileCoverLabel,
        ProfileText.editProfileAvatarLabel,
        ProfileText.editProfileNicknameLabel,
        ProfileText.editProfileGenderLabel,
        ProfileText.editProfileBirthdayLabel,
        ProfileText.editProfileRegionLabel,
        ProfileText.editProfilePhoneLabel,
        ProfileText.editProfileQuwoquanIdLabel,
        ProfileText.editProfileQrCodeLabel,
        ProfileText.editProfileBioLabel,
        ProfileText.editProfileTagsLabel,
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
        find.text(ProfileText.editProfileFillCtaValue),
        findsAtLeastNWidgets(1),
        reason: '未填写资料应使用可行动的中性补全提示',
      );
      expect(
        find.text(ProfileText.editProfileSelectCtaValue),
        findsAtLeastNWidgets(1),
        reason: '选择型空值应以简短好处提示用户补充',
      );
      expect(
        find.text(ProfileText.editProfileGenderUnsetValue),
        findsAtLeastNWidgets(1),
        reason: '未设置性别时不应默认显示为不展示',
      );
      expect(
        find.byIcon(CupertinoIcons.doc_on_doc),
        findsNothing,
        reason: '趣我圈号行只展示系统分配的号，不显示额外图标',
      );

      await tester.tap(find.text(ProfileText.editProfileGenderLabel).first);
      await _pumpFrames(tester, count: 8);
      expect(find.text(ProfileText.editProfileGenderMale), findsWidgets);
      expect(find.text(ProfileText.editProfileGenderFemale), findsWidgets);
      expect(find.byIcon(CupertinoIcons.person_2), findsNothing);
      await tester.tap(
        find.text(ProfileText.editProfileGenderUnspecified).last,
      );
      await _pumpFrames(tester, count: 8);

      await tester.tap(find.text(ProfileText.editProfileRegionLabel).first);
      await _pumpFrames(tester, count: 8);
      expect(find.text(ProfileText.editProfileRegionTitle), findsOneWidget);
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
      expect(find.text('广东 云浮'), findsOneWidget);

      await tester.tap(
        find.byKey(const ValueKey<String>('edit-profile-nickname-row')),
      );
      await _pumpFrames(tester, count: 8);
      expect(find.text(ProfileText.editProfileNicknameLabel), findsWidgets);
      await tester.enterText(
        find.byType(CupertinoTextField).first,
        newNickname,
      );
      await _pumpFrames(tester);
      await tester.tap(
        find.byKey(const ValueKey<String>('edit-profile-text-save')),
      );
      await _pumpFrames(tester, count: 8);

      final saveButton = find.byKey(
        const ValueKey<String>('edit-profile-save'),
      );
      expect(
        tester.widget<CupertinoButton>(saveButton).onPressed,
        isNotNull,
        reason: '地区与昵称变更后主表单必须可提交',
      );
      await tester.tap(saveButton);
      await _pumpFrames(tester, count: 20);

      expect(find.text(newNickname), findsAtLeastNWidgets(1));
      expect(
        mockRepo.commands.map((command) => command.regionTagRef),
        contains('Topic/地理/行政区/中国/广东省/云浮市'),
      );
      expect(mockRepo.lastCommand, isA<UpdateUserProfileCommand>());
      expect(
        noNetworkClient.requestedUris,
        isEmpty,
        reason: '资料编辑 UAT 的全部业务依赖必须显式注入，不得回退真实网络',
      );
      await tester.pump(const Duration(seconds: 4));
    });
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

class _UnusedProfileMediaUploadGateway implements ProfileMediaUploadGateway {
  const _UnusedProfileMediaUploadGateway();

  @override
  Future<ProfileMediaUploadResult> uploadImage({
    required String localPath,
    required ProfileMediaTarget target,
  }) {
    throw StateError('profile journey does not select media');
  }
}
