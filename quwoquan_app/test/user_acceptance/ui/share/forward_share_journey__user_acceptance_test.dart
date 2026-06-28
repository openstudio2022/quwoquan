import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_confirm_sheet.dart';
import 'package:quwoquan_app/ui/user/widgets/my_qr_card.dart';

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
      activePersonaContextProvider.overrideWith(
        (ref) async => ActivePersonaContextViewData.fallback(
          subAccountId: 'persona_forward',
          ownerUserId: 'fixture_user_current',
          displayName: '转发测试分身',
          avatarUrl: '',
          personaContextVersion: 'ctx_forward',
        ),
      ),
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
    expect(repository.lastCardPayload?['forwardKind'], 'profileQr');
    expect(repository.lastCardPayload?['extra'], isA<Map<String, Object?>>());
  });
}

class _ForwardJourneyChatRepository extends MockChatRepository {
  String? lastConversationId;
  String? lastType;
  String? lastContent;
  Map<String, dynamic>? lastCardPayload;

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 500,
  }) async {
    final base = DateTime.utc(2026, 6, 27, 12);
    return List<ChatInboxDto>.generate(
      3,
      (index) => ChatInboxDto(
        id: 'conv_$index',
        type: 'direct',
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

  @override
  Future<SendMessageResponse> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    Map<String, dynamic>? media,
    Map<String, dynamic>? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? senderSubAccountId,
    String? personaContextVersion,
    String? senderDisplayNameSnapshot,
    String? senderAvatarUrlSnapshot,
    required String clientMsgId,
  }) async {
    lastConversationId = conversationId;
    lastType = type;
    lastContent = content;
    lastCardPayload = cardPayload;
    return SendMessageResponse(
      id: 'msg_forward',
      seq: 1,
      timestamp: DateTime.utc(2026, 6, 27, 12),
    );
  }
}
