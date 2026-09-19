import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String rehearsalOtpCode = '000000';
const String rehearsalIdentityOrigin = 'rehearsal_local';
const String rehearsalAssistantMarker = '【模拟】';

Never rehearsalUnsupported() =>
    throw contentCapabilityUnavailable('rehearsal_operation');

Object? cloneRehearsalValue(Object? value) {
  if (value is Map) {
    return _deepCopyMap(value);
  }
  if (value is List) {
    return <Object?>[for (final item in value) cloneRehearsalValue(item)];
  }
  return value;
}

Map<String, Object?> _deepCopyMap(Map<dynamic, dynamic> source) {
  final result = <String, Object?>{};
  for (final entry in source.entries) {
    result['${entry.key}'] = cloneRehearsalValue(entry.value);
  }
  return result;
}

Map<String, Object?> requestBodyMap(CloudOperationRequestPayload payload) {
  final body = payload.body;
  if (body is Map<String, Object?>) {
    return body;
  }
  if (body is Map) {
    return <String, Object?>{
      for (final entry in body.entries) '${entry.key}': entry.value,
    };
  }
  return const <String, Object?>{};
}

final class RehearsalRejected {
  const RehearsalRejected(this.error);
  final Object error;
}

Never rehearsalUnauthorized() {
  throw localDomainCloudException('USER.USER.unauthorized');
}

Never rehearsalNotFound(String code) {
  throw localDomainCloudException(code);
}

final class RehearsalInvocation {
  RehearsalInvocation({
    required this.operation,
    required this.payload,
    required this.context,
    required this.store,
    required this.now,
    required this.nextId,
    this.canonicalActorId,
  });

  final CloudOperationContract operation;
  final CloudOperationRequestPayload payload;
  final CloudOperationInvocationContext context;
  final AlphaRehearsalStore store;
  final DateTime Function() now;
  final String Function(String prefix) nextId;
  final String? canonicalActorId;

  String get actorId {
    final canonical = canonicalActorId?.trim() ?? '';
    if (canonical.isNotEmpty) {
      return canonical;
    }
    final persona = context.actor.personaId?.trim() ?? '';
    if (persona.isNotEmpty) {
      return persona;
    }
    return context.actor.accountId?.trim() ?? '';
  }

  void requireActor() {
    if (actorId.isEmpty) {
      rehearsalUnauthorized();
    }
  }

  Map<String, Object?> get body => requestBodyMap(payload);

  String path(String name) => payload.pathParameters[name] ?? '';

  String query(String name) => payload.queryParameters[name] ?? '';
}

abstract interface class RehearsalObjectHandler {
  Future<Object?> handle(RehearsalInvocation invocation);

  Stream<Object?>? stream(RehearsalInvocation invocation);
}
