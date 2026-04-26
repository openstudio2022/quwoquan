import 'package:quwoquan_runtime_errors/src/runtime_failure_context.dart';
import 'package:quwoquan_runtime_errors/src/runtime_failure_location.dart';

enum RuntimeFailureOrigin {
  user,
  environment,
  localClient,
  remoteDependency,
  system,
  developer,
}

enum RuntimeFailureKind {
  validation,
  contract,
  permission,
  auth,
  network,
  rateLimited,
  unavailable,
  timeout,
  notFound,
  unsupported,
  cancelled,
  storage,
  parsing,
  model,
  internal,
}

enum RuntimeFailureNature {
  transient,
  permanent,
  requiresUserAction,
  requiresPermission,
  bug,
}

abstract interface class RuntimeFailureBase {
  String get code;
  RuntimeFailureOrigin get origin;
  RuntimeFailureKind get kind;
  RuntimeFailureNature get nature;
  RuntimeFailureLocation get location;
  RuntimeFailureContext get context;
}

class RuntimeFailure implements RuntimeFailureBase {
  const RuntimeFailure({
    required this.code,
    required this.origin,
    required this.kind,
    required this.nature,
    required this.location,
    required this.context,
  });

  factory RuntimeFailure.unknown({String code = 'CLOUD.SYSTEM.unknown_error'}) {
    return RuntimeFailure(
      code: code,
      origin: RuntimeFailureOrigin.system,
      kind: RuntimeFailureKind.internal,
      nature: RuntimeFailureNature.bug,
      location: const RuntimeFailureLocation.unknown(),
      context: const RuntimeFailureContext(),
    );
  }

  factory RuntimeFailure.fromJson(Map<String, dynamic> json) {
    return RuntimeFailure(
      code: ((json['code'] as String?) ?? 'CLOUD.SYSTEM.unknown_error').trim(),
      origin: _enumByName(
        RuntimeFailureOrigin.values,
        json['origin'],
        RuntimeFailureOrigin.system,
      ),
      kind: _enumByName(
        RuntimeFailureKind.values,
        json['kind'],
        RuntimeFailureKind.internal,
      ),
      nature: _enumByName(
        RuntimeFailureNature.values,
        json['nature'],
        RuntimeFailureNature.bug,
      ),
      location: RuntimeFailureLocation.fromJson(
        (json['location'] as Map?)?.cast<String, dynamic>(),
      ),
      context: RuntimeFailureContext.fromJson(
        (json['context'] as Map?)?.cast<String, dynamic>(),
      ).normalized(),
    );
  }

  @override
  final String code;
  @override
  final RuntimeFailureOrigin origin;
  @override
  final RuntimeFailureKind kind;
  @override
  final RuntimeFailureNature nature;
  @override
  final RuntimeFailureLocation location;
  @override
  final RuntimeFailureContext context;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'code': code,
      'origin': origin.name,
      'kind': kind.name,
      'nature': nature.name,
      'location': location.toJson(),
      'context': context.toJson(),
    };
  }
}

T _enumByName<T extends Enum>(List<T> values, Object? raw, T fallback) {
  if (raw is! String) return fallback;
  for (final value in values) {
    if (value.name == raw.trim()) return value;
  }
  return fallback;
}
