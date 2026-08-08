// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-002
// readiness_case: contact_discovery_record_get_latest_contact_discovery_app_local
// readiness_case: contact_discovery_record_dismiss_contact_discovery_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/adapters/contact_discovery_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'GetLatest/Dismiss use exact generated operations and stable retry intent',
    () async {
      final executor = _ContactDiscoveryExecutor();
      final facet = RemoteContactDiscoveryFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId, {String? idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: 'user.contact-discovery',
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              actor: const CloudOperationActorContext(
                accountId: 'account-1',
                personaId: 'persona-1',
              ),
            ),
      );
      final repository = RemoteContactDiscoveryRepository(
        commandWriter: facet,
        query: facet,
        idempotencyKeyFactory: () => 'dismiss-intent-1',
      );

      final latest = await repository.getLatest();
      await expectLater(
        repository.dismiss('  discovery-1  '),
        throwsA(isA<StateError>()),
      );
      await repository.dismiss('discovery-1');

      expect(latest.id, 'discovery-1');
      expect(latest.matchCount, 1);
      expect(latest.matchedPersonaIds, <String>['persona-2']);
      expect(executor.operationIds, <String>[
        AppCloudOperationIds
            .userContactDiscoveryRecordGetLatestContactDiscovery,
        AppCloudOperationIds.userContactDiscoveryRecordDismissContactDiscovery,
        AppCloudOperationIds.userContactDiscoveryRecordDismissContactDiscovery,
      ]);
      expect(executor.payloads[0].pathParameters, isEmpty);
      expect(executor.payloads[0].queryParameters, isEmpty);
      expect(executor.payloads[0].body, isNull);
      expect(executor.payloads[1].pathParameters, <String, String>{
        'id': 'discovery-1',
      });
      expect(executor.payloads[1].queryParameters, isEmpty);
      expect(executor.payloads[1].body, isNull);
      expect(
        executor.contexts.map((context) => context.idempotencyKey),
        <String?>[null, 'dismiss-intent-1', 'dismiss-intent-1'],
      );
    },
  );

  test('blank dismiss id fails before transport', () async {
    final executor = _ContactDiscoveryExecutor();
    final facet = RemoteContactDiscoveryFacet(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId, {String? idempotencyKey}) =>
          CloudOperationInvocationContext(
            surfaceId: 'user.contact-discovery',
            clientPageId: clientPageId,
            idempotencyKey: idempotencyKey,
            actor: const CloudOperationActorContext(
              accountId: 'account-1',
              personaId: 'persona-1',
            ),
          ),
    );
    final repository = RemoteContactDiscoveryRepository(
      commandWriter: facet,
      query: facet,
      idempotencyKeyFactory: () => 'dismiss-intent-1',
    );

    await expectLater(repository.dismiss('  '), throwsA(isNotNull));
    expect(executor.operationIds, isEmpty);
  });
}

final class _ContactDiscoveryExecutor implements CloudOperationExecutor {
  final operations = <CloudOperationContract>[];
  final contexts = <CloudOperationInvocationContext>[];
  final payloads = <CloudOperationRequestPayload>[];
  int _dismissAttempts = 0;

  List<String> get operationIds => operations
      .map((operation) => operation.canonicalOperationId)
      .toList(growable: false);

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operations.add(operation);
    contexts.add(context);
    payloads.add(requestEncoder());
    if (operation.canonicalOperationId ==
        AppCloudOperationIds
            .userContactDiscoveryRecordDismissContactDiscovery) {
      _dismissAttempts += 1;
      if (_dismissAttempts == 1) {
        throw StateError('connection lost after request write');
      }
      return responseDecoder(<String, Object?>{'status': 'dismissed'});
    }
    return responseDecoder(<String, Object?>{
      'id': 'discovery-1',
      'status': 'completed',
      'matchedPersonaIds': <String>['persona-2'],
      'matchCount': 1,
      'matches': <Object?>[],
      'expireAt': '2026-08-11T10:00:00Z',
      'completedAt': '2026-08-08T10:00:00Z',
    });
  }
}
