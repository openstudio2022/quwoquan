import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/assistant_remote_test_support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('consent wire requires the complete current shape and fails closed', () {
    expect(
      () => AssistantSkillConsent.fromJson(<String, dynamic>{
        'skillId': kPersonalContentAccessSkillId,
        'grantedScope': kPersonalContentAccessSkillId,
        'grantedAt': '2026-07-13T00:00:00Z',
      }),
      throwsFormatException,
    );
    final revoked = AssistantSkillConsent.fromJson(<String, dynamic>{
      'skillId': kPersonalContentAccessSkillId,
      'grantedScope': kPersonalContentAccessSkillId,
      'granted': true,
      'grantedAt': '2026-07-13T00:00:00Z',
      'revokedAt': '2026-07-13T00:00:00Z',
    });

    expect(revoked.granted, isFalse);
  });

  test('remote list failure never returns a locally cached grant', () async {
    final store = AssistantConsentStore(accountId: 'account-a');
    await store.upsert(
      AssistantSkillConsent(
        skillId: kPersonalContentAccessSkillId,
        grantedScope: kPersonalContentAccessSkillId,
        granted: true,
        updatedAt: DateTime.utc(2026, 7, 13),
      ),
    );
    final httpClient = CloudHttpClient(
      client: MockClient((_) async => http.Response('unavailable', 503)),
    );
    final repository = RemoteAssistantRepository(
      consentAccountId: 'account-a',
      store: store,
      httpClient: httpClient,
      operationClient: buildAssistantRemoteTestOperationClient(httpClient),
      sessionInvocationContext: assistantRemoteTestInvocationContext,
    );

    await expectLater(repository.listConsents(), throwsA(isNotNull));
  });

  test('remote grant requires an authoritative granted response', () async {
    final httpClient = CloudHttpClient(
      client: MockClient((request) async {
        expect(request.headers['Idempotency-Key'], 'consent-fail-closed');
        return http.Response(
          jsonEncode(<String, dynamic>{
            'consent': <String, dynamic>{
              'skillId': kPersonalContentAccessSkillId,
              'grantedScope': kPersonalContentAccessSkillId,
              'granted': false,
            },
          }),
          200,
          headers: const <String, String>{'content-type': 'application/json'},
        );
      }),
    );
    final repository = RemoteAssistantRepository(
      consentAccountId: 'account-a',
      httpClient: httpClient,
      operationClient: buildAssistantRemoteTestOperationClient(httpClient),
      sessionInvocationContext: assistantRemoteTestInvocationContext,
    );

    await expectLater(
      repository.grantSkillConsent(
        skillId: kPersonalContentAccessSkillId,
        clientRequestId: 'consent-fail-closed',
      ),
      throwsA(isNotNull),
    );
  });

  test('local consent cache is physically partitioned by accountId', () async {
    final actorA = AssistantConsentStore(accountId: 'account-a');
    final actorB = AssistantConsentStore(accountId: 'account-b');
    await actorA.upsert(
      AssistantSkillConsent(
        skillId: kPersonalContentAccessSkillId,
        grantedScope: kPersonalContentAccessSkillId,
        granted: true,
        updatedAt: DateTime.utc(2026, 7, 13),
      ),
    );

    expect(await actorA.load(), hasLength(1));
    expect(await actorB.load(), isEmpty);
    final preferences = await SharedPreferences.getInstance();
    final raw = preferences.getString(preferences.getKeys().single);
    expect(jsonDecode(raw!), isA<List<dynamic>>());
    expect(raw, isNot(contains('schema')));
  });
}
