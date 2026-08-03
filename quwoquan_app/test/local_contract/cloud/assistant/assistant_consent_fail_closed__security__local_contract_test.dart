// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_consent_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/assistant_remote_test_support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('generated consent wire requires the complete canonical shape', () {
    expect(
      () => SkillConsent.fromJson(<String, dynamic>{
        'skillId': kPersonalContentAccessSkillId,
        'grantedScopes': const <String>[kPersonalContentAccessScope],
        'grantedAt': '2026-07-13T00:00:00Z',
      }),
      throwsFormatException,
    );
  });

  test('remote list failure never returns a locally cached grant', () async {
    final store = AssistantConsentStore(accountId: 'account-a');
    await store.upsert(_consent(accountId: 'account-a'));
    final httpClient = CloudHttpClient(
      client: MockClient((_) async => http.Response('unavailable', 503)),
      authTokenProvider: const _ConsentAuthTokenProvider(),
    );
    final adapter = RemoteAssistantSkillConsentAdapter(
      client: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: _invocationContext,
    );

    await expectLater(adapter.listConsents(), throwsA(isNotNull));
    expect(await store.load(), hasLength(1));
  });

  test(
    'grant sends complete scope set and requires authoritative receipt',
    () async {
      late http.Request captured;
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode(<String, dynamic>{
              'consent': <String, dynamic>{
                'skillId': kPersonalContentAccessSkillId,
                'grantedScopes': const <String>[kPersonalContentAccessScope],
                'granted': false,
              },
              'replayed': false,
            }),
            200,
            request: request,
            headers: const <String, String>{'content-type': 'application/json'},
          );
        }),
        authTokenProvider: const _ConsentAuthTokenProvider(),
      );
      final adapter = RemoteAssistantSkillConsentAdapter(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: _invocationContext,
      );

      await expectLater(
        adapter.grantSkillConsent(
          skillId: kPersonalContentAccessSkillId,
          grantedScopes: const <String>[kPersonalContentAccessScope],
          clientRequestId: 'consent-fail-closed',
        ),
        throwsA(isA<CloudException>()),
      );
      expect(captured.headers['Idempotency-Key'], 'consent-fail-closed');
      expect(
        (jsonDecode(captured.body) as Map<String, dynamic>)['grantedScopes'],
        const <String>[kPersonalContentAccessScope],
      );
    },
  );

  test('local consent cache is physically partitioned by accountId', () async {
    final actorA = AssistantConsentStore(accountId: 'account-a');
    final actorB = AssistantConsentStore(accountId: 'account-b');
    await actorA.upsert(_consent(accountId: 'account-a'));

    expect(await actorA.load(), hasLength(1));
    expect(await actorB.load(), isEmpty);
    final preferences = await SharedPreferences.getInstance();
    final raw = preferences.getString(preferences.getKeys().single);
    expect(jsonDecode(raw!), isA<List<dynamic>>());
    expect(raw, isNot(contains('schema')));
  });
}

SkillConsent _consent({required String accountId}) {
  return SkillConsent(
    id: 'consent:personal-content',
    accountId: accountId,
    skillId: kPersonalContentAccessSkillId,
    grantedScopes: const <String>[kPersonalContentAccessScope],
    grantedAt: '2026-07-13T00:00:00Z',
    revokedAt: null,
    granted: true,
  );
}

CloudOperationInvocationContext _invocationContext(
  String clientPageId, {
  String? idempotencyKey,
}) {
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.assistantSkills.id,
    routeId: AppUiSurfaces.assistantSkills.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'assistant-test-account',
      personaId: 'assistant-test-persona',
    ),
    idempotencyKey: idempotencyKey,
  );
}

final class _ConsentAuthTokenProvider implements CloudAuthTokenProvider {
  const _ConsentAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-consent-test-token';
}
