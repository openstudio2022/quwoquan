// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-001
// readiness_case: persona_create_persona_app_local
// readiness_case: persona_update_persona_app_local
// readiness_case: persona_apply_persona_profile_sync_app_local
// readiness_case: persona_retire_persona_app_local
// readiness_case: persona_activate_persona_app_local
// readiness_case: persona_update_user_profile_app_local
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  group('RemotePersonaCommandWriter generated HTTP readiness', () {
    test('六项 command 精确走 production Remote，503 重试复用同一幂等意图', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final attempts = <String, int>{};
      final remote = _remote(
        requests,
        responseFor: (request) {
          final operationId = _requiredHeader(
            request.headers,
            'X-Client-Operation-Id',
          );
          final attempt = attempts.update(
            operationId,
            (value) => value + 1,
            ifAbsent: () => 1,
          );
          if (attempt == 1) {
            return http.Response(
              jsonEncode(<String, Object?>{
                'code': UserErrorCode.internalError.code,
                'message': 'user dependency unavailable',
              }),
              503,
              headers: const <String, String>{
                'content-type': 'application/json',
                'retry-after': '0',
              },
            );
          }
          return _successResponse(operationId);
        },
      );

      final created = await remote.createPersona(_createCommand());
      final updated = await remote.updatePersona(_updateCommand());
      final synced = await remote.applyPersonaProfileSync(_syncCommand());
      final retired = await remote.retirePersona(_retireCommand());
      final activated = await remote.activatePersona(_activateCommand());
      final profile = await remote.updateUserProfile(_profileCommand());

      expect(created.personaId, _personaId);
      expect(created.displayName, '摄影分身');
      expect(created.userHandle, 'photo-persona');
      expect(created.status, PersonaStatus.active);
      expect(updated.personaId, _personaId);
      expect(updated.displayName, '更新后的摄影分身');
      expect(updated.bio, '保留真实摄影经历');
      expect(synced.status, 'applied');
      expect(synced.appliedCount, 2);
      expect(synced.fieldsMask, <String>['displayName', 'bio']);
      expect(retired.personaId, _personaId);
      expect(retired.allowed, isTrue);
      expect(retired.reason, PersonaLifecycleGuardReason.allowed);
      expect(activated.ownerUserId, 'account-1');
      expect(activated.personaId, _personaId);
      expect(activated.displayName, '摄影分身');
      expect(profile.userId, 'account-1');
      expect(profile.nickname, '旅行摄影者');
      expect(profile.profileVersion, 8);
      expect(profile.bio, '持续记录真实旅程');
      expect(profile.regionTagRef, _regionTagRef);
      expect(profile.identityTags, <String>['旅行摄影', '城市漫步']);

      expect(attempts, <String, int>{
        for (final contractCase in _contractCases) contractCase.operationId: 2,
      });
      for (final contractCase in _contractCases) {
        final operationRequests = requests
            .where(
              (request) =>
                  _header(request.headers, 'X-Client-Operation-Id') ==
                  contractCase.operationId,
            )
            .toList(growable: false);
        expect(
          operationRequests,
          hasLength(2),
          reason: contractCase.operationId,
        );
        _expectRequest(operationRequests[0], contractCase, attempt: 1);
        _expectRequest(operationRequests[1], contractCase, attempt: 2);
        expect(
          _header(operationRequests[0].headers, 'Idempotency-Key'),
          _header(operationRequests[1].headers, 'Idempotency-Key'),
          reason: '${contractCase.operationId} retry intent must be stable',
        );
      }
    });

    for (final failureCase in _failureCases) {
      test(
        '${failureCase.operationId} canonical failure 保留 code/status/operation',
        () async {
          final requests = <CapturedRemoteApiPathRequest>[];
          final remote = _remote(
            requests,
            responseFor: (_) => remoteApiPathJsonResponse(<String, Object?>{
              'code': UserErrorCode.invalidArgument.code,
              'message': 'invalid persona command',
              'requestId': 'request-persona-invalid',
              'traceId': 'trace-persona-invalid',
            }, statusCode: UserErrorCode.invalidArgument.httpStatus),
          );

          await expectLater(
            failureCase.invoke(remote),
            throwsA(
              isA<CloudException>()
                  .having(
                    (error) => error.code,
                    'code',
                    UserErrorCode.invalidArgument.code,
                  )
                  .having(
                    (error) => error.statusCode,
                    'statusCode',
                    UserErrorCode.invalidArgument.httpStatus,
                  )
                  .having(
                    (error) => error.sourceOperationId,
                    'sourceOperationId',
                    failureCase.operationId,
                  ),
            ),
          );
          expect(requests, hasLength(1));
        },
      );

      test(
        '${failureCase.operationId} malformed 2xx response fail-closed',
        () async {
          final requests = <CapturedRemoteApiPathRequest>[];
          final remote = _remote(
            requests,
            responseFor: (_) => remoteApiPathJsonResponse(
              const <String, Object?>{'unexpected': 'shape'},
            ),
          );

          await expectLater(
            failureCase.invoke(remote),
            throwsA(
              isA<CloudException>().having(
                (error) => error.type,
                'type',
                CloudErrorType.invalidResponse,
              ),
            ),
          );
          expect(requests, hasLength(1));
        },
      );
    }
  });
}

const String _personaId = 'persona-1';
const String _regionTagRef = 'Topic/地理/行政区/中国/广东省/深圳市';

final List<_PersonaContractCase> _contractCases = <_PersonaContractCase>[
  _PersonaContractCase(
    operationId: AppCloudOperationIds.userPersonaCreatePersona,
    clientPageId: UserRequestPageIds.createPersona,
    method: 'POST',
    path: '/user/personas',
    surfaceId: AppUiSurfaces.profilePersonas.id,
    body: const <String, Object?>{
      'displayName': '摄影分身',
      'avatarUrl': 'https://cdn.example.com/persona.jpg',
      'isolationLevel': 'open',
      'purposeHint': 'travel_photography',
    },
  ),
  _PersonaContractCase(
    operationId: AppCloudOperationIds.userPersonaUpdatePersona,
    clientPageId: UserRequestPageIds.updatePersona,
    method: 'PATCH',
    path: '/user/personas/persona-1',
    surfaceId: AppUiSurfaces.profilePersonas.id,
    body: const <String, Object?>{
      'displayName': '更新后的摄影分身',
      'backgroundUrl': 'https://cdn.example.com/persona-background.jpg',
      'isolationLevel': 'strict',
      'purposeHint': 'documented_travel',
      'applyScope': 'selected',
      'syncTargetIds': <String>['persona-2'],
      'fieldsMask': <String>['displayName', 'bio'],
    },
  ),
  _PersonaContractCase(
    operationId: AppCloudOperationIds.userPersonaApplyPersonaProfileSync,
    clientPageId: UserRequestPageIds.applyPersonaProfileSync,
    method: 'POST',
    path: '/user/personas/persona-1/profile-sync',
    surfaceId: AppUiSurfaces.profilePersonas.id,
    body: const <String, Object?>{
      'applyScope': 'selected',
      'syncTargetIds': <String>['persona-2'],
      'fieldsMask': <String>['displayName', 'bio'],
    },
  ),
  _PersonaContractCase(
    operationId: AppCloudOperationIds.userPersonaRetirePersona,
    clientPageId: UserRequestPageIds.retirePersona,
    method: 'POST',
    path: '/user/personas/persona-1/retire',
    surfaceId: AppUiSurfaces.profilePersonas.id,
  ),
  _PersonaContractCase(
    operationId: AppCloudOperationIds.userPersonaActivatePersona,
    clientPageId: UserRequestPageIds.activatePersona,
    method: 'POST',
    path: '/user/personas/persona-1/activate',
    surfaceId: AppUiSurfaces.profilePersonas.id,
  ),
  _PersonaContractCase(
    operationId: AppCloudOperationIds.userPersonaUpdateUserProfile,
    clientPageId: UserRequestPageIds.updateUserProfile,
    method: 'PATCH',
    path: '/user/profile',
    surfaceId: AppUiSurfaces.profileEdit.id,
    body: const <String, Object?>{
      'nickname': '旅行摄影者',
      'bio': '持续记录真实旅程',
      'gender': 'unspecified',
      'birthDate': '1995-01-02',
      'regionTagRef': _regionTagRef,
      'identityTags': <String>['旅行摄影', '城市漫步'],
      'profileVisibility': 'public',
      'applyScope': 'current_persona',
      'fieldsMask': <String>['nickname', 'bio', 'regionTagRef'],
    },
  ),
];

final List<
  ({
    String operationId,
    Future<Object> Function(RemotePersonaCommandWriter remote) invoke,
  })
>
_failureCases =
    <
      ({
        String operationId,
        Future<Object> Function(RemotePersonaCommandWriter remote) invoke,
      })
    >[
      (
        operationId: AppCloudOperationIds.userPersonaCreatePersona,
        invoke: (remote) => remote.createPersona(_createCommand()),
      ),
      (
        operationId: AppCloudOperationIds.userPersonaUpdatePersona,
        invoke: (remote) => remote.updatePersona(_updateCommand()),
      ),
      (
        operationId: AppCloudOperationIds.userPersonaApplyPersonaProfileSync,
        invoke: (remote) => remote.applyPersonaProfileSync(_syncCommand()),
      ),
      (
        operationId: AppCloudOperationIds.userPersonaRetirePersona,
        invoke: (remote) => remote.retirePersona(_retireCommand()),
      ),
      (
        operationId: AppCloudOperationIds.userPersonaActivatePersona,
        invoke: (remote) => remote.activatePersona(_activateCommand()),
      ),
      (
        operationId: AppCloudOperationIds.userPersonaUpdateUserProfile,
        invoke: (remote) => remote.updateUserProfile(_profileCommand()),
      ),
    ];

RemotePersonaCommandWriter _remote(
  List<CapturedRemoteApiPathRequest> requests, {
  required RemoteApiPathResponseFactory responseFor,
}) {
  return RemotePersonaCommandWriter(
    client: buildRemoteApiPathOperationClient(
      requests,
      responseFor: responseFor,
    ),
    invocationContext: (clientPageId) {
      final surface = clientPageId == UserRequestPageIds.updateUserProfile
          ? AppUiSurfaces.profileEdit
          : AppUiSurfaces.profilePersonas;
      return CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        idempotencyKey: 'persona-$clientPageId-intent',
        actor: const CloudOperationActorContext(
          accountId: 'account-1',
          personaId: _personaId,
        ),
      );
    },
  );
}

CreatePersonaCommand _createCommand() => CreatePersonaCommand(
  displayName: ' 摄影分身 ',
  avatarUrl: 'https://cdn.example.com/persona.jpg',
  isolationLevel: 'open',
  purposeHint: 'travel_photography',
);

UpdatePersonaCommand _updateCommand() => UpdatePersonaCommand(
  personaId: ' $_personaId ',
  displayName: '更新后的摄影分身',
  backgroundUrl: 'https://cdn.example.com/persona-background.jpg',
  isolationLevel: 'strict',
  purposeHint: 'documented_travel',
  applyScope: 'selected',
  syncTargetIds: const <String>['persona-2'],
  fieldsMask: const <String>['displayName', 'bio'],
);

ApplyPersonaProfileSyncCommand _syncCommand() => ApplyPersonaProfileSyncCommand(
  personaId: ' $_personaId ',
  applyScope: ' selected ',
  syncTargetIds: const <String>['persona-2'],
  fieldsMask: const <String>['displayName', 'bio'],
);

RetirePersonaCommand _retireCommand() =>
    RetirePersonaCommand(personaId: ' $_personaId ');

ActivatePersonaCommand _activateCommand() =>
    ActivatePersonaCommand(personaId: ' $_personaId ');

UpdateUserProfileCommand _profileCommand() => UpdateUserProfileCommand(
  nickname: '旅行摄影者',
  bio: '持续记录真实旅程',
  gender: 'unspecified',
  birthDate: '1995-01-02',
  regionTagRef: _regionTagRef,
  identityTags: const <String>['旅行摄影', '城市漫步'],
  profileVisibility: 'public',
  applyScope: 'current_persona',
  fieldsMask: const <String>['nickname', 'bio', 'regionTagRef'],
);

http.Response _successResponse(String operationId) {
  final Object body = switch (operationId) {
    AppCloudOperationIds.userPersonaCreatePersona => _personaItem(
      displayName: '摄影分身',
    ),
    AppCloudOperationIds.userPersonaUpdatePersona => _personaItem(
      displayName: '更新后的摄影分身',
      bio: '保留真实摄影经历',
    ),
    AppCloudOperationIds.userPersonaApplyPersonaProfileSync =>
      const <String, Object?>{
        'status': 'applied',
        'appliedCount': 2,
        'fieldsMask': <String>['displayName', 'bio'],
      },
    AppCloudOperationIds.userPersonaRetirePersona => const <String, Object?>{
      'personaId': _personaId,
      'requestedAction': 'retire',
      'allowed': true,
      'reason': 'allowed',
      'requiresSuccessor': false,
    },
    AppCloudOperationIds.userPersonaActivatePersona => _activePersonaContext,
    AppCloudOperationIds.userPersonaUpdateUserProfile =>
      const <String, Object?>{
        'userId': 'account-1',
        'nickname': '旅行摄影者',
        'nicknameCustomized': true,
        'profileVersion': 8,
        'avatarVersion': 3,
        'bio': '持续记录真实旅程',
        'identityTags': <String>['旅行摄影', '城市漫步'],
        'gender': 'unspecified',
        'birthDate': '1995-01-02T00:00:00Z',
        'region': '广东 深圳',
        'regionTagRef': _regionTagRef,
        'status': 'active',
        'updatedAt': '2026-08-09T00:00:00Z',
      },
    _ => throw StateError('unexpected Persona operation: $operationId'),
  };
  return remoteApiPathJsonResponse(body);
}

Map<String, Object?> _personaItem({required String displayName, String? bio}) =>
    <String, Object?>{
      'personaId': _personaId,
      'displayName': displayName,
      'userHandle': 'photo-persona',
      'avatarUrl': 'https://cdn.example.com/persona.jpg',
      'backgroundUrl': 'https://cdn.example.com/persona-background.jpg',
      'bio': bio,
      'isolationLevel': 'open',
      'isPrimary': false,
      'isActive': false,
      'status': 'active',
      'retiredAt': null,
      'inheritsProfileFromOwner': false,
      'overriddenProfileFields': <String>['displayName', 'bio'],
      'lastProfileSyncAt': '2026-08-09T00:00:00Z',
      'lastProfileSyncSource': 'persona_management',
      'profileVisibility': 'public',
      'purposeHint': 'travel_photography',
      'updatedAt': '2026-08-09T00:00:00Z',
      'lastActivatedAt': null,
    };

const Map<String, Object?> _activePersonaContext = <String, Object?>{
  'ownerUserId': 'account-1',
  'personaId': _personaId,
  'subjectType': 'persona',
  'displayName': '摄影分身',
  'avatarUrl': 'https://cdn.example.com/persona.jpg',
  'avatarVersion': 3,
  'isPrimary': false,
  'isolationLevel': 'open',
  'profileVisibility': 'public',
  'contextVersion': 8,
  'personaSnapshotVersion': 5,
  'sourceSurfaceId': 'profilePersonas',
  'explicitOverride': true,
  'switchedAt': '2026-08-09T00:00:00Z',
};

void _expectRequest(
  CapturedRemoteApiPathRequest request,
  _PersonaContractCase contractCase, {
  required int attempt,
}) {
  expect(request.method, contractCase.method);
  expect(request.path, contractCase.path);
  expect(request.query, isEmpty);
  expect(request.body, contractCase.body);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: contractCase.clientPageId,
    surfaceId: contractCase.surfaceId,
    operationId: contractCase.operationId,
  );
  expect(
    _requiredHeader(request.headers, 'Authorization'),
    'Bearer integration-contract-token',
  );
  expect(
    _requiredHeader(request.headers, 'Idempotency-Key'),
    'persona-${contractCase.clientPageId}-intent',
  );
  expect(_requiredHeader(request.headers, 'X-Client-Attempt'), '$attempt');
}

String _requiredHeader(Map<String, String> headers, String name) {
  final value = _header(headers, name);
  if (value == null || value.isEmpty) {
    throw StateError('missing header $name');
  }
  return value;
}

String? _header(Map<String, String> headers, String name) {
  final normalized = name.toLowerCase();
  for (final entry in headers.entries) {
    if (entry.key.toLowerCase() == normalized) {
      return entry.value;
    }
  }
  return null;
}

final class _PersonaContractCase {
  const _PersonaContractCase({
    required this.operationId,
    required this.clientPageId,
    required this.method,
    required this.path,
    required this.surfaceId,
    this.body = const <String, Object?>{},
  });

  final String operationId;
  final String clientPageId;
  final String method;
  final String path;
  final String surfaceId;
  final Map<String, Object?> body;
}
