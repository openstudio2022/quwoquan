// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: fbc0dc8fe3b657727b15cc73a6bc3a67a04f0f1f452c9c4f9c8d8e81cb6b7855

library;

import '../operation_request_payload.dart';

part '../generated/requests/ops/ops_operation_contracts.g.requests.g.dart';

enum AppReleaseUpdateState {
  none("none"),
  available("available"),
  required("required");

  const AppReleaseUpdateState(this.wireName);

  final String wireName;

  static AppReleaseUpdateState fromWire(Object? value, String path) {
    return switch (value) {
      "none" => AppReleaseUpdateState.none,
      "available" => AppReleaseUpdateState.available,
      "required" => AppReleaseUpdateState.required,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum StartupRecoveryAction {
  none("none"),
  openUpdate("open_update"),
  openWeb("open_web"),
  externalReturn("external_return"),
  runtimeReentry("runtime_reentry");

  const StartupRecoveryAction(this.wireName);

  final String wireName;

  static StartupRecoveryAction fromWire(Object? value, String path) {
    return switch (value) {
      "none" => StartupRecoveryAction.none,
      "open_update" => StartupRecoveryAction.openUpdate,
      "open_web" => StartupRecoveryAction.openWeb,
      "external_return" => StartupRecoveryAction.externalReturn,
      "runtime_reentry" => StartupRecoveryAction.runtimeReentry,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum StartupRecoveryLifecycle {
  enter("enter"),
  phaseChange("phase_change"),
  externalAction("external_action"),
  runtimeReentry("runtime_reentry"),
  exit("exit"),
  failure("failure");

  const StartupRecoveryLifecycle(this.wireName);

  final String wireName;

  static StartupRecoveryLifecycle fromWire(Object? value, String path) {
    return switch (value) {
      "enter" => StartupRecoveryLifecycle.enter,
      "phase_change" => StartupRecoveryLifecycle.phaseChange,
      "external_action" => StartupRecoveryLifecycle.externalAction,
      "runtime_reentry" => StartupRecoveryLifecycle.runtimeReentry,
      "exit" => StartupRecoveryLifecycle.exit,
      "failure" => StartupRecoveryLifecycle.failure,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum StartupRecoveryMount {
  bootstrap("bootstrap"),
  runtimeBoundary("runtime_boundary"),
  safeShell("safe_shell"),
  routerError("router_error");

  const StartupRecoveryMount(this.wireName);

  final String wireName;

  static StartupRecoveryMount fromWire(Object? value, String path) {
    return switch (value) {
      "bootstrap" => StartupRecoveryMount.bootstrap,
      "runtime_boundary" => StartupRecoveryMount.runtimeBoundary,
      "safe_shell" => StartupRecoveryMount.safeShell,
      "router_error" => StartupRecoveryMount.routerError,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum StartupRecoveryPhase {
  startupChecking("startup_checking"),
  startupUpdateRequired("startup_update_required"),
  startupWebOnly("startup_web_only"),
  startupLatest("startup_latest"),
  startupVersionUnavailable("startup_version_unavailable"),
  runtimeUnavailable("runtime_unavailable"),
  runtimeReentering("runtime_reentering"),
  runtimeVersionChecking("runtime_version_checking"),
  runtimeUpdateRequired("runtime_update_required"),
  runtimeWebOnly("runtime_web_only"),
  runtimeLatest("runtime_latest"),
  runtimeVersionUnavailable("runtime_version_unavailable");

  const StartupRecoveryPhase(this.wireName);

  final String wireName;

  static StartupRecoveryPhase fromWire(Object? value, String path) {
    return switch (value) {
      "startup_checking" => StartupRecoveryPhase.startupChecking,
      "startup_update_required" => StartupRecoveryPhase.startupUpdateRequired,
      "startup_web_only" => StartupRecoveryPhase.startupWebOnly,
      "startup_latest" => StartupRecoveryPhase.startupLatest,
      "startup_version_unavailable" =>
        StartupRecoveryPhase.startupVersionUnavailable,
      "runtime_unavailable" => StartupRecoveryPhase.runtimeUnavailable,
      "runtime_reentering" => StartupRecoveryPhase.runtimeReentering,
      "runtime_version_checking" => StartupRecoveryPhase.runtimeVersionChecking,
      "runtime_update_required" => StartupRecoveryPhase.runtimeUpdateRequired,
      "runtime_web_only" => StartupRecoveryPhase.runtimeWebOnly,
      "runtime_latest" => StartupRecoveryPhase.runtimeLatest,
      "runtime_version_unavailable" =>
        StartupRecoveryPhase.runtimeVersionUnavailable,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum StartupRecoverySurface {
  pageAppStartupRecovery("page.app.startup_recovery");

  const StartupRecoverySurface(this.wireName);

  final String wireName;

  static StartupRecoverySurface fromWire(Object? value, String path) {
    return switch (value) {
      "page.app.startup_recovery" =>
        StartupRecoverySurface.pageAppStartupRecovery,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum VisitTargetType {
  page("page"),
  post("post"),
  circle("circle"),
  user("user");

  const VisitTargetType(this.wireName);

  final String wireName;

  static VisitTargetType fromWire(Object? value, String path) {
    return switch (value) {
      "page" => VisitTargetType.page,
      "post" => VisitTargetType.post,
      "circle" => VisitTargetType.circle,
      "user" => VisitTargetType.user,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class AppReleaseRecoveryView {
  const AppReleaseRecoveryView({
    required this.platform,
    required this.latestVersion,
    required this.latestBuild,
    required this.minimumSupportedVersion,
    required this.minimumSupportedBuild,
    required this.updateState,
    this.updateUrl,
    required this.recoveryUrl,
  });

  final String platform;
  final String latestVersion;
  final String latestBuild;
  final String minimumSupportedVersion;
  final String minimumSupportedBuild;
  final AppReleaseUpdateState updateState;
  final String? updateUrl;
  final String recoveryUrl;

  factory AppReleaseRecoveryView.fromWire(
    Map<String, Object?> map, [
    String path = "AppReleaseRecoveryView",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "platform",
      "latestVersion",
      "latestBuild",
      "minimumSupportedVersion",
      "minimumSupportedBuild",
      "updateState",
      "updateUrl",
      "recoveryUrl",
    }, path);
    return AppReleaseRecoveryView(
      platform: _requiredString(map["platform"], '$path.platform'),
      latestVersion: _requiredString(
        map["latestVersion"],
        '$path.latestVersion',
      ),
      latestBuild: _requiredString(map["latestBuild"], '$path.latestBuild'),
      minimumSupportedVersion: _requiredString(
        map["minimumSupportedVersion"],
        '$path.minimumSupportedVersion',
      ),
      minimumSupportedBuild: _requiredString(
        map["minimumSupportedBuild"],
        '$path.minimumSupportedBuild',
      ),
      updateState: AppReleaseUpdateState.fromWire(
        map["updateState"],
        '$path.updateState',
      ),
      updateUrl: map["updateUrl"] == null
          ? null
          : _requiredString(map["updateUrl"], '$path.updateUrl'),
      recoveryUrl: _requiredString(map["recoveryUrl"], '$path.recoveryUrl'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "platform": platform,
    "latestVersion": latestVersion,
    "latestBuild": latestBuild,
    "minimumSupportedVersion": minimumSupportedVersion,
    "minimumSupportedBuild": minimumSupportedBuild,
    "updateState": updateState.wireName,
    if (updateUrl != null) "updateUrl": updateUrl!,
    "recoveryUrl": recoveryUrl,
  };
}

final class EventRecordBatchReceipt {
  const EventRecordBatchReceipt({
    required this.acceptedCount,
    required this.duplicateBatch,
  });

  final int acceptedCount;
  final bool duplicateBatch;

  factory EventRecordBatchReceipt.fromWire(
    Map<String, Object?> map, [
    String path = "EventRecordBatchReceipt",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "acceptedCount",
      "duplicateBatch",
    }, path);
    return EventRecordBatchReceipt(
      acceptedCount: _requiredInt(map["acceptedCount"], '$path.acceptedCount'),
      duplicateBatch: _requiredBool(
        map["duplicateBatch"],
        '$path.duplicateBatch',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "acceptedCount": acceptedCount,
    "duplicateBatch": duplicateBatch,
  };
}

final class RecordVisitReceipt {
  const RecordVisitReceipt({
    required this.targetType,
    required this.targetKey,
    required this.visitCount,
    required this.occurredAt,
    required this.replayed,
  });

  final VisitTargetType targetType;
  final String targetKey;
  final int visitCount;
  final DateTime occurredAt;
  final bool replayed;

  factory RecordVisitReceipt.fromWire(
    Map<String, Object?> map, [
    String path = "RecordVisitReceipt",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "targetType",
      "targetKey",
      "visitCount",
      "occurredAt",
      "replayed",
    }, path);
    return RecordVisitReceipt(
      targetType: VisitTargetType.fromWire(
        map["targetType"],
        '$path.targetType',
      ),
      targetKey: _requiredNonBlankString(map["targetKey"], '$path.targetKey'),
      visitCount: _requiredInt(map["visitCount"], '$path.visitCount'),
      occurredAt: _requiredTimestamp(map["occurredAt"], '$path.occurredAt'),
      replayed: _requiredBool(map["replayed"], '$path.replayed'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetType": targetType.wireName,
    "targetKey": targetKey,
    "visitCount": visitCount,
    "occurredAt": occurredAt.toUtc().toIso8601String(),
    "replayed": replayed,
  };
}

final class StartupTelemetryBatchReceipt {
  const StartupTelemetryBatchReceipt({
    required this.acceptedCount,
    required this.duplicateBatch,
  });

  final int acceptedCount;
  final bool duplicateBatch;

  factory StartupTelemetryBatchReceipt.fromWire(
    Map<String, Object?> map, [
    String path = "StartupTelemetryBatchReceipt",
  ]) {
    _rejectUnknownFields(map, const <String>{
      "acceptedCount",
      "duplicateBatch",
    }, path);
    return StartupTelemetryBatchReceipt(
      acceptedCount: _requiredInt(map["acceptedCount"], '$path.acceptedCount'),
      duplicateBatch: _requiredBool(
        map["duplicateBatch"],
        '$path.duplicateBatch',
      ),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "acceptedCount": acceptedCount,
    "duplicateBatch": duplicateBatch,
  };
}

AppReleaseRecoveryView decodeAppReleaseRecoveryView(Object? response) =>
    AppReleaseRecoveryView.fromWire(
      _requiredObject(response, "AppReleaseRecoveryView"),
      "AppReleaseRecoveryView",
    );

EventRecordBatchReceipt decodeEventRecordBatchReceipt(Object? response) =>
    EventRecordBatchReceipt.fromWire(
      _requiredObject(response, "EventRecordBatchReceipt"),
      "EventRecordBatchReceipt",
    );

RecordVisitReceipt decodeRecordVisitReceipt(Object? response) =>
    RecordVisitReceipt.fromWire(
      _requiredObject(response, "RecordVisitReceipt"),
      "RecordVisitReceipt",
    );

StartupTelemetryBatchReceipt decodeStartupTelemetryBatchReceipt(
  Object? response,
) => StartupTelemetryBatchReceipt.fromWire(
  _requiredObject(response, "StartupTelemetryBatchReceipt"),
  "StartupTelemetryBatchReceipt",
);

void decodeEmptyResponse(Object? response) {
  if (response != null) {
    throw const FormatException('empty response must not contain a body');
  }
}

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException(
      '$path contains unknown fields: ${unknown.join(', ')}',
    );
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}
