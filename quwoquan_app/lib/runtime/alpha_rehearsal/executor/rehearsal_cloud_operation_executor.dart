import 'dart:async';
import 'dart:convert';

import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/handler_registry.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_identity.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class AlphaRehearsalCloudOperationExecutor
    implements CloudOperationExecutor, CloudOperationStreamExecutor {
  AlphaRehearsalCloudOperationExecutor({
    required this.store,
    AlphaRehearsalIdentityOwner? identityOwner,
    AlphaRehearsalHandlerRegistry? registry,
    DateTime Function()? now,
  }) : identityOwner = identityOwner ?? AlphaRehearsalIdentityOwner(store),
       registry = registry ?? const AlphaRehearsalHandlerRegistry(),
       _now = now ?? DateTime.now;

  final AlphaRehearsalStore store;
  final AlphaRehearsalIdentityOwner identityOwner;
  final AlphaRehearsalHandlerRegistry registry;
  final DateTime Function() _now;
  bool _disposed = false;

  void dispose() {
    _disposed = true;
  }

  void _requireActive() {
    if (_disposed) rehearsalUnsupported();
  }

  Set<String> get supportedCanonicalIds => registry.supportedCanonicalIds;
  Set<String> get unsupportedCanonicalIds => registry.unsupportedCanonicalIds;
  Set<String> get transportCanonicalIds => registry.transportCanonicalIds;
  Set<String> get coveredCanonicalIds => registry.coveredCanonicalIds;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    _requireActive();
    throwIfCloudOperationInterrupted(
      cancellation: context.cancellation,
      deadlineAt: context.deadlineAt,
    );
    _enforceAuth(operation, context);
    final payload = requestEncoder();
    final actor =
        identityOwner.canonicalPersonaId(
          accountId: context.actor.accountId,
          personaId: context.actor.personaId,
        ) ??
        'device:${context.actor.deviceActorId ?? 'guest'}';
    final fence = store.captureFence(actor);
    void check() {
      _requireActive();
      fence();
      throwIfCloudOperationInterrupted(
        cancellation: context.cancellation,
        deadlineAt: context.deadlineAt,
        now: _now,
      );
    }

    final requestKey = context.idempotencyKey?.trim() ?? '';
    final key = jsonEncode([actor, operation.canonicalOperationId, requestKey]);
    final outcome = await store.commit<Object?>(() async {
      check();
      _enforceKnownActor(operation, context);
      final replayed = requestKey.isEmpty
          ? null
          : store.idempotentResponse(key);
      if (replayed != null) {
        return _decode(operation, responseDecoder, replayed['response']);
      }
      final invocation = RehearsalInvocation(
        operation: operation,
        payload: payload,
        context: context,
        store: store,
        now: _now,
        nextId: store.nextId,
        canonicalActorId: actor,
      );
      final wire = await registry.dispatch(invocation);
      check();
      if (wire is RehearsalRejected) return wire;
      final result = _decode(operation, responseDecoder, wire);
      if (requestKey.isNotEmpty) {
        store.idempotency[key] = {'response': cloneRehearsalValue(wire)};
      }
      if (operation.kind == 'command') {
        store.events.add({
          'eventId': store.nextId('event_'),
          'actorId': actor,
          'operation': operation.canonicalOperationId,
          'spaceGeneration': store.spaceGeneration,
        });
      }
      return result;
    }, beforeCommit: check);
    if (outcome is RehearsalRejected) throw outcome.error;
    return outcome as TResponse;
  }

  @override
  Stream<TResponse> stream<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async* {
    _requireActive();
    throwIfCloudOperationInterrupted(
      cancellation: context.cancellation,
      deadlineAt: context.deadlineAt,
    );
    _enforceAuth(operation, context);
    final payload = requestEncoder();
    await store.ensureLoaded();
    _enforceKnownActor(operation, context);
    final invocation = RehearsalInvocation(
      operation: operation,
      payload: payload,
      context: context,
      store: store,
      now: _now,
      nextId: store.nextId,
    );
    final streamed = registry.stream(invocation);
    if (streamed != null) {
      await for (final event in streamed) {
        throwIfCloudOperationInterrupted(
          cancellation: context.cancellation,
          deadlineAt: context.deadlineAt,
        );
        yield _decode(operation, responseDecoder, event);
      }
      return;
    }
    rehearsalUnsupported();
  }

  TResponse _decode<TResponse>(
    CloudOperationContract operation,
    CloudOperationResponseDecoder<TResponse> responseDecoder,
    Object? wire,
  ) {
    if (operation.responseEntity.trim().isEmpty) {
      return responseDecoder(null);
    }
    return responseDecoder(wire);
  }

  void _enforceKnownActor(
    CloudOperationContract operation,
    CloudOperationInvocationContext context,
  ) {
    if (operation.authMode != 'required') return;
    final account = context.actor.accountId?.trim() ?? '';
    final persona = context.actor.personaId?.trim() ?? '';
    final known = identityOwner.knowsActor(
      accountId: account,
      personaId: persona,
    );
    if (!known) rehearsalUnauthorized();
  }

  void _enforceAuth(
    CloudOperationContract operation,
    CloudOperationInvocationContext context,
  ) {
    if (operation.authMode != 'required') {
      return;
    }
    final persona = context.actor.personaId?.trim() ?? '';
    final account = context.actor.accountId?.trim() ?? '';
    if (persona.isEmpty && account.isEmpty) {
      throw localDomainCloudException('USER.USER.unauthorized');
    }
  }
}
