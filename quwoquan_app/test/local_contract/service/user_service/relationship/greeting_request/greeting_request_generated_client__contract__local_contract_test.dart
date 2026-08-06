import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/transport/cloud_operation_recording_executor.dart';
import '../../../../../support/service/user_service/relationship/greeting_request/greeting_request_fixtures.dart';

void main() {
  const context = CloudOperationInvocationContext(
    surfaceId: 'addContact',
    clientPageId: 'contact.contract',
    actor: CloudOperationActorContext(personaId: 'persona-current'),
  );
  test('GreetingRequest generated client 编解码 typed command/result', () async {
    final executor = CloudOperationRecordingExecutor(
      response: greetingRequestRecordFixture(status: 'pending'),
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client.userGreetingRequestSendGreetingRequest(
      SendGreetingCommand(
        targetPersonaId: 'persona-target',
        requestMessage: '你好',
      ),
      context: context,
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.userGreetingRequestSendGreetingRequest,
    );
    expect(executor.body, <String, Object?>{
      'targetPersonaId': 'persona-target',
      'requestMessage': '你好',
      'source': 'profile',
    });
    expect(result.status, GreetingRequestStatus.pending);
  });
}
