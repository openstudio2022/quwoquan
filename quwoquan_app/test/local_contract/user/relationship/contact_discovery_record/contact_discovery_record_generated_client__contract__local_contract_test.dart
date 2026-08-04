import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/user/relationship/contact_facets_test_executor.dart';

void main() {
  const context = CloudOperationInvocationContext(
    surfaceId: 'addContact',
    clientPageId: 'contact.contract',
    actor: CloudOperationActorContext(personaId: 'persona-current'),
  );
  test('ContactDiscovery generated client 只上传哈希列表', () async {
    final executor = ContactRecordingExecutor(
      response: <String, Object?>{
        'id': 'discovery-1',
        'status': 'completed',
        'matchedPersonaIds': <Object?>[],
        'matchCount': 0,
        'matches': <Object?>[],
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client
        .userContactDiscoveryRecordInitiateContactDiscovery(
          InitiateContactDiscoveryCommand(
            hashedPhones: const <String>[
              'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            ],
          ),
          context: context,
        );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.userContactDiscoveryRecordInitiateContactDiscovery,
    );
    expect(executor.body, <String, Object?>{
      'hashedPhones': const <String>[
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      ],
    });
    expect(result.matches, isEmpty);
  });

}
