import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/transport/cloud_operation_recording_executor.dart';

void main() {
  const context = CloudOperationInvocationContext(
    surfaceId: 'addContact',
    clientPageId: 'contact.contract',
    actor: CloudOperationActorContext(personaId: 'persona-current'),
  );
  test('RelationshipCapability generated client 保留 16 个能力位', () async {
    final executor = CloudOperationRecordingExecutor(
      response: <String, Object?>{
        'viewerPersonaId': 'persona-current',
        'targetPersonaId': 'persona-target',
        'relationState': 'mutual',
        'canFollow': false,
        'canUnfollow': true,
        'canFollowBack': false,
        'canGreet': false,
        'canOpenConversation': true,
        'canCreateDirectConversation': true,
        'canSendMessage': true,
        'hasPendingGreeting': false,
        'hasFormalConversation': true,
        'canStartVoiceCall': true,
        'canStartVideoCall': true,
        'isBlocked': false,
        'isBlockedBy': false,
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client
        .userPersonaRelationshipGetRelationshipCapability(
          GetRelationshipCapabilityQuery(targetPersonaId: 'persona-target'),
          context: context,
        );

    expect(executor.pathParameters, <String, String>{
      'personaId': 'persona-target',
    });
    expect(result.relationState, 'mutual');
    expect(result.canStartVideoCall, isTrue);
  });
}
