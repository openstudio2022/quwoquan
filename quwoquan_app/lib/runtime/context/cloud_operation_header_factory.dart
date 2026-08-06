import 'dart:math';

import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class CloudOperationHeaderFactory {
  CloudOperationHeaderFactory({
    required this.clientContextProvider,
    DateTime Function()? now,
    int Function()? entropy,
  }) : _now = now ?? DateTime.now,
       _entropy = entropy ?? (() => Random().nextInt(36 * 36 * 36 * 36));

  final CloudClientContextProvider clientContextProvider;
  final DateTime Function() _now;
  final int Function() _entropy;

  Map<String, String> build({
    required CloudOperationContract operation,
    required CloudOperationInvocationContext invocation,
    DateTime? effectiveDeadlineAt,
  }) {
    final client = clientContextProvider.snapshot();
    final now = _now();
    if (client.sessionId.trim().isEmpty ||
        client.platform.trim().isEmpty ||
        client.appVersion.trim().isEmpty ||
        client.locale.trim().isEmpty) {
      throw StateError('Cloud client context is incomplete');
    }
    _validate(
      operation,
      invocation,
      client: client,
      now: now,
      effectiveDeadlineAt: effectiveDeadlineAt,
    );
    final timestamp = now.microsecondsSinceEpoch.toRadixString(36);
    final random = _entropy().toRadixString(36);
    final traceId =
        'APP.${client.sessionId}.${invocation.surfaceId}.'
        '${operation.canonicalOperationId}.$timestamp.$random';
    final requestId =
        'APP.${invocation.surfaceId}.${operation.canonicalOperationId}.'
        '$timestamp.$random';
    final accountId = invocation.actor.accountId?.trim() ?? '';
    final personaId = invocation.actor.personaId?.trim() ?? '';
    final deviceActorId =
        invocation.actor.deviceActorId?.trim().isNotEmpty == true
        ? invocation.actor.deviceActorId!.trim()
        : client.deviceActorId?.trim() ?? '';
    final disclosedActors = _disclosedActors(
      operation.actorRequirement,
      accountId: accountId,
      personaId: personaId,
      deviceActorId: deviceActorId,
    );
    final deadlineAt = effectiveDeadlineAt ?? invocation.deadlineAt;
    final headers = <String, String>{
      'X-Client-Page-Id': invocation.clientPageId.trim(),
      'X-Client-Surface-Id': invocation.surfaceId.trim(),
      'X-Client-Operation-Id': operation.canonicalOperationId,
      if ((invocation.routeId ?? '').trim().isNotEmpty)
        'X-Client-Route-Id': invocation.routeId!.trim(),
      'X-Client-Session-Id': client.sessionId,
      ...disclosedActors,
      if ((invocation.referralSource ?? '').trim().isNotEmpty)
        'X-Referral-Source': invocation.referralSource!.trim(),
      if ((invocation.feedRequestId ?? '').trim().isNotEmpty)
        'X-Feed-Request-Id': invocation.feedRequestId!.trim(),
      if ((invocation.shareId ?? '').trim().isNotEmpty)
        'X-Share-Id': invocation.shareId!.trim(),
      if ((invocation.modelId ?? '').trim().isNotEmpty)
        'X-Model-Id': invocation.modelId!.trim(),
      if ((invocation.experimentBucket ?? '').trim().isNotEmpty)
        'X-Experiment-Bucket': invocation.experimentBucket!.trim(),
      if ((invocation.idempotencyKey ?? '').trim().isNotEmpty)
        'Idempotency-Key': invocation.idempotencyKey!.trim(),
      if (deadlineAt != null)
        'X-Client-Deadline-At': deadlineAt.toUtc().toIso8601String(),
      'X-Client-Sent-At': now.toUtc().toIso8601String(),
      'X-Client-Device-Platform': client.platform,
      'X-Client-App-Version': client.appVersion,
      'X-Client-Locale': client.locale,
      'X-Trace-Id': traceId,
      'X-Request-Id': requestId,
    };
    for (final entry in headers.entries) {
      if (entry.value.contains('\r') || entry.value.contains('\n')) {
        throw ArgumentError.value(
          entry.value,
          entry.key,
          'Cloud operation header values cannot contain CR/LF',
        );
      }
    }
    return headers;
  }

  void _validate(
    CloudOperationContract operation,
    CloudOperationInvocationContext invocation, {
    required CloudClientContextSnapshot client,
    required DateTime now,
    DateTime? effectiveDeadlineAt,
  }) {
    final surfaceId = invocation.surfaceId.trim();
    if (!operation.surfaceIds.contains(surfaceId)) {
      throw ArgumentError.value(
        surfaceId,
        'surfaceId',
        'Surface is not bound to ${operation.canonicalOperationId}',
      );
    }
    if (invocation.clientPageId.trim().isEmpty) {
      throw ArgumentError.value(
        invocation.clientPageId,
        'clientPageId',
        'Client page id is required',
      );
    }
    final hasAccount = (invocation.actor.accountId ?? '').trim().isNotEmpty;
    final hasPersona = (invocation.actor.personaId ?? '').trim().isNotEmpty;
    final hasDevice =
        (invocation.actor.deviceActorId ?? '').trim().isNotEmpty ||
        (client.deviceActorId ?? '').trim().isNotEmpty;
    final actorSatisfied = switch (operation.actorRequirement) {
      'none' => true,
      'account' => hasAccount,
      'persona' => hasPersona,
      'device' => hasDevice,
      'personaOrDevice' || 'persona_or_device' => hasPersona || hasDevice,
      _ => false,
    };
    if (!actorSatisfied) {
      throw ArgumentError(
        '${operation.canonicalOperationId} requires '
        '${operation.actorRequirement} actor',
      );
    }
    final deadline = effectiveDeadlineAt ?? invocation.deadlineAt;
    if (deadline != null && !deadline.isAfter(now)) {
      throw ArgumentError.value(
        deadline,
        'deadlineAt',
        'Operation deadline must be in the future',
      );
    }
  }

  Map<String, String> _disclosedActors(
    String actorRequirement, {
    required String accountId,
    required String personaId,
    required String deviceActorId,
  }) {
    return switch (actorRequirement) {
      'none' => const <String, String>{},
      'account' => <String, String>{
        if (accountId.isNotEmpty) 'X-Client-Account-Id': accountId,
      },
      'persona' => <String, String>{
        if (personaId.isNotEmpty) 'X-Client-Persona-Id': personaId,
      },
      'device' => <String, String>{
        if (deviceActorId.isNotEmpty) 'X-Client-Device-Actor-Id': deviceActorId,
      },
      'personaOrDevice' || 'persona_or_device' =>
        personaId.isNotEmpty
            ? <String, String>{'X-Client-Persona-Id': personaId}
            : <String, String>{
                if (deviceActorId.isNotEmpty)
                  'X-Client-Device-Actor-Id': deviceActorId,
              },
      _ => const <String, String>{},
    };
  }
}
