import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_detail_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';

import '../../../../../support/service/circle_service/circle_management/gathering/gathering_test_support.dart';

GatheringDetailPage _page({ValueChanged<String>? onEnterChat}) {
  return GatheringDetailPage(
    gatheringId: 'gathering-1',
    copy: gatheringDetailTestCopy,
    onEnterChat: onEnterChat,
  );
}

void main() {
  group('GatheringDetailPage dynamic primary action', () {
    testWidgets('公开开放活动显示 join 且只提交 typed join command', (tester) async {
      final port = InMemoryGatheringPort(
        detail: GatheringDetailPresentationSlice(
          publicDetail: publicGatheringDetail(),
        ),
      );
      await pumpGatheringWidget(tester, port: port, child: _page());

      expect(find.text('Public Gathering'), findsOneWidget);
      expect(find.text(gatheringDetailTestCopy.joinAction), findsOneWidget);
      expect(find.byKey(GatheringDetailPage.privatePlaceKey), findsNothing);

      await tester.tap(find.byKey(GatheringDetailPage.primaryActionKey));
      await tester.pumpAndSettle();
      expect(port.joinCalls, 1);
      expect(port.applyCalls, 0);
      expect(port.acceptCalls, 0);
    });

    testWidgets('邀请制 1:1 保持 group Gathering 并显示 accept', (tester) async {
      final port = InMemoryGatheringPort(
        detail: GatheringDetailPresentationSlice(
          publicDetail: publicGatheringDetail(
            maxParticipants: 1,
            occupiedSeats: 1,
            full: true,
            admission: GatheringAdmissionPolicy.inviteOnly,
            audience: GatheringAudiencePolicy.inviteOnly,
            admissionState: GatheringAdmissionState.full,
            participationState: GatheringParticipationState.invitedPending,
            participationSource: GatheringAdmissionSource.invitation,
          ),
        ),
      );
      await pumpGatheringWidget(tester, port: port, child: _page());

      expect(
        find.text(gatheringDetailTestCopy.acceptInvitationAction),
        findsOneWidget,
      );
      expect(find.text('1/1'), findsOneWidget);

      await tester.tap(find.byKey(GatheringDetailPage.primaryActionKey));
      await tester.pumpAndSettle();
      expect(port.acceptCalls, 1);
    });

    testWidgets('多人审批活动显示 apply', (tester) async {
      final port = InMemoryGatheringPort(
        detail: GatheringDetailPresentationSlice(
          publicDetail: publicGatheringDetail(
            maxParticipants: 8,
            occupiedSeats: 3,
            admission: GatheringAdmissionPolicy.approval,
          ),
        ),
      );
      await pumpGatheringWidget(tester, port: port, child: _page());

      expect(find.text(gatheringDetailTestCopy.applyAction), findsOneWidget);
      await tester.tap(find.byKey(GatheringDetailPage.primaryActionKey));
      await tester.pumpAndSettle();
      expect(port.applyCalls, 1);
    });

    testWidgets('full 先 watch，席位重开后刷新为 join', (tester) async {
      final full = GatheringDetailPresentationSlice(
        publicDetail: publicGatheringDetail(
          maxParticipants: 4,
          occupiedSeats: 4,
          full: true,
          admissionState: GatheringAdmissionState.full,
        ),
      );
      final port = InMemoryGatheringPort(detail: full);
      await pumpGatheringWidget(tester, port: port, child: _page());

      expect(
        find.text(gatheringDetailTestCopy.watchAvailabilityAction),
        findsOneWidget,
      );
      port.detail = GatheringDetailPresentationSlice(
        publicDetail: publicGatheringDetail(
          maxParticipants: 4,
          occupiedSeats: 3,
        ),
      );
      await tester.tap(find.byKey(GatheringDetailPage.primaryActionKey));
      await tester.pumpAndSettle();

      expect(port.watchCalls, 1);
      expect(find.text(gatheringDetailTestCopy.joinAction), findsOneWidget);
    });

    testWidgets('进行中有效参与者进入活动群聊主场', (tester) async {
      String? enteredConversation;
      final port = InMemoryGatheringPort(
        detail: GatheringDetailPresentationSlice(
          publicDetail: publicGatheringDetail(
            temporal: GatheringTemporalPhase.inProgress,
            admissionState: GatheringAdmissionState.closed,
            participationState: GatheringParticipationState.active,
            conversationId: 'conversation-1',
          ),
        ),
      );
      await pumpGatheringWidget(
        tester,
        port: port,
        child: _page(
          onEnterChat: (conversationId) => enteredConversation = conversationId,
        ),
      );

      expect(
        find.text(gatheringDetailTestCopy.enterChatAction),
        findsOneWidget,
      );
      await tester.tap(find.byKey(GatheringDetailPage.primaryActionKey));
      expect(enteredConversation, 'conversation-1');
    });

    testWidgets('进行中未参与者与 completed 都是只读终态', (tester) async {
      final port = InMemoryGatheringPort(
        detail: GatheringDetailPresentationSlice(
          publicDetail: publicGatheringDetail(
            lifecycle: GatheringLifecycleStatus.completed,
            temporal: GatheringTemporalPhase.ended,
            admissionState: GatheringAdmissionState.closed,
            outcome: GatheringOutcomeStatus.unverified,
          ),
        ),
      );
      await pumpGatheringWidget(tester, port: port, child: _page());

      expect(find.text(gatheringDetailTestCopy.readOnlyAction), findsOneWidget);
      expect(
        find.text(gatheringDetailTestCopy.unverifiedOutcome),
        findsOneWidget,
      );
      await tester.tap(find.byKey(GatheringDetailPage.primaryActionKey));
      await tester.pump();
      expect(port.joinCalls + port.applyCalls + port.acceptCalls, 0);
    });
  });

  group('GatheringDetailPage permission and host console', () {
    testWidgets('非 active viewer 看不到私密地点、申请答案和 Host console', (tester) async {
      final private = privateGatheringDetail(
        authority: GatheringViewerAuthoritySlice.none,
        exactMeetingPoint: 'SECRET_MEETING_POINT',
        applications: const <GatheringApplicationInboxItemSlice>[
          GatheringApplicationInboxItemSlice(
            personaId: 'applicant',
            displayName: 'Applicant',
            participationVersion: 1,
            answers: <GatheringApplicationAnswerInput>[
              GatheringApplicationAnswerInput(
                questionId: 'q1',
                answerText: 'SECRET_ANSWER',
              ),
            ],
          ),
        ],
      );
      final port = InMemoryGatheringPort(
        detail: GatheringDetailPresentationSlice(
          publicDetail: publicGatheringDetail(),
          privateDetail: private,
        ),
      );
      await pumpGatheringWidget(tester, port: port, child: _page());

      expect(find.text('Shanghai'), findsOneWidget);
      expect(find.text('SECRET_MEETING_POINT'), findsNothing);
      expect(find.text('SECRET_ANSWER'), findsNothing);
      expect(find.byKey(GatheringDetailPage.hostConsoleKey), findsNothing);
    });

    testWidgets('active viewer 可见私密地点但无管理动作', (tester) async {
      const participantAuthority = GatheringViewerAuthoritySlice(
        isOrganizer: false,
        isActiveParticipant: true,
        canReviewApplications: false,
        canInvite: false,
        canRemoveParticipants: false,
        canChangeCapacity: false,
        canChangeAdmission: false,
        canUpdateMaterialDetails: false,
        canCancel: false,
        canStart: false,
        canRecordOutcome: false,
      );
      final port = InMemoryGatheringPort(
        detail: GatheringDetailPresentationSlice(
          publicDetail: publicGatheringDetail(
            participationState: GatheringParticipationState.active,
            conversationId: 'conversation-1',
          ),
          privateDetail: privateGatheringDetail(
            authority: participantAuthority,
            exactMeetingPoint: 'ACTIVE_PRIVATE_PLACE',
          ),
        ),
      );
      await pumpGatheringWidget(tester, port: port, child: _page());

      expect(find.text('ACTIVE_PRIVATE_PLACE'), findsOneWidget);
      expect(find.byKey(GatheringDetailPage.privatePlaceKey), findsOneWidget);
      expect(find.byKey(GatheringDetailPage.hostConsoleKey), findsNothing);
    });

    testWidgets('authority 决定 Host console，审批使用 typed command', (tester) async {
      final port = InMemoryGatheringPort(
        detail: GatheringDetailPresentationSlice(
          publicDetail: publicGatheringDetail(),
          privateDetail: privateGatheringDetail(
            authority: hostAuthority,
            applications: const <GatheringApplicationInboxItemSlice>[
              GatheringApplicationInboxItemSlice(
                personaId: 'applicant',
                displayName: 'Applicant',
                participationVersion: 7,
                answers: <GatheringApplicationAnswerInput>[
                  GatheringApplicationAnswerInput(
                    questionId: 'q1',
                    answerText: 'Organizer visible answer',
                  ),
                ],
              ),
            ],
            roster: const <GatheringRosterItemSlice>[
              GatheringRosterItemSlice(
                personaId: 'member',
                displayName: 'Member',
                state: GatheringParticipationState.active,
                admissionSource: GatheringAdmissionSource.open,
                participationVersion: 3,
              ),
            ],
          ),
        ),
      );
      await pumpGatheringWidget(tester, port: port, child: _page());

      expect(find.byKey(GatheringDetailPage.hostConsoleKey), findsOneWidget);
      await tester.scrollUntilVisible(
        find.byKey(GatheringDetailPage.approveKey('applicant')),
        300,
        // Host console 里还有别的可滚动子树，必须显式指向页面主滚动体，
        // 否则默认 finder 命中多个 Scrollable。
        scrollable: find
            .descendant(
              of: find.byType(SingleChildScrollView),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      await tester.tap(find.byKey(GatheringDetailPage.approveKey('applicant')));
      await tester.pumpAndSettle();

      expect(port.reviewCalls, 1);
      expect(port.lastReview?.participantPersonaId, 'applicant');
      expect(port.lastReview?.expectedParticipationVersion, 7);
      expect(port.lastReview?.decision, GatheringApplicationDecision.approve);
    });
  });

  group('GatheringDetailPage loading/error/empty', () {
    testWidgets('query 未完成时保持 loading', (tester) async {
      final gate = Completer<void>();
      final port = InMemoryGatheringPort()..queryGate = gate;
      await pumpGatheringWidget(tester, port: port, child: _page());

      expect(find.byKey(GatheringDetailPage.loadingKey), findsOneWidget);
      gate.complete();
      await tester.pumpAndSettle();
      expect(find.byKey(GatheringDetailPage.emptyKey), findsOneWidget);
    });

    testWidgets('null typed slice 显示 empty', (tester) async {
      final port = InMemoryGatheringPort();
      await pumpGatheringWidget(tester, port: port, child: _page());
      await tester.pump();

      expect(find.byKey(GatheringDetailPage.emptyKey), findsOneWidget);
    });

    testWidgets('query 错误可恢复重试', (tester) async {
      final port = InMemoryGatheringPort()
        ..queryError = StateError('query unavailable');
      await pumpGatheringWidget(tester, port: port, child: _page());
      await tester.pumpAndSettle();

      expect(port.queryCalls, 1);
      port
        ..queryError = null
        ..detail = GatheringDetailPresentationSlice(
          publicDetail: publicGatheringDetail(),
        );
      // 恢复动作文案由统一错误语义目录拥有；页面 copy 只是语义没有给出
      // primary action 时的兜底，这里必须断言用户真正看到的恢复入口。
      await tester.tap(find.text(SearchText.reload));
      await tester.pumpAndSettle();

      expect(port.queryCalls, 2);
      expect(find.text('Public Gathering'), findsOneWidget);
    });
  });
}
