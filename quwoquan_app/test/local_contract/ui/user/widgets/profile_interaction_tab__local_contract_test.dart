import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

import '../../../../support/harness/profile_shell_scroll_utils.dart';

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

/// 记录型 content 仓库桩：断言内联「赞 / 回复评论」真实调用 content 仓库（T2）。
class _RecordingContentRepository extends MockContentRepository {
  int reactCalls = 0;
  String? lastReactCommentId;
  String? lastReactReaction;
  int createCommentCalls = 0;
  String? lastCreatePostId;
  String? lastCreateContent;
  String? lastCreateReplyToCommentId;

  @override
  Future<CommentDto> reactToComment({
    required String commentId,
    required String reaction,
  }) {
    reactCalls++;
    lastReactCommentId = commentId;
    lastReactReaction = reaction;
    return super.reactToComment(commentId: commentId, reaction: reaction);
  }

  @override
  Future<CommentDto> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
    List<String> attachmentMediaIds = const <String>[],
    List<Map<String, dynamic>> mentions = const <Map<String, dynamic>>[],
    String? subAccountId,
    String? personaContextVersion,
  }) {
    createCommentCalls++;
    lastCreatePostId = postId;
    lastCreateContent = content;
    lastCreateReplyToCommentId = replyToCommentId;
    return super.createComment(
      postId: postId,
      content: content,
      replyToCommentId: replyToCommentId,
      attachmentMediaIds: attachmentMediaIds,
      mentions: mentions,
      subAccountId: subAccountId,
      personaContextVersion: personaContextVersion,
    );
  }
}

/// 记录型 chat 仓库桩：断言内联「私信」真实调用 chat 仓库发送预置感谢私信（T2）。
class _RecordingChatRepository extends MockChatRepository {
  int createConversationCalls = 0;
  String? lastConversationType;
  List<String>? lastInitialMemberIds;
  int sendMessageCalls = 0;
  String? lastSentConversationId;
  String? lastSentType;
  String? lastSentContent;

  @override
  Future<ChatConversationCreatedDto> createConversation({
    required String type,
    String? title,
    String? circleId,
    String? circleGroupId,
    String? originType,
    String? bindingType,
    String? lifecyclePolicy,
    int? maxGroupSize,
    List<String>? initialMemberIds,
  }) {
    createConversationCalls++;
    lastConversationType = type;
    lastInitialMemberIds = initialMemberIds;
    return super.createConversation(
      type: type,
      title: title,
      circleId: circleId,
      circleGroupId: circleGroupId,
      originType: originType,
      bindingType: bindingType,
      lifecyclePolicy: lifecyclePolicy,
      maxGroupSize: maxGroupSize,
      initialMemberIds: initialMemberIds,
    );
  }

  @override
  Future<SendMessageResponse> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    CloudJsonMap? media,
    CloudJsonMap? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? senderSubAccountId,
    String? personaContextVersion,
    String? senderDisplayNameSnapshot,
    String? senderAvatarUrlSnapshot,
    required String clientMsgId,
  }) {
    sendMessageCalls++;
    lastSentConversationId = conversationId;
    lastSentType = type;
    lastSentContent = content;
    return super.sendMessage(
      conversationId: conversationId,
      type: type,
      content: content,
      mediaUrl: mediaUrl,
      media: media,
      cardPayload: cardPayload,
      replyToMessageId: replyToMessageId,
      mentions: mentions,
      senderSubAccountId: senderSubAccountId,
      personaContextVersion: personaContextVersion,
      senderDisplayNameSnapshot: senderDisplayNameSnapshot,
      senderAvatarUrlSnapshot: senderAvatarUrlSnapshot,
      clientMsgId: clientMsgId,
    );
  }
}

Widget _interactionTabActionsApp(
  _InteractionContractRepository repository, {
  _RecordingContentRepository? contentRepository,
  _RecordingChatRepository? chatRepository,
}) {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(repository),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
      if (contentRepository != null)
        contentRepositoryProvider.overrideWithValue(contentRepository),
      if (chatRepository != null)
        chatRepositoryProvider.overrideWithValue(chatRepository),
    ],
    child: MaterialApp(
      theme: ThemeData.light(),
      home: const SizedBox(
        height: 720,
        child: ProfileInteractionTab(
          mode: ProfileMode.mine,
          userId: 'profile_owner',
          isDark: false,
        ),
      ),
    ),
  );
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

Widget _interactionTabRouterApp(
  _InteractionContractRepository repository, {
  CommentObservability? observability,
}) {
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
        builder: (context, state) => Text(
          '作品页:${state.pathParameters['workId'] ?? ''};'
          'filter:${state.uri.queryParameters['filter'] ?? ''};'
          'openComments:${state.uri.queryParameters['openComments'] ?? ''};'
          'entrySource:${state.uri.queryParameters['commentEntrySource'] ?? ''};'
          'targetCommentId:${state.uri.queryParameters['targetCommentId'] ?? ''};'
          'targetParentCommentId:${state.uri.queryParameters['targetParentCommentId'] ?? ''};'
          'targetReplyId:${state.uri.queryParameters['targetReplyId'] ?? ''};'
          'replyToCommentId:${state.uri.queryParameters['replyToCommentId'] ?? ''}',
        ),
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(repository),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
      if (observability != null)
        commentObservabilityProvider.overrideWithValue(observability),
    ],
    child: MaterialApp.router(theme: ThemeData.light(), routerConfig: router),
  );
}

class _RecordedCommentAction {
  _RecordedCommentAction(this.eventName, this.properties);

  final String eventName;
  final Map<String, Object?> properties;
}

/// 记录型评论可观测桩：断言互动入口是否真实发射深链埋点（T2）。
class _RecordingCommentObservability extends CommentObservability {
  _RecordingCommentObservability()
    : super(analytics: AnalyticsService.forTesting());

  final List<_RecordedCommentAction> actions = <_RecordedCommentAction>[];

  @override
  void trackAction({
    required String eventName,
    required String postId,
    String? commentId,
    String? entrySource,
    String? surfaceMode,
    String? sortMode,
    int? replyDepth,
    int? latencyMs,
    String? failureKind,
    int? attachmentCount,
    int? mentionCount,
    int? itemCount,
    String? reaction,
    String? result,
  }) {
    actions.add(
      _RecordedCommentAction(eventName, <String, Object?>{
        'postId': postId,
        'commentId': ?commentId,
        'entrySource': ?entrySource,
        'result': ?result,
      }),
    );
  }

  _RecordedCommentAction? firstAction(String eventName) {
    for (final action in actions) {
      if (action.eventName == eventName) return action;
    }
    return null;
  }
}

ProfileInteractionActivityViewData _interaction({
  required String id,
  required String primaryText,
  required List<String> filterKeys,
  String direction = 'received',
  String displaySubAccountId = 'u_display',
  String displayName = '林清越',
  String displayAvatarUrl = '',
  String targetContentType = 'contract_target',
  String previewMediaKind = 'text',
  String previewImageUrl = '',
  String previewText = '街角光影',
  String previewObjectId = '',
  String previewRouteId = AppLinkTemplates.postRouteId,
  String contextText = '',
  String commentKind = 'none',
  String commentId = '',
  String parentCommentId = '',
  bool previewUnavailable = false,
}) {
  return ProfileInteractionActivityViewData(
    activityId: id,
    activityType: 'contract_activity',
    direction: direction,
    commentKind: commentKind,
    commentId: commentId,
    parentCommentId: parentCommentId,
    actorSubAccountId: 'u_actor',
    actorDisplayName: '互动用户',
    actorAvatarUrl: '',
    targetSubAccountId: 'profile_owner',
    targetContentId: 'post_$id',
    targetContentType: targetContentType,
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
    previewObjectId: previewObjectId.isEmpty ? 'post_$id' : previewObjectId,
    previewRouteId: previewUnavailable ? '' : previewRouteId,
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

Future<void> _tapPreviewSurface(WidgetTester tester, String activityId) async {
  final finder = find.byKey(
    ValueKey<String>('profile-interaction-preview-button-$activityId'),
  );
  final topLeft = tester.getTopLeft(finder);
  await tester.tapAt(topLeft + const Offset(6, 6));
}

Future<void> _tapInteractionSubTab(WidgetTester tester, String label) async {
  final tabBar = find.byKey(
    const ValueKey<String>('profile-interaction-secondary-tabs'),
  );
  if (label == UITextConstants.interactionSubViews) {
    await tester.drag(tabBar, const Offset(-160, 0));
    await _pumpFrames(tester, count: 4);
  }
  await tester.tap(
    find
        .ancestor(of: find.text(label), matching: find.byType(CupertinoButton))
        .first,
  );
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
    expect(
      find.descendant(
        of: find.byKey(
          const ValueKey<String>('profile-interaction-secondary-tabs'),
        ),
        matching: find.text(UITextConstants.interactionSubVisitors),
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
            _interaction(
              id: 'view',
              primaryText: '契约主句：浏览',
              filterKeys: const <String>['all', 'views'],
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
    expect(find.text('契约主句：浏览'), findsOneWidget);
    expect(find.text('旧字段不应作为主句'), findsNothing);
    expect(find.byIcon(CupertinoIcons.chevron_forward), findsNothing);

    await tester.tap(
      find
          .ancestor(
            of: find.text(UITextConstants.interactionSubComments),
            matching: find.byType(CupertinoButton),
          )
          .first,
    );
    await _pumpFrames(tester);

    expect(find.text('契约主句：评论'), findsOneWidget);
    expect(find.text('契约主句：点赞'), findsNothing);
    expect(find.text('契约主句：转发'), findsNothing);
    expect(
      tester.widget<Text>(find.text('林清越')).style?.fontWeight,
      AppTypography.regular,
    );
    expect(
      tester.widget<Text>(find.text('契约主句：评论')).style?.fontWeight,
      AppTypography.regular,
    );

    await tester.tap(
      find
          .ancestor(
            of: find.text(UITextConstants.interactionSubShares),
            matching: find.byType(CupertinoButton),
          )
          .first,
    );
    await _pumpFrames(tester);

    expect(find.text('契约主句：转发'), findsOneWidget);
    expect(find.text('契约主句：评论'), findsNothing);

    await _tapInteractionSubTab(tester, UITextConstants.interactionSubVisitors);
    await _pumpFrames(tester);

    expect(
      find.text(UITextConstants.profileInteractionViewReceivedText),
      findsOneWidget,
    );
    expect(find.text('契约主句：转发'), findsNothing);
  });

  testWidgets('互动二级 Tab 不渲染方向开关，避免挤压二级分类', (tester) async {
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
    expect(
      find.byKey(
        const ValueKey<String>('profile-interaction-direction-switch'),
      ),
      findsNothing,
    );
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

  testWidgets('图片预览加载失败显示原因并提供图标重试', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      _interactionTabApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'broken-image',
              primaryText: '损坏图片主句',
              filterKeys: const <String>['all'],
              targetContentType: 'image',
              previewMediaKind: 'image',
              previewImageUrl: 'https://invalid.invalid/missing.jpg',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    expect(
      find.byKey(const ValueKey<String>('profile-interaction-preview-loading')),
      findsWidgets,
    );

    await _pumpFrames(tester, count: 30);
    expect(
      find.byKey(const ValueKey<String>('profile-interaction-preview-error')),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.profileInteractionPreviewLoadFailed),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.retry), findsNothing);
    expect(
      find.byKey(
        const ValueKey<String>('profile-interaction-preview-retry-icon'),
      ),
      findsOneWidget,
    );
    final previewSize = tester.getSize(
      find.byKey(
        const ValueKey<String>(
          'profile-interaction-preview-button-broken-image',
        ),
      ),
    );
    expect(previewSize.width / previewSize.height, closeTo(3 / 2, 0.01));

    await tester.tap(
      find.byKey(const ValueKey<String>('profile-interaction-preview-retry')),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey<String>('profile-interaction-preview-loading')),
      findsWidgets,
    );
  });

  testWidgets('视频无封面或封面失败时不显示播放按钮', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      _interactionTabApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'video-without-cover',
              primaryText: '无封面视频主句',
              filterKeys: const <String>['all'],
              targetContentType: 'video',
              previewMediaKind: 'video',
              previewImageUrl: '',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('profile-interaction-preview-error')),
      findsOneWidget,
    );
    expect(find.byIcon(CupertinoIcons.play_circle_fill), findsNothing);
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
              id: 'article',
              primaryText: '文章记录主句',
              filterKeys: const <String>['all', 'comments'],
              targetContentType: 'article',
              previewMediaKind: 'text',
              previewText: '长文预览标题',
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
    expect(
      find.text(UITextConstants.profileInteractionPreviewLoadFailed),
      findsWidgets,
    );
    expect(
      find.byKey(
        const ValueKey<String>('profile-interaction-preview-retry-icon'),
      ),
      findsWidgets,
    );
    expect(find.text('文字记录预览'), findsOneWidget);
    expect(
      tester.widget<Text>(find.text('长文预览标题')).style?.fontWeight,
      AppTypography.regular,
    );
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
      find.byKey(
        const ValueKey<String>('profile-interaction-direction-switch'),
      ),
      findsNothing,
    );
    expect(find.text('他人主页收到主句'), findsOneWidget);
    expect(find.text('他人主页不应展示发出'), findsNothing);
  });

  testWidgets('预览点击使用生成路由 helper 并按内容类型传 filter', (tester) async {
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
              targetContentType: 'article',
              previewMediaKind: 'text',
              previewText: '可点击长文预览',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);
    await _tapPreviewSurface(tester, 'clickable');
    await tester.pumpAndSettle();
    expect(
      find.text(
        '作品页:post_clickable;filter:article;openComments:;'
        'entrySource:;targetCommentId:;targetParentCommentId:;targetReplyId:;'
        'replyToCommentId:',
      ),
      findsOneWidget,
    );

    await tester.pumpWidget(
      _interactionTabRouterApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'video-clickable',
              primaryText: '可点击视频主句',
              filterKeys: const <String>['all'],
              targetContentType: 'video',
              previewMediaKind: 'video',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);
    await _tapPreviewSurface(tester, 'video-clickable');
    await tester.pumpAndSettle();
    expect(
      find.text(
        '作品页:post_video-clickable;filter:video;openComments:;'
        'entrySource:;targetCommentId:;targetParentCommentId:;targetReplyId:;'
        'replyToCommentId:',
      ),
      findsOneWidget,
    );

    await tester.pumpWidget(
      _interactionTabRouterApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'image-clickable',
              primaryText: '可点击图片主句',
              filterKeys: const <String>['all'],
              targetContentType: 'image',
              previewMediaKind: 'image',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);
    await _tapPreviewSurface(tester, 'image-clickable');
    await tester.pumpAndSettle();
    expect(
      find.text(
        '作品页:post_image-clickable;filter:image;openComments:;'
        'entrySource:;targetCommentId:;targetParentCommentId:;targetReplyId:;'
        'replyToCommentId:',
      ),
      findsOneWidget,
    );
  });

  testWidgets('一级评论互动深链携带 targetCommentId 精确定位（openComments=true）', (
    tester,
  ) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final recorder = _RecordingCommentObservability();
    await tester.pumpWidget(
      _interactionTabRouterApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'comment-deeplink',
              primaryText: '评论了你的记录：写得真好',
              filterKeys: const <String>['all', 'comments'],
              commentKind: 'comment',
              commentId: 'comment_top_1',
              targetContentType: 'image',
              previewMediaKind: 'text',
              previewText: '评论引用原记录',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
        observability: recorder,
      ),
    );
    await _pumpFrames(tester);

    await _tapPreviewSurface(tester, 'comment-deeplink');
    await tester.pumpAndSettle();
    expect(
      find.text(
        '作品页:post_comment-deeplink;filter:image;openComments:true;'
        'entrySource:profile-interaction;targetCommentId:comment_top_1;'
        'targetParentCommentId:;targetReplyId:;replyToCommentId:',
      ),
      findsOneWidget,
    );
    // 互动入口深链埋点真实发射：entrySource=profile-interaction, result=initiated, 带 commentId。
    final entry = recorder.firstAction(CommentEventNames.deeplinkOpened);
    expect(entry, isNotNull);
    expect(entry!.properties['entrySource'], equals('profile-interaction'));
    expect(entry.properties['result'], equals('initiated'));
    expect(entry.properties['postId'], equals('post_comment-deeplink'));
    expect(entry.properties['commentId'], equals('comment_top_1'));
  });

  testWidgets('回复类互动深链携带 targetParentCommentId/targetReplyId 高亮父评论行', (
    tester,
  ) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final recorder = _RecordingCommentObservability();
    await tester.pumpWidget(
      _interactionTabRouterApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'reply-deeplink',
              primaryText: '回复了你：完全同意',
              filterKeys: const <String>['all', 'comments'],
              commentKind: 'reply',
              commentId: 'comment_reply_9',
              parentCommentId: 'comment_top_1',
              targetContentType: 'image',
              previewMediaKind: 'text',
              previewText: '回复引用原记录',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
        observability: recorder,
      ),
    );
    await _pumpFrames(tester);

    await _tapPreviewSurface(tester, 'reply-deeplink');
    await tester.pumpAndSettle();
    expect(
      find.text(
        '作品页:post_reply-deeplink;filter:image;openComments:true;'
        'entrySource:profile-interaction;targetCommentId:;'
        'targetParentCommentId:comment_top_1;targetReplyId:comment_reply_9;'
        'replyToCommentId:',
      ),
      findsOneWidget,
    );
    final entry = recorder.firstAction(CommentEventNames.deeplinkOpened);
    expect(entry, isNotNull);
    expect(entry!.properties['commentId'], equals('comment_reply_9'));
  });

  testWidgets('评论类活动「赞」乐观切换已赞态并调用 reactToComment', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final content = _RecordingContentRepository();
    await tester.pumpWidget(
      _interactionTabActionsApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'cmt',
              primaryText: '评论了你的记录：写得真好',
              filterKeys: const <String>['all', 'comments'],
              commentKind: 'comment',
              commentId: 'comment_top_1',
              previewMediaKind: 'text',
              previewText: '评论引用原记录',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
        contentRepository: content,
      ),
    );
    await _pumpFrames(tester);

    final likeKey = const ValueKey<String>('profile-interaction-like-cmt');
    expect(find.byKey(likeKey), findsOneWidget);
    expect(
      find.text(UITextConstants.profileInteractionLikeComment),
      findsOneWidget,
    );

    await tester.tap(find.byKey(likeKey));
    await _pumpFrames(tester);

    expect(content.reactCalls, 1);
    expect(content.lastReactCommentId, 'comment_top_1');
    expect(content.lastReactReaction, 'like');
    expect(
      find.text(UITextConstants.profileInteractionCommentLiked),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(likeKey),
        matching: find.byIcon(CupertinoIcons.heart_fill),
      ),
      findsOneWidget,
    );
  });

  testWidgets('评论类活动「回复评论」直接进入评论详情并携带 replyToCommentId', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      _interactionTabRouterApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'cmt',
              primaryText: '评论了你的记录：写得真好',
              filterKeys: const <String>['all', 'comments'],
              commentKind: 'comment',
              commentId: 'comment_top_1',
              previewObjectId: 'post_target_9',
              previewMediaKind: 'text',
              previewText: '评论引用原记录',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);

    final replyChipKey = const ValueKey<String>(
      'profile-interaction-reply-cmt',
    );
    await tester.tap(find.byKey(replyChipKey));
    await tester.pumpAndSettle();

    expect(
      find.text(
        '作品页:post_target_9;filter:image;openComments:true;'
        'entrySource:profile-interaction;targetCommentId:comment_top_1;'
        'targetParentCommentId:;targetReplyId:;replyToCommentId:comment_top_1',
      ),
      findsOneWidget,
    );
  });

  testWidgets('点赞类活动「私信」通过 chat 仓库发送预置感谢私信', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(AppToast.dismiss);

    final chat = _RecordingChatRepository();
    await tester.pumpWidget(
      _interactionTabActionsApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'like',
              primaryText: '赞了你的记录',
              filterKeys: const <String>['all', 'likes'],
              displaySubAccountId: 'u_liker',
              previewMediaKind: 'image',
              previewImageUrl: 'media/content/test/image.jpg',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
        chatRepository: chat,
      ),
    );
    await _pumpFrames(tester);

    final dmKey = const ValueKey<String>('profile-interaction-dm-like');
    expect(find.byKey(dmKey), findsOneWidget);

    await tester.tap(find.byKey(dmKey));
    await _pumpFrames(tester);

    expect(chat.createConversationCalls, 1);
    expect(chat.lastConversationType, 'direct');
    expect(chat.lastInitialMemberIds, equals(<String>['u_liker']));
    expect(chat.sendMessageCalls, 1);
    expect(chat.lastSentType, 'text');
    expect(
      chat.lastSentContent,
      UITextConstants.profileInteractionThanksLikeMessage,
    );
    expect(
      chat.lastSentConversationId,
      equals(chat.lastSentConversationId?.trim()),
    );
    expect((chat.lastSentConversationId ?? '').isNotEmpty, isTrue);
    AppToast.dismiss();
  });

  testWidgets('点赞类活动「谢谢」切换为已感谢确认态（不可重复）', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(AppToast.dismiss);

    await tester.pumpWidget(
      _interactionTabActionsApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'like',
              primaryText: '赞了你的记录',
              filterKeys: const <String>['all', 'likes'],
              displaySubAccountId: 'u_liker',
              previewMediaKind: 'image',
              previewImageUrl: 'media/content/test/image.jpg',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);

    final thankKey = const ValueKey<String>('profile-interaction-thank-like');
    expect(find.byKey(thankKey), findsOneWidget);
    expect(find.text(UITextConstants.profileInteractionThank), findsOneWidget);

    await tester.tap(find.byKey(thankKey));
    await _pumpFrames(tester);

    expect(
      find.text(UITextConstants.profileInteractionThanked),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(thankKey),
        matching: find.byIcon(CupertinoIcons.heart_fill),
      ),
      findsOneWidget,
    );
    AppToast.dismiss();
  });
}
