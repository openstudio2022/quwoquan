import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/harness/profile_shell_scroll_utils.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/cloud_services/test_content_comment_facet.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

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

class _InteractionContractRepository
    implements
        ContentProfileInteractionQueryFacet,
        ContentProfileInteractionReadFactAppendFacet {
  const _InteractionContractRepository({
    required this.received,
    required this.sent,
  });

  final List<ProfileInteractionActivityViewData> received;
  final List<ProfileInteractionActivityViewData> sent;

  @override
  Future<ContentProfileInteractionPage> listActivities(
    ContentProfileInteractionPageQuery query, {
    required ContentProfileInteractionDirection direction,
  }) async {
    final filterKey = switch (query.type) {
      ContentProfileInteractionType.like => 'likes',
      ContentProfileInteractionType.comment => 'comments',
      ContentProfileInteractionType.share => 'shares',
    };
    final source = direction == ContentProfileInteractionDirection.received
        ? received
        : sent;
    final items = source
        .where((item) => item.filterKeys.contains(filterKey))
        .take(query.limit)
        .map(_contentActivityFromView)
        .toList(growable: false);
    return ContentProfileInteractionPage(items: items);
  }

  @override
  Future<ContentProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) async {
    return ContentProfileInteractionReadFactAck(
      factId: 'fact-${command.activityId}-${command.state.wireValue}',
      activityId: command.activityId,
      state: command.state.wireValue,
      occurredAt: DateTime.utc(2026, 7, 15),
      replayed: false,
    );
  }
}

/// 记录型 chat 仓库桩：断言内联「私信」真实调用 chat 仓库发送预置感谢私信（T2）。
class _RecordingChatRepository extends MockChatRepository {
  final _RecordingMessageWriter writer = _RecordingMessageWriter();
  int createConversationCalls = 0;
  String? lastConversationType;
  List<String>? lastInitialMemberIds;
  int get sendMessageCalls => writer.sendMessageCalls;
  String? get lastSentConversationId => writer.lastCommand?.conversationId;
  String? get lastSentType => writer.lastCommand?.type;
  String? get lastSentContent => writer.lastCommand?.content;

  @override
  Future<ChatConversationCreatedDto> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) {
    createConversationCalls++;
    lastConversationType = type;
    lastInitialMemberIds = initialMemberIds;
    return super.createConversation(
      type: type,
      title: title,
      maxGroupSize: maxGroupSize,
      initialMemberIds: initialMemberIds,
      idempotencyKey: idempotencyKey,
    );
  }
}

class _RecordingMessageWriter implements ChatMessageCommandWriter {
  int sendMessageCalls = 0;
  ChatSendMessageCommand? lastCommand;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    sendMessageCalls++;
    lastCommand = command;
    return ChatSendMessageResult(
      messageId: 'message-${command.clientMsgId}',
      seq: sendMessageCalls,
      timestamp: DateTime.utc(2026, 7, 15),
    );
  }
}

Widget _interactionTabActionsApp(
  _InteractionContractRepository repository, {
  TestContentCommentFacet? commentFacet,
  _RecordingChatRepository? chatRepository,
}) {
  return ProviderScope(
    overrides: [
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      profileInteractionQueryFacetProvider.overrideWithValue(repository),
      profileInteractionReadFactAppendFacetProvider.overrideWithValue(
        repository,
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
      if (commentFacet != null)
        ...mockContentFacetOverrides(
          MockContentRepository(),
          commentFacet: commentFacet,
        ),
      if (chatRepository != null)
        chatRepositoryCompositionProvider.overrideWithValue(chatRepository),
      if (chatRepository != null)
        chatMessageCommandWriterProvider.overrideWithValue(
          chatRepository.writer,
        ),
      if (chatRepository != null)
        activePersonaContextProvider.overrideWith(
          (ref) async => ActivePersonaContextViewData.fallback(
            subAccountId: 'profile_owner_persona',
            ownerUserId: 'profile_owner',
            displayName: '主页测试分身',
            avatarUrl: '',
            contextVersion: 3,
          ),
        ),
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
  const interactions = _InteractionContractRepository(
    received: <ProfileInteractionActivityViewData>[],
    sent: <ProfileInteractionActivityViewData>[],
  );
  return ProviderScope(
    overrides: [
      ...mockContentFacetOverrides(MockContentRepository()),
      intersectionRepositoryProvider.overrideWithValue(
        AlphaIntersectionRepository(),
      ),
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      authorImpactQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
      profileInteractionQueryFacetProvider.overrideWithValue(interactions),
      profileInteractionReadFactAppendFacetProvider.overrideWithValue(
        interactions,
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
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      profileInteractionQueryFacetProvider.overrideWithValue(repository),
      profileInteractionReadFactAppendFacetProvider.overrideWithValue(
        repository,
      ),
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
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      profileInteractionQueryFacetProvider.overrideWithValue(repository),
      profileInteractionReadFactAppendFacetProvider.overrideWithValue(
        repository,
      ),
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

ContentProfileInteractionActivity _contentActivityFromView(
  ProfileInteractionActivityViewData view,
) {
  final occurredAt =
      view.occurredAt ?? view.createdAt ?? DateTime.utc(2026, 6, 18);
  return ContentProfileInteractionActivity(
    activityId: view.activityId,
    activityType: view.filterKeys.contains('comments')
        ? 'comment'
        : view.filterKeys.contains('shares')
        ? 'share'
        : 'like',
    direction: view.direction,
    commentKind: view.commentKind,
    commentId: view.commentId,
    parentCommentId: view.parentCommentId,
    viewerReaction: view.viewerReaction,
    actorSubAccountId: view.actorSubAccountId,
    actorDisplayName: view.actorDisplayName,
    actorAvatarUrl: view.actorAvatarUrl,
    actorAvatarVersion: view.actorAvatarVersion,
    counterpartSubAccountId: view.counterpartSubAccountId,
    counterpartDisplayName: view.counterpartDisplayName,
    counterpartAvatarUrl: view.counterpartAvatarUrl,
    targetSubAccountId: view.targetSubAccountId,
    targetContentId: view.targetContentId,
    targetContentType: view.targetContentType,
    targetContentSummary: view.targetContentSummary,
    targetKind: view.targetKind,
    targetAvailability: view.targetAvailability,
    targetReplyCount: view.targetReplyCount,
    displaySubAccountId: view.displaySubAccountId,
    displayName: view.displayName,
    displayAvatarUrl: view.displayAvatarUrl,
    displayAvatarVersion: view.displayAvatarVersion,
    displayUserRouteId: view.displayUserRouteId,
    primaryText: view.primaryText,
    contextText: view.contextText,
    previewMediaKind: view.previewMediaKind,
    previewImageUrl: view.previewImageUrl,
    previewText: view.previewText,
    previewUnavailable: view.previewUnavailable,
    previewObjectId: view.previewObjectId,
    previewRouteId: view.previewRouteId,
    outboundShareEventId: view.outboundShareEventId,
    shareText: view.shareText,
    impactPrimaryText: view.impactPrimaryText,
    impactDeepLink: view.impactDeepLink,
    filterKeys: view.filterKeys,
    createdAt: view.createdAt ?? occurredAt,
    occurredAt: occurredAt,
    seenAt: view.seenAt,
    readAt: view.readAt,
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

Future<void> _showInteractionSubTab(
  WidgetTester tester,
  InteractionSubTab subTab,
) async {
  final tab = find.byType(ProfileInteractionTab);
  final container = ProviderScope.containerOf(tester.element(tab));
  container
      .read(profileNotifierProvider('profile_owner').notifier)
      .setInteractionSubTab(subTab);
  await _pumpFrames(tester);
}

Future<void> _tapPreviewSurface(WidgetTester tester, String activityId) async {
  final finder = find.byKey(
    ValueKey<String>('profile-interaction-preview-button-$activityId'),
  );
  final topLeft = tester.getTopLeft(finder);
  await tester.tapAt(topLeft + const Offset(6, 6));
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
        matching: find.text(ProfileText.interactionSubComments),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(
          const ValueKey<String>('profile-interaction-secondary-tabs'),
        ),
        matching: find.text(ProfileText.interactionSubLikes),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: find.byKey(
          const ValueKey<String>('profile-interaction-secondary-tabs'),
        ),
        matching: find.text(ProfileText.interactionSubVisitors),
      ),
      findsNothing,
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
              filterKeys: const <String>['likes'],
            ),
            _interaction(
              id: 'comment',
              primaryText: '契约主句：评论',
              filterKeys: const <String>['comments'],
            ),
            _interaction(
              id: 'share',
              primaryText: '契约主句：转发',
              filterKeys: const <String>['shares'],
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
      ),
    );
    await _pumpFrames(tester);

    expect(find.text('契约主句：点赞'), findsOneWidget);
    expect(find.text('契约主句：评论'), findsNothing);
    expect(find.text('契约主句：转发'), findsNothing);
    expect(find.text('旧字段不应作为主句'), findsNothing);
    expect(find.byIcon(CupertinoIcons.chevron_forward), findsNothing);

    await tester.tap(
      find
          .ancestor(
            of: find.text(ProfileText.interactionSubComments),
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
  });

  testWidgets('赞二级 Tab 不渲染方向开关，避免挤压分类', (tester) async {
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
              filterKeys: const <String>['likes'],
            ),
          ],
          sent: [
            _interaction(
              id: 'sent',
              direction: 'sent',
              primaryText: '发出方向主句',
              filterKeys: const <String>['likes'],
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
              filterKeys: const <String>['likes'],
              previewMediaKind: 'audio',
              previewText: '未知预览文本',
            ),
            _interaction(
              id: 'unavailable',
              primaryText: '失效预览主句',
              filterKeys: const <String>['likes'],
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
      find.text(ProfileText.profileInteractionOriginalUnavailable),
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
              filterKeys: const <String>['likes'],
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
      find.text(ProfileText.profileInteractionPreviewLoadFailed),
      findsOneWidget,
    );
    expect(find.text(FoundationText.retry), findsNothing);
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
              filterKeys: const <String>['likes'],
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
              filterKeys: const <String>['likes'],
              previewMediaKind: 'image',
              previewImageUrl: 'media/content/test/image.jpg',
              previewText: '图片记录',
            ),
            _interaction(
              id: 'video',
              primaryText: '视频记录主句',
              filterKeys: const <String>['likes'],
              previewMediaKind: 'video',
              previewText: '视频记录',
            ),
            _interaction(
              id: 'text',
              primaryText: '文字记录主句',
              filterKeys: const <String>['likes'],
              previewMediaKind: 'text',
              previewText: '文字记录预览',
            ),
            _interaction(
              id: 'article',
              primaryText: '文章记录主句',
              filterKeys: const <String>['comments'],
              targetContentType: 'article',
              previewMediaKind: 'text',
              previewText: '长文预览标题',
            ),
            _interaction(
              id: 'comment-ref',
              primaryText: '评论了你的记录：写得真好',
              filterKeys: const <String>['comments'],
              contextText: '引用评论：写得真好',
              commentKind: 'comment',
              previewMediaKind: 'text',
              previewText: '评论引用原记录',
            ),
            _interaction(
              id: 'reply-ref',
              primaryText: '回复了你：我也喜欢',
              filterKeys: const <String>['comments'],
              contextText: '你说：这组颜色像旧电影',
              commentKind: 'reply',
              previewMediaKind: 'text',
              previewText: '回复引用原记录',
            ),
            _interaction(
              id: 'deleted',
              primaryText: '删除态主句',
              filterKeys: const <String>['comments'],
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
      find.text(ProfileText.profileInteractionPreviewLoadFailed),
      findsWidgets,
    );
    expect(
      find.byKey(
        const ValueKey<String>('profile-interaction-preview-retry-icon'),
      ),
      findsWidgets,
    );
    expect(find.text('文字记录预览'), findsOneWidget);

    await _showInteractionSubTab(tester, InteractionSubTab.comments);

    expect(
      tester.widget<Text>(find.text('长文预览标题')).style?.fontWeight,
      AppTypography.regular,
    );
    expect(find.text('引用评论：写得真好'), findsOneWidget);
    expect(find.text('你说：这组颜色像旧电影'), findsOneWidget);
    expect(
      find.text(ProfileText.profileInteractionOriginalUnavailable),
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
              filterKeys: const <String>['likes'],
            ),
          ],
          sent: [
            _interaction(
              id: 'other-sent',
              primaryText: '他人主页不应展示发出',
              filterKeys: const <String>['likes'],
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
              filterKeys: const <String>['likes'],
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
              filterKeys: const <String>['likes'],
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
              filterKeys: const <String>['likes'],
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
              filterKeys: const <String>['likes'],
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
              filterKeys: const <String>['comments'],
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
    await _showInteractionSubTab(tester, InteractionSubTab.comments);

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
              filterKeys: const <String>['comments'],
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
    await _showInteractionSubTab(tester, InteractionSubTab.comments);

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

    final comments = TestContentCommentFacet(
      items: <ContentCommentListItem>[testCommentItem(id: 'comment_top_1')],
    );
    await tester.pumpWidget(
      _interactionTabActionsApp(
        _InteractionContractRepository(
          received: [
            _interaction(
              id: 'cmt',
              primaryText: '评论了你的记录：写得真好',
              filterKeys: const <String>['comments'],
              commentKind: 'comment',
              commentId: 'comment_top_1',
              previewMediaKind: 'text',
              previewText: '评论引用原记录',
            ),
          ],
          sent: const <ProfileInteractionActivityViewData>[],
        ),
        commentFacet: comments,
      ),
    );
    await _pumpFrames(tester);
    await _showInteractionSubTab(tester, InteractionSubTab.comments);

    final likeKey = const ValueKey<String>('profile-interaction-like-cmt');
    expect(find.byKey(likeKey), findsOneWidget);
    expect(
      find.text(ProfileText.profileInteractionLikeComment),
      findsOneWidget,
    );

    await tester.tap(find.byKey(likeKey));
    await _pumpFrames(tester);

    expect(comments.reactionCalls, 1);
    expect(comments.lastReactionCommand?.commentId, 'comment_top_1');
    expect(
      comments.lastReactionCommand?.reaction,
      ContentCommentReactionValue.like,
    );
    expect(
      find.text(ProfileText.profileInteractionCommentLiked),
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
              filterKeys: const <String>['comments'],
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
    await _showInteractionSubTab(tester, InteractionSubTab.comments);

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
              filterKeys: const <String>['likes'],
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
      ProfileText.profileInteractionThanksLikeMessage,
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
              filterKeys: const <String>['likes'],
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
    expect(find.text(ProfileText.profileInteractionThank), findsOneWidget);

    await tester.tap(find.byKey(thankKey));
    await _pumpFrames(tester);

    expect(
      find.text(ProfileText.profileInteractionThanked),
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
