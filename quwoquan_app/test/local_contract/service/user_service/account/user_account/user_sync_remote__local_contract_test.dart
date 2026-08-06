// spec_ref: specs/feature-tree/user-identity-profile-relationship/user-service-cloud-delivery/remote-profile-delivery/spec.md#gwt-001
// readiness_case: user_account_pull_user_sync_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/user_sync_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'PullUserSync 只经 generated request/response 单轨并保留 typed union',
    () async {
      final executor = _UserSyncExecutor(response: _validResponse());
      final repository = RemoteUserSyncRepository(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.chatList.id,
          routeId: AppUiSurfaces.chatList.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
        ),
      );

      final result = await repository.pull(afterSeq: 7, limit: 20);

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.userUserAccountPullUserSync,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.chatList.id);
      expect(executor.request?.body, <String, Object?>{
        'afterSeq': 7,
        'limit': 20,
      });
      expect(result.latestSyncSeq, 8);
      expect(result.patches.single.kind, UserSyncPatchKind.userAvatarUpdated);
      expect(result.patches.single.userAvatarUpdated?.userId, 'user-2');
      expect(result.patches.single.conversationAvatarUpdated, isNull);
    },
  );

  test('PullUserSync generated decoder 对未知 wire 字段 fail closed', () async {
    final response = _validResponse()..['legacyPatches'] = const <Object?>[];
    final repository = RemoteUserSyncRepository(
      client: GeneratedCloudOperationClient(
        _UserSyncExecutor(response: response),
      ),
      invocationContext: (clientPageId) => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.chatList.id,
        routeId: AppUiSurfaces.chatList.routeId,
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(accountId: 'account-1'),
      ),
    );

    await expectLater(
      repository.pull(afterSeq: 7),
      throwsA(isA<FormatException>()),
    );
  });
}

Map<String, Object?> _validResponse() => <String, Object?>{
  'patches': <Object?>[
    <String, Object?>{
      'syncSeq': 8,
      'kind': 'user_avatar_updated',
      'userAvatarUpdated': <String, Object?>{
        'userId': 'user-2',
        'avatarUrl': 'media/avatar/user-2/current/profile.png',
        'avatarVersion': 4,
      },
      'occurredAt': '2026-08-04T00:00:00Z',
    },
  ],
  'latestSyncSeq': 8,
  'hasMore': false,
  'requiresResync': false,
};

final class _UserSyncExecutor implements CloudOperationExecutor {
  _UserSyncExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  CloudOperationRequestPayload? request;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    request = requestEncoder();
    return responseDecoder(response);
  }
}
