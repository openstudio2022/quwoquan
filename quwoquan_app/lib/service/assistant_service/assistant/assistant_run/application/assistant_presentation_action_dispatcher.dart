import 'dart:collection';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/errors/generated/assistant/assistant_errors.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum AssistantActionIntentRejection {
  unknownKind,
  invalidShape,
  expired,
  digestMismatch,
  targetMismatch,
  replay,
}

final class AssistantActionIntentRejected implements Exception {
  const AssistantActionIntentRejected(this.reason);

  final AssistantActionIntentRejection reason;

  @override
  String toString() => 'AssistantActionIntentRejected(${reason.name})';
}

/// App-side fail-closed consumer for the closed ActionIntent union.
///
/// Validation is intentionally repeated at the client boundary: malformed,
/// expired, digest-mismatched, target-mismatched, or replayed intents must not
/// reach navigation, input, approval, or device execution ports.
final class AssistantActionIntentConsumer {
  AssistantActionIntentConsumer({DateTime Function()? clock})
    : _clock = clock ?? _systemUtcNow;

  static final RegExp _identifier = RegExp(
    r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$',
  );
  static final RegExp _digest = RegExp(r'^sha256:[0-9a-f]{64}$');
  static final RegExp _unsafeUri = RegExp(
    r'(?:javascript|data|file):',
    caseSensitive: false,
  );
  static final RegExp _rawHtml = RegExp(
    r'<\s*/?\s*[a-z][^>]*>',
    caseSensitive: false,
  );

  final DateTime Function() _clock;
  final Set<String> _consumedJtis = <String>{};

  AssistantActionIntentWire inspect(AssistantActionIntentWire action) {
    _validate(action);
    if (_consumedJtis.contains(action.jti.trim())) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.replay,
      );
    }
    return action;
  }

  void validateDeviceActionIntent(
    AssistantExecuteDeviceActionIntentWire intent,
  ) {
    if (!_validExecuteDeviceActionIntent(intent)) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.invalidShape,
      );
    }
  }

  AssistantActionIntentWire consume(
    AssistantActionIntentWire action, {
    String expectedRunId = '',
  }) {
    _validate(action);
    final normalizedExpectedRunId = expectedRunId.trim();
    final targetRunId = switch (action.kind) {
      'ApproveTool' => action.approveTool!.runId.trim(),
      'ExecuteDeviceAction' => action.executeDeviceAction!.runId.trim(),
      'ProvideInput' => action.provideInput!.runId.trim(),
      _ => '',
    };
    if (normalizedExpectedRunId.isNotEmpty &&
        targetRunId.isNotEmpty &&
        targetRunId != normalizedExpectedRunId) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.targetMismatch,
      );
    }
    if (!_consumedJtis.add(action.jti.trim())) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.replay,
      );
    }
    return action;
  }

  void _validate(AssistantActionIntentWire action) {
    final issuedAt = DateTime.tryParse(action.issuedAt);
    final expiresAt = DateTime.tryParse(action.expiresAt);
    final now = _clock().toUtc();
    if (!_identifier.hasMatch(action.intentId.trim()) ||
        !_identifier.hasMatch(action.jti.trim()) ||
        !_digest.hasMatch(action.requestDigest.trim()) ||
        issuedAt == null ||
        expiresAt == null ||
        !expiresAt.isAfter(issuedAt) ||
        expiresAt.difference(issuedAt) > const Duration(minutes: 5)) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.invalidShape,
      );
    }
    if (issuedAt.toUtc().isAfter(now) || !now.isBefore(expiresAt.toUtc())) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.expired,
      );
    }

    final subcontracts = <Object?>[
      action.navigate,
      action.approveTool,
      action.executeDeviceAction,
      action.provideInput,
    ].where((value) => value != null).length;
    if (subcontracts != 1) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.invalidShape,
      );
    }

    final Map<String, Object?> payload;
    switch (action.kind) {
      case 'Navigate':
        final value = action.navigate;
        if (value == null ||
            !_identifier.hasMatch(value.routeId.trim()) ||
            !_identifier.hasMatch(value.objectTypeRef.trim()) ||
            !_identifier.hasMatch(value.objectId.trim())) {
          throw const AssistantActionIntentRejected(
            AssistantActionIntentRejection.invalidShape,
          );
        }
        payload = value.toJson();
      case 'ApproveTool':
        final value = action.approveTool;
        if (value == null ||
            !_validRunToolTarget(value.runId, value.toolInvocationId) ||
            (value.decision != 'approved' && value.decision != 'rejected') ||
            !_identifier.hasMatch(value.capability.trim()) ||
            !_digest.hasMatch(value.inputDigest.trim()) ||
            !_validOpaquePermit(value.approvalPermit)) {
          throw const AssistantActionIntentRejected(
            AssistantActionIntentRejection.invalidShape,
          );
        }
        payload = value.toJson();
      case 'ExecuteDeviceAction':
        final value = action.executeDeviceAction;
        if (value == null || !_validExecuteDeviceActionIntent(value)) {
          throw const AssistantActionIntentRejected(
            AssistantActionIntentRejection.invalidShape,
          );
        }
        payload = value.toJson();
      case 'ProvideInput':
        final value = action.provideInput;
        if (value == null ||
            !_validRunToolTarget(value.runId, value.toolInvocationId) ||
            !_identifier.hasMatch(value.inputName.trim()) ||
            !_identifier.hasMatch(value.inputSchemaRef.trim()) ||
            !_validOpaquePermit(value.inputPermit)) {
          throw const AssistantActionIntentRejected(
            AssistantActionIntentRejection.invalidShape,
          );
        }
        payload = value.toJson();
      default:
        throw const AssistantActionIntentRejected(
          AssistantActionIntentRejection.unknownKind,
        );
    }

    if (_canonicalDigest(payload) != action.requestDigest.trim()) {
      throw const AssistantActionIntentRejected(
        AssistantActionIntentRejection.digestMismatch,
      );
    }
  }

  bool _validRunToolTarget(String runId, String toolInvocationId) =>
      _identifier.hasMatch(runId.trim()) &&
      _identifier.hasMatch(toolInvocationId.trim());

  bool _validExecuteDeviceActionIntent(
    AssistantExecuteDeviceActionIntentWire intent,
  ) =>
      _validRunToolTarget(intent.runId, intent.toolInvocationId) &&
      _identifier.hasMatch(intent.installationId.trim()) &&
      _identifier.hasMatch(intent.deviceId.trim()) &&
      _identifier.hasMatch(intent.capability.trim()) &&
      _digest.hasMatch(intent.inputDigest.trim()) &&
      _identifier.hasMatch(intent.idempotencyKey.trim()) &&
      _validOpaquePermit(intent.deviceActionPermit);

  bool _validOpaquePermit(String value) {
    final normalized = value.trim();
    return normalized.length >= 16 &&
        normalized.length <= 4096 &&
        !normalized.contains(RegExp(r'[\r\n\t ]')) &&
        !_unsafeUri.hasMatch(normalized) &&
        !_rawHtml.hasMatch(normalized);
  }
}

abstract interface class AssistantNavigateIntentHandler {
  bool canNavigate(AssistantNavigateIntentWire intent);

  Future<void> navigate(AssistantNavigateIntentWire intent);
}

abstract interface class AssistantProvideInputIntentHandler {
  bool canProvideInput(AssistantProvideInputIntentWire intent);

  Future<void> provideInput(AssistantProvideInputIntentWire intent);
}

final class AssistantDeviceActionExecutionResult {
  const AssistantDeviceActionExecutionResult({
    required this.outcome,
    required this.executedAt,
    this.deviceObjectId,
    this.failureCode,
  });

  final String outcome;
  final DateTime executedAt;
  final String? deviceObjectId;
  final String? failureCode;
}

abstract interface class AssistantDeviceActionExecutor {
  bool canExecute(AssistantExecuteDeviceActionIntentWire intent);

  Future<AssistantDeviceActionExecutionResult> execute(
    AssistantExecuteDeviceActionIntentWire intent,
  );
}

final class UnavailableAssistantNavigateIntentHandler
    implements AssistantNavigateIntentHandler {
  const UnavailableAssistantNavigateIntentHandler();

  @override
  bool canNavigate(AssistantNavigateIntentWire intent) => false;

  @override
  Future<void> navigate(AssistantNavigateIntentWire intent) =>
      Future<void>.error(
        UnsupportedError('Assistant Navigate intent handler is unavailable'),
      );
}

final class UnavailableAssistantProvideInputIntentHandler
    implements AssistantProvideInputIntentHandler {
  const UnavailableAssistantProvideInputIntentHandler();

  @override
  bool canProvideInput(AssistantProvideInputIntentWire intent) => false;

  @override
  Future<void> provideInput(AssistantProvideInputIntentWire intent) =>
      Future<void>.error(
        UnsupportedError(
          'Assistant ProvideInput intent handler is unavailable',
        ),
      );
}

/// Production remains fail-closed until the platform composition binds the
/// opaque permit to a concrete Device bridge request.
final class UnavailableAssistantDeviceActionExecutor
    implements AssistantDeviceActionExecutor {
  const UnavailableAssistantDeviceActionExecutor();

  @override
  bool canExecute(AssistantExecuteDeviceActionIntentWire intent) => false;

  @override
  Future<AssistantDeviceActionExecutionResult> execute(
    AssistantExecuteDeviceActionIntentWire intent,
  ) {
    return Future<AssistantDeviceActionExecutionResult>.value(
      AssistantDeviceActionExecutionResult(
        outcome: 'unavailable',
        executedAt: _systemUtcNow(),
        failureCode: AssistantErrorCode.deviceActionUnavailable.code,
      ),
    );
  }
}

final assistantNavigateIntentHandlerProvider =
    Provider<AssistantNavigateIntentHandler>(
      (ref) => const UnavailableAssistantNavigateIntentHandler(),
    );

final assistantProvideInputIntentHandlerProvider =
    Provider<AssistantProvideInputIntentHandler>(
      (ref) => const UnavailableAssistantProvideInputIntentHandler(),
    );

final assistantDeviceActionExecutorProvider =
    Provider<AssistantDeviceActionExecutor>(
      (ref) => const UnavailableAssistantDeviceActionExecutor(),
    );

bool isValidAssistantActionIntent(
  AssistantActionIntentWire action, {
  DateTime Function()? clock,
}) {
  try {
    AssistantActionIntentConsumer(clock: clock).inspect(action);
    return true;
  } on AssistantActionIntentRejected {
    return false;
  }
}

String assistantActionIntentRequestDigest(Map<String, Object?> payload) =>
    _canonicalDigest(payload);

String _canonicalDigest(Map<String, Object?> payload) {
  final encoded = jsonEncode(_canonicalJsonValue(payload));
  return 'sha256:${sha256.convert(utf8.encode(encoded))}';
}

Object? _canonicalJsonValue(Object? value) {
  if (value is Map) {
    final result = SplayTreeMap<String, Object?>();
    for (final entry in value.entries) {
      result[entry.key.toString()] = _canonicalJsonValue(entry.value);
    }
    return result;
  }
  if (value is Iterable) {
    return value.map(_canonicalJsonValue).toList(growable: false);
  }
  return value;
}

DateTime _systemUtcNow() => DateTime.now().toUtc();
