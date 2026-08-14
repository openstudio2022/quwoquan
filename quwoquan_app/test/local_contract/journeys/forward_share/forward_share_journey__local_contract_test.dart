import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/profile_presentation_slots.dart'
    show profileQrSharePresenter;
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_sheet.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_template.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_confirm_sheet.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_models.dart';
import 'package:quwoquan_app/runtime/shell/share/forward_share_sheet.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/presentation/my_qr_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/service/chat_service/chat/chat_inbox_view/chat_inbox_view_fixture_builder.dart';
import '../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';

const _qrCard = ProfileQrCardData(
  publicProfileUrl: 'https://mock.quwoquan.local/u/current',
  qrPayload: 'quwoquan://profile/current?qr=mock_current',
  qrTokenId: 'qr_current',
  avatarUrl: '',
  displayName: 'fixture_user_current',
  region: '杭州',
  shareText: 'quwoquan://profile/current?qr=mock_current',
);

Widget _wrap(_ForwardJourneyChatRepository repository) {
  return ProviderScope(
    overrides: [
      ...chatTestRepositoryOverrides(
        conversation: repository.conversation,
        contact: repository.contact,
      ),
      chatMessageCommandWriterProvider.overrideWithValue(repository.writer),
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData.fallback(
          personaId: 'persona_forward',
          ownerUserId: 'fixture_user_current',
          displayName: '转发测试分身',
          avatarUrl: '',
          contextVersion: 1,
        ),
      ),
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
    ],
    child: const CupertinoApp(
      home: SizedBox(
        width: AppSpacing.webPcLoginSurfaceWidth,
        child: MyQrCardView(
          card: _qrCard,
          sharePresenter: profileQrSharePresenter,
        ),
      ),
    ),
  );
}

void main() {
  // spec_ref: specs/feature-tree/chat-conversation/chat-experience-optimization/spec.md#open-002
  testWidgets('转发面板最近会话加载中呈现共享骨架屏', (tester) async {
    final repository = _ForwardJourneyChatRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...chatTestRepositoryOverrides(
            conversation: _SlowForwardConversationRepository(
              repository.conversation,
            ),
            contact: repository.contact,
          ),
          chatMessageCommandWriterProvider.overrideWithValue(
            repository.writer,
          ),
          authSessionControllerProvider.overrideWith(
            _AuthenticatedSession.new,
          ),
        ],
        child: const CupertinoApp(
          home: ForwardShareSheet(
            payload: AppForwardPayload(
              kind: AppForwardSubjectKind.chatMessage,
              title: '骨架断言样本',
              shareText: '骨架断言样本',
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(
      find.byType(AppSkeletonListRows),
      findsOneWidget,
      reason: '最近会话加载中必须使用共享列表骨架',
    );
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
  });

  testWidgets('我的二维码应用内转发旅程发送 card 消息', (tester) async {
    final repository = _ForwardJourneyChatRepository();
    await tester.pumpWidget(_wrap(repository));

    await tester.tap(find.text(ProfileText.editProfileQrShareAction));
    await tester.pumpAndSettle();
    expect(find.text(ChatText.forwardMostContacted), findsOneWidget);

    await tester.tap(find.text(ChatText.forwardActionAppContacts));
    await tester.pumpAndSettle();
    expect(find.text(ChatText.forwardSelectChatTitle), findsOneWidget);

    await tester.tap(find.text('会话 2').first);
    await tester.pumpAndSettle();
    expect(find.text(ChatText.forwardSendToLabel), findsOneWidget);
    expect(
      tester
          .widget<CupertinoTextField>(find.byType(CupertinoTextField).last)
          .maxLines,
      ForwardConfirmSheet.maxMessageLines,
    );

    await tester.enterText(find.byType(CupertinoTextField).last, '发给你看看');
    await tester.tap(find.text(ChatText.send).last);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));

    expect(repository.lastConversationId, 'conv_2');
    expect(repository.lastType, 'card');
    expect(repository.lastContent, '发给你看看');
    expect(repository.lastCard?.kind, MessageCardKind.profileQr);
    expect(repository.lastCard?.attributes, isNotEmpty);
  });

  // spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-002
  testWidgets('会话文本消息经 App 内转发以 text 消息直达并另发附言', (tester) async {
    final repository = _ForwardJourneyChatRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...chatTestRepositoryOverrides(
            conversation: repository.conversation,
            contact: repository.contact,
          ),
          chatMessageCommandWriterProvider.overrideWithValue(
            repository.writer,
          ),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              personaId: 'persona_forward',
              ownerUserId: 'fixture_user_current',
              displayName: '转发测试分身',
              avatarUrl: '',
              contextVersion: 1,
            ),
          ),
          authSessionControllerProvider.overrideWith(
            _AuthenticatedSession.new,
          ),
        ],
        child: CupertinoApp(
          home: Builder(
            builder: (context) => CupertinoButton(
              child: const Text('转发这条消息'),
              onPressed: () => ForwardShareSheet.show(
                context,
                payload: const AppForwardPayload(
                  kind: AppForwardSubjectKind.chatMessage,
                  title: '周六观星聚会集合点',
                  shareText: '周六观星聚会集合点在天文台北门，记得带三脚架。',
                ),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('转发这条消息'));
    await tester.pumpAndSettle();
    expect(find.text(ChatText.forwardMostContacted), findsOneWidget);

    await tester.tap(find.text(ChatText.forwardActionAppContacts));
    await tester.pumpAndSettle();
    await tester.tap(find.text('会话 2').first);
    await tester.pumpAndSettle();
    expect(find.text(ChatText.forwardSendToLabel), findsOneWidget);

    await tester.enterText(find.byType(CupertinoTextField).last, '这条转给你');
    await tester.tap(find.text(ChatText.send).last);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));

    // 转发原文以 text 消息原样发送（不构造 card、端不改写原文）。
    expect(repository.writer.commands, hasLength(2));
    final forwarded = repository.writer.commands.first;
    expect(forwarded.conversationId, 'conv_2');
    expect(forwarded.type, 'text');
    expect(forwarded.content, '周六观星聚会集合点在天文台北门，记得带三脚架。');
    expect(forwarded.card, isNull);
    // 附言另发一条，不与原文拼接。
    final note = repository.writer.commands.last;
    expect(note.type, 'text');
    expect(note.content, '这条转给你');
    expect(note.clientMsgId, endsWith('-note'));
  });

  testWidgets('Post 两段式分享旅程可向群聊发送结构化 card', (tester) async {
    final repository = _ForwardJourneyChatRepository();
    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        ContentPostViewData(
          id: 'post_share_journey',
          type: 'micro',
          identity: 'moment',
          displayFormat: 'note',
          assistantUsePolicy: AssistantUsePolicy.inherit,
          authorId: 'author_share_journey',
          displayName: '旅程作者',
          avatarUrl: '',
          authorRoleLabel: '',
          authorIdentityTags: const <String>[],
          authorVerified: false,
          body: '一条值得分享的记录',
          imageUrls: const <String>[],
          likeCount: 0,
          commentCount: 0,
          shareCount: 0,
          createdAt: DateTime.utc(2026, 7, 14),
        ),
      ),
      enableIdentityTemplate: true,
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...chatTestRepositoryOverrides(
            conversation: repository.conversation,
            contact: repository.contact,
          ),
          chatMessageCommandWriterProvider.overrideWithValue(repository.writer),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              personaId: 'persona_forward',
              ownerUserId: 'fixture_user_current',
              displayName: '转发测试分身',
              avatarUrl: '',
              contextVersion: 1,
            ),
          ),
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
        ],
        child: CupertinoApp(
          home: Builder(
            builder: (context) => CupertinoButton(
              onPressed: () =>
                  ContentShareSheet.show(context, template: template),
              child: const Text('open-post-share'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-post-share'));
    await tester.pumpAndSettle();
    expect(find.text(ChatText.shareInternalTitle), findsOneWidget);
    expect(find.text(ChatText.shareExternalTitle), findsOneWidget);

    await tester.tap(find.text(ChatText.shareTargetGroup));
    await tester.pumpAndSettle();
    await tester.tap(find.text('会话 1').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(CupertinoTextField).last, '群里一起看看');
    await tester.tap(find.text(ChatText.send).last);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));

    expect(repository.lastConversationId, 'conv_1');
    expect(repository.lastType, 'card');
    expect(repository.lastContent, '群里一起看看');
    expect(repository.lastCard?.kind, MessageCardKind.contentPost);
    expect(
      repository.lastCard?.attributes
          .where((attribute) => attribute.name == 'postId')
          .single
          .value,
      'post_share_journey',
    );
  });

  testWidgets('游客选择群聊分享后登录成功续接原目标且关闭策略安全', (tester) async {
    final repository = _ForwardJourneyChatRepository();
    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        ContentPostViewData(
          id: 'post_share_auth_resume',
          type: 'micro',
          identity: 'moment',
          displayFormat: 'note',
          assistantUsePolicy: AssistantUsePolicy.inherit,
          authorId: 'author_share_auth_resume',
          displayName: '续接作者',
          avatarUrl: '',
          authorRoleLabel: '',
          authorIdentityTags: const <String>[],
          authorVerified: false,
          body: '登录后继续分享到群聊',
          imageUrls: const <String>[],
          likeCount: 0,
          commentCount: 0,
          shareCount: 0,
          createdAt: DateTime.utc(2026, 7, 19),
        ),
      ),
      enableIdentityTemplate: true,
    );
    final container = ProviderContainer(
      overrides: [
        ...chatTestRepositoryOverrides(
          conversation: repository.conversation,
          contact: repository.contact,
        ),
        chatMessageCommandWriterProvider.overrideWithValue(repository.writer),
        activePersonaContextProvider.overrideWith(
          (ref) async => ActivePersonaContextViewData.fallback(
            personaId: 'persona_forward',
            ownerUserId: 'fixture_user_current',
            displayName: '转发测试分身',
            avatarUrl: '',
            contextVersion: 1,
          ),
        ),
        authSessionControllerProvider.overrideWith(
          _FlippableForwardSession.new,
        ),
      ],
    );
    addTearDown(container.dispose);
    final router = GoRouter(
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.home,
          builder: (context, state) => CupertinoButton(
            onPressed: () =>
                ContentShareSheet.show(context, template: template),
            child: const Text('open-guest-post-share'),
          ),
        ),
        GoRoute(
          path: AppRoutePaths.loginPathTemplate,
          builder: (context, state) =>
              const SizedBox(key: ValueKey<String>('share-login-sentinel')),
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('open-guest-post-share'));
    await tester.pumpAndSettle();
    await tester.tap(find.text(ChatText.shareTargetGroup));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('share-login-sentinel')),
      findsOneWidget,
    );
    final pending = container.read(authContinuationProvider);
    expect(pending, isA<ShareContentContinuation>());
    expect(
      (pending! as ShareContentContinuation).target,
      ContentShareContinuationTarget.groupChat,
    );
    expect(
      GoRouterState.of(
        tester.element(
          find.byKey(const ValueKey<String>('share-login-sentinel')),
        ),
      ).uri.queryParameters[loginGuestDismissPopQueryParam],
      LoginDismissPolicy.safeFallback.name,
    );

    (container.read(authSessionControllerProvider.notifier)
            as _FlippableForwardSession)
        .loginNow();
    router.pop();
    await tester.pumpAndSettle();

    expect(container.read(authContinuationProvider), isNull);
    expect(find.text('会话 1'), findsOneWidget);
  });
}

class _ForwardJourneyChatRepository {
  _ForwardJourneyChatRepository() {
    final facets = ChatTestFacets();
    conversation = _ForwardJourneyConversationRepository(facets.conversation);
    contact = _ForwardJourneyContactRepository(facets.contact);
  }

  final _ForwardJourneyMessageWriter writer = _ForwardJourneyMessageWriter();
  late final ChatConversationRepository conversation;
  late final ChatContactRepository contact;
  String? get lastConversationId => writer.lastCommand?.conversationId;
  String? get lastType => writer.lastCommand?.type;
  String? get lastContent => writer.lastCommand?.content;
  MessageCard? get lastCard => writer.lastCommand?.card;
}

final class _SlowForwardConversationRepository extends Fake
    implements ChatConversationRepository {
  _SlowForwardConversationRepository(this._delegate);

  final ChatConversationRepository _delegate;

  @override
  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    return _delegate.listConversations(cursor: cursor, limit: limit);
  }
}

final class _ForwardJourneyConversationRepository
    implements ChatConversationRepository {
  const _ForwardJourneyConversationRepository(this._delegate);

  final ChatConversationRepository _delegate;

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) => _delegate.listMessageHome(filter: filter, cursor: cursor, limit: limit);

  @override
  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = 500,
  }) async {
    final base = DateTime.utc(2026, 6, 27, 12);
    return List<ChatInboxViewData>.generate(
      3,
      (index) => chatInboxFixture(
        id: 'conv_$index',
        type: index == 1 ? 'group' : 'direct',
        title: '会话 $index',
        lastMessagePreview: '最近消息 $index',
        lastMessageTime: base.add(Duration(minutes: index)),
      ),
    ).take(limit).toList(growable: false);
  }

  @override
  Future<ChatConversationCreatedViewData> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) => _delegate.createConversation(
    type: type,
    title: title,
    maxGroupSize: maxGroupSize,
    initialMemberIds: initialMemberIds,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<ConversationViewData> getConversation(String conversationId) =>
      _delegate.getConversation(conversationId);

  @override
  Future<void> updateConversationTitle(String conversationId, String title) =>
      _delegate.updateConversationTitle(conversationId, title);

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) => _delegate.updateConversationSettings(
    conversationId: conversationId,
    muted: muted,
    pinned: pinned,
  );

  @override
  Future<List<ChatConversationTimestamp>> getConversationTimestamps() =>
      _delegate.getConversationTimestamps();

  @override
  Future<List<ConversationViewData>> batchGetConversations(List<String> ids) =>
      _delegate.batchGetConversations(ids);
}

final class _ForwardJourneyContactRepository implements ChatContactRepository {
  const _ForwardJourneyContactRepository(this._delegate);

  final ChatContactRepository _delegate;

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = 20,
  }) => _delegate.listContacts(cursor: cursor, limit: limit);

  @override
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 500,
  }) async {
    return <ContactHomeRow>[];
  }

  @override
  Future<List<ChatContactRowViewData>> listGroupCandidates({
    String? conversationId,
    int limit = 100,
  }) => _delegate.listGroupCandidates(
    conversationId: conversationId,
    limit: limit,
  );
}

class _ForwardJourneyMessageWriter implements ChatMessageCommandWriter {
  final List<ChatSendMessageCommand> commands = <ChatSendMessageCommand>[];
  ChatSendMessageCommand? get lastCommand =>
      commands.isEmpty ? null : commands.last;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    commands.add(command);
    return ChatSendMessageResult(
      messageId: 'msg_forward_${commands.length}',
      seq: commands.length,
      timestamp: DateTime.utc(2026, 6, 27, 12),
    );
  }
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'share-journey-token',
      refreshToken: 'share-journey-refresh-token',
      activePersonaId: 'persona_forward',
      ownerId: 'fixture_user_current',
    );
  }
}

class _FlippableForwardSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);

  void loginNow() {
    state = const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'share-resume-token',
      refreshToken: 'share-resume-refresh-token',
      activePersonaId: 'persona_forward',
      ownerId: 'fixture_user_current',
    );
  }
}
