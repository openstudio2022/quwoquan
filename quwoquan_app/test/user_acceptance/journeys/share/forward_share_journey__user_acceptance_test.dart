import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_confirm_sheet.dart';
import 'package:quwoquan_app/ui/user/widgets/my_qr_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/fixtures/chat/chat_inbox_fixture_builder.dart';

const _qrCard = ProfileQrCardData(
  publicProfileUrl: 'https://mock.quwoquan.local/u/current',
  qrPayload: 'quwoquan://profile/current?qr=mock_current',
  qrTokenId: 'qr_current',
  styleVersion: 'v1',
  avatarUrl: '',
  displayName: 'fixture_user_current',
  region: '杭州',
  shareText: 'quwoquan://profile/current?qr=mock_current',
);

Widget _wrap(_ForwardJourneyChatRepository repository) {
  return ProviderScope(
    overrides: [
      chatRepositoryProvider.overrideWithValue(repository),
      chatMessageCommandWriterProvider.overrideWithValue(repository.writer),
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData.fallback(
          subAccountId: 'persona_forward',
          ownerUserId: 'fixture_user_current',
          displayName: '转发测试分身',
          avatarUrl: '',
          personaContextVersion: 'ctx_forward',
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

    await tester.tap(find.text(UITextConstants.editProfileQrShareAction));
    await tester.pumpAndSettle();
    expect(find.text(UITextConstants.forwardMostContacted), findsOneWidget);

    await tester.tap(find.text(UITextConstants.forwardActionAppContacts));
    await tester.pumpAndSettle();
    expect(find.text(UITextConstants.forwardSelectChatTitle), findsOneWidget);

    await tester.tap(find.text('会话 2').first);
    await tester.pumpAndSettle();
    expect(find.text(UITextConstants.forwardSendToLabel), findsOneWidget);
    expect(
      tester
          .widget<CupertinoTextField>(find.byType(CupertinoTextField).last)
          .maxLines,
      ForwardConfirmSheet.maxMessageLines,
    );

    await tester.enterText(find.byType(CupertinoTextField).last, '发给你看看');
    await tester.tap(find.text(UITextConstants.send).last);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));

    expect(repository.lastConversationId, 'conv_2');
    expect(repository.lastType, 'card');
    expect(repository.lastContent, '发给你看看');
    expect(repository.lastCard?.kind, 'profileQr');
    expect(repository.lastCard?.attributes, isNotEmpty);
  });

  testWidgets('Post 两段式分享旅程可向群聊发送结构化 card', (tester) async {
    final repository = _ForwardJourneyChatRepository();
    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        MicroPostDto(
          id: 'post_share_journey',
          type: 'micro',
          identity: 'moment',
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
          chatRepositoryProvider.overrideWithValue(repository),
          chatMessageCommandWriterProvider.overrideWithValue(repository.writer),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'persona_forward',
              ownerUserId: 'fixture_user_current',
              displayName: '转发测试分身',
              avatarUrl: '',
              personaContextVersion: 'ctx_forward',
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
    expect(find.text(UITextConstants.shareInternalTitle), findsOneWidget);
    expect(find.text(UITextConstants.shareExternalTitle), findsOneWidget);

    await tester.tap(find.text(UITextConstants.shareTargetGroup));
    await tester.pumpAndSettle();
    await tester.tap(find.text('会话 1').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(CupertinoTextField).last, '群里一起看看');
    await tester.tap(find.text(UITextConstants.send).last);
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));

    expect(repository.lastConversationId, 'conv_1');
    expect(repository.lastType, 'card');
    expect(repository.lastContent, '群里一起看看');
    expect(repository.lastCard?.kind, 'post');
    expect(
      repository.lastCard?.attributes
          .where((attribute) => attribute.name == 'postId')
          .single
          .value,
      'post_share_journey',
    );
  });
}

class _ForwardJourneyChatRepository extends MockChatRepository {
  final _ForwardJourneyMessageWriter writer = _ForwardJourneyMessageWriter();
  String? get lastConversationId => writer.lastCommand?.conversationId;
  String? get lastType => writer.lastCommand?.type;
  String? get lastContent => writer.lastCommand?.content;
  ChatMessageCardCommand? get lastCard => writer.lastCommand?.card;

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 500,
  }) async {
    final base = DateTime.utc(2026, 6, 27, 12);
    return List<ChatInboxDto>.generate(
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
  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 500,
  }) async {
    return <ContactHomeRowDto>[];
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
      activeSubAccountId: 'persona_forward',
      ownerId: 'fixture_user_current',
    );
  }
}
