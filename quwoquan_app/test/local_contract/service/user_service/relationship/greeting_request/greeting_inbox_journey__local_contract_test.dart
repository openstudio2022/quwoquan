// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/greeting-intersection-context/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/greeting-intersection-context/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/presentation/greeting_inbox_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';

void main() {
  testWidgets('打招呼收件可忽略、发件可撤回并回显终态（UAT 旅程）', (tester) async {
    final now = DateTime.utc(2026, 7, 19, 12);
    final repository = alphaGreetingRepository(
      seedInbox: <GreetingRequestRecord>[
        GreetingRequestRecord(
          id: 'greeting_inbox_1',
          requesterPersonaId: 'ps_sender',
          targetPersonaId: 'ps_me',
          requestMessage: '你好，想交流一下',
          status: GreetingRequestStatus.pending,
          source: GreetingRequestSource.profile,
          createdAt: now,
          updatedAt: now,
        ),
      ],
      seedOutbox: <GreetingRequestRecord>[
        GreetingRequestRecord(
          id: 'greeting_outbox_1',
          requesterPersonaId: 'ps_me',
          targetPersonaId: 'ps_target',
          requestMessage: '你的作品很有意思',
          status: GreetingRequestStatus.pending,
          source: GreetingRequestSource.profile,
          createdAt: now,
          updatedAt: now,
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [greetingRepositoryProvider.overrideWithValue(repository)],
        child: const CupertinoApp(home: GreetingInboxPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('ps_sender'), findsOneWidget);
    await tester.tap(find.text(ChatText.chatGreetingInboxIgnore));
    await tester.pumpAndSettle();
    expect(find.text(ChatText.chatGreetingStatusIgnored), findsOneWidget);

    await tester.tap(find.text(ChatText.chatGreetingSentTab));
    await tester.pumpAndSettle();
    expect(find.text('ps_target'), findsOneWidget);
    await tester.tap(find.text(ChatText.chatGreetingCancel));
    await tester.pumpAndSettle();
    await tester.tap(find.text(ChatText.chatGreetingCancel).last);
    await tester.pumpAndSettle();

    expect(find.text(ChatText.chatGreetingStatusCancelled), findsOneWidget);
    final sent = await repository.listOutbox(status: '');
    expect(sent.single.status, 'cancelled');
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('请求箱展示云侧破冰依据；无依据的问候不伪造依据', (tester) async {
    final now = DateTime.utc(2026, 8, 13, 12);
    final repository = alphaGreetingRepository(
      seedInbox: <GreetingRequestRecord>[
        GreetingRequestRecord(
          id: 'greeting_with_context',
          requesterPersonaId: 'ps_photographer',
          targetPersonaId: 'ps_me',
          requestMessage: '周末观星活动认识一下？',
          intersectionSnapshot: GreetingIntersectionSnapshot(
            intersectionId: 'intersection_1',
            evidenceId: 'evidence_1',
            sourceRef: 'coWishlistedEntity',
            objectTypeRef: 'entity',
            objectId: 'entity_star_park',
            primaryText: '你们都想去五彩池观星营地',
            resolvedAt: now,
          ),
          status: GreetingRequestStatus.pending,
          source: GreetingRequestSource.recommendation,
          createdAt: now,
          updatedAt: now,
        ),
        GreetingRequestRecord(
          id: 'greeting_plain',
          requesterPersonaId: 'ps_stranger',
          targetPersonaId: 'ps_me',
          requestMessage: '你好',
          status: GreetingRequestStatus.pending,
          source: GreetingRequestSource.profile,
          createdAt: now,
          updatedAt: now,
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [greetingRepositoryProvider.overrideWithValue(repository)],
        child: const CupertinoApp(home: GreetingInboxPage()),
      ),
    );
    await tester.pumpAndSettle();

    // GWT-001：成立交集的依据整体来自云侧快照原文。
    expect(
      find.text('你们都想去五彩池观星营地'),
      findsOneWidget,
      reason: '请求箱必须展示云侧破冰依据原文',
    );
    // GWT-002：无依据的普通问候不得伪造任何依据文案。
    expect(find.text('ps_stranger'), findsOneWidget);
    expect(
      find.textContaining('都想去'),
      findsOneWidget,
      reason: '依据只出现在携带云侧快照的请求上',
    );
  });
}
