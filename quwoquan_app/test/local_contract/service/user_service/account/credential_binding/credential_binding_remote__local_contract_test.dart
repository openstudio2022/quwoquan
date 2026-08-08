// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-003
// readiness_case: credential_binding_bind_carrier_phone_credential_app_local
// readiness_case: credential_binding_bind_phone_credential_app_local
// readiness_case: credential_binding_complete_federated_phone_binding_app_local
// readiness_case: credential_binding_list_credentials_app_local
// readiness_case: credential_binding_unbind_credential_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/account/credential_binding/adapters/credential_binding_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  test(
    'CredentialBinding 五项 Facet 只经 generated client 且保持 exact wire/auth',
    () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final client = buildRemoteApiPathOperationClient(
        requests,
        responseFor: _responseFor,
      );
      final reader = RemoteCredentialBindingQuery(
        client: client,
        invocationContext: _invocationContext,
      );
      final writer = RemoteAppCredentialBindingCommandWriter(
        client: client,
        invocationContext: _invocationContext,
      );
      final publicWriter = RemoteAppCredentialBindingCommandWriter(
        client: buildRemoteApiPathOperationClient(
          requests,
          responseFor: _responseFor,
          authenticated: false,
        ),
        invocationContext: _invocationContext,
      );

      final carrier = await writer.bindCarrierPhoneCredential(
        BindCarrierPhoneCredentialCommand(
          vendor: ' aliyun ',
          carrierToken: ' carrier-token-opaque ',
          deviceId: ' device-1 ',
          platform: ' ios ',
          displayLabel: '138****0000',
        ),
      );
      final phone = await writer.bindPhoneCredential(
        BindPhoneCredentialCommand(
          phone: ' 13800000000 ',
          otpCode: ' 123456 ',
          displayLabel: '138****0000',
        ),
      );
      final session = await publicWriter.completeFederatedPhoneBinding(
        CompleteFederatedPhoneBindingCommand(
          bindingTicket: ' binding-ticket-1 ',
          phone: ' 13800000000 ',
          otpCode: ' 654321 ',
          challengeId: ' challenge-1 ',
          deviceId: ' device-1 ',
          platform: ' ios ',
          appVersion: ' 1.2.3 ',
          agreementVersion: ' agreement-current ',
          privacyVersion: ' privacy-current ',
        ),
      );
      final credentials = await reader.listCredentials(
        const ListCredentialsQuery(),
      );
      final unbound = await writer.unbindCredential(
        UnbindCredentialCommand(credentialType: ' carrier_phone '),
      );

      expect(carrier.credentialType, CredentialType.carrierPhone);
      expect(carrier.displayLabel, '138****0000');
      expect(carrier.version, greaterThan(0));
      expect(phone.credentialType, CredentialType.phone);
      expect(phone.displayLabel, '138****0000');
      expect(phone.version, greaterThan(0));
      expect(session.accessToken, isNotEmpty);
      expect(session.refreshToken, isNotEmpty);
      expect(session.ownerId, 'owner-1');
      expect(session.activePersona?.personaId, 'persona-1');
      expect(credentials.credentials, hasLength(2));
      expect(
        credentials.credentials.map((credential) => credential.id),
        everyElement(isNotEmpty),
      );
      expect(unbound.credentialType, CredentialType.carrierPhone);
      expect(unbound.isActive, isFalse);
      expect(unbound.version, greaterThan(0));

      expect(
        requests.map((request) => request.headers['X-Client-Operation-Id']),
        <String>[
          AppCloudOperationIds.userCredentialBindingBindCarrierPhoneCredential,
          AppCloudOperationIds.userCredentialBindingBindPhoneCredential,
          AppCloudOperationIds
              .userCredentialBindingCompleteFederatedPhoneBinding,
          AppCloudOperationIds.userCredentialBindingListCredentials,
          AppCloudOperationIds.userCredentialBindingUnbindCredential,
        ],
      );

      _expectRequest(
        requests[0],
        operationId: AppCloudOperationIds
            .userCredentialBindingBindCarrierPhoneCredential,
        method: 'POST',
        pathTemplate: '/owner/credentials/carrier-phone/bind',
        path: '/owner/credentials/carrier-phone/bind',
        authMode: 'required',
        actorRequirement: 'account',
        principal: 'account',
        ownershipPolicy: 'current_account_owner',
        clientPageId: UserRequestPageIds.bindCarrierPhoneCredential,
        body: <String, Object?>{
          'vendor': 'aliyun',
          'carrierToken': 'carrier-token-opaque',
          'deviceId': 'device-1',
          'platform': 'ios',
          'displayLabel': '138****0000',
        },
      );
      _expectRequest(
        requests[1],
        operationId:
            AppCloudOperationIds.userCredentialBindingBindPhoneCredential,
        method: 'POST',
        pathTemplate: '/owner/credentials/phone/bind',
        path: '/owner/credentials/phone/bind',
        authMode: 'required',
        actorRequirement: 'account',
        principal: 'account',
        ownershipPolicy: 'current_account_owner',
        clientPageId: UserRequestPageIds.bindPhoneCredential,
        body: <String, Object?>{
          'phone': '13800000000',
          'otpCode': '123456',
          'displayLabel': '138****0000',
        },
      );
      _expectRequest(
        requests[2],
        operationId: AppCloudOperationIds
            .userCredentialBindingCompleteFederatedPhoneBinding,
        method: 'POST',
        pathTemplate: '/auth/login/social/phone/complete',
        path: '/auth/login/social/phone/complete',
        authMode: 'public',
        actorRequirement: 'none',
        principal: 'public',
        ownershipPolicy: 'federated_phone_binding_ticket_holder',
        clientPageId: UserRequestPageIds.completeFederatedPhoneBinding,
        body: <String, Object?>{
          'bindingTicket': 'binding-ticket-1',
          'phone': '13800000000',
          'otpCode': '654321',
          'challengeId': 'challenge-1',
          'deviceId': 'device-1',
          'platform': 'ios',
          'appVersion': '1.2.3',
          'agreementVersion': 'agreement-current',
          'privacyVersion': 'privacy-current',
        },
      );
      _expectRequest(
        requests[3],
        operationId: AppCloudOperationIds.userCredentialBindingListCredentials,
        method: 'GET',
        pathTemplate: '/owner/credentials',
        path: '/owner/credentials',
        authMode: 'required',
        actorRequirement: 'account',
        principal: 'account',
        ownershipPolicy: 'current_account_owner',
        clientPageId: UserRequestPageIds.listCredentials,
      );
      _expectRequest(
        requests[4],
        operationId: AppCloudOperationIds.userCredentialBindingUnbindCredential,
        method: 'DELETE',
        pathTemplate: '/owner/credentials/{credentialType}',
        path: '/owner/credentials/carrier_phone',
        authMode: 'required',
        actorRequirement: 'account',
        principal: 'account',
        ownershipPolicy: 'current_account_owner',
        clientPageId: UserRequestPageIds.unbindCredential,
      );
    },
  );

  test('CredentialBinding response decoders 拒绝 SECRET/protected 字段', () {
    expect(
      () => decodeListCredentialsSlice(<String, Object?>{
        'credentials': <Object?>[
          <String, Object?>{
            'id': 'credential-phone-1',
            'credentialType': 'phone',
            'credentialKey': 'must-never-cross-wire',
            'displayLabel': '138****0000',
            'isActive': true,
            'boundAt': '2026-08-08T08:00:00Z',
            'version': 3,
          },
        ],
      }),
      throwsFormatException,
    );
    expect(
      () => decodeCredentialBindingCommandResult(<String, Object?>{
        'credentialType': 'phone',
        'isActive': true,
        'version': 3,
        'idempotentReplay': false,
        'ownerId': 'must-not-cross-command-receipt',
      }),
      throwsFormatException,
    );
    expect(
      () => decodeAuthSessionGrant(<String, Object?>{
        ..._authSessionResponse(),
        'bindingTicket': 'must-not-echo',
      }),
      throwsFormatException,
    );
  });
}

CloudOperationInvocationContext _invocationContext(String clientPageId) {
  final isPublic =
      clientPageId == UserRequestPageIds.completeFederatedPhoneBinding;
  return CloudOperationInvocationContext(
    surfaceId: isPublic ? 'login' : 'settingsAccountSecurity',
    clientPageId: clientPageId,
    actor: isPublic
        ? const CloudOperationActorContext()
        : const CloudOperationActorContext(accountId: 'account-1'),
  );
}

http.Response _responseFor(http.Request request) {
  final operationId = request.headers['X-Client-Operation-Id'];
  final response = switch (operationId) {
    AppCloudOperationIds.userCredentialBindingBindCarrierPhoneCredential =>
      <String, Object?>{
        'credentialType': 'carrier_phone',
        'isActive': true,
        'version': 2,
        'idempotentReplay': false,
        'displayLabel': '138****0000',
      },
    AppCloudOperationIds.userCredentialBindingBindPhoneCredential =>
      <String, Object?>{
        'credentialType': 'phone',
        'isActive': true,
        'version': 3,
        'idempotentReplay': false,
        'displayLabel': '138****0000',
      },
    AppCloudOperationIds.userCredentialBindingCompleteFederatedPhoneBinding =>
      _authSessionResponse(),
    AppCloudOperationIds.userCredentialBindingListCredentials =>
      <String, Object?>{
        'credentials': <Object?>[
          <String, Object?>{
            'id': 'credential-phone-1',
            'credentialType': 'phone',
            'displayLabel': '138****0000',
            'isActive': true,
            'boundAt': '2026-08-08T08:00:00Z',
            'version': 3,
          },
          <String, Object?>{
            'id': 'credential-carrier-1',
            'credentialType': 'carrier_phone',
            'displayLabel': '138****0000',
            'isActive': true,
            'boundAt': '2026-08-08T08:01:00Z',
            'version': 2,
          },
        ],
      },
    AppCloudOperationIds.userCredentialBindingUnbindCredential =>
      <String, Object?>{
        'credentialType': 'carrier_phone',
        'isActive': false,
        'version': 4,
        'idempotentReplay': false,
        'displayLabel': '138****0000',
      },
    _ => throw StateError(
      'unexpected credential binding operation '
      '$operationId',
    ),
  };
  return remoteApiPathJsonResponse(response);
}

Map<String, Object?> _authSessionResponse() => <String, Object?>{
  'accessToken': 'access-token',
  'refreshToken': 'refresh-token',
  'ownerId': 'owner-1',
  'accountState': 'active',
  'identityOrigin': 'federated_slot_a',
  'logicalShard': 7,
  'anonymousRetentionPolicy': 'retained',
  'personaCount': 1,
  'sessionRememberTtlSeconds': 2592000,
  'activePersona': <String, Object?>{'personaId': 'persona-1'},
};

void _expectRequest(
  CapturedRemoteApiPathRequest request, {
  required String operationId,
  required String method,
  required String pathTemplate,
  required String path,
  required String authMode,
  required String actorRequirement,
  required String principal,
  required String ownershipPolicy,
  required String clientPageId,
  Object? body,
}) {
  final operation = canonicalRemoteApiOperation(operationId);
  expect(operation.objectId, 'user.credential_binding');
  expect(operation.method, method);
  expect(operation.pathTemplate, pathTemplate);
  expect(operation.authMode, authMode);
  expect(operation.actorRequirement, actorRequirement);
  expect(operation.principal, principal);
  expect(operation.ownershipPolicy, ownershipPolicy);
  expect(operation.idempotency, 'none');
  expect(request.method, method);
  expect(request.path, path);
  expect(request.query, isEmpty);
  expect(request.body, body ?? const <String, Object?>{});
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: authMode == 'public' ? 'login' : 'settingsAccountSecurity',
    operationId: operationId,
  );
  expect(
    _header(request.headers, 'Authorization'),
    authMode == 'required' ? 'Bearer integration-contract-token' : isNull,
  );
  expect(_header(request.headers, 'Idempotency-Key'), isNull);
}

String? _header(Map<String, String> headers, String name) {
  final normalized = name.toLowerCase();
  for (final entry in headers.entries) {
    if (entry.key.toLowerCase() == normalized) return entry.value;
  }
  return null;
}
