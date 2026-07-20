import 'dart:convert';

import 'package:quwoquan_app/core/observability/generated/runtime_log_catalog.g.dart';

enum RuntimeLogKind { deploy, runtime, access, event, exception, audit }

enum RuntimeLogSeverity { debug, info, warn, error }

extension RuntimeLogKindWire on RuntimeLogKind {
  String get wireName => name;
}

extension RuntimeLogSeverityWire on RuntimeLogSeverity {
  String get wireName => name.toUpperCase();
}

final class RuntimeLogAttributes {
  RuntimeLogAttributes(Iterable<MapEntry<String, String>> entries)
    : _values = _validate(entries);

  const RuntimeLogAttributes.empty() : _values = const <String, String>{};

  factory RuntimeLogAttributes.fromMap(Map<String, String> values) =>
      RuntimeLogAttributes(values.entries);

  final Map<String, String> _values;

  Map<String, String> toWire() => _values;

  static RuntimeLogAttributes fromWire(Map<String, Object?> values) {
    return RuntimeLogAttributes(
      values.entries.map((entry) {
        if (entry.value is! String) {
          throw ArgumentError.value(
            entry.value,
            'attributes.${entry.key}',
            '属性值必须是字符串',
          );
        }
        return MapEntry<String, String>(entry.key, entry.value! as String);
      }),
    );
  }

  static Map<String, String> _validate(
    Iterable<MapEntry<String, String>> entries,
  ) {
    final values = <String, String>{};
    for (final entry in entries) {
      final key = entry.key.trim();
      if (key.isEmpty ||
          key.length > RuntimeLogCatalog.maxAttributeKeyLength ||
          entry.value.length > RuntimeLogCatalog.maxAttributeValueLength ||
          _isForbiddenKey(key)) {
        throw ArgumentError.value(key, 'attributes', '包含不允许的日志属性');
      }
      values[key] = entry.value;
    }
    if (values.length > RuntimeLogCatalog.maxAttributes ||
        utf8.encode(jsonEncode(values)).length >
            RuntimeLogCatalog.maxAttributesBytes) {
      throw ArgumentError('日志属性数量或体积超出目录限制');
    }
    return Map<String, String>.unmodifiable(values);
  }

  static bool _isForbiddenKey(String key) {
    final normalized = key.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
    final blocked = <String>{
      ...RuntimeLogCatalog.forbiddenFields,
      ...RuntimeLogCatalog.forbiddenAttributeKeys,
      ...RuntimeLogCatalog.highCardinalityMetricKeys,
    };
    return blocked.any((candidate) {
      final value = candidate.toLowerCase().replaceAll(
        RegExp(r'[^a-z0-9]'),
        '',
      );
      return normalized == value ||
          (value != 'ip' && normalized.contains(value));
    });
  }
}

final class RuntimeLogResource {
  const RuntimeLogResource({
    required this.sourceType,
    required this.environment,
    required this.service,
    this.component = '',
    this.appVersion = '',
    this.serviceVersion = '',
  });

  final String sourceType;
  final String environment;
  final String service;
  final String component;
  final String appVersion;
  final String serviceVersion;

  Map<String, String> toWire() => <String, String>{
    'sourceType': sourceType,
    'service': service,
    if (environment.isNotEmpty) 'environment': environment,
    if (component.isNotEmpty) 'component': component,
    if (appVersion.isNotEmpty) 'appVersion': appVersion,
    if (serviceVersion.isNotEmpty) 'service.version': serviceVersion,
  };

  static RuntimeLogResource fromWire(Map<String, Object?> values) =>
      RuntimeLogResource(
        sourceType: values['sourceType']?.toString() ?? '',
        environment: values['environment']?.toString() ?? '',
        service: values['service']?.toString() ?? '',
        component: values['component']?.toString() ?? '',
        appVersion: values['appVersion']?.toString() ?? '',
        serviceVersion: values['service.version']?.toString() ?? '',
      );
}

final class RuntimeLogCorrelation {
  const RuntimeLogCorrelation({
    this.requestId = '',
    this.traceId = '',
    this.spanId = '',
    this.operationId = '',
    this.pageName = '',
    this.surfaceId = '',
    this.executionId = '',
    this.workPackageId = '',
    this.environmentRunId = '',
  });

  final String requestId;
  final String traceId;
  final String spanId;
  final String operationId;
  final String pageName;
  final String surfaceId;
  final String executionId;
  final String workPackageId;
  final String environmentRunId;

  Map<String, String> toWire() => <String, String>{
    if (requestId.isNotEmpty) 'requestId': requestId,
    if (traceId.isNotEmpty) 'traceId': traceId,
    if (spanId.isNotEmpty) 'spanId': spanId,
    if (operationId.isNotEmpty) 'operationId': operationId,
    if (pageName.isNotEmpty) 'pageName': pageName,
    if (surfaceId.isNotEmpty) 'surfaceId': surfaceId,
    if (executionId.isNotEmpty) 'executionId': executionId,
    if (workPackageId.isNotEmpty) 'workPackageId': workPackageId,
    if (environmentRunId.isNotEmpty) 'environmentRunId': environmentRunId,
  };

  static RuntimeLogCorrelation fromWire(Map<String, Object?> values) =>
      RuntimeLogCorrelation(
        requestId: values['requestId']?.toString() ?? '',
        traceId: values['traceId']?.toString() ?? '',
        spanId: values['spanId']?.toString() ?? '',
        operationId: values['operationId']?.toString() ?? '',
        pageName: values['pageName']?.toString() ?? '',
        surfaceId: values['surfaceId']?.toString() ?? '',
        executionId: values['executionId']?.toString() ?? '',
        workPackageId: values['workPackageId']?.toString() ?? '',
        environmentRunId: values['environmentRunId']?.toString() ?? '',
      );
}

final class RuntimeLogRecord {
  RuntimeLogRecord({
    required this.recordId,
    required this.occurredAt,
    required this.observedAt,
    required this.kind,
    required this.severity,
    required this.signal,
    required this.message,
    required this.resource,
    required this.correlation,
    this.step = '',
    this.event = '',
    this.result = '',
    this.method = '',
    this.route = '',
    this.status = '',
    this.durationMs,
    this.action = '',
    this.target = '',
    this.errorCode = '',
    this.fingerprint = '',
    this.attributes = const RuntimeLogAttributes.empty(),
  }) {
    if (!RuntimeLogCatalog.logKinds.contains(kind.wireName)) {
      throw ArgumentError.value(kind, 'kind', '不在日志目录中');
    }
    if (!RuntimeLogCatalog.severityLevels.contains(severity.wireName)) {
      throw ArgumentError.value(severity, 'severity', '不在日志级别闭集中');
    }
    if (!RuntimeLogCatalog.signals.contains(signal)) {
      throw ArgumentError.value(signal, 'signal', '未登记日志信号');
    }
    if (RuntimeLogCatalog.signalKinds[signal] != kind.wireName) {
      throw ArgumentError.value(signal, 'signal', '与日志类型不匹配');
    }
    final signalContract = RuntimeLogCatalog.signalRegistry[signal];
    if (signalContract == null ||
        attributes.toWire().keys.any(
          (key) => !signalContract.attributeAllowlist.contains(key),
        )) {
      throw ArgumentError.value(
        attributes.toWire(),
        'attributes',
        '包含未在 signal 目录登记的属性',
      );
    }
    final correlationKeys = correlation.toWire().keys;
    if (correlationKeys.any(
      (key) => !signalContract.correlationKeys.contains(key),
    )) {
      throw ArgumentError.value(
        correlation.toWire(),
        'correlation',
        '包含未在 signal 目录登记的关联键',
      );
    }
    if (resource.sourceType.trim().isEmpty || resource.service.trim().isEmpty) {
      throw ArgumentError('日志 resource 必须提供 sourceType 与 service');
    }
    if (utf8.encode(message).length > RuntimeLogCatalog.maxMessageBytes) {
      throw ArgumentError.value(message, 'message', '超过日志消息长度限制');
    }
    switch (kind) {
      case RuntimeLogKind.deploy:
        if (step.isEmpty || result.isEmpty) {
          throw ArgumentError('deploy 日志必须提供 step 与 result');
        }
        break;
      case RuntimeLogKind.runtime:
      case RuntimeLogKind.event:
        if (event.isEmpty || result.isEmpty) {
          throw ArgumentError('${kind.wireName} 日志必须提供 event 与 result');
        }
        break;
      case RuntimeLogKind.access:
        if (method.isEmpty ||
            route.isEmpty ||
            status.isEmpty ||
            durationMs == null ||
            durationMs! < 0) {
          throw ArgumentError('access 日志字段不完整');
        }
        break;
      case RuntimeLogKind.exception:
        if (errorCode.isEmpty) {
          throw ArgumentError('exception 日志必须提供 errorCode');
        }
        break;
      case RuntimeLogKind.audit:
        if (action.isEmpty || target.isEmpty || result.isEmpty) {
          throw ArgumentError('audit 日志字段不完整');
        }
        break;
    }
  }

  final String recordId;
  final DateTime occurredAt;
  final DateTime observedAt;
  final RuntimeLogKind kind;
  final RuntimeLogSeverity severity;
  final String signal;
  final String message;
  final RuntimeLogResource resource;
  final RuntimeLogCorrelation correlation;
  final String step;
  final String event;
  final String result;
  final String method;
  final String route;
  final String status;
  final int? durationMs;
  final String action;
  final String target;
  final String errorCode;
  final String fingerprint;
  final RuntimeLogAttributes attributes;

  Map<String, Object?> toWire() => <String, Object?>{
    'schema': RuntimeLogCatalog.schema,
    'recordId': recordId,
    'occurredAt': occurredAt.toUtc().toIso8601String(),
    'observedAt': observedAt.toUtc().toIso8601String(),
    'logKind': kind.wireName,
    'severity': severity.wireName,
    'signal': signal,
    'message': message,
    'resource': resource.toWire(),
    if (correlation.toWire().isNotEmpty) 'correlation': correlation.toWire(),
    if (step.isNotEmpty) 'step': step,
    if (event.isNotEmpty) 'event': event,
    if (result.isNotEmpty) 'result': result,
    if (method.isNotEmpty) 'method': method,
    if (route.isNotEmpty) 'route': route,
    if (status.isNotEmpty) 'status': status,
    if (durationMs != null) 'durationMs': durationMs,
    if (action.isNotEmpty) 'action': action,
    if (target.isNotEmpty) 'target': target,
    if (errorCode.isNotEmpty) 'errorCode': errorCode,
    if (fingerprint.isNotEmpty) 'fingerprint': fingerprint,
    if (attributes.toWire().isNotEmpty) 'attributes': attributes.toWire(),
  };

  String encode() => jsonEncode(toWire());

  static RuntimeLogRecord fromWire(Map<String, Object?> wire) {
    if (wire['schema'] != RuntimeLogCatalog.schema) {
      throw ArgumentError.value(wire['schema'], 'schema', '日志标准不匹配');
    }
    for (final required in RuntimeLogCatalog.envelopeRequiredFields) {
      final value = wire[required];
      if (value == null || (value is String && value.trim().isEmpty)) {
        throw ArgumentError.value(required, 'wire', '缺少必填日志字段');
      }
    }
    final unknown = wire.keys.where(
      (field) =>
          !RuntimeLogCatalog.envelopeRequiredFields.contains(field) &&
          !RuntimeLogCatalog.envelopeOptionalFields.contains(field),
    );
    if (unknown.isNotEmpty) {
      throw ArgumentError.value(unknown.join(','), 'wire', '包含未登记日志字段');
    }
    for (final forbidden in RuntimeLogCatalog.forbiddenFields) {
      if (wire.containsKey(forbidden)) {
        throw ArgumentError.value(forbidden, 'wire', '包含禁止日志字段');
      }
    }
    final resourceValue = wire['resource'];
    if (resourceValue is! Map) {
      throw ArgumentError.value(resourceValue, 'resource', '必须是对象');
    }
    final correlationValue = wire['correlation'];
    final attributesValue = wire['attributes'];
    _assertKnownNestedFields(
      resourceValue,
      RuntimeLogCatalog.resourceRequiredFields.toSet()
        ..addAll(RuntimeLogCatalog.resourceOptionalFields),
      'resource',
    );
    if (correlationValue is Map) {
      _assertKnownNestedFields(
        correlationValue,
        RuntimeLogCatalog.correlationOptionalFields,
        'correlation',
      );
    }
    final occurredAt = DateTime.tryParse(wire['occurredAt']?.toString() ?? '');
    final observedAt = DateTime.tryParse(wire['observedAt']?.toString() ?? '');
    final kind = _parseKind(wire['logKind']);
    final severity = _parseSeverity(wire['severity']);
    if (occurredAt == null ||
        observedAt == null ||
        kind == null ||
        severity == null) {
      throw ArgumentError('日志时间、类型或级别无效');
    }
    return RuntimeLogRecord(
      recordId: wire['recordId']?.toString() ?? '',
      occurredAt: occurredAt.toUtc(),
      observedAt: observedAt.toUtc(),
      kind: kind,
      severity: severity,
      signal: wire['signal']?.toString() ?? '',
      message: wire['message']?.toString() ?? '',
      resource: RuntimeLogResource.fromWire(
        resourceValue.cast<String, Object?>(),
      ),
      correlation: correlationValue is Map
          ? RuntimeLogCorrelation.fromWire(
              correlationValue.cast<String, Object?>(),
            )
          : const RuntimeLogCorrelation(),
      step: wire['step']?.toString() ?? '',
      event: wire['event']?.toString() ?? '',
      result: wire['result']?.toString() ?? '',
      method: wire['method']?.toString() ?? '',
      route: wire['route']?.toString() ?? '',
      status: wire['status']?.toString() ?? '',
      durationMs: _asInt(wire['durationMs']),
      action: wire['action']?.toString() ?? '',
      target: wire['target']?.toString() ?? '',
      errorCode: wire['errorCode']?.toString() ?? '',
      fingerprint: wire['fingerprint']?.toString() ?? '',
      attributes: attributesValue is Map
          ? RuntimeLogAttributes.fromWire(
              attributesValue.cast<String, Object?>(),
            )
          : const RuntimeLogAttributes.empty(),
    );
  }

  static RuntimeLogKind? _parseKind(Object? value) {
    final text = value?.toString() ?? '';
    for (final kind in RuntimeLogKind.values) {
      if (kind.wireName == text) return kind;
    }
    return null;
  }

  static RuntimeLogSeverity? _parseSeverity(Object? value) {
    final text = value?.toString() ?? '';
    for (final severity in RuntimeLogSeverity.values) {
      if (severity.wireName == text) return severity;
    }
    return null;
  }

  static int? _asInt(Object? value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }

  static void _assertKnownNestedFields(
    Map value,
    Set<String> allowed,
    String field,
  ) {
    for (final key in value.keys) {
      if (key is! String || !allowed.contains(key)) {
        throw ArgumentError.value(key, field, '包含未登记字段');
      }
    }
  }
}
