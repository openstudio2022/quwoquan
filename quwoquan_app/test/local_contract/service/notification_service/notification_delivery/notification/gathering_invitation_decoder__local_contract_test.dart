// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('typed Gathering invitation decodes without private room data', () {
    final message = decodeAppMessage(<String, Object?>{
      'messageId': 'message-invitation-1',
      'userId': 'persona-recipient',
      'messageType': 'circle',
      'source': 'gathering_invitation',
      'sourceId': 'gathering-1',
      'destination': <String, Object?>{
        'type': 'user',
        'id': 'persona-recipient',
      },
      'title': '活动邀请',
      'summary': '周末看展',
      'target': <String, Object?>{
        'targetType': 'gathering',
        'targetId': 'gathering-1',
        'query': <String, Object?>{},
      },
      'gatheringInvitation': <String, Object?>{
        'gatheringId': 'gathering-1',
        'inviterPersonaId': 'persona-inviter',
        'recipientPersonaId': 'persona-recipient',
        'purposeSummary': '周末看展',
        'schedule': <String, Object?>{
          'timezone': 'Asia/Shanghai',
          'dateLabel': '2026-08-08',
        },
        'place': <String, Object?>{
          'mode': 'physical',
          'coarsePlaceLabel': '浦东新区',
        },
        'participationVersion': 1,
        'status': 'pending',
        'actionIntents': <Object?>[
          <String, Object?>{
            'action': 'accept',
            'expectedGatheringVersion': 11,
            'expectedParticipationVersion': 1,
          },
          <String, Object?>{
            'action': 'decline',
            'expectedGatheringVersion': 11,
            'expectedParticipationVersion': 1,
          },
        ],
      },
      'read': false,
      'createdAt': '2026-08-06T12:00:00Z',
    });

    final invitation = message.gatheringInvitation;
    expect(invitation, isNotNull);
    expect(invitation!.status, AppMessageGatheringInvitationStatus.pending);
    expect(
      invitation.actionIntents.map((intent) => intent.action),
      <AppMessageGatheringInvitationAction>[
        AppMessageGatheringInvitationAction.accept,
        AppMessageGatheringInvitationAction.decline,
      ],
    );
    expect(invitation.place.exactMeetingPoint, isNull);
  });
}
