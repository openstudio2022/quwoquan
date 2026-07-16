import 'package:quwoquan_runtime_errors/src/runtime_failure_context.dart';
import 'package:quwoquan_runtime_errors/src/runtime_failure_location.dart';
import 'package:quwoquan_runtime_errors/src/runtime_recovery_directive.dart';

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
  String get semanticReason;
  int? get transportStatus;
  RuntimeFailureOrigin get origin;
  RuntimeFailureKind get kind;
  RuntimeFailureNature get nature;
  RuntimeFailureLocation get location;
  RuntimeFailureContext get context;
  RuntimeRecoveryDirective get recovery;
}

class RuntimeFailure implements RuntimeFailureBase {
  const RuntimeFailure({
    required this.code,
    this.semanticReason = '',
    this.transportStatus,
    required this.origin,
    required this.kind,
    required this.nature,
    required this.location,
    required this.context,
    this.recovery = const RuntimeRecoveryDirective.none(),
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
      semanticReason: ((json['semanticReason'] as String?) ?? '').trim(),
      transportStatus: _transportStatus(json['transportStatus']),
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
      recovery: RuntimeRecoveryDirective.fromJson(
        (json['recovery'] as Map?)?.cast<String, dynamic>(),
      ),
    );
  }

  @override
  final String code;
  @override
  final String semanticReason;
  @override
  final int? transportStatus;
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
  @override
  final RuntimeRecoveryDirective recovery;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'code': code,
      'semanticReason': semanticReason,
      if (transportStatus != null) 'transportStatus': transportStatus,
      'origin': origin.name,
      'kind': kind.name,
      'nature': nature.name,
      'location': location.toJson(),
      'context': context.toJson(),
      'recovery': recovery.toJson(),
    };
  }
}

int? _transportStatus(Object? raw) {
  final value = switch (raw) {
    int value => value,
    String value => int.tryParse(value.trim()),
    _ => null,
  };
  if (value == null || value < 100 || value > 599) return null;
  return value;
}

T _enumByName<T extends Enum>(List<T> values, Object? raw, T fallback) {
  if (raw is! String) return fallback;
  for (final value in values) {
    if (value.name == raw.trim()) return value;
  }
  return fallback;
}
