import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

import '../../../support/harness/profile_shell_scroll_utils.dart';

/// 互动 Tab：切换后渲染 ProfileInteractionTab，二级子页（赞/评论/分享）可见。
class _NoNetworkHttpOverrides extends HttpOverrides {}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

class _InteractionContractRepository extends MockUserProfileRepository {
  const _InteractionContractRepository({
    required this.received,
    required this.sent,
  });

  final List<ProfileInteractionActivityViewData> received;
  final List<ProfileInteractionActivityViewData> sent;

  @override
  Future<List<ProfileInteractionActivityViewData>>
  listProfileInteractionReceivedView(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return received.take(limit).toList(growable: false);
  }

  @override
  Future<List<ProfileInteractionActivityViewData>>
  listProfileInteractionSentView(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return sent.take(limit).toList(growable: false);
  }
}

Widget _scopedApp() {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
    ],
    child: MaterialApp(
      theme: ThemeData.light(),
      home: const ProfileShell(
        mode: ProfileMode.mine,
        userId: 'nature_photographer',
      ),
    ),
  );
}

Widget _interactionTabApp(
  _InteractionContractRepository repository, {
  ProfileMode mode = ProfileMode.mine,
}) {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(repository),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
    ],
    child: MaterialApp(
      theme: ThemeData.light(),
      home: SizedBox(
        height: 720,
        child: ProfileInteractionTab(
          mode: mode,
          userId: 'profile_owner',
          isDark: false,
        ),
      ),
    ),
  );
}

Widget _interactionTabRouterApp(_InteractionContractRepository repository) {
  final router = GoRouter(
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => const SizedBox(
          height: 720,
          child: ProfileInteractionTab(
            mode: ProfileMode.mine,
            userId: 'profile_owner',
            isDark: false,
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.userProfilePathTemplate.replaceAll(
          '{username}',
          ':username',
        ),
        builder: (context, state) =>
            Text('用户页:${state.pathParameters['username'] ?? ''}'),
      ),
      GoRoute(
        path: AppRoutePaths.workBrowserPathTemplate.replaceAll(
          '{workId}',
          ':workId',
        ),
        builder: (context, state) =>
            Text('作品页:${state.pathParameters['workId'] ?? ''}'),
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(repository),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
    ],
    child: MaterialApp.router(theme: ThemeData.light(), routerConfig: router),
  );
}

ProfileInteractionActivityViewData _interaction({
  required String id,
  required String primaryText,
  required List<String> filterKeys,
  String direction = 'received',
  String displaySubAccountId = 'u_display',
  String displayName = '林清越',
  String displayAvatarUrl = '',
  String previewMediaKind = 'text',
  String previewImageUrl = '',
  String previewText = '街角光影',
  String contextText = '',
  String commentKind = 'none',
  bool previewUnavailable = false,
}) {
  return ProfileInteractionActivityViewData(
    activityId: id,
    activityType: 'contract_activity',
    direction: direction,
    commentKind: commentKind,
    actorSubAccountId: 'u_actor',
    actorDisplayName: '互动用户',
    actorAvatarUrl: '',
    targetSubAccountId: 'profile_owner',
    targetContentId: 'post_$id',
    targetContentType: 'contract_target',
    targetContentSummary: '旧字段不应作为主句',
    displaySubAccountId: displaySubAccountId,
    displayName: displayName,
    displayAvatarUrl: displayAvatarUrl,
    displayUserRouteId: AppLinkTemplates.userRouteId,
    primaryText: primaryText,
    contextText: contextText,
    previewMediaKind: previewMediaKind,
    previewImageUrl: previewImageUrl,
    previewText: previewText,
    previewUnavailable: previewUnavailable,
    previewObjectId: 'post_$id',
    previewRouteId: previewUnavailable ? '' : AppLinkTemplates.postRouteId,
    filterKeys: filterKeys,
    createdAt: DateTime.utc(2026, 6, 18),
  );
}

void _setPhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3.0;
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 20}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 80));
  }
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  testWidgets('切换到互动 Tab 渲染 ProfileInteractionTab + 二级子页', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scopedApp());
    await _pumpFrames(tester);
    await tapProfilePrimaryTab(tester, '互动');
    await _pumpFrames(tester);

    expect(find.byType(ProfileInteractionTab), findsOneWidget);
    expect(
      find.descendant(
        of: find.byKey(
          const ValueKey<String>('profile-interaction-secondary-tabs'),
        ),
        matching: find.text(UITextConstants.interactionSubAll),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(
          const ValueKey<String>('profile-interaction-secondary-tabs'),
        ),
        matching: find.text(UITextConstants.interactionSubLikes),
      ),
      findsOneWidget,
    );
  });

  testWidgets('filterKeys 驱动二级过滤，主句只读契约字段', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      _interactionTabApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'like',
              primaryText: '契约主句：点赞',
              filterKeys: const <String>['all', 'likes'],
            ),
            _interaction(
              id: 'comment',
              primaryText: '契约主句：评论',
              filterKeys: const <String>['all', 'comments'],
            ),
            _interaction(
              id: 'share',
              primaryText: '契约主句：转发',
              filterKeys: const <String>['all', 'shares'],
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);

    expect(find.text('契约主句：点赞'), findsOneWidget);
    expect(find.text('契约主句：评论'), findsOneWidget);
    expect(find.text('契约主句：转发'), findsOneWidget);
    expect(find.text('旧字段不应作为主句'), findsNothing);
    expect(find.byIcon(CupertinoIcons.chevron_forward), findsNothing);

    await tester.tap(find.text(UITextConstants.interactionSubComments));
    await _pumpFrames(tester);

    expect(find.text('契约主句：评论'), findsOneWidget);
    expect(find.text('契约主句：点赞'), findsNothing);
    expect(find.text('契约主句：转发'), findsNothing);

    await tester.tap(find.text(UITextConstants.interactionSubShares));
    await _pumpFrames(tester);

    expect(find.text('契约主句：转发'), findsOneWidget);
    expect(find.text('契约主句：评论'), findsNothing);
  });

  testWidgets('方向入口使用统一底部面板并切换 sent 数据', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      _interactionTabApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'received',
              primaryText: '收到方向主句',
              filterKeys: const <String>['all'],
            ),
          ],
          sent: [
            _interaction(
              id: 'sent',
              direction: 'sent',
              primaryText: '发出方向主句',
              filterKeys: const <String>['all'],
            ),
          ],
        ),
      ),
    );
    await _pumpFrames(tester);

    expect(find.text('收到方向主句'), findsOneWidget);
    await tester.tap(
      find.byKey(const ValueKey<String>('profile-interaction-direction-entry')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byType(AppBottomModalSurface), findsOneWidget);
    await tester.tap(
      find.text(UITextConstants.profileInteractionDirectionSent).last,
    );
    await _pumpFrames(tester);

    expect(find.text('发出方向主句'), findsOneWidget);
    expect(find.text('收到方向主句'), findsNothing);
  });

  testWidgets('未知 previewMediaKind 降级文本，失效态显示契约空态', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      _interactionTabApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'unknown',
              primaryText: '未知预览主句',
              filterKeys: const <String>['all'],
              previewMediaKind: 'audio',
              previewText: '未知预览文本',
            ),
            _interaction(
              id: 'unavailable',
              primaryText: '失效预览主句',
              filterKeys: const <String>['all'],
              previewMediaKind: 'none',
              previewText: '',
              previewUnavailable: true,
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);

    expect(find.text('未知预览文本'), findsOneWidget);
    expect(
      find.text(UITextConstants.profileInteractionOriginalUnavailable),
      findsOneWidget,
    );
  });

  testWidgets('图片/视频/文本/评论引用/回复引用/删除态按契约字段渲染', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      _interactionTabApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'image',
              primaryText: '图片记录主句',
              filterKeys: const <String>['all', 'likes'],
              previewMediaKind: 'image',
              previewImageUrl: 'media/content/test/image.jpg',
              previewText: '图片记录',
            ),
            _interaction(
              id: 'video',
              primaryText: '视频记录主句',
              filterKeys: const <String>['all', 'likes'],
              previewMediaKind: 'video',
              previewText: '视频记录',
            ),
            _interaction(
              id: 'text',
              primaryText: '文字记录主句',
              filterKeys: const <String>['all', 'shares'],
              previewMediaKind: 'text',
              previewText: '文字记录预览',
            ),
            _interaction(
              id: 'comment-ref',
              primaryText: '评论了你的记录：写得真好',
              filterKeys: const <String>['all', 'comments'],
              contextText: '引用评论：写得真好',
              commentKind: 'comment',
              previewMediaKind: 'text',
              previewText: '评论引用原记录',
            ),
            _interaction(
              id: 'reply-ref',
              primaryText: '回复了你：我也喜欢',
              filterKeys: const <String>['all', 'comments'],
              contextText: '你说：这组颜色像旧电影',
              commentKind: 'reply',
              previewMediaKind: 'text',
              previewText: '回复引用原记录',
            ),
            _interaction(
              id: 'deleted',
              primaryText: '删除态主句',
              filterKeys: const <String>['all', 'comments'],
              previewMediaKind: 'none',
              previewText: '',
              previewUnavailable: true,
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);

    expect(find.text('图片记录主句'), findsOneWidget);
    expect(find.text('视频记录主句'), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.play_circle_fill), findsOneWidget);
    expect(find.text('文字记录预览'), findsOneWidget);
    expect(find.text('引用评论：写得真好'), findsOneWidget);
    expect(find.text('你说：这组颜色像旧电影'), findsOneWidget);
    expect(
      find.text(UITextConstants.profileInteractionOriginalUnavailable),
      findsOneWidget,
    );
  });

  testWidgets('他人主页不显示方向入口', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      _interactionTabApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'other',
              primaryText: '他人主页收到主句',
              filterKeys: const <String>['all'],
            ),
          ],
          sent: [
            _interaction(
              id: 'other-sent',
              primaryText: '他人主页不应展示发出',
              filterKeys: const <String>['all'],
            ),
          ],
        ),
        mode: ProfileMode.other,
      ),
    );
    await _pumpFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('profile-interaction-direction-entry')),
      findsNothing,
    );
    expect(find.text('他人主页收到主句'), findsOneWidget);
    expect(find.text('他人主页不应展示发出'), findsNothing);
  });

  testWidgets('头像昵称与预览点击使用生成路由 helper', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      _interactionTabRouterApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'clickable',
              primaryText: '可点击主句',
              filterKeys: const <String>['all'],
              displaySubAccountId: 'u_target',
              displayName: '可点击用户',
              previewMediaKind: 'text',
              previewText: '可点击预览',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);

    await tester.tap(find.text('可点击用户'));
    await tester.pumpAndSettle();
    expect(find.text('用户页:u_target'), findsOneWidget);

    await tester.pumpWidget(
      _interactionTabRouterApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'clickable',
              primaryText: '可点击主句',
              filterKeys: const <String>['all'],
              previewMediaKind: 'text',
              previewText: '可点击预览',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);
    await tester.tap(find.text('可点击预览'));
    await tester.pumpAndSettle();
    expect(find.text('作品页:post_clickable'), findsOneWidget);
  });
}
