import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/user/relationship/contact_facets_test_executor.dart';

void main() {
  const context = CloudOperationInvocationContext(
    surfaceId: 'addContact',
    clientPageId: 'contact.contract',
    actor: CloudOperationActorContext(personaId: 'persona-current'),
  );
  test('GreetingRequest generated client 编解码 typed command/result', () async {
    final executor = ContactRecordingExecutor(
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
    expect(result.status, 'pending');
  });

}
