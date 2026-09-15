// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/executor/rehearsal_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/handler_registry.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/user_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('真实 supported 与 explicit unsupported 完整划分 App contracts', () {
    final executor = AlphaRehearsalCloudOperationExecutor(
      store: AlphaRehearsalStore(persistence: MemoryRehearsalPersistence()),
    );
    final appContracts = appCloudOperationContracts.keys.toSet();
    final supported = executor.supportedCanonicalIds;
    final unsupported = executor.unsupportedCanonicalIds;

    expect(supported.intersection(unsupported), isEmpty);
    expect(supported.union(unsupported), appContracts);
    expect(supported.difference(appContracts), isEmpty);
    expect(unsupported.difference(appContracts), isEmpty);
    expect(supported, contains('gateway.persisted_query_execution.SearchPage'));
    expect(
      executor.transportCanonicalIds,
      contains(
        'gateway.persisted_query_execution.ExecutePersistedGraphQLQuery',
      ),
    );
    expect(
      supported,
      contains('assistant.assistant_run.StreamAssistantRunEvents'),
    );
  });

  test('registry 的 user 登记只能来自真实 supported 能力清单', () {
    const registry = AlphaRehearsalHandlerRegistry();
    for (final id in registry.supportedCanonicalIds.where(
      (id) => id.startsWith('user.'),
    )) {
      expect(
        userRehearsalCapabilities[id]?.status,
        UserRehearsalCapabilityStatus.supported,
        reason: id,
      );
    }
  });

  test('Subject 关注闭包的能力声明与 registry 可 dispatch 双向一致', () async {
    const registry = AlphaRehearsalHandlerRegistry();
    bool inScope(String id) =>
        id.startsWith('user.subject_follow.') ||
        id.startsWith('user.following_subject.');
    final declared = userRehearsalCapabilities.values
        .where(
          (capability) =>
              inScope(capability.canonicalOperationId) &&
              capability.status == UserRehearsalCapabilityStatus.supported,
        )
        .map((capability) => capability.canonicalOperationId)
        .toSet();
    expect(declared, {
      'user.subject_follow.FollowSubject',
      'user.subject_follow.UnfollowSubject',
      'user.following_subject.ListFollowingSubjects',
    });
    expect(registry.supportedCanonicalIds.where(inScope).toSet(), declared);
    expect(registry.unsupportedCanonicalIds.intersection(declared), isEmpty);
    final store = AlphaRehearsalStore(
      persistence: MemoryRehearsalPersistence(),
    );
    for (final id in declared) {
      await expectLater(
        registry.dispatch(
          RehearsalInvocation(
            operation: appCloudOperationContracts[id]!,
            payload: const CloudOperationRequestPayload(),
            context: const CloudOperationInvocationContext(
              surfaceId: 'alphaCoverage',
              clientPageId: 'alphaCoverage',
              actor: CloudOperationActorContext(),
            ),
            store: store,
            now: () => DateTime.utc(2026),
            nextId: store.nextId,
          ),
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.code,
            '未登录命中真实 handler 的鉴权，而非 unsupported',
            'USER.USER.unauthorized',
          ),
        ),
        reason: id,
      );
    }
  });

  test(
    'explicit unsupported inventory 逐项 typed capability unavailable',
    () async {
      const registry = AlphaRehearsalHandlerRegistry();
      final store = AlphaRehearsalStore(
        persistence: MemoryRehearsalPersistence(),
      );
      var sequence = 0;
      for (final canonicalId in registry.unsupportedCanonicalIds) {
        final operation = appCloudOperationContracts[canonicalId]!;
        await expectLater(
          registry.dispatch(
            RehearsalInvocation(
              operation: operation,
              payload: const CloudOperationRequestPayload(),
              context: const CloudOperationInvocationContext(
                surfaceId: 'alphaCoverage',
                clientPageId: 'alphaCoverage',
                actor: CloudOperationActorContext(),
              ),
              store: store,
              now: () => DateTime.utc(2026),
              nextId: (prefix) => '$prefix${sequence++}',
            ),
          ),
          throwsA(
            isA<CloudException>()
                .having(
                  (error) => error.runtimeFailure.semanticReason,
                  'semanticReason',
                  'content_source_capability_unavailable',
                )
                .having(
                  (error) => error.sourceOperationId,
                  'sourceOperationId',
                  canonicalId,
                ),
          ),
          reason: canonicalId,
        );
        await expectLater(
          registry.stream(
            RehearsalInvocation(
              operation: operation,
              payload: const CloudOperationRequestPayload(),
              context: const CloudOperationInvocationContext(
                surfaceId: 'alphaCoverage',
                clientPageId: 'alphaCoverage',
                actor: CloudOperationActorContext(),
              ),
              store: store,
              now: () => DateTime.utc(2026),
              nextId: (prefix) => '$prefix${sequence++}',
            ),
          ),
          emitsError(
            isA<CloudException>()
                .having(
                  (error) => error.runtimeFailure.semanticReason,
                  'semanticReason',
                  'content_source_capability_unavailable',
                )
                .having(
                  (error) => error.sourceOperationId,
                  'sourceOperationId',
                  canonicalId,
                ),
          ),
          reason: '$canonicalId stream',
        );
      }
    },
  );
}
