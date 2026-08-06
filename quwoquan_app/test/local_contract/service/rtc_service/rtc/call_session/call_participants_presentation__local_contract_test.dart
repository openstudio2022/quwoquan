import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_participant_presentation.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_participants_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/rtc_service/rtc/call_session/rtc_contract_test_builders.dart';

void main() {
  test('conversation member projection enriches display and trust', () async {
    final resolver = _PresentationResolver();
    final container = ProviderContainer(
      overrides: [
        callParticipantPresentationResolverProvider.overrideWithValue(resolver),
      ],
    );
    addTearDown(container.dispose);

    await container
        .read(callParticipantsProvider.notifier)
        .syncRoster(<CallParticipant>[
          buildCallParticipantContract(
            userId: 'user-known',
            role: ParticipantRole.invitee,
            status: ParticipantStatus.ringing,
          ),
          buildCallParticipantContract(
            userId: 'user-unknown',
            role: ParticipantRole.invitee,
            status: ParticipantStatus.ringing,
          ),
        ], conversationId: 'conversation-1');

    final participants = container.read(callParticipantsProvider).participants;
    final known = participants.singleWhere(
      (participant) => participant.userId == 'user-known',
    );
    final unknown = participants.singleWhere(
      (participant) => participant.userId == 'user-unknown',
    );
    expect(known.displayName, '契约好友');
    expect(known.avatarUrl, isNotEmpty);
    expect(known.trustRelation, TrustRelation.known);
    expect(known.needsTrustWarning, isFalse);
    expect(unknown.displayName, 'user-unknown');
    expect(unknown.trustRelation, TrustRelation.possiblyUnknown);
  });

  test(
    'ringing presentation is a trusted fallback without conversation data',
    () async {
      final container = ProviderContainer(
        overrides: [
          callParticipantPresentationResolverProvider.overrideWithValue(
            _PresentationResolver(),
          ),
        ],
      );
      addTearDown(container.dispose);

      await container.read(callParticipantsProvider.notifier).syncRoster(
        <CallParticipant>[
          buildCallParticipantContract(
            userId: 'caller',
            role: ParticipantRole.initiator,
            status: ParticipantStatus.ringing,
          ),
        ],
        callerFallback: const CallParticipantPresentation(
          userId: 'caller',
          displayName: '来电用户',
          avatarUrl: 'https://cdn.example/caller.png',
          knownInCurrentContext: true,
        ),
      );

      final caller = container
          .read(callParticipantsProvider)
          .participants
          .single;
      expect(caller.displayName, '来电用户');
      expect(caller.trustRelation, TrustRelation.known);
    },
  );
}

final class _PresentationResolver
    implements CallParticipantPresentationResolver {
  @override
  Future<Map<String, CallParticipantPresentation>> resolve({
    required String conversationId,
    required Set<String> userIds,
  }) async => <String, CallParticipantPresentation>{
    if (userIds.contains('user-known'))
      'user-known': const CallParticipantPresentation(
        userId: 'user-known',
        displayName: '契约好友',
        avatarUrl: 'data:image/png;base64,AA==',
        knownInCurrentContext: true,
      ),
  };
}
