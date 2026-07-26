import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_circle_share_picker_route.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/share/forward_external_share_service.dart';
import 'package:quwoquan_app/ui/share/forward_share_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/fixtures/chat/chat_inbox_fixture_builder.dart';

class _FakeShareActionHandler implements ContentShareActionHandler {
  final List<String> executed = <String>[];

  _FakeShareActionHandler();

  @override
  Future<ContentShareActionResult> execute(
    BuildContext context,
    ContentShareTemplate template,
    ContentShareAction action,
  ) async {
    executed.add(action.id);
    return ContentShareActionResult(
      actionId: action.id,
      success: true,
      dismissed: false,
    );
  }
}

void main() {
  testWidgets('点滴分享模板展示 identity actions 与时间语境', (tester) async {
    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        MicroPostDto(
          id: 'moment_1',
          type: 'micro',
          identity: 'moment',
          assistantUsePolicy: 'inherit',
          authorId: 'user_1',
          displayName: '阿宁',
          avatarUrl: '',
          authorRoleLabel: '',
          authorIdentityTags: const <String>[],
          authorVerified: false,
          body: '清晨六点的光，刚好落在湖面。',
          imageUrls: const ['https://example.com/moment.jpg'],
          likeCount: 8,
          commentCount: 2,
          shareCount: 1,
          createdAt: DateTime(2026, 3, 12, 6, 0),
        ),
      ),
      enableIdentityTemplate: true,
      visibility: 'public',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ContentShareSheet(template: template)),
      ),
    );

    expect(template.profileId, 'moment');
    expect(template.deeplink, 'quwoquan://content/post/moment_1');
    expect(
      template.landingUrl,
      startsWith(AppPublicContentLinks.postWebUrl('moment_1')),
    );
    expect(find.text(UITextConstants.shareTemplateMomentTitle), findsOneWidget);
    expect(find.text(UITextConstants.copyLink), findsOneWidget);
    expect(find.text(ChatText.shareActionSavePoster), findsOneWidget);
    expect(find.text(ChatText.shareInternalTitle), findsOneWidget);
    expect(find.text(UITextConstants.shareTargetCircle), findsOneWidget);
    expect(find.text(ChatText.shareTargetGroup), findsOneWidget);
    expect(find.text(ChatText.shareTargetMessage), findsOneWidget);
    expect(find.text(ChatText.shareExternalTitle), findsOneWidget);
    expect(find.text(ChatText.shareActionMore), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('content-share-close-button')),
      findsOneWidget,
    );
    expect(find.textContaining('2026-03-12'), findsOneWidget);
  });

  testWidgets('点击分享动作会委托给 handler 并触发完成回调', (tester) async {
    final handler = _FakeShareActionHandler();
    final completed = <String>[];
    final telemetry = _CapturingTelemetryRecorder();
    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        MicroPostDto(
          id: 'moment_action',
          type: 'micro',
          identity: 'moment',
          assistantUsePolicy: 'inherit',
          authorId: 'user_action',
          displayName: '小悠',
          avatarUrl: '',
          authorRoleLabel: '',
          authorIdentityTags: const <String>[],
          authorVerified: false,
          body: '点击复制链接应该走真实 handler',
          imageUrls: const <String>[],
          likeCount: 0,
          commentCount: 0,
          shareCount: 0,
          createdAt: DateTime(2026, 3, 12, 10, 0),
        ),
      ),
      enableIdentityTemplate: true,
      visibility: 'public',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ContentShareSheet(
            template: template,
            actionHandler: handler,
            journeyEventTracker: JourneyEventTracker(
              telemetryReporter: telemetry,
            ),
            onActionCompleted: (result) async {
              completed.add(result.actionId);
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text(UITextConstants.copyLink));
    await tester.pump();

    expect(handler.executed, equals(<String>['copy_link']));
    expect(completed, equals(<String>['copy_link']));
    expect(telemetry.payloads, hasLength(1));
    expect(telemetry.payloads.single.extensions['journey'], 'content_share');
    expect(telemetry.payloads.single.extensions['action'], 'copy_link');
    expect(telemetry.payloads.single.extensions['result'], 'success');
    expect(telemetry.payloads.single.extensions['durationMs'], isA<int>());
  });

  testWidgets('最近聊天加载失败只降级对应分区并保留全部分享入口', (tester) async {
    var retryCount = 0;
    final recentRecipients = Completer<List<AppForwardRecipient>>();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ContentShareSheet(
            template: _publicTemplate('share_recent_error'),
            recentRecipients: recentRecipients.future,
            onRecentRecipientsRetry: () => retryCount += 1,
          ),
        ),
      ),
    );
    recentRecipients.completeError(
      StateError('recent conversations unavailable'),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.sectionLoadFailedTitleDefault),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.shareTargetCircle), findsOneWidget);
    expect(find.text(ChatText.shareTargetGroup), findsOneWidget);
    expect(find.text(ChatText.shareTargetMessage), findsOneWidget);
    expect(find.text(ChatText.shareExternalTitle), findsOneWidget);

    await tester.tap(find.text(UITextConstants.tryAgain));
    await tester.pump();
    expect(retryCount, 1);
  });

  testWidgets('默认复制链接动作会写入剪贴板', (tester) async {
    String? copiedText;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copiedText = (call.arguments as Map?)?['text']?.toString();
        }
        return null;
      },
    );
    addTearDown(() {
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      );
    });

    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        MicroPostDto(
          id: 'moment_clipboard',
          type: 'micro',
          identity: 'moment',
          assistantUsePolicy: 'inherit',
          authorId: 'user_clipboard',
          displayName: '阿遥',
          avatarUrl: '',
          authorRoleLabel: '',
          authorIdentityTags: const <String>[],
          authorVerified: false,
          body: '复制链接测试',
          imageUrls: const <String>[],
          likeCount: 0,
          commentCount: 0,
          shareCount: 0,
          createdAt: DateTime(2026, 3, 12, 11, 0),
        ),
      ),
      enableIdentityTemplate: true,
      visibility: 'public',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () async {
                await const DefaultContentShareActionHandler().execute(
                  context,
                  template,
                  const ContentShareAction(
                    id: 'copy_link',
                    label: UITextConstants.copyLink,
                  ),
                );
              },
              child: const Text('trigger'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('trigger'));
    await tester.pump();

    expect(copiedText, template.landingUrl);
    await tester.pump(const Duration(seconds: 3));
    await tester.pump();
  });

  testWidgets('作品公开分享生成标准链接并保留标签', (tester) async {
    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        ArticlePostDto(
          id: 'work_1',
          type: 'article',
          identity: 'work',
          assistantUsePolicy: 'inherit',
          authorId: 'user_2',
          displayName: '洛白',
          avatarUrl: '',
          authorRoleLabel: '',
          authorIdentityTags: const <String>[],
          authorVerified: false,
          title: '城市夜拍攻略',
          body: '从机位、快门到后期流程，适合第一次扫街的摄影爱好者。',
          summary: '从机位、快门到后期流程，适合第一次扫街的摄影爱好者。',
          coverUrl: 'https://example.com/work.jpg',
          articleTemplate: 'tech',
          articleFontPreset: 'mono',
          likeCount: 12,
          commentCount: 4,
          shareCount: 3,
          createdAt: DateTime(2026, 3, 12, 20, 0),
        ),
        wire: const <String, dynamic>{
          'tagRefs': <String>['攻略', '夜景'],
        },
      ),
      enableIdentityTemplate: true,
      visibility: 'public',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ContentShareSheet(template: template)),
      ),
    );

    expect(template.profileId, 'work');
    expect(template.deeplink, 'quwoquan://content/post/work_1');
    expect(
      template.landingUrl,
      startsWith(AppPublicContentLinks.postWebUrl('work_1')),
    );
    expect(find.text(UITextConstants.shareTemplateWorkTitle), findsOneWidget);
    expect(
      find.text(UITextConstants.shareCircleVisibilityNotice),
      findsNothing,
    );
    expect(find.textContaining('#攻略 #夜景'), findsOneWidget);
  });

  testWidgets('私密内容会被分享模板拦截', (tester) async {
    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        ArticlePostDto(
          id: 'private_1',
          type: 'article',
          identity: 'work',
          assistantUsePolicy: 'inherit',
          authorId: 'user_3',
          displayName: '周周',
          avatarUrl: '',
          authorRoleLabel: '',
          authorIdentityTags: const <String>[],
          authorVerified: false,
          title: '仅自己可见',
          body: '这是一条私密内容。',
          summary: '这是一条私密内容。',
          coverUrl: '',
          articleTemplate: 'gentle',
          articleFontPreset: 'clean',
          likeCount: 0,
          commentCount: 0,
          shareCount: 0,
          createdAt: DateTime(2026, 3, 12, 12, 0),
        ),
      ),
      enableIdentityTemplate: true,
      visibility: 'private',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ContentShareSheet(template: template)),
      ),
    );

    expect(template.isBlocked, isTrue);
    expect(find.text(ChatText.sharePrivateBlocked), findsAtLeastNWidgets(1));
    expect(find.text(UITextConstants.copyLink), findsNothing);
  });

  testWidgets('关闭 identity share flag 仍使用身份模板布局但标记为非身份模板', (tester) async {
    final template = ContentShareTemplateBuilder.build(
      surfaceView: ContentSurfaceViewMapper.fromDto(
        MicroPostDto(
          id: 'share_flag_off_1',
          type: 'micro',
          identity: 'moment',
          assistantUsePolicy: 'inherit',
          authorId: 'user_4',
          displayName: '南栀',
          avatarUrl: '',
          authorRoleLabel: '',
          authorIdentityTags: const <String>[],
          authorVerified: false,
          body: '回退到通用分享面板',
          imageUrls: const <String>[],
          likeCount: 0,
          commentCount: 0,
          shareCount: 0,
          createdAt: DateTime(2026, 3, 12, 9, 0),
        ),
      ),
      enableIdentityTemplate: false,
      visibility: 'public',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: ContentShareSheet(template: template)),
      ),
    );

    expect(template.isIdentityTemplate, isFalse);
    expect(
      find.text(
        UITextConstants.contentLabelForKey('share_template_moment_subtitle'),
      ),
      findsAtLeastNWidgets(1),
    );
    expect(find.text(UITextConstants.copyLink), findsOneWidget);
    expect(find.text(ChatText.shareActionSavePoster), findsOneWidget);
  });

  testWidgets('内容分享面板的群聊入口只展示群会话', (tester) async {
    final chat = _ContentShareChatRepository();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(chat),
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
        ],
        child: MaterialApp(
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => ContentShareSheet.show(
                context,
                template: _publicTemplate('share_group_picker'),
              ),
              child: const Text('open-connected-share'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-connected-share'));
    await tester.pumpAndSettle();
    expect(find.text(ChatText.shareInternalTitle), findsOneWidget);
    expect(find.text('最近私信'), findsOneWidget);
    expect(find.text('最近群聊'), findsOneWidget);

    await tester.tap(find.text(ChatText.shareTargetGroup));
    await tester.pumpAndSettle();

    expect(find.text(ChatText.shareSelectGroupTitle), findsOneWidget);
    expect(find.text('最近群聊'), findsOneWidget);
    expect(find.text('最近私信'), findsNothing);
  });

  testWidgets('内容分享面板的微信入口复用定向分享服务', (tester) async {
    final chat = _ContentShareChatRepository();
    final external = _RecordingExternalShareService();
    final outboundShares = _RecordingOutboundShareWriter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(chat),
          forwardExternalShareServiceProvider.overrideWithValue(external),
        ],
        child: MaterialApp(
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => ContentShareSheet.show(
                context,
                template: _publicTemplate('share_wechat'),
                outboundShareWriter: outboundShares,
              ),
              child: const Text('open-wechat-share'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-wechat-share'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text(ChatText.forwardActionWechatFriend));
    await tester.pumpAndSettle();
    await tester.tap(find.text(ChatText.forwardActionWechatFriend));
    await tester.pump();

    expect(external.targets, <ForwardExternalShareTarget>[
      ForwardExternalShareTarget.wechatFriend,
    ]);
    expect(outboundShares.lastCommand, isNull);
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('仅微信 completed 回执追加 OutboundShareFact', (tester) async {
    final chat = _ContentShareChatRepository();
    final external = _RecordingExternalShareService(
      delivery: ForwardExternalShareDelivery.wechatCompleted,
      requestId: 'wechat-provider-receipt-1',
    );
    final outboundShares = _RecordingOutboundShareWriter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(chat),
          forwardExternalShareServiceProvider.overrideWithValue(external),
        ],
        child: MaterialApp(
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => ContentShareSheet.show(
                context,
                template: _publicTemplate('share_wechat_completed'),
                outboundShareWriter: outboundShares,
              ),
              child: const Text('open-completed-share'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-completed-share'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text(ChatText.forwardActionWechatFriend));
    await tester.tap(find.text(ChatText.forwardActionWechatFriend));
    await tester.pump();

    expect(outboundShares.lastCommand?.postId, 'share_wechat_completed');
    expect(outboundShares.lastCommand?.channel, 'wechat_friend');
    expect(outboundShares.lastCommand?.destinationKind, 'external_app');
    expect(outboundShares.lastCommand?.destination, 'wechatFriend');
    expect(
      outboundShares.lastCommand?.providerReceiptId,
      'wechat-provider-receipt-1',
    );
    expect(outboundShares.lastCommand?.referralId, isNotEmpty);
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('外部分享异常保留面板上下文并提供动作级重试', (tester) async {
    final chat = _ContentShareChatRepository();
    final external = _ThrowingExternalShareService();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(chat),
          forwardExternalShareServiceProvider.overrideWithValue(external),
        ],
        child: MaterialApp(
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => ContentShareSheet.show(
                context,
                template: _publicTemplate('share_external_error'),
              ),
              child: const Text('open-failing-share'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-failing-share'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text(ChatText.forwardActionWechatFriend));
    await tester.pumpAndSettle();
    await tester.tap(find.text(ChatText.forwardActionWechatFriend));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.text(UITextConstants.submitNotCompleted), findsOneWidget);
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('content-share-panel')),
      findsOneWidget,
    );
    expect(external.callCount, 1);
  });

  testWidgets('选择圈子后调用强类型 PlaceCirclePost 命令', (tester) async {
    final circle = CircleDto(
      id: 'circle_share_target',
      name: '摄影同好圈',
      description: '分享影像与摄影经验',
      ownerId: 'owner_share',
      createdAt: DateTime.utc(2026, 7, 14),
      updatedAt: DateTime.utc(2026, 7, 14),
    );
    final membershipQuery = _CircleMembershipQuery(<CircleDto>[circle]);
    final placementWriter = _RecordingCirclePostPlacementWriter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          resolvedOwnerUserIdProvider.overrideWithValue('owner_share'),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'persona_share',
              ownerUserId: 'owner_share',
              displayName: '分享测试分身',
              avatarUrl: '',
              contextVersion: 1,
            ),
          ),
        ],
        child: MaterialApp(
          home: Builder(
            builder: (context) => ElevatedButton(
              onPressed: () => Navigator.of(context).push<bool>(
                MaterialPageRoute<bool>(
                  builder: (_) => ContentCircleSharePickerRoute(
                    postId: 'post_share_target',
                    placementWriter: placementWriter,
                    membershipQuery: membershipQuery,
                  ),
                ),
              ),
              child: const Text('open-circle-picker'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open-circle-picker'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('摄影同好圈'));
    await tester.pumpAndSettle();
    expect(
      find.text(UITextConstants.shareCircleConfirmTitle('摄影同好圈')),
      findsOneWidget,
    );
    await tester.tap(find.text(UITextConstants.confirm));
    await tester.pumpAndSettle();

    expect(placementWriter.lastCommand?.postId, 'post_share_target');
    expect(placementWriter.lastCommand?.circleId, 'circle_share_target');
    await tester.pump(const Duration(seconds: 4));
  });
}

final class _CapturingTelemetryRecorder implements AppTelemetryRecorder {
  final List<AppTelemetryPayload> payloads = <AppTelemetryPayload>[];

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    payloads.add(payload);
    return AppTelemetryRecordResult.accepted;
  }
}

ContentShareTemplate _publicTemplate(String postId) {
  return ContentShareTemplateBuilder.build(
    surfaceView: ContentSurfaceViewMapper.fromDto(
      MicroPostDto(
        id: postId,
        type: 'micro',
        identity: 'moment',
        assistantUsePolicy: 'inherit',
        authorId: 'share_author',
        displayName: '分享作者',
        avatarUrl: '',
        authorRoleLabel: '',
        authorIdentityTags: const <String>[],
        authorVerified: false,
        body: '值得分享的内容',
        imageUrls: const <String>[],
        likeCount: 0,
        commentCount: 0,
        shareCount: 0,
        createdAt: DateTime.utc(2026, 7, 14),
      ),
    ),
    enableIdentityTemplate: true,
  );
}

final class _CircleMembershipQuery implements CircleMembershipQuery {
  const _CircleMembershipQuery(this.circles);

  final List<CircleDto> circles;

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) => throw UnimplementedError();

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) async => const CircleMembershipPageSlice(items: <CircleMembershipSlice>[]);

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) async => PersonaCirclePageSlice(
    items: circles
        .take(query.limit)
        .map(
          (circle) => PersonaCircleSummary(
            circleId: circle.id,
            name: circle.name,
            description: circle.description ?? '',
            coverUrl: circle.coverUrl ?? '',
            iconUrl: circle.iconUrl ?? '',
            ownerPersonaId: circle.ownerId,
            ownerDisplayNameSnapshot: '',
            category: circle.category ?? '',
            subCategory: circle.subCategory ?? '',
            tags: circle.tags,
            memberCount: circle.memberCount,
            postCount: circle.postCount,
            weeklyActiveCount: circle.weeklyActiveCount,
            state: circle.status,
            visibility: circle.visibility,
            joinPolicy: circle.joinPolicy,
            kind: circle.kind,
            displaySubjectType: circle.displaySubjectType,
            followEnabled: circle.followEnabled,
            defaultPublicGroupId: circle.defaultPublicGroupId ?? '',
            linkedHomepageId: '',
            linkedHomepageType: '',
            linkedHomepageTitle: '',
            createdAt: circle.createdAt,
            updatedAt: circle.updatedAt,
          ),
        )
        .toList(growable: false),
  );
}

class _ContentShareChatRepository extends MockChatRepository {
  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = 500,
  }) async {
    return <ChatInboxDto>[
      chatInboxFixture(
        id: 'direct_share',
        type: 'direct',
        title: '最近私信',
        lastMessageTime: DateTime.utc(2026, 7, 14, 10),
      ),
      chatInboxFixture(
        id: 'group_share',
        type: 'group',
        title: '最近群聊',
        lastMessageTime: DateTime.utc(2026, 7, 14, 11),
      ),
    ];
  }

  @override
  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = 500,
  }) async {
    return const <ContactHomeRowDto>[];
  }
}

class _RecordingExternalShareService implements ForwardExternalShareService {
  _RecordingExternalShareService({
    this.delivery = ForwardExternalShareDelivery.wechatAccepted,
    this.requestId = '',
  });

  final ForwardExternalShareDelivery delivery;
  final String requestId;
  final List<ForwardExternalShareTarget> targets =
      <ForwardExternalShareTarget>[];

  @override
  Future<ForwardExternalShareResult> share({
    required AppForwardPayload payload,
    required ForwardExternalShareTarget target,
  }) async {
    targets.add(target);
    return ForwardExternalShareResult(
      target: target,
      delivery: delivery,
      requestId: requestId,
    );
  }
}

class _ThrowingExternalShareService implements ForwardExternalShareService {
  int callCount = 0;

  @override
  Future<ForwardExternalShareResult> share({
    required AppForwardPayload payload,
    required ForwardExternalShareTarget target,
  }) async {
    callCount += 1;
    throw StateError('external share unavailable');
  }
}

class _RecordingCirclePostPlacementWriter
    implements CirclePostPlacementCommandWriter {
  PlaceCirclePostCommand? lastCommand;

  @override
  Future<CirclePostPlacementCommandResult> placePost(
    PlaceCirclePostCommand command,
  ) async {
    lastCommand = command;
    return const CirclePostPlacementCommandResult(
      placementId: 'placement-share-target',
      version: 1,
      state: 'active',
      idempotentReplay: false,
    );
  }

  @override
  Future<CirclePostPlacementCommandResult> removePost(
    RemoveCirclePostCommand command,
  ) async => const CirclePostPlacementCommandResult(
    placementId: 'placement-share-target',
    version: 1,
    state: 'removed',
    idempotentReplay: false,
  );

  @override
  Future<CirclePostPlacementCommandResult> setPinned(
    PinCirclePostCommand command,
  ) async => const CirclePostPlacementCommandResult(
    placementId: 'placement-share-target',
    version: 1,
    state: 'active',
    idempotentReplay: false,
  );

  @override
  Future<CirclePostPlacementCommandResult> setFeatured(
    FeatureCirclePostCommand command,
  ) async => const CirclePostPlacementCommandResult(
    placementId: 'placement-share-target',
    version: 1,
    state: 'active',
    idempotentReplay: false,
  );
}

class _RecordingOutboundShareWriter
    implements ContentOutboundShareAppendWriter {
  CreateContentOutboundShareCommand? lastCommand;

  @override
  Future<ContentOutboundShareFactResult> appendOutboundShare(
    CreateContentOutboundShareCommand command,
  ) async {
    lastCommand = command;
    return ContentOutboundShareFactResult(
      eventId: 'outbound-share-event-1',
      postId: command.postId,
      channel: command.channel,
      referralId: command.referralId,
      occurredAt: command.clientConfirmedAt,
      replayed: false,
    );
  }
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'share-test-token',
      activeSubAccountId: 'share_persona',
      ownerId: 'share_owner',
    );
  }
}
