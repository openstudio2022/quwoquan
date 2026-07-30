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

  test('consent wire without explicit granted=true fails closed', () {
    final missingGranted = AssistantSkillConsent.fromJson(<String, dynamic>{
      'skillId': kPersonalContentAccessSkillId,
      'grantedScope': kPersonalContentAccessSkillId,
      'revokedAt': '',
    });
    final revoked = AssistantSkillConsent.fromJson(<String, dynamic>{
      'skillId': kPersonalContentAccessSkillId,
      'grantedScope': kPersonalContentAccessSkillId,
      'granted': true,
      'revokedAt': '2026-07-13T00:00:00Z',
    });

    expect(missingGranted.granted, isFalse);
    expect(revoked.granted, isFalse);
  });

  test('remote list failure never returns a locally cached grant', () async {
    final store = AssistantConsentStore(actorScope: 'account-a/persona-a');
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
      consentActorScope: 'account-a/persona-a',
      store: store,
      httpClient: httpClient,
      operationClient: buildAssistantRemoteTestOperationClient(httpClient),
      conversationInvocationContext: assistantRemoteTestInvocationContext,
    );

    await expectLater(repository.listConsents(), throwsA(isNotNull));
  });

  test('remote grant requires an authoritative granted response', () async {
    final httpClient = CloudHttpClient(
      client: MockClient(
        (_) async => http.Response(
          jsonEncode(<String, dynamic>{
            'consent': <String, dynamic>{
              'skillId': kPersonalContentAccessSkillId,
              'grantedScope': kPersonalContentAccessSkillId,
              'granted': false,
            },
          }),
          200,
          headers: const <String, String>{'content-type': 'application/json'},
        ),
      ),
    );
    final repository = RemoteAssistantRepository(
      consentActorScope: 'account-a/persona-a',
      httpClient: httpClient,
      operationClient: buildAssistantRemoteTestOperationClient(httpClient),
      conversationInvocationContext: assistantRemoteTestInvocationContext,
    );

    await expectLater(
      repository.grantSkillConsent(skillId: kPersonalContentAccessSkillId),
      throwsA(isNotNull),
    );
  });

  test('local consent cache is physically partitioned by actor', () async {
    final actorA = AssistantConsentStore(actorScope: 'account-a/persona-a');
    final actorB = AssistantConsentStore(actorScope: 'account-b/persona-b');
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
  });
}
