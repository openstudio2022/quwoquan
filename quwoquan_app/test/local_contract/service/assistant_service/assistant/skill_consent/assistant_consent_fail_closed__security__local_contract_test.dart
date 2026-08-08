// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
// readiness_case: skill_consent_grant_skill_consent_app_local
// readiness_case: skill_consent_list_consents_app_local
// readiness_case: skill_consent_revoke_skill_consent_app_local
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/adapters/assistant_consent_store.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/adapters/skill_consent_remote.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/skill_consent_facet.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';

const _travelCompanionSkillId = 'travel_companion';
const _travelCompanionRequiredScopes = <String>[
  'assistant.learning.feedback_context.read',
  'assistant.memory.preferences.read',
];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('generated consent wire requires the complete canonical shape', () {
    expect(
      () => SkillConsent.fromJson(<String, dynamic>{
        'skillId': _travelCompanionSkillId,
        'grantedScopes': _travelCompanionRequiredScopes,
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
    final adapter = AssistantConsentStore.decorateRemoteSuccess(
      accountId: 'account-a',
      remote: RemoteAssistantSkillConsentAdapter(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: _invocationContext,
      ),
    );

    await expectLater(adapter.listConsents(), throwsA(isNotNull));
    expect(await store.load(), hasLength(1));
  });

  test('successful remote list replaces the account snapshot', () async {
    final store = AssistantConsentStore(accountId: 'account-a');
    await store.upsert(
      _consent(accountId: 'account-a', skillId: 'skill.previous'),
    );
    final remoteItems = <SkillConsent>[
      _consent(accountId: 'account-a', skillId: 'skill.current'),
    ];
    final facet = AssistantConsentStore.decorateRemoteSuccess(
      accountId: 'account-a',
      remote: _ScriptedConsentFacet(listResult: remoteItems),
    );

    final result = await facet.listConsents();

    expect(result, same(remoteItems));
    expect((await store.load()).map((item) => item.skillId), <String>[
      'skill.current',
    ]);
  });

  test(
    'remote list with another account is rejected without cache update',
    () async {
      final store = AssistantConsentStore(accountId: 'account-a');
      await store.upsert(_consent(accountId: 'account-a'));
      final facet = AssistantConsentStore.decorateRemoteSuccess(
        accountId: 'account-a',
        remote: _ScriptedConsentFacet(
          listResult: <SkillConsent>[_consent(accountId: 'account-b')],
        ),
      );

      await expectLater(facet.listConsents(), throwsFormatException);
      expect((await store.load()).single.accountId, 'account-a');
    },
  );

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
                'skillId': _travelCompanionSkillId,
                'grantedScopes': _travelCompanionRequiredScopes,
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
          skillId: _travelCompanionSkillId,
          grantedScopes: _travelCompanionRequiredScopes,
          clientRequestId: 'consent-fail-closed',
        ),
        throwsA(isA<CloudException>()),
      );
      expect(captured.headers['Idempotency-Key'], 'consent-fail-closed');
      expect(
        (jsonDecode(captured.body) as Map<String, dynamic>)['grantedScopes'],
        _travelCompanionRequiredScopes,
      );
    },
  );

  test(
    'list/revoke use exact generated operations and typed responses',
    () async {
      final executor = _SkillConsentExecutor();
      final adapter = RemoteAssistantSkillConsentAdapter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _invocationContext,
      );

      final consents = await adapter.listConsents();
      await adapter.revokeSkillConsent(
        skillId: _travelCompanionSkillId,
        clientRequestId: 'revoke-consent-1',
      );

      expect(executor.operationIds, <String>[
        AppCloudOperationIds.assistantSkillConsentListConsents,
        AppCloudOperationIds.assistantSkillConsentRevokeSkillConsent,
      ]);
      expect(executor.operations[0].method, 'GET');
      expect(executor.operations[0].pathTemplate, '/assistant/consents');
      expect(executor.payloads[0].pathParameters, isEmpty);
      expect(executor.payloads[0].queryParameters, isEmpty);
      expect(executor.payloads[0].body, isNull);
      expect(executor.contexts[0].idempotencyKey, isNull);
      expect(executor.operations[1].method, 'DELETE');
      expect(
        executor.operations[1].pathTemplate,
        '/assistant/skills/{skillId}/consent',
      );
      expect(executor.payloads[1].pathParameters, <String, String>{
        'skillId': _travelCompanionSkillId,
      });
      expect(executor.payloads[1].queryParameters, isEmpty);
      expect(executor.payloads[1].body, isNull);
      expect(executor.contexts[1].idempotencyKey, 'revoke-consent-1');
      expect(consents, hasLength(1));
      expect(consents.single.accountId, 'assistant-test-account');
      expect(consents.single.skillId, _travelCompanionSkillId);
      expect(consents.single.grantedScopes, _travelCompanionRequiredScopes);
      expect(executor.decodedResponses[1], isA<RevokeSkillConsentReceipt>());
    },
  );

  test('successful matching grant updates only its account snapshot', () async {
    final remoteConsent = _consent(
      accountId: 'account-a',
      skillId: 'skill.travel',
      grantedScopes: const <String>['context.trip.read', 'tool.calendar.write'],
    );
    final facet = AssistantConsentStore.decorateRemoteSuccess(
      accountId: 'account-a',
      remote: _ScriptedConsentFacet(grantResult: remoteConsent),
    );

    final result = await facet.grantSkillConsent(
      skillId: 'skill.travel',
      grantedScopes: const <String>['tool.calendar.write', 'context.trip.read'],
      clientRequestId: 'grant-travel',
    );

    expect(result, same(remoteConsent));
    final stored = await AssistantConsentStore(accountId: 'account-a').load();
    expect(stored, hasLength(1));
    expect(stored.single.grantedScopes, remoteConsent.grantedScopes);
    expect(await AssistantConsentStore(accountId: 'account-b').load(), isEmpty);
  });

  test(
    'semantically mismatched grant never changes the prior snapshot',
    () async {
      final store = AssistantConsentStore(accountId: 'account-a');
      await store.upsert(_consent(accountId: 'account-a'));
      final facet = AssistantConsentStore.decorateRemoteSuccess(
        accountId: 'account-a',
        remote: _ScriptedConsentFacet(
          grantResult: _consent(
            accountId: 'account-b',
            skillId: 'skill.travel',
            grantedScopes: const <String>['context.trip.read'],
          ),
        ),
      );

      await expectLater(
        facet.grantSkillConsent(
          skillId: 'skill.travel',
          grantedScopes: const <String>['context.trip.read'],
          clientRequestId: 'grant-wrong-account',
        ),
        throwsFormatException,
      );
      expect((await store.load()).single.skillId, _travelCompanionSkillId);
    },
  );

  test('revoke updates snapshot only after remote success', () async {
    final store = AssistantConsentStore(accountId: 'account-a');
    await store.upsert(_consent(accountId: 'account-a'));
    final failedFacet = AssistantConsentStore.decorateRemoteSuccess(
      accountId: 'account-a',
      remote: _ScriptedConsentFacet(revokeError: StateError('unavailable')),
    );

    await expectLater(
      failedFacet.revokeSkillConsent(
        skillId: _travelCompanionSkillId,
        clientRequestId: 'revoke-failed',
      ),
      throwsStateError,
    );
    expect(await store.load(), hasLength(1));

    final successfulFacet = AssistantConsentStore.decorateRemoteSuccess(
      accountId: 'account-a',
      remote: _ScriptedConsentFacet(),
    );
    await successfulFacet.revokeSkillConsent(
      skillId: _travelCompanionSkillId,
      clientRequestId: 'revoke-succeeded',
    );
    expect(await store.load(), isEmpty);
  });

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

  test('blank account cannot create a shared unauthenticated partition', () {
    expect(() => AssistantConsentStore(accountId: '   '), throwsArgumentError);
  });
}

SkillConsent _consent({
  required String accountId,
  String skillId = _travelCompanionSkillId,
  List<String> grantedScopes = _travelCompanionRequiredScopes,
}) {
  return SkillConsent(
    id: 'consent:$skillId',
    accountId: accountId,
    skillId: skillId,
    grantedScopes: grantedScopes,
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

final class _SkillConsentExecutor implements CloudOperationExecutor {
  final operations = <CloudOperationContract>[];
  final contexts = <CloudOperationInvocationContext>[];
  final payloads = <CloudOperationRequestPayload>[];
  final decodedResponses = <Object?>[];

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
    final response = switch (operation.canonicalOperationId) {
      AppCloudOperationIds.assistantSkillConsentListConsents =>
        <String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'id': 'consent:$_travelCompanionSkillId',
              'accountId': 'assistant-test-account',
              'skillId': _travelCompanionSkillId,
              'grantedScopes': _travelCompanionRequiredScopes,
              'grantedAt': '2026-07-13T00:00:00Z',
              'revokedAt': null,
              'granted': true,
            },
          ],
        },
      AppCloudOperationIds.assistantSkillConsentRevokeSkillConsent =>
        <String, Object?>{
          'status': 'revoked',
          'skillId': _travelCompanionSkillId,
          'replayed': false,
        },
      _ => throw StateError(
        'unexpected operation ${operation.canonicalOperationId}',
      ),
    };
    final decoded = responseDecoder(response);
    decodedResponses.add(decoded);
    return decoded;
  }
}

final class _ScriptedConsentFacet implements AssistantSkillConsentFacet {
  _ScriptedConsentFacet({
    this.listResult = const <SkillConsent>[],
    this.grantResult,
    this.revokeError,
  });

  final List<SkillConsent> listResult;
  final SkillConsent? grantResult;
  final Object? revokeError;

  @override
  Future<List<SkillConsent>> listConsents() async => listResult;

  @override
  Future<SkillConsent> grantSkillConsent({
    required String skillId,
    required List<String> grantedScopes,
    required String clientRequestId,
  }) async {
    final result = grantResult;
    if (result == null) {
      throw StateError('grant result was not configured');
    }
    return result;
  }

  @override
  Future<void> revokeSkillConsent({
    required String skillId,
    required String clientRequestId,
  }) async {
    final error = revokeError;
    if (error != null) {
      throw error;
    }
  }
}
