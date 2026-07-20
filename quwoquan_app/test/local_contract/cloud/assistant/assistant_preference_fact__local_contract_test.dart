import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

void main() {
  test('Remote 偏好 Facet 使用 metadata 路径并完成设置、列表、遗忘与恢复', () async {
    final transport = _PreferenceClient();
    final repository = RemoteAssistantRepository(
      httpClient: CloudHttpClient(client: transport),
      consentActorScope: 'assistant-preference-test',
    );

    final created = await repository.setAssistantPreference(
      scope: AssistantPreferenceScope.session,
      conversationId: 'acv_preference',
      kind: AssistantPreferenceKind.replyLength,
      value: 'concise',
      sourceType: AssistantPreferenceSourceType.explicitRewrite,
    );
    expect(created.preferenceId, 'apf_preference');

    final listed = await repository.listAssistantPreferences(
      scope: AssistantPreferenceScope.session,
      conversationId: 'acv_preference',
    );
    expect(listed.single.value, 'concise');

    final revoked = await repository.revokeAssistantPreference(
      preferenceId: created.preferenceId,
    );
    expect(revoked.status, AssistantPreferenceStatus.revoked.wireName);

    final restored = await repository.restoreAssistantPreference(
      preferenceId: created.preferenceId,
    );
    expect(restored.status, AssistantPreferenceStatus.active.wireName);

    expect(transport.requests, hasLength(4));
    expect(transport.requests[0].method, 'POST');
    expect(transport.requests[0].url.path, '/assistant/preferences');
    expect(
      jsonDecode(transport.requestBodies[0]),
      containsPair('conversationId', 'acv_preference'),
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
}

final class _PreferenceClient extends http.BaseClient {
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
    final payload = request.method == 'GET'
        ? <String, Object?>{
            'items': <Object?>[_fact(status: 'active')],
          }
        : _fact(status: revoked ? 'revoked' : 'active');
    return http.StreamedResponse(
      Stream<List<int>>.value(utf8.encode(jsonEncode(payload))),
      200,
      request: request,
      headers: const <String, String>{'content-type': 'application/json'},
    );
  }
}

Map<String, Object?> _fact({required String status}) => <String, Object?>{
  'preferenceId': 'apf_preference',
  'userId': 'persona_owner',
  'scope': 'session',
  'conversationId': 'acv_preference',
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
