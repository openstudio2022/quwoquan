import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/adapters/contact_discovery_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/transport/cloud_operation_recording_executor.dart';

void main() {
  const context = CloudOperationInvocationContext(
    surfaceId: 'addContact',
    clientPageId: 'contact.contract',
    actor: CloudOperationActorContext(personaId: 'persona-current'),
  );
  test('ContactDiscovery generated client 只上传哈希列表', () async {
    final executor = CloudOperationRecordingExecutor(
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

  group('RemoteContactDiscoveryRepository latest 三态语义', () {
    test('合法零命中是带 record id 的成功结果', () async {
      final repository = _repository(
        result: ContactDiscoveryResult(
          id: 'discovery-empty-match',
          status: DiscoveryStatus.completed,
          matchedPersonaIds: <String>[],
          matchCount: 0,
          matches: <ContactDiscoveryMatchResult>[],
        ),
      );

      final result = await repository.getLatest();

      expect(result.id, 'discovery-empty-match');
      expect(result.matchCount, 0);
      expect(result.matches, isEmpty);
    });

    test('canonical not_found 与无 code HTTP 404 均保留失败语义', () async {
      final canonicalNotFound = CloudErrorMapper.fromStatusCode(
        404,
        body: '{"code":"${UserErrorCode.contactDiscoveryNotFound.code}"}',
      );
      final rawHttpNotFound = CloudErrorMapper.fromStatusCode(404);

      await expectLater(
        _repository(failure: canonicalNotFound).getLatest(),
        throwsA(same(canonicalNotFound)),
      );
      await expectLater(
        _repository(failure: rawHttpNotFound).getLatest(),
        throwsA(same(rawHttpNotFound)),
      );
    });

    test('依赖失败不降级为空结果', () async {
      final dependencyFailure = CloudErrorMapper.fromStatusCode(
        503,
        body: '{"code":"${UserErrorCode.internalError.code}"}',
      );

      await expectLater(
        _repository(failure: dependencyFailure).getLatest(),
        throwsA(same(dependencyFailure)),
      );
    });

    test('空 record id 是协议失败而非合法空', () async {
      final repository = _repository(
        result: ContactDiscoveryResult(
          id: '',
          status: DiscoveryStatus.completed,
          matchedPersonaIds: <String>[],
          matchCount: 0,
          matches: <ContactDiscoveryMatchResult>[],
        ),
      );

      await expectLater(
        repository.getLatest(),
        throwsA(
          isA<CloudException>().having(
            (error) => error.type,
            'type',
            CloudErrorType.invalidResponse,
          ),
        ),
      );
    });
  });
}

RemoteContactDiscoveryRepository _repository({
  ContactDiscoveryResult? result,
  Object? failure,
}) {
  return RemoteContactDiscoveryRepository(
    commandWriter: const _UnusedContactDiscoveryCommandWriter(),
    query: _ContactDiscoveryQueryDouble(result: result, failure: failure),
  );
}

final class _ContactDiscoveryQueryDouble implements ContactDiscoveryQuery {
  const _ContactDiscoveryQueryDouble({this.result, this.failure});

  final ContactDiscoveryResult? result;
  final Object? failure;

  @override
  Future<ContactDiscoveryResult> getLatestContactDiscovery(
    GetLatestContactDiscoveryQuery query,
  ) async {
    final configuredFailure = failure;
    if (configuredFailure != null) {
      throw configuredFailure;
    }
    return result!;
  }
}

final class _UnusedContactDiscoveryCommandWriter
    implements ContactDiscoveryCommandWriter {
  const _UnusedContactDiscoveryCommandWriter();

  @override
  Future<ContactDiscoveryDismissResult> dismissContactDiscovery(
    DismissContactDiscoveryCommand command,
  ) {
    throw UnimplementedError();
  }

  @override
  Future<ContactDiscoveryResult> initiateContactDiscovery(
    InitiateContactDiscoveryCommand command,
  ) {
    throw UnimplementedError();
  }
}
