import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_view_data.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_confirm_sheet.dart';
import 'package:quwoquan_app/ui/user/widgets/my_qr_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/fixtures/chat/chat_inbox_fixture_builder.dart';

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
      chatRepositoryCompositionProvider.overrideWithValue(repository),
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
        child: MyQrCardView(card: _qrCard),
      ),
    ),
  );
}

void main() {
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

  testWidgets('Post 两段式分享旅程可向群聊发送结构化 card', (tester) async {
    final repository = _ForwardJourneyChatRepository();
    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        ContentPostViewData(
          id: 'post_share_journey',
          type: 'micro',
          identity: 'moment',
          displayFormat: 'note',
          assistantUsePolicy: 'inherit',
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
          chatRepositoryCompositionProvider.overrideWithValue(repository),
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
          assistantUsePolicy: 'inherit',
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
        chatRepositoryCompositionProvider.overrideWithValue(repository),
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

class _ForwardJourneyChatRepository extends MockChatRepository {
  final _ForwardJourneyMessageWriter writer = _ForwardJourneyMessageWriter();
  String? get lastConversationId => writer.lastCommand?.conversationId;
  String? get lastType => writer.lastCommand?.type;
  String? get lastContent => writer.lastCommand?.content;
  MessageCard? get lastCard => writer.lastCommand?.card;

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
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 500,
  }) async {
    return <ContactHomeRow>[];
  }
}

class _ForwardJourneyMessageWriter implements ChatMessageCommandWriter {
  ChatSendMessageCommand? lastCommand;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    lastCommand = command;
    return ChatSendMessageResult(
      messageId: 'msg_forward',
      seq: 1,
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
