import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/ui/share/forward_external_share_service.dart';
import 'package:quwoquan_app/ui/share/forward_share_models.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_confirm_sheet.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_recipient_widgets.dart';
import 'package:quwoquan_app/ui/share/widgets/forward_share_sheet.dart';

const _payload = AppForwardPayload(
  kind: AppForwardSubjectKind.profileQr,
  title: 'fixture_user_current 的二维码',
  subtitle: '北京',
  deeplink: 'quwoquan://profile/current',
  shareText: 'quwoquan://profile/current',
);

Widget _wrap({
  required Widget child,
  required _ForwardSheetChatRepository repository,
  ForwardExternalShareService? externalShareService,
}) {
  return ProviderScope(
    overrides: [
      chatRepositoryProvider.overrideWithValue(repository),
      if (externalShareService != null)
        forwardExternalShareServiceProvider.overrideWithValue(
          externalShareService,
        ),
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
    child: CupertinoApp(home: child),
  );
}

void main() {
  test('AppForwardPayload 对所有转发对象类型保持同一卡片 payload 契约', () {
    for (final kind in AppForwardSubjectKind.values) {
      final payload = AppForwardPayload(
        kind: kind,
        title: '转发对象 ${kind.name}',
        subtitle: '统一转发预览',
        thumbnailUrl: 'media/avatar/s/archived-avatar/user/${kind.name}.png',
        deeplink: 'quwoquan://${kind.name}/target',
        landingUrl: 'https://mock.quwoquan.local/${kind.name}/target',
        shareText: '分享 ${kind.name}',
        extra: <String, Object?>{'source': kind.name},
      );

      final cardPayload = payload.toCardPayload(message: '请看看');

      expect(cardPayload['forwardKind'], kind.name);
      expect(cardPayload['title'], payload.title);
      expect(cardPayload['subtitle'], payload.subtitle);
      expect(cardPayload['thumbnailUrl'], payload.thumbnailUrl);
      expect(cardPayload['deeplink'], payload.deeplink);
      expect(cardPayload['landingUrl'], payload.landingUrl);
      expect(cardPayload['shareText'], payload.shareText);
      expect(cardPayload['message'], '请看看');
      expect(cardPayload['extra'], <String, Object?>{'source': kind.name});
    }
  });

  testWidgets('转发底部面板只展示最近聊天与三个目标动作', (tester) async {
    final repository = _ForwardSheetChatRepository();
    await tester.pumpWidget(
      _wrap(
        repository: repository,
        child: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('open'),
            onPressed: () => ForwardShareSheet.show(context, payload: _payload),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.forwardMostContacted), findsOneWidget);
    final title = tester.widget<Text>(
      find.text(UITextConstants.forwardMostContacted),
    );
    expect(title.style?.fontSize, AppTypography.iosTitle3);
    final surface = tester.widget<AppBottomModalSurface>(
      find.byType(AppBottomModalSurface),
    );
    expect(surface.showHandle, isFalse);
    expect(
      surface.contentPadding,
      EdgeInsets.fromLTRB(
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
        SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
      ),
    );
    expect(find.byType(ForwardRecentRecipientItem), findsNWidgets(10));
    expect(find.text(UITextConstants.forwardActionAppContacts), findsOneWidget);
    expect(
      find.text(UITextConstants.forwardActionWechatFriend),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.forwardActionWechatMoments),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.editProfileQrSaveAction), findsNothing);
    expect(find.text(UITextConstants.editProfileQrScanAction), findsNothing);
    expect(find.text(UITextConstants.cancel), findsOneWidget);
  });

  testWidgets('微信好友和朋友圈入口携带外部转发目标语义', (tester) async {
    final repository = _ForwardSheetChatRepository();
    final externalShareService = _RecordingExternalShareService();
    await tester.pumpWidget(
      _wrap(
        repository: repository,
        externalShareService: externalShareService,
        child: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('open'),
            onPressed: () => ForwardShareSheet.show(context, payload: _payload),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.text(UITextConstants.forwardActionWechatFriend));
    await tester.pump();
    await tester.pump(const Duration(seconds: 4));
    expect(externalShareService.targets, <ForwardExternalShareTarget>[
      ForwardExternalShareTarget.wechatFriend,
    ]);
    expect(externalShareService.payloads.single.title, _payload.title);

    await tester.tap(find.text(UITextConstants.forwardActionWechatMoments));
    await tester.pump();
    await tester.pump(const Duration(seconds: 4));
    expect(externalShareService.targets, <ForwardExternalShareTarget>[
      ForwardExternalShareTarget.wechatFriend,
      ForwardExternalShareTarget.wechatMoments,
    ]);
  });

  test('外部微信分享无原生 SDK 时显式降级到系统分享', () async {
    final gateway = _RecordingSystemShareGateway();
    final service = SharePlusForwardExternalShareService(
      capabilities: CapabilityProfile.mobile,
      systemShareGateway: gateway,
    );

    final result = await service.share(
      payload: _payload,
      target: ForwardExternalShareTarget.wechatFriend,
    );

    expect(result.target, ForwardExternalShareTarget.wechatFriend);
    expect(result.delivery, ForwardExternalShareDelivery.systemShareFallback);
    expect(gateway.texts, <String>[_payload.shareText]);
    expect(gateway.subjects, <String>[_payload.title]);
  });

  test('外部微信分享原生投递成功时不再打开系统分享', () async {
    final gateway = _RecordingSystemShareGateway();
    final wechatGateway = _RecordingWechatShareGateway(delivered: true);
    final service = SharePlusForwardExternalShareService(
      capabilities: CapabilityProfile.mobile.copyWith(
        wechatTargetedShare: true,
      ),
      systemShareGateway: gateway,
      wechatShareGateway: wechatGateway,
    );

    final result = await service.share(
      payload: _payload,
      target: ForwardExternalShareTarget.wechatMoments,
    );

    expect(result.delivery, ForwardExternalShareDelivery.targetedWechat);
    expect(wechatGateway.targets, <ForwardExternalShareTarget>[
      ForwardExternalShareTarget.wechatMoments,
    ]);
    expect(gateway.texts, isEmpty);
  });

  test('外部微信分享原生投递失败时回落系统分享', () async {
    final gateway = _RecordingSystemShareGateway();
    final wechatGateway = _RecordingWechatShareGateway(delivered: false);
    final service = SharePlusForwardExternalShareService(
      capabilities: CapabilityProfile.mobile.copyWith(
        wechatTargetedShare: true,
      ),
      systemShareGateway: gateway,
      wechatShareGateway: wechatGateway,
    );

    final result = await service.share(
      payload: _payload,
      target: ForwardExternalShareTarget.wechatFriend,
    );

    expect(result.delivery, ForwardExternalShareDelivery.systemShareFallback);
    expect(wechatGateway.targets, <ForwardExternalShareTarget>[
      ForwardExternalShareTarget.wechatFriend,
    ]);
    expect(gateway.texts, <String>[_payload.shareText]);
  });

  test('外部微信分享在无系统分享能力的平台返回不可用且不调用分享网关', () async {
    final gateway = _RecordingSystemShareGateway();
    final service = SharePlusForwardExternalShareService(
      capabilities: CapabilityProfile.ohos,
      systemShareGateway: gateway,
    );

    final result = await service.share(
      payload: _payload,
      target: ForwardExternalShareTarget.wechatMoments,
    );

    expect(result.target, ForwardExternalShareTarget.wechatMoments);
    expect(result.delivery, ForwardExternalShareDelivery.unavailable);
    expect(gateway.texts, isEmpty);
  });

  testWidgets('发送给联系人入口打开统一选择聊天页并过滤圈子行', (tester) async {
    final repository = _ForwardSheetChatRepository();
    await tester.pumpWidget(
      _wrap(
        repository: repository,
        child: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('open'),
            onPressed: () => ForwardShareSheet.show(context, payload: _payload),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.forwardActionAppContacts));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.forwardSelectChatTitle), findsOneWidget);
    expect(find.text(UITextConstants.forwardRecentForwards), findsNothing);
    expect(find.byType(ForwardRecentRecipientItem), findsNothing);
    expect(find.text(UITextConstants.forwardRecentChats), findsOneWidget);
    expect(find.byType(ForwardRecipientListCard), findsWidgets);
    expect(
      tester.getTopLeft(find.text('最近 11')).dy,
      lessThan(tester.getTopLeft(find.text('最近 10')).dy),
    );
    await tester.drag(
      find.byType(ListView),
      Offset(0, -AppSpacing.oneHundred * 8),
    );
    await tester.pumpAndSettle();
    expect(find.text(UITextConstants.forwardContacts), findsOneWidget);
    expect(find.text('联系人 A'), findsOneWidget);
    expect(find.text('群聊 A'), findsOneWidget);
    expect(find.text('圈子行'), findsNothing);
  });

  testWidgets('确认发送使用 card 消息和转发 payload', (tester) async {
    final repository = _ForwardSheetChatRepository();
    await tester.pumpWidget(
      _wrap(
        repository: repository,
        child: Builder(
          builder: (context) => CupertinoButton(
            child: const Text('send'),
            onPressed: () => ForwardConfirmSheet.show(
              context,
              payload: _payload,
              recipient: const AppForwardRecipient(
                id: 'conv_0',
                kind: AppForwardRecipientKind.conversation,
                title: '最近 0',
                conversationId: 'conv_0',
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('send'));
    await tester.pumpAndSettle();
    final input = tester.widget<CupertinoTextField>(
      find.byType(CupertinoTextField),
    );
    final surface = tester.widget<AppBottomModalSurface>(
      find.byType(AppBottomModalSurface),
    );
    expect(surface.showHandle, isFalse);
    expect(input.maxLines, ForwardConfirmSheet.maxMessageLines);
    expect(input.keyboardType, TextInputType.multiline);
    await tester.enterText(find.byType(CupertinoTextField), '一起看看');
    await tester.pump();
    await tester.tap(find.text(UITextConstants.send).last);
    await tester.pumpAndSettle();

    expect(repository.sendCallCount, 1);
    expect(repository.lastConversationId, 'conv_0');
    expect(repository.lastType, 'card');
    expect(repository.lastContent, '一起看看');
    expect(repository.lastCardPayload?['forwardKind'], 'profileQr');
    expect(repository.lastCardPayload?['message'], '一起看看');
    expect(repository.lastSenderSubAccountId, 'persona_forward');
    await tester.pump(const Duration(seconds: 4));
  });
}

class _ForwardSheetChatRepository extends MockChatRepository {
  int sendCallCount = 0;
  String? lastConversationId;
  String? lastType;
  String? lastContent;
  Map<String, dynamic>? lastCardPayload;
  String? lastSenderSubAccountId;

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 500,
  }) async {
    final base = DateTime.utc(2026, 6, 27, 12);
    return List<ChatInboxDto>.generate(
      12,
      (index) => ChatInboxDto(
        id: 'conv_$index',
        type: index.isEven ? 'direct' : 'group',
        title: '最近 $index',
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
    return <ContactHomeRowDto>[
      ContactHomeRowDto(
        id: 'user_a',
        kind: 'user',
        objectId: 'user_a',
        userId: 'user_a',
        title: '联系人 A',
        subtitle: '互相关注',
        lastActiveAt: DateTime.utc(2026, 6, 27, 11),
      ),
      ContactHomeRowDto(
        id: 'group_a',
        kind: 'group',
        objectId: 'group_a',
        conversationId: 'group_a',
        title: '群聊 A',
        memberCount: 8,
        lastActiveAt: DateTime.utc(2026, 6, 27, 10),
      ),
      ContactHomeRowDto(
        id: 'circle_a',
        kind: 'circle',
        objectId: 'circle_a',
        circleId: 'circle_a',
        title: '圈子行',
      ),
    ].take(limit).toList(growable: false);
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
    sendCallCount += 1;
    lastConversationId = conversationId;
    lastType = type;
    lastContent = content;
    lastCardPayload = cardPayload;
    lastSenderSubAccountId = senderSubAccountId;
    return SendMessageResponse(
      id: 'msg_forward',
      seq: 1,
      timestamp: DateTime.utc(2026, 6, 27, 12),
    );
  }
}

class _RecordingExternalShareService implements ForwardExternalShareService {
  final targets = <ForwardExternalShareTarget>[];
  final payloads = <AppForwardPayload>[];

  @override
  Future<ForwardExternalShareResult> share({
    required AppForwardPayload payload,
    required ForwardExternalShareTarget target,
  }) async {
    payloads.add(payload);
    targets.add(target);
    return ForwardExternalShareResult(
      target: target,
      delivery: ForwardExternalShareDelivery.targetedWechat,
    );
  }
}

class _RecordingSystemShareGateway implements ForwardSystemShareGateway {
  final texts = <String>[];
  final subjects = <String>[];

  @override
  Future<void> share({required String text, required String subject}) async {
    texts.add(text);
    subjects.add(subject);
  }
}

class _RecordingWechatShareGateway implements ForwardWechatShareGateway {
  _RecordingWechatShareGateway({required this.delivered});

  final bool delivered;
  final targets = <ForwardExternalShareTarget>[];

  @override
  Future<bool> share({
    required AppForwardPayload payload,
    required ForwardExternalShareTarget target,
  }) async {
    targets.add(target);
    return delivered;
  }
}
