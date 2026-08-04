// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-002
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

import '../../../support/assistant_remote_test_support.dart';

void main() {
  test('App 不从消息或诊断结果推断长期 AssistantPreference', () {
    final retiredService = File(
      <String>[
        'lib',
        'assistant',
        'memory',
        'preference',
        'preference_' + 'fact_service.dart',
      ].join(Platform.pathSeparator),
    );
    expect(retiredService.existsSync(), isFalse);

    final assistantSources = Directory('lib/assistant')
        .listSync(recursive: true)
        .whereType<File>()
        .where((file) => file.path.endsWith('.dart'));
    for (final source in assistantSources) {
      final content = source.readAsStringSync();
      expect(
        content,
        isNot(contains('buildLongTermPreference' + 'Facts')),
        reason: '${source.path} must not infer persistent preferences',
      );
      expect(
        content,
        isNot(contains('collectPreference' + 'FactsFromMessages')),
        reason: '${source.path} must not promote messages into memory',
      );
    }
  });

  test('Remote 偏好 Facet 使用 metadata 路径并完成设置、列表、遗忘与恢复', () async {
    final transport = _PreferenceClient();
    final httpClient = CloudHttpClient(
      client: transport,
      authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
    );
    final repository = RemoteAssistantRepository(
      operationClient: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: assistantRemoteTestInvocationContext,
      presentationCapabilities: assistantRemoteTestPresentationCapabilities,
    );

    final created = await repository.setAssistantPreference(
      scope: AssistantPreferenceScope.session,
      sessionId: 'asn_preference',
      kind: AssistantPreferenceKind.replyLength,
      value: 'concise',
      sourceType: AssistantPreferenceSourceType.explicitRewrite,
    );
    expect(created.preferenceId, 'apf_preference');

    final listed = await repository.listAssistantPreferences(
      scope: AssistantPreferenceScope.session,
      sessionId: 'asn_preference',
    );
    expect(listed.single.value, 'concise');

    final revoked = await repository.revokeAssistantPreference(
      preferenceId: created.preferenceId,
    );
    expect(revoked.status, AssistantPreferenceStatus.revoked);

    final restored = await repository.restoreAssistantPreference(
      preferenceId: created.preferenceId,
    );
    expect(restored.status, AssistantPreferenceStatus.active);

    expect(transport.requests, hasLength(4));
    expect(transport.requests[0].method, 'POST');
    expect(transport.requests[0].url.path, '/assistant/preferences');
    expect(
      jsonDecode(transport.requestBodies[0]),
      containsPair('sessionId', 'asn_preference'),
    );
    expect(
      transport.requests[1].url.queryParameters,
      containsPair('status', 'active'),
    );
    expect(
      transport.requests[2].url.path,
      '/assistant/preferences/apf_preference/revoke',
    );
    expect(
      transport.requests[3].url.path,
      '/assistant/preferences/apf_preference/restore',
    );
  });

  test('Remote 偏好 Facet 保留 canonical preference_not_found', () async {
    final httpClient = CloudHttpClient(
      client: _PreferenceClient(statusCode: 404),
      authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
    );
    final repository = RemoteAssistantRepository(
      operationClient: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: assistantRemoteTestInvocationContext,
      presentationCapabilities: assistantRemoteTestPresentationCapabilities,
    );

    await expectLater(
      repository.revokeAssistantPreference(preferenceId: 'apf_missing'),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 404)
            .having(
              (error) => error.code,
              'code',
              'ASSISTANT.USER.preference_not_found',
            ),
      ),
    );
  });

  test('Remote 偏好 Facet 提交经用户确认的来源与确认标记', () async {
    final transport = _PreferenceClient();
    final httpClient = CloudHttpClient(
      client: transport,
      authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
    );
    final repository = RemoteAssistantRepository(
      operationClient: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: assistantRemoteTestInvocationContext,
      presentationCapabilities: assistantRemoteTestPresentationCapabilities,
    );

    await repository.setAssistantPreference(
      scope: AssistantPreferenceScope.longTerm,
      kind: AssistantPreferenceKind.frequentLocations,
      value: '杭州',
      sourceType: AssistantPreferenceSourceType.sessionConfirmed,
      sourceSessionId: 'asn_memory_source',
      confirmed: true,
    );

    expect(
      jsonDecode(transport.requestBodies.single),
      containsPair('sourceSessionId', 'asn_memory_source'),
    );
    expect(
      jsonDecode(transport.requestBodies.single),
      containsPair('confirmed', true),
    );
  });
}

final class _PreferenceClient extends http.BaseClient {
  _PreferenceClient({this.statusCode = 200});

  final int statusCode;
  final List<http.BaseRequest> requests = <http.BaseRequest>[];
  final List<String> requestBodies = <String>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    if (request is http.Request) {
      requestBodies.add(request.body);
    } else {
      requestBodies.add('');
    }
    final revoked = request.url.path.endsWith('/revoke');
    final payload = statusCode == 404
        ? const <String, Object?>{'code': 'ASSISTANT.USER.preference_not_found'}
        : request.method == 'GET'
        ? <String, Object?>{
            'items': <Object?>[_preference(status: 'active')],
          }
        : _preference(status: revoked ? 'revoked' : 'active');
    return http.StreamedResponse(
      Stream<List<int>>.value(utf8.encode(jsonEncode(payload))),
      statusCode,
      request: request,
      headers: const <String, String>{'content-type': 'application/json'},
    );
  }
}

Map<String, Object?> _preference({required String status}) => <String, Object?>{
  'preferenceId': 'apf_preference',
  'userId': 'persona_owner',
  'scope': 'session',
  'sessionId': 'asn_preference',
  'kind': 'reply_length',
  'value': 'concise',
  'sourceType': 'explicit_rewrite',
  'status': status,
  if (status == 'revoked') ...<String, Object?>{
    'revokedAt': '2026-07-20T08:01:00Z',
    'revocationDeadline': '2026-07-20T08:11:00Z',
  },
  'createdAt': '2026-07-20T08:00:00Z',
  'updatedAt': '2026-07-20T08:01:00Z',
  'version': status == 'revoked' ? 2 : 3,
};
