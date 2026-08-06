/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_remote.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_query_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/user_profile_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

const _personaManagementItem = <String, Object?>{
  'personaId': 'persona_1',
  'displayName': '摄影分身',
  'userHandle': 'photo-persona',
  'isolationLevel': 'open',
  'profileVisibility': 'public',
  'isPrimary': false,
  'isActive': false,
  'status': 'active',
  'inheritsProfileFromOwner': true,
  'overriddenProfileFields': <String>[],
  'updatedAt': '2026-07-20T00:00:00Z',
};

const _activePersonaContext = <String, Object?>{
  'ownerUserId': 'account-1',
  'personaId': 'persona_1',
  'subjectType': 'persona',
  'displayName': '摄影分身',
  'avatarUrl': '',
  'avatarVersion': 0,
  'isPrimary': false,
  'isolationLevel': 'open',
  'profileVisibility': 'public',
  'contextVersion': 1,
  'personaSnapshotVersion': 1,
  'sourceSurfaceId': 'profilePersonas',
  'explicitOverride': false,
  'switchedAt': '2026-07-20T12:00:00Z',
};

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountListPersonas,
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'items': <Object?>[_personaManagementItem],
    });
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetPersonaManagementSummary,
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'items': <Object?>[_personaManagementItem],
      'quota': <String, Object?>{
        'ownerUserId': 'account-1',
        'totalCount': 1,
        'quotaLimit': 5,
        'remainingCount': 4,
        'activePersonaId': 'persona_1',
        'primaryPersonaId': 'persona_1',
      },
      'activeContext': _activePersonaContext,
    });
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetActivePersonaContext,
          )) {
    return remoteApiPathJsonResponse(_activePersonaContext);
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard,
            pathParameters: const <String, String>{'personaId': 'persona_1'},
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'personaId': 'persona_1',
      'requestedAction': 'retire',
      'allowed': true,
      'reason': 'allowed',
      'requiresSuccessor': false,
    });
  }
  if (request.method == 'POST' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userPersonaCreatePersona,
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      ..._personaManagementItem,
      'displayName': request.body.isEmpty
          ? ''
          : (jsonDecode(request.body) as Map<String, dynamic>)['displayName'],
    });
  }
  if (request.method == 'PATCH' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userPersonaUpdatePersona,
            pathParameters: const <String, String>{'personaId': 'persona_1'},
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      ..._personaManagementItem,
      'displayName': '新分身名',
    });
  }
  if (request.method == 'POST' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userPersonaActivatePersona,
            pathParameters: const <String, String>{'personaId': 'persona_1'},
          )) {
    return remoteApiPathJsonResponse(_activePersonaContext);
  }
  if (request.method == 'POST' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userPersonaApplyPersonaProfileSync,
            pathParameters: const <String, String>{'personaId': 'persona_1'},
          )) {
    return remoteApiPathJsonResponse({
      'status': 'ok',
      'appliedCount': 1,
      'fieldsMask': <String>['phone', 'email'],
    });
  }
  if (request.method == 'POST' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userPersonaRetirePersona,
            pathParameters: const <String, String>{'personaId': 'persona_1'},
          )) {
    return remoteApiPathJsonResponse({
      'personaId': 'persona_1',
      'requestedAction': 'retire',
      'allowed': true,
      'reason': 'allowed',
      'requiresSuccessor': false,
    });
  }
  return remoteApiPathJsonResponse('{}');
}

void main() {
  group('PersonaQuery Remote — operations.yaml 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemotePersonaQuery repo;
    late RemotePersonaCommandWriter personaWriter;

    setUp(() {
      log = [];
      final generatedClient = buildRemoteApiPathOperationClient(
        log,
        responseFor: _responseFor,
      );
      final userProfileQuery = RemoteUserProfileQueryFacet(
        client: generatedClient,
        invocationContext: (clientPageId, _) {
          final surface =
              clientPageId == UserRequestPageIds.getActivePersonaContext
              ? AppUiSurfaces.appShell
              : AppUiSurfaces.profilePersonas;
          return CloudOperationInvocationContext(
            surfaceId: surface.id,
            routeId: surface.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(
              accountId: 'account-1',
              personaId: 'persona-1',
            ),
          );
        },
      );
      repo = RemotePersonaQuery(
        managementQuery: userProfileQuery,
        publicProfileQuery: userProfileQuery,
      );
      personaWriter = RemotePersonaCommandWriter(
        client: generatedClient,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.profilePersonas.id,
          routeId: AppUiSurfaces.profilePersonas.routeId,
          clientPageId: clientPageId,
          idempotencyKey: 'persona-path-contract-idempotency-key',
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
        ),
      );
    });

    test('listPersonas → GET /user/persona/personas', () async {
      await repo.listPersonas();
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.userUserAccountListPersonas,
        ),
      );
    });

    test(
      'getPersonaManagementSummary → GET /user/persona/personas/summary',
      () async {
        await repo.getPersonaManagementSummary();
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetPersonaManagementSummary,
          ),
        );
      },
    );

    test(
      'getActivePersonaContext → GET /user/persona/personas/active',
      () async {
        await repo.getActivePersonaContext();
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetActivePersonaContext,
          ),
        );
      },
    );

    test('createPersona → POST /user/persona/personas', () async {
      final result = await personaWriter.createPersona(
        CreatePersonaCommand(displayName: '摄影分身'),
      );
      expect(result.personaId, 'persona_1');
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        canonicalRemoteApiPath(AppCloudOperationIds.userPersonaCreatePersona),
      );
      expect(log.last.body['displayName'], '摄影分身');
    });

    test('updatePersona → PATCH /user/persona/personas/{id}', () async {
      final result = await personaWriter.updatePersona(
        UpdatePersonaCommand(personaId: 'persona_1', displayName: '新分身名'),
      );
      expect(result.displayName, '新分身名');
      expect(log.last.method, 'PATCH');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.userPersonaUpdatePersona,
          pathParameters: const <String, String>{'personaId': 'persona_1'},
        ),
      );
    });

    test(
      'activatePersona → POST /user/persona/personas/{id}/activate',
      () async {
        final result = await personaWriter.activatePersona(
          ActivatePersonaCommand(personaId: 'persona_1'),
        );
        expect(result.personaId, 'persona_1');
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.userPersonaActivatePersona,
            pathParameters: const <String, String>{'personaId': 'persona_1'},
          ),
        );
      },
    );

    test('Persona 移除单轨为 retire，不生成硬删除命令', () {
      final personaCommands = appCloudOperationContracts.values.where(
        (operation) =>
            operation.objectId == 'user.persona' && operation.kind == 'command',
      );
      expect(
        personaCommands.where((operation) => operation.method == 'DELETE'),
        isEmpty,
      );
      final retireOperation =
          appCloudOperationContracts[AppCloudOperationIds
              .userPersonaRetirePersona];
      expect(retireOperation, isNotNull);
      expect(
        retireOperation!.pathTemplate,
        canonicalRemoteApiOperation(
          AppCloudOperationIds.userPersonaRetirePersona,
        ).pathTemplate,
      );
    });

    test(
      'applyPersonaProfileSync → POST /user/persona/personas/{id}/profile-sync',
      () async {
        final result = await personaWriter.applyPersonaProfileSync(
          ApplyPersonaProfileSyncCommand(
            personaId: 'persona_1',
            applyScope: 'selected',
            fieldsMask: const <String>['phone', 'email'],
          ),
        );
        expect(result.appliedCount, 1);
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.userPersonaApplyPersonaProfileSync,
            pathParameters: const <String, String>{'personaId': 'persona_1'},
          ),
        );
      },
    );

    test(
      'getPersonaLifecycleGuard → GET /user/persona/personas/{id}/lifecycle-guard',
      () async {
        await repo.getPersonaLifecycleGuard('persona_1');
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard,
            pathParameters: const <String, String>{'personaId': 'persona_1'},
          ),
        );
      },
    );

    test('retirePersona → POST /user/persona/personas/{id}/retire', () async {
      final result = await personaWriter.retirePersona(
        RetirePersonaCommand(personaId: 'persona_1'),
      );
      expect(result.requestedAction, PersonaLifecycleAction.retire);
      expect(result.allowed, isTrue);
      expect(result.reason, PersonaLifecycleGuardReason.allowed);
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.userPersonaRetirePersona,
          pathParameters: const <String, String>{'personaId': 'persona_1'},
        ),
      );
    });
  });
}
